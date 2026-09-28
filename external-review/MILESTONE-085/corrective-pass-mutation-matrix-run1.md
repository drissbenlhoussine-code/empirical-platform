> **SUPERSEDED — corrective-pass campaign run 1, BLOCKED (111 of 120).** Kept as recorded.
> Its nine blockers and their corrections are listed in [corrective-pass.md](corrective-pass.md);
> the current campaign is `mutation-matrix.md`.

# MILESTONE-085 — Mutation Matrix

**111 of 120 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `187492de6d1ae32f28a65b7ed0a9a879c3d7637a9b166c4c5c9ec7419bfe9132`, after `187492de6d1ae32f28a65b7ed0a9a879c3d7637a9b166c4c5c9ec7419bfe9132`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `broker_uncertainty_width` | The bound is as wide as the measured round trip | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_the_uncertainty_width_is_exactly_the_measured_round_trip` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `broker_clock_monotonicity` | A broker clock moving backwards refuses | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_a_broker_clock_that_moves_backwards_is_refused` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `broker_certainty_margin` | Time too uncertain to decide the freshness margin refuses | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_uncertainty_at_or_beyond_the_margin_is_refused[60.0]` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `authorization_basis_pairs_the_post_response_host_reading` | The basis pairs the broker timestamp with the host reading AFTER the response | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_broker_fetch_latency_cannot_extend_the_authorization_deadline` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `authorization_basis_interval_required` | An authorization without an interval-shaped basis is not dispatchable | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_replaced_pre_fetch_pairing_is_no_longer_trusted` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `broker_basis_required` | An authorization carrying a basis cannot be checked without broker time | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_basis_cannot_be_checked_without_broker_time` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `broker_basis_authorization_expiry` | An approval expires on the broker's clock, through its own basis | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_host_clock_ahead_only_while_authorizing_cannot_extend_the_authorization` | **EXECUTED_FAIL_BLOCKER** | the test failed, but not for the intended reason ('DID NOT RAISE' absent): m085_paper_execution_handlers.py:1208: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_a_host_clock_ahead_only_while_authorizing_cannot_extend_the_authorization
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.66s
 |
| `authorization_not_future_dated_against_its_basis` | authorized_at may not postdate the host reading its expiry is mapped with | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_future_dated_authorization_cannot_be_mapped` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `m084_deadline_on_proposal_time_basis` | M084 deadlines are enforced on the broker's clock through the proposal's own basis | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_intent_deadline_is_mapped_through_the_proposal_basis` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `m084_deadline_never_through_a_later_basis` | A deadline written at evaluation is never translated through the issuance basis | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_intent_deadline_is_mapped_through_the_proposal_basis` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `proposal_basis_required` | A proposal evaluated without its own basis cannot be issued for Paper | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `decision_basis_required` | An approval recorded without its own basis cannot be issued for Paper | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `proposal_basis_matches_the_exact_proposal` | Proposal evidence describing different deadlines is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_proposal_evidence_describing_another_proposal_refuses_the_preview` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `approval_before_proposal_expiry_on_broker_time` | An approval recorded after the proposal expired on the broker's clock is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_approval_recorded_after_the_proposal_expired_is_refused` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `approval_expiry_at_issuance_through_the_decision_basis` | An intent issued after the approval expired on the broker's clock is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_approval_that_expired_before_issuance_is_refused` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `stale_proposal_refused_at_issuance` | Issuance is refused when a deadline it relies on passed on the broker's clock | `src/empirical_platform/usecases/paper_execution.py` | `test_the_chain_is_refused_somewhere_and_nothing_is_sent` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `approval_refused_for_a_proposal_expired_on_broker_time` | A human cannot approve a proposal that may have expired on the broker's clock | `src/empirical_platform/usecases/paper_execution.py` | `test_a_proposal_that_expired_on_the_broker_clock_cannot_be_approved` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `evaluation_uses_the_measured_host_reading` | The proposal is evaluated at the basis host reading, not at an unmeasured instant | `src/empirical_platform/usecases/paper_execution.py` | `test_the_proposal_is_evaluated_at_the_host_reading_taken_after_the_clock_response` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `decision_uses_the_measured_host_reading` | The approval is decided at the basis host reading, not at an unmeasured instant | `src/empirical_platform/usecases/paper_execution.py` | `test_an_approval_is_decided_at_the_host_reading_taken_after_the_clock_response` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `intent_basis_required` | An intent issued without its own basis is not dispatchable | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_intent_without_its_own_basis_is_refused_before_any_broker_call` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `intent_basis_matches_the_exact_intent` | Evidence describing a different intent is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_evidence_describing_a_different_intent_is_refused[expires_at]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `intent_basis_bound_to_issuance` | An intent-time basis cannot be attached after the intent was issued | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_intent_evidence_cannot_be_attached_after_issuance` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `issuance_uses_the_measured_host_reading` | The intent is issued at the basis host reading, not at an unmeasured instant | `src/empirical_platform/usecases/paper_execution.py` | `test_the_intent_is_issued_at_the_host_reading_taken_after_the_clock_response` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `wall_clock_rollback` | Backward wall clock refuses | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_rollback_refuses[utc]` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `post_fetch_time` | Post-fetch evaluation uses current time | `src/empirical_platform/usecases/paper_execution.py` | `test_an_intent_expiring_during_the_fetch_is_refused` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `final_authorization_expiry` | Authorization is still valid at HTTP send | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[authorization-connect]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `final_intent_expiry` | Intent expiry is checked after preparation | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[intent-prepare]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `final_session_close` | Market close is checked after preparation | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[session-prepare]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `final_quote_freshness` | Quote remains fresh after connection | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[quote-connect]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `monotonic_elapsed` | Elapsed work ages a stalled wall clock | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_stalled_wall_clock_does_not_stop_expiry` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `http_final_guard` | Guard runs after connect before HTTP send | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_final_guard_runs_after_connect_and_before_http_request[False]` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `claim_time_after_lock` | A row-lock wait ages the permission: time is re-read after the lock | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_real_row_lock_wait_cannot_consume_expired_permission` | **EXECUTED_PASS** | detected; restored to `0bb79acbe940f471` |
| `paper_hostname_pin` | Only paper-api.alpaca.markets may receive an order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_endpoint_host_claim_matches_the_pinned_constant` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `https_requirement` | Only https may carry a credential | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_non_paper_endpoint_is_refused[http://paper-api.alpaca.markets]` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `redirect_refusal` | A redirect is refused, never followed | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `TestRedirectsAreRefusedNotFollowed` | **EXECUTED_FAIL_BLOCKER** | the test failed, but not for the intended reason ('DID NOT RAISE' absent): ts\integration\test_m085_hostile_http.py:330: AssertionError
=========================== short test summary info ===========================
FAILED tests/integration/test_m085_hostile_http.py::TestRedirectsAreRefusedNotFollowed::test_every_redirect_is_refused[https://api.alpaca.markets/v2/orders-301]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 1.02s
 |
| `live_host_rejection` | An alternative host is refused even if it is a real Alpaca host | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_non_paper_endpoint_is_refused[https://api.alpaca.markets]` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `userinfo_rejection` | A URL carrying userinfo is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_userinfo_is_refused_by_the_userinfo_rule_specifically` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `non_canonical_port_rejection` | A port outside the canonical HTTPS boundary is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_non_paper_endpoint_is_refused[https://paper-api.alpaca.markets:8443]` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `human_authorization_requirement` | A preview carrying refusals cannot be authorized | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_refused_preview_cannot_be_authorized` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `account_binding` | An authorization does not permit a dispatch to another account | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation1-different paper account]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `fingerprint_binding` | An authorization does not permit a changed order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation0-order changed after it was authorized]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `approval_expiry` | An expired authorization permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation2-has expired]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `single_use_authorization` | A consumed authorization permits nothing further | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_consumed_authorization_permits_nothing_further` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `deterministic_client_order_id` | The order identity is derived, not generated | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_it_is_a_pure_function_of_persisted_identity` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `client_order_id_account_binding` | A different account yields a different order identity | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_different_account_yields_a_different_order_identity` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `unknown_outcome_state` | An ambiguous dispatch can be resolved but never retried | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unknown_outcome_can_be_resolved_but_never_retried` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `terminal_states_are_terminal` | Nothing leaves a terminal state | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_terminal_state_has_no_outgoing_edge` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `long_only_rule` | A sell cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override0-long-only]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `whole_share_rule` | A fractional quantity cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_fractional_quantity_is_not_even_representable` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `extended_hours_refusal` | Extended hours cannot be enabled | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override7-extended-hours]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `day_only_rule` | A time in force other than DAY cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override5-DAY]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `kill_switch` | An engaged execution kill switch refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override0-kill switch]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `quote_freshness` | A stale quote refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override13-older than the]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `quote_future_timestamp` | A quote after post-fetch evaluation time refuses authorization | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override14-dated after the latest possible]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `buying_power_check` | A cost ceiling above paper buying power refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override11-exceeds paper buying power]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `notional_ceiling` | A cost ceiling above the configured limit refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override10-exceeds the limit]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `exposure_limit` | An existing position refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override9-position of 5 already exists]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `asset_tradability` | An untradable asset refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override6-not tradable]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `watchlist` | A symbol off the approved watchlist refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override5-not on the approved watchlist]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `account_dispatchability` | A blocked paper account refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override1-does not permit orders]` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `response_identity_validation` | An acknowledgement about another order is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_mismatched_acknowledgement_fails_closed[override0-client_order_id]` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `response_quantity_validation` | An acknowledgement for a different quantity is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_mismatched_acknowledgement_fails_closed[override3-quantity]` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `credential_redaction` | A credential echoed by a peer is scrubbed before storage | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_peer_echoing_our_secret_has_it_scrubbed_before_storage` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `maximum_diagnostic_body_size` | A stored broker response body is bounded | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_an_oversized_body_is_bounded_before_it_is_stored` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `broker_status_map_closure` | An unmapped broker status does not become a known one | `src/empirical_platform/usecases/paper_execution.py` | `test_the_broker_status_map_is_exactly_this_closed_set` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `authority_enum_closure` | A claim the schema does not name cannot enter the contract | `external-review/MILESTONE-085/current-authority.schema.json` | `test_every_list_length_is_exact` | **EXECUTED_PASS** | detected; restored to `99b3925b8288e605` |
| `authority_version_const` | The authority version is frozen at 1 | `external-review/MILESTONE-085/current-authority.schema.json` | `test_the_authority_version_is_pinned_to_one` | **EXECUTED_PASS** | detected; restored to `99b3925b8288e605` |
| `deterministic_markdown_check` | The document is the deterministic rendering of the contract | `external-review/MILESTONE-085/current-authority.json` | `test_the_markdown_is_byte_identical_to_the_rendering` | **EXECUTED_PASS** | detected; restored to `806da25586641b63` |
| `database_transition_trigger` | The database refuses an illegal execution transition | `migrations/versions/b1e9d47c30a5_create_m085_paper_execution_schema.py` | `test_the_database_table_matches_the_domain_table_exactly` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |
| `database_single_use_trigger` | The database refuses a second consumption | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_a_second_consumption_is_refused_by_the_trigger` | **EXECUTED_FAIL_BLOCKER** | the test failed, but not for the intended reason ('DID NOT RAISE' absent): rective pass: send-time policy binding and immutable terminal attempts.
=========================== short test summary info ===========================
FAILED tests/integration/test_m085_paper_execution_postgres.py::TestTheDatabaseEnforcesSingleUse::test_a_second_consumption_is_refused_by_the_trigger
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 3.13s
 |
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
| `authority_contract_reads_the_sql_installed_at_head` | An enforcement claim is checked against the guard installed at head | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_every_database_enforcement_claim_names_sql_installed_at_head` | **EXECUTED_PASS** | detected; restored to `849cf3b38f8048f0` |
| `dispatch_claim_lease` | The claim is conditional, so two workers cannot both win | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_exactly_one_wins_and_the_loser_receives_the_winner[repetition-1]` | **EXECUTED_PASS** | detected; restored to `0bb79acbe940f471` |
| `policy_derived_from_the_configuration` | The quote age limit is the stored configuration's, not a constant or argument | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_send_time_limit_is_the_configurations` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `policy_fingerprint_covers_every_limit` | Changing the quote age limit changes the policy fingerprint | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_limit_is_part_of_the_policy_fingerprint` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `final_guard_policy_fingerprint` | A re-derived policy other than the authorized one refuses the send | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_loosened_configuration_cannot_satisfy_an_authorization` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `spread_limit` | A spread above the configured limit refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_exactly_the_limit_is_permitted_and_one_hundredth_more_is_not` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `entry_window` | A broker instant that may be outside the entry window refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `TestTheEntryWindowIsJudgedOnTheBrokerClock` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `authorization_binds_every_field` | An authorization whose quote ask is not the preview's permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_tampering_with_any_bound_field_is_named` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `authorization_never_outlives_the_intent` | A stored authorization expiring after its intent permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_stored_authorization_outliving_its_intent_is_refused` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `authorization_after_preview_freshness` | A preview older than the configured freshness limit cannot be authorized | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_preview_older_than_the_freshness_limit_cannot_be_authorized` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `dispatch_checks_the_binding` | The submit handler refuses a stored authorization that does not describe its preview | `src/empirical_platform/usecases/paper_execution.py` | `test_a_tampered_stored_authorization_refuses[quote_captured_at-value1]` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `final_guard_reads_the_kill_switch_again` | The kill switch is re-read after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_kill_switch_engaged_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `final_guard_reads_the_configuration_again` | The configuration is re-loaded and re-derived after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_configuration_changed_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `final_guard_reads_the_market_session_again` | The session is judged from the clock fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_market_that_closes_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `final_guard_reads_the_quote_again` | The quote is judged as fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_quote_that_goes_stale_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `liquidation_deadline_never_later_than_the_calendar` | Host skew can shorten the liquidation deadline but never extend it | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_slow_host_at_evaluation_does_not_move_the_deadline_later` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `liquidation_deadline_at_dispatch` | A dispatch at 15:50 after a slow-host evaluation never submits | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_slow_host_at_evaluation_cannot_extend_the_liquidation_deadline` | **EXECUTED_FAIL_BLOCKER** | the test failed, but not for the intended reason ('assert' absent): est_m085_corrective_pass_handlers.py:503: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_corrective_pass_handlers.py::TestTheLiquidationDeadlineAtDispatch::test_a_slow_host_at_evaluation_cannot_extend_the_liquidation_deadline
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.67s
 |
| `liquidation_deadline_for_another_date` | A liquidation deadline written for another date cannot be evaluated, so it refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_deadline_written_for_another_date_cannot_be_evaluated` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `definitive_refusal_statuses` | Only 400, 401, 403 and 422 can prove an order was refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `definitive_refusal_requires_the_brokers_document` | A definitive status proves nothing without the broker's JSON error object | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_PASS** | detected; restored to `36101e37ff531f4b` |
| `adapter_uncertain_status_is_ambiguous` | The adapter reports a non-definitive order answer as ambiguous, not as a refusal | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_an_uncertain_status_is_never_reported_as_a_refusal` | **EXECUTED_PASS** | detected; restored to `bfc889600f0906e0` |
| `dispatch_uncertain_status_is_unknown` | The handler records a non-definitive answer as SUBMISSION_UNKNOWN, not REJECTED | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[fake-500-without-view]` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `dispatch_ambiguous_is_unknown` | A possibly delivered request is SUBMISSION_UNKNOWN, never terminal | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[timeout-after-send]` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `dispatch_unexpected_fault_is_unknown` | A fault after the send guard passed is recorded as SUBMISSION_UNKNOWN | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[unexpected-fault-after-send]` | **EXECUTED_PASS** | detected; restored to `d3305e598388fa83` |
| `reconcile_a_stale_in_progress_attempt` | An attempt left IN_PROGRESS is reconciled to the broker's answer | `src/empirical_platform/usecases/paper_execution.py` | `test_a_stale_in_progress_attempt_is_reconciled_to_the_brokers_answer` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |
| `reconcile_leaves_a_live_dispatch_alone` | An attempt IN_PROGRESS for less than the not-found window is not looked up | `src/empirical_platform/usecases/paper_execution.py` | `test_a_live_dispatch_is_left_to_finish` | **EXECUTED_FAIL_BLOCKER** | the test failed, but not for the intended reason ('lookups' absent): N_IN_PROGRESS

tests\unit\test_m085_corrective_pass_handlers.py:433: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_corrective_pass_handlers.py::TestAnInterruptedDispatchCanBeReconciled::test_a_live_dispatch_is_left_to_finish
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.66s
 |
| `repository_refuses_a_terminal_transition` | The repository refuses any transition of a terminal attempt, legibly | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_the_repository_refuses_before_the_database_is_asked` | **EXECUTED_PASS** | detected; restored to `0bb79acbe940f471` |
| `database_terminal_attempt_immutable` | The database refuses every UPDATE of a terminal attempt, same-state included | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_no_update_of_a_filled_attempt_is_accepted[identical-same-state]` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_broker_identity_written_once` | The database refuses rewriting a recorded broker order id or instant | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_a_live_attempt_cannot_rewrite_what_was_already_recorded[broker_order_id]` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_authorization_equals_its_preview` | The database refuses an authorization whose quote ask is not the preview's | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_any_field_other_than_the_previews_is_refused` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_authorization_inserted_unconsumed` | The database refuses an authorization inserted already consumed | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_an_authorization_inserted_already_consumed_is_refused` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_authorization_never_outlives_the_intent` | The database refuses an authorization expiring after its intent | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_an_authorization_outliving_its_intent_is_refused_to_the_tick` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_authorization_within_preview_freshness` | The database refuses an authorization granted after the preview's freshness limit | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_an_authorization_after_the_previews_freshness_limit_is_refused` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_refused_preview_not_authorizable` | The database refuses authorizing a preview that carries refusals | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_a_preview_with_refusals_cannot_be_authorized` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_preview_carries_the_configuration_policy` | The database refuses a preview whose quote age limit is not the configuration's | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_a_looser_or_different_policy_is_refused` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_preview_carries_the_intent_order` | The database refuses a preview whose limit price is not the intent's | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_an_order_other_than_the_intents_is_refused` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_authorizable_preview_within_its_cap` | The database CHECK refuses an authorizable preview priced above its cap | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_an_authorizable_preview_above_its_cap_is_refused_by_check` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `schema_head_exact` | Any revision set other than exactly the M085 head refuses | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_any_other_revision_refuses_before_the_body_runs` | **EXECUTED_FAIL_BLOCKER** | the test failed, but not for the intended reason ('DID NOT RAISE' absent): inst a mismatched schema

tests\unit\test_m085_paper_composition.py:424: Failed
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_paper_composition.py::TestTheSchemaHeadIsExact::test_any_other_revision_refuses_before_the_body_runs[no-revision]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 1.01s
 |
| `schema_head_checked_by_the_composition` | The paper runtime checks the schema head before handing anything out | `src/empirical_platform/entrypoints/_paper_composition.py` | `test_any_other_revision_refuses_before_the_body_runs` | **EXECUTED_FAIL_BLOCKER** | the test failed, but not for the intended reason ('DID NOT RAISE' absent): inst a mismatched schema

tests\unit\test_m085_paper_composition.py:424: Failed
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_paper_composition.py::TestTheSchemaHeadIsExact::test_any_other_revision_refuses_before_the_body_runs[no-revision]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.97s
 |
| `legacy_dry_run_refused` | --dry-run refuses before any runtime, writer, socket or file is touched | `tools/m085_paper_acceptance.py` | `test_dry_run_is_refused_before_any_record_connection_or_file` | **EXECUTED_PASS** | detected; restored to `ae4c0946d89f190d` |

## Blockers

- `broker_basis_authorization_expiry`: the test failed, but not for the intended reason ('DID NOT RAISE' absent): m085_paper_execution_handlers.py:1208: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_paper_execution_handlers.py::TestSubmitAuthorizedPaperOrder::test_a_host_clock_ahead_only_while_authorizing_cannot_extend_the_authorization
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.66s

- `redirect_refusal`: the test failed, but not for the intended reason ('DID NOT RAISE' absent): ts\integration\test_m085_hostile_http.py:330: AssertionError
=========================== short test summary info ===========================
FAILED tests/integration/test_m085_hostile_http.py::TestRedirectsAreRefusedNotFollowed::test_every_redirect_is_refused[https://api.alpaca.markets/v2/orders-301]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 1.02s

- `database_transition_trigger`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.
- `database_single_use_trigger`: the test failed, but not for the intended reason ('DID NOT RAISE' absent): rective pass: send-time policy binding and immutable terminal attempts.
=========================== short test summary info ===========================
FAILED tests/integration/test_m085_paper_execution_postgres.py::TestTheDatabaseEnforcesSingleUse::test_a_second_consumption_is_refused_by_the_trigger
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 3.13s

- `liquidation_deadline_at_dispatch`: the test failed, but not for the intended reason ('assert' absent): est_m085_corrective_pass_handlers.py:503: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_corrective_pass_handlers.py::TestTheLiquidationDeadlineAtDispatch::test_a_slow_host_at_evaluation_cannot_extend_the_liquidation_deadline
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.67s

- `reconcile_a_stale_in_progress_attempt`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.
- `reconcile_leaves_a_live_dispatch_alone`: the test failed, but not for the intended reason ('lookups' absent): N_IN_PROGRESS

tests\unit\test_m085_corrective_pass_handlers.py:433: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_corrective_pass_handlers.py::TestAnInterruptedDispatchCanBeReconciled::test_a_live_dispatch_is_left_to_finish
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.66s

- `schema_head_exact`: the test failed, but not for the intended reason ('DID NOT RAISE' absent): inst a mismatched schema

tests\unit\test_m085_paper_composition.py:424: Failed
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_paper_composition.py::TestTheSchemaHeadIsExact::test_any_other_revision_refuses_before_the_body_runs[no-revision]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 1.01s

- `schema_head_checked_by_the_composition`: the test failed, but not for the intended reason ('DID NOT RAISE' absent): inst a mismatched schema

tests\unit\test_m085_paper_composition.py:424: Failed
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_paper_composition.py::TestTheSchemaHeadIsExact::test_any_other_revision_refuses_before_the_body_runs[no-revision]
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.97s


