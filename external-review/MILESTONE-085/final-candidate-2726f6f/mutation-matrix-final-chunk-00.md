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
| `broker_uncertainty_width` | The bound is as wide as the measured round trip | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_the_uncertainty_width_is_exactly_the_measured_round_trip` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `broker_clock_monotonicity` | A broker clock moving backwards refuses | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_a_broker_clock_that_moves_backwards_is_refused` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `broker_certainty_margin` | Time too uncertain to decide the freshness margin refuses | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_uncertainty_at_or_beyond_the_margin_is_refused[60.0]` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `authorization_basis_pairs_the_post_response_host_reading` | The basis pairs the broker timestamp with the host reading AFTER the response | `src/empirical_platform/shared/brokerage/paper_time.py` | `test_broker_fetch_latency_cannot_extend_the_authorization_deadline` | **EXECUTED_PASS** | detected; restored to `547393f9ec018f98` |
| `authorization_basis_interval_required` | An authorization without an interval-shaped basis is not dispatchable | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_replaced_pre_fetch_pairing_is_no_longer_trusted` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `broker_basis_required` | An authorization carrying a basis cannot be checked without broker time | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_basis_cannot_be_checked_without_broker_time` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `broker_basis_authorization_expiry` | An approval expires on the broker's clock, through its own basis | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_host_clock_ahead_only_while_authorizing_cannot_extend_the_authorization` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `authorization_not_future_dated_against_its_basis` | authorized_at may not postdate the host reading its expiry is mapped with | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_future_dated_authorization_cannot_be_mapped` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `m084_deadline_on_proposal_time_basis` | M084 deadlines are enforced on the broker's clock through the proposal's own basis | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_intent_deadline_is_mapped_through_the_proposal_basis` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `m084_deadline_never_through_a_later_basis` | A deadline written at evaluation is never translated through the issuance basis | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_intent_deadline_is_mapped_through_the_proposal_basis` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `proposal_basis_required` | A proposal evaluated without its own basis cannot be issued for Paper | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `decision_basis_required` | An approval recorded without its own basis cannot be issued for Paper | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `proposal_basis_matches_the_exact_proposal` | Proposal evidence describing different deadlines is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_proposal_evidence_describing_another_proposal_refuses_the_preview` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `approval_before_proposal_expiry_on_broker_time` | An approval recorded after the proposal expired on the broker's clock is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_approval_recorded_after_the_proposal_expired_is_refused` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `approval_expiry_at_issuance_through_the_decision_basis` | An intent issued after the approval expired on the broker's clock is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_approval_that_expired_before_issuance_is_refused` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |
| `stale_proposal_refused_at_issuance` | Issuance is refused when a deadline it relies on passed on the broker's clock | `src/empirical_platform/usecases/paper_execution.py` | `test_the_chain_is_refused_somewhere_and_nothing_is_sent` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `approval_refused_for_a_proposal_expired_on_broker_time` | A human cannot approve a proposal that may have expired on the broker's clock | `src/empirical_platform/usecases/paper_execution.py` | `test_a_proposal_that_expired_on_the_broker_clock_cannot_be_approved` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `evaluation_uses_the_measured_host_reading` | The proposal is evaluated at the basis host reading, not at an unmeasured instant | `src/empirical_platform/usecases/paper_execution.py` | `test_the_proposal_is_evaluated_at_the_host_reading_taken_after_the_clock_response` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `decision_uses_the_measured_host_reading` | The approval is decided at the basis host reading, not at an unmeasured instant | `src/empirical_platform/usecases/paper_execution.py` | `test_an_approval_is_decided_at_the_host_reading_taken_after_the_clock_response` | **EXECUTED_PASS** | detected; restored to `fcdcf3383a1e7ec7` |
| `intent_basis_required` | An intent issued without its own basis is not dispatchable | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_intent_without_its_own_basis_is_refused_before_any_broker_call` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |

