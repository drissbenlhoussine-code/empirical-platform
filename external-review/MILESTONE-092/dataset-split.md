# MILESTONE-092 — Predeclared Dataset Split (written before any V2 candidate is evaluated)

Three non-overlapping historical blocks, same fixed 8-symbol universe throughout: AAPL,
AMZN, GOOGL, META, MSFT, NVDA, QQQ, SPY. Weekday sessions only (a calendar approximation;
an actual market holiday yields zero bars for that date and is excluded honestly, exactly
as M091 did for 2026-09-07).

Since DEVELOPMENT already covers the most recent 60 completed sessions up to 2026-09-29 and
no future data exists, VALIDATION and FINAL HOLDOUT are both drawn from the historical period
*before* DEVELOPMENT begins — going further back in time, in two non-overlapping 40-session
blocks, VALIDATION being the block immediately adjacent to (and preceding) DEVELOPMENT, and
FINAL HOLDOUT the block immediately preceding VALIDATION. This keeps VALIDATION temporally
closest to DEVELOPMENT (most similar market regime) while FINAL HOLDOUT is a genuinely older,
never-inspected-during-selection period — the stricter test.

Computed via `tools/m090_replay.py`'s own `recent_completed_session_dates(count, before)`
helper (`count` weekdays strictly before `before`, oldest first), unmodified.

## DEVELOPMENT (diagnostic/research only — used throughout Phases 1, 6-13)

Copied verbatim from `external-review/MILESTONE-091/results.json`'s own `session_dates`
field — never recomputed, to guarantee zero drift from the exact 60 dates M091 already used.

- **60 sessions:** 2026-07-08 → 2026-09-29 (inclusive)

## VALIDATION (Phase 14 — not inspected before the Phase 13 freeze)

`recent_completed_session_dates(40, before=date(2026, 7, 8))`

- **40 sessions:** 2026-05-13 → 2026-07-07 (inclusive)

## FINAL HOLDOUT (Phase 15 — not inspected before the Phase 13 freeze, and only run at all
if VALIDATION shows credible improvement)

`recent_completed_session_dates(40, before=date(2026, 5, 13))`

- **40 sessions:** 2026-03-18 → 2026-05-12 (inclusive)

## Overlap verification

Programmatically verified zero date overlap among all three sets (`dev & validation`,
`dev & holdout`, `validation & holdout` are all the empty set) — see
`tests/unit/test_m092_dataset_split.py::test_the_three_blocks_never_overlap`, which asserts
this against the exact frozen date lists in `tools/m092_validation.py`.

## What was NOT done during this split

No bars were fetched for VALIDATION or FINAL HOLDOUT at the time this document was written.
No candidate was evaluated against either block. Only the calendar-date computation above
was performed, which requires no market data at all.
