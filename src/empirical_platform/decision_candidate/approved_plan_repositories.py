"""RELEASE v1 -- the storage contract for `ApprovedPlan`.

ONE REPOSITORY, ONE ATOMIC CLAIM. `save` is append-only (a plan is written exactly once,
at Owner-approval time). `claim_exit_trigger` is the ONE controlled mutation a plan ever
undergoes, and it is the exit-collision-safety primitive: it must be implemented as a
single conditional UPDATE (`WHERE triggered_exit_kind IS NULL`) inside one transaction,
the same discipline `PositionExitAttemptRepository.claim_dispatch` already proves
exactly-once elsewhere in this codebase. A losing caller gets `None` back, never an
exception and never the other caller's claim silently overwritten.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, ExitTriggerKind

__all__ = ["ApprovedPlanRepository"]


class ApprovedPlanRepository(Protocol):
    """Durable storage for Owner-approved full trade plans."""

    def save(self, plan: ApprovedPlan) -> ApprovedPlan:
        """Persist a brand-new plan. Refuses (raises) if `plan_id` already exists."""
        ...

    def get(self, plan_id: str) -> ApprovedPlan | None: ...

    def for_entry(self, entry_intent_governance_id: str) -> ApprovedPlan | None:
        """The plan that authorized this entry, if any. At most one plan per entry."""
        ...

    def list_unclaimed(self, limit: int) -> tuple[ApprovedPlan, ...]:
        """Plans whose exit trigger has not yet been claimed, oldest first.

        The automatic manager polls this to find plans it still needs to evaluate. A plan
        whose entry has not yet filled, or whose position is already fully closed, is still
        included here if unclaimed -- the manager itself decides eligibility from broker
        truth each tick; this repository does not try to guess "open" from its own state.
        """
        ...

    def list_claimed(self, limit: int) -> tuple[ApprovedPlan, ...]:
        """Plans whose exit trigger HAS been claimed, oldest claim first.

        The manager polls this on every tick (not just after a fresh claim) so that a
        process restarted between the claim and a resolved exit resumes correctly from
        durable truth -- this is the restart-recovery boundary "after claim / before broker
        acknowledgement" in the release mission.
        """
        ...

    def claim_exit_trigger(
        self, plan_id: str, *, kind: ExitTriggerKind, claimed_at: datetime
    ) -> ApprovedPlan | None:
        """Atomically claim the right to submit this plan's exit.

        Returns the updated plan on a win, or `None` if another caller already claimed it
        (`EXIT_ALREADY_CLAIMED`) -- the caller must submit nothing in that case.
        """
        ...
