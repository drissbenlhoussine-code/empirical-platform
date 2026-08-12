"""Concrete PostgreSQL `PositionPlanRepository` adapter (MILESTONE-060)."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from typing import Any, cast

from empirical_platform.decision_candidate.market_data import Instrument
from empirical_platform.decision_candidate.position_plan import (
    PositionPlan,
    PositionPlanRejectionReason,
    PositionPlanStatus,
    PositionSizing,
)
from empirical_platform.identifiers.pairs import DomainIdentity
from empirical_platform.identifiers.types import PositionPlanId, TradePlanId
from empirical_platform.shared.contracts.repository import AggregateAlreadyExists, AggregateNotFound
from empirical_platform.shared.errors import FoundationError
from empirical_platform.shared.identifiers import RuntimeIdentifier
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService
from empirical_platform.shared.persistence.postgres_repositories._errors import (
    unique_violation_constraint_name,
)

_AGGREGATE_KIND = "PositionPlan"
_ROOT_UNIQUE_CONSTRAINTS = {"pk_position_plan", "uq_position_plan_governance_id"}


def _row_to_plan(row: Mapping[str, Any]) -> PositionPlan:
    sizing: PositionSizing | None = None
    if row["entry_price"] is not None:
        sizing = PositionSizing(
            entry_price=cast(Decimal, row["entry_price"]),
            stop_price=cast(Decimal, row["stop_price"]),
            risk_per_unit=cast(Decimal, row["risk_per_unit"]),
            allowed_risk_amount=cast(Decimal, row["allowed_risk_amount"]),
            maximum_notional=cast(Decimal, row["maximum_notional"]),
            risk_based_quantity=int(row["risk_based_quantity"]),
            capital_based_quantity=int(row["capital_based_quantity"]),
            quantity=int(row["quantity"]),
            position_notional=cast(Decimal, row["position_notional"]),
            actual_risk=cast(Decimal, row["actual_risk"]),
        )
    return PositionPlan(
        identity=DomainIdentity(
            governance_id=PositionPlanId(str(row["governance_id"])),
            runtime_id=RuntimeIdentifier(str(row["runtime_id"])),
        ),
        source_trade_plan_id=TradePlanId(str(row["source_trade_plan_governance_id"])),
        instrument=Instrument(str(row["instrument_symbol"])),
        policy_id=str(row["policy_id"]),
        policy_version=str(row["policy_version"]),
        policy_maximum_risk_percent=cast(Decimal, row["policy_maximum_risk_percent"]),
        policy_maximum_notional_percent=cast(Decimal, row["policy_maximum_notional_percent"]),
        policy_allow_fractional_shares=bool(row["policy_allow_fractional_shares"]),
        supplied_account_equity=cast(Decimal, row["supplied_account_equity"]),
        supplied_risk_percent=cast(Decimal, row["supplied_risk_percent"]),
        status=PositionPlanStatus(str(row["status"])),
        sizing=sizing,
        reasons=tuple(PositionPlanRejectionReason(reason) for reason in row["reasons"]),
    )


class PostgresPositionPlanRepository:
    """Concrete, storage-aware `PositionPlanRepository` implementation."""

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def get(self, identity: DomainIdentity[PositionPlanId]) -> PositionPlan:
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM position_plan "
                "WHERE runtime_id = :runtime_id AND governance_id = :governance_id",
                {
                    "runtime_id": str(identity.runtime_id),
                    "governance_id": str(identity.governance_id),
                },
            )
            if not rows:
                raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=identity)
            plan = _row_to_plan(rows[0])
        return plan

    def get_by_governance_id(self, governance_id: PositionPlanId) -> PositionPlan:
        """MILESTONE-072. Load a PositionPlan by governance id alone."""
        with self._service.unit_of_work() as work:
            rows = work.execute(
                "SELECT * FROM position_plan WHERE governance_id = :governance_id",
                {"governance_id": str(governance_id)},
            )
            if not rows:
                raise AggregateNotFound(aggregate_kind=_AGGREGATE_KIND, identity=governance_id)
            plan = _row_to_plan(rows[0])
        return plan

    def add(self, plan: PositionPlan) -> None:
        identity = plan.identity
        sizing = plan.sizing
        with self._service.unit_of_work() as work:
            try:
                work.execute(
                    "INSERT INTO position_plan "
                    "(runtime_id, governance_id, source_trade_plan_governance_id, "
                    "instrument_symbol, policy_id, policy_version, "
                    "policy_maximum_risk_percent, policy_maximum_notional_percent, "
                    "policy_allow_fractional_shares, supplied_account_equity, "
                    "supplied_risk_percent, status, reasons, entry_price, stop_price, "
                    "risk_per_unit, allowed_risk_amount, maximum_notional, "
                    "risk_based_quantity, capital_based_quantity, quantity, "
                    "position_notional, actual_risk) "
                    "VALUES (:runtime_id, :governance_id, :source_trade_plan_governance_id, "
                    ":instrument_symbol, :policy_id, :policy_version, "
                    ":policy_maximum_risk_percent, :policy_maximum_notional_percent, "
                    ":policy_allow_fractional_shares, :supplied_account_equity, "
                    ":supplied_risk_percent, :status, :reasons, :entry_price, :stop_price, "
                    ":risk_per_unit, :allowed_risk_amount, :maximum_notional, "
                    ":risk_based_quantity, :capital_based_quantity, :quantity, "
                    ":position_notional, :actual_risk)",
                    {
                        "runtime_id": str(identity.runtime_id),
                        "governance_id": str(identity.governance_id),
                        "source_trade_plan_governance_id": str(plan.source_trade_plan_id),
                        "instrument_symbol": str(plan.instrument),
                        "policy_id": plan.policy_id,
                        "policy_version": plan.policy_version,
                        "policy_maximum_risk_percent": plan.policy_maximum_risk_percent,
                        "policy_maximum_notional_percent": plan.policy_maximum_notional_percent,
                        "policy_allow_fractional_shares": plan.policy_allow_fractional_shares,
                        "supplied_account_equity": plan.supplied_account_equity,
                        "supplied_risk_percent": plan.supplied_risk_percent,
                        "status": plan.status.value,
                        "reasons": [reason.value for reason in plan.reasons],
                        "entry_price": sizing.entry_price if sizing else None,
                        "stop_price": sizing.stop_price if sizing else None,
                        "risk_per_unit": sizing.risk_per_unit if sizing else None,
                        "allowed_risk_amount": sizing.allowed_risk_amount if sizing else None,
                        "maximum_notional": sizing.maximum_notional if sizing else None,
                        "risk_based_quantity": sizing.risk_based_quantity if sizing else None,
                        "capital_based_quantity": sizing.capital_based_quantity if sizing else None,
                        "quantity": sizing.quantity if sizing else None,
                        "position_notional": sizing.position_notional if sizing else None,
                        "actual_risk": sizing.actual_risk if sizing else None,
                    },
                )
            except FoundationError as exc:
                constraint_name = unique_violation_constraint_name(exc)
                if constraint_name in _ROOT_UNIQUE_CONSTRAINTS:
                    raise AggregateAlreadyExists(
                        aggregate_kind=_AGGREGATE_KIND, identity=identity
                    ) from exc
                raise
