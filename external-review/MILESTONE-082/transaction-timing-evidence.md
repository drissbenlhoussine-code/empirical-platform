> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This file records earlier reasoning, earlier conclusions and reproduced
> defects. Some of what it says was true only of an earlier candidate, and
> some of it is explicitly withdrawn. It is preserved so the history stays
> readable; it is not imported, rendered or validated as current truth.
>
> The single active statement of M082 authority is
> [`current-authority.md`](current-authority.md).

# M082 - Transaction Timing Evidence

> **⚠ SUPERSEDED — this file describes an EARLIER candidate.**
> The authoritative latest correction is
> **`owner-correction-mission-findings-12-15.md`**. Where this file conflicts
> with it, that file wins. Nothing here is deleted: it is the record of what was
> believed at the time, including the parts that were wrong.


> **⚠ CORRECTED AFTER OWNER REVIEW — READ THIS FIRST.**
>
> Two conclusions recorded below are **RETRACTED**. They are left in place, not
> deleted, so the original reasoning stays readable and the correction stays
> visible.
>
> **RETRACTION 1 (Owner finding 1) — "point-in-time historical snapshot".**
> The artifact was built from the CURRENT ledger, so a receipt created after the
> cutoff and an event created after the cutoff both changed the historical
> output. Executed: two databases with identical evidence at W produced
> `ATTESTED_AFTER_CUTOFF` vs `NO_SYSTEM_RECEIPT_EVIDENCE`, differing counts, and
> a leak of a future event's id, position and instrument symbol. Any sentence
> below claiming the artifact is a point-in-time snapshot, or that "nothing
> attested after the cutoff influences any figure", is **SUPERSEDED** by
> `reality-gate.md`. The snapshot is now built FROM RECEIPTS labelled at or
> before the cutoff; `ATTESTED_AFTER_CUTOFF`, `NO_SYSTEM_RECEIPT_EVIDENCE`,
> `attested_after_cutoff_count` and `unattested_count` no longer exist.
>
> **RETRACTION 2 (Owner finding 2) — the wall-clock upper bound.**
> Any sentence below asserting `commit_time(event) < system_received_at`, that
> `system_received_at <= W` implies durable commit by W, that the guarantee is
> "one-directional", or that M082 "can never overstate", is **RETRACTED**. A
> backward host clock breaks it, and the attack is executed in
> `test_a_backward_clock_breaks_the_wall_clock_implication`. What survives is
> the CAUSAL claim: the read-back preceded the receipt. **M082 therefore does
> NOT replace M079's `recorded_at` firewall.**
>
> Renames that followed: `attested_known_by` → `events_with_receipt_labelled_by`,
> `attested_as_of` → `receipt_label_cutoff`, `--attested-as-of` →
> `--receipt-label-cutoff`.


Everything here was **executed** against PostgreSQL 16.13. Nothing is argued.

## 1. All in-transaction timestamps precede COMMIT

| Function | Behaviour inside one transaction |
|---|---|
| `transaction_timestamp()` | frozen at transaction start; does **not** advance |
| `statement_timestamp()` | advances per statement |
| `clock_timestamp()` | advances continuously |

Measured by sleeping one second inside a single transaction and re-reading all
three. **None of them is a commit time.**

## 2. The commit-gap leak, proved

A transaction assigned its timestamp and paused before committing. `K` was
chosen during the pause.

```
timestamp ASSIGNED : 13:44:14.924211
K chosen in pause  : 13:44:16.424349
rows VISIBLE at K  : 0             <- genuinely not durable
COMMIT             : 13:44:17.926

historical query "assigned_at <= K"  ->  RETURNS THE ROW
```

The row was invisible to every reader at `K`, yet the historical query at `K`
reports it as available. **This is the same class of defect M079 exists to
prevent.** The size of the window is irrelevant to whether the claim is true.

## 3. The post-commit receipt inverts it, proved

The identical pause, against the **real M082 attestation path**:

```
row visible at K            : 0
K                           : 13:56:09.230006
event COMMIT                : 13:56:10.732522
receipt system_received_at  : 13:56:10.753081
```

`system_received_at` falls **after** the commit, and therefore after `K`. The
historical query at `K` correctly returns **nothing**.

```
RETRACTED (owner review finding 2): this inequality is NOT proved and is false
under a backward host clock. Kept verbatim as the original reasoning.

commit_time(event)  <  system_received_at(receipt)
  =>  system_received_at <= K  IMPLIES  durably committed by K
```

The converse does not hold, and that asymmetry is deliberate: an event committed
just before `K` but attested just after it is **excluded**. M082 may understate
what was known and can never overstate it.

> **⚠ RETRACTED (owner review finding 2).** The "can never overstate" guarantee
> above is withdrawn; the executed backward-clock attack disproves it.

## 4. Commit-time authority is unavailable, and is not faked

```
track_commit_timestamp = off
SELECT pg_xact_commit_timestamp(xmin)
  -> ObjectNotInPrerequisiteState: could not get commit timestamp data
```

Off by default, requires a **server restart**, not retroactive, and
deployment-wide. M082 uses no commit timestamp and claims no commit time.

## 5. What the authority level actually is

| Level | Claim | M082 |
|---|---|---|
| 1 | operator asserted `recorded_at` | not this |
| 2 | application assigned observed time | **not quite this** |
| 3 | database assigned observed time | not this |
| 4 | transaction committed by time X | **THIS, as an upper bound** *(RETRACTED)* |
| 5 | evidence visible to every reader by X | not claimed |

M082 reaches level 4 **as a one-directional bound**: the event *had already*
committed when the instant was taken. It does not reach the exact commit time,
and it does not reach level 5.

> **⚠ RETRACTED (owner review finding 2).** The level-4 row and the paragraph
> above are withdrawn. M082 does **not** reach level 4. `system_received_at` is
> a system-assigned LABEL and bounds nothing: an executed backward-clock attack
> produces a label preceding the event's real commit. What M082 reaches is
> **level 2 — an application-assigned observation label — plus a causal ordering
> proof** that the event was read back from committed persistence before the
> receipt was created. Kept verbatim as the original reasoning; see
> `reality-gate.md` for the current statement.
