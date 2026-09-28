# MILESTONE-085 — Mutation Matrix

**7 of 7 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `c07f8da4365b367e9e67dca70cade211cf50e6c2c67dd2a797a1699762f352a0`, after `c07f8da4365b367e9e67dca70cade211cf50e6c2c67dd2a797a1699762f352a0`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `absence_never_revokes_a_positive_observation` | An UNKNOWN whose identity was positively observed is never resolved by absence | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_never_discards_a_prior_positive_observation` | **EXECUTED_PASS** | detected; restored to `648b5c619ccbd957` |
| `missing_broker_time_evidence_is_unresolved` | Rounds without a broker clock interval never satisfy the waiting interval | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_completed_rounds_without_broker_time_evidence_never_satisfy_the_interval` | **EXECUTED_PASS** | detected; restored to `d5ef7536b95dbca5` |
| `database_round_sequence_allocated_under_the_attempt_lock` | Sequence allocation serialises on the attempt row; MAX+1 is never unprotected | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_allocation_holds_the_attempt_lock_between_reading_and_inserting` | **EXECUTED_PASS** | detected; restored to `e6a7f02817291520` |
| `database_round_completed_exactly_once` | The completion statement matches only the still-incomplete round | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_the_journal_completes_a_round_exactly_once_and_binds_it_to_the_attempt` | **EXECUTED_PASS** | detected; restored to `e6a7f02817291520` |
| `database_finalisation_rejects_a_stale_round_snapshot` | Terminal absence resolution requires the round set the caller judged | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_a_round_completed_by_another_process_after_the_snapshot_is_never_finalised_from_it` | **EXECUTED_PASS** | detected; restored to `e6a7f02817291520` |
| `database_finalisation_re_evaluates_on_fresh_rows` | Terminal absence resolution re-applies the policy on the locked, fresh rows | `src/empirical_platform/shared/persistence/postgres_repositories/paper_execution_repositories.py` | `test_finalisation_honours_positive_evidence_recorded_without_a_round` | **EXECUTED_PASS** | detected; restored to `e6a7f02817291520` |
| `database_round_sequence_unique_per_attempt` | The schema refuses two rounds with the same (attempt_id, sequence) | `migrations/versions/a7d3c9e14f26_add_m085_reconciliation_round_journal.py` | `test_the_journal_completes_a_round_exactly_once_and_binds_it_to_the_attempt` | **EXECUTED_PASS** | detected; restored to `a735abc9373f8256` |

