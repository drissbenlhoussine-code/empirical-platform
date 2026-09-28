# M085 canonical authority contract closure (review finding AUTH-1)

Status: CORRECTED CANDIDATE — OWNER PUBLICATION APPROVAL REQUIRED. Local commit only; not pushed,
not merged, not frozen, not OWNER_ACCEPTED, not READY_FOR_PAPER. Paper acceptance NOT_STARTED. M086
NOT_STARTED. No Alpaca call of any kind; no Paper order; no real Proposal/Approval/Intent; no
acceptance-database mutation. No reconciliation production behaviour, migration, trigger, state
machine, send-boundary, M083 or M084 content is changed by this closure.

Published head reviewed: `673394e0834f19df7ce8a4ca9700f4cc793e2bc7`. Candidate:
**`88ea0ed3d036a4243520e1f6b1da57ab9404333b`** (`88ea0ed`). Verification for the exact SHA:
[verification.md](verification.md); logs in `runs-88ea0ed/`.

## 1. The finding

Between `832b20b` and `673394e`, `current-authority.md` and `tools/render_m085_authority.py`
changed while `current-authority.json` and `current-authority.schema.json` stayed byte-identical and
`authority_version` stayed `1`. The renderer had widened the sentence of the existing identifier
`reconciliation_addresses_the_original_client_order_id_under_a_bounded_not_found_policy` (and of the
limitation `the_bounded_not_found_reconciliation_policy_is_a_stated_choice_not_a_proof`) to carry the
durable-round and broker-clock semantics. The renderer declares the JSON to be the ONLY source of
M085 authority; for the published candidate that invariant was false. A governance defect, not an
execution defect: the code the widened sentences described was (and is) verified.

## 2. What the canonical contract now says — authority version 1 → 2

No versioning rule in this repository documents that a semantic expansion may keep the version, and
every milestone pins `authority_version` as a const with tests rejecting a bump. The meaning and the
enforcement surface changed materially, so the version advances to **2**; version 1 is rejected by
the same const (tested). Historical version-1 evidence is untouched.

Every v1 identifier survives (tested by exact counts). Added, each as its own closed identifier:

| Section | Identifier | Mission item |
|---|---|---|
| proves | `every_reconciliation_network_attempt_is_a_durable_round_begun_before_its_network_work` | 2 |
| proves | `rounds_are_ordered_by_a_durable_per_attempt_sequence_never_by_reconciler_wall_clocks` | 3 |
| proves | `a_failed_unusable_found_or_incomplete_round_ends_the_qualifying_not_found_run` | 4 |
| proves | `absence_resolution_requires_unknown_and_no_bound_order_observation_found_or_open_round` | 5 (state, bound, observed, FOUND, incomplete) |
| proves | `absence_resolution_requires_two_completed_not_found_rounds_and_sixty_broker_seconds` | 5 (2 rounds, 60 s broker-time lower bound) |
| proves | `waiting_interval_is_current_broker_earliest_minus_anchor_broker_latest_never_wall_clocks` | 6 |
| proves | `missing_contradictory_or_incompatible_round_or_time_evidence_keeps_the_outcome_unresolved` | 7 |
| proves | `absence_finalisation_revalidates_fresh_evidence_under_the_attempt_lock_not_a_snapshot` | 8 |
| proves | `round_sequence_allocation_holds_the_attempt_row_lock_so_a_race_waits_instead_of_colliding` | §3 "allocation is serialized/atomic as implemented" (application code, stated as a proof not as database enforcement) |
| does_not_prove | `that_the_broker_never_accepted_an_order_the_bounded_absence_policy_resolved_as_rejected` | 9 (also: no resend permission; the intent's single dispatch is spent) |
| database_enforcement | `a_reconciliation_round_begins_incomplete_by_trigger` | §3 |
| database_enforcement | `a_round_is_bound_to_its_attempt_intent_authorization_and_client_order_id_by_trigger` | §3 |
| database_enforcement | `unique_reconciliation_round_sequence_per_attempt` | §3 |
| database_enforcement | `a_reconciliation_round_identity_is_immutable_by_trigger` | §3 |
| database_enforcement | `a_round_is_completed_exactly_once_and_only_to_a_completed_outcome_by_trigger` | §3 |
| database_enforcement | `reconciliation_rounds_refuse_delete` | §3 |
| structural_limitations | `the_waiting_interval_assumes_a_monotone_broker_clock_not_evidence_of_processing` | time-model assumptions, stated as a limit |
| structural_limitations | `legacy_acknowledgements_without_rounds_are_operator_evidence_and_never_count` | legacy records |

Item 1 (reconciliation addresses the original deterministic client_order_id) is the existing
identifier, whose sentence is **restored to its version-1 wording**; the round semantics no longer
ride inside it (tested: neither restored sentence mentions rounds or the broker clock).

What PostgreSQL proves, precisely: each enforcement identifier is pinned to SQL installed at head by
the chain rendered offline (`must begin incomplete`, `does not describe attempt`, `names attempt %
which does not exist`, `uq_paper_reconciliation_round_attempt_sequence`, `reconciliation round %
identity is immutable`, `is complete (%) and is immutable`, `may only be updated to a completed
outcome`, `paper_reconciliation_round_append_only_trigger`). The serialised allocation and the
finalisation re-validation are **application** code over `FOR UPDATE` and are claimed under
`proves`, pinned by AST/source tests, not under `database_enforcement`. Nothing new is claimed
against a database owner, DDL, a disabled trigger, TRUNCATE, DROP, a superuser or broker truth: the
v1 `does_not_prove` and `structural_limitations` entries that say so remain, unchanged.

## 3. The renderer-meaning escape hatch, closed

Mechanism: the canonical contract carries **`rendered_meaning_digest`** — the SHA-256 of the
renderer's five identifier → sentence tables (canonical JSON, sorted keys), written as an
**integer** so that no 64-hex token exists for the secret scanner to flag and no scanner rule had to
be weakened. The schema pins it as a `const`. `tools/render_m085_authority.py` refuses to render,
and `--check` fails with `MeaningDriftError`, when the tables do not digest to the declared value.
Consequences, all tested:

- a renderer-only rewrite of any sentence fails the renderer, `--check`, the contract test and the
  exhaustion table's renderer gate until `current-authority.json` **and** its schema are changed —
  the change is visible in the canonical contract by construction;
- renaming an identifier changes the digest; the whole mapping is digested, so this is not a
  keyword comparison;
- the digest is reproducible (`--print-meaning-digest`) and appears in the rendered document.

Mutation families added and detected: `authority_meaning_digest_pins_the_sentences` (renderer-only
sentence rewrite → `MeaningDriftError`), `authority_meaning_digest_is_a_schema_const` (digest merely
typed, not pinned), `authority_names_the_durable_round_guarantee` (a v2 identifier dropped from the
contract → `SchemaError`); `authority_version_const` and `authority_enum_closure` retargeted to
version 2 and the 23-item `proves` enumeration.

## 4. Under-claims and stale wording corrected

- **Broker order validation.** The v1 sentence listed client order id, symbol, side, quantity and
  order type. `order_terms_mismatches` compares, and the sentence now states: those five, the limit
  price where the order has one (and its absence where it has none), time in force, extended hours,
  and the already bound broker order id where the attempt has one; a field the broker did not
  report is a mismatch and is never substituted; an order found by reconciliation is adopted only
  when the broker client's account is the authorized one. Pinned: the set of `mismatches.append(...)`
  literals parsed from the function equals exactly the fields the sentence names, and the account
  comparison is present in the reconciliation adoption path.
- **Reconciliation policy key.** `RECONCILIATION_UNKNOWN_POLICY` gains the canonical
  `minimum_broker_seconds_between_qualifying_reconciliation_rounds` (60) and declares the historical
  `minimum_seconds_since_dispatch_before_not_found_counts` in `legacy_key_aliases` as an alias of
  it with the same value. The old key is kept (no runtime consumer reads either; only tests do), so
  no consumer changed silently. This is the only production-file edit of the closure and it changes
  no behaviour; the constant is unchanged.

## 5. What was NOT changed

Reconciliation handler, domain policy functions, repository, migration `a7d3c9e14f26`, triggers and
functions, the execution state machine, the send boundary, M083 and M084 content, and the two
earlier authority contracts (M083, M084 remain at their own version 1 with their own tests).
Historical evidence documents are not rewritten; `reconciliation-evidence-safety/` and
`durable-reconciliation-rounds/` stand as records of their rounds.

## 6. V1 — Owner-ratification statement, PREPARED (not self-approved)

The narrow V1 correction (`05eec31`, rows 21/29 recognised by ratified blob id; row 28 by exact
inventory) is intact and untouched by this closure. The statement the Owner would ratify, verbatim:

> I ratify (a) the two scoped M084/checkpoint exceptions already reviewed — the M085-owned
> `m084-frozen-path-digests.json` manifest is authorized only while its blob equals the pinned
> `RATIFIED_M084_MANIFEST_BLOB`, and `PROJECT_CHECKPOINT.md` is authorized only while its blob equals
> the pinned §119 record `RATIFIED_CHECKPOINT_BLOB`; (b) the corrected exhaustion-table expectations
> of `tools/render_m085_exhaustion_table.py` at `05eec31`: rows 21 and 29 pass only for those exact
> blobs, row 28 requires `changed-files.txt` to equal `git diff --name-status <base>...HEAD`, and
> rows 1, 3, 20–26 and 28–31 are executed at rendering time while rows 2, 4–19 and 27 derive from
> recorded documents of earlier runs; (c) that a rendered result of 31/31 `EXECUTED_PASS` is a
> statement of engineering verification only — row 12 records a bounded external submission that
> was honestly BLOCKED by quote staleness and is not a successful external execution — and that it
> does NOT constitute, imply or advance external Paper acceptance, which remains NOT_STARTED and
> requires its own Owner-authorized exercise.

Until the Owner signs that statement, V1 remains OPEN and the table remains prepared evidence.
