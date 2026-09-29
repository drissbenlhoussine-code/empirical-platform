"""MILESTONE-089 FINAL SAFETY CLOSURE -- the exit's quote must be fresh, or REFUSE.

The mission's own words: "If quote becomes too stale: REFUSE." `PreviewPositionExitHandler`
required a positive bid but enforced no explicit age bound (adversarial-review.md finding
#6). This suite pins the fix: `PreviewPositionExitHandler` and
`SubmitAuthorizedPositionExitHandler` both now call M085's own `quote_refusal` -- the ONE
durable freshness/quality gate this codebase already has, reused unchanged -- against
`ExecutionPolicy.quote_maximum_age_seconds`, derived from the SAME `OperatorTradingConfiguration`
version that governed the position's entry. No new constant was introduced.

Every case here uses the REAL SIMULATION broker/console (`simulation_world`), the SAME harness
`test_m087_position_exit_service.py` already proves the round trip with, so "existing M087
SIMULATION behavior remains correct" is exercised by the SAME machinery, not a separate mock.
Only the "refused at preview" and "future-dated" cases substitute a controllable fake market-data
port for the one call whose staleness the test must dictate; the broker, the repositories and the
configuration are all real.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from tests.unit._m086_fakes import World, simulation_world

from empirical_platform.decision_candidate.paper_execution import PaperExecutionState
from empirical_platform.usecases.operator_console import ConsoleRefusalError
from empirical_platform.usecases.position_exit import (
    PositionExitRefusedError,
    PreviewPositionExitCommand,
    PreviewPositionExitHandler,
)


@pytest.fixture
def world(tmp_path: Path) -> World:
    return simulation_world(tmp_path, exits=True)


def _intent(world: World, symbol: str) -> str:
    return f"INT-{world.proposal_id(symbol)}"


def _approve(world: World, symbol: str) -> None:
    proposal = world.proposal_id(symbol)
    view = world.service.prepare_approval(proposal)
    outcome = world.service.confirm_approval(proposal, view.ticket)
    assert outcome.sent == "sent", outcome.message


def _settle(world: World, passes: int = 2) -> None:
    for _ in range(passes):
        world.clock.advance(5)
        world.service.refresh_executions()


def _open_position(world: World, symbol: str = "AAPL") -> str:
    world.load_day((symbol,))
    _approve(world, symbol)
    _settle(world)
    intent = _intent(world, symbol)
    entry = world.repositories.attempts.for_intent(intent)
    assert entry is not None and entry.state is PaperExecutionState.FILLED
    return intent


@dataclass
class _Quote:
    """A `PaperMarketDataPort.fetch_quote` view with a caller-chosen `captured_at`."""

    symbol: str
    bid: str
    ask: str
    captured_at: datetime
    source: str = "test-controlled"


class _ControllableMarketData:
    """Everything but the quote's age/timestamp is realistic; that one field is the point."""

    endpoint_host = "test-market-data"

    def __init__(self, quote: _Quote | None) -> None:
        self._quote = quote

    def fetch_quote(self, symbol: str) -> _Quote | None:
        del symbol
        return self._quote


def _preview_with_quote(world: World, intent: str, quote: _Quote | None) -> None:
    """Attempt a preview using the REAL broker/repositories/configuration but a chosen quote."""
    PreviewPositionExitHandler(
        intents=world.repositories.intents,
        entry_attempts=world.repositories.attempts,
        exit_attempts=world.exits.attempts,
        previews=world.exits.previews,
        events=world.exits.events,
        broker=world.broker,
        market_data=_ControllableMarketData(quote),
        configurations=world.repositories.configurations,
        environment="SIMULATION",
        time_source=world.clock,
    ).handle(
        PreviewPositionExitCommand(
            entry_intent_governance_id=intent,
            preview_id=f"XPV-TEST-{intent}",
            created_at=world.clock.utc,
        )
    )


# ---------------------------------------------------------------------------
# 1. Fresh quote accepted
# ---------------------------------------------------------------------------


def test_a_fresh_quote_is_accepted_at_preview(world: World) -> None:
    intent = _open_position(world, "AAPL")
    quote = _Quote(
        symbol="AAPL",
        bid="227.40",
        ask="227.60",
        captured_at=world.clock.utc - timedelta(seconds=5),
    )
    # 5s old against the fixture's 60s policy (operator_console_fixtures.SIMULATION
    # configuration, maximum_market_data_age_seconds=60): comfortably fresh.
    _preview_with_quote(world, intent, quote)  # must not raise
    preview = world.exits.previews.latest_for_entry(intent)
    assert preview is not None
    assert preview.quote_bid == quote.bid or str(preview.quote_bid) == quote.bid


# ---------------------------------------------------------------------------
# 2. Stale quote refused AT PREVIEW
# ---------------------------------------------------------------------------


def test_a_stale_quote_is_refused_at_preview_and_nothing_is_sent(world: World) -> None:
    intent = _open_position(world, "AAPL")
    stale = _Quote(
        symbol="AAPL",
        bid="227.40",
        ask="227.60",
        captured_at=world.clock.utc - timedelta(seconds=200),
    )
    # 200s old against the 60s policy limit: REFUSE, not a repriced or silently accepted exit.
    with pytest.raises(PositionExitRefusedError, match="not usable to price this exit"):
        _preview_with_quote(world, intent, stale)
    assert world.exits.previews.latest_for_entry(intent) is None  # nothing was persisted
    assert world.exits.attempts.for_entry(intent) == ()  # and certainly nothing was dispatched


# ---------------------------------------------------------------------------
# 3. Future/invalid quote timestamp refused
# ---------------------------------------------------------------------------


def test_a_future_dated_quote_is_refused_at_preview(world: World) -> None:
    intent = _open_position(world, "AAPL")
    future = _Quote(
        symbol="AAPL",
        bid="227.40",
        ask="227.60",
        captured_at=world.clock.utc + timedelta(seconds=30),
    )
    with pytest.raises(PositionExitRefusedError, match="not usable to price this exit"):
        _preview_with_quote(world, intent, future)
    assert world.exits.previews.latest_for_entry(intent) is None


def test_a_missing_quote_is_refused_at_preview(world: World) -> None:
    intent = _open_position(world, "AAPL")
    with pytest.raises(PositionExitRefusedError, match="not usable to price this exit"):
        _preview_with_quote(world, intent, None)
    assert world.exits.previews.latest_for_entry(intent) is None


# ---------------------------------------------------------------------------
# 4. Fresh at review, stale by confirm: REFUSE, never a silently reauthorized exit
# ---------------------------------------------------------------------------


def test_a_quote_fresh_at_review_but_stale_by_confirm_is_refused_and_sends_nothing(
    world: World,
) -> None:
    intent = _open_position(world, "AAPL")
    review = world.service.exits.review(intent)  # type: ignore[union-attr]
    assert review.side == "SELL TO CLOSE"  # the real, unstaled review succeeded

    # More than the 60s policy limit elapses before the Owner confirms. The STORED preview
    # evidence (quote_bid/quote_ask/quote_captured_at) is unchanged; only the broker clock the
    # confirm step measures has moved on.
    world.clock.advance(120)

    with pytest.raises(ConsoleRefusalError, match="no longer usable"):
        world.service.exits.confirm(intent, review.ticket)  # type: ignore[union-attr]

    # Zero SELL orders: no attempt was ever claimed, and the broker holds no order under the
    # exit's own deterministic identity.
    assert world.exits.attempts.for_entry(intent) == ()
    preview = world.exits.previews.get(f"XPV-{intent}-1")
    assert preview is not None
    status, view, _ = world.broker.fetch_order_by_client_order_id(preview.request.client_order_id)
    assert view is None


# ---------------------------------------------------------------------------
# 5. Existing M087 SIMULATION behaviour is unchanged: the fresh round trip still closes
# ---------------------------------------------------------------------------


def test_the_fresh_round_trip_still_fully_closes_the_position(world: World) -> None:
    """MILESTONE-089 regression pin: the freshness gate does not touch a normal fresh exit."""
    intent = _open_position(world, "AAPL")
    review = world.service.exits.review(intent)  # type: ignore[union-attr]
    outcome = world.service.exits.confirm(intent, review.ticket)  # type: ignore[union-attr]
    assert outcome.ok is True
    for _ in range(3):
        world.clock.advance(5)
        world.service.exits.refresh()  # type: ignore[union-attr]
    (attempt,) = world.exits.attempts.for_entry(intent)
    assert attempt.position_closed
    assert world.store.position("AAPL") == 0
