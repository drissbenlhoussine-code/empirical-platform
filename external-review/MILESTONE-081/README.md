# MILESTONE-081 - Operator-Asserted Round-Trip Result Ratio - External Review Package

**Status: IMPLEMENTED_AND_REVIEWED_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

Base `master` `43eb2c3defdc2964af45be5eaa5c3789743e3475`.

## The gap this closes, and the one it was careful not to open

M080 emits a per-position monetary value **and forbids a reader to combine two of
them**, because no currency is persisted on an M076 event. That left a reader
asking "which of these two positions did better" with exactly one option - divide
the money themselves - which is the unsupported act M080's own limitation
forbids. **M080 closed an arithmetic gap and opened a comparison hazard.**

M081 supplies the one comparison primitive that is provably safe:

```
                asserted_round_trip_result
    ratio  =  ----------------------------------------
              asserted_entry_cost_for_exited_quantity
```

dimensionless by **exact** cancellation, per position, never aggregated - and it
makes the unsafe comparison structurally impossible by emitting no monetary value
at all.

## The finding that decided the milestone

**There is no instrument-level quote-currency authority anywhere in this
repository.** `InstrumentMaster` does not have one. M067's `currency` denominates
a simulated study's capital policy, not an operator's asserted execution price.
So candidate A - a denomination authority - was **rejected rather than invented**,
and the milestone that *needs* no currency was built instead.

## Two bounds proved, not guarded

Both follow from frozen M076's `asserted_price > 0` and positive integer
quantities:

- the denominator is strictly positive, so **division by zero is unreachable**;
- exit consideration is a sum of strictly positive terms, so the ratio is
  **strictly greater than -1, always**. A total loss would require an asserted
  exit price of zero, which M076 rejects.

## The defect worth your time

**R01** - the decimal approximation rounded `ROUND_HALF_EVEN` and, at the
`NUMERIC(20,6)` boundary, printed **`-1`**: the exact value the bound above
proves unreachable. A `float()` of that ratio is also exactly `-1.0`. Found by
executing the boundary, not by reading the code. Rounding is now truncation
toward zero, which guarantees the approximation can never show a magnitude the
ledger's arithmetic cannot produce.

## Read in this order

| File | What it is |
|---|---|
| `reality-gate.md` | what the number is, its dimension, its denominator authority, and what may not be done with it |
| `scope-and-design-snapshot.md` | the 27-section design, including the candidate ranking and the rejected alternatives |
| `hostile-design-review.md` | 156 attacks, 9 findings, all corrected **before** any code |
| `hostile-implementation-review.md` | 232 executed attacks; 1 defect (R01) and 10 wrong probe assertions of my own |
| `focused-re-review.md` | the R01 correction re-attacked in its changed area |
| `fresh-second-verification-pass.md` | separate database, different instruments, three exits, reversed knowledge order |
| `validation-results.md` | every gate, and the baseline-vs-candidate failing-ID diff in both modes |
| `known-limitations.md` | 18 items |
| `owner-review-checklist.md` | the seven judgment calls, stated so they can be overruled |
| `changed-files.txt` | every file this branch touches |

## Nothing here is erased

Ten of my own probe assertions were wrong - including a forbidden-token search
that reported `EDGE` inside `KNOWLEDGE_AS_OF`, and a currency search that flagged
the artifact's own denial. Each is recorded beside the attack it broke. A test
that fails for the wrong reason is as misleading as one that passes for the wrong
reason.
