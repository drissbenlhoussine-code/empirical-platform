# M095 Phase 19 -- Candidate Direction Gate

## Rule (mechanical, `tools/m095_event_study.py::classify`)

A direction qualifies only if ALL of:
1. survives COST1 (predeclared combined event+gap-up mean 30m move >= 0.10% round trip);
2. temporally stable (same sign in both chronological halves of the 100-session window);
3. not cross-symbol concentrated (no single symbol > 60% of the qualifying observations);
4. cross-symbol sign agreement (every symbol with n>=3 observations shares the same sign).

Exactly one predeclared direction was evaluated: `EVENT_KNOWN_BEFORE_OPEN_PLUS_GAP_UP`
(a company-specific news article published before the session open, combined with a
SMALL-or-LARGE opening gap up, per `event-taxonomy.md`'s predeclared definitions).

## Result

| Gate | Outcome |
|---|---|
| Survives COST1 | **FAIL** -- mean 30m move +0.023% vs. 0.10% required |
| Temporally stable | **FAIL** -- first half -0.065%, second half +0.091% (sign flip) |
| Not cross-symbol concentrated | PASS -- largest symbol share (NVDA, 53/258 = 20.5%) well under 60% |
| Cross-symbol sign agreement | **FAIL** -- 4 of 6 symbols negative, 2 (META, MSFT) positive |

**`EVENT_KNOWN_BEFORE_OPEN_PLUS_GAP_UP` is NOT eligible.** 3 of 4 gates fail.

## Leads flagged but NOT selected (per Phase 17's own discipline against post-hoc cutoff
## selection, see `event-study-findings.md`)

- `GAP_UP_LARGE` alone (vs. the combined SMALL+LARGE group actually evaluated) shows a
  materially larger mean move that would clear COST1 on this sample -- not evaluated
  against temporal/cross-symbol stability as its own predeclared direction, since
  isolating it only became visible after looking at the gap-bucket table.
- High relative early volume among event+gap-up observations shows the most separated
  split measured in this milestone (+0.244% vs. -0.197%) -- same caveat: discovered by
  looking at this study's own output, not predeclared before running it.
- Selectivity IC (gap magnitude vs. 30m forward return among event-present gap-ups) is
  +0.1525 -- the largest rank correlation measured across M093-M095's cumulative
  research, consistent with (likely the same underlying effect as) the GAP_UP_LARGE
  asymmetry above.

These three observations are mutually consistent (larger gap, more volume, more move) and
plausibly describe the SAME underlying phenomenon -- but none was predeclared as its own
testable direction before this study ran, so none is "selected" here. They are recorded
as the most concrete, specific direction for a future, PROPERLY PRE-REGISTERED M096/later
study: fix a `GAP_UP_LARGE`-and-high-relative-volume definition BEFORE fetching any new
outcome data, then run the exact same cost/temporal/cross-symbol gate this milestone
already built.

## Decision

**No direction is selected.** `EVENT_KNOWN_BEFORE_OPEN_PLUS_GAP_UP`, the one predeclared
direction this milestone actually tested end-to-end, fails 3 of 4 mechanical gates. Per
Phase 19's own framing, `NO_EVENT_EDGE_FOUND` is an acceptable and informative result,
consistent with M091 (`NO_EDGE_FOUND`), M092 (`NO_EDGE_V2`), M093 (`NO_CANDIDATE_EDGE`),
and M094 (`NO_PROMISING_EDGE_SOURCE`).

**Classification: `NO_EVENT_EDGE_FOUND`.**

Phase 20 is moot (no direction qualified, so no final-strategy build is at risk here
regardless). The locked FINAL HOLDOUT (2026-03-18 through 2026-05-12) was never touched at
any point in M095 -- see `holdout-confirmation.md`.
