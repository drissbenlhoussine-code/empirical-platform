# M082 - Known Limitations

> **⚠ CORRECTED AFTER OWNER REVIEW.** Items 1, 2 and 10 of the first version are
> **RETRACTED**; they are quoted at the bottom rather than deleted.

1. **A receipt proves a CAUSAL fact only.** The attestation process read the
   event back from committed persistence, and only then created the receipt.
   That holds regardless of any clock.
2. **`system_received_at` is a LABEL, not a bound.** It does not bound the
   event's commit time, in either direction.
3. **A label at or before an instant W does NOT prove the event was durably
   committed by W.** The cutoff is a label comparison, not a knowledge-time
   proof. An executed backward-clock attack produces exactly this failure.
4. **M082 therefore does NOT replace M079's `recorded_at` firewall.** M079,
   M080 and M081 continue to filter operator-supplied `recorded_at` exactly as
   frozen. Adopting receipt authority downstream is a separate future milestone.
5. **The clock is the application host clock.** It can be wrong, adjusted, or
   moved backward, and a sufficiently privileged actor can influence it.
6. **No monotonicity is enforced and no cryptographic claim is made.** This is
   not a trusted timestamping service.
7. **PostgreSQL commit timestamps are not used.** `track_commit_timestamp` is an
   optional, off-by-default, restart-required server setting the platform does
   not control, so commit-time authority is unavailable and is not claimed.
8. **No ordering authority is emitted.** A database sequence is assignment
   order, not commit order, and its gaps do not mean missing receipts. Ordering
   is by `(system_received_at, event_governance_id)` for determinism only.
9. **The snapshot is receipt-cutoff only.** It is built from receipts labelled
   at or before the cutoff. A later receipt, and an event with no such receipt,
   are structurally unreachable — no entry, no count, no ordering position.
10. **The snapshot cannot report how much it excluded.** No count of hidden rows
    is offered, because any such count would itself be future-aware.
11. **An event absent from the snapshot is not attested by M082.** Absence is
    the representation, and it is never filled in from `recorded_at`,
    `event_timestamp` or a migration time.
12. **Legacy events are never attested retroactively.** The migration creates
    the table empty.
13. **Coverage is not universal.** The M076 writer is unchanged and still
    reachable, so events can still be appended without a receipt.
14. **A crash between the event's commit and its attestation leaves the event
    permanently unattested.** That honest absence was chosen over a fabricated
    instant; a later reconciliation may assign only a **later** label.
15. **Immutability has two layers with different strengths.** The repository has
    no `UPDATE`/`DELETE` path, and a database trigger refuses both from direct
    SQL. A superuser can still drop the trigger, and `TRUNCATE` is a
    statement-level operation a row trigger does not intercept.
16. **The attestation clock is injectable.** That exists so the backward-clock
    attack can be executed rather than argued. Production wiring passes nothing
    and gets `datetime.now(UTC)`; the CLI has no path to it.
17. **`recorded_at` remains unvalidated in M076.** M082 does not fix that field;
    it supplies a separate, weaker authority beside it.
18. **M082 emits no monetary value, no ratio, no aggregate and no performance
    figure.**
19. **Pre-existing and untouched:** the M062/M064/M065 CRLF seal debt.

---

## RETRACTED items from the first version

> **1. A receipt is an upper bound witness, not a commit time.** It says the
> event had **already** committed when the instant was taken. It does not say
> when it committed.
>
> **2. The guarantee is one-directional.** Attested at or before the cutoff
> implies durably committed by the cutoff; the converse does not hold. M082 may
> **understate** what was known and can never overstate it.

Both are withdrawn. They assumed the label ordered numerically with the commit,
which a backward clock breaks — while item 3 of that same list already conceded
the clock "can move backward". The two could not both be true, and the Owner
review caught the contradiction.

> **10. Immutability has two layers…** *(unchanged in substance; renumbered to
> 15.)*

Additionally, the first version's item list contained **no** statement that the
snapshot excluded future rows structurally, because it did not — see
`reality-gate.md` for the executed leak.
