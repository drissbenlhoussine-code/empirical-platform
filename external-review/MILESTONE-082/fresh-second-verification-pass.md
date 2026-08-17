# M082 - Fresh Second Verification Pass

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


Same agent, so **not** an independent review. A genuinely new database, created
empty and migrated from scratch, with deliberately different inputs.

- Database `m082_second_pass`, **dropped and created empty**, full migration
  chain applied from scratch.
- Different instruments: `PLTR`, `COIN`, `ARM`, `SMCI`.
- Different event ids, positions, quantities and prices.
- Different effective timestamps (2027, not 2026).
- **Deliberately false `recorded_at`** values: five years early, and 900 days
  early.
- Concurrent attestation, retry, and a bypassed legacy event never attested.

## What the second pass attacked, and what held

| Claim | Result |
|---|---|
| A five-year-early `recorded_at` reaches the receipt | **Did not** - the instant is system-assigned and matches neither the lie nor the event timestamp |
| A bypassed legacy event gets attested | **Did not** - `NO_SYSTEM_RECEIPT_EVIDENCE`, instant `None` |
| Five concurrent attesters create multiple authorities | **Did not** - one instant, one row, and a later retry returns the same |
| The cutoff boundary drifts on a fresh database | **Did not** - excluded one microsecond before, included exactly at |

**4 passed.**

The env-var override used to point alembic at the fresh database is scoped to
the alembic call **only**; leaving it set across the yield would make later
comparisons compare a database with itself.
