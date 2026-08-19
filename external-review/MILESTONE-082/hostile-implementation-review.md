> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This file records earlier reasoning, earlier conclusions and reproduced
> defects. Some of what it says was true only of an earlier candidate, and
> some of it is explicitly withdrawn. It is preserved so the history stays
> readable; it is not imported, rendered or validated as current truth.
>
> The single active statement of M082 authority is
> [`current-authority.md`](current-authority.md).

# M082 - Hostile Implementation Review

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


**263 attacks executed against the running code, the usecase layer, the CLI, the
schema and real PostgreSQL.** All 263 pass at the current head.

**2 defects found, both by execution.** **Two probe errors of my own** are
recorded, plus one compatibility break my migration caused in a frozen
milestone's test.

| Batch | Attacks |
|---|---|
| authority/semantics, one-directional guarantee *(RETRACTED claim - see finding 2)*, `recorded_at` isolation | 32 |
| schema and database introspection | 17 |
| immutability | 8 |
| idempotency and retry | 21 |
| concurrency | 3 |
| clock | 9 |
| downstream isolation | 5 |
| rendering, JSON, CLI | 20 |
| dense cutoff-boundary sweep | 31 |
| dense `recorded_at` lie sweep | 21 |
| status partition, ordering | 13 |
| rollback and failure | 6 |
| bypass | 5 |
| input-order independence | 20 |
| attester identity | 6 |
| multi-event integrity | 10 |
| microsecond boundary | 9 |
| determinism | 10 |
| limitation-text integrity | 12 |
| **total** | **263** |

---

## R01 (HIGH) - the concurrent-loser path crashed instead of yielding

**Found by executing four concurrent attesters**, not by reading the code.

```
FoundationError('Nested persistence units of work are not supported')  x3
```

**Root cause.** On a `UNIQUE` conflict the repository called `get_for_event` to
return the winner's receipt — but it did so **while still inside its own unit of
work**, and the persistence layer forbids nesting. So three of four callers
crashed, in precisely the branch that exists to make concurrency graceful.

**Why the design review missed it.** The design said "the loser reports the
winner's receipt", which is correct as a *policy*. The defect was in *where* the
read happened, which only running four threads at once could reveal.

**Fix.** The conflict is now only **detected** inside the transaction; the
winner is read after it has closed.

**Regression coverage.** Six concurrent attesters, asserting no errors, exactly
one row, and one shared instant — in the integration suite and in the second
pass.

## R02 (MEDIUM) - my migration broke a frozen milestone's reversibility test

`test_m076_migration_is_reversible` began failing: it did `upgrade head` then
`downgrade -1` and asserted M076's table was gone. That held only while M076's
migration **was** head. Any later migration breaks it — mine was simply the
first.

**This is the one place M082 touches a frozen milestone's file**, and it is
flagged for the Owner as a judgment call. The change is minimal and
intent-preserving: the downgrade target is now M076's **own predecessor
revision, stated absolutely**, instead of a relative step. The test still proves
exactly what it always proved — that M076's `downgrade()` genuinely removes
M076's table — and it no longer depends on which milestone happens to be newest.

No M076 semantics, source, schema or behaviour changed.

## Two probe errors of my own, recorded

1. **Harness forward references.** Five checks failed with `NameError` because I
   defined helpers after first use — the same mistake I made in M081's harness.
   Wrong harness, not wrong code.
2. **`recorded_at` substring search.** I asserted the module "never reads
   `recorded_at`" by searching for the string, and it failed — because the
   **limitation text names `recorded_at` in order to deny it**. The real claim
   is that it is never read as an *attribute*, which is what the corrected probe
   asserts (`.recorded_at` appears nowhere).

Also recorded: a variable-shadowing bug in the first mandatory-attack script,
where the cutoff `K` shadowed the `OperatorPositionEventKind` alias `K`.

## One finding the trigger produced by itself

The immutability trigger **blocked my own test cleanup** on its first run:

```
psycopg.errors.RaiseException: operator_event_receipt is append-only:
DELETE is not permitted
```

That is live confirmation that database-enforced immutability works, arriving
from a direction I did not plan. Fixtures now use `TRUNCATE`, which a row-level
trigger does not intercept — exactly as design note D-I12 recorded in advance.

---

## The mandatory attacks

| Mandate | Result |
|---|---|
| §24 commit-gap | **no leak** - receipt instant falls after commit and after `K`; the event is excluded at `K` |
| §25 two-connection ordering | receipt order is **attestation order**; assignment order proved unequal to commit order, so no sequence is emitted |
| §26 legacy backfill prohibition | a deliberately false `recorded_at` ten years early never becomes a receipt instant; status is `NO_SYSTEM_RECEIPT_EVIDENCE` |
| §27 double-database | two databases with identical attested prefixes agree exactly on which events are attested at the cutoff, while their tails differ radically |

## Selected attack results

**`recorded_at` cannot influence M082 (21 dense lies, -5000d to +5000d):** every
one leaves attestation unchanged. `.recorded_at` appears nowhere in the module or
the repository.

**Boundary exactness (31 offsets, plus 9 at microsecond resolution):** inclusion
flips exactly at the receipt instant, inclusive.

**Input-order independence (20 shuffles):** the report is byte-identical
regardless of the order events and receipts arrive in.

**Immutability:** direct `UPDATE` blocked, direct `DELETE` blocked, duplicate
insert blocked, receipt-for-missing-event blocked, and deleting an attested
event blocked by `RESTRICT` — so receipt evidence cannot silently vanish.

**Idempotency:** 15 retries return the identical receipt; exactly one row
survives.

**Downstream isolation:** M079, M080 and M081 contain **no** reference to
`operator_event_receipt`, `attested_known_by` or `system_received_at`, and all
four frozen modules are byte-identical to the baseline.

**Schema:** five columns, all `NOT NULL`, **no column default** — so no
database-generated instant exists to be mistaken for a commit time. `UNIQUE` on
the event id, FK with `RESTRICT`, one index, zero altered tables, zero rows
written by the migration, and a `downgrade` that removes the table, the index,
the trigger and the function.
