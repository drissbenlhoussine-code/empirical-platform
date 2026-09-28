# MILESTONE-085 — Mutation Matrix

**16 of 18 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `e566f2d0a31f53fc5556703cedbd47feeb0b7ed3642684b6216430ce55b8a76c`, after `e566f2d0a31f53fc5556703cedbd47feeb0b7ed3642684b6216430ce55b8a76c`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `deterministic_client_order_id` | The order identity is derived, not generated | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_it_is_a_pure_function_of_persisted_identity` | **EXECUTED_PASS** | detected; restored to `69ca9e616c1b8c7c` |
| `terminal_states_are_terminal` | Nothing leaves a terminal state | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_terminal_state_has_no_outgoing_edge` | **EXECUTED_PASS** | detected; restored to `69ca9e616c1b8c7c` |
| `definitive_refusal_statuses` | Only 400, 401, 403 and 422 can prove an order was refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |
| `definitive_refusal_requires_the_brokers_document` | A definitive status proves nothing without the broker's JSON error object | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_PASS** | detected; restored to `69ca9e616c1b8c7c` |
| `adapter_uncertain_status_is_ambiguous` | The adapter reports a non-definitive order answer as ambiguous, not as a refusal | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_an_uncertain_status_is_never_reported_as_a_refusal` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `duplicate_identity_422_is_not_a_refusal` | Alpaca's duplicate client_order_id 422 is an existing identity, never a refusal | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_documented_duplicate_answer_is_an_existing_identity` | **EXECUTED_PASS** | detected; restored to `69ca9e616c1b8c7c` |
| `unknown_422_shape_fails_closed` | A 422 without the broker's integer code is uncertain, not a refusal | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unknown_shape_is_uncertain` | **EXECUTED_PASS** | detected; restored to `69ca9e616c1b8c7c` |
| `identity_collision_looks_the_identity_up` | A collision is resolved by looking up the SAME client_order_id, not by guessing | `src/empirical_platform/usecases/paper_execution.py` | `test_an_exact_match_found_before_sending_is_adopted_without_a_send` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `pre_send_lookup_uses_the_derived_identity` | The identity asked about before sending is the derived one, not a replacement | `src/empirical_platform/usecases/paper_execution.py` | `test_an_exact_match_found_before_sending_is_adopted_without_a_send` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `no_resend_after_a_collision` | An intent with any attempt is never dispatched again, collision included | `src/empirical_platform/usecases/paper_execution.py` | `test_a_collision_is_never_followed_by_a_second_dispatch` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `identity_match_checks_the_symbol` | A broker order with another symbol is never adopted as ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_field_is_a_collision[symbol-TSLA]` | **EXECUTED_PASS** | detected; restored to `69ca9e616c1b8c7c` |
| `identity_match_checks_the_quantity` | A broker order with another quantity is never adopted as ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_field_is_a_collision[quantity-2]` | **EXECUTED_PASS** | detected; restored to `69ca9e616c1b8c7c` |
| `identity_match_checks_the_side` | A broker order with another side is never adopted as ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_field_is_a_collision[side-sell]` | **EXECUTED_PASS** | detected; restored to `69ca9e616c1b8c7c` |
| `reconcile_recovers_unknown_after_restart` | A new process reconciles an UNKNOWN attempt instead of leaving it | `src/empirical_platform/usecases/paper_execution.py` | `test_an_unknown_attempt_is_recovered_by_a_new_process_through_the_same_identity` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `reconcile_refuses_a_mismatching_order` | Reconciliation never adopts a broker order that differs from the authorized one | `src/empirical_platform/usecases/paper_execution.py` | `test_reconciliation_of_an_unknown_attempt_refuses_a_mismatching_order` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `database_rebuilt_meets_existing_identity` | Against PostgreSQL, a rebuilt database meets the broker's order and sends nothing | `src/empirical_platform/usecases/paper_execution.py` | `test_a_rebuilt_database_adopts_the_brokers_exact_order_and_sends_nothing` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `frozen_path_guard_covers_m084` | The frozen-path guard governs MILESTONE-084 as well as MILESTONE-083 | `tools/check_frozen_paths.py` | `test_the_guard_freezes_exactly_m083_and_m084` | **EXECUTED_PASS** | detected; restored to `f7ef4546e1bc2779` |
| `frozen_path_guard_pins_m084_to_the_ratified_commit` | M084 is compared against the ratified commit, not against whatever HEAD holds | `tools/check_frozen_paths.py` | `test_m084_is_pinned_to_the_ratified_commit_and_m083_to_its_original_base` | **EXECUTED_FAIL_BLOCKER** | the test does not pass again after restoration: tests\architecture\test_frozen_milestones.py:107: AssertionError
=========================== short test summary info ===========================
FAILED tests/architecture/test_frozen_milestones.py::TestBothMilestonesAreGoverned::test_m084_is_pinned_to_the_ratified_commit_and_m083_to_its_original_base
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.33s
 |

## Blockers

- `definitive_refusal_statuses`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.
- `frozen_path_guard_pins_m084_to_the_ratified_commit`: the test does not pass again after restoration: tests\architecture\test_frozen_milestones.py:107: AssertionError
=========================== short test summary info ===========================
FAILED tests/architecture/test_frozen_milestones.py::TestBothMilestonesAreGoverned::test_m084_is_pinned_to_the_ratified_commit_and_m083_to_its_original_base
!!!!!!!!!!!!!!!!!!!!!!!!!! stopping after 1 failures !!!!!!!!!!!!!!!!!!!!!!!!!!
1 failed in 0.33s


