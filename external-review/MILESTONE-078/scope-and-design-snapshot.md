# MILESTONE-078 — Research Decision Follow-Through Audit — Scope and Design

## Status: IMPLEMENTATION CANDIDATE — NOT OWNER FROZEN

## 1. Repository Truth

Verified from repository objects at mission start, not from the mission text.

| Fact | Value |
|---|---|
| `master` HEAD | `183401efae221ecfea4cbb3837e79d045721f174` |
| `LATEST_FROZEN_MILESTONE` | `MILESTONE-077` |
| M075 / M076 / M077 | `APPROVED_AND_FROZEN` |
| `M078_STATUS` | `NOT_STARTED` |
| Baseline, PostgreSQL off | 8 failed, 1975 passed, 12 errors |
| Baseline, PostgreSQL on | 24 failed, 2311 passed, 44 errors |

The 8/24 failures and 12/44 errors are the pre-existing M062/M064/M065 CRLF
seal debt, which M078 does not touch.

## 2. A Contradiction in the Frozen Record, Documented Rather Than Reconciled

M077's freeze record states that decision-versus-outcome evaluation was deferred
because it "requires an outcome, which requires either market revaluation or
realized proceeds, and **M076 asserts neither**."

**Half of that is inaccurate, and the code is the authority.** M076's
`OperatorAssertedPositionEvent` carries a validated `asserted_price` on *every*
event kind, including `CLOSED` and `REDUCED`
(`operator_position_ledger.py:136,160-186`). The operator therefore *does*
assert exit prices, and they are persisted in `operator_position_event`.

What is true is that nothing **reads** them: `_fold_one_position` returns
`(quantity, is_open, opening_event)` and the notional is computed solely as
`Decimal(quantity) * opening.asserted_price` (`:340,:422`). `DerivedPosition`
exposes `asserted_entry_price` and no exit price at all.

So the accurate statement is: *M076 asserts no market revaluation, and it does
carry asserted exit prices that no derivation currently uses.*

This is recorded here rather than silently corrected, and it is **not** repaired
in M077's frozen document. It matters because it changes what M078 could have
been — see §4.

## 3. The Proved Gap

### Current state

Plan lineage exists. `OperatorAssertedPositionEvent.source_position_plan_governance_id`
records which position plan an operator cited when asserting a position. A
repository-wide search shows it is consumed in exactly **two** ways:

1. `portfolio_aware_capital_feasibility.open_position_plan_lineage()` — used
   *only* to suppress double counting, and *only* over positions **open at
   `as_of`**, and *only* for **the session being briefed today**;
2. display of a single held position's cited plan in the brief renderers.

### Missing capability

**Nothing in the repository can answer what became of a research session's
approved plans.** Specifically, no code path answers:

- which approved plans have an operator-asserted position recorded against them?
- which have one that is now closed?
- which have **nothing recorded at all**?
- which of the operator's asserted positions cite **no plan of this session** —
  or no plan at all?

The inputs all exist and are reachable through frozen public contracts:
`ResearchSessionRepository.get()` / `.list_recent()` and
`OperatorPositionLedgerRepository.list_all()`. Nothing joins them.

### Product consequence

The platform can propose, size, and check feasibility against held exposure —
and then loses the thread. An operator cannot ask the system *"did I record
anything against what my own research recommended, and what am I holding that
my research never proposed?"* That second half matters: an asserted position
citing no plan is the platform's only detectable signal of an unplanned,
undocumented position.

### Why this is the correct next boundary

It is the **honest half** of decision/outcome linkage. It requires no
valuation, no market price, no broker, and produces **no monetary figure at
all** (§7). It is a strict prerequisite for any future outcome or calibration
work: before you can evaluate whether a recommendation was *good*, you must be
able to say whether anything was *recorded against it*.

## 4. Candidates Considered

| # | Candidate | Value | Fit | Deps ready | Honesty risk | Impl risk | Verdict |
|---|---|---|---|---|---|---|---|
| **1** | **Research decision follow-through audit** | High | High | Yes | **Very low** | Low | **SELECTED** |
| 2 | Operator-asserted round-trip result on closed positions | High | High | **Yes** (see §2) | **Very high** | Medium | Rejected |
| 3 | Historical-market revaluation of open positions | High | Medium | Yes (M065/M069 data) | **Very high** | High | Rejected |
| 4 | Cross-session asserted-exposure evolution | Medium | High | Yes | Low | Medium | Rejected |
| 5 | Position lifecycle / capital-release timeline | Low | High | Yes | Low | Low | Rejected |

### Why the alternatives should wait

**Candidate 2** is now *technically* available — §2 shows the asserted exit
price is already persisted. It is rejected on honesty, not on feasibility.
Subtracting an asserted entry from an asserted exit produces a number that is
**substantively realized P&L**, and the mission forbids claiming realized P&L.
Renaming it would be exactly the failure mode the mission names: *no disclaimer
may rescue fundamentally misleading semantics*. It would also be the first
profit-shaped number the platform has ever emitted, which is a decision for the
owner to authorize explicitly rather than for this mission to take unilaterally.
**It is now unblocked and should be the owner's next explicit choice.**

**Candidate 3** would introduce market valuation into a brief whose M077 banner
states, in frozen text, that it is "NOT a market valuation". Adding one beside
it would make the platform contradict itself in a single output.

**Candidate 4** is real but weaker: M071 already compares sessions' decisions,
and exposure evolution answers a reporting question rather than an
auditability one.

**Candidate 5** is largely already covered — M077 charges open exposure and
closed positions release it implicitly.

## 5. Selected Capability

**A read-only follow-through audit for one research session, as of an explicit
timestamp.**

For every approved position plan of that session, report whether an
operator-asserted position citing it is open, is closed, or was never recorded.
Separately, report the operator's open asserted positions that cite no plan of
this session.

## 6. Domain Vocabulary — chosen against overclaiming

| Term | Means exactly | Deliberately **not** |
|---|---|---|
| `ASSERTED_POSITION_OPEN` | an operator-asserted position citing this plan is open at `as_of` | "executed", "filled", "held" as verified fact |
| `ASSERTED_POSITION_CLOSED` | such a position exists and is closed at `as_of` | "exited", "realized", "completed trade" |
| `NO_ASSERTED_POSITION_RECORDED` | **nothing was recorded** citing this plan | "ignored", "rejected", "not acted upon", "not followed" |
| `CITES_NO_PLAN` | an open asserted position carries no plan citation | "unauthorized", "discretionary", "off-plan" |
| `CITES_PLAN_OUTSIDE_THIS_SESSION` | it cites a plan id not among this session's approved plans | "wrong", "stale", "invalid" |

**The single most important term is `NO_ASSERTED_POSITION_RECORDED`.** Absence
of a record is *not* evidence the operator did nothing. It is evidence that
nothing was written down. Every rendering states this, and it is enforced by
test.

There is deliberately no `FOLLOWED` / `NOT_FOLLOWED` / `ADHERENCE` /
`COMPLIANCE` vocabulary anywhere: those words assert a judgement about the
operator's conduct that the data cannot support.

## 7. The Strongest Honesty Property: M078 Computes No Money

**M078 emits no monetary value of any kind** — no notional, no price, no
capital, no proceeds, no difference. It reports statuses, counts, quantities
and identifiers only.

This is a structural guarantee, not a convention: accidental P&L, accidental
valuation and accidental profitability claims are impossible when no arithmetic
over prices is performed. A test asserts that no field of the result carries a
price or notional.

## 8. Authoritative and Non-Authoritative Inputs

| Input | Authority |
|---|---|
| the session's approved position plans | **authoritative** for *what was recommended* |
| `source_position_plan_governance_id` on `OPENED` events | **authoritative** for *what the operator cited* |
| M076's fold (`derive_position_state`) | **authoritative** for *open vs closed at `as_of`* |
| absence of a citation | **not authoritative** for anything about the operator's real conduct |
| the ledger as a whole | **not authoritative** for broker reality |

## 9. Temporal Semantics

`FOLLOW_THROUGH_OBSERVED_AT(t)`: a pure function of (this session's approved
plans, the ledger folded at `t`).

- `as_of` is **required**, timezone-aware, and inclusive — no default, because
  a default would silently pick a window and the answer depends entirely on it.
- Events after `as_of` are excluded by M076's own filter, unchanged; the
  excluded count is surfaced.
- `recorded_at` never participates: when an assertion was *typed* cannot change
  what was *held*.
- If `as_of` precedes the session's own `as_of`, the window ends before the
  session existed. The result is still computed, and a limitation states that
  no follow-through was possible in that window — it is not silently reported
  as "nothing recorded".

Distinct from `STATE_AT(t)`, `EVENT_AFTER(t)`,
`HISTORICAL_EVIDENCE_AVAILABLE_AT(t)` (M074),
`RECOMMENDATION_SET_FEASIBILITY_AT(t)` (M075),
`OPERATOR_ASSERTED_POSITION_STATE_AT(t)` (M076) and
`PORTFOLIO_AWARE_FEASIBILITY_AT(t)` (M077).

## 10. Deterministic Rules

- Plan entries ordered by `(rank ascending, then instrument symbol)`, ranked
  before unranked — identical to M075/M077 so the artifacts cannot disagree.
- Unlinked positions ordered by `(instrument symbol, position governance id)`.
- A plan cited by **both** an open and a closed position reports
  `ASSERTED_POSITION_OPEN` — the currently-true fact — and retains both counts,
  so the closed one is never lost.
- Blank and whitespace-only citations are **not** identifiers (the M077 R04
  lesson), and are treated as no citation.
- No set/dict iteration order reaches the output.

## 11. Failure and Absence Modes

Absence is never rendered as a pass, and no state is silently coerced.

| Condition | Behaviour |
|---|---|
| Session has no approved plans | `NO_APPROVED_POSITION_PLANS`; unlinked positions still reported |
| Ledger empty | every plan `NO_ASSERTED_POSITION_RECORDED`, stated explicitly |
| Ledger unreadable | `NOT_ASSESSABLE` / `LEDGER_UNAVAILABLE` — never "nothing recorded" |
| Persisted events incoherent | `NOT_ASSESSABLE` / `LEDGER_INCOHERENT` |
| Naive `as_of` | rejected at the boundary by M076's own guard |
| `as_of` before the session's `as_of` | computed, with an explicit limitation |
| Session not found | the repository's own error propagates; not disguised |
| Blank or whitespace-only approved plan id | `NOT_ASSESSABLE` / `SESSION_PLAN_REFERENCES_INCOHERENT` |
| One plan id naming two instruments | `NOT_ASSESSABLE` / `SESSION_PLAN_REFERENCES_INCOHERENT` — no arbitrary first plan is audited |
| One plan id with diverging `rank` | **audited**; `rank` is presentation priority, not identity, and the divergence is reported |
| Exact duplicate plan reference | deduplicated deterministically, count reported |

**The plan governance id is the join authority** (owner correction to
`2c14d0a`). It is validated as an identity *before* any lineage is read, and
before the ledger checks, so an incoherent session reports the same reason
whatever the ledger is doing. A withheld audit fabricates nothing: entries and
unlinked positions are empty and every count is zero.

A database-level failure propagates rather than being converted into a soft
verdict — the M077 A1 precedent.

## 12. Architecture and Persistence

| Layer | Change |
|---|---|
| `decision_candidate/research_decision_follow_through.py` | **New.** One pure, I/O-free module |
| `usecases/audit_research_decision_follow_through.py` | **New.** Reads sessions + ledger through frozen contracts |
| `usecases/research_decision_follow_through_io.py` | **New.** Text + JSON from one derived object |
| `entrypoints/audit_research_decision_follow_through.py` | **New CLI** |
| **Persistence** | **None.** Zero new table, zero migration, zero new repository |
| M072 daily brief | **Untouched** — follow-through is a question about the past, not about today |
| M075 / M076 / M077 | **Untouched.** Read-only through public contracts |

M076 is not modified to expose lineage; as in M077, the lineage is projected
from the same event tuple already read, and M076's fold remains the sole
authority on open versus closed.

## 13. Explicit Non-Goals

Monetary values of any kind; realized or unrealized P&L; profitability;
valuation; market prices; broker integration, confirmation or reconciliation;
execution or fills; judgement of operator conduct; causal claims about why a
plan was or was not acted on; predictive or calibration claims; any new
PostgreSQL table or migration; modification of M075/M076/M077; repair of the
M062/M064/M065 seal debt. **MILESTONE-079 is not built.**

## 14. Test Strategy

Attacks against the claims, not mirrors of the implementation: nominal;
exact `as_of` boundary and one microsecond either side; future-event exclusion;
identical instants at different UTC offsets; naive timestamps; empty ledger;
empty plan set; all-invalid; mixed validity; duplicate and blank citations; a
plan cited by both an open and a closed position; input permutation;
determinism; repeated invocation; real PostgreSQL round trip; text/JSON
semantic parity; the no-money structural guarantee; forbidden vocabulary; and
M075/M076/M077 compatibility.

## 15. Acceptance Criteria

1. Every approved plan of the session receives exactly one status.
2. `NO_ASSERTED_POSITION_RECORDED` is never rendered as a claim about conduct.
3. Open asserted positions citing no plan of this session are reported.
4. No monetary value appears anywhere in the result.
5. Text and JSON agree semantically.
6. Zero change to M075/M076/M077 semantics; zero new schema.
7. Real-PostgreSQL evidence, cross-checked with raw SQL.
