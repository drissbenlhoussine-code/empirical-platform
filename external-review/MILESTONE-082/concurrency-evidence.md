> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This file records earlier reasoning, earlier conclusions and reproduced
> defects. Some of what it says was true only of an earlier candidate, and
> some of it is explicitly withdrawn. It is preserved so the history stays
> readable; it is not imported, rendered or validated as current truth.
>
> The single active statement of M082 authority is
> [`current-authority.md`](current-authority.md).

# M082 - Concurrency Evidence

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


All executed against real PostgreSQL.

## 1. A sequence is assignment order, not commit order

Two connections:

```
A assigned seq=1 ... committed LAST
B assigned seq=2 ... committed FIRST

sequence order : [A, B]
COMMIT order   : [B, A]        ->  they disagree
```

## 2. Sequence gaps do not mean missing receipts

With a deliberate rollback between two inserts, the surviving values were
`1, 2, 3, 5`. The `4` was consumed by the rolled-back transaction. **A gap is
not lost data.**

**Consequence:** M082 emits **no sequence**. It would carry two standing
misreadings for no capability, since deterministic ordering is already available
from `(system_received_at, event_governance_id)`.

## 3. Receipt order is attestation order

Two events, the second appended later but attested **first**:

```
EV-ORD-B attested at .314
EV-ORD-A attested at .818
list_all() -> [EV-ORD-B, EV-ORD-A]
```

M082 claims exactly this and nothing more: the receipts order by when
attestation ran. No commit-order authority is claimed.

## 4. Concurrent attesters for one event

Six threads attesting the same event simultaneously:

- **no errors**
- **exactly one receipt row**
- **every caller observed the same instant**

The `UNIQUE` constraint decides; the losers report the winner's receipt rather
than failing.

> **This is where implementation defect R01 was found.** The first version read
> the winner back *while still inside the losing transaction*, which raised
> "Nested persistence units of work are not supported" — so the losers crashed
> instead of reporting the winner, which is precisely the case the branch exists
> to handle. The conflict is now only *detected* inside the transaction and the
> winner is read after it closes.

## 5. Rollback and recovery

- a rolled-back receipt leaves **no row**;
- the event correctly remains `NO_SYSTEM_RECEIPT_EVIDENCE`;
- re-attestation afterwards succeeds and records a **later, true** instant,
  never a historical one.
