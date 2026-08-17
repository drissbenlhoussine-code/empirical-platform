# M082 - Owner Correction Mission, Findings 7-11

Everything here was **executed**. Nothing is argued.

Old head `699d7f9`. Same branch, same PR (#12).

---

## Repository truth gate

| | |
|---|---|
| base master | `28a10530dbc295fedacfa89c8aef246b35a0b86e` |
| local head == remote head | `699d7f95aa4941e091d28445ef8743cb4a2195af` |
| working tree | clean |
| `LATEST_FROZEN_MILESTONE` | `MILESTONE-081` |

---

## All five findings reproduced BEFORE any change

### Finding 7 - the receipt did not bind the event payload

```
before mutation : position=POS-ORIGINAL symbol=AAPL
                  receipt label=2026-08-17T10:53:06.159807+00:00
after  mutation : position=POS-MUTATED symbol=ZZZZ
                  receipt label=2026-08-17T10:53:06.159807+00:00
RECEIPT identity/label unchanged : True
REPORT CHANGED                   : True
M076 user-defined triggers       : 0
```

### Finding 8 - `pg_temp` shadowing, by a genuinely unprivileged role

```
role privileges: super=false createdb=false createrole=false

txn 1:  CREATE TEMP TABLE operator_position_event; INSERT decoy; COMMIT
txn 2:  INSERT the REAL event into public   (still in progress)
        INSERT the receipt                  -> SUCCEEDED

after commit:
  event xmin=162804  receipt xmin=162804  SAME TRANSACTION=true
```

### Finding 9 - malformed future tails reached the report

```
baseline report at 2027 cutoff   : 2 entries
9a blank attested_by, label 2099 : ValueError: attested_by must be non-empty
9b unreceipted NaN event 2099    : InvalidOperation
```

### Finding 10 - two non-atomic reads

```
read1 events=2  read2 receipts=2
build result : MissingAttestedEventError: receipt 'RC-RACE' attests event
               'EV-RACE', which was not supplied
```

### Fail-closed gap

The trigger refused only `in progress` and `aborted`, so any future or
unexpected non-NULL status value would have been **accepted**.

---

## Candidate ranking for finding 7

| | Candidate | Authority gained | Cost | Verdict |
|---|---|---|---|---|
| **A** | **receipt-only: attest event IDENTITY, drop payload enrichment** | none beyond what is already proved | artifact stops showing instrument/position | **SELECTED** |
| B | capture payload into the receipt row by trigger | a NEW claim, "payload as of receipt time" | new columns, more trigger surface, and it **strengthens** M082 - which this mission forbids | rejected |
| C | make M076 rows immutable once a receipt exists | payload stability | alters a **frozen** milestone's table behaviour and downgrade path | rejected |

A is the smallest honest design and the only one that adds no claim. It also
**collapses findings 9 and 10**: with no ledger read there is no malformed-row
exposure and no split-read race. B was tempting precisely because it looks
stronger, which is the reason to refuse it.

---

## After the correction - every attack re-executed

| Attack | Result |
|---|---|
| M076 payload changed after receipt | **artifact unchanged**; no payload field exists to move |
| `pg_temp` shadowing, non-superuser, committed decoy | **REFUSED** - "requires a PRIOR COMMITTED event ... in progress" |
| genuinely prior-committed control | **ACCEPTED** |
| same-transaction event + receipt after qualification | **REFUSED** |
| blank `attested_by` at the write boundary | **REFUSED** by `ck_operator_event_receipt_attested_by_present` |
| well-formed 2099 receipt vs a 2027 cutoff | **never fetched**; report byte-identical |
| unreceipted 2099 `NaN` event | **never fetched**; report byte-identical |
| event + receipt committing at the former read boundary | valid bounded result, **no raise** |
| unexpected writer status | **REFUSED** - explicit allowlist |
| receipt identity for future M083 watermarking | **preserved** |

---

## What changed, and what was deliberately not changed

**Changed:** the artifact is receipt-only; the handler reads one store through
one cutoff-narrowed query; every relation and function in the trigger and the
repository is schema-qualified with a pinned `search_path`; four `CHECK`
constraints enforce receipt identity and metadata at the write boundary; the
status test is an explicit allowlist; the console script is
`empirical-platform-receipt-label-cutoff-view`.

**Not changed:** M079/M080/M081, M076 production code, `PROJECT_CHECKPOINT.md`.
No commit-time, wall-clock, historical-knowledge or universal-attestation
authority was added anywhere - the correction only ever removes claims.

---

## The claim M082 now makes

> A persisted M082 receipt binds a stable receipt identity to an exact M076
> event governance identity whose real public-table row was visible as coming
> from a prior committed transaction at receipt insertion. The receipt label is
> not commit time, trusted wall-clock truth, historical knowledge time, or proof
> of availability at an arbitrary cutoff.
>
> **M082 does not attest the current or historical payload of that M076 event.**

---

## Probe errors of my own, recorded

1. My first finding-8 probe created the decoy row **inside** the attack
   transaction, so it was in progress too and the trigger correctly refused. The
   attack only works when the decoy is committed in an **earlier** transaction of
   the same session. Recorded because a bypass that "does not reproduce" is the
   easiest kind of finding to dismiss wrongly.
2. My finding-9 cleanup used `DELETE` on receipts, which the immutability
   trigger refuses - that guarantee working as designed. Switched to `TRUNCATE`.
