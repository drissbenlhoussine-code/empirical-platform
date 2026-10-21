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
from tests.unit._v1_fakes import FakeApprovedPlans, FakeExternalPositionClosures

from empirical_platform.decision_candidate.approved_plan import (
    ApprovedPlan,
    ExitTriggerKind,
    derive_system_identity,
)
from empirical_platform.decision_candidate.external_position_closure import (
    ExternalPositionClosure,
    external_position_closure_id,
)
from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedOrder,
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


def _simulate_external_sell(
    world: World, symbol: str, *, quantity: int, filled_avg_price: str, client_order_id: str
) -> None:
    """Simulate a SELL this platform never dispatched -- e.g. a manual broker-dashboard
    trade. Writes straight into the simulated broker's own order book and position via its
    PUBLIC seams (`put`/`reduce_position`), bypassing `submit_close_order` and every
    Preview/Authorize/Submit handler entirely, exactly as a real external fill would."""
    order = SimulatedOrder(
        broker_order_id=world.store.next_broker_order_id(),
        client_order_id=client_order_id,
        symbol=symbol,
        side="sell",
        quantity=str(quantity),
        order_type="market",
        limit_price=None,
        time_in_force="day",
        extended_hours=False,
        status="filled",
        filled_quantity=str(quantity),
        filled_avg_price=filled_avg_price,
        scenario="EXIT_FILLED",
        lookups=0,
        cancel_requested=False,
        received_at=world.clock.utc.isoformat(),
    )
    world.store.put(order)
    world.store.reduce_position(symbol, quantity)


def _manager(
    world: World,
    plans: FakeApprovedPlans,
    external_closures: FakeExternalPositionClosures | None = None,
) -> PositionPlanManager:
    return PositionPlanManager(
        plans=plans,
        external_closures=external_closures
        if external_closures is not None
        else (FakeExternalPositionClosures()),
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


def test_a_stop_trigger_persists_the_exact_quote_evidence_that_drove_it(world: World) -> None:
    """FORENSIC AUDIT FOLLOW-UP (2026-10-20 early-STOP incident, entry
    INT-PRP-089-PAPER-20261020T145108Z): reconstructing what actually triggered that STOP
    required pulling Alpaca's historical quotes after the fact -- nothing in the database
    recorded the bid/ask/timestamp/feed that drove it. This proves the fix: the claimed
    plan row now carries that evidence directly."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")

    manager.evaluate_once(now=world.clock.utc)

    claimed = plans.get(plan.plan_id)
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.STOP
    assert claimed.triggered_exit_quote_bid == Decimal("229.00")
    assert claimed.triggered_exit_quote_ask == Decimal("229.10")
    assert claimed.triggered_exit_quote_captured_at is not None
    assert claimed.triggered_exit_quote_source is not None


def test_a_thin_quote_bid_claims_the_trigger_with_zero_cross_check(world: World) -> None:
    """Item 9 reproduction: the exact mechanism behind the 2026-10-20 incident.

    `evaluate_exit_trigger` (`decision_candidate/approved_plan.py`) fires STOP whenever
    `last_price <= plan.stop_price`, where `last_price` is nothing but the raw bid
    `_bid_as_decimal` pulled off the quote. `_evaluate_unclaimed` claims this trigger via
    `claim_exit_trigger` -- the ONE irreversible action (`ApprovedPlan.is_claimed` then
    refuses the trigger forever, see `evaluate_exit_trigger`'s first line) -- WITHOUT ever
    checking the ask, the quote's own staleness, or any other corroborating source. Real
    production: Alpaca's IEX-only single-venue feed showed a genuine, several-seconds-stable
    bid of 335.72 while the consolidated tape traded 339.85-340.87 throughout, with zero
    trade ever printing at or near 335.72 -- i.e. a bid that bears no demonstrated
    relationship to the broader market can still win this irreversible claim. This test
    reproduces that: a bid inside the stop band with a realistic, narrow spread (so it is
    NOT caught by the separate, later, narrower spread-sanity check the preview/pricing
    stage applies -- see the next test for that boundary) claims and dispatches cleanly,
    proving the claim step itself performs no cross-check of any kind. This is TODAY's
    real, intentionally UNCHANGED behavior -- see the PR description for why adding a
    rejection check here is a separate, larger decision for the Owner to make explicitly.
    """
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.STOP
    # Unlike the real incident, this bid -- which never had to justify itself against
    # anything else -- is no longer silently discarded: it is now durable evidence.
    assert claimed.triggered_exit_quote_bid == Decimal("229.00")
    assert claimed.triggered_exit_quote_ask == Decimal("229.10")


def test_an_extreme_spread_claims_the_trigger_but_then_sticks_in_needs_attention(
    world: World,
) -> None:
    """The boundary discovered while writing the item 9 reproduction above: there IS a
    spread-sanity check in this codebase (a 1% limit), but it lives in the PREVIEW/pricing
    stage (`PreviewPositionExitHandler`), which runs AFTER `claim_exit_trigger` has already
    irreversibly consumed the one-shot trigger. An extreme spread therefore cannot be
    cross-checked away before the claim -- it can only block the DISPATCH of a trigger
    that is now permanently claimed, surfacing as `NEEDS_ATTENTION` instead of a silent bad
    fill. The plan is NOT stuck forever: `_resume_claimed` retries `_attempt_exit` with a
    FRESH quote on every later tick (this is why the real 2026-10-20 incident still
    resolved cleanly roughly a minute later, once the anomalous bid had already cleared by
    the time its own preview fetched a fresh quote) -- but until a fresh quote clears the
    1% bound, the claimed trigger cannot be reassigned, cancelled, or re-evaluated against
    a different kind, and the quote evidence that caused the stall is exactly what this
    PR's persistence change makes visible without needing operator log archaeology.
    """
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="229.00", ask="500.00")

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.NEEDS_ATTENTION
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.STOP
    assert claimed.is_claimed  # irreversible: the trigger was consumed before the refusal
    assert claimed.triggered_exit_quote_bid == Decimal("229.00")
    assert claimed.triggered_exit_quote_ask == Decimal("500.00")
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert sells == []  # nothing was actually dispatched


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

    # FORENSIC AUDIT FOLLOW-UP: a time-based claim never consults a quote, so it must
    # never carry quote evidence either (enforced by both `ApprovedPlan.__post_init__`
    # and the database guard -- see migration f3a7c9e2b164).
    claimed = plans.get(plan_id="PLAN-1")
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.MANDATORY_EXIT
    assert claimed.triggered_exit_quote_bid is None
    assert claimed.triggered_exit_quote_ask is None
    assert claimed.triggered_exit_quote_captured_at is None
    assert claimed.triggered_exit_quote_source is None


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


# ---------------------------------------------------------------------------
# External closure: a position closed outside this platform's own exit pipeline
# ---------------------------------------------------------------------------


def _closure(
    world: World, intent: str, *, client_order_id: str = "EXTERNAL-SELL-1"
) -> ExternalPositionClosure:
    return ExternalPositionClosure(
        closure_id=external_position_closure_id(intent),
        entry_intent_governance_id=intent,
        symbol="AAPL",
        quantity=8,
        broker_order_id="sim-external-1",
        client_order_id=client_order_id,
        filled_avg_price=Decimal("229.00"),
        recorded_by="owner",
        recorded_at=world.clock.utc,
    )


def test_a_claimed_plan_with_a_recorded_external_closure_is_never_evaluated_again(
    world: World,
) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    plans.claim_exit_trigger(plan.plan_id, kind=ExitTriggerKind.STOP, claimed_at=world.clock.utc)
    _simulate_external_sell(
        world, "AAPL", quantity=8, filled_avg_price="229.00", client_order_id="EXTERNAL-SELL-1"
    )
    closures = FakeExternalPositionClosures()
    closures.save(_closure(world, intent))
    manager = _manager(world, plans, closures)

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert len(outcomes) == 1
    assert outcomes[0].kind is PlanOutcomeKind.EXTERNALLY_CLOSED
    assert world.exits.attempts.for_entry(intent) == ()
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1  # the one EXTERNAL sell already simulated; none dispatched by us


def test_an_unclaimed_plan_with_a_recorded_external_closure_is_never_evaluated(
    world: World,
) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    _simulate_external_sell(
        world, "AAPL", quantity=8, filled_avg_price="229.00", client_order_id="EXTERNAL-SELL-1"
    )
    closures = FakeExternalPositionClosures()
    closures.save(_closure(world, intent))
    manager = _manager(world, plans, closures)
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")  # inside the stop band; would fire

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.EXTERNALLY_CLOSED
    claimed = plans.get(plan_id="PLAN-1")
    assert claimed is not None and not claimed.is_claimed  # the ORIGINAL plan row is untouched
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sells) == 1


def test_an_external_closure_recorded_after_restart_still_stops_the_plan(world: World) -> None:
    """Restart recovery for the NEW outcome: a fresh manager instance, reading the SAME
    durable closure record, must never resume Preview/Authorize/Submit for this plan."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    plans.claim_exit_trigger(plan.plan_id, kind=ExitTriggerKind.STOP, claimed_at=world.clock.utc)
    _simulate_external_sell(
        world, "AAPL", quantity=8, filled_avg_price="229.00", client_order_id="EXTERNAL-SELL-1"
    )
    closures = FakeExternalPositionClosures()
    closures.save(_closure(world, intent))

    restarted = world.restart()
    manager = _manager(restarted, plans, closures)
    outcomes = manager.evaluate_once(now=restarted.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.EXTERNALLY_CLOSED
    assert restarted.exits.attempts.for_entry(intent) == ()
    sells = [o for o in restarted.store.orders() if o.side == "sell"]
    assert len(sells) == 1
