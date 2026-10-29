"""RELEASE v1 -- the Active Trade page's MANAGEMENT STATUS value.

Pure derivation, no I/O: given an `ApprovedPlan` (or `None`, if this position has no
managed plan) and its current exit attempt (if any, from the SAME `PositionExitAttempt`
the manual exit flow already reads), returns exactly one of the mission's seven status
words. Never guesses; an attempt whose outcome is ambiguous (`SUBMISSION_UNKNOWN`) or
terminal-but-not-verified-closed reads as "Needs attention" -- the same word the existing
console already uses for a position that needs a human to look at it.
"""

from __future__ import annotations

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan
from empirical_platform.decision_candidate.position_exit import PositionExitAttempt

__all__ = [
    "MANAGEMENT_STATUS_VALUES",
    "ApprovedPlan",
    "PositionExitAttempt",
    "management_status",
]

MANAGEMENT_STATUS_VALUES = (
    "Monitoring",
    "Stop triggered",
    "Target triggered",
    "Mandatory exit triggered",
    "Exit submitted",
    "Needs attention",
    "Closed",
)

_TRIGGERED_LABEL = {
    "STOP": "Stop triggered",
    "TARGET": "Target triggered",
    "MANDATORY_EXIT": "Mandatory exit triggered",
}


def management_status(
    plan: ApprovedPlan | None,
    attempt: PositionExitAttempt | None,
    *,
    assessment_refusals: tuple[str, ...] = (),
) -> str:
    """`assessment_refusals` is `AssessPositionExitHandler.handle(...).refusals` for this
    plan's entry, from the SAME assessment the caller's request already computed elsewhere
    (never a fresh call made just for this function) -- empty when the caller has none to
    offer, or when the position is not currently blocked. RELEASE v1 VISIBILITY FIX: a plan
    whose trigger has not yet fired is "Monitoring" ONLY while the position is actually
    eligible to be closed if a trigger did fire; a plan the manager can never successfully
    act on (e.g. blocked by `exit_eligibility`'s own competing-entry or attribution refusal)
    must say so, not claim a false "Monitoring" health.
    """
    if plan is None:
        return "Monitoring"
    if attempt is not None and attempt.position_closed:
        return "Closed"
    if plan.triggered_exit_kind is None:
        return "Needs attention" if assessment_refusals else "Monitoring"
    if attempt is None:
        # Claimed, but the manager has not yet dispatched (or this is the instant between
        # claim and dispatch) -- the trigger itself is the most honest status to show.
        return _TRIGGERED_LABEL[plan.triggered_exit_kind.value]
    if attempt.outcome_is_known and attempt.is_terminal and not attempt.position_closed:
        # FAILED/CANCELLED (no fill), or FILLED-but-not-yet-verified-closed: either way a
        # human should look, not assume the automatic manager will resolve it alone.
        return "Needs attention"
    if not attempt.outcome_is_known:
        return "Needs attention"
    return "Exit submitted"
