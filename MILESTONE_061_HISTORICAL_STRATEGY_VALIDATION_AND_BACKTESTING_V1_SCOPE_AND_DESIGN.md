# MILESTONE-061 - Historical Strategy Validation and Backtesting V1 - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony macro-milestone process used by M053-M060. This milestone answers the first product question that M057-M060 intentionally left unresolved: given only information available at each historical decision cutoff, what would the frozen decision stack have selected, and what would have happened afterward under one explicit deterministic outcome model?

M061 is validation infrastructure first. It must be able to reveal poor historical behavior honestly. It must not optimize the strategy against the acceptance fixture and must not claim profitability or live-trading readiness.

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M061 baseline: `a544be6ee073456d0360108e87105d4f3ab1be59` (the final M060 owner-freeze hash-recording HEAD; M060 fully `APPROVED_AND_FROZEN`), independently re-verified before implementation began.

## 2. Fresh Historical / Backtest Inventory

An exhaustive fresh search (`backtest`, `historical`, `simulation`, `performance`, `pnl`, `drawdown`, `trade_outcome`, `slippage`, `commission`, `walk_forward`, `out_of_sample`) produced:

- **Frozen predecessor concepts**: M057 deterministic market-observation evaluation, M058 multi-instrument scan/ranking, M059 risk-gated `TradePlan`, M060 position-sizing and capital gate.
- **Governance-only references**: prior milestone documents describe future empirical validation and historical strategy evaluation, but no frozen runtime contract existed before this milestone.
- **Absent / unimplemented before M061**: no first-class backtest run, no historical dataset authority, no persisted trade-outcome record, no backtest metrics record, no deterministic outcome simulator, no raw historical validation CLI.

No production backtest runtime existed before this milestone.

## 3. Reuse of Frozen M057-M060 Logic

M061 reuses the frozen production decision stack directly:

- M057 `evaluate()` remains the only strategy-evaluation function;
- M058 `build_scan()` remains the only ranking/scan function;
- M059 `build_trade_plan()` remains the only risk-geometry gate;
- M060 `build_position_plan()` remains the only position-sizing gate.

M061 adds deterministic orchestration only. It does **not** create backtest-specific copies of strategy, ranking, trade-planning, or position-sizing semantics.

## 4. First Historical Validation Contract

M061 originates a first-class immutable historical-validation record:

- `HistoricalBacktestRun`
- `HistoricalBacktestTrade`
- `HistoricalDatasetAuthority`
- `HistoricalDataset`
- explicit versioned execution, outcome, and cost models.

The persisted run preserves:

- identity;
- dataset identity / version / source kind / interval / time bounds / checksum;
- strategy, ranking, risk-policy, and sizing-policy identity/version;
- caller-supplied sizing context;
- decision cadence;
- execution assumption identity/version;
- outcome model identity/version;
- cost model identity/version;
- ambiguity policy;
- aggregate metrics;
- per-trade provenance and realized outcome evidence.

## 5. Dataset Authority

M061 acceptance uses a fixed, versioned, immutable local fixture:

- dataset id `DATASET-6101`
- dataset version `1`
- source kind `FIXED_TEST_UNIVERSE`
- interval `ONE_MINUTE`
- instrument universe: `AAPL`, `AMZN`, `GOOG`, `MSFT`, `NVDA`, `TSLA`
- timestamp grid: `2026-08-10T13:40:00+00:00` through `2026-08-10T13:51:00+00:00`
- 12 bars per instrument, 72 bars total
- raw-byte SHA-256 captured at parse time and persisted on every run

The fixture is intentionally small and mechanical. It exists to exercise historical-validation behavior, not to manufacture attractive returns or support market-wide claims.

## 6. Decision-Time Model

Every historical decision is made at **bar close** of cutoff `T` using only bars `<= T`. The evaluation cutoff is explicit and stored on every simulated trade. The backtest runner constructs each observation window as `series[: cutoff_index + 1]`, so future bars cannot enter the decision stack.

## 7. Execution Assumption

M061 selects one explicit deterministic V1 execution rule:

- `NEXT_BAR_OPEN_ENTRY` v1
- decision at close `T`
- hypothetical entry at next bar open `T+1`

This was chosen because it is the least look-ahead-prone coherent model available from OHLC bars while remaining compatible with the frozen M059/M060 entry geometry.

## 8. Exit / Outcome Model

M061 selects one explicit deterministic V1 outcome model:

- `STOP_TARGET_TIME_EXIT` v1
- maximum holding horizon: 3 bars
- no overnight positions

Supported outcomes:

- `TARGET_HIT`
- `STOP_HIT`
- `TIME_EXIT`
- `NO_ENTRY`

If the next-bar open is already beyond or equal to the planned target, or at or below the planned stop, the trade is classified `NO_ENTRY` rather than pretending a fill occurred inside invalid geometry.

## 9. Same-Bar Ambiguity Policy

OHLC bars cannot reveal whether stop or target was hit first when both are traversed in the same bar. M061 resolves this with one explicit conservative rule:

- `STOP_FIRST`

This policy is versioned through the outcome model and persisted on every simulated trade.

## 10. Transaction Cost Model

M061 selects one explicit deterministic V1 cost model:

- `BPS_SLIPPAGE_WITH_OPTIONAL_FIXED_COMMISSION` v1
- entry slippage: default `5` bps
- exit slippage: default `5` bps
- fixed commission per side: default `0`

Zero-cost runs are not the silent default. A caller may override the parameters explicitly, but every run persists the exact values used.

## 11. PnL Semantics

All financial math uses `Decimal`.

For each executed long trade:

- `gross_pnl = (exit_price - entry_price) * quantity`
- `transaction_costs = entry_slippage_cost + exit_slippage_cost + (2 * fixed_commission_per_side)`
- `net_pnl = gross_pnl - transaction_costs`
- `risk_amount = authoritative M060 actual_risk`
- `r_multiple = net_pnl / risk_amount`

`NO_ENTRY` trades carry zero PnL/costs and no R-multiple.

## 12. Portfolio Boundary

M061 is **not** a portfolio engine. It does not introduce:

- mutable account state;
- cash ledger;
- leverage;
- margin;
- cross-position optimization;
- simultaneous-position capital competition;
- broker execution;
- order lifecycle management.

The chosen V1 interpretation is an **independent-trade historical validator** that preserves M060's per-trade position-sizing truth without claiming full portfolio realism.

## 13. Core Performance Metrics

M061 reports only a concise, correctly defined metric set:

- evaluated cutoff count
- evaluated opportunity count
- approved trade-plan count
- approved position-plan count
- simulated trade count
- executed trade count
- wins
- losses
- flats
- time exits
- no-entry count
- gross PnL
- net PnL
- average net PnL
- average R
- total R
- win rate
- profit factor
- maximum realized-PnL drawdown

No vanity metrics, no sharpe-like claims, and no account-equity curve claims are introduced.

## 14. Drawdown Semantics

M061 reports **maximum realized-PnL drawdown**, not account-level drawdown. The series is the cumulative sum of persisted realized `net_pnl` values ordered by `(exit_timestamp, trade_sequence)`.

## 15. Zero-Denominator Semantics

M061 never emits accidental `Infinity` or `NaN`:

- no executed trades -> optional metric fields may be `None`
- no losses -> `profit_factor = None`
- no wins -> `win_rate` remains deterministic, `profit_factor` uses actual denominator behavior
- no R-bearing executed trades -> `average_r = None`

## 16. Historical Provenance

Every simulated trade preserves direct lineage to:

- dataset id / version / checksum
- evaluation cutoff
- local `DecisionCandidate` id
- local `TradingOpportunityScan` id
- local `TradePlan` id
- local `PositionPlan` id
- execution assumption
- outcome model
- cost model

This keeps the central audit question answerable: why does this historical trade exist, and exactly what information was available at selection time?

## 17. Look-Ahead Protection

M061 includes explicit hostile verification that mutates advantageous future data outside the consumed horizon and proves earlier decisions/trade outcomes remain identical. Future bars are used only after entry for outcome evaluation.

## 18. Persistence Model

M061 adds first-class PostgreSQL persistence:

- `historical_backtest_run`
- `historical_backtest_trade`

The run row stores dataset authority, policy identities/versions, model parameters, aggregate metrics, and product classification. The trade row stores per-trade provenance, timing, prices, costs, PnL, ambiguity handling, and outcomes. No pretty-text-only persistence path exists.

## 19. Application Layer and CLI

Application layer:

- `RunHistoricalBacktestCommand` / `RunHistoricalBacktestHandler`
- `GetHistoricalBacktestRunQuery` / `GetHistoricalBacktestRunHandler`

Production entrypoints:

- `empirical-platform-run-historical-backtest`
- `empirical-platform-get-historical-backtest-run`

The CLI exercises real PostgreSQL persistence and returns structured JSON. No direct CLI-to-repository shortcut exists.

## 20. Acceptance Surface

The acceptance fixture must and does demonstrate:

- multiple chronological cutoffs
- `LONG_CANDIDATE` and `NO_TRADE`
- ranking
- approved and rejected trade plans
- approved position plans
- winning trades
- losing trades
- same-bar ambiguity
- `NO_ENTRY`
- `TIME_EXIT`

Expected mechanical acceptance outcomes:

- `AAPL` -> `TARGET_HIT`
- `AMZN` -> `STOP_HIT`
- `NVDA` -> ambiguous same-bar stop/target, conservatively `STOP_HIT`
- `GOOG` -> `NO_ENTRY`
- `TSLA` -> `TIME_EXIT`
- `MSFT` -> upstream trade-plan rejection, therefore no simulated trade

## 21. Independent Verification and Raw SQL

M061 includes:

- an independently-authored recomputation path that does not call production backtest outcome/metric functions;
- raw SQL verification of persisted rows after real application execution;
- deterministic replay verification proving trade outcomes/metrics remain identical across reruns apart from intentional run identity differences.

## 22. Realism Boundaries

M061 deliberately does **not** build:

- tick simulation
- order-book reconstruction
- latency modeling
- partial fills
- exchange matching
- broker-specific fees
- portfolio cash competition
- strategy optimization loops
- market-wide survivorship-bias claims
- profitability or live-readiness conclusions

## 23. Hostile Review Focus

The milestone hostile review attacks:

- malformed chronological data
- shared-grid violations
- future-data leakage
- missing entry bar
- target hit
- stop hit
- same-bar ambiguity
- time exit
- no entry
- zero-denominator metrics
- deterministic replay
- duplicate run identity
- raw SQL vs application truth
- CLI subprocess behavior
- no broker / no network / no LLM dependency
- no scope creep into portfolio or optimization behavior

## 24. Product Classification Boundary

The strongest allowed positive statement is:

- `VALIDATION_ENGINE_PROVEN_FIXTURE_RESULTS_RECORDED`

M061 may not claim:

- strategy profitability
- market-wide validity
- broker readiness
- live-trading readiness

## 25. Expected Product Delta vs M060

Before M061, the platform could decide whether a contemporaneous opportunity should become a persisted `TradePlan` and then a persisted `PositionPlan`, but it could not answer the historical question "what would this stack have produced over a fixed prior dataset, and what would have happened afterward under explicit deterministic assumptions?" After M061, it can answer that question reproducibly, persist the answer, retrieve it later, and independently verify the result.
