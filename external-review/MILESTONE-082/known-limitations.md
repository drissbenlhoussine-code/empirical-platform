# M082 - Known Limitations

1. **A receipt is an upper bound witness, not a commit time.** It says the event
   had **already** committed when the instant was taken. It does not say when it
   committed.
2. **The guarantee is one-directional.** Attested at or before the cutoff implies
   durably committed by the cutoff; the converse does not hold. M082 may
   **understate** what was known and can never overstate it.
3. **The clock is the application host clock.** It can be wrong, adjusted, or
   moved backward, and a sufficiently privileged actor can influence it. M082
   says *system-assigned*, never *true* or *actual* time.
4. **No monotonicity and no cryptographic claim.** This is not a trusted
   timestamping service.
5. **PostgreSQL commit timestamps are not used.** `track_commit_timestamp` is an
   optional, off-by-default, restart-required server setting the platform does
   not control, so commit-time authority is unavailable and is not claimed.
6. **No ordering authority is emitted.** A database sequence is assignment order,
   not commit order, and its gaps do not mean missing receipts. Ordering is by
   `(system_received_at, event_governance_id)` for determinism only.
7. **Legacy events are never attested retroactively.** The migration creates the
   table empty and a receipt is never manufactured from `recorded_at`,
   `event_timestamp` or a migration time.
8. **Coverage is not universal.** The M076 writer is unchanged and still
   reachable, so events can still be appended without a receipt. Only events
   possessing a receipt are eligible for M082-authoritative analysis.
9. **A crash between the event's commit and its attestation leaves the event
   permanently unattested.** That honest absence was chosen over a fabricated
   instant; a later reconciliation may assign only a **later true** instant.
10. **Immutability has two layers with different strengths.** The repository has
    no `UPDATE`/`DELETE` path, and a database trigger refuses both from direct
    SQL. A superuser can still drop the trigger, and `TRUNCATE` is a
    statement-level operation a row trigger does not intercept.
11. **M079, M080 and M081 do not consume this authority.** They continue to
    filter the operator-supplied `recorded_at` exactly as frozen. Adopting
    receipt authority downstream requires its own milestone.
12. **M082 emits no monetary value, no ratio, no aggregate and no performance
    figure.**
13. **`recorded_at` remains unvalidated in M076.** M082 does not fix that field;
    it supplies a separate authority beside it. An operator can still persist any
    `recorded_at` they like.
14. **Pre-existing and untouched:** the M062/M064/M065 CRLF seal debt.
