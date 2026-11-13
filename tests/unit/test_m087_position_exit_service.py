"""MILESTONE-087 -- the Owner closes a position from the console: review, confirm, verify.

Over the in-memory world with the REAL simulation broker, the REAL M085 chain for the entry
and the REAL M087 handlers for the exit. Every case here is one of the adversarial attacks
the mission names; each asserts what was durably recorded and what the broker received.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world

from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.decision_candidate.position_exit import PositionExitState
from empirical_platform.shared.brokerage.simulation_paper import SimulationExitScenario
from empirical_platform.usecases.operator_console import ConsoleRefusalError, HumanState
from empirical_platform.usecases.operator_console_exits import (
    CATEGORY_EXIT_IN_PROGRESS,
    CATEGORY_NEEDS_ATTENTION,
    CATEGORY_OPEN_POSITION,
    CATEGORY_POSITION_CLOSED,
    CATEGORY_WORKING_ENTRY,
    DEADLINE_MISSED_TRUTH,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


def _intent(world: World, symbol: str) -> str:
    return f"INT-{world.proposal_id(symbol)}"


def _approve(world: World, symbol: str, *, expect_sent: bool = True) -> None:
    proposal = world.proposal_id(symbol)
    view = world.service.prepare_approval(proposal)
    outcome = world.service.confirm_approval(proposal, view.ticket)
    if expect_sent:
        assert outcome.sent == "sent", outcome.message


def _settle(world: World, passes: int = 2) -> None:
    for _ in range(passes):
        world.clock.advance(5)
        world.service.refresh_executions()


def _open_position(
    world: World,
    symbol: str = "AAPL",
    *,
    exit_scenario: SimulationExitScenario | None = None,
) -> str:
    """Load, approve and fill one entry: the position the exit tests start from."""
    world.load_day(
        (symbol,), exit_scenarios=None if exit_scenario is None else {symbol: exit_scenario}
    )
    _approve(world, symbol)
    _settle(world)
    intent = _intent(world, symbol)
    entry = world.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.state is PaperExecutionState.FILLED
    return intent


def _exits(world: World, intent: str) -> tuple:
    return world.exits.attempts.for_entry(intent)


# ---------------------------------------------------------------------------
# The happy round trip
# ---------------------------------------------------------------------------


def test_the_full_round_trip_closes_the_position_and_history_shows_the_realized_result(
    world: World,
) -> None:
    intent = _open_position(world, "AAPL")
    (held,) = world.service.active_trades()
    assert held.category == CATEGORY_OPEN_POSITION and held.can_review_exit
    assert held.exit is None and not held.position_closed
    assert world.store.position("AAPL") == 8

    review = world.service.exits.review(intent)  # type: ignore[union-attr]
    assert review.side == "SELL TO CLOSE" and review.environment == "SIMULATION"
    assert review.exit_quantity == "8" and review.current_holding == "8"
    assert review.order_type == "LIMIT" and review.limit_price == "227.40"  # the staged bid
    assert review.entry_avg_fill_price == "227.50"  # the entry filled at the ask
    assert review.liquidation_deadline > world.clock.utc
    assert review.authorization_expires_at <= review.liquidation_deadline
    assert "Owner" in review.deadline_note
    assert world.exits.attempts.for_entry(intent) == ()  # reviewing sends nothing

    outcome = world.service.exits.confirm(intent, review.ticket)  # type: ignore[union-attr]
    assert outcome.ok and outcome.sent == "sent" and outcome.state is HumanState.ACCEPTED
    (exit_attempt,) = _exits(world, intent)
    assert exit_attempt.state is PositionExitState.ACCEPTED
    assert exit_attempt.client_order_id.startswith("m087-")
    assert exit_attempt.quantity == 8 and not exit_attempt.position_closed
    sent = [o for o in world.store.orders() if o.side == "sell"]
    assert len(sent) == 1 and sent[0].client_order_id == exit_attempt.client_order_id
    assert sent[0].quantity == "8" and sent[0].limit_price == "227.40"

    (in_progress,) = world.service.active_trades()
    assert in_progress.category == CATEGORY_EXIT_IN_PROGRESS and not in_progress.can_review_exit
    assert in_progress.exit is not None and not in_progress.exit.position_closed
    assert [s.label for s in in_progress.exit.timeline] == [
        "Open position",
        "Exit reviewed",
        "Owner confirmed",
        "Exit submitted",
        "Accepted",
        "Filled / Cancelled / Needs attention",
        "Position closed",
    ]
    assert not in_progress.exit.timeline[-1].reached  # never "closed" because it was submitted

    _settle(world)
    closed = world.exits.attempts.active_for_entry(intent)
    assert closed is not None and closed.state is PositionExitState.FILLED
    assert closed.position_closed and closed.closed_position_verified_at is not None
    assert world.store.position("AAPL") == 0
    assert world.service.active_trades() == ()  # a verified closed position leaves Active
    assert world.service.today().active_positions_count == 0
    summary = world.service.execution(intent)
    assert summary.category == CATEGORY_POSITION_CLOSED and summary.position_closed
    assert summary.exit is not None and summary.exit.timeline[-1].reached
    assert summary.exit.realized is not None
    assert summary.exit.realized.realized_pnl == (Decimal("227.40") - Decimal("227.50")) * 8
    (row,) = world.service.history(symbol="AAPL")
    assert row.execution_outcome == "Position closed (simulation)"
    assert "realized −0.80 USD" in row.result and "simulation" in row.result
    assert row.quantity == "8" and row.price == "227.50"


def test_a_duplicate_confirmation_and_a_second_tab_never_create_a_second_exit(
    world: World,
) -> None:
    intent = _open_position(world, "AAPL")
    exits = world.service.exits
    assert exits is not None
    tab_one = exits.review(intent)
    tab_two = exits.review(intent)  # a second review page, a second preview version
    assert tab_two.preview_version == tab_one.preview_version + 1
    first = exits.confirm(intent, tab_one.ticket)
    assert first.ok and first.title == "Exit confirmed and sent"
    again = exits.confirm(intent, tab_one.ticket)  # double click / refresh of the POST
    other_tab = exits.confirm(intent, tab_two.ticket)
    assert again.title == "Already confirmed" and other_tab.title == "Already confirmed"
    assert len(_exits(world, intent)) == 1
    assert len([o for o in world.store.orders() if o.side == "sell"]) == 1
    # The second preview was never authorized, so nothing about it can be spent later.
    assert world.exits.authorizations.latest_for_entry(intent).preview_id == tab_one.preview_id  # type: ignore[union-attr]


def test_a_second_process_over_the_same_records_cannot_send_again(world: World) -> None:
    intent = _open_position(world, "AAPL")
    review = world.service.exits.review(intent)  # type: ignore[union-attr]
    world.service.exits.confirm(intent, review.ticket)  # type: ignore[union-attr]
    restarted = world.restart()
    # A ticket from the previous process is refused (new secret); and even a fresh review in
    # the new process is refused because an exit is already in progress.
    with pytest.raises(ConsoleRefusalError):
        restarted.service.exits.confirm(intent, review.ticket)  # type: ignore[union-attr]
    with pytest.raises(ConsoleRefusalError, match="already in progress"):
        restarted.service.exits.review(intent)  # type: ignore[union-attr]
    assert len(_exits(restarted, intent)) == 1


# ---------------------------------------------------------------------------
# Refusals before anything is sent
# ---------------------------------------------------------------------------


def test_a_stale_ticket_and_an_expired_review_send_nothing(world: World) -> None:
    intent = _open_position(world, "AAPL")
    exits = world.service.exits
    assert exits is not None
    review = exits.review(intent)
    tampered = review.ticket.replace(review.fingerprint_short, "0" * 12, 1)
    with pytest.raises(ConsoleRefusalError, match="Out of date|did not come"):
        exits.confirm(intent, tampered)
    world.clock.advance(16 * 60)
    with pytest.raises(ConsoleRefusalError, match="too old"):
        exits.confirm(intent, review.ticket)
    assert _exits(world, intent) == ()
    assert [o for o in world.store.orders() if o.side == "sell"] == []


def test_the_kill_switch_engaged_after_the_review_does_not_block_the_confirmation(
    world: World,
) -> None:
    """RELEASE v1 behavior change: the kill switch blocks NEW ENTRIES only. An already-open
    position must never be silently trapped by it, so an engaged kill switch must not block
    reviewing, authorizing, or submitting a position-reducing exit. See
    `docs/operations/kill-switch.md`."""
    intent = _open_position(world, "AAPL")
    exits = world.service.exits
    assert exits is not None
    review = exits.review(intent)
    world.service.set_kill_switch(engaged=True, reason="test")
    outcome = exits.confirm(intent, review.ticket)
    assert outcome.ok
    assert len(_exits(world, intent)) == 1
    assert [o for o in world.store.orders() if o.side == "sell"] != []


def test_a_position_that_changed_after_the_review_is_refused_at_confirmation(world: World) -> None:
    intent = _open_position(world, "AAPL")
    exits = world.service.exits
    assert exits is not None
    review = exits.review(intent)
    world.store.add_position("AAPL", 1)  # an unexplained external share appears
    with pytest.raises(ConsoleRefusalError, match="changed after it was reviewed|does not equal"):
        exits.confirm(intent, review.ticket)
    assert _exits(world, intent) == ()
    with pytest.raises(ConsoleRefusalError, match="operator attention"):
        exits.review(intent)


@pytest.mark.parametrize(
    ("symbol", "reason"),
    [
        ("NVDA", "no long position"),  # accepted, never filled: zero position
        ("AMZN", "filled nothing|no long position|REJECTED"),  # rejected by the broker
        ("MSFT", "partially filled"),  # remainder still working
    ],
)
def test_ineligible_positions_are_refused_with_the_attention_sentence(
    world: World, symbol: str, reason: str
) -> None:
    world.load_day((symbol,))
    _approve(world, symbol)
    _settle(world)
    with pytest.raises(ConsoleRefusalError, match=reason) as refused:
        world.service.exits.review(_intent(world, symbol))  # type: ignore[union-attr]
    assert "Position requires operator attention" in refused.value.message
    assert _exits(world, _intent(world, symbol)) == ()


def test_a_cancelled_partial_entry_becomes_a_stable_position_that_can_be_closed(
    world: World,
) -> None:
    world.load_day(("MSFT",))
    _approve(world, "MSFT")
    _settle(world)
    intent = _intent(world, "MSFT")
    entry = world.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.state is PaperExecutionState.PARTIALLY_FILLED
    (row,) = world.service.active_trades()
    assert row.category == CATEGORY_WORKING_ENTRY  # the remainder can still fill
    world.service.cancel_execution(intent)
    _settle(world)
    entry = world.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.state is PaperExecutionState.CANCELED
    assert entry.filled_quantity == Decimal(2)  # half of 4
    assert world.store.position("MSFT") == 2
    (row,) = world.service.active_trades()
    assert row.category == CATEGORY_OPEN_POSITION and row.can_review_exit
    review = world.service.exits.review(intent)  # type: ignore[union-attr]
    assert review.exit_quantity == "2"
    outcome = world.service.exits.confirm(intent, review.ticket)  # type: ignore[union-attr]
    assert outcome.ok
    # MSFT's exit races a cancel and fills anyway.
    (exit_attempt,) = _exits(world, intent)
    world.service.exits.cancel(exit_attempt.attempt_id)  # type: ignore[union-attr]
    _settle(world)
    closed = world.exits.attempts.active_for_entry(intent)
    assert closed is not None and closed.position_closed
    assert world.store.position("MSFT") == 0


def test_a_second_entry_in_the_same_symbol_is_refused_by_m085_so_attribution_stays_single(
    world: World,
) -> None:
    """Two lots in one symbol never arise through the engine: M085 refuses the second BUY while
    a position exists. The domain rule for an ambiguous position is covered in the domain
    suite; here the first position stays exclusively attributable and closable."""
    first = _open_position(world, "AAPL")
    world.clock.advance(24 * 3600)  # a new simulation day: a second AAPL proposal
    world.load_day(("AAPL",))
    _approve(world, "AAPL", expect_sent=False)
    second = _intent(world, "AAPL")
    assert world.repositories.attempts.for_intent(second) is None  # nothing was sent
    assert world.store.position("AAPL") == 8
    review = world.service.exits.review(first)  # type: ignore[union-attr]
    assert review.exit_quantity == "8"
    assert world.service.exits.assess(first).snapshot.competing_entry_attempt_ids == ()  # type: ignore[union-attr]


# ---------------------------------------------------------------------------
# What the broker does with the exit
# ---------------------------------------------------------------------------


def test_a_broker_rejection_leaves_the_position_open_and_reviewable_again(world: World) -> None:
    intent = _open_position(world, "AAPL", exit_scenario=SimulationExitScenario.EXIT_REJECTION)
    exits = world.service.exits
    assert exits is not None
    review = exits.review(intent)
    outcome = exits.confirm(intent, review.ticket)
    assert not outcome.ok and outcome.title == "Exit rejected by the broker"
    (rejected,) = _exits(world, intent)
    assert rejected.state is PositionExitState.REJECTED and rejected.failure_code == "HTTP_403"
    assert world.store.position("AAPL") == 8
    (row,) = world.service.active_trades()
    assert row.category == CATEGORY_OPEN_POSITION and row.can_review_exit
    second = exits.review(intent)
    assert second.preview_version == 2
    # A new exit is a NEW identity; the refused one is never re-sent under the same id.
    exits.confirm(intent, second.ticket)
    attempts = _exits(world, intent)
    assert len(attempts) == 2 and attempts[0].client_order_id != attempts[1].client_order_id


def test_a_failure_before_the_send_is_blocked_with_nothing_sent(world: World) -> None:
    intent = _open_position(
        world, "AAPL", exit_scenario=SimulationExitScenario.EXIT_FAILURE_BEFORE_SEND
    )
    exits = world.service.exits
    assert exits is not None
    outcome = exits.confirm(intent, exits.review(intent).ticket)
    assert outcome.sent == "nothing_sent" and outcome.state is HumanState.BLOCKED
    (blocked,) = _exits(world, intent)
    assert blocked.state is PositionExitState.REJECTED and blocked.failure_code == "NOT_SENT"
    assert [o for o in world.store.orders() if o.side == "sell"] == []
    assert world.store.position("AAPL") == 8


def test_an_ambiguous_exit_is_unknown_and_reconciliation_addresses_the_same_identity(
    world: World,
) -> None:
    intent = _open_position(
        world, "AAPL", exit_scenario=SimulationExitScenario.EXIT_AMBIGUOUS_AFTER_POSSIBLE_SEND
    )
    exits = world.service.exits
    assert exits is not None
    ticket = exits.review(intent).ticket
    outcome = exits.confirm(intent, ticket)
    assert outcome.sent == "unknown" and "do not retry" in outcome.title
    (unknown,) = _exits(world, intent)
    assert unknown.state is PositionExitState.SUBMISSION_UNKNOWN
    (row,) = world.service.active_trades()
    assert row.category == CATEGORY_NEEDS_ATTENTION
    # A second confirmation while UNKNOWN reports the same exit and sends nothing.
    again = exits.confirm(intent, ticket)
    assert again.sent == "unknown" and again.message.startswith("Already confirmed")
    with pytest.raises(ConsoleRefusalError, match="already in progress"):
        exits.review(intent)
    _settle(world)
    resolved = world.exits.attempts.active_for_entry(intent)
    assert resolved is not None and resolved.position_closed
    lookups = [o for o in world.store.orders() if o.side == "sell"]
    assert len(lookups) == 1 and lookups[0].client_order_id == unknown.client_order_id
    assert len(_exits(world, intent)) == 1


def test_an_exit_never_received_is_resolved_by_the_bounded_absence_policy(world: World) -> None:
    intent = _open_position(
        world, "AAPL", exit_scenario=SimulationExitScenario.EXIT_RECONCILIATION_NOT_FOUND
    )
    exits = world.service.exits
    assert exits is not None
    outcome = exits.confirm(intent, exits.review(intent).ticket)
    assert outcome.sent == "unknown"
    for _ in range(3):
        world.clock.advance(40)
        world.service.refresh_executions()
    (resolved,) = _exits(world, intent)
    assert resolved.state is PositionExitState.REJECTED
    assert resolved.failure_code == "NOT_FOUND_AT_BROKER"
    assert world.store.position("AAPL") == 8  # the position remains open, honestly
    (row,) = world.service.active_trades()
    assert row.category == CATEGORY_OPEN_POSITION


def test_a_restart_while_the_exit_is_unknown_preserves_unknown_and_then_resolves_it(
    world: World,
) -> None:
    intent = _open_position(
        world, "AAPL", exit_scenario=SimulationExitScenario.EXIT_RESTART_WHILE_UNKNOWN
    )
    exits = world.service.exits
    assert exits is not None
    exits.confirm(intent, exits.review(intent).ticket)
    (unknown,) = _exits(world, intent)
    assert unknown.state is PositionExitState.SUBMISSION_UNKNOWN
    restarted = world.restart()
    (still,) = restarted.exits.attempts.for_entry(intent)
    assert still.state is PositionExitState.SUBMISSION_UNKNOWN  # nothing was sent by restarting
    assert len([o for o in restarted.store.orders() if o.side == "sell"]) == 1
    _settle(restarted)
    closed = restarted.exits.attempts.active_for_entry(intent)
    assert closed is not None and closed.position_closed
    assert closed.client_order_id == unknown.client_order_id


def test_a_partial_exit_fill_reduces_the_position_but_never_calls_it_closed(world: World) -> None:
    intent = _open_position(world, "AAPL", exit_scenario=SimulationExitScenario.EXIT_PARTIAL_FILL)
    exits = world.service.exits
    assert exits is not None
    exits.confirm(intent, exits.review(intent).ticket)
    _settle(world)
    (partial,) = _exits(world, intent)
    assert partial.state is PositionExitState.PARTIALLY_FILLED
    assert partial.filled_quantity == Decimal(4) and not partial.position_closed
    assert world.store.position("AAPL") == 4
    (row,) = world.service.active_trades()
    assert row.category == CATEGORY_EXIT_IN_PROGRESS
    assert row.exit is not None and row.exit.can_cancel
    exits.cancel(partial.attempt_id)
    _settle(world)
    (cancelled,) = _exits(world, intent)
    assert cancelled.state is PositionExitState.CANCELED
    # The remainder is a stable position again: attributable 4 == broker 4, a full close of 4.
    review = exits.review(intent)
    assert review.exit_quantity == "4" and review.preview_version == 2


def test_a_missed_liquidation_deadline_is_recorded_and_shown_and_nothing_is_sent(
    world: World,
) -> None:
    intent = _open_position(world, "AAPL")
    deadline = world.repositories.intents.get(intent).mandatory_liquidation_at  # type: ignore[union-attr]
    world.clock.utc = deadline
    world.clock.monotonic += 1
    world.service.refresh_executions()
    (row,) = world.service.active_trades()
    assert row.deadline_tone == "danger" and DEADLINE_MISSED_TRUTH in row.deadline_note
    assert any(DEADLINE_MISSED_TRUTH in w for w in row.warnings)
    assert world.service.exits.deadline_missed_recorded(intent)  # type: ignore[union-attr]
    assert _exits(world, intent) == ()  # no unattended liquidation, ever
    assert world.store.position("AAPL") == 8
    world.service.refresh_executions()
    events = [e for e in world.exits.events.for_entry(intent) if "DEADLINE" in e.event_type]
    assert len(events) == 1  # recorded once


def test_the_simulator_refuses_to_cross_below_zero(world: World) -> None:
    world.store.add_position("KO", 3)
    with pytest.raises(ValueError, match="negative"):
        world.store.reduce_position("KO", 4)
    assert world.store.position("KO") == 3
    assert world.store.reduce_position("KO", 3) == 0
    assert world.broker.fetch_position("KO") is None
