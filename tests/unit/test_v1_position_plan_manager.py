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
    SimulatedMarketData,
    SimulatedOrder,
    SimulatedQuoteView,
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


def test_a_consistent_thin_quote_bid_still_claims_cleanly(world: World) -> None:
    """EXIT SIGNAL QUALITY GATE follow-up to item 9's original reproduction (history below).

    `evaluate_exit_trigger` fires STOP whenever `last_price <= plan.stop_price`; this bid
    is nothing but the raw `_bid_as_decimal` pulled off a single quote. Before the quality
    gate below, `_evaluate_unclaimed` claimed this irreversibly with no cross-check of any
    kind -- see `test_the_2026_10_20_incident_is_no_longer_claimed_on_a_single_outlier_tick`
    for the actual flickering-evidence case this gate now catches. THIS test proves the
    gate does not add friction when there is nothing to catch: a bid with no staged recent
    history gets the simulation's default self-consistent window (see
    `SimulatedMarketData.fetch_recent_quotes`), agrees with itself 100% of the time, and
    claims on the SAME tick exactly as before -- a real, sustained STOP must never wait.
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
    assert claimed.triggered_exit_quote_bid == Decimal("229.00")
    assert claimed.triggered_exit_quote_ask == Decimal("229.10")


def test_the_2026_10_20_incident_is_no_longer_claimed_on_a_single_outlier_tick(
    world: World,
) -> None:
    """EXIT SIGNAL QUALITY GATE (2026-10-21 hardening): the actual reproduction.

    Retrieving Alpaca's own historical IEX quote ticks for the 15 seconds preceding the
    real 2026-10-20 claim showed only 360 of 664 ticks (54%) actually crossed stop_price --
    a coin flip, not a sustained move; the ask stayed anchored near the real trading price
    throughout. This stages that exact shape: a 50/50 split between an outlier low bid and
    a normal high bid over a 15-second window, with the single LATEST tick happening to be
    the outlier (as it genuinely was in production). The plan must NOT be claimed -- it is
    left to re-evaluate next tick -- and no SELL is dispatched.
    """
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("338.40"), target=Decimal("400")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="335.72", ask="340.11")
    outlier = world.market_data.fetch_quote("AAPL")
    assert outlier is not None
    normal = SimulatedQuoteView(
        symbol="AAPL", bid="340.25", ask="340.52", captured_at=outlier.captured_at
    )
    world.market_data.stage_recent_quotes(
        "AAPL",
        [outlier, normal] * 6,  # 12 ticks, 50% crossing stop_price -- below 90%
    )

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.TRIGGER_EVIDENCE_UNCERTAIN
    assert "sample_size=12" in outcomes[0].detail
    assert "fraction=0.50" in outcomes[0].detail
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and not claimed.is_claimed
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert sells == []


def test_a_genuine_sustained_stop_still_claims_on_the_same_tick(world: World) -> None:
    """Fast-market check: a genuine, sustained move must NOT be delayed even one tick. A
    real gap-down's recent quote history moves together -- it does not oscillate back to
    the old level -- so every tick in the lookback window agrees, and the gate claims
    immediately, same as before this hardening existed."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="228.50", ask="228.60")
    primary = world.market_data.fetch_quote("AAPL")
    assert primary is not None
    captured_at = primary.captured_at
    world.market_data.stage_recent_quotes(
        "AAPL",
        [
            SimulatedQuoteView(symbol="AAPL", bid=bid, ask=ask, captured_at=captured_at)
            for bid, ask in (
                ("229.80", "229.90"),
                ("229.40", "229.50"),
                ("229.10", "229.20"),
                ("228.90", "229.00"),
                ("228.70", "228.80"),
                ("228.50", "228.60"),
            )
        ],
    )

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.STOP


def test_a_thin_sample_falls_back_to_trusting_the_single_quote(world: World) -> None:
    """Below `EXIT_QUOTE_CORROBORATION_MINIMUM_SAMPLE`, agreement cannot be meaningfully
    assessed at all (an illiquid stretch may simply not produce enough ticks in 15s). The
    gate deliberately fails OPEN toward the pre-hardening behavior here, never toward
    silently blocking a protective exit -- see the PR description's residual risks."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")
    world.market_data.stage_recent_quotes("AAPL", [])  # thinner than any real market

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.STOP


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


def test_a_flickering_target_spike_is_not_claimed_on_a_single_outlier_tick(world: World) -> None:
    """ADVERSARIAL REVIEW (PR #41, 2026-10-21): the gate is symmetric by construction
    (`_price_trigger_corroboration` handles STOP and TARGET identically), but nothing had
    exercised the TARGET side with inconsistent evidence until this test. A thin,
    momentarily high bid can claim a false TARGET exactly as a thin, momentarily low bid
    claimed the false 2026-10-20 STOP -- the same 50/50 flicker shape, mirrored above the
    target instead of below the stop."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("200"), target=Decimal("228")))
    manager = _manager(world, plans)
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")  # outlier spike above target
    outlier = world.market_data.fetch_quote("AAPL")
    assert outlier is not None
    normal = SimulatedQuoteView(
        symbol="AAPL", bid="220.00", ask="220.10", captured_at=outlier.captured_at
    )
    world.market_data.stage_recent_quotes("AAPL", [outlier, normal] * 6)

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.TRIGGER_EVIDENCE_UNCERTAIN
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and not claimed.is_claimed
    sells = [o for o in world.store.orders() if o.side == "sell"]
    assert sells == []


# ---------------------------------------------------------------------------
# A failing recent-quotes call fails OPEN, never blocking a protective exit
# ---------------------------------------------------------------------------


class _RecentQuotesAlwaysFail:
    """ADVERSARIAL REVIEW (PR #41): wraps a real `SimulatedMarketData` but makes
    `fetch_recent_quotes` raise, simulating an Alpaca historical-quotes outage that is
    independent of `fetch_quote` (the primary snapshot) still working fine -- exactly the
    asymmetric-failure shape a real outage could take."""

    def __init__(self, inner: SimulatedMarketData) -> None:
        self._inner = inner

    @property
    def endpoint_host(self) -> str:
        return self._inner.endpoint_host

    def fetch_quote(self, symbol: str) -> SimulatedQuoteView | None:
        return self._inner.fetch_quote(symbol)

    def fetch_recent_quotes(
        self, symbol: str, *, start: datetime, end: datetime, limit: int = 1000
    ) -> tuple[SimulatedQuoteView, ...]:
        raise ConnectionError("simulated Alpaca historical-quotes outage")


def test_a_failing_recent_quotes_call_still_claims_a_genuine_stop(world: World) -> None:
    """ADVERSARIAL REVIEW (PR #41, 2026-10-21): a `fetch_recent_quotes` failure (network
    error, timeout) must fail OPEN exactly like an empty/thin result does -- never
    propagate and abort the entire tick (every other plan `evaluate_once` was about to
    evaluate too) over a failure in a check that is, by this gate's own design, allowed
    to be unavailable. `_corroborate_price_trigger` catches it and falls back to trusting
    the single latest quote, same as the thin-sample case."""
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plan = plans.save(_plan(world, intent, stop=Decimal("230"), target=Decimal("260")))
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")
    broken_manager = PositionPlanManager(
        plans=plans,
        external_closures=FakeExternalPositionClosures(),
        intents=world.repositories.intents,
        entry_attempts=world.repositories.attempts,
        exit_attempts=world.exits.attempts,
        previews=world.exits.previews,
        authorizations=world.exits.authorizations,
        acknowledgements=world.exits.acknowledgements,
        events=world.exits.events,
        rounds=world.exits.rounds,
        broker=world.broker,
        market_data=_RecentQuotesAlwaysFail(world.market_data),
        configurations=world.repositories.configurations,
        environment="SIMULATION",
        time_source=world.clock,
    )

    outcomes = broken_manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED, outcomes[0].detail
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.STOP


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


def test_an_uncertain_stop_candidate_past_the_mandatory_deadline_still_claims_mandatory_exit(
    world: World,
) -> None:
    """ADVERSARIAL REVIEW (PR #41, 2026-10-21): `evaluate_exit_trigger` has ALWAYS
    prioritized STOP over MANDATORY_EXIT when both conditions are simultaneously true
    (`decision_candidate/approved_plan.py`'s own docstring: "a price that has already
    crossed the stop is the more urgent risk-bounding fact"). Before the quality gate,
    this never mattered in practice: whichever branch `evaluate_exit_trigger` picked was
    claimed immediately, so SOME exit happened right away regardless of which kind won.

    The quality gate breaks that property: if the price condition is ALSO met but its
    evidence is uncertain, `_evaluate_unclaimed` used to return `TRIGGER_EVIDENCE_UNCERTAIN`
    and claim NOTHING -- not STOP (uncertain), and not MANDATORY_EXIT either, because
    `evaluate_exit_trigger` already returned STOP before ever examining the deadline. A
    plan already past its mandatory liquidation deadline, with a flickering price also
    sitting at the stop, would sit completely unclaimed -- directly contradicting the
    mission's own requirement: "A poor-quality quote must not silently prevent timely
    mandatory exit." This proves the fix: MANDATORY_EXIT is independently re-checked and
    still claims on this exact tick.
    """
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    deadline = world.clock.utc + timedelta(minutes=5)
    plans.save(
        _plan(
            world,
            intent,
            stop=Decimal("230"),
            target=Decimal("260"),
            mandatory_liquidation_at=deadline,
        )
    )
    manager = _manager(world, plans)
    world.clock.advance(int(timedelta(minutes=5).total_seconds()) - 60)  # past the deadline
    _set_quote(world, "AAPL", bid="229.00", ask="229.10")  # ALSO below the stop
    outlier = world.market_data.fetch_quote("AAPL")
    assert outlier is not None
    normal = SimulatedQuoteView(
        symbol="AAPL", bid="240.00", ask="240.10", captured_at=outlier.captured_at
    )
    world.market_data.stage_recent_quotes(
        "AAPL",
        [outlier, normal] * 6,  # 50/50 split -- the STOP price condition is uncertain
    )

    outcomes = manager.evaluate_once(now=world.clock.utc)

    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    claimed = plans.get(plan_id="PLAN-1")
    assert claimed is not None
    assert claimed.triggered_exit_kind is ExitTriggerKind.MANDATORY_EXIT
    # A time-based claim never consults a quote -- it must never carry quote evidence,
    # exactly like `test_the_mandatory_exit_fires_on_time_alone` above.
    assert claimed.triggered_exit_quote_bid is None
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
