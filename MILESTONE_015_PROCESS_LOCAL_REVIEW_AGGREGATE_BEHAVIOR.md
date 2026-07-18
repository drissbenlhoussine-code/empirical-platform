# MILESTONE-015 - Process-Local Review Aggregate Behavior

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-015 |
| Title | Process-Local Review Aggregate Behavior |
| Version | 1.0 |
| Status | IMPLEMENTED / AWAITING INDEPENDENT FREEZE REVIEW |
| Implementation baseline | `d45f44389997c34984b28a22661ce54d76584bef` |
| Scope authority | `MILESTONE_015_PROCESS_LOCAL_REVIEW_AGGREGATE_BEHAVIOR_SCOPE_SELECTION.md` |
| Implementation type | Process-local aggregate behavior only |
| Persistence introduced | No |
| Schemas or migrations introduced | No |
| APIs or workers introduced | No |

## 2. Scope Summary

This milestone implements exactly one process-local aggregate:

```text
Review
```

The Review aggregate reviews exactly one Evidence Package by immutable `EvidencePackageId` target reference. It does not load, inspect, validate, or mutate the target.

## 3. Requirement-to-Code Traceability

| Requirement | Implementation | Test evidence |
| --- | --- | --- |
| `DomainIdentity[ReviewId]` identity | `Review.identity` in `src/empirical_platform/review/aggregate.py` | `test_construction_sets_assigned_identity_target_reviewer_and_empty_content` |
| Evidence-Package-only target | `ReviewTargetReference` | `test_target_reference_is_evidence_package_only_and_immutable` |
| Opaque reviewer reference | `ReviewerReference` | `test_reviewer_reference_is_opaque_data_only_and_immutable` |
| Initial state `ASSIGNED` | `Review.__init__` | construction tests |
| `ASSIGNED -> IN_PROGRESS` | `Review.start` | start tests |
| Findings only while `IN_PROGRESS` | `Review.add_finding` | finding tests |
| Finding sequence deterministic | `ReviewFinding.sequence` assigned by aggregate | finding and mixed-operation tests |
| Completion requires finding, disposition, rationale | `Review.complete` | completion tests |
| Cancellation requires reason | `Review.cancel` | cancellation tests |
| Terminal immutability | transition guards and content guards | terminal immutability tests |
| Content version increments | `AggregateVersion.next()` on finding append | finding tests |
| Lifecycle sequence increments only on transitions | `TransitionSequence.next()` inside `_transition` | lifecycle and mixed-operation tests |
| Transition history is historical data only | `StateTransitionRecord` tuple | lifecycle tests |
| Rejection atomicity | validation before mutation | rejection snapshot tests |

## 4. Implemented Files

| File | Purpose |
| --- | --- |
| `src/empirical_platform/review/aggregate.py` | Implements `Review`, `ReviewTargetReference`, `ReviewerReference`, and `ReviewFinding` |
| `src/empirical_platform/review/__init__.py` | Exports the M015 Review public surface |
| `tests/unit/test_review_aggregate.py` | Focused construction, lifecycle, finding, disposition, cancellation, terminal, boundary, and atomicity tests |
| `MILESTONE_015_PROCESS_LOCAL_REVIEW_AGGREGATE_BEHAVIOR.md` | Implementation report |

## 5. Aggregate Design

### Identity

`Review` requires `DomainIdentity[ReviewId]`.

It rejects:

- non-`DomainIdentity` identity values;
- `DomainIdentity` values whose `governance_id` is not `ReviewId`.

Governance identifier and runtime UUID separation remains delegated to the canonical `DomainIdentity` primitive.

### Target

`ReviewTargetReference` is immutable and contains:

- `target_kind = "EVIDENCE_PACKAGE"`;
- one `EvidencePackageId`.

It does not contain Run target support, target lifecycle state, object-storage location, repository reference, or target existence validation.

### Reviewer Reference

`ReviewerReference` is immutable opaque local data:

- value must be a non-empty string;
- value grants no authority;
- value proves no reviewer independence;
- value is not an authentication identity.

### Lifecycle

Initial state:

```text
ASSIGNED
```

Allowed transitions:

```text
ASSIGNED -> IN_PROGRESS
ASSIGNED -> CANCELLED
IN_PROGRESS -> COMPLETED
IN_PROGRESS -> CANCELLED
```

Terminal states:

```text
COMPLETED
CANCELLED
```

No reopen, revision, withdrawal, replacement, supersession, or arbitrary transition method is implemented.

### Findings

`ReviewFinding` is immutable and aggregate-owned.

Fields:

- `sequence`;
- `text`;
- optional `rationale`;
- optional tuple of opaque evidence-reference strings.

Findings are append-only and may be added only while the Review is `IN_PROGRESS`.

### Disposition and Rationale

`ReviewDisposition` remains separate from lifecycle state.

Disposition:

- starts unset;
- is set exactly once during successful completion;
- requires non-empty final disposition rationale;
- does not mutate the target;
- does not trigger Audit, Decision Candidate, Decision Freeze, or downstream behavior.

### Cancellation

Cancellation:

- is allowed from `ASSIGNED` or `IN_PROGRESS`;
- requires a non-empty reason;
- stores cancellation reason;
- leaves disposition and final disposition rationale unset.

## 6. Invariant Table

| Invariant | Enforcement point | Allowed behavior | Rejected behavior | Version effect | Sequence effect | History effect | Atomicity evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Review identity is `DomainIdentity[ReviewId]` | constructor | valid identity | wrong identity type or governance ID | none | none | none | construction tests |
| Target is Evidence Package only | `ReviewTargetReference` | `EvidencePackageId` | `RunId` or other object | none | none | none | target tests |
| Reviewer reference is non-empty opaque data | `ReviewerReference` | non-empty string | blank, whitespace, non-string | none | none | none | reviewer tests |
| Findings only while in progress | `add_finding` | append in `IN_PROGRESS` | append in `ASSIGNED`, `COMPLETED`, `CANCELLED` | +1 on success | unchanged | unchanged | finding and terminal tests |
| Completion requires local content | `complete` | finding plus disposition plus rationale | no finding, invalid disposition, blank rationale | +1 on success | +1 on success | one record | completion tests |
| Cancellation requires reason | `cancel` | non-empty reason | blank or non-string reason | +1 on success | +1 on success | one record | cancellation tests |
| Terminal states are immutable | all mutators | none after terminal | content or lifecycle mutation | unchanged | unchanged | unchanged | terminal tests |

## 7. Lifecycle Matrix

| Current state | Operation | Next state | Allowed/rejected | Version | Sequence | History |
| --- | --- | --- | --- | --- | --- | --- |
| `ASSIGNED` | `start` | `IN_PROGRESS` | Allowed | +1 | +1 | append one transition |
| `ASSIGNED` | `cancel` | `CANCELLED` | Allowed | +1 | +1 | append one transition |
| `ASSIGNED` | `complete` | none | Rejected | unchanged | unchanged | unchanged |
| `IN_PROGRESS` | `add_finding` | `IN_PROGRESS` | Allowed | +1 | unchanged | unchanged |
| `IN_PROGRESS` | `complete` | `COMPLETED` | Allowed with findings, disposition, rationale | +1 | +1 | append one transition |
| `IN_PROGRESS` | `cancel` | `CANCELLED` | Allowed with reason | +1 | +1 | append one transition |
| `COMPLETED` | any mutation | none | Rejected | unchanged | unchanged | unchanged |
| `CANCELLED` | any mutation | none | Rejected | unchanged | unchanged | unchanged |

## 8. Content Mutation Matrix

| Operation | Required state | Validation | Version | Sequence | History | Rejection behavior |
| --- | --- | --- | --- | --- | --- | --- |
| `add_finding` | `IN_PROGRESS` | text non-empty; optional rationale/reference non-empty; references tuple | +1 | unchanged | unchanged | full observable state unchanged |
| `complete` | `IN_PROGRESS` | at least one finding; valid disposition; final rationale non-empty | +1 | +1 | append one transition | full observable state unchanged |
| `cancel` | `ASSIGNED` or `IN_PROGRESS` | cancellation reason non-empty | +1 | +1 | append one transition | full observable state unchanged |

## 9. Validation Evidence

Final validation:

| Command | Result |
| --- | --- |
| `python --version` | `Python 3.13.14` |
| `powershell -ExecutionPolicy Bypass -File .\scripts\security.ps1` | Passed; secret scan target count `156`; no known vulnerabilities found |
| `powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1` | Passed; `141 passed`, `9 skipped`; coverage `92.32%` |
| `python -m pytest tests\unit\test_review_aggregate.py --no-cov` | `22 passed` |
| `python -m ruff format --check .` | `91 files already formatted` |
| `python -m ruff check .` | `All checks passed` |
| `python -m mypy` | `Success: no issues found in 55 source files` |
| `python tools\check_architecture.py .` | Passed |
| `git diff --check` | Passed with Git LF-to-CRLF working-copy warning only |

## 10. Scope-Integrity Audit

| Check | Result |
| --- | --- |
| No persistence introduced | PASS |
| No repository introduced | PASS |
| No schema or migration introduced | PASS |
| No API or worker introduced | PASS |
| No outbox or event dispatch introduced | PASS |
| No Audit runtime introduced | PASS |
| No Decision Candidate runtime introduced | PASS |
| No Decision Freeze introduced | PASS |
| No target lookup introduced | PASS |
| No target mutation introduced | PASS |
| No reviewer authority enforcement introduced | PASS |
| No reviewer independence enforcement introduced | PASS |
| No trading, vendor, market-data, or campaign execution behavior introduced | PASS |

## 11. Issue Register

| Issue ID | Severity | Finding | Resolution |
| --- | --- | --- | --- |
| M015-IMPLEMENTATION-ISSUE-0001 | MINOR | Initial focused test run identified repeated completion error text that did not expose terminal state. | Error message was tightened while preserving behavior; focused tests passed afterward. |
| M015-IMPLEMENTATION-ISSUE-0002 | MINOR | Independent hostile review found missing explicit tests for duplicate finding content semantics, all canonical dispositions, completion after cancellation, non-string final rationale, and non-string evidence-reference entries. | Added M015-scoped contract tests without changing aggregate behavior; final focused and full validation passed. |

No MAJOR or CRITICAL implementation issues remain.

## 12. Deferred Items

Deferred beyond MILESTONE-015:

- Run-target Review behavior;
- Run aggregate behavior;
- Campaign aggregate behavior;
- reviewer independence gate execution;
- reviewer authority and authentication;
- target existence or lifecycle validation;
- duplicate active Review prevention for the same target;
- stale-review reconciliation after evidence invalidation;
- Audit runtime;
- Decision Candidate runtime;
- persistence schema and repository design;
- APIs, workers, job ledger, outbox, and orchestration.

## 13. Hostile Review

Post-implementation hostile review checks:

| Check | Result |
| --- | --- |
| Unsupported identity semantics | PASS |
| Reviewer authority leakage | PASS |
| Governance/runtime identity confusion | PASS |
| Target existence or lifecycle lookup | PASS |
| Cross-aggregate behavior | PASS |
| Disposition/lifecycle conflation | PASS |
| Terminal immutability | PASS |
| Version and sequence behavior | PASS |
| Mutable findings | PASS |
| Infrastructure leakage | PASS |
| Broad abstractions | PASS |
| Migration changes | PASS |

## 14. Final Status

```text
IMPLEMENTED / AWAITING INDEPENDENT FREEZE REVIEW
```

MILESTONE-015 is implemented but not frozen. Freeze requires a separate independent hostile-review mission.
