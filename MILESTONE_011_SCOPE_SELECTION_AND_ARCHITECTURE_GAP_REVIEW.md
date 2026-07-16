# MILESTONE-011 - Scope Selection and Architecture Gap Review

## 1. Document Control

| Field | Value |
| --- | --- |
| Milestone | MILESTONE-011 |
| Document | MILESTONE_011_SCOPE_SELECTION_AND_ARCHITECTURE_GAP_REVIEW.md |
| Version | 1.0 |
| Status | SCOPE SELECTED / DESIGN MILESTONE REQUIRED |
| Repository Baseline | b8f3f91240aff7d743d20577ef0fd658f74cf28a |
| Scope Type | Analysis and scope selection only |
| Implementation Performed | No |
| Commit Policy | Do not stage or commit automatically |

## 2. Scope

This review selects the correct next milestone after the frozen infrastructure foundation:

- MILESTONE-007 process-local foundations;
- MILESTONE-008 PostgreSQL connectivity;
- MILESTONE-009 object-storage connectivity;
- MILESTONE-010 unified infrastructure runtime composition.

The review evaluates candidate directions, identifies the first blocked platform capability, and recommends the next milestone type and scope. It does not implement the selected milestone.

## 3. Repository Baseline

Repository state was inspected at:

```text
b8f3f91240aff7d743d20577ef0fd658f74cf28a
```

Branch state before this report was clean on `master`:

```text
master, clean working tree
```

The working tree was clean before this document was created.

## 4. Governing Documents

| Document | Repository Availability | Use in Review |
| --- | --- | --- |
| MILESTONE_001_SYSTEM_IMPLEMENTATION_ARCHITECTURE.md | Not present in repository | Referenced indirectly through integration and later milestone lineage |
| MILESTONE_002_TECHNOLOGY_SELECTION_AND_ENGINEERING_BLUEPRINT.md | Not present in repository | Referenced indirectly through implementation milestones |
| MILESTONE_003_PLATFORM_FOUNDATION_INITIALIZATION.md | Not present in repository | Referenced indirectly through MILESTONE-004 and later implementation evidence |
| MILESTONE_004_REPOSITORY_SCAFFOLDING_AND_TOOLCHAIN_BOOTSTRAP.md | Present | Repository, toolchain, and scaffold foundation |
| MILESTONE_005_INFRASTRUCTURE_ARCHITECTURE.md | Present | Infrastructure architecture and execution-boundary constraints |
| MILESTONE_006_FOUNDATION_CONTRACTS.md | Present | Foundation contracts for errors, health, logging, identifiers, persistence, object storage, and orchestration boundary |
| MILESTONE_001_006_DOCUMENT_INTEGRATION_REVIEW.md | Present | Integration lineage for 001 through 006 |
| MILESTONE_007_FIRST_INFRASTRUCTURE_IMPLEMENTATION_SLICE.md | Present | Process-local foundations |
| MILESTONE_008_PERSISTENCE_CONNECTIVITY_FOUNDATION_SLICE.md | Present | PostgreSQL connectivity and unit-of-work foundation |
| MILESTONE_009_OBJECT_STORAGE_CONNECTIVITY_FOUNDATION_SLICE.md | Present | S3-compatible object-storage connectivity foundation |
| MILESTONE_010_SCOPE_SELECTION_AND_ARCHITECTURE_GAP_REVIEW.md | Present | Selected unified runtime composition |
| MILESTONE_010_UNIFIED_INFRASTRUCTURE_RUNTIME_COMPOSITION.md | Present | Frozen unified runtime result |

M011-SCOPE-ISSUE-0001: MILESTONE-001 through MILESTONE-003 are not materialized in the repository at this baseline. This is not blocking for scope selection because the 004-010 chain, integration review, and implementation evidence provide sufficient architectural lineage. It should be resolved before future audits that require direct file-level verification of 001-003.

## 5. Current Capability Inventory

| Capability | Classification | Evidence |
| --- | --- | --- |
| Process-local foundations | IMPLEMENTED AND VERIFIED | Configuration, clocks, identifiers, logging, health, errors, placeholder entrypoints |
| PostgreSQL connectivity / unit of work | IMPLEMENTED AND VERIFIED | SQLAlchemy Core engine, transaction semantics, health, integration tests |
| Object storage | IMPLEMENTED AND VERIFIED | S3-compatible adapter, fake adapter, MinIO integration tests |
| Unified runtime | IMPLEMENTED AND VERIFIED | `initialize_infrastructure_runtime`, lifecycle, combined health, PostgreSQL plus MinIO integration |
| Runtime lifecycle | IMPLEMENTED AND VERIFIED | NEW, STARTING, READY, STOPPING, STOPPED, FAILED |
| Health/readiness | IMPLEMENTED AND VERIFIED | Multi-axis health model and combined runtime health |
| Domain entity model | DESIGNED ONLY / NOT YET IMPLEMENTED | Boundary packages exist, but no runtime entities or invariants |
| Campaign/run/dataset/evidence concepts | DESIGNED ONLY | Identifier types and empty boundary packages exist; no domain model |
| Governance registry | DESIGNED ONLY / EXPLICITLY DEFERRED | `registry` package boundary exists; no runtime model or write path |
| Job ledger | DESIGNED ONLY / EXPLICITLY DEFERRED | Orchestration interface placeholder exists; no table or runtime behavior |
| Transactional outbox | NOT YET DESIGNED | No delivery semantics or schema exists |
| Audit event ledger | NOT YET DESIGNED | Audit package boundary exists; no event model or persistence |
| Orchestration | DESIGNED ONLY | Interface boundary only |
| Workers | NOT YET DESIGNED | No worker runtime or scheduler |
| APIs | PARTIALLY IMPLEMENTED | Static health/version placeholders only |
| Production entrypoint | PARTIALLY IMPLEMENTED | CLI placeholders exist; no runtime-serving process |
| Telemetry/export | EXPLICITLY DEFERRED | Logging and health exist; no metrics/tracing exporter |
| Authentication | NOT YET DESIGNED | No auth model or implementation |
| Persistence schemas | EXPLICITLY DEFERRED | `migrations/versions` remains empty |
| Storage layouts | EXPLICITLY DEFERRED | No domain bucket/object hierarchy |

## 6. Current Runtime Topology

The current topology is:

```text
Process-local foundations
        |
        v
Unified infrastructure runtime
        |
        +--> PostgreSQL connectivity and unit-of-work abstraction
        |
        +--> S3-compatible object-storage abstraction
        |
        +--> Combined health/readiness and lifecycle state
```

The topology proves infrastructure connectivity, dependency readiness, error translation, and shutdown ownership. It intentionally does not define business runtime objects.

## 7. Remaining Architecture Gaps

The major remaining gaps are:

- no canonical runtime entity model for Campaign, Run, Dataset, Evidence Package, Review, Audit, or Decision Candidate;
- no frozen state machines for those entities;
- no persistence ownership rules for domain metadata;
- no object-storage layout rules for evidence artifacts;
- no domain invariants or aggregate boundaries;
- no orchestration semantics for future asynchronous work;
- no event delivery or transactional outbox semantics;
- no audit event ledger model;
- no production runtime process boundary beyond placeholders.

The first irreversible design pressure is not infrastructure connectivity. It is the shape of the domain kernel that would determine future schema, storage layout, orchestration, and API boundaries.

## 8. First Blocked Platform Capability

The first blocked platform capability is implementing any real campaign-oriented platform behavior.

That capability is blocked because the repository does not yet define:

- which runtime entity or aggregate is created first;
- canonical entity fields and identity rules;
- state transition rules;
- persistence boundaries;
- storage-reference boundaries;
- audit and traceability hooks;
- whether job ledger or outbox semantics are prerequisites for the first behavior.

Without those decisions, adding schemas, repositories, APIs, workers, or ledgers would lock in domain assumptions too early.

## 9. Candidate A Evaluation

Candidate A: Job Ledger and Transactional Outbox Design.

| Dimension | Assessment |
| --- | --- |
| Traceability | Supported by orchestration boundary and future execution needs |
| Infrastructure or domain | Cross-cutting infrastructure, but event contents are domain-dependent |
| Tables justified now | Not yet; no first async workflow or event model is frozen |
| Delivery semantics | Not frozen |
| Idempotency requirements | Not tied to concrete domain commands yet |
| Retry semantics | Premature without worker model |
| Transaction boundaries | Need domain metadata model first |
| Worker dependency | High |
| Design before implementation | Required eventually |
| Lock-in risk | High if designed before domain entities |

Result: important but premature. Job ledger/outbox design should follow the first domain kernel design or be included only as a dependency placeholder.

Score: 68 / 100.

## 10. Candidate B Evaluation

Candidate B: Governance Registry Model.

| Dimension | Assessment |
| --- | --- |
| Exact entities | Not frozen as runtime software objects |
| Source of truth | Markdown governance documents remain the current source |
| Ingestion path | Not defined |
| Relationship to documents | Risk of duplicating document governance |
| Runtime ownership | Not yet justified |
| Write semantics | Not defined |
| Coupling risk | High |

Result: premature as runtime software. It should remain document-governance unless a later milestone defines ingestion, source-of-truth, and read/write semantics.

Score: 45 / 100.

## 11. Candidate C Evaluation

Candidate C: First Domain Kernel / Canonical Runtime Entities.

| Dimension | Assessment |
| --- | --- |
| Candidate first entities | Campaign, Run, Dataset, Evidence Package, Criterion Result, Review, Audit, Decision Candidate references |
| Invariants | Not yet frozen in software terms |
| State machines | Governance lifecycle exists, but runtime state transitions are not yet specified |
| Persistence requirements | Need design before schema |
| Object-storage layout | Must be referenced but can remain deferred |
| Job infrastructure prerequisite | Not for design; can remain deferred |
| Design without implementation | Yes |

Result: strongest next step. The next real capability needs a canonical runtime entity model before any schema, repository, API, worker, ledger, or storage layout is safe.

Score: 90 / 100.

## 12. Candidate D Evaluation

Candidate D: Production Entrypoint and Runtime Wiring.

| Dimension | Assessment |
| --- | --- |
| Runtime gap | Unified runtime lacks a long-running production process |
| Meaningful capability | Limited without domain behavior |
| API/worker boundary | Not designed |
| Long-running process readiness | Premature |
| Risk reduction | Moderate for deployment, low for domain correctness |

Result: useful later, but it would mostly wire infrastructure without enabling the first real platform behavior.

Score: 58 / 100.

## 13. Candidate E Evaluation

Candidate E: Observability and Telemetry Foundation.

| Dimension | Assessment |
| --- | --- |
| Current sufficiency | Structured logging and health are sufficient for the next design step |
| Metrics/tracing need | Real, but not blocking first domain design |
| Exporter selection | Premature |
| Risk closure | Moderate operational benefit, low architectural unblock |
| Vendor neutrality | Achievable, but not urgent |

Result: can remain deferred until runtime behavior exists to observe.

Score: 55 / 100.

## 14. Additional Candidate Evaluation, if any

No separate additional candidate is introduced. A "Canonical Domain Model Specification" or "State Machine Foundation" would duplicate Candidate C. Candidate C should be scoped precisely enough to cover canonical runtime entities, invariants, state machines, and persistence/storage boundary decisions without implementing them.

## 15. Comparative Score Matrix

| Candidate | Architectural Necessity /20 | Traceability /15 | Prerequisite Readiness /15 | Risk Reduction /15 | Lock-In Avoidance /10 | Boundedness /10 | Testability /5 | Reversibility /5 | Enables Next Capability /5 | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A. Job Ledger and Transactional Outbox Design | 14 | 12 | 8 | 11 | 6 | 7 | 4 | 3 | 3 | 68 |
| B. Governance Registry Model | 8 | 8 | 5 | 6 | 4 | 6 | 3 | 3 | 2 | 45 |
| C. First Domain Kernel / Canonical Runtime Entities | 20 | 14 | 13 | 14 | 9 | 9 | 3 | 4 | 4 | 90 |
| D. Production Entrypoint and Runtime Wiring | 11 | 10 | 8 | 8 | 8 | 7 | 3 | 2 | 1 | 58 |
| E. Observability and Telemetry Foundation | 10 | 9 | 8 | 7 | 8 | 7 | 3 | 2 | 1 | 55 |

## 16. Anti-Confirmation-Bias Review

This review did not assume that the first domain kernel must be next. The strongest counterargument is that job ledger/outbox design can prevent later rework. That argument fails at this point because no first domain command, aggregate, state transition, or event payload exists. Designing delivery semantics without domain ownership would either stay abstract or hard-code guesses.

The strongest counterargument for production entrypoint work is that the unified runtime is not yet started by a real process. That is true, but a runnable process with no domain behavior would validate little beyond what MILESTONE-010 already proves.

The strongest counterargument for observability is operational maturity. That is valid, but existing health and logging are adequate for designing the first domain kernel.

## 17. Schema and Domain Lock-In Analysis

The highest lock-in risk is creating tables before entity boundaries and state machines are frozen. Campaign, Run, Dataset, Evidence Package, Review, Audit, and Decision Candidate concepts are governance-visible but not yet software-model precise.

The next milestone should avoid:

- database schemas;
- migration revisions;
- repositories;
- object-storage folder/key layouts;
- event/outbox tables;
- API request/response contracts;
- worker behavior.

It should instead define the canonical domain kernel with enough precision to make later schema and repository design reversible and evidence-based.

## 18. Dependency and Sequencing Analysis

Recommended sequence:

```text
MILESTONE-011 Scope Selection
        |
        v
MILESTONE-012 Canonical Runtime Domain Kernel Design
        |
        v
MILESTONE-013 Domain Metadata Persistence Design
        |
        v
MILESTONE-014 Repository and State Transition Implementation Slice
        |
        v
Job Ledger / Outbox Design or Production Entrypoint, depending on first domain workflow
```

This sequence preserves the infrastructure foundation while avoiding premature schema, event, or runtime-process choices.

## 19. Recommended MILESTONE-011

The recommended next milestone is:

```text
MILESTONE-012 - Canonical Runtime Domain Kernel Design
```

This recommendation means the next actual milestone after this scope-selection report should design, but not implement, the first domain kernel for campaign-oriented runtime behavior.

## 20. Milestone Type Decision

Decision:

```text
DESIGN MILESTONE REQUIRED
```

Reason: schemas, state machines, aggregate boundaries, domain invariants, persistence ownership, and storage-reference rules are not frozen. Implementation would be premature.

## 21. Exact Scope

The next milestone should define:

- canonical runtime entities;
- entity identity and identifier usage;
- aggregate boundaries;
- required fields at the design level;
- lifecycle/state machines;
- allowed transitions;
- invariants;
- relationships between Campaign, Run, Dataset, Evidence Package, Criterion Result, Review, Audit, and Decision Candidate;
- persistence boundary requirements without schema;
- object-storage reference requirements without layout;
- audit/traceability hooks without event ledger implementation;
- repository and outbox prerequisites for later milestones.

## 22. Exact Non-Goals

The next milestone must not:

- create schemas or migrations;
- create tables;
- implement repositories;
- implement job ledger or transactional outbox;
- implement governance registry;
- implement audit event ledger;
- implement APIs;
- implement workers or schedulers;
- implement campaign execution;
- implement vendor/trading behavior;
- define object-storage domain layout;
- create a Decision Candidate or Decision Freeze.

## 23. Prerequisites

Prerequisites for the next design milestone:

- MILESTONE-010 remains approved and frozen;
- MILESTONE-001 through MILESTONE-003 should be materialized into the repository or explicitly linked for direct future audit;
- current identifier type inventory should be reviewed against the domain kernel;
- deferred schema and storage-layout constraints from MILESTONE-008 through MILESTONE-010 should remain active.

## 24. Risks

| Risk ID | Severity | Description | Mitigation |
| --- | --- | --- | --- |
| M011-SCOPE-ISSUE-0001 | MINOR | MILESTONE-001 through MILESTONE-003 are absent from the repository | Materialize or register those documents before future integration audits |
| M011-SCOPE-ISSUE-0002 | MAJOR | Implementing schemas before domain state machines are frozen would create hard-to-reverse lock-in | Use a design-only domain-kernel milestone next |
| M011-SCOPE-ISSUE-0003 | MAJOR | Designing job ledger/outbox before domain commands exist could create abstract or incorrect delivery semantics | Defer ledger/outbox until domain kernel and first workflow are defined |
| M011-SCOPE-ISSUE-0004 | MINOR | Production entrypoint work could become superficial wiring | Defer until it validates real domain behavior |

## 25. Acceptance Boundaries

This report is complete only if:

- repository baseline is confirmed;
- current capabilities are classified;
- all five named candidate directions are evaluated;
- scoring is explicit;
- schema and lock-in risks are addressed;
- the next milestone type is selected;
- no implementation, schema, migration, table, repository, API, worker, registry, ledger, outbox, or domain behavior is introduced.

## 26. Final Decision

Final decision:

```text
DESIGN MILESTONE REQUIRED
```

Recommended next mission:

```text
MILESTONE-012 - Canonical Runtime Domain Kernel Design
```

MILESTONE-011 selects the next scope only. It does not implement that scope.
