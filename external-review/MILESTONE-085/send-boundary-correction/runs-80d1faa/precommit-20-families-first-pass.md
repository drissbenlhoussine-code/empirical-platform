# MILESTONE-085 — Mutation Matrix

**18 of 20 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `a8560ced7042068ebe7f9700fc6094f79420c429bddab351b9a3e633b1edf1d9`, after `a8560ced7042068ebe7f9700fc6094f79420c429bddab351b9a3e633b1edf1d9`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `response_identity_validation` | An acknowledgement about another order is refused | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_mismatched_acknowledgement_fails_closed[override0-client_order_id]` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `response_quantity_validation` | An acknowledgement for a different quantity is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_mismatched_acknowledgement_fails_closed[override3-quantity]` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `duplicate_identity_422_is_not_a_refusal` | Alpaca's duplicate client_order_id 422 is an existing identity, never a refusal | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_documented_duplicate_answer_is_an_existing_identity` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `identity_collision_looks_the_identity_up` | A collision is resolved by looking up the SAME client_order_id, not by guessing | `src/empirical_platform/usecases/paper_execution.py` | `test_an_exact_match_found_before_sending_is_observed_not_adopted` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `pre_send_lookup_uses_the_derived_identity` | The identity asked about before sending is the derived one, not a replacement | `src/empirical_platform/usecases/paper_execution.py` | `test_an_exact_match_found_before_sending_is_observed_not_adopted` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |
| `reconcile_refuses_a_mismatching_order` | Reconciliation never adopts a broker order that differs from the authorized one | `src/empirical_platform/usecases/paper_execution.py` | `test_a_differing_term_is_never_adopted_even_with_lineage[symbol-TSLA]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `send_boundary_no_read_after_the_decision` | Nothing sits between the final decision and the transport's POST | `src/empirical_platform/usecases/paper_execution.py` | `test_the_boundary_reads_everything_before_the_kill_switch_and_samples_time_last` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `send_boundary_kill_switch_read_after_the_slow_reads` | The kill switch is read fresh after the slow reads, not from the pre-claim snapshot | `src/empirical_platform/usecases/paper_execution.py` | `test_the_kill_switch_engaged_during_a_slow_read_stops_the_post[lookup]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `send_boundary_time_sampled_after_the_reads` | Deadlines are judged on time sampled after every slow read | `src/empirical_platform/usecases/paper_execution.py` | `test_the_authorization_expiring_during_a_slow_read_stops_the_post[lookup]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `inconclusive_lookup_is_not_a_rejection` | An inconclusive pre-send identity lookup is recoverable, not a terminal refusal | `src/empirical_platform/usecases/paper_execution.py` | `test_it_becomes_unknown_with_nothing_sent[http-500]` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `unresolved_identity_recovered_after_restart` | A new process reconciles an unresolved identity instead of leaving it | `src/empirical_platform/usecases/paper_execution.py` | `test_after_a_restart_a_successful_lookup_surfaces_the_order_without_attributing_it` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `reconcile_requires_lineage_before_adoption` | An order under our identity is adopted only by an attempt that may have sent it | `src/empirical_platform/usecases/paper_execution.py` | `test_nothing_is_ever_resent_and_no_later_authorization_reopens_it` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `reconcile_verifies_the_account` | A found order is adopted only when the broker client's account is the authorized one | `src/empirical_platform/usecases/paper_execution.py` | `test_an_account_that_is_not_the_authorized_one_is_never_adopted` | **EXECUTED_PASS** | detected; restored to `ce8c362456349df3` |
| `lineage_unsent_never_attributed` | An attempt recorded as not having sent can never be attributed a found order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_pre_send_observation_did_not_transmit` | **EXECUTED_FAIL_BLOCKER** | THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it. |
| `unknown_error_code_is_uncertain` | A refusal code Alpaca does not document for that status proves nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_unknown_or_inconsistent_semantics_are_uncertain` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `acknowledgement_terms_compared_canonically` | Our own POST's acknowledgement is compared on every authorized term | `src/empirical_platform/shared/brokerage/alpaca_paper.py` | `test_a_differing_acknowledgement_is_uncertain` | **EXECUTED_PASS** | detected; restored to `75f2c9d28442a370` |
| `terms_compare_limit_price` | A broker order with another limit price is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[limit_price-5.00]` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `terms_compare_time_in_force` | A broker order with another time_in_force is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[time_in_force-gtc]` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `terms_compare_extended_hours` | A broker order with another extended_hours flag is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[extended_hours-True]` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |
| `terms_compare_bound_broker_order_id` | A broker id already bound to the attempt must stay consistent | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_bound_broker_order_id_must_stay_consistent` | **EXECUTED_PASS** | detected; restored to `08dc76f828f401b2` |

## Blockers

- `pre_send_lookup_uses_the_derived_identity`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.
- `lineage_unsent_never_attributed`: THE MUTATION SURVIVED. The named test still passes with the rule removed, so it does not detect it.

