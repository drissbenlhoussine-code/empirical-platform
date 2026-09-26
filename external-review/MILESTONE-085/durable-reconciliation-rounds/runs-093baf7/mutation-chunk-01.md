# MILESTONE-085 — Mutation Matrix

**28 of 28 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `b96e298a8b997dd74e5e40189ea8d046c13e4a37966ad6c771f1a4de560b5f3a`, after `b96e298a8b997dd74e5e40189ea8d046c13e4a37966ad6c771f1a4de560b5f3a`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `account_binding` | An authorization does not permit a dispatch to another account | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation1-different paper account]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `fingerprint_binding` | An authorization does not permit a changed order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation0-order changed after it was authorized]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `approval_expiry` | An expired authorization permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation2-has expired]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `single_use_authorization` | A consumed authorization permits nothing further | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_consumed_authorization_permits_nothing_further` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `deterministic_client_order_id` | The order identity is derived, not generated | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_it_is_a_pure_function_of_persisted_identity` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `client_order_id_account_binding` | A different account yields a different order identity | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_different_account_yields_a_different_order_identity` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `unknown_outcome_state` | An ambiguous dispatch can be resolved but never retried | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unknown_outcome_can_be_resolved_but_never_retried` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `terminal_states_are_terminal` | Nothing leaves a terminal state | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_terminal_state_has_no_outgoing_edge` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `long_only_rule` | A sell cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override0-long-only]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `whole_share_rule` | A fractional quantity cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_fractional_quantity_is_not_even_representable` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `extended_hours_refusal` | Extended hours cannot be enabled | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override7-extended-hours]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `day_only_rule` | A time in force other than DAY cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override5-DAY]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `kill_switch` | An engaged execution kill switch refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override0-kill switch]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `quote_freshness` | A stale quote refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override13-older than the]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `quote_future_timestamp` | A quote after post-fetch evaluation time refuses authorization | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override14-dated after the latest possible]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `buying_power_check` | A cost ceiling above paper buying power refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override11-exceeds paper buying power]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `notional_ceiling` | A cost ceiling above the configured limit refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override10-exceeds the limit]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `exposure_limit` | An existing position refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override9-position of 5 already exists]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `asset_tradability` | An untradable asset refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override6-not tradable]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `watchlist` | A symbol off the approved watchlist refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override5-not on the approved watchlist]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `account_dispatchability` | A blocked paper account refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override1-does not permit orders]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `response_quantity_validation` | An acknowledgement for a different quantity is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_acknowledgement_fails_closed[override3-quantity]` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `broker_status_map_closure` | An unmapped broker status does not become a known one | `src/empirical_platform/usecases/paper_execution.py` | `test_the_broker_status_map_is_exactly_this_closed_set` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `authority_enum_closure` | A claim the schema does not name cannot enter the contract | `external-review/MILESTONE-085/current-authority.schema.json` | `test_every_list_length_is_exact` | **EXECUTED_PASS** | detected; restored to `99b3925b8288e605` |
| `authority_version_const` | The authority version is frozen at 1 | `external-review/MILESTONE-085/current-authority.schema.json` | `test_the_authority_version_is_pinned_to_one` | **EXECUTED_PASS** | detected; restored to `99b3925b8288e605` |
| `deterministic_markdown_check` | The document is the deterministic rendering of the contract | `external-review/MILESTONE-085/current-authority.json` | `test_the_markdown_is_byte_identical_to_the_rendering` | **EXECUTED_PASS** | detected; restored to `806da25586641b63` |
| `database_transition_trigger` | The database refuses an illegal execution transition | `migrations/versions/9c4b2e7d5a18_bind_m085_send_policy_and_terminal_attempts.py` | `test_the_database_table_matches_the_domain_table_exactly` | **EXECUTED_PASS** | detected; restored to `a9169e35f81a8327` |
| `database_single_use_trigger` | The database refuses a second consumption | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_a_second_consumption_is_refused_by_the_trigger` | **EXECUTED_PASS** | detected; restored to `849cf3b38f8048f0` |

