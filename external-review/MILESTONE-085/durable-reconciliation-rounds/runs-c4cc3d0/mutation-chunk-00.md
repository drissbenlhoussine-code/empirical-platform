# MILESTONE-085 — Mutation Matrix

**12 of 12 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `a5c387a39f23ad22472a3d2cb96108af6e2296e9e3c0c985a93ae25c1ca2c663`, after `a5c387a39f23ad22472a3d2cb96108af6e2296e9e3c0c985a93ae25c1ca2c663`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `dispatch_checks_the_binding` | The submit handler refuses a stored authorization that does not describe its preview | `src/empirical_platform/usecases/paper_execution.py` | `test_a_tampered_stored_authorization_refuses[quote_captured_at-value1]` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `final_guard_reads_the_kill_switch_again` | The kill switch is re-read after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_kill_switch_engaged_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `final_guard_reads_the_configuration_again` | The configuration is re-loaded and re-derived after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_configuration_changed_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `final_guard_reads_the_market_session_again` | The session is judged from the clock fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_market_that_closes_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `final_guard_reads_the_quote_again` | The quote is judged as fetched after the claim | `src/empirical_platform/usecases/paper_execution.py` | `test_a_quote_that_goes_stale_after_the_claim_is_refused` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `liquidation_deadline_at_dispatch` | A dispatch at 15:50 after a slow-host evaluation never submits | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_slow_host_at_evaluation_cannot_extend_the_liquidation_deadline` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `dispatch_uncertain_status_is_unknown` | The handler records a non-definitive answer as SUBMISSION_UNKNOWN, not REJECTED | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[fake-500-without-view]` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `dispatch_ambiguous_is_unknown` | A possibly delivered request is SUBMISSION_UNKNOWN, never terminal | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[timeout-after-send]` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `dispatch_unexpected_fault_is_unknown` | A fault after the send guard passed is recorded as SUBMISSION_UNKNOWN | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_and_the_broker_receives_at_most_one_submission[unexpected-fault-after-send]` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `reconcile_a_stale_in_progress_attempt` | An attempt left IN_PROGRESS is reconciled to the broker's answer | `src/empirical_platform/usecases/paper_execution.py` | `test_a_stale_in_progress_attempt_is_reconciled_to_the_brokers_answer` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `reconcile_leaves_a_live_dispatch_alone` | An attempt IN_PROGRESS for less than the not-found window is not looked up | `src/empirical_platform/usecases/paper_execution.py` | `test_a_live_dispatch_is_left_to_finish` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `reconcile_absence_never_rejects_a_live_dispatch` | A not-found answer never resolves an attempt that may still be sending | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_while_the_dispatcher_is_still_sending_never_rejects` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |

