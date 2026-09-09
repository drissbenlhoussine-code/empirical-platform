# MILESTONE-084 - Decision-to-Approval Product Core - Macro Milestone Freeze

## Status: FINAL - OWNER FROZEN

## Repository Authority

Branch `master`. M084 baseline `707161a1e8edeb7e0c95f3dafc7180ba9d782cc6` (the
M083 Owner Freeze hash-recording HEAD; M083 fully `APPROVED_AND_FROZEN`),
re-resolved from git and from `PROJECT_CHECKPOINT.md` immediately before the
merge rather than taken from the mission text. Delivered through pull request
#14, reviewed at head `e0907c4b95ceb455dc83984ef9a0aaae7066f567`, closed at
corrected head `e661fa9c56a09fd0d2c5410c46b0fcc29c725427` with both `foundation`
runs green on that exact SHA (`34376127027` push, `34376131800` pull_request),
and merged into `master` as `a7cca5109a4d8f9154f08f3dc4d4f4398e8c866c`.

The pull request was merged with a **true merge commit** carrying two parents,
`707161a1` and `e661fa9c`. **All thirty-six branch commits are preserved and
none was squashed away.** The merge introduced no change of its own: the tree at
`a7cca51` is identical to the tree at `e661fa9`.

The active design is `external-review/MILESTONE-084/scope-and-design.md`. The
external review package is under `external-review/MILESTONE-084/`.

All evidence in this record - including every PostgreSQL result - was executed in
a Linux container against a real PostgreSQL 16.13 server, not simulated. **CI
runs no PostgreSQL**, so a green CI run is not evidence that any database rule
holds; every database result here was obtained locally and is recorded as such.

## The Authority Is Not Stated In Prose

M084's authority is stated **once**, machine-readably, in
`external-review/MILESTONE-084/current-authority.json`, validated against the
committed closed schema `current-authority.schema.json`, and rendered
deterministically to `current-authority.md` by `tools/render_m084_authority.py`.
The renderer maps closed identifiers to fixed sentences and interprets no prose.
`--check` fails if the committed document is not the byte-exact rendering.

The schema uses `const`, closed `enum`, exact `minItems`/`maxItems` and
`additionalProperties: false` at every object boundary, so an unknown claim
identifier is **unrepresentable**, not merely discouraged. `authority_version`
is pinned with `const 1`: it was once pinned with `minimum`/`maximum`, which
this contract's validator does not implement - a decorative constraint, removed
as finding FIND-H1-01.

This freeze record is prose. Where this document and
`current-authority.json` could ever be read as differing, **the JSON governs.**

## A. What The Product Core Proves - Twelve Bounded Claims

1. `one_versioned_operator_configuration_governing_one_evaluation`
2. `one_evaluation_context_bound_to_exactly_one_persisted_m083_watermark`
3. `the_receipt_count_and_set_digest_read_from_the_loaded_watermark_not_from_the_caller`
4. `deterministic_single_reason_no_trade_or_one_proposal_from_one_input_set`
5. `quantity_price_and_risk_verdict_derived_by_the_engine_never_supplied_by_the_caller`
6. `one_fingerprint_binding_one_approval_to_one_exact_set_of_order_terms`
7. `order_terms_immutable_after_insert_with_status_the_only_mutable_column`
8. `a_closed_proposal_state_machine_in_which_only_prepared_has_outgoing_edges`
9. `at_most_one_explicit_human_decision_per_proposal`
10. `at_most_one_order_intent_per_proposal_derived_from_that_decision`
11. `every_stored_intent_is_not_submitted_and_no_transition_away_from_it_exists`
12. `no_module_of_the_package_imports_an_order_submission_dependency`

Nothing further.

## B. What It Does NOT Prove - Twelve Explicit Non-Claims

1. that an asserted quote, account or session matches what the market or broker
   showed;
2. that the M082 receipts behind the watermark describe anything historically
   true;
3. profitability, expected return or advice;
4. fillability, liquidity at the proposed price, or execution quality;
5. broker acceptance of the intent or of its terms;
6. that an approved intent was, will be, or can be sent to any venue;
7. paper or live trading readiness;
8. regulatory, tax or reporting compliance;
9. protection against DDL, trigger disable, TRUNCATE, DROP or superuser;
10. cryptographic sealing against an attacker with database write access;
11. any wall-clock chronology beyond the instants the caller supplied;
12. that a proposal absent from the table was never evaluated.

## C. M084 Cannot Send An Order, And That Is A Property Of What Exists

This is the claim the milestone is built around, and it is not a convention
anyone must remember. Four independent mechanisms, each re-proved by mutation
rather than asserted - weaken it and a named test fails:

- `SubmissionState` declares exactly **one** member, `NOT_SUBMITTED`. There is no
  other member to transition to.
- A database `CHECK` pins every stored intent's `submission_state` to that
  value, and an append-only trigger refuses the `UPDATE` that would change it.
- At most one intent exists per proposal, enforced by a unique constraint.
- A package-wide deny-list in `tools/check_architecture.py` refuses an
  order-submission import in **any** module, aimed at the real symbols - Alpaca's
  own client method is `submit_order`, read from their published source rather
  than guessed.

No credentials, no broker SDK, no endpoint, no paper order, no live order, no
FIX connectivity, no scheduled or unattended submission, and no approval by
default, by absence of rejection, or covering more than one exact proposal
version.

## D. What The Database Enforces, And What It Does Not

Enforced (`database_enforcement`, every value measured against a live server):

- `unleveraged_long_only_intraday_preparation_mode_configuration_only: true`
- `order_terms_immutable_after_insert: true`
- `closed_proposal_state_machine_on_update: true` - only `PREPARED` has outgoing
  edges.
- `decision_admitted_only_against_a_prepared_proposal_with_a_matching_fingerprint: true`
- `one_decision_per_proposal: true`
- `one_intent_per_proposal: true`
- `intent_terms_re_derived_from_the_proposal_and_decision_at_insert: true`
- `submission_state_restricted_to_not_submitted: true`
- `decisions_intents_and_risk_check_evidence_append_only: true`
- `evaluation_context_requires_an_existing_watermark_row: true`
- `ddl_authority_trigger_disable_truncate_drop_superuser: false` - stated as
  **false**, i.e. explicitly NOT enforced.

The last value is demonstrated rather than taken on trust: hostile attack A1-11
executes the `TRUNCATE` and shows it succeeding, instead of quoting the
disclaimer.

## E. Known Limitations - Recorded, Not Repaired Away

The seven `structural_limitations` stand as written:

- row-level refusals do not cover `TRUNCATE`, `DROP`, a disabled trigger or a
  superuser;
- market inputs are **operator-asserted** and are never verified against a
  venue;
- the fingerprint is a change detector, not a cryptographic seal;
- risk-check evidence is excluded from the fingerprint by design;
- a NO_TRADE is not persisted, so the tables do not record every evaluation;
- the engine reads no clock, and every instant it records was supplied to it;
- the liquidation-deadline check compares local times, not an exchange calendar.

**The frozen M083 reset is inexecutable at the M084 head.** M084's foreign key
makes M083's fixture `TRUNCATE` structurally illegal - PostgreSQL refuses to
truncate a table a foreign key references, whether or not the referencing table
holds a single row. This was measured, not assumed, and it was **not** repaired
by adding `CASCADE` to M083's frozen test: the two results are obtained
separately and neither stands in for the other.

- **Frozen M083 acceptance** - M083's unmodified suites, at M083's own revision,
  in their own git worktree and their own database: **51 passed**.
- **M084 compatibility** - twelve M084-owned tests covering M083's schema,
  triggers, rows and reset semantics at the M084 head and across M084's
  downgrade.

## F. The Frozen M083 Boundary, And The Breach That Produced The Guard

This branch once modified two M083-owned test files and justified it by
narrowing the frozen surface to "the authority contract and the documents". That
was wrong. It turns "M083 still passes" into "M083 passes a test M084 rewrote",
which is a different claim and not the one the freeze was for. Both files were
restored **byte-for-byte**, the coverage they provided was re-earned as M084's
own, and the limitation above was recorded instead of repaired.

`tools/check_frozen_paths.py` now makes the boundary mechanical rather than a
matter of the author's judgement: **27 governed paths**, each pinned to its git
blob id as of the base commit, with an **empty and empty-asserted** exemption
list. Ownership goes to the highest milestone a path names, so M084's own
writing about M083 is M084's. The guard holds in a shallow Windows CI checkout,
which took three CI failures to get right (FIND-CI-01, FIND-CI-02, FIND-CI-03).

## G. Validation Evidence

- **Mutation**: 27 of 27 families detected, each with a named detecting test,
  each restored byte-identically and re-verified. Four safety claims in §C are
  cross-referenced to the mutation that would break them.
- **Hostile review**: **183 executed attacks** across five formally separate
  passes, 0 findings. An attack is code that runs; a refusal counts only when
  its message names the rule that refused.
- **Concurrency**: 36 races, four repetitions, each on a rebuilt database with a
  distinct `pg_database.oid` recorded as proof.
- **Performance**: 0 to 25,000 rows, median/p95/max with sample counts, query
  plans and observed lock waits. Validation evidence only; it enters no claim.
- **Regression**: four modes, base and candidate, on equally fresh databases.
- **Operator walkthrough**: 18 steps against an **installed wheel**, including
  three distinct NO_TRADE demonstrations.
- **Exhaustion table**: 27 items, 27 `EXECUTED_PASS`, 0 `EXECUTED_FAIL_BLOCKER`,
  each status derived from its evidence rather than typed. It rendered ten
  blockers on its first run, for items whose record did not yet exist.
- **Suppressions**: 0 coverage pragmas and 0 skipped tests in the whole diff,
  counted by `tokenize` rather than by grep.

Coverage 79.41% against the floor of 79, which was not lowered.

## H. Findings - Every One Removed Or Bounded A Claim

Twelve findings, all closed. Two were the same defect twice: a risk check that
could never report `FAILED`, publishing a refusal the product cannot make
(`notional_limit`, `order_type_permitted`) - both removed, both invariants now
proved by execution. Two were in the test harnesses themselves: a mutation
campaign measuring stale bytecode, which can report a real detection as
SURVIVED, and lock instrumentation looking for a lock type that never occurs,
reporting "not blocked" for waits that demonstrably happened. One was an
untested safety binding: deleting the approval-to-proposal-version check changed
no test outcome. Three were CI/local divergences in the frozen-path guard.

The last is **FIND-S-01**, closed in the final correction `e661fa9`: the secret
scanner had been taught to clear `BASE`, `_BASE`, `FROZEN_COMMIT` and JSON
`"base"` carrying 40 hex characters **anywhere in the repository**. A constant's
name is evidence about its author's intent and none at all about its value, so
that would have cleared a real credential under those names. The rules are
removed; the five commit ids are written in eight-character groups so nothing
needs clearing; and the one remaining rule, for the frozen blob-id manifest,
checks the value against git's own index. FIND-CI-03 is marked **SUPERSEDED IN
PART** rather than withdrawn: its diagnosis about scan-batch composition stands.

Full list with resolutions in
`external-review/MILESTONE-084/validation-results.md`.

## I. Frozen Preservation

No M083 path appears in the M084 diff. `tools/check_frozen_paths.py` reports
27 governed paths unmodified since `707161a1`, verified by blob id and by
`git diff`, at the merged master head. M083's own suites pass unmodified at
M083's own revision.

## J. Claim Honesty

M084 makes no profitability claim, no fillability claim, no execution-quality
claim, no investment-advice claim and no paper- or live-trading-readiness claim.
The broker and market-data research conclusion is marked **CONDITIONAL**: its
decisive input is a search summary, because all three vendors' documentation
domains are blocked in this environment.
`external-review/MILESTONE-084/operator-verification-checklist.md` lists the
exact URLs and questions, and **no row of it has been completed**. No broker was
contacted, no account was opened, no credential was created, no terms were
accepted, and no paper or live order was submitted.

M084 consumes M083's watermark authority and neither replaces nor strengthens
it.

## K. Owner Approval

The Owner granted conditional approval to correct one known secret-scanner
finding, verify it, merge and freeze, in a single execution. The correction is
`e661fa9`, touching only the secret-scanner implementation and its tests,
M084-owned guards and tools, and M084's derived review artifacts - no M083 file,
no production module, no `PROJECT_CHECKPOINT.md` change.

**MILESTONE-084 is APPROVED_AND_FROZEN.**

## L. Next Permitted Action

`MILESTONE-085` - **recommendation only.** M085 and M086 are `NOT_STARTED`. No
M085 or M086 file, design or scope exists.

A future milestone may submit an intent to a paper account. It is not started,
and it **must add a submission-state transition in the open**, because none
exists: there is no member to transition to, the database refuses the update,
and the architecture gate refuses the import. That is the point of this freeze.
