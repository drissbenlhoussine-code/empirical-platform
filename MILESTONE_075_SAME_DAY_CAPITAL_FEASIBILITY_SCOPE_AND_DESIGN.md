# MILESTONE-075 — Same-Day Capital Feasibility for the Daily Research Brief — Scope and Design

## Status: IMPLEMENTATION CANDIDATE — NOT OWNER FROZEN

## 1. Repository Authority

Verified independently at mission start, not taken from the mission text:

| Fact | Value |
|---|---|
| `origin/master` | `9b427594814e3eda9fb8b598aa7119349dcbd581` |
| ahead / behind | 0 / 0, working tree clean |
| `LATEST_FROZEN_MILESTONE` | `MILESTONE-074` |
| `M074_STATUS` | `APPROVED_AND_FROZEN` |
| `M074_OWNER_FREEZE_COMMIT` | `64c5327` |
| `M075_STATUS` | `NOT_STARTED` |
| `M063_STATUS` | `APPROVED_AND_FROZEN` (exceptional reconciliation record present) |
| M075 files present | none |

## 2. The Product Limitation M075 Closes

**The daily brief can hand the operator a set of position plans that is collectively
infeasible under the platform's own capital policy, and say nothing about it.**

This is not a hypothesis. It is arithmetic over two frozen policies:

- **M060 `SizingPolicy`** sizes *each* position plan independently, capped at
  `maximum_notional_percent = 0.25` of `supplied_account_equity`. Every plan in a
  session is sized against the *same, full* equity number. `build_position_plan()`
  takes no argument describing any other position.
- **M067 `PortfolioCapitalPolicy`** — already frozen, already used by this platform for
  its own historical evidence — caps total exposure at
  `max_capital_utilization_percent = 1.00` and `max_concurrent_positions = 10`, and
  carries a closed rejection vocabulary for exactly this situation.

Measured consequence at the shipped defaults (`$100,000` equity):

| Approved plans in one session | Maximum combined notional | Verdict under M067's own policy |
|---|---|---|
| 2 | 50% | ok |
| 3 | 75% | ok |
| 4 | 100% | at the limit |
| **5** | **125%** | **exceeds capital** |
| 8 | 200% | exceeds capital |
| 10 | 250% | exceeds capital |

`grep` confirms the daily path performs no aggregation whatsoever: no `sum(`, no
total notional, no total risk, and no capital policy anywhere in
`build_daily_research_brief.py` or `daily_research_brief.py`. The brief renders each
plan's own `position_notional` and `actual_risk` in isolation.

So the platform already *knows* how to reason about concurrent capital — it does so
correctly in M067, for history — and does not apply that reasoning to the one artefact
a human actually acts on each morning.

## 3. Fresh Capability Inventory

Repository-grounded, from source rather than milestone prose.

| # | Capability | Verdict | Evidence |
|---|---|---|---|
| A | Market-data acquisition | PRODUCTION_USABLE | M069 real Yahoo adapter, live-network integration test |
| B | Dataset authority / integrity | STRONG_RESEARCH_CAPABILITY | sha256 seals, `dataset_snapshot`, tamper tests |
| C | Instrument identity | STRONG_RESEARCH_CAPABILITY | `instrument_master`, `InstrumentId` resolution |
| D | Universe membership / history | STRONG_RESEARCH_CAPABILITY | M064 `membership`, `universe_authority` |
| E | Corporate-action mechanics | STRONG_RESEARCH_CAPABILITY | M065 adjusted/raw snapshots |
| F | Candidate generation | PRODUCTION_USABLE | M057 `candidate`, `strategy`, `ranking` |
| G | Trade planning | PRODUCTION_USABLE | M059 `trade_plan` with geometry gate |
| H | Risk evaluation | PRODUCTION_USABLE | M059 reward/risk, reason codes |
| I | Position sizing | PARTIAL | M060 sizes each plan **in isolation**; no cross-plan capital view |
| J | Historical backtesting | STRONG_RESEARCH_CAPABILITY | M061 |
| K | Holdout validation | STRONG_RESEARCH_CAPABILITY | M062 |
| L | Walk-forward robustness | STRONG_RESEARCH_CAPABILITY | M063, 10 windows |
| M | Portfolio historical evidence | STRONG_RESEARCH_CAPABILITY | M067 concurrent-position simulation |
| N | Cross-instrument dependence | STRONG_RESEARCH_CAPABILITY | M068 |
| O | Daily orchestration | PRODUCTION_USABLE | M070 + M073 one command |
| P | Multi-day continuity | PARTIAL | M071 compares *decisions* only; no capital/exposure continuity |
| Q | Operator-facing reporting | PRODUCTION_USABLE | M072 brief, text + JSON |
| R | Historical evidence discoverability | PRODUCTION_USABLE | M074 |
| S | Current portfolio awareness | ABSENT | no holdings concept anywhere outside M067's simulation |
| T | Durable position state | ABSENT | `PositionPlan` is a terminal verdict; no lifecycle, no open/closed |
| U | Paper-trading readiness | ABSENT | gated on S and T |
| V | Simulated execution / fills | ABSENT for the daily path (M067 simulates fills historically only) |
| W | P&L / equity continuity | ABSENT | equity is a CLI number re-supplied every day |
| X | Scheduling / automation | ABSENT | no cron/scheduler anywhere |
| Y | Failure recovery / idempotency | PARTIAL | sessions record FAILED stages; no resume |
| Z | Observability / auditability | FOUNDATION_ONLY | `audit/` and `governance/` packages are empty `__init__` only |
| AA | Real-world operator usability | PARTIAL | one command exists; **no aggregate capital view — this milestone** |
| AB | Reproducibility across clean envs | PARTIAL | M062/M064/M065 CRLF seal debt; 8 failures + 12 errors on a clean LF checkout |
| AC | Deployment / runtime readiness | FOUNDATION_ONLY | no Dockerfile, no service unit; scripts are PowerShell-only |
| AD | Live-trading readiness | ABSENT | and deliberately so |

## 4. Candidate Ranking

Five serious candidates, each answering the ten required questions in condensed form.

### C1 — Same-Day Capital Feasibility for the Daily Brief **(SELECTED)**

Operator problem: the brief recommends N positions that may collectively exceed
available capital, with no warning. Currently forces manual work: the operator must
hand-total notionals every morning and mentally apply a capital limit. Unlocks: frozen
M067 `PortfolioCapitalPolicy` reasoning, applied to today's own set. New capability:
yes — no aggregate capital view exists anywhere in the daily path. Honestly
implementable: yes, entirely from data the brief already loads. Preserves frozen
architecture: yes, purely additive, no schema. Moves toward credible evaluation: yes —
it is the smallest honest precondition for any future position-state or paper-trading
milestone. Risks: low; pure computation, no I/O, no state. Dependencies: none beyond
M060/M067/M072 (all frozen). Tempting adjacent scope to reject: durable position state,
open-position tracking, cross-day exposure, execution, paper trading.

### C2 — Durable Position State / PositionBook

Would close S, T, and unlock U. **Rejected for M075**: it requires a genuinely new
aggregate, new schema, a lifecycle state machine, fill semantics, and a defensible
answer to "what is a position when nothing was ever executed?" That is a large,
irreversible architectural commitment. Critically, it is *harder to do honestly* before
C1 exists: a position book whose entries were sized by a policy that never checked
aggregate capital would encode the same defect durably. C1 is its precondition, not its
competitor.

### C3 — Repair the M062/M064/M065 CRLF seal debt

Would move AB from PARTIAL toward PRODUCTION_USABLE. **Rejected as the M075 headline**:
it is remediation, not product capability. It touches three frozen milestones and needs
its own owner authorization (as the M063 record itself states). Assessed against the
mission's explicit test — does it block M075? — the answer is **no**: see Section 11.
Recorded as known debt, untouched.

### C4 — Scheduling / unattended daily automation

Would close X. **Rejected**: automating a workflow whose output can be collectively
infeasible amplifies the C1 defect rather than fixing it. Correctness before cadence.

### C5 — Observability / audit trail

Would move Z off FOUNDATION_ONLY. **Rejected**: valuable but not the sharpest gap; the
daily product's *substance* is the weaker link, and there is no operator pain today that
an audit trail relieves.

### Ranking

| Criterion (1–5) | C1 | C2 | C3 | C4 | C5 |
|---|---|---|---|---|---|
| Product leverage | 5 | 5 | 1 | 2 | 2 |
| Evidence value | 4 | 3 | 2 | 1 | 3 |
| Architectural fit | 5 | 2 | 3 | 3 | 4 |
| Implementation risk (5 = lowest) | 5 | 1 | 2 | 3 | 4 |
| Operator usefulness | 5 | 4 | 1 | 3 | 2 |
| Dependency unlock | 5 | 4 | 2 | 1 | 2 |
| Scientific honesty | 5 | 3 | 4 | 2 | 4 |
| Future optionality | 5 | 3 | 2 | 2 | 3 |
| **Total** | **39** | **25** | **17** | **17** | **24** |

## 5. Selected Capability

**M075 — Same-Day Capital Feasibility.**

The daily brief gains a `SAME-DAY CAPITAL FEASIBILITY` section that takes the session's
*own* approved position plans, applies one explicit capital policy, admits them in a
deterministic priority order, and reports exactly which plans fit, which do not, and why.

## 6. Architecture Placement

| Layer | Change |
|---|---|
| `decision_candidate/same_day_capital_feasibility.py` | **new**, pure, I/O-free: the assessment rule and its value objects |
| `decision_candidate/daily_research_brief.py` | additive optional field, defaulted — same pattern M074 used |
| `usecases/build_daily_research_brief.py` | collects sizing facts already loaded; calls the pure rule |
| `usecases/daily_research_brief_io.py` | text + JSON rendering |
| `entrypoints/build_daily_research_brief.py`, `run_daily_research_workflow.py` | `--no-capital-feasibility` |

No new aggregate. **No new table. No migration. No new repository. No new I/O.** The
inputs are already fetched by the existing brief handler.

Reused rather than duplicated:
- **`PortfolioCapitalPolicy`** (M067, frozen) — a pure constraint value object; reusing it
  keeps one definition of "capital limits" in the repository.
- **`PortfolioRejectionReason`** (M067, frozen) — its members are exactly the reasons that
  arise here.

Deliberately **not** reused: `PortfolioAllocationOutcome`. Its `ALLOCATED` member asserts
that capital *was allocated*. M075 allocates nothing. M075 owns a separate, honest
vocabulary: `FITS_WITHIN_CAPITAL` / `EXCEEDS_CAPITAL`.

## 7. Temporal and State Semantics

The mission requires these be kept distinct. M075 introduces a **fourth** category and
must not be confused with the other three:

| Category | Meaning | Status in this repository |
|---|---|---|
| `STATE_AT(t)` | what the operator actually holds at time t | **ABSENT** — M075 does not create it |
| `EVENT_AFTER(t)` | fills, executions, closes after t | **ABSENT** — M075 does not create it |
| `HISTORICAL_EVIDENCE_AVAILABLE_AT(t)` | prior research evidence visible at t | M074 |
| `RECOMMENDATION_SET_FEASIBILITY_AT(t)` | **M075** — is *this one session's own* approved set collectively satisfiable under one explicit capital policy? | new |

`RECOMMENDATION_SET_FEASIBILITY_AT(t)` is a pure function of the session's own plans plus
a policy. It reads no state outside the session, no prior day, and no market data after
`as_of`. There is therefore no future-data channel, no cross-day contamination channel,
and no portfolio-state channel — because there is no such input at all.

## 8. Deterministic Semantics

- **Admission order:** `(rank ascending, then instrument_symbol ascending)`. `rank` is the
  session's own operator-facing priority; symbol breaks ties. Plans with `rank = None` sort
  after all ranked plans, then by symbol. Fully deterministic, no set iteration.
- **Equity:** each `PositionPlan` carries `supplied_account_equity`. Within one session
  these are normally identical. If they differ, M075 uses the **minimum** (conservative)
  and emits an explicit inconsistency limitation. It never averages and never picks
  arbitrarily.
- **Admission rule**, applied in order, per plan:
  1. if admitted count already equals `max_concurrent_positions` → `MAX_CONCURRENT_POSITIONS`
  2. else if `committed + notional > capital × max_capital_utilization_percent` → `MAX_CAPITAL_UTILIZATION_EXCEEDED`
  3. else admit and add to committed
  A plan that does not fit does **not** block later, smaller plans from being assessed;
  each is evaluated against remaining capacity in order. This is stated explicitly because
  it is a real design choice, not an accident.
- **Decimal arithmetic only.** No float anywhere in the rule.
- **Replay:** identical session → identical result, since the rule is pure.

## 9. Failure and Empty-State Semantics

| Situation | Behaviour |
|---|---|
| session not COMPLETED | no assessment; section states it is unavailable, not "feasible" |
| zero approved plans | explicit `no approved position plans` state — never rendered as a pass |
| equity ≤ 0 or absent | assessment withheld with an explicit reason |
| plan missing sizing | that plan is excluded and named in the limitations |
| inconsistent equity across plans | minimum used, inconsistency named |
| `--no-capital-feasibility` | the assessment is not computed at all, and the section says so |

Absence is never silently rendered as success. This mirrors M074's own
`discovery failed ≠ confirmed absence` discipline.

## 10. Evidence and Test Strategy

- Pure unit tests over the rule: ordering, ties, concurrency cap, utilisation cap,
  boundary equality, zero/negative equity, empty set, inconsistent equity, Decimal
  exactness, replay determinism.
- Usecase tests: brief built with and without the assessment.
- Rendering tests: text and JSON carry the *same* verdicts.
- PostgreSQL integration: a real session whose approved plans exceed capital, proving the
  brief reports it end-to-end through the real application boundary and the real CLI.
- A regression test for every genuine defect found in adversarial review.

## 11. M062 / M064 / M065 Seal Debt — Blocking Assessment

Required by the mission before touching or ignoring it.

M075 introduces **no fixture, no dataset bundle, and no byte seal**. Its tests are
constructed in-memory from typed domain objects. It reads no file whose bytes are hashed.

Therefore the CRLF/LF debt **does not block M075**: not its capability, not its tests, not
CI (which runs `windows-latest`), not its reproducibility. Per the mission's own rule, it
is documented as known debt and **left alone**. No M062/M064/M065 file is touched.

## 12. What M075 Proves — and What It Does Not

**Proves:** that a given session's approved position plans either do, or do not,
collectively satisfy one explicit, versioned capital policy — and, when they do not,
exactly which plans exceed it and why.

**Does not prove, and must never be read as:** that any position was taken, that the
operator holds anything, that capital was allocated or reserved, that prior-day positions
were considered, that any trade is profitable, that execution is realistic, or that the
system is ready for live or paper trading. It is a `DIAGNOSTIC` over a
`RECOMMENDATION_SET`, nothing more.

## 13. Out of Scope

Durable position state; open-position tracking; cross-day exposure; cash ledger; margin;
leverage; fills; execution simulation in the daily path; P&L continuity; paper trading;
live trading; broker integration; scheduling; M067/M068 recomputation; any repair of the
M062/M064/M065 seal debt; any new PostgreSQL table.

## 14. M076 Boundary

M075 deliberately stops at "is today's recommended set feasible". The natural successor —
**durable position state**, so that feasibility can account for what is already held — is
recommendation only and is **NOT** built here.

## 15. Acceptance Criteria

1. A session whose approved plans exceed capital is reported as exceeding, with per-plan
   reasons, in both text and JSON.
2. A session whose plans fit is reported as fitting, with utilisation shown.
3. Zero approved plans renders an explicit empty state, not a pass.
4. `--no-capital-feasibility` suppresses computation on both daily paths.
5. Deterministic across replays and independent of input ordering.
6. No new table, no migration, no frozen semantic change.
7. Full canonical gates pass with the coverage floor unchanged.

## 16. PRIMARY-AGENT ADVERSARIAL DESIGN REVIEW

Run against this design before any code was written. This is my own attack on my own
design; it is **not** an independent review.

| # | Attack | Verdict |
|---|---|---|
| D01 | `rank` is `int \| None`; a None rank breaks sorting | **FIXED** — None ranks sort after all ranked plans, then by symbol |
| D02 | Duplicate ranks give nondeterministic order | **FIXED** — symbol is the explicit tiebreak |
| D03 | Set/dict iteration leaks nondeterminism | PASS — inputs are tuples, sorted explicitly |
| D04 | Float rounding in capital arithmetic | PASS — `Decimal` only, no float anywhere in the rule |
| D05 | Exact-boundary spend is wrongly rejected | **FIXED** — comparison is strict `>`, so exactly 100% utilisation admits; a dedicated boundary test is mandatory |
| D06 | Reusing `PortfolioAllocationOutcome.ALLOCATED` would claim capital was allocated | **FIXED** — M075 owns `FITS_WITHIN_CAPITAL` / `EXCEEDS_CAPITAL`; only the *reason* vocabulary is reused |
| D07 | A rejected position plan consumes capital | PASS — only `APPROVED_POSITION_PLAN` plans are considered |
| D08 | Future data leaks in | PASS — the rule has no market-data, no date, and no cross-day input at all |
| D09 | Prior-day positions silently assumed absent | **FIXED** — stated explicitly as a limitation on every rendering, not merely in this document |
| D10 | The capital base is presented as a real account balance | **FIXED** — it is the operator-supplied `supplied_account_equity`, and the rendering must say so |
| D11 | Plans in one session carry different equity | **FIXED** — minimum is used (conservative), inconsistency named explicitly; never averaged |
| D12 | Zero or negative equity produces a nonsense verdict | **FIXED** — assessment withheld with an explicit reason |
| D13 | Zero approved plans renders as "feasible" | **FIXED** — distinct empty state; absence is never a pass |
| D14 | An approved plan with no sizing is silently dropped | **FIXED** — excluded *and* named in limitations |
| D15 | A FAILED session gets a confident feasibility verdict | **FIXED** — gated on COMPLETED, mirroring M074 |
| D16 | Text and JSON could disagree | PASS by construction — both render one computed result; a parity test is mandatory |
| D17 | Adding a parameter breaks frozen M072/M074 callers | PASS — new parameter is keyword-only with a default, exactly M074's own pattern |
| D18 | A frozen M067 file must be modified to reuse its types | PASS — import only; zero bytes of M067 change |
| D19 | New table or migration sneaks in | PASS — the result is derived at brief-build time; no persistence |
| D20 | A big plan blocks all later smaller plans | **ACCEPTED AND DOCUMENTED** — each plan is assessed in priority order against remaining capacity; a later smaller plan can still be admitted. This is a deliberate choice, stated in Section 8, not an accident |
| D21 | Currency is assumed | **FIXED** — the session carries no currency; the policy's `USD` default is used and the assumption is stated |
| D22 | Concurrency cap of 10 is invented by M075 | PASS — it is M067's own frozen default, reused rather than originated, and labelled as such |
| D23 | The milestone introduces a byte seal and inherits the CRLF debt | PASS — M075 has no fixture and no hashed file (Section 11) |
| D24 | The section could be read as investment advice | **FIXED** — explicit banner naming it a diagnostic over a recommendation set |

Every **FIXED** item above was corrected in this document *before* implementation began.
