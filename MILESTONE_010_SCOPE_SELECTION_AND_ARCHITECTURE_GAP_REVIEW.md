# MILESTONE-010 SCOPE SELECTION AND ARCHITECTURE GAP REVIEW

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-010 |
| Document name | Scope Selection and Architecture Gap Review |
| Version | 1.0 |
| Status | DRAFT / SCOPE DECISION UNDER REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Baseline | `24fb2a7d6720208e9d87b87c1a43872566e7c2d0` |
| Created | 2026-07-16 |
| Scope type | Analysis and design-selection only |

## 2. Scope

This review determines the correct next implementation milestone after MILESTONE-007,
MILESTONE-008, and MILESTONE-009.

This document does not implement MILESTONE-010. It does not modify source code, create
schemas, create migrations, create tables, add APIs, add workers, add adapters, or introduce
domain models.

Candidate directions reviewed:

| Candidate | Direction |
| --- | --- |
| A | Unified Infrastructure Runtime Composition |
| B | Job Ledger / Transactional Outbox Foundation |
| C | Governance Registry Read Model Foundation |
| D | Audit Event Ledger Foundation, considered only as a possible alternate foundation slice |

## 3. Repository Baseline

Repository commands reviewed:

```text
git status --short --branch
branch: master

git log --oneline --decorate -8
24fb2a7 (HEAD -> master) Implement MILESTONE-009 object storage connectivity foundation
579c296 Implement MILESTONE-008 persistence connectivity foundation
79bb2e1 Implement MILESTONE-007 foundation infrastructure slice
1444ea2 Resolve MILESTONE-004 verification blockers and approve integration
bb93c06 Add infrastructure architecture and foundation contracts drafts
449389f Initialize MILESTONE-004 platform foundation scaffold

git rev-parse HEAD
24fb2a7d6720208e9d87b87c1a43872566e7c2d0
```

Baseline is confirmed. The pre-review working tree was clean.

## 4. Governing Documents

Documents reviewed:

| Document | Role in this decision |
| --- | --- |
| `MILESTONE_001_SYSTEM_IMPLEMENTATION_ARCHITECTURE.md` | Defines logical subsystems, governance boundary, execution boundary, failure domains, and traceability requirements |
| `MILESTONE_002_TECHNOLOGY_SELECTION_AND_ENGINEERING_BLUEPRINT.md` | Selects PostgreSQL, S3-compatible object storage, modular monolith, job ledger/outbox, audit ledger, and implementation sequence |
| `MILESTONE_003_PLATFORM_FOUNDATION_INITIALIZATION.md` | Defines repository boundaries, schema deferral, object-storage planning, registry/governance module boundaries, and readiness checklist |
| `MILESTONE_004_REPOSITORY_SCAFFOLDING_AND_TOOLCHAIN_BOOTSTRAP.md` | Creates the scaffold and toolchain |
| `MILESTONE_005_INFRASTRUCTURE_ARCHITECTURE.md` | Defines infrastructure layers, dependency graph, ownership boundaries, failure domains, and extensibility principles |
| `MILESTONE_006_FOUNDATION_CONTRACTS.md` | Defines configuration, persistence, object storage, clock, identifier, logging, error, and health contracts |
| `MILESTONE_001_006_DOCUMENT_INTEGRATION_REVIEW.md` | Confirms readiness for first infrastructure implementation slice |
| `MILESTONE_007_FIRST_INFRASTRUCTURE_IMPLEMENTATION_SLICE.md` | Implements foundation config, clocks, identifiers, logging, errors, health, and base runtime bootstrap |
| `MILESTONE_008_PERSISTENCE_CONNECTIVITY_FOUNDATION_SLICE.md` | Implements PostgreSQL connectivity, unit of work, persistence health, and PostgreSQL-only bootstrap |
| `MILESTONE_009_OBJECT_STORAGE_CONNECTIVITY_FOUNDATION_SLICE.md` | Implements S3/MinIO connectivity, generic object operations, object-storage health, and object-storage-only bootstrap |

Key governing evidence:

- MILESTONE-001 requires execution modules to read governance state rather than infer it, but it does not define a schema or ingestion path.
- MILESTONE-002 selects PostgreSQL job ledger / transactional outbox as required for the initial architecture, but its sequencing places governance registry read models at step 6, campaign/run/dataset/evidence metadata at step 7, audit event ledger at step 8, evidence manifest/checksum model at step 9, and job ledger/outbox at step 10.
- MILESTONE-003 explicitly defers schemas and migrations, and flags that migration policy must precede first schema work.
- MILESTONE-008 and MILESTONE-009 intentionally avoided domain schemas, job ledger tables, audit tables, registry models, retention policy, evidence layout, workers, APIs, and campaign behavior.

## 5. Current Capability Inventory

| Capability | Classification | Repository evidence |
| --- | --- | --- |
| Process-local runtime composition | PARTIALLY IMPLEMENTED | `FoundationRuntime` exists, with base, PostgreSQL-only, and object-storage-only initializer functions |
| Configuration | IMPLEMENTED AND VERIFIED | `shared/config/settings.py`, config snapshot tests, secret-safe contexts |
| Clocks | IMPLEMENTED AND VERIFIED | `shared/interfaces/clock.py`, clock tests |
| Runtime identifiers | IMPLEMENTED AND VERIFIED | `shared/identifiers.py`, UUIDv4 runtime IDs, deterministic substitute |
| Governance identifier value objects | PARTIALLY IMPLEMENTED | `identifiers/types.py` contains `CAMP`, `RUN`, `DATASET`, `EVID`, `REVIEW`, `AUD`, `DCAND` value objects only |
| Logging/fallback | IMPLEMENTED AND VERIFIED | `shared/logging`, MILESTONE-007 tests |
| Error model | IMPLEMENTED AND VERIFIED | `FoundationError`, persistence and object-storage translation |
| Health aggregation | IMPLEMENTED AND VERIFIED | `shared/health.py`, layer and aggregate tests |
| PostgreSQL pool/UoW/connectivity | IMPLEMENTED AND VERIFIED | `shared/persistence/postgres.py`, unit tests, PostgreSQL integration tests |
| S3/MinIO client/connectivity | IMPLEMENTED AND VERIFIED | `shared/object_storage/s3.py`, unit tests, MinIO integration tests |
| Startup/shutdown | PARTIALLY IMPLEMENTED | Each dependency has its own lifecycle; no combined all-or-nothing runtime startup/shutdown path |
| Combined readiness | PARTIALLY IMPLEMENTED | `HealthReport` can aggregate layers, but no initializer composes both persistence and object storage into one report |
| Orchestration/job infrastructure | DESIGNED ONLY | `shared/interfaces/orchestration.py` contains only a minimal health protocol |
| Persistence schema | EXPLICITLY DEFERRED | `migrations/versions` is empty; MILESTONE-008 states no schema or table was added |
| Transactional outbox | EXPLICITLY DEFERRED | MILESTONE-008 non-goals and deferred items |
| Registry models | DESIGNED ONLY | Module boundary exists; no runtime model, schema, source-of-truth loader, or ingestion path |
| Campaign/run models | DESIGNED ONLY | Package skeleton and identifier types only |
| Dataset/evidence models | DESIGNED ONLY | Package skeletons only |
| APIs/workers | EXPLICITLY DEFERRED | No production API or worker implementation |
| Trading/vendor/campaign behavior | EXPLICITLY DEFERRED | No such behavior in source tree |

## 6. Implemented Runtime Topology

Current topology is parallel rather than unified:

```text
initialize_foundation_runtime
    -> config
    -> logging
    -> clocks
    -> identifiers
    -> internal health

initialize_foundation_runtime_with_postgresql
    -> config
    -> logging
    -> PostgresPersistenceService.initialize()
    -> clocks
    -> identifiers
    -> persistence health

initialize_foundation_runtime_with_object_storage
    -> config
    -> logging
    -> S3ObjectStorageService.initialize()
    -> clocks
    -> identifiers
    -> object-storage health
```

There is one runtime dataclass, but no single authoritative initializer for the platform's required infrastructure dependencies together. The repository has separate tests for base bootstrap, PostgreSQL bootstrap, object-storage bootstrap, PostgreSQL integration, and MinIO integration. It does not have combined integration tests proving that both adapters initialize, report readiness, fail, and shut down together under one runtime owner.

## 7. Remaining Architecture Gaps

| ID | Severity | Gap | Evidence | Consequence |
| --- | --- | --- | --- | --- |
| M010-SCOPE-ISSUE-0001 | MAJOR | No single authoritative infrastructure runtime owns both PostgreSQL and object storage | Separate initializer functions in `shared/bootstrap.py` | First non-foundation capability would have to choose or duplicate bootstrap paths |
| M010-SCOPE-ISSUE-0002 | MAJOR | Combined startup is not all-or-nothing across both dependencies | PostgreSQL and object storage are initialized independently | Partial runtime readiness could be misinterpreted as platform readiness |
| M010-SCOPE-ISSUE-0003 | MAJOR | Combined shutdown order and bounded cleanup are not defined | Each adapter has `close`, but runtime has no lifecycle owner | Resource cleanup may become duplicated or inconsistent |
| M010-SCOPE-ISSUE-0004 | MAJOR | Combined readiness and failure propagation are not tested | Health aggregation exists; no both-dependency runtime test exists | Later domain modules could run when only one dependency is ready |
| M010-SCOPE-ISSUE-0005 | MAJOR | Registry read model lacks approved runtime entity and ingestion model | Skeleton `registry` package only; governance artifacts remain Markdown documents | Implementing registry tables now risks premature schema lock-in |
| M010-SCOPE-ISSUE-0006 | MAJOR | Job ledger/outbox schema and delivery semantics are not sufficiently specified in code | `orchestration.py` is a health protocol only; migrations are empty | Implementing outbox now risks creating a custom workflow engine before lifecycle semantics are constrained |
| M010-SCOPE-ISSUE-0007 | MINOR | Static health entrypoint is not yet wired to runtime health | `entrypoints/health.py` returns a static payload | Acceptable for MILESTONE-004/007, but insufficient for combined infrastructure readiness |

## 8. Candidate A Evaluation

Candidate A: Unified Infrastructure Runtime Composition.

Assessment:

| Dimension | Evaluation |
| --- | --- |
| Value | High. It closes the immediate split between persistence and object-storage startup paths. |
| Necessity | High. Any future schema, registry, evidence, outbox, or campaign module needs one runtime owner for required infrastructure. |
| Dependencies | Already available: config, logging, health, persistence adapter, object-storage adapter, fakes, local Compose services. |
| Scope | Domain-neutral. Can be limited to runtime composition, lifecycle, combined health, failure handling, and integration tests. |
| Risks | Could drift into dependency-injection framework or service container design if not bounded. |
| Current gap closed | Yes. Directly closes M010-SCOPE-ISSUE-0001 through M010-SCOPE-ISSUE-0004 and partially addresses M010-SCOPE-ISSUE-0007. |
| Existing bootstrap impact | Existing separate functions should either delegate to, or remain compatibility wrappers around, one canonical runtime composition path. |
| Missing tests | Combined startup success, persistence-fails cleanup, object-storage-fails cleanup, ordered shutdown, idempotent shutdown, combined health, integration with both Docker services. |

Decision: Candidate A is the best next MILESTONE-010.

## 9. Candidate B Evaluation

Candidate B: Job Ledger / Transactional Outbox Foundation.

Assessment:

| Dimension | Evaluation |
| --- | --- |
| Value | High later. MILESTONE-002 selects PostgreSQL job ledger / transactional outbox for initial workflow architecture. |
| Necessity | Real, but not immediate before runtime composition. |
| Dependencies | Requires PostgreSQL connectivity, migration policy, schema ownership, delivery semantics, job state model, outbox state model, idempotency rules, and worker boundary. |
| Schema justification | Not yet sufficient. MILESTONE-008 deliberately left schema/migrations/job ledger deferred. |
| Worker requirement | No worker exists. Implementing tables before lifecycle semantics and runtime ownership would be premature. |
| Delivery semantics | Exactly-once, at-least-once, retry, visibility timeout, lease, and poison-message behavior are not yet codified in the repository. |
| Design prerequisite | Yes. A focused job-ledger/outbox design or schema milestone should precede implementation unless MILESTONE-010 is restricted to design only. |

Decision: Candidate B is not recommended for immediate implementation. It should follow unified runtime composition and a narrow schema/semantics design gate.

## 10. Candidate C Evaluation

Candidate C: Governance Registry Read Model Foundation.

Assessment:

| Dimension | Evaluation |
| --- | --- |
| Exact entities | Not approved as runtime entities. Governance documents mention registries, gates, risks, deferred items, freeze states, and baselines, but the runtime data model is not defined. |
| Infrastructure vs domain | Ambiguous. Governance registry state is platform governance, but importing Markdown milestone state into runtime tables risks coupling code to document internals. |
| Source of truth | Not implemented. Existing governance documents are Markdown artifacts; no ingestion authority or synchronization mechanism exists in the repository. |
| Read-only status | Read-only does not remove the write-path problem. Data must still be populated, synchronized, versioned, and invalidated. |
| Schema approval | No approved database schema or Alembic migration exists. |
| Duplication risk | High. A runtime registry could duplicate Markdown governance artifacts without canonical import rules. |
| Traceability | Conceptually traceable to MILESTONE-001/002, but insufficiently specified for implementation now. |

Decision: Candidate C is premature for implementation. It should not be selected until the entity model, source-of-truth rule, ingestion path, synchronization behavior, and schema ownership are approved.

## 11. Other Candidate Evaluation

Candidate D: Audit Event Ledger Foundation.

Rationale for consideration: MILESTONE-002 selects a PostgreSQL audit event ledger for governance-significant events, and auditability is a core quality attribute.

Assessment: This candidate has strong traceability but shares the same blocker as Candidate B: it requires schema, append-only semantics, retention/export rules, and runtime ownership. It also depends on a unified runtime that can reliably initialize persistence and report readiness before audit writes are accepted.

Decision: Candidate D is valid later, but not recommended before Candidate A.

## 12. Comparative Score Matrix

Rubric: architectural necessity 20, traceability 15, domain neutrality 15, readiness of prerequisites 15, risk reduction 10, implementation boundedness 10, testability 5, reversibility 5, avoidance of premature schema/domain lock-in 5.

| Candidate | Necessity /20 | Traceability /15 | Domain neutrality /15 | Prerequisites /15 | Risk reduction /10 | Boundedness /10 | Testability /5 | Reversibility /5 | Avoids lock-in /5 | Total /100 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A. Unified Infrastructure Runtime Composition | 20 | 14 | 15 | 15 | 10 | 9 | 5 | 5 | 5 | 98 |
| B. Job Ledger / Transactional Outbox | 15 | 15 | 10 | 6 | 8 | 5 | 4 | 3 | 2 | 68 |
| C. Governance Registry Read Model | 12 | 12 | 8 | 3 | 6 | 4 | 3 | 3 | 1 | 52 |
| D. Audit Event Ledger Foundation | 13 | 14 | 11 | 5 | 7 | 5 | 4 | 3 | 2 | 64 |

## 13. Anti-Confirmation-Bias Review

This review explicitly tested the earlier suggestion that MILESTONE-010 should be Governance Registry Read Model Foundation.

Counter-evidence against Candidate C:

- The repository has no approved registry entity model.
- The repository has no ingestion mechanism from Markdown governance artifacts.
- "Read-only" registry still requires a write/import/synchronization path.
- The registry package is currently an empty boundary, not an executable model.
- Selecting it now would introduce the first database schema before the runtime can compose PostgreSQL and object storage together.

Counter-evidence against Candidate A:

- MILESTONE-002 sequencing lists governance registry read models before job ledger/outbox.
- MILESTONE-002 also selected job ledger/outbox as required-now workflow architecture.
- A runtime composition milestone was not named explicitly in the MILESTONE-002 sequence.

Why Candidate A still wins:

- MILESTONE-008 and MILESTONE-009 created two required infrastructure adapters through separate startup paths.
- Any registry, audit, evidence, campaign, or job/outbox implementation would depend on both PostgreSQL and object storage being owned by one reliable runtime.
- Candidate A closes an observed repository gap without creating schemas or domain lock-in.

## 14. Risks

| ID | Severity | Risk | Mitigation |
| --- | --- | --- | --- |
| M010-SCOPE-ISSUE-0008 | MEDIUM | Unified runtime composition could become a general dependency-injection framework. | Keep MILESTONE-010 limited to concrete foundation dependency lifecycle and health. |
| M010-SCOPE-ISSUE-0009 | MEDIUM | Compatibility wrappers may leave multiple authoritative startup paths. | Define one canonical initializer; older focused initializers delegate or remain explicitly test-only/focused. |
| M010-SCOPE-ISSUE-0010 | MEDIUM | Failure cleanup may be under-tested. | Require tests for persistence-fails, object-storage-fails, and partial-initialization cleanup. |
| M010-SCOPE-ISSUE-0011 | LOW | Runtime composition may defer schema progress by one milestone. | Accept because it lowers risk before first schema-bearing milestone. |

## 15. Deferred Items

| Item | Deferred until |
| --- | --- |
| Governance registry read model schema | Entity model, source-of-truth rule, ingestion path, and synchronization semantics are approved |
| Job ledger / transactional outbox tables | Runtime composition is complete and job/outbox state semantics are designed |
| Audit event ledger schema | Runtime composition is complete and append-only audit semantics are designed |
| Campaign/run/dataset/evidence metadata modules | Foundational runtime and first schema governance are complete |
| Evidence manifest/checksum model | Evidence metadata boundaries and object-storage layout are approved |
| APIs/workers | Runtime, schema, and execution semantics are approved |

## 16. Recommended MILESTONE-010

Recommended direction:

```text
Unified Infrastructure Runtime Composition
```

Recommended status at creation:

```text
DRAFT / RUNTIME COMPOSITION UNDER REVIEW
```

Rationale: The immediate bottleneck is not a missing domain model; it is the absence of one authoritative runtime that composes the already-built foundation services together. MILESTONE-010 should make PostgreSQL and object storage jointly owned, jointly health-reported, jointly lifecycle-managed, and jointly tested while remaining domain-neutral.

## 17. Explicit Scope of Recommended Milestone

MILESTONE-010 should implement only:

- one canonical infrastructure runtime initializer for base foundations plus PostgreSQL persistence plus object storage;
- explicit startup order;
- all-or-nothing startup behavior;
- partial-initialization cleanup when a later dependency fails;
- ordered shutdown;
- idempotent shutdown;
- combined health report including configuration, clocks, identifiers, logging, persistence, and object storage;
- dependency injection of fake persistence and fake object storage for deterministic tests;
- focused unit tests for combined lifecycle;
- integration test using both local PostgreSQL and local MinIO only when explicitly opted in;
- compatibility strategy for the existing base, PostgreSQL-only, and object-storage-only initializers;
- documentation in the MILESTONE-010 report.

## 18. Explicit Non-Goals

MILESTONE-010 must not implement:

- database schemas, migrations, or tables;
- governance registry read models;
- registry ingestion from Markdown documents;
- job ledger or transactional outbox;
- audit event ledger;
- campaign/run/dataset/evidence models;
- domain repositories;
- APIs;
- workers;
- vendor adapters;
- trading logic;
- empirical validation logic;
- evidence layouts or retention policies;
- Decision Candidate or Decision Freeze behavior.

## 19. Prerequisites

| Prerequisite | Status |
| --- | --- |
| MILESTONE-007 foundation runtime primitives | Met |
| MILESTONE-008 PostgreSQL connectivity foundation | Met |
| MILESTONE-009 object-storage connectivity foundation | Met |
| Fake persistence substitute | Met |
| Fake object-storage substitute | Met |
| Local Docker Compose services for PostgreSQL and MinIO | Met |
| Architecture checker | Met |
| Schema/migration approval | Not required for Candidate A |

## 20. Acceptance Boundaries

MILESTONE-010 is acceptable only if:

- a single canonical runtime can initialize both persistence and object storage;
- a failed dependency prevents a ready runtime from being returned;
- a later dependency failure closes any earlier initialized dependency;
- runtime shutdown is ordered and idempotent;
- combined health reflects both dependency layers;
- existing focused bootstrap behavior is preserved or deliberately delegated;
- no schema, migration, table, domain model, API, worker, registry, or job ledger is introduced;
- full verification remains green.

## 21. Final Decision

Candidate A is selected.

Final recommendation:

```text
MILESTONE-010 - Unified Infrastructure Runtime Composition
```

Candidate B is deferred until runtime composition is complete and job/outbox semantics are approved.

Candidate C is deferred because registry entity models, source-of-truth rules, ingestion, synchronization, and schema ownership are not yet approved.

Candidate D is deferred until runtime composition and audit ledger semantics are approved.
