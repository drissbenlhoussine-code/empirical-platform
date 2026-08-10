# MILESTONE-066 - Out-of-Sample Strategy Evidence + Statistical Reliability + False-Confidence Firewall - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

`git fetch origin` confirmed `HEAD == origin/master` at `4c11079` (M065
owner-freeze-commit-hash record), 0 ahead / 0 behind, before M066
implementation began. `PROJECT_CHECKPOINT.md` confirmed
`LATEST_FROZEN_MILESTONE=MILESTONE-065`,
`M065_STATUS=APPROVED_AND_FROZEN`, `M066_STATUS=NOT_STARTED`. Full
governance and design decisions are recorded in
`MILESTONE_066_OUT_OF_SAMPLE_STRATEGY_EVIDENCE_STATISTICAL_RELIABILITY_AND_FALSE_CONFIDENCE_FIREWALL_SCOPE_AND_DESIGN.md`.

## Delivered Capability

A new, additive `decision_candidate.statistical_evidence` module
computes a post-hoc, read-only `StatisticalEvidenceReport` from an
already-frozen M064 `SurvivorshipAwareRobustnessStudy` and its M061
window `HistoricalBacktestRun`s: descriptive trade/window evidence, a
deterministic percentile bootstrap (mean/median/aggregate R, window-level
mean total-R), a conservative breadth-and-stability-gated evidence
classification, 5 concentration/outlier sensitivity views, a
permutation-based drawdown-path stress explicitly distinguished from the
bootstrap, and a mandatory, hard-coded false-confidence-firewall
limitations set persisted on every report. Zero changes to any
strategy/ranking/risk/sizing/execution code. Purely additive PostgreSQL
schema (3 new tables). Two new CLI entrypoints, no HTTP.

## Implementation Evidence

- **Source:** `src/empirical_platform/decision_candidate/statistical_evidence.py`
  (~600 lines), `statistical_evidence_repository.py` (Protocol),
  `shared/persistence/postgres_repositories/statistical_evidence_repository.py`,
  `usecases/run_statistical_evidence_analysis.py`,
  `usecases/get_statistical_evidence_report.py`,
  `usecases/statistical_evidence_io.py`,
  `entrypoints/run_statistical_evidence_analysis.py`,
  `entrypoints/get_statistical_evidence_report.py`,
  migration `f18a6b3d9e42` (down-revision `c275f69cee79`, purely
  additive), plus a `StatisticalEvidenceReportId` identifier and
  `pyproject.toml` console-script registration.
- **Tests:** 55 pure unit tests
  (`test_decision_candidate_statistical_evidence.py`: bootstrap policy
  validation, descriptive-statistics primitives, bootstrap determinism,
  drawdown-path computation, classification breadth+sign-stability gate,
  false-confidence-firewall invariants, 15 named statistical attack
  cases) + 3 acceptance-control tests
  (`test_decision_candidate_statistical_evidence_controls.py`:
  weak-sample, outlier, negative controls, Phases 24-26) + 1 independent
  recomputation integration test (no production statistical helper
  imported) + 6 PostgreSQL lifecycle/acceptance tests (full run->persist
  ->retrieve, real CLI subprocess, deterministic replay, seed
  sensitivity, upstream-not-found, tampered-runtime-id,
  duplicate-governance-id), 65 new tests total.
- **Full regression:** `1832 passed, 6 skipped, 1 failed` with real
  PostgreSQL opt-in (91.76% coverage). The 1 failure is the pre-existing,
  unrelated M026 credential-repr false positive present identically in
  every prior milestone's equivalent full-suite run this session.

## Canonical Results

Run against the real M064 canonical fixture (`SURV-6650`/`SURV-6800`
across sessions, 35 executed trades pooled across 10 walk-forward
windows, `DATASET-6401`/`SURVIVORSHIP_AWARE_MECHANICS_FIXTURE`):

```
trade_sample_size: 35   window_sample_size: 10
mean_r_per_trade: 0.4460   median_r_per_trade: 0.2264
mean_r_interval (90% CI): [-0.3707, 0.4460, 1.3634]
net_pnl: 1516.0222   profit_factor: 1.6178
classification: LIMITED_SAMPLE_BREADTH
```

This is the honest, un-massaged result on the first and only fixture
run: the mean-R 90% confidence interval spans zero, so despite a
favorable point estimate and positive net PnL, the false-confidence
firewall and the sign-instability cap correctly prevent the
classification from reaching `MODERATE_SAMPLE_BREADTH` (the tier breadth
alone would otherwise reach) or higher. Per the mission's own Phase 23,
this weak/limited-evidence outcome is accepted and reported as a valid,
successful M066 result -- not regenerated or reinterpreted to look
stronger.

## Hostile Review

79 explicit attack/verification cases were catalogued in
`external-review/MILESTONE-066/hostile-review-matrix.md` (empty/tiny/
outlier-dominated/duplicate-value samples, bootstrap policy edge cases,
classification breadth-and-stability gating, weak-sample/outlier/negative
controls, false-confidence-firewall integrity, upstream-authority
lineage and tamper rejection, database-level CHECK/FK/UNIQUE
enforcement, PostgreSQL round-trip and raw-SQL agreement, real CLI
subprocess evidence, independent recomputation, no-optimization/
no-broker/no-network/no-LLM claim-honesty greps, and frozen-predecessor
preservation). Three genuine defects were found and fixed inline:

1. `sensitivity_views` were built in construction order but retrieved
   from PostgreSQL `ORDER BY label` order, causing a run-vs-get ordering
   drift caught via a real CLI round-trip. Fixed by canonicalizing the
   list by label inside `build_statistical_evidence_report()` itself
   (mirrors the M065 `CorporateActionManifest` precedent).
2. An early entrypoint draft reached into `decision_candidate` directly
   via a raw `__import__(...)` hack, violating the
   `entrypoints`-cannot-import-`decision_candidate`-directly architecture
   rule. Fixed by re-exporting `BootstrapMethod`/`BootstrapPolicy`
   through `usecases/run_statistical_evidence_analysis.py`'s own
   `__all__`.
3. `test_m066_statistical_evidence_independent_verification.py`
   originally depended on out-of-band, manually-seeded data from an
   earlier ad-hoc CLI run; a sibling test's schema-drop teardown silently
   invalidated it, causing an unhandled `UndefinedTable` error instead of
   a clean skip. Fixed by making the test fully self-contained (builds
   its own study and report via the real production usecases), matching
   the established `study_seeded` pattern in the sibling lifecycle test
   module.

All three fixes were independently re-attacked and re-verified during
the second pass (see below). No CRITICAL or MAJOR finding remains open.

## Canonical Validation

`ruff check src tests` clean. `mypy src` clean (238 files; the one
`SecretStr | None` false positive in the new lifecycle test file is the
same pre-existing, already-accepted pattern present identically in the
frozen M065 test file). `tools/check_architecture.py` exit 0. Full
`pytest tests/ -q` (unit + integration, PostgreSQL opt-in, run alone with
no concurrent process against the container): `1832 passed, 6 skipped, 1
failed` (the pre-existing M026 false positive only) in 523s, 91.76%
coverage. Every frozen predecessor milestone (M020-M065) remains green.

An earlier attempt to run the full suite while a separate foreground
PostgreSQL test process was also active against the same container
produced 3 additional failures in unrelated M053/M055 tests -- diagnosed
as a concurrency artifact (both processes independently drop/recreate
the shared schema) and confirmed resolved by re-running the suite alone;
not a real regression.

## Attempting to Disprove the Central Claim

M066's central claim is that its breadth-and-stability-gated
classification and false-confidence firewall are not decorative -- that
the sign-instability cap genuinely suppresses an otherwise-favorable
breadth tier when the underlying evidence does not support it. This was
tested directly against the real, persisted canonical result: by trade/
window counts alone (35 trades, 10 windows), the sample would classify
as `MODERATE_SAMPLE_BREADTH`; because the real mean-R 90% interval spans
zero, the sign-instability cap correctly downgrades it to
`LIMITED_SAMPLE_BREADTH` -- confirmed via an independent, from-scratch
reimplementation of the classification arithmetic (not the production
`_classify()` function) in the second pass. The cap demonstrably binds
on genuine fixture data, not merely a hand-constructed unit-test input.
No evidence was found to disprove the central claim.

## Logically Independent Second Pass

Full record: `external-review/MILESTONE-066/independent-second-pass.md`.
Summary: a genuinely different, freshly-created PostgreSQL container
(`m066-second-pass-pg`, `postgres:16`, port 55490, never used by any
earlier M066 evidence), Git truth re-established from scratch
(`HEAD == origin/master` at `4c11079`, 0/0), all 21 migrations (M020
through M066) applied cleanly to an empty database, and every
acceptance step driven through the real installed CLI executables. A
standalone, stdlib+psycopg-only script (zero imports from any M066
production module) independently recomputed sample sizes, mean/median R,
net PnL, one sensitivity view, and the full mean-R bootstrap interval
(own `random.Random` loop, own percentile-index arithmetic, same seed)
directly from raw PostgreSQL rows -- every value matched the
production-persisted report exactly. All three hostile-review-fixed
defects were independently re-attacked from scratch on the fresh
container and confirmed still fixed. The mean-R point estimate
(`0.4460`) was byte-for-byte identical to every earlier run of the same
fixture-and-seed combination against the original `m063-dev-pg`
container in this session, confirming deterministic replay across two
entirely independent PostgreSQL environments and container lifecycles.

## No Optimization / No Cherry-Picking / No Broker / No Network / No LLM

Repeated independently in the second pass:
`grep -rniE "openai|anthropic|llm|gpt|chat_completion"`,
`grep -rniE "broker|place_order|submit_order|live_trading"`,
`grep -rniE "requests\.|urllib|httpx|socket\.|http://|https://"` across
all new M066 source: no matches. No M066 output was ever used to
optimize, select, re-rank, or re-size a strategy/ranking/risk/sizing
parameter -- confirmed by inspection: no code path reads a
`StatisticalEvidenceReport` field and writes it back into any upstream
decision object. The genuinely `LIMITED_SAMPLE_BREADTH` classification
produced on the first and only real fixture run was accepted and
reported as-is, not regenerated to force a stronger-looking tier.

## Product Honesty Gate (Reality Gate)

Seven explicit questions, answered against the real, persisted evidence
and the real source code -- not aspirationally:

1. **Does M066 prove the strategy is profitable?** **NO.** The
   classification vocabulary is explicitly breadth-and-stability
   language (`LIMITED_SAMPLE_BREADTH`, etc.), never a probability-of-
   profitability claim; `FALSE_CONFIDENCE_FIREWALL_LIMITATIONS` states
   this explicitly on every persisted report.
2. **Does a confidence interval above zero guarantee future or live
   returns?** **NO.** Explicitly and literally stated as the 5th firewall
   limitation: "A confidence interval entirely above zero is not proof
   of future or live profitability."
3. **Does M066 quantify uncertainty?** **YES.** Every report carries a
   deterministic, explicitly-seeded percentile bootstrap confidence
   interval for mean/median/aggregate R (and window-level mean total-R
   when window count permits), persisted alongside the point estimate.
4. **Are small samples exposed, not hidden?** **YES.** The canonical
   fixture's own 10 windows is explicitly close to the
   `_INSUFFICIENT_WINDOW_THRESHOLD=5` floor, and the classification
   (`LIMITED_SAMPLE_BREADTH`) and the firewall's 6th limitation ("a large
   trade count drawn from one narrow historical period is not broad
   temporal evidence") both surface this honestly rather than suppress
   it.
5. **Is concentration/outlier-dependence exposed?** **YES.** Five
   sensitivity views (canonical + excluding-best/worst-trade,
   excluding-best/worst-window) directly show how much the canonical
   result depends on any single observation; the outlier control test
   proves a single dominant winner produces a visibly wider, less
   reliable interval rather than a falsely strong classification.
6. **Is every report linked to exact upstream historical authority?**
   **YES.** Every `StatisticalEvidenceReport` copies `dataset_bundle_id`/
   `dataset_bundle_sha256`/`universe_id`/`membership_manifest_hash`/
   `strategy_id`/`risk_policy_id`/`sizing_policy_id` (and versions)
   verbatim from the source study, all validated non-empty; a report
   bound to a nonexistent or tampered upstream study is rejected via
   `AggregateNotFound`.
7. **Was any strategy, ranking, risk, or sizing parameter optimized
   using M066's own results?** **NO.** M066 is post-hoc evaluation only;
   no code path anywhere reads a `StatisticalEvidenceReport` and feeds it
   back into any upstream decision. Confirmed by inspection and by the
   grep audit above finding no optimization/search/re-ranking/re-sizing
   logic in any new M066 source.

**No claim of real-data usage, statistical significance, a proven
trading edge, predictive power, live-trading readiness, or market
representativeness is made anywhere in this milestone.** M066 makes
statistical uncertainty and sample-breadth limitations explicit and
proves the reliability-evaluation mechanics honestly; it does not
certify that the evaluated strategy is profitable or ready to trade.

## Owner Approval

All mandatory phases (0-34) of the M066 mission specification are
complete: repository-authority verification, fresh statistics inventory,
scope/no-optimization-boundary design, upstream-authority-lineage
binding, trade-level/window-level sample separation, descriptive
evidence, bootstrap authority and confidence intervals, window-level
uncertainty, evidence-sufficiency classification, the false-confidence
firewall, concentration/outlier sensitivity, drawdown-path stress, data
honesty, PostgreSQL persistence, real CLI, deterministic replay,
independent verification, statistical attack tests, claim-honesty audit,
canonical acceptance study, weak-sample/outlier/negative controls, full
PostgreSQL end-to-end acceptance, a 79-case hostile review with 3
inline-fixed defects, full canonical validation, a logically independent
second pass on a genuinely fresh container that attempted and failed to
disprove the central claim, and the 7-question reality gate above. Zero
blockers remain.

**Freeze declaration:** `M066 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M066 APPROVED_AND_FROZEN`.

## Deferred / M066 Boundary

Explicitly out of scope and not built: hypothesis testing / p-values,
Sharpe/Sortino/Calmar ratios, Monte Carlo price simulation, any strategy
re-optimization using M066's own evidence, any HTTP transport, any
broker/execution code, any generic statistics framework beyond the
narrow set this milestone actually needed. **MILESTONE-067 was
explicitly NOT built, per the mission's own instruction.**

## Next Permitted Action

MILESTONE-067 -- recommendation only; not started as part of M066.
