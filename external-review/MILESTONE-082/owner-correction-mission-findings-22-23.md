> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This file records earlier reasoning, earlier conclusions and reproduced
> defects. Some of what it says was true only of an earlier candidate, and
> some of it is explicitly withdrawn. It is preserved so the history stays
> readable; it is not imported, rendered or validated as current truth.
>
> The single active statement of M082 authority is
> [`current-authority.md`](current-authority.md).

# M082 — Owner Residual Claim-Surface Correction — Findings 22–23

**Status: `CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW`. Not merged, not frozen.**

This is the **authoritative latest correction** in this package. Every other file
describes an earlier candidate and carries its own superseded notice. Nothing is
deleted: incorrect earlier conclusions are kept visible as RETRACTED or
SUPERSEDED, and now inside blocks that are **explicitly scoped**.

Starting head `9b487d1`. Base `master` `28a1053`, `M081 APPROVED_AND_FROZEN`,
`LATEST_FROZEN_MILESTONE=MILESTONE-081` unchanged. Production behaviour,
migration SQL, the 29-character set, the CHECK constraints, the causal trigger,
cutoff behaviour and the Finding-21 tests are **untouched**.

---

## Finding 22 — the active design still treated the LABEL as a real instant

### Reproduced pre-correction, against `9b487d1`

The finding-20 sweep read source files only. The **active design** was never
swept, and it still treated the LABEL as a real instant at which something
happened. The block below is quoted as the defect, not asserted:
```
§8   "at the instant recorded in `system_received_at`"
§8   "Because the receipt instant is taken strictly **after** the event is  <!-- QUOTED-DEFECT -->
      durably committed"
§10  "already durably committed **at** `system_received_at`, measured by the
      **application host clock** of the process performing the attestation"
§11  "a value taken in the attesting process after that read is unambiguous
      about ordering"
§12  "at `system_received_at`, which on the sanctioned `attest()` path is taken
      from the application host clock **after** that read"
§12  "durably visible at any instant *earlier* than `system_received_at`"
§14  "beyond the receipt instants themselves"  <!-- QUOTED-DEFECT -->
§15  "receipt instant precedes commit"  <!-- QUOTED-DEFECT -->
§15  "recoverable later by an honest, clearly-later receipt"
§16  "the receipt records the **later, true** instant"
§16  "A later reconciliation may assign a later receipt instant."  <!-- QUOTED-DEFECT -->
§23  "`system_received_at` … the attestation instant"  <!-- QUOTED-DEFECT -->
§23  "`attested_by` … the pathway that attested"
§23  "`attester_version` … which writer produced it"
§26  "creates the receipt with the **later** true instant"  <!-- QUOTED-DEFECT -->
```

### The scoping defect, which is the more serious half

§8 carried a retraction notice that scoped itself to **"the inequality below"**.
Everything after that fenced inequality — the implication, the "**Proved by
execution**" claim and the "**can never overstate**" claim — sat **outside** the
retraction and read as active text (the reproduced defect is quoted next; it is
WITHDRAWN and asserted by nothing here):

```
RETRACTED: system_received_at <= K   IMPLIES   the event was durably committed by K
```

That is the claim `RETRACTION 2` withdrew at the top of the document, standing
unmarked in the section that explains why the design is sound. §16's two
reconciliation sentences were likewise active while the **domain module's own
limitations had already retracted them by name**.

### Corrected

Applied throughout, and stated once in §12 as the governing rule.
SWEEP VOCABULARY — the bullets below name the banned wording in order to ban it:
* `system_received_at` is a **LABEL** — never a *receipt instant*, never an  <!-- QUOTED-DEFECT -->
  *attestation instant*;  <!-- QUOTED-DEFECT -->
* **ON THE SANCTIONED `attest()` PATH** the clock **CALL** is issued **causally
  after** the read-back — the call is ordered, by program order plus PostgreSQL
  transaction visibility;
* the **value that call returns proves no wall-clock chronology** — not the
  observation's real time, not a bound, not an ordering against anything;
* **AS A GENERIC PERSISTED VALUE** the metadata has **UNAUTHENTICATED
  PROVENANCE**;
* old text survives **only inside explicitly scoped RETRACTED / SUPERSEDED
  blocks**, and the §8 block now says so — *"Everything from the inequality to
  the end of this block is withdrawn"* — rather than naming one line.

§§8, 10, 11, 12, 14, 15, 16, 23, 26 and the §2 M079 quotation were corrected.
The §2 quotation is now explicitly framed as *M079 speaking about `recorded_at`*,
not an M082 claim about an M082 column.

---

## Finding 23 — generic-origin language in the active tests

### Reproduced pre-correction, against `9b487d1`

Both lines below are quoted as the defect, not asserted:
```
tests/integration/test_m082_operator_event_receipt_lifecycle.py:235:
    """Scenarios B and C, and scenario D: the receipt stays system-controlled."""  <!-- QUOTED-DEFECT -->
tests/integration/test_m082_operator_event_receipt_lifecycle.py:244:
    # The receipt reflects system authority, not the operator's claim.  <!-- QUOTED-DEFECT -->
```

Both are generic origin claims. Neither is what the test drives: the test writes
through `attest()` and shows only that an operator-supplied `recorded_at`,
however absurd, does not reach the label **on that path**. A direct SQL receipt
is not system-controlled at all, and this suite proves elsewhere that one is  <!-- QUOTED-DEFECT -->
accepted by design.

Two equivalents were found by the same sweep and corrected with them; both are
quoted here as the defect: the pause-window docstring's *"The receipt instant  <!-- QUOTED-DEFECT -->
must fall AFTER K"*, and the unit suite's *"a caller cannot supply the
attestation instant"*.  <!-- QUOTED-DEFECT -->

Each is replaced by the narrower true statement, with the withdrawn wording kept
in a `SUPERSEDED (owner finding 23)` line beside it.

---

## Requirement 4 — the executable claim sweep, widened and made paragraph-local

`test_no_active_m082_claim_surface_asserts_origin_or_instant` now sweeps
**thirteen** surfaces: the seven M082 source and migration files, the **active
design**, the **current README**, **this report**, and the **three active M082
test files** including the one that hosts the sweep.

SWEEP VOCABULARY — banned phrase families, named here in order to ban them:
`system-assigned` / `system assigned` / `system-controlled` / `system controlled`
/ `reflects system authority` (origin) and `receipt instant` /
`attestation instant` / `true instant` (label-as-instant).

**The exemption is paragraph-local, not file-scoped.** The previous version
reset only on a blank line within a single file shape; a marker anywhere in a
file could excuse an unmarked claim far below it. The rules now derive from the
three file shapes actually swept:

* a blank line ends a paragraph — **except inside a fenced block**, where blank
  lines are content;
* a bare `#`, `"""` or `>` ends one in comment blocks and docstrings;
* a **markdown blockquote is continuous**, so a `> **⚠ RETRACTED**` banner scopes
  its whole quote;
* a **fenced block inherits** the marker state of the paragraph that introduced
  it — which is how quoted defect evidence such as the block above stays visible
  without being asserted.

Marker vocabulary: `retracted`, `superseded`, `withdrawn`, `qualified`,
`corrected by owner finding`, `reproduced`, `pre-correction`, `sweep vocabulary`,
`quoted here as the defect`.

### Executed negative control — `test_the_claim_sweep_is_paragraph_local_not_file_scoped`

A **surviving design phrase** — the exact wording finding 22 removed from §23 —
is appended to the real design file, far below every existing marker and in its
own paragraph. Quoted as the defect:
```
The `system_received_at` column records the attestation instant.  <!-- QUOTED-DEFECT -->
```

The sweep must catch it, and must go quiet again when it is removed. Executed
result: with the phrase injected, the sweep reports the following, quoted here
as the defect and not asserted:
```
MILESTONE_082_..._SCOPE_AND_DESIGN.md:<n>: The `system_received_at` column records the attestation instant.  <!-- QUOTED-DEFECT -->
```

and the design is restored in a `finally` block, verified clean afterwards by
the test's own final assertion. A file-scoped exemption would have passed this,
because that file legitimately contains dozens of retraction markers.

---

## Requirement 5 — evidence reconciled, including against my own report

### Secret-scan target count

**1136 at `9b487d1`**, verified by re-running the target discovery against a
clean checkout of that commit; the target lists at `9b487d1` and at the corrected
tree before this mission's new file were byte-identical.

My findings-20-21 report and the PR body said **1135**. That number was measured
**before** the report file itself was written, so it was correct when taken and
**stale for the commit it described**. The Owner's stated 1136 is the correct
figure for `9b487d1`.

**At the new head the count is 1137**, because this correction adds exactly one
file — `owner-correction-mission-findings-22-23.md`. Both figures are recorded
rather than one being quietly carried forward. Findings: **0** at both heads.

### "No suppressions anywhere" — **RETRACTED as false**

That claim appeared in the PR body and in earlier evidence. The exact
delta-scoped truth, measured as `git diff master` restricted to `src`,
`migrations`, `tests`, `tools`:

| Scope | Count | Detail |
|---|---|---|
| Production + migration | **2** | one `# pragma: no cover` on an unreachable defensive branch in the receipt repository adapter (`if winner is None`, reachable only if a conflicting row vanished); one `# noqa: E501` on a long import line |
| Tests | **16** | 11 `noqa` (7 `ANN202`, 2 `BLE001`, 1 `E501`, 1 `ANN001`) and 5 `type: ignore` on dynamically-typed helper returns |
| **M082 delta total** | **18** | |
| Introduced by findings 22–23 | **0** | `git diff 9b487d1 -- src migrations tests` contains no added suppression line |
| Repository-wide pre-existing baseline | 872 | untouched by this branch |

> **⚠ RETRACTED (owner finding 25).** This paragraph read: *"no suppression is
> used to silence a failing gate, no test is skipped or xfailed, and findings
> 22–23 add none"*. The skip/xfail half is **FALSE** — see
> `owner-correction-mission-findings-24-25.md`.

The honest claim is therefore: **no suppression is used to silence a failing
gate, no M082 test is xfailed or unconditionally skipped, PostgreSQL-dependent
fixtures conditionally skip when explicit PostgreSQL opt-in is absent, no
failing finding is concealed by skip or xfail, and findings 22–23 add no
suppression** — not "no suppressions anywhere", and not a denial that the
repository or a PG-off run reports skips.

---

## Preservation

Findings 22–23 change **documentation and test prose only**. Verified by
docstring-stripped AST comparison against `9b487d1` for every changed production
and migration file. The 29-character set, the four CHECK constraints, the causal
trigger, cutoff behaviour, receipt idempotency and the Finding-21 per-column
tests are unchanged. M076 production, M079/M080/M081 production and
`PROJECT_CHECKPOINT.md` are untouched. `M083` remains `NOT_STARTED`.

## Status

```
M081  APPROVED_AND_FROZEN
M082  CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW
M083  NOT_STARTED
PR #12  OPEN / NOT MERGED
```

No approval, merge, freeze or zero-blocker conclusion is claimed on the Owner's
behalf.
