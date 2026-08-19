> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This file records earlier reasoning, earlier conclusions and reproduced
> defects. Some of what it says was true only of an earlier candidate, and
> some of it is explicitly withdrawn. It is preserved so the history stays
> readable; it is not imported, rendered or validated as current truth.
>
> The single active statement of M082 authority is
> [`current-authority.md`](current-authority.md).

# MILESTONE-082 — Owner Narrow Correction Mission — Findings 24–25

**Status: CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

> **⚠ THIS IS THE AUTHORITATIVE LATEST CORRECTION REPORT.** Every other file in
> this package describes an earlier candidate and carries its own superseded
> notice. It supersedes `owner-correction-mission-findings-22-23.md`.

| | |
|---|---|
| Branch | `feature/m082-operator-event-receipt-attestation` |
| Old head | `fc550f7326125bd1f60cbdaf37671fe37e77e11f` |
| Base `master` | `28a10530dbc295fedacfa89c8aef246b35a0b86e` |
| Scope | documentation and tests only; **empty production behavior delta** |

---

## Finding 24 — residual active claims escaped the paragraph-local sweep

### Pre-correction reproduction, preserved verbatim

The claim sweep introduced by finding 23 was executed against `fc550f7`:

```
REPRODUCED, PRE-CORRECTION, AT fc550f7:
  pytest -k test_no_active_m082_claim_surface_asserts_origin_or_instant
  pytest -k test_the_claim_sweep_is_paragraph_local_not_file_scoped
  -> 2 passed
```

**That green result is preserved here because it is misleading.** It is kept as
evidence, not as reassurance. At the very moment the sweep reported **zero
offenders**, section 13 of the active design still carried, entirely outside any
locally scoped block, this text:

```
REPRODUCED DEFECT, WITHDRAWN, ASSERTED BY NOTHING HERE:

  `system_received_at` is an **upper bound witness** on the event's commit time
  M082 ... knows the event **had already committed** by `system_received_at`
```

The sweep passed because its vocabulary covered only the origin and
label-as-instant families. It could not see an upper-bound claim, a snapshot
claim, a removed status name or a removed CLI name. A passing sweep was
therefore evidence about the sweep, not about the document.

### The six sections, and how each failed locally

| § | Reproduced defect | Correction |
|---|---|---|
| 13 | `RETRACTED` banner was a blockquote; the withdrawn "upper bound witness" text sat **outside** it as plain active paragraphs | whole withdrawn block moved **inside** the banner's blockquote, wrapped in explicit *(Withdrawn text begins/ends.)* markers, and a **WHAT IS TRUE INSTEAD** paragraph added |  <!-- QUOTED-DEFECT -->
| 17 | `NO_SYSTEM_RECEIPT_EVIDENCE` stated as current behaviour, with **no marker at all** | active text now says the event is **structurally absent**; the removed status name is quoted inside a `SUPERSEDED` blockquote |  <!-- QUOTED-DEFECT -->
| 20 | `RETAINED VERBATIM ... WITHDRAWN REASONING:` was a one-line marker; the snapshot and "durably committed by `W`" paragraphs that followed were unmarked | entire retained block moved inside one blockquote under its own banner |  <!-- QUOTED-DEFECT -->
| 21 | `SUPERSEDED` blockquote followed by plain active text still using `attested_as_of` and "snapshot" | original text moved inside a blockquote carrying its own repeated banner |  <!-- QUOTED-DEFECT -->
| 24 | **malformed preservation** — the code span opened before the banner and closed after it, so the banner was swallowed into a broken span and the withdrawn command/flag rendered as active | code span repaired; active text now names only the current command and flag; withdrawn names quoted inside a blockquote |
| 27 | removed status table (`ATTESTED`, `NO_SYSTEM_RECEIPT_EVIDENCE`, `ATTESTED_AFTER_CUTOFF`) fully active, no marker | active text states the artifact emits **no status vocabulary at all**; table quoted inside a `SUPERSEDED` blockquote |  <!-- QUOTED-DEFECT -->

A global banner is not scoping. Every preserved false block is now blockquoted
under one explicit banner that begins in the same block.

### The strengthened sweep

Five families, all lowercased before matching:

| Family — sweep vocabulary, banned phrases named in order to ban them | Members | Negation allowed? |
|---|---|---|
| origin / label-as-instant *(existing)* | `system-assigned`, `system assigned`, `system-controlled`, `system controlled`, `reflects system authority`, `receipt instant`, `attestation instant`, `true instant` | no |  <!-- QUOTED-DEFECT -->
| upper bound / commit-by-label | `upper bound witness`, `upper-bound witness`, `durably committed by`, `implies durable commit`, `commit_time(event) <` | **yes** |  <!-- QUOTED-DEFECT -->
| historical / knowledge snapshot | `knowledge snapshot`, `historical snapshot`, `point-in-time snapshot`, `attested snapshot`, `snapshot at a cutoff` | **yes** |  <!-- QUOTED-DEFECT -->
| removed status names | `attested_after_cutoff`, `no_system_receipt_evidence`, `unattested_count` | no |  <!-- QUOTED-DEFECT -->
| removed API / CLI names | `attested_as_of`, `attested-as-of`, `attested_known_by`, `attested-evidence-snapshot`, `missingattestedeventerror` | no |  <!-- QUOTED-DEFECT -->

**Why two families accept negation.** Both banned phrases quoted in this
paragraph are named as sweep vocabulary, not asserted. For the assertive
families the corrected wording *is* the same words denied — "M082 is **NOT** a historical snapshot" has  <!-- QUOTED-DEFECT -->
to stay sayable while "M082 exposes a historical snapshot" must not. A line  <!-- QUOTED-DEFECT -->
whose only hits are assertive-family and which carries a negator
(`not `, `n't`, `never`, `no longer`, `cannot`, `no such`, `nothing`) is not an
offender. **Removed names get no such pass**: a deleted contract may be named
only under an explicit removal, rename or retraction marker, because naming it
in an unmarked active paragraph presents it as current.

Scoping markers gained `removed`, `renamed`, `no longer exists`,
`deliberately no`, `banned` — each of which states that the named thing is gone.

### Executed negative controls — the three classes finding 24 named

Each phrase is appended to the real active design in its **own unmarked
paragraph**, so only the phrase itself can trigger the sweep; each is then
removed and the file must go quiet.

| # | Injected — banned phrase, quoted as the defect | Caught on |
|---|---|---|
| 1 | ``​`system_received_at` is an upper bound witness on the commit time.`` | `upper bound witness` |  <!-- QUOTED-DEFECT -->
| 2 | `An event with no receipt reports NO_SYSTEM_RECEIPT_EVIDENCE.` | `no_system_receipt_evidence` |  <!-- QUOTED-DEFECT -->
| 3 | `The command takes --attested-as-of and emits a historical snapshot.` | `attested-as-of` |  <!-- QUOTED-DEFECT -->

All three caught, all three restored, file clean afterwards.

**Anti-vacuity probe, executed.** `_REMOVED_STATUS_NAMES` was temporarily
emptied and the control re-run:

```
REPRODUCED PROBE OUTPUT. The status name below is REMOVED and quoted as the
defect the blinded sweep failed to catch.

AssertionError: the sweep did NOT catch:
  An event with no receipt reports NO_SYSTEM_RECEIPT_EVIDENCE.
assert []
1 failed
```

Restored, `1 passed`. The control fails when the sweep is blinded, so it is
testing the sweep and not itself.

### Scoping the sweep did not weaken it

Making the strengthened sweep pass required adding paragraph-local markers to
**11 further places** that named a withdrawn claim or a removed identifier
without saying so locally — in the domain module, the attest usecase, the
design, this package's README, the findings 22–23 report, and two test files.
Every one was corrected by adding scoping, never by narrowing the vocabulary.
Two of them are worth naming: a fenced block of reproduced attack output in the
README inherited no marker because the blank line before the fence ended the
introducing paragraph (marker moved **inside** the fence), and several
`REMOVED` markers landed on the line *after* the banned name (reworded so the
marker precedes it).

---

## Finding 25 — the "no test is skipped" evidence claim was false

### Pre-correction reproduction

```
external-review/MILESTONE-082/validation-results.md:611
  "No suppression silences a failing gate, and no test is skipped or xfailed."

external-review/MILESTONE-082/owner-correction-mission-findings-22-23.md:197
  "...no test is skipped or xfailed, and findings 22-23 add none..."
```

Measured, PG-off, on the two M082 PostgreSQL suites:

```
5 passed, 187 skipped in 3.82s
```

Both M082 PostgreSQL fixtures call `pytest.skip()` when the opt-in is absent:

```
tests/integration/test_m082_operator_event_receipt_lifecycle.py:95
tests/integration/test_m082_operator_event_receipt_second_pass.py:67
    pytest.skip("PostgreSQL integration tests require explicit opt-in")
```

The old sentence is **RETRACTED in place**, visibly, in both files.

### Replacement wording

> No suppression silences a failing gate. **No M082 test is xfailed or
> unconditionally skipped.** PostgreSQL-dependent fixtures **conditionally
> skip** when explicit PostgreSQL opt-in is absent. **No failing finding is
> concealed by skip or xfail.** This statement is scoped to M082's own tests and
> does **not** deny that the repository at large, or any PG-off run, reports
> skips — both do.

Measured basis for the middle clause, across the three M082 test files:
**zero** `xfail`, **zero** `skipif`, **zero** `@pytest.mark.skip`.

---

## Preservation proof

| Constraint | Result |
|---|---|
| `migrations/` byte-identical to `fc550f7` | **`git diff --quiet` → 0. IDENTICAL** |
| Production behavior delta | **EMPTY** — docstring-stripped AST of both changed production files is byte-identical to `fc550f7` |
| `PROJECT_CHECKPOINT.md` | unchanged; `LATEST_FROZEN_MILESTONE=MILESTONE-081` |
| M076 production, M079/M080/M081 | unchanged |
| Database schema, CHECKs, trigger, blank set, cutoff, idempotency | untouched |
| Finding-21 constraint controls | untouched and passing |
| Prior commits | neither amended nor squashed |

Only two production files changed, both comment/docstring-only, and both proven
equal after docstring stripping:

```
src/empirical_platform/decision_candidate/operator_event_receipt.py
src/empirical_platform/usecases/attest_operator_event_receipt.py
```

---

## Validation

| Gate | Result |
|---|---|
| M082 unit | **40 collected, 40 passed** |
| M082 PostgreSQL lifecycle | **189 collected, 189 passed** |
| M082 fresh second pass | **4 collected, 4 passed** |
| M076–M082 compatibility chain | **471 passed** |
| Claim sweep + 3 sweep controls | **4 passed** |
| Migration up / down / up | `d9a2f5c81b73` → `b7e1c4a95d38` → `d9a2f5c81b73`, clean |
| `compileall` | OK |
| `ruff format --check` | 613 files formatted |
| `ruff check` | All checks passed |
| `mypy src` | no issues in 311 source files |
| architecture checker | clean |
| `git diff --check` | clean |

The M082 suites were **re-run after** `ruff format` reflowed the test file, because
a formatter reflow has silently broken a test anchor in this branch before.

---

## What M082 still claims, unchanged by this mission

> A persisted receipt binds a stable receipt identity to an exact M076 event
> governance identity whose real public row was observed as originating from a
> prior committed transaction at receipt insertion. It does not attest event
> payload, wall-clock chronology, commit time, historical availability, or the
> provenance of persisted metadata labels.

**M081 APPROVED_AND_FROZEN · M082 CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW ·
M083 NOT_STARTED · PR #12 OPEN / NOT MERGED**
