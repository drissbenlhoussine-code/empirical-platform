# MILESTONE-080 — Operator-Asserted Round-Trip Result — Scope and Design

## Status: IMPLEMENTATION CANDIDATE — NOT OWNER FROZEN

---

> ## ⚠ TWO SECTIONS SUPERSEDED BY OWNER REVIEW
>
> **§14 (precision) and §15 (excluded components) were both wrong.** They are
> retracted in place below and the corrected semantics are summarised here.
>
> **Finding 1 — the arithmetic was not exact.** §14 claimed "products and sums
> are exact" under `Decimal`. `Decimal` arithmetic and `normalize()` are
> **context-sensitive**, and M076 persists `quantity` as PostgreSQL `INTEGER`,
> so `2147483647 × 99999999999999.999999` is a persistence-valid product of
> **30 significant digits** — six more than the default 28-digit context keeps.
> All monetary arithmetic is now carried in **Python integers scaled to 10⁻⁶**,
> exact by construction and independent of the ambient context, with rendering
> performing no `Decimal` operation at all.
>
> **Finding 2 — not every excluded component is a cost.** §15 called the whole
> list costs and claimed every result is "systematically more favourable" than
> reality. Dividends **raise** a long position's real outcome, corporate actions
> move it either way, and tax effects are jurisdiction-dependent. The concept is
> now `EXCLUDED_ECONOMIC_COMPONENTS`, partitioned into
> `EXCLUDED_FRICTION_COMPONENTS` and `EXCLUDED_NON_DIRECTIONAL_COMPONENTS`, and
> the artifact states that it is **not a complete economic outcome** and that the
> **direction of the total omitted effect is not generally knowable**.
>
> The API vocabulary was corrected **before** freeze deliberately: freezing a
> field named for a false claim would be worse than renaming it now.

---


## 1. Repository Authority

Verified from repository objects at mission start, not from the mission text.

| Fact | Value |
|---|---|
| `master` HEAD | `0e73e0bebbd6ecbfc672cbced14010ccf4d5f7b6` |
| `LATEST_FROZEN_MILESTONE` | `MILESTONE-079` |
| `M079_STATUS` | `APPROVED_AND_FROZEN` |
| `M080_STATUS` | `NOT_STARTED` |
| `NEXT_PERMITTED_ACTION` | `MILESTONE-080 -- recommendation only; not started as part of M079` |
| ahead/behind | 0/0, working tree clean |

No material difference from the mission text.

## 2. M079 Starting Point, and One Correction to Its Frozen Prose

M079 froze `OPERATOR_EVIDENCE_AVAILABLE_AT(E, K)`: `recorded_at <= K` is the only
knowledge filter, applied once, and no assertion recorded after `K` may influence
any output. `events_known_by` is **public** (`__all__`), so M080 reuses the
firewall rather than reimplementing it.

**A correction to M079's frozen limitation 8, documented rather than silently
reconciled.** That limitation states flatly that "`recorded_at` is
operator-supplied". The code says something more precise:

| Path | Who sets `recorded_at` |
|---|---|
| `entrypoints/record_operator_position_event.py:70` | **the system** — `datetime.now(UTC)`, and there is **no `--recorded-at` flag** |
| `usecases/record_operator_position_event.py:100` | the caller, as a parameter |
| domain `__post_init__` | accepts any timezone-aware value |

So in the **only shipped write path** the value is process-clock-assigned. What
is true is that **nothing enforces it**: the usecase and domain accept an
arbitrary instant, so a programmatic caller can supply any value, and there is no
monotonicity or immutability guarantee.

M079's frozen document is **not edited**. The correction is recorded here, and it
materially lowers candidate B's score in §4.

## 3. Fresh Gap Analysis

### The proved gap, from code

M076 stores `asserted_price` on **every** lifecycle event — `OPENED`, `REDUCED`
and `CLOSED` alike — validated positive and exactly representable as
`NUMERIC(20, 6)`, and round-tripped by the repository.

A repository-wide search for consumers of `asserted_price` outside M076 itself
returns **only the persistence adapter, the write usecase and the write CLI**.
Every one of those is a *write* path.

The single derivation that reads a price reads exactly one:

```python
notional = Decimal(quantity) * opening.asserted_price   # operator_position_ledger.py:419
```

**`opening`. The entry price only.** The asserted price on every `REDUCED` and
every `CLOSED` event is write-only data: persisted, validated, never read by any
derivation in the repository.

This is the same shape as M079's gap — stored, validated, round-tripped, unused —
and it is the last input the platform needs to answer what a research decision
came to.

### What already exists, and must not be confused with it

`realized_pnl`, `profit_factor` and `maximum_realized_pnl_drawdown` **already
exist** in the repository — in M062 validation studies, M063 robustness studies
and M067 portfolio studies. Every one of those is **simulated** P&L over
historical bars in a backtest. None touches an operator assertion.

M080 must not blur that line. The platform's existing money vocabulary belongs to
simulation; M080's belongs to operator assertions, and the two are different
kinds of claim.

## 4. Candidate Ranking

Six candidates, eleven criteria, 1–5 (5 best). Honesty risk, temporal-leakage
risk, frozen-contract risk and complexity are scored so that **5 = low risk / low
complexity**.

| # | Candidate | Product | Scientific | Honesty risk | Temporal risk | Arch leverage | Unlock | Frozen risk | Complexity | Persistence | Operator | Testability | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **1** | **Asserted round-trip result (A)** | 5 | 5 | **2** | 4 | 5 | 5 | 4 | 3 | 5 | 5 | 5 | **48** |
| 2 | Lifecycle/round-trip audit, no money (E) | 3 | 3 | **5** | 4 | 3 | 2 | 4 | 4 | 5 | 3 | 5 | 41 |
| 3 | Cross-session exposure evolution (C) | 4 | 3 | 4 | 4 | 3 | 2 | 4 | 3 | 5 | 4 | 5 | 41 |
| 4 | System-recorded knowledge authority (B) | 2 | 3 | 5 | 5 | 3 | 2 | **1** | 3 | **1** | 2 | 4 | 31 |
| 5 | Decision calibration / effectiveness (D) | 5 | 5 | 1 | **2** | 2 | 2 | 3 | 1 | 3 | 3 | 2 | 29 |
| 6 | `recorded_at` index / query-side filter (F) | 1 | 1 | 5 | 5 | 2 | 1 | 4 | 5 | 2 | 1 | 3 | 30 |

### Why candidate A wins

- It is the **only** candidate that closes a proved, code-level gap: exit prices
  are stored and read by nothing.
- Its stated prerequisite now **exists**. M077's and M078's freezes both deferred
  it because there was no `recorded_at` firewall; M079 built one, and made
  `events_known_by` public specifically so it could be composed.
- It **unlocks** calibration (D), which is otherwise unreachable.
- It needs **zero schema, zero migration, zero new repository** — the data is
  already persisted.
- Its honesty risk is the highest of the six, and that is the reason it needs the
  most careful vocabulary rather than a reason to avoid it. §18 and §23 discharge it.

### Rejected candidates

| Rejected | Why |
|---|---|
| **B — system-recorded knowledge authority** | Scored down by §2's finding. The shipped CLI **already** stamps `recorded_at` with the system clock, so the practical gap is narrower than M079's prose implies. Closing the remaining gap properly means an immutable, system-assigned receipt column — a **schema change to a frozen M076 table** and a change to the frozen event contract. High frozen risk, near-zero downstream unlock. It should be its own explicitly authorized milestone, not a side effect of M080. |
| **E — lifecycle audit without monetary result** | This is candidate A with the arithmetic removed. It builds almost the same machinery, leaves the proved gap open, and unlocks nothing. Choosing it would be avoiding the honesty question rather than answering it. |
| **C — cross-session exposure evolution** | Honest and useful, but reports a trend rather than closing a gap or unblocking anything. |
| **D — calibration** | Highest value, lowest readiness; strictly gated on A. Temporal risk 2. |
| **F — `recorded_at` index** | Infrastructure, not product. M079 already recorded it as a deliberate deferral. |

## 5. Selected Capability

**`OPERATOR_ASSERTED_ROUND_TRIP_RESULT_AT(E, K)`** — a read-only, additive,
**position-centric** report of the arithmetic implied by the operator's own
asserted prices and quantities for the quantity they assert they exited, computed
from evidence recorded by knowledge cutoff `K` about what they say happened by
effective cutoff `E`.

**Position-centric, deliberately.** The alternative — auditing one research
session's approved plans — was designed and rejected during this analysis, for a
structural reason worth recording:

> M078's `audit_research_decision_follow_through` requires a `held_state` from
> `derive_position_state`, and that function raises on the **first** key that
> does not fold, voiding the whole audit. Knowledge filtering makes truncated
> prefixes common — that is the entire point of M079 — so composing M078's audit
> would produce `NOT_ASSESSABLE` for an entire session because of one unrelated
> position. M079 solved this with **per-key** folding, and M080 adopts the same
> resilience.

M080 therefore reports the cited plan id per position as **lineage metadata via
M078's public `cited_plan_by_position`**, and never treats it as a session join.
**M078 remains the sole authority on session→ledger joins.** §11 states the
boundary.

## 6. Authority Model

| Concern | Authority | M080's role |
|---|---|---|
| knowledge filter `recorded_at <= K` | **M079 `events_known_by`** | calls it once; applies no other knowledge filter |
| effective filter and lifecycle fold | **frozen M076 `derive_position_state`** | calls it per key; never re-implements it |
| open vs closed | **frozen M076** | never decides independently |
| plan citation projection | **M078 `cited_plan_by_position`** | calls it; reports the result as metadata |
| session→ledger join | **M078** | **out of scope for M080** |
| exit prices and quantities | the persisted events | reads them; asserts nothing about their truth |
| the arithmetic | **M080, new** | the only thing M080 adds |

No frozen module is modified. No new table, column, migration or repository.

## 7. Vocabulary

### The monetary concept, named honestly

`asserted_round_trip_result` = `asserted_exit_consideration` −
`asserted_entry_cost_for_exited_quantity`.

It is **arithmetic over operator-asserted prices and quantities**, on the
quantity the operator asserts they exited, using the entry price the operator
asserted. Nothing more.

It is **not** broker realized P&L, verified profit, actual execution result,
actual cash proceeds, investment performance, market return, or a tax result.
The tokens `BROKER_REALIZED_PNL`, `ACTUAL_PROFIT`, `VERIFIED_PROCEEDS`,
`MARKET_RETURN` and `EXECUTION_PNL` appear nowhere, enforced by test. The bare
token `PNL` appears nowhere either — see §23.

### Status vocabulary

| Status | Meaning |
|---|---|
| `NO_EXIT_ASSERTED_YET` | opened, nothing exited by `E` as recorded by `K`. **No arithmetic is emitted.** |
| `PARTIAL_EXIT_ASSERTED` | some quantity exited, position still open. Arithmetic covers the **exited quantity only** and is never extrapolated to the open remainder. |
| `FULLY_EXITED_ASSERTED` | the position is closed **and** the visible exit quantities reconcile exactly to the opened quantity. |
| `EXIT_QUANTITY_UNRECONCILED` | the fold says closed, but the visible exit components do **not** account for the opened quantity. See §10 — this is a real, reachable state, not a defensive stub. |
| `UNRESOLVED_KNOWLEDGE_SEQUENCE` | the evidence recorded by `K` does not fold. Carried through from M079 unchanged; no arithmetic, no inference. |

## 8. Temporal Model

Two required, inclusive, timezone-aware cutoffs, neither defaulted — identical in
contract to M079:

- `effective_as_of = E` bounds **occurrence** (`event_timestamp <= E`), applied by
  frozen M076.
- `knowledge_as_of = K` bounds **recording** (`recorded_at <= K`), applied by
  M079's `events_known_by`, once.

### Decision time is reported, never used as a filter

M080 does not invent a decision-time contract. A position's opening
`event_timestamp` is reported; any relationship between it and a plan's session
is **M078's** question. Filtering on a decision timestamp would silently redefine
what is being asked, so M080 does not do it.

### Current reconstruction vs point-in-time evaluation

These are different products and M080 keeps them apart by construction:

| | Question | How to ask it |
|---|---|---|
| **A. Current reconstruction** | what does the ledger *now* record happened? | set `K` to the present |
| **B. Point-in-time evaluation** | what had the ledger recorded by `K`? | set `K` to the historical instant |

Both cutoffs are echoed in every rendering so the two can never be confused.

## 9. Knowledge-Time Model

The M079 invariant is inherited **whole**: no assertion with `recorded_at > K`
may influence whether an outcome exists, the entry price, any exit price, any
quantity, the arithmetic, the completion status, the classification, the counts,
the explanation, the limitations or the ordering.

It is enforced **structurally**, as in M079: `events_known_by` is called once at
the boundary and the evaluation core is handed only the survivors, so a
post-cutoff row is unreachable rather than merely unused.

Evolution across cutoffs is legitimate: an evaluation at `K1` may report
`PARTIAL_EXIT_ASSERTED` and the same position at `K2` may report
`FULLY_EXITED_ASSERTED`. The `K1` answer must remain reproducible from `K1`
evidence alone, and must never be retroactively strengthened.

## 10. The Derived-`CLOSED`-Quantity Hazard — a load-bearing finding

Found **before implementation**, by executing frozen M076 rather than reading it.

`validate_appended_event` **derives** a `CLOSED` event's quantity from the state
immediately before it, ordered by `event_timestamp`, and persists that derived
value. Proven: supplying `quantity=999` for a close after `OPENED 10, REDUCED 4`
persists `6`.

That derivation happens at **append** time over the **full** effective-time
history. It is not re-derived per knowledge cutoff. So:

```
OPENED  q=10  effective d1  recorded d1
REDUCED q=4   effective d2  recorded d9   <- recorded LATE
CLOSED  q=6   effective d3  recorded d3   <- derived from the FULL history
```

At `K = d3` the visible prefix is `OPENED(10), CLOSED(6)`. **It folds
coherently** — M076 accepts it and M079 reports `KNOWN_CLOSED`. Yet the visible
exit components account for **6 of 10** shares. Four shares are unexplained,
because the reduction that explains them was not recorded until `d9`.

Naive round-trip arithmetic would either report the 6-share result as *the*
result for a closed position, or extrapolate it to 10. Both are dishonest.

**Design consequence.** M080 must not treat "the fold says closed" as "the exit
quantities are complete". It reconciles `Σ visible exit quantities` against the
opened quantity from **visible evidence alone**, and reports
`EXIT_QUANTITY_UNRECONCILED` — with the shortfall named and no result asserted as
complete — when they disagree.

## 11. Lineage Semantics

M080 reports `cited_position_plan_governance_id` per position, projected by
M078's public `cited_plan_by_position`, which already strips blank and
whitespace-only citations (carried from the M077 R04 defect).

**M080 asserts nothing about that citation.** It does not claim the position
belongs to any session, does not validate the plan exists, and does not resolve
identity ambiguity — those are M078's job and M078 remains their sole authority.
A citation is reported as *what the operator recorded*, labelled as such.

Fail-closed rules that **are** M080's: a position whose visible evidence does not
fold yields `UNRESOLVED_KNOWLEDGE_SEQUENCE` and no arithmetic; an instrument
mismatch within a position key is M076's own rejection and surfaces as the same
unresolved status.

## 12. Arithmetic Semantics

Derived from frozen M076 by execution. All sixteen §6 questions of the mission
are answered in `external-review/MILESTONE-080/hostile-design-review.md`.

Let the visible events for one position key, effective-filtered to `E` and
knowledge-filtered to `K`, be ordered by M076's own `(event_timestamp,
governance_id)` key.

```
entry_price      = OPENED.asserted_price                       (Decimal)
exit_events      = [e for e in visible if e.kind in (REDUCED, CLOSED)]
exited_quantity  = Σ e.quantity                                (int)
exit_consideration        = Σ (Decimal(e.quantity) * e.asserted_price)
entry_cost_for_exited     = Decimal(exited_quantity) * entry_price
round_trip_result         = exit_consideration - entry_cost_for_exited
```

- Quantities are **`int`** in M076, not `Decimal`. They are widened to `Decimal`
  for the multiplication so no float ever appears.
- `exited_quantity == 0` ⇒ **no arithmetic is emitted at all**, not a zero.
- A reduction landing exactly on zero closes the position with **no `CLOSED`
  event**; the sum over reductions alone then reconciles. Proven by execution.

## 13. Partial Lifecycle Semantics

If the position is still open, the arithmetic covers **only** the exited
quantity. The still-open remainder gets no result, no per-share extrapolation and
no implied value. The open quantity is reported as a separate integer so the
reader can see what is *not* covered.

## 14. ⚠ RETRACTED — Precision Semantics

> **Retracted by Owner review.** The exactness claim below is false for the
> maximum persistence-valid quantity. Preserved verbatim.

Decimal throughout; no float anywhere in the module. Products and sums are exact:
a `NUMERIC(20, 6)` price times an integer quantity is exact in `Decimal`, and
addition of exacts is exact. Results are rendered with M076's own `_money`-style
canonical form — `normalize()` then `format(..., "f")` — so a value read from
memory and one read from PostgreSQL render identically. No quantization and no
rounding is applied to a result, because rounding a number the operator implied
is the same small dishonesty M076 refused for prices.

## 15. ⚠ RETRACTED — Fees, Slippage, Taxes, Corporate Actions — explicitly absent

> **Retracted by Owner review.** Calling the whole list *costs* and claiming a
> universally favourable bias is false. Preserved verbatim.

M076 stores **none** of the following, so none is in the arithmetic:

| Component | In M076? | In the result? |
|---|---|---|
| commissions | no | **excluded** |
| spread / slippage | no | **excluded** |
| exchange or regulatory fees | no | **excluded** |
| taxes | no | **excluded** |
| dividends | no | **excluded** |
| corporate actions (splits, mergers) | no | **excluded** |
| financing / borrow cost | no | **excluded** |
| current market price | no | **no unrealized result is computed** |

⚠ **RETRACTED.** Itemising on every result was right; the bias claim was not.
The corrected statement is that the result is **not a complete economic
outcome** and that the **direction of the total omitted effect is not generally
knowable** — frictions would normally reduce a raw result, while dividends,
corporate actions and tax effects move it either way.

## 16. Persistence and Query Architecture

Zero new tables, columns, migrations or repositories. M080 reads the existing
M076 event stream through the existing repository's `list_all()`, exactly as
M077, M078 and M079 do, and filters in memory. The absence of a `recorded_at`
index is inherited from M079 and remains a deliberate deferral.

## 17. Deterministic Ordering

Entries are ordered by `(instrument_symbol, position_governance_id)` — the same
total order M079 uses. Within a position, events are consumed in M076's own
`(event_timestamp, governance_id)` order. No ordering depends on any post-cutoff
row, asserted by test.

## 18. Error and Absence Semantics

Absence is never rendered as a pass. A ledger that cannot be read yields
`NOT_ASSESSABLE` / `LEDGER_UNAVAILABLE` and withholds everything. A database
failure **propagates** rather than being disguised as a soft verdict — bad *data*
is withheld honestly; a broken *database* is not. Nothing recorded by `K` yields
a distinct outcome that explicitly is **not** "nothing happened".

## 19. CLI, Text and JSON

One console script, `empirical-platform-asserted-round-trip`, requiring both
`--effective-as-of` and `--knowledge-as-of` with UTC offsets and defaulting
neither. Text and JSON are rendered from **one object** so they cannot drift, and
parity is asserted by test.

## 20. Frozen-Contract Preservation

`operator_position_ledger.py` (M076), `same_day_capital_feasibility.py` (M075),
`portfolio_aware_capital_feasibility.py` (M077),
`research_decision_follow_through.py` (M078) and
`operator_evidence_availability.py` (M079) are read-only and unmodified, verified
by diff. M062/M064/M065 seal debt is untouched. `PROJECT_CHECKPOINT.md` is not
modified by this branch.

## 21. Security and Privacy

No credential, secret, host or connection string is rendered. The module is pure:
no I/O, no clock, no randomness, no float, no network.

## 22. What M080 Proves

That, from the operator assertions **recorded by `K`** about what they say
happened **by `E`**, a given quantity was asserted exited at given asserted
prices against a given asserted entry price, and what those numbers come to when
subtracted.

## 23. What M080 Does NOT Prove

It does not prove that any trade occurred, that it occurred at the stated price,
that any cash moved, or that the operator's assertions are true. It is **not**
broker realized P&L, **not** verified profit, **not** an actual execution result,
**not** actual cash proceeds, **not** investment performance, **not** a market
return and **not** a tax result. It excludes every cost component in §15. It
computes **no** unrealized result for an open position, because no authoritative
current market price exists in the platform. It makes no causal, predictive or
calibration claim, and no investment advice.

The word "P&L" is not used for M080's own quantity anywhere, including in field
names, statuses, JSON keys and rendered text. It appears only in negative
disclaimers stating what the result is not.

## 24. M081 Boundary

Explicitly out of scope and **not built**: calibration or decision-effectiveness
scoring; any aggregate across positions, sessions or time; win rate; expectancy;
return percentages; unrealized results; market prices; broker integration or
reconciliation; fee, tax, dividend or corporate-action modelling; a
system-assigned immutable receipt time; any new PostgreSQL table, column or
migration; modification of M070, M075, M076, M077, M078 or M079; any repair of
the M062/M064/M065 seal debt.
