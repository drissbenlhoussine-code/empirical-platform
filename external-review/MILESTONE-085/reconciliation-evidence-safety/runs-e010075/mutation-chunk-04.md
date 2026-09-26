# MILESTONE-085 — Mutation Matrix

**18 of 18 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `cbb5318236d04147c30eb9c031d9abbebcb833bac2f38578d63a406dc0689389`, after `cbb5318236d04147c30eb9c031d9abbebcb833bac2f38578d63a406dc0689389`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `lineage_unsent_never_attributed` | An attempt recorded as not having sent can never be attributed a found order | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_event_recording_no_send_outranks_a_state_that_would_otherwise_qualify[SUBMISSION_UNKNOWN-AMBIGUOUS-CLIENT_ORDER_ID_COLLISION]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `unknown_error_code_is_uncertain` | A refusal code Alpaca does not document for that status proves nothing | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_unknown_or_inconsistent_semantics_are_uncertain` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `terms_compare_limit_price` | A broker order with another limit price is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[limit_price-5.00]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `terms_compare_time_in_force` | A broker order with another time_in_force is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[time_in_force-gtc]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `terms_compare_extended_hours` | A broker order with another extended_hours flag is never ours | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_every_authorized_term_is_compared[extended_hours-True]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `terms_compare_bound_broker_order_id` | A broker id already bound to the attempt must stay consistent | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_bound_broker_order_id_must_stay_consistent` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `lineage_requires_the_send_boundary_record` | SUBMISSION_IN_PROGRESS alone is preparation; lineage needs the persisted boundary | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_death_during_the_pre_send_lookup_leaves_no_lineage` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `send_boundary_record_is_bound_field_by_field` | A boundary record lends lineage only when every bound field is this attempt's | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_boundary_record_that_does_not_bind_lends_no_lineage[authorization_id]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `send_boundary_recorded_before_the_send` | The send-capable boundary is persisted before the request can leave | `src/empirical_platform/usecases/paper_execution.py` | `test_our_own_post_then_death_before_acknowledgement_is_recovered_without_resending` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `final_checks_follow_the_boundary_write` | The kill switch is read after the boundary write, which may block | `src/empirical_platform/usecases/paper_execution.py` | `test_the_kill_switch_engaged_during_the_boundary_write_stops_the_post` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `historical_adoption_requires_the_account_binding` | Reconciliation verifies the boundary record against the authorized account | `src/empirical_platform/usecases/paper_execution.py` | `test_a_tampered_account_in_the_persisted_boundary_record_blocks_attribution` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `absence_counts_only_the_consecutive_suffix` | The bounded policy counts the trailing consecutive not-found run, not every 404 | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_unusable_answer_breaks_the_consecutive_not_found_run` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `lookup_failure_breaks_the_absence_run` | A recorded lookup failure breaks the consecutive not-found run | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_lookup_that_raises_is_recorded_and_breaks_the_run` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `lookup_failure_is_recorded` | A reconciliation lookup that raises leaves an event behind | `src/empirical_platform/usecases/paper_execution.py` | `test_a_lookup_that_raises_is_recorded_and_breaks_the_run` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `absence_never_rejects_a_known_order` | A bound, acknowledged order is never rejected because a lookup said 404 | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_never_rejects_a_previously_accepted_order` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `absence_never_revokes_a_positive_observation` | An UNKNOWN whose identity was positively observed is never resolved by absence | `src/empirical_platform/usecases/paper_execution.py` | `test_absence_never_discards_a_prior_positive_observation` | **EXECUTED_PASS** | detected; restored to `b394b64c097bb004` |
| `binding_parser_rejects_padding_and_duplicates` | A boundary record with more or fewer than the canonical tokens is rejected whole | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole[identical-duplicate-appended]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `binding_parser_requires_canonical_keys` | Each token must carry the canonical key for its position | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole[fields-out-of-canonical-order]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |

