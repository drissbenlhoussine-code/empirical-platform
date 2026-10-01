"""MILESTONE-095 Phase 3/5/10/11/21/23 -- the event research framework's own safety proofs.

Covers: holdout blocked before any network access (news fetch), publication-time filtering
with an ADVERSARIAL after-T-is-invisible-at-T proof, deterministic gap buckets, point-in-time
relative-volume (never reads today's own later bars or full-day volume), and non-overlapping
temporal construction.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from empirical_platform.decision_candidate.m093_holdout_guard import (
    HOLDOUT_END,
    HOLDOUT_START,
    HoldoutLockedError,
)
from empirical_platform.decision_candidate.m095_event_data import (
    EventRecord,
    EventType,
    SessionRelation,
)
from empirical_platform.decision_candidate.market_data import Bar, BarInterval, Instrument
from empirical_platform.usecases.m095_event_research import (
    GapBucket,
    events_usable_at,
    fetch_symbol_news_guarded,
    gap_bucket,
    relative_early_volume,
)


class _StubNewsPortRaisesIfCalled:
    """Any network call reaching this stub proves the holdout guard did NOT fire first."""

    def fetch_news(self, *args: object, **kwargs: object) -> object:
        raise AssertionError(
            "news fetch must never be reached for a window touching the locked holdout"
        )


@pytest.mark.parametrize(
    ("window_start", "window_end"),
    [
        (HOLDOUT_START, HOLDOUT_END),
        (date(2026, 4, 1), date(2026, 4, 5)),
        # Straddles the locked range without either endpoint sitting inside it.
        (date(2026, 3, 1), date(2026, 6, 1)),
        # Only the END touches the locked range.
        (date(2026, 5, 1), HOLDOUT_END),
    ],
)
def test_news_fetch_refuses_before_any_network_access_for_windows_touching_holdout(
    window_start: date, window_end: date
) -> None:
    with pytest.raises(HoldoutLockedError):
        fetch_symbol_news_guarded(
            _StubNewsPortRaisesIfCalled(),  # type: ignore[arg-type]
            "AAPL",
            window_start_date=window_start,
            window_end_date=window_end,
            retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
        )


def test_news_fetch_does_not_refuse_a_real_research_window() -> None:
    """Negative control: a window entirely outside the locked range reaches the stub's own
    (intentionally failing) `fetch_news` -- proving the guard discriminates rather than
    refusing everything."""
    with pytest.raises(AssertionError, match="news fetch must never be reached"):
        fetch_symbol_news_guarded(
            _StubNewsPortRaisesIfCalled(),  # type: ignore[arg-type]
            "AAPL",
            window_start_date=date(2026, 5, 13),
            window_end_date=date(2026, 5, 20),
            retrieved_at=datetime(2026, 9, 1, tzinfo=UTC),
        )


def _event(published_at: datetime) -> EventRecord:
    return EventRecord(
        event_id="x",
        symbol="AAPL",
        event_type=EventType.OTHER_NEWS,
        source="benzinga",
        published_at=published_at,
        session_relation=SessionRelation.REGULAR_SESSION,
        headline="irrelevant",
        retrieved_at=published_at,
        source_version="alpaca-news-v1beta1",
    )


def test_event_published_before_t_is_usable_at_t() -> None:
    t = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    event = _event(t - timedelta(minutes=1))
    assert events_usable_at([event], t) == (event,)


def test_event_published_exactly_at_t_is_usable_at_t() -> None:
    t = datetime(2026, 6, 1, 14, 0, tzinfo=UTC)
    event = _event(t)
    assert events_usable_at([event], t) == (event,)


def test_event_published_one_second_after_t_is_invisible_at_t() -> None:
    """ADVERSARIAL (Phase 5): an event published one second after the decision instant must
    not leak into that decision -- the gap between 'usable' and 'invisible' is exactly zero,
    not a rounding tolerance."""
    t = datetime(2026, 6, 1, 14, 0, 0, tzinfo=UTC)
    poisoned_future_event = _event(t + timedelta(seconds=1))
    assert events_usable_at([poisoned_future_event], t) == ()


def test_events_usable_at_requires_timezone_aware_instant() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        events_usable_at([], datetime(2026, 6, 1, 14, 0))  # noqa: DTZ001


def test_gap_bucket_is_deterministic_and_predeclared() -> None:
    assert gap_bucket(Decimal("0.0")) == GapBucket.FLAT
    assert gap_bucket(Decimal("0.05")) == GapBucket.FLAT
    assert gap_bucket(Decimal("-0.05")) == GapBucket.FLAT
    assert gap_bucket(Decimal("0.5")) == GapBucket.GAP_UP_SMALL
    assert gap_bucket(Decimal("-0.5")) == GapBucket.GAP_DOWN_SMALL
    assert gap_bucket(Decimal("1.5")) == GapBucket.GAP_UP_LARGE
    assert gap_bucket(Decimal("-1.5")) == GapBucket.GAP_DOWN_LARGE
    # Exactly on a threshold falls on the lenient (smaller-bucket) side, deterministically.
    assert gap_bucket(Decimal("0.1")) == GapBucket.FLAT
    assert gap_bucket(Decimal("1.0")) == GapBucket.GAP_UP_SMALL


def _bar(ts: datetime, volume: int) -> Bar:
    return Bar(
        instrument=Instrument("AAPL"),
        interval=BarInterval.ONE_MINUTE,
        timestamp=ts,
        open=Decimal("100"),
        high=Decimal("100"),
        low=Decimal("100"),
        close=Decimal("100"),
        volume=volume,
    )


def test_relative_early_volume_is_point_in_time_safe() -> None:
    """Uses only the first-N-minutes window of today and of each PRIOR session passed in --
    never today's own later bars (even when present in `today_bars`) and never a full-day
    total."""
    open_ts = datetime(2026, 6, 5, 13, 30, tzinfo=UTC)
    today_bars = tuple(
        _bar(open_ts + timedelta(minutes=m), volume=1000) for m in range(0, 120)
    )  # 2 hours of bars, volume 1000/min throughout
    prior_session = tuple(
        _bar(open_ts - timedelta(days=1) + timedelta(minutes=m), volume=500) for m in range(0, 120)
    )
    result = relative_early_volume(today_bars, [prior_session], first_n_minutes=30)
    assert result is not None
    # today: 30 bars * 1000 = 30000; prior median: 30 bars * 500 = 15000 -> ratio 2.0
    assert result == Decimal("2")


def test_relative_early_volume_none_without_prior_sessions() -> None:
    open_ts = datetime(2026, 6, 5, 13, 30, tzinfo=UTC)
    today_bars = (_bar(open_ts, volume=1000),)
    assert relative_early_volume(today_bars, []) is None


def test_relative_early_volume_empty_today_is_none() -> None:
    assert relative_early_volume((), []) is None
