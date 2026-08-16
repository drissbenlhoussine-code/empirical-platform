# M082 - Reality Gate

## What does M082 prove?

That the platform's persistence boundary **read this M076 event back as already
durably committed** at a system-assigned instant.

## Exactly which claim level?

| Level | Claim | Reached? |
|---|---|---|
| 1 | operator asserted `recorded_at` | this is what M079-M081 use, and what M082 does **not** rely on |
| 2 | application assigned observed time | the mechanism, but not the claim |
| 3 | database assigned observed time | **no** - the database clock is not used |
| 4 | transaction committed by time X | **YES, as a one-directional upper bound** |
| 5 | evidence visible to every reader by X | **no** |

```
system_received_at <= W   IMPLIES   the event was durably committed by W
```

The converse does **not** hold. M082 may **understate** what was known and can
never **overstate** it.

## Does it prove commit time?

**No.** It proves the event *had already* committed when the instant was taken.
PostgreSQL's `track_commit_timestamp` is off, `pg_xact_commit_timestamp` errors
here, and M082 does not fake it.

## Does it prove wall-clock truth?

**No.** The instant comes from the application host clock, which can be wrong,
adjusted, or moved backward. M082 says **system-assigned**, never *true* or
*actual* time. No cryptographic claim, no monotonicity claim.

## Does it prove event truth?

**No.** It says nothing about whether the operator's assertion is honest,
whether `recorded_at` is honest, whether any trade occurred, or whether any
price was paid.

## Does it prove broker execution?

**No.**

## Does it retroactively attest legacy events?

**No, and this is enforced rather than promised.** The migration creates the
table **empty**. A receipt is never manufactured from `recorded_at`,
`event_timestamp`, or a migration time. An unattested event reports
`NO_SYSTEM_RECEIPT_EVIDENCE` and remains a valid M076 operator assertion.

## Does it cover all future events?

**No.** The M076 writer is unchanged and still reachable, so events can still be
appended without a receipt. Only events possessing a receipt are eligible for
M082-authoritative analysis, and the artifact says so.

## Does it change M079, M080 or M081?

**No.** All four frozen modules are byte-identical, and none of them references
the receipt at all. They continue to filter the operator-supplied `recorded_at`
exactly as frozen. Adopting receipt authority downstream would change the
meaning of every figure they emit and requires its own milestone.

## The one thing worth stating plainly

M079's own frozen docstring admits `recorded_at` "is an operator-supplied field,
not a system-assigned immutable" one. M082 supplies what that sentence says is
missing — but only for events that go through the attestation path, and only as
a bound, not as a commit time.

The temptation here was to claim more: to call the instant a commit time, or to
call a sequence an ordering authority, or to quietly backfill legacy events so
the coverage looked complete. Each was measured, and each was refused with the
measurement recorded.
