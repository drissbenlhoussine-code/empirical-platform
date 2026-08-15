# MILESTONE-079 — Operator Evidence Availability Snapshot — Scope and Design


---

> ## ⚠ SUPERSEDED IN PART BY OWNER REVIEW
>
> Owner review of the first M079 candidate found a **temporal leak in this
> design**. The passages marked ⚠ below are **retracted**; they are kept in
> place so the corrected reasoning is auditable against the reasoning it
> replaced.
>
> **What was wrong.** When the knowledge-filtered sequence failed to fold, the
> design re-folded the same key against the **unfiltered** event set to choose
> between `INCOMPLETE_KNOWLEDGE_SEQUENCE` and `LEDGER_INCOHERENT_FOR_POSITION`.
> That set can contain assertions with `recorded_at > K`, so **future knowledge
> decided the status emitted at historical `K`** — even though no quantity was
> copied from it. The same rule condemns `total_event_count` and
> `excluded_by_knowledge_cutoff`, both functions of post-cutoff rows.
>
> **What replaced it.**
>
> | Retracted | Corrected |
> |---|---|
> | `INCOMPLETE_KNOWLEDGE_SEQUENCE` + `LEDGER_INCOHERENT_FOR_POSITION` | one `UNRESOLVED_KNOWLEDGE_SEQUENCE` |
> | `incomplete_knowledge_count`, `incoherent_position_count` | `unresolved_position_count` |
> | `total_event_count` | `known_event_count` — recorded **by** `K` |
> | `excluded_by_knowledge_cutoff` | removed; a static limitation explains why no such count can exist |
> | `excluded_by_effective_cutoff` | kept — computed from evidence recorded by `K`, so leak-free |
>
> `UNRESOLVED_KNOWLEDGE_SEQUENCE` means: *the evidence recorded by this cutoff
> does not form a coherent fold, and from that evidence alone it cannot be known
> whether this is temporary incompleteness or underlying ledger incoherence.*
>
> The guarantee is now **structural**: all snapshot logic lives in
> `_snapshot_from_known_evidence`, which is never given the unfiltered events.
>
> **Claim language also corrected.** `recorded_at` is operator-supplied, so M079
> claims to report *what the ledger records as having been recorded by `K`* —
> not *what evidence was actually available by `K`*.

---

## Status: IMPLEMENTATION CANDIDATE — NOT OWNER FROZEN

## 1. Repository Authority

Verified from repository objects at mission start, not from the mission text.

| Fact | Value |
|---|---|
| `master` HEAD | `5945e4effd48dfa97939bbd9448fa600503d4f89` |
| `LATEST_FROZEN_MILESTONE` | `MILESTONE-078` |
| `M078_STATUS` | `APPROVED_AND_FROZEN` |
| `M079_STATUS` | `NOT_STARTED` |
| `NEXT_PERMITTED_ACTION` | `MILESTONE-079 -- recommendation only; not started as part of M078` |

No material difference from the mission text.

## 2. Post-M078 Gap Analysis

### The proved gap, from code

M076 persists **two** timestamps on every operator assertion:

- `event_timestamp` — when the operator says the event happened;
- `recorded_at` — when the assertion was written down.

Both are `TIMESTAMPTZ NOT NULL`, both are validated timezone-aware
(`operator_position_ledger.py:149`), and both are `SELECT`ed and `INSERT`ed by
the repository.

**`recorded_at` is never filtered on, never ordered on, and never read by any
derivation anywhere in the repository.** A repository-wide search for
`recorded_at` alongside any `WHERE`, comparison, filter or `ORDER BY` returns
nothing. The fold's only temporal filter is:

```python
considered = tuple(e for e in events if e.event_timestamp <= as_of)   # :413
```

So the platform **already stores knowledge-time and has no way to use it.**

### The consequence, named by M078 itself

M078's frozen limitation states it plainly: M078 is an **effective-time** audit;
a later backfilled assertion can change the answer for an earlier `as_of`; and
M078 "must NOT be used as point-in-time calibration or forward-evaluation
evidence without a `recorded_at` / evidence-availability firewall."

**That firewall does not exist.** Nothing in the repository can answer *"what
did the operator ledger actually know as of historical time t?"*

### Why this blocks everything downstream

Forward evaluation, calibration and honest decision/outcome analysis all
require evaluating a decision against only the evidence available when it was
made. Without a knowledge-time filter, every such analysis silently includes
assertions recorded *after* the moment being evaluated — a textbook look-ahead
leak that would credit the system with knowledge it did not have.

## 3. Candidate Ranking

Six candidates, ten criteria, 1–5 (5 best).

| # | Candidate | Product | Scientific | Honesty risk | Arch fit | Unlock | Persistence | Frozen risk | Temporal risk | Testability | Operator use | **Total** |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **1** | **Evidence-availability firewall (A)** | 4 | **5** | **5** | 5 | **5** | 5 | 4 | 3 | 5 | 4 | **45** |
| 2 | Cross-session exposure evolution (D) | 4 | 3 | 4 | 5 | 2 | 5 | 4 | 4 | 5 | 4 | 40 |
| 3 | Decision → asserted outcome evaluation (B) | 5 | 4 | **1** | 4 | 4 | 5 | 4 | **2** | 4 | 4 | 37 |
| 4 | Forward observation / paper authority (C) | 4 | 4 | 1 | 3 | 4 | 2 | 3 | 3 | 3 | 3 | 30 |
| 5 | Calibration / decision effectiveness (E) | 5 | 5 | 1 | 2 | 3 | 3 | 3 | **1** | 2 | 3 | 28 |
| 6 | Per-instrument concentration guard | 3 | 2 | 3 | 4 | 2 | 5 | 3 | 5 | 5 | 3 | 35 |

*Honesty risk and temporal risk are scored so that 5 = low risk.*

### Why candidate A wins

It is the **only** candidate that is a strict prerequisite for three of the
others. B, C and E all evaluate a decision against later information; each is
unsafe until knowledge-time filtering exists. Building any of them first would
bake a look-ahead leak into the platform's first evaluation artifact — the
hardest kind of error to detect later, because the numbers look plausible.

It is also the cheapest and safest: the data is **already persisted**, so no
schema, no migration, no new I/O, and no frozen contract needs to move.

### Rejected alternatives

| Rejected | Why |
|---|---|
| **B — asserted outcome evaluation** | The mission asks whether `recorded_at` leakage makes historical evaluation unsafe. **It does**, and this design proves it: without a knowledge filter, any historical outcome number silently includes backfilled assertions. Section 5 of the mission says not to proceed through that contradiction. B is also the highest honesty risk — subtracting an asserted entry from an asserted exit is substantively realized P&L. **A is its precondition.** |
| **C — forward observation authority** | Would introduce a new observation primitive whose historical validity depends on the same missing firewall. |
| **D — cross-session exposure evolution** | Genuinely useful and honest, but it reports a trend rather than unblocking anything, and the trend itself would be effective-time only. |
| **E — calibration** | Highest value, **lowest readiness**. Explicitly gated on A. Temporal risk 1. |
| Concentration guard | Orthogonal; M067's policy has no per-instrument cap and M068's dependence evidence is historical. |

## 4. Selected Capability

**A read-only, additive, point-in-time operator-evidence snapshot.**

Given an **effective** cutoff `E` and a **knowledge** cutoff `K`, report the
operator-asserted position state derivable from exactly those assertions that
were both effective by `E` **and recorded by `K`** — and report, without
inventing coherence, the position keys whose evidence is incomplete at `K`.

## 5. Authority Model

| Input | Authority |
|---|---|
| `event_timestamp` | **authoritative** for *when the operator says it happened* |
| `recorded_at` | **authoritative** for *when the assertion became available* |
| M076's fold | **authoritative** for open vs closed, per position key |
| the ledger | **not authoritative** for broker reality, execution, fills or market truth |
| an incomplete key at `K` | **not authoritative** for anything — no state is asserted for it |

## 6. Temporal Model — two explicit dimensions

Three distinct concepts, never conflated:

| Concept | Meaning | Field |
|---|---|---|
| `EFFECTIVE_TIME` | when the operator asserts the event happened | `event_timestamp` |
| `RECORDED_TIME` | when the platform received the assertion | `recorded_at` |
| `QUERY` | the pair being evaluated | `effective_as_of`, `knowledge_as_of` |

**Eligibility:** `event_timestamp <= effective_as_of` **AND**
`recorded_at <= knowledge_as_of`. Both bounds **inclusive**, matching M076's
own inclusive `as_of` so the two milestones cannot disagree on a boundary.

Both cutoffs are **required** and must be timezone-aware. Neither has a
default: a default on either dimension would silently choose an epistemic
stance.

### The separation of duties that keeps M076 frozen

M079 applies **only** the knowledge filter. It then hands the surviving events
to M076's own `derive_position_state(events=…, as_of=effective_as_of)`, which
applies the effective filter and folds.

**M079 adds exactly one dimension and delegates the other.** M076's fold
remains the sole authority on open versus closed, is not modified, and is not
re-implemented.

### `M079_POINT_IN_TIME` vs M076/M078 effective-time

`OPERATOR_EVIDENCE_AVAILABLE_AT(effective_as_of, knowledge_as_of)`.

Setting `knowledge_as_of` to the present reproduces M076's answer. Setting it to
a historical instant produces a **different, and for evaluation the only
honest,** answer. Both are legitimate products and they are **not**
interchangeable:

- M076/M078 answer *"what does the ledger **now** say happened by E?"*
- M079 answers *"what evidence was **available** by K about what happened by E?"*

## 7. The Central Adversarial Case: an incomplete knowledge prefix

Knowledge filtering can legitimately produce a sequence M076's fold **rejects**:

```
E1 OPENED   effective Aug 10, recorded Aug 12
E2 CLOSED   effective Aug 11, recorded Aug 11
```

At `K = Aug 11`, the `CLOSED` is visible and its `OPENED` is not.
`_fold_one_position` raises `POSITION_NOT_OPEN` — *"no OPENED event exists for
this position"* (`:335-338`).

**Reporting that as corrupt data would be a false diagnosis** — precisely the
M078 R03 defect generalised. The events are individually valid and the full
sequence is coherent; only the *knowledge-filtered view* is incomplete. That is
not corruption, it is the honest shape of partial knowledge.

**Design decision.** Classification is **per position key**, never global:

- a key whose filtered events fold → its derived state is reported;
- a key whose filtered events do not fold → ⚠ *retracted, now* **`UNRESOLVED_KNOWLEDGE_SEQUENCE`**,
  carrying M076's own rejection reason, with **no state invented**.

A single incomplete key must not withhold the whole snapshot: that would
destroy the capability for the common case where most keys are complete. To
isolate failure without re-implementing anything, M079 folds **one key at a
time** through M076's own function and catches per key.

**Nothing is guessed.** No missing opening is inferred, no quantity assumed, no
"probable" state reported.

### ⚠ RETRACTED — Incompleteness must not mask corruption (design review T07)

> **This entire subsection is retracted.** The discriminator it describes is
> the temporal leak Owner review found. Preserved verbatim below.

M076's fold raises the **same** exception type for a knowledge-truncated prefix
and for genuinely corrupt data — two `OPENED` events on one key, an instrument
mismatch, a reduction exceeding the open quantity. Labelling every per-key
failure `INCOMPLETE_KNOWLEDGE_SEQUENCE` would hide real corruption behind an
innocent-sounding status.

**Discriminator.** On the failure path only, re-fold the key against the
**unfiltered** event set:

| K-filtered fold | Unfiltered fold | Conclusion |
|---|---|---|
| fails | **succeeds** | the failure is *caused by* knowledge filtering → `INCOMPLETE_KNOWLEDGE_SEQUENCE` |
| fails | **fails** | the underlying data is genuinely incoherent → `LEDGER_INCOHERENT_FOR_POSITION`, carrying M076's own reason |

The discriminator decides **only how to label a refusal**. No state from the
unfiltered fold is ever reported, so no future knowledge leaks into the answer.

### ⚠ PARTIALLY RETRACTED — Two exclusion counts, not one (design review C05)

> **`excluded_by_knowledge_cutoff` is retracted**; it counts post-cutoff rows.
> `excluded_by_effective_cutoff` survives. Preserved verbatim below.

An operator must be able to tell *"it hadn't happened yet"* from *"it hadn't
been recorded yet"*. M076's own excluded count sees only exclusions among
knowledge-survivors, so M079 reports both dimensions separately:

- `excluded_by_effective_cutoff` — recorded by `K`, but `event_timestamp > E`;
- `excluded_by_knowledge_cutoff` — `recorded_at > K`, whatever their effective
  time.

A single merged count would make the firewall's own effect invisible.

## 8. Deterministic Semantics

- Position keys ordered by `(instrument_symbol, position_governance_id)`.
- Incomplete keys ordered identically and reported separately.
- Event eligibility is a pure predicate over two fields; no set/dict iteration
  order reaches the output.
- Same `(E, K)` over the same ledger always yields an identical result.
- Ordering ties are impossible: `position_governance_id` is unique per key.

## 9. Failure and Absence Semantics

Absence is never rendered as a pass, and no state is coerced.

| Condition | Behaviour |
|---|---|
| Nothing recorded by `K` | `NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF`, stated explicitly — distinct from "nothing happened" |
| Ledger unreadable | `NOT_ASSESSABLE` / `LEDGER_UNAVAILABLE` |
| A key's evidence does not fold at `K` | ⚠ *retracted, now* `UNRESOLVED_KNOWLEDGE_SEQUENCE` for that key only |
| Naive `effective_as_of` or `knowledge_as_of` | rejected at the query boundary as a **request** error, never as a data claim (the M078 R03 lesson, applied to both dimensions) |
| `knowledge_as_of` < `effective_as_of` | permitted and meaningful — "what did we know on Aug 11 about what happened by Aug 20?" — with a limitation naming the stance |
| Genuinely malformed persisted data | M076's own rejection surfaces per key, distinguished from incompleteness by its reason |

A database-level failure propagates rather than becoming a soft verdict — the
M077/M078 precedent.

## 10. Persistence and Query Model

**No new schema and no migration.** `recorded_at` is already persisted as
`TIMESTAMPTZ NOT NULL`. Adding a column or table would be unjustified.

An index on `recorded_at` is deliberately **not** added: M079 reads through the
existing `list_all()` and filters in memory, exactly as M077 and M078 do, so no
new query shape reaches PostgreSQL and an index would optimise nothing that
runs.

Read-only: M079 has no write path on any dependency.

## 11. Lineage Model

`source_position_plan_governance_id` is carried through unchanged where
present. M079 introduces no new lineage concept and makes no causal claim.

## 12. Frozen-Contract Preservation

| Milestone | Treatment |
|---|---|
| M076 | **Read-only, unmodified.** Its fold is the sole authority and is delegated to, not copied. Its `as_of` is **not** reinterpreted — M079 passes `effective_as_of` into it, which is exactly what `as_of` already means |
| M077 | Untouched |
| M078 | Untouched |
| M070–M075 | Untouched |
| M062/M064/M065 seal debt | Not repaired |
| M063 record | Preserved |

## 13. Security and Migration Impact

No new external input, no new credential, no new network path, no new file
read, no new table, no migration. The CLI accepts two timestamps and two
identifiers.

## 14. Scientific-Honesty Boundary

M079 proves **evidence availability**, and nothing else.

It does **not** prove broker execution, actual fills, actual holdings, market
truth, valuation, P&L, profitability, causation, or investment advice. The
asserted entry price and asserted open notional it carries are M076's own
figures under M076's own semantics — operator assertions, never revalued, never
a market price.

Vocabulary is `KNOWN_` / `ASSERTED` / `INCOMPLETE_`, never `VERIFIED`,
`EXECUTED`, `FILLED`, `REALIZED` or `CONFIRMED`. `KNOWN_OPEN` means *known to
the ledger by `K`*, not *known to be true*, and the banner says so.

`UNRESOLVED_KNOWLEDGE_SEQUENCE` (⚠ formerly `INCOMPLETE_KNOWLEDGE_SEQUENCE`) is a property of the **snapshot**, not of the
operator: it says this view lacks evidence, not that anyone kept poor records.

A `KNOWN_OPEN` quantity may later prove to have been reduced by an assertion
recorded after `K`. That is not an error — it is precisely what was known at
`K`, and it is the reason the milestone exists.

## 15. Acceptance Scenarios

1. Effective before `E`, recorded before `K` → visible.
2. Effective before `E`, recorded **after** `K` → **invisible** (the firewall).
3. Effective **after** `E`, recorded before `K` → invisible.
4. Exact boundary on either dimension → inclusive.
5. Backfilled `OPENED` invisible at `K1`, visible at `K2 > K1` — same `E`,
   different answer, which is the whole point.
6. `CLOSED` visible without its `OPENED` → ⚠ *retracted, now* `UNRESOLVED_KNOWLEDGE_SEQUENCE`,
   nothing invented.
7. M076's present-day answer differs from M079's historical answer over the
   same ledger — proven side by side.

## 16. What M079 Proves, and Does Not

**Proves:** which operator assertions were available at a knowledge cutoff, and
the position state derivable from exactly those.

**Does not prove:** that any trade occurred; that anything is broker-verified;
what anything is worth; whether anything was profitable; that a recommendation
caused a position; or that the operator's assertions are true. It is a
statement about **what was on record**, not about the world.

## 17. M080 Boundary

Explicitly not built: outcome or P&L evaluation; calibration; forward or paper
observation; market revaluation; broker integration; any change to M076's fold
or `as_of`; any new table or migration; repair of the M062/M064/M065 seal debt.
**MILESTONE-080 is not started.**
