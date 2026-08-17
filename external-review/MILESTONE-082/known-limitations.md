# M082 - Known Limitations

> **⚠ SUPERSEDED — this file describes an EARLIER candidate.**
> The authoritative latest correction is
> **`owner-correction-mission-findings-12-15.md`**. Where this file conflicts
> with it, that file wins. Nothing here is deleted: it is the record of what was
> believed at the time, including the parts that were wrong.


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
9. **The view is receipt-label-cutoff only.** It is built from receipts labelled
   at or before the cutoff. A later receipt, and an event with no such receipt,
   are structurally unreachable — no entry, no count, no ordering position.
10. **The view cannot report how much it excluded.** No count of hidden rows
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


---

## Added by the final authority hardening pass

20. **A persisted row now proves the causal claim, database-enforced.** A
    `BEFORE INSERT` trigger refuses a receipt whose referenced event was written
    by the current transaction. Before it, a direct SQL caller could fabricate
    both in one transaction and the report could not tell.
21. **`system_received_at`, `attested_by` and `attester_version` are NOT
    authenticated.** A direct SQL caller with write access can forge all three
    for an already-committed event. A test asserts this forgery succeeds, so the
    limitation cannot silently drift.
22. **Immutability is row-level UPDATE/DELETE under the installed trigger only.**
    `TRUNCATE` succeeds — proved by a test — and DROP TRIGGER, DROP TABLE and
    superuser mutation remain possible. Not absolute database immutability.
23. **This is a RECEIPT-LABEL-CUTOFF VIEW, not a stable snapshot.** Repeated
    evaluation at the same cutoff can return MORE, because a label can be
    backdated. Executed and recorded.
24. **`HISTORICAL_OUTPUT_POST_W_INDEPENDENT=YES` is SUPERSEDED.** The view is
    independent of receipts whose persisted *label* exceeds the cutoff, and of
    events lacking a qualifying receipt — not of receipts created later with a
    backdated label.


---

## Added by the fail-closed pass

25. **The prior-commit enforcement fails CLOSED.** The `pg_xact_status` call is
    unguarded: a future `xid8`, a failed conversion or a missing privilege
    propagates and the INSERT is refused. An earlier version caught
    `EXCEPTION WHEN OTHERS` and accepted on any failure, which made the
    invariant fail OPEN.
26. **"Unknown status accepted" means exactly one thing.** It means
    `pg_xact_status` **returned NULL**, its documented answer for a transaction
    too old to have status information. It does **not** mean "any inability to
    determine status is accepted".
27. **`aborted` is refused, not accepted.** It is unreachable for a row the
    trigger can see — an aborted writer's row is visible to nobody, measured —
    but an aborted writer's event never committed, so accepting it would be the
    wrong direction for an invariant.
28. **NULL status was not observed in this environment.** `pg_xact_status('1')`
    returns `committed`, not NULL. The NULL branch rests on PostgreSQL's
    documented old-transaction semantics and is retained as an accept; it is
    stated here rather than claimed as measured.


---

## Added by the Owner correction mission (findings 7-11)

29. **M082 does not attest the event PAYLOAD, current or historical.** M076
    carries zero user-defined immutability triggers, so its row can be updated
    after a receipt exists. Executed: an `UPDATE` changed the earlier artifact
    while the receipt identity and label stood still. The artifact is now
    receipt-only and emits no payload field at all.
30. **What a receipt binds is identity.** A stable receipt identity to an exact
    M076 event governance identity whose real `public` row was visible as coming
    from a prior committed transaction at receipt insertion.
31. **`system_received_at`, `attested_by` and `attester_version` are
    application-assigned on the sanctioned `attest()` path and unauthenticated
    as persisted values.** The database enforces the prior-committed origin of
    the referenced event and nothing else about these three.
32. **Every authority-relevant relation is schema-qualified.** An unqualified
    name resolves through the caller's `search_path`, and `pg_temp` precedes
    `public`. A non-superuser used exactly that to attest an in-progress event.
33. **The cutoff is applied in SQL.** Rows beyond it are never fetched, so a
    malformed far-future row cannot decide whether an earlier-cutoff artifact can
    be built.
34. **The status test is an explicit allowlist.** `committed` and a documented
    `NULL` accept; everything else refuses. The previous denylist would have
    accepted any future status value.
35. **The report reads one store through one query.** The split ledger/receipt
    read that raised `MissingAttestedEventError` during ordinary concurrency has
    no mechanism left.


---

## Added by the Owner correction mission (findings 12-15)

36. **RETRACTED AND REPLACED BY ITEM 42.** *(Original text:)* "Blank" is an explicitly enumerated, shared character set. The database
    and the domain use `BLANK_CHARACTERS` verbatim and are asserted equal against
    the live database. Neither engine's native whitespace notion could be made to
    match the other's: PostgreSQL's `[:space:]` excludes vertical tab and NBSP,
    and Python's `str.strip()` covers far more of Unicode.
37. **RETRACTED AND REPLACED BY ITEM 42.** *(Original text:)* Exotic Unicode whitespace outside that set is accepted by both sides.
    Stated rather than hidden. Agreement is the property that matters: the
    database is the write boundary and the domain must never reject what the
    database stored.
38. **The three metadata fields have different sanctioned-path origins and the
    same persisted status.** `system_received_at` from the host clock after
    read-back, `attester_version` from an application constant, `attested_by`
    **caller-supplied and passed through unchanged** - and all three
    **unauthenticated as persisted values**.
39. **No individual persisted receipt can be said to have come through
    `attest()`.** The database does not prove that, and neither renderer claims
    it.
40. **A crash after event commit but before receipt insertion leaves an
    unattested gap**, not a permanent state. A later explicit attestation proves
    only its own causal ordering, and its label may be numerically **earlier** or
    later. RETRACTED: "permanently unattested" and "only a LATER label" - the
    two contradicted each other and the second is false under this milestone's
    own clock model.
41. **A legacy event may later be explicitly attested**, creating only current
    causal receipt authority - never retroactive historical authority.


---

## Added by the Owner correction mission (findings 16-18)

42. **"Blank" is the COMPLETE Python 3.13 `str.strip()` set - all 29
    codepoints.** Items 36 and 37 are retracted: the earlier seven-character set
    made the two sides agree by WEAKENING Python, so `U+2003 EM SPACE` and
    twenty other blanks would have been accepted by both. The domain uses bare
    `str.strip()`; the migration carries a frozen raw literal because a
    migration is history and must not import mutable application code; a test
    asserts the two agree against the INSTALLED constraint definitions.
43. **Both boundaries refuse all 29.** The database CHECKs and the sanctioned
    command/domain construction path, proved by 120 executed CHECK attacks and
    the same 30 cases through construction.
44. **Application-clock and application-constant wording appears only under an
    explicit ON THE SANCTIONED `attest()` PATH qualification.** Generic persisted
    rows are UNAUTHENTICATED PROVENANCE.
