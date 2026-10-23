"""RELEASE v1 -- external position closure: a position closed OUTSIDE this platform's own
exit pipeline (e.g. an Owner's manual broker-dashboard SELL), recorded durably so the
automatic Plan Manager stops retrying an exit that can never succeed, without ever claiming
the platform itself dispatched or verified a SELL.

WHY THIS IS A SEPARATE RECORD, NOT A `PositionExitAttempt`. `PositionExitAttempt`'s own
invariants (`decision_candidate/position_exit.py`) assume a dispatch THIS platform claimed
and submitted: its `client_order_id`/`authorization_id`/`broker_order_id` all trace back to
a preview and authorization this platform itself minted, and the database triggers in
`migrations_paper_exit` enforce that lineage. An externally-placed order has none of it, and
forcing one into `PositionExitAttempt`'s shape would either violate those invariants or
require fabricating a preview/authorization for a dispatch that never happened. This type is
the one place the pre-existing `ApprovedPlan` row and its trigger history
(`decision_candidate/approved_plan.py`) are deliberately left untouched -- see
`usecases.record_external_position_closure` for how a record here is gated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

__all__ = [
    "EXTERNAL_POSITION_CLOSURE_RECORDED_EVENT_TYPE",
    "ExternalPositionClosure",
    "external_position_closure_id",
]

_MAXIMUM_IDENTIFIER_LENGTH = 64

#: Fits `position_exit_event.event_type`'s existing `String(length=48)` column unchanged.
EXTERNAL_POSITION_CLOSURE_RECORDED_EVENT_TYPE = "EXTERNAL_POSITION_CLOSURE_RECORDED"


def _require_identifier(value: object, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_IDENTIFIER_LENGTH} characters")


def _require_aware(value: object, *, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"{field} must be a timezone-aware datetime")


def _require_whole_positive(value: object, *, field: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field} must be an int")
    if value <= 0:
        raise ValueError(f"{field} must be positive")


def external_position_closure_id(entry_intent_governance_id: str) -> str:
    """Deterministic: at most one closure record can ever exist per entry, by construction
    (both this id and the repository's own UNIQUE constraint on the entry column)."""
    return f"XEC-{entry_intent_governance_id}"


@dataclass(frozen=True, slots=True)
class ExternalPositionClosure:
    """ONE durable record: this entry's position was observed closed by a SELL the broker
    itself confirms, which this platform never dispatched. Append-only; never updated.

    Every field but `recorded_by`/`recorded_at` is evidence READ from the broker by
    `usecases.record_external_position_closure.RecordExternalPositionClosureHandler` at the
    moment of recording -- never asserted by the caller and never re-derived from
    `ApprovedPlan`. `recorded_by` identifies the human who ran the reconciliation (analogous
    to a manual exit's own `authorized_by`), but this type carries no authority to dispatch
    anything: see the handler's own docstring for why no SELL or BUY can ever result from
    this path.
    """

    closure_id: str
    entry_intent_governance_id: str
    symbol: str
    quantity: int
    broker_order_id: str
    client_order_id: str
    filled_avg_price: Decimal
    recorded_by: str
    recorded_at: datetime

    def __post_init__(self) -> None:
        for field_name in (
            "closure_id",
            "entry_intent_governance_id",
            "broker_order_id",
            "client_order_id",
            "recorded_by",
        ):
            _require_identifier(getattr(self, field_name), field=field_name)
        if self.closure_id != external_position_closure_id(self.entry_intent_governance_id):
            raise ValueError(
                "closure_id must be exactly "
                "external_position_closure_id(entry_intent_governance_id)"
            )
        if not self.symbol or self.symbol != self.symbol.strip().upper():
            raise ValueError("symbol must be upper-case and unpadded")
        _require_whole_positive(self.quantity, field="quantity")
        if not isinstance(self.filled_avg_price, Decimal) or self.filled_avg_price <= 0:
            raise ValueError("filled_avg_price must be a positive Decimal")
        _require_aware(self.recorded_at, field="recorded_at")
