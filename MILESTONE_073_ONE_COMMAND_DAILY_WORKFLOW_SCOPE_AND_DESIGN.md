# MILESTONE-073 - One-Command Daily Research Workflow - Scope and Design

## Phase 0: Repository Truth

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. Verified
independently via `git fetch origin`, `git rev-parse HEAD`,
`git rev-parse origin/master`, `git rev-list --left-right --count
HEAD...origin/master`, `git status --short`: `HEAD == origin/master ==
f935913157a8fb8a50e01706f178f1c11b929426`, 0 ahead / 0 behind, working
tree clean. `PROJECT_CHECKPOINT.md` confirms
`LATEST_FROZEN_MILESTONE=MILESTONE-072`, `M072_STATUS=APPROVED_AND_FROZEN`,
`M073_STATUS=NOT_STARTED`. Matches the mission's expected lineage
exactly. M072 was not redone or reopened.

## Phase 1: Product Reality Question

"What can an operator actually do with this platform today, from
start to finish, without reading source code, manually connecting
internal milestones, or inventing missing operational steps?"

Answered empirically in Phase 3 below, not assumed.

## Phase 2: Full 40-Area Product Inventory

Every row checked against live source and, where practical, the real
installed product surface this session.

| # | Area | State | Evidence |
|---|---|---|---|
| 1 | Market-data acquisition | PRODUCTION_USABLE | `empirical-platform-acquire-market-data-snapshot` and, more importantly, `run-daily-research`'s own internal use of `YahooFinanceChartMarketDataSource` -- real network fetch confirmed live this session (real 200 responses, real bars) |
| 2 | Dataset authority | PRODUCTION_USABLE | `DatasetSnapshotAuthority`/`dataset_sha256` persisted and shown in every session's own FACT/DATA QUALITY section |
| 3 | Data integrity/hash verification | PRODUCTION_USABLE | `DATASET_INTEGRITY_CHECK` stage, confirmed COMPLETED in the live run |
| 4 | Corporate-action semantics | RESEARCH_USABLE | M065 `corporate_actions.py`/`corporate_action_stress.py` exist and are tested, but not surfaced anywhere in the daily brief |
| 5 | Instrument identity | PRODUCTION_USABLE | `InstrumentMaster` auto-built per session (`build_trivial_instrument_master`) |
| 6 | Historical universe membership | RESEARCH_USABLE | M064 `universe_authority.py`/`historical_universe.py` exist, not wired into daily research |
| 7 | Survivorship-aware mechanics | RESEARCH_USABLE | M064 `survivorship_study.py` exists as a standalone study, not part of the daily path |
| 8 | Strategy evaluation | PRODUCTION_USABLE | Confirmed live: real `evaluate()` ran against real AAPL/MSFT/GOOG bars, honest `NO_TRADE` result |
| 9 | Candidate generation | PRODUCTION_USABLE | `DecisionCandidate` persisted live for all 3 real instruments |
| 10 | Multi-instrument scanning | PRODUCTION_USABLE | `TradingOpportunityScan` (M058) ran live across 3 instruments in one session |
| 11 | Opportunity ranking | PRODUCTION_USABLE | `BREAKOUT_VOLUME_STRENGTH_SUM` ranking model id shown in the live FACT payload |
| 12 | Trade planning | PRODUCTION_USABLE | `TRADE_PLANNING` stage COMPLETED live (0 candidates reached this stage on the live day tested, which is itself an honest, correct outcome) |
| 13 | Risk gating | PRODUCTION_USABLE | `REFERENCE_HIGH_BREAKOUT_RISK_GATE` confirmed wired in the live session |
| 14 | Position sizing | PRODUCTION_USABLE | `EQUITY_PERCENT_RISK_SIZING_GATE` confirmed wired live |
| 15 | Historical execution simulation | RESEARCH_USABLE | M061 backtest evidence attaches to every session (`BACKTEST_EVIDENCE` stage, confirmed live: 39 evaluated opportunities, 1 executed trade) but is retrospective-only, never a live claim |
| 16 | Backtesting | PRODUCTION_USABLE (as a standalone capability) | `empirical-platform-run-historical-backtest` exists and is exercised by every session's own BACKTEST_EVIDENCE stage |
| 17 | Holdout validation | RESEARCH_USABLE | M062 exists as a standalone CLI, not part of the daily path |
| 18 | Walk-forward robustness | RESEARCH_USABLE | M063 exists as a standalone CLI, not part of the daily path |
| 19 | Statistical evidence | RESEARCH_USABLE | M066 exists as a standalone CLI, not part of the daily path |
| 20 | Shared-capital portfolio accounting | RESEARCH_USABLE | M067 `portfolio_study.py` exists, fully tested, zero lineage into daily research (freshly re-confirmed via grep this session, again) |
| 21 | Concurrent-position handling | ABSENT from daily path | No notion of "already-open positions" exists anywhere in the daily session/brief; every session sizes as if starting from flat, every day |
| 22 | Cross-instrument dependence | RESEARCH_USABLE | M068 `portfolio_dependence.py` exists, fully tested, zero lineage into daily research (freshly re-confirmed) |
| 23 | Daily orchestration | PRODUCTION_USABLE | M070's `run-daily-research` -- confirmed live, one real command, real data, real full 7-stage pipeline |
| 24 | Session persistence | PRODUCTION_USABLE | Confirmed live via raw retrieval and `list-daily-research` |
| 25 | Session history | PRODUCTION_USABLE | `list-daily-research` confirmed live, correct chronological ordering |
| 26 | Day-over-day comparison | PRODUCTION_USABLE | Confirmed live: `RESEARCH-1002`'s own brief correctly compared against `RESEARCH-1001` |
| 27 | Operator daily brief | PRODUCTION_USABLE | Confirmed live: real, legible, attention-sectioned brief produced from real data |
| 28 | Data freshness | PARTIAL | `as_of`/`dataset_sha256` shown, but no "as-of vs today" staleness signal (a deliberate M072 boundary, still true) |
| 29 | Data-source reliability | PARTIAL | Exactly one real vendor (Yahoo unofficial endpoint), no fallback; a raw request without a browser User-Agent header returned HTTP 429 during this session's own testing, confirming the endpoint is real, rate-limit-sensitive, and single-point-of-failure -- the shipped adapter already sends a `User-Agent`, mitigating but not eliminating this |
| 30 | Report explainability | PRODUCTION_USABLE | M072 -- rejection reasons, risk evidence, attention levels all confirmed live |
| 31 | Portfolio evidence in daily workflow | ABSENT | Confirmed by grep and live brief inspection -- zero portfolio fields anywhere in the daily brief |
| 32 | Dependence evidence in daily workflow | ABSENT | Same, confirmed |
| 33 | Alerts/attention handling | PRODUCTION_USABLE (in-brief) | M072's `AttentionLevel` + session `WARNING` banner; no external notification channel (email/desktop/webhook), but the mission's own Phase 12 boundary already treats the ATTENTION section itself as the deterministic alert surface |
| 34 | Operational configuration | ABSENT | No persisted operator defaults anywhere; every CLI invocation requires the full argument set from scratch, confirmed by direct grep (no config file, no settings table) and by the live simulation itself, which required retyping the universe, equity, and risk percent for a second command |
| 35 | Failure recovery | PRODUCTION_USABLE | M070's own fail-honestly-and-persist semantics, reused unchanged and re-confirmed working in M072's FAILED-session tests |
| 36 | Usability from one terminal session | PARTIAL | The live simulation required 2 separate commands (`run-daily-research` then `daily-brief`) with a manually-tracked session identifier passed between mental context, not literally between commands (the brief defaults to "latest", which happens to work, but the operator must trust that no other session interleaves) |
| 37 | Real-data readiness | PRODUCTION_USABLE | Confirmed live this session with real AAPL/MSFT/GOOG bars |
| 38 | Paper-trading readiness | ABSENT | No paper account, no simulated order/fill concept anywhere |
| 39 | Live-trading readiness | ABSENT (by design) | No broker integration anywhere in the codebase; explicitly and permanently out of scope |
| 40 | Documentation/operator discoverability | PARTIAL | Each CLI's own `--help`-style usage string exists (`SystemExit` usage message), but there is no single "start here" operator entry point describing the two-command morning routine |

**Phase-1 gate answer, from live evidence, not assumption:** the
operator CAN today run one real command against real data and get one
real, legible research artifact -- M070/M071/M072 genuinely deliver
that. But the *complete* morning routine still requires two separate
commands, run in the right order, with the operator personally
remembering which universe/equity/risk-percent to type each time. That
is real, observed, repeated friction (area #34 and #36), not a
theoretical one.

## Phase 3: Real Daily Workflow Simulation (executed live this session)

Fresh PostgreSQL (`m070-dev-pg`, schema dropped and recreated to
genuinely empty), all 16 migrations applied from empty, then, using
only installed commands and real Yahoo Finance data (no fixtures):

1. `empirical-platform-run-daily-research RESEARCH-1001 2026-08-11 30 <path> 100000 0.01 AAPL MSFT GOOG` -- real network fetch, real evaluation, `COMPLETED`, all 3 instruments `NO_TRADE` (an honest, non-cherry-picked real-world result).
2. `empirical-platform-run-daily-research RESEARCH-1002 2026-08-12 30 <path> 100000 0.01 AAPL MSFT GOOG` -- same, `COMPLETED`, all 3 `NO_TRADE`.
3. `empirical-platform-daily-brief` (default, no args) -- correctly found `RESEARCH-1002`, correctly compared against `RESEARCH-1001`, rendered a legible, sectioned, real brief with genuine rejection reasons (`closing price did not clear the reference high; volume did not exceed the reference average`) and real `dataset_sha256`/`data_source` provenance.
4. `empirical-platform-list-daily-research 10 AAPL MSFT GOOG` -- correct chronological history.

**Where the operator left the product and started doing manual
plumbing:** between steps 1/2 and step 3. The operator had to (a)
invent a fresh, correctly-formatted `RESEARCH-NNNN` identifier by hand
for each day, tracking which numbers were already used; (b) retype the
exact same universe, account equity, and risk percent on every
invocation, from memory, with no persisted default and no cross-check
that today's numbers match yesterday's intent; (c) run a second,
separate command to see the result, trusting (correctly, but only by
convention) that `daily-brief`'s own "latest session" default would
resolve to the session just created and not some other session that
might exist. None of this is a defect in M070/M071/M072 individually
-- each is exactly what it was scoped to be -- but stitched together
end-to-end, it is real, repeated, unnecessary manual work.

## Phase 4: Friction Map

- Must manually invent a fresh session identifier every day (a
  low-level implementation detail -- `RESEARCH-\d{4}` -- leaking into
  daily operator UX).
- Must manually retype universe/equity/risk-percent every single
  invocation; nothing is remembered between days.
- Must run two separate commands to go from "nothing" to "I can see
  today's brief" -- there is no single command a operator can run
  before market open and be done.
- Portfolio (M067) and dependence (M068) evidence exist but are
  completely disconnected from the daily workflow -- confirmed
  ABSENT again, freshly, not merely carried forward from M072's own
  finding.
- Single real data vendor, no fallback -- a real, observed
  reliability edge (a bare request without a User-Agent header was
  rate-limited; the shipped adapter already avoids this specific
  failure, but there is still no secondary source if Yahoo's
  unofficial endpoint changes shape or blocks the platform's own
  User-Agent).
- No scheduling -- confirmed absent by grep; the operator must
  remember to run the workflow at all.
- No saved operator configuration/profile -- confirmed absent.
- No paper-trading loop -- confirmed absent, and per the mission's
  own Phase 7 gate, correctly not yet a candidate (portfolio/risk
  evidence is not yet integrated into the daily workflow, which the
  mission explicitly lists as a precondition).

## Phase 5-6: Candidate Ranking

Criteria: `PRODUCT_VALUE`, `DAILY_OPERATOR_VALUE`, `DEPENDENCY_UNLOCK`,
`ARCHITECTURAL_LEVERAGE`, `EVIDENCE_VALUE`, `IMPLEMENTATION_COST`,
`OPERATIONAL_RISK`, `PREMATURE_COMPLEXITY_RISK`.

| Candidate | PRODUCT_VALUE | DAILY_OPERATOR_VALUE | DEPENDENCY_UNLOCK | ARCHITECTURAL_LEVERAGE | EVIDENCE_VALUE | IMPLEMENTATION_COST | OPERATIONAL_RISK | PREMATURE_COMPLEXITY_RISK | Verdict |
|---|---|---|---|---|---|---|---|---|---|
| **One-command pre-market research workflow** | HIGH | HIGH -- this is literally the morning routine | MEDIUM -- simplifies the foundation every future milestone builds on | HIGH -- zero new business logic, pure composition of two already-frozen usecases (`RunDailyResearchSessionHandler` + `BuildDailyResearchBriefHandler`) | LOW-MEDIUM -- no new evidence type, pure workflow ergonomics | LOW -- one new entrypoint, zero new persistence | LOW | LOW | **SELECTED** |
| M067 portfolio integration into daily brief | MEDIUM | MEDIUM | LOW | LOW -- no genuine session-to-portfolio-study lineage exists; would require inventing a linkage (e.g., "open positions" concept) that doesn't exist yet | MEDIUM | HIGH | MEDIUM -- risk of fabricated/implied linkage | HIGH | REJECTED -- premature; the missing "concurrent-position handling" concept (area #21) is itself a prerequisite gap, not solved by this milestone |
| M068 dependence integration into daily brief | MEDIUM | MEDIUM | LOW | LOW -- dependence studies operate over an explicitly-chosen historical window/universe, not a single session's live candidate set; no clean per-session lineage exists | MEDIUM | HIGH | LOW | HIGH | REJECTED -- same lineage gap as M067; forcing a linkage would misrepresent a historical study as live evidence |
| Persistent operator research configuration | MEDIUM | MEDIUM-HIGH | LOW | MEDIUM -- needs new persistence (a settings table) or a config file, a genuinely new architectural surface | NONE | MEDIUM | LOW | MEDIUM -- explicit mission warning against "a generic settings platform" | REJECTED as a standalone milestone; its most valuable slice (sensible defaults so the operator stops retyping) is absorbed into the selected candidate's own CLI defaults, at far lower cost |
| Data-source fallback/reliability | MEDIUM | LOW-MEDIUM -- the live simulation succeeded without incident | LOW | MEDIUM | LOW | HIGH -- a second real vendor adapter plus equivalence-checking, per the mission's own Phase 10 minimum-architecture requirement | MEDIUM | MEDIUM | REJECTED for this milestone -- real, but not the sharpest, most-repeatedly-observed friction; disproportionate cost for the evidence gathered |
| Meaningful alerts/change notifications | LOW-MEDIUM | LOW-MEDIUM | LOW | LOW -- would need a new delivery channel (email/desktop/webhook) | LOW -- mostly redundant with M072's own `AttentionLevel`/`session_warnings`, which already function as the deterministic alert surface | MEDIUM | LOW | MEDIUM | REJECTED -- the alert *evidence* already exists (M072); a delivery channel is a distinct, lower-priority concern |
| Session trend/history summaries beyond M071 | LOW | LOW-MEDIUM | LOW | MEDIUM | LOW | MEDIUM | LOW | LOW | REJECTED -- narrow enhancement, lower daily value than the selected candidate |
| Automatic daily universe selection | MEDIUM | MEDIUM | LOW | LOW -- needs a persisted watchlist/candidate-universe concept that does not exist | LOW | HIGH | MEDIUM | HIGH | REJECTED -- real value but disproportionate cost and scope-creep risk for one milestone |
| Report artifact/export | LOW | LOW | LOW | LOW | NONE | MEDIUM | LOW | MEDIUM | REJECTED -- already explicitly deferred as premature in M072; still true, nothing changed |
| Paper-trading simulation | evaluated per mission Phase 7 | -- | -- | -- | -- | -- | -- | -- | REJECTED for M073 -- the mission's own gate requires portfolio/risk evidence to be sufficiently integrated into daily research first (area #31/#32 = ABSENT); selecting it now would violate the mission's own stated precondition |

**Selection: One-Command Pre-Market Research Workflow.** It is the
only candidate directly supported by friction *observed while actually
running the product this session*, not inferred from reading source.
It satisfies the Product Value Rule (Phase 6) on multiple axes at
once: it reduces manual work (no more hand-invented session ids, no
more retyped defaults, no more second command), and it makes the
system more reliably runnable end-to-end. It introduces zero new
business logic and zero new persistence, matching Phase 14/16's
minimal-architecture mandate as closely as any candidate this audit
found.

## Phase 7: Paper-Trading Boundary -- Explicitly Not Selected

Per the mission's own Phase 7 gate, paper trading requires "portfolio/
risk evidence sufficiently integrated" into daily research. This
audit freshly re-confirmed (area #31/#32) that it is not. Paper
trading is therefore correctly rejected for M073, not merely because
it "sounds like the next logical milestone."

## Phase 15: Selected-Capability Design

**Product problem.** An operator's real morning routine currently
requires two separate commands, a hand-invented session identifier,
and fully re-typed universe/equity/risk-percent inputs every day, with
no persisted defaults.

**Before/after.**
- Before: `empirical-platform-run-daily-research RESEARCH-1042
  2026-08-13 20 /tmp/x.json 100000 0.01 AAPL MSFT GOOG` (operator must
  invent `RESEARCH-1042` and remember it was not used before), then
  separately `empirical-platform-daily-brief`.
- After: `empirical-platform-daily-workflow AAPL MSFT GOOG` -- one
  command, sensible defaults for everything else (today's date, a
  20-day lookback, $100,000 equity, 1% risk), auto-generated session
  identity, immediate brief output. Every default remains overridable
  via explicit flags.

**Authoritative inputs.** Exactly the same real, frozen M057-M072
evidence chain the two existing commands already use --
`RunDailyResearchSessionHandler` (M070, unmodified) and
`BuildDailyResearchBriefHandler` (M072, unmodified). No new evidence
source.

**Domain model.** None. This capability is pure composition-root
orchestration -- there is no new domain concept, no new aggregate, no
new value object.

**Application capability.** None new either, in the `usecases/` sense
-- the entrypoint composes two already-existing usecase handlers
directly, exactly mirroring how `run_daily_research_session.py`'s own
entrypoint and `build_daily_research_brief.py`'s own entrypoint each
already compose their own single handler. The only genuinely new code
is entrypoint-level: default resolution (today's date via
`SystemWallClock`, fixed sensible numeric defaults) and a tiny, pure,
independently-testable random session-governance-id generator.

**Persistence need.** None. Zero new tables, zero new migrations. The
random session id relies on the research_session table's own existing
`governance_id` uniqueness constraint as the honest collision
backstop -- identical in spirit to the already-established
`_derived_governance_id` precedent (M070's own docstring: "a residual
collision probability remains inherent... `AggregateAlreadyExists` is
the honest, disclosed backstop, never silently swallowed").

**CLI/product UX.** New console script `empirical-platform-daily-workflow`:

```
usage: empirical-platform-daily-workflow [--json]
    [--as-of YYYY-MM-DD] [--lookback-days N]
    [--account-equity X] [--risk-percent X]
    <symbol> [symbol ...]
```

At least one symbol is required; every other input has a sensible,
documented, overridable default. Prints the resulting brief (text by
default, `--json` for machine output) -- the same two renderers M072
already built, unchanged.

**Failure semantics.** `RunDailyResearchSessionHandler.handle()`
already never raises past the persist point (M070's own frozen
guarantee) -- any failure, including a session-id collision at
`GOVERNANCE_SETUP`, becomes an honestly-FAILED, fully-persisted
session. The workflow entrypoint always proceeds to build and print a
brief for whatever session resulted, success or failure -- M072's
brief already renders a `WARNING` banner for a FAILED session. No new
failure-handling logic is introduced; the existing chain's own honesty
guarantees are simply exercised end-to-end without an operator-visible
seam.

**Deterministic behavior.** The only non-deterministic element is the
random 4-digit session-id suffix (a UI/identity convenience, not a
business-logic input) and, when `--as-of` is omitted, today's real
date. Given the same explicit `--as-of` and inputs, the research and
brief content is exactly as deterministic as the two commands it
composes already are.

**Auditability.** Unchanged -- every governance id, stage, and
provenance field the two composed commands already produce is
preserved verbatim; the workflow adds no new opacity.

**Limitations.** Carries the same M070/M072 claim-honesty tuple,
unmodified. Does not add scheduling, does not add a saved
configuration profile, does not add a second data vendor, does not
touch M067/M068.

**Explicit non-goals.** No operator configuration persistence, no
scheduling/cron, no data-source fallback, no portfolio/dependence
integration, no paper trading, no alerting delivery channel. Each was
evaluated and explicitly rejected above, not silently skipped.

## Phase 16: Minimal Architecture

One new file: `entrypoints/run_daily_research_workflow.py`. No new
usecase module, no new domain module, no new migration, no new
repository method. This is the smallest architecture-consistent
implementation available for the selected capability.

## Deferred / M073 Boundary

Explicitly out of scope and not built: M067/M068 daily integration
(gated on a "concurrent-position handling" concept that does not yet
exist), operator configuration persistence, data-source fallback,
automatic universe selection, alert delivery channels, session-trend
summaries, report export, paper trading, live trading.
**MILESTONE-074 is explicitly NOT built as part of this mission.**
