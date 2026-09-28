# MILESTONE-085 — Mutation Matrix

**14 of 14 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `cd7162aba6cdcc2e066f7a15c68b9fc3077164893c24b3289d821e8a56185108`, after `cd7162aba6cdcc2e066f7a15c68b9fc3077164893c24b3289d821e8a56185108`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `legacy_dry_run_refused` | --dry-run refuses before any runtime, writer, socket or file is touched | `tools/m085_paper_acceptance.py` | `test_dry_run_is_refused_before_any_record_connection_or_file` | **EXECUTED_PASS** | detected; restored to `6e1458806f9fcbfc` |
| `duplicate_identity_422_is_not_a_refusal` | Alpaca's duplicate client_order_id 422 is an existing identity, never a refusal | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_documented_duplicate_answer_is_an_existing_identity` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `unknown_422_shape_fails_closed` | A 422 without the broker's integer code is uncertain, not a refusal | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unknown_shape_is_uncertain` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `identity_collision_looks_the_identity_up` | A collision is resolved by looking up the SAME client_order_id, not by guessing | `src/empirical_platform/usecases/paper_execution.py` | `test_an_exact_match_found_before_sending_is_adopted_without_a_send` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `pre_send_lookup_uses_the_derived_identity` | The identity asked about before sending is the derived one, not a replacement | `src/empirical_platform/usecases/paper_execution.py` | `test_an_exact_match_found_before_sending_is_adopted_without_a_send` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `no_resend_after_a_collision` | An intent with any attempt is never dispatched again, collision included | `src/empirical_platform/usecases/paper_execution.py` | `test_a_collision_is_never_followed_by_a_second_dispatch` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `identity_match_checks_the_symbol` | A broker order with another symbol is never adopted as ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_field_is_a_collision[symbol-TSLA]` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `identity_match_checks_the_quantity` | A broker order with another quantity is never adopted as ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_field_is_a_collision[quantity-2]` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `identity_match_checks_the_side` | A broker order with another side is never adopted as ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_field_is_a_collision[side-sell]` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `reconcile_recovers_unknown_after_restart` | A new process reconciles an UNKNOWN attempt instead of leaving it | `src/empirical_platform/usecases/paper_execution.py` | `test_an_unknown_attempt_is_recovered_by_a_new_process_through_the_same_identity` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `reconcile_refuses_a_mismatching_order` | Reconciliation never adopts a broker order that differs from the authorized one | `src/empirical_platform/usecases/paper_execution.py` | `test_reconciliation_of_an_unknown_attempt_refuses_a_mismatching_order` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `database_rebuilt_meets_existing_identity` | Against PostgreSQL, a rebuilt database meets the broker's order and sends nothing | `src/empirical_platform/usecases/paper_execution.py` | `test_a_rebuilt_database_adopts_the_brokers_exact_order_and_sends_nothing` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `frozen_path_guard_covers_m084` | The frozen-path guard governs MILESTONE-084 as well as MILESTONE-083 | `tools/check_frozen_paths.py` | `test_the_guard_freezes_exactly_m083_and_m084` | **EXECUTED_PASS** | detected; restored to `f7ef4546e1bc2779` |
| `frozen_path_guard_pins_m084_to_the_ratified_commit` | M084 is compared against the ratified commit, not against whatever HEAD holds | `tools/check_frozen_paths.py` | `test_m084_is_pinned_to_the_ratified_commit_and_m083_to_its_original_base` | **EXECUTED_PASS** | detected; restored to `f7ef4546e1bc2779` |

