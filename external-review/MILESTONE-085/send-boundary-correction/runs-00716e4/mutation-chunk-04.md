# MILESTONE-085 — Mutation Matrix

**20 of 20 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `b484179c2fb15454b7115b07dd79d3a3f522bef110634fcbe3b723ec86da973e`, after `b484179c2fb15454b7115b07dd79d3a3f522bef110634fcbe3b723ec86da973e`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `identity_match_checks_the_symbol` | A broker order with another symbol is never adopted as ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_field_is_a_collision[symbol-TSLA]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `identity_match_checks_the_quantity` | A broker order with another quantity is never adopted as ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_field_is_a_collision[quantity-2]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `identity_match_checks_the_side` | A broker order with another side is never adopted as ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_field_is_a_collision[side-sell]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `reconcile_recovers_unknown_after_restart` | A new process reconciles an UNKNOWN attempt instead of leaving it | `src/empirical_platform/usecases/paper_execution.py` | `test_an_unknown_attempt_is_recovered_by_a_new_process_through_the_same_identity` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `reconcile_refuses_a_mismatching_order` | Reconciliation never adopts a broker order that differs from the authorized one | `src/empirical_platform/usecases/paper_execution.py` | `test_a_differing_term_is_never_adopted_even_with_lineage[symbol-TSLA]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `database_rebuilt_meets_existing_identity` | Against PostgreSQL, a rebuilt database meets the broker's order and sends nothing | `src/empirical_platform/usecases/paper_execution.py` | `test_a_rebuilt_database_observes_the_brokers_order_without_attributing_or_sending` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `send_boundary_no_read_after_the_decision` | Nothing sits between the final decision and the transport's POST | `src/empirical_platform/usecases/paper_execution.py` | `test_the_boundary_reads_everything_before_the_kill_switch_and_samples_time_last` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `send_boundary_kill_switch_read_after_the_slow_reads` | The kill switch is read fresh after the slow reads, not from the pre-claim snapshot | `src/empirical_platform/usecases/paper_execution.py` | `test_the_kill_switch_engaged_during_a_slow_read_stops_the_post[lookup]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `send_boundary_time_sampled_after_the_reads` | Deadlines are judged on time sampled after every slow read | `src/empirical_platform/usecases/paper_execution.py` | `test_the_authorization_expiring_during_a_slow_read_stops_the_post[lookup]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `inconclusive_lookup_is_not_a_rejection` | An inconclusive pre-send identity lookup is recoverable, not a terminal refusal | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_with_nothing_sent[http-500]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `unresolved_identity_recovered_after_restart` | A new process reconciles an unresolved identity instead of leaving it | `src/empirical_platform/usecases/paper_execution.py` | `test_after_a_restart_a_successful_lookup_surfaces_the_order_without_attributing_it` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `reconcile_requires_lineage_before_adoption` | An order under our identity is adopted only by an attempt that may have sent it | `src/empirical_platform/usecases/paper_execution.py` | `test_nothing_is_ever_resent_and_no_later_authorization_reopens_it` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `reconcile_verifies_the_account` | A found order is adopted only when the broker client's account is the authorized one | `src/empirical_platform/usecases/paper_execution.py` | `test_an_account_that_is_not_the_authorized_one_is_never_adopted` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `lineage_unsent_never_attributed` | An attempt recorded as not having sent can never be attributed a found order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_event_recording_no_send_outranks_a_state_that_would_otherwise_qualify[SUBMISSION_UNKNOWN-AMBIGUOUS-CLIENT_ORDER_ID_COLLISION]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `unknown_error_code_is_uncertain` | A refusal code Alpaca does not document for that status proves nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_unknown_or_inconsistent_semantics_are_uncertain` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `acknowledgement_terms_compared_canonically` | Our own POST's acknowledgement is compared on every authorized term | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_differing_acknowledgement_is_uncertain` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `terms_compare_limit_price` | A broker order with another limit price is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[limit_price-5.00]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `terms_compare_time_in_force` | A broker order with another time_in_force is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[time_in_force-gtc]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `terms_compare_extended_hours` | A broker order with another extended_hours flag is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[extended_hours-True]` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |
| `terms_compare_bound_broker_order_id` | A broker id already bound to the attempt must stay consistent | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_bound_broker_order_id_must_stay_consistent` | **EXECUTED_PASS** | detected; restored to `1d7c8ed263d5b86e` |

