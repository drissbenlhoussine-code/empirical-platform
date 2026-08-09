# MILESTONE-063 - Broad Historical Robustness + Walk-Forward Sequencing + Regime Analysis + Sample Expansion - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony process established in M053-M062. This milestone answers the question M062 deliberately left open: after proving honest multi-period holdout isolation, can the frozen M057-M062 stack now be exercised across a materially broader, windowed historical fixture with deterministic walk-forward sequencing, explicit post-hoc regime labeling, and transparent cross-window robustness reporting, without claiming profitability, live-trading readiness, survivorship-bias removal, tuning, or predictive regime intelligence?

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M063 baseline: `5cb112ea883dfbe453f94ff0c95749dd26231c06` (the M062 Owner Freeze hash-recording HEAD; M062 fully `APPROVED_AND_FROZEN`), independently re-verified at mission start and again before the logically independent second pass.

## 2. Fresh Validation Inventory

A fresh search of the live repository before implementation resumed found no pre-existing walk-forward robustness-study code, no pre-existing regime-analysis implementation, no robustness persistence surface, and no cross-window concentration/sensitivity reporting anywhere in `src/` or `tests/`. M062 remains the nearest predecessor authority: it proved strict holdout isolation, dataset-bundle tamper detection, and honest multi-period evidence recording, while explicitly not implementing walk-forward sequencing, broader evidence breadth, or regime analysis.

## 3. Frozen Stack Reuse

M063 reuses the existing frozen stack rather than replacing it. `build_historical_backtest_run()` from M061 remains the only historical execution engine; M057 still owns evaluation timing and reference-window breakout logic, M058 still owns ranking, M059 still owns trade-plan gating, M060 still owns sizing/capital gating, M061 still owns next-bar-open historical execution semantics, and M062 remains the immediately prior dataset-authority/segmentation precedent. M063 contributes deterministic window slicing, descriptive regime labeling, cross-window aggregation, persistence, and reporting only. No `historical_backtest.py`, ranking model, risk policy, sizing policy, execution assumption, or outcome model source was modified.

## 4. Dataset Bundle Authority

`RobustnessDatasetBundle` / `RobustnessDatasetAuthority` (`decision_candidate/robustness_study.py`) define first-class dataset authority for M063. The canonical committed fixture (`tests/fixtures/m063_robustness_study/synthetic_broad_robustness_dataset_bundle.json`) carries:

- `dataset_bundle_id = DATASET-6301`
- `dataset_bundle_version = "1"`
- `source_kind = FIXED_ROBUSTNESS_FIXTURE`
- `sha256 = ca98478ce6156f41c4535eaa040fd3e161229a71acd771a477ee9648ac3dd506`
- `interval = ONE_MINUTE`
- `instrument_count = 6`
- `total_bars_per_instrument = 160`
- `time range = 2026-08-10T13:00:00+00:00` through `2026-08-10T15:39:00+00:00`

This is fixed local test evidence, not live or downloaded market data.

## 5. Universe Authority

M063 promotes universe authority to a first-class persisted concept. The same canonical fixture declares:

- `universe_id = UNIVERSE-6301`
- `universe_version = "1"`
- `universe_membership_model = FIXED_SYNTHETIC_UNIVERSE`
- `constituents = [AAPL, AMZN, GOOG, MSFT, NVDA, TSLA]`

`build_historical_robustness_study()` rejects bundles whose window series do not match the declared canonical universe constituents. Because this is a fixed, synthetic universe with no membership-history model, the persisted survivorship disclosure remains the explicit constant `SURVIVORSHIP_BIAS_NOT_ADDRESSED`.

## 6. Evidence Breadth Delta vs M062

M062's canonical bundle carried 4 instruments, 48 bars per instrument, 3 isolated segments, 24 scored cutoffs, and 12 total executed trades. M063 materially expands evidence breadth with:

- 6 instruments
- 160 bars per instrument
- 960 total bars
- 10 deterministic windows
- 80 scored cutoffs
- 59 simulated trades
- 59 executed trades

The expansion is structural, not row duplication: more instruments, more chronological windows, more scored cutoffs, more trades, and wider volatility variation across the same frozen strategy/risk/sizing/execution stack.

## 7. Walk-Forward Window Model

Each `WalkForwardWindowSpec` is a first-class authority object with:

- `window_id`
- `sequence_index`
- `warmup_bar_count`
- `scoring_bar_count`
- `buffer_bar_count`
- `start_bar_index`
- `end_bar_index`
- `scoring_start_bar_index`
- `scoring_end_bar_index`

The canonical fixture declares exactly 10 windows (`W01`..`W10`) in sequence order. Each window is a private, contiguous 16-bar block per instrument: `warmup=5`, `scoring=8`, `buffer=3`. This preserves the same reference-window and holding-horizon semantics frozen in M057/M061 while extending them across a longer deterministic walk-forward chain.

## 8. Warmup / Context Boundary

Warmup bars are DATA_CONTEXT only, never scored. `build_historical_robustness_study()` enforces:

- `warmup_bar_count == reference_window_size`
- `buffer_bar_count == outcome_model.holding_horizon_bars`
- `scoring_bar_count >= 1`

Every persisted window result records both full data bounds (`data_start_timestamp`, `data_end_timestamp`) and scored bounds (`scoring_start_timestamp`, `scoring_end_timestamp`), so context bars and scored bars remain auditable as separate concepts.

## 9. Window Contract and Ordering

M063 treats window sequencing as an authority surface, not caller presentation order. It rejects:

- zero windows
- duplicate `window_id`
- duplicate `sequence_index`
- inverted or empty ranges
- out-of-range windows
- insufficient warmup
- illegal overlaps

Input list order does not control canonical semantics; `sequence_index` does. A shuffled caller-provided list must serialize back to the same canonical ordered study.

## 10. Temporal Firewall

Each window is evaluated against its own isolated bar block. No later window data may affect:

- M057 evaluation
- M058 ranking
- M059 trade-plan decisions
- M060 sizing
- M061 historical execution
- earlier-window aggregate metrics

This is proven in two forms: automated tests and an independent second-pass mutation attack that changes only the late `W10` block and confirms `W01`..`W09` remain semantically identical.

## 11. Regime Policy

M063 introduces one explicit, versioned, descriptive regime policy only:

- `regime_policy_id = POST_HOC_REALIZED_VOLATILITY_TERTILE`
- `regime_policy_version = "1"`

Each window receives a post-hoc label based on realized volatility:

- `LOW_VOLATILITY`
- `NORMAL_VOLATILITY`
- `HIGH_VOLATILITY`

This is descriptive grouping only. It is not predictive, not a training signal, not a trading input, and not a parameter-selection device.

## 12. Regime Non-Interference

Regime labels must never affect upstream strategy behavior. They may change only analytical grouping and reporting. They must not affect:

- evaluation outcomes
- ranked candidates
- trade plans
- position plans
- historical fills
- window metrics

They are attached after the frozen execution path completes, not before.

## 13. Robustness Study Domain

`HistoricalRobustnessStudy` persists:

- study identity
- dataset authority
- universe authority
- strategy/policy/model identities and versions
- window manifest
- per-window results
- cross-window metrics
- regime breakdown
- concentration metrics
- excluding-best-window sensitivity
- survivorship disclosure
- conservative classification

This remains an evidence-recording product, not a profitability or deployment certification surface.

## 14. Cross-Window Metrics

The persisted study reports transparent cross-window metrics only:

- `window_count`
- `positive_net_pnl_window_count`
- `negative_net_pnl_window_count`
- `positive_total_r_window_count`
- `negative_total_r_window_count`
- `median_window_net_pnl`
- `median_window_total_r`
- `best_window_by_net_pnl`
- `worst_window_by_net_pnl`
- `best_window_by_total_r`
- `worst_window_by_total_r`
- `all_window_net_pnl_total`
- `all_window_total_r_total`
- `largest_positive_window_share_of_positive_pnl`
- `largest_negative_window_share_of_absolute_negative_pnl`
- `excluding_best_window_net_pnl_total`
- `excluding_best_window_total_r_total`

No opaque composite "robustness score" exists.

## 15. Sparse / Edge Window Semantics

Weak evidence remains evidence. M063 preserves rather than deletes:

- zero-trade windows
- one-trade windows
- all-win windows
- all-loss windows
- zero-positive-PnL cases
- zero-negative-PnL cases

Zero-denominator concentration cases are handled explicitly without NaN or Infinity.

## 16. Classification Vocabulary

M063 keeps lifecycle and product interpretation separate.

Lifecycle:

- `HistoricalRobustnessStudyStatus.STUDY_COMPLETED`

Conservative evidence classification:

- `ROBUSTNESS_EVIDENCE_RECORDED`
- `ROBUSTNESS_EVIDENCE_MIXED`
- `ROBUSTNESS_EVIDENCE_WEAK`
- `INSUFFICIENT_SAMPLE`

Deliberately excluded vocabulary includes `PROFITABLE`, `PROVEN_EDGE`, and `LIVE_READY`.

## 17. Canonical Fixture Shape

The committed fixture is synthetic, deterministic, and vendor-neutral. It spans 6 instruments on one continuous one-minute grid, 160 bars per instrument, with 10 declared windows and a fixed universe. The intent is broader evidence breadth and volatility variety, not market realism claims.

## 18. Canonical Results (Actual, Unmassaged)

The canonical persisted study over the committed fixture produced:

- `window_count = 10`
- `total_evaluated_cutoff_count = 80`
- `total_simulated_trade_count = 59`
- `total_executed_trade_count = 59`
- `positive_net_pnl_window_count = 7`
- `negative_net_pnl_window_count = 3`
- `positive_total_r_window_count = 7`
- `negative_total_r_window_count = 3`
- `median_window_net_pnl = 183.944565`
- `median_window_total_r = 1.634932038356822214357869934`
- `best_window_by_net_pnl = W08 / 1245.30999130`
- `worst_window_by_net_pnl = W07 / -293.055420`
- `best_window_by_total_r = W05 / 18.24646990892242838850180340`
- `worst_window_by_total_r = W06 / -7.737888034172596900624932265`
- `all_window_net_pnl_total = 3159.55176410`
- `all_window_total_r_total = 33.84096575766330478385285292`
- `excluding_best_window_net_pnl_total = 1914.24177280`
- `excluding_best_window_total_r_total = 15.59449584874087639535104952`
- `largest_positive_window_share_of_positive_pnl = 0.3481136196652371557486284593`
- `largest_negative_window_share_of_absolute_negative_pnl = 0.7014969015918107753748046817`
- classification `ROBUSTNESS_EVIDENCE_MIXED`

These are descriptive historical fixture results only.

## 19. Regime Breakdown (Canonical)

By the post-hoc realized-volatility tertile policy:

| Regime | Windows | Executed trades | Net PnL total | Total R total | Positive windows | Negative windows |
| --- | --- | --- | --- | --- | --- | --- |
| `HIGH_VOLATILITY` | 4 | 24 | 1763.01930780 | 31.44137038984579508964519536 | 3 | 1 |
| `NORMAL_VOLATILITY` | 3 | 18 | 935.62955130 | 8.570505275741854650543960310 | 1 | 2 |
| `LOW_VOLATILITY` | 3 | 17 | 460.902905 | -6.170909907924344956336302749 | 3 | 0 |

This is analytical grouping only, not a trading-policy recommendation.

## 20. Product Honesty Gate

M063 does not prove profitability. It does not prove live readiness. It does not remove survivorship bias. It does not tune the strategy. It does not search for better parameters. It records broader, better-structured historical robustness evidence over a deterministic fixture while keeping the frozen execution stack unchanged.

## 21. In Scope

`robustness_study.py` domain, repository protocol, migration `63e46fdef1c7`, PostgreSQL repository adapter, runtime wiring, run/get usecases, IO serialization, two CLI entrypoints, one canonical six-instrument robustness fixture, focused unit tests, PostgreSQL lifecycle tests, independent recomputation tests, regime non-interference/temporal-firewall/window-order attacks, and this governance document.

## 22. Out of Scope

Any live or downloaded market data, any parameter tuning/search/optimization, any new strategy/risk/sizing/execution engine, any broker or network dependency, any LLM dependency, any portfolio engine, any vendor ranking, any claim of profitability or live readiness, any Campaign/Run/EvidencePackage/Review/DecisionCandidate lifecycle change, and any M064 capability selection or implementation.

## 23. M064 Boundary

This document selects exactly one M063 capability. No M064 capability, terminology, or sequencing decision is made here.

## 24. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
