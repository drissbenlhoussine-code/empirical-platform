# MILESTONE-068 - Cross-Instrument Dependence + Correlation-Aware Portfolio Risk Evidence + Concentrated-Exposure Firewall - Scope and Design

## 1. Repository Authority

`git fetch origin` confirmed `HEAD == origin/master` at `0cc287a` (M067
owner-freeze-commit-hash record) with 0 ahead / 0 behind before any M068
work began. `PROJECT_CHECKPOINT.md` confirmed
`LATEST_FROZEN_MILESTONE=MILESTONE-067`,
`M067_STATUS=APPROVED_AND_FROZEN`, `M068_STATUS=NOT_STARTED`.

## 2. Fresh Inventory (Phase 2)

A live-repository search for `correlation`/`covariance`/`dependence`/
`co-movement`/`portfolio variance`/`correlation matrix`/`concentration`/
`diversification`/`factor`/`beta`/`sector`/`cluster`/`exposure`/
`concurrent positions` found:

- **ABSENT everywhere** in the `decision_candidate` domain -- only
  unrelated docstring word-matches (e.g. M067's own "concentration"
  usage referring to capital-utilization concentration, never a
  cross-instrument statistical concept).
- **FROZEN and reused verbatim**: M067's `PortfolioEvidenceReport.
  allocation_decisions` (the real concurrent-position timeline, with
  `entry_timestamp`/`exit_timestamp`/`risk_amount` per allocated
  position) and the M064/M065 dataset bundle's own
  `HistoricalInstrumentSeries` (raw per-instrument bar closes, the same
  bundle M067's own upstream M064 study already declares and hashes).

M068 is therefore genuinely new capability, not a duplication of
anything frozen.

## 3. Core Boundary (Phase 3)

Historical risk EVIDENCE only. No portfolio optimizer, no
Markowitz/efficient-frontier/risk-parity/Kelly/Black-Litterman, no
automatic diversification or automatic position resizing, no ML
clustering, no factor model, no future-correlation forecast, no hedging
recommendation, no live risk management. M068 evaluates the exact
concurrent-position timeline M067 already froze under one explicit,
predeclared estimation policy -- it never re-allocates, re-sizes, or
mutates anything upstream.

## 4. Data Authority (Phase 4)

Every `PortfolioDependenceReport` binds to two upstream authorities,
both hash/identity-verified before any computation: (1) the exact M067
`PortfolioEvidenceReport` (governance ID + runtime ID), which supplies
the concurrent-position timeline; (2) the exact M064/M065 dataset bundle
file that M067's own report already declares
(`dataset_bundle_sha256`), hash-verified via the existing
`parse_robustness_dataset_bundle_file(..., expected_sha256=...)`
function -- no untraceable correlation report, no second hashing path.

## 5. Return Series Semantics (Phase 5)

Simple arithmetic returns, `r_t = (close_t - close_{t-1}) /
close_{t-1}`, over the source bundle's own bar grid -- the smallest,
most transparent choice available, deliberately avoiding a second,
harder-to-audit convention (log returns) this codebase has never
needed. No forward-filling of missing bars; a return is computed only
between two genuinely consecutive bars present in the data.

## 6. Temporal Firewall (Phase 6)

Dependence evidence at any estimation cutoff `T` uses only bars with
`timestamp <= T`, restricted to the most recent `lookback_bar_count`
bars at or before that cutoff. A future bar can never affect an earlier
cutoff's own correlation, concentration, or classification. Proven via
a pure-function unit test, a real-event-timeline acceptance control, and
an independent from-scratch falsification attempt during the second
pass (bar-deletion equivalence check) -- zero violations found under
any of the three.

## 7-8. Pairwise Dependence + Correlation Matrix (Phases 7-8)

Pearson correlation over the timestamp-aligned intersection of two
return series. Canonically ordered (`instrument_a <= instrument_b`,
including the diagonal self-pair) so `(A,B)` and `(B,A)` are always the
same one persisted record -- symmetry and no-duplicate-pair are
structural guarantees of construction, not runtime checks that could
silently disagree. Persisted per pair: both instruments, observation
count, estimation start/end, correlation, and an explicit
`PairDependenceStatus` (`DEFINED`/`INSUFFICIENT_OBSERVATIONS`/
`UNDEFINED_ZERO_VARIANCE`) -- never a fabricated 0 when undefined.

## 9. Concurrent Exposure Link (Phase 9 -- the key product feature)

Dependence is evaluated only among instruments M067's own event
timeline shows genuinely open at the same historical instant -- derived
directly from `allocation_decisions`, never from positions that merely
coexist in the same study without overlapping in time. The same
instrument appearing twice in one state (two separate open positions in
the same symbol) is correct and intentional: their self-correlation of 1
correctly reflects genuine full dependence, not a bug to deduplicate
away.

## 10. Dependence-Weighted Concentration (Phase 10)

`w'Cw` using the pairwise correlation matrix as the dependence
weighting, no expected returns anywhere. An undefined pair is
conservatively treated as correlation = 1 within this weighting only
(never silently assumed independent, which would understate
concentration risk) -- documented explicitly in the module and function
docstrings. Never called an "optimized risk score."

## 11-19. Controls, Classification, Instability, Stress, Estimation Window

Six named acceptance controls (perfect-correlation, low-dependence,
negative-correlation, constant-series, false-diversification-attack,
future-mutation-attack) proven on hand-constructed but deterministic
fixtures. A conservative, explicit 4-value `DependenceEvidenceClassification`
(`INSUFFICIENT_DEPENDENCE_EVIDENCE`/`LOW_OBSERVED_DEPENDENCE`/
`MIXED_OBSERVED_DEPENDENCE`/`HIGH_OBSERVED_DEPENDENCE`), thresholds
`0.40`/`0.70`, never SAFE/DIVERSIFIED/OPTIMAL vocabulary anywhere.
Correlation instability compares first-half vs. second-half of one
estimation window and reports the single largest pairwise delta, never
averaging instability away. Concentration stress is a diagnostic-only
perfect-correlation-assumption comparison, never mutating the canonical
M067 allocation. One explicit, frozen `DependenceEstimationPolicy`
(`lookback_bar_count`, `minimum_overlapping_observations`,
`policy_id`/`version`) -- no lookback search.

## 20. Domain Model

Kept deliberately small: `DependenceEstimationPolicy`,
`PairwiseDependenceEvidence`, `ConcurrentExposureState`,
`ConcentrationStressResult`, `PortfolioDependenceReport`. One new domain
module (~700 lines), zero generic risk-analytics framework.

## 21. PostgreSQL (Phase 21)

Three purely additive tables: `portfolio_dependence_report`,
`portfolio_dependence_pair`, `portfolio_dependence_concurrent_state`.
Answers every question the mission poses via raw SQL: which portfolio
study and dataset produced this report, every pairwise correlation and
its status, every concurrent-exposure state's weights and concentration
figures, and the estimation policy used.

## 22. Application + Real CLI (Phase 22)

`empirical-platform-run-portfolio-dependence-evidence` /
`empirical-platform-get-portfolio-dependence-evidence`. No HTTP.

## 23. What M068 PROVES

That historical cross-instrument dependence, evaluated only among
instruments an already-frozen M067 portfolio genuinely held
concurrently, can expose nominal capital diversification as understating
true historical concentration -- proven both on a hand-constructed
false-diversification control and organically on the real M064 fixture
(states with repeated same-instrument concurrent positions driving
`dependence_aware_concentration` to `1.0000` while `nominal_concentration`
sits at `0.34`-`0.50`) -- via an 81-case hostile review (one
test-construction defect found and fixed) and an independent second
pass on fresh infrastructure that directly, aggressively attempted (and
failed) to falsify the temporal-firewall and value-range invariants.

## 24. What M068 DOES NOT PROVE

Does not prove diversification (nominal or dependence-aware). Does not
predict future correlation -- historical correlation is not future
correlation, stated explicitly in every persisted report's own
`limitations`. Does not optimize allocation, hedge, or manage live risk.
Does not certify the canonical portfolio's real dependence is high or
low in any absolute sense beyond what the real fixture actually showed
(`HIGH_OBSERVED_DEPENDENCE` on this specific fixture, honestly reported,
not tuned).

## 25. Out of Scope

Markowitz/efficient-frontier/risk-parity/Kelly/Black-Litterman, any
portfolio optimizer, automatic diversification, automatic position
resizing, ML clustering, factor models, any change to
strategy/ranking/risk/sizing/capital-allocation code, any HTTP
transport, any broker/execution code, MILESTONE-069.

## 26. Status

`APPROVED_AND_FROZEN` -- see
`MILESTONE_068_CROSS_INSTRUMENT_DEPENDENCE_CORRELATION_AWARE_PORTFOLIO_RISK_EVIDENCE_AND_CONCENTRATED_EXPOSURE_FIREWALL_MACRO_MILESTONE_FREEZE.md`.
