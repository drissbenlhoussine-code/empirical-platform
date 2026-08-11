# MILESTONE-069 - Real Market-Data Acquisition Pipeline - Scope and Design

## 1. Repository Authority

`git fetch origin` confirmed `HEAD == origin/master` at `92b05c5` (M068
owner-freeze-commit-hash record) with 0 ahead / 0 behind before any M069
work began. `PROJECT_CHECKPOINT.md` confirmed
`LATEST_FROZEN_MILESTONE=MILESTONE-068`,
`M068_STATUS=APPROVED_AND_FROZEN`, `M069_STATUS=NOT_STARTED`.

## 2. Phase 1: Fresh Product-Readiness Gap Analysis

A fresh, 25-area inventory of the live M020-M068 system (market-data
ingestion, dataset authority, universe construction, survivorship
handling, corporate actions, strategy decisions, ranking, risk, sizing,
execution simulation, backtesting, holdout validation, walk-forward
robustness, statistical uncertainty, portfolio capital accounting,
concurrent positions, cross-instrument dependence, daily workflow
orchestration, candidate generation, user-facing research output,
persistence, auditability, reproducibility, operational usability,
real-data readiness) found every single decision-logic capability
genuinely rigorous, well-tested, and honestly evidenced, but classified
**market-data ingestion as PLACEHOLDER** and **real-data readiness as
ABSENT**: `historical_import.py`'s own docstring states "No network
fetch. No hidden vendor call."; `README.md` still lists "Market-data
acquisition" under "Not Implemented," unchanged since the original
scaffold, 68 milestones later. No fixture across any prior milestone was
ever sourced from anything but a hand-built or seeded-synthetic file.

**Biggest blocker identified:** the platform has never once computed
anything from real market data -- every one of 12 consecutive frozen
milestones is rigorous but has only ever been exercised against
synthetic fixtures.

**5+ candidates ranked** (PRODUCT_VALUE / ARCHITECTURAL_LEVERAGE /
EVIDENCE_VALUE / DEPENDENCY_UNLOCK / IMPLEMENTATION_COST /
RISK_OF_PREMATURE_COMPLEXITY): real market-data acquisition (selected,
HIGH leverage/unlock, LOW risk); daily research orchestration (rejected
-- would orchestrate around fake data, hollow); correlation-aware
position sizing (rejected -- the mission's own named trap; also reopens
a boundary M066-M068 explicitly froze shut); portfolio risk gating
(rejected -- same boundary-reversal problem); operational UX/reporting
(rejected -- polish with nothing real yet to report on); richer
universe/data authority (rejected -- sophistication at the wrong layer);
end-to-end research session (rejected -- same hollow-orchestration
problem as daily orchestration).

## 3. Core Boundary

Read-only, publicly-published historical price data acquisition only.
No live/streaming quotes, no order execution, no broker connectivity, no
API key or credential of any kind, no attempt to bypass any
bot-detection/CAPTCHA challenge, no profitability claim, no parameter
optimization. A different, unrelated vendor endpoint (Stooq's CSV
download) was tried first and **abandoned specifically because it
returned a JavaScript bot-verification challenge** -- confirmed directly
during design, never worked around.

## 4. Adapter Boundary Design

A `MarketDataSource` Protocol separates "how bytes are obtained" from
"how bytes are validated and normalized." Two adapters: `FakeMarketDataSource`
(deterministic, offline, zero network -- used for every canonical/CI
-required test, mirroring the established `shared/persistence/fake.py`
precedent) and `YahooFinanceChartMarketDataSource` (a real,
network-capable adapter over Yahoo Finance's unofficial
`/v8/finance/chart/` JSON endpoint -- the same widely-used,
no-authentication, no-bot-challenge endpoint the open-source `yfinance`
library itself relies on for read-only historical price data). The real
adapter's own `source_name` explicitly contains "UNOFFICIAL" so no
downstream consumer can mistake this for a licensed vendor relationship.

## 5. Real Network Dependency, Fully Opt-In

The real adapter is exercised only in an explicitly opt-in integration
test, gated behind `EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS=1`, mirroring
the established `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS` opt-in pattern
exactly -- canonical CI/build acceptance remains fully offline and
deterministic, preserving the "no network dependency" virtue every prior
milestone's hostile review has checked, while genuinely adding the
capability behind an explicit, narrow boundary.

## 6. Reused Infrastructure (No New PostgreSQL Schema)

`AcquireMarketDataSnapshotHandler` translates a real adapter's own
vendor-specific bytes into the exact CSV shape the frozen M065
`parse_source_csv` already requires, then calls the unmodified, frozen
M065 `import_raw_historical_dataset_snapshot()`/`write_dataset_artifact()`
functions verbatim -- no parallel import engine, no new OHLC/chronology
validator. Persistence reuses the frozen M065 `DatasetSnapshotRepository`
unmodified, using its own existing free-text `source_kind`/`source_name`/
`source_reference`/`license_note` columns to carry acquisition
provenance honestly (`source_kind='MARKET_DATA_ACQUISITION'`,
`source_name='YAHOO_FINANCE_UNOFFICIAL_CHART_JSON'` or
`'FAKE_OFFLINE_FIXTURE'`). Retrieval reuses the unmodified, frozen M065
`get-historical-dataset-snapshot` CLI verbatim. **Zero new tables, zero
new migration.**

## 7. `BarInterval.ONE_DAY` Extension

Real EOD daily data is fundamentally daily-granularity; claiming
`ONE_MINUTE` for it would be a factual misrepresentation. `market_data.py`'s
`BarInterval` enum (frozen since M057) was extended with one new,
purely-additive member, `ONE_DAY`, with the docstring corrected from
"intraday" to accurately describe both intraday and daily support. No
existing member changed or removed; zero regression in any frozen
predecessor test.

## 8. What M069 PROVES

That real, live-fetched, hash-verified historical market data can enter
this platform for the first time and flow, completely unmodified,
through the exact frozen M057-M061 strategy/ranking/risk/sizing/
execution/backtesting stack -- proven end-to-end, twice, on two
genuinely independent PostgreSQL environments, with real AAPL/MSFT/GOOG
and AAPL/TSLA data respectively, and independently re-verified via a
standalone hash/referential-integrity recomputation script that found no
evidence of fabrication.

## 9. What M069 DOES NOT PROVE

Does not prove the acquired data is licensed or officially sanctioned
(the adapter's own name says "UNOFFICIAL"). Does not guarantee the real
endpoint remains reachable indefinitely -- a genuine, disclosed fragility
of any unofficial API, mitigated by keeping the real network dependency
fully opt-in and never required for canonical acceptance. Does not
execute any trade or move any money. Does not claim the canonical
backtest result (5 real trades, 3 wins / 2 losses, net PnL $183.82) is
evidence of a trading edge -- it is the first genuine numbers this
platform has ever produced, reported honestly, not a profitability
claim.

## 10. Out of Scope

Correlation-aware position sizing, portfolio risk gating, daily research
orchestration, operational UX/reporting, richer universe/data authority,
any second real-vendor adapter, live/streaming quotes, any broker/
execution code, MILESTONE-070.

## 11. Status

`APPROVED_AND_FROZEN` -- see
`MILESTONE_069_REAL_MARKET_DATA_ACQUISITION_PIPELINE_MACRO_MILESTONE_FREEZE.md`.
