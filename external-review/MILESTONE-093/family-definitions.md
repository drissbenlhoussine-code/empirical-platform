# MILESTONE-093 -- canonical family definitions (Phase 10)

This document is committed BEFORE any screening or performance comparison exists against the
Phase 2 research dataset -- no such comparison code exists in this repository as of this
commit (verifiable by `git log` on this branch: every commit up to and including this one is a
family's own domain module, its own tests, the holdout guard, the Phase 3 common framework, or
this document itself; the Phase 11 screening/comparison run is explicitly out of scope for this
stage of the mission and has not been started). Per Phase 10's own instruction, these
definitions must not be altered after seeing results without a new, explicit research
iteration (the limited 2-revision allowance is a later phase's concern, not this document's).

All five families share ONE deterministic execution substrate --
`src/empirical_platform/usecases/m093_research_framework.py` (Phase 3): the same
holdout-guarded bar fetch, the same look-ahead discipline (`ObservationWindow` /
`bars[:index+1]`-only reads), the same position-sizing formula, the same three cost models
(`COST_MODEL_0`/`_1`/`_2`, byte-identical to M091/M092's own percentages), the same
stop-first same-bar ambiguity rule, and the same metrics/concentration computation. **The only
thing that differs between families below is their own entry / stop / target / regime logic.**

Long-only throughout, matching every prior milestone's own scope. Fixed 8-symbol universe:
`AAPL, AMZN, GOOGL, META, MSFT, NVDA, QQQ, SPY` (Family E excludes SPY and QQQ from its own
comparisons -- see below).

---

## Family A -- Trend Continuation

Module: `src/empirical_platform/decision_candidate/opportunity_family_trend_continuation.py`
Structure model id: `ESTABLISH_PULLBACK_RESUMPTION_HIGHER_LOW_V1`

**Why this differs from V1/V2's breakout:** V1/V2 require only a close above an N-bar range
high with no prior trend context. Family A requires an established uptrend to exist FIRST,
then a pullback that preserves that trend's own structure, then a resumption -- never a bare
range breakout.

- **Required evidence:** `policy.lookback_bars` reference bars (strictly before the decision
  bar), split into an ESTABLISH phase (the first `lookback_bars - pullback_bars` bars) and a
  PULLBACK phase (the last `pullback_bars` bars).
- **Entry condition:** (1) the establish phase's second half makes a higher high than its
  first half (`establish_second_half_high > establish_first_half_high`); (2) the pullback
  phase's own low does not violate the establish phase's own low
  (`pullback_low >= establish_low`); (3) the evaluation bar's close reclaims ABOVE the
  pullback phase's own high (`current.close > pullback_high`) -- deliberately the pullback's
  local high, not the establish phase's overall high; (4) evaluation-bar volume reaches at
  least `minimum_volume_ratio` times the establish phase's own average volume; (5) evaluation-
  bar volume meets `minimum_liquidity_shares`.
- **Stop method:** the pullback phase's own low (structural -- its violation disproves the
  continuation thesis).
- **Target method:** `entry + target_range_multiple * reference_average_range`, floored at
  `entry + minimum_reward_risk_ratio * risk_per_share`.
- **Invalidation / rejection reasons:** `INSUFFICIENT_REFERENCE_BARS`,
  `INSUFFICIENT_LIQUIDITY`, `NO_ESTABLISHED_TREND`, `PULLBACK_BROKE_STRUCTURE`,
  `NO_RESUMPTION_TRIGGER`, `WEAK_RESUMPTION_VOLUME`.
- **Entry window / minimum evidence:** any evaluation bar with at least `lookback_bars`
  reference bars available before it within the session.
- **Position sizing:** the shared framework's `position_size` (Phase 3), unchanged.
- **Mandatory exit:** the shared framework's mandatory-liquidation doctrine (Phase 3),
  unchanged -- identical liquidation instant convention to V1/V2.

## Family B -- VWAP Pullback / Reclaim

Module: `src/empirical_platform/decision_candidate/opportunity_family_vwap_pullback.py`
Structure model id: `SESSION_VWAP_PULLBACK_RECLAIM_V1`

**Why this differs from V1/V2's breakout:** uses a computed intraday reference level (the
session's own cumulative VWAP) rather than a bare price-range high, and requires a
constructive-then-pullback-then-reclaim sequence around that level.

- **Required evidence:** `compute_vwap_series(bars)` -- `series[i]` is the session VWAP
  computed from `bars[0]` through `bars[i]` inclusive ONLY (look-ahead-safe by construction,
  proven by `tests/unit/test_m093_family_vwap_pullback.py::test_vwap_series_entry_i_is_unaffected_by_any_bar_after_i`).
  `constructive_lookback_bars + pullback_bars` reference bars before the decision bar.
- **Entry condition:** (1) every bar in the constructive window closed above its own
  then-current VWAP; (2) at least one bar in the pullback window touched or dipped to the
  running VWAP (`bar.low <= current_vwap`); (3) the evaluation bar reclaims
  (`current.close > current_vwap AND current.close > current.open`); (4) volume and liquidity
  confirmation, same convention as Family A.
- **Stop method:** the pullback window's own low.
- **Target method:** range-aware (`target_range_multiple * reference_average_range`), floored
  at the minimum R:R, identical formula shape to Family A.
- **Invalidation / rejection reasons:** `INSUFFICIENT_REFERENCE_BARS`,
  `INSUFFICIENT_LIQUIDITY`, `NO_CONSTRUCTIVE_CONTEXT`, `NO_VWAP_PULLBACK`, `NO_VWAP_RECLAIM`,
  `WEAK_RECLAIM_VOLUME`.
- **Entry window / minimum evidence:** any evaluation bar at or after index
  `constructive_lookback_bars + pullback_bars`.
- **Position sizing / mandatory exit:** shared framework, unchanged.

## Family C -- Opening Range Breakout

Module: `src/empirical_platform/decision_candidate/opportunity_family_opening_range.py`
Structure model id: `FIXED_DURATION_OPENING_RANGE_BREAKOUT_V1`

**Why this differs from V1/V2's breakout:** the reference range is explicitly the session's
own FIRST N minutes (one of exactly two fixed, predeclared durations), not a rolling N-bar
lookback re-evaluated at every bar.

- **Required evidence:** `OPENING_RANGE_VARIANTS_MINUTES = (5, 15)` -- the only two duration
  variants this family tests, per Phase 7's own "at most 2, do not test dozens of durations"
  instruction. `compute_opening_range` reads only `bars[0:duration_minutes]`.
- **Entry condition:** (1) `index >= policy.first_eligible_bar_index` (== `duration_minutes`)
  -- structurally enforced: `evaluate_opening_range_breakout` raises `ValueError` for any
  smaller index, so no opportunity can ever have a decision timestamp inside the opening-range
  window itself (proven for every such index by
  `tests/unit/test_m093_family_opening_range.py::test_evaluate_raises_for_any_index_inside_the_opening_range_window`);
  (2) `current.close > opening_range.high`; (3) volume confirmation computed ONLY from
  post-range reference bars (`bars[duration_minutes:index]`), never the opening range's own
  bars as the baseline; (4) liquidity.
- **Stop method:** the opening range's own low (a breakout that gives back the whole range
  disproves the thesis).
- **Target method:** `target_range_multiple * opening_range_width`, floored at the minimum
  R:R.
- **Invalidation / rejection reasons:** `INSUFFICIENT_LIQUIDITY`,
  `INSUFFICIENT_POST_RANGE_REFERENCE`, `NO_OPENING_RANGE_BREAKOUT`, `WEAK_BREAKOUT_VOLUME`.
- **Entry window / minimum evidence:** `first_eligible_bar_index` through the session's own
  last evaluable bar, with at least `minimum_reference_bars` post-range bars observed.
- **Position sizing / mandatory exit:** shared framework, unchanged.

## Family D -- Conditional Mean Reversion

Module: `src/empirical_platform/decision_candidate/opportunity_family_mean_reversion.py`
Structure model id: `REGIME_GATED_VWAP_DEVIATION_STABILIZATION_V1`

**Why this differs from V1/V2's breakout:** the only family in this milestone that is not a
continuation/breakout pattern at all -- explicitly regime-gated so it never "buys falling
prices merely because they fell" (Phase 8's own instruction). Reuses Family B's
`compute_vwap_series` unchanged (imported, not reimplemented).

- **Required evidence:** a `regime_lookback_bars`-bar regime window (>= 4 bars, split into two
  halves), the running VWAP series, the current and previous bar.
- **Entry condition -- ALL THREE together, never deviation alone:** (1) REGIME: the regime
  window's first-half average close does not exceed its second-half average close by more
  than `maximum_adverse_trend_percent` (no strong adverse/downward trend); (2) DEVIATION: the
  current close is at least `minimum_deviation_percent` below the current session VWAP; (3)
  STABILIZATION: the evaluation bar closes above its own open AND its low does not undercut
  the previous bar's low (`current.low >= previous.low`) -- a genuine reversal bar, proven
  distinct from deviation-alone by
  `tests/unit/test_m093_family_mean_reversion.py::test_a_new_low_with_no_stabilization_is_rejected_even_though_it_deviates_from_vwap`.
- **Stop method:** the current (reversal) bar's own low -- tight and structural; a new low
  immediately after disproves the stabilization thesis.
- **Target method:** the current session VWAP itself -- never an arbitrary fixed upside
  multiple, per Phase 8's own instruction -- floored at the minimum R:R.
- **Invalidation / rejection reasons:** `INSUFFICIENT_REFERENCE_BARS`,
  `INSUFFICIENT_LIQUIDITY`, `ADVERSE_TREND_REGIME`, `INSUFFICIENT_VWAP_DEVIATION`,
  `NO_STABILIZATION_EVIDENCE`.
- **Entry window / minimum evidence:** any evaluation bar at or after index
  `regime_lookback_bars`.
- **Position sizing / mandatory exit:** shared framework, unchanged.

## Family E -- Relative Strength

Module: `src/empirical_platform/decision_candidate/opportunity_family_relative_strength.py`
Structure model id: `BOUNDED_INTERVAL_OUTPERFORMANCE_VS_BENCHMARK_V1`

**Why this differs from V1/V2's breakout:** the only family that compares a symbol against a
benchmark rather than evaluating a symbol in isolation -- a genuinely different information
source (relative, not absolute, price action).

- **Benchmark handling (Phase 9's explicit-exclusion option):** `BENCHMARK_SYMBOLS = frozenset
  ({"SPY", "QQQ"})` are excluded from this family entirely.
  `evaluate_relative_strength` refuses immediately with reason `BENCHMARK_SYMBOL_EXCLUDED` for
  either symbol, before touching any bar or benchmark data -- proven by
  `tests/unit/test_m093_family_relative_strength.py::test_spy_and_qqq_are_excluded_before_any_bar_is_read`.
  No symbol is ever compared against its own future performance: the benchmark is always a
  different instrument's bars, aligned by exact timestamp (`build_benchmark_index`, a dict
  keyed by timestamp, not positional index), and only the two exact timestamps a decision
  needs (now, and `lookback_bars` bars ago) are ever read -- proven immune to bars at later
  timestamps by
  `tests/unit/test_m093_family_relative_strength.py::test_appending_future_benchmark_bars_does_not_change_the_evaluation`.
- **Required evidence:** `lookback_bars` reference bars on the symbol's own series; a
  benchmark bar at the decision timestamp AND at the reference-start timestamp (a missing
  benchmark bar at either required timestamp is rejected as `INSUFFICIENT_BENCHMARK_EVIDENCE`,
  never approximated or interpolated).
- **Entry condition:** (1) the benchmark's own same-interval return is at least
  `minimum_benchmark_return_percent` ("constructive"); (2) the symbol's own same-interval
  return exceeds the benchmark's by at least `minimum_outperformance_percent`; (3) the
  reference window's own low is not violated (`current.low >= reference_low`); (4) the
  evaluation bar's close exceeds the reference window's own highest close (resumption
  trigger); (5) liquidity.
- **Stop method:** the reference window's own low.
- **Target method:** range-aware (`target_range_multiple * reference_average_range`), floored
  at the minimum R:R.
- **Invalidation / rejection reasons:** `BENCHMARK_SYMBOL_EXCLUDED`,
  `INSUFFICIENT_REFERENCE_BARS`, `INSUFFICIENT_BENCHMARK_EVIDENCE`,
  `INSUFFICIENT_LIQUIDITY`, `BENCHMARK_NOT_CONSTRUCTIVE`, `INSUFFICIENT_OUTPERFORMANCE`,
  `STRUCTURE_BROKEN`, `NO_RESUMPTION_TRIGGER`.
- **Entry window / minimum evidence:** any evaluation bar at or after index `lookback_bars`,
  for any symbol other than SPY/QQQ, with both required benchmark timestamps present.
- **Position sizing / mandatory exit:** shared framework, unchanged.

---

## Freeze statement

These five definitions, exactly as written above and as implemented in the five modules
listed, are frozen as of this commit. No family's entry / stop / target / regime logic may be
altered after any screening or comparison result exists without an explicit new research
iteration (governed by the Phase 11+ mission text, out of scope for this document). This
document's own commit -- together with the `git log` ordering on this branch, where every
family module and this document predate any screening/comparison code -- is the evidence that
the freeze happened before results, mirroring the same discipline M091's and M092's own
policy-freeze commits used.
