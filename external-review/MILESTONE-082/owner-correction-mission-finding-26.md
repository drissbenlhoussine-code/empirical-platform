> **HISTORICAL RECORD — NOT CURRENT M082 AUTHORITY**
>
> This file records earlier reasoning, earlier conclusions and reproduced
> defects. Some of what it says was true only of an earlier candidate, and
> some of it is explicitly withdrawn. It is preserved so the history stays
> readable; it is not imported, rendered or validated as current truth.
>
> The single active statement of M082 authority is
> [`current-authority.md`](current-authority.md).

# MILESTONE-082 — Owner Final Sweep Correction — Finding 26

**Status: CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

> **⚠ THIS IS THE AUTHORITATIVE LATEST CORRECTION REPORT.** It supersedes
> `owner-correction-mission-findings-24-25.md`. Every other file in this package
> describes an earlier candidate and carries its own superseded notice.

| | |
|---|---|
| Branch | `feature/m082-operator-event-receipt-attestation` |
| Old head | `b8791472efee83796174608bfc5ee317b84a956b` |
| Base `master` | `28a10530dbc295fedacfa89c8aef246b35a0b86e` |
| Scope | documentation and tests only; **empty production behavior delta** |

---

## Finding 26 — exemption laundering in the claim sweep

### Pre-correction reproduction, preserved

All six attacks were executed against `b879147` before anything changed.

| # | Attack | Offenders at `b879147` | Verdict |
|---|---|---|---|
| 1 | `upper bound witness` with an unrelated negator later in the sentence | 1 *(as line-wrapped in the brief)* / **0** *(negator on the same line)* | **BYPASS** |  <!-- QUOTED-DEFECT -->
| 2 | `M082 exposes a historical snapshot, not merely a label-selection view.` | **0** | **BYPASS** |  <!-- QUOTED-DEFECT -->
| 3 | `Nothing prevents M082 from being a historical snapshot.` | **0** | **BYPASS** |  <!-- QUOTED-DEFECT -->
| 4 | `This qualified design states that M082 exposes a historical snapshot.` | **0** | **BYPASS** |  <!-- QUOTED-DEFECT -->
| 5 | `` `recorded_at` is operator-supplied. `` then `M082 exposes a historical snapshot.` | **0** | **BYPASS** |  <!-- QUOTED-DEFECT -->
| 6 | `This paragraph records a removed field from M079.` then the same claim | **0** | **BYPASS** |

**One honest correction to the brief.** Attack 1 *as written there* was caught,
because its negator falls on the second physical line and the sweep is
line-based. The mechanism the finding describes is nonetheless real: the same
claim written on **one** line returned **0 offenders**. Both variants were
executed and both results are recorded above rather than rounded to "all six".

Three distinct laundering routes were therefore live:

* **any negator anywhere on the line** exempted the whole line (attacks 1–3),
  including the double negative of attack 3, which *asserts* the claim;
* **any substring** of a marker word anywhere in the paragraph exempted every
  following line (attacks 4 and 6) — ordinary prose such as *"a removed field"*
  or *"This qualified design"* was indistinguishable from a banner;
* the **`recorded_at` / `operator-supplied` exception** set a paragraph-wide
  flag that flowed into later, unrelated M082 sentences (attack 5).

### The new structural exemption model

Exemption is now **structural only**. A banned phrase is exempt when, and only
when, one of these holds:

| # | Rule | Scope |
|---|---|---|
| 1 | the line sits inside a **banner-governed blockquote run** (a maximal run of `>` lines containing a banner line) | the whole quote |
| 2 | the line sits inside a **banner-governed fenced block** (banner is the immediately preceding non-empty line, or the fence's own first non-empty line) | the whole fence |
| 3 | the line sits in a **paragraph whose FIRST line is a banner** | that paragraph |
| 4 | the line **is itself** a banner line | that line |
| 5 | the line carries an explicit **line-local annotation** — `# BANNED-TERM` or `<!-- QUOTED-DEFECT -->` | that line |
| 6 | a negator **grammatically governs** every banned phrase on the line, and all of them are assertive-family | that line |

Nothing else exempts anything. The `recorded_at` / `operator-supplied`
paragraph exception is **deleted outright**; M079's quotation now carries the
explicit `QUOTED FROM M079:` banner instead.

**A banner is recognised structurally, not by substring.** After stripping
leading whitespace and the decoration characters `> # * - _ = ⚠ — ( [ " ' `` ` ``,
the line must **begin** with an upper-case token from:

```
RETRACTED  RETRACTION  SUPERSEDED  SUPERSESSION  WITHDRAWN  REMOVED
RENAMED  REPRODUCED  PRE-CORRECTION  CORRECTED  SWEEP VOCABULARY
QUOTED FROM M079
```

`This qualified design states …` and `a removed field from M079` are ordinary
prose: the token is neither first nor upper-case, so they scope nothing.

**Rule 3 is what kills paragraph laundering.** A banner must *lead* its block.
A marker appearing lower down is prose, so attack 6's second line is no longer
covered by its first. Paragraphs break on a blank line and on a bare `#`,
`"""`, `'''` or `>` — which is how the migration's two retraction banners keep
governing their own comment sub-blocks **without the migration being edited at
all**.

**Governing-clause negation.** A negator now exempts a phrase only when it sits
immediately before it, with nothing between them but determiners and light
adverbs (`a an the any some such merely just simply only even necessarily
really truly itself at all`):

```
SWEEP VOCABULARY. Examples of the rule, not assertions.

"is NOT a historical snapshot"                  -> governed     -> exempt
"exposes a historical snapshot, not merely a"   -> NOT governed -> offender
"NOTHING prevents ... a historical snapshot"    -> NOT governed -> offender
```

This is a structural adjacency test, not natural-language interpretation.

### The line-local annotation

Lines that must **spell** a banned term in order to ban or quote it — the
sweep's own vocabulary tuples, assertions that a term is absent, tables of what
was removed — carry `# BANNED-TERM` (Python) or `<!-- QUOTED-DEFECT -->`
(Markdown, invisible when rendered). It governs **its own line only** and can
never flow, which is the precise property the old paragraph markers lacked.
110 such lines were annotated across the swept surfaces.

### Negative controls — all six, permanent

`test_no_laundering_bypass_survives_the_structural_sweep` injects each attack
into the **real active design** in its own paragraph, asserts it is caught and
that the sweep names the expected phrase, then restores the file. **All six
caught independently.**

### Positive controls — honest wording must survive

`test_honest_denials_and_explicit_banners_remain_acceptable`:

| # | Wording | Result |
|---|---|---|
| 1 | `M082 is not a historical snapshot.` | **accepted** |
| 2 | `system_received_at is not an upper-bound witness.` | **accepted** |
| 3 | withdrawn claim inside an explicit `> **RETRACTED:**` blockquote | **accepted** |
| 4 | removed identifiers inside an explicit `> **REMOVED:**` block | **accepted** |
| 5 | M079's `recorded_at` quotation under `QUOTED FROM M079:` | **accepted** |

Control 5 is the one that matters for attack 5: the quotation is accepted, and
because the paragraph exception is gone it grants **no** exemption to any later
M082 claim.

### Anti-vacuity probe — executed, both rules

`test_weakening_either_structural_rule_breaks_its_control` restores each rule to
its `b879147` behaviour in turn and requires the matching attack to slip through
again:

* negation weakened to *"any negator anywhere on the line"* → **attack 2
  laundered**; rule restored → attack 2 caught.
* banner weakened to *"any substring, including `qualified`"* → **attack 4
  laundered**; rule restored → attack 4 caught.

Both controls therefore test the rules and not themselves.

---

## Preservation proof

| Constraint | Result |
|---|---|
| `migrations/` byte-identical to `b879147` | **`git diff --quiet` → 0. IDENTICAL** — no migration edit was needed |
| Production behavior delta | **EMPTY** (docstring-stripped AST, all three changed files) |
| Emitted artifact text | `ATTESTED_EVIDENCE_BANNER`, `_LIMITATIONS`, `BLANK_CHARACTERS` — **runtime values IDENTICAL** |
| `PROJECT_CHECKPOINT.md` | unchanged; `LATEST_FROZEN_MILESTONE=MILESTONE-081` |
| M076 production, M079/M080/M081 | unchanged |
| Schema, trigger, blank invariant, cutoff, receipt semantics, idempotency | untouched |
| Findings 24–25 corrected design sections | unchanged in substance; only marker syntax tightened |
| Prior commits | neither amended nor squashed |

Production changes are comment- and docstring-only. Because `_LIMITATIONS`
elements are runtime strings, their annotations are Python **comments** placed
after the closing quote — the emitted text is unchanged, proven by evaluating
both versions and comparing values.

---

## Validation

| Gate | Result |
|---|---|
| M082 unit | **40 collected, 40 passed** |
| M082 PostgreSQL lifecycle | **192 collected, 192 passed** |
| M082 fresh second pass | **4 collected, 4 passed** |
| Complete claim-sweep suite | **7 collected, 7 passed** |
| M076–M082 compatibility chain | **474 passed** |
| `compileall` / `ruff format --check` / `ruff check` | OK / 613 files / all passed |
| `mypy src` | no issues in 311 source files |
| architecture / negative fixture | exit 0 / exit 1 (both as required) |
| `python -m build` | wheel built |
| `git diff --check` | clean |

The suites were re-run **after** `ruff format`, which reflowed annotated lines
and reintroduced 9 offenders; annotation and formatting were then iterated to a
fixed point. This failure mode has bitten this branch before and is why the
convergence loop exists.

---

## What M082 still claims, unchanged by this mission

> A persisted receipt binds a stable receipt identity to an exact M076 event
> governance identity whose real public row was observed as originating from a
> prior committed transaction at receipt insertion. It does not attest event
> payload, wall-clock chronology, commit time, historical availability, or the
> provenance of persisted metadata labels.

**M081 APPROVED_AND_FROZEN · M082 CORRECTED_CANDIDATE_PENDING_OWNER_REVIEW ·
M083 NOT_STARTED · PR #12 OPEN / NOT MERGED**
