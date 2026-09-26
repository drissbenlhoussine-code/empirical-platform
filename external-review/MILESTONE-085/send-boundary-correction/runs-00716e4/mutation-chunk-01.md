# MILESTONE-085 — Mutation Matrix

**22 of 22 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `b484179c2fb15454b7115b07dd79d3a3f522bef110634fcbe3b723ec86da973e`, after `b484179c2fb15454b7115b07dd79d3a3f522bef110634fcbe3b723ec86da973e`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `final_session_close` | Market close is checked after preparation | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[session-prepare]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `final_quote_freshness` | Quote remains fresh after connection | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[quote-connect]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `http_final_guard` | Guard runs after connect before HTTP send | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_final_guard_runs_after_connect_and_before_http_request[False]` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `paper_hostname_pin` | Only paper-api.alpaca.markets may receive an order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_endpoint_host_claim_matches_the_pinned_constant` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `https_requirement` | Only https may carry a credential | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_non_paper_endpoint_is_refused[http://paper-api.alpaca.markets]` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `redirect_refusal` | A redirect is refused, never followed | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `TestRedirectsAreRefusedNotFollowed` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `live_host_rejection` | An alternative host is refused even if it is a real Alpaca host | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_non_paper_endpoint_is_refused[https://api.alpaca.markets]` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `userinfo_rejection` | A URL carrying userinfo is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_userinfo_is_refused_by_the_userinfo_rule_specifically` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `non_canonical_port_rejection` | A port outside the canonical HTTPS boundary is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_non_paper_endpoint_is_refused[https://paper-api.alpaca.markets:8443]` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `human_authorization_requirement` | A preview carrying refusals cannot be authorized | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_refused_preview_cannot_be_authorized` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `account_binding` | An authorization does not permit a dispatch to another account | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation1-different paper account]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `fingerprint_binding` | An authorization does not permit a changed order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation0-order changed after it was authorized]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `approval_expiry` | An expired authorization permits nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation2-has expired]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `single_use_authorization` | A consumed authorization permits nothing further | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_consumed_authorization_permits_nothing_further` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `deterministic_client_order_id` | The order identity is derived, not generated | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_it_is_a_pure_function_of_persisted_identity` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `client_order_id_account_binding` | A different account yields a different order identity | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_different_account_yields_a_different_order_identity` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `unknown_outcome_state` | An ambiguous dispatch can be resolved but never retried | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unknown_outcome_can_be_resolved_but_never_retried` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `terminal_states_are_terminal` | Nothing leaves a terminal state | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_terminal_state_has_no_outgoing_edge` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `long_only_rule` | A sell cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override0-long-only]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `whole_share_rule` | A fractional quantity cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_fractional_quantity_is_not_even_representable` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `extended_hours_refusal` | Extended hours cannot be enabled | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override7-extended-hours]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `day_only_rule` | A time in force other than DAY cannot be expressed | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_forbidden_request_is_refused[override5-DAY]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |

