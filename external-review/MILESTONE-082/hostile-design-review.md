# M082 - Hostile Design Review

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


**207 attacks against the design before a single line of M082 was written.**
The decisive ones were **executed against real PostgreSQL**, not argued — a
design attack that is only reasoned about is worth less than one that runs.
**11 findings changed the design.**

---

## Findings that changed the design

### D-F01 (CRITICAL) — an in-transaction receipt timestamp leaks knowledge

Executed. A transaction assigned its timestamp then paused before commit:

```
timestamp ASSIGNED : 13:44:14.924211
K chosen in pause  : 13:44:16.424349
rows VISIBLE at K  : 0            <- genuinely not durable
COMMIT             : 13:44:17.926

historical query "assigned_at <= K"  ->  RETURNS THE ROW
```

The row was invisible to every reader at `K`, yet the historical query at `K`
reports it available. **This is the same class of defect M079 exists to
prevent**, reintroduced through the back door.

**Correction:** the receipt moved to a **second transaction, after the event has
committed and been read back**. Re-executed with the identical pause, the
post-commit query at `K` correctly returns nothing.

### D-F02 (HIGH) — `transaction_timestamp()` is the worst available choice

Measured: inside one transaction, `transaction_timestamp()` is frozen at
transaction *start* and does not advance, while `statement_timestamp()` and
`clock_timestamp()` do. A long transaction could therefore stamp a receipt
arbitrarily far before its own commit.

**Correction:** no database-side timestamp is used at all; see D-F03.

### D-F03 (HIGH) — commit-time authority is unavailable, and must not be faked

```
track_commit_timestamp = off
pg_xact_commit_timestamp(xmin) -> ObjectNotInPrerequisiteState
```

It is off by default, needs a **server restart**, is not retroactive, and is a
deployment-wide setting the platform does not control.

**Correction:** M082 uses no commit timestamp and **claims no commit time**. The
authority level is stated as an upper-bound witness instead.

### D-F04 (HIGH) — a sequence is assignment order, not commit order

Executed with two connections: `A` took `seq=1` and committed **last**; `B` took
`seq=2` and committed **first**. Sequence order `[A,B]`, commit order `[B,A]`.

A deliberate rollback then produced surviving values `1, 2, 3, 5` — a gap that
does **not** mean a missing receipt.

**Correction:** **no sequence is emitted.** It would carry two standing
misreadings ("commit order", "gap = lost data") for no capability, since
deterministic ordering is already available from
`(system_received_at, event_governance_id)`.

### D-F05 (HIGH) — my own gap probe was wrong, and understated the gap

My first `recorded_at` probe reused one position key, so three of five attempts
were rejected — by the ledger's open/closed rules, not by any time rule. I
briefly read that as evidence of a `recorded_at` bound.

Re-run with distinct keys, **all five persist**, including year 1999, year 2999,
a future date, and a `recorded_at` before its own `event_timestamp`.

**Correction:** the gap statement is rewritten from measurement. Recorded because
I nearly wrote a *false* statement in the safe-sounding direction.

### D-F06 (HIGH) — one transaction versus two is a correctness choice, not convenience

Both were analysed. One transaction avoids a partial commit but **guarantees**
the D-F01 leak. Two transactions admit a crash window in which an event has no
receipt.

**Correction:** two transactions, deliberately. An unreceipted event is an
**honest absence**, recoverable later by a clearly-later receipt. A pre-commit
receipt is a **false presence**, recoverable never.

### D-F07 (HIGH) — the old M076 writer still exists

M082 cannot claim all future events carry receipt authority without disabling a
frozen writer.

**Correction:** eligibility is explicit — only events possessing a valid receipt
are eligible for M082-authoritative analysis; unreceipted events remain valid
M076 assertions with no M082 authority.

### D-F08 (MEDIUM) — "append-only" was going to be overclaimed

The M076 repository has no `UPDATE`/`DELETE`, but nothing stops direct SQL.

**Correction:** two layers, each named for what it is. A `BEFORE UPDATE OR
DELETE` trigger was **executed** and genuinely blocks direct SQL, so receipts are
*database-enforced immutable*; the surviving caveat (a superuser can drop the
trigger) is stated rather than hidden.

### D-F09 (MEDIUM) — `ON DELETE CASCADE` would destroy evidence

**Correction:** `ON DELETE RESTRICT`. If an M076 row were ever removed, receipt
evidence must not silently vanish with it.

### D-F10 (MEDIUM) — the conservative error direction had to be stated, not assumed

`system_received_at <= W` implies durable commit by `W`; the converse fails.

**Correction:** both directions are stated on every report — M082 may
**understate** what was known and can never **overstate** it.

### D-F11 (LOW) — vocabulary collision with M079

**Correction:** M079 says `knowledge_as_of`; M082 says `attested_as_of`. Two
products, two authorities, two words.

---

## CLOCK — 24 attacks

| # | Attack | Result |
|---|---|---|
| D-C01 | which clock is it? | application host clock, named explicitly |
| D-C02 | database server clock instead | rejected — would reopen "which clock relative to what" after the read-back |
| D-C03 | external trusted time service | not used; no such dependency claimed |
| D-C04 | `transaction_timestamp()` frozen at txn start | **measured true** — D-F02 |
| D-C05 | `statement_timestamp()` advances | measured true |
| D-C06 | `clock_timestamp()` advances | measured true |
| D-C07 | all three precede commit | **measured true** |
| D-C08 | host clock simply wrong | stated as a limitation, not denied |
| D-C09 | host clock adjusted by NTP | same |
| D-C10 | clock moves backward | possible; M082 claims no monotonicity |
| D-C11 | clock moves forward abruptly | same |
| D-C12 | two receipts share an instant | permitted; ordering tie-broken by `event_governance_id` |
| D-C13 | operator influences the clock | possible for a privileged operator; stated |
| D-C14 | DB admin changes server clock | irrelevant — the server clock is not used |
| D-C15 | caller supplies the receipt instant | **forbidden** — not a parameter |
| D-C16 | tests monkeypatch the clock | possible in tests; not a production path, and stated |
| D-C17 | naive datetime reaches the receipt | refused at the boundary |
| D-C18 | non-UTC offset stored | `TIMESTAMPTZ` round-trip **executed**, tz-aware on read |
| D-C19 | timezone lost on read | no — verified |
| D-C20 | is it called "true time"? | **never** — "system-assigned" only |
| D-C21 | is it called "actual time"? | never |
| D-C22 | leap second | no claim depends on sub-second exactness |
| D-C23 | is monotonicity claimed? | **no** |
| D-C24 | is a cryptographic claim made? | **no** — not a timestamping authority |

## TRANSACTION — 22 attacks

| # | Attack | Result |
|---|---|---|
| D-T01 | timestamp before commit | **the leak, proved** — D-F01 |
| D-T02 | post-commit stamp closes it | **proved** by re-running the same pause |
| D-T03 | rollback after timestamp | receipt never exists; event unreceipted |
| D-T04 | commit delayed arbitrarily | irrelevant — the stamp is after commit |
| D-T05 | connection dropped mid-receipt | receipt txn rolls back |
| D-T06 | deadlock | rolls back; retry permitted |
| D-T07 | retry after failure | later, true instant recorded |
| D-T08 | event txn rolls back | no event, and the FK refuses a receipt |
| D-T09 | receipt without read-back | forbidden by design — the read-back is what proves durability |
| D-T10 | read-back sees uncommitted row | impossible at READ COMMITTED |
| D-T11 | is commit time claimed? | **no** — D-F03 |
| D-T12 | is `pg_xact_commit_timestamp` depended on? | **no** — unavailable, proved |
| D-T13 | optional server config assumed | **none** |
| D-T14 | one-transaction convenience | rejected — D-F06 |
| D-T15 | crash between phases | event unreceipted; honest absence |
| D-T16 | is that crash window hidden? | no — §16 of the design |
| D-T17 | long-running receipt txn | the stamp is taken in-process after the read |
| D-T18 | nested transaction | not used |
| D-T19 | autocommit assumption | not relied on |
| D-T20 | isolation level assumption | only READ COMMITTED visibility, the PostgreSQL default |
| D-T21 | receipt txn reads a *later* event state | irrelevant — only existence is read |
| D-T22 | two-phase commit | not used, not needed |

## CONCURRENCY — 20 attacks

| # | Attack | Result |
|---|---|---|
| D-N01 | A and B overlap | independent receipts |
| D-N02 | A stamps first, commits last | **proved** ordering hazard — D-F04 |
| D-N03 | sequence first, commit last | same; no sequence emitted |
| D-N04 | duplicate receipt concurrently | `UNIQUE` on `event_governance_id`; one survives |
| D-N05 | loser sees a crash | no — surfaced as "already attested" |
| D-N06 | duplicate event id concurrently | M076's own unique constraint |
| D-N07 | is commit order claimed? | **no** |
| D-N08 | is receipt order claimed as knowledge order? | only that each receipt implies commit-by-its-instant |
| D-N09 | ordering under equal instants | tie-broken by id |
| D-N10 | interleaved attesters, different events | independent |
| D-N11 | attester crashes holding a lock | txn rolls back |
| D-N12 | lost update between attesters | impossible — no `UPDATE` path |
| D-N13 | phantom receipt | `UNIQUE` prevents |
| D-N14 | receipt for event mid-append | FK refuses until committed |
| D-N15 | sequence gaps read as missing data | no sequence — D-F04 |
| D-N16 | ordering by insertion order | never |
| D-N17 | concurrent read during attestation | reads see committed state only |
| D-N18 | attester version skew | recorded in `attester_version` |
| D-N19 | is a stable committed prefix claimed? | **no** — that is the rejected watermark, M083 |
| D-N20 | out-of-order commits break a prefix | **proved**, and is exactly why C was rejected |

## LEGACY — 16 attacks

| # | Attack | Result |
|---|---|---|
| D-L01 | old event, no receipt | `NO_SYSTEM_RECEIPT_EVIDENCE` |
| D-L02 | backfill from `recorded_at` | **forbidden** |
| D-L03 | backfill from `event_timestamp` | **forbidden** |
| D-L04 | backfill at migration time | **forbidden** — the migration creates the table empty |
| D-L05 | backfill from a "created_at" guess | no such column exists |
| D-L06 | migration writes any row | **none** |
| D-L07 | legacy event treated as attested | no — eligibility is explicit |
| D-L08 | legacy event silently excluded | no — it appears with its absence state |
| D-L09 | absence rendered as a zero/instant | never |
| D-L10 | reconciliation assigns a historical instant | **forbidden**; only a later true one |
| D-L11 | is the M076 event invalidated? | **no** — it remains a valid operator assertion |
| D-L12 | does M079 change for legacy rows? | no — M079 untouched |
| D-L13 | operator can request a backdated receipt | not a parameter |
| D-L14 | "attested" implied for all events | denied in the artifact |
| D-L15 | count of unreceipted events implies loss | stated as absence of authority, not loss |
| D-L16 | is absence recoverable? | yes, by a later honest receipt |

## BYPASS — 12 attacks

| # | Attack | Result |
|---|---|---|
| D-B01 | direct M076 repository append | still possible; produces an unreceipted event |
| D-B02 | old CLI | unchanged, unreceipted |
| D-B03 | test factory path | same |
| D-B04 | malicious chosen `recorded_at` | **persists** (proved), and carries no M082 authority |
| D-B05 | does M082 claim universal coverage? | **no** — D-F07 |
| D-B06 | is the old writer disabled? | **no** — that would alter frozen behaviour |
| D-B07 | raw SQL insert into M076 | possible; unreceipted |
| D-B08 | raw SQL insert into the receipt table | possible for a DB-privileged actor; stated |
| D-B09 | receipt for a non-existent event | FK refuses |
| D-B10 | receipt via the CLI without ingestion | attestation is its own usecase |
| D-B11 | does eligibility appear in the output? | yes, per entry |
| D-B12 | can a reader tell attested from unattested? | yes — distinct states |

## ATOMICITY — 12 attacks

| # | Attack | Result |
|---|---|---|
| D-A01 | event ok, receipt fails | unreceipted; honest |
| D-A02 | receipt ok, event fails | impossible — FK plus read-back |
| D-A03 | crash between phases | unreceipted |
| D-A04 | retry after partial success | idempotent by event |
| D-A05 | two receipts from a retry | `UNIQUE` prevents |
| D-A06 | retry creates a second authority | **no** — returns the existing receipt |
| D-A07 | partial write visible | no — each phase is its own transaction |
| D-A08 | event visible before receipt | yes, and that is the honest interim state |
| D-A09 | receipt visible before event | impossible |
| D-A10 | is the crash window documented? | yes |
| D-A11 | is it silently repaired? | **no** |
| D-A12 | is a fabricated instant ever used to repair it? | **never** |

## IMMUTABILITY — 14 attacks

| # | Attack | Result |
|---|---|---|
| D-I01 | `UPDATE` via repository | no code path |
| D-I02 | `DELETE` via repository | no code path |
| D-I03 | upsert via repository | no code path |
| D-I04 | direct SQL `UPDATE` | **BLOCKED by trigger — executed** |
| D-I05 | direct SQL `DELETE` | **BLOCKED by trigger — executed** |
| D-I06 | duplicate insert | `UNIQUE` refuses |
| D-I07 | is "immutable" overclaimed? | no — both layers named for what they are |
| D-I08 | API-append-only conflated with DB-enforced | explicitly distinguished |
| D-I09 | superuser drops the trigger | possible; **stated**, not hidden |
| D-I10 | migration edits receipts | none written |
| D-I11 | downgrade destroys receipts | downgrade drops the table; stated |
| D-I12 | `TRUNCATE` | not blocked by a row trigger; stated |
| D-I13 | receipt id reused | PK refuses |
| D-I14 | receipt rewritten by a later attester | no `UPDATE` path plus `UNIQUE` |

## SEMANTICS — 22 attacks

| # | Attack | Result |
|---|---|---|
| D-S01 | "received" read as "committed" | denied — upper-bound witness only |
| D-S02 | "system assigned" read as "true time" | denied |
| D-S03 | sequence read as wall clock | no sequence |
| D-S04 | sequence read as commit order | no sequence |
| D-S05 | gaps read as missing data | no sequence |
| D-S06 | receipt read as proof the trade happened | denied |
| D-S07 | receipt read as proof `recorded_at` is honest | denied |
| D-S08 | receipt read as proof of broker execution | denied |
| D-S09 | is exact commit time claimed? | **no** |
| D-S10 | is durable visibility to *every* reader claimed? | only that it had committed by the instant |
| D-S11 | is the converse claimed? | **no** — conservative direction stated |
| D-S12 | does absence mean the event is invalid? | **no** |
| D-S13 | does absence mean data loss? | **no** |
| D-S14 | is "attested" used for legacy rows? | never |
| D-S15 | is M079 relabelled? | never |
| D-S16 | `knowledge_as_of` vs `attested_as_of` | distinct — D-F11 |
| D-S17 | is a currency/monetary claim made? | none — M082 emits no value |
| D-S18 | is a performance claim made? | none |
| D-S19 | "verified" anywhere | forbidden token |
| D-S20 | "guaranteed" anywhere | forbidden token |
| D-S21 | "proof of receipt" as a legal claim | denied |
| D-S22 | is the host clock called authoritative? | it is called **system-assigned**, with limits stated |

## TEMPORAL LEAKAGE — 18 attacks

| # | Attack | Result |
|---|---|---|
| D-P01 | post-cutoff receipt influences a snapshot at `W` | excluded |
| D-P02 | commit-gap inclusion | **impossible** by construction — D-F01 corrected |
| D-P03 | backdated operator `recorded_at` influences M082 | **no** — M082 never reads `recorded_at` |
| D-P04 | future `recorded_at` influences M082 | no |
| D-P05 | event effective before receipt | ordinary and permitted |
| D-P06 | event effective after receipt | permitted; M082 makes no effective-time claim |
| D-P07 | `W` exactly at a receipt instant | inclusive, stated |
| D-P08 | `W` one microsecond before | excluded |
| D-P09 | `W` in the future | permitted; returns everything attested |
| D-P10 | naive `W` | refused at the request boundary |
| D-P11 | two reads at the same `W` differ | deterministic |
| D-P12 | appending an event after the read changes the snapshot at `W` | no |
| D-P13 | appending a *receipt* after the read changes it | no — its instant is later than `W` |
| D-P14 | does M082 read `recorded_at` at all? | **no** |
| D-P15 | does M082 read `event_timestamp`? | only to display, never to filter knowledge |
| D-P16 | can the caller inject the cutoff clock? | `W` is a caller parameter, and is *the question asked*, not an authority |
| D-P17 | can the caller inject the receipt instant? | **no** |
| D-P18 | double-database identical-prefix proof | required in implementation |

## DOWNSTREAM — 14 attacks

| # | Attack | Result |
|---|---|---|
| D-D01 | M079 accidentally trusts receipts | **no** — M079 untouched, byte-identical |
| D-D02 | M080 bypasses its firewall | no — untouched |
| D-D03 | M081 recomputed under new authority | no — untouched |
| D-D04 | calibration treats legacy rows as attested | no calibration exists in M082 |
| D-D05 | does M082 wrap M079's output? | no |
| D-D06 | does M082 change any M079 vocabulary? | no |
| D-D07 | is `events_known_by` modified? | no |
| D-D08 | does M080's report gain a field? | no |
| D-D09 | does M081's ratio change? | no |
| D-D10 | does any frozen test change? | no |
| D-D11 | does the M076 table change? | **no** |
| D-D12 | does the M076 repository change? | no |
| D-D13 | is a future milestone required to adopt this? | **yes**, stated explicitly |
| D-D14 | does M082 silently strengthen a past claim? | **no** |

## ARCHITECTURE AND SCHEMA — 33 attacks

| # | Attack | Result |
|---|---|---|
| D-X01 | FK target is not UNIQUE, so the FK cannot exist | **executed** — `uq_operator_position_event_governance_id` exists; the FK is valid |
| D-X02 | `ON DELETE CASCADE` destroys evidence | `RESTRICT` — D-F09 |
| D-X03 | two receipts for one event | `UNIQUE` on `event_governance_id` |
| D-X04 | receipt for a missing event | FK refuses |
| D-X05 | nullable authority column | every one is `NOT NULL` |
| D-X06 | naive timestamp column type | `TIMESTAMPTZ`, round-trip **executed** |
| D-X07 | primary key absent | `receipt_governance_id` PK |
| D-X08 | an existing table altered | **none** |
| D-X09 | an existing column altered | none |
| D-X10 | more than one migration | exactly one |
| D-X11 | migration is not reversible | `downgrade` drops the table and the trigger |
| D-X12 | downgrade silently keeps the trigger function | dropped explicitly |
| D-X13 | migration backfills rows | **none** |
| D-X14 | new third-party dependency | none |
| D-X15 | new repository for M076 | none — M076's is untouched |
| D-X16 | global mutable state | none |
| D-X17 | randomness | none |
| D-X18 | wall clock read inside the domain layer | none — the instant is supplied to the domain |
| D-X19 | `usecases` imports `shared.persistence` | forbidden by the architecture checker |
| D-X20 | `entrypoints` imports `decision_candidate` | forbidden by the checker |
| D-X21 | ordering by a non-persisted field | ordering is `(system_received_at, event_governance_id)` |
| D-X22 | ordering by insertion order | never |
| D-X23 | unrelated refactor | none |
| D-X24 | seal-debt repair | none |
| D-X25 | M083 work started | none |
| D-X26 | index missing for the query path | index on `system_received_at` |
| D-X27 | `attested_by` treated as an authority | it is a recorded string, stated as such |
| D-X28 | `attester_version` treated as an authority | same |
| D-X29 | secret stored | none |
| D-X30 | privilege escalation in the attestation path | none |
| D-X31 | frozen dataclass mutated | none |
| D-X32 | frozen repository contract changed | none |
| D-X33 | `PROJECT_CHECKPOINT.md` changed on this branch | none |

---

**207 attacks. 11 findings, all corrected in the design before implementation.**
No unresolved HIGH or CRITICAL finding remains.
