# MILESTONE-094 Phase 1/18 -- Locked Final Holdout Confirmation

Per Phase 1 and Phase 18 (both verbatim Owner instructions): the M092 FINAL HOLDOUT
(2026-03-18 through 2026-05-12, inclusive) must remain untouched through all of M094 --
discovery, screening, horizon/regime/cross-sectional/selectivity/gap studies, temporal and
cross-symbol stability checks, the scorecard, and the decision gate. M094 is research-
direction discovery only; the holdout remains reserved for a future, separate milestone
that performs a one-shot final holdout validation of a frozen strategy candidate.

## Carry-forward, not reinvention (Phase 1)

M094 does not define a second holdout guard. `tools/m094_edge_source_study.py`'s single
fetch wrapper, `_fetch`, calls `fw.fetch_session_bars_guarded` -- the SAME function M093
itself used, which calls `m093_holdout_guard.assert_not_holdout` before any network call.
This is the literal same guard, same constants (`HOLDOUT_START = 2026-03-18`,
`HOLDOUT_END = 2026-05-12`), unmodified.

## What was actually run

- `fetch_research_bars` (Phase 3): fetched only the 100-session research dataset
  (2026-05-13 through 2026-09-29) for all 8 symbols, via `_fetch` exclusively.
- Phases 4-16: pure re-computation over that one in-memory cache -- zero additional fetch
  calls at any phase.

At no point did M094 request any date outside the 100-session research dataset.

## How this is enforced, not just asserted

1. **The single fetch point.** `tests/unit/test_m094_edge_source_study.py::
   test_the_only_fetch_call_in_this_tool_goes_through_the_guarded_entry_point` is an
   AST-based static proof that `_fetch` -- the only function in this tool that touches
   network I/O -- calls exclusively `fw.fetch_session_bars_guarded`, never any other path.
   `test_fetch_research_bars_reaches_the_broker_only_through_fetch` proves the loop that
   fetches the whole dataset also goes exclusively through `_fetch`.

2. **The guard actively rejects the locked range at M094's own call site.**
   `test_fetch_refuses_before_any_network_access_for_holdout_dates` calls `_fetch` with a
   stub broker port whose `fetch_minute_bars` raises `AssertionError` if ever reached, for
   every boundary date and two interior dates of the locked range, and asserts
   `HoldoutLockedError` is raised instead -- proving the guard fires BEFORE the network
   call, not merely that the network call happens to fail for an unrelated reason.
   `test_fetch_does_not_refuse_a_research_dataset_date` is the negative control: the same
   stub, called with a real research date, DOES reach the stub (and raises the stub's own
   assertion) -- proving the guard discriminates rather than refusing everything.

3. **The research dataset itself is proven to have zero overlap with the locked range** --
   reused directly from M093's own already-proven-safe `research_session_dates()`
   (`test_research_session_dates_is_imported_verbatim_from_m093_not_redefined` proves this
   tool imports the identical function object, not a coincidentally-matching redefinition).

4. **No literal date construction in this tool's own source falls in the locked range** --
   `test_no_date_construction_call_in_this_tool_falls_inside_the_locked_holdout` is an
   AST-based static check walking every literal `date(y, m, d)` / `date.fromisoformat(...)`
   construction anywhere in `tools/m094_edge_source_study.py` (there are none; the tool
   imports the dataset rather than constructing dates itself, and this test will catch it
   if that ever changes).

## Conclusion

The locked FINAL HOLDOUT (2026-03-18 through 2026-05-12) was never fetched, inspected, or
otherwise used at any point during M094, by construction (the only fetch path is guarded,
carried forward unmodified from M093) and by test (both the guard and the dataset and this
milestone's own tool are independently proven). It remains reserved, untouched, for a
future milestone regardless of this milestone's own classification.
