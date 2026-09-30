# M093 Phase 19 -- Locked Final Holdout Confirmation

Per Phase 1 and Phase 19 (both verbatim Owner instructions): the M092 FINAL HOLDOUT
(2026-03-18 through 2026-05-12, inclusive) was never evaluated by M092 and must remain
untouched through all of M093 -- discovery, screening, revision, regime analysis,
cross-symbol/walk-forward robustness checks, candidate selection, and any freeze. M093
ends with a frozen candidate or `NO_CANDIDATE_EDGE`; the holdout itself is reserved for a
separate future M094 mission.

## What was actually run in Phases 11-19

- Phase 11 screening (`tools/m093_family_screening.py --phase screen`, and its
  equivalent scratchpad run that produced the committed
  `external-review/MILESTONE-093/screening-results.json`): fetched only the 100-session
  research dataset (2026-05-13 through 2026-09-29) for all 8 symbols.
- Phase 13 revisions (`--phase revise`): same 100-session dataset, restricted to
  MEAN_REVERSION and VWAP_PULLBACK only.
- Phases 14-16 robustness analysis (`--phase robustness`): pure re-aggregation of the
  Phase 11 decisions already fetched -- no new fetch calls at all.

At no point in Phases 11-19 was any date outside the 100-session research dataset
requested.

## How this is enforced, not just asserted

1. **The single fetch point.** Every bar fetch in M093 -- Phase 0-10's family modules,
   and this fork's own `tools/m093_family_screening.py` -- goes exclusively through
   `m093_research_framework.fetch_session_bars_guarded`, which calls
   `m093_holdout_guard.assert_not_holdout(session_date)` as its literal first action,
   before any network call (`m093_research_framework.py:84`). There is no second fetch
   path anywhere in the M093 code this fork added.

2. **The guard itself is proven to actively reject the locked range** --
   `tests/unit/test_m093_holdout_guard.py` (Phase 0-10, already in place) parametrizes
   over every single day in `[2026-03-18, 2026-05-12]` and asserts `HoldoutLockedError`
   is raised for each one, plus the exact boundary dates and the research dates that must
   NOT be rejected.

3. **The research dataset itself is proven to have zero overlap with the locked range**
   -- `tests/unit/test_m093_research_data.py` (Phase 0-10, already in place) proves the
   combined 100-session set is disjoint from, and chronologically after,
   `[2026-03-18, 2026-05-12]`.

4. **This fork's own screening tool is proven to draw from exactly that dataset, and to
   fetch exclusively through the guarded entry point** --
   `tests/unit/test_m093_family_screening.py` (new in this fork):
   - `test_research_session_dates_is_exactly_100_sessions` / `..._never_falls_inside_the_
     locked_holdout` / `..._matches_the_already_proven_safe_dataset`: the tool's own
     `research_session_dates()` returns exactly the already-proven-safe 100 dates, not a
     coincidentally-overlapping different set.
   - `test_the_only_fetch_call_in_this_tool_goes_through_the_guarded_entry_point`: an
     AST-based static check (not a text grep) proving the tool's one network-touching
     function, `_fetch`, calls nothing except `fw.fetch_session_bars_guarded`.
   - `test_no_date_construction_call_produces_a_holdout_date_anywhere_in_the_tool_source`:
     an AST-based static check walking every literal `date(y, m, d)` /
     `date.fromisoformat(...)` construction anywhere in the tool's source and asserting
     none of them falls inside the locked range.

5. **Manual verification during this fork's own work.** Every fetch performed while
   producing the Phase 11 screening results (800 symbol/session pairs, 785 non-empty)
   went through `fetch_session_bars_guarded`; the guard was exercised, not bypassed, on
   every one of those calls, and none raised `HoldoutLockedError` because none of the 100
   research dates falls in the locked range (proven by item 3 above).

## Conclusion

The locked FINAL HOLDOUT (2026-03-18 through 2026-05-12) was never fetched, inspected, or
otherwise used at any point during M093 Phases 0-19, by construction (the only fetch path
is guarded) and by test (both the guard and the dataset and this fork's own tool are
independently proven). M093 ends at Phase 19 with a `NO_CANDIDATE_EDGE` classification
(`candidate-selection.md`) and therefore Phase 18's freeze does not apply; the holdout
remains reserved, untouched, for a future M094 mission regardless of this milestone's own
classification.
