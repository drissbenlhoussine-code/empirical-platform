"""Append-only routed plan evidence; one durable claim precedes any broker write.

This engineering store is explicitly isolated from the Alpaca B/C migration chains.
The constructor requires its exact expected database comment, never a guessed name.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, ExitTriggerKind
from empirical_platform.decision_candidate.market_access_ports import (
    DispatchRecord,
    MarketHistoryEntry,
    PositionsSnapshot,
)
from empirical_platform.decision_candidate.market_identity import aware
from empirical_platform.decision_candidate.market_plan import (
    MarketPlan,
    OrderPurpose,
    OrderTruth,
    read_market_plan,
)
from empirical_platform.decision_candidate.operator_trading_configuration import (
    OperatorTradingConfiguration,
    configuration_fingerprint,
)
from empirical_platform.shared.config.settings import PostgreSQLConfigSnapshot
from empirical_platform.shared.persistence.database_safety import (
    IDENTITY_QUERY,
    TEST_IDENTITY,
    DatabaseSafetyError,
    require_test_connection,
)


def create_market_store(config: PostgreSQLConfigSnapshot, expected_identity: str) -> MarketStore:
    return MarketStore(create_engine(config.sqlalchemy_url()), expected_identity=expected_identity)


class MarketStore:
    def __init__(self, engine: Engine, *, expected_identity: str) -> None:
        if expected_identity != TEST_IDENTITY and not expected_identity.startswith(
            "PERSONAL_PAPER:MARKET_ACCESS:"
        ):
            raise DatabaseSafetyError("explicit separate market-access database identity required")
        self.engine = engine
        self.identity = expected_identity

    @contextmanager
    def transaction(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            row = connection.execute(text(IDENTITY_QUERY)).mappings().one()
            if row["identity"] != self.identity:
                raise DatabaseSafetyError("market-access database identity mismatch")
            if self.identity == TEST_IDENTITY:
                require_test_connection(connection)
            heads: Any = (
                connection.execute(text("SELECT version_num FROM alembic_version")).scalars().all()
            )
            if heads != ["ibkr_market_access_01"]:
                raise DatabaseSafetyError("market-access schema mismatch")
            yield connection


class MarketConfigurationRepository:
    """Implements the canonical configuration port, with canonical codecs injected."""

    requires_current_risk_contract = True

    def __init__(
        self,
        store: MarketStore,
        *,
        encode: Callable[[OperatorTradingConfiguration], dict[str, Any]],
        decode: Callable[[object], OperatorTradingConfiguration],
    ) -> None:
        self.store, self.encode, self.decode = store, encode, decode

    def save(self, configuration: OperatorTradingConfiguration) -> OperatorTradingConfiguration:
        configuration.__post_init__()
        if configuration.base_currency != "EUR" or configuration.risk_contract_version != 2:
            raise ValueError("EUR risk-v2 policy required")
        with self.store.transaction() as connection:
            connection.execute(
                text(
                    "INSERT INTO market_configuration VALUES "
                    "(:id,:version,:fp,CAST(:body AS jsonb)) ON CONFLICT DO "
                    "NOTHING"
                ),
                {
                    "id": configuration.configuration_governance_id,
                    "version": configuration.configuration_version,
                    "fp": configuration_fingerprint(configuration),
                    "body": json.dumps(self.encode(configuration)),
                },
            )
            row: Any = connection.execute(
                text(
                    "SELECT fingerprint FROM market_configuration WHERE "
                    "governance_id=:id AND version=:version"
                ),
                {
                    "id": configuration.configuration_governance_id,
                    "version": configuration.configuration_version,
                },
            ).scalar_one()
            if row != configuration_fingerprint(configuration):
                raise ValueError("configuration identity collision")
        return configuration

    def get(
        self, configuration_governance_id: str, configuration_version: int
    ) -> OperatorTradingConfiguration | None:
        with self.store.transaction() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT body,fingerprint FROM market_configuration "
                        "WHERE governance_id=:id AND version=:version"
                    ),
                    {"id": configuration_governance_id, "version": configuration_version},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            value = self.decode(row["body"])
            if configuration_fingerprint(value) != row["fingerprint"]:
                raise ValueError("configuration corruption")
            return value

    def latest(self, configuration_governance_id: str) -> OperatorTradingConfiguration | None:
        with self.store.transaction() as connection:
            version: Any = connection.execute(
                text("SELECT max(version) FROM market_configuration WHERE governance_id=:id"),
                {"id": configuration_governance_id},
            ).scalar_one()
        return None if version is None else self.get(configuration_governance_id, version)


class PostgresMarketJournal:
    def __init__(self, store: MarketStore) -> None:
        self.store = store

    def save_plan(self, plan: MarketPlan) -> None:
        plan.__post_init__()
        with self.store.transaction() as connection:
            fp: Any = connection.execute(
                text(
                    "SELECT fingerprint FROM market_configuration WHERE "
                    "governance_id=:id AND version=:version"
                ),
                {"id": plan.configuration_id, "version": plan.configuration_version},
            ).scalar_one()
            if fp != plan.configuration_fingerprint:
                raise ValueError("configuration fingerprint mismatch")
            connection.execute(
                text(
                    "INSERT INTO "
                    "market_plan(plan_id,fingerprint,body,configuration_id,configuration_version) "
                    "VALUES (:id,:fp,CAST(:body AS jsonb),:cfg,:version) ON "
                    "CONFLICT DO NOTHING"
                ),
                {
                    "id": plan.plan_id,
                    "fp": plan.fingerprint,
                    "body": json.dumps(plan.document()),
                    "cfg": plan.configuration_id,
                    "version": plan.configuration_version,
                },
            )
            if self._plan(connection, plan.plan_id) != plan:
                raise ValueError("immutable plan identity collision")

    @staticmethod
    def _plan(connection: Connection, plan_id: str) -> MarketPlan:
        row = (
            connection.execute(
                text("SELECT body,fingerprint FROM market_plan WHERE plan_id=:id"), {"id": plan_id}
            )
            .mappings()
            .one()
        )
        result = read_market_plan(row["body"])
        if result.fingerprint != row["fingerprint"] or result.plan_id != plan_id:
            raise ValueError("durable plan corruption")
        return result

    def get_plan(self, plan_id: str) -> MarketPlan:
        with self.store.transaction() as connection:
            return self._plan(connection, plan_id)

    def approve(self, plan_id: str, owner: str, fingerprint: str, now: datetime) -> ApprovedPlan:
        with self.store.transaction() as connection:
            result = self._plan(connection, plan_id).approve(owner, fingerprint, now)
            changed = connection.execute(
                text(
                    "UPDATE market_plan SET owner_id=:owner,approved_at=:now "
                    "WHERE plan_id=:id AND owner_id IS NULL RETURNING plan_id"
                ),
                {"id": plan_id, "owner": owner, "now": now},
            ).scalar_one_or_none()
            if changed is None:
                raise ValueError("plan already approved; approval cannot be replaced")
            return result

    def approval(self, plan_id: str) -> ApprovedPlan | None:
        with self.store.transaction() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT owner_id,approved_at,trigger_kind,triggered_at "
                        "FROM market_plan WHERE plan_id=:id"
                    ),
                    {"id": plan_id},
                )
                .mappings()
                .one()
            )
            if row["owner_id"] is None:
                return None
            plan = self._plan(connection, plan_id)
            value = plan.approve(row["owner_id"], plan.fingerprint, row["approved_at"])
            return replace(
                value,
                triggered_exit_kind=ExitTriggerKind(row["trigger_kind"])
                if row["trigger_kind"]
                else None,
                triggered_exit_at=row["triggered_at"],
            )

    def active_plans(self) -> tuple[MarketPlan, ...]:
        with self.store.transaction() as connection:
            ids: Any = (
                connection.execute(
                    text(
                        "SELECT plan_id FROM market_plan WHERE owner_id IS NOT "
                        "NULL AND closed_at IS NULL ORDER BY plan_id"
                    )
                )
                .scalars()
                .all()
            )
            return tuple(self._plan(connection, value) for value in ids)

    def history(self) -> tuple[MarketHistoryEntry, ...]:
        with self.store.transaction() as connection:
            rows = (
                connection.execute(
                    text(
                        "SELECT p.plan_id,p.closed_at,p.realized_price_pnl,"
                        "CASE WHEN p.closed_at IS NOT NULL THEN 'CLOSED' "
                        "ELSE COALESCE(d.state,'AWAITING_OWNER') END AS status FROM market_plan p "
                        "LEFT JOIN market_dispatch d ON p.plan_id=d.plan_id AND d.purpose='BUY' "
                        "ORDER BY p.plan_id LIMIT 500"
                    )
                )
                .mappings()
                .all()
            )
            return tuple(
                MarketHistoryEntry(
                    self._plan(connection, row["plan_id"]),
                    row["status"],
                    row["realized_price_pnl"],
                    row["closed_at"],
                )
                for row in rows
            )

    def claim_trigger(self, plan_id: str, kind: ExitTriggerKind, now: datetime) -> bool:
        aware(now)
        with self.store.transaction() as connection:
            return (
                connection.execute(
                    text(
                        "UPDATE market_plan SET "
                        "trigger_kind=:kind,triggered_at=:now WHERE "
                        "plan_id=:id AND owner_id IS NOT NULL AND trigger_kind "
                        "IS NULL AND closed_at IS NULL RETURNING plan_id"
                    ),
                    {"id": plan_id, "kind": kind.value, "now": now},
                ).scalar_one_or_none()
                is not None
            )

    def reserve(
        self,
        plan: MarketPlan,
        purpose: OrderPurpose,
        order_id: int,
        quantity: Decimal,
        limit_price: Decimal,
        now: datetime,
    ) -> DispatchRecord | None:
        aware(now)
        if (
            not 0 < quantity <= plan.risk.quantity
            or not limit_price.is_finite()
            or limit_price <= 0
        ):
            raise ValueError("invalid dispatch bounds")
        with self.store.transaction() as connection:
            # The singleton serializes all new entry claims, including different plans.
            engaged: Any = connection.execute(
                text("SELECT engaged FROM market_safety WHERE singleton FOR UPDATE")
            ).scalar_one()
            if self._plan(connection, plan.plan_id) != plan:
                raise ValueError("changed durable plan")
            approved = (
                connection.execute(
                    text(
                        "SELECT owner_id,trigger_kind,closed_at FROM market_plan WHERE plan_id=:id"
                    ),
                    {"id": plan.plan_id},
                )
                .mappings()
                .one()
            )
            if approved["owner_id"] is None or approved["closed_at"] is not None:
                raise ValueError("active Owner approval required")
            if purpose is OrderPurpose.ENTRY:
                if (
                    engaged
                    or not plan.created_at <= now < plan.approval_expires
                    or quantity != plan.risk.quantity
                    or limit_price != plan.risk.entry_ceiling
                ):
                    raise ValueError("entry authorization gate")
                occupied: Any = connection.execute(
                    text(
                        "SELECT count(*) FROM market_dispatch d JOIN "
                        "market_plan p USING(plan_id) WHERE d.purpose='BUY' "
                        "AND p.closed_at IS NULL"
                    )
                ).scalar_one()
                if occupied:
                    return None  # Includes UNKNOWN, rejected and unverified cancellations.
            elif purpose is OrderPurpose.CLOSE:
                if approved["trigger_kind"] is None:
                    raise ValueError("approved exit trigger required")
                entry = self._truth(connection, plan.plan_id, OrderPurpose.ENTRY)
                if (
                    entry is None
                    or entry.status not in ("FILLED", "CANCELED")
                    or entry.filled != quantity
                ):
                    raise ValueError("terminal attributable fill required before close")
            else:
                raise ValueError("unsupported purpose")
            reference = plan.order_reference(purpose)
            row = connection.execute(
                text(
                    "INSERT INTO market_dispatch VALUES "
                    "(:id,:purpose,:order,:ref,:q,:price,'CLAIMED',:now) ON "
                    "CONFLICT DO NOTHING RETURNING plan_id"
                ),
                {
                    "id": plan.plan_id,
                    "purpose": purpose.value,
                    "order": order_id,
                    "ref": reference,
                    "q": quantity,
                    "price": limit_price,
                    "now": now,
                },
            ).scalar_one_or_none()
            return (
                None
                if row is None
                else DispatchRecord(
                    plan.plan_id, purpose, order_id, reference, quantity, limit_price, "CLAIMED"
                )
            )

    def dispatch(self, plan_id: str, purpose: OrderPurpose) -> DispatchRecord | None:
        with self.store.transaction() as connection:
            row = (
                connection.execute(
                    text("SELECT * FROM market_dispatch WHERE plan_id=:id AND purpose=:purpose"),
                    {"id": plan_id, "purpose": purpose.value},
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            return DispatchRecord(
                plan_id,
                purpose,
                row["order_id"],
                row["reference"],
                row["quantity"],
                row["limit_price"],
                row["state"],
            )

    def observe(self, plan: MarketPlan, record: DispatchRecord, truth: OrderTruth | None) -> None:
        body = None
        if truth is not None:
            truth.require_matches(plan, record.purpose, record.order_id)
            if truth.quantity != record.quantity:
                raise ValueError("quantity changed at broker")
            body = json.dumps(asdict(truth), default=str)
        with self.store.transaction() as connection:
            previous = self._truth(connection, plan.plan_id, record.purpose)
            if previous is not None and truth is not None:
                if previous.permanent_id != truth.permanent_id or previous.filled > truth.filled:
                    raise ValueError("broker identity changed or cumulative fills regressed")
            connection.execute(
                text(
                    "INSERT INTO market_observation(plan_id,purpose,body) "
                    "VALUES (:id,:purpose,CAST(:body AS jsonb))"
                ),
                {"id": plan.plan_id, "purpose": record.purpose.value, "body": body},
            )
            connection.execute(
                text(
                    "UPDATE market_dispatch SET state=:state WHERE plan_id=:id AND purpose=:purpose"
                ),
                {
                    "id": plan.plan_id,
                    "purpose": record.purpose.value,
                    "state": truth.status if truth else "UNKNOWN",
                },
            )

    def _truth(
        self, connection: Connection, plan_id: str, purpose: OrderPurpose
    ) -> OrderTruth | None:
        body = connection.execute(
            text(
                "SELECT body FROM market_observation WHERE plan_id=:id AND "
                "purpose=:purpose ORDER BY sequence DESC LIMIT 1"
            ),
            {"id": plan_id, "purpose": purpose.value},
        ).scalar_one_or_none()
        if body is None:
            return None
        plan = self._plan(connection, plan_id)
        if (
            body.pop("instrument") != plan.document()["instrument"]
            or body.pop("account") != plan.document()["account"]
        ):
            raise ValueError("persisted observation route mismatch")
        body["purpose"] = OrderPurpose(body["purpose"])
        for field in ("quantity", "filled", "average_price"):
            body[field] = Decimal(body[field]) if body[field] is not None else None
        body["observed_at"] = datetime.fromisoformat(body["observed_at"])
        return OrderTruth(instrument=plan.instrument, account=plan.account, **body)

    def truth(self, plan_id: str, purpose: OrderPurpose) -> OrderTruth | None:
        with self.store.transaction() as connection:
            return self._truth(connection, plan_id, purpose)

    def close_verified(
        self,
        plan: MarketPlan,
        realized_price_pnl: Decimal,
        now: datetime,
        verification: PositionsSnapshot,
    ) -> None:
        aware(now)
        aware(verification.observed_at)
        if (
            verification.account != plan.account
            or verification.positions
            or not 0 <= (now - verification.observed_at).total_seconds() <= 30
        ):
            raise ValueError("fresh zero snapshot of the exact account required")
        if not realized_price_pnl.is_finite():
            raise ValueError("finite EUR price P&L required")
        with self.store.transaction() as connection:
            entry = self._truth(connection, plan.plan_id, OrderPurpose.ENTRY)
            exit_truth = self._truth(connection, plan.plan_id, OrderPurpose.CLOSE)
            if (
                entry is None
                or exit_truth is None
                or exit_truth.status != "FILLED"
                or entry.filled != exit_truth.filled
                or entry.average_price is None
                or exit_truth.average_price is None
            ):
                raise ValueError("full close evidence required")
            if (
                realized_price_pnl
                != (exit_truth.average_price - entry.average_price) * entry.filled
            ):
                raise ValueError("price P&L must match durable execution evidence")
            if verification.observed_at < exit_truth.observed_at:
                raise ValueError("zero verification must follow the confirmed exit fill")
            connection.execute(
                text(
                    "INSERT INTO market_zero_verification VALUES "
                    "(:id,:at,:account,:instrument,:permanent,0) ON CONFLICT DO NOTHING"
                ),
                {
                    "id": plan.plan_id,
                    "at": verification.observed_at,
                    "account": plan.account.reference,
                    "instrument": plan.instrument.fingerprint,
                    "permanent": exit_truth.permanent_id,
                },
            )
            connection.execute(
                text(
                    "UPDATE market_plan SET "
                    "closed_at=:now,realized_price_pnl=:pnl WHERE plan_id=:id "
                    "AND closed_at IS NULL"
                ),
                {"id": plan.plan_id, "now": now, "pnl": realized_price_pnl},
            )

    def entry_count(self, since: datetime) -> int:
        with self.store.transaction() as connection:
            return int(
                connection.execute(
                    text(
                        "SELECT count(*) FROM market_dispatch WHERE "
                        "purpose='BUY' AND created_at>=:since"
                    ),
                    {"since": since},
                ).scalar_one()
            )

    def kill_switch(self) -> bool:
        with self.store.transaction() as connection:
            return bool(
                connection.execute(
                    text("SELECT engaged FROM market_safety WHERE singleton")
                ).scalar_one()
            )

    def claim_cancel(self, record: DispatchRecord, now: datetime) -> bool:
        aware(now)
        with self.store.transaction() as connection:
            return (
                connection.execute(
                    text(
                        "INSERT INTO market_cancel_claim VALUES "
                        "(:id,:purpose,:now) ON CONFLICT DO NOTHING RETURNING "
                        "plan_id"
                    ),
                    {"id": record.plan_id, "purpose": record.purpose.value, "now": now},
                ).scalar_one_or_none()
                is not None
            )
