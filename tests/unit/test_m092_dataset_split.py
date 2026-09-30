"""MILESTONE-092 Phase 3 -- the three predeclared dataset blocks never overlap.

Reproduces `external-review/MILESTONE-092/dataset-split.md`'s own computation exactly: if
this test ever fails, that document is stale and must be regenerated, not silently ignored.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEVELOPMENT_SOURCE = REPO_ROOT / "external-review" / "MILESTONE-091" / "results.json"


def _recent_completed_session_dates(count: int, *, before: date) -> tuple[date, ...]:
    """Identical to `tools/m090_replay.py`'s own helper -- duplicated here (not imported)
    so this test has no import-time dependency on a tools/ script."""
    found: list[date] = []
    cursor = before - timedelta(days=1)
    while len(found) < count:
        if cursor.weekday() < 5:
            found.append(cursor)
        cursor -= timedelta(days=1)
    return tuple(reversed(found))


def test_the_three_blocks_never_overlap() -> None:
    with open(DEVELOPMENT_SOURCE, encoding="utf-8") as fh:
        m091_results = json.load(fh)
    development = frozenset(date.fromisoformat(d) for d in m091_results["session_dates"])
    assert len(development) == 60

    validation = frozenset(_recent_completed_session_dates(40, before=min(development)))
    holdout = frozenset(_recent_completed_session_dates(40, before=min(validation)))

    assert len(validation) == 40
    assert len(holdout) == 40
    assert development & validation == frozenset()
    assert development & holdout == frozenset()
    assert validation & holdout == frozenset()

    # Matches external-review/MILESTONE-092/dataset-split.md exactly.
    assert min(validation) == date(2026, 5, 13)
    assert max(validation) == date(2026, 7, 7)
    assert min(holdout) == date(2026, 3, 18)
    assert max(holdout) == date(2026, 5, 12)


def test_validation_is_strictly_before_development() -> None:
    with open(DEVELOPMENT_SOURCE, encoding="utf-8") as fh:
        m091_results = json.load(fh)
    development = frozenset(date.fromisoformat(d) for d in m091_results["session_dates"])
    validation = frozenset(_recent_completed_session_dates(40, before=min(development)))
    assert max(validation) < min(development)


def test_holdout_is_strictly_before_validation() -> None:
    with open(DEVELOPMENT_SOURCE, encoding="utf-8") as fh:
        m091_results = json.load(fh)
    development = frozenset(date.fromisoformat(d) for d in m091_results["session_dates"])
    validation = frozenset(_recent_completed_session_dates(40, before=min(development)))
    holdout = frozenset(_recent_completed_session_dates(40, before=min(validation)))
    assert max(holdout) < min(validation)
