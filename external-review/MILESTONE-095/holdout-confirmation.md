# M095 Phase 3/18 -- Locked Final Holdout Confirmation

Per Phase 3/18 (both verbatim Owner instructions): the M092 FINAL HOLDOUT (2026-03-18
through 2026-05-12, inclusive) must remain untouched through all of M095 -- data-source
research, the event adapter, the event+gap study, every phase of analysis, and candidate
selection. M095 ends with research directions only; the holdout stays reserved for a
future milestone after a candidate is frozen.

## What was actually fetched in M095

- **Bars**: the SAME 100-session research dataset (2026-05-13 through 2026-09-29) M093/
  M094 already used, for all 8 symbols, via `tools.m095_event_study.fetch_all_bars` ->
  `_fetch_bars` -> `m093_research_framework.fetch_session_bars_guarded` (the SAME
  single, already-proven guarded entry point M093/M094 used -- not a new one).
- **News**: the SAME 100-session window, for the 6 ranked symbols, via
  `tools.m095_event_study.fetch_all_events` -> `m095_event_research.
  fetch_symbol_news_guarded` -- a NEW guarded entry point, added in M095, that calls
  `m093_holdout_guard.assert_not_holdout` for EVERY calendar date in the requested
  window (not just the two endpoints) before making any network call.

At no point in M095 was any date outside the 100-session research dataset requested, for
either bars or news.

## How this is enforced, not just asserted

1. **The bars guard is unchanged and reused verbatim** -- `fetch_session_bars_guarded`
   is imported from `m093_research_framework`, never redefined or duplicated.
2. **The news guard is a new, independent entry point with its own proof.**
   `tests/unit/test_m095_event_research.py` parametrizes over 4 windows including the
   exact locked boundary dates and windows that merely STRADDLE the locked range without
   either endpoint sitting inside it, asserting `HoldoutLockedError` in every case, via a
   stub news port that raises `AssertionError` if its `fetch_news` is ever reached --
   proving the guard fires BEFORE any network call, not merely that the result happens
   to look right. A negative control (`test_news_fetch_does_not_refuse_a_real_research_
   window`) proves the guard discriminates rather than refusing everything.
3. **Static AST proof that the tool's own fetch functions call nothing but the guarded
   entry points** -- `tests/unit/test_m095_event_study.py::
   test_fetch_all_bars_reaches_the_broker_only_through_the_guarded_fetch` and
   `test_fetch_all_events_reaches_the_broker_only_through_the_guarded_fetch` walk the
   AST of `fetch_all_bars`/`fetch_all_events` and assert they call exclusively
   `_fetch_bars`/`research.fetch_symbol_news_guarded`, never `fetch_minute_bars` or
   `news_port.fetch_news` directly.
4. **Static AST proof that no literal date construction in the tool's source falls
   inside the locked range** -- `test_no_date_construction_call_in_this_tool_falls_
   inside_the_locked_holdout` walks every `date(...)`/`date.fromisoformat(...)` call in
   `tools/m095_event_study.py`'s own source (there are none that construct a literal
   date at all -- the tool imports `research_session_dates()` from M093 rather than
   recomputing a range) and would catch one if a future edit added it.
5. **Research-date source is reused verbatim, never recomputed** --
   `test_research_session_dates_is_imported_verbatim_from_m093_not_redefined` proves
   `tools.m095_event_study`'s `research_session_dates` IS (object identity) `tools.
   m093_family_screening`'s own function, not a second, possibly-drifted definition.
6. **Manual verification during this run.** Every one of the 800 bar fetches and 6
   paginated news-fetch sequences performed while producing
   `event-study-results.json` went through a guarded entry point; none raised
   `HoldoutLockedError` because none of the 100 research dates falls in the locked
   range (already proven disjoint by M093's own `test_m093_research_data.py`, reused
   unchanged here).

## Conclusion

The locked FINAL HOLDOUT (2026-03-18 through 2026-05-12) was never fetched, inspected, or
otherwise used at any point during M095, for either bars or news, by construction (both
fetch paths are guarded, and the news guard is independently proven) and by test. M095
ends with `NO_EVENT_EDGE_FOUND` (`candidate-selection.md`); the holdout remains reserved,
untouched, for a future milestone after a credible candidate is frozen.
