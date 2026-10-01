"""RELEASE v1 -- `approve_full_plan`: ONE Owner action authorizes both the bounded entry
AND creates the durable `ApprovedPlan` the automatic manager later watches, over the REAL
simulation broker and the REAL M084-M086 handler chain (via `OperatorConsoleService`,
unmodified).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans

from empirical_platform.decision_candidate.approved_plan import derive_system_identity
from empirical_platform.usecases.full_plan_approval import approve_full_plan
from empirical_platform.usecases.operator_console import ConsoleRefusalError


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path)


def test_approving_creates_both_the_entry_and_the_plan_in_one_action(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    review = world.service.prepare_approval(proposal_id)
    plans = FakeApprovedPlans()

    outcome = approve_full_plan(
        world.service,
        world.repositories,
        plans,
        proposal_id=proposal_id,
        token=review.ticket,
        candidate_id="OPP-TEST-1",
    )

    assert outcome.approval.sent == "sent"
    assert outcome.plan is not None
    assert outcome.plan_created_now is True

    intent = world.repositories.intents.for_proposal(proposal_id)
    assert intent is not None
    assert outcome.plan.entry_intent_governance_id == intent.intent_governance_id
    assert outcome.plan.symbol == "AAPL"
    assert outcome.plan.stop_price < outcome.plan.target_price
    assert outcome.plan.mandatory_liquidation_at == intent.mandatory_liquidation_at
    assert outcome.plan.owner_approval_id == f"DEC-{proposal_id}"
    assert outcome.plan.system_identity == derive_system_identity(
        plan_id=outcome.plan.plan_id, owner_approval_id=outcome.plan.owner_approval_id
    )
    assert not outcome.plan.is_claimed


def test_the_plan_terms_come_from_the_fresh_proposal_not_a_stale_candidate_number(
    world: World,
) -> None:
    """The entry/stop/target are the FRESH, just-computed M085 proposal's own fields --
    never values the caller could pass in (the `candidate_id` parameter carries no price
    data at all), matching the pipeline's existing freshness discipline everywhere else."""
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    proposal = world.repositories.proposals.get(proposal_id)
    assert proposal is not None
    review = world.service.prepare_approval(proposal_id)
    plans = FakeApprovedPlans()

    outcome = approve_full_plan(
        world.service,
        world.repositories,
        plans,
        proposal_id=proposal_id,
        token=review.ticket,
        candidate_id="OPP-TEST-2",
    )

    assert outcome.plan is not None
    assert outcome.plan.stop_price == proposal.stop_loss_price
    assert outcome.plan.target_price == proposal.profit_exit_price
    assert outcome.plan.approved_quantity == proposal.quantity


def test_calling_it_again_is_idempotent_and_never_creates_a_second_plan(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    review = world.service.prepare_approval(proposal_id)
    plans = FakeApprovedPlans()

    first = approve_full_plan(
        world.service,
        world.repositories,
        plans,
        proposal_id=proposal_id,
        token=review.ticket,
        candidate_id="OPP-TEST-3",
    )
    second = approve_full_plan(
        world.service,
        world.repositories,
        plans,
        proposal_id=proposal_id,
        token=review.ticket,
        candidate_id="OPP-TEST-3",
    )

    assert first.plan_created_now is True
    assert second.plan_created_now is False
    assert second.plan == first.plan
    assert len(plans.rows) == 1


def test_resuming_after_an_interrupted_call_creates_the_missing_plan(world: World) -> None:
    """Simulates the exact narrow window the module docstring names: the entry was
    authorized/submitted by an earlier call, but that call never reached plan creation
    (e.g. the process died). A resuming call -- here, a plain re-approval -- still creates
    the plan from durable entry-pipeline state, closing the gap in practice."""
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    review = world.service.prepare_approval(proposal_id)
    # The entry pipeline runs to completion on its own (no plan created) -- the "crash".
    outcome = world.service.confirm_approval(proposal_id, review.ticket)
    assert outcome.sent == "sent"
    plans = FakeApprovedPlans()
    assert plans.rows == {}

    resumed = approve_full_plan(
        world.service,
        world.repositories,
        plans,
        proposal_id=proposal_id,
        token=review.ticket,
        candidate_id="OPP-TEST-4",
    )

    assert resumed.plan is not None
    assert resumed.plan_created_now is True
    intent = world.repositories.intents.for_proposal(proposal_id)
    assert intent is not None
    assert resumed.plan.entry_intent_governance_id == intent.intent_governance_id


def test_a_rejected_or_expired_approval_creates_no_plan(world: World) -> None:
    world.load_day(("AAPL",))
    proposal_id = world.proposal_id("AAPL")
    review = world.service.prepare_approval(proposal_id)
    world.clock.advance(3601)
    plans = FakeApprovedPlans()

    with pytest.raises(ConsoleRefusalError):
        approve_full_plan(
            world.service,
            world.repositories,
            plans,
            proposal_id=proposal_id,
            token=review.ticket,
            candidate_id="OPP-TEST-5",
        )
    assert plans.rows == {}
