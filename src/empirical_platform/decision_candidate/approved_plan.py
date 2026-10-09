"""RELEASE v1 -- the Owner's one durable approval of a complete trade plan.

WHAT THIS IS. Release Blocker 2 requires ONE Owner approval to durably authorize BOTH a
bounded PAPER entry AND the future, automatic, position-reducing exits (stop, target,
mandatory liquidation) that follow it -- without asking the Owner to approve those exits
again. `ApprovedPlan` is the durable record of exactly those frozen terms: it is written
once, at approval time, and never mutated except for the ONE atomic exit-trigger claim
(`triggered_exit_kind`) described below.

WHAT IT DOES NOT DO. This module never calls a broker, never reads a clock, and never
decides anything about the LIVE market. It is pure data plus pure decision functions, the
same discipline `operator_trading_configuration.py` and `trade_proposal.py` already use:
the automatic position-plan manager (`usecases/position_plan_manager.py`) supplies fresh
evidence and calls `evaluate_exit_trigger` to get an answer; this module never fetches
that evidence itself.

THE SYSTEM IDENTITY IS NOT A LOOPHOLE. The automatic manager must authorize an exit
through the SAME `AuthorizePositionExitHandler`/`SubmitAuthorizedPositionExitHandler`
chain a human uses, which requires an `authorized_by` identity. `derive_system_identity`
produces a stable string that deterministically traces back to the ONE Owner approval
that created this plan (`plan_id` + the Owner's own approval identity, never freeform
text) -- it authorizes nothing beyond the exits this exact plan already named, and it
cannot be constructed without an existing plan and an existing Owner approval id.

EXACTLY ONE EXIT TRIGGER MAY WIN (exit-collision safety). Stop, target and mandatory-exit
conditions are evaluated independently and may become true in the same evaluation tick.
`triggered_exit_kind` is a single nullable column claimed via the SAME conditional
`UPDATE ... WHERE triggered_exit_kind IS NULL` pattern `claim_dispatch` already proves
exactly-once for order dispatch elsewhere in this codebase (see
`ApprovedPlanRepository.claim_exit_trigger`). A trigger that loses the claim must treat
that as `EXIT_ALREADY_CLAIMED` and submit nothing -- it never resubmits "just in case" and
never overwrites a prior claim. The existing exit pipeline's own `exit_eligibility` (an
exit is refused while another is in progress) and `claim_dispatch` (at most one active
exit attempt per position) are a second, independent layer of the same guarantee: even if
two callers raced past the plan-level claim somehow, the exit-attempt table itself cannot
hold two active attempts for the same entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum

__all__ = [
    "ApprovedPlan",
    "ExitTriggerKind",
    "derive_system_identity",
    "evaluate_exit_trigger",
]

_MAXIMUM_IDENTIFIER_LENGTH = 64

#: How long before `mandatory_liquidation_at` the automatic manager must already have
#: submitted the mandatory exit. Matches the documented safety-buffer requirement in the
#: release mission ("Use a documented safety buffer before regular-session close"). Chosen
#: so a plan evaluated on the manager's own poll interval (see
#: `position_plan_manager.DEFAULT_POLL_INTERVAL_SECONDS`, 15s) has many evaluation
#: opportunities to submit before the hard deadline even under broker/network delay.
MANDATORY_EXIT_SAFETY_BUFFER_SECONDS = 120


class ExitTriggerKind(StrEnum):
    """Which of the three pre-approved exit conditions fired. Never a fourth value."""

    STOP = "STOP"
    TARGET = "TARGET"
    MANDATORY_EXIT = "MANDATORY_EXIT"


def _require_identifier(value: str, *, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} must be a non-empty string")
    if len(value) > _MAXIMUM_IDENTIFIER_LENGTH:
        raise ValueError(f"{field} must be at most {_MAXIMUM_IDENTIFIER_LENGTH} characters")


def derive_system_identity(*, plan_id: str, owner_approval_id: str) -> str:
    """The ONLY `authorized_by` string the automatic manager may ever use.

    Deterministic, not generated: the same `(plan_id, owner_approval_id)` always produces
    the same identity, so the audit trail can always be walked back to the one human
    approval that authorized it. It is never accepted as a human `authorized_by` value for
    a MANUAL exit (see `position_plan_manager.py`'s own refusal when a caller tries to pass
    it from the console) -- it exists only for the automatic manager's own use.
    """
    _require_identifier(plan_id, field="plan_id")
    _require_identifier(owner_approval_id, field="owner_approval_id")
    return f"system:approved-plan:{plan_id}:owner-approval:{owner_approval_id}"


@dataclass(frozen=True, slots=True)
class ApprovedPlan:
    """The complete, immutable terms the Owner approved in ONE action.

    Everything except `triggered_exit_kind`/`triggered_exit_at` is write-once at approval
    time. Those two fields are the one deliberate, atomically-claimed mutation this record
    ever undergoes -- see the module docstring.
    """

    plan_id: str
    candidate_id: str
    entry_intent_governance_id: str
    symbol: str
    approved_quantity: Decimal
    stop_price: Decimal
    target_price: Decimal
    mandatory_liquidation_at: datetime
    owner_approval_id: str
    system_identity: str
    created_at: datetime
    triggered_exit_kind: ExitTriggerKind | None = None
    triggered_exit_at: datetime | None = None

    def __post_init__(self) -> None:
        _require_identifier(self.plan_id, field="plan_id")
        _require_identifier(self.candidate_id, field="candidate_id")
        _require_identifier(self.entry_intent_governance_id, field="entry_intent_governance_id")
        _require_identifier(self.symbol, field="symbol")
        _require_identifier(self.owner_approval_id, field="owner_approval_id")
        if self.approved_quantity <= 0:
            raise ValueError("approved_quantity must be positive")
        if self.stop_price <= 0 or self.target_price <= 0:
            raise ValueError("stop_price and target_price must be positive")
        if self.stop_price >= self.target_price:
            raise ValueError(
                "stop_price must be strictly below target_price (long-only full close)"
            )
        expected_identity = derive_system_identity(
            plan_id=self.plan_id, owner_approval_id=self.owner_approval_id
        )
        if self.system_identity != expected_identity:
            raise ValueError(
                "system_identity must be exactly derive_system_identity(plan_id, "
                "owner_approval_id); a plan can never carry a freeform or mismatched identity"
            )
        if (self.triggered_exit_kind is None) != (self.triggered_exit_at is None):
            raise ValueError(
                "triggered_exit_kind and triggered_exit_at must be set, or unset, together"
            )

    @property
    def is_claimed(self) -> bool:
        return self.triggered_exit_kind is not None

    @property
    def mandatory_exit_deadline(self) -> datetime:
        """When the automatic manager must have ALREADY submitted the mandatory exit."""
        return self.mandatory_liquidation_at - timedelta(
            seconds=MANDATORY_EXIT_SAFETY_BUFFER_SECONDS
        )


def evaluate_exit_trigger(
    plan: ApprovedPlan, *, last_price: Decimal, now: datetime
) -> ExitTriggerKind | None:
    """Pure decision: which exit condition, if any, has been reached right now.

    Priority when more than one condition is simultaneously true: STOP, then TARGET, then
    MANDATORY_EXIT. A long-only plan's `stop_price < target_price` invariant means price
    cannot satisfy both the stop and target conditions at once, so this ordering only ever
    matters between a price trigger and the independent time-based mandatory-exit trigger;
    STOP is given priority there too, because a price that has already crossed the stop is
    the more urgent risk-bounding fact. This function never widens `stop_price` or
    `target_price` and never looks at anything the plan did not already freeze.
    """
    if plan.is_claimed:
        return None
    if last_price <= plan.stop_price:
        return ExitTriggerKind.STOP
    if last_price >= plan.target_price:
        return ExitTriggerKind.TARGET
    if now >= plan.mandatory_exit_deadline:
        return ExitTriggerKind.MANDATORY_EXIT
    return None
