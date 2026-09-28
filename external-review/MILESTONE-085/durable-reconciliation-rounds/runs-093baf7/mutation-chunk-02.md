# MILESTONE-085 — Mutation Matrix

**27 of 28 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `b96e298a8b997dd74e5e40189ea8d046c13e4a37966ad6c771f1a4de560b5f3a`, after `b96e298a8b997dd74e5e40189ea8d046c13e4a37966ad6c771f1a4de560b5f3a`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `database_attempt_insert_guard` | The database refuses an attempt without a consumed authorization | `migrations/versions/b1e9d47c30a5_create_m085_paper_execution_schema.py` | `test_an_attempt_without_a_consumed_authorization_is_refused` | **EXECUTED_PASS** | detected; restored to `fb7762aa8cf07742` |
| `m084_intent_boundary` | A paper row naming an unknown intent is refused | `migrations/versions/b1e9d47c30a5_create_m085_paper_execution_schema.py` | `test_a_paper_row_naming_an_unknown_intent_is_still_refused` | **EXECUTED_PASS** | detected; restored to `fb7762aa8cf07742` |
| `authority_contract_reads_the_sql_installed_at_head` | An enforcement claim is checked against the guard installed at head | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_every_database_enforcement_claim_names_sql_installed_at_head` | **EXECUTED_PASS** | detected; restored to `849cf3b38f8048f0` |
| `dispatch_claim_lease` | The claim is conditional, so two workers cannot both win | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_exactly_one_wins_and_the_loser_receives_the_winner[repetition-1]` | **EXECUTED_PASS** | detected; restored to `e6a7f02817291520` |
| `policy_derived_from_the_configuration` | The quote age limit is the stored configuration's, not a constant or argument | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_send_time_limit_is_the_configurations` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `policy_fingerprint_covers_every_limit` | Changing the quote age limit changes the policy fingerprint | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_limit_is_part_of_the_policy_fingerprint` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `final_guard_policy_fingerprint` | A re-derived policy other than the authorized one refuses the send | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_loosened_configuration_cannot_satisfy_an_authorization` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `spread_limit` | A spread above the configured limit refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_exactly_the_limit_is_permitted_and_one_hundredth_more_is_not` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `entry_window` | A broker instant that may be outside the entry window refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `TestTheEntryWindowIsJudgedOnTheBrokerClock` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `authorization_binds_every_field` | An authorization whose quote ask is not the preview's permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_tampering_with_any_bound_field_is_named` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `authorization_never_outlives_the_intent` | A stored authorization expiring after its intent permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_stored_authorization_outliving_its_intent_is_refused` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `authorization_after_preview_freshness` | A preview older than the configured freshness limit cannot be authorized | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_preview_older_than_the_freshness_limit_cannot_be_authorized` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `dispatch_checks_the_binding` | The submit handler refuses a stored authorization that does not describe its preview | `src/empirical_platform/usecases/paper_execution.py` | `test_a_tampered_stored_authorization_refuses[quote_captured_at-value1]` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `final_guard_reads_the_kill_switch_again` | The kill switch is re-read after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_kill_switch_engaged_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `final_guard_reads_the_configuration_again` | The configuration is re-loaded and re-derived after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_configuration_changed_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `final_guard_reads_the_market_session_again` | The session is judged from the clock fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_market_that_closes_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `final_guard_reads_the_quote_again` | The quote is judged as fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_quote_that_goes_stale_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `liquidation_deadline_never_later_than_the_calendar` | Host skew can shorten the liquidation deadline but never extend it | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_slow_host_at_evaluation_does_not_move_the_deadline_later` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `liquidation_deadline_at_dispatch` | A dispatch at 15:50 after a slow-host evaluation never submits | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_slow_host_at_evaluation_cannot_extend_the_liquidation_deadline` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `liquidation_deadline_for_another_date` | A liquidation deadline written for another date cannot be evaluated, so it refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_deadline_written_for_another_date_cannot_be_evaluated` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `definitive_refusal_statuses` | Only 400, 401, 403 and 422 can prove an order was refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `definitive_refusal_requires_the_brokers_document` | A definitive status proves nothing without the broker's JSON error object | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `dispatch_uncertain_status_is_unknown` | The handler records a non-definitive answer as SUBMISSION_UNKNOWN, not REJECTED | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[fake-500-without-view]` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `dispatch_ambiguous_is_unknown` | A possibly delivered request is SUBMISSION_UNKNOWN, never terminal | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[timeout-after-send]` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `dispatch_unexpected_fault_is_unknown` | A fault after the send guard passed is recorded as SUBMISSION_UNKNOWN | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[unexpected-fault-after-send]` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `reconcile_a_stale_in_progress_attempt` | An attempt left IN_PROGRESS is reconciled to the broker's answer | `src/empirical_platform/usecases/paper_execution.py` | `test_a_stale_in_progress_attempt_is_reconciled_to_the_brokers_answer` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `reconcile_leaves_a_live_dispatch_alone` | An attempt IN_PROGRESS for less than the not-found window is not looked up | `src/empirical_platform/usecases/paper_execution.py` | `test_a_live_dispatch_is_left_to_finish` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `reconcile_absence_never_rejects_a_live_dispatch` | A not-found answer never resolves an attempt that may still be sending | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_while_the_dispatcher_is_still_sending_never_rejects` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |

## Blockers

- `reconcile_absence_never_rejects_a_live_dispatch`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.

