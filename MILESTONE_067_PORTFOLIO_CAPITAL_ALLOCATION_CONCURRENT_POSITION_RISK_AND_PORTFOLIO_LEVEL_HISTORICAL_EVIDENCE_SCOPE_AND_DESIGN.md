# MILESTONE-067 - Portfolio Capital Allocation + Concurrent Position Risk + Portfolio-Level Historical Evidence - Scope and Design

## 1. Repository Authority

`git fetch origin` confirmed `HEAD == origin/master` at `3ca8a65` (M066
owner-freeze-commit-hash record) with 0 ahead / 0 behind before any M067
work began. `PROJECT_CHECKPOINT.md` confirmed
`LATEST_FROZEN_MILESTONE=MILESTONE-066`,
`M066_STATUS=APPROVED_AND_FROZEN`, `M067_STATUS=NOT_STARTED`.

## 2. Fresh Inventory (Phase 2)

A live-repository search for `portfolio`/`capital allocation`/`cash
ledger`/`equity curve`/`concurrent positions`/`exposure`/`position
overlap`/`portfolio drawdown`/`portfolio PnL`/`gross/net exposure`/
`capital utilization`/`allocation rejection`/`risk budget`/`portfolio
risk`/`correlation`/`strategy aggregation` found:

- **ABSENT everywhere**, confirmed explicitly by `position_plan.py`'s
  own module docstring: "Deliberately not an Account or Portfolio
  aggregate... No account, portfolio, cash-ledger, margin, or leverage
  concept is introduced -- `account_equity` is a plain caller-supplied
  number." M060's position sizing gate reasons about one trade in
  isolation against a caller-supplied equity figure; it has never
  modeled a shared, stateful capital pool across multiple concurrent
  positions.
- **FROZEN and reused verbatim**: `HistoricalBacktestTrade.risk_amount`
  (M061, the pre-computed dollar risk of one position, already gated by
  M060's own sizing policy) and `HistoricalBacktestTrade.scan_rank`
  (M058's own frozen ranking-model conviction) are the two upstream
  fields M067 reuses as, respectively, the capital a position commits
  and the tie-break priority when several opportunities compete for
  that capital at the same instant.

M067 is therefore genuinely new capability, not a duplication of
anything frozen.

## 3. Core Boundary (Phase 3)

Historical research only. No broker, live orders, exchange connectivity,
real money, paper-broker integration, HTTP market execution, LLM trade
decisions, portfolio optimizer, mean-variance optimizer, Kelly
optimization, parameter tuning, strategy selection, or dynamic strategy
mutation. M067 evaluates already-frozen trade opportunities under one
explicit, predeclared capital policy -- it never re-runs, re-ranks,
re-sizes, or re-optimizes anything upstream.

## 4. Capital Authority (Phase 4)

`PortfolioCapitalPolicy`: `initial_capital`, `currency`,
`max_concurrent_positions`, `max_capital_utilization_percent`, plus
`policy_id`/`version` for exact lineage. No hidden defaults --
`DEFAULT_PORTFOLIO_CAPITAL_POLICY` is one explicit, named, fully-typed
constant ($100,000 / USD / 10 positions / 100% utilization), never a
bare literal at the point of use.

## 5. Portfolio Clock / Event Ordering (Phase 5)

A global, deterministic event timeline: every opportunity contributes
one OPEN event (at `entry_timestamp`) and one CLOSE event (at
`exit_timestamp`). Same-timestamp tie-break, in order:

1. A **different** opportunity's CLOSE (priority 0) is processed before
   any OPEN (priority 1) at the same instant, so capital freed by an
   exit is available to a same-instant competing entry.
2. Simultaneous OPENs are ordered by ascending `scan_rank` (the
   opportunity's own frozen upstream ranking-model conviction -- reused,
   never a new alpha model), tie-broken by `(instrument_symbol,
   trade_sequence)`.
3. A **zero-duration** opportunity's own self-close (`entry_timestamp ==
   exit_timestamp`) is priority 2 -- strictly after all priority-1 opens
   at that instant, since a position cannot close before it opens, and a
   position genuinely, if briefly, occupies capital during its own
   instant.

The full event list is computed once, up front, purely from immutable
historical data -- never caller input order -- then replayed strictly in
order with no lookahead.

## 6. Concurrent-Position Semantics (Phase 6)

At every OPEN/CLOSE event: `open_position_count`, `occupied_capital`
(sum of `risk_amount` for currently open positions), `available_capital`,
and `equity` (realized-PnL-only: `initial_capital + cumulative realized
PnL`) are all tracked and persisted as a `PortfolioEquityObservation`.
No mark-to-market price is invented for open positions -- occupied
capital is reported honestly as the exposure figure the frozen data can
actually support, never a fabricated unrealized-PnL estimate.

## 7. Capital Competition / Rejection Semantics (Phases 7-8)

When an OPEN event's own opportunity cannot be funded, it is REJECTED
with exactly one of three closed-vocabulary reasons:
`INSUFFICIENT_AVAILABLE_CAPITAL`, `MAX_CONCURRENT_POSITIONS`,
`MAX_CAPITAL_UTILIZATION_EXCEEDED`. Every candidate opportunity --
allocated or rejected -- is persisted; nothing is silently dropped.

## 8. No Double-Spending (Phase 9)

Capital is reserved (`available -= risk_amount`, `occupied +=
risk_amount`) only at a successful OPEN and released (`available +=
reserved + net_pnl`, `occupied -= reserved`) only at that same
position's own CLOSE event -- never shared, never double-counted.
Aggressively attacked in the hostile review and the independent second
pass (see below); no violation found under either generous or
deliberately stressed capital.

## 9. Capital Release (Phase 10)

Capital becomes reusable only at the position's own real, already-known
`exit_timestamp` -- never early, never using any other opportunity's
future data. Proven directly by the `test_acceptance_control_capital_release`
acceptance control on real fixture data.

## 10-15. Equity Curve, Exposure, Concentration, Drawdown, Sensitivity

`PortfolioEvidenceReport` persists: allocation/rejection counts (with a
reason breakdown), `ending_capital`/`realized_pnl`/
`portfolio_return_percent`, `peak_equity`/`max_drawdown` (a true
peak-to-trough figure over the realized equity sequence, never a naive
sum of individual-trade drawdowns), `max_concurrent_positions_observed`/
`average_concurrent_positions` (time-weighted), `peak_occupied_capital`/
`peak_capital_utilization_percent`, largest instrument/position/window
PnL contributions, and exactly 3 predeclared capital-sensitivity
scenarios (`CANONICAL`, `REDUCED_CAPITAL`, `TIGHTER_MAX_CONCURRENCY`) --
diagnostic only, never altering the canonical result, never searched for
a favorable outcome.

## 16. Domain Model (Phase 19)

Kept deliberately small: `PortfolioCapitalPolicy`,
`PortfolioAllocationDecision` (doubles as the position record for
allocated opportunities -- a position is simply an allocation decision
that succeeded, avoiding a second near-duplicate structure per this
phase's own "keep it small" instruction), `PortfolioEquityObservation`,
`CapitalSensitivityView`, `PortfolioEvidenceReport`. One new domain
module (~700 lines), zero generic asset-management framework.

## 17. Upstream Authority (Phase 18)

Every `PortfolioEvidenceReport` copies its full lineage
(`dataset_bundle_id`/`sha256`, `universe_id`, `membership_manifest_hash`,
`strategy_id`, `ranking_model_id`, `risk_policy_id`, `sizing_policy_id`,
and versions) verbatim from the source M064
`SurvivorshipAwareRobustnessStudy`, identical in structure to M066's own
lineage binding. A report bound to a nonexistent or tampered upstream
study is rejected via `AggregateNotFound` before any allocation
computation.

## 18. PostgreSQL (Phase 20)

Four purely additive tables: `portfolio_study`,
`portfolio_allocation_decision`, `portfolio_equity_observation`,
`portfolio_capital_sensitivity`. Answers every question the mission
poses via raw SQL: which capital policy produced this study, which
opportunities were allocated/rejected and why, when was capital
occupied/released, the resulting equity/drawdown, and the exact upstream
evidence lineage.

## 19. Application + Real CLI (Phase 21)

`empirical-platform-run-portfolio-historical-evidence` /
`empirical-platform-get-portfolio-historical-evidence`. No HTTP.

## 20. What M067 PROVES

That shared capital is accounted for deterministically across
genuinely concurrent, overlapping real historical trade opportunities,
without double-spending or future-data leakage -- proven via a hostile
review (75 cases, 2 genuine defects found and fixed) and an independent
second pass on fresh infrastructure that directly, aggressively
attempted (and failed) to falsify the no-double-spending claim, both
under generous and under deliberately stressed real capital.

## 21. What M067 DOES NOT PROVE

Does not prove the strategy is profitable. Does not prove the capital
policy used is optimal -- it evaluates one predeclared policy (plus 3
predeclared sensitivity variants) honestly, never searches for a
favorable one. Does not execute live money. Does not certify the
canonical capital policy will bind under real market conditions -- the
real M064 fixture's own risk amounts are small enough relative to the
default $100,000 pool that the canonical run shows zero rejections, an
honest, unremarkable result reported as-is.

## 22. Out of Scope

Mean-variance / Kelly / any portfolio optimizer, correlation-aware
sizing, margin/leverage, multi-currency conversion, any change to
strategy/ranking/risk/sizing code, any HTTP transport, any
broker/execution code.

## 23. Status

`APPROVED_AND_FROZEN` -- see
`MILESTONE_067_PORTFOLIO_CAPITAL_ALLOCATION_CONCURRENT_POSITION_RISK_AND_PORTFOLIO_LEVEL_HISTORICAL_EVIDENCE_MACRO_MILESTONE_FREEZE.md`.
