# MILESTONE-085 — Mutation Matrix

**6 of 7 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `72fd2f257c8b13b28726c3512f3422c9c62ce52415961990675c083f88af2631`, after `72fd2f257c8b13b28726c3512f3422c9c62ce52415961990675c083f88af2631`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `definitive_refusal_statuses` | Only 400, 401, 403 and 422 can prove an order was refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |
| `definitive_refusal_requires_the_brokers_document` | A definitive status proves nothing without the broker's JSON error object | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `adapter_uncertain_status_is_ambiguous` | The adapter reports a non-definitive order answer as ambiguous, not as a refusal | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_an_uncertain_status_is_never_reported_as_a_refusal` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `duplicate_identity_422_is_not_a_refusal` | Alpaca's duplicate client_order_id 422 is an existing identity, never a refusal | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_documented_duplicate_answer_is_an_existing_identity` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `unknown_422_shape_fails_closed` | A 422 without the broker's integer code is uncertain, not a refusal | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unknown_shape_is_uncertain` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `frozen_path_guard_covers_m084` | The frozen-path guard governs MILESTONE-084 as well as MILESTONE-083 | `tools/check_frozen_paths.py` | `test_the_guard_freezes_exactly_m083_and_m084` | **EXECUTED_PASS** | detected; restored to `f7ef4546e1bc2779` |
| `frozen_path_guard_pins_m084_to_the_ratified_commit` | M084 is compared against the ratified commit, not against whatever HEAD holds | `tools/check_frozen_paths.py` | `test_m084_is_pinned_to_the_ratified_commit_and_m083_to_its_original_base` | **EXECUTED_PASS** | detected; restored to `f7ef4546e1bc2779` |

## Blockers

- `definitive_refusal_statuses`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.

