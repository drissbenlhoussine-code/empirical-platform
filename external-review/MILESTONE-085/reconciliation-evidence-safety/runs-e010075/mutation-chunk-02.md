# MILESTONE-085 — Mutation Matrix

**23 of 23 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `cbb5318236d04147c30eb9c031d9abbebcb833bac2f38578d63a406dc0689389`, after `cbb5318236d04147c30eb9c031d9abbebcb833bac2f38578d63a406dc0689389`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `watchlist` | A symbol off the approved watchlist refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override5-not on the approved watchlist]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `account_dispatchability` | A blocked paper account refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override1-does not permit orders]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `response_quantity_validation` | An acknowledgement for a different quantity is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_acknowledgement_fails_closed[override3-quantity]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `broker_status_map_closure` | An unmapped broker status does not become a known one | `src/empirical_platform/usecases/paper_execution.py` | `test_the_broker_status_map_is_exactly_this_closed_set` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `policy_derived_from_the_configuration` | The quote age limit is the stored configuration's, not a constant or argument | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_send_time_limit_is_the_configurations` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `policy_fingerprint_covers_every_limit` | Changing the quote age limit changes the policy fingerprint | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_limit_is_part_of_the_policy_fingerprint` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `final_guard_policy_fingerprint` | A re-derived policy other than the authorized one refuses the send | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_loosened_configuration_cannot_satisfy_an_authorization` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `spread_limit` | A spread above the configured limit refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_exactly_the_limit_is_permitted_and_one_hundredth_more_is_not` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `entry_window` | A broker instant that may be outside the entry window refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `TestTheEntryWindowIsJudgedOnTheBrokerClock` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `authorization_binds_every_field` | An authorization whose quote ask is not the preview's permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_tampering_with_any_bound_field_is_named` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `authorization_never_outlives_the_intent` | A stored authorization expiring after its intent permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_stored_authorization_outliving_its_intent_is_refused` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `authorization_after_preview_freshness` | A preview older than the configured freshness limit cannot be authorized | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_preview_older_than_the_freshness_limit_cannot_be_authorized` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `dispatch_checks_the_binding` | The submit handler refuses a stored authorization that does not describe its preview | `src/empirical_platform/usecases/paper_execution.py` | `test_a_tampered_stored_authorization_refuses[quote_captured_at-value1]` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `final_guard_reads_the_kill_switch_again` | The kill switch is re-read after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_kill_switch_engaged_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `final_guard_reads_the_configuration_again` | The configuration is re-loaded and re-derived after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_configuration_changed_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `final_guard_reads_the_market_session_again` | The session is judged from the clock fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_market_that_closes_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `final_guard_reads_the_quote_again` | The quote is judged as fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_quote_that_goes_stale_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `liquidation_deadline_never_later_than_the_calendar` | Host skew can shorten the liquidation deadline but never extend it | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_slow_host_at_evaluation_does_not_move_the_deadline_later` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `liquidation_deadline_at_dispatch` | A dispatch at 15:50 after a slow-host evaluation never submits | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_slow_host_at_evaluation_cannot_extend_the_liquidation_deadline` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `liquidation_deadline_for_another_date` | A liquidation deadline written for another date cannot be evaluated, so it refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_deadline_written_for_another_date_cannot_be_evaluated` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `definitive_refusal_statuses` | Only 400, 401, 403 and 422 can prove an order was refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `definitive_refusal_requires_the_brokers_document` | A definitive status proves nothing without the broker's JSON error object | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `dispatch_uncertain_status_is_unknown` | The handler records a non-definitive answer as SUBMISSION_UNKNOWN, not REJECTED | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[fake-500-without-view]` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |

