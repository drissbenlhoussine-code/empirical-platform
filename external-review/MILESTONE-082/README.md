# MILESTONE-082 - Operator Event Receipt Attestation - External Review Package

**Status: IMPLEMENTED_AND_REVIEWED_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

Base `master` `28a1053`.

## The gap this closes

M079 introduced `OPERATOR_EVIDENCE_AVAILABLE_AT(E,K)` and M080/M081 build their
temporal filtering on it. All three filter on `recorded_at` — and M079's own
frozen docstring already admits what that field is:

> an operator-supplied field, not a system-assigned immutable one

So every temporal claim in the frozen chain rests on a value the operator
chooses. An operator can persist any `recorded_at` they like, including one in
the past, and M079-M081 will honour it. **M082 supplies the missing
system-assigned authority beside that field — without touching it.**

```
operator_event_receipt.system_received_at  <=  W
    IMPLIES  the M076 event was durably committed by W
```

One direction only. M082 may **understate** what was known and can never
overstate it.

## The proof that decided the design, and it was executed

The obvious implementation — a `now()` default, or `transaction_timestamp()`, or
any instant taken inside the writing transaction — **is wrong**, and not by a
margin you can wave away:

```
timestamp ASSIGNED : 13:44:14.924211
K chosen in pause  : 13:44:16.424349
rows VISIBLE at K  : 0            <- genuinely not durable
COMMIT             : 13:44:17.926

historical query "assigned_at <= K"  ->  RETURNS THE ROW
```

The row was invisible to **every** reader at `K`, yet the historical query at `K`
reported it as available. That is precisely the class of defect M079 exists to
prevent, reintroduced by the convenient design. The size of the window does not
change whether the claim is true.

The receipt is therefore written in a **separate transaction, after the event's
own commit**, which inverts the direction:

```
row visible at K            : 0
K                           : 13:56:09.230006
event COMMIT                : 13:56:10.732522
receipt system_received_at  : 13:56:10.753081
```

An event committed just before `K` but attested just after it is **excluded**.
That asymmetry is the deliberate cost of never overstating.

## What was refused rather than faked

- **Commit-time authority.** `track_commit_timestamp` is off,
  `pg_xact_commit_timestamp` errors here, and turning it on requires a
  deployment-wide server restart and is not retroactive. M082 uses no commit
  timestamp and claims no commit time.
- **Ordering authority.** A `bigserial` is assignment order, not commit order,
  and its gaps are rollbacks rather than missing receipts. No ordering authority
  is emitted.
- **Legacy backfill.** The migration creates the table **empty**. A receipt is
  never manufactured from `recorded_at`, `event_timestamp`, or a migration time.
  An unattested event reports `NO_SYSTEM_RECEIPT_EVIDENCE` — absence stays
  absence.

## The defects worth your time

**R01 (HIGH)** — the concurrent-loser path **crashed** rather than yielding.
Four concurrent attesters raced; the loser caught its unique violation and then
read the winner *inside its own unit of work*, producing
`FoundationError('Nested persistence units of work are not supported')` in three
of four callers. Found by executing four concurrent attesters, not by reading
the code.

**R02** — my migration broke a **frozen milestone's** test.
`test_m076_migration_is_reversible` used a relative `downgrade(cfg, "-1")`, which
silently assumed M076 sat at head. Fixed by targeting M076's own predecessor
revision explicitly. **This is the one frozen-milestone file this branch
touches, and it is called out for you in `owner-review-checklist.md`.**

Separately, the immutability trigger blocked **my own test cleanup** — `DELETE`
was refused — which is live confirmation the guarantee holds, and exactly what
design note D-I12 predicted. Fixtures now use `TRUNCATE`.

## Read in this order

| File | What it is |
|---|---|
| `reality-gate.md` | which of the five claim levels this reaches, and the four things it does not prove |
| `transaction-timing-evidence.md` | the executed commit-gap leak and its inversion; why commit time is unavailable |
| `scope-and-design-snapshot.md` | the 31-section design, the seven candidates, and the rejected alternatives |
| `hostile-design-review.md` | 207 attacks, 11 findings, all corrected **before** any code |
| `hostile-implementation-review.md` | 263 executed attacks; 2 defects (R01, R02) and 2 probe errors of my own |
| `concurrency-evidence.md` | the four-attester race, before and after R01 |
| `focused-re-review.md` | the R01 correction re-attacked in its changed area |
| `fresh-second-verification-pass.md` | separate database, different events, reversed attestation order |
| `validation-results.md` | every gate, and the baseline-vs-candidate failing-ID diff in both modes |
| `known-limitations.md` | 14 items |
| `owner-review-checklist.md` | the judgment calls, stated so they can be overruled |
| `changed-files.txt` | every file this branch touches |

## Nothing here is erased

Two of my own probe assertions were wrong — including a `recorded_at` substring
search that flagged the artifact's own limitation text denying it, and a
variable shadowing that reused `K` for both the cutoff and an event-kind alias.
Each is recorded beside the attack it broke. A test that fails for the wrong
reason is as misleading as one that passes for the wrong reason.

An earlier gap-proof probe was also wrong: it reused a single position key, so
three of five attempts were rejected by M076's ledger-state rules and I nearly
recorded a **narrower false gap** as the result. Re-run with distinct keys, all
five persist. The corrected measurement is the one in
`transaction-timing-evidence.md`.
