"""RELEASE v1 -- `PositionPlanManager` over the REAL simulation broker and the REAL M087
exit handlers. Every case here proves the automatic manager submits the SAME kind of
SELL_TO_CLOSE a human would, through the same pipeline, without a second Owner approval,
and without ever double-submitting across a race or a simulated restart.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    ExitTriggerKind,
    derive_system_identity,
)
from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.shared.brokerage.simulation_paper import (
    default_exit_scenario_table,
    default_scenario_table,
)
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


def _set_quote(world: World, symbol: str, *, bid: str, ask: str) -> None:
    scenarios = default_scenario_table()
    exits = default_exit_scenario_table()
    world.store.stage(
        scenarios={symbol: scenarios[symbol]},
        quotes={symbol: (bid, ask)},
        exit_scenarios={symbol: exits[symbol]},
    )


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


def _plan(
    world: World,
    intent: str,
    *,
    plan_id: str = "PLAN-1",
    stop: Decimal,
    target: Decimal,
    mandatory_liquidation_at: datetime | None = None,
) -> ApprovedPlan:
    owner_approval_id = "OWN-1"
    return ApprovedPlan(
        plan_id=plan_id,
        candidate_id="CAND-1",
        entry_intent_governance_id=intent,
        symbol="AAPL",
        approved_quantity=Decimal("8"),
        stop_price=stop,
        target_price=target,
        mandatory_liquidation_at=mandatory_liquidation_at or (world.clock.utc + timedelta(hours=4)),
        owner_approval_id=owner_approval_id,
        system_identity=derive_system_identity(
            plan_id=plan_id, owner_approval_id=owner_approval_id
        ),
        created_at=world.clock.utc,
    )


# ---------------------------------------------------------------------------
# Monitoring: no trigger yet
# ---------------------------------------------------------------------------


def test_a_plan_inside_the_band_only_monitors(world: World) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plans.save(_plan(world, intent, stop=Decimal("200"), target=Decimal("260")))
    manager = _manager(world, plans)
    outcomes = manager.evaluate_once(now=world.clock.utc)
    assert len(outcomes) == 1
    assert outcomes[0].kind is PlanOutcomeKind.MONITORING
    assert world.exits.attempts.for_entry(intent) == ()


# ---------------------------------------------------------------------------
# Stop fires
# ---------------------------------------------------------------------------


def test_a_stop_trigger_submits_the_same_sell_to_close_a_human_would(world: World) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")

    outcomes = manager.evaluate_once(now=world.clock.utc)
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED

    claimed = plans.get(plan.plan_id)
    assert claimed is not None
    assert claimed.triggered_exit_kind is ExitTriggerKind.STOP

    (attempt,) = world.exits.attempts.for_entry(intent)
    assert attempt.authorization_id.startswith("XAU-plan-")
    (authorization,) = (
        a for a in [world.exits.authorizations.get(attempt.authorization_id)] if a is not None
    )
    assert authorization.authorized_by == plan.system_identity
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1


def test_a_second_tick_after_the_stop_fired_does_not_resubmit(world: World) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")

    manager.evaluate_once(now=world.clock.utc)
    world.clock.advance(5)
    world.service.refresh_executions()
    second = manager.evaluate_once(now=world.clock.utc)

    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1
    assert all(
        o.kind in (PlanOutcomeKind.EXIT_RECONCILED, PlanOutcomeKind.EXIT_ALREADY_IN_PROGRESS)
        for o in second
    )


# ---------------------------------------------------------------------------
# Target fires
# ---------------------------------------------------------------------------


def test_a_target_trigger_submits_a_sell_to_close(world: World) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("200"), target=Decimal("228")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")

    outcomes = manager.evaluate_once(now=world.clock.utc)
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.TARGET


# ---------------------------------------------------------------------------
# Mandatory exit fires on time alone, even inside the stop/target band
# ---------------------------------------------------------------------------


def test_the_mandatory_exit_fires_on_time_alone(world: World) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    deadline = world.clock.utc + timedelta(minutes=5)
    plans.save(
        _plan(
            world,
            intent,
            stop=Decimal("200"),
            target=Decimal("260"),
            mandatory_liquidation_at=deadline,
        )
    )
    manager = _manager(world, plans)

    world.clock.advance(int(timedelta(minutes=5).total_seconds()) - 60)
    outcomes = manager.evaluate_once(now=world.clock.utc)
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    assert world.exits.attempts.for_entry(intent) != ()


# ---------------------------------------------------------------------------
# Collision safety: a second concurrent manager never double-submits
# ---------------------------------------------------------------------------


def test_two_managers_racing_on_the_same_tick_submit_exactly_one_exit(world: World) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    manager_a = _manager(world, plans)
    manager_b = _manager(world, plans)
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")

    now = world.clock.utc
    outcomes_a = manager_a.evaluate_once(now=now)
    outcomes_b = manager_b.evaluate_once(now=now)

    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1
    kinds = {outcomes_a[0].kind, outcomes_b[0].kind}
    assert PlanOutcomeKind.EXIT_CLAIMED in kinds
    # Whichever manager loses the race either sees the plan already claimed (if it was
    # still in `list_unclaimed` for this tick), or -- having observed it via
    # `list_claimed` -- reconciles the in-flight attempt rather than resubmitting. Both
    # are "did not submit a second SELL"; never a second order either way (asserted above).
    assert kinds <= {
        PlanOutcomeKind.EXIT_CLAIMED,
        PlanOutcomeKind.EXIT_ALREADY_CLAIMED,
        PlanOutcomeKind.EXIT_ALREADY_IN_PROGRESS,
        PlanOutcomeKind.EXIT_RECONCILED,
    }


# ---------------------------------------------------------------------------
# Restart recovery: a claim durably recorded but not yet dispatched is resumed
# ---------------------------------------------------------------------------


def test_a_claim_recorded_but_not_yet_dispatched_is_resumed_after_restart(world: World) -> None:
    """Simulates the exact boundary the release mission calls out: 'after claim / before
    broker acknowledgement'. The claim is made directly (as if the prior process died the
    instant after `claim_exit_trigger` returned, before calling Preview/Authorize/Submit),
    then a FRESH manager (over a restarted broker/market connection, matching `World.restart`)
    must pick it up and complete the dispatch -- never re-evaluate the trigger, never skip it."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    plans.claim_exit_trigger(plan.plan_id, kind=ExitTriggerKind.STOP, claimed_at=world.clock.utc)
    assert world.exits.attempts.for_entry(intent) == ()

    restarted = world.restart()
    manager = _manager(restarted, plans)
    outcomes = manager.evaluate_once(now=restarted.clock.utc)

    assert any(o.kind is PlanOutcomeKind.EXIT_SUBMITTED for o in outcomes)
    assert world.exits.attempts.for_entry(intent) != ()
    sells = [o for o in restarted.store.orders() if o.side == "sell"]
    assert len(sells) == 1
