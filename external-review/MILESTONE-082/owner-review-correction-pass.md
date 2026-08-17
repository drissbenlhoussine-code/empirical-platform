# M082 - Owner Review Correction Pass

> **⚠ SUPERSEDED — this file describes an EARLIER candidate.**
> The authoritative latest correction is
> **`owner-correction-mission-findings-12-15.md`**. Where this file conflicts
> with it, that file wins. Nothing here is deleted: it is the record of what was
> believed at the time, including the parts that were wrong.


Everything here was **executed**. Nothing is argued.

Old head `25eab77`. This pass adds one correction commit on the same branch and
the same PR (#12).

---

## FINDING 1 - historical snapshot leaked future receipts and future events

### Reproduced first, against the PRE-CORRECTION head

Two real PostgreSQL databases, identical evidence authoritative at `W`.

**Attack A — a receipt created after `W`, in DB-A only:**

```
object identical : False
text   identical : False
json   identical : False
DB-A E2 status   : ATTESTED_AFTER_CUTOFF
DB-B E2 status   : NO_SYSTEM_RECEIPT_EVIDENCE
A after_cutoff_count: 1  B: 0
A unattested_count  : 0  B: 1
```

**Attack B — an entirely new event added after `W`, in DB-A only:**

```
object identical : False
text   identical : False
json   identical : False
entry count A/B  : 3 2
future id leaked : True
future pos leaked: True
future sym leaked: True
```

The banner's sentence *"Nothing attested after the cutoff influences any figure
below"* was therefore **false**, exactly as the Owner said.

### The architectural decision: OPTION 1, true receipt-cutoff snapshot

`build_attested_evidence_report` is now **receipts-first**. Only receipts whose
label is at or before the cutoff produce entries; `events` is consulted solely
to resolve the detail of an event one of those receipts already names, and that
row is append-only and immutable in M076, so its contents at read time equal its
contents at the cutoff.

A later receipt and an unreceipted event are **structurally unreachable** — they
cannot contribute an entry, a count, or an ordering position. This is not a
filter applied afterwards to a ledger-derived list; the ledger-derived list no
longer exists.

Removed, and **not replaced**:

| Removed | Why |
|---|---|
| `ATTESTED_AFTER_CUTOFF` | describes a receipt the snapshot must not see |
| `NO_SYSTEM_RECEIPT_EVIDENCE` | describes present-day inventory, i.e. possibly-future existence |
| `AttestedEvidenceStatus` (whole enum) | with both above gone, every entry is attested by construction |
| `attested_after_cutoff_count` | future-tail count |
| `unattested_count` | future-tail count |

No replacement count of hidden rows was added. **The snapshot may not know how
much evidence it excluded**, and its own text now says so.

A separate current-coverage product was **not** built: nothing in this milestone
needs it, and inventing one would be new scope. If it is ever wanted it must be
a distinct product with distinct semantics, exactly as the Owner said.

### Re-run against the CORRECTED head

```
=== ATTACK A - FUTURE RECEIPT NON-INTERFERENCE ===
object identical : True
text   identical : True
json   identical : True
has after_cutoff_count: False
has unattested_count  : False

=== ATTACK B - FUTURE EVENT EXISTENCE NON-INTERFERENCE ===
object identical : True
text   identical : True
json   identical : True
future id leaked : False
future pos leaked: False
future sym leaked: False
```

### A probe error of my own, recorded

The first re-run reported `object identical : False` even after the correction.
The code was right; **my probe was wrong**. The two databases had been attested
at genuinely different wall-clock moments, so the surviving entry's label
differed for a reason with nothing to do with the leak. Pinning the label so the
two databases hold *genuinely* identical evidence is what let the comparison
demand full identity.

This is the same weakness the original double-database test had: because it
could not compare instants, it compared only a **projection** of the entries —
and that is precisely why it passed while the leak was live. It now demands the
full object, the full text and the full JSON.

---

## FINDING 2 - the application wall clock does not prove the claimed bound

### The contradiction, as the Owner stated it

The module claimed `commit_time(event) < system_received_at` and therefore
`system_received_at <= W ⇒ committed by W`, while its own limitations admitted
the host clock "can be wrong, can be adjusted, and can move backward". **Both
could not be true.**

### The mandatory backward-clock attack, executed

The clock was made injectable so this could be run rather than reasoned about.
Against real PostgreSQL:

```
real commit (wall clock) : 2026-08-16T15:12:55.926191+00:00
receipt label            : 2026-08-16T15:02:55.926191+00:00
label precedes commit    : True
W (between them)         : 2026-08-16T15:07:55.926191+00:00
W < real commit          : True

snapshot at W includes the event : True
label-filter at W includes it    : True
```

The event was **not** committed at real wall-clock `W`, yet it is listed. The
implication is false and the "can never overstate" guarantee is gone.

The event's real commit chronology is unambiguous: the append returned before
the attesting call began, and the read-back inside `attest` could only succeed
against a committed row.

### The decision: OPTION A, weaken to causal receipt attestation

No stronger authority exists under this repository's and deployment's
constraints, and each candidate was rejected on evidence rather than taste:

| Candidate | Verdict |
|---|---|
| `pg_xact_commit_timestamp` | `track_commit_timestamp=off`; errors here; needs a deployment-wide restart; not retroactive. Not silently enabled. |
| `transaction_timestamp()` | precedes COMMIT; proved to leak. |
| a sequence | assignment order with rollback gaps, not commit order or wall clock. |
| assumed monotonic host clock | nothing enforces it; assuming it is the defect itself. |
| trusted timestamping service | none exists in this repository. |

So M082 keeps only what it can prove:

**A. CAUSAL AUTHORITY — claimed.** The attestation process read the event back
from committed persistence before creating the receipt. Clock-independent.

**B. WALL-CLOCK AUTHORITY — not claimed.** `system_received_at` is a
system-assigned label. Comparing it to an arbitrary historical `W` does not
prove durable availability at `W`.

### The consequence, stated rather than buried

**M082 does NOT replace M079's `recorded_at` firewall.** A smaller true
primitive is better than a stronger false one. Binding an evaluation to receipt
identities, or to an explicitly persisted receipt set captured at decision time,
is a future milestone. **It is not started.**

### Renames, because a name is a claim

| Old | New | Why |
|---|---|---|
| `attested_known_by` | `events_with_receipt_labelled_by` | "known by" asserted knowledge at a time |
| `attested_as_of` | `receipt_label_cutoff` | "as of" asserted a point-in-time stance |
| `--attested-as-of` | `--receipt-label-cutoff` | same, on the CLI |
| `AttestedEvidenceStatus` | *(removed)* | its two other members were the leak |

---

## R02 - the frozen M076 test change, re-verified as the Owner required

| Requirement | Result |
|---|---|
| no M076 behavioural assertion changed | **confirmed** — the diff's only `assert` line is docstring prose; no assertion added, removed or altered |
| no test weakened | **confirmed** — same up→down→up structure, same table-existence assertions |
| only migration-target addressing changed | **confirmed** — `downgrade(cfg, "-1")` → `downgrade(cfg, "31365632c016")` |
| `31365632c016` is genuinely M076's own predecessor | **confirmed** — it is the literal `down_revision` in M076's migration, whose `revision` is `b7e1c4a95d38` |
| still passes against M076 in isolation | **confirmed** — with M082's migration removed, `alembic heads` reports `b7e1c4a95d38 (head)` and the test passes |
| still passes with M082's migration present | **confirmed** — full M076 suite, 16 passed |
| no production M076 code changed | **confirmed** — the only M076 path in the branch diff is this test file |

---

## What the correction did NOT change

- the two-transaction model, and the commit-gap proof that forced it;
- the refusal to enable or fake commit timestamps;
- the refusal to treat a sequence as commit order;
- the append-only schema, the immutability trigger, the FK `RESTRICT`;
- the empty-table migration and the legacy-backfill prohibition;
- idempotency, concurrency and the R01 fix;
- M079/M080/M081, still byte-identical and still not consuming this authority.
