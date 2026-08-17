# M082 - Reality Gate

> **⚠ SUPERSEDED — this file describes an EARLIER candidate.**
> The authoritative latest correction is
> **`owner-correction-mission-findings-12-15.md`**. Where this file conflicts
> with it, that file wins. Nothing here is deleted: it is the record of what was
> believed at the time, including the parts that were wrong.


> **⚠ CORRECTED AFTER OWNER REVIEW.** Two claims that stood in the first version
> of this file are **RETRACTED**. Both are quoted below rather than deleted, so
> the original reasoning and its failure remain readable.
>
> 1. **RETRACTED — the wall-clock upper bound.** This file previously reached
>    "level 4, as a one-directional upper bound", and said M082 "may understate
>    what was known and can never overstate it". Neither was proved, and both
>    are false under a backward host clock — a possibility this same file
>    already admitted, so the two statements could never both be true.
> 2. **RETRACTED — the point-in-time snapshot.** The artifact was built from the
>    CURRENT ledger, so a receipt created after the cutoff, and an event created
>    after the cutoff, both changed the historical output. It was a retrospective
>    coverage report, not a knowledge snapshot.

## What does M082 prove?

**A causal fact, and nothing more:**

    the attestation process READ THIS EVENT BACK from committed persistence,
    and only THEN created this receipt.

That holds by program order plus PostgreSQL transaction visibility: `attest`
runs in its own transaction, so it can observe the event only if the event's
transaction has already committed. **It does not depend on any clock.**

`system_received_at` is a **system-assigned label** recorded beside that fact.

## Exactly which claim level?

| Level | Claim | Reached? |
|---|---|---|
| 1 | operator asserted `recorded_at` | what M079–M081 use; what M082 does **not** rely on |
| 2 | application assigned observed time | **YES — this is the label, and it is only a label** |
| 3 | database assigned observed time | **no** — the database clock is not used |
| 4 | transaction committed by wall-clock time X | **NO — RETRACTED, see below** |
| 5 | evidence visible to every reader by X | **no** |

### RETRACTED: the level-4 claim

The first version of this file said:

> ```
> system_received_at <= W   IMPLIES   the event was durably committed by W
> ```
> M082 may **understate** what was known and can never **overstate** it.

**That is withdrawn.** Executed counter-example, against real PostgreSQL:

```
real commit (wall clock) : 15:12:55.926191
receipt label            : 15:02:55.926191   <- clock moved BACK ten minutes
cutoff W (between them)  : 15:07:55.926191
W < real commit          : True

snapshot at W includes the event : True
```

The event was **not** committed at real wall-clock `W`, yet the snapshot lists
it. Causal ordering is not numerical wall-clock ordering when the clock can
jump. So M082 **can** overstate, and the "never overstate" guarantee is gone.

What survives is the causal claim, which never depended on the clock.

## Does it prove commit time?

**No.** PostgreSQL's `track_commit_timestamp` is off, `pg_xact_commit_timestamp`
errors here, and M082 does not fake it.

## Does it prove wall-clock truth?

**No — and this is now stated without the earlier hedge.** The label comes from
the application host clock, which can be wrong, adjusted, or moved backward. No
monotonicity is enforced. No cryptographic claim is made.

## Does comparing the label to a historical instant prove availability then?

**No.** The cutoff is a **label comparison**, not a knowledge-time proof.

## Does M082 replace M079's `recorded_at` firewall?

**No.** This is the honest consequence of the retraction, and it is the most
important sentence in this file. M082 supplies a **smaller true primitive** —
causal receipt attestation — instead of a **larger false one**. M079, M080 and
M081 continue to filter operator-supplied `recorded_at` exactly as frozen.

Binding an evaluation to receipt identities, or to an explicitly persisted
receipt set captured at decision time, rather than reconstructing wall-clock
availability afterwards, is a **future milestone**. It is not started.

## Does a PERSISTED ROW prove the causal claim?

**Yes, now — database-enforced.** A `BEFORE INSERT` trigger refuses a receipt
whose referenced event was written by the current transaction.

### RETRACTED: the previous pass's implicit assumption

Before that trigger, the causal claim held only for receipts produced through
`attest()`. A direct SQL caller could insert an event and its receipt in ONE
transaction — the foreign key was satisfied because the event was visible to
that transaction — and the report listed the result as authoritative with a
forged 2020 label and a forged attester. Reproduced before being fixed.

The mechanism was chosen by measurement: `xmin = pg_current_xact_id()::xid`
**misses savepoints** (a subtransaction gets its own, higher xid), and an xid
ordering comparison **falsely refuses** a concurrent committed writer that holds
a higher xid. The trigger instead asks whether the writing transaction is still
`in progress`, which is correct in every case measured.

## Does the enforcement fail closed?

**Yes, now.** The status call is unguarded, so any checker failure propagates and
the INSERT is refused.

### CORRECTED: the enforcement used to FAIL OPEN

The first version of the trigger wrapped the status call in
`EXCEPTION WHEN OTHERS` and treated any failure as an unknown status, which was
then **accepted**. Executed demonstration: a role without `EXECUTE` on
`pg_xact_status` raises `permission denied for function pg_xact_status`, and the
handler converted that into an accept. For an invariant, unexpected failure of
the checker must never become permission to insert.

Two different unknowns, now kept apart:

| Situation | Behaviour |
|---|---|
| `pg_xact_status` **returns NULL** (documented old-transaction answer) | accepted — a live transaction always has its CLOG |
| the checker **fails** (future `xid8`, failed conversion, missing privilege) | **refused — fails closed** |
| status `in progress` | refused |
| status `aborted` | refused — unreachable for a visible row, but never accepted |
| status `committed` | accepted |

## What is NOT database-enforced

`system_received_at`, `attested_by` and `attester_version` are **unauthenticated
labels**. A direct SQL caller with write access can insert a receipt for an
**already committed** event carrying any of the three, and this view cannot
distinguish it from one `attest()` produced. That forgery is asserted by a test,
so the limitation cannot silently drift.

Immutability is **row-level UPDATE/DELETE under the installed trigger only**.
`TRUNCATE` succeeds — proved by a test — and DROP TRIGGER, DROP TABLE and
superuser mutation remain possible. This is not absolute database immutability.

## Is the artifact a stable point-in-time snapshot?

**No, and it is no longer called one.** It is a **RECEIPT-LABEL-CUTOFF VIEW**: a
predicate over the labels in the CURRENT persisted receipt set.

### SUPERSEDED: `HISTORICAL_OUTPUT_POST_W_INDEPENDENT=YES`

That claim was too broad. Because a label can be backdated, a receipt created
LATER can carry a qualifying label. Executed, through the real attestation path:

```
entries at cutoff (before) : ['EV-COMMITTED']
entries at cutoff (after)  : ['EV-COMMITTED', 'EV-LATE']
object / text / json identical : False / False / False
```

Control: a later FORWARD-labelled receipt leaves the cutoff untouched. Only
backdating destabilises it.

The precise statement is: the view is independent of receipts whose persisted
**label** is greater than the cutoff, and of events lacking a qualifying
receipt; it is **NOT** stable against receipts created later with a **backdated**
label. No hidden creation timestamp was added to paper over this — that would
reopen the authority problem one layer down.

## Is the artifact free of future interference by label?

**Yes, now — structurally.** The snapshot is built **from receipts** whose label
is at or before the cutoff. A later receipt and an unreceipted event cannot
contribute an entry, a count, or an ordering position.

### RETRACTED: the earlier construction

The first version built entries from `ledger.list_all()` and emitted
`ATTESTED`, `ATTESTED_AFTER_CUTOFF` and `NO_SYSTEM_RECEIPT_EVIDENCE`, plus
`attested_after_cutoff_count` and `unattested_count`. Its banner said:

> "Nothing attested after the cutoff influences any figure below."

**That sentence was false.** Executed, two databases with identical evidence at
`W`:

```
ATTACK A - a receipt created after W, in DB-A only
  DB-A E2 status : ATTESTED_AFTER_CUTOFF     DB-B E2 status : NO_SYSTEM_RECEIPT_EVIDENCE
  after_cutoff_count  A=1 B=0                unattested_count  A=0 B=1

ATTACK B - a new event added after W, in DB-A only
  entry count A=3 B=2
  future event id / position / symbol leaked into the historical text : True / True / True
```

After the correction, the same two attacks give **identical full object,
identical text, identical JSON** on both sides.

## Are there future-tail counts?

**No.** `attested_after_cutoff_count` and `unattested_count` are removed and
**not replaced**. The snapshot deliberately **cannot say how much it excluded**,
and says so in its own text — any such count would itself be future-aware.

## Does it retroactively attest legacy events?

**No, and this is enforced rather than promised.** The migration creates the
table **empty**. A receipt is never manufactured from `recorded_at`,
`event_timestamp`, or a migration time. An unattested event simply does not
appear, and remains a valid M076 operator assertion.

## Does it cover all future events?

**No.** The M076 writer is unchanged and still reachable.

## Does it change M079, M080 or M081?

**No.** All frozen modules are byte-identical, and none references the receipt.

## The one thing worth stating plainly

The temptation in this milestone was to claim more than the mechanism supports:
to call a label a commit-time bound, to call a present-day inventory a
historical snapshot, to call a sequence an ordering authority, or to backfill
legacy events so coverage looked complete.

The first version of M082 resisted three of those four and **fell for the first
two**. Both were caught by the Owner, both are reproduced here by execution
rather than argument, and both corrections make the milestone's claim **smaller
and true** rather than larger and false.
