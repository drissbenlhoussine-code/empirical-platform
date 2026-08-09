# MILESTONE-062 - Broader Historical Validation (Out-of-Sample Holdout) - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony process established in M053-M061. This milestone answers the question M061's own freeze document explicitly left open: it disclaimed "the strategy is robust out-of-sample" and "survivorship bias is absent" as claims M061 does not make. M062 moves from one fixed mechanics-validation fixture to controlled multi-period validation with strict holdout separation -- without claiming profitability, live-trading readiness, or that survivorship bias is solved.

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M062 baseline: `75798508832bb8c5b5465d653489f1de52526461` (the M061 Owner Freeze hash-recording HEAD; M061 fully `APPROVED_AND_FROZEN`), independently re-verified via `git fetch` at mission start and again at the start of the independent second pass.

## 2. Fresh Validation Inventory (Phase 1)

An exhaustive fresh search (`validation_study`, `holdout`, `out_of_sample`, `development_period`, `walk_forward`, `dataset_bundle`, `dataset_split`, `robustness`, `generalization`, `optimization`, `grid_search`, `parameter_search`, `survivorship`, `regime`) found zero pre-existing code anywhere in `src/` or `tests/`. **No prior frozen multi-period-validation authority exists.** M061's own freeze document is the governing precedent (Classification C, governance-only): it explicitly disclaims out-of-sample robustness and survivorship-bias claims, which is the authority M062 acts on.

## 3. M061 Reuse (Phase 7)

`build_historical_backtest_run()` (`decision_candidate/historical_backtest.py`) is imported and called directly, once per segment, with zero modification. No second backtesting engine exists anywhere in this changeset. M061 remains authoritative for decision timing, next-bar-open entry, `STOP_FIRST` ambiguity, holding horizon, cost model, PnL, and every metric. M062's own contribution is limited to deterministic dataset slicing, cross-segment comparison, and persistence of the resulting study.

## 4. Dataset Bundle Authority (Phase 2)

`ValidationDatasetBundle`/`ValidationDatasetBundleAuthority` (`decision_candidate/validation_study.py`): `dataset_bundle_id` (a `DatasetId`), `dataset_bundle_version`, `source_kind` (always `FIXED_VALIDATION_FIXTURE` for the committed fixture -- never described as historical-market evidence), `sha256`, `interval`, `instrument_count`, `total_bars_per_instrument`. The canonical fixture (`tests/fixtures/m062_validation_study/synthetic_multi_period_validation_dataset_bundle.json`) does not depend on mutable internet data: 4 instruments (AAPL, MSFT, GOOG, AMZN), 1-minute bars, 48 bars per instrument, generated once by a documented, fixed-seed (`6062001`) pseudo-random-walk script and committed as-is -- never hand-edited after generation to shape results (Section 12 of the fixture's own `README.md` records the exact process). SHA-256: `3289c380b233b06495c865b1645185436318b2394d77faaea97be96bf787c9f3`.

## 5. Segment Model and Roles (Phase 3)

Exactly one `DEVELOPMENT_REFERENCE` segment and exactly two holdout segments (`HOLDOUT_1`, `HOLDOUT_2`), declared in that fixed order. `build_validation_study()` rejects: missing development segment, fewer than two holdouts, wrong segment order, duplicate `segment_id`, an empty segment (`scoring_bar_count < 1`), and any declared segment range whose total bar count does not equal the bundle's own per-instrument bar count ("range outside dataset"). Each segment is a private, non-overlapping, contiguous 16-bar block: `warmup_bar_count=5` + `scoring_bar_count=8` + `buffer_bar_count=3`. No bar ever belongs to more than one segment.

## 6. Warmup / Lookback Boundary (Phase 6)

Each segment's own `warmup_bar_count` bars provide DATA_CONTEXT only (the M057 reference-window calculation) and are structurally never scored -- M061's own `evaluated_cutoffs = range(reference_window_size, bars_per_instrument - holding_horizon_bars)` guarantees this without any new M062 logic. `build_validation_study()` additionally enforces `warmup_bar_count == reference_window_size` and `buffer_bar_count == outcome_model.holding_horizon_bars` exactly, so the declared `scoring_bar_count` is always trustworthy (8 scored cutoffs per segment, verified against real fixture output). Each `ValidationSegment` record persists both its `data_start/end_timestamp` (the full range fed to M061, including warmup/buffer) and its `scoring_start/end_timestamp` (the narrower range whose cutoffs were actually scored) -- both independently retrievable.

## 7. Holdout Firewall (Phase 5)

Because segments are non-overlapping, contiguous, private bar blocks, no segment's `HistoricalDataset` slice (fed to M061) ever includes a single bar from another segment. This was proven, not merely asserted, three separate times: (a) a hostile test mutating `HOLDOUT_2`'s entire private block leaves `DEVELOPMENT_REFERENCE` and `HOLDOUT_1` byte-for-byte unchanged; (b) a hostile test mutating `DEVELOPMENT_REFERENCE`'s own scoring range leaves both holdouts unchanged; (c) the independent second pass repeated the attack against `HOLDOUT_1`'s own private block (the *middle* segment) and confirmed both neighbors -- `DEVELOPMENT_REFERENCE` and `HOLDOUT_2` -- were unaffected in either direction. All three were run against real PostgreSQL through the real production entrypoints.

## 8. No Fake Training (Phase 4)

The M057-M061 policy stack is frozen and untouched. `build_validation_study()` applies the exact same `RiskPolicy`/`SizingPolicy`/`HistoricalExecutionAssumption`/`HistoricalOutcomeModel`/`HistoricalCostModel` objects to every segment -- verified directly via raw SQL (identical `strategy_id`/`risk_policy_id`/`sizing_policy_id`/... across all three persisted `historical_backtest_run` rows) and via source inspection (no conditional branch anywhere reads one segment's own results to adjust another segment's inputs). `DEVELOPMENT_REFERENCE` is descriptive reference only, never a training signal.

## 9. Study Domain and Persistence (Phase 8/19)

`HistoricalValidationStudy` (one row, migration `a66cb39e7dba`, table `validation_study`) plus `ValidationSegment`/`ValidationSegmentResult` (three rows per study, table `validation_segment`, FK'd to both `validation_study` and the unmodified M061 `historical_backtest_run` table by governance_id and runtime_id). Persists: dataset bundle identity/version/hash, every policy/model identity+version, supplied equity/risk-percent, per-segment boundaries (both DATA_CONTEXT and SCORING_PERIOD ranges), per-segment metrics, cross-segment PnL/R deltas, survivorship-bias disclosure, status, and classification. Full per-trade detail for every segment remains independently reachable through the unmodified, frozen M061 `get_historical_backtest_run` CLI -- never duplicated into the M062 tables.

## 10. Study Report and Generalization Comparison (Phase 9/10)

Per segment: simulated/executed/win/loss/time-exit/no-entry counts, gross/net PnL, average net PnL, average R, total R, win rate, profit factor, maximum realized-PnL drawdown -- M061's own metric semantics, unchanged. Study-level: `holdout_1_net_pnl_delta`/`holdout_1_total_r_delta`/`holdout_2_net_pnl_delta`/`holdout_2_total_r_delta` (each holdout's own metric minus the development reference's), a transparent descriptive comparison -- no opaque "generalization score."

## 11. Classification Vocabulary (Phase 11)

`HistoricalValidationStudyStatus.STUDY_COMPLETED` (lifecycle) and `HistoricalValidationStudyClassification.HOLDOUT_RESULTS_RECORDED` / `INSUFFICIENT_EVIDENCE` (product statement -- `INSUFFICIENT_EVIDENCE` when either holdout executes zero trades, since there is then nothing to meaningfully compare). Deliberately excludes `STRATEGY_PROFITABLE`, `STRATEGY_VALIDATED`, `READY_FOR_LIVE_TRADING`, `PRODUCTION_READY` -- no such vocabulary exists anywhere in this module.

## 12. Dataset Tamper Detection (Phase 15)

`parse_validation_dataset_bundle_file(path, *, expected_sha256)` (`usecases/validation_study_io.py`) computes the file's real SHA-256 (via M061's own `dataset_sha256()` helper, reused verbatim) and raises before any parsing or study construction if it does not match the caller-declared `expected_sha256` -- proven directly (a one-byte mutation is rejected with `ValueError`, and zero rows are written to PostgreSQL), and independently reproduced in the second pass against a fresh container.

## 13. Survivorship-Bias and Sample-Size Disclosure (Phase 13/14)

`SURVIVORSHIP_BIAS_NOT_ADDRESSED` is a persisted field on every study, always this exact value for the fixed four-instrument fixture (no membership changes, no delisting model, no historical index-membership data). Sample size is small and reported plainly: 8 scored cutoffs and at most 5 executed trades per segment -- never described as statistically strong or significant evidence anywhere in this codebase or its governance.

## 14. Actual Results (Phase 12, hand-verified, un-massaged)

| Segment | Executed | Wins | Losses | Net PnL | Total R | Win rate |
| --- | --- | --- | --- | --- | --- | --- |
| DEVELOPMENT_REFERENCE | 4 | 4 | 0 | 933.85 | 14.31 | 100% |
| HOLDOUT_1 | 3 | 1 | 2 | 64.58 | -0.59 | 33.3% |
| HOLDOUT_2 | 5 | 3 | 2 | 383.23 | 5.45 | 60% |

Both holdouts underperform the development reference (`holdout_1_net_pnl_delta = -869.27`, `holdout_2_net_pnl_delta = -550.62`). This is reported as-is: the fixture's own generation parameters were fixed once, before any result was inspected, and never adjusted afterward.

## 15. Hostile Review and Independent Second Pass (Phase 24/26)

All 38 mission-specified questions were attacked; every one is covered by a real test or a direct source/grep audit, with zero blocking findings (full disposition in the freeze document). The independent second pass -- a genuinely different, freshly-provisioned PostgreSQL container, driven exclusively through real subprocess CLI invocations -- independently reproduced the exact same results, independently re-ran the tamper-detection attack, independently re-ran a holdout-mutation attack against a different segment (`HOLDOUT_1`, proving no leakage in either direction), independently confirmed deterministic replay, and attempted and failed to disprove the central product claim.

## 16. Product-Value / Honesty Gate (Phase 28)

Does M062 prove strategy profitability? **No.** Does it prove live-trading readiness? **No.** Does it solve survivorship bias? **No** (explicitly disclosed, not solved). Does it provide stronger validation evidence than M061? **Yes** -- M061 proved the engine mechanically sound against one fixture; M062 proves that same engine can be evaluated across independently-isolated periods without holdout information ever influencing an earlier decision, and reports a genuine (unfavorable) generalization gap rather than hiding it.

## 17. In-Scope

`validation_study.py` domain (bundle/segment/study types, `build_validation_study()`), `validation_study_repository.py` Protocol, migration `a66cb39e7dba`, `PostgresHistoricalValidationStudyRepository`, two usecases, two CLI entrypoints and their `pyproject.toml` registration, one multi-period synthetic fixture, unit tests (segment/bundle validation, independent verification, hostile cases), one PostgreSQL acceptance suite (lifecycle, tamper, both mutation attacks, replay, multi-study, CLI), and this governance document.

## 18. Out-of-Scope

Any transport/HTTP/UI layer; live or downloaded market data; any parameter search, tuning, or "best configuration" selection; a walk-forward re-fitting loop; portfolio/account state; any change to Campaign/Run/EvidencePackage/Review/DecisionCandidate/TradingOpportunityScan/TradePlan/PositionPlan/HistoricalBacktestRun or their entrypoints; any claim of profitability, live readiness, or resolved survivorship bias.

## 19. M063 Boundary

This scope selects exactly one MILESTONE-062 capability. No MILESTONE-063 capability, terminology, or sequencing decision is made anywhere in this document. **M062 does not certify performance -- it records evidence.**

## 20. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
