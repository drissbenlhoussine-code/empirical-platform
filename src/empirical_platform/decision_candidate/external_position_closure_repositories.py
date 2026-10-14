"""RELEASE v1 -- the storage contract for `ExternalPositionClosure`.

APPEND-ONLY, AT MOST ONE PER ENTRY. `save` is called exactly once per entry in practice
(the handler checks `for_entry` first and returns the existing record instead of saving
again), but a backend MUST also enforce this itself with its own uniqueness guard (the
Postgres implementation uses a UNIQUE constraint on `entry_intent_governance_id`, the same
discipline `ApprovedPlanRepository`/`PositionExitAttemptRepository` already use elsewhere in
this codebase), so a concurrent caller can never create two closure records for one entry.
"""

from __future__ import annotations

from typing import Protocol

from empirical_platform.decision_candidate.external_position_closure import (
    ExternalPositionClosure,
)

__all__ = ["ExternalPositionClosureRepository"]


class ExternalPositionClosureRepository(Protocol):
    """Durable storage for externally-observed position closures."""

    def save(self, closure: ExternalPositionClosure) -> ExternalPositionClosure:
        """Persist a brand-new record. Raises if one already exists for this entry."""
        ...

    def for_entry(self, entry_intent_governance_id: str) -> ExternalPositionClosure | None: ...
