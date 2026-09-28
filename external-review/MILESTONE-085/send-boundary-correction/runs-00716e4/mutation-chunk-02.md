# MILESTONE-085 — Mutation Matrix

**22 of 22 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `b484179c2fb15454b7115b07dd79d3a3f522bef110634fcbe3b723ec86da973e`, after `b484179c2fb15454b7115b07dd79d3a3f522bef110634fcbe3b723ec86da973e`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `kill_switch` | An engaged execution kill switch refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override0-kill switch]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `quote_freshness` | A stale quote refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override13-older than the]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `quote_future_timestamp` | A quote after post-fetch evaluation time refuses authorization | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override14-dated after the latest possible]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `buying_power_check` | A cost ceiling above paper buying power refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override11-exceeds paper buying power]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `notional_ceiling` | A cost ceiling above the configured limit refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override10-exceeds the limit]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `exposure_limit` | An existing position refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override9-position of 5 already exists]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `asset_tradability` | An untradable asset refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override6-not tradable]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `watchlist` | A symbol off the approved watchlist refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override5-not on the approved watchlist]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `account_dispatchability` | A blocked paper account refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override1-does not permit orders]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `response_identity_validation` | An acknowledgement about another order is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_mismatched_acknowledgement_fails_closed[override0-client_order_id]` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `response_quantity_validation` | An acknowledgement for a different quantity is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_acknowledgement_fails_closed[override3-quantity]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `credential_redaction` | A credential echoed by a peer is scrubbed before storage | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_peer_echoing_our_secret_has_it_scrubbed_before_storage` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `maximum_diagnostic_body_size` | A stored broker response body is bounded | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_an_oversized_body_is_bounded_before_it_is_stored` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `broker_status_map_closure` | An unmapped broker status does not become a known one | `src/empirical_platform/usecases/paper_execution.py` | `test_the_broker_status_map_is_exactly_this_closed_set` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `policy_derived_from_the_configuration` | The quote age limit is the stored configuration's, not a constant or argument | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_send_time_limit_is_the_configurations` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `policy_fingerprint_covers_every_limit` | Changing the quote age limit changes the policy fingerprint | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_limit_is_part_of_the_policy_fingerprint` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `final_guard_policy_fingerprint` | A re-derived policy other than the authorized one refuses the send | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_loosened_configuration_cannot_satisfy_an_authorization` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `spread_limit` | A spread above the configured limit refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_exactly_the_limit_is_permitted_and_one_hundredth_more_is_not` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `entry_window` | A broker instant that may be outside the entry window refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `TestTheEntryWindowIsJudgedOnTheBrokerClock` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `authorization_binds_every_field` | An authorization whose quote ask is not the preview's permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_tampering_with_any_bound_field_is_named` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `authorization_never_outlives_the_intent` | A stored authorization expiring after its intent permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_stored_authorization_outliving_its_intent_is_refused` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `authorization_after_preview_freshness` | A preview older than the configured freshness limit cannot be authorized | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_preview_older_than_the_freshness_limit_cannot_be_authorized` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |

