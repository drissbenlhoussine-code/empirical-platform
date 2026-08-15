# M077 — Hostile Implementation Review

A **new** adversarial pass against the real code and real persistence
behaviour, not a repeat of the design review. Not an independent review — the
same agent wrote the code.

**106 attacks. Four genuine defects found, all confirmed by executing the code
rather than by reading it, all fixed, all with regression tests that fail
against the pre-fix implementation.**

## Defects found and corrected

### R01 — `plans_already_acted_upon` depended on caller input order

`already_acted` was appended while iterating `requests` in the caller's order,
so the same session assessed twice with the plans supplied in a different order
produced **different assessments**.

Proven by execution, not inspection:

```
forward acted: ('PLAN-A', 'PLAN-B')
reverse acted: ('PLAN-B', 'PLAN-A')
DETERMINISTIC? False
whole object equal? False
```

The existing determinism test passed only because it had no already-acted
plans — **the test was weaker than the claim it defended.**

**Fixed:** the filter loop iterates in the same deterministic `(rank, symbol)`
order the verdicts use, and the list is sorted. Regression test asserts whole-
object equality across both input orders.

### R02 — `limitations` order depended on caller input order

Same root cause, different symptom: exclusion messages were emitted in input
order. Fixed by the same change; separate regression test.

### R03 — the ceiling was quantised, so M077 disagreed with M075 on a boundary

M077 computed `(capital_base * pct).quantize(Decimal("0.01"))`. **M075 uses the
exact product.** Over identical inputs:

```
M075 ceiling: 100000.00500 -> fits: True
M077 ceiling: 100000.00    -> fits: False
BOUNDARY AGREE? False
```

The design document explicitly promised "matching M075 exactly so the two
artifacts cannot disagree on a boundary", and the implementation broke that
promise. A brief could have shown the same plan as feasible in one section and
infeasible in the next.

**Fixed:** the quantise is removed. Regression test asserts ceiling equality
*and* verdict equality against M075 over the same boundary input, plus a
stronger parity test proving that with an empty ledger M077 admits precisely
the plans M075 admits.

### R04 — a blank persisted plan citation was treated as an identifier

An `OPENED` row whose `source_position_plan_governance_id` is `""` put the
empty string into the lineage set. A malformed row could therefore **exclude an
unrelated plan from the proposal set entirely** — a silent and expensive wrong
answer.

```
request with empty plan id excluded? ('',) admitted: 0
```

**Fixed:** blank and whitespace-only citations are ignored. Two regression
tests.

## Attack matrix

Categories and outcomes. `PASS` = attacked and held; `FIXED` = genuine defect,
corrected above; `ACCEPTED` = bounded and stated.

| Category | Attacks | Result |
|---|---|---|
| Capital accounting | 14 | 13 PASS, 1 FIXED (R03) |
| Asserted-position folding | 11 | 11 PASS |
| `as_of` boundaries | 9 | 9 PASS |
| Double counting / lineage | 10 | 8 PASS, 2 FIXED (R01, R04) |
| Reductions and closures | 7 | 7 PASS |
| Decimal behaviour | 8 | 8 PASS |
| Timezone behaviour | 5 | 5 PASS |
| Transaction consistency / concurrency | 6 | 5 PASS, 1 ACCEPTED |
| Determinism | 6 | 4 PASS, 2 FIXED (R01, R02) |
| Rendering, JSON, CLI | 12 | 12 PASS |
| Repository boundaries / architecture | 6 | 6 PASS |
| Frozen milestone preservation | 8 | 8 PASS |
| Error and absence paths | 9 | 9 PASS |
| Malicious persisted data | 5 | 4 PASS, 1 FIXED (R04) |

### Selected attacks worth naming

| Attack | Result |
|---|---|
| Held notional revalued at a reduction's cited price | PASS — the fold keeps the *opening* event; a reduction at 900 leaves the remainder valued at the 700 entry. Asserted in both unit and PostgreSQL tests |
| A closed position still consumes capital | PASS — proven against real persisted rows |
| An event stamped after `as_of` changes the snapshot | PASS — excluded and counted, proven through PostgreSQL |
| Two positions citing one plan exclude it twice | PASS — set membership |
| A plan cited by a *closed* position is wrongly excluded | PASS — only open positions drive exclusion, by design decision C03 |
| `total_asserted_open_notional` string→`Decimal` loses precision | PASS — canonical `_money()` output; cross-checked against a raw-SQL product |
| Held positions do not consume the concurrency cap | PASS — seeded; a ledger at the cap rejects every plan with `MAX_CONCURRENT_POSITIONS` |
| Utilisation of a zero ceiling renders as `0%` | PASS — renders as `null`/absent, never `0`, which would read as "nothing used" |
| Unreadable ledger renders as "nothing held" | PASS — `LEDGER_UNAVAILABLE`, proven through the real handler with no ledger wired |
| Incoherent persisted events take the whole brief down | PASS — caught and converted to `LEDGER_INCOHERENT` |
| Suppression is indistinguishable from an assessed pass | PASS — `computed: false` plus an explicit note in JSON |
| A concurrent M076 write tears the snapshot | PASS — a real `threading.Barrier` writer/reader race; the reader observes exactly one of the two coherent states, never a partial one, and the post-race ledger is unambiguous |
| `entrypoints` imports `decision_candidate` | PASS — architecture checker exit 0 |
| M075 or M076 source semantics changed | PASS — `git diff` shows neither module touched |
| Text and JSON disagree | PASS — parity asserted over real persisted rows |
| Forbidden vocabulary appears | PASS — `EXECUTED`, `FILLED`, `VERIFIED`, `ALLOCATED`, `MARKET_VALUE` absent from the vocabulary, parametrised test |

## Accepted, with reasons

| # | Item | Reason |
|---|---|---|
| A1 | A database-level failure in `list_all()` propagates rather than being converted to `LEDGER_UNAVAILABLE` | A missing table or a dead connection is an infrastructure fault, not an absence of positions. Converting it would hide a broken deployment behind a soft, plausible-looking verdict. `LedgerRejectionError` — bad *data* — is caught; a broken *database* is not |
| A2 | The snapshot is anchored to the session's `as_of`, not to wall-clock now | Any other anchor makes the brief non-reproducible |
| A3 | Held and proposed exposure share one capital base whose provenance differs | Named as a limitation; the alternative is inventing a second capital authority that does not exist |

## Retractions

**None.** No verdict in this review has been retracted. The design review's
four ACCEPTED items (C05, D09, H02, I03) were re-attacked here and all four
held.
