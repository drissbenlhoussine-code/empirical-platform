"""Audit A P1-2 -- an entry is refused when the mandatory exit cannot start before the close.

The rule: refuse unless  (liquidation - 120s)  <  (next_close - 300s)  strictly; a missing or
naive close refuses. On a 13:00 ET early-close day with the configured 15:45 liquidation
EVERY entry is refused for that day (the exit deadline lies after the close whatever the entry
time). Allowing entries on such days needs the Owner to move the configured liquidation time
earlier (before 12:53 ET). That is an Owner decision and is NOT made here.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from empirical_platform.decision_candidate.approved_plan import (
    MANDATORY_EXIT_SAFETY_BUFFER_SECONDS,
)
from empirical_platform.decision_candidate.session_close_guard import (
    SESSION_CLOSE_ENTRY_BUFFER_SECONDS,
    session_close_before_liquidation_refusal,
)

_NY = ZoneInfo("America/New_York")


def _ny(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=_NY)


def _refusal(liquidation: datetime, close: datetime | None) -> str | None:
    return session_close_before_liquidation_refusal(
        mandatory_liquidation_at=liquidation,
        market_next_close=close,
        operator_timezone="America/New_York",
    )


def test_the_constants_are_the_documented_ones() -> None:
    assert MANDATORY_EXIT_SAFETY_BUFFER_SECONDS == 120
    assert SESSION_CLOSE_ENTRY_BUFFER_SECONDS == 300


@pytest.mark.parametrize("entry_label", ["10:05", "12:30", "14:00", "15:30"])
def test_a_regular_day_is_allowed_for_every_entry_time(entry_label: str) -> None:
    # The rule does not depend on the entry time: only on liquidation versus the close.
    del entry_label
    assert _refusal(_ny(2026, 9, 10, 15, 45), _ny(2026, 9, 10, 16, 0)) is None


@pytest.mark.parametrize("entry_label", ["10:05", "12:30", "14:00", "15:30"])
@pytest.mark.parametrize("day", [(2026, 11, 27), (2026, 12, 24)])
def test_every_entry_on_an_early_close_day_is_refused_with_the_configured_liquidation(
    entry_label: str, day: tuple[int, int, int]
) -> None:
    del entry_label
    refusal = _refusal(_ny(*day, 15, 45), _ny(*day, 13, 0))
    assert refusal == (
        "the market closes at 13:00 ET, before the mandatory liquidation time 15:45 ET; "
        "no entry today"
    )


def test_a_missing_or_naive_close_fails_closed() -> None:
    assert "unknown" in (_refusal(_ny(2026, 9, 10, 15, 45), None) or "")
    naive = datetime(2026, 9, 10, 16, 0)
    assert "unknown" in (_refusal(_ny(2026, 9, 10, 15, 45), naive) or "")


def test_the_boundary_is_strict() -> None:
    close = _ny(2026, 11, 27, 13, 0)
    # deadline = liquidation - 120s must be strictly before close - 300s (12:55:00).
    assert _refusal(_ny(2026, 11, 27, 12, 56, 59), close) is None  # deadline 12:54:59
    assert _refusal(_ny(2026, 11, 27, 12, 57, 0), close) is not None  # deadline == 12:55:00
    assert _refusal(_ny(2026, 11, 27, 12, 57, 1), close) is not None  # deadline 12:55:01


def test_an_owner_liquidation_time_moved_earlier_allows_an_early_close_day() -> None:
    assert _refusal(_ny(2026, 11, 27, 12, 45), _ny(2026, 11, 27, 13, 0)) is None


def test_the_close_already_before_the_exit_deadline_refuses() -> None:
    assert _refusal(_ny(2026, 9, 10, 15, 45), _ny(2026, 9, 10, 15, 0)) is not None


@pytest.mark.parametrize(
    ("day", "close_utc_hour"),
    [((2026, 10, 30), 20), ((2026, 11, 2), 21), ((2026, 3, 6), 21), ((2026, 3, 9), 20)],
)
def test_daylight_saving_does_not_shift_the_rule(
    day: tuple[int, int, int], close_utc_hour: int
) -> None:
    # 16:00 ET is 20:00 UTC in EDT and 21:00 UTC in EST; the local-time rule is unchanged.
    close = datetime(*day, close_utc_hour, 0, tzinfo=UTC)
    assert _refusal(_ny(*day, 15, 45), close) is None
    early = close - timedelta(hours=3)
    refusal = _refusal(_ny(*day, 15, 45), early)
    assert refusal is not None and "closes at 13:00 ET" in refusal
