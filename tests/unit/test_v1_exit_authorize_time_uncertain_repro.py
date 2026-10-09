"""Reproduction, isolated TEST data only -- `PlanManagerThread` stalls forever between
Preview and Authorization when the tick's `now` disagrees, even briefly, with what the
Authorize handler's own clock read reports.

INCIDENT: 2026-10-09 AAPL Paper position. `PositionPlanManager` claimed the
MANDATORY_EXIT trigger and wrote a `position_exit_preview` row, but never wrote a
`position_exit_authorization` or `position_exit_attempt` row. The position stayed open
past its deadline. Nothing in the UI or the database ever showed NEEDS_ATTENTION.

ROOT CAUSE: `AuthorizePositionExitHandler.handle` (usecases/position_exit.py) raises
`PaperTimeUncertainError` -- not `PositionExitRefusedError` -- when the authorization
instant is later than this host's own fresh reading of the broker time basis
(position_exit.py:540-544). `PositionPlanManager._attempt_exit` wraps the whole
Preview -> Authorize -> Submit sequence in `except PositionExitRefusedError`
ONLY (position_plan_manager.py:342); `PaperTimeUncertainError` is a sibling
`ValueError` subclass (paper_time.py:129), not a `PositionExitRefusedError`
(position_exit.py:152), so it is never caught there. It escapes `_attempt_exit`,
`_evaluate_unclaimed`/`_resume_claimed`, and `evaluate_once`, reaching only
`PlanManagerThread._run`'s blanket `except Exception: _LOG.exception(...)` --
which logs and keeps the thread alive, but returns no `PlanEvaluationOutcome` and
leaves `PlanOutcomeKind.NEEDS_ATTENTION` unreached. Every following tick repeats
the identical failure forever: the preview is already saved, so `_attempt_exit`
calls `self._authorize_handler.handle(...)` again with a fresh `now`, which can
retrip the same check, with no owner-visible status change.

Contrast: `SubmitAuthorizedPositionExitHandler.handle` (position_exit.py:830)
already treats `PaperTimeUncertainError` as an ordinary, recordable refusal --
`except (PositionExitRefusedError, PaperTimeUncertainError) as error:` -- proving
the codebase already recognizes this exception as part of the exit pipeline's
normal refusal vocabulary. `_attempt_exit`'s except clause is simply missing it.

This test reproduces the failure with NO real broker, NO real Postgres: everything
is the existing in-memory `World` simulation fixture used by every other test in
this file. It passes a tick `now` that is one second ahead of what the shared fake
clock will independently report when `AuthorizePositionExitHandler` takes its own
fresh reading -- modelling exactly the real-world gap between the time the
`PlanManagerThread` captured at tick start and the time the Authorize handler's own
`PaperTimeWindow` observes a few network calls later, when those two readings of
"now" do not agree by even a fraction of a second.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    derive_system_identity,
)
from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.usecases.position_plan_manager import (
    PlanOutcomeKind,
    PositionPlanManager,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


def _intent(world: World, symbol: str) -> str:
    return f"INT-{world.proposal_id(symbol)}"


def _open_position(world: World, symbol: str = "AAPL") -> str:
    world.load_day((symbol,))
    proposal = world.proposal_id(symbol)
    view = world.service.prepare_approval(proposal)
    outcome = world.service.confirm_approval(proposal, view.ticket)
    assert outcome.sent == "sent", outcome.message
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    intent = _intent(world, symbol)
    entry = world.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.state is PaperExecutionState.FILLED
    return intent


def _manager(world: World, plans: FakeApprovedPlans) -> PositionPlanManager:
    return PositionPlanManager(
        plans=plans,
        intents=world.repositories.intents,
        entry_attempts=world.repositories.attempts,
        exit_attempts=world.exits.attempts,
        previews=world.exits.previews,
        authorizations=world.exits.authorizations,
        acknowledgements=world.exits.acknowledgements,
        events=world.exits.events,
        rounds=world.exits.rounds,
        broker=world.broker,
        market_data=world.market_data,
        configurations=world.repositories.configurations,
        environment="SIMULATION",
        time_source=world.clock,
    )


def _mandatory_exit_plan(world: World, intent: str) -> ApprovedPlan:
    owner_approval_id = "OWN-1"
    plan_id = "PLAN-1"
    return ApprovedPlan(
        plan_id=plan_id,
        candidate_id="CAND-1",
        entry_intent_governance_id=intent,
        symbol="AAPL",
        approved_quantity=Decimal("8"),
        stop_price=Decimal("200"),
        target_price=Decimal("999"),
        mandatory_liquidation_at=world.clock.utc,
        owner_approval_id=owner_approval_id,
        system_identity=derive_system_identity(
            plan_id=plan_id, owner_approval_id=owner_approval_id
        ),
        created_at=world.clock.utc,
    )


def test_a_tick_now_one_second_ahead_of_the_clock_is_needs_attention_not_a_crash(
    world: World,
) -> None:
    """FIXED behavior. Before the fix, this exact scenario raised
    `PaperTimeUncertainError` uncaught out of `evaluate_once` -- which is how the
    real AAPL incident happened: Preview written, Authorize never completes, the
    plan permanently stuck with no owner-visible status. After the fix,
    `_attempt_exit` catches `PaperTimeUncertainError` the same way it already
    catches `PositionExitRefusedError`, and the tick returns a normal
    `NEEDS_ATTENTION` outcome instead of propagating.
    """
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_mandatory_exit_plan(world, intent))
    manager = _manager(world, plans)

    tick_now = world.clock.utc + timedelta(seconds=1)

    outcomes = manager.evaluate_once(now=tick_now)

    assert outcomes[0].kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert all(o.kind is PlanOutcomeKind.NEEDS_ATTENTION for o in outcomes)
    assert world.exits.previews.next_version_for_entry(intent) == 2, (
        "the preview from the first (failing) authorize call is still there"
    )
    assert world.exits.attempts.for_entry(intent) == (), (
        "no exit attempt should exist -- authorization never completed"
    )
    claimed = plans.get(plan.plan_id)
    assert claimed is not None
    assert claimed.triggered_exit_kind is not None, (
        "the trigger remains claimed durably -- the NEXT tick resumes the SAME "
        "plan through _resume_claimed/_attempt_exit rather than re-evaluating it "
        "as a fresh, unclaimed trigger"
    )


def test_the_plan_self_heals_once_the_clock_disagreement_clears(world: World) -> None:
    """The transient refusal is not fatal: once the clock reading that tripped
    `PaperTimeUncertainError` is no longer ahead, the VERY NEXT tick resumes the
    SAME claimed plan and completes the exit -- no restart, no manual
    intervention, no duplicate order.
    """
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plans.save(_mandatory_exit_plan(world, intent))
    manager = _manager(world, plans)

    bad_tick_now = world.clock.utc + timedelta(seconds=1)
    first = manager.evaluate_once(now=bad_tick_now)
    assert first[0].kind is PlanOutcomeKind.NEEDS_ATTENTION

    # The next poll, a real 15s later: the clock has genuinely caught up past the
    # stored preview's `created_at` (which was stamped using the artificially-ahead
    # `bad_tick_now`), so the age/basis checks that tripped above now pass cleanly.
    world.clock.advance(15)
    second = manager.evaluate_once(now=world.clock.utc)

    assert second[0].kind is PlanOutcomeKind.EXIT_SUBMITTED
    (attempt,) = world.exits.attempts.for_entry(intent)
    assert attempt.authorization_id.startswith("XAU-plan-")
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1, "exactly one SELL_TO_CLOSE, never a duplicate"
    assert world.exits.previews.next_version_for_entry(intent) == 2, (
        "the SAME preview from the first tick was reused, not regenerated"
    )
