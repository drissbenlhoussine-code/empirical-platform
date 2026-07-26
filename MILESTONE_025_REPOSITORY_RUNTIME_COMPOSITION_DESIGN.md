# MILESTONE-025 - Repository Runtime Composition Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-025-DESIGN |
| Title | Repository Runtime Composition Design |
| Version | 1.0 |
| Status | DESIGN READY FOR INDEPENDENT REVIEW |
| Repository baseline | `b2283281f670703c95de0b6fe8ee83d58c5e3ac1` |
| Implementation authorized | No |

## 2. Purpose

Define the repository runtime composition boundary that future implementation will use to obtain the four concrete PostgreSQL repository adapters as one coherent infrastructure unit backed by a single `PostgresPersistenceService`.

## 3. Design Inputs

| Input | Required by this design |
| --- | --- |
| M020 | Repository Protocol surfaces and error taxonomy remain unchanged |
| M021 | Mapper contracts and durable-record reconstruction remain unchanged |
| M022 | PostgreSQL schema/migration remains unchanged |
| M023 | Concrete PostgreSQL repository adapters are reused unchanged |
| M024 | `PostgresPersistenceService.run_composed(operations)` is the only cross-repository atomic execution primitive |

## 4. Architectural Problem

After M024, callers can compose multiple repository operations atomically only if they manually construct the correct repository adapter instances over the exact same `PostgresPersistenceService`. That manual wiring is now the next architectural gap: it is easy to accidentally mix services, construct only part of the repository set, or hide M024's same-service rule inside future application code.

M025 solves only that wiring gap.

## 5. Selected Design

Introduce a narrow PostgreSQL repository runtime composition object in the infrastructure layer.

The future object is conceptually named `PostgresRepositoryRuntime`. It owns no domain behavior. It exposes:

- `campaigns`;
- `runs`;
- `evidence_packages`;
- `reviews`;
- `run_composed(operations)`;
- `close()`.

The four repository attributes are concrete M023 PostgreSQL adapters constructed with the same `PostgresPersistenceService` instance. `run_composed(operations)` delegates directly to that same service's frozen M024 method.

## 6. Package Placement

Future implementation belongs under:

```text
src/empirical_platform/shared/persistence/postgres_repositories/runtime.py
```

This placement is intentional because:

- the concrete repository adapters already live under `shared.persistence.postgres_repositories`;
- `shared` is the current infrastructure composition boundary for PostgreSQL persistence;
- no domain package should import a concrete PostgreSQL repository runtime;
- no application-service package exists yet.

## 7. Public Surface

The future public surface is intentionally small:

```text
PostgresRepositoryRuntime(
    service: PostgresPersistenceService,
)

.campaigns -> PostgresCampaignRepository
.runs -> PostgresRunRepository
.evidence_packages -> PostgresEvidencePackageRepository
.reviews -> PostgresReviewRepository
.run_composed(operations) -> tuple[object, ...]
.close() -> None
```

This is an infrastructure composition surface, not a domain contract. It must not alter or replace M020 repository Protocols.

## 8. Ownership Rules

The runtime object owns:

- construction of the four concrete repository adapter instances;
- guarantee that all four adapters share the exact same `PostgresPersistenceService` object identity;
- delegation of composed execution to that same service;
- idempotent close forwarding to the service.

The runtime object does not own:

- configuration loading;
- secret handling;
- database migrations;
- schema creation;
- aggregate reconstruction;
- repository method semantics;
- application workflow decisions;
- retry policy.

## 9. Transaction Semantics

Single repository calls keep their existing M023 behavior: each method opens its own Unit of Work through `self._service.unit_of_work()`.

Cross-repository atomic work must use:

```text
runtime.run_composed(operations)
```

The runtime must not implement its own transaction manager. It must call:

```text
self._service.run_composed(operations)
```

and return the tuple produced by M024 only after the underlying composed transaction commits.

## 10. Error Semantics

Repository methods continue to surface the frozen M020 repository error taxonomy through the frozen M023 adapters.

M024 composition failures continue to surface through `FoundationError` or the already-translated repository error raised by the failing operation.

M025 must not add a new error taxonomy unless a future implementation review proves a narrow construction-time error cannot be represented by existing foundation errors.

## 11. Lifecycle Semantics

Construction is side-effect light:

- it may validate that the supplied service is not `None`;
- it must not open a database connection merely to prove readiness;
- it must not run migrations;
- it must not emit health status.

`close()` delegates to the shared `PostgresPersistenceService.close()` and must be idempotent because the service close operation is already expected to be safe to call repeatedly.

Use after close remains governed by the existing persistence service behavior. M025 must not invent a second lifecycle state machine.

## 12. Identity and Scope Integrity

The runtime composition must preserve:

- governance/runtime identity separation;
- `DomainIdentity[...]` inputs at repository boundaries;
- runtime UUID behavior already frozen in aggregate and repository layers;
- M024 same-service owner isolation.

It must not add cross-aggregate invariants or validate that a Campaign, Run, EvidencePackage, and Review belong together. Those are future application-service concerns.

## 13. Compatibility With M020 Through M024

| Prior milestone | Compatibility rule |
| --- | --- |
| M020 | No Protocol signature changes |
| M021 | No mapper Protocol or durable-record changes |
| M022 | No schema or migration changes |
| M023 | No repository adapter behavior changes |
| M024 | No transaction mechanism reimplementation |

## 14. Validation Obligations for Future Implementation

Future implementation must include tests proving:

- all four repositories are exposed;
- all four repositories share one service instance;
- `run_composed` delegates exactly once to the service primitive;
- `close()` is idempotent and delegates to the service;
- no repository Protocol signature changes;
- no schema, migration, API, worker, retry, Audit, Decision Candidate, Decision Freeze, market-data, vendor, trading, or campaign execution behavior.

Real PostgreSQL validation is required because the object composes concrete PostgreSQL adapters. The minimum integration proof is one composed operation involving at least two exposed repositories over the same disposable PostgreSQL instance.

## 15. Rejected Alternatives

| Alternative | Rejection reason |
| --- | --- |
| Application service first | Premature; application services need a stable repository runtime composition boundary |
| Global dependency injection container | Too broad and likely to obscure ownership |
| Retry policy first | Depends on application service orchestration and would risk hidden transaction retries |
| Generic repository factory | Broader than needed and weaker than a concrete PostgreSQL runtime over frozen adapters |
| Bootstrap integration now | Premature; no application entrypoint consumes the repository runtime yet |

## 16. Deferred Items

- application services;
- retry-on-optimistic-concurrency policy;
- bootstrap wiring into an application entrypoint;
- APIs and workers;
- query/read-model projections;
- Audit runtime;
- Decision Candidate and Decision Freeze;
- market-data, vendor, trading, and empirical campaign execution behavior.

## 17. Risk Register

| Issue | Severity | Mitigation |
| --- | --- | --- |
| M025-DESIGN-RISK-0001: runtime composition drifts into application orchestration | MAJOR | Keep surface limited to repository exposure and M024 delegation |
| M025-DESIGN-RISK-0002: future implementation reimplements transaction semantics | MAJOR | Require direct delegation to `PostgresPersistenceService.run_composed` |
| M025-DESIGN-RISK-0003: future implementation silently changes M020/M023 behavior | MAJOR | Require unchanged Protocols/adapters and regression tests |
| M025-DESIGN-RISK-0004: generic DI container scope creep | MINOR | Reject global container until real consumers exist |

## 18. Acceptance Criteria

M025 design is acceptable only if an independent review confirms:

- the selected scope follows M024's deferred Candidate E;
- no implementation is present;
- no frozen prior milestone is rewritten;
- the design preserves all M020-M024 contracts;
- the future implementation boundary is narrow and independently testable;
- M025 remains not approved, not frozen, and not implemented.

## 19. Final Status

```text
M025 DESIGN READY FOR INDEPENDENT REVIEW
M025 NOT APPROVED
M025 NOT FROZEN
M025 IMPLEMENTATION NOT STARTED
```
