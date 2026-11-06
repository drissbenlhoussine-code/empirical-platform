"""RELIABLE, BOUNDED exit reconciliation and retry management (fix D3).

Drives the REAL `PositionPlanManager` over the REAL simulation broker and the REAL M087 exit
handlers, with deterministic clocks. The defect these pin: a STOP / TARGET / MANDATORY exit is
ONE day-limit sell at the trigger-time bid; before this fix the manager only reconciled it,
never cancelled or repriced, so an unfilled exit left the position open for ever, and a
CANCELED / REJECTED / EXPIRED attempt killed automatic management for good.

Invariants asserted throughout: at most ONE live sell order at the broker at any time, a
replacement only after the predecessor is broker-confirmed terminal, remaining quantity only,
LIMIT orders only, a bounded number of attempts, loud NEEDS_ATTENTION when the budget is spent.
"""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans
from tests.unit.test_v1_position_plan_manager import (
    _manager,
    _open_position,
    _plan,
)

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, derive_system_identity
from empirical_platform.decision_candidate.position_exit import (
    EXIT_MAX_ATTEMPTS_PER_SESSION,
    EXIT_MAX_CONCESSION_BPS,
    EXIT_RETRIES_EXHAUSTED_EVENT_TYPE,
    PositionExitAttempt,
    PositionExitState,
    exit_limit_concession_bps,
    exit_limit_price,
)
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedOrder,
    SimulationExitScenario,
    default_scenario_table,
)
from empirical_platform.usecases.position_exit import (
    CancelPositionExitCommand,
    CancelPositionExitHandler,
)
from empirical_platform.usecases.position_plan_manager import (
    PlanEvaluationOutcome,
    PlanOutcomeKind,
    PositionPlanManager,
)

_REST = SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED
_FILL = SimulationExitScenario.EXIT_FILLED
_CLOSED = PlanEvaluationOutcome("-", "-", PlanOutcomeKind.EXIT_RECONCILED, "position closed")
_TERMINAL_BROKER = {"filled", "canceled", "rejected", "expired"}


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


def _stage(world: World, *, bid: str, scenario: SimulationExitScenario) -> None:
    world.store.stage(
        scenarios={"AAPL": default_scenario_table()["AAPL"]},
        quotes={"AAPL": (bid, str(Decimal(bid) + Decimal("0.1")))},
        exit_scenarios={"AAPL": scenario},
    )


def _sells(world: World) -> list[SimulatedOrder]:
    return [o for o in world.store.orders() if o.side == "sell"]


def _live_sells(world: World) -> list[SimulatedOrder]:
    return [o for o in _sells(world) if o.status not in _TERMINAL_BROKER]


def _attempts(world: World, intent: str) -> tuple[PositionExitAttempt, ...]:
    return world.exits.attempts.for_entry(intent)


def _tick(world: World, manager: PositionPlanManager, *, advance: int = 0) -> PlanEvaluationOutcome:
    if advance:
        world.clock.advance(advance)
    # On the claim tick the freshly claimed plan is also resumed (reconciled) in the same
    # pass, so more than one outcome is normal; the LAST one is where the plan ended up.
    outcomes = manager.evaluate_once(now=world.clock.utc)
    # A closed position drops out of the managed set: report that as a plain reconcile.
    outcome = outcomes[-1] if outcomes else _CLOSED
    assert len(_live_sells(world)) <= 1, "at most ONE live sell order at the broker, ever"
    return outcome


def _setup(
    world: World,
    *,
    stop: str = "230",
    bid: str = "229.00",
    scenario: SimulationExitScenario = _REST,
    plan: ApprovedPlan | None = None,
) -> tuple[str, FakeApprovedPlans, PositionPlanManager]:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    plans.save(plan or _plan(world, intent, stop=Decimal(stop), target=Decimal("260")))
    manager = _manager(world, plans)
    _stage(world, bid=bid, scenario=scenario)
    return intent, plans, manager


# ---------------------------------------------------------------------------
# The pure price rule
# ---------------------------------------------------------------------------


def test_limit_price_rule_is_bounded_and_never_above_the_bid() -> None:
    bid = Decimal("229.00")
    assert exit_limit_price(bid, generation=0) == bid
    previous = bid
    for generation in range(0, 12):
        price = exit_limit_price(bid, generation=generation)
        assert price <= previous <= bid
        assert price >= bid * (1 - Decimal(EXIT_MAX_CONCESSION_BPS) / 10000) - Decimal("0.01")
        previous = price
    assert exit_limit_price(bid, generation=1) == Decimal("228.77")
    assert exit_limit_concession_bps(99) == EXIT_MAX_CONCESSION_BPS
    with pytest.raises(ValueError):
        exit_limit_concession_bps(-1)


# ---------------------------------------------------------------------------
# The old repro, turned green
# ---------------------------------------------------------------------------


def test_unfilled_stop_is_repriced_after_the_spacing_window_and_fills(world: World) -> None:
    intent, _, manager = _setup(world)
    _tick(world, manager)
    assert len(_attempts(world, intent)) == 1
    (first,) = _sells(world)
    assert first.limit_price == "229.00"

    # Inside the spacing window nothing is cancelled and nothing is re-sent.
    _tick(world, manager, advance=15)
    assert len(_sells(world)) == 1 and _sells(world)[0].status == "accepted"

    # The market keeps collapsing; past the spacing window the exit is replaced, and this
    # time the venue fills it.
    _stage(world, bid="200.00", scenario=_FILL)
    outcome = _tick(world, manager, advance=20)
    assert outcome.kind is PlanOutcomeKind.EXIT_SUBMITTED, outcome.detail
    sells = _sells(world)
    assert [s.status for s in sells] == ["canceled", "accepted"]
    assert sells[1].limit_price == "199.80"  # bid 200.00 less one 10 bps step, a LIMIT
    assert sells[1].order_type == "limit"
    for _ in range(4):
        _tick(world, manager, advance=5)
    attempts = _attempts(world, intent)
    assert [a.state for a in attempts] == [PositionExitState.CANCELED, PositionExitState.FILLED]
    assert attempts[-1].position_closed
    assert world.store.position("AAPL") == 0
    assert len({a.client_order_id for a in attempts}) == 2


def test_the_original_repro_no_longer_leaves_the_position_open_forever(world: World) -> None:
    """STOP at 229.00, the bid falls to 200 / 150 / 100 and nothing ever fills: previously
    one sell at 229.00 for ever. Now: bounded, bid-relative, loud, never absurdly low."""
    intent, _, manager = _setup(world)
    _tick(world, manager)
    for bid in ("200.00", "150.00", "100.00"):
        _stage(world, bid=bid, scenario=_REST)
        _tick(world, manager, advance=30)
    sells = _sells(world)
    assert len(sells) >= 3
    prices = [Decimal(s.limit_price or "0") for s in sells]
    assert prices[0] == Decimal("229.00")
    # Every later price is within the hard concession cap of the bid it was priced from.
    for price, bid in zip(prices[1:], ("200.00", "150.00", "100.00"), strict=False):
        assert Decimal(bid) * Decimal("0.995") - Decimal("0.01") <= price <= Decimal(bid)
    assert sum(1 for s in sells if s.status not in _TERMINAL_BROKER) == 1
    assert world.store.position("AAPL") == 8
    assert all(a.quantity == 8 for a in _attempts(world, intent))


# ---------------------------------------------------------------------------
# Bounded retries and the loud stop
# ---------------------------------------------------------------------------


def test_max_attempts_exhausted_is_loud_durable_and_stops_automatic_sends(world: World) -> None:
    intent, _, manager = _setup(world)
    _tick(world, manager)
    outcomes = [_tick(world, manager, advance=15) for _ in range(40)]
    attempts = _attempts(world, intent)
    assert len(attempts) == EXIT_MAX_ATTEMPTS_PER_SESSION
    assert len(_sells(world)) == EXIT_MAX_ATTEMPTS_PER_SESSION
    last = outcomes[-1]
    assert last.kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert EXIT_RETRIES_EXHAUSTED_EVENT_TYPE in last.detail
    # The final order is left working (never cancelled with nothing to replace it) and is
    # still reconciled; nothing further is sent no matter how long this runs.
    assert len(_live_sells(world)) == 1
    events = [
        e
        for e in world.exits.events.for_entry(intent)
        if e.event_type == EXIT_RETRIES_EXHAUSTED_EVENT_TYPE
    ]
    assert len(events) == 1, "one durable alert, not one per tick"
    for _ in range(10):
        _tick(world, manager, advance=15)
    assert len(_attempts(world, intent)) == EXIT_MAX_ATTEMPTS_PER_SESSION


def test_a_rejected_replacement_is_retried_a_bounded_number_of_times_then_needs_attention(
    world: World,
) -> None:
    intent, _, manager = _setup(world)
    _tick(world, manager)
    _stage(world, bid="200.00", scenario=SimulationExitScenario.EXIT_REJECTION)
    outcomes = [_tick(world, manager, advance=15) for _ in range(40)]
    attempts = _attempts(world, intent)
    assert len(attempts) == EXIT_MAX_ATTEMPTS_PER_SESSION
    assert [a.state for a in attempts[1:]] == [PositionExitState.REJECTED] * 4
    assert attempts[0].state is PositionExitState.CANCELED
    assert outcomes[-1].kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert EXIT_RETRIES_EXHAUSTED_EVENT_TYPE in outcomes[-1].detail
    assert _live_sells(world) == [] and world.store.position("AAPL") == 8


# ---------------------------------------------------------------------------
# Partial fills
# ---------------------------------------------------------------------------


def test_partial_fill_then_only_the_remaining_quantity_is_replaced(world: World) -> None:
    intent, _, manager = _setup(world, scenario=SimulationExitScenario.EXIT_PARTIAL_FILL)
    _tick(world, manager)
    _tick(world, manager, advance=15)
    _stage(world, bid="228.00", scenario=_FILL)
    _tick(world, manager, advance=15)  # observes the partial, cancels, replaces the rest
    first, second = _attempts(world, intent)
    assert first.state is PositionExitState.CANCELED
    assert first.filled_quantity == Decimal(4)
    assert second.quantity == 4, "remaining quantity only, never the original 8"
    for _ in range(4):
        _tick(world, manager, advance=5)
    assert world.store.position("AAPL") == 0
    assert sum(Decimal(s.filled_quantity) for s in _sells(world)) == Decimal(8)
    assert _attempts(world, intent)[-1].position_closed


def test_an_external_position_change_stops_the_replacement_rather_than_overselling(
    world: World,
) -> None:
    intent, _, manager = _setup(world)
    _tick(world, manager)
    world.store.reduce_position("AAPL", 3)  # someone else sold 3 at the broker
    _stage(world, bid="228.00", scenario=_FILL)
    outcome = _tick(world, manager, advance=30)
    assert outcome.kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert len(_sells(world)) == 1 and _live_sells(world) == []
    assert len(_attempts(world, intent)) == 1


# ---------------------------------------------------------------------------
# Cancel / replace races and uncertainty
# ---------------------------------------------------------------------------


def test_order_that_fills_during_the_cancel_is_never_replaced(world: World) -> None:
    intent, _, manager = _setup(world, scenario=SimulationExitScenario.EXIT_CANCEL_FILL_RACE)
    _tick(world, manager)
    _tick(world, manager, advance=30)  # cancel is requested and LOSES to the fill
    (attempt,) = _attempts(world, intent)
    assert attempt.state is PositionExitState.FILLED and attempt.position_closed
    assert len(_sells(world)) == 1
    assert world.store.position("AAPL") == 0
    _tick(world, manager, advance=30)
    assert len(_sells(world)) == 1


class _FlakyCancelBroker:
    """Delegates everything; `cancel_order` raises `failures` times (reaching the broker
    first when `deliver` is true, i.e. the acknowledgement is lost, not the request)."""

    def __init__(self, inner: object, *, failures: int, deliver: bool) -> None:
        self._inner = inner
        self.failures = failures
        self.deliver = deliver

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def cancel_order(self, broker_order_id: str) -> tuple[int, str]:
        if self.failures > 0:
            self.failures -= 1
            if self.deliver:
                self._inner.cancel_order(broker_order_id)  # type: ignore[attr-defined]
            raise TimeoutError("simulated: the cancel acknowledgement never arrived")
        return self._inner.cancel_order(broker_order_id)  # type: ignore[attr-defined,no-any-return]


def _manager_over(world: World, plans: FakeApprovedPlans, broker: object) -> PositionPlanManager:
    inner = _manager(world, plans)
    del inner
    return PositionPlanManager(
        plans=plans,
        external_closures=world.external_closures,
        intents=world.repositories.intents,
        entry_attempts=world.repositories.attempts,
        exit_attempts=world.exits.attempts,
        previews=world.exits.previews,
        authorizations=world.exits.authorizations,
        acknowledgements=world.exits.acknowledgements,
        events=world.exits.events,
        rounds=world.exits.rounds,
        broker=broker,  # type: ignore[arg-type]
        market_data=world.market_data,
        configurations=world.repositories.configurations,
        environment="SIMULATION",
        time_source=world.clock,
    )


def test_cancel_acknowledgement_unknown_reconciles_first_and_never_duplicates(
    world: World,
) -> None:
    intent, plans, _ = _setup(world)
    manager = _manager_over(
        world, plans, _FlakyCancelBroker(world.broker, failures=1, deliver=True)
    )
    _tick(world, manager)
    outcome = _tick(
        world, manager, advance=30
    )  # the DELETE reached the broker, its answer was lost
    assert outcome.kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert "cancel acknowledgement unknown" in outcome.detail
    assert len(_sells(world)) == 1
    # Next tick reconciles by client_order_id: the broker says canceled, and ONLY THEN is the
    # next generation sent.
    _stage(world, bid="228.00", scenario=_FILL)
    outcome = _tick(world, manager, advance=1)
    assert [a.state for a in _attempts(world, intent)][0] is PositionExitState.CANCELED
    assert len(_sells(world)) == 2
    for _ in range(3):
        _tick(world, manager, advance=5)
    assert world.store.position("AAPL") == 0


def test_cancel_that_never_reached_the_broker_sends_no_replacement_and_retries_bounded(
    world: World,
) -> None:
    intent, plans, _ = _setup(world)
    flaky = _FlakyCancelBroker(world.broker, failures=2, deliver=False)
    manager = _manager_over(world, plans, flaky)
    _tick(world, manager)
    _tick(world, manager, advance=30)  # cancel error #1
    assert len(_sells(world)) == 1 and _sells(world)[0].status == "accepted"
    _tick(world, manager, advance=15)  # inside the spacing window: no new cancel
    assert flaky.failures == 1
    _tick(world, manager, advance=15)  # cancel error #2
    assert flaky.failures == 0 and len(_sells(world)) == 1
    _tick(world, manager, advance=30)  # cancel succeeds, order canceled, replacement sent
    assert [s.status for s in _sells(world)][0] == "canceled"
    assert len(_sells(world)) == 2
    assert len(_attempts(world, intent)) == 2


def test_cancel_refused_because_the_order_already_finished_is_reconciled_not_resent(
    world: World,
) -> None:
    intent, _, manager = _setup(world, scenario=SimulationExitScenario.EXIT_PARTIAL_FILL)
    _tick(world, manager)
    # The venue completes the order underneath us (fills it whole) before we can cancel.
    order = _sells(world)[0]
    world.store.put(
        replace(order, status="filled", filled_quantity=order.quantity, filled_avg_price="229.00")
    )
    world.store.reduce_position("AAPL", 8)
    _tick(world, manager, advance=30)
    (attempt,) = _attempts(world, intent)
    assert attempt.state is PositionExitState.FILLED and attempt.position_closed
    assert len(_sells(world)) == 1


# ---------------------------------------------------------------------------
# Uncertainty: an ambiguous send is never blindly resent
# ---------------------------------------------------------------------------


def test_an_ambiguous_send_is_reconciled_by_client_order_id_and_never_resent(
    world: World,
) -> None:
    intent, _, manager = _setup(
        world, scenario=SimulationExitScenario.EXIT_RECONCILIATION_NOT_FOUND
    )
    _tick(world, manager)
    (first,) = _attempts(world, intent)
    assert first.state is PositionExitState.SUBMISSION_UNKNOWN
    seen = {first.attempt_id}
    for _ in range(12):
        _tick(world, manager, advance=15)
        attempts = _attempts(world, intent)
        active = [a for a in attempts if a.state not in {PositionExitState.REJECTED}]
        assert len(active) <= 1, "never two live attempts"
        for earlier in attempts[:-1]:
            # A newer attempt exists only once the older one is a broker-confirmed terminal.
            assert earlier.is_terminal, earlier
        seen |= {a.attempt_id for a in attempts}
    assert _sells(world) == [], "the simulated broker never received any of them"
    rounds = world.exits.rounds.for_attempt(first.attempt_id)
    assert len(rounds) >= 2, "reconciled by client_order_id, not guessed"


# ---------------------------------------------------------------------------
# Market hours and DAY expiry
# ---------------------------------------------------------------------------


def test_nothing_is_cancelled_or_sent_while_the_market_is_closed(world: World) -> None:
    intent, _, manager = _setup(world)
    _tick(world, manager)
    world.store.set_market_open(False)
    outcome = _tick(world, manager, advance=120)
    assert outcome.kind is PlanOutcomeKind.EXIT_WAITING_FOR_MARKET
    assert _sells(world)[0].status == "accepted" and len(_sells(world)) == 1
    assert world.store.orders()[0].cancel_requested is False
    world.store.set_market_open(True)
    _tick(world, manager, advance=15)
    assert len(_sells(world)) == 2


def test_a_day_exit_that_expires_at_the_close_is_rearmed_next_session(world: World) -> None:
    intent, _, manager = _setup(world)
    _tick(world, manager)
    (order,) = _sells(world)
    world.store.set_market_open(False)
    world.store.put(replace(order, status="expired"))  # the broker's DAY expiry at the close
    outcome = _tick(world, manager, advance=3600)
    assert outcome.kind is PlanOutcomeKind.EXIT_WAITING_FOR_MARKET
    (expired,) = _attempts(world, intent)
    assert expired.state is PositionExitState.EXPIRED
    assert len(_sells(world)) == 1, "nothing is sent while the market is closed"
    # Next session: re-armed with a NEW generation (new identity), a fresh budget.
    world.store.set_market_open(True)
    _stage(world, bid="227.00", scenario=_FILL)
    _tick(world, manager, advance=3600)
    for _ in range(3):
        _tick(world, manager, advance=5)
    attempts = _attempts(world, intent)
    assert [a.state for a in attempts] == [PositionExitState.EXPIRED, PositionExitState.FILLED]
    assert attempts[0].client_order_id != attempts[1].client_order_id
    assert attempts[0].attempt_id != attempts[1].attempt_id
    assert attempts[1].position_closed and world.store.position("AAPL") == 0


def test_a_canceled_or_rejected_attempt_no_longer_kills_automatic_management(
    world: World,
) -> None:
    """The second half of the defect: CANCELED / REJECTED was excluded from
    `active_for_entry` while the consumed deterministic authorization blocked any new one, so
    every later tick returned 'no unused human exit authorization exists' for ever."""
    intent, plans, manager = _setup(world)
    _tick(world, manager)
    (attempt,) = _attempts(world, intent)
    CancelPositionExitHandler(
        attempts=world.exits.attempts,
        acknowledgements=world.exits.acknowledgements,
        events=world.exits.events,
        broker=world.broker,
    ).handle(CancelPositionExitCommand(attempt.attempt_id, at=world.clock.utc))  # the Owner cancels
    _stage(world, bid="228.00", scenario=_FILL)
    for _ in range(6):
        _tick(world, manager, advance=15)
    assert _attempts(world, intent)[-1].position_closed
    assert world.store.position("AAPL") == 0


def test_a_mandatory_liquidation_reprices_on_the_faster_clock(world: World) -> None:
    intent = _open_position(world)
    plans = FakeApprovedPlans()
    owner = "OWN-1"
    plans.save(
        ApprovedPlan(
            plan_id="PLAN-1",
            candidate_id="CAND-1",
            entry_intent_governance_id=intent,
            symbol="AAPL",
            approved_quantity=Decimal("8"),
            stop_price=Decimal("200"),
            target_price=Decimal("999"),
            mandatory_liquidation_at=world.clock.utc,
            owner_approval_id=owner,
            system_identity=derive_system_identity(plan_id="PLAN-1", owner_approval_id=owner),
            created_at=world.clock.utc,
        )
    )
    manager = _manager(world, plans)
    _stage(world, bid="229.00", scenario=_REST)
    _tick(world, manager)
    _stage(world, bid="229.00", scenario=_FILL)
    _tick(world, manager, advance=16)  # a STOP would still be inside its 30s window
    assert [s.status for s in _sells(world)][0] == "canceled"
    assert len(_sells(world)) == 2


# ---------------------------------------------------------------------------
# Restart recovery and the kill switch
# ---------------------------------------------------------------------------


def test_a_brand_new_manager_every_tick_still_never_duplicates(world: World) -> None:
    """All state is durable: rebuild the manager from the durable repositories on EVERY tick
    through the whole unfilled -> cancel -> replace -> fill sequence."""
    intent, plans, _ = _setup(world)
    _stage(world, bid="229.00", scenario=_REST)
    _tick(world, _manager(world, plans))
    _tick(world, _manager(world, plans), advance=20)
    _stage(world, bid="226.00", scenario=_FILL)
    for _ in range(8):
        _tick(world, _manager(world, plans), advance=15)
    attempts = _attempts(world, intent)
    assert [a.state for a in attempts] == [PositionExitState.CANCELED, PositionExitState.FILLED]
    assert world.store.position("AAPL") == 0
    assert len(_sells(world)) == 2


def test_a_restart_in_the_middle_of_a_cancel_resumes_safely(world: World) -> None:
    intent, plans, manager = _setup(world)
    _tick(world, manager)
    (attempt,) = _attempts(world, intent)
    world.clock.advance(30)
    # The process dies right after the cancel was requested (CANCEL_REQUESTED is durable).
    CancelPositionExitHandler(
        attempts=world.exits.attempts,
        acknowledgements=world.exits.acknowledgements,
        events=world.exits.events,
        broker=world.broker,
    ).handle(CancelPositionExitCommand(attempt.attempt_id, at=world.clock.utc))
    assert _attempts(world, intent)[0].state is PositionExitState.CANCEL_REQUESTED
    _stage(world, bid="228.00", scenario=_FILL)
    restarted = _manager(world, plans)
    _tick(world, restarted)
    for _ in range(4):
        _tick(world, restarted, advance=5)
    attempts = _attempts(world, intent)
    assert [a.state for a in attempts] == [PositionExitState.CANCELED, PositionExitState.FILLED]
    assert len(_sells(world)) == 2 and world.store.position("AAPL") == 0


def test_a_crash_between_authorize_and_submit_of_a_replacement_resumes_the_same_slot(
    world: World,
) -> None:
    intent, plans, manager = _setup(world)
    _tick(world, manager)
    _stage(world, bid="228.00", scenario=_FILL)
    submit = manager._submit_handler

    class _Crash:
        def handle(self, command: object) -> object:
            raise RuntimeError("process died between Authorize and Submit")

    manager._submit_handler = _Crash()  # type: ignore[assignment]
    world.clock.advance(30)
    with pytest.raises(RuntimeError):
        manager.evaluate_once(now=world.clock.utc)
    assert len(_attempts(world, intent)) == 1, "no replacement attempt was claimed"
    assert _attempts(world, intent)[0].state is PositionExitState.CANCELED
    restarted = _manager(world, plans)
    del submit
    for _ in range(6):
        _tick(world, restarted, advance=5)
    attempts = _attempts(world, intent)
    assert [a.state for a in attempts] == [PositionExitState.CANCELED, PositionExitState.FILLED]
    assert len(_sells(world)) == 2
    # The SAME generation slot was resumed: exactly two previews and authorizations exist.
    assert len(world.exits.previews.rows) == 2  # type: ignore[attr-defined]
    assert len(world.exits.authorizations.rows) == 2  # type: ignore[attr-defined]


def test_the_kill_switch_never_blocks_an_exit_or_its_replacement(world: World) -> None:
    intent, _, manager = _setup(world)
    world.kill_switch.engage(changed_by="owner", changed_at=world.clock.utc, reason="test")
    _tick(world, manager)
    _stage(world, bid="228.00", scenario=_FILL)
    for _ in range(6):
        _tick(world, manager, advance=15)
    assert _attempts(world, intent)[-1].position_closed
    assert world.kill_switch.engaged


def test_every_exit_is_a_limit_order(world: World) -> None:
    _, _, manager = _setup(world)
    _tick(world, manager)
    for _ in range(12):
        _tick(world, manager, advance=15)
    assert _sells(world)
    assert {s.order_type for s in _sells(world)} == {"limit"}
    assert all(s.limit_price is not None for s in _sells(world))
