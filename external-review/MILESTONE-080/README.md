# MILESTONE-080 — Operator-Asserted Round-Trip Result — External Review Package

**Status: CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

> ## ⚠ This package covers TWO passes
>
> Owner review of the first candidate (`d8c8244`) found **two blocking defects
> my own 152-attack review missed**:
>
> 1. **The arithmetic was not exact.** `Decimal` products and `normalize()` are
>    context-sensitive, and at the maximum persistence-valid quantity
>    (`2147483647`) six digits were silently lost. Fixed with exact
>    scaled-integer arithmetic.
> 2. **"Every omitted component is a cost" was false.** Dividends, corporate
>    actions and taxes are not costs, so the claimed universally favourable bias
>    does not hold. Vocabulary and claims corrected before freeze.
>
> Superseded verdicts — design review E04, E06, E07, E12 and H08 — are marked
> **RETRACTED in place**, not deleted. Read
> `hostile-implementation-review.md` §"Owner review correction" first.

M080 reads the one thing M076 stored and nothing ever used: the `asserted_price`
on `REDUCED` and `CLOSED` events. It reports the arithmetic those prices imply
for the quantity the operator asserts they exited, governed entirely by M079's
knowledge-time firewall.

**This milestone emits money for the first time from operator assertions.** Read
`reality-gate.md` first — it states exactly what the number is, what it is not,
and which costs are excluded.

## Read in this order

| File | What it is |
|---|---|
| `reality-gate.md` | what the number is and is not; the misreading analysis |
| `scope-and-design-snapshot.md` | the 24-section design as it stood before implementation |
| `hostile-design-review.md` | 137 attacks, 46 design corrections **before** any code |
| `hostile-implementation-review.md` | 175 attacks; 1 defect I found (R01) + the 2 the Owner found |
| `focused-re-review.md` | the correction re-attacked in its changed area |
| `fresh-second-verification-pass.md` | separate database, different inputs, reversed recording order |
| `validation-results.md` | gates, and the baseline-vs-candidate failing-ID diff |
| `known-limitations.md` | 14 items, including one correcting M079's frozen prose |
| `owner-review-checklist.md` | what to check, and the three judgment calls |
| `changed-files.txt` | every file this branch touches |

## The two findings worth your time

**Design review T07 — a coherent fold can hide missing exits.** M076 derives a
`CLOSED` event's quantity at append time from the full history and persists it.
A knowledge-filtered prefix can therefore fold cleanly while accounting for only
part of the opened quantity. Proven by execution, fixed with a reconciliation and
a distinct status, and the shortfall proven never negative across 1521 cutoff
combinations.

**Implementation review R01 — the number did not state its own coverage.** Three
result lines were word-for-word identical whether a position was fully exited,
60% still open, or missing 4 of 10 units. The facts were present elsewhere in the
report; that is not enough, because the number is what gets quoted. Fixed at the
point of reading.

## Nothing here is erased

An intermittent M077 test failure observed once and never reproduced is recorded
in `validation-results.md` and the implementation review, unexplained rather than
quietly dropped. Two of my own probe assertions were wrong — both unanchored
substring matches — and both are recorded beside the attacks they broke.
