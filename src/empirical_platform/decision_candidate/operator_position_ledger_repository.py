"""Domain-facing operator-asserted position ledger contract (MILESTONE-076).

Append-only by construction: there is no update and no delete on this contract.

MILESTONE-076 owner correction (Finding 1). `append` alone is not a safe
contract for a durable ledger. Reading, validating and appending as three
separate steps lets two concurrent writers validate against the same stale
state and both persist, leaving a sequence the canonical fold rejects. The
contract therefore exposes `append_validated`, which an implementation must
make ATOMIC for a position key -- validation and insertion inside one
transaction, serialised against concurrent writers to the same key.
"""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.operator_position_ledger import (
    OperatorAssertedPositionEvent,
)


class OperatorPositionLedgerRepository(Protocol):
    """Persistence-neutral contract for the append-only operator ledger."""

    def append_validated(
        self, candidate: OperatorAssertedPositionEvent
    ) -> OperatorAssertedPositionEvent:
        """Atomically serialise on the candidate's position key, re-read that
        key's committed events, validate the whole resulting sequence, and
        append.

        Implementations MUST hold the position-key lock across the read and the
        insert, so a concurrent writer cannot validate against state this call
        is about to invalidate. Raises `LedgerRejectionError` if the resulting
        sequence would be incoherent. Returns the event as persisted, which may
        differ from the candidate: a CLOSED event's quantity is derived.
        """
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
