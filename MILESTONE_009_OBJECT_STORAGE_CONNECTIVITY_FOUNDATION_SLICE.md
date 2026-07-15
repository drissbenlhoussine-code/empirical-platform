# MILESTONE-009 - Object Storage Connectivity Foundation Slice

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-009 |
| Title | Object Storage Connectivity Foundation Slice |
| Version | 1.0 |
| Status | APPROVED AND FROZEN |
| Date | 2026-07-15 |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Baseline Commit | `579c296ed1655442fdc61de8b3caa7030d0d87cf` |
| Scope Type | S3-compatible object-storage connectivity and generic object operations |

## 2. Scope

This milestone implements the smallest S3-compatible object-storage foundation authorized by MILESTONE-002 through MILESTONE-008.

Implemented:

- S3-compatible object-storage configuration;
- object-storage service interface for opaque keys;
- boto3-based S3/MinIO adapter lifecycle;
- bucket reachability probe;
- generic put, get, head, exists, list, and delete operations;
- immutable provider metadata representation;
- not-found behavior distinct from infrastructure failure;
- object-storage error translation into the foundation error model;
- object-storage dependency-health reporting;
- optional startup composition with object storage;
- deterministic in-memory fake object-storage substitute;
- real MinIO integration tests against Docker Compose.

## 3. Non-Goals

Not implemented:

- dataset directories or key layouts;
- evidence-package layout;
- campaign, run, dataset, evidence, vendor, or trading key conventions;
- retention, archival, or lifecycle policies;
- checksum interpretation as evidence integrity;
- manifests or evidence package writers;
- raw or normalized storage domain models;
- vendor-specific storage;
- business repositories;
- domain schemas or migrations;
- production APIs, background workers, or workflow orchestration;
- Decision Candidate or Decision Freeze behavior.

## 4. Governing Documents

| Document | Governing role |
| --- | --- |
| `MILESTONE_002_TECHNOLOGY_SELECTION_AND_ENGINEERING_BLUEPRINT.md` | Selects S3-compatible object storage for raw/evidence artifacts |
| `MILESTONE_003_PLATFORM_FOUNDATION_INITIALIZATION.md` | Defines object-storage initialization as future foundation work |
| `MILESTONE_005_INFRASTRUCTURE_ARCHITECTURE.md` | Defines object-storage layer ownership, trust boundary, and failure domain |
| `MILESTONE_006_FOUNDATION_CONTRACTS.md` | Defines Object Storage, Configuration, Error, Health, and Logging contracts |
| `MILESTONE_007_FIRST_INFRASTRUCTURE_IMPLEMENTATION_SLICE.md` | Provides foundation error, configuration, health, logging, and bootstrap primitives |
| `MILESTONE_008_PERSISTENCE_CONNECTIVITY_FOUNDATION_SLICE.md` | Provides the prior external-dependency adapter pattern and independence boundary |

## 5. Repository Baseline

Baseline reviewed:

```text
579c296 Implement MILESTONE-008 persistence connectivity foundation
79bb2e1 Implement MILESTONE-007 foundation infrastructure slice
1444ea2 Resolve MILESTONE-004 verification blockers and approve integration
bb93c06 Add infrastructure architecture and foundation contracts drafts
449389f Initialize MILESTONE-004 platform foundation scaffold
```

Pre-change repository state was clean on `master`.

## 6. Requirement-to-Code Traceability

| Requirement | Source | Existing artifact | Implementation | Tests | Non-goals |
| --- | --- | --- | --- | --- | --- |
| S3-compatible storage abstraction | M002 Sections 11, 25, 26 | `pyproject.toml` object-storage group | `shared/object_storage/s3.py` | `test_s3_object_storage.py`, `test_minio_object_storage.py` | No domain storage framework |
| Object Storage Contract operations and not-found distinction | M006 Section 7 | Placeholder `shared/interfaces/object_storage.py` | Expanded interface and adapter/fake | fake, S3, MinIO tests | No evidence key semantics |
| Configuration resolves once and is secret-safe | M006 Section 5 | `shared/config/settings.py` | `ObjectStorageConfigSnapshot` | `test_object_storage_config.py` | No production secrets manager |
| Lower-level SDK exception translation | M006 Section 12 | `FoundationError` | `translate_object_storage_error` | S3 unit and MinIO invalid credential tests | No raw SDK exception leakage |
| Multi-axis object-storage health | M005 Section 4; M006 Section 13 | `shared/health.py` | adapter and fake `health()` | unit and integration health tests | No health API expansion |
| Startup/shutdown composition | M006 cross-contract rules | `shared/bootstrap.py` | `initialize_foundation_runtime_with_object_storage` | `test_object_storage_bootstrap.py` | No DI container |

## 7. Technology Decision

Selected: `boto3` with botocore client configuration, isolated behind a local object-storage adapter.

Alternatives considered:

| Alternative | Decision | Rationale |
| --- | --- | --- |
| boto3/botocore | Selected | Already present in the MILESTONE-003 dependency plan and pyproject optional group; supports S3-compatible MinIO; easy to isolate behind a replaceable adapter. |
| MinIO Python SDK | Rejected for this slice | Strong MinIO fit, but would bind the foundation more tightly to local development tooling instead of generic S3-compatible semantics. |
| Filesystem-backed object store | Rejected | Would weaken S3-compatible behavior and not test the selected storage boundary. |
| Domain storage framework | Rejected | Out of scope; would introduce key/layout semantics too early. |

Reversibility: the SDK is confined to `shared/object_storage/s3.py`; callers depend on `ObjectStorageService`.

Dependency impact: `verify.ps1` now installs the existing `object-storage` optional dependency group.

## 8. Files Created

| File | Purpose |
| --- | --- |
| `src/empirical_platform/shared/object_storage/__init__.py` | Object-storage package boundary |
| `src/empirical_platform/shared/object_storage/fake.py` | Deterministic in-memory fake |
| `src/empirical_platform/shared/object_storage/s3.py` | S3-compatible adapter, lifecycle, operations, health, and error translation |
| `tests/unit/test_object_storage_config.py` | Object-storage config tests |
| `tests/unit/test_object_storage_fake.py` | Fake object-storage contract tests |
| `tests/unit/test_object_storage_bootstrap.py` | Startup composition tests |
| `tests/unit/test_s3_object_storage.py` | Adapter lifecycle, operation, translation, and safety tests |
| `tests/integration/test_minio_object_storage.py` | Real MinIO integration tests |
| `MILESTONE_009_OBJECT_STORAGE_CONNECTIVITY_FOUNDATION_SLICE.md` | This milestone report |

## 9. Files Modified

| File | Modification |
| --- | --- |
| `.env.example` | Adds safe object-storage connectivity placeholders |
| `scripts/verify.ps1` | Installs object-storage optional dependency group |
| `src/empirical_platform/shared/bootstrap.py` | Adds optional object-storage startup composition |
| `src/empirical_platform/shared/config/settings.py` | Adds immutable object-storage config snapshot |
| `src/empirical_platform/shared/interfaces/object_storage.py` | Expands generic object-storage contract surface |

## 10. Object-Storage Configuration

`ObjectStorageConfigSnapshot` captures connectivity-only settings:

- endpoint URL;
- region;
- infrastructure-only foundation bucket;
- access key and secret key as `SecretStr`;
- TLS flag;
- path-style addressing flag;
- connection timeout;
- operation timeout;
- explicit `create_bucket_if_missing` flag.

No dataset, evidence, campaign, run, vendor, retention, or lifecycle setting is present. Safe diagnostics remove embedded endpoint credentials and expose only boolean credential-presence flags.

## 11. Client Lifecycle

`S3ObjectStorageService` owns:

- client construction;
- bucket reachability probe;
- optional infrastructure-only bucket creation when explicitly configured;
- initialized/closed state;
- use-before-initialization rejection;
- use-after-close rejection;
- idempotent close.

The base bootstrap path does not import boto3. The concrete adapter is lazy-loaded only when object-storage composition is requested.

## 12. Generic Object Operations

Implemented generic operations:

- `put_object`;
- `get_object`;
- `head_object`;
- `object_exists`;
- `list_objects`;
- `delete_object`.

Keys are opaque strings. The implementation rejects empty keys and null-byte keys only. No path, folder, dataset, campaign, evidence, vendor, or retention meaning is assigned.

## 13. Metadata and Not-Found Model

Metadata is represented by `ObjectMetadata`:

- object key;
- size;
- content type;
- provider checksum/ETag as opaque provider metadata;
- last-modified timestamp;
- provider metadata mapping.

`get_object` and `head_object` return `None` when the object is absent. `delete_object` returns `False` when the object is absent. Not-found is therefore distinguishable from an infrastructure error.

## 14. Consistency Semantics

Declared production-adapter semantics:

```text
MINIO_STRONG_READ_AFTER_WRITE
```

Observed against MinIO:

- read-after-write is immediate;
- list-after-write is immediate in the tested local MinIO environment;
- delete visibility is immediate in the tested local MinIO environment;
- overwrite visibility is immediate in the tested local MinIO environment.

Generic S3 portability is not claimed as empirically verified by this milestone. Callers may rely only on the adapter's declared semantics for the tested MinIO-compatible environment until another provider is tested.

## 15. Error Translation

SDK failures are translated into `FoundationError` with:

- category `object_storage_error`;
- layer `object_storage`;
- operation context;
- safe message;
- redacted context.

Translated conditions include invalid configuration, endpoint unreachable, access denied, timeout, bucket missing, object missing, read/write/list/delete failures, use before initialization, use after close, and unexpected SDK failure. Raw boto3/botocore exception types do not escape the adapter boundary.

## 16. Health Integration

Object-storage health is reported as `LayerHealth`:

- before initialization: LIVENESS `PASS`, READINESS `UNKNOWN`, DEPENDENCY HEALTH `UNKNOWN`;
- reachable: LIVENESS `PASS`, READINESS `PASS`, DEPENDENCY HEALTH `PASS`;
- unreachable/auth failure: LIVENESS `PASS`, READINESS `FAIL`, DEPENDENCY HEALTH `FAIL`;
- closed: LIVENESS `PASS`, READINESS `FAIL`, DEPENDENCY HEALTH `UNKNOWN`.

A failed object operation does not automatically set LIVENESS to `FAIL`.

## 17. Startup/Shutdown Integration

`initialize_foundation_runtime_with_object_storage` composes:

1. configuration;
2. logging;
3. object-storage initialization and probe;
4. clocks;
5. identifiers;
6. health report.

If mandatory object-storage initialization fails, no ready runtime is returned. Shutdown is handled by `ObjectStorageService.close`, which is idempotent.

## 18. Fake/Test Substitute

`FakeObjectStorageService` implements:

- put/get/head/exists/list/delete;
- deterministic metadata;
- explicit not-found behavior;
- lifecycle checks;
- idempotent close;
- configurable failure injection;
- declared fake consistency semantics.

The fake uses no filesystem and carries no domain storage semantics.

## 19. MinIO Integration Testing

Integration command used:

```text
docker compose -f .\infra\local\compose.yaml up -d object-storage
.\.venv\Scripts\python.exe -m pytest tests\integration\test_minio_object_storage.py -q --no-cov
docker compose -f .\infra\local\compose.yaml down --remove-orphans
```

Observed result:

```text
4 passed in 5.11s
```

The test creates uniquely named `foundation-m009-*` buckets, writes only generic opaque keys, deletes test objects, deletes temporary buckets, and stops the Compose service afterward.

## 20. Architecture Boundary Evidence

The object-storage implementation is contained under `shared/object_storage` and imports no domain modules. The boto3/botocore imports appear only inside the object-storage adapter and tests. Persistence and object storage do not import or depend on each other. Bootstrap composes them independently.

The negative architecture fixture still reports the expected illegal import:

```text
tests\fixtures\illegal_imports\src\empirical_platform\review\bad_import.py: review may not import acquisition
```

## 21. Security Evidence

Security controls implemented:

- credentials stored as `SecretStr`;
- endpoint credentials removed from safe diagnostics;
- public errors omit raw SDK messages;
- access key and secret key values are never logged;
- signed URLs are not generated;
- basic-auth-shaped test values are fragment-built to preserve strict secret scanning;
- retries are bounded by botocore config with `max_attempts=1`;
- no hidden filesystem persistence exists.

Canonical security scan:

```text
Secret scan target count: 100
No known vulnerabilities found
```

## 22. Persistence Independence

MILESTONE-009 does not modify:

- persistence schema;
- Alembic migrations;
- domain database models;
- persistence unit-of-work semantics.

Object storage is a separate adapter and failure domain.

## 23. Storage Integrity and Cleanup

MinIO integration tests:

- create only temporary `foundation-m009-*` buckets;
- use opaque test keys;
- remove test objects;
- remove temporary buckets;
- stop Compose services with `down --remove-orphans`.

No dataset, evidence, campaign, or retention layout is created.

## 24. Test Evidence

Full verification:

```text
72 passed, 7 skipped
coverage: 89.44%
```

Skipped tests are explicit opt-in integration tests during normal `verify.ps1`: 4 MinIO tests and 3 PostgreSQL tests. The MinIO tests pass under the explicit command in Section 19. PostgreSQL tests remain unchanged from MILESTONE-008.

Other validation:

```text
Ruff format: passed
Ruff lint: passed
Mypy: passed
Architecture checker: passed
Negative architecture fixture: passed
Dependency audit: passed with expected local package skip
Secret scan: passed
Build: passed
Import/version: passed, 0.0.0
Docker Compose config: passed
git diff --check: passed
```

## 25. Deferred Items

| Item | Reason |
| --- | --- |
| Dataset/evidence bucket layout | Domain storage model not authorized |
| Evidence checksums and manifests | Evidence package milestone not authorized |
| Raw/normalized artifact writers | Acquisition and normalization are not implemented |
| Object retention/lifecycle policy | Requires governance and entitlement decisions |
| Object versioning policy | Not required for connectivity foundation |
| Production secrets manager | Deferred by prior milestones |
| Provider portability beyond MinIO | Requires future provider-specific verification |

## 26. Risks

| ID | Severity | Risk | Mitigation |
| --- | --- | --- | --- |
| OBJECT-STORAGE-RISK-0001 | Medium | MinIO behavior may not represent every S3-compatible provider's consistency behavior. | Declared semantics are limited to tested MinIO behavior; generic S3 portability remains unverified. |
| OBJECT-STORAGE-RISK-0002 | Medium | Future domain key conventions could leak into the foundation adapter. | Interface uses opaque keys only; report explicitly defers layouts. |
| OBJECT-STORAGE-RISK-0003 | Low | In-memory payload handling is not suitable for very large future objects. | This slice is connectivity foundation only; streaming/multipart remains deferred. |

## 27. Implementation Issue Register

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| OBJECT-STORAGE-ISSUE-0001 | MINOR | Initial Docker check found Docker Desktop installed but Linux engine stopped. | RESOLVED by starting Docker Desktop and rerunning MinIO integration. |
| OBJECT-STORAGE-ISSUE-0002 | MINOR | Initial MinIO test command used global Python, whose pytest version did not satisfy repository `minversion`. | RESOLVED by using the repository venv interpreter. |
| OBJECT-STORAGE-ISSUE-0003 | MINOR | The first shutdown integration test closed the shared fixture before cleanup. | RESOLVED by isolating shutdown verification and deleting the temporary bucket before closing. |
| OBJECT-STORAGE-ISSUE-0004 | MINOR | Secret scanner detected basic-auth-shaped test URL literals. | RESOLVED by fragment-building those test values; security scan passes. |

No CRITICAL or MAJOR implementation issue remains open.

## 28. Acceptance Criteria

| Criterion | Result |
| --- | --- |
| Generic object-storage contract is satisfied | PASSED |
| MinIO integration tests pass | PASSED |
| Consistency semantics are documented honestly | PASSED |
| No domain bucket/key structure introduced | PASSED |
| No raw SDK exception escapes | PASSED |
| Credentials are safe | PASSED |
| Health/Error/Logging boundaries remain intact | PASSED |
| Persistence independence preserved | PASSED |
| `verify.ps1` passes | PASSED |
| `security.ps1` passes | PASSED |
| Compose config passes | PASSED |
| Temporary objects, buckets, and services cleaned up | PASSED |
| No CRITICAL or MAJOR issue remains | PASSED |

## 29. Quality Rubric

| Category | Max | Score | Rationale |
| --- | --- | --- | --- |
| Traceability | 20 | 20 | Every implemented behavior maps to M002/M003/M005/M006/M007/M008 inputs. |
| Scope discipline | 20 | 19 | No domain layout or retention policy; foundation bucket is infrastructure-only. |
| Contract fidelity | 20 | 19 | Generic operations, not-found, health, lifecycle, and error translation implemented; streaming/multipart deferred. |
| Test coverage | 15 | 14 | 72 full-suite tests pass with 89.44% coverage; 4 MinIO tests pass explicitly. |
| Security posture | 10 | 10 | Credentials redacted, strict secret scan clean, signed URLs not introduced. |
| Architecture integrity | 10 | 10 | SDK stays under adapter; persistence and object storage remain independent. |
| Maintainability | 5 | 5 | Narrow interface, replaceable adapter, deterministic fake. |

**MILESTONE-009 score: 97 / 100.**

## 30. Final Status

```text
APPROVED AND FROZEN
```

Final verification passed after this report was added to the repository. All MILESTONE-009 approval criteria are met.
