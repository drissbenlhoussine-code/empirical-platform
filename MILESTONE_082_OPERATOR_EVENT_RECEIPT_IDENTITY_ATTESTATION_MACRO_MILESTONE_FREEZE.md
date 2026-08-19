# MILESTONE-082 - Operator Event Receipt Identity Attestation - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Branch `master`. M082 baseline `28a10530dbc295fedacfa89c8aef246b35a0b86e` (the
M081 Owner Freeze hash-recording HEAD; M081 fully `APPROVED_AND_FROZEN`),
re-resolved from git and from `PROJECT_CHECKPOINT.md` immediately before the
merge rather than taken from the mission text. Delivered through pull request
#12, owner-approved at head `e225d84d88b4d91b160fd3f43f95333f241378e7` with both
`verify` runs green on that exact SHA (`32245618866`, `32245615070`), and merged
into `master` as `2e211eae49515b6d58663ee7ededf6b768cb56ca`.

The pull request was merged with a **true merge commit** carrying two parents,
`28a1053` and `e225d84`. **All twenty-two commits are preserved and none was
squashed away.** The four commits of the final closure and acceptance sequence:

| Commit | What it is |
|---|---|
| `37e99a5` | closure refactor: the canonical authority contract replaces the prose claim sweep |
| `8d575bb` | Windows path separators, CRLF-portable archive checksum, coverage margin |
| `12c3b84` | archive checksum grouped so the secret scanner stops classifying it as a secret |
| `e225d84` | the three structural contract gaps closed |

The active design is
`MILESTONE_082_OPERATOR_EVENT_RECEIPT_ATTESTATION_SCOPE_AND_DESIGN.md`. The
external review package is under `external-review/MILESTONE-082/`.

All evidence in this record - including every PostgreSQL result - was executed in
a Linux container against a real PostgreSQL 16.13 server, not simulated.

## The Authority Is Not Stated In Prose

This is the structural decision of the milestone, and it is deliberate.

M082's authority is stated **once**, machine-readably, in
`external-review/MILESTONE-082/current-authority.json`, validated against the
committed closed schema `current-authority.schema.json`, and rendered
deterministically to `current-authority.md` by `tools/render_m082_authority.py`.
The renderer maps closed identifiers to fixed sentences and interprets no prose.
`--check` fails if the committed document is not the byte-exact rendering.

The schema uses `const`, closed `enum`, exact item counts and
`additionalProperties: false`. An unknown claim identifier is therefore
**unrepresentable**, not merely discouraged. `authority_version` is frozen at
`const: 1`, so a version bump is an explicit schema change rather than a silent
one.

## A. What A Persisted Receipt Proves

A persisted receipt binds:

- a **stable receipt identity**;
- a binding to **one exact M076 event governance identity**;
- that the referenced `public` event row **originated from a prior committed
  transaction at receipt insertion**.

The attestation process reads the event back from committed persistence and only
then creates the receipt. `attest()` runs in a transaction of its own, so it can
observe the event only if the event's transaction has already committed. The
claim is **causal** and holds regardless of any clock.

## B. What It Does NOT Prove - Seven Explicit Non-Claims

Enumerated as a closed set in the contract, and none of them may be weakened:

1. **not** the event payload, current or historical;
2. **not** the event's commit time;
3. **not** any wall-clock chronology;
4. **not** historical availability;
5. **not** availability to an arbitrary reader at an arbitrary cutoff;
6. **not** the provenance of persisted metadata;
7. **not** that an arbitrary persisted receipt came through the sanctioned
   `attest()` path.

## C. Metadata Provenance - Unauthenticated As A Generic Persisted Value

As **generic persisted values**, `system_received_at`, `attested_by` and
`attester_version` have **UNAUTHENTICATED PROVENANCE**. A direct SQL caller with
write access can insert a receipt for an already-committed event carrying any
allowed value, and neither renderer nor contract can tell it apart from one
`attest()` produced. **This acceptance is by design and is not a defect.**

**ON THE SANCTIONED `attest()` PATH ONLY:** the application clock CALL that
produces `system_received_at` is issued causally after the committed read-back -
**the value it returns proves no chronology**; `attester_version` is an
application constant; `attested_by` is caller-supplied and passed through
unchanged.

## D. The Cutoff Is A Receipt-Label Filter And Nothing More

It selects receipts whose label is at or before the cutoff and asserts nothing
else. It does **not** carry historical knowledge authority, does **not** emit
future-tail counts, and does **not** enrich entries with event payload.

It is **not** a point-in-time reconstruction. Because a label can be backdated, a
receipt created later can carry a qualifying label, so **repeated evaluation at
the same cutoff can legitimately change**. The view deliberately reports no count
of what it excluded, because counting it would itself be future-aware.

## E. What The Database Enforces, And What It Does Not

| Property | Enforced |
|---|---|
| the referenced event exists | **yes** - foreign key |
| the referenced event came from a prior committed transaction | **yes** - BEFORE INSERT trigger, schema-qualified, pinned `search_path`, explicit status allowlist, fails closed |
| exactly one receipt per event | **yes** - UNIQUE |
| receipt evidence cannot vanish with its event | **yes** - `ON DELETE RESTRICT` |
| row-level UPDATE/DELETE immutability | **yes** - trigger |
| non-blank identity and metadata | **yes** - four CHECKs over the complete 29-character Python `str.strip()` set |
| the provenance of persisted metadata | **NO** |
| any wall-clock chronology | **NO** |

Row immutability is **row-level UPDATE/DELETE only**. TRUNCATE, DROP TRIGGER,
DROP TABLE and a superuser remain outside it. This is **not** absolute database
immutability.

## F. Twenty-Eight Owner Findings - Every One Removed A Claim

No owner review on this branch strengthened M082. Each removed authority the
milestone could not support: the future-receipt leak; the unproved wall-clock
upper bound; a stale migration claim; a same-transaction forged receipt; an
unstable cutoff; a fail-open trigger; payload binding; a `pg_temp` bypass; a
far-future crash; non-atomic reads; stale claim surfaces; a blank-definition
mismatch; overclaimed metadata provenance; clock chronology in crash language;
and the residual provenance, scoping and grammar defects of findings 20 through
28.

**M082 does NOT replace M079's `recorded_at` firewall.** It supplies a smaller
true primitive - causal receipt attestation - instead of a larger false one.

## G. The Retired Validation Approach - Recorded Honestly

Findings 20 through 28 produced **eight consecutive green prose sweeps, each
defeated by the next review**. Treating English as executable authority required
parsers for banners, paragraphs, blockquotes, fences, negation, comment tokens
and Markdown context, and every added rule created a new bypass surface.

That approach is **retired**: 42 top-level definitions deleted, both annotation
tokens removed from every active surface, and no replacement marker introduced.
A test asserts the retired names do not reappear. **The pattern, not any single
bypass, is what justified the change.**

## H. Active Authority Versus Historical Record

`authority-surface-manifest.json` classifies **every** M082 document exactly
once, into a **closed** three-name class set, enforced by test:

| Class | Count |
|---|---|
| `CURRENT_AUTHORITY` | 3 - the contract, its schema, the generated document |
| `CURRENT_VALIDATION_EVIDENCE` | 7 |
| `HISTORICAL_RECORD` | 24 |

`CURRENT_AUTHORITY` is asserted as an **exact set**, so nothing can be demoted
out of authority and nothing promoted into it.

**Zero files were deleted.** Every historical file carries a `HISTORICAL RECORD
- NOT CURRENT M082 AUTHORITY` notice. Nothing historical is imported, rendered or
validated as truth. **Withdrawn conclusions are preserved visibly, not rewritten
into correctness.**

One deliberate deviation is recorded rather than hidden: a byte-identical archive
cannot carry an inline notice without ceasing to be byte-identical. Byte-identity
won, the notice is supplied at directory level, and the exemption is recorded in
the manifest with its checksum and enforced by test.

## I. Adversarial Review

Over 250 executed attacks across the design, implementation and review passes,
including the mandatory owner attacks: future-receipt interference, a backward
clock, a same-transaction direct SQL INSERT, a `pg_temp` shadowing bypass, forged
metadata through direct SQL, per-column blank refusal through all four installed
CHECKs, and the twelve closure attacks plus the three final-acceptance attacks.

**Every negative control is anti-vacuous**: the matching rule is weakened, the
attack is shown to pass, the rule is restored, and the attack is shown to fail.

## J. Validation Evidence

| Suite | Collected | Result |
|---|---|---|
| M082 unit (domain) | 40 | 40 passed |
| M082 CLI argument handling | 9 | 9 passed |
| M082 handler wiring | 4 | 4 passed |
| M082 PostgreSQL lifecycle | 184 | 184 passed |
| M082 fresh second pass | 4 | 4 passed |
| M082 authority contract | 36 | 36 passed |
| **M082 together** | **277** | **277 passed** |

Full regression at `12c3b84`, each run in isolation: PostgreSQL-on 24 failed /
2973 passed / 44 errors; PostgreSQL-off 8 failed / 2368 passed / 12 errors.
**Failing-ID diffs EMPTY in both modes** against the baseline. Production and
migrations are byte-identical from `12c3b84` to `e225d84`, so the campaign was
not repeated at the final head.

Gates: `compileall`, `ruff format --check`, `ruff check`, `mypy`,
`render_m082_authority.py --check`, architecture exit 0, negative fixture exit 1,
dependency audit, secret scan 0 findings, wheel and sdist, clean-environment
wheel import, console entry point verified from the installed wheel,
`git diff --check`, changed-files exact comparison.

## K. Frozen Preservation

M076 production code, M079, M080 and M081 are **byte-identical** across the
merge and do **not** consume this authority. The M082 migration `d9a2f5c81b73`
adds one table and performs **no backfill**. No existing table was altered, no
existing repository method changed, and `PROJECT_CHECKPOINT.md` was untouched by
the milestone itself.

## L. M062 / M064 / M065 Seal Debt - Not Repaired

M082 introduces no fixture, no dataset bundle and no byte seal, so the
pre-existing CRLF seal debt provably does not block it. It continues to warrant
its own authorization and was deliberately not repaired here.

## M. Known Limitations

- The contract states what M082 **claims**; it cannot prove the **database**
  matches it. That correspondence rests on the executed PostgreSQL suites.
- Prose elsewhere in the repository can still overstate M082. What was removed is
  the pretence that a parser could detect that automatically.
- The historical record remains large and contains withdrawn claims by design.
- `authority_version` is frozen at 1 with no defined migration path to a
  version 2.
- Row immutability does not cover TRUNCATE, DROP or a superuser.
- A crash between event commit and receipt insertion leaves an unattested gap.

## N. Claim Honesty

`M082_PROFITABILITY_CLAIM=NONE_MADE`.
`M082_LIVE_TRADING_READINESS_CLAIM=NONE_MADE`.
`M082_INVESTMENT_ADVICE_CLAIM=NONE_MADE`.

M082 emits no monetary value, no ratio, no aggregate and no performance figure of
any kind. It does not assert that an operator's assertion is true, that
`recorded_at` is honest, that any trade occurred, or that any price was paid.

## O. Owner Approval

Owner approval was explicitly granted for exact candidate head
`e225d84d88b4d91b160fd3f43f95333f241378e7`, with PR #12 open and not merged,
`master` at `28a1053`, both CI runs green on that exact SHA, and a clean working
tree - all five identities re-resolved immediately before the merge.

**Freeze declaration:** `M082 MACRO MILESTONE APPROVED_AND_FROZEN`.
`M082 APPROVED_AND_FROZEN`.

## P. Deferred / M082 Boundary

Explicitly not built: any knowledge watermark; any change to M079, M080 or M081;
any commit-time, wall-clock, payload, historical-availability or
universal-attestation authority; any backfill of legacy events; any second
receipt authority. Binding an evaluation to an explicitly persisted receipt set
is a future evidence-watermark milestone and is **not started**.

## Q. Next Permitted Action

MILESTONE-083 - **recommendation only**; not started as part of M082.
