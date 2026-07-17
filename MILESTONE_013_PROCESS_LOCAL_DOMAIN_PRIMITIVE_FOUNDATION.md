# MILESTONE-013 - Process-Local Domain Primitive Foundation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-013 |
| Title | Process-Local Domain Primitive Foundation |
| Version | 1.0 |
| Status | APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Baseline | `8a5f1eb1e4eb850ea46f7f8d8ad355318cbe2cbe` |
| Mission type | Implementation slice |
| Implementation scope | Process-local immutable domain primitives only |
| Commit policy | Not staged and not committed by this mission |

## 2. Scope

This milestone implements the approved process-local domain primitive slice selected by `MILESTONE_013_DOMAIN_KERNEL_IMPLEMENTATION_SCOPE_SELECTION.md`.

The implementation is limited to:

- Campaign lifecycle enum;
- Run lifecycle enum;
- Evidence Package lifecycle enum;
- Review lifecycle enum;
- Review disposition enum;
- `AggregateVersion`;
- `TransitionSequence`;
- `StateTransitionRecord`;
- governance/runtime identity-pairing helper;
- immutable Dataset Manifest primitive;
- immutable Criterion Result primitive;
- focused unit tests and architecture-boundary verification.

## 3. Baseline Verification

Required baseline:

```text
8a5f1eb1e4eb850ea46f7f8d8ad355318cbe2cbe
```

Verified repository state before implementation:

- branch: `master`;
- HEAD: `8a5f1eb1e4eb850ea46f7f8d8ad355318cbe2cbe`;
- working tree: clean.

## 4. Package Placement

| Package | Added primitive responsibility | Boundary rationale |
| --- | --- | --- |
| `empirical_platform.shared.domain` | `AggregateVersion`, `TransitionSequence`, `StateTransitionRecord` | Shared, process-local primitives with no dependency on domain packages, persistence, storage, or entrypoints |
| `empirical_platform.identifiers` | `DomainIdentity`, `pair_identity` | Identifier pairing reuses existing governance ID wrappers and runtime UUID type |
| `empirical_platform.campaign` | Campaign and Run lifecycle enums | Run has no separate package; MILESTONE-012 places Run under campaign-oriented runtime behavior |
| `empirical_platform.datasets` | `DatasetManifest` | Dataset Manifest is conceptually owned by Run and remains storage-layout-neutral |
| `empirical_platform.evidence` | Evidence Package lifecycle enum and `CriterionResult` | Criterion Result is conceptually owned by Evidence Package |
| `empirical_platform.review` | Review lifecycle enum and Review disposition enum | Review lifecycle and disposition remain separate |

## 5. Requirement-to-Code Traceability

| Requirement | Code | Tests |
| --- | --- | --- |
| Campaign lifecycle enum | `src/empirical_platform/campaign/lifecycle.py` | `tests/unit/test_domain_lifecycle_primitives.py` |
| Run lifecycle enum | `src/empirical_platform/campaign/lifecycle.py` | `tests/unit/test_domain_lifecycle_primitives.py` |
| Evidence Package lifecycle enum | `src/empirical_platform/evidence/lifecycle.py` | `tests/unit/test_domain_lifecycle_primitives.py` |
| Review lifecycle enum | `src/empirical_platform/review/lifecycle.py` | `tests/unit/test_domain_lifecycle_primitives.py` |
| Review disposition enum | `src/empirical_platform/review/lifecycle.py` | `tests/unit/test_domain_lifecycle_primitives.py` |
| AggregateVersion | `src/empirical_platform/shared/domain/versioning.py` | `tests/unit/test_domain_versioning_and_transitions.py` |
| TransitionSequence | `src/empirical_platform/shared/domain/versioning.py` | `tests/unit/test_domain_versioning_and_transitions.py` |
| StateTransitionRecord | `src/empirical_platform/shared/domain/transitions.py` | `tests/unit/test_domain_versioning_and_transitions.py` |
| Identity pairing | `src/empirical_platform/identifiers/pairs.py` | `tests/unit/test_domain_identity_pairs.py` |
| Dataset Manifest | `src/empirical_platform/datasets/manifest.py` | `tests/unit/test_dataset_manifest_primitive.py` |
| Criterion Result | `src/empirical_platform/evidence/results.py` | `tests/unit/test_criterion_result_primitive.py` |
| Architecture boundary | Existing `tools/check_architecture.py` | Full `scripts/verify.ps1` and architecture test suite |

## 6. Primitive Implementation Details

### Lifecycle Enums

Lifecycle enums are implemented with `StrEnum` and match the frozen MILESTONE-012 state names exactly:

- Campaign: `DRAFT`, `READY_FOR_AUTHORIZATION`, `AUTHORIZED`, `ACTIVE`, `SUSPENDED`, `COMPLETED`, `CANCELLED`;
- Run: `CREATED`, `AUTHORIZED`, `ACQUIRING`, `NORMALIZING`, `VALIDATING`, `EXECUTION_COMPLETED`, `FAILED`, `CANCELLED`;
- Evidence Package: `INITIALIZED`, `COLLECTING`, `SEALED`, `INVALIDATED`;
- Review: `ASSIGNED`, `IN_PROGRESS`, `COMPLETED`, `CANCELLED`.

Archive is not modeled as a lifecycle state. Review disposition is separate from Review lifecycle.

### Review Disposition

Review disposition is implemented as:

- `ACCEPTED`;
- `REJECTED`;
- `CHANGES_REQUESTED`;
- `INCONCLUSIVE`.

These values do not appear in the Review lifecycle enum.

### AggregateVersion

`AggregateVersion` is an immutable, ordered primitive with:

- non-negative validation;
- `initial()` returning `0`;
- `next()` returning a new incremented value.

It does not read or write persistence and does not enforce database concurrency.

### TransitionSequence

`TransitionSequence` is an immutable, ordered primitive with:

- positive validation;
- `initial()` returning `1`;
- `next()` returning a new incremented value.

It is intentionally distinct from `AggregateVersion` and is not an event ID.

### StateTransitionRecord

`StateTransitionRecord` is immutable historical lifecycle data containing:

- optional `from_state`;
- required `to_state`;
- `AggregateVersion`;
- `TransitionSequence`;
- actor;
- timestamp;
- optional typed identity reference;
- optional correlation ID;
- optional reason.

It is not a domain event, event-bus payload, outbox message, or persistence schema.

### DomainIdentity

`DomainIdentity` pairs one existing governance identifier with one existing runtime UUID:

- governance IDs are reused from `empirical_platform.identifiers.types`;
- runtime UUIDs are reused from `empirical_platform.shared.identifiers`;
- the pair does not allocate IDs;
- the pair does not create a registry;
- the pair does not imply persistence.

### DatasetManifest

`DatasetManifest` is immutable and conceptually Run-owned. It records bounded process-local facts:

- `RunId`;
- optional `DatasetId`;
- timestamp;
- source;
- optional acquisition method;
- optional normalization method;
- notes.

It has no bucket, object key, vendor, market-data, retention, or storage-layout semantics.

### CriterionResult

`CriterionResult` is immutable and conceptually Evidence-Package-owned. It records bounded process-local facts:

- `EvidencePackageId`;
- criterion identifier;
- timestamp;
- generic result label;
- optional summary;
- evidence references.

It has no scoring engine, vendor, trading, bucket, object key, or persistence semantics.

## 7. Test and Coverage Evidence

Focused primitive test command:

```powershell
.\.venv\Scripts\python -m pytest tests/unit/test_domain_lifecycle_primitives.py tests/unit/test_domain_versioning_and_transitions.py tests/unit/test_domain_identity_pairs.py tests/unit/test_dataset_manifest_primitive.py tests/unit/test_criterion_result_primitive.py
```

Focused primitive result:

```text
19 passed
Coverage: 82.82%
```

Full verification command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
```

Full verification result:

```text
Python 3.13.14
102 passed, 9 skipped
Coverage: 90.66%
Architecture checker passed
Negative architecture fixture passed
Build passed
Import/version check passed: 0.0.0
```

## 8. Architecture and Security Evidence

Security command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\security.ps1
```

Security result:

```text
security.ps1 passed
Secret scan target count: 148
No known vulnerabilities found
```

Architecture result:

```text
tools/check_architecture.py . passed
tests/fixtures/illegal_imports negative fixture produced the expected violation
```

No framework, database, adapter, object-storage implementation, repository, worker, API, outbox, or job-ledger dependency was introduced by the domain primitives.

## 9. Scope-Integrity Audit

| Scope check | Result |
| --- | --- |
| No Campaign aggregate behavior | PASS |
| No Run aggregate behavior | PASS |
| No Evidence Package aggregate behavior | PASS |
| No Review aggregate behavior | PASS |
| No transition services | PASS |
| No schemas, tables, columns, migrations, or ORM mappings | PASS |
| No repositories | PASS |
| No APIs or workers | PASS |
| No persistence or object-storage implementation changes | PASS |
| No event dispatch, job ledger, or outbox | PASS |
| No Audit runtime | PASS |
| No Decision Candidate or Decision Freeze | PASS |
| No market data, trading logic, vendor behavior, or campaign execution | PASS |
| Lifecycle enums exactly match MILESTONE-012 | PASS |
| Review lifecycle and disposition remain separate | PASS |
| Archive remains outside lifecycle | PASS |
| Dataset Manifest remains storage-layout-neutral and vendor-neutral | PASS |
| Criterion Result remains scoring-engine-neutral and vendor-neutral | PASS |

## 10. Issue Register

| ID | Severity | Description | Resolution |
| --- | --- | --- | --- |
| M013-IMPLEMENTATION-ISSUE-0001 | MINOR | Default shell `python` used an older non-project pytest and could not run the focused tests. | Resolved by running verification through the repository `.venv` interpreter. |
| M013-IMPLEMENTATION-ISSUE-0002 | MINOR | Ruff required Python 3.13 native type-parameter syntax for the generic identity pair helper. | Resolved by converting `DomainIdentity` and `pair_identity` to PEP 695 syntax. |
| M013-IMPLEMENTATION-ISSUE-0003 | MINOR | Initial integer primitives accepted booleans because `bool` subclasses `int` in Python. | Resolved by explicit integer and non-boolean validation for `AggregateVersion` and `TransitionSequence`. |
| M013-IMPLEMENTATION-ISSUE-0004 | MINOR | Initial transition record did not expose optional identity-reference and correlation fields required by acceptance review. | Resolved with a generic optional `identity_reference` and optional `correlation_id` without importing identifier packages into `shared.domain`. |

No CRITICAL or MAJOR implementation issue remains open.

## 11. Files Created

- `src/empirical_platform/shared/domain/__init__.py`
- `src/empirical_platform/shared/domain/versioning.py`
- `src/empirical_platform/shared/domain/transitions.py`
- `src/empirical_platform/identifiers/pairs.py`
- `src/empirical_platform/campaign/lifecycle.py`
- `src/empirical_platform/datasets/manifest.py`
- `src/empirical_platform/evidence/lifecycle.py`
- `src/empirical_platform/evidence/results.py`
- `src/empirical_platform/review/lifecycle.py`
- `tests/unit/test_domain_lifecycle_primitives.py`
- `tests/unit/test_domain_versioning_and_transitions.py`
- `tests/unit/test_domain_identity_pairs.py`
- `tests/unit/test_dataset_manifest_primitive.py`
- `tests/unit/test_criterion_result_primitive.py`
- `MILESTONE_013_PROCESS_LOCAL_DOMAIN_PRIMITIVE_FOUNDATION.md`

## 12. Files Modified

- `src/empirical_platform/identifiers/__init__.py`
- `src/empirical_platform/campaign/__init__.py`
- `src/empirical_platform/datasets/__init__.py`
- `src/empirical_platform/evidence/__init__.py`
- `src/empirical_platform/review/__init__.py`

## 13. Deferred Items

- Campaign aggregate behavior;
- Run aggregate behavior;
- Evidence Package aggregate behavior;
- Review aggregate behavior;
- command handlers and transition services;
- persistence schema design;
- schema/migration implementation;
- repository contracts and concrete repositories;
- event dispatch, event store, job ledger, and transactional outbox;
- audit runtime;
- Decision Candidate runtime;
- Decision Freeze;
- campaign execution and empirical validation behavior.

## 14. Blockers

No blocker remains for this milestone.

Future aggregate behavior remains intentionally deferred to a later milestone.

## 15. Independent Score

| Area | Score | Rationale |
| --- | ---: | --- |
| Scope control | 20 / 20 | Only approved process-local primitives were implemented |
| MILESTONE-012 traceability | 20 / 20 | Lifecycle states and primitive names trace directly to frozen design |
| Immutability and typing | 15 / 15 | Dataclasses are frozen/slotted; enums are typed; tests verify immutability |
| Boundary compliance | 15 / 15 | Architecture checker passed; no infrastructure dependency introduced |
| Test coverage | 15 / 15 | Focused and full suites passed with coverage above threshold |
| Reversibility | 8 / 10 | Primitive names are now public API, but no persistence/API/schema lock-in exists |
| Documentation evidence | 5 / 5 | Implementation report records traceability, evidence, issues, and deferrals |

Total:

```text
98 / 100
```

## 16. Final Status

```text
APPROVED AND FROZEN
```

MILESTONE-013 implements the approved process-local domain primitive foundation without aggregate behavior, persistence, schemas, repositories, APIs, workers, outbox, job ledger, Audit runtime, Decision Candidate runtime, vendor behavior, trading behavior, campaign execution, or Decision Freeze.

## 17. Lifecycle Audit

Lifecycle enums exactly match the frozen MILESTONE-012 state lists.

Excluded states remain absent:

- `ARCHIVED` is not a lifecycle state;
- `REVIEWED` is not an Evidence Package state;
- `VALID` and `INVALID` are not Run execution states;
- `RERUN_REQUIRED` is not a backward Run lifecycle state;
- `ACCEPTED` and `REJECTED` are Review dispositions, not Review lifecycle states.

## 18. Versioning Audit

`AggregateVersion` and `TransitionSequence` are separate immutable runtime types:

- both reject booleans;
- both reject invalid numeric ranges;
- both expose deterministic `initial()` and `next()` behavior;
- neither exposes decrement behavior;
- neither carries persistence, database revision, or event identifier semantics.

## 19. Transition Record Audit

`StateTransitionRecord` is immutable historical data:

- it preserves prior and next state values exactly;
- it preserves `AggregateVersion` and `TransitionSequence` exactly;
- it preserves `occurred_at` exactly;
- it supports optional typed identity reference without importing identifier packages into `shared.domain`;
- it supports optional correlation ID;
- it does not validate lifecycle transition legality;
- it does not dispatch events;
- it has no outbox or ORM semantics.

## 20. Identity Pairing Audit

`DomainIdentity` and `pair_identity` preserve separation between governance identifiers and runtime UUIDs:

- existing governance ID wrappers remain canonical;
- existing runtime UUID wrapper remains canonical;
- invalid inversions are rejected at runtime and by typing where statically visible;
- no global registry, uniqueness service, database-generated ID, Audit runtime, or Decision Candidate runtime is introduced.

## 21. Dataset Manifest Audit

`DatasetManifest` remains:

- immutable;
- conceptually Run-owned;
- not an aggregate root;
- bounded to process-local metadata;
- storage-layout-neutral;
- filesystem-path-neutral;
- provider-neutral;
- vendor-neutral;
- lifecycle-free;
- repository-free;
- persistence-annotation-free.

## 22. Criterion Result Audit

`CriterionResult` remains:

- immutable;
- conceptually Evidence-Package-owned;
- not an aggregate root;
- bounded and generic;
- scoring-engine-neutral;
- statistical-computation-free;
- trading-neutral;
- vendor-neutral;
- lifecycle-free;
- persistence-annotation-free;
- storage-annotation-free.

## 23. Type-Safety Audit

Type-safety review result:

- `mypy` passed in strict project mode;
- Ruff lint passed;
- Ruff format check passed;
- generic identity pairing uses Python 3.13 type-parameter syntax;
- `StateTransitionRecord` uses a generic identity-reference field without weakening the architecture boundary;
- no production `Any`, casts, mutable defaults, dynamic imports, unsafe deserialization, or hidden framework coupling were introduced.

## 24. Security Audit

Security review result:

- `security.ps1` passed;
- no secrets detected;
- secret scan target count: `148`;
- no vulnerable dependency was introduced;
- no dynamic import, arbitrary object execution, or unsafe deserialization was introduced.

## 25. Migration and Infrastructure Integrity

Infrastructure integrity result:

- `migrations/versions` remains empty;
- no migration was created;
- no schema, table, or column definition was added;
- no Compose change was made;
- no PostgreSQL adapter change was made;
- no object-storage adapter change was made;
- Docker services were unnecessary and not started.

## 26. Acceptance Issue Register

| ID | Severity | Description | Disposition |
| --- | --- | --- | --- |
| M013-ACCEPTANCE-ISSUE-0001 | MINOR | Boolean values were not explicitly rejected by numeric primitives in the initial implementation. | Corrected and tested. |
| M013-ACCEPTANCE-ISSUE-0002 | MINOR | Transition record acceptance criteria required optional identity reference and correlation support. | Corrected and tested. |
| M013-ACCEPTANCE-ISSUE-0003 | ADVISORY | Initial report used 16 sections while the review mission expected a 28-section integrity structure. | Corrected by adding Sections 17 through 28. |

No CRITICAL or MAJOR acceptance issue remains open.

## 27. Commit Readiness

MILESTONE-013 is ready for a review-and-commit package if:

- focused tests pass;
- full verification passes;
- security passes;
- architecture checks pass;
- `git diff --check` passes;
- staged files are limited to the reviewed MILESTONE-013 package.

Current review result supports commit readiness.

## 28. Final Acceptance Status

```text
APPROVED AND FROZEN
```

The implementation is ready for a documentation-and-code review commit. MILESTONE-014 has not started.
