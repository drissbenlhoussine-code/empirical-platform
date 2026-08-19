# MILESTONE-082 — Operator Event Receipt Identity Attestation — Review Package

**Status: FINAL_CLOSURE_CANDIDATE_PENDING_OWNER_REVIEW. Not merged, not frozen.**

> **⚠ START HERE — [`current-authority.md`](current-authority.md).**
>
> That document is the **single active statement** of what this milestone
> establishes. It is generated deterministically from
> [`current-authority.json`](current-authority.json), which is the canonical,
> machine-readable, schema-validated contract.
>
> Nothing else in this package carries authority.

Base `master` `28a1053`.

## How this package is organised

Every file is classified exactly once in
[`authority-surface-manifest.json`](authority-surface-manifest.json), and that
classification is enforced by test, not by convention.

| Class | Meaning | Files |
|---|---|---|
| `CURRENT_AUTHORITY` | what M082 claims **now** | the canonical contract, its schema, the generated document, and the current design |
| `CURRENT_VALIDATION_EVIDENCE` | how that claim was checked at this head | this README, the manifest, changed-files, validation results, the closure report |
| `HISTORICAL_RECORD` | earlier reasoning, preserved unedited | every earlier review and correction report, and the archived legacy design |

Historical files each carry a top-level notice saying they are not current
authority. They are never imported, rendered, or validated as truth. They are
kept because deleting a withdrawn conclusion would hide how the milestone got
here.

## The claim, in one sentence

A persisted receipt binds a stable receipt identity to one exact M076 event
governance identity whose real `public` row originated from a **prior committed
transaction** at receipt insertion. It does not attest event payload, commit
time, wall-clock chronology, historical availability, or the provenance of
persisted metadata.

The exact, enumerated version of that sentence — including every non-claim — is
in the canonical contract.

## Where to look

| File | What it is |
|---|---|
| `current-authority.md` | **START HERE.** The active authority, generated |
| `current-authority.json` | the canonical contract |
| `current-authority.schema.json` | the closed schema that contract must satisfy |
| `authority-surface-manifest.json` | the classification of every M082 document |
| `owner-final-closure-candidate.md` | the closure mission's delivery report |
| `validation-results.md` | executed gates at this head |
| `runtime-output-fixture.json` | frozen reviewed runtime output, pinned by digest |
| `changed-files.txt` | the exact `master..head` file list |
| `history/` | the archived legacy design, byte-identical, with its checksum |

## What replaced the previous validation approach

Earlier candidates validated authority by scanning English prose for banned
phrases and exempting it with banners, paragraph rules, negation parsing and
inline annotations. Findings 20 through 28 each defeated that mechanism, and its
green results proved only that its grammar accepted the text.

It is retired. Authority is now a small closed contract, and validation is
structural: schema conformance, closed identifier sets, byte-exact rendering,
manifest completeness, and runtime output that cannot exceed the contract.
