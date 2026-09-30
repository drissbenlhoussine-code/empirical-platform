"""MILESTONE-093 Phase 2 -- the combined 100-session research dataset (M091 DEVELOPMENT UNION
M092 VALIDATION) proven to have zero overlap with the locked FINAL HOLDOUT range, matching
`external-review/MILESTONE-093/research-data.md`."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from empirical_platform.decision_candidate.m093_holdout_guard import (
    HOLDOUT_END,
    HOLDOUT_START,
    HoldoutLockedError,
    assert_not_holdout,
)

_RESULTS_091 = Path("external-review/MILESTONE-091/results.json")

# Reproduced from `tools.m090_replay.recent_completed_session_dates(40, before=date(2026, 7, 8))`
# -- the exact 40-session VALIDATION block M092 itself computed and documented in
# `external-review/MILESTONE-092/dataset-split.md`.
_VALIDATION_START = date(2026, 5, 13)
_VALIDATION_END = date(2026, 7, 7)
_VALIDATION_SESSION_COUNT = 40


def _development_dates() -> tuple[date, ...]:
    payload = json.loads(_RESULTS_091.read_text(encoding="utf-8"))
    return tuple(date.fromisoformat(d) for d in payload["session_dates"])


def _validation_dates() -> tuple[date, ...]:
    from tools.m090_replay import recent_completed_session_dates

    return recent_completed_session_dates(_VALIDATION_SESSION_COUNT, before=date(2026, 7, 8))


def test_development_block_is_exactly_the_m091_60_sessions() -> None:
    development = _development_dates()
    assert len(development) == 60
    assert development[0] == date(2026, 7, 8)
    assert development[-1] == date(2026, 9, 29)


def test_validation_block_is_exactly_the_m092_40_sessions() -> None:
    validation = _validation_dates()
    assert len(validation) == _VALIDATION_SESSION_COUNT
    assert validation[0] == _VALIDATION_START
    assert validation[-1] == _VALIDATION_END


def test_development_and_validation_blocks_do_not_overlap() -> None:
    development = set(_development_dates())
    validation = set(_validation_dates())
    assert development.isdisjoint(validation)


def test_combined_research_dataset_is_exactly_100_sessions() -> None:
    combined = set(_development_dates()) | set(_validation_dates())
    assert len(combined) == 100


def test_no_research_date_falls_inside_the_locked_holdout_range() -> None:
    """The Phase 2 zero-overlap proof: every one of the 100 combined research dates must be
    accepted by `assert_not_holdout` -- none may fall inside the locked
    [2026-03-18, 2026-05-12] FINAL HOLDOUT range."""
    combined = sorted(set(_development_dates()) | set(_validation_dates()))
    for session_date in combined:
        assert_not_holdout(session_date)  # must not raise for any research date


def test_the_research_dataset_is_adjacent_to_not_overlapping_the_holdout_boundary() -> None:
    combined = sorted(set(_development_dates()) | set(_validation_dates()))
    earliest_research_date = combined[0]
    assert earliest_research_date > HOLDOUT_END
    assert HOLDOUT_START < HOLDOUT_END < earliest_research_date


@pytest.mark.parametrize(
    "held_out_date",
    [HOLDOUT_START, date(2026, 4, 1), HOLDOUT_END],
)
def test_holdout_dates_themselves_are_never_part_of_the_research_dataset(
    held_out_date: date,
) -> None:
    combined = set(_development_dates()) | set(_validation_dates())
    assert held_out_date not in combined
    with pytest.raises(HoldoutLockedError):
        assert_not_holdout(held_out_date)
