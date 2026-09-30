"""MILESTONE-093 Phase 1 -- the machine-enforced FINAL HOLDOUT lock.

The M092 FINAL HOLDOUT (2026-03-18 through 2026-05-12 inclusive) was never fetched or
evaluated by M092 and must stay that way through the whole of M093 -- discovery, candidate
selection, tuning, comparison, debugging, and walk-forward checks. A future, SEPARATE M094
milestone performs the one-shot final holdout validation.

THIS IS AN ACTIVE CHECK, NOT AN ABSENCE OF A BUG. Every M093 data-fetching entry point calls
`assert_not_holdout` before fetching a single bar. A date inside the locked range causes an
immediate, loud `HoldoutLockedError` -- never a silent skip, never a quiet omission.
"""

from __future__ import annotations

from datetime import date

__all__ = [
    "HOLDOUT_END",
    "HOLDOUT_START",
    "HoldoutLockedError",
    "assert_not_holdout",
    "is_holdout_date",
]

#: The M092 FINAL HOLDOUT block, inclusive on both ends. Copied verbatim from
#: `external-review/MILESTONE-092/dataset-split.md` -- never recomputed, to guarantee zero
#: drift from the exact dates M092 itself froze.
HOLDOUT_START = date(2026, 3, 18)
HOLDOUT_END = date(2026, 5, 12)


class HoldoutLockedError(ValueError):
    """Raised when any M093 code path requests a date inside the locked FINAL HOLDOUT
    block. This is a hard stop, not a warning -- the caller must use a different date."""


def is_holdout_date(session_date: date) -> bool:
    """True if `session_date` falls inside the locked FINAL HOLDOUT block (inclusive)."""
    return HOLDOUT_START <= session_date <= HOLDOUT_END


def assert_not_holdout(session_date: date) -> None:
    """Raise `HoldoutLockedError` if `session_date` is inside the locked FINAL HOLDOUT
    block. Every M093 bar-fetching entry point must call this BEFORE fetching anything."""
    if is_holdout_date(session_date):
        raise HoldoutLockedError(
            f"{session_date.isoformat()} is inside the locked M092 FINAL HOLDOUT block "
            f"({HOLDOUT_START.isoformat()} through {HOLDOUT_END.isoformat()}, inclusive). "
            "M093 discovery, candidate selection, tuning, comparison, debugging, and "
            "walk-forward checks must never fetch or evaluate this range. It is reserved "
            "for a future, separate M094 one-shot final holdout validation."
        )
