"""MILESTONE-076 -- record one operator-asserted position event.

Validates the event against the ENTIRE resulting sequence for its position key,
not merely against the state at its own timestamp, so a back-dated event that
would invalidate a later one is rejected instead of silently corrupting history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from empirical_platform.decision_candidate.operator_position_ledger import (
    OPERATOR_LEDGER_BANNER,
    LedgerRejectionError,
    OperatorAssertedPositionEvent,
    OperatorPositionEventKind,
)
from empirical_platform.decision_candidate.operator_position_ledger_repository import (
    OperatorPositionLedgerRepository,
)

__all__ = [
    "OPERATOR_LEDGER_BANNER",
    "LedgerRejectionError",
    "RecordOperatorPositionEventCommand",
    "RecordOperatorPositionEventHandler",
    "RecordedOperatorEventView",
    "build_operator_position_event",
]


@dataclass(frozen=True, slots=True)
class RecordOperatorPositionEventCommand:
    """One operator assertion to record."""

    event: OperatorAssertedPositionEvent


class RecordOperatorPositionEventHandler:
    """Append one operator assertion, rejecting anything incoherent."""

    __slots__ = ("_ledger",)

    def __init__(self, *, ledger_repository: OperatorPositionLedgerRepository) -> None:
        self._ledger = ledger_repository

    def handle(self, command: RecordOperatorPositionEventCommand) -> OperatorAssertedPositionEvent:
        """Delegate to the repository's ATOMIC validate-and-append.

        MILESTONE-076 owner correction (Finding 1). This handler previously did
        read -> validate -> append across separate transactions, so two
        concurrent writers could both validate against the same stale state and
        both persist, leaving a sequence the canonical fold rejects. Validation
        now happens inside the same transaction, under the same position-key
        lock, as the insert -- the only place the invariant can actually hold.
        """
        return self._ledger.append_validated(command.event)


@dataclass(frozen=True, slots=True)
class RecordedOperatorEventView:
    """Primitive-only view of a recorded assertion.

    `entrypoints` may not import `decision_candidate` (architecture rule), so
    the application layer owns both construction from primitives and the
    primitive-only result the CLI renders.
    """

    governance_id: str
    position_governance_id: str
    instrument_symbol: str
    event_kind: str
    quantity: int
    event_timestamp: str

    @classmethod
    def of(cls, event: OperatorAssertedPositionEvent) -> RecordedOperatorEventView:
        return cls(
            governance_id=event.governance_id,
            position_governance_id=event.position_governance_id,
            instrument_symbol=event.instrument_symbol,
            event_kind=event.kind.value,
            quantity=event.quantity,
            event_timestamp=event.event_timestamp.isoformat(),
        )


def build_operator_position_event(
    *,
    governance_id: str,
    runtime_id: str,
    position_governance_id: str,
    instrument_symbol: str,
    kind: str,
    quantity: int,
    asserted_price: Decimal,
    event_timestamp: datetime,
    recorded_at: datetime,
    source_position_plan_governance_id: str | None = None,
    note: str | None = None,
) -> OperatorAssertedPositionEvent:
    """Build one assertion from primitives, so the CLI never touches the domain."""
    return OperatorAssertedPositionEvent(
        governance_id=governance_id,
        runtime_id=runtime_id,
        position_governance_id=position_governance_id,
        instrument_symbol=instrument_symbol,
        kind=OperatorPositionEventKind(kind),
        quantity=quantity,
        asserted_price=asserted_price,
        event_timestamp=event_timestamp,
        recorded_at=recorded_at,
        source_position_plan_governance_id=source_position_plan_governance_id,
        note=note,
    )
