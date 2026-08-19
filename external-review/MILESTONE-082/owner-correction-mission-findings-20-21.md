> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This file records earlier reasoning, earlier conclusions and reproduced
> defects. Some of what it says was true only of an earlier candidate, and
> some of it is explicitly withdrawn. It is preserved so the history stays
> readable; it is not imported, rendered or validated as current truth.
>
> The single active statement of M082 authority is
> [`current-authority.md`](current-authority.md).

# M082 — Owner Final Micro-Correction Mission — Findings 20–21

> **⚠ SUPERSEDED — this file describes an EARLIER candidate.**
> The authoritative latest correction is
> **`owner-correction-mission-findings-22-23.md`**. Where this file conflicts
> with it, that file wins. Two figures in it are corrected there: the
> secret-scan target count (1135 → **1136** at `9b487d1`) and the claim that
> there are no suppressions anywhere, which is **retracted as false**.

**Status: `CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW`. Not merged, not frozen.**

*(Superseded banner, kept visible:)* This is the **authoritative latest
correction** in this package. Every other file
describes an earlier candidate and carries its own superseded notice. Nothing is
deleted anywhere: incorrect earlier conclusions are kept visible as RETRACTED or
SUPERSEDED.

Starting head `2ce4135`. Base `master` `28a1053`, `M081 APPROVED_AND_FROZEN`,
`LATEST_FROZEN_MILESTONE=MILESTONE-081` unchanged.

---

## Finding 20 — generic persisted-row provenance claims survived

### Reproduced against the rejected head `2ce4135`, before any change

The previous correction reported that generic provenance had been fully swept.
It had not. The sweep test that was supposed to enforce it,
`test_no_active_surface_claims_sanctioned_provenance_without_qualification`,
reads **only rendered output** — the text renderer, the JSON payload and the
report's `limitations` tuple. It never looked at a source file, so it passed
while the domain module still said, in the docstring of the **generic** type
that every persisted row is mapped into:

```
class OperatorEventReceipt:
    """One system receipt attesting an M076 event was read back as committed.

    `system_received_at` is a SYSTEM-ASSIGNED LABEL taken from the application
    host clock after the read-back. ...
```

Executed grep over `2ce4135`, restricted to the domain module, returned four
unqualified generic origin claims:

```
operator_event_receipt.py:21   `system_received_at` is a SYSTEM-ASSIGNED LABEL recorded alongside that causal
operator_event_receipt.py:172  `system_received_at` is a SYSTEM-ASSIGNED LABEL taken from the application
operator_event_receipt.py:274  No entry can be derived from a receipt whose system-assigned label is after
operator_event_receipt.py:312  filters a system-assigned label; it does not establish what was knowable.
```

and four more across the port, the PostgreSQL adapter, the use case and the
migration. A direct-SQL receipt is mapped into exactly these types, so none of
them may assert an origin.

### The distinction now applied everywhere

```
GENERIC PERSISTED VALUE:
    UNAUTHENTICATED PROVENANCE.
ON THE SANCTIONED attest() PATH ONLY:
    system_received_at is obtained from the application host clock after
    read-back; attester_version is an application constant; attested_by is
    caller-supplied and passed through unchanged.
```

Corrected surfaces — domain module (module docstring, `OperatorEventReceipt`,
`AttestedEventEntry`, `events_with_receipt_labelled_by`), the repository port,
the PostgreSQL adapter, `GetAttestedEvidenceReportQuery`, the migration comment,
design §8/§11/§12/§13/§22/§30, this package's `README.md` and
`known-limitations.md`. The CLI entry point and both renderers were already
correct and were not touched.

`MILESTONE_082_..._SCOPE_AND_DESIGN.md` **§30, "What M082 Proves"**, additionally
still carried the fully retracted wall-clock implication —
`system_received_at <= W` implies durable commit by `W` — with no inline marker.
The document-level RETRACTION 2 banner already withdrew it, but it sat unmarked
in the one section a reader consults for what the milestone proves. It is now
quoted verbatim under an inline retraction and replaced by the causal statement.

### The sweep now reaches the source

Two new tests read the **M082 source files themselves**:

* `test_no_m082_source_file_asserts_generic_metadata_origin` — no active line may
  assert `system-assigned` for a persisted value. A `RETRACTED`/`SUPERSEDED`
  marker governs its **own paragraph** (a blank line, or a bare `#` in a comment
  block, ends it), so withdrawn text stays visible without being exempted
  wholesale.
* `test_every_sanctioned_path_origin_claim_is_explicitly_qualified` — a file that
  names the application host clock or an application constant must also state the
  `ON THE SANCTIONED attest() PATH` qualification **and** the
  `UNAUTHENTICATED PROVENANCE` of a generic persisted value.

**Executed negative control.** The pre-correction domain module was restored from
`2ce4135` into the working tree and the sweep re-run:

```
AssertionError: generic origin claim survives:
  .../operator_event_receipt.py:21:  `system_received_at` is a SYSTEM-ASSIGNED LABEL recorded alongside that causal
  .../operator_event_receipt.py:172: `system_received_at` is a SYSTEM-ASSIGNED LABEL taken from the application
  .../operator_event_receipt.py:274: No entry can be derived from a receipt whose system-assigned label is after
  .../operator_event_receipt.py:312: filters a system-assigned label; it does not establish what was knowable.
1 failed
```

The corrected module was restored and the sweep passes. The new test catches
exactly the four defects the rendered-output sweep could not see.

---

## Finding 21 — the four-constraint control claim was overstated

The **exact installed-set equality** test is valid and does protect all four
CHECK constraints; it is unchanged. The **controls** test did not.

### Reproduced by execution against real PostgreSQL 16.13

The mutated trim set (frozen 29 + the letter `v`) was built and **resolved by
PostgreSQL itself**, then asked what the values the old test actually wrote into
each column would do:

```
FROZEN set resolved by PostgreSQL: 29 characters
MUTATED set (frozen + letter v)  : 30 characters

receipt_governance_id  value='v-RC0'          PASSES mutated CHECK = True
receipt_governance_id  value='valve-RC1'      PASSES mutated CHECK = True
receipt_governance_id  value=' padded -RC2'   PASSES mutated CHECK = True
receipt_governance_id  value='\tvalve\t-RC3'  PASSES mutated CHECK = True
receipt_governance_id  value='vvv-RC4'        PASSES mutated CHECK = True
event_governance_id    value='EV-CTRL0'       PASSES mutated CHECK = True   (never received a control at all)
attested_by            value='v'              PASSES mutated CHECK = False
attester_version       value='vvv'            PASSES mutated CHECK = False
```

The receipt id was built as `f"{control}-RC{index}"`, so the suffix kept it
non-empty after trimming; the event id never carried a control. **Every observed
negative-control failure could only have come from `attested_by` /
`attester_version`.** The claim "controls are driven through all four installed
CHECK constraints" was therefore **not proved**, exactly as the Owner stated.

### The strengthened test

`test_each_installed_check_accepts_every_control_in_its_own_column` is
parametrised over the four constrained columns. In each case **exactly one**
column receives the exact control value — `v`, `valve`, `" padded "`,
`"\tvalve\t"`, `vvv` — while the other three carry ordinary valid values. The
M076 event is always committed in **its own prior transaction**; writing both in
one transaction is refused by the prior-commit trigger, which is that guarantee
working.

**Upstream restriction check.** M076's own table (`b7e1c4a95d38`) places **no**
blank CHECK on `governance_id` — only `UNIQUE` and `varchar(64)`. All five
controls can therefore legally exist as M076 event governance identities, and
**no control had to be narrowed away**. Nothing is simulated.

### Executed negative mutation control

`r"\x76"` (the letter `v`) was appended to the migration's frozen trim set and
the migration re-applied.

1. **Exact-set equality fails:**

```
AssertionError: ck_operator_event_receipt_attested_by_present: installed trim
set differs from the frozen set; extra=['v'] missing=[]
```

2. **Each of the four independent column controls detects it** — all four
   parametrised cases fail, each refused by **its own named CHECK**:

```
FAILED ...test_each_installed_check_accepts_every_control_in_its_own_column[receipt_governance_id]
FAILED ...test_each_installed_check_accepts_every_control_in_its_own_column[event_governance_id]
FAILED ...test_each_installed_check_accepts_every_control_in_its_own_column[attested_by]
FAILED ...test_each_installed_check_accepts_every_control_in_its_own_column[attester_version]

CheckViolation: violates check constraint "ck_operator_event_receipt_receipt_id_present"
  DETAIL:  Failing row contains (v, EV-IND00, 2026-04-01 00:00:00+00, ordinary-attester, M082.1).
CheckViolation: violates check constraint "ck_operator_event_receipt_event_id_present"
  DETAIL:  Failing row contains (RC-IND10, v, 2026-04-01 00:00:00+00, ordinary-attester, M082.1).
```

The two columns that previously detected **nothing** now each fail on their own
constraint. The migration was restored immediately; `grep -c x76` returns `0`,
and the only remaining migration delta is the finding-20 comment correction.

**Honest limit, stated rather than implied.** Detection of an added `v` comes
from the all-`v` controls (`v`, `vvv`), which trim to empty. `valve`,
`" padded "` and `"\tvalve\t"` do not trim to empty under that mutation and
cannot detect it on any column — they are **acceptance** controls, proving a real
identifier is not mangled. Both roles are exercised on all four columns.

---

## What M082 claims — unchanged and still narrow

> A persisted receipt binds a stable receipt identity to an exact M076 event
> governance identity whose real public row was observed as originating from a
> prior committed transaction at receipt insertion.
> It does not attest event payload, wall-clock chronology, commit time,
> historical availability, or the provenance of persisted metadata labels.

## Preservation

Provably unchanged: the 29-character blank set; the four installed CHECK
constraints; the prior-committed-row causal trigger; the receipt-only
architecture; the cutoff SQL and future-tail behaviour; receipt idempotency.

**Executed proof** — every changed production/migration file was parsed and
compared against `2ce4135` as a **docstring-stripped AST**:

```
IDENTICAL (docstring-stripped AST): decision_candidate/operator_event_receipt.py
IDENTICAL (docstring-stripped AST): decision_candidate/operator_event_receipt_repository.py
IDENTICAL (docstring-stripped AST): shared/persistence/.../operator_event_receipt_repository.py
IDENTICAL (docstring-stripped AST): usecases/attest_operator_event_receipt.py
IDENTICAL (docstring-stripped AST): migrations/versions/d9a2f5c81b73_...py

NON-STRING/NON-COMMENT PRODUCTION BEHAVIOUR DIFF: EMPTY
```

M076 production, M079/M080/M081 production (9 files, byte-identical to `master`)
and `PROJECT_CHECKPOINT.md` are untouched. `M083` remains `NOT_STARTED`.

## Validation

| Gate | Result |
|---|---|
| M082 unit suite | **40 collected, 40 passed** |
| M082 PostgreSQL lifecycle | **187 collected, 187 passed** (was 182) |
| Fresh second pass (schema dropped, re-upgraded) | **187 passed** |
| `test_m082_..._second_pass.py` | **4 passed** |
| M076–M082 chain, 13 integration files | **311 passed** |
| M076–M082 chain, unit surface | **357 passed** |
| Migration up → down → up | clean; all four CHECKs resolve to **exactly 29** characters |
| Source provenance sweep | 2 new tests pass; **negative control fails as required** |
| Per-column control | 4 parametrised cases pass; **negative control fails on all four** |
| `git diff --check` | clean |
| compile / ruff format / ruff check / mypy | clean (`mypy`: 311 source files) |
| Architecture checker | exit 0; negative fixture exit 1 as required |
| Secret scan | 1135 targets, **0 findings** |
| Suppressions introduced | **none** |

### Regression comparison — baseline re-derived in the same working tree

| Run | Result | Failing ids |
|---|---|---|
| Baseline `2ce4135`, PG-ON | 24 failed, 2930 passed, 44 errors | 68 |
| Corrected, PG-ON | 24 failed, **2935** passed, 44 errors | 68 |
| Baseline `2ce4135`, PG-OFF | 8 failed, 2327 passed, 12 errors | 20 |
| Corrected, PG-OFF | 8 failed, **2329** passed, 12 errors | 20 |

**Both sorted failing-ID diffs are EMPTY.** The passed counts rise by exactly the
new tests (+5 PG-ON, +2 PG-OFF — the two source sweeps need no database). The
pre-existing failures are the untouched M062/M064/M065 CRLF seal debt and
unrelated environment-dependent suites; they are not repaired here.

## Probe errors, recorded rather than hidden

1. A first shell probe built the trim set with doubled backslashes, so
   PostgreSQL resolved a **154-character** set instead of 29. Caught by asserting
   the length before trusting any result; the probe was rewritten to read the
   frozen literal out of the migration and let PostgreSQL resolve it.
2. The first version of the source sweep exempted a retraction **line**, not a
   retraction **paragraph**, so it flagged five continuation lines of the new
   retraction blocks. The rule was corrected to paragraph scope, and the negative
   control re-confirmed it still catches the original four defects.
3. The formatter reflowed the test file after the edit. Because a silent
   parametrisation failure has happened in this milestone before, collection was
   re-counted after formatting: **187**, with **4** parametrised cases present.

## Status

```
M081  APPROVED_AND_FROZEN
M082  CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW
M083  NOT_STARTED
PR #12  OPEN / NOT MERGED
```

No approval, merge, freeze or zero-blocker conclusion is claimed on the Owner's
behalf.
