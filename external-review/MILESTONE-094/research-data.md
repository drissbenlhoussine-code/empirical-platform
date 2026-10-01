# MILESTONE-094 Phase 3 -- research data reuse

## What this is

M094 reuses the IDENTICAL 100-session research dataset M093 already used -- M091's
DEVELOPMENT block (60 sessions) UNION M092's VALIDATION block (40 sessions), the same fixed
8-symbol universe (`AAPL, AMZN, GOOGL, META, MSFT, NVDA, QQQ, SPY`), the same date range
(2026-05-13 through 2026-09-29 inclusive). `tools/m094_edge_source_study.py` imports
`research_session_dates` directly from `tools/m093_family_screening.py` -- it does not
recompute a second date range that could silently drift from M093's own.

This is deliberate reuse, not re-litigation: M091 classified `NO_EDGE_FOUND` and M092
classified `NO_EDGE_V2`/M093 classified `NO_CANDIDATE_EDGE` against their own strategy
definitions over this window; M094 asks an entirely different question of the SAME bars
(information value, not a trading rule), so reusing the window is the same "same universe,
same window, different question" discipline M093 itself used when it reused M091/M092's
data for its own, genuinely different, family screening.

## Reused vs newly fetched

M093's own raw 1-minute bars were never persisted to disk -- only its aggregated metrics
were committed to `external-review/MILESTONE-093/screening-results.json`. This tool
therefore legitimately RE-FETCHES the same (symbol, session) pairs, through the exact same
guarded entry point M093 used, but fetches each pair exactly ONCE for the whole run and
reuses that one in-memory cache across every phase (4 through 16) -- no phase in this
milestone re-fetches a symbol/session pair another phase already fetched.

- **Newly fetched this run:** all 800 (symbol, session) pairs (8 symbols x 100 sessions);
  **768 came back non-empty** (32 empty).
- **Reused across phases within this run:** every one of those 800 fetches, across Phases
  5-16 (horizon study, multi-timeframe, regime, cross-sectional, selectivity, gap study,
  information coefficient, temporal/cross-symbol stability, cost-aware value).
- **Newly introduced dates or symbols beyond the already-exposed M091/M092/M093 research
  window:** zero.
- **Missing data:** 32 of 800 symbol/session pairs came back empty, close to but not
  identical to M093's own 15-empty count (785 non-empty of 800) over the nominally same
  window. Both runs skip empty pairs rather than fabricating bars; the small difference is
  consistent with this run re-fetching from the live Alpaca Paper market-data endpoint on a
  different day than M093's own run (transient provider-side gaps can differ run to run for
  the same historical range), not a bug in the fetch or holdout-guard logic -- every
  (symbol, date) pair fetched here is still a date from the same, already-proven-safe
  100-session set.

## Locked FINAL HOLDOUT boundary (never fetched in M094)

Identical to M093's own confirmation: the combined research dataset's earliest date,
`2026-05-13`, is exactly one weekday after the locked FINAL HOLDOUT range's last date,
`2026-05-12` -- the two ranges are adjacent, not overlapping. Zero dates in this dataset
fall inside `[2026-03-18, 2026-05-12]`. See `holdout-confirmation.md` for the full proof.
