"""MILESTONE-095 Phase 3/5/8-18 -- the event-driven research framework.

HOLDOUT-GUARDED AT THE ONE FETCH POINT, exactly like M093/M094: `fetch_symbol_news_guarded`
calls `m093_holdout_guard.assert_not_holdout` before ever reaching the network, for every
date in the requested window -- not just the endpoints. There is no second fetch path.

POINT-IN-TIME SAFETY (Phase 5): `events_usable_at` is the ONLY function in this module (or
anywhere in M095) that is allowed to decide whether an event is visible to a decision at
time T, and it does so with a single `published_at <= T` comparison -- never `updated_at`,
never a lookahead. `tests/unit/test_m095_event_research.py` proves adversarially that an
event published one second after T is invisible to a decision at T.

REUSES M094's OWN FORWARD-RETURN/REGIME/RANKING PRIMITIVES (`forward_return_to_horizon`,
`forward_return_to_liquidation`, `opening_gap_percent`, `spy_vwap_position`,
`spy_session_return_sign`, `spearman_rank_correlation`, `common_timestamps`) rather than
rebuilding them -- M095 is a new event layer ON TOP of the same look-ahead-safe bar
machinery M093/M094 already proved correct, not a parallel reimplementation of it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from statistics import median
from typing import TYPE_CHECKING

from empirical_platform.decision_candidate.m093_holdout_guard import assert_not_holdout
from empirical_platform.decision_candidate.m095_event_data import (
    EventRecord,
    EventType,
    SessionRelation,
    normalize_alpaca_articles,
)
from empirical_platform.decision_candidate.market_data import Bar
from empirical_platform.usecases.m094_edge_source_research import (
    EASTERN,
    forward_return_to_horizon,
    forward_return_to_liquidation,
    opening_gap_percent,
)

if TYPE_CHECKING:
    from empirical_platform.shared.brokerage.alpaca_paper import AlpacaPaperMarketDataClient

__all__ = [
    "GAP_THRESHOLDS_PERCENT",
    "RELATIVE_VOLUME_LOOKBACK_SESSIONS",
    "EventGapObservation",
    "GapBucket",
    "events_usable_at",
    "fetch_symbol_news_guarded",
    "gap_bucket",
    "observations_for_symbol",
    "opportunities_per_month",
    "relative_early_volume",
]


# ---------------------------------------------------------------------------
# The one guarded fetch point (Phase 3)
# ---------------------------------------------------------------------------


def fetch_symbol_news_guarded(
    news_port: AlpacaPaperMarketDataClient,
    symbol: str,
    *,
    window_start_date: date,
    window_end_date: date,
    retrieved_at: datetime,
) -> tuple[EventRecord, ...]:
    """The SINGLE place any M095 code fetches news. Every date in
    `[window_start_date, window_end_date]` is checked against the locked holdout BEFORE
    the network call -- not just the two endpoints, so a window that merely straddles the
    locked range (even if its own start/end sit outside it) is still refused."""
    probe = window_start_date
    while probe <= window_end_date:
        assert_not_holdout(probe)
        probe += timedelta(days=1)
    start = datetime.combine(window_start_date, datetime.min.time(), tzinfo=EASTERN).astimezone(UTC)
    end = datetime.combine(
        window_end_date + timedelta(days=1), datetime.min.time(), tzinfo=EASTERN
    ).astimezone(UTC)
    collected: list[EventRecord] = []
    page_token: str | None = None
    while True:
        page = news_port.fetch_news(
            (symbol,), start=start, end=end, limit=50, page_token=page_token
        )
        collected.extend(
            normalize_alpaca_articles(page.articles, symbol=symbol, retrieved_at=retrieved_at)
        )
        if page.next_page_token is None:
            break
        page_token = page.next_page_token
    return tuple(collected)


# ---------------------------------------------------------------------------
# Point-in-time usability (Phase 5)
# ---------------------------------------------------------------------------


def events_usable_at(events: Sequence[EventRecord], at: datetime) -> tuple[EventRecord, ...]:
    """Events visible to a decision made AT `at`. `published_at <= at` is the entire rule --
    no event published after `at`, even by one second, is ever included."""
    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")
    return tuple(event for event in events if event.published_at <= at)


# ---------------------------------------------------------------------------
# Gap buckets (Phase 10) -- predeclared thresholds, fixed before outcome comparison
# ---------------------------------------------------------------------------


class GapBucket(StrEnum):
    GAP_DOWN_LARGE = "GAP_DOWN_LARGE"
    GAP_DOWN_SMALL = "GAP_DOWN_SMALL"
    FLAT = "FLAT"
    GAP_UP_SMALL = "GAP_UP_SMALL"
    GAP_UP_LARGE = "GAP_UP_LARGE"


#: Percent-of-prior-close thresholds, predeclared (mission Phase 10: "do NOT brute-force
#: dozens of cutoffs"). |gap| <= 0.1% is FLAT; 0.1%-1.0% is SMALL; beyond 1.0% is LARGE.
#: Fixed before `tools/m095_event_study.py` is run against outcome data.
GAP_THRESHOLDS_PERCENT: tuple[Decimal, Decimal] = (Decimal("0.1"), Decimal("1.0"))


def gap_bucket(gap_percent: Decimal) -> GapBucket:
    flat_threshold, large_threshold = GAP_THRESHOLDS_PERCENT
    if gap_percent > large_threshold:
        return GapBucket.GAP_UP_LARGE
    if gap_percent > flat_threshold:
        return GapBucket.GAP_UP_SMALL
    if gap_percent < -large_threshold:
        return GapBucket.GAP_DOWN_LARGE
    if gap_percent < -flat_threshold:
        return GapBucket.GAP_DOWN_SMALL
    return GapBucket.FLAT


# ---------------------------------------------------------------------------
# Relative early volume (Phase 11) -- point-in-time safe: prior COMPLETED sessions only
# ---------------------------------------------------------------------------

RELATIVE_VOLUME_LOOKBACK_SESSIONS = 20


def relative_early_volume(
    today_bars: Sequence[Bar],
    prior_session_bars: Sequence[Sequence[Bar]],
    *,
    first_n_minutes: int = 30,
) -> Decimal | None:
    """Cumulative volume in the first `first_n_minutes` of TODAY's session, divided by the
    median of the same quantity across `prior_session_bars` (fully-completed, STRICTLY
    PRIOR sessions only -- the caller passes these in, this function never reaches outside
    the sequences it is given, and never uses today's own later bars or full-day volume).
    `None` if there are no prior sessions to compare against."""
    if not today_bars:
        return None
    window_end = today_bars[0].timestamp + timedelta(minutes=first_n_minutes)
    today_volume = sum(bar.volume for bar in today_bars if bar.timestamp < window_end)
    prior_volumes: list[int] = []
    for session_bars in prior_session_bars:
        if not session_bars:
            continue
        session_window_end = session_bars[0].timestamp + timedelta(minutes=first_n_minutes)
        prior_volumes.append(
            sum(bar.volume for bar in session_bars if bar.timestamp < session_window_end)
        )
    if not prior_volumes:
        return None
    baseline = median(prior_volumes)
    if baseline == 0:
        return None
    return Decimal(today_volume) / Decimal(baseline)


# ---------------------------------------------------------------------------
# One row of the event+gap study (Phase 8)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class EventGapObservation:
    symbol: str
    session_date: date
    event_present: bool
    event_type: EventType | None
    session_relation: SessionRelation | None
    gap_percent: Decimal | None
    bucket: GapBucket | None
    relative_early_volume: Decimal | None
    forward_return_15m: Decimal | None
    forward_return_30m: Decimal | None
    forward_return_60m: Decimal | None
    forward_return_120m: Decimal | None
    forward_return_session: Decimal | None
    spy_gap_sign: str | None


def observations_for_symbol(
    symbol: str,
    *,
    session_dates: Sequence[date],
    bars_by_date: Mapping[date, Sequence[Bar]],
    prior_close_by_date: Mapping[date, Decimal],
    events: Sequence[EventRecord],
    spy_bars_by_date: Mapping[date, Sequence[Bar]] | None = None,
    spy_prior_close_by_date: Mapping[date, Decimal] | None = None,
) -> tuple[EventGapObservation, ...]:
    """Build one `EventGapObservation` per session that has bars. The observation point is
    fixed at the session's first bar (the open) -- see `data-source-qualification.md`'s
    scope note: this milestone studies the open observation point only, not the mission's
    full open+5/15/30m sweep, to keep the implementation proportionate to what Phase 1/2's
    qualification actually supports."""
    rows: list[EventGapObservation] = []
    sorted_dates = sorted(session_dates)
    for position, session_date in enumerate(sorted_dates):
        bars = bars_by_date.get(session_date)
        if not bars:
            continue
        prior_close = prior_close_by_date.get(session_date)
        gap = opening_gap_percent(prior_close, bars[0].open) if prior_close is not None else None
        bucket = gap_bucket(gap) if gap is not None else None
        session_open = bars[0].timestamp
        usable = events_usable_at(events, session_open)
        event_present = len(usable) > 0
        # Most-recent usable event (closest to the open) decides the type/relation shown.
        chosen = max(usable, key=lambda e: e.published_at) if usable else None
        prior_sessions = [
            bars_by_date[d]
            for d in sorted_dates[max(0, position - RELATIVE_VOLUME_LOOKBACK_SESSIONS) : position]
            if d in bars_by_date and bars_by_date[d]
        ]
        rel_vol = relative_early_volume(bars, prior_sessions)
        spy_gap_sign: str | None = None
        if spy_bars_by_date is not None and spy_prior_close_by_date is not None:
            spy_bars = spy_bars_by_date.get(session_date)
            spy_prior = spy_prior_close_by_date.get(session_date)
            if spy_bars and spy_prior is not None:
                spy_gap = opening_gap_percent(spy_prior, spy_bars[0].open)
                if spy_gap is not None:
                    spy_gap_sign = "POSITIVE" if spy_gap >= 0 else "NEGATIVE"
        rows.append(
            EventGapObservation(
                symbol=symbol,
                session_date=session_date,
                event_present=event_present,
                event_type=chosen.event_type if chosen else None,
                session_relation=chosen.session_relation if chosen else None,
                gap_percent=gap,
                bucket=bucket,
                relative_early_volume=rel_vol,
                forward_return_15m=forward_return_to_horizon(bars, 0, horizon_minutes=15),
                forward_return_30m=forward_return_to_horizon(bars, 0, horizon_minutes=30),
                forward_return_60m=forward_return_to_horizon(bars, 0, horizon_minutes=60),
                forward_return_120m=forward_return_to_horizon(bars, 0, horizon_minutes=120),
                forward_return_session=forward_return_to_liquidation(bars, 0),
                spy_gap_sign=spy_gap_sign,
            )
        )
    return tuple(rows)


# ---------------------------------------------------------------------------
# Frequency economics (Phase 18)
# ---------------------------------------------------------------------------


def opportunities_per_month(
    count: int, *, session_count: int, sessions_per_month: int = 21
) -> Decimal:
    """`count` qualifying observations spread over `session_count` real sessions, scaled to
    a 21-trading-day month. `session_count` must be the ACTUAL number of sessions the
    observations were drawn from, never a calendar-day count."""
    if session_count <= 0:
        raise ValueError("session_count must be positive")
    return Decimal(count) / Decimal(session_count) * Decimal(sessions_per_month)
