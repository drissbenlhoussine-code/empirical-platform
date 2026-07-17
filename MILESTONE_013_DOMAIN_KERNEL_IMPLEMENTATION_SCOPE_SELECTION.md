# MILESTONE-013 - Domain Kernel Implementation Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-013 |
| Title | Domain Kernel Implementation Scope Selection |
| Version | 1.0 |
| Status | IMPLEMENTATION SLICE READY |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Repository baseline | `cb10fe87b2d2ac171a4ad4d6b0987f423e5a887f` |
| Mission type | Scope selection and architecture gap review only |
| Implementation performed | None |
| Source code modified | No |
| Schema, migration, or table created | No |
| Commit policy | Not staged and not committed by this mission |

## 2. Scope

This document selects the next implementation scope after the approved and frozen MILESTONE-012 canonical runtime domain kernel design.

The mission reviews the repository, governing documents, implemented capabilities, deferred boundaries, and design risks to decide whether the next milestone can safely implement a narrow domain-kernel slice.

This document does not implement code, create schemas, create migrations, define repositories, create APIs, add workers, add job ledger behavior, add outbox behavior, execute campaigns, validate vendors, create a Decision Candidate, or perform a Decision Freeze.

## 3. Repository Baseline

The repository baseline for this review is:

```text
cb10fe87b2d2ac171a4ad4d6b0987f423e5a887f
```

Observed repository state at review:

- branch: `master`;
- working tree before report creation: clean;
- MILESTONE-012 freeze correction is the current HEAD;
- `migrations/versions` contains no migration revisions;
- source packages for campaign, datasets, evidence, review, audit, archive, registry, validation, acquisition, and normalization exist as boundaries but do not contain domain behavior;
- the repository contains infrastructure foundations for configuration, logging, errors, health, runtime identifiers, persistence connectivity, object-storage connectivity, and unified runtime composition.

## 4. Governing Documents

| Document | Status / Role | Relevance to MILESTONE-013 |
| --- | --- | --- |
| `MILESTONE_005_INFRASTRUCTURE_ARCHITECTURE.md` | Approved infrastructure architecture | Domain code may depend on foundation layers; foundation layers must not depend on domain code |
| `MILESTONE_006_FOUNDATION_CONTRACTS.md` | Approved foundation contracts | Foundation identifiers, errors, health, persistence, storage, and orchestration boundaries |
| `MILESTONE_007_FIRST_INFRASTRUCTURE_IMPLEMENTATION_SLICE.md` | Approved implementation evidence | Runtime identifier and foundation behavior exists |
| `MILESTONE_008_PERSISTENCE_CONNECTIVITY_FOUNDATION_SLICE.md` | Approved implementation evidence | PostgreSQL connectivity exists without schema ownership |
| `MILESTONE_009_OBJECT_STORAGE_CONNECTIVITY_FOUNDATION_SLICE.md` | Approved implementation evidence | Object storage connectivity exists without domain layout or retention policy |
| `MILESTONE_010_UNIFIED_INFRASTRUCTURE_RUNTIME_COMPOSITION.md` | Approved implementation evidence | Foundation services can be composed without domain behavior |
| `MILESTONE_011_SCOPE_SELECTION_AND_ARCHITECTURE_GAP_REVIEW.md` | Scope selection predecessor | Selected MILESTONE-012 as the required design gate before domain implementation |
| `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` | Approved and frozen | Defines aggregate roots, entity ownership, lifecycles, invariants, persistence boundaries, and explicit deferrals |
| `MILESTONE_012_EXTERNAL_ARTIFACT_REGISTRATION_AND_BASELINE_RECONCILIATION.md` | Registered baseline reconciliation | Confirms external artifacts are informative or non-normative for freeze unless otherwise classified |
| `docs/governance/baseline/manifest/MILESTONE_012_EXTERNAL_BASELINE_MANIFEST.md` | Registered artifact manifest | Provides traceability without turning all external drafts into freeze prerequisites |

## 5. Current Capability Inventory

Implemented and verified capabilities:

- Python 3.13 project scaffold, package layout, and quality tooling;
- module-boundary architecture checks with negative fixture;
- static health and version entrypoints;
- foundation configuration and safe redaction;
- structured logging foundation;
- foundation error categories and translation boundaries;
- governance identifier value objects for `CAMP`, `RUN`, `DATASET`, `EVID`, `REVIEW`, `AUD`, and `DCAND`;
- opaque runtime UUIDv4 identifiers and deterministic test generator;
- PostgreSQL connectivity foundation, unit-of-work semantics, and health reporting without schemas;
- S3-compatible object-storage connectivity foundation without domain object layout;
- unified runtime composition for foundation dependencies.

Designed but not implemented:

- Campaign, Run, Evidence Package, and Review aggregate roots;
- Dataset Manifest as an immutable owned record under Run;
- Criterion Result as an owned entity under Evidence Package;
- aggregate versioning, transition sequencing, state transition records, and domain lifecycle enums;
- domain commands, repositories, schemas, migrations, event vocabulary implementation, APIs, workers, audit runtime, and Decision Candidate runtime.

Explicitly absent:

- ORM entity mappings;
- domain tables;
- Alembic migration revisions;
- domain repositories;
- business queries;
- job ledger or transactional outbox;
- audit ledger;
- object-storage layout, bucket hierarchy, key conventions, retention rules, or evidence sealing implementation;
- campaign execution, vendor behavior, market-data behavior, B3 criteria, empirical validation, trading logic, Decision Candidate, and Decision Freeze.

## 6. Frozen Domain Model Summary

MILESTONE-012 freezes the initial runtime domain kernel around four aggregate roots:

| Aggregate root | Core responsibility | Initial implementation relevance |
| --- | --- | --- |
| Campaign | Campaign scope, authorization status, and high-level lifecycle | Requires identifiers, lifecycle states, versioning, and transition record primitives before behavior |
| Run | One execution attempt under one Campaign; owns Dataset Manifests | Requires Run lifecycle states, immutable scope/manifest primitives, and rerun identity rules |
| Evidence Package | Evidence package lifecycle, seal/invalidation concepts, object references, and Criterion Results | Requires package lifecycle states, immutable Criterion Result primitives, and seal-aware invariants later |
| Review | Independent review assignment, findings, and disposition | Requires Review lifecycle states and review disposition separation before behavior |

MILESTONE-012 defers Audit and Decision Candidate runtime aggregates. It also explicitly prohibits schemas, migrations, repositories, APIs, workers, job ledger, outbox, audit event ledger, object-storage layouts, bucket conventions, key conventions, retention policy, campaign execution, vendor behavior, Decision Candidate behavior, and Decision Freeze behavior in the initial kernel design.

## 7. Current Implementation Gap

The first implementation gap after MILESTONE-012 is not infrastructure connectivity and not persistence. It is the absence of process-local domain primitives that can express the frozen kernel without committing to a database schema.

The repository already contains governance ID wrappers and runtime UUID wrappers. It does not yet contain:

- domain lifecycle state enums for Campaign, Run, Evidence Package, and Review;
- review disposition values separate from Review lifecycle states;
- aggregate version and transition sequence primitives;
- immutable state transition record structure;
- immutable Dataset Manifest primitive;
- immutable Criterion Result primitive;
- tests proving those primitives are immutable, bounded, and dependency-clean;
- architecture checks confirming the domain primitives do not import persistence, object storage, bootstrap composition, entrypoints, or infrastructure adapters.

## 8. First Blocked Capability

The first blocked capability is any safe implementation of aggregate behavior.

Aggregate behavior cannot be implemented cleanly until the repository has shared domain primitives for:

- lifecycle states;
- immutable transition records;
- aggregate versioning;
- transition sequencing;
- identity pairing between governance IDs and runtime UUIDs;
- immutable owned records used by Run and Evidence Package.

Implementing schemas, repositories, outbox, APIs, or workers before those primitives would force persistence and integration decisions to define the domain indirectly.

## 9. Candidate A Evaluation

Candidate A: Domain Value Objects and Identity Foundation.

Scope considered:

- reuse existing governance ID wrappers instead of rewriting them;
- reuse existing runtime UUID wrapper instead of rewriting it;
- add missing aggregate version and transition sequence primitives;
- add state transition record primitives;
- add lifecycle state enums for Campaign, Run, Evidence Package, and Review;
- add Review disposition values separate from Review lifecycle;
- add immutable Dataset Manifest and Criterion Result primitives, with no persistence mapping and no behavior beyond local validation/immutability;
- add unit tests and architecture-boundary tests only.

Evaluation:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 19 | Aggregate behavior, schemas, repositories, and events all require these primitives |
| Traceability to frozen MILESTONE-012 /15 | 15 | Directly implements MILESTONE-012 Sections 7, 13-18, 21, 22, 24, and 26 without expanding scope |
| Prerequisite readiness /15 | 14 | Foundation IDs and runtime UUIDs already exist; only missing domain primitives remain |
| Risk reduction /15 | 15 | Prevents schemas and repositories from inventing lifecycle or immutability semantics |
| Schema lock-in avoidance /10 | 10 | Fully process-local and schema-free |
| Testability /10 | 10 | Can be tested with unit tests and architecture checks only |
| Reversibility /5 | 5 | Small primitives can be adjusted before persistence lock-in |
| Boundedness /5 | 5 | No external dependencies, no adapters, no runtime process |
| Enables next capability /5 | 5 | Enables aggregate behavior and later persistence design |
| Total /100 | 98 | Recommended |

Decision: Candidate A is the strongest immediate implementation slice, provided it is narrowed to missing domain primitives and does not duplicate existing identifier code.

## 10. Candidate B Evaluation

Candidate B: Process-Local Aggregate Behavior for Campaign, Run, Evidence Package, and Review.

Scope considered:

- implement aggregate classes;
- enforce lifecycle transitions;
- enforce local invariants;
- produce internal transition records;
- avoid persistence and external integration.

Evaluation:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 20 | Aggregate behavior is the first real domain capability |
| Traceability to frozen MILESTONE-012 /15 | 15 | Directly traceable to the frozen aggregate model |
| Prerequisite readiness /15 | 10 | Missing primitives would either be implemented ad hoc or bundled into a larger slice |
| Risk reduction /15 | 13 | Reduces ambiguity but is riskier if primitives are not separated first |
| Schema lock-in avoidance /10 | 9 | Can be schema-free if carefully constrained |
| Testability /10 | 9 | Highly testable, but test surface is broader than Candidate A |
| Reversibility /5 | 4 | Aggregate APIs become harder to revise once tests and future modules depend on them |
| Boundedness /5 | 3 | Four aggregate roots plus owned records is larger than the safest first slice |
| Enables next capability /5 | 5 | Enables persistence design and first command workflows |
| Total /100 | 88 | Defer until Candidate A is complete |

Decision: Candidate B should follow Candidate A. It is implementation-ready conceptually, but too broad as the first code-bearing domain milestone after a design freeze.

## 11. Candidate C Evaluation

Candidate C: Domain Metadata Schema Design.

Scope considered:

- design tables, columns, constraints, indexes, and migration ownership for Campaign, Run, Evidence Package, Review, Dataset Manifest, and Criterion Result metadata.

Evaluation:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 17 | Persistence will be necessary, but not before process-local primitives exist |
| Traceability to frozen MILESTONE-012 /15 | 12 | MILESTONE-012 defines persistence boundaries but explicitly avoids schema details |
| Prerequisite readiness /15 | 7 | Aggregate behavior and primitive model are not yet implemented |
| Risk reduction /15 | 10 | Could reduce future storage ambiguity but creates premature lock-in |
| Schema lock-in avoidance /10 | 2 | This is the first schema-locking step |
| Testability /10 | 6 | Reviewable as design; not executable without implementation |
| Reversibility /5 | 2 | Schema decisions become expensive to reverse |
| Boundedness /5 | 3 | Would need many entity and relationship decisions at once |
| Enables next capability /5 | 4 | Enables migration work later, but not safely yet |
| Total /100 | 63 | Premature |

Decision: Candidate C is not recommended for MILESTONE-013.

## 12. Candidate D Evaluation

Candidate D: Persistence Implementation for Domain Metadata.

Scope considered:

- add migrations;
- add tables;
- add repositories;
- persist aggregate metadata and lifecycle transition history.

Evaluation:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 16 | Necessary later |
| Traceability to frozen MILESTONE-012 /15 | 10 | MILESTONE-012 explicitly says no schema, table, migration, ORM mapping, or repository API is defined |
| Prerequisite readiness /15 | 3 | Missing schema design, primitive implementation, aggregate behavior, and repository contract design |
| Risk reduction /15 | 6 | Would create more risk than it removes now |
| Schema lock-in avoidance /10 | 0 | Direct schema lock-in |
| Testability /10 | 7 | Testable but premature |
| Reversibility /5 | 1 | Low reversibility after migrations and repository contracts exist |
| Boundedness /5 | 1 | Too broad for this point |
| Enables next capability /5 | 3 | Enables durable behavior later, but unsafe now |
| Total /100 | 47 | Not ready |

Decision: Candidate D is blocked by missing domain primitive and schema-design prerequisites.

## 13. Candidate E Evaluation

Candidate E: Event, Job Ledger, or Transactional Outbox Design.

Scope considered:

- design event delivery semantics;
- design outbox or job ledger schema;
- define worker semantics and retry rules.

Evaluation:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 12 | Important later for durable workflows |
| Traceability to frozen MILESTONE-012 /15 | 8 | MILESTONE-012 defines domain event vocabulary but explicitly avoids outbox schema, event store, queue, or dispatcher design |
| Prerequisite readiness /15 | 4 | No first domain command or aggregate implementation exists |
| Risk reduction /15 | 6 | Could help later but would be abstract now |
| Schema lock-in avoidance /10 | 3 | Delivery semantics often imply schema and operational constraints |
| Testability /10 | 4 | Hard to validate without domain commands |
| Reversibility /5 | 2 | Low once delivery semantics are fixed |
| Boundedness /5 | 2 | Cross-cutting and operationally broad |
| Enables next capability /5 | 2 | Does not enable first aggregate implementation as directly as Candidate A |
| Total /100 | 43 | Premature |

Decision: Candidate E remains deferred until domain commands and aggregate behavior exist.

## 14. Candidate F Evaluation

Candidate F: Review-Only Domain Slice.

Scope considered:

- implement Review lifecycle and disposition first;
- avoid Campaign, Run, and Evidence Package behavior.

Evaluation:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 13 | Review is important but depends on reviewable targets |
| Traceability to frozen MILESTONE-012 /15 | 12 | Review lifecycle is frozen, but target existence and evidence references are not implemented |
| Prerequisite readiness /15 | 8 | Review primitives are ready to define, but Review aggregate behavior lacks Run/Evidence Package targets |
| Risk reduction /15 | 8 | Helps independence modeling but does not unblock broader kernel |
| Schema lock-in avoidance /10 | 8 | Can be process-local |
| Testability /10 | 8 | Lifecycle/disposition tests are straightforward |
| Reversibility /5 | 4 | Fairly reversible if primitive-only |
| Boundedness /5 | 4 | Narrow but incomplete |
| Enables next capability /5 | 3 | Enables review behavior but not the first execution chain |
| Total /100 | 68 | Defer or include only the disposition primitive in Candidate A |

Decision: Candidate F is too narrow as a standalone milestone. Its lifecycle and disposition primitives should be included in Candidate A.

## 15. Additional Candidate Evaluation, if any

Additional candidate considered: Domain Test Harness and Contract Fixtures.

This could add only fixtures and testing helpers for future aggregate behavior. It is useful, but as a standalone milestone it would create test scaffolding before the primitives being tested exist. The appropriate treatment is to include focused unit tests and architecture-boundary checks inside Candidate A, not to create a separate milestone.

No additional candidate is recommended.

## 16. Comparative Score Matrix

| Candidate | Architectural necessity /20 | Traceability /15 | Prerequisite readiness /15 | Risk reduction /15 | Schema lock-in avoidance /10 | Testability /10 | Reversibility /5 | Boundedness /5 | Enables next capability /5 | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A. Domain Value Objects and Identity Foundation | 19 | 15 | 14 | 15 | 10 | 10 | 5 | 5 | 5 | 98 |
| B. Process-Local Aggregate Behavior | 20 | 15 | 10 | 13 | 9 | 9 | 4 | 3 | 5 | 88 |
| C. Domain Metadata Schema Design | 17 | 12 | 7 | 10 | 2 | 6 | 2 | 3 | 4 | 63 |
| D. Domain Persistence Implementation | 16 | 10 | 3 | 6 | 0 | 7 | 1 | 1 | 3 | 47 |
| E. Event, Job Ledger, or Outbox Design | 12 | 8 | 4 | 6 | 3 | 4 | 2 | 2 | 2 | 43 |
| F. Review-Only Domain Slice | 13 | 12 | 8 | 8 | 8 | 8 | 4 | 4 | 3 | 68 |

## 17. Anti-Confirmation-Bias Review

Counterargument against Candidate A:

- Existing identifier wrappers already exist, so implementing "identity foundation" could duplicate code.

Resolution:

- The recommended scope must reuse existing `empirical_platform.identifiers` and `empirical_platform.shared.identifiers` rather than reimplementing them. The scope is not "all IDs"; it is the missing process-local domain primitives around versioning, lifecycle, transition records, Dataset Manifest, and Criterion Result.

Counterargument for Candidate B:

- MILESTONE-012 is frozen, so aggregate behavior may be ready now.

Resolution:

- Aggregate behavior is nearly ready, but implementing four aggregate roots as the first domain code slice would bundle lifecycle enums, versioning, transition records, owned records, invariant enforcement, and command methods into one large change. Candidate A makes Candidate B smaller, more testable, and less likely to entangle persistence assumptions.

Counterargument for Candidate C or D:

- Persistent metadata is necessary for real campaigns.

Resolution:

- True, but premature. MILESTONE-012 explicitly stops short of schema and repository design. The repository has `migrations/versions` empty by policy. Schema work should follow implemented process-local primitives and aggregate behavior.

Counterargument for Candidate E:

- Event and outbox semantics should be designed before domain commands produce events.

Resolution:

- MILESTONE-012 only defines event vocabulary and explicitly avoids outbox/event-store/dispatcher design. The next code slice should generate no durable events. Internal transition records can exist without outbox semantics.

## 18. Schema Lock-In Analysis

Candidate A has the lowest schema lock-in risk because it:

- introduces no table;
- introduces no migration;
- introduces no ORM mapping;
- introduces no repository interface;
- introduces no serialization contract beyond in-process value semantics;
- does not select persistence keys, indexes, or foreign-key strategy;
- preserves MILESTONE-012's explicit deferral of schema, repository, outbox, and audit-ledger decisions.

The primary lock-in risk inside Candidate A is naming. That risk is acceptable because MILESTONE-012 already freezes the canonical domain terms: Campaign, Run, Evidence Package, Review, Dataset Manifest, Criterion Result, AggregateVersion, TransitionSequence, and StateTransitionRecord.

## 19. Dependency and Sequencing Analysis

Recommended sequence from the current baseline:

```text
MILESTONE-012 approved domain kernel design
        |
        v
MILESTONE-013 process-local domain primitives
        |
        v
MILESTONE-014 process-local aggregate behavior
        |
        v
MILESTONE-015 domain metadata persistence design
        |
        v
MILESTONE-016 domain metadata schema/migration slice
        |
        v
MILESTONE-017 repository contracts and durable aggregate persistence
```

This sequence avoids letting persistence, object storage, event delivery, or APIs become the accidental owner of domain semantics.

## 20. Recommended MILESTONE-013

Recommended MILESTONE-013:

```text
MILESTONE-013 - Process-Local Domain Primitive Foundation
```

Purpose:

Implement the minimal process-local domain primitives required by MILESTONE-012 before aggregate behavior, persistence schema, repository contracts, APIs, workers, event delivery, audit runtime, or Decision Candidate behavior.

Recommended status at creation:

```text
DRAFT / DOMAIN PRIMITIVE FOUNDATION UNDER REVIEW
```

Final target status if implementation passes:

```text
APPROVED AND FROZEN
```

## 21. Milestone Type Decision

Selected milestone type:

```text
IMPLEMENTATION SLICE READY
```

Rationale:

- MILESTONE-012 is approved and frozen;
- the required behavior is local and bounded;
- no schema, persistence, object storage, API, worker, job ledger, outbox, audit ledger, campaign execution, vendor behavior, or Decision Candidate behavior is required;
- the implementation can be fully verified with unit tests, import checks, architecture checks, type checks, and existing repository verification.

## 22. Exact Implementation Scope

MILESTONE-013 should implement only:

- missing domain lifecycle enums for Campaign, Run, Evidence Package, and Review, matching MILESTONE-012 lifecycle names exactly;
- Review disposition enum separate from Review lifecycle state;
- `AggregateVersion` primitive;
- `TransitionSequence` primitive;
- immutable `StateTransitionRecord` primitive;
- identity-pairing primitives or helpers that pair existing governance IDs with existing runtime UUIDs without reimplementing either;
- immutable `DatasetManifest` primitive scoped as an owned record under Run;
- immutable `CriterionResult` primitive scoped as an owned entity under Evidence Package;
- local validation required to preserve MILESTONE-012's process-local invariants;
- unit tests for construction, invalid input rejection, immutability, equality, ordering where applicable, and separation of lifecycle state from disposition;
- architecture-boundary enforcement proving domain primitives do not import infrastructure adapters, persistence implementations, object-storage implementations, entrypoints, bootstrap runtime composition, or tests.

Recommended source placement:

- use existing domain boundary packages under `src/empirical_platform/`;
- reuse `src/empirical_platform/identifiers/` and `src/empirical_platform/shared/identifiers.py`;
- keep shared domain-neutral primitives in a narrowly named shared/domain module only if multiple aggregates need them;
- keep aggregate-specific primitives inside the owning domain package when they are not shared.

Any exact file layout must respect `tools/check_architecture.py` and existing module-boundary rules.

## 23. Exact Non-Goals

MILESTONE-013 must not implement:

- Campaign aggregate behavior;
- Run aggregate behavior;
- Evidence Package aggregate behavior;
- Review aggregate behavior;
- domain command handlers;
- application services;
- persistence schemas, migrations, tables, columns, constraints, indexes, or seed data;
- ORM mappings;
- repository protocols or concrete repositories;
- API routes or production endpoints;
- background workers;
- job ledger;
- transactional outbox;
- event store;
- audit event ledger;
- governance registry runtime;
- object-storage layout, bucket hierarchy, key convention, retention policy, or evidence sealing implementation;
- campaign execution;
- empirical validation;
- B3 criteria;
- vendor adapters;
- market-data acquisition;
- trading behavior;
- Decision Candidate behavior;
- Decision Freeze behavior.

## 24. Invariants Included

MILESTONE-013 should include only invariants that can be enforced locally by primitives:

| Invariant | Included enforcement |
| --- | --- |
| Governance IDs are distinct from runtime UUIDs | Reuse existing ID classes and runtime UUID class; pairing helper must not substitute one for the other |
| AggregateVersion is non-negative and monotonic by explicit next-step operation | Primitive validation and successor operation |
| TransitionSequence is positive or starts at the approved initial value and advances monotonically by explicit successor operation | Primitive validation and successor operation |
| StateTransitionRecord is immutable | Frozen dataclass or equivalent immutable model |
| StateTransitionRecord records from-state, to-state, actor/reference context, timestamp, version, and transition sequence without becoming a durable event | Primitive shape and naming |
| Campaign lifecycle enum contains only MILESTONE-012 Campaign lifecycle states | Exact enum membership tests |
| Run lifecycle enum contains only MILESTONE-012 Run lifecycle states | Exact enum membership tests |
| Evidence Package lifecycle enum contains only MILESTONE-012 Evidence Package lifecycle states | Exact enum membership tests |
| Review lifecycle and Review disposition remain separate | Separate primitives and tests |
| Dataset Manifest is immutable after creation | Immutable primitive and mutation rejection tests |
| Criterion Result is immutable after creation as a primitive | Immutable primitive and mutation rejection tests |

## 25. Invariants Deferred

The following invariants require aggregate behavior, persistence, or cross-aggregate coordination and must remain deferred:

- Campaign completion requires no active Runs;
- Run belongs to exactly one persisted Campaign;
- Run authorized scope snapshot mutation is rejected by a command handler;
- rerun creates a new persisted Run identity;
- Dataset Manifest supersession through Run behavior;
- Criterion Result cannot change after Evidence Package sealing;
- Evidence Package sealing, invalidation, and integrity verification;
- Review target must exist and be reviewable;
- reviewer independence gate enforcement;
- evidence invalidation making prior Review stale or qualified;
- Decision Candidate evidence sufficiency;
- durable transition history;
- optimistic-concurrency checks against persistent aggregate version;
- repository-level uniqueness;
- schema-level referential integrity.

## 26. Testing Strategy

Required tests for the next implementation milestone:

- unit tests for every lifecycle enum and disposition enum;
- unit tests for `AggregateVersion` validation and successor behavior;
- unit tests for `TransitionSequence` validation and successor behavior;
- unit tests for `StateTransitionRecord` immutability and required fields;
- unit tests proving governance IDs and runtime UUIDs are not interchangeable;
- unit tests for Dataset Manifest immutability and optional Dataset ID behavior;
- unit tests for Criterion Result immutability and evidence-package-local ownership semantics;
- architecture-boundary tests using the existing checker;
- type checking through the existing toolchain;
- full repository verification through `scripts/verify.ps1`;
- security scan through `scripts/security.ps1` if dependency changes occur.

No PostgreSQL or MinIO integration test is required for Candidate A unless the implementation accidentally introduces an external dependency, which would be a scope violation.

## 27. Architecture Boundaries

Required boundaries for MILESTONE-013:

- domain primitives may depend on standard library, existing identifier value objects, existing runtime UUID primitives, and foundation error types only if needed for safe domain validation;
- domain primitives must not depend on PostgreSQL, SQLAlchemy, psycopg, boto3, MinIO, object-storage adapters, runtime bootstrap, entrypoints, scripts, test fixtures, or Docker configuration;
- infrastructure modules must not import new domain primitives;
- domain primitives must not read environment variables;
- domain primitives must not log secrets or depend on logging setup;
- domain primitives must not open database connections, object-storage clients, files, sockets, or subprocesses;
- domain primitives must not create durable event, outbox, audit-ledger, or repository contracts.

## 28. Risks

| ID | Severity | Risk | Mitigation |
| --- | --- | --- | --- |
| M013-SCOPE-ISSUE-0001 | MINOR | Existing identifier wrappers could be duplicated by accident | Require explicit reuse of `empirical_platform.identifiers` and `empirical_platform.shared.identifiers` |
| M013-SCOPE-ISSUE-0002 | MAJOR | Aggregate behavior may creep into primitive implementation | Limit MILESTONE-013 to construction, validation, immutability, equality, and successor primitives |
| M013-SCOPE-ISSUE-0003 | MAJOR | Persistence concerns may leak into primitive shapes | Prohibit schema annotations, ORM mappings, repository methods, and serialization contracts beyond local values |
| M013-SCOPE-ISSUE-0004 | MINOR | Lifecycle enum names could drift from MILESTONE-012 | Require exact membership tests against MILESTONE-012 state names |
| M013-SCOPE-ISSUE-0005 | MINOR | Review disposition could be incorrectly modeled as lifecycle state | Require separate Review lifecycle and disposition primitives |

No CRITICAL blocker was identified for Candidate A.

## 29. Acceptance Criteria

This scope-selection report is complete if:

- repository baseline is recorded;
- governing documents are identified;
- current capability inventory distinguishes implemented, designed, absent, and deferred capabilities;
- Candidate A through Candidate F are evaluated;
- comparative scoring uses the required 100-point rubric;
- anti-confirmation-bias review is documented;
- schema lock-in risk is addressed;
- one milestone type decision is selected;
- exact implementation scope and exact non-goals are specified;
- included and deferred invariants are separated;
- testing strategy is defined;
- architecture boundaries are stated;
- no source code is modified;
- no schema, migration, table, repository, API, worker, job ledger, outbox, audit ledger, Decision Candidate, Decision Freeze, trading behavior, vendor behavior, campaign execution, or empirical validation is introduced.

Result: PASS.

## 30. Final Decision

Final decision:

```text
IMPLEMENTATION SLICE READY
```

Recommended next mission:

```text
MILESTONE-013 - Process-Local Domain Primitive Foundation
```

The next milestone may implement a narrow, process-local domain primitive slice. It must not implement aggregate behavior, persistence, schemas, repositories, APIs, workers, job ledger, outbox, audit runtime, Decision Candidate runtime, campaign execution, vendor behavior, market-data behavior, trading behavior, or Decision Freeze behavior.
