"""MILESTONE-093 Phase 1 -- proving the FINAL HOLDOUT lock is an active check, not an
absence of a bug."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from empirical_platform.decision_candidate.m093_holdout_guard import (
    HOLDOUT_END,
    HOLDOUT_START,
    HoldoutLockedError,
    assert_not_holdout,
    is_holdout_date,
)

#: M091 DEVELOPMENT and M092 VALIDATION are now legitimate M093 research data -- the guard
#: must never reject them.
_RESEARCH_DATES = (
    date(2026, 7, 8),  # DEVELOPMENT start
    date(2026, 9, 29),  # DEVELOPMENT end
    date(2026, 5, 13),  # VALIDATION start
    date(2026, 7, 7),  # VALIDATION end
    date(2026, 8, 3),  # DEVELOPMENT interior
)


def test_the_locked_range_is_exactly_the_m092_final_holdout() -> None:
    assert HOLDOUT_START == date(2026, 3, 18)
    assert HOLDOUT_END == date(2026, 5, 12)


@pytest.mark.parametrize(
    "offset_days", list(range(0, (date(2026, 5, 12) - date(2026, 3, 18)).days + 1))
)
def test_every_date_in_the_locked_range_is_rejected(offset_days: int) -> None:
    locked_date = HOLDOUT_START + timedelta(days=offset_days)
    assert is_holdout_date(locked_date)
    with pytest.raises(HoldoutLockedError):
        assert_not_holdout(locked_date)


def test_the_exact_endpoints_are_rejected_inclusive() -> None:
    with pytest.raises(HoldoutLockedError):
        assert_not_holdout(HOLDOUT_START)
    with pytest.raises(HoldoutLockedError):
        assert_not_holdout(HOLDOUT_END)


def test_one_day_before_and_after_the_locked_range_are_not_rejected() -> None:
    assert not is_holdout_date(HOLDOUT_START - timedelta(days=1))
    assert not is_holdout_date(HOLDOUT_END + timedelta(days=1))
    assert_not_holdout(HOLDOUT_START - timedelta(days=1))
    assert_not_holdout(HOLDOUT_END + timedelta(days=1))


@pytest.mark.parametrize("research_date", _RESEARCH_DATES)
def test_development_and_validation_dates_are_never_rejected(research_date: date) -> None:
    assert not is_holdout_date(research_date)
    assert_not_holdout(research_date)  # must not raise
