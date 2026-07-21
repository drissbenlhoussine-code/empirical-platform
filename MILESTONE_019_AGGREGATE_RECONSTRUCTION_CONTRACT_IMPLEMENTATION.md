# MILESTONE-019 - Aggregate Reconstruction Contract Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-019 |
| Title | Aggregate Reconstruction Contract Implementation |
| Version | 1.0 |
| Status | IMPLEMENTATION COMPLETE - PENDING INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Baseline | `2200357194bf44ce0c60b0b2160b0605f2455b54` |
| Mission type | Implementation only |
| Repositories, schemas, migrations, APIs, workers, or runtime composition created | No |
| Aggregate source files modified | No |

## 2. Scope

This implementation provides persistence-neutral reconstruction contracts for exactly four frozen process-local aggregates:

- Campaign;
- Run;
- EvidencePackage;
- Review.

The implementation does not provide persistence, repository contracts, mapper contracts, schemas, migrations, serialization, application services, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze, trading logic, vendor behavior, or empirical execution behavior.

## 3. Files Changed

Created:

- `src/empirical_platform/shared/domain/reconstruction.py`;
- `src/empirical_platform/campaign/_reconstruction.py`;
- `src/empirical_platform/run/_reconstruction.py`;
- `src/empirical_platform/evidence/_reconstruction.py`;
- `src/empirical_platform/review/_reconstruction.py`;
- `tests/unit/test_aggregate_reconstruction.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/campaign/bad_persistence_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/review/bad_sqlalchemy_import.py`;
- `MILESTONE_019_AGGREGATE_RECONSTRUCTION_CONTRACT_IMPLEMENTATION.md`.

Modified:

- `src/empirical_platform/shared/domain/__init__.py`;
- `tools/check_architecture.py`;
- `tests/architecture/test_module_boundaries.py`.

## 4. Shared Error Model

Implemented in:

```text
empirical_platform.shared.domain.reconstruction
```

Implemented:

- `ReconstructionErrorCategory`;
- `ReconstructionError`.

The error categories are exactly the frozen M019 categories. The error constructor accepts:

```text
ReconstructionError(category, message, *, field=None, context=None)
```

No database, SQLAlchemy, psycopg, S3, MinIO, object-storage, repository, runtime, or infrastructure error category was added.

## 5. Shared Helper Boundary

The shared reconstruction module contains only narrowly identical helper behavior:

- iterable materialization into immutable tuples;
- element-type verification;
- simple runtime instance checking;
- common transition-history sequence, identity, edge, current-state, terminal-following, and next-sequence validation.

Aggregate lifecycle matrices, version floors, terminal metadata, duplicate collection rules, collection identity rules, current-manifest derivation, and Review finding-sequence semantics remain aggregate-specific.

## 6. State Records

Implemented immutable slots-based reconstruction state records:

| Aggregate | State record | Module |
| --- | --- | --- |
| Campaign | `CampaignReconstructionState` | `empirical_platform.campaign._reconstruction` |
| Run | `RunReconstructionState` | `empirical_platform.run._reconstruction` |
| EvidencePackage | `EvidencePackageReconstructionState` | `empirical_platform.evidence._reconstruction` |
| Review | `ReviewReconstructionState` | `empirical_platform.review._reconstruction` |

State records perform structural validation and tuple materialization only. They are not ORM models, serializers, repositories, schemas, mappers, API DTOs, events, or persistence models.

## 7. Factories

Implemented internal factories:

| Aggregate | Factory | Construction mechanism |
| --- | --- | --- |
| Campaign | `_reconstruct_campaign` | `object.__new__(Campaign)` after validation |
| Run | `_reconstruct_run` | `object.__new__(Run)` after validation |
| EvidencePackage | `_reconstruct_evidence_package` | `object.__new__(EvidencePackage)` after validation |
| Review | `_reconstruct_review` | `object.__new__(Review)` after validation |

Factories do not call public constructors, public lifecycle methods, public content mutation methods, clocks, repositories, persistence services, object storage, event dispatch, audit emission, or outbox behavior.

## 8. Version Floors

Implemented floors:

- Campaign: version must be at least the highest transition-history version; positive `DRAFT` version with empty history is allowed for prior scope revisions.
- Run: version must be at least the maximum of highest transition-history version and manifest count.
- EvidencePackage: version must be at least the maximum of highest transition-history version and count of Criterion Results plus ArtifactReferences.
- Review: version must be at least the maximum of highest transition-history version and finding count.

Versions are restored exactly and are never incremented during reconstruction.

## 9. History Validation

Implemented common history validation:

- canonical `StateTransitionRecord` type;
- identity match when identity reference is present;
- first transition from canonical initial state;
- sequence begins at `1`;
- sequence is contiguous;
- lifecycle edge is allowed by the aggregate;
- final transition state matches restored current state;
- terminal transition is not followed by another transition;
- next transition sequence equals last sequence plus one;
- empty-history legality is aggregate-specific.

Timestamp monotonicity is not validated. Timestamps, actors, reasons, and correlation IDs are preserved as historical facts.

## 10. Collection Rules

Implemented:

- Run manifest order preservation, Run identity matching, duplicate non-null manifest ID rejection, and repeated unidentified manifest allowance.
- EvidencePackage Criterion Result order preservation, package identity matching, duplicate criterion ID rejection, ArtifactReference order preservation, and duplicate exact artifact value rejection.
- Review finding order preservation and contiguous positive finding sequence validation. Duplicate finding text remains allowed.

No collection is sorted, merged, normalized, deduplicated, repaired, overwritten, or silently discarded.

## 11. Terminal Metadata Rules

Implemented:

- Campaign post-authorization cancellation requires a final transition reason.
- Run `FAILED` and `CANCELLED` require final transition reasons.
- EvidencePackage `SEALED` and `INVALIDATED` require results and artifact references; `INVALIDATED` requires final transition reason.
- Review `COMPLETED` requires findings, disposition, and final rationale; `CANCELLED` requires cancellation reason and no disposition; non-terminal states reject terminal metadata.

## 12. Architecture Changes

The architecture checker now rejects infrastructure imports from domain reconstruction boundaries that are currently enforceable:

- `empirical_platform.shared.persistence`;
- `sqlalchemy`;
- `psycopg`;
- `boto3`.

Negative fixtures were added for Campaign persistence import and Review SQLAlchemy import. Existing module-boundary rules were not weakened.

## 13. Tests

Added focused unit tests for:

- shared error categories and constructor shape;
- state-record immutability, slots, and tuple materialization;
- successful Campaign, Run, EvidencePackage, and Review reconstruction;
- positive `DRAFT` Campaign version;
- terminal Campaign restoration;
- Run current-manifest derivation and unidentified manifest behavior;
- EvidencePackage sealed and invalidated restoration;
- Review completed and cancelled restoration;
- wrong factory input type;
- malformed history;
- identity mismatch;
- transition after terminal state;
- version floor rejection;
- collection identity and duplicate rejection;
- terminal metadata rejection;
- public export absence.

Architecture tests verify the new negative fixtures.

## 14. Validation Evidence

Validation was run during implementation:

```text
python -m pytest tests/unit/test_aggregate_reconstruction.py tests/architecture/test_module_boundaries.py --no-cov
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
python -m ruff format .
python -m ruff check .
python -m mypy
```

Observed full-suite evidence before final report creation:

- Python: `3.13.14`;
- focused reconstruction and architecture tests: `25 passed`;
- full test suite: `244 passed, 9 skipped`;
- coverage: `91.93%`;
- secret scan target count: `185`;
- architecture checker: passed;
- negative fixtures: passed;
- build/import/version checks: passed.

Final validation must be rerun before commit.

## 15. Hostile Self-Review

| ID | Severity | Finding | Correction | Disposition |
| --- | --- | --- | --- | --- |
| M019-IMPLEMENTATION-ISSUE-0001 | MAJOR | Initial architecture-checker rule blocked existing `shared.bootstrap` because it broadly forbade `shared.persistence` imports from all shared modules. | Narrowed the rule to shared domain modules only. | Resolved |
| M019-IMPLEMENTATION-ISSUE-0002 | MAJOR | Shared reconstruction initially imported `DomainIdentity`, reversing the shared-to-identifiers dependency direction. | Removed the identifier import and made shared history validation accept an opaque identity object. | Resolved |
| M019-IMPLEMENTATION-ISSUE-0003 | MINOR | State-record annotations initially used `Iterable` after post-init tuple materialization. | Changed state fields to tuple annotations while preserving defensive runtime materialization. | Resolved |
| M019-IMPLEMENTATION-ISSUE-0004 | MINOR | Focused tests initially missed several hostile malformed cases. | Added tests for terminal-following-history, identity mismatch, version floors, invalidated evidence, cancelled review, and unidentified manifests. | Resolved |
| M019-IMPLEMENTATION-ISSUE-0005 | MAJOR | EvidencePackage history validation initially treated `SEALED` as a terminal lifecycle state, rejecting the frozen `SEALED -> INVALIDATED` transition path. | Changed EvidencePackage terminal-following validation so only `INVALIDATED` blocks later transitions. Sealed content immutability remains aggregate behavior, not terminal-history blocking. | Resolved |
| M019-IMPLEMENTATION-ISSUE-0006 | MAJOR | Campaign reconstruction initially accepted histories missing reasons for frozen Campaign transitions that require reasons: authorization, activation, suspension, resume, completion, and post-authorization cancellation. | Added aggregate-specific Campaign transition reason validation and regression tests while preserving optional pre-authorization reason paths. | Resolved |

No unresolved M019 implementation issue remains in this report.

## 16. Explicit Non-Goals Confirmed

Not implemented:

- repository contracts or implementations;
- persistence mappers;
- serializers;
- SQL;
- ORM;
- schemas;
- migrations;
- PostgreSQL persistence;
- Unit of Work;
- transactions;
- optimistic concurrency save behavior;
- APIs;
- workers;
- schedulers;
- outbox;
- runtime composition;
- Audit;
- Decision Candidate;
- Decision Freeze;
- event sourcing;
- trading logic;
- market data;
- vendor behavior;
- production execution.

`migrations/versions` remains empty.

## 17. Final Status

```text
IMPLEMENTATION COMPLETE - PENDING INDEPENDENT REVIEW
```
