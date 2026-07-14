# MILESTONE-008 - Persistence Connectivity Foundation Slice

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-008 |
| Title | Persistence Connectivity Foundation Slice |
| Version | 1.0 |
| Status | APPROVED AND FROZEN |
| Date | 2026-07-15 |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Baseline Commit | `79bb2e1c4c863d23d5f42e78a07dad9be096e32f` |
| Scope Type | PostgreSQL connectivity and transaction foundation |

## 2. Scope

This milestone implements the smallest PostgreSQL persistence foundation authorized by MILESTONE-002 through MILESTONE-007.

Implemented:

- PostgreSQL connectivity configuration;
- SQLAlchemy engine and connection lifecycle;
- connectivity probe using `SELECT 1`;
- bounded unit-of-work with commit and rollback semantics;
- driver exception translation into `FoundationError`;
- persistence dependency-health reporting;
- optional startup composition with PostgreSQL persistence;
- deterministic fake persistence substitute;
- real PostgreSQL integration tests against Docker Compose.

## 3. Non-Goals

Not implemented:

- domain tables, schemas, migrations, or seed data;
- repositories for campaign, run, dataset, evidence, review, audit, or decision entities;
- vendor, market-data, trading, or empirical-validation persistence;
- object-storage adapter or bucket/key layout;
- authentication tables;
- job ledger, transactional outbox tables, or audit event ledger tables;
- production API, UI, workers, or orchestration workflows;
- Decision Candidate or Decision Freeze behavior.

## 4. Governing Documents

| Document | Governing role |
| --- | --- |
| `MILESTONE_002_TECHNOLOGY_SELECTION_AND_ENGINEERING_BLUEPRINT.md` | Selects PostgreSQL 17, modular monolith, PostgreSQL-backed metadata/workflow direction |
| `MILESTONE_003_PLATFORM_FOUNDATION_INITIALIZATION.md` | Lists SQLAlchemy, Alembic, psycopg, typed settings, local PostgreSQL dependency |
| `MILESTONE_004_REPOSITORY_SCAFFOLDING_AND_TOOLCHAIN_BOOTSTRAP.md` | Toolchain and local Docker foundation |
| `MILESTONE_005_INFRASTRUCTURE_ARCHITECTURE.md` | Persistence layer ownership, trust boundary, failure-domain rules |
| `MILESTONE_006_FOUNDATION_CONTRACTS.md` | Persistence, Configuration, Error, Health, Logging contract rules |
| `MILESTONE_007_FIRST_INFRASTRUCTURE_IMPLEMENTATION_SLICE.md` | Foundation Error, configuration snapshot, health model, and bootstrap foundation |

MILESTONE-002 and MILESTONE-003 were read from `C:\Users\LuxSy\Desktop` because they are governing baseline documents external to the repository root. No external document was modified.

## 5. Repository Baseline

Baseline reviewed:

```text
79bb2e1 Implement MILESTONE-007 foundation infrastructure slice
1444ea2 Resolve MILESTONE-004 verification blockers and approve integration
bb93c06 Add infrastructure architecture and foundation contracts drafts
449389f Initialize MILESTONE-004 platform foundation scaffold
```

Pre-change repository state was clean on `master`.

## 6. Requirement-to-Code Traceability

| Requirement | Source | Existing artifact | Implementation | Tests | Non-goals |
| --- | --- | --- | --- | --- | --- |
| PostgreSQL 17 transactional metadata foundation | M002 Sections 10, 25, 26; M003 Section 8 | `pyproject.toml`, `infra/local/compose.yaml` | `shared/persistence/postgres.py` | `tests/integration/test_postgres_connectivity.py` | No metadata schema |
| Unit-of-work atomicity and isolation boundary | M006 Section 6 | `shared/interfaces/persistence.py` placeholder | `PersistenceUnitOfWork`, `PostgresUnitOfWork` | `test_postgres_persistence.py`, `test_persistence_fake.py` | No domain repositories |
| Configuration resolves once and is secret-safe | M006 Section 5; M003 Section 6 | `shared/config/settings.py` | `PostgreSQLConfigSnapshot` | `test_postgresql_config.py` | No domain settings |
| Lower-level exception translation | M006 Section 12; M007 Error model | `FoundationError` | `translate_persistence_error` | unit and integration failure tests | No domain error categories |
| Multi-axis persistence health | M005 Section 4; M006 Section 13 | `shared/health.py` | `PostgresPersistenceService.health` | unit and integration health tests | No health API expansion |
| Startup/shutdown integration | M006 cross-contract rules; M007 bootstrap | `shared/bootstrap.py` | `initialize_foundation_runtime_with_postgresql` | `test_persistence_bootstrap.py` | No DI container |

## 7. Technology Decision

Selected: SQLAlchemy 2 Core/Engine with the `psycopg` PostgreSQL dialect.

Alternatives considered:

| Alternative | Decision | Rationale |
| --- | --- | --- |
| SQLAlchemy Core + psycopg | Selected | MILESTONE-003 explicitly lists SQLAlchemy and psycopg; provides pooling and transaction boundaries without ORM mappings. |
| Raw psycopg only | Rejected for this slice | Narrow and possible, but would recreate pooling/lifecycle mechanics already provided by the selected stack. |
| SQLAlchemy ORM | Rejected | No domain models or schemas are authorized; ORM mapping would imply entity persistence too early. |
| SQLite substitute | Rejected for production adapter | Useful for unit injection only; MILESTONE-002 selects PostgreSQL 17. |

Reversibility: the implementation is isolated under `shared/persistence`; future replacement can preserve the `PersistenceService` and `PersistenceUnitOfWork` protocols.

Dependency impact: `verify.ps1` now installs the existing `persistence` optional dependency group so SQLAlchemy/psycopg are part of the validated foundation surface.

## 8. Files Created

| File | Purpose |
| --- | --- |
| `src/empirical_platform/shared/persistence/__init__.py` | Persistence foundation exports |
| `src/empirical_platform/shared/persistence/postgres.py` | PostgreSQL connectivity, unit-of-work, health, and error translation |
| `src/empirical_platform/shared/persistence/fake.py` | Deterministic fake persistence service |
| `tests/unit/test_postgresql_config.py` | PostgreSQL configuration tests |
| `tests/unit/test_persistence_fake.py` | Fake persistence contract tests |
| `tests/unit/test_postgres_persistence.py` | Adapter lifecycle, transaction, translation, health tests |
| `tests/unit/test_persistence_bootstrap.py` | Startup composition tests |
| `tests/integration/test_postgres_connectivity.py` | Real PostgreSQL integration tests |
| `MILESTONE_008_PERSISTENCE_CONNECTIVITY_FOUNDATION_SLICE.md` | This milestone report |

## 9. Files Modified

| File | Modification |
| --- | --- |
| `.env.example` | Adds safe PostgreSQL connectivity placeholders and local port placeholder |
| `infra/local/compose.yaml` | Makes local PostgreSQL host port configurable with default `55432` |
| `pyproject.toml` | Adds `integration` marker |
| `scripts/verify.ps1` | Installs the persistence dependency group during verification |
| `src/empirical_platform/shared/config/settings.py` | Adds immutable PostgreSQL connectivity snapshot |
| `src/empirical_platform/shared/interfaces/persistence.py` | Expands persistence protocols |
| `src/empirical_platform/shared/bootstrap.py` | Adds optional PostgreSQL-aware startup composition |

## 10. Persistence Configuration

`PostgreSQLConfigSnapshot` captures connectivity-only settings:

- host;
- port;
- database;
- user;
- password as `SecretStr`;
- pool size;
- max overflow;
- connection timeout;
- application name.

The snapshot is immutable, deterministic in tests, and does not expose the password in safe context. URL construction occurs at the adapter boundary and is not logged or included in public error payloads.

## 11. Connection/Pool Lifecycle

`PostgresPersistenceService` owns:

- engine creation;
- pool initialization;
- connectivity probe;
- connection acquisition and release;
- idempotent close;
- rejection of use after close;
- rejection of use before initialization.

The local PostgreSQL Compose host port is configurable. Default host binding is `55432` to avoid collision with unrelated local PostgreSQL services while preserving container port `5432`.

## 12. Unit-of-Work Semantics

`PostgresUnitOfWork` provides:

- explicit begin on context entry;
- commit on successful context exit;
- rollback on exceptional context exit;
- explicit `commit`;
- explicit `rollback`;
- no double completion;
- connection release on completion;
- nested unit-of-work rejection through a process-local context variable.

Isolation behavior: this slice uses the database and SQLAlchemy default isolation configuration. It does not claim serializable behavior.

## 13. Error Translation

All lower-level SQLAlchemy/DBAPI failures are translated to `FoundationError` with:

- category `persistence_error`;
- layer `persistence`;
- operation context;
- safe human-readable message;
- no password, DSN, or driver message in public payload fields.

Configuration failures from missing required PostgreSQL password remain Configuration-category `FoundationError` and are not reclassified as Persistence errors.

## 14. Health Integration

Persistence health is reported as a `LayerHealth` signal:

- before initialization: LIVENESS `PASS`, READINESS `UNKNOWN`, DEPENDENCY HEALTH `UNKNOWN`;
- reachable: LIVENESS `PASS`, READINESS `PASS`, DEPENDENCY HEALTH `PASS`;
- unreachable: LIVENESS `PASS`, READINESS `FAIL`, DEPENDENCY HEALTH `FAIL`;
- closed: LIVENESS `PASS`, READINESS `FAIL`, DEPENDENCY HEALTH `UNKNOWN`.

A single failed operation does not automatically force LIVENESS to `FAIL`.

## 15. Startup/Shutdown Integration

`initialize_foundation_runtime_with_postgresql` composes:

1. configuration;
2. logging;
3. PostgreSQL persistence initialization and probe;
4. clocks;
5. identifiers;
6. health report.

If mandatory persistence initialization fails, no ready runtime is returned. Shutdown is handled by `PersistenceService.close`, which is idempotent and stops new work.

## 16. PostgreSQL Integration Testing

Integration test command:

```text
docker compose -f .\infra\local\compose.yaml up -d postgres
python -m pytest tests\integration\test_postgres_connectivity.py -q --no-cov
docker compose -f .\infra\local\compose.yaml down --remove-orphans
```

Observed result:

```text
POSTGRES_READY=True
POSTGRES_INTEGRATION_EXIT=0
3 passed in 2.98s
POSTGRES_DOWN_EXIT=0
```

The first integration attempt identified a local host-port collision on `localhost:5432`; see `PERSISTENCE-ISSUE-0001`.

## 17. Architecture Boundary Evidence

The persistence implementation is contained under `shared/persistence` and imports no domain modules. Domain modules are not modified. The architecture checker remains unchanged.

Driver imports are isolated to the persistence implementation and tests. Future domain modules must depend on persistence abstractions rather than driver objects.

## 18. Security Evidence

Security controls implemented:

- password stored as `SecretStr`;
- safe config context reports only `password_configured`;
- public error payloads omit DSNs and driver messages;
- test secret-looking values are placeholders only;
- no real credentials committed;
- no SQL is built from untrusted domain input because no domain query API exists.

Canonical security scan:

```text
Secret scan target count: 91
No known vulnerabilities found
```

## 19. Database/Migration Integrity

No migration file was added.

No persistent table or application schema was added.

Migration directory still contains only the existing Alembic boundary:

```text
migrations/env.py
migrations/README.md
migrations/versions/
```

Integration tests use `SELECT 1` and temporary transaction-local tables with `ON COMMIT DROP`.

## 20. Test Evidence

Focused validation:

```text
54 unit tests passed
3 PostgreSQL integration tests passed
```

Full verification:

```text
56 passed, 3 skipped
coverage: 90.91%
```

The three skipped tests are the opt-in PostgreSQL integration tests during normal `verify.ps1`; they pass under the explicit PostgreSQL integration command in Section 16.

## 21. Deferred Items

| Item | Reason |
| --- | --- |
| Domain metadata schema | Not authorized by this connectivity slice |
| Alembic migrations | No schema exists yet |
| Job ledger / transactional outbox tables | Requires later schema milestone |
| Domain repositories | Requires domain metadata model |
| Object-storage adapter | Explicitly out of scope |
| Production secrets manager | Deferred by prior milestones |
| Production backup/recovery implementation | Requires schema and deployment decisions |

## 22. Risks

| ID | Severity | Risk | Mitigation |
| --- | --- | --- | --- |
| PERSISTENCE-RISK-0001 | Medium | Local PostgreSQL ports may collide with developer machine services. | Compose host port is configurable and defaults to `55432`. |
| PERSISTENCE-RISK-0002 | Medium | SQL string execution could become a domain-query escape hatch later. | Current tests use only infrastructure-local trivial statements; future domain repositories must define a narrower query surface. |
| PERSISTENCE-RISK-0003 | Low | Default database isolation is not yet an explicit project-level isolation guarantee. | Documented; no serializable guarantee is claimed. |

## 23. Implementation Issue Register

| ID | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| PERSISTENCE-ISSUE-0001 | MINOR | Initial integration test against `localhost:5432` reached an unrelated local PostgreSQL endpoint. | RESOLVED by making Compose PostgreSQL host port configurable with default `55432`; integration tests pass. |
| PERSISTENCE-ISSUE-0002 | MINOR | Initial engine storage design shadowed the engine property. | RESOLVED by using explicit `_engine_obj` storage and `engine` accessor. |
| PERSISTENCE-ISSUE-0003 | MINOR | PostgreSQL configuration errors could be reclassified during initialization. | RESOLVED by preserving existing `FoundationError` category when initialization fails due configuration. |
| PERSISTENCE-ISSUE-0004 | MINOR | Focused lint/type pass found import sorting, strict `__exit__` typing, and secret-shaped fixture literal issues. | RESOLVED; Ruff, mypy, and unit tests pass. |

No CRITICAL or MAJOR implementation issue remains open.

## 24. Acceptance Criteria

| Criterion | Result |
| --- | --- |
| Adapter satisfies frozen Persistence Contract | PASSED |
| PostgreSQL connectivity passes | PASSED |
| Transaction commit/rollback tests pass | PASSED |
| No domain schema/table/migration is added | PASSED |
| Health/Error/Logging boundaries remain intact | PASSED |
| `security.ps1` passes | PASSED |
| `verify.ps1` passes | PASSED |
| Docker Compose config passes | PASSED |
| PostgreSQL integration tests pass | PASSED |
| No CRITICAL or MAJOR implementation issue remains | PASSED |

## 25. Quality Rubric

| Category | Max | Score | Rationale |
| --- | --- | --- | --- |
| Traceability | 20 | 20 | Every implemented behavior maps to M002/M003/M005/M006/M007 inputs. |
| Scope discipline | 20 | 19 | No schema/domain behavior; local Compose host-port adjustment is operationally scoped. |
| Contract fidelity | 20 | 19 | Unit-of-work, translation, health, lifecycle implemented; isolation remains default/documented. |
| Test coverage | 15 | 14 | 56 full-suite tests pass with 90.91% coverage; 3 PostgreSQL tests pass under explicit integration command. |
| Security posture | 10 | 10 | Secrets are redacted and no real credentials committed. |
| Architecture integrity | 10 | 10 | Driver imports stay under persistence boundary; no domain imports. |
| Maintainability | 5 | 5 | Narrow protocols, replaceable adapter, fake substitute. |

**MILESTONE-008 score: 97 / 100.**

## 26. Final Status

```text
APPROVED AND FROZEN
```

Final verification passed after this report was added to the repository. All MILESTONE-008 approval criteria are met.
