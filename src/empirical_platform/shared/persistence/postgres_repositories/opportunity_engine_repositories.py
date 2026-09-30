"""MILESTONE-090 persistence for the Opportunity Engine's two tables.

THE SAME DISCIPLINE AS EVERY OTHER MILESTONE'S POSTGRES MODULE: every SQL statement is a
literal constant (never interpolated), every persisted value is read fail-closed (a wrong type
is refused, never coerced), and `transition`/`save` map directly onto the database triggers
that enforce the SAME closed status-transition table and append-only rules the migration
installs -- this module trusts the database to refuse what it should refuse rather than
re-implementing that logic in Python and hoping the two never drift apart.

NO SCHEMA-HEAD GUARD HERE, DELIBERATELY. Unlike M085/M087/M089, this schema has no
`require_exact_m09X_schema_head` guard: these are research/read tables with no broker-write
path in this milestone (see `opportunity_engine_repositories.py`'s -- the domain ports module's
-- own docstring, and `external-review/MILESTONE-090/scope-and-design.md` Section 4).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from empirical_platform.decision_candidate.opportunity_engine import (
    MarketSessionState,
    OpportunityDecision,
    OpportunityStatus,
    OwnerOpportunityAction,
    RejectionReason,
    TradingOpportunity,
)
from empirical_platform.shared.errors.foundation import FoundationError, FoundationErrorCategory
from empirical_platform.shared.persistence.postgres import PostgresPersistenceService

__all__ = [
    "PostgresOpportunityDecisionRepository",
    "PostgresOpportunityEngineRuntime",
    "PostgresOpportunityRepository",
]

_OPERATION = "m090.row_mapping"


# ---------------------------------------------------------------------------
# Fail-closed readers
# ---------------------------------------------------------------------------


def _fail(field: str, value: object, expected: str) -> FoundationError:
    return FoundationError(
        category=FoundationErrorCategory.PERSISTENCE,
        message=(
            f"persisted MILESTONE-090 value {field} is {type(value).__name__}, not {expected}; "
            "refusing to coerce a malformed stored value"
        ),
        layer="persistence",
        operation=_OPERATION,
        context={"field": field, "actual_type": type(value).__name__},
    )


def _str(row: Mapping[str, Any], field: str) -> str:
    value = row[field]
    if not isinstance(value, str):
        raise _fail(field, value, "str")
    return value


def _optional_int(row: Mapping[str, Any], field: str) -> int | None:
    value = row[field]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _fail(field, value, "int or NULL")
    return int(value)


def _optional_decimal(row: Mapping[str, Any], field: str) -> Decimal | None:
    value = row[field]
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise _fail(field, value, "Decimal or NULL")
    return value


def _instant(row: Mapping[str, Any], field: str) -> datetime:
    value = row[field]
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise _fail(field, value, "timezone-aware datetime")
    return value


def _optional_instant(row: Mapping[str, Any], field: str) -> datetime | None:
    return None if row[field] is None else _instant(row, field)


def _strings(row: Mapping[str, Any], field: str) -> tuple[str, ...]:
    raw = _str(row, field)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as error:
        raise _fail(field, raw, "a JSON array of strings") from error
    if not isinstance(parsed, list) or any(not isinstance(item, str) for item in parsed):
        raise _fail(field, parsed, "a JSON array of strings")
    return tuple(parsed)


def _q(*parts: str) -> str:
    """Join literal fragments into one statement. Every fragment is a module-level constant."""
    return "".join(parts)


# ---------------------------------------------------------------------------
# Opportunity
# ---------------------------------------------------------------------------

_OPPORTUNITY_COLUMNS = (
    "opportunity_id, policy_fingerprint, symbol, generated_at, expires_at, evidence_as_of, "
    "session, bid, ask, spread_percent, entry_price, stop_price, target_price, "
    "risk_per_share, reward_per_share, reward_risk_ratio, quantity, notional, maximum_loss, "
    "mandatory_liquidation_at, structure_model_id, structure_model_version, evidence, "
    "quality_score, quality_model_id, quality_model_version, rejection_reasons, status"
)
_OPPORTUNITY_INSERT = _q(
    "INSERT INTO public.opportunity (",
    _OPPORTUNITY_COLUMNS,
    ") VALUES (:opportunity_id, :policy_fingerprint, :symbol, :generated_at, :expires_at, "
    ":evidence_as_of, :session, :bid, :ask, :spread_percent, :entry_price, :stop_price, "
    ":target_price, :risk_per_share, :reward_per_share, :reward_risk_ratio, :quantity, "
    ":notional, :maximum_loss, :mandatory_liquidation_at, :structure_model_id, "
    ":structure_model_version, :evidence, :quality_score, :quality_model_id, "
    ":quality_model_version, :rejection_reasons, :status) RETURNING ",
    _OPPORTUNITY_COLUMNS,
)
_OPPORTUNITY_BY_ID = _q(
    "SELECT ", _OPPORTUNITY_COLUMNS, " FROM public.opportunity WHERE opportunity_id = :key"
)
_OPPORTUNITY_LATEST_FOR_SYMBOL_TODAY = _q(
    "SELECT ",
    _OPPORTUNITY_COLUMNS,
    " FROM public.opportunity WHERE symbol = :symbol "
    "AND generated_at >= :session_start AND generated_at < :session_end "
    "ORDER BY generated_at DESC LIMIT 1",
)
_OPPORTUNITY_FOR_SESSION = _q(
    "SELECT ",
    _OPPORTUNITY_COLUMNS,
    " FROM public.opportunity WHERE generated_at >= :session_start AND generated_at < :session_end "
    "ORDER BY generated_at ASC, opportunity_id ASC",
)
_OPPORTUNITY_TRANSITION = _q(
    "UPDATE public.opportunity SET status = :status WHERE opportunity_id = :opportunity_id "
    "RETURNING ",
    _OPPORTUNITY_COLUMNS,
)


def _row_to_opportunity(row: Mapping[str, Any]) -> TradingOpportunity:
    return TradingOpportunity(
        opportunity_id=_str(row, "opportunity_id"),
        policy_fingerprint=_str(row, "policy_fingerprint"),
        symbol=_str(row, "symbol"),
        generated_at=_instant(row, "generated_at"),
        expires_at=_instant(row, "expires_at"),
        evidence_as_of=_instant(row, "evidence_as_of"),
        session=MarketSessionState(_str(row, "session")),
        bid=_optional_decimal(row, "bid"),
        ask=_optional_decimal(row, "ask"),
        spread_percent=_optional_decimal(row, "spread_percent"),
        entry_price=_optional_decimal(row, "entry_price"),
        stop_price=_optional_decimal(row, "stop_price"),
        target_price=_optional_decimal(row, "target_price"),
        risk_per_share=_optional_decimal(row, "risk_per_share"),
        reward_per_share=_optional_decimal(row, "reward_per_share"),
        reward_risk_ratio=_optional_decimal(row, "reward_risk_ratio"),
        quantity=_optional_int(row, "quantity"),
        notional=_optional_decimal(row, "notional"),
        maximum_loss=_optional_decimal(row, "maximum_loss"),
        mandatory_liquidation_at=_optional_instant(row, "mandatory_liquidation_at"),
        structure_model_id=_str(row, "structure_model_id"),
        structure_model_version=_str(row, "structure_model_version"),
        evidence=_strings(row, "evidence"),
        quality_score=_optional_decimal(row, "quality_score"),
        quality_model_id=_str(row, "quality_model_id"),
        quality_model_version=_str(row, "quality_model_version"),
        rejection_reasons=tuple(RejectionReason(r) for r in _strings(row, "rejection_reasons")),
        status=OpportunityStatus(_str(row, "status")),
    )


class PostgresOpportunityRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, opportunity: TradingOpportunity) -> TradingOpportunity:
        o = opportunity
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _OPPORTUNITY_INSERT,
                {
                    "opportunity_id": o.opportunity_id,
                    "policy_fingerprint": o.policy_fingerprint,
                    "symbol": o.symbol,
                    "generated_at": o.generated_at,
                    "expires_at": o.expires_at,
                    "evidence_as_of": o.evidence_as_of,
                    "session": o.session.value,
                    "bid": o.bid,
                    "ask": o.ask,
                    "spread_percent": o.spread_percent,
                    "entry_price": o.entry_price,
                    "stop_price": o.stop_price,
                    "target_price": o.target_price,
                    "risk_per_share": o.risk_per_share,
                    "reward_per_share": o.reward_per_share,
                    "reward_risk_ratio": o.reward_risk_ratio,
                    "quantity": o.quantity,
                    "notional": o.notional,
                    "maximum_loss": o.maximum_loss,
                    "mandatory_liquidation_at": o.mandatory_liquidation_at,
                    "structure_model_id": o.structure_model_id,
                    "structure_model_version": o.structure_model_version,
                    "evidence": json.dumps(list(o.evidence)),
                    "quality_score": o.quality_score,
                    "quality_model_id": o.quality_model_id,
                    "quality_model_version": o.quality_model_version,
                    "rejection_reasons": json.dumps([r.value for r in o.rejection_reasons]),
                    "status": o.status.value,
                },
            )
        return _row_to_opportunity(rows[0])

    def get(self, opportunity_id: str) -> TradingOpportunity | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_OPPORTUNITY_BY_ID, {"key": opportunity_id}))
        return _row_to_opportunity(rows[0]) if rows else None

    def latest_for_symbol_today(
        self, symbol: str, *, session_date: str
    ) -> TradingOpportunity | None:
        start = datetime.fromisoformat(f"{session_date}T00:00:00+00:00")
        end = datetime.fromisoformat(f"{session_date}T23:59:59.999999+00:00")
        with self._service.unit_of_work() as work:
            rows = list(
                work.execute(
                    _OPPORTUNITY_LATEST_FOR_SYMBOL_TODAY,
                    {"symbol": symbol, "session_start": start, "session_end": end},
                )
            )
        return _row_to_opportunity(rows[0]) if rows else None

    def list_for_session(self, session_date: str) -> tuple[TradingOpportunity, ...]:
        start = datetime.fromisoformat(f"{session_date}T00:00:00+00:00")
        end = datetime.fromisoformat(f"{session_date}T23:59:59.999999+00:00")
        with self._service.unit_of_work() as work:
            rows: Sequence[Mapping[str, Any]] = work.execute(
                _OPPORTUNITY_FOR_SESSION, {"session_start": start, "session_end": end}
            )
        return tuple(_row_to_opportunity(row) for row in rows)

    def transition(
        self, *, opportunity_id: str, target: OpportunityStatus, at: datetime
    ) -> TradingOpportunity:
        del at  # no separate transitioned_at column: `status` alone carries the current state
        if not isinstance(target, OpportunityStatus):
            raise ValueError("target must be an OpportunityStatus")
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _OPPORTUNITY_TRANSITION, {"opportunity_id": opportunity_id, "status": target.value}
            )
        if not rows:
            raise ValueError(f"no opportunity {opportunity_id!r} exists")
        return _row_to_opportunity(rows[0])


# ---------------------------------------------------------------------------
# Opportunity decision
# ---------------------------------------------------------------------------

_DECISION_COLUMNS = "decision_id, opportunity_id, action, decided_by, decided_at"
_DECISION_INSERT = _q(
    "INSERT INTO public.opportunity_decision (",
    _DECISION_COLUMNS,
    ") VALUES (:decision_id, :opportunity_id, :action, :decided_by, :decided_at) RETURNING ",
    _DECISION_COLUMNS,
)
_DECISION_FOR_OPPORTUNITY = _q(
    "SELECT ",
    _DECISION_COLUMNS,
    " FROM public.opportunity_decision WHERE opportunity_id = :key",
)


def _row_to_decision(row: Mapping[str, Any]) -> OpportunityDecision:
    return OpportunityDecision(
        decision_id=_str(row, "decision_id"),
        opportunity_id=_str(row, "opportunity_id"),
        action=OwnerOpportunityAction(_str(row, "action")),
        decided_by=_str(row, "decided_by"),
        decided_at=_instant(row, "decided_at"),
    )


class PostgresOpportunityDecisionRepository:
    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    def save(self, decision: OpportunityDecision) -> OpportunityDecision:
        d = decision
        with self._service.unit_of_work() as work:
            rows = work.execute(
                _DECISION_INSERT,
                {
                    "decision_id": d.decision_id,
                    "opportunity_id": d.opportunity_id,
                    "action": d.action.value,
                    "decided_by": d.decided_by,
                    "decided_at": d.decided_at,
                },
            )
        return _row_to_decision(rows[0])

    def for_opportunity(self, opportunity_id: str) -> OpportunityDecision | None:
        with self._service.unit_of_work() as work:
            rows = list(work.execute(_DECISION_FOR_OPPORTUNITY, {"key": opportunity_id}))
        return _row_to_decision(rows[0]) if rows else None


class PostgresOpportunityEngineRuntime:
    """The two MILESTONE-090 repositories over one caller-owned service."""

    __slots__ = ("_service",)

    def __init__(self, service: PostgresPersistenceService) -> None:
        self._service = service

    @property
    def opportunities(self) -> PostgresOpportunityRepository:
        return PostgresOpportunityRepository(self._service)

    @property
    def decisions(self) -> PostgresOpportunityDecisionRepository:
        return PostgresOpportunityDecisionRepository(self._service)
