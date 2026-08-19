> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This file records earlier reasoning, earlier conclusions and reproduced
> defects. Some of what it says was true only of an earlier candidate, and
> some of it is explicitly withdrawn. It is preserved so the history stays
> readable; it is not imported, rendered or validated as current truth.
>
> The single active statement of M082 authority is
> [`current-authority.md`](current-authority.md).

# MILESTONE-082 — Owner Narrow Correction — Finding 27

**Status: CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

> **⚠ THIS IS THE AUTHORITATIVE LATEST CORRECTION REPORT.** It supersedes
> `owner-correction-mission-finding-26.md`. Every other file in this package
> describes an earlier candidate and carries its own superseded notice.

| | |
|---|---|
| Branch | `feature/m082-operator-event-receipt-attestation` |
| Old head | `7ed953adc484ae60b023c717238abd778ab5af42` |
| Base `master` | `28a10530dbc295fedacfa89c8aef246b35a0b86e` |
| Scope | documentation and tests only; **empty production behavior delta** |

---

## Finding 27 — the exemption grammar was looser than its documented contract

### Pre-correction reproduction, preserved

All five attacks executed against `7ed953a`, each injected independently into
the real active design. **Every one returned ZERO offenders.**

```
REPRODUCED at 7ed953a. Quoted as defects, asserted by nothing here.

ATTACK                                                OFFENDERS   VERDICT
--------------------------------------------------------------------------
1 late banner governs an EARLIER false claim               0      BYPASS
2 raw marker name as ordinary prose                        0      BYPASS
3 raw Markdown marker name, no comment syntax              0      BYPASS
4 banner-token prefix without a boundary                   0      BYPASS
5 negator substring inside another word                    0      BYPASS
--------------------------------------------------------------------------
bypasses: 5/5
```

**The finding-26 green result is therefore SUPERSEDED as misleading**, exactly
as its predecessors were. A sweep that reports zero offenders proves only that
its *grammar* accepted the surface, never that the surface is honest. That has
now been true three reviews running, and it is recorded here rather than
smoothed over.

Each attack exploited a different gap between the documented contract and the
implemented grammar:

| # | Gap |
|---|---|
| 1 | a blockquote run was governed if **any** line in it was a banner, so a banner on line 2 retroactively exempted the false claim on line 1 |
| 2 | the Python annotation was a **substring** test, so the bare word `BANNED-TERM` in running prose annotated the line |
| 3 | likewise `QUOTED-DEFECT` without its `<!-- … -->` comment syntax |
| 4 | a banner token was matched by `startswith` with **no end boundary**, so `REMOVEDLY` was a banner |
| 5 | negators were bare substrings, so `not` matched inside `knot` and governed the claim after it |

### The corrected grammar

**Rule 1 — blockquote order.** A blockquote run is governed only when its
**first non-empty content line** is a valid banner. A later banner never
governs what precedes it.

**Rule 2 — exact annotation grammar.** Exactly two forms are recognised:

* `# BANNED-TERM` — and in Python it must be a **real COMMENT token**. The file
  is tokenised, so the same text inside a string literal annotates nothing.
* `<!-- QUOTED-DEFECT -->` — the complete Markdown comment.

The undocumented `(QUOTED-DEFECT)` parenthetical is **abolished as a marker**.
It was an implicit third form that never appeared in the contract. Measured on
this branch: **17 occurrences across 5 files**, every one of them re-scoped
structurally — none deleted, none excused.

**Rule 3 — banner token boundary.** A recognised token must be followed by
end-of-line or a non-word character. `REMOVEDLY`, `CORRECTEDNESS` and every
equivalent prefix are ordinary prose.

**Rule 4 — negator lexical boundary.** Negators are matched as independent
lexical tokens with `(?<![\w-])…(?![\w-])`. `not` inside `knot`, or `no` inside
a longer identifier, governs nothing.

### Re-scoping, done honestly

Removing the undocumented marker plus the blockquote-order fix exposed **20**
lines. Every one was re-scoped by giving its paragraph a **truthful leading
banner** — `QUOTED FROM M079:`, `REMOVED`, `RENAMED`, `REPRODUCED`,
`SWEEP VOCABULARY` — or, for code lines, the exact `# BANNED-TERM` comment.
**No banned phrase was removed from the vocabulary and no surface was dropped
from the sweep.**

> **RETRACTED — an intermediate approach of my own.** A first pass prefixed
> every affected paragraph mechanically with `REPRODUCED DEFECT, quoted not
> asserted.` That produced *false* prose: it labelled the module's own
> explanation (`WHAT THIS EXISTS TO FIX`) and its true statement
> (`THIS IS A RECEIPT-LABEL-CUTOFF VIEW, NOT A HISTORICAL SNAPSHOT`) as
> reproduced defects. Green results obtained that way would have been worthless.
> The mechanical prefix was reverted in all five files and every paragraph was
> re-scoped individually with an accurate banner.

### Negative controls — all five, permanent

`test_no_grammar_bypass_survives_the_exact_marker_contract` injects each attack
into the real active design, asserts it is caught and that the sweep names the
expected phrase, then restores the file. **All five caught independently.**

### Positive controls — the documented forms still work

`test_the_exact_marker_contract_still_accepts_documented_forms`:

| # | Form | Result |
|---|---|---|
| 1 | honest negation — `M082 is not a historical snapshot.` | **accepted** |
| 2 | correctly **leading** `RETRACTED:` blockquote | **accepted** |
| 3 | correctly leading governed fence | **accepted** |
| 4 | exact Python annotation `# BANNED-TERM`, on a **Python** surface | **accepted** |
| 5 | exact Markdown annotation `<!-- QUOTED-DEFECT -->` | **accepted** |

Control 4 also asserts the **contrast**: the identical line *without* its
comment token is **caught**. That contrast is what makes the annotation a
grammar rather than a substring.

> **Corrected during this mission.** Control 4 was first written to inject a
> Python annotation into the Markdown design inside a ` ```python ` fence, and
> it failed. The failure was correct — the `# BANNED-TERM` form is deliberately
> Python-only, honoured only where a real COMMENT token exists. The control was
> wrong, not the rule, and it now runs against a real `.py` surface.

### Anti-vacuity — one mutation per structural rule

`test_weakening_each_finding_27_rule_breaks_its_own_control` reverts each rule
to its `7ed953a` behaviour in turn and requires the matching attack to slip
through again, then be caught once restored:

| Rule reverted | Attack laundered | Restored |
|---|---|---|
| 1 — blockquote order → `any()` banner in the run | attack 1 | caught again |
| 2 — annotation grammar → bare substring | attack 2 | caught again |
| 3 — banner boundary → `startswith` only | attack 4 | caught again |
| 4 — negator boundary → substring match | attack 5 | caught again |

---

## Preservation proof

| Constraint | Result |
|---|---|
| `migrations/` byte-identical to `7ed953a` | **IDENTICAL** |
| Production behavior delta | **EMPTY** (docstring-stripped AST, all 3 touched files) |
| Emitted artifact text | `ATTESTED_EVIDENCE_BANNER`, `_LIMITATIONS`, `BLANK_CHARACTERS` — **runtime VALUES identical** |
| `PROJECT_CHECKPOINT.md` | unchanged; `LATEST_FROZEN_MILESTONE=MILESTONE-081` |
| M076 production, M079 / M080 / M081 | unchanged |
| Schema, trigger, 29-character blank set, four CHECKs, cutoff, receipt semantics, idempotency, repository behaviour | untouched |
| Prior commits | neither amended nor squashed |

---

## Validation

| Gate | Result |
|---|---|
| M082 unit | **40 collected, 40 passed** |
| M082 PostgreSQL lifecycle | **195 collected, 195 passed** |
| M082 fresh second pass | **4 collected, 4 passed** |
| Complete claim-sweep suite | **10 collected, 10 passed** |
| M076–M082 compatibility chain | **477 passed** |
| Migration up / down / up | `d9a2f5c81b73` → `b7e1c4a95d38` → `d9a2f5c81b73`, clean |
| `compileall` / `ruff format --check` / `ruff check` | OK / 613 files / all passed |
| `mypy src` | no issues in 311 source files |
| architecture / negative fixture | exit 0 / exit 1 |
| dependency audit / build | no actionable finding / wheel built |
| `git diff --check` | clean |

---

## What M082 still claims, unchanged by this mission

> A persisted receipt binds a stable receipt identity to an exact M076 event
> governance identity whose real public row was observed as originating from a
> prior committed transaction at receipt insertion. It does not attest event
> payload, wall-clock chronology, commit time, historical availability, or the
> provenance of persisted metadata labels.

**M081 APPROVED_AND_FROZEN · M082 CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW ·
M083 NOT_STARTED · PR #12 OPEN / NOT MERGED**
