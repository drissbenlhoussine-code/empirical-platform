"""RELEASE v1 -- Release Blocker 2's connector: ONE Owner approval creates BOTH the
bounded PAPER entry authorization AND the durable `ApprovedPlan` the automatic manager
later watches, so the Owner never approves the eventual stop/target/mandatory exit again.

REUSE, NOT DUPLICATION. `approve_full_plan` calls `OperatorConsoleService.confirm_approval`
UNCHANGED -- the exact same decide -> issue -> preview -> authorize -> submit chain
M086-M089's console already uses, with its full existing safety logic (stale-ticket
refusal, kill-switch check, "terms changed" cross-check, idempotent resumption). This
module adds NOTHING to that chain's own decisions about whether an entry may be sent; it
only reads what `confirm_approval` already produced and, the moment a real entry
authorization exists, creates the plan that lets the automatic manager take over.

THE ORDERING GUARANTEE, STATED HONESTLY. The mission's own architecture note asks for
"never a window where an entry is authorized without its corresponding ApprovedPlan
existing." `confirm_approval` is one call that may authorize AND submit the entry
internally; this module cannot insert a step in the middle of that already-proven,
heavily-tested method without risking its safety logic, so it instead creates the
`ApprovedPlan` IMMEDIATELY after `confirm_approval` returns -- a real, if narrow (same
Python call, no network round trip in between), window rather than a literal zero-width
one. This is closed in practice, not just in theory, by making `approve_full_plan` itself
idempotent: it is safe to call again (e.g. the Owner's page retries, or a supervisor
retries after a crash) and will create the missing `ApprovedPlan` for an entry that was
already authorized/submitted by an earlier, interrupted call, exactly mirroring
`confirm_approval`'s own resume-from-durable-state discipline. It never creates a SECOND
plan for the same entry (`ApprovedPlanRepository.save`'s own uniqueness is relied on).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    derive_system_identity,
)
from empirical_platform.decision_candidate.approved_plan_repositories import (
    ApprovedPlanAlreadyExistsError,
    ApprovedPlanRepository,
)
from empirical_platform.usecases.decision_to_approval import NotFoundError
from empirical_platform.usecases.operator_console import (
    ActionOutcome,
    ConsoleRepositories,
    OperatorConsoleService,
)

__all__ = ["FullPlanApprovalOutcome", "approve_full_plan"]


@dataclass(frozen=True, slots=True)
class FullPlanApprovalOutcome:
    approval: ActionOutcome
    plan: ApprovedPlan | None
    #: True only when THIS call created the plan row (vs. finding one already there from
    #: an earlier, interrupted call -- see the module docstring's ordering note).
    plan_created_now: bool


def approve_full_plan(
    service: OperatorConsoleService,
    repositories: ConsoleRepositories,
    plans: ApprovedPlanRepository,
    *,
    proposal_id: str,
    token: str,
    candidate_id: str,
) -> FullPlanApprovalOutcome:
    """The ONE Owner-facing action: review the complete plan -> APPROVE.

    `candidate_id` names the Research Candidate (M090 `TradingOpportunity.opportunity_id`)
    this approval was reviewed from, purely for traceability in `ApprovedPlan`/History --
    it plays NO role in the entry terms, which always come from the freshly-prepared M085
    `TradeProposal` (`stop_loss_price`/`profit_exit_price`/`quantity`), never from the
    opportunity's own (possibly stale, research-time) numbers. This is the same freshness
    discipline every other step in this pipeline already enforces.
    """
    approval = service.confirm_approval(proposal_id, token)

    intent = repositories.intents.for_proposal(proposal_id)
    if intent is None:
        # Entry was not authorized (rejected, blocked, or refused) -- no plan to create.
        return FullPlanApprovalOutcome(approval=approval, plan=None, plan_created_now=False)

    existing = plans.for_entry(intent.intent_governance_id)
    if existing is not None:
        return FullPlanApprovalOutcome(approval=approval, plan=existing, plan_created_now=False)

    proposal = repositories.proposals.get(proposal_id)
    if proposal is None:
        raise NotFoundError(f"no trade proposal {proposal_id!r} exists for an issued intent")

    owner_approval_id = f"DEC-{proposal_id}"
    plan = ApprovedPlan(
        plan_id=f"PLAN-{intent.intent_governance_id}",
        candidate_id=candidate_id,
        entry_intent_governance_id=intent.intent_governance_id,
        symbol=intent.symbol,
        approved_quantity=Decimal(proposal.quantity),
        stop_price=proposal.stop_loss_price,
        target_price=proposal.profit_exit_price,
        mandatory_liquidation_at=intent.mandatory_liquidation_at,
        owner_approval_id=owner_approval_id,
        system_identity=derive_system_identity(
            plan_id=f"PLAN-{intent.intent_governance_id}", owner_approval_id=owner_approval_id
        ),
        created_at=intent.created_at,
    )
    try:
        saved = plans.save(plan)
    except ApprovedPlanAlreadyExistsError:
        # Lost a race against another caller creating the same plan; read back the winner.
        winner = plans.for_entry(intent.intent_governance_id)
        assert winner is not None
        return FullPlanApprovalOutcome(approval=approval, plan=winner, plan_created_now=False)
    return FullPlanApprovalOutcome(approval=approval, plan=saved, plan_created_now=True)
