# MILESTONE-077 — Portfolio-Aware Capital Feasibility — Scope and Design

## Status: IMPLEMENTATION CANDIDATE — NOT OWNER FROZEN

## 1. Repository Truth

Verified from repository objects at mission start, not from the mission text.

| Fact | Value |
|---|---|
| `master` HEAD | `e05cb2fae0544bb7f427bb686e9a37522f3936ad` |
| `LATEST_FROZEN_MILESTONE` | `MILESTONE-076` |
| `M075_STATUS` / `M076_STATUS` | `APPROVED_AND_FROZEN` |
| `M077_STATUS` | `NOT_STARTED` |
| M076 lineage on master | `14e8bd2`, `f1b4340`, `f41c35e`, merge `635a2f6`, freeze `1429827`, hash-record `e05cb2f` — all ancestors |

## 2. The Hypothesis, Tested Rather Than Assumed

The mission proposed that after M076 the daily path still cannot judge today's
proposed positions *after* accounting for already-held operator-asserted
exposure. **The hypothesis is confirmed, and the proof is structural.**

`grep` over `src/` for every M076 symbol returns consumers in exactly three
places: M076's own two usecases, M076's own two CLI entrypoints, and the
persistence runtime that constructs the repository. **No other module in the
repository imports the ledger.** `build_daily_research_brief.py` does not
reference it. `same_day_capital_feasibility.py` imports only M067's
`portfolio_study`.

### The sixteen questions, answered from code

| # | Question | Answer from source |
|---|---|---|
| 1 | Can the daily brief query M076 open positions? | **No.** `BuildDailyResearchBriefHandler` has no ledger dependency in `__slots__` or `__init__`. |
| 2 | Does M075 include M076-held exposure? | **No.** It admits plans against `capital_base` seeded at zero committed notional. |
| 3 | Can the system distinguish existing from proposed exposure? | Only by running two unrelated CLIs and comparing by eye. No artifact holds both. |
| 4 | Can it answer "how much capital is already represented by assertions"? | The *inputs* exist (`DerivedPositionState.total_asserted_open_notional`) but nothing relates them to a capital base. |
| 5 | Can it answer "which of today's plans remain feasible given that"? | **No.** This is the gap. |
| 6 | Is there enough in M076 to compute existing exposure honestly? | **Yes, and only one figure is honest:** quantity × asserted **entry** price. It is a record of what the operator said they committed. It is **not** market value, not verified cost basis, not a broker balance, not current valuation. |
| 7 | Does M076 retain enough after REDUCED/CLOSED? | **Yes.** `_fold_one_position` returns the *opening* event, so the surviving quantity is valued at the original asserted entry price. Closed positions carry `is_open=False` and are returned in a separate tuple. |
| 8 | What does the fold retain across multiple events? | `(open_quantity, is_open, opening_event)`. Reductions decrement quantity; a reduction landing exactly on zero closes the key. The entry price never changes. |
| 9 | Is asserted price sufficient for capital feasibility, or does using it overclaim? | Sufficient **only** under a label that says what it is. Asserting "capital represented by operator assertions" is honest. Asserting "current portfolio value" would fabricate a market observation M076 never made. |
| 10 | Would wiring M076 into M075 alter M075's frozen semantics? | **Yes, and irreconcilably.** M075's own rendered banner states it is "NOT current portfolio state; NOT open positions; NOT prior-day exposure". Feeding held exposure into M075 would make its banner false. |
| 11 | So should M077 be a new additive artifact? | **Yes.** This is forced by Q10, not chosen for convenience. |
| 12 | Can the bridge stay read-only w.r.t. M076? | **Yes.** It calls `list_all()` and the pure `derive_position_state()`. It never appends. |
| 13 | What timestamp defines the snapshot? | The session's own `as_of`, which the brief already carries and which M076's fold already treats as inclusive. |
| 14 | How are future-dated events excluded? | By M076's existing filter `event_timestamp <= as_of`, whose excluded count is already surfaced as `excluded_future_event_count`. M077 reuses it rather than reimplementing it. |
| 15 | Edge cases | Enumerated in §9 and each one is a named test. |
| 16 | Is M068 dependence relevant? | **It is relevant in principle and deliberately excluded.** M068 is historical dependence evidence. Using it as an operational concentration control would be exactly the "historical evidence silently becoming operational truth" error the mission forbids. Named as a non-goal in §12. |

## 3. Candidate Ranking

Eight candidates, six criteria, 1–5 (5 is best).

| # | Candidate | Product | Empirical | Impl. risk | Frozen risk | Honesty risk | Unlocks | **Total** |
|---|---|---|---|---|---|---|---|---|
| **1** | **Portfolio-aware capital feasibility (A+B)** | 5 | 4 | 4 | 4 | 4 | 5 | **26** |
| 2 | Operational exposure summary (E) | 3 | 2 | 5 | 5 | 4 | 2 | 21 |
| 3 | Session→position lineage (H) | 2 | 4 | 5 | 4 | 5 | 3 | 23 |
| 4 | Decision-vs-outcome evaluation (D/L) | 5 | 5 | 2 | 3 | 2 | 4 | 21 |
| 5 | Forward/paper observation primitive (C) | 4 | 4 | 2 | 3 | 1 | 4 | 18 |
| 6 | Realized/unrealized observation (G) | 4 | 3 | 2 | 3 | 1 | 3 | 16 |
| 7 | Data freshness authority (I) | 3 | 3 | 4 | 4 | 4 | 2 | 20 |
| 8 | Concentration guard from M068 (F) | 3 | 2 | 3 | 2 | 1 | 2 | 13 |

### Why the winner won

**Candidate 1 closes a gap that is arithmetic, not aesthetic.** M075 tells the
operator that today's five plans fit inside their equity. If they already hold
three asserted positions consuming most of that equity, M075's answer is still
"fits" — and it is silent about why that may be wrong. Every input needed to
say something better already exists and is already persisted; nothing must be
invented, acquired, or simulated.

It also scores highest on *unlocks*: decision-vs-outcome evaluation (candidate
4) and any legitimate forward-evaluation milestone both need a defensible
notion of "exposure already taken", which is precisely what M077 defines.

### Why the others lost

| Rejected | Why |
|---|---|
| Operational exposure summary (E) | A strict subset of candidate 1 — it reports held exposure without relating it to capital, so it answers no decision question. Candidate 1 subsumes it. |
| Session→position lineage (H) | Genuinely valuable and low-risk, but it is a *component*: M077 needs plan lineage anyway to avoid double-counting (§7), so this ships inside candidate 1 rather than as its own milestone. |
| Decision-vs-outcome evaluation (D/L) | The highest scientific value of any candidate, and premature. Evaluating a decision against its outcome requires an outcome, which requires either market revaluation or realized proceeds. M076 asserts neither. Building it now would force fabricated valuation. **This is the strongest future milestone and M077 is a precondition for it.** |
| Forward/paper observation (C) | Honesty risk 1. "Paper trading" implies simulated execution against market prices the platform does not have operationally. |
| Realized/unrealized observation (G) | Same defect: "unrealized" is definitionally a market-versus-cost comparison, and there is no operational market price. |
| Data freshness authority (I) | Real but orthogonal, and it blocks nothing. |
| Concentration guard from M068 (F) | Honesty risk 1 and frozen risk 2: it would convert historical dependence evidence into an operational control, the exact leak the mission forbids. |

## 4. Selected Capability

**A new, additive, read-only decision artifact: portfolio-aware capital
feasibility.**

Given a completed session's approved position plans *and* the positions the
operator has asserted are open as of that session's `as_of`, report which of
today's plans remain feasible once already-asserted exposure is charged against
the same explicit capital policy — and say plainly that the held figure is an
operator assertion, not a market valuation.

## 5. Architecture

| Layer | Change |
|---|---|
| `decision_candidate/portfolio_aware_capital_feasibility.py` | **New.** One pure, I/O-free module. |
| `decision_candidate/daily_research_brief.py` | One additive keyword-defaulted field, exactly the M074/M075 pattern. |
| `usecases/build_daily_research_brief.py` | Optional ledger repository + suppression flag, exactly the M075 pattern. |
| `usecases/daily_research_brief_io.py` | Text + JSON rendering from one derived object. |
| `entrypoints/*` | One suppression flag on each of the two daily paths. |
| **Persistence** | **None.** Zero new table, zero migration, zero new repository. |
| **M076** | **Untouched.** Read via its existing contract only. |
| **M075** | **Untouched.** Neither modified nor re-interpreted. |

M077 reads the ledger **once** via `list_all()`, passes those events to M076's
own `derive_position_state()` for state, and projects the *same* tuple for
plan lineage. It never reimplements the fold.

## 6. Domain Semantics

- **Capital base** — identical rule to M075: the minimum
  `supplied_account_equity` across usable approved plans. Not a verified
  balance.
- **Held asserted notional** — `DerivedPositionState.total_asserted_open_notional`,
  i.e. Σ (open quantity × asserted entry price). Never revalued.
- **Utilization, not depletion.** Charging held notional against the capital
  base does **not** claim the operator's cash was reduced. Buying an asset
  converts cash into that asset and leaves equity unchanged. M067's model is
  *utilization* — `max_capital_utilization_percent` measures how much of the
  capital base is **deployed** — and deployed capital is exactly what a held
  asserted position represents. This distinction is stated because the figure
  is otherwise easy to misread as a cash balance.
- **Ceiling** — `capital_base × max_capital_utilization_percent`, from M067's
  frozen default policy, exactly as M075 computes it.
- **Admission** — the loop is seeded with held exposure and held position count
  rather than with zero:
  - committed notional starts at held asserted notional
  - concurrent-position count starts at the number of open asserted positions
  - each plan is then admitted in M075's deterministic order (rank, then
    symbol) if it fits both caps
- **Strict `>`** — a set landing exactly on the ceiling is feasible, matching
  M075 so the two artifacts cannot disagree on a boundary.

### Outcome vocabulary

`FITS_WITHIN_REMAINING_CAPITAL`, `EXCEEDS_REMAINING_CAPITAL`,
`ALREADY_AT_OR_OVER_CAPITAL`, `NO_APPROVED_POSITION_PLANS`, `NOT_ASSESSABLE`.

Deliberately **not** `ALLOCATED`, `EXECUTED`, `FILLED`, `VERIFIED`. M077
allocates nothing and verifies nothing.

## 7. Double Counting — the central correctness risk

An operator may assert a position **citing one of today's own plans** via
`source_position_plan_governance_id`. Counting both the held position and the
same plan as "proposed" would charge the operator twice for one decision.

M077 therefore builds a lineage index from the `OPENED` events of positions
that are open at `as_of`, and any approved plan whose governance id appears in
that index is **excluded from the proposed set and named explicitly** as
already acted upon. It is not silently dropped and not silently double-charged.

## 8. Temporal Semantics

`PORTFOLIO_AWARE_FEASIBILITY_AT(t)` — a pure function of (this session's
approved plans, the operator ledger folded at `t`, one capital policy).

Inclusive `as_of`, inherited from M076 unchanged. Events after `as_of` are
excluded by M076's own filter and their count is surfaced. `recorded_at` never
participates. Distinct from `STATE_AT(t)`, `EVENT_AFTER(t)`,
`HISTORICAL_EVIDENCE_AVAILABLE_AT(t)` (M074),
`RECOMMENDATION_SET_FEASIBILITY_AT(t)` (M075), and
`OPERATOR_ASSERTED_POSITION_STATE_AT(t)` (M076).

## 9. Absence, Error and Boundary Semantics

Absence is never rendered as a pass.

| Condition | Behaviour |
|---|---|
| Session not completed | `NOT_ASSESSABLE` / `SESSION_NOT_COMPLETED` |
| Capital base ≤ 0 | `NOT_ASSESSABLE` / `NON_POSITIVE_CAPITAL_BASE` |
| Ledger unavailable | `NOT_ASSESSABLE` / `LEDGER_UNAVAILABLE` — never treated as "no positions" |
| Empty ledger | Assessed normally, held exposure `0`, explicitly stated |
| Held exposure ≥ ceiling | `ALREADY_AT_OR_OVER_CAPITAL`; every plan excluded with a reason |
| Held exposure exactly = ceiling | Over the line only on strict `>`; equality leaves zero headroom, so any positive plan is excluded |
| No approved plans, positions held | `NO_APPROVED_POSITION_PLANS`, and held exposure still reported |
| Position closed before `as_of` | Not counted |
| Reduction before `as_of` | Counted at the reduced quantity |
| Reduction after `as_of` | Excluded; excluded-event count surfaced |
| Mixed timezone offsets for one instant | Identical result — M076 requires aware datetimes and compares instants |
| Suppressed by flag | Field is `None`, which is distinct from an assessment that could not be made |

A `LedgerRejectionError` from malformed persisted data is caught and converted
to `NOT_ASSESSABLE` / `LEDGER_INCOHERENT` rather than taking the brief down.

## 10. Concurrency

M077 reads; M076 may be writing concurrently.

`PostgresOperatorPositionLedgerRepository.list_all()` is a **single `SELECT`**
inside one transaction. Under PostgreSQL's default `READ COMMITTED`, a single
statement observes one consistent snapshot taken at statement start, so M077
can never observe a torn write. M076's `append_validated` commits a position's
event atomically under a per-position advisory lock, so every snapshot M077
observes is a coherent ledger state — a given event is either wholly visible or
wholly invisible.

**No additional locking is required, and adding any would be unjustified.** The
consistency requirement is a point-in-time snapshot, and one statement already
provides exactly that. This is asserted as a proven property, not hand-waved:
it is exercised by a concurrency test in which a writer appends while a reader
folds.

## 11. Honesty Boundary

The rendered banner — not merely documentation — must state that the result is
based on **operator-asserted** position records; is **not** broker-verified; that
the asserted price is **not** a current market price; and that it is **not**
execution evidence, **not** a verified account balance, **not** P&L, **not** a
profitability claim and **not** advice.

A forbidden-vocabulary test asserts that `EXECUTED`, `FILLED`, `VERIFIED`,
`ALLOCATED`, `MARKET_VALUE` and `P&L` appear nowhere in the module or its
rendered output.

## 12. Explicit Non-Goals

Market revaluation; P&L, realized or unrealized; broker integration or
reconciliation; execution or fills; paper trading; modification of M075 or
M076; any new PostgreSQL table or migration; operational use of M067/M068
historical evidence, including concentration control; cross-day trend
reporting; repair of the M062/M064/M065 seal debt. **MILESTONE-078 is not
built.**

## 13. Acceptance Criteria

1. A completed session with held asserted exposure reports which plans remain
   feasible after that exposure is charged.
2. Held exposure derives solely from M076 and is never revalued.
3. A plan already acted upon is excluded exactly once and named.
4. Text and JSON agree semantically.
5. Zero change to M075/M076 semantics; zero new schema.
6. Every edge case in §9 is a named test.
7. Real-PostgreSQL evidence, cross-checked with raw SQL.
