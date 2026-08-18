# MILESTONE-082 — Owner Final Closure Candidate

**Status: FINAL_CLOSURE_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

Starting head: `f61f14b15fb5caa5bebc89abef2bca65cecd0318`.
Base `master`: `28a10530dbc295fedacfa89c8aef246b35a0b86e`.

The final head and CI run ids are recorded in the PR #12 body after push and CI
completion. Nothing in this file embeds its own commit SHA.

---

## 1. Finding 28, reproduced against `f61f14b` before anything changed

Three marker-context bypasses, each injected independently into a real swept
surface. **All three returned zero offenders.**

| # | Attack | Offenders | Verdict |
|---|---|---|---|
| A | marker text inside a Python **string**, plus an unrelated real comment on the same line | 0 | **BYPASS** |
| B | Markdown marker text inside a Python **string** | 0 | **BYPASS** |
| C | Markdown marker displayed as inline **code**, not acting as a comment | 0 | **BYPASS** |

### Exact cause

* `_python_comment_lines()` recorded only that *some* `COMMENT` token existed on
  the line;
* `_has_inline_marker()` then searched the **entire raw line** for the marker;
* so the marker itself never had to be *inside* that comment token — any line
  with any comment could be annotated by text in a string;
* and the Markdown marker was accepted with no file-type check and no Markdown
  parsing context, so a marker rendered as code still annotated the line.

### The finding-27 conclusion is SUPERSEDED as misleading

Finding 27's green sweep is retained in the historical record and is **withdrawn
as evidence of correctness**. It proved only that its grammar accepted the text.
That has now been true for Findings 20, 21, 22, 23, 24, 26, 27 and 28 in
sequence — eight consecutive green results, each defeated by the next review.

---

## 2. The architectural decision: the claim sweep is retired

The sequence above is not a run of bad luck; it is the signature of a wrong
approach. Treating English prose as executable authority requires a parser for
banners, paragraphs, blockquotes, fences, negation, comment tokens and Markdown
context — and every added rule created a new bypass surface. The annotations
`BANNED-TERM` and `QUOTED-DEFECT` had become a second, undocumented language
embedded inside Python and Markdown.

**Retired entirely.** Deleted, not disabled:

```
_paragraph_scoped_offenders   _governed_blocks        _is_banner_line
_has_inline_marker            _python_comment_lines   _negation_governs
_NEGATOR_PATTERNS             _BANNER_TOKENS          _BANNER_DECORATION
_SCOPING_MARKERS              _INLINE_MARKERS         _ORIGIN_PHRASES
_UPPER_BOUND_PHRASES          _SNAPSHOT_PHRASES       _REMOVED_STATUS_NAMES
_REMOVED_API_NAMES            _ALL_BANNED             _FILLER
```

…together with **42 top-level definitions** in the lifecycle suite, including
every test whose purpose was to prove that the prose parser parsed prose. No
replacement marker name was introduced.

There is now **no banner parser, no paragraph parser, no negation parser and no
annotation parser** anywhere in active validation.

---

## 3. Canonical machine-readable authority

`external-review/MILESTONE-082/current-authority.json` is the single source of
M082 authority: structured, deterministic, and validated against the committed
closed schema `current-authority.schema.json`.

The schema uses `const`, closed `enum`, exact `minItems`/`maxItems` and
`additionalProperties: false`, so an unknown claim identifier is not merely
discouraged — it is **unrepresentable**.

It carries no timestamp, no hash, no CI run id and no commit self-reference.

`current-authority.md` is rendered from it by `tools/render_m082_authority.py`,
which supports `--check` and fails if the committed Markdown is not the
byte-exact rendering. The renderer maps closed identifiers to fixed sentences;
it interprets no prose.

**The claim was not strengthened to make canonicalisation easier.** The contract
enumerates 3 positive claims and 7 explicit non-claims, matching what the
milestone already established.

---

## 4. Active authority versus historical record

`authority-surface-manifest.json` classifies **every** M082 document exactly
once, and the classification is enforced by test.

| Class | Count |
|---|---|
| `CURRENT_AUTHORITY` | 4 |
| `CURRENT_VALIDATION_EVIDENCE` | 5 |
| `HISTORICAL_RECORD` | 24 |

Every historical file carries a top-level `HISTORICAL RECORD — NOT CURRENT M082
AUTHORITY` notice pointing at `current-authority.md`. Nothing historical is
imported, rendered, or validated as truth. No historical conclusion was deleted
or silently rewritten.

### One deliberate, recorded deviation

The byte-identical archive **cannot** carry an inline notice without ceasing to
be byte-identical. Those two requirements genuinely conflict for that one file.
The conflict is resolved in favour of byte-identity, because the checksum is
what makes the archive verifiable; the notice is supplied at directory level in
`history/README.md`. The exemption is recorded in the manifest with the
checksum, is enforced by test, and is not a general loophole — a corrupted
archive fails its checksum test.

### Archive

```
external-review/MILESTONE-082/history/MILESTONE_082_SCOPE_AND_DESIGN_at_f61f14b.md
  source commit : f61f14b15fb5caa5bebc89abef2bca65cecd0318
  original path : MILESTONE_082_OPERATOR_EVENT_RECEIPT_ATTESTATION_SCOPE_AND_DESIGN.md
  bytes         : 46733
  sha256        : 4112b1b1da560739827a042f48e5a72c49ec66e4e7c524f88fe89a9656c85e9b
```

The active root design was replaced with a concise current design (76 lines,
from over a thousand) containing only current architecture and a link to that
archive. The prior accumulated validation evidence was likewise moved to
`history/validation-results-through-finding-27.md`.

---

## 5. Hostile attacks and outcomes

| # | Attack | Outcome |
|---|---|---|
| A | unknown positive claim added to the contract | closed schema **rejects** |
| B | a required non-authority removed | schema **rejects** |
| C | generated Markdown modified without the JSON | `--check` **fails** |
| D | JSON modified without regenerating Markdown | `--check` **fails** |
| E | one file classified twice | manifest validation **fails** |
| F | one document left unclassified | manifest validation **fails** |
| G | a current-authority file marked historical | required-surface validation **fails** |
| H | historical notice removed from a historical file | validation **fails** |
| I | historical file imported by production or the renderer | import validation **fails** |
| J | a retired annotation token reintroduced into an active source | retired-mechanism validation **fails** |
| K | commit-time / wall-clock / payload / historical-availability authority added | closed claim set **rejects** |
| L | direct-SQL receipt with forged metadata | accepted only under existing database rules; neither renderer nor the canonical contract claims sanctioned-path provenance for it |

Additionally: corrupting the byte-identical archive **fails** its checksum test.

Each control is **anti-vacuous**: the rule is weakened, the attack is shown to
pass, the rule is restored, and the attack is shown to fail again.

---

## 6. Production and database preservation

| Constraint | Result |
|---|---|
| `migrations/` byte-identical to `f61f14b` | **IDENTICAL** |
| Production behaviour delta | **EMPTY** — docstring-stripped AST comparison |
| Emitted runtime values | `ATTESTED_EVIDENCE_BANNER`, `_LIMITATIONS`, `BLANK_CHARACTERS` — **values identical** |
| Text and JSON report output | unchanged |
| M076 production, M079, M080, M081 | unchanged |
| Trigger, foreign key, uniqueness, row immutability | unchanged |
| 29-character blank set, four CHECK constraints | unchanged |
| Receipt idempotency, receipt-only architecture, cutoff SQL | unchanged |
| Future-tail non-interference, no payload enrichment | unchanged |
| Direct-SQL acceptance semantics | unchanged |
| `PROJECT_CHECKPOINT.md` | unchanged; `LATEST_FROZEN_MILESTONE=MILESTONE-081` |
| New table / migration / receipt authority / M083 | **none** |

Production changes are docstring-only, in three files.

---

## 6b. Validation, with collection counts

| Suite | Collected | Result |
|---|---|---|
| M082 unit | 40 | 40 passed |
| M082 PostgreSQL lifecycle | 184 | 184 passed |
| M082 fresh second pass | 4 | 4 passed |
| **M082 authority contract (new)** | **28** | **28 passed** |
| M082 suites together | 256 | 256 passed |
| M076–M082 compatibility chain | — | 494 passed |

The lifecycle suite falls from 195 to 184 because the eleven tests that existed
to prove the prose parser parsed prose were deleted with it. The 28 new
structural tests replace them.

### Full regression, exact failing-ID comparison

| Mode | Baseline `f61f14b` | Candidate | Failing-ID diff |
|---|---|---|---|
| PostgreSQL **on** | 24 failed, 2943 passed, 44 errors | 24 failed, 2957 passed, 44 errors | **EMPTY** (24 ids) |
| PostgreSQL **off** | 8 failed, 2337 passed, 12 errors | 8 failed, 2352 passed, 12 errors | **EMPTY** (8 ids) |

### Repository gates

`compileall` OK · `ruff format --check` 615 files · `ruff check` all passed ·
`mypy` no issues in 312 source files · architecture checker exit 0 · negative
architecture fixture exit 1 · dependency audit no actionable finding · wheel and
sdist built · **clean-environment wheel import OK** (blank set size 29) ·
**console entry point verified from the installed wheel** · `git diff --check`
clean · migration up/down/up `d9a2f5c81b73` → `b7e1c4a95d38` → `d9a2f5c81b73` ·
secret scan 1150 targets, 0 findings · changed-files exact comparison · clean
tree.

---

## 7. Unresolved limitations, stated rather than closed

* The contract asserts what M082 claims; it cannot prove the **database** matches
  it. That correspondence is established by the executed PostgreSQL suites, not
  by the contract.
* `current-authority.md` is generated, but a reader can still write prose
  elsewhere in the repository that overstates M082. What has been removed is the
  pretence that a parser could detect that automatically; the defence is now that
  authority lives in exactly one enumerated place.
* The historical record remains large and contains withdrawn claims by design. A
  reader who ignores the notices can still be misled by an archived file.
* `authority_version` is 1 and there is no migration path defined for a future
  version 2; that is deliberate scope, not an oversight.

---

## 8. Probe errors and misleading intermediate conclusions

1. **The notice stamp broke the archive's byte-identity.** Stamping all
   historical files changed the archive's SHA-256 from
   `4112b1b1…` to `2c556376…`. Caught by re-verifying against `f61f14b`; the
   archive was restored and the directory-level notice adopted instead. Recorded
   because the first checksum published in this mission's working notes was
   briefly wrong.
2. **A stale byte count.** The current design first recorded `47193` bytes for
   the archive, computed while the notice was still prepended. Corrected to
   `46733`; the design, the manifest and `history/README.md` now agree.
3. **The contract suite tripped its own rules**, naming the retired tokens and
   retired function names in order to ban them. Resolved by exempting exactly
   that one file by resolved path — an explicit single-file exemption, not a
   pattern other files could satisfy.
4. **A regression baseline was contaminated, and its result is discarded.** The
   first isolated-baseline attempt ran in a git worktree while other database
   tests were running in the main tree, and reported `25 failed / 83 errors`
   against the candidate's `24 / 44`. That is a collision artifact, not a
   finding. It was discarded and the baseline re-run with nothing else touching
   PostgreSQL, giving `24 failed / 2943 passed / 44 errors` and an EMPTY
   failing-ID diff. This is the second time in this branch's history that I have
   made exactly this mistake.
5. **I claimed an unimplemented gate.** `validation-results.md` listed "runtime
   text and JSON expose no authority beyond the canonical contract" as passing
   before that test existed. Caught during the in-mission hostile review. The
   gate was then implemented structurally — closed key sets, forbidden field
   fragments, and text/JSON consistency — rather than the claim being softened.
6. **The clean-environment console-entry-point check first failed** with
   `ModuleNotFoundError: sqlalchemy`. That was the check being wrong, not the
   package: the CLI requires the `[persistence]` extra. Re-run with the extra,
   it prints its usage correctly.
7. **`jsonschema` is not installed.** Rather than add a runtime dependency, the
   committed schema is enforced by a small dependency-free validator inside the
   renderer that implements exactly the keywords the schema uses. This is
   recorded because "schema-validated" could otherwise be read as implying a
   third-party validator.

---

## 9. Status

```
M081  APPROVED_AND_FROZEN
M082  FINAL_CLOSURE_CANDIDATE_PENDING_OWNER_REVIEW
M083  NOT_STARTED
PR #12  OPEN / NOT MERGED
```

No approval, freeze, merge or zero-blockers claim is made on the Owner's behalf.
