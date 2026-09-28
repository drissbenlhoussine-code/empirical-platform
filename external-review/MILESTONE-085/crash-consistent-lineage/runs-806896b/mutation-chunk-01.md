# MILESTONE-085 — Mutation Matrix

**22 of 22 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `a8bce8c248b676227aa8835dfb99bd83efefc7bf5c7c90c172070767e8a2fabf`, after `a8bce8c248b676227aa8835dfb99bd83efefc7bf5c7c90c172070767e8a2fabf`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `final_session_close` | Market close is checked after preparation | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[session-prepare]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `final_quote_freshness` | Quote remains fresh after connection | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[quote-connect]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `paper_hostname_pin` | Only paper-api.alpaca.markets may receive an order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_endpoint_host_claim_matches_the_pinned_constant` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `human_authorization_requirement` | A preview carrying refusals cannot be authorized | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_refused_preview_cannot_be_authorized` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `account_binding` | An authorization does not permit a dispatch to another account | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation1-different paper account]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `fingerprint_binding` | An authorization does not permit a changed order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation0-order changed after it was authorized]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `approval_expiry` | An expired authorization permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation2-has expired]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `single_use_authorization` | A consumed authorization permits nothing further | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_consumed_authorization_permits_nothing_further` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `deterministic_client_order_id` | The order identity is derived, not generated | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_it_is_a_pure_function_of_persisted_identity` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `client_order_id_account_binding` | A different account yields a different order identity | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_different_account_yields_a_different_order_identity` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `unknown_outcome_state` | An ambiguous dispatch can be resolved but never retried | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unknown_outcome_can_be_resolved_but_never_retried` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `terminal_states_are_terminal` | Nothing leaves a terminal state | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_terminal_state_has_no_outgoing_edge` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `long_only_rule` | A sell cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override0-long-only]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `whole_share_rule` | A fractional quantity cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_fractional_quantity_is_not_even_representable` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `extended_hours_refusal` | Extended hours cannot be enabled | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override7-extended-hours]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `day_only_rule` | A time in force other than DAY cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override5-DAY]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `kill_switch` | An engaged execution kill switch refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override0-kill switch]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `quote_freshness` | A stale quote refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override13-older than the]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `quote_future_timestamp` | A quote after post-fetch evaluation time refuses authorization | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override14-dated after the latest possible]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `buying_power_check` | A cost ceiling above paper buying power refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override11-exceeds paper buying power]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `notional_ceiling` | A cost ceiling above the configured limit refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override10-exceeds the limit]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `exposure_limit` | An existing position refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override9-position of 5 already exists]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |

