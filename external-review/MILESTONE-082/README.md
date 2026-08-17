# MILESTONE-082 - Operator Event Receipt Attestation - External Review Package

**Status: CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

> **⚠ Hardened after a second Owner review.** Three further findings are resolved:
> a stale upper-bound claim that survived in the **migration**; a persisted row
> that did **not** prove the causal claim against a direct same-transaction SQL
> INSERT; and a label cutoff that is **not** a stable snapshot. Read
> `owner-review-hardening-pass.md` first.

Base `master` `28a1053`.

> **⚠ This package was corrected after Owner review. Two claims are RETRACTED.**
> Read `owner-review-correction-pass.md` before anything else — it reproduces
> both defects by execution and records exactly what the milestone now claims.

## What M082 claims, after the correction

**A causal fact, and nothing more:**

    the attestation process READ THIS EVENT BACK from committed persistence,
    and only THEN created this receipt.

That holds by program order plus PostgreSQL transaction visibility, and **it
does not depend on any clock**. `system_received_at` is a **system-assigned
label** recorded beside that fact.

## What M082 no longer claims

**RETRACTED — the wall-clock upper bound.** The first version claimed
`commit_time(event) < system_received_at`, therefore `system_received_at <= W`
implies durable commit by `W`, and that M082 "can never overstate". Executed
counter-example, real PostgreSQL:

```
real commit (wall clock) : 15:12:55.926191
receipt label            : 15:02:55.926191   <- host clock moved BACK ten minutes
cutoff (between them)    : 15:07:55.926191

snapshot at the cutoff includes the event : True
```

The event was **not** committed at that real instant, yet it is listed. The
module's own limitations had already admitted the clock "can move backward", so
the two statements could never both be true — and nothing had proved the bound.

**The honest consequence, stated rather than buried: M082 does NOT replace
M079's `recorded_at` firewall.** A smaller true primitive beats a stronger false
one. Binding an evaluation to receipt identities, or to an explicitly persisted
receipt set captured at decision time, is a future milestone. It is not started.

**RETRACTED — "point-in-time historical snapshot".** The artifact was built from
the CURRENT ledger, so rows created after the cutoff changed the historical
output. Two databases with identical evidence at `W`:

```
ATTACK A - a receipt created after W, in DB-A only
  DB-A : ATTESTED_AFTER_CUTOFF     DB-B : NO_SYSTEM_RECEIPT_EVIDENCE
  after_cutoff_count A=1 B=0       unattested_count A=0 B=1

ATTACK B - a new event added after W, in DB-A only
  entry count A=3 B=2
  future event id / position / symbol leaked into the historical text : True / True / True
```

The banner's own sentence *"Nothing attested after the cutoff influences any
figure below"* was false.

## What replaced it: a true receipt-cutoff snapshot

The artifact is now built **from receipts** labelled at or before the cutoff.
A later receipt and an unreceipted event are **structurally unreachable** — no
entry, no count, no ordering position. `ATTESTED_AFTER_CUTOFF`,
`NO_SYSTEM_RECEIPT_EVIDENCE`, the whole status enum,
`attested_after_cutoff_count` and `unattested_count` are gone and **not
replaced**: the snapshot deliberately **cannot say how much it excluded**, and
its own text says so.

Re-run after the correction: **full object, full text and full JSON identical**
on both sides of both attacks.

## Names are claims, so three of them changed

| Old | New |
|---|---|
| `attested_known_by` | `events_with_receipt_labelled_by` |
| `attested_as_of` | `receipt_label_cutoff` |
| `--attested-as-of` | `--receipt-label-cutoff` |

## What survived the correction untouched

The two-transaction model and the executed commit-gap proof that forced it; the
refusal to enable or fake commit timestamps; the refusal to treat a sequence as
commit order; the empty-table migration and the legacy-backfill prohibition; the
append-only schema, immutability trigger and FK `RESTRICT`; idempotency,
concurrency and the R01 fix; and M079/M080/M081, byte-identical and still not
consuming this authority.

## Defects, all found by execution

| # | Defect |
|---|---|
| Owner 1 | historical snapshot leaked future receipts and future events |
| Owner 2 | the wall-clock upper bound was unproved and false under a backward clock |
| Owner 3 | a stale upper-bound claim survived in the migration; the first sweep never searched `migrations/` |
| Owner 4 | a persisted row did not prove the causal claim — a same-transaction direct SQL INSERT forged one |
| Owner 5 | the label cutoff is not a stable snapshot; a later backdated label changes the same cutoff |
| Owner 6 | the prior-commit trigger caught `EXCEPTION WHEN OTHERS` and **failed open** — any checker error became permission to insert |
| R01 | the concurrent-loser path crashed with a nested unit of work instead of yielding |
| R02 | this branch's migration broke frozen M076's reversibility test (test-only; re-verified in full) |

## Read in this order

| File | What it is |
|---|---|
| `owner-review-fail-closed-pass.md` | **start here** — finding 6, the fail-open enforcement, reproduced and corrected |
| `owner-review-hardening-pass.md` | findings 3, 4 and 5 |
| `owner-review-correction-pass.md` | the previous pass — findings 1 and 2 |
| `reality-gate.md` | which claim level this reaches, and the two levels it no longer claims |
| `transaction-timing-evidence.md` | the executed commit-gap leak; why commit time is unavailable |
| `scope-and-design-snapshot.md` | the design, the eight candidates, the rejected alternatives |
| `hostile-design-review.md` | 207 attacks, 11 findings, all corrected before any code |
| `hostile-implementation-review.md` | 263 executed attacks; R01 and R02 |
| `concurrency-evidence.md` | the four-attester race, before and after R01 |
| `focused-re-review.md` | the R01 correction re-attacked in its changed area |
| `fresh-second-verification-pass.md` | separate database, different events, reversed attestation order |
| `validation-results.md` | every gate, and the baseline-vs-candidate failing-ID diff |
| `known-limitations.md` | 19 items, with the retracted ones quoted |
| `owner-review-checklist.md` | the judgment calls, stated so they can be overruled |
| `changed-files.txt` | every file this branch touches |

Files predating the correction carry a visible retraction notice at the top.
Nothing was deleted.

## Nothing here is erased

My own probe errors are recorded beside the attacks they broke. Three matter:

- a `recorded_at` substring search that flagged the artifact's own limitation
  text denying it;
- a forbidden-token search for `"upper bound"` that failed on the artifact's own
  **retraction** of that claim — the identical mistake, made twice;
- a re-run of Attack A that reported a difference after the fix, because *my
  probe* let the two databases take different wall-clock labels. That same
  weakness is why the original double-database test compared only a projection
  of the entries — **and that is exactly why it passed while the leak was live.**

A test that fails for the wrong reason misleads as much as one that passes for
the wrong reason. The second kind is what the Owner had to catch.
