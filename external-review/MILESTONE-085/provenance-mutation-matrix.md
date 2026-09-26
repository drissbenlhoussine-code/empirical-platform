# MILESTONE-085 — Provenance Mutation Matrix

> **Superseded by the corrective pass:** see [corrective-pass.md](corrective-pass.md).
> Historical run of the per-act provenance families, blocked run included. The current campaign is `mutation-matrix.md`.

**24 of 24 affected families detected** on the final source, over two sequential runs.
A surviving mutation is a defect, never a pass.

This matrix covers ONLY the families affected by the per-act deadline provenance
correction (`temporal-correction.md`, *"SUPERSEDED A THIRD TIME"*): the new proposal-
and decision-time families, the families whose rule or detecting test this correction
changed, the database families of every M085 time-basis table, and the authority
contract family. The other rows of `mutation-matrix.md` (run 3, 67 of 67) were not
re-run; its row `m084_deadline_on_intent_time_basis` is SUPERSEDED by
`m084_deadline_on_proposal_time_basis` below.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again. Both runs were sequential, with PostgreSQL on (disposable
database `m085_pgon_c7a41f0`) and nothing else writing to the tree; a SHA-256 digest of
every tracked and untracked file (1320) was taken around each run.

| Run | Scope | Result | Tree-wide restoration |
|---|---|---|---|
| 1 | 24 affected families | **23 of 24 detected, 1 blocker** | 1320 files, 0 changed / removed / added |
| 2 | the blocker, detecting fragment corrected | **1 of 1 detected** | 1320 files, 0 changed / removed / added |

The run-1 blocker, corrected in the CAMPAIGN'S EXPECTATION, not in the rule or the test:
`evaluation_uses_the_measured_host_reading` was detected, but the campaign had named
`assert` as the reason. Evaluating the proposal at the pre-request host reading is refused
first by the real domain binder -- *"a basis cannot be attached to a proposal after the
fact"* (`ValueError`) -- before the test's own assertion runs. The expected fragment is
now that refusal, as for the existing `issuance_uses_the_measured_host_reading`.

## Final result per family

| Family | Rule removed | File | Detecting test | Status | Run |
|---|---|---|---|---|---|
| `m084_deadline_on_proposal_time_basis` | M084 deadlines are enforced on the broker's clock through the proposal's own basis | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_intent_deadline_is_mapped_through_the_proposal_basis` | **EXECUTED_PASS** | 1 |
| `m084_deadline_never_through_a_later_basis` | A deadline written at evaluation is never translated through the issuance basis | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_the_intent_deadline_is_mapped_through_the_proposal_basis` | **EXECUTED_PASS** | 1 |
| `proposal_basis_required` | A proposal evaluated without its own basis cannot be issued for Paper | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes` | **EXECUTED_PASS** | 1 |
| `decision_basis_required` | An approval recorded without its own basis cannot be issued for Paper | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_a_proposal_or_approval_without_its_own_basis_is_refused_before_m084_writes` | **EXECUTED_PASS** | 1 |
| `proposal_basis_matches_the_exact_proposal` | Proposal evidence describing different deadlines is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_proposal_evidence_describing_another_proposal_refuses_the_preview` | **EXECUTED_PASS** | 1 |
| `approval_before_proposal_expiry_on_broker_time` | An approval recorded after the proposal expired on the broker's clock is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_approval_recorded_after_the_proposal_expired_is_refused` | **EXECUTED_PASS** | 1 |
| `approval_expiry_at_issuance_through_the_decision_basis` | An intent issued after the approval expired on the broker's clock is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_approval_that_expired_before_issuance_is_refused` | **EXECUTED_PASS** | 1 |
| `stale_proposal_refused_at_issuance` | Issuance is refused when a deadline it relies on passed on the broker's clock | `src/empirical_platform/usecases/paper_execution.py` | `test_the_chain_is_refused_somewhere_and_nothing_is_sent` (PostgreSQL, the reproduced path) | **EXECUTED_PASS** | 1 |
| `approval_refused_for_a_proposal_expired_on_broker_time` | A human cannot approve a proposal that may have expired on the broker's clock | `src/empirical_platform/usecases/paper_execution.py` | `test_a_proposal_that_expired_on_the_broker_clock_cannot_be_approved` | **EXECUTED_PASS** | 1 |
| `evaluation_uses_the_measured_host_reading` | The proposal is evaluated at the basis host reading, not at an unmeasured instant | `src/empirical_platform/usecases/paper_execution.py` | `test_the_proposal_is_evaluated_at_the_host_reading_taken_after_the_clock_response` | **EXECUTED_PASS** | 2 |
| `decision_uses_the_measured_host_reading` | The approval is decided at the basis host reading, not at an unmeasured instant | `src/empirical_platform/usecases/paper_execution.py` | `test_an_approval_is_decided_at_the_host_reading_taken_after_the_clock_response` | **EXECUTED_PASS** | 1 |
| `intent_basis_required` | An intent issued without its own basis is not dispatchable | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_an_intent_without_its_own_basis_is_refused_before_any_broker_call` | **EXECUTED_PASS** | 1 |
| `intent_basis_matches_the_exact_intent` | Evidence describing a different intent is refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_evidence_describing_a_different_intent_is_refused[expires_at]` | **EXECUTED_PASS** | 1 |
| `intent_basis_bound_to_issuance` | An intent-time basis cannot be attached after the intent was issued | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_intent_evidence_cannot_be_attached_after_issuance` | **EXECUTED_PASS** | 1 |
| `issuance_uses_the_measured_host_reading` | The intent is issued at the basis host reading, not at an unmeasured instant | `src/empirical_platform/usecases/paper_execution.py` | `test_the_intent_is_issued_at_the_host_reading_taken_after_the_clock_response` | **EXECUTED_PASS** | 1 |
| `final_intent_expiry` | Intent expiry is checked after preparation | `src/empirical_platform/usecases/paper_execution.py` | `test_elapsed_work_cannot_extend_a_deadline[intent-prepare]` | **EXECUTED_PASS** | 1 |
| `database_single_use_trigger` | The database refuses a second consumption | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_a_second_consumption_is_refused_by_the_trigger` | **EXECUTED_PASS** | 1 |
| `database_intent_basis_matches_intent` | The database refuses evidence that does not describe the exact stored intent | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_evidence_describing_another_intent_is_refused[expires_at]` | **EXECUTED_PASS** | 1 |
| `database_intent_basis_bound_to_issuance` | The database refuses evidence whose host reading is not the issuance instant | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_evidence_not_bound_to_the_issuance_instant_is_refused` | **EXECUTED_PASS** | 1 |
| `database_proposal_basis_matches_proposal` | The database refuses proposal evidence that does not describe the stored proposal | `migrations/versions/e61b3f9a4c27_add_m085_proposal_and_decision_time_basis.py` | `test_proposal_evidence_describing_another_proposal_is_refused[expires_at]` | **EXECUTED_PASS** | 1 |
| `database_decision_basis_matches_approval` | The database refuses decision evidence that does not describe the stored approval | `migrations/versions/e61b3f9a4c27_add_m085_proposal_and_decision_time_basis.py` | `test_decision_evidence_describing_another_approval_is_refused[decision_expires_at]` | **EXECUTED_PASS** | 1 |
| `database_proposal_basis_bound_to_evaluation` | The database refuses proposal evidence whose host reading is not the evaluation | `migrations/versions/e61b3f9a4c27_add_m085_proposal_and_decision_time_basis.py` | `test_proposal_evidence_not_bound_to_the_evaluation_instant_is_refused` | **EXECUTED_PASS** | 1 |
| `database_decision_basis_bound_to_decision` | The database refuses decision evidence whose host reading is not the decision | `migrations/versions/e61b3f9a4c27_add_m085_proposal_and_decision_time_basis.py` | `test_decision_evidence_not_bound_to_the_decision_instant_is_refused` | **EXECUTED_PASS** | 1 |
| `authority_contract_reads_the_sql_installed_at_head` | An enforcement claim is checked against the guard installed at head | `migrations/versions/d4f18a6c2e97_add_m085_intent_time_basis.py` | `test_every_database_enforcement_claim_names_sql_installed_at_head` | **EXECUTED_PASS** | 1 |

## The authority family, against the contract it replaces

The same mutation -- the expiry message removed from the guard `d4f18a6c2e97` installs --
was applied in a detached worktree at `73a2f96` and that commit's contract test was run:
`test_every_database_enforcement_claim_names_something_in_the_migration` **15 passed**.
The replaced contract read only `b1e9d47c30a5`, where the superseded guard still carries
the message, so it could not see the rule removed from the SQL a database at head runs.
The worktree was restored and left clean.
