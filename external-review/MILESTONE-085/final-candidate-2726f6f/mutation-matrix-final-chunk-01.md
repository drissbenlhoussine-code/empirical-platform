# MILESTONE-085 — Mutation Matrix

**20 of 20 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `cd7162aba6cdcc2e066f7a15c68b9fc3077164893c24b3289d821e8a56185108`, after `cd7162aba6cdcc2e066f7a15c68b9fc3077164893c24b3289d821e8a56185108`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `intent_basis_matches_the_exact_intent` | Evidence describing a different intent is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_evidence_describing_a_different_intent_is_refused[expires_at]` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `intent_basis_bound_to_issuance` | An intent-time basis cannot be attached after the intent was issued | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_intent_evidence_cannot_be_attached_after_issuance` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `issuance_uses_the_measured_host_reading` | The intent is issued at the basis host reading, not at an unmeasured instant | `src/empirical_platform/usecases/paper_execution.py` | `test_the_intent_is_issued_at_the_host_reading_taken_after_the_clock_response` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `wall_clock_rollback` | Backward wall clock refuses | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_rollback_refuses[utc]` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `post_fetch_time` | Post-fetch evaluation uses current time | `src/empirical_platform/usecases/paper_execution.py` | `test_an_intent_expiring_during_the_fetch_is_refused` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `final_authorization_expiry` | Authorization is still valid at HTTP send | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[authorization-connect]` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `final_intent_expiry` | Intent expiry is checked after preparation | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[intent-prepare]` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `final_session_close` | Market close is checked after preparation | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[session-prepare]` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `final_quote_freshness` | Quote remains fresh after connection | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[quote-connect]` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `monotonic_elapsed` | Elapsed work ages a stalled wall clock | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_stalled_wall_clock_does_not_stop_expiry` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `http_final_guard` | Guard runs after connect before HTTP send | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_final_guard_runs_after_connect_and_before_http_request[False]` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `claim_time_after_lock` | A row-lock wait ages the permission: time is re-read after the lock | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_real_row_lock_wait_cannot_consume_expired_permission` | **EXECUTED_PASS** | detected; restored to `0bb79acbe940f471` |
| `paper_hostname_pin` | Only paper-api.alpaca.markets may receive an order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_endpoint_host_claim_matches_the_pinned_constant` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `https_requirement` | Only https may carry a credential | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_non_paper_endpoint_is_refused[http://paper-api.alpaca.markets]` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `redirect_refusal` | A redirect is refused, never followed | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `TestRedirectsAreRefusedNotFollowed` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `live_host_rejection` | An alternative host is refused even if it is a real Alpaca host | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_non_paper_endpoint_is_refused[https://api.alpaca.markets]` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `userinfo_rejection` | A URL carrying userinfo is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_userinfo_is_refused_by_the_userinfo_rule_specifically` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `non_canonical_port_rejection` | A port outside the canonical HTTPS boundary is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_non_paper_endpoint_is_refused[https://paper-api.alpaca.markets:8443]` | **EXECUTED_PASS** | detected; restored to `ed5659a44ba2e65e` |
| `human_authorization_requirement` | A preview carrying refusals cannot be authorized | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_refused_preview_cannot_be_authorized` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `account_binding` | An authorization does not permit a dispatch to another account | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_material_change_removes_the_permission[mutation1-different paper account]` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |

