# MILESTONE-085 — Mutation Matrix

**20 of 20 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `cd7162aba6cdcc2e066f7a15c68b9fc3077164893c24b3289d821e8a56185108`, after `cd7162aba6cdcc2e066f7a15c68b9fc3077164893c24b3289d821e8a56185108`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `response_identity_validation` | An acknowledgement about another order is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_mismatched_acknowledgement_fails_closed[override0-client_order_id]` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `response_quantity_validation` | An acknowledgement for a different quantity is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_mismatched_acknowledgement_fails_closed[override3-quantity]` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `credential_redaction` | A credential echoed by a peer is scrubbed before storage | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_peer_echoing_our_secret_has_it_scrubbed_before_storage` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `maximum_diagnostic_body_size` | A stored broker response body is bounded | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_an_oversized_body_is_bounded_before_it_is_stored` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `broker_status_map_closure` | An unmapped broker status does not become a known one | `src/empirical_platform/usecases/paper_execution.py` | `test_the_broker_status_map_is_exactly_this_closed_set` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `authority_enum_closure` | A claim the schema does not name cannot enter the contract | `external-review/MILESTONE-085/current-authority.schema.json` | `test_every_list_length_is_exact` | **EXECUTED_PASS** | detected; restored to `99b3925b8288e605` |
| `authority_version_const` | The authority version is frozen at 1 | `external-review/MILESTONE-085/current-authority.schema.json` | `test_the_authority_version_is_pinned_to_one` | **EXECUTED_PASS** | detected; restored to `99b3925b8288e605` |
| `deterministic_markdown_check` | The document is the deterministic rendering of the contract | `external-review/MILESTONE-085/current-authority.json` | `test_the_markdown_is_byte_identical_to_the_rendering` | **EXECUTED_PASS** | detected; restored to `806da25586641b63` |
| `database_transition_trigger` | The database refuses an illegal execution transition | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_the_database_table_matches_the_domain_table_exactly` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_single_use_trigger` | The database refuses a second consumption | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_a_second_consumption_is_refused_by_the_trigger` | **EXECUTED_PASS** | detected; restored to `849cf3b38f8048f0` |
| `database_attempt_insert_guard` | The database refuses an attempt without a consumed authorization | `migrations/versions/b1e9d47c30a5_create_m085_paper_execution_schema.py` | `test_an_attempt_without_a_consumed_authorization_is_refused` | **EXECUTED_PASS** | detected; restored to `fb7762aa8cf07742` |
| `m084_intent_boundary` | A paper row naming an unknown intent is refused | `migrations/versions/b1e9d47c30a5_create_m085_paper_execution_schema.py` | `test_a_paper_row_naming_an_unknown_intent_is_still_refused` | **EXECUTED_PASS** | detected; restored to `fb7762aa8cf07742` |
| `database_basis_interval_shape` | The database refuses an authorization dated after its basis host reading | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_a_malformed_basis_is_refused[authorized-after-the-basis-reading]` | **EXECUTED_PASS** | detected; restored to `849cf3b38f8048f0` |
| `database_basis_immutable` | The consuming UPDATE cannot rewrite the authorization basis | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_the_basis_cannot_be_rewritten_by_the_consuming_update[basis_broker_earliest_at]` | **EXECUTED_PASS** | detected; restored to `849cf3b38f8048f0` |
| `database_intent_basis_matches_intent` | The database refuses evidence that does not describe the exact stored intent | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_evidence_describing_another_intent_is_refused[expires_at]` | **EXECUTED_PASS** | detected; restored to `849cf3b38f8048f0` |
| `database_intent_basis_bound_to_issuance` | The database refuses evidence whose host reading is not the issuance instant | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_evidence_not_bound_to_the_issuance_instant_is_refused` | **EXECUTED_PASS** | detected; restored to `849cf3b38f8048f0` |
| `database_proposal_basis_matches_proposal` | The database refuses proposal evidence that does not describe the stored proposal | `migrations/versions/e61b3f9a4c27_add_m085_proposal_and_decision_time_basis.py` | `test_proposal_evidence_describing_another_proposal_is_refused[expires_at]` | **EXECUTED_PASS** | detected; restored to `7c75a894b28011ac` |
| `database_decision_basis_matches_approval` | The database refuses decision evidence that does not describe the stored approval | `migrations/versions/e61b3f9a4c27_add_m085_proposal_and_decision_time_basis.py` | `test_decision_evidence_describing_another_approval_is_refused[decision_expires_at]` | **EXECUTED_PASS** | detected; restored to `7c75a894b28011ac` |
| `database_proposal_basis_bound_to_evaluation` | The database refuses proposal evidence whose host reading is not the evaluation | `migrations/versions/e61b3f9a4c27_add_m085_proposal_and_decision_time_basis.py` | `test_proposal_evidence_not_bound_to_the_evaluation_instant_is_refused` | **EXECUTED_PASS** | detected; restored to `7c75a894b28011ac` |
| `database_decision_basis_bound_to_decision` | The database refuses decision evidence whose host reading is not the decision | `migrations/versions/e61b3f9a4c27_add_m085_proposal_and_decision_time_basis.py` | `test_decision_evidence_not_bound_to_the_decision_instant_is_refused` | **EXECUTED_PASS** | detected; restored to `7c75a894b28011ac` |

