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

---

# Owner review correction — a temporal leak my own review missed

**Status: this section supersedes T07 and C05 in `hostile-design-review.md`.
Those entries are retained there, visibly retracted, not deleted.**

## What the Owner found

M079 filtered candidate evidence correctly with `recorded_at <= K`. But when the
knowledge-filtered sequence failed to fold, the implementation **re-folded the
same key against the unfiltered event set** to decide between
`INCOMPLETE_KNOWLEDGE_SEQUENCE` and `LEDGER_INCOHERENT_FOR_POSITION`.

That unfiltered set can contain assertions with `recorded_at > K`. So **future
knowledge decided the status emitted at historical K.**

No quantity or state was ever copied from the future fold — my design review
checked exactly that, and a test asserted it. Checking it is what made the
defect invisible to me: I verified that no *value* leaked and never asked
whether the *classification* leaked. It did.

The worked case:

| | |
|---|---|
| At `K` | the `CLOSED` is visible; its `OPENED` is not yet recorded |
| Later | the `OPENED` is recorded, after `K` |
| Old code said | `INCOMPLETE_KNOWLEDGE_SEQUENCE` — *because it looked at the later OPENED* |
| The truth at `K` | the system could not know whether this was temporary incompleteness or genuine incoherence |

## Two further leaks the same rule exposes

Once the rule is stated properly — *no assertion with `recorded_at > K` may
influence position state, status, reason, counts, limitations, ordering or
classification* — two fields fail it that neither my design review nor my
implementation review questioned:

| Field | Why it leaks |
|---|---|
| `total_event_count` | `len(events)` over the whole ledger; grows with rows recorded after `K` |
| `excluded_by_knowledge_cutoff` | literally counts the rows the firewall hid, so it is a direct readout of post-cutoff data |

The limitation string carrying that second count leaked with it.

## What replaced them

| Before | After |
|---|---|
| `INCOMPLETE_KNOWLEDGE_SEQUENCE` + `LEDGER_INCOHERENT_FOR_POSITION` | a single `UNRESOLVED_KNOWLEDGE_SEQUENCE` |
| `incomplete_knowledge_count`, `incoherent_position_count` | `unresolved_position_count` |
| `total_event_count` | `known_event_count` — assertions recorded **by** `K` |
| `excluded_by_knowledge_cutoff` | *removed*; a static limitation explains why no such count can exist |
| `excluded_by_effective_cutoff` | **kept** — computed only from evidence recorded by `K`, so it does not leak |

`UNRESOLVED_KNOWLEDGE_SEQUENCE` means exactly: *the evidence recorded by this
cutoff does not form a coherent fold, and from that evidence alone it cannot be
known whether this is temporary incompleteness or underlying ledger
incoherence.* M076's own rejection reason for the **filtered** fold is still
reported, because that is derived from visible evidence and is leak-free.

Temporal evolution stays legitimate: a query at a later `K2` may fold
successfully, or may remain unresolved. Neither outcome reaches back and
strengthens the answer at `K`.

## Why the fix is structural, not disciplinary

The first candidate *stated* the guarantee and then broke it three fields later.
Restating it would not have been a fix. So the snapshot logic now lives in
`_snapshot_from_known_evidence(known, effective_as_of, knowledge_as_of)`, which
is **never given the unfiltered events**. A post-cutoff row is not merely unused
there — it is unreachable. `build_operator_evidence_snapshot` reads `events`
exactly once, through `events_known_by`, and hands on only the survivors.

A test asserts this by inspecting the function's own signature and source, so a
future refactor that re-introduces the unfiltered set fails loudly rather than
silently.

## Claim language corrected

`recorded_at` is an operator-supplied field, not a system-assigned immutable
receipt time. M079 therefore no longer claims to report *what evidence was
actually available at K*. It claims to report **what the ledger records as
having been recorded by K**, and the weaker claim is stated in the banner and
carried as a limitation on every snapshot, including the empty and withheld
ones.

## Attacks run for this correction

| # | Attack | Result |
|---|---|---|
| O01 | `CLOSED` visible at `K`, `OPENED` recorded after `K` | `UNRESOLVED_KNOWLEDGE_SEQUENCE`, no state |
| O02 | Same visible prefix, future `OPENED` present vs absent | **Snapshots equal** |
| O03 | `REDUCED` visible, `OPENED` recorded later | same unresolved status |
| O04 | Advance `K` past the backfill | folds normally; earlier answer unchanged |
| O05 | Future event, different instrument, other position | no change at `K` |
| O06 | Future duplicate-governance-id event | no change at `K` |
| O07 | Every snapshot field, four future-row shapes, parametrised | no field differs |
| O08 | Ordering with a future row that would sort first | ordering unchanged |
| O09 | Limitations with a future row | limitations identical; no hidden-count string present |
| O10 | Healthy `KNOWN_OPEN` path with a future `REDUCED` | quantity unchanged at `K` |
| O11 | Status vocabulary itself | exactly three members; no future-resolvable verdict exists |
| O12 | Data incoherent *within* the visible window | also merely `UNRESOLVED`; M076's reason still distinct |
| O13 | Unresolved at `K` may stay unresolved at `K2` | holds |
| O14 | `_snapshot_from_known_evidence` signature and source | cannot reach post-cutoff evidence |
| O15 | Banner claim language | records-recorded, not actually-available |
| O16 | Operator-supplied caveat on every snapshot shape | present on all three |
| O17 | **Two real PostgreSQL databases**, identical `recorded_at <= K` rows, different afterwards | identical snapshot, identical JSON, identical text |
| O18 | The same two databases at a later `K` | they diverge, proving they were genuinely different all along |
| O19 | Second pass: append post-cutoff rows between two reads | answer byte-identical; visible once `K` advances |
| O20 | M076 through M079 | M076 still sees every event; unchanged by the call |

**20 attacks, 3 defects** (the discriminator, `total_event_count`,
`excluded_by_knowledge_cutoff`), all three fixed.

## Two things this correction cost, stated plainly

1. **The product got less informative.** An operator can no longer be told that
   a gap is "probably just a late recording". That distinction was never ours to
   make at `K`.
2. **The snapshot can no longer say how much it hid.** Counting hidden
   assertions requires reading them. The limitation now says so explicitly
   rather than quietly omitting the number.

## One correction to my own earlier evidence

My first-candidate report called the T07 discriminator "load-bearing" and the
central safeguard against incompleteness masking corruption. That claim was
wrong, and it appeared in the design review header, the reality gate, the
validation results, the PR body and the A–AF report. It is retracted in each
place rather than removed.
