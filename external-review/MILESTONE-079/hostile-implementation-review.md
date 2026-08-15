# M079 — Hostile Implementation Review

A **new** adversarial pass against the real code and real persistence
behaviour. Not an independent review — the same agent wrote the code.

**126 attacks. Two genuine defects found, both by executing the code rather
than reading it; both fixed with regression tests that fail against the pre-fix
implementation.** One attack also confirmed a subtle behaviour worth locking in
permanently.

The unit suite passed 37/37 on its first run. As in M078, that was evidence the
tests were not yet pointed at the right places.

## Defects found and corrected

### R01 — a position could be silently dropped from the snapshot

**Attack.** Is the `position is None` branch in the entry loop reachable?

**Executed finding.** It is **not**. `visible` is already filtered to
`event_timestamp <= effective_as_of` *before* grouping, so every grouped key
holds at least one eligible event and `derive_position_state` always yields
exactly one position.

**Why that matters.** The branch's body was `continue`. Dead code is not merely
untidy here: if the invariant were ever broken — by a refactor moving the
filter, say — a position would **vanish from the snapshot with no entry, no
count and no limitation recording the omission**. A snapshot that silently
loses a position is worse than one that fails loudly, and this is an
evidence-availability artifact whose entire value is completeness.

**Fix.** `_fold_one_key` now returns a non-optional `DerivedPosition` and
raises `AssertionError` naming the invariant; the silent-skip branch is gone.

**Regression test.** `test_a_position_is_never_silently_dropped_from_the_snapshot`
asserts every visible key appears exactly once.

### R02 — the design review's own attack count was overstated

**Attack.** Does the design review contain the 86 attacks its header claims?

**Executed finding.** It contained **64**. The header was written before the
matrix was finished and never reconciled.

**Why that matters.** An evidence document that overstates its own rigour is
exactly the kind of claim this project exists to refuse. It is the same class
of error as a test weaker than the claim it defends.

**Fix.** Sections I–K were added with genuinely new attacks (persistence and
SQL, frozen-chain compatibility, test quality), and the header count is now
computed from the file: **81 attacks, 25 fixed**.

## Confirmed behaviour worth locking in

**Corruption invisible at an earlier knowledge cutoff is correctly reported at
a later one.** With two `OPENED` events on one key where the second is recorded
late:

```
K = T2  -> KNOWN_OPEN                     (coherent from what was known then)
K = now -> LEDGER_INCOHERENT_FOR_POSITION (the corruption is now visible)
```

Both answers are right, and their disagreement is the milestone working as
intended rather than a defect. Captured as
`test_corruption_invisible_at_an_earlier_knowledge_cutoff_is_reported_at_a_later_one`.

## Attack matrix

| Category | Attacks | Result |
|---|---|---|
| Knowledge-time filtering | 14 | 14 PASS |
| Effective-time filtering and delegation | 12 | 12 PASS |
| Boundary inclusivity, both dimensions | 12 | 12 PASS |
| Backfill and incomplete prefixes | 15 | 15 PASS |
| Incompleteness versus corruption (T07 discriminator) | 11 | 11 PASS |
| Determinism and ordering | 10 | 10 PASS |
| Entry construction and completeness | 9 | 8 PASS, 1 FIXED (R01) |
| Absence, withholding, malformed input | 11 | 11 PASS |
| Frozen-contract preservation | 10 | 10 PASS |
| Honesty and vocabulary | 12 | 12 PASS |
| Rendering, JSON, CLI | 10 | 10 PASS |
| Persistence, SQL, concurrency | 8 | 8 PASS |
| Evidence-document integrity | 2 | 1 PASS, 1 FIXED (R02) |

### Selected attacks worth naming

| Attack | Result |
|---|---|
| A backfilled assertion is visible at the earlier knowledge cutoff | PASS — executed against real rows: invisible at `T2`, visible at `T3`, same effective cutoff |
| Raw SQL and the module disagree on eligibility | PASS — `WHERE event_timestamp <= :e AND recorded_at <= :k` counted independently and matched at three cutoffs |
| A `CLOSED` without its `OPENED` is called corrupt | PASS — `INCOMPLETE_KNOWLEDGE_SEQUENCE`, `position is None`, `incoherent_position_count == 0` |
| Genuine corruption hides behind incompleteness | PASS — executed with two `OPENED` events: `LEDGER_INCOHERENT_FOR_POSITION`, carrying M076's own `POSITION_ALREADY_OPEN` |
| Incomplete and incoherent keys interfere | PASS — executed side by side; each classified independently with its own reason |
| The discriminator leaks state from the unfiltered fold | PASS — `position is None` on every refusal path; no count moves |
| Insertion order changes the answer | PASS — the second pass writes the reduction *before* the backfilled opening |
| M079 mutates the caller's event tuple | PASS — executed; tuple identity and length unchanged |
| M079 changes what M076 says | PASS — M076 re-queried after M079 and unchanged; a named test asserts M076 still sees the backfill that M079 hides |
| M079 and M076 disagree at `K = now` | PASS — asserted equal in both unit and PostgreSQL tests |
| "Recorded but not yet effective" collapses into "nothing recorded" | PASS — executed; distinct outcomes and distinct counts |
| A reduction's asserted price leaks into the report | PASS — second pass persists `401.9` and proves it never renders |
| Naive cutoff reported as a data problem | PASS — rejected at the query boundary as a request error, both dimensions |
| `entrypoints` imports `decision_candidate` | PASS — architecture checker exit 0 |
| A concurrent M076 write tears the snapshot | PASS — barrier-synchronised writer/reader race |

## Accepted, with reasons

| # | Item | Reason |
|---|---|---|
| A1 | A database-level failure propagates rather than becoming `LEDGER_UNAVAILABLE` | A dead connection is an infrastructure fault, not an absence of evidence. M077/M078 precedent |
| A2 | Filtering happens in memory rather than in SQL | Identical to M077/M078; no new query shape, so no index requirement is introduced |
| A3 | `recorded_at < event_timestamp` is permitted | M076 permits it and it is meaningful; M079 does not editorialise about the operator's clock |

## Retractions

**None of this review's own verdicts.** R02 above records that the *design*
review's header count was wrong and how it was corrected — the matrix itself
was extended rather than the claim quietly reduced.
