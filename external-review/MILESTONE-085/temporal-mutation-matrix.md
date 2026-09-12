# MILESTONE-085 — Mutation Matrix

**12 of 12 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `broker_time_upper` | Broker round-trip uncertainty ages deadlines | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_broker_round_trip_uncertainty_cannot_extend_a_permission` | **EXECUTED_PASS** | detected; restored to `8362a3242669c571` |
| `wall_clock_rollback` | Backward wall clock refuses | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_rollback_refuses[utc]` | **EXECUTED_PASS** | detected; restored to `8362a3242669c571` |
| `clock_alignment` | Uncertain broker/local alignment refuses | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_uncertain_absolute_alignment_refuses[1]` | **EXECUTED_PASS** | detected; restored to `8362a3242669c571` |
| `post_fetch_time` | Post-fetch evaluation uses current time | `src/empirical_platform/usecases/paper_execution.py` | `test_a_quote_newer_than_the_command_instant_is_authorizable` | **EXECUTED_PASS** | detected; restored to `7235661e1600ef84` |
| `final_authorization_expiry` | Authorization is still valid at HTTP send | `src/empirical_platform/usecases/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[authorization-connect]` | **EXECUTED_PASS** | detected; restored to `7235661e1600ef84` |
| `final_intent_expiry` | Intent expiry is checked after preparation | `src/empirical_platform/usecases/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[intent-prepare]` | **EXECUTED_PASS** | detected; restored to `7235661e1600ef84` |
| `final_session_close` | Market close is checked after preparation | `src/empirical_platform/usecases/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[session-prepare]` | **EXECUTED_PASS** | detected; restored to `7235661e1600ef84` |
| `final_quote_freshness` | Quote remains fresh after connection | `src/empirical_platform/usecases/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[quote-connect]` | **EXECUTED_PASS** | detected; restored to `7235661e1600ef84` |
| `monotonic_elapsed` | Elapsed work ages a stalled wall clock | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_stalled_wall_clock_does_not_stop_expiry` | **EXECUTED_PASS** | detected; restored to `8362a3242669c571` |
| `http_final_guard` | Guard runs after connect before HTTP send | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_final_guard_runs_after_connect_and_before_http_request[False]` | **EXECUTED_PASS** | detected; restored to `160fed63bad57e5b` |
| `quote_freshness` | A stale quote refuses a preview | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override13-older than the]` | **EXECUTED_PASS** | detected; restored to `89201b2cd6ced879` |
| `quote_future_timestamp` | A quote after post-fetch evaluation time refuses authorization | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_each_condition_produces_its_own_refusal[override14-dated after this preview]` | **EXECUTED_PASS** | detected; restored to `89201b2cd6ced879` |
