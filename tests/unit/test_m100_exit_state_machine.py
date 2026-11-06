"""M100 D3 -- the bounded, auditable, fail-closed exit state machine.

Everything runs over the REAL simulation broker and the REAL M087/M089 exit handlers with a
deterministic clock. No test sleeps; time only moves when the test advances it. The scenarios the
Owner listed are each proven here: unfilled exits, partial fills, pending cancellations,
cancel/fill races, duplicate-exit prevention, broker outages, market close, restart
reconciliation, unexpected broker responses and position quantity changes.

The invariant checked after EVERY tick by ``_tick``: at most one live (non-terminal) SELL exists
at the broker, and the total quantity of live-plus-filled sells never exceeds the entry quantity.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import NoReturn

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans, FakeExternalPositionClosures
from tests.unit.test_v1_position_plan_manager import _open_position, _plan

from empirical_platform.decision_candidate.position_exit import PositionExitState
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulatedOrder,
    SimulationExitScenario,
    default_exit_scenario_table,
    default_scenario_table,
)
from empirical_platform.usecases.position_plan_manager import (
    EXIT_CANCEL_CONFIRMATION_SECONDS,
    EXIT_MAXIMUM_ATTEMPTS,
    EXIT_UNPROTECTED_ESCALATION_SECONDS,
    EXIT_WORKING_REST_SECONDS,
    PlanEvaluationOutcome,
    PlanOutcomeKind,
    PositionPlanManager,
)

_LIVE = {"new", "accepted", "partially_filled", "pending_cancel", "pending_new"}


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


def _stage(world: World, scenario: SimulationExitScenario, *, bid: str = "229.00") -> None:
    """Fix the exit behaviour and a bid that is through the stop."""
    entries = default_scenario_table()
    exits = default_exit_scenario_table()
    exits["AAPL"] = scenario
    world.store.stage(
        scenarios={"AAPL": entries["AAPL"]},
        quotes={"AAPL": (bid, f"{float(bid) + 0.10:.2f}")},
        exit_scenarios={"AAPL": exits["AAPL"]},
    )


def _manager(world: World, plans: FakeApprovedPlans) -> PositionPlanManager:
    return PositionPlanManager(
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
        market_data=world.market_data,
        configurations=world.repositories.configurations,
        environment="SIMULATION",
        time_source=world.clock,
        entry_kill_switch=world.kill_switch,
    )


class Scene:
    """One open AAPL position with a STOP plan that has been breached."""

    def __init__(self, world: World, scenario: SimulationExitScenario) -> None:
        self.world = world
        self.intent = _open_position(world)
        self.entry_quantity = int(
            world.store.position("AAPL")
        )  # whole shares the broker holds before any exit
        self.plans = FakeApprovedPlans()
        self.plan = self.plans.save(_plan(world, self.intent, stop=_stop(), target=_target()))
        self.manager = _manager(world, self.plans)
        _stage(world, scenario)

    # -- driving -------------------------------------------------------------------------
    def tick(self, seconds: float = 0) -> PlanEvaluationOutcome:
        """Advance the clock, run one tick, check the safety invariant, return the outcome."""
        if seconds:
            self.world.clock.advance(seconds)
        outcomes = self.manager.evaluate_once(now=self.world.clock.utc)
        self.assert_no_overlap_or_oversell()
        assert len(outcomes) <= 2  # a plan claimed this tick is also resumed this tick
        if not outcomes:  # a closed position is no longer an unresolved plan
            return PlanEvaluationOutcome(
                self.plan.plan_id, self.intent, PlanOutcomeKind.MONITORING, "none"
            )
        return outcomes[0] if outcomes[0].kind is PlanOutcomeKind.EXIT_CLAIMED else outcomes[-1]

    def sells(self) -> list[SimulatedOrder]:
        return [o for o in self.world.store.orders() if o.side == "sell"]

    def live_sells(self) -> list[SimulatedOrder]:
        return [o for o in self.sells() if o.status in _LIVE]

    def attempts(self) -> tuple:
        return self.world.exits.attempts.for_entry(self.intent)

    def risk_events(self) -> list:
        return [
            e
            for e in self.world.exits.events.for_entry(self.intent)
            if e.event_type == "EXIT_UNRESOLVED_RISK"
        ]

    def assert_no_overlap_or_oversell(self) -> None:
        live = self.live_sells()
        assert len(live) <= 1, f"overlapping live exits: {[o.client_order_id for o in live]}"
        # Shares already sold plus the unfilled remainder of the one live order must fit inside
        # what the position held when the first exit was sent.
        filled = sum(int(float(o.filled_quantity)) for o in self.sells())
        remainder = sum(int(o.quantity) - int(float(o.filled_quantity)) for o in live)
        assert filled + remainder <= self.entry_quantity, "exits would oversell the position"


def _stop() -> Decimal:
    return Decimal("230")


def _target() -> Decimal:
    return Decimal("260")


# ---------------------------------------------------------------------------------------------
# Unfilled exits: cancel (requested, then CONFIRMED), then re-arm -- never overlapping
# ---------------------------------------------------------------------------------------------


def test_an_unfilled_exit_is_cancelled_confirmed_and_only_then_rearmed(world: World) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    assert scene.tick().kind is PlanOutcomeKind.EXIT_CLAIMED
    (first,) = scene.attempts()

    # It rests, correctly untouched, until the rest period has elapsed.
    assert scene.tick(EXIT_WORKING_REST_SECONDS - 10).kind is PlanOutcomeKind.EXIT_RECONCILED
    assert len(scene.sells()) == 1

    # Now a cancel is REQUESTED. Requesting is not cancelling: no replacement exists yet.
    assert scene.tick(20).kind is PlanOutcomeKind.EXIT_CANCEL_REQUESTED
    assert scene.attempts()[0].state is PositionExitState.CANCEL_REQUESTED
    assert len(scene.sells()) == 1

    # The broker confirms the cancel on reconciliation; the attempt only now becomes CANCELED.
    scene.tick(1)
    assert scene.attempts()[0].state is PositionExitState.CANCELED
    assert len(scene.sells()) == 1

    # With a CONFIRMED cancel and the position intact, the next tick re-arms exactly once.
    assert scene.tick(1).kind is PlanOutcomeKind.EXIT_REARMED
    attempts = scene.attempts()
    assert [a.state for a in attempts][0] is PositionExitState.CANCELED
    assert len(attempts) == 2 and len(scene.sells()) == 2
    assert len({a.client_order_id for a in attempts}) == 2  # a NEW broker identity
    assert attempts[1].quantity == scene.entry_quantity


def test_a_resting_exit_is_never_cancelled_early(world: World) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    for _ in range(5):
        outcome = scene.tick((EXIT_WORKING_REST_SECONDS - 5) / 5)
        assert outcome.kind is PlanOutcomeKind.EXIT_RECONCILED
    assert scene.attempts()[0].state is PositionExitState.ACCEPTED


def test_repeated_ticks_cannot_create_a_second_live_exit(world: World) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    for _ in range(40):
        scene.tick(5)  # the invariant is asserted inside tick()
    assert len(scene.live_sells()) <= 1


def test_attempts_are_bounded_and_the_last_one_escalates_instead_of_retrying(
    world: World,
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    for _ in range(400):
        scene.tick(10)
        if scene.risk_events():
            break
    assert len(scene.attempts()) == EXIT_MAXIMUM_ATTEMPTS
    assert len(scene.sells()) == EXIT_MAXIMUM_ATTEMPTS
    (event,) = scene.risk_events()
    assert "final allowed exit attempt" in event.detail
    assert world.kill_switch.engaged is True  # new ENTRIES are stopped
    # Still exactly one live exit protecting the position, and no further attempts, ever.
    for _ in range(60):
        outcome = scene.tick(10)
        assert outcome.kind is PlanOutcomeKind.EXIT_UNRESOLVED_RISK
    assert len(scene.attempts()) == EXIT_MAXIMUM_ATTEMPTS
    assert len(scene.risk_events()) == 1  # escalation is idempotent, not a flood


# ---------------------------------------------------------------------------------------------
# Partial fills and position quantity changes
# ---------------------------------------------------------------------------------------------


def test_a_partial_fill_is_cancelled_and_the_replacement_sells_only_the_remainder(
    world: World,
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_PARTIAL_FILL)
    scene.tick()
    scene.tick(1)  # the broker reports the partial fill
    first = scene.attempts()[0]
    assert first.state is PositionExitState.PARTIALLY_FILLED
    sold = int(first.filled_quantity or 0)
    assert 0 < sold < scene.entry_quantity

    scene.tick(EXIT_WORKING_REST_SECONDS)  # rested -> cancel requested
    scene.tick(1)  # cancel confirmed -> CANCELED with the part-fill kept
    assert scene.attempts()[0].state is PositionExitState.CANCELED
    assert int(scene.attempts()[0].filled_quantity or 0) == sold

    _stage(world, SimulationExitScenario.EXIT_FILLED)
    assert scene.tick(1).kind is PlanOutcomeKind.EXIT_REARMED
    second = scene.attempts()[1]
    assert second.quantity == scene.entry_quantity - sold  # the remainder, never the whole
    scene.tick(1)
    scene.tick(1)
    assert world.store.position("AAPL") == 0
    assert scene.attempts()[-1].position_closed


def test_a_position_resized_outside_the_platform_stops_the_exit_and_escalates(
    world: World,
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    scene.tick(EXIT_WORKING_REST_SECONDS + 1)  # cancel requested
    scene.tick(1)  # cancel confirmed
    world.store.reduce_position("AAPL", 3)  # someone sold 3 shares at the broker directly
    outcome = scene.tick(1)
    assert outcome.kind is PlanOutcomeKind.EXIT_UNRESOLVED_RISK
    assert "cannot be safely re-exited" in outcome.detail
    assert len(scene.sells()) == 1  # nothing further was sent: it could have oversold
    assert world.kill_switch.engaged is True


# ---------------------------------------------------------------------------------------------
# Cancel races, pending cancellations and uncertainty
# ---------------------------------------------------------------------------------------------


def test_a_cancel_that_loses_to_a_fill_ends_filled_and_never_rearms(world: World) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_CANCEL_FILL_RACE)
    scene.tick()
    scene.tick(EXIT_WORKING_REST_SECONDS + 1)  # cancel requested; the venue fills it instead
    scene.tick(1)
    attempts = scene.attempts()
    assert len(attempts) == 1 and attempts[0].state is PositionExitState.FILLED
    scene.tick(1)
    assert len(scene.sells()) == 1
    assert world.store.position("AAPL") == 0
    assert not scene.risk_events()


def test_a_cancel_the_broker_never_confirms_is_escalated_and_nothing_is_replaced(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    scene.tick(EXIT_WORKING_REST_SECONDS + 1)  # cancel requested
    real = world.broker.fetch_order_by_client_order_id

    def _stuck(client_order_id: str) -> tuple[int, object, str]:
        status, view, body = real(client_order_id)
        if view is not None:
            stuck = world.store.order(client_order_id)
            assert stuck is not None
            world.store.put(replace(stuck, status="pending_cancel", cancel_requested=False))
            view = world.store.order(client_order_id).view()  # type: ignore[union-attr]
        return status, view, body

    monkeypatch.setattr(world.broker, "fetch_order_by_client_order_id", _stuck)
    for _ in range(EXIT_CANCEL_CONFIRMATION_SECONDS // 10 + 3):
        outcome = scene.tick(10)
    assert outcome.kind is PlanOutcomeKind.EXIT_UNRESOLVED_RISK
    assert "has not confirmed the cancel" in outcome.detail
    assert len(scene.sells()) == 1  # never assume it was cancelled: no replacement exists
    assert world.kill_switch.engaged is True


def test_an_unknown_submission_is_only_reconciled_never_replaced(world: World) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_AMBIGUOUS_AFTER_POSSIBLE_SEND)
    scene.tick()
    for _ in range(30):
        scene.tick(30)
    assert len(scene.attempts()) == 1  # no second exit while the first one's fate is uncertain
    assert len(scene.sells()) == 1


def test_an_unrecognised_broker_status_is_never_acted_on(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    real = world.broker.fetch_order_by_client_order_id

    def _odd(client_order_id: str) -> tuple[int, object, str]:
        status, view, body = real(client_order_id)
        order = world.store.order(client_order_id)
        if order is not None:
            world.store.put(replace(order, status="wibble"))
            view = world.store.order(client_order_id).view()  # type: ignore[union-attr]
        return status, view, body

    monkeypatch.setattr(world.broker, "fetch_order_by_client_order_id", _odd)
    scene.tick(1)
    outcome = scene.tick(EXIT_WORKING_REST_SECONDS + 1)
    assert outcome.kind is PlanOutcomeKind.EXIT_UNRESOLVED_RISK
    assert "does not recognise" in outcome.detail
    assert len(scene.sells()) == 1  # not cancelled, not replaced
    assert [a.state for a in scene.attempts()] != [PositionExitState.CANCELED]


# ---------------------------------------------------------------------------------------------
# Outages, market close and restarts
# ---------------------------------------------------------------------------------------------


def test_a_broker_outage_takes_no_exit_action_and_recovers_afterwards(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    real = world.broker.fetch_order_by_client_order_id

    def _down(client_order_id: str) -> NoReturn:
        raise ConnectionError("broker unreachable")

    monkeypatch.setattr(world.broker, "fetch_order_by_client_order_id", _down)
    outcome = scene.tick(EXIT_WORKING_REST_SECONDS + 30)  # long past the rest period
    assert outcome.kind is PlanOutcomeKind.NEEDS_ATTENTION
    assert "ConnectionError" in outcome.detail
    assert scene.attempts()[0].state is PositionExitState.ACCEPTED  # no cancel on a guess
    assert len(scene.sells()) == 1

    monkeypatch.setattr(world.broker, "fetch_order_by_client_order_id", real)
    assert scene.tick(1).kind is PlanOutcomeKind.EXIT_CANCEL_REQUESTED  # normal service resumes


def test_an_expired_exit_with_the_market_closed_waits_then_escalates(world: World) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    (order,) = scene.sells()
    world.store.put(replace(order, status="expired"))  # DAY order lapsed at the close
    world.store.set_market_open(False)
    scene.tick(1)  # reconcile records EXPIRED
    assert scene.attempts()[0].state is PositionExitState.EXPIRED
    waiting = scene.tick(1)
    assert waiting.kind is PlanOutcomeKind.EXIT_WAITING_FOR_MARKET
    assert not world.kill_switch.engaged

    outcome = scene.tick(EXIT_UNPROTECTED_ESCALATION_SECONDS + 1)
    assert outcome.kind is PlanOutcomeKind.EXIT_UNRESOLVED_RISK
    assert world.kill_switch.engaged is True
    assert len(scene.sells()) == 1  # nothing was sent into a closed market


def test_a_repricing_cancel_is_not_attempted_close_to_the_close(world: World) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    # The simulated clock reports the close 4h away; make it 60s away instead.
    from empirical_platform.shared.brokerage import simulation_paper

    real_clock = world.broker.fetch_clock

    def _closing() -> simulation_paper.SimulatedClockView:
        view = real_clock()
        return simulation_paper.SimulatedClockView(
            is_open=True,
            timestamp=view.timestamp,
            next_open=None,
            next_close=view.timestamp.replace(microsecond=0) + timedelta(seconds=60),
        )

    world.broker.fetch_clock = _closing  # type: ignore[method-assign]
    outcome = scene.tick(EXIT_WORKING_REST_SECONDS + 5)
    assert outcome.kind is PlanOutcomeKind.EXIT_RECONCILED
    assert "not repriced" in outcome.detail
    assert scene.attempts()[0].state is PositionExitState.ACCEPTED  # the resting order stays


def test_a_restart_mid_cancel_resumes_from_durable_state_without_a_second_exit(
    world: World,
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    scene.tick(EXIT_WORKING_REST_SECONDS + 1)  # cancel requested
    assert scene.attempts()[0].state is PositionExitState.CANCEL_REQUESTED

    scene.manager = _manager(world, scene.plans)  # a brand-new process: only durable state remains
    scene.tick(1)  # reconciles the cancel
    assert scene.attempts()[0].state is PositionExitState.CANCELED
    assert scene.tick(1).kind is PlanOutcomeKind.EXIT_REARMED
    assert len(scene.attempts()) == 2

    scene.manager = _manager(world, scene.plans)  # and again
    for _ in range(5):
        scene.tick(5)
    assert len(scene.attempts()) == 2 and len(scene.live_sells()) == 1


def test_exits_are_never_blocked_by_an_engaged_entry_kill_switch_or_a_breached_entry_limit(
    world: World,
) -> None:
    """Risk-reducing exits do not pass through the entry gate or the entry kill switch."""
    scene = Scene(world, SimulationExitScenario.EXIT_FILLED)
    world.kill_switch.engaged = True  # entries are stopped...
    world.store.stage_day_pnl(realized="-5000", whole_day="-5000")  # ...and the daily loss is blown
    assert scene.tick().kind is PlanOutcomeKind.EXIT_CLAIMED
    scene.tick(1)
    scene.tick(1)
    assert world.store.position("AAPL") == 0
    assert scene.attempts()[-1].position_closed


def test_a_filled_exit_is_closed_once_and_never_rearmed(world: World) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_FILLED)
    scene.tick()
    for _ in range(6):
        scene.tick(30)
    assert len(scene.attempts()) == 1 and scene.attempts()[0].position_closed
    assert len(scene.sells()) == 1
    assert not scene.risk_events()


# ---------------------------------------------------------------------------------------------
# Review findings: a transient failure must not latch a re-arm; a refused cancel must escalate
# ---------------------------------------------------------------------------------------------


def test_a_transient_failure_after_the_rearm_preview_does_not_wedge_that_generation(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    scene.tick(EXIT_WORKING_REST_SECONDS + 1)  # cancel requested
    scene.tick(1)  # cancel confirmed
    real_handler = scene.manager._submit_handler
    calls = {"n": 0}

    class _Flaky:
        def handle(self, command: object) -> object:
            calls["n"] += 1
            if calls["n"] == 1:
                raise ConnectionError("broker unreachable during the re-arm")
            return real_handler.handle(command)  # type: ignore[arg-type]

    monkeypatch.setattr(scene.manager, "_submit_handler", _Flaky())
    assert scene.tick(1).kind is PlanOutcomeKind.NEEDS_ATTENTION  # prepared, then it failed
    assert len(scene.attempts()) == 1
    # Much later the prepared pair is stale; a fresh identity is minted and the re-arm succeeds.
    outcome = scene.tick(400)
    assert outcome.kind is PlanOutcomeKind.EXIT_REARMED
    assert len(scene.attempts()) == 2 and len(scene.live_sells()) == 1


def test_a_cancel_the_broker_keeps_refusing_is_escalated_not_silently_retried_forever(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    monkeypatch.setattr(world.broker, "cancel_order", lambda _id: (403, "{}"))
    seen = set()
    for _ in range(40):
        outcome = scene.tick(10)
        seen.add(outcome.kind)
    assert PlanOutcomeKind.EXIT_UNRESOLVED_RISK in seen
    assert world.kill_switch.engaged is True
    assert len(scene.sells()) == 1  # the order was never replaced
    (event,) = scene.risk_events()
    assert "has not accepted a cancel" in event.detail


def test_an_owner_who_releases_the_kill_switch_is_not_overridden_every_tick(
    world: World,
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    for _ in range(300):
        scene.tick(10)
        if world.kill_switch.engaged:
            break
    assert world.kill_switch.engaged
    world.kill_switch.engaged = False  # the Owner releases it
    for _ in range(5):
        scene.tick(10)
    assert world.kill_switch.engaged is False


def test_the_nth_attempt_ending_terminal_and_unfilled_escalates_and_never_sends_another(
    world: World,
) -> None:
    scene = Scene(world, SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED)
    scene.tick()
    for _ in range(400):
        if len(scene.sells()) == EXIT_MAXIMUM_ATTEMPTS:
            break
        scene.tick(10)
    assert len(scene.sells()) == EXIT_MAXIMUM_ATTEMPTS
    last = scene.live_sells()[0]
    world.store.put(replace(last, status="expired"))  # the final attempt ends unfilled
    for _ in range(20):
        outcome = scene.tick(10)
    assert outcome.kind is PlanOutcomeKind.EXIT_UNRESOLVED_RISK
    assert len(scene.sells()) == EXIT_MAXIMUM_ATTEMPTS  # a further exit was NOT sent
    assert any("exit attempts were spent" in e.detail for e in scene.risk_events())
