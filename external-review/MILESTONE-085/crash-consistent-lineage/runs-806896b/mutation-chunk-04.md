# MILESTONE-085 — Mutation Matrix

**14 of 14 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `a8bce8c248b676227aa8835dfb99bd83efefc7bf5c7c90c172070767e8a2fabf`, after `a8bce8c248b676227aa8835dfb99bd83efefc7bf5c7c90c172070767e8a2fabf`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `unresolved_identity_recovered_after_restart` | A new process reconciles an unresolved identity instead of leaving it | `src/empirical_platform/usecases/paper_execution.py` | `test_after_a_restart_a_successful_lookup_surfaces_the_order_without_attributing_it` | **EXECUTED_PASS** | detected; restored to `839371632b5fde7f` |
| `reconcile_requires_lineage_before_adoption` | An order under our identity is adopted only by an attempt that may have sent it | `src/empirical_platform/usecases/paper_execution.py` | `test_nothing_is_ever_resent_and_no_later_authorization_reopens_it` | **EXECUTED_PASS** | detected; restored to `839371632b5fde7f` |
| `reconcile_verifies_the_account` | A found order is adopted only when the broker client's account is the authorized one | `src/empirical_platform/usecases/paper_execution.py` | `test_an_account_that_is_not_the_authorized_one_is_never_adopted` | **EXECUTED_PASS** | detected; restored to `839371632b5fde7f` |
| `lineage_unsent_never_attributed` | An attempt recorded as not having sent can never be attributed a found order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_event_recording_no_send_outranks_a_state_that_would_otherwise_qualify[SUBMISSION_UNKNOWN-AMBIGUOUS-CLIENT_ORDER_ID_COLLISION]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `unknown_error_code_is_uncertain` | A refusal code Alpaca does not document for that status proves nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_unknown_or_inconsistent_semantics_are_uncertain` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `terms_compare_limit_price` | A broker order with another limit price is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[limit_price-5.00]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `terms_compare_time_in_force` | A broker order with another time_in_force is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[time_in_force-gtc]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `terms_compare_extended_hours` | A broker order with another extended_hours flag is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[extended_hours-True]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `terms_compare_bound_broker_order_id` | A broker id already bound to the attempt must stay consistent | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_bound_broker_order_id_must_stay_consistent` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `lineage_requires_the_send_boundary_record` | SUBMISSION_IN_PROGRESS alone is preparation; lineage needs the persisted boundary | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_death_during_the_pre_send_lookup_leaves_no_lineage` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `send_boundary_record_is_bound_field_by_field` | A boundary record lends lineage only when every bound field is this attempt's | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_boundary_record_that_does_not_bind_lends_no_lineage[authorization_id]` | **EXECUTED_PASS** | detected; restored to `278ddb7327599ae0` |
| `send_boundary_recorded_before_the_send` | The send-capable boundary is persisted before the request can leave | `src/empirical_platform/usecases/paper_execution.py` | `test_our_own_post_then_death_before_acknowledgement_is_recovered_without_resending` | **EXECUTED_PASS** | detected; restored to `839371632b5fde7f` |
| `final_checks_follow_the_boundary_write` | The kill switch is read after the boundary write, which may block | `src/empirical_platform/usecases/paper_execution.py` | `test_the_kill_switch_engaged_during_the_boundary_write_stops_the_post` | **EXECUTED_PASS** | detected; restored to `839371632b5fde7f` |
| `historical_adoption_requires_the_account_binding` | Reconciliation verifies the boundary record against the authorized account | `src/empirical_platform/usecases/paper_execution.py` | `test_a_tampered_account_in_the_persisted_boundary_record_blocks_attribution` | **EXECUTED_PASS** | detected; restored to `839371632b5fde7f` |

