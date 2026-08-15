"""Domain-facing operator-asserted position ledger contract (MILESTONE-076).

Append-only by construction: there is no update and no delete on this contract.
"""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
)


class OperatorPositionLedgerRepository(Protocol):
    """Persistence-neutral contract for the append-only operator ledger."""

    def append(self, event: OperatorAssertedPositionEvent) -> None:
        """Persist one new event. The event's governance id must not exist."""
        ...

    def list_all(self) -> tuple[OperatorAssertedPositionEvent, ...]:
        """Every recorded event, ordered deterministically by
        `(event_timestamp, governance_id)`."""
        ...

    def list_for_position(
        self, position_governance_id: str
    ) -> tuple[OperatorAssertedPositionEvent, ...]:
        """Every event for one position key, in the same deterministic order."""
        ...
