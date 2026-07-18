# MILESTONE-014 - Process-Local Evidence Package Aggregate Behavior

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-014 |
| Title | Process-Local Evidence Package Aggregate Behavior |
| Version | 1.0 |
| Status | APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen architecture baseline | `09bbce8e750deff730e250e35cd5a9cf8b1fe5e1` |
| Implementation baseline | `68bddce850552299ba3faf8a94cb328f312ccb60` |
| Mission type | Implementation slice |
| Implementation scope | Process-local Evidence Package aggregate behavior only |

## 2. Scope

This milestone implements one process-local Evidence Package aggregate root selected by `MILESTONE_014_PROCESS_LOCAL_AGGREGATE_BEHAVIOR_SCOPE_SELECTION.md`.

The implementation is limited to:

- `EvidencePackage` aggregate root;
- `ArtifactReference` value object;
- local lifecycle transitions;
- aggregate version increments;
- transition sequence progression;
- transition history recording;
- immutable Criterion Result and artifact-reference collection exposure;
- focused unit tests.

## 3. Package Placement

| Package | Responsibility |
| --- | --- |
| `empirical_platform.evidence.package` | Process-local aggregate root and opaque artifact-reference value object |
| `empirical_platform.evidence.__init__` | Public evidence package exports |
| `tests.unit.test_evidence_package_aggregate` | Focused aggregate behavior, invariant, and boundary tests |

## 4. Requirement-to-Code Traceability

| Requirement | Code | Tests |
| --- | --- | --- |
| Evidence Package identity | `EvidencePackage.identity` | construction tests |
| Run parent context | `EvidencePackage.run_id` | construction tests |
| Initial lifecycle state | `EvidencePackage.__init__` | construction tests |
| Lifecycle transitions | `start_collection`, `seal`, `invalidate` | lifecycle tests |
| Version increments | `AggregateVersion.next()` usage | content and lifecycle tests |
| Transition sequence | `TransitionSequence.next()` usage | lifecycle tests |
| Transition history | `StateTransitionRecord` append | lifecycle tests |
| Criterion Result collection | `add_criterion_result` | content tests |
| Artifact-reference collection | `ArtifactReference`, `add_artifact_reference` | content tests |
| Atomic rejection | validate-before-mutate implementation | rejection tests |
| Deferred boundaries | no infrastructure dependencies | boundary tests and architecture checker |

## 5. Aggregate Design

`EvidencePackage` is a concrete process-local aggregate root. It is not a base class, framework, command handler, repository, event source, or persistence model.

The aggregate stores:

- `DomainIdentity[EvidencePackageId]`;
- immutable parent `RunId`;
- `EvidencePackageLifecycleState`;
- `AggregateVersion`;
- next `TransitionSequence`;
- tuple of `StateTransitionRecord`;
- tuple of `CriterionResult`;
- tuple of `ArtifactReference`.

All collection views are tuples. No mutable collection is exposed.

## 6. Lifecycle Semantics

Allowed lifecycle transitions:

| From | Operation | To |
| --- | --- | --- |
| `INITIALIZED` | `start_collection` | `COLLECTING` |
| `COLLECTING` | `seal` | `SEALED` |
| `SEALED` | `invalidate` | `INVALIDATED` |

Each accepted lifecycle transition:

- increments `AggregateVersion` exactly once;
- appends exactly one `StateTransitionRecord`;
- records the current `TransitionSequence`;
- advances the next `TransitionSequence` exactly once.

Construction does not append lifecycle history.

## 7. Content Mutation Semantics

`CriterionResult` and `ArtifactReference` additions are allowed only during `COLLECTING`.

Each accepted content addition:

- increments `AggregateVersion` exactly once;
- does not append lifecycle transition history;
- does not advance `TransitionSequence`.

Duplicate `CriterionResult.criterion_id` values are rejected within one Evidence Package.

Duplicate exact `ArtifactReference.value` values are rejected within one Evidence Package.

## 8. Atomicity

Rejected operations mutate nothing.

The implementation validates all preconditions before assigning new aggregate state. Unit tests snapshot and compare identity, Run ID, lifecycle state, version, next transition sequence, transition history, Criterion Result collection, and artifact-reference collection across rejection paths.

## 9. Boundary Compliance

The implementation does not introduce:

- persistence;
- repositories;
- schemas;
- migrations;
- SQLAlchemy mappings;
- APIs;
- workers;
- job ledger;
- transactional outbox;
- event dispatch;
- object-storage layout;
- object-storage clients;
- filesystem clients;
- Campaign, Run, Review, Audit, or Decision Candidate aggregate behavior;
- trading, vendor, market-data, campaign-execution, or Decision Freeze behavior.

`migrations/versions` remains empty.

## 10. Initial Issue Register

| ID | Severity | Description | Disposition |
| --- | --- | --- | --- |
| M014-IMPLEMENTATION-ISSUE-0001 | MINOR | Initial focused pytest command passed behavior tests but failed the global coverage threshold because it intentionally ran only one test file. | Resolved by using `--no-cov` for focused behavior tests and full `verify.ps1` for canonical project coverage. |
| M014-IMPLEMENTATION-ISSUE-0002 | MINOR | Initial implementation required formatting and line-length cleanup. | Resolved with `ruff format` and `ruff check --fix`; final formatting and lint passed. |
| M014-IMPLEMENTATION-ISSUE-0003 | MINOR | Hostile review identified untested deterministic rejection branches for wrong content object types, wrong timestamp type, and non-string invalidation reason. | Resolved with focused atomicity tests. |
| M014-IMPLEMENTATION-ISSUE-0004 | MINOR | Independent hostile review identified missing explicit tests for seal failure with only artifact references and repeated invalidation rejection. | Resolved with focused atomicity tests and correction commit. |

No CRITICAL or MAJOR implementation issue remains open.

## 11. Deferred Items

- Campaign aggregate behavior;
- Run aggregate behavior;
- Review aggregate behavior;
- Audit runtime;
- Decision Candidate runtime;
- persistence schemas and repositories;
- APIs and workers;
- job ledger and outbox;
- object-storage layout and retention policy;
- campaign execution and empirical validation.

## 12. Test and Validation Evidence

Focused MILESTONE-014 command:

```powershell
python -m pytest tests/unit/test_evidence_package_aggregate.py --no-cov
```

Focused result:

```text
17 passed before hostile-review correction; 17 passed after correction
```

Static validation:

```text
ruff format --check: passed
ruff check: passed
mypy: passed in strict mode across 54 source files
architecture checker: passed
negative architecture fixture: produced expected review/acquisition violation
git diff --check: passed
```

Security validation:

```text
Python 3.13.14
security.ps1 passed
Secret scan target count: 152
No known vulnerabilities found
```

Full verification:

```text
Python 3.13.14
119 passed, 9 skipped
Coverage: 91.48%
Architecture checker passed
Negative architecture fixture passed
Build passed
Import/version check passed: 0.0.0
```

## 13. Hostile Review

| Check | Result |
| --- | --- |
| Scope creep | PASS |
| Frozen architecture violation | PASS |
| Persistence leakage | PASS |
| Infrastructure leakage | PASS |
| Cross-aggregate lookup or mutation | PASS |
| Unsupported lifecycle behavior | PASS |
| Incorrect version increments | PASS |
| Incorrect transition-sequence increments | PASS |
| False transition-history entries for content additions | PASS |
| Mutable collection exposure | PASS |
| Duplicate-rule enforcement | PASS |
| Rejection atomicity | PASS |
| Deferred functionality introduced | PASS |
| `migrations/versions` empty | PASS |

## 14. Independent Score

| Area | Score | Rationale |
| --- | ---: | --- |
| Scope control | 20 / 20 | Only one process-local Evidence Package aggregate was implemented |
| MILESTONE-012 and MILESTONE-014 traceability | 20 / 20 | Lifecycle, ownership, duplicate, and versioning rules follow frozen scope |
| Local invariant enforcement | 18 / 20 | All accepted local invariants are enforced without external lookup |
| Atomicity and immutability | 15 / 15 | Tests prove rejection preservation and tuple collection exposure |
| Boundary compliance | 15 / 15 | No persistence, storage, repository, API, worker, or cross-aggregate dependency was introduced |
| Test and validation evidence | 15 / 15 | Focused and full suites passed with coverage above threshold |
| Reversibility | 8 / 10 | Public aggregate API is now established, but no schema, repository, or integration lock-in exists |

Total:

```text
96 / 100
```

## 15. Final Status

```text
APPROVED AND FROZEN
```
