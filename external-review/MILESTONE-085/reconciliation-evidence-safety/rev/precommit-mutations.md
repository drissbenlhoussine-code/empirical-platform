# MILESTONE-085 — Mutation Matrix

**16 of 18 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `46e91cae90858c5f55e5cb021bba45e93ddac34fb20af467a9b1b3d28129b797`, after `46e91cae90858c5f55e5cb021bba45e93ddac34fb20af467a9b1b3d28129b797`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `unknown_outcome_state` | An ambiguous dispatch can be resolved but never retried | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unknown_outcome_can_be_resolved_but_never_retried` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `reconcile_a_stale_in_progress_attempt` | An attempt left IN_PROGRESS is reconciled to the broker's answer | `src/empirical_platform/usecases/paper_execution.py` | `test_a_stale_in_progress_attempt_is_reconciled_to_the_brokers_answer` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `reconcile_leaves_a_live_dispatch_alone` | An attempt IN_PROGRESS for less than the not-found window is not looked up | `src/empirical_platform/usecases/paper_execution.py` | `test_a_live_dispatch_is_left_to_finish` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `reconcile_absence_never_rejects_a_live_dispatch` | A not-found answer never resolves an attempt that may still be sending | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_while_the_dispatcher_is_still_sending_never_rejects` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `reconcile_recovers_unknown_after_restart` | A new process reconciles an UNKNOWN attempt instead of leaving it | `src/empirical_platform/usecases/paper_execution.py` | `test_an_unknown_attempt_is_recovered_by_a_new_process_through_the_same_identity` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `database_rebuilt_meets_existing_identity` | Against PostgreSQL, a rebuilt database meets the broker's order and sends nothing | `src/empirical_platform/usecases/paper_execution.py` | `test_a_rebuilt_database_observes_the_brokers_order_without_attributing_or_sending` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `reconcile_requires_lineage_before_adoption` | An order under our identity is adopted only by an attempt that may have sent it | `src/empirical_platform/usecases/paper_execution.py` | `test_nothing_is_ever_resent_and_no_later_authorization_reopens_it` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `lineage_requires_the_send_boundary_record` | SUBMISSION_IN_PROGRESS alone is preparation; lineage needs the persisted boundary | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_death_during_the_pre_send_lookup_leaves_no_lineage` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `send_boundary_record_is_bound_field_by_field` | A boundary record lends lineage only when every bound field is this attempt's | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_boundary_record_that_does_not_bind_lends_no_lineage[authorization_id]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `send_boundary_recorded_before_the_send` | The send-capable boundary is persisted before the request can leave | `src/empirical_platform/usecases/paper_execution.py` | `test_our_own_post_then_death_before_acknowledgement_is_recovered_without_resending` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `historical_adoption_requires_the_account_binding` | Reconciliation verifies the boundary record against the authorized account | `src/empirical_platform/usecases/paper_execution.py` | `test_a_tampered_account_in_the_persisted_boundary_record_blocks_attribution` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `absence_counts_only_the_consecutive_suffix` | The bounded policy counts the trailing consecutive not-found run, not every 404 | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unusable_answer_breaks_the_consecutive_not_found_run` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `lookup_failure_breaks_the_absence_run` | A recorded lookup failure breaks the consecutive not-found run | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_lookup_that_raises_is_recorded_and_breaks_the_run` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `lookup_failure_is_recorded` | A reconciliation lookup that raises leaves an event behind | `src/empirical_platform/usecases/paper_execution.py` | `test_a_lookup_that_raises_is_recorded_and_breaks_the_run` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `absence_never_rejects_a_known_order` | A bound, acknowledged order is never rejected because a lookup said 404 | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_never_rejects_a_previously_accepted_order` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `absence_never_revokes_a_positive_observation` | An UNKNOWN whose identity was positively observed is never resolved by absence | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_never_discards_a_prior_positive_observation` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `binding_parser_rejects_padding_and_duplicates` | A boundary record with more or fewer than the canonical tokens is rejected whole | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole[identical duplicate appended]` | **EXECUTED_FAIL_BLOCKER** | the detecting test does not pass before the mutation: 
no tests ran in 0.48s
ERROR: not found: C:\Users\LuxSy\Documents\trading\tests\unit\test_m085_boundary_binding_parser.py::test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole
(no match in any of [<Module test_m085_boundary_binding_parser.py>])

 |
| `binding_parser_requires_canonical_keys` | Each token must carry the canonical key for its position | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole[fields out of canonical order]` | **EXECUTED_FAIL_BLOCKER** | the detecting test does not pass before the mutation: 
no tests ran in 0.48s
ERROR: not found: C:\Users\LuxSy\Documents\trading\tests\unit\test_m085_boundary_binding_parser.py::test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole
(no match in any of [<Module test_m085_boundary_binding_parser.py>])

 |

## Blockers

- `binding_parser_rejects_padding_and_duplicates`: the detecting test does not pass before the mutation: 
no tests ran in 0.48s
ERROR: not found: C:\Users\LuxSy\Documents\trading\tests\unit\test_m085_boundary_binding_parser.py::test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole
(no match in any of [<Module test_m085_boundary_binding_parser.py>])


- `binding_parser_requires_canonical_keys`: the detecting test does not pass before the mutation: 
no tests ran in 0.48s
ERROR: not found: C:\Users\LuxSy\Documents\trading\tests\unit\test_m085_boundary_binding_parser.py::test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole
(no match in any of [<Module test_m085_boundary_binding_parser.py>])



