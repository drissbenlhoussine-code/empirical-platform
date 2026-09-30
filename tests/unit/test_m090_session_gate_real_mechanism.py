"""MILESTONE-090 Category E (session) -- the REAL session-gate mechanism, not a fake port.

`tests/unit/test_usecases_opportunity_engine.py` already proves `GenerateOpportunitiesHandler`
reacts correctly to `_m090_fakes.FakeClockView` -- but that fake stands in for the BROKER
TRANSPORT (`fetch_clock()`'s network round trip), never for the session-state LOGIC itself.
This file calls `decision_candidate.opportunity_engine.market_session_state` -- the exact
production function `GenerateOpportunitiesHandler.handle()` and
`_opportunity_engine_composition.OpportunityEngineRuntime.generate_today` both call -- directly,
with real `datetime`/`ZoneInfo`/`BoundedInstant` values, no fake or mock of any kind. No network
call is made: `AlpacaPaperClient.fetch_clock()`'s own HTTP round trip is exercised by the
`EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS=1`-gated live-network suite (M069's established pattern),
not duplicated here.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from empirical_platform.decision_candidate.opportunity_engine import (
    MarketSessionState,
    market_session_state,
)
from empirical_platform.shared.brokerage.paper_time import BoundedInstant

_EARLIEST = time(10, 0)
_LATEST = time(15, 30)
_ZONE = "America/New_York"


def _instant(hour: int, minute: int = 0) -> BoundedInstant:
    """A REAL, zero-uncertainty broker instant at `hour:minute` America/New_York, converted to
    UTC exactly the way a real Alpaca clock timestamp already arrives (timezone-aware)."""
    local = datetime(2026, 6, 10, hour, minute, tzinfo=ZoneInfo(_ZONE))
    moment = local.astimezone(UTC)
    return BoundedInstant(earliest=moment, latest=moment)


def test_market_closed_wins_over_every_other_signal() -> None:
    assert (
        market_session_state(
            is_open=False,
            broker_now=_instant(12, 0),
            earliest_entry_time=_EARLIEST,
            latest_entry_time=_LATEST,
            operator_timezone=_ZONE,
        )
        is MarketSessionState.MARKET_CLOSED
    )


def test_premarket_research_before_the_entry_window_opens() -> None:
    assert (
        market_session_state(
            is_open=True,
            broker_now=_instant(9, 0),
            earliest_entry_time=_EARLIEST,
            latest_entry_time=_LATEST,
            operator_timezone=_ZONE,
        )
        is MarketSessionState.PREMARKET_RESEARCH
    )


def test_regular_session_inside_the_entry_window() -> None:
    assert (
        market_session_state(
            is_open=True,
            broker_now=_instant(12, 30),
            earliest_entry_time=_EARLIEST,
            latest_entry_time=_LATEST,
            operator_timezone=_ZONE,
        )
        is MarketSessionState.REGULAR_SESSION
    )


def test_entry_window_closed_after_the_entry_window_but_market_still_open() -> None:
    assert (
        market_session_state(
            is_open=True,
            broker_now=_instant(16, 0),
            earliest_entry_time=_EARLIEST,
            latest_entry_time=_LATEST,
            operator_timezone=_ZONE,
        )
        is MarketSessionState.ENTRY_WINDOW_CLOSED
    )


def test_a_boundary_straddling_broker_uncertainty_interval_reads_conservatively() -> None:
    """A REAL clock read never carries zero uncertainty in production (a request/response round
    trip takes measurable time); this proves the conservative-widening rule fires against the
    production `BoundedInstant` type, not a fake stand-in for it."""
    moment_before = datetime(2026, 6, 10, 9, 59, 30, tzinfo=ZoneInfo(_ZONE)).astimezone(UTC)
    moment_after = datetime(2026, 6, 10, 10, 0, 30, tzinfo=ZoneInfo(_ZONE)).astimezone(UTC)
    straddling = BoundedInstant(earliest=moment_before, latest=moment_after)
    assert (
        market_session_state(
            is_open=True,
            broker_now=straddling,
            earliest_entry_time=_EARLIEST,
            latest_entry_time=_LATEST,
            operator_timezone=_ZONE,
        )
        is not MarketSessionState.REGULAR_SESSION
    )


def test_every_state_is_reachable_from_the_same_real_function_no_duplication() -> None:
    """All four `MarketSessionState` members are producible from ONE call site -- proving this
    suite does not silently test a narrower subset than Phase 4 requires."""
    produced = {
        market_session_state(
            is_open=is_open,
            broker_now=_instant(hour),
            earliest_entry_time=_EARLIEST,
            latest_entry_time=_LATEST,
            operator_timezone=_ZONE,
        )
        for is_open, hour in ((False, 12), (True, 9), (True, 12), (True, 16))
    }
    assert produced == set(MarketSessionState)
