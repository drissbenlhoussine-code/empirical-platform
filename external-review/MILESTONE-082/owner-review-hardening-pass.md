# M082 - Owner Review Final Authority Hardening Pass

Everything here was **executed**. Nothing is argued.

Old head `5be05bd`. One correction commit, same branch, same PR (#12).

---

## FINDING 3 - a stale upper-bound claim survived in the migration

The previous pass corrected the module, the banner, the limitations, the tests
and the evidence package — and **missed the migration**, which still said:

> `system_received_at` ... is an **UPPER BOUND WITNESS** on the event's commit
> time -- never the commit time itself.

That is the claim retracted by finding 2, sitting in the one file that defines
the persisted schema. Corrected in place, with the retraction stated beside it.

### Why the first sweep missed it

The reconciliation sweep searched `src`, `tests`, the design document and
`external-review`. **`migrations/` was not in the list.** The sweep tool is now
a script over the whole tree with a `.venv` exclusion, and it classifies each hit
as ACTIVE or RETRACTION-MARKED rather than merely counting.

Its first run had a defect of its own: it scanned `.venv` and reported 91
"active" hits, 83 of which were `mypy`, `sqlalchemy` and `psycopg` talking about
type-variable and range upper bounds. Recorded rather than quietly fixed.

### Final state of the sweep

| | |
|---|---|
| RETRACTION-MARKED occurrences | **87** |
| ACTIVE occurrences | **8**, every one a denial or a heading naming the defect |

Newly marked in this pass: the two design documents' `commit_time(event) <
system_received_at` block and their "upper bound witness" sentence, the
transaction-timing evidence's inequality and its "can never overstate"
paragraph, and the implementation review's "one-directional guarantee" batch
label.

---

## FINDING 4 - a persisted receipt row did not prove the causal claim

### Reproduced first, against the pre-trigger head

```
=== same-transaction event + receipt, raw SQL ===
  same-transaction INSERT accepted by the database : True
  M082 report lists it as authoritative           : True
  label / attested_by : 2020-01-01T00:00:00+00:00 / forged-attester
```

The foreign key was satisfied because the event was visible to the very
transaction that wrote it. A direct SQL caller could therefore manufacture a
receipt for an event that had **never independently committed**, and the report
could not tell it apart from one `attest()` produced.

### The mechanism was chosen by measurement, not by reading documentation

The obvious check — `event.xmin = pg_current_xact_id()::xid` — **is wrong**, and
PostgreSQL 16.13 says so directly:

```
CASE 1  same transaction, no savepoint : xmin=140564 cur=140564 equal=true
CASE 2  prior committed transaction    : xmin=140564 cur=140565 equal=false
CASE 3  same transaction, SAVEPOINT    : xmin=140567 cur=140566 equal=FALSE  <- MISSES THE ATTACK
```

A subtransaction gets its **own, higher** xid, so the naive comparison lets the
attack straight through. An ordering comparison (`xmin < current`) fails in the
other direction: a **concurrent transaction with a HIGHER xid** can commit before
we read, and a legitimate receipt would be falsely refused.

The test that is actually correct is **"is the writing transaction still in
progress?"** — because if a row is visible to us and its writer is still in
progress, that writer can only be our own transaction or a subtransaction of it;
MVCC never shows another transaction's uncommitted rows.

Measured across every case the Owner named:

| Case | `pg_xact_status` | Verdict |
|---|---|---|
| same transaction, no savepoint | `in progress` | **refuse** |
| prior committed transaction | `committed` | accept |
| same transaction, one SAVEPOINT | `in progress` | **refuse** |
| nested savepoints, two levels | `in progress` | **refuse** |
| rollback to savepoint, then re-insert | `in progress` | **refuse** |
| concurrent committed writer, HIGHER xid (A=140579, row xmin=140580) | `committed` | accept — no false refusal |
| frozen row after `VACUUM FREEZE` | `committed` | accept |
| aborted transaction | row not visible at all | n/a |

`xid` is 32-bit; `pg_xact_status` takes `xid8`. The trigger promotes `xmin` into
the current xid8 epoch. That is exact for the only case being tested, because a
transaction still in progress is necessarily in the current epoch. An unknown
status (an xid too old for CLOG retention) is treated as **not** in progress and
accepted: a live transaction always has its CLOG present, so "too old to know"
can only mean "committed long ago".

### DECISION: OPTION A - database-enforced prior-transaction existence

A `BEFORE INSERT` trigger refuses a receipt whose referenced event was written by
the current transaction. After the fix:

```
same-transaction attack   : REFUSED - "requires a PRIOR COMMITTED event"
SAVEPOINT variant         : REFUSED
nested savepoints         : REFUSED
rollback-to-savepoint     : REFUSED
concurrent higher-xid     : ACCEPTED (no false refusal)
repository attest() path  : ACCEPTED
```

**The causal claim now holds for every persisted row**, not merely for rows this
repository produced.

### DATABASE_ENFORCEMENT_LEVEL, stated exactly

| Property | Enforced by the database? |
|---|---|
| the referenced event exists | **yes** — foreign key |
| the referenced event was committed by a PRIOR transaction | **yes** — `BEFORE INSERT` trigger |
| exactly one receipt per event | **yes** — UNIQUE |
| receipt evidence cannot vanish with its event | **yes** — `ON DELETE RESTRICT` |
| row-level UPDATE/DELETE immutability | **yes** — `BEFORE UPDATE OR DELETE` trigger |
| `system_received_at` is a true instant | **NO** |
| `attested_by` identifies the real writer | **NO** |
| `attester_version` is genuine | **NO** |
| the row was produced by `attest()` | **NO** |
| TRUNCATE / DROP TRIGGER / DROP TABLE / superuser | **NO** |

### The residual limitation, pinned by a test rather than by prose

```
=== direct INSERT for an ALREADY COMMITTED event ===
  accepted                       : True
  forged label / by              : 1999 / not-the-attester
  forged attester_version stored : M999-FORGED
```

Option A does **not** close this, and the artifact does not pretend it does.
`test_a_direct_insert_for_an_already_committed_event_is_still_accepted` asserts
the forgery succeeds **and** that the limitation text admits it. If that test
ever starts failing, the limitations have become too weak, not too strong.

No cryptography, no signatures, no permission model and no stored-procedure gate
were claimed, because none was implemented.

---

## FINDING 5 - the label cutoff is not a stable historical snapshot

### Reproduced, through the REAL attestation path

```
entries at cutoff (before)     : ['EV-COMMITTED']
  ... a LATER attestation runs, with a backward clock ...
entries at cutoff (after)      : ['EV-COMMITTED', 'EV-LATE']
SAME cutoff, object identical  : False
SAME cutoff, text identical    : False
SAME cutoff, json identical    : False
```

Control, to isolate the cause:

```
a later FORWARD-labelled receipt : object identical : True
```

Only **backdated** labels destabilise the cutoff. This does not contradict the
causal claim; it does mean the artifact was mis-described.

### What the previous pass claimed, and what is now claimed

`HISTORICAL_OUTPUT_POST_W_INDEPENDENT=YES` was **too broad** and is
**SUPERSEDED**. The precise statement:

> The view is independent of receipts whose persisted **label** is greater than
> the cutoff, and of events lacking a qualifying receipt.
>
> It is **NOT** stable against receipts created later with a **backdated**
> label.

### Terminology change

"Snapshot" implies knowledge at a historical wall-clock instant, which this
cannot deliver. The artifact is now a **RECEIPT-LABEL-CUTOFF VIEW** — in the
heading, the banner, the limitations, the dataclass docstrings and the design
documents. The banner states in its own words that it is a predicate over the
labels in the **current** persisted receipt set, that it is not a reconstruction
of which receipts existed at that instant, and that **repeated evaluation at the
same cutoff can change**.

No hidden creation timestamp was added. That would have reopened finding 4 one
layer down, with a second unauthenticated column instead of one.

---

## Immutability wording

Corrected in the migration and the repository docstring. Both previously said
"DATABASE-ENFORCED immutability" without qualification. What is enforced is
**row-level UPDATE/DELETE under the installed trigger** — and
`test_immutability_is_row_level_update_delete_only` proves the boundary by
executing a `TRUNCATE` that **succeeds**.

---

## M076

Unchanged from the previous pass. No new migration revision was created — the
M082 revision is not frozen and was amended in place — so the R02 test's
downgrade target `31365632c016` needs no mechanical adjustment. No M076
production change.
