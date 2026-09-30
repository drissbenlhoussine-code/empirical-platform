# MILESTONE-093 -- research/discovery dataset (Phase 2)

## What this is

M091's DEVELOPMENT block (60 sessions) UNION M092's VALIDATION block (40 sessions) = **100
non-overlapping sessions**, now legitimate research/discovery data for M093's family screening.
Both blocks were already fully evaluated against V1/V2's respective policies in their own
milestones (M091 classified `NO_EDGE_FOUND` on DEVELOPMENT; M092 classified `NO_EDGE_V2` on
VALIDATION), so re-using them for a genuinely different set of strategy families is not
cherry-picking or re-litigating already-spent evidence -- it is the same 8-symbol universe,
same historical window, being asked a different question by different signal logic.

Same fixed 8-symbol universe throughout, no cherry-picking:
`AAPL, AMZN, GOOGL, META, MSFT, NVDA, QQQ, SPY` (identical to M090/M091/M092).

## DEVELOPMENT block (M091's own, copied verbatim)

Source: `external-review/MILESTONE-091/results.json`'s own `session_dates` field (the exact
list M091 fetched and classified against, not a re-derivation).

- **60 sessions:** 2026-07-08 through 2026-09-29 (inclusive)

## VALIDATION block (M092's own)

Source: `tools/m090_replay.recent_completed_session_dates(40, before=date(2026, 7, 8))` --
identical computation to the one `external-review/MILESTONE-092/dataset-split.md` itself
documents producing VALIDATION.

- **40 sessions:** 2026-05-13 through 2026-07-07 (inclusive)

## Combined research dataset (100 sessions, sorted, deduplicated)

```json
["2026-05-13", "2026-05-14", "2026-05-15", "2026-05-18", "2026-05-19", "2026-05-20", "2026-05-21", "2026-05-22", "2026-05-25", "2026-05-26", "2026-05-27", "2026-05-28", "2026-05-29", "2026-06-01", "2026-06-02", "2026-06-03", "2026-06-04", "2026-06-05", "2026-06-08", "2026-06-09", "2026-06-10", "2026-06-11", "2026-06-12", "2026-06-15", "2026-06-16", "2026-06-17", "2026-06-18", "2026-06-19", "2026-06-22", "2026-06-23", "2026-06-24", "2026-06-25", "2026-06-26", "2026-06-29", "2026-06-30", "2026-07-01", "2026-07-02", "2026-07-03", "2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10", "2026-07-13", "2026-07-14", "2026-07-15", "2026-07-16", "2026-07-17", "2026-07-20", "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-27", "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04", "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11", "2026-09-14", "2026-09-15", "2026-09-16", "2026-09-17", "2026-09-18", "2026-09-21", "2026-09-22", "2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29"]
```

- **100 sessions total**, `2026-05-13` through `2026-09-29` (inclusive).
- `len(set(DEVELOPMENT) | set(VALIDATION)) == len(DEVELOPMENT) + len(VALIDATION) == 100` --
  proven by construction (both blocks were computed from disjoint, non-overlapping calendar
  windows by `recent_completed_session_dates`) and re-verified by
  `tests/unit/test_m093_research_data.py`.

## Locked FINAL HOLDOUT boundary (never fetched in M093)

The combined research dataset's earliest date, `2026-05-13`, is exactly one weekday after the
locked FINAL HOLDOUT range's last date, `2026-05-12` -- the two ranges are adjacent, not
overlapping. **Zero dates in the combined 100-session research dataset fall inside
`[2026-03-18, 2026-05-12]`** (M092's own FINAL HOLDOUT, still locked per
`src/empirical_platform/decision_candidate/m093_holdout_guard.py`), proven by
`tests/unit/test_m093_research_data.py::test_no_research_date_falls_inside_the_locked_holdout_range`,
which calls `assert_not_holdout` against every one of the 100 dates above and asserts none
raise.
