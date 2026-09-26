# MILESTONE-085 — Mutation Matrix

**13 of 15 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `1496beaab55ffff884e0b611812c895707c5bea82d766d108f834c22c08a8000`, after `1496beaab55ffff884e0b611812c895707c5bea82d766d108f834c22c08a8000`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `absence_counts_only_the_consecutive_suffix` | The bounded policy counts the trailing consecutive not-found run, not every 404 | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unusable_answer_breaks_the_consecutive_not_found_run` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `lookup_failure_breaks_the_absence_run` | A recorded lookup failure breaks the consecutive not-found run | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_lookup_that_raises_is_recorded_and_breaks_the_run` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `lookup_failure_is_recorded` | A reconciliation lookup that raises leaves an event behind | `src/empirical_platform/usecases/paper_execution.py` | `test_a_lookup_that_raises_is_recorded_and_breaks_the_run` | **EXECUTED_PASS** | detected; restored to `0dc003a91d905d68` |
| `absence_never_rejects_a_known_order` | A bound, acknowledged order is never rejected because a lookup said 404 | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_never_rejects_a_previously_accepted_order` | **EXECUTED_PASS** | detected; restored to `0dc003a91d905d68` |
| `absence_never_revokes_a_positive_observation` | An UNKNOWN whose identity was positively observed is never resolved by absence | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_never_discards_a_prior_positive_observation` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |
| `round_begun_durably_before_any_network_work` | No lookup runs before the round it belongs to is committed | `src/empirical_platform/usecases/paper_execution.py` | `test_q2_when_beginning_the_round_fails_no_lookup_is_made` | **EXECUTED_PASS** | detected; restored to `0dc003a91d905d68` |
| `incomplete_round_ends_the_consecutive_run` | A round whose outcome is unknown is never skipped when counting consecutive 404s | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_q2_a_failed_round_whose_outcome_write_fails_stays_incomplete_and_blocks_resolution` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `incomplete_round_blocks_resolution` | An incomplete round anywhere in the journal forbids an absence decision | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_delayed_earlier_round_blocks_later_negatives_until_it_completes` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `rounds_ordered_by_sequence_never_by_timestamp` | Safety decisions order rounds by their allocated sequence, not by host timestamps | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_q4_a_failure_recorded_by_a_skewed_reconciler_still_breaks_the_run[reconciler-B-lags]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `found_round_forbids_absence_resolution` | A completed FOUND round is positive evidence that later 404s never override | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_delayed_earlier_round_blocks_later_negatives_until_it_completes` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `waiting_bound_uses_the_conservative_endpoints` | The waiting lower bound is current.earliest - anchor.latest, never the reverse | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_q4_interval_uncertainty_straddling_the_threshold_waits_for_the_lower_bound` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `missing_broker_time_evidence_is_unresolved` | Rounds without a broker clock interval never satisfy the waiting interval | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_completed_rounds_without_broker_time_evidence_never_satisfy_the_interval` | **EXECUTED_FAIL_BLOCKER** | the test failed, but not for the intended reason ('missing broker-time evidence was read as sufficient' absent): ng_lower_bound_seconds

tests\unit\test_m085_reconciliation_rounds.py:619: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_reconciliation_rounds.py::test_completed_rounds_without_broker_time_evidence_never_satisfy_the_interval
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.72s
 |
| `contradictory_broker_readings_are_not_trusted` | A current reading earlier than the anchor yields no interval, not its magnitude | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_q4_a_broker_clock_that_reads_backwards_is_not_trusted_for_the_interval` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `round_interval_is_the_broker_clock_not_the_caller_wall_time` | A completed round carries the broker clock interval sampled in it, not command.at | `src/empirical_platform/usecases/paper_execution.py` | `test_q4_a_leading_host_clock_cannot_manufacture_the_waiting_interval` | **EXECUTED_PASS** | detected; restored to `0dc003a91d905d68` |
| `raised_lookup_is_a_failed_round_not_a_not_found_one` | A round whose network work raised is completed FAILED; no HTTP status is fabricated | `src/empirical_platform/usecases/paper_execution.py` | `test_a_failed_broker_clock_fetch_makes_the_round_failed_without_time_evidence` | **EXECUTED_PASS** | detected; restored to `0dc003a91d905d68` |

## Blockers

- `absence_never_revokes_a_positive_observation`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.
- `missing_broker_time_evidence_is_unresolved`: the test failed, but not for the intended reason ('missing broker-time evidence was read as sufficient' absent): ng_lower_bound_seconds

tests\unit\test_m085_reconciliation_rounds.py:619: AssertionError
=========================== short test summary info ===========================
FAILED tests/unit/test_m085_reconciliation_rounds.py::test_completed_rounds_without_broker_time_evidence_never_satisfy_the_interval
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.72s


