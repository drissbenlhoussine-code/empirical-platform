# MILESTONE-070 - Daily Research Orchestration - Scope and Design

## Repository Truth (Phase 0)

Verified at mission start, not assumed: `git fetch origin`; `HEAD ==
origin/master`; 0 ahead / 0 behind; clean working tree; M069 recorded as
`APPROVED_AND_FROZEN`; `LATEST_FROZEN_MILESTONE = MILESTONE-069`; M070
`NOT_STARTED`. Lineage ended at
`6f644f5c42de2d018f284155222a901079b01d6a`.

## Product Objective (Phase 1)

M069 closed the real-data gap: real historical bars can be acquired from
a live vendor and fed through the frozen strategy/ranking/risk/sizing/
backtest stack. But no single command yet produces one complete daily
research session -- an operator still has to manually invoke acquisition,
then scan, then trade-plan, then position-plan, then backtest, in the
correct order, tracking governance ids by hand. M070's product question:
**can one operator launch ONE command and obtain ONE complete, persisted,
reproducible daily research session from real market data?** M070 is
explicitly NOT another mathematical research layer -- no new strategy,
ranking, risk, or sizing math is introduced.

## Fresh Product Inventory (Phase 2)

Frozen, reusable capabilities inventoried: M057 (`evaluate_trading_observation`/
strategy), M058 (`run_trading_opportunity_scan`/ranking), M059
(`build_trade_plan`/risk gate), M060 (`build_position_plan`/sizing), M061
(`run_historical_backtest`/backtest evidence + `parse_historical_backtest_dataset_file`
artifact parser), M065 (`dataset_snapshot`/historical-import schema and
invariants), M069 (`AcquireMarketDataSnapshotHandler`/real+Fake market
-data sources). M051-M054 (Campaign/Run/EvidencePackage) are reused only
as the FK-satisfying governance chain M058 already requires, created
transparently. M067 (portfolio capital accounting) and M068
(cross-instrument dependence) are deliberately NOT wired in: both operate
on collections of trades/windows across time, not a single day's
live-candidate snapshot, and forcing them in would require inventing
synthetic backtest-run sets -- exactly the premature complexity the
mission itself warns against.

## Orchestration Principle (Phase 3)

The orchestrator constructs commands, invokes existing frozen handlers,
coordinates the governance-chain identities, persists session state,
collects outputs, and produces the final report. It never reimplements
strategy, ranking, risk, sizing, backtest, correlation, or market-data
-parsing logic -- verified via `grep` showing zero duplicated business
-logic functions and via the hostile review matrix's own cases 5-11.

## Daily Research Session Identity (Phase 4)

`ResearchSession` (new, `decision_candidate/research_session.py`): session
id, created_at, as_of, requested universe, data source, dataset identity/
version/hash, strategy/ranking/risk/sizing policy ids+versions, governance
-chain ids, an ordered `stage_manifest` (`StageRecord` per stage: name,
version, started_at/completed_at, status, input authority, output
identity, error metadata), per-instrument `decisions`, counts, backtest
-evidence references, and the fixed claim-honesty `limitations` tuple.
`ResearchSessionStatus` carries the full CREATED/ACQUIRING_DATA/
RUNNING_RESEARCH/COMPLETED/FAILED vocabulary the mission asks for, even
though only COMPLETED/FAILED are ever the terminal *persisted* value --
the whole orchestration happens inside one synchronous CLI invocation
with nothing observing it mid-flight, so a session is persisted exactly
once, at the end, in the "compute once, persist once" pattern already
established for M057-M069's own non-lifecycle aggregates (deliberately
lighter than Campaign/Run's own OCC/transition-history machinery, which
solves a different problem -- multiple observers over a long-lived
process).

## One Command (Phase 5)

`empirical-platform-run-daily-research <session_governance_id>
<as_of_date> <lookback_days> <artifact_path> <account_equity>
<risk_percent> <symbol> [symbol ...]` -- 6 fixed positional arguments plus
a variadic symbol list, not a 30-argument CLI. Sensible frozen defaults
(`reference_window_size=5`, the frozen `DEFAULT_RISK_POLICY`/
`DEFAULT_SIZING_POLICY`) cover everything else.

## Real Data (Phase 6)

The canonical path always uses the real, frozen M069
`YahooFinanceChartMarketDataSource` -- no second market-data client was
built. Offline determinism uses the same M069 `FakeMarketDataSource`
dependency-injected at the usecase layer (matching the established M069
precedent: "offline" means Fake adapter + real PostgreSQL, not no
database). Network tests remain gated behind
`EMPIRICAL_PLATFORM_RUN_NETWORK_TESTS=1`.

## As-of Firewall (Phase 7, mandatory)

Two layers, both new: `derive_shared_evaluation_timestamp` restricts to
bars `<= as_of` before picking the one cross-instrument cutoff every
instrument shares (required by M058's own `validate_scan_universe`,
which needs exactly one evaluation timestamp across the whole universe);
`derive_observation_window` then builds each instrument's window ending
EXACTLY at that shared timestamp, never independently. The acquisition
request itself is additionally bounded (`end_date = as_of.date()`) as a
first, cheap layer. Attacked directly in
`test_future_data_attack_as_of_firewall`.

## Stage Manifest (Phase 8) / Failure Semantics (Phase 9)

7 ordered stages: GOVERNANCE_SETUP, DATA_ACQUISITION,
DATASET_INTEGRITY_CHECK, CANDIDATE_SCAN, TRADE_PLANNING,
POSITION_SIZING, BACKTEST_EVIDENCE. Each stage's own work is wrapped in
`try/except Exception`; any exception short-circuits to a local
`fail_session(...)` closure that builds and persists a FAILED session
with every already-completed stage's own evidence intact, never
fabricating downstream output, never silently retrying. Underlying
exception type/message are always preserved (`failure_type`/
`failure_message`).

## Replay Semantics (Phase 10)

Same as_of/instruments/policies/source bytes under a fresh session
identity produce semantically equivalent decisions (`scan_decision`
sequence, candidate/backtest counts). Per-session derived governance ids
and the dataset artifact's own hash (which embeds the session-derived
`dataset_id`) are identity fields and are not required to match --
exactly as the mission itself permits.

## Final Daily Report (Phase 11) / No Trade Command (Phase 12) / Product Honesty (Phase 13)

`research_session_report_payload()` sections the report into FACT (what
happened), HISTORICAL_EVIDENCE (retrospective-only backtest evidence,
explicitly labeled as not a live claim), DIAGNOSTIC (stage manifest,
failure detail), and LIMITATION (the fixed 5-statement claim-honesty
tuple: not a trading instruction, historical evidence isn't predictive,
backtest results aren't expected profit, the data source may have
limitations, no broker order was submitted). No `place_order`/
`submit_order`/broker-credential/live-execution code exists anywhere in
M070 (confirmed by grep across every new file).

## PostgreSQL (Phase 14)

3 new, additive tables (`research_session`, `research_session_stage`,
`research_session_decision`) reference frozen authorities by governance
id (FK columns), never copy their content. A genuine, pre-existing gap
was found via real integration testing: M057's own `decision_candidate`
CHECK constraint never accounted for M069's own `BarInterval.ONE_DAY`
addition -- M070 is the first capability to persist a daily-granularity
candidate through the frozen M057/M058 pipeline. Fixed with its own
dedicated additive migration (`3b44e3d71f52`), narrowing nothing,
`downgrade()` restoring the original constraint.

## Session Retrieval (Phase 15) / Real CLI Acceptance (Phase 16) / Offline Acceptance (Phase 17)

`empirical-platform-get-daily-research` retrieves a persisted session
without rerunning the pipeline. Canonical real-CLI acceptance: fresh
PostgreSQL, migrate, run the installed CLI with real network, retrieve
through the installed get CLI, compare run/get semantics, inspect raw
SQL directly -- no Python shortcut. The full offline suite (7 of 8
integration tests, all 71 unit tests) runs deterministically with zero
network access; canonical CI never depends on Yahoo availability.

## Multi-Instrument (Phase 18) / Attacks (Phases 19-22)

`test_multi_instrument_session_exercises_several_instruments` and the
canonical real-CLI runs (both the implementation-time run and the
independent second pass) use 2-3 real instruments together, never a
single-ticker demo. Partial-failure, source-tamper, future-data, and
duplicate-session attacks are each covered by a dedicated integration
test (see `external-review/MILESTONE-070/hostile-review-matrix.md`).

## Operator Usability (Phase 23) / Performance (Phase 24) / Observability (Phase 25)

The CLI's own argument names are product-level; an operator never names
a Campaign, Run, EvidencePackage, scan, trade plan, or position plan.
The dataset artifact is parsed exactly once and reused for both window
derivation and the backtest call -- no redundant re-fetch or re-parse.
The stage manifest plus the FACT/DIAGNOSTIC payload sections directly
answer "what ran / what data / what failed / what completed / what
report was produced" without any new logging/metrics/tracing platform.

## Deferred / M070 Boundary

Explicitly out of scope and not built: portfolio capital accounting
(M067) and cross-instrument dependence (M068) wiring into the daily
session, any second real-vendor adapter, live/streaming quotes, any
broker/execution code, any LLM-based decision path. **MILESTONE-071 was
explicitly NOT built, per the mission's own instruction.**
