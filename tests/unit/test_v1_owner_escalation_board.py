"""AUDIT A / P1-1 -- automatic exit management must never stop making progress silently.

Drives the REAL `PositionPlanManager` over the simulation world, ticks it through the real
`PlanManagerThread._tick_once` (so the `AttentionBoard` is fed exactly as in production), and
renders the REAL `/active` and `/safety` routes (`build_paper_application`) from the real
`OperatorConsoleService.active_trades()`.

Each escalation source (retries exhausted, cancel budget, unresolved send, market closed /
clock unreadable, plan evaluation error, quote-gate block, entry-side remainder / unmapped
status, tick-level exception) must produce the Owner-visible banner; the board must heal
itself; the false "nothing further is sent without your confirmation" sentence must be gone
for automatic exits; and every dynamic string must be escaped.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Never

import pytest
from tests.unit._m086_fakes import World, simulation_world
from tests.unit._v1_fakes import FakeApprovedPlans
from tests.unit.test_m086_operator_console_routes import Client
from tests.unit.test_v1_exit_retry_management import (
    _attempts,
    _FlakyCancelBroker,
    _manager_over,
    _sells,
    _setup,
    _stage,
)
from tests.unit.test_v1_paper_console_app_routes import _backend

from empirical_platform.decision_candidate.approved_plan import ExitTriggerKind
from empirical_platform.decision_candidate.position_exit import EXIT_MAX_ATTEMPTS_PER_SESSION
from empirical_platform.entrypoints import _operator_console_html as html
from empirical_platform.entrypoints._operator_console_web import SecuritySession
from empirical_platform.entrypoints.paper_operator_console_app import build_paper_application
from empirical_platform.shared.brokerage.simulation_paper import (
    SimulationExitScenario,
    default_scenario_table,
)
from empirical_platform.usecases.operator_console_exits import PLAN_MANAGED_ATTEMPT_PREFIXES
from empirical_platform.usecases.position_plan_manager import (
    ATTENTION_QUOTE_GATE_GRACE_SECONDS,
    MANAGER_TICK_ATTENTION_KEY,
    AttentionBoard,
    ManagerThreadHandle,
    PlanEvaluationOutcome,
    PlanManagerThread,
    PlanOutcomeKind,
    PositionPlanManager,
    _attempt_id,
)

HEADLINE = "AUTOMATIC EXIT STOPPED — CLOSE THIS POSITION MANUALLY AT THE BROKER"
FALSE_SENTENCE = "nothing further is sent without your confirmation"


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


class _Rig:
    """The real thread tick + a real exit-capable console backend over the same world."""

    def __init__(
        self, world: World, intent: str, plans: FakeApprovedPlans, manager: PositionPlanManager
    ) -> None:
        self.world = world
        self.intent = intent
        self.handle = ManagerThreadHandle()
        self.board = self.handle.attention
        self.thread = PlanManagerThread(manager, now=lambda: world.clock.utc, attention=self.board)
        backend = replace(
            _backend(),
            service=world.service,
            _plans=plans,
            _exits=world.exits,
            _market_data=world.market_data,
            _manager_thread_handle=self.handle,
        )
        self.client = Client(build_paper_application(backend, security=SecuritySession()))  # type: ignore[arg-type]

    def tick(self, advance: int = 0) -> None:
        if advance:
            self.world.clock.advance(advance)
        assert self.thread._tick_once() is None

    def active(self) -> str:
        reply = self.client.get("/active")
        assert reply.code == 200, reply.body[:500]
        return reply.body

    def safety(self) -> str:
        reply = self.client.get("/safety")
        assert reply.code == 200, reply.body[:500]
        return reply.body


def _rig(
    world: World,
    *,
    bid: str = "229.00",
    scenario: SimulationExitScenario = SimulationExitScenario.EXIT_ACCEPTED_NOT_FILLED,
) -> _Rig:
    intent, plans, manager = _setup(world, bid=bid, scenario=scenario)
    return _Rig(world, intent, plans, manager)


def _exhaust(rig: _Rig) -> None:
    rig.tick()
    for _ in range(40):
        rig.tick(advance=15)


# ---------------------------------------------------------------------------
# Healthy flows never raise a false alarm
# ---------------------------------------------------------------------------


def test_the_board_is_empty_in_a_normal_stop_to_fill_flow(world: World) -> None:
    rig = _rig(world, scenario=SimulationExitScenario.EXIT_FILLED)
    for _ in range(6):
        rig.tick(advance=5)
        assert rig.board.items() == ()
    assert world.store.position("AAPL") == 0
    assert HEADLINE not in rig.active()
    assert "none" in rig.safety().lower()


def test_the_board_is_empty_while_a_working_exit_is_repriced_within_budget(world: World) -> None:
    rig = _rig(world)
    rig.tick()
    for _ in range(3):  # a reprice or two, well inside the attempt budget
        rig.tick(advance=15)
        assert rig.board.items() == ()
    assert HEADLINE not in rig.active()


# ---------------------------------------------------------------------------
# Each escalation source -> a banner (page top AND card) and a /safety entry
# ---------------------------------------------------------------------------


def _assert_banner(rig: _Rig, expected: str) -> None:
    page = rig.active()
    assert page.count(HEADLINE) >= 2, "banner at the top AND on the affected trade card"
    assert "attention-banner" in page and "attention-alert" in page
    assert expected in page
    assert "AAPL" in page
    safety = rig.safety()
    assert "Plans needing attention" in safety and expected in safety


def test_retries_exhausted_with_a_working_order_shows_the_banner(world: World) -> None:
    rig = _rig(world)
    _exhaust(rig)
    assert len(_attempts(world, rig.intent)) == EXIT_MAX_ATTEMPTS_PER_SESSION
    _assert_banner(rig, "EXIT_RETRIES_EXHAUSTED")
    assert "close the position yourself at the broker" in rig.active()


def test_retries_exhausted_with_every_attempt_terminal_shows_the_banner(world: World) -> None:
    rig = _rig(world)
    rig.tick()
    _stage(world, bid="200.00", scenario=SimulationExitScenario.EXIT_REJECTION)
    for _ in range(40):
        rig.tick(advance=15)
    _assert_banner(rig, "EXIT_RETRIES_EXHAUSTED")
    # The positions is held, so the manual-exit review link is offered where eligible.
    assert "/exit/review?intent=" in rig.active()


def test_cancel_budget_spent_shows_the_banner(world: World) -> None:
    intent, plans, _ = _setup(world)
    flaky = _FlakyCancelBroker(world.broker, failures=100, deliver=False)
    rig = _Rig(world, intent, plans, _manager_over(world, plans, flaky))
    rig.tick()
    for _ in range(40):
        rig.tick(advance=31)
    item = rig.board.for_entry(intent)
    assert item is not None and item.kind == "NEEDS_ATTENTION"
    _assert_banner(rig, "cancel requests were not confirmed by the broker")


def test_unresolved_send_longer_than_the_alert_window_shows_the_banner(world: World) -> None:
    rig = _rig(world, scenario=SimulationExitScenario.EXIT_RECONCILIATION_NOT_FOUND)
    # The broker lookup keeps failing, so the ambiguous send can never be resolved.
    world.broker.fetch_order_by_client_order_id = lambda client_order_id: (  # type: ignore[method-assign]
        503,
        None,
        "broker unavailable",
    )
    rig.tick()
    for _ in range(12):
        rig.tick(advance=15)
    assert len(_attempts(world, rig.intent)) == 1, "never re-sent"
    _assert_banner(rig, "unresolved for")


def test_market_closed_while_an_exit_is_triggered_shows_the_banner_and_heals(
    world: World,
) -> None:
    rig = _rig(world)
    world.store.set_market_open(False)
    rig.tick()
    _assert_banner(rig, "not in a regular trading session")
    world.store.set_market_open(True)
    rig.tick(advance=5)
    assert rig.board.items() == ()
    assert HEADLINE not in rig.active()


def test_unreadable_broker_clock_shows_the_banner(world: World) -> None:
    rig = _rig(world)
    original = world.broker.fetch_clock

    def broken() -> Never:
        raise RuntimeError("clock down")

    world.broker.fetch_clock = broken  # type: ignore[method-assign]
    rig.tick()
    _assert_banner(rig, "broker clock could not be read")
    world.broker.fetch_clock = original  # type: ignore[method-assign]
    rig.tick(advance=5)
    assert rig.board.items() == ()


def test_a_plan_evaluation_error_shows_the_banner_and_heals(world: World) -> None:
    rig = _rig(world)
    original = world.market_data.fetch_quote
    world.market_data.fetch_quote = lambda symbol: (_ for _ in ()).throw(  # type: ignore[method-assign]
        RuntimeError("boom")
    )
    rig.tick()
    world.market_data.fetch_quote = original  # type: ignore[method-assign]
    _assert_banner(rig, "PLAN_EVALUATION_ERROR")
    rig.tick(advance=5)
    assert HEADLINE not in rig.active()


def test_a_wide_spread_blocking_a_triggered_stop_shows_the_banner_only_after_the_grace(
    world: World,
) -> None:
    rig = _rig(world, bid="229.00")
    world.store.stage(
        scenarios={"AAPL": default_scenario_table()["AAPL"]},
        quotes={"AAPL": ("229.00", "245.00")},
        exit_scenarios={"AAPL": SimulationExitScenario.EXIT_FILLED},
    )
    rig.tick()
    assert _sells(world) == [], "the quote gate is NOT bypassed"
    assert rig.board.items() == (), "a single blocked tick is routine, not an alarm"
    assert HEADLINE not in rig.active()
    for _ in range(ATTENTION_QUOTE_GATE_GRACE_SECONDS // 15 + 2):
        rig.tick(advance=15)
    assert _sells(world) == [], "still nothing sent"
    item = rig.board.for_entry(rig.intent)
    assert item is not None and item.kind == "QUOTE_GATE_BLOCKED"
    _assert_banner(
        rig,
        "a triggered STOP/TARGET/MANDATORY exit cannot be priced: quote spread/age gate; "
        "position remains open",
    )
    # Recovery: a tight spread lets the exit through and the banner disappears.
    world.store.stage(
        scenarios={"AAPL": default_scenario_table()["AAPL"]},
        quotes={"AAPL": ("229.00", "229.10")},
        exit_scenarios={"AAPL": SimulationExitScenario.EXIT_FILLED},
    )
    rig.tick(advance=5)
    rig.tick(advance=5)
    assert rig.board.items() == ()
    assert HEADLINE not in rig.active()


def test_a_manager_tick_exception_is_shown_and_heals(world: World) -> None:
    intent, plans, manager = _setup(world)
    rig = _Rig(world, intent, plans, manager)
    original = manager.evaluate_once

    def boom(*, now: datetime) -> Never:
        raise RuntimeError("database down")

    rig.thread._manager = type("M", (), {"evaluate_once": staticmethod(boom)})()  # type: ignore[assignment]
    assert rig.thread._tick_once() is not None
    page = rig.active()
    assert "AUTOMATIC EXIT MANAGEMENT FAILED" in page and "database down" in page
    assert rig.board.for_entry(MANAGER_TICK_ATTENTION_KEY) is not None
    rig.thread._manager = type("M", (), {"evaluate_once": staticmethod(original)})()  # type: ignore[assignment]
    rig.tick(advance=5)
    assert rig.board.items() == ()
    assert "AUTOMATIC EXIT MANAGEMENT FAILED" not in rig.active()


def test_entry_side_unmapped_status_and_remainder_exhaustion_reach_the_board() -> None:
    board = AttentionBoard()
    now = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
    board.record_tick(
        (
            PlanEvaluationOutcome(
                "P1", "INT-1", PlanOutcomeKind.NEEDS_ATTENTION, "UNMAPPED_BROKER_STATUS (entry)"
            ),
            PlanEvaluationOutcome(
                "P2",
                "INT-2",
                PlanOutcomeKind.NEEDS_ATTENTION,
                "ENTRY_REMAINDER_CANCEL_EXHAUSTED: 3 cancels not confirmed",
            ),
        ),
        now=now,
    )
    reasons = {i.key: i.reason for i in board.items()}
    assert "UNMAPPED_BROKER_STATUS" in reasons["INT-1"]
    assert "ENTRY_REMAINDER_CANCEL_EXHAUSTED" in reasons["INT-2"]


class _Entry:
    def __init__(self, attempt_id: str, *, terminal: bool) -> None:
        self.attempt_id = attempt_id
        self.is_terminal = terminal


class _Assessment:
    eligible = False

    def __init__(self, entry: _Entry) -> None:
        self.entry_attempt = entry


def test_an_unmapped_entry_status_event_is_escalated_only_while_the_entry_is_non_terminal(
    world: World,
) -> None:
    """The real manager, given read access to the entry event trail, escalates the durable
    `UNMAPPED_BROKER_STATUS` event of a still-non-terminal entry (and only that)."""
    from empirical_platform.decision_candidate.paper_execution import PaperExecutionEvent

    intent, plans, _ = _setup(world)
    entry = world.repositories.attempts.for_intent(intent)
    world.repositories.events.append(
        PaperExecutionEvent(
            event_id="EVT-UNMAPPED-test",
            intent_governance_id=intent,
            attempt_id=entry.attempt_id,
            event_type="UNMAPPED_BROKER_STATUS",
            occurred_at=world.clock.utc,
            detail="the broker reports status 'suspended'",
        )
    )
    probe = _manager_over(world, plans, world.broker)
    plan = plans.for_entry(intent)
    assert (
        probe._unmapped_entry_status(plan, _Assessment(_Entry(entry.attempt_id, terminal=False)))
        is None
    ), "without read access to the entry trail nothing is read"
    probe._entry_events = world.repositories.events
    assert (
        probe._unmapped_entry_status(plan, _Assessment(_Entry(entry.attempt_id, terminal=True)))
        is None
    )
    detail = probe._unmapped_entry_status(
        plan, _Assessment(_Entry(entry.attempt_id, terminal=False))
    )
    assert detail is not None and "UNMAPPED_BROKER_STATUS" in detail and "suspended" in detail


# ---------------------------------------------------------------------------
# Wording, escaping, self-healing
# ---------------------------------------------------------------------------


def test_the_false_confirmation_sentence_is_gone_for_automatic_exits(world: World) -> None:
    rig = _rig(world)
    rig.tick()
    assert _sells(world), "an automatic exit is working at the broker"
    attempt = _attempts(world, rig.intent)[0]
    assert attempt.attempt_id.startswith(PLAN_MANAGED_ATTEMPT_PREFIXES)
    page = rig.active()
    assert "Exit in progress" in page
    assert FALSE_SENTENCE not in page
    assert "sends and reprices this exit on its own within bounded limits" in page
    assert "you may still close the position manually" in page


def test_the_manual_confirmation_wording_remains_for_a_manual_exit(world: World) -> None:
    from empirical_platform.usecases import operator_console

    source = Path(operator_console.__file__).read_text(encoding="utf-8")
    assert FALSE_SENTENCE in source, "kept, but only on the Owner-confirmed manual-exit branch"


def test_plan_managed_prefixes_match_what_the_manager_mints(world: World) -> None:
    intent, plans, _ = _setup(world)
    plan = plans.for_entry(intent)
    kind = ExitTriggerKind.STOP
    for slot in (0, 1, 7):
        assert _attempt_id(plan, kind, slot).startswith(PLAN_MANAGED_ATTEMPT_PREFIXES)
    assert not f"XAT-{intent}-1".startswith(PLAN_MANAGED_ATTEMPT_PREFIXES)


def test_every_dynamic_string_is_html_escaped() -> None:
    board = AttentionBoard()
    now = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
    board.record_tick(
        (
            PlanEvaluationOutcome(
                "P1", "INT-<b>", PlanOutcomeKind.NEEDS_ATTENTION, "<script>alert(1)</script>"
            ),
        ),
        now=now,
    )
    items = board.items()
    banner = html.attention_banner(
        items, details={"INT-<b>": ("<i>AAPL</i>", "/exit/review?intent=<x>")}
    )
    card = html.attention_card_alert(items[0], review_manual_exit_url="/x?a=<s>")
    section = html.attention_section(items)
    for rendered in (banner, card, section):
        assert "<script>" not in rendered and "<b>" not in rendered
        assert "&lt;script&gt;" in rendered or "entry INT-&lt;b&gt;" in rendered


def test_the_board_heals_when_a_plan_is_no_longer_evaluated() -> None:
    board = AttentionBoard()
    now = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
    board.record_tick(
        (PlanEvaluationOutcome("P1", "INT-1", PlanOutcomeKind.NEEDS_ATTENTION, "stuck"),),
        now=now,
    )
    assert len(board.items()) == 1
    board.record_tick((), now=now + timedelta(seconds=15))
    assert board.items() == ()


def test_the_latest_outcome_wins_within_one_tick_and_first_seen_is_kept() -> None:
    board = AttentionBoard()
    t0 = datetime(2026, 1, 5, 15, 0, tzinfo=UTC)
    stuck = PlanEvaluationOutcome("P1", "INT-1", PlanOutcomeKind.NEEDS_ATTENTION, "stuck")
    board.record_tick((stuck,), now=t0)
    board.record_tick((stuck,), now=t0 + timedelta(seconds=30))
    (item,) = board.items()
    assert item.first_seen_at == t0 and item.last_seen_at == t0 + timedelta(seconds=30)
    ok = PlanEvaluationOutcome("P1", "INT-1", PlanOutcomeKind.EXIT_RECONCILED, "fine")
    board.record_tick((stuck, ok), now=t0 + timedelta(seconds=45))
    assert board.items() == ()


def test_a_console_without_a_plan_manager_has_no_attention_section() -> None:
    reply = Client(build_paper_application(_backend(), security=SecuritySession())).get("/safety")  # type: ignore[arg-type]
    assert reply.code == 200 and "Plans needing attention" not in reply.body
