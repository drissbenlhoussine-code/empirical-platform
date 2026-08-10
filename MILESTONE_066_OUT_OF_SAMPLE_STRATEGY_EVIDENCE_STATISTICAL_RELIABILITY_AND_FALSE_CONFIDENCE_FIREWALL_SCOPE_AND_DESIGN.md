# MILESTONE-066 - Out-of-Sample Strategy Evidence + Statistical Reliability + False-Confidence Firewall - Scope and Design

## 1. Repository Authority

`git fetch origin` confirmed `HEAD == origin/master` at `4c11079` (M065
owner-freeze-commit-hash record) with 0 ahead / 0 behind before any M066
work began. `PROJECT_CHECKPOINT.md` confirmed `LATEST_FROZEN_MILESTONE=
MILESTONE-065`, `M065_STATUS=APPROVED_AND_FROZEN`,
`M066_STATUS=NOT_STARTED`.

## 2. Fresh Statistics/Bootstrap Inventory (Phase 1)

A dedicated inventory pass across the frozen M057-M065 stack classified
20 named statistical concepts as IMPLEMENTED / FROZEN / PARTIAL /
PLACEHOLDER / ABSENT before any new code was written, to avoid
duplicating existing functionality:

- **Already frozen and reused verbatim, never modified:** trade-level
  `r_multiple`/`net_pnl` on `HistoricalBacktestTrade` (M061); window-level
  aggregation and a window-level `_median()` in `robustness_study.py`
  (M063); single-run `_drawdown()` in `historical_backtest.py` (M061);
  `CURRENT_UNIVERSE_BIAS_STRESS` and `CORPORATE_ACTION_SEMANTICS_STRESS`
  comparator patterns (M064/M065) as the structural template for a
  diagnostic that compares two computations without altering canonical
  results.
- **ABSENT, and therefore the actual scope of M066:** any confidence
  interval, resampling/bootstrap mechanism, sample-size-aware evidence
  classification, concentration/outlier sensitivity view, or explicit
  false-confidence-firewall statement. No prior milestone computes
  uncertainty around any statistic -- every prior result is a single
  point value.
- **Explicitly not duplicated:** M066's own `_mean`/`_median`/
  `_standard_deviation`/`_historical_realized_drawdown` operate on a
  pooled, cross-window trade-level sample (or the one true chronological
  cross-window path) -- a genuinely different granularity from
  `robustness_study.py`'s own per-window `_median()` and
  `historical_backtest.py`'s own single-run drawdown, which never span
  multiple windows/runs.

## 3. Selected Statistical Technique Set (Phases 2-3)

A deliberately minimal, transparent set, per the mission's own
"avoid academic-statistics theater" instruction:

- **Point estimates:** mean, median, standard deviation, win rate, net
  PnL, total R, profit factor, best/worst trade, largest-trade PnL share.
- **Uncertainty:** one bootstrap method only -- the non-parametric
  percentile bootstrap (resampling with replacement), applied to
  mean-R, median-R, and aggregate-R at the trade level, and to mean
  total-R at the window level when window count permits.
- **Sensitivity:** exactly 5 diagnostic views (canonical,
  excluding-best-trade, excluding-worst-trade, excluding-best-window,
  excluding-worst-window) -- never altering canonical results.
- **Path sensitivity:** one drawdown-path resampling method -- reordering
  (permutation, no replacement) of the identical realized trade outcomes,
  explicitly distinguished from the bootstrap.
- **No** hypothesis testing, no p-values, no Sharpe/Sortino/Calmar ratio,
  no Monte Carlo price simulation, no walk-forward re-optimization, no
  machine-learning model. These would either duplicate existing
  evidence, imply a level of statistical sophistication this sample size
  cannot support, or cross into optimization -- explicitly forbidden.

## 4. Mandatory No-Optimization Boundary (Phase 3)

M066 evaluates already-frozen M061/M064 outputs only. It never re-runs,
re-ranks, re-sizes, or re-optimizes the strategy, ranking model, risk
policy, or sizing policy. `build_statistical_evidence_report()` takes an
already-persisted `SurvivorshipAwareRobustnessStudy` and its window
`HistoricalBacktestRun`s as read-only inputs and produces exactly one new
aggregate: a `StatisticalEvidenceReport`. No output of M066 feeds back
into any upstream decision -- there is no code path anywhere that reads a
`StatisticalEvidenceReport` and uses it to change a strategy, ranking,
risk, or sizing parameter.

## 5. Upstream Authority Lineage (Phase 4)

Every `StatisticalEvidenceReport` copies its full lineage
(`dataset_bundle_id`/`dataset_bundle_sha256`, `universe_id`,
`membership_manifest_hash`, `strategy_id`, `ranking_model_id`,
`risk_policy_id`, `sizing_policy_id`, and their versions) verbatim from
the source `SurvivorshipAwareRobustnessStudy`, never independently
re-derived. A report bound to a nonexistent or tampered upstream study is
rejected via `AggregateNotFound` before any statistical computation
occurs. A statistical report without exact upstream lineage is treated as
invalid by construction -- every lineage field is validated non-empty in
`StatisticalEvidenceReport.__post_init__`.

## 6. Sample Model: TRADE_LEVEL_SAMPLE vs. WINDOW_LEVEL_SAMPLE (Phase 5)

Two independent sample units are tracked and never conflated:
`TRADE_LEVEL_SAMPLE` (individual executed trades, pooled across every
window that produced at least one) and `WINDOW_LEVEL_SAMPLE` (the
study's own walk-forward windows). The evidence classification is gated
by the WEAKER of the two -- 200 trades drawn from only 2 windows is
still `INSUFFICIENT_SAMPLE_BREADTH`, never treated as equivalent to 200
trades broadly spread across 20 windows.

## 7. Descriptive Evidence (Phase 6)

Reused where already authoritative (trade `r_multiple`/`net_pnl` from
M061, window `net_pnl`/`total_r` from M063/M064); newly computed at the
cross-window pooled level where no frozen equivalent exists: win rate,
mean/median/stdev R, best/worst trade R, largest-trade share of positive
PnL, profit factor, and cross-window historical realized max drawdown.

## 8. Bootstrap Authority + Confidence Intervals (Phases 7-8)

A deterministic, explicitly-seeded, non-parametric percentile bootstrap.
Every `BootstrapPolicy` carries an explicit `policy_id`/`version`/
`method`/`resample_count`/`seed`/`confidence_level`, persisted verbatim
on every report -- no field is ever silently defaulted at the point of
use. A fresh `random.Random(seed)` instance is constructed locally inside
each bootstrap call, never the global `random` module. Only 4 confidence
levels are supported (0.80/0.90/0.95/0.99); `resample_count` must be at
least 200. `DEFAULT_BOOTSTRAP_POLICY` uses 2000 resamples, seed
`6066001`, 90% confidence.

## 9. Window-Level Uncertainty (Phase 9)

A separate `window_level_interval` (mean total-R across windows) is
computed only when `window_sample_size >= 5` (the same insufficient-
window threshold used by the classification gate); otherwise it is
persisted as `None`, never fabricated from too few windows. The
canonical M064 fixture (10 windows) is explicitly and honestly close to
this floor -- the false-confidence-firewall limitations note that a
large trade count from one narrow period is not broad temporal evidence,
and the classification's window-breadth gate independently enforces the
same caution at the window level.

## 10. Evidence-Sufficiency Classification (Phase 10)

`StatisticalEvidenceClassification` (`INSUFFICIENT_SAMPLE_BREADTH` /
`LIMITED_SAMPLE_BREADTH` / `MODERATE_SAMPLE_BREADTH` /
`BROADER_HISTORICAL_SAMPLE_BREADTH`) is a conservative,
breadth-and-stability-gated judgment -- never a "probability of
profitability." It is governed by the weaker of trade-breadth vs.
window-breadth, then capped by whether the mean-R bootstrap interval
excludes zero. `excludes_zero` is deliberately symmetric with respect to
sign: a confidently negative interval also excludes zero and reaches the
same tier a confidently positive interval of equal breadth would -- a
profitable small or outlier-dominated sample must still classify weakly,
and a genuinely negative but broad and stable sample must be reported as
well-evidenced, not suppressed or flipped optimistic.

## 11. False-Confidence Firewall (Phase 11)

`FALSE_CONFIDENCE_FIREWALL_LIMITATIONS` is a fixed 6-statement tuple,
persisted verbatim on every report (`StatisticalEvidenceReport.__post_init__`
rejects any deviation), covering: positive net PnL, high win rate, and
profit factor > 1 do not imply reliable evidence; a positive bootstrap
point estimate does not guarantee a real edge; a CI entirely above zero
is not proof of future/live profitability; a large trade count from one
narrow period is not broad temporal evidence.

## 12-14. Sensitivity + Drawdown-Path Stress (Phases 12-15)

Exactly 5 sensitivity views (canonical + 4 excluding-one-observation
views), computed from separately-filtered tuples that never mutate the
canonical sample. A drawdown-path resampling stress reorders (permutes,
no replacement) the identical realized trade outcomes, explicitly
distinguished in naming and implementation from the bootstrap
(resampling with replacement): "reorder" vs. "bootstrap resample"
language is honored throughout, in two separate functions.

## 15. Synthetic-vs-Real Data Honesty (Phase 15)

M066 inherits M065's own honest `dataset_source_kind` field verbatim
from the source study -- `SURVIVORSHIP_AWARE_MECHANICS_FIXTURE` in every
acceptance run in this milestone. No M066 field, docstring, CLI output,
or governance document claims real market-vendor provenance.

## 16. Domain Size (Phase 16)

One new module (`statistical_evidence.py`, ~600 lines), zero generic
statistics framework, zero new decision/ranking/risk/sizing logic. Three
new PostgreSQL tables, purely additive.

## 17. Persistence, CLI, Determinism (Phases 17-19)

Purely additive migration (`f18a6b3d9e42`, down-revision `c275f69cee79`)
adding `statistical_evidence_report` / `_bootstrap_interval` /
`_sensitivity`, with a single-column FK to `survivorship_study.runtime_id`
and closed-enum CHECK constraints on `classification`/`bootstrap_method`/
sensitivity `label`. Two new CLI entrypoints
(`run-statistical-evidence-analysis` / `get-statistical-evidence-report`),
no HTTP. Deterministic replay is guaranteed for a fixed seed: two
independent `run` calls against the same study produce byte-identical
intervals and classification (verified live, Section "Actual results"
below).

## 18. What M066 PROVES

That the observed M064 canonical fixture's performance carries only
`LIMITED_SAMPLE_BREADTH` evidence once uncertainty is honestly
quantified -- the raw mean-R 90% bootstrap interval spans zero
(`[-0.3707, 1.3634]`), which caps the classification below what the raw
35-trade/10-window breadth alone would otherwise suggest
(`MODERATE_SAMPLE_BREADTH`). That the false-confidence-firewall
mechanism genuinely binds on real, non-synthetic data, not merely by
construction in a unit test.

## 19. What M066 DOES NOT PROVE

Does not prove the strategy is profitable. Does not guarantee future or
live returns. Was not used to optimize, select, re-rank, or re-size
anything. Does not certify the sample is broad enough for strong
inference -- 10 windows is explicitly close to the insufficient-window
floor, and this is stated honestly rather than hidden. Does not use real
market data (inherits M065's own honest fixture labeling).

## 20. Out of Scope

Hypothesis testing / p-values, Sharpe/Sortino/Calmar, Monte Carlo price
simulation, machine learning, any change to strategy/ranking/risk/sizing
code, any HTTP transport, any broker/execution code.

## 21. Status

`APPROVED_AND_FROZEN` -- see
`MILESTONE_066_OUT_OF_SAMPLE_STRATEGY_EVIDENCE_STATISTICAL_RELIABILITY_AND_FALSE_CONFIDENCE_FIREWALL_MACRO_MILESTONE_FREEZE.md`.
