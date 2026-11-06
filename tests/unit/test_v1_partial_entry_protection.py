"""PARTIAL ENTRY PROTECTION and PLAN ISOLATION (safety gaps 1-3).

Drives the REAL `PositionPlanManager` + `EntryRemainderProtector` over the REAL simulation broker
(MSFT's entry fills half then rests) with deterministic clocks. Invariants asserted throughout:
an entry is never sent twice, an entry with zero fills is never cancelled, the cancel budget is
bounded, and the filled quantity (never the approved quantity) is what gets sold.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans
from tests.unit.test_m087_position_exit_domain import a_snapshot
from tests.unit.test_v1_position_plan_manager import _intent, _manager, _plan

from empirical_platform.decision_candidate.approved_plan import ApprovedPlan, ExitTriggerKind
from empirical_platform.decision_candidate.paper_execution import (
    ExecutionAttempt,
    PaperExecutionState,
)
from empirical_platform.decision_candidate.paper_portfolio_limits import (
    ledger_counts_order,
    trading_day_bounds,
)
from empirical_platform.decision_candidate.position_exit import exit_eligibility
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedOrder,
    SimulationExitScenario,
    default_scenario_table,
)
from empirical_platform.usecases.entry_remainder_protection import (
    ENTRY_CANCEL_MIN_SPACING_SECONDS,
    ENTRY_MAX_CANCEL_REQUESTS,
    ENTRY_PARTIAL_PROACTIVE_CANCEL_SECONDS,
    ENTRY_REMAINDER_EXHAUSTED_EVENT_TYPE,
    EntryRemainderProtector,
)
from empirical_platform.usecases.paper_execution import (
    ReconcilePaperOrderCommand,
    ReconcilePaperOrderHandler,
)
from empirical_platform.usecases.position_plan_manager import (
    PLAN_EVALUATION_ERROR_EVENT_TYPE,
    PlanOutcomeKind,
    PositionPlanManager,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


def _protector(world: World, broker: object | None = None) -> EntryRemainderProtector:
    return EntryRemainderProtector(
        attempts=world.repositories.attempts,
        acknowledgements=world.repositories.acknowledgements,
        events=world.repositories.events,
        rounds=world.repositories.rounds,
        authorizations=world.repositories.authorizations,
        previews=world.repositories.previews,
        broker=broker or world.broker,  # type: ignore[arg-type]
        time_source=world.clock,
    )


def _guarded_manager(
    world: World, plans: FakeApprovedPlans, broker: object | None = None
) -> PositionPlanManager:
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
        broker=broker or world.broker,  # type: ignore[arg-type]
        market_data=world.market_data,
        configurations=world.repositories.configurations,
        environment="SIMULATION",
        time_source=world.clock,
        entry_remainder_protector=_protector(world, broker),
    )


def _approve_and_settle(world: World, symbol: str) -> str:
    world.load_day((symbol,))
    proposal = world.proposal_id(symbol)
    view = world.service.prepare_approval(proposal)
    assert world.service.confirm_approval(proposal, view.ticket).sent == "sent"
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    return _intent(world, symbol)


def _partial_entry(world: World) -> str:
    """An entry that is PARTIALLY_FILLED (half of 4 filled, remainder resting)."""
    intent = _approve_and_settle(world, "MSFT")
    entry = _entry(world, intent)
    assert entry.state is PaperExecutionState.PARTIALLY_FILLED
    assert entry.filled_quantity == Decimal(2)
    return intent


def _entry(world: World, intent: str) -> ExecutionAttempt:
    entry = world.repositories.attempts.for_intent(intent)
    assert entry is not None
    return entry


def _stage_msft(world: World, bid: str) -> None:
    world.store.stage(
        scenarios={"MSFT": default_scenario_table()["MSFT"]},
        quotes={"MSFT": (bid, str(Decimal(bid) + Decimal("0.2")))},
        exit_scenarios={"MSFT": SimulationExitScenario.EXIT_FILLED},
    )


def _plan_for(
    world: World, intent: str, *, stop: str, bid: str, deadline_in: int | None = None
) -> tuple[FakeApprovedPlans, ApprovedPlan]:
    plan = replace(
        _plan(world, intent, stop=Decimal(stop), target=Decimal("900")),
        symbol="MSFT",
        approved_quantity=Decimal(4),
    )
    if deadline_in is not None:
        plan = replace(
            plan, mandatory_liquidation_at=world.clock.utc + timedelta(seconds=deadline_in)
        )
    plans = FakeApprovedPlans()
    plans.save(plan)
    _stage_msft(world, bid)
    return plans, plan


def _buys(world: World) -> list[SimulatedOrder]:
    return [o for o in world.store.orders() if o.side == "buy"]


def _sells(world: World) -> list[SimulatedOrder]:
    return [o for o in world.store.orders() if o.side == "sell"]


def _entry_events(world: World, intent: str, event_type: str) -> list[object]:
    return [e for e in world.repositories.events.for_intent(intent) if e.event_type == event_type]


class _CancelBroker:
    """Delegates everything; `cancel_order` is counted and can fail, lose its answer or race
    a fill."""

    def __init__(self, inner: object, *, mode: str = "ok", failures: int = 0) -> None:
        self._inner = inner
        self.mode = mode
        self.failures = failures
        self.cancel_calls = 0

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def cancel_order(self, broker_order_id: str) -> tuple[int, str]:
        self.cancel_calls += 1
        inner = self._inner
        store = inner.store if hasattr(inner, "store") else inner._store  # type: ignore[attr-defined]
        if self.mode == "fill_race":
            order = store.order_by_broker_id(broker_order_id)
            store.add_position(order.symbol, int(order.quantity) - int(order.filled_quantity))
            store.put(
                replace(
                    order,
                    status="filled",
                    filled_quantity=order.quantity,
                    filled_avg_price="418.30",
                )
            )
            return 422, '{"message": "order is already filled"}'
        if self.failures > 0:
            self.failures -= 1
            if self.mode == "lost_ack":
                inner.cancel_order(broker_order_id)  # type: ignore[attr-defined]
            raise TimeoutError("simulated: the cancel acknowledgement never arrived")
        return inner.cancel_order(broker_order_id)  # type: ignore[attr-defined,no-any-return]


# ---------------------------------------------------------------------------
# Gap 1: a partially filled entry that EXPIRES still holds shares
# ---------------------------------------------------------------------------


def test_an_expired_partial_entry_is_a_closable_holding_entry(world: World) -> None:
    intent = _partial_entry(world)
    entry = _entry(world, intent)
    order = next(o for o in world.store.orders() if o.broker_order_id == entry.broker_order_id)
    world.store.put(replace(order, status="expired"))  # the DAY remainder lapsed at the close
    world.clock.advance(5)
    world.service.refresh_executions()
    entry = _entry(world, intent)
    assert entry.state is PaperExecutionState.EXPIRED and entry.filled_quantity == Decimal(2)
    assessment = world.service.exits.assess(intent)  # type: ignore[union-attr]
    assert assessment.eligible, assessment.refusals
    assert assessment.snapshot.attributable_quantity == 2
    # ... and the automatic manager can now stop it out, selling exactly the filled shares.
    plans, _ = _plan_for(world, intent, stop="500", bid="410.00")
    outcomes = _manager(world, plans).evaluate_once(now=world.clock.utc)
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED, outcomes
    (sell,) = _sells(world)
    assert sell.quantity == "2"


def test_an_expired_entry_with_no_fills_is_still_refused() -> None:
    refusals = exit_eligibility(
        a_snapshot(
            entry_state="EXPIRED", entry_filled_quantity=Decimal(0), broker_position_quantity=0
        ),
        existing_exit=None,
    )
    assert any("filled nothing" in r for r in refusals), refusals


def test_an_expired_entry_that_left_shares_is_eligible_at_the_domain_level() -> None:
    snapshot = a_snapshot(
        entry_state="EXPIRED", entry_filled_quantity=Decimal(4), broker_position_quantity=4
    )
    assert exit_eligibility(snapshot, existing_exit=None) == ()
    assert snapshot.attributable_quantity == 4


# ---------------------------------------------------------------------------
# Gap 2: the partial entry's remainder is cancelled, then the exit is attributable
# ---------------------------------------------------------------------------


def test_a_stop_condition_cancels_the_remainder_at_once_and_sells_exactly_the_filled_quantity(
    world: World,
) -> None:
    intent = _partial_entry(world)
    plans, _ = _plan_for(world, intent, stop="430", bid="418.10")
    manager = _guarded_manager(world, plans)
    outcomes = manager.evaluate_once(now=world.clock.utc)
    # Cancel -> broker confirms canceled -> the SAME tick proceeds to claim and send the stop.
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED, outcomes
    entry = _entry(world, intent)
    assert entry.state is PaperExecutionState.CANCELED and entry.filled_quantity == Decimal(2)
    assert len(_buys(world)) == 1, "the entry is never resent"
    (sell,) = _sells(world)
    assert sell.quantity == "2" and sell.side == "sell"
    assert len(_entry_events(world, intent, "CANCEL_REQUESTED")) == 1


def test_the_mandatory_deadline_cancels_the_remainder_and_liquidates(world: World) -> None:
    intent = _partial_entry(world)
    plans, plan = _plan_for(world, intent, stop="1", bid="418.10", deadline_in=135)
    manager = _guarded_manager(world, plans)
    # Before the deadline (and inside the proactive window): nothing is cancelled.
    assert manager.evaluate_once(now=world.clock.utc)[0].kind is PlanOutcomeKind.NOT_ELIGIBLE
    assert _entry(world, intent).state is PaperExecutionState.PARTIALLY_FILLED
    world.clock.advance(20)  # past plan.mandatory_exit_deadline (135 - 120 = 15s)
    assert world.clock.utc >= plan.mandatory_exit_deadline
    outcomes = manager.evaluate_once(now=world.clock.utc)
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    claimed = plans.get(plan.plan_id)
    assert claimed is not None and claimed.triggered_exit_kind is ExitTriggerKind.MANDATORY_EXIT
    assert _entry(world, intent).state is PaperExecutionState.CANCELED
    (sell,) = _sells(world)
    assert sell.quantity == "2"


def test_a_partial_entry_with_no_trigger_is_cancelled_proactively_after_the_bound(
    world: World,
) -> None:
    intent = _partial_entry(world)
    plans, plan = _plan_for(world, intent, stop="1", bid="418.10")
    manager = _guarded_manager(world, plans)
    assert manager.evaluate_once(now=world.clock.utc)[0].kind is PlanOutcomeKind.NOT_ELIGIBLE
    world.clock.advance(ENTRY_PARTIAL_PROACTIVE_CANCEL_SECONDS - 30)
    assert manager.evaluate_once(now=world.clock.utc)[0].kind is PlanOutcomeKind.NOT_ELIGIBLE
    assert _entry_events(world, intent, "CANCEL_REQUESTED") == []
    world.clock.advance(60)
    outcomes = manager.evaluate_once(now=world.clock.utc)
    assert outcomes[0].kind is PlanOutcomeKind.MONITORING, outcomes  # entry final, protected
    assert _entry(world, intent).state is PaperExecutionState.CANCELED
    assert _sells(world) == [] and len(_buys(world)) == 1
    # From now on the stop is live on the filled quantity.
    _stage_msft(world, "400.00")
    stopped = replace(plan, stop_price=Decimal("410"))
    plans.rows[stopped.plan_id] = stopped
    assert manager.evaluate_once(now=world.clock.utc)[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    assert [s.quantity for s in _sells(world)] == ["2"]


def test_the_proactive_clock_survives_a_restart(world: World) -> None:
    intent = _partial_entry(world)
    plans, _ = _plan_for(world, intent, stop="1", bid="418.10")
    _guarded_manager(world, plans).evaluate_once(now=world.clock.utc)
    world.clock.advance(ENTRY_PARTIAL_PROACTIVE_CANCEL_SECONDS + 5)
    fresh = _guarded_manager(world, plans)  # a brand new process: nothing remembered in RAM
    assert fresh.evaluate_once(now=world.clock.utc)[0].kind is PlanOutcomeKind.MONITORING
    assert _entry(world, intent).state is PaperExecutionState.CANCELED


def test_no_cancel_is_attempted_while_the_market_is_closed(world: World) -> None:
    intent = _partial_entry(world)
    plans, _ = _plan_for(world, intent, stop="430", bid="418.10")
    manager = _guarded_manager(world, plans)
    world.store.set_market_open(False)
    outcomes = manager.evaluate_once(now=world.clock.utc)
    assert outcomes[0].kind is PlanOutcomeKind.NOT_ELIGIBLE
    assert "no cancel attempted" in outcomes[0].detail
    assert _entry_events(world, intent, "CANCEL_REQUESTED") == []
    assert _entry(world, intent).state is PaperExecutionState.PARTIALLY_FILLED
    world.store.set_market_open(True)
    assert manager.evaluate_once(now=world.clock.utc)[0].kind is PlanOutcomeKind.EXIT_CLAIMED


def test_an_entry_with_zero_fills_is_never_cancelled(world: World) -> None:
    intent = _approve_and_settle(world, "NVDA")
    assert _entry(world, intent).state is PaperExecutionState.PAPER_ACCEPTED
    plan = replace(_plan(world, intent, stop=Decimal("500"), target=Decimal("900")), symbol="NVDA")
    plans = FakeApprovedPlans()
    plans.save(plan)
    broker = _CancelBroker(world.broker)
    manager = _guarded_manager(world, plans, broker)
    for _ in range(6):
        world.clock.advance(60)
        outcomes = manager.evaluate_once(now=world.clock.utc)
        assert outcomes[0].kind is PlanOutcomeKind.NOT_ELIGIBLE
    assert broker.cancel_calls == 0
    assert _entry(world, intent).state is PaperExecutionState.PAPER_ACCEPTED


def test_the_kill_switch_does_not_block_the_protective_cancel(world: World) -> None:
    intent = _partial_entry(world)
    plans, _ = _plan_for(world, intent, stop="430", bid="418.10")
    world.kill_switch.engaged = True
    outcomes = _guarded_manager(world, plans).evaluate_once(now=world.clock.utc)
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    assert _entry(world, intent).state is PaperExecutionState.CANCELED


def test_a_fill_that_races_the_cancel_proceeds_normally_on_the_whole_quantity(
    world: World,
) -> None:
    intent = _partial_entry(world)
    plans, _ = _plan_for(world, intent, stop="430", bid="418.10")
    broker = _CancelBroker(world.broker, mode="fill_race")
    outcomes = _guarded_manager(world, plans, broker).evaluate_once(now=world.clock.utc)
    assert broker.cancel_calls == 1
    assert _entry(world, intent).state is PaperExecutionState.FILLED
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    (sell,) = _sells(world)
    assert sell.quantity == "4"


def test_an_ambiguous_cancel_is_reconciled_by_client_order_id_and_never_duplicated(
    world: World,
) -> None:
    intent = _partial_entry(world)
    plans, _ = _plan_for(world, intent, stop="430", bid="418.10")
    broker = _CancelBroker(world.broker, mode="lost_ack", failures=1)
    outcomes = _guarded_manager(world, plans, broker).evaluate_once(now=world.clock.utc)
    # The DELETE reached the broker but its answer was lost: reconcile finds CANCELED.
    assert broker.cancel_calls == 1
    assert _entry(world, intent).state is PaperExecutionState.CANCELED
    assert outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED
    assert len(_buys(world)) == 1
    assert len(_entry_events(world, intent, "ENTRY_REMAINDER_CANCEL_ERROR")) == 1


def test_the_cancel_budget_is_bounded_and_exhaustion_is_loud_and_durable(world: World) -> None:
    intent = _partial_entry(world)
    plans, _ = _plan_for(world, intent, stop="430", bid="418.10")
    broker = _CancelBroker(world.broker, mode="never_arrives", failures=1000)
    manager = _guarded_manager(world, plans, broker)
    for sent in range(1, ENTRY_MAX_CANCEL_REQUESTS + 1):
        outcomes = manager.evaluate_once(now=world.clock.utc)
        assert outcomes[0].kind is PlanOutcomeKind.NEEDS_ATTENTION
        assert broker.cancel_calls == sent
        if sent < ENTRY_MAX_CANCEL_REQUESTS:
            # Inside the spacing window no second cancel is sent.
            again = manager.evaluate_once(now=world.clock.utc)
            assert again[0].kind is PlanOutcomeKind.NOT_ELIGIBLE
            assert "cancel pending" in again[0].detail
            assert broker.cancel_calls == sent
        world.clock.advance(ENTRY_CANCEL_MIN_SPACING_SECONDS)
    assert broker.cancel_calls == ENTRY_MAX_CANCEL_REQUESTS
    last = manager.evaluate_once(now=world.clock.utc)[0]
    assert last.kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert ENTRY_REMAINDER_EXHAUSTED_EVENT_TYPE in last.detail
    assert broker.cancel_calls == ENTRY_MAX_CANCEL_REQUESTS, "no sixth cancel"
    assert len(_entry_events(world, intent, ENTRY_REMAINDER_EXHAUSTED_EVENT_TYPE)) == 1
    manager.evaluate_once(now=world.clock.utc)
    assert len(_entry_events(world, intent, ENTRY_REMAINDER_EXHAUSTED_EVENT_TYPE)) == 1
    assert _sells(world) == [] and len(_buys(world)) == 1


# ---------------------------------------------------------------------------
# Gap 3: one plan's exception never aborts the tick
# ---------------------------------------------------------------------------


class _FailsFor:
    def __init__(self, inner: object, intent: str, error: BaseException) -> None:
        self._inner = inner
        self._intent = intent
        self._error = error

    def handle(self, intent: str, **kwargs: object) -> object:
        if intent == self._intent:
            raise self._error
        return self._inner.handle(intent, **kwargs)  # type: ignore[attr-defined]


def _two_open_positions(world: World) -> tuple[str, FakeApprovedPlans]:
    world.load_day(("AAPL", "META"))
    filled = default_scenario_table()["AAPL"]
    quotes = {"AAPL": ("227.40", "227.50"), "META": ("512.40", "512.70")}
    exits = SimulationExitScenario.EXIT_FILLED
    world.store.stage(
        scenarios={"AAPL": filled, "META": filled},
        quotes=quotes,
        exit_scenarios={"AAPL": exits, "META": exits},
    )
    for symbol in ("AAPL", "META"):
        proposal = world.proposal_id(symbol)
        view = world.service.prepare_approval(proposal)
        assert world.service.confirm_approval(proposal, view.ticket).sent == "sent"
    for _ in range(2):
        world.clock.advance(5)
        world.service.refresh_executions()
    first, second = _intent(world, "AAPL"), _intent(world, "META")
    assert _entry(world, second).state is PaperExecutionState.FILLED
    plans = FakeApprovedPlans()
    plans.save(_plan(world, first, plan_id="PLAN-A", stop=Decimal("500"), target=Decimal("900")))
    plans.save(
        replace(
            _plan(world, second, plan_id="PLAN-B", stop=Decimal("700"), target=Decimal("900")),
            symbol="META",
        )
    )
    return first, plans


def _error_events(world: World, intent: str) -> list[object]:
    return [
        e
        for e in world.exits.events.for_entry(intent)
        if e.event_type == PLAN_EVALUATION_ERROR_EVENT_TYPE
    ]


def test_one_plans_exception_does_not_starve_the_next_plan(world: World) -> None:
    first, plans = _two_open_positions(world)
    manager = _manager(world, plans)
    manager._assess = _FailsFor(  # type: ignore[assignment]
        manager._assess, first, RuntimeError("duplicate key value violates unique constraint")
    )
    outcomes = manager.evaluate_once(now=world.clock.utc)
    by_plan = {o.plan_id: o for o in outcomes if o.plan_id == "PLAN-A"}
    assert by_plan["PLAN-A"].kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert PLAN_EVALUATION_ERROR_EVENT_TYPE in by_plan["PLAN-A"].detail
    assert "RuntimeError" in by_plan["PLAN-A"].detail
    # On the claim tick the claimed plan is also resumed in the same pass.
    assert PlanOutcomeKind.EXIT_CLAIMED in {o.kind for o in outcomes if o.plan_id == "PLAN-B"}
    assert [s.symbol for s in _sells(world)] == ["META"]
    assert len(_error_events(world, first)) == 1
    # Re-ticking in the same hour does not pile up duplicate error rows.
    manager.evaluate_once(now=world.clock.utc)
    assert len(_error_events(world, first)) == 1


def test_system_exit_and_keyboard_interrupt_are_never_swallowed(world: World) -> None:
    first, plans = _two_open_positions(world)
    for error in (KeyboardInterrupt(), SystemExit(1)):
        manager = _manager(world, plans)
        manager._assess = _FailsFor(manager._assess, first, error)  # type: ignore[assignment]
        with pytest.raises(type(error)):
            manager.evaluate_once(now=world.clock.utc)


# ---------------------------------------------------------------------------
# `suspended` is not terminal
# ---------------------------------------------------------------------------


class _SuspendedView:
    def __init__(self, inner: object) -> None:
        self._inner = inner

    @property
    def status(self) -> str:
        return "suspended"

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)


class _SuspendedReports:
    """Reports every order found by client_order_id as Alpaca's non-terminal `suspended`."""

    def __init__(self, inner: object) -> None:
        self._inner = inner

    def __getattr__(self, name: str) -> object:
        return getattr(self._inner, name)

    def fetch_order_by_client_order_id(self, client_order_id: str) -> tuple[int, object, str]:
        status, view, payload = self._inner.fetch_order_by_client_order_id(client_order_id)  # type: ignore[attr-defined]
        return status, (None if view is None else _SuspendedView(view)), payload


def test_a_suspended_entry_never_becomes_rejected_and_still_blocks_a_new_entry(
    world: World,
) -> None:
    world.load_day(("NVDA",))
    proposal = world.proposal_id("NVDA")
    view = world.service.prepare_approval(proposal)
    assert world.service.confirm_approval(proposal, view.ticket).sent == "sent"
    intent = _intent(world, "NVDA")
    handler = ReconcilePaperOrderHandler(
        attempts=world.repositories.attempts,
        acknowledgements=world.repositories.acknowledgements,
        events=world.repositories.events,
        broker=_SuspendedReports(world.broker),  # type: ignore[arg-type]
        authorizations=world.repositories.authorizations,
        previews=world.repositories.previews,
        rounds=world.repositories.rounds,
        time_source=world.clock,
    )
    attempt = _entry(world, intent)
    for _ in range(3):
        world.clock.advance(5)
        attempt = handler.handle(ReconcilePaperOrderCommand(intent, at=world.clock.utc))
    assert attempt.broker_status == "suspended"
    assert attempt.state is not PaperExecutionState.REJECTED and not attempt.is_terminal
    assert any(
        e.event_type == "UNMAPPED_BROKER_STATUS"
        for e in world.repositories.events.for_intent(intent)
    )
    # The D1 ledger still counts it as a sent, non-rejected order: it is not freed.
    day_start, day_end = trading_day_bounds(world.clock.utc)
    (row,) = world.repositories.attempts.entry_ledger(day_start=day_start, day_end=day_end)
    assert row.state != "REJECTED" and ledger_counts_order(row)
    # And the exit pipeline refuses to treat it as a position-less, never-sent entry.
    assert any(
        "entry order is PAPER" in r
        for r in world.service.exits.assess(intent).refusals  # type: ignore[union-attr]
    )
