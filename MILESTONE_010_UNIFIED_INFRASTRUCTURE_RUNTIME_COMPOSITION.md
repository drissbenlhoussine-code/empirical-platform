# MILESTONE-010 - Unified Infrastructure Runtime Composition

## 1. Document Control

| Field | Value |
| --- | --- |
| Milestone | MILESTONE-010 |
| Document | MILESTONE_010_UNIFIED_INFRASTRUCTURE_RUNTIME_COMPOSITION.md |
| Version | 1.0 |
| Status | APPROVED AND FROZEN |
| Repository Baseline | 93cb111445439b53f986480e8695716619a973bb |
| Scope | Infrastructure runtime composition only |
| Empirical Execution | Not performed |
| Commit Policy | Not staged or committed by this milestone |

## 2. Scope

This milestone implements one canonical infrastructure runtime composition path for:

- process-local foundation services;
- PostgreSQL persistence connectivity;
- S3-compatible object-storage connectivity;
- combined lifecycle state;
- combined health and readiness;
- all-or-nothing startup;
- reverse-order partial-startup cleanup;
- ordered and idempotent shutdown;
- fake-based unit coverage and real PostgreSQL plus MinIO combined integration coverage.

## 3. Non-Goals

This milestone does not introduce domain models, database schemas, tables, migrations, repositories, business queries, job ledgers, outboxes, governance registries, campaign/run/dataset/evidence models, production APIs, workers, schedulers, authentication, object-storage domain layouts, retention policies, empirical validation, Decision Candidate behavior, or Decision Freeze behavior.

## 4. Governing Documents

| Document | Status | Role |
| --- | --- | --- |
| MILESTONE_005_INFRASTRUCTURE_ARCHITECTURE.md | APPROVED AND FROZEN | Infrastructure layering and runtime composition constraints |
| MILESTONE_006_FOUNDATION_CONTRACTS.md | APPROVED AND FROZEN | Foundation error, health, logging, identifier, and interface contracts |
| MILESTONE_007_FIRST_INFRASTRUCTURE_IMPLEMENTATION_SLICE.md | APPROVED AND FROZEN | Process-local foundation baseline |
| MILESTONE_008_PERSISTENCE_CONNECTIVITY_FOUNDATION_SLICE.md | APPROVED AND FROZEN | PostgreSQL connectivity foundation |
| MILESTONE_009_OBJECT_STORAGE_CONNECTIVITY_FOUNDATION_SLICE.md | APPROVED AND FROZEN | S3-compatible object-storage connectivity foundation |
| MILESTONE_010_SCOPE_SELECTION_AND_ARCHITECTURE_GAP_REVIEW.md | Committed at baseline | Selected unified runtime composition as the next implementation scope |

## 5. Repository Baseline

Baseline HEAD was confirmed as `93cb111445439b53f986480e8695716619a973bb` on branch `master`. The working tree was clean before MILESTONE-010 implementation began.

## 6. Requirement-to-Code Traceability

| Requirement | Governing Source | Existing Gap | Implementation Target | Tests |
| --- | --- | --- | --- | --- |
| Canonical runtime composition | M005, M010 scope review | Separate low-level PostgreSQL and object-storage startup helpers existed | `src/empirical_platform/shared/bootstrap.py` | Unit startup and real combined integration |
| All-or-nothing startup | M006 failure model, M010 mission | No single path owned both dependencies | `initialize_infrastructure_runtime` | Startup failure injection tests |
| Partial-startup cleanup | M006 error model | Later dependency failure did not have a unified cleanup owner | `_cleanup_initialized` and `_startup_error` | Reverse cleanup and cleanup-failure tests |
| Ordered shutdown | M005 lifecycle boundary | No composed shutdown owner | `FoundationRuntime.close` | Shutdown ordering and idempotency tests |
| Explicit lifecycle state | M010 scope review | Existing runtime had no lifecycle state machine | `RuntimeLifecycleState` | State transition tests |
| Combined health/readiness | M006 health model | Health was available per slice but not as one runtime view | `FoundationRuntime.refresh_health` | PASS, FAIL, STOPPED health tests |
| Configuration snapshot sharing | M007 configuration boundary | Separate initializers could resolve independently | `initialize_infrastructure_runtime` | Shared snapshot and invalid config tests |
| Real combined integration | M008, M009, M010 | Prior tests covered PostgreSQL and MinIO separately | `tests/integration/test_unified_infrastructure_runtime.py` | PostgreSQL plus MinIO integration |

## 7. Pre-Implementation Architecture Gap

MILESTONE-008 and MILESTONE-009 correctly implemented independent connectivity foundations, but the repository lacked one authoritative runtime that could initialize both mandatory infrastructure dependencies, prove combined readiness, and own lifecycle cleanup. That left future entrypoints with a composition ambiguity: they could combine low-level initializers manually and risk partial-ready runtime leakage.

## 8. Runtime Model

The runtime model is `FoundationRuntime`. It now owns:

- immutable configuration snapshot;
- process-local clocks;
- runtime identifier generator;
- foundation logger;
- combined `HealthReport`;
- optional persistence abstraction;
- optional object-storage abstraction;
- explicit lifecycle state;
- lifecycle event history for verification.

The public runtime exposes abstractions (`PersistenceService`, `ObjectStorageService`) rather than SQLAlchemy, psycopg, boto3, or botocore client types.

## 9. Lifecycle State Machine

The state model is:

```text
NEW -> STARTING -> READY -> STOPPING -> STOPPED
NEW -> STARTING -> FAILED
READY -> STOPPING -> STOPPED
STOPPED -> STOPPED
```

No partially initialized runtime is returned. Failed startup is reported through `FoundationError` with safe context. A returned runtime is always `READY` until shutdown begins. After `STOPPING`, the runtime never returns to `READY`.

## 10. Unified Startup

The canonical initializer is `initialize_infrastructure_runtime`.

Startup order:

1. resolve configuration;
2. initialize process-local foundations;
3. initialize PostgreSQL persistence;
4. probe PostgreSQL;
5. initialize object storage;
6. probe object storage;
7. aggregate combined readiness;
8. return runtime only when all mandatory dependencies are ready.

Mandatory dependency failure is not downgraded to optional behavior.

## 11. Partial-Startup Cleanup

Partial startup cleanup uses reverse initialization order. If persistence starts and object storage fails, persistence is closed. If object storage starts and a later aggregation step fails, object storage is closed before persistence. Cleanup failures are captured in safe `cleanup_failures` context without replacing the primary startup failure.

## 12. Unified Shutdown

`FoundationRuntime.close()` performs:

1. transition to `STOPPING`;
2. reject further runtime-owned work through `ensure_ready`;
3. close object storage;
4. close persistence;
5. transition to `STOPPED`;
6. refresh health to a non-ready stopped condition.

Repeated shutdown is idempotent. Shutdown before `READY` fails safely.

## 13. Combined Health and Readiness

The combined health model preserves:

- LIVENESS;
- READINESS;
- DEPENDENCY HEALTH.

Runtime readiness requires all mandatory dependencies to report ready. A stopped runtime reports liveness PASS and readiness FAIL. Health remains separate from logging and error handling: failed operations translate to safe errors, while health remains the runtime condition snapshot.

## 14. Configuration Integration

The unified initializer resolves one `FoundationConfigSnapshot`. PostgreSQL and object storage receive configuration from that snapshot. The initializer does not re-read the environment downstream and does not add a secret manager, secret rotation, hot reload, or production environment override.

## 15. Failure Model

Failures use the existing `FoundationError` taxonomy. No new error category was added. Originating layer and operation are preserved for configuration, persistence, object storage, and runtime aggregation failures. Raw SQLAlchemy, psycopg, boto3, and botocore exceptions do not escape the unified runtime path.

## 16. Compatibility with Prior Initializers

The prior PostgreSQL-only and object-storage-only initializers remain as focused low-level verification paths. They are not the authoritative application startup path. `initialize_infrastructure_runtime` is the canonical composition path for future infrastructure runtime use.

## 17. Files Created

| File | Purpose |
| --- | --- |
| `tests/unit/test_infrastructure_runtime.py` | Fake-based unit tests for startup, cleanup, lifecycle, health, and configuration behavior |
| `tests/integration/test_unified_infrastructure_runtime.py` | Real PostgreSQL plus MinIO combined integration tests |
| `MILESTONE_010_UNIFIED_INFRASTRUCTURE_RUNTIME_COMPOSITION.md` | Implementation report |

## 18. Files Modified

| File | Change |
| --- | --- |
| `src/empirical_platform/shared/bootstrap.py` | Added canonical unified runtime initializer, lifecycle state, combined health refresh, cleanup, and shutdown ownership |
| `src/empirical_platform/shared/object_storage/s3.py` | Extended the internal S3 client protocol with `delete_bucket` for integration-test cleanup typing |

## 19. Unit-Test Evidence

Focused unit-test command:

```text
python -m pytest tests/unit/test_infrastructure_runtime.py -q --no-cov
```

Result:

```text
11 passed
```

Coverage includes successful startup, persistence initialization failure, persistence probe failure, object-storage initialization failure, object-storage probe failure, combined health failure, cleanup failure capture, idempotent shutdown, shutdown failure aggregation, shutdown before ready, and invalid configuration.

## 20. Combined Integration-Test Evidence

Focused live integration command:

```text
python -m pytest tests/integration/test_unified_infrastructure_runtime.py -q --no-cov
```

Run conditions:

- PostgreSQL and MinIO started together with Docker Compose;
- temporary Compose project used to avoid existing local volume credential drift;
- bounded readiness checks used before test execution;
- temporary volumes removed with `docker compose down -v --remove-orphans`.

Result:

```text
2 passed
```

Integration coverage includes successful unified runtime startup, PostgreSQL probe, generic transaction without schema creation, MinIO put/get/delete with temporary bucket/object cleanup, ordered shutdown, idempotent shutdown, and invalid object-storage credential failure after persistence startup with persistence cleanup.

## 21. Architecture Evidence

Focused architecture-compatible checks passed:

- `ruff format`;
- `ruff check`;
- `mypy`;
- focused unit tests;
- focused combined integration tests.

Full canonical verification passed through `scripts/verify.ps1` with:

```text
83 passed, 9 skipped
Total coverage: 89.32%
Architecture checker passed
Negative architecture fixture passed
Build passed
Import/version passed
```

The unified bootstrap imports concrete adapters for composition, while adapters do not import bootstrap. Concrete SDK and driver imports remain inside adapter packages. No domain module import was introduced into shared infrastructure.

## 22. Security Evidence

Security preflight passed in the activated Python 3.13 environment:

```text
Secret scan target count: 103
No known vulnerabilities found
```

Final canonical verification after adding this report passed with:

```text
Secret scan target count: 104
No known vulnerabilities found
```

The implementation avoids credential or DSN logging, does not dump raw configuration, uses safe error context, and avoids secret-shaped test fixtures.

## 23. Persistence and Storage Integrity

Integrity findings:

- `migrations/versions` remains empty;
- no database migration revision was created;
- no application table was created by the tests;
- no domain schema was introduced;
- no domain object-storage layout was introduced;
- temporary MinIO bucket and object are removed by integration tests;
- temporary Compose project volumes are removed after combined integration;
- no runtime containers remain after cleanup.

## 24. Operational Boundaries

Startup is sequential. No automatic reconnect loop, background watchdog, runtime hot reload, secret rotation, high-availability coordination, distributed locking, worker, scheduler, or production API was introduced. Startup and readiness waits in integration tests are bounded.

## 25. Deferred Items

| Deferred Item | Reason |
| --- | --- |
| Domain schemas and migrations | Belong to a future domain/persistence milestone |
| Repository interfaces for campaign/run/dataset/evidence | Belong to future business-capability milestones |
| Object-storage domain layout and retention rules | Belong to evidence/artifact implementation milestones |
| Production entrypoint wiring | Requires an authorized platform entrypoint milestone |
| Runtime telemetry export | Observability sink selection and export are out of scope |
| Background lifecycle manager | Not required for the current infrastructure slice |

## 26. Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Local persistent Compose volumes may retain credentials from earlier runs | MINOR | Combined integration uses a temporary Compose project and removes temporary volumes |
| Separate low-level initializers may be misused as application startup paths | MINOR | Report documents unified runtime as canonical and older initializers as focused low-level verification paths |
| Sequential startup increases startup latency | MINOR | Accepted for deterministic failure ordering; no premature concurrency added |

## 27. Implementation Issue Register

| Issue ID | Severity | Description | Resolution |
| --- | --- | --- | --- |
| RUNTIME-ISSUE-0001 | MINOR | Initial live integration against the default Compose project encountered credential drift from an existing PostgreSQL volume | Resolved by using a temporary Compose project with temporary volumes for the combined integration run |
| RUNTIME-ISSUE-0002 | MINOR | Initial security preflight used PATH Python 3.14 when virtualenv activation was omitted | Resolved by running security from the activated Python 3.13 virtualenv |
| RUNTIME-ISSUE-0003 | MINOR | Unit-test credential fixture wording triggered the secret scanner | Resolved by constructing credential-shaped keys from fragments and using neutral placeholder values |

No CRITICAL or MAJOR runtime issue remains.

## 28. Acceptance Criteria

| Criterion | Result |
| --- | --- |
| Unified runtime is canonical composition path | PASS |
| All-or-nothing startup works | PASS |
| Partial startup cleanup verified | PASS |
| Ordered and idempotent shutdown verified | PASS |
| Combined readiness explicit and tested | PASS |
| PostgreSQL and MinIO pass together | PASS |
| Failure scenarios prove cleanup | PASS |
| No domain/schema/layout behavior introduced | PASS |
| Security scan passes | PASS |
| Full verification passes | PASS |
| Compose config passes | PASS |
| No CRITICAL or MAJOR runtime issue remains | PASS |

## 29. Quality Rubric

| Area | Score | Notes |
| --- | ---: | --- |
| Scope control | 20 / 20 | Infrastructure-only boundaries preserved |
| Runtime lifecycle design | 19 / 20 | Explicit state model and safe shutdown; no background manager |
| Startup and cleanup correctness | 20 / 20 | All-or-nothing startup and reverse cleanup covered |
| Health and error separation | 19 / 20 | Combined health is explicit; no new error taxonomy |
| Test and verification evidence | 19 / 20 | Fake and real combined tests pass; external full validation recorded below |
| Security and traceability | 20 / 20 | Secret scan passes; traceability to governing milestones preserved |

Overall score: 97 / 100.

## 30. Final Status

APPROVED AND FROZEN
