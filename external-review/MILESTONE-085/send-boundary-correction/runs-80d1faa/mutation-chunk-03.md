# MILESTONE-085 — Mutation Matrix

**20 of 22 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `793a800c6fdbc2e321db2f4a067b8aba00e327429f9db18a34ff6d64514cbcbe`, after `793a800c6fdbc2e321db2f4a067b8aba00e327429f9db18a34ff6d64514cbcbe`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `dispatch_checks_the_binding` | The submit handler refuses a stored authorization that does not describe its preview | `src/empirical_platform/usecases/paper_execution.py` | `test_a_tampered_stored_authorization_refuses[quote_captured_at-value1]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `final_guard_reads_the_kill_switch_again` | The kill switch is re-read after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_kill_switch_engaged_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `final_guard_reads_the_configuration_again` | The configuration is re-loaded and re-derived after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_configuration_changed_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `final_guard_reads_the_market_session_again` | The session is judged from the clock fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_market_that_closes_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `final_guard_reads_the_quote_again` | The quote is judged as fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_quote_that_goes_stale_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `liquidation_deadline_never_later_than_the_calendar` | Host skew can shorten the liquidation deadline but never extend it | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_slow_host_at_evaluation_does_not_move_the_deadline_later` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `liquidation_deadline_at_dispatch` | A dispatch at 15:50 after a slow-host evaluation never submits | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_slow_host_at_evaluation_cannot_extend_the_liquidation_deadline` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `liquidation_deadline_for_another_date` | A liquidation deadline written for another date cannot be evaluated, so it refuses | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_deadline_written_for_another_date_cannot_be_evaluated` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `definitive_refusal_statuses` | Only 400, 401, 403 and 422 can prove an order was refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |
| `definitive_refusal_requires_the_brokers_document` | A definitive status proves nothing without the broker's JSON error object | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |
| `adapter_uncertain_status_is_ambiguous` | The adapter reports a non-definitive order answer as ambiguous, not as a refusal | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_an_uncertain_status_is_never_reported_as_a_refusal` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `dispatch_uncertain_status_is_unknown` | The handler records a non-definitive answer as SUBMISSION_UNKNOWN, not REJECTED | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[fake-500-without-view]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `dispatch_ambiguous_is_unknown` | A possibly delivered request is SUBMISSION_UNKNOWN, never terminal | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[timeout-after-send]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `dispatch_unexpected_fault_is_unknown` | A fault after the send guard passed is recorded as SUBMISSION_UNKNOWN | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[unexpected-fault-after-send]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `reconcile_a_stale_in_progress_attempt` | An attempt left IN_PROGRESS is reconciled to the broker's answer | `src/empirical_platform/usecases/paper_execution.py` | `test_a_stale_in_progress_attempt_is_reconciled_to_the_brokers_answer` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `reconcile_leaves_a_live_dispatch_alone` | An attempt IN_PROGRESS for less than the not-found window is not looked up | `src/empirical_platform/usecases/paper_execution.py` | `test_a_live_dispatch_is_left_to_finish` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `reconcile_absence_never_rejects_a_live_dispatch` | A not-found answer never resolves an attempt that may still be sending | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_while_the_dispatcher_is_still_sending_never_rejects` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `duplicate_identity_422_is_not_a_refusal` | Alpaca's duplicate client_order_id 422 is an existing identity, never a refusal | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_documented_duplicate_answer_is_an_existing_identity` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `unknown_422_shape_fails_closed` | A 422 without the broker's integer code is uncertain, not a refusal | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unknown_shape_is_uncertain` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `identity_collision_looks_the_identity_up` | A collision is resolved by looking up the SAME client_order_id, not by guessing | `src/empirical_platform/usecases/paper_execution.py` | `test_an_exact_match_found_before_sending_is_observed_not_adopted` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `pre_send_lookup_uses_the_derived_identity` | The identity asked about before sending is the derived one, not a replacement | `src/empirical_platform/usecases/paper_execution.py` | `test_an_exact_match_found_before_sending_is_observed_not_adopted` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `no_resend_after_a_collision` | An intent with any attempt is never dispatched again, collision included | `src/empirical_platform/usecases/paper_execution.py` | `test_a_collision_is_never_followed_by_a_second_dispatch` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |

## Blockers

- `definitive_refusal_statuses`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.
- `definitive_refusal_requires_the_brokers_document`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.

