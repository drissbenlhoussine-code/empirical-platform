# MILESTONE-002 TECHNOLOGY SELECTION AND ENGINEERING BLUEPRINT

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MILESTONE-002 |
| Title | MILESTONE-002 - Technology Selection and Engineering Blueprint |
| Version | 1.0 |
| Status | DRAFT / ENGINEERING BLUEPRINT UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Original Publication Date | 2026-07-13 |
| Current Revision Date | 2026-07-13 |
| Approval Date | Not applicable - not approved or frozen |
| Scope | Implementation-ready engineering blueprint derived from MILESTONE-001 |
| Prior Architecture Input | MILESTONE-001 System Implementation Architecture |
| Implementation Status | No implementation |
| Repository Status | Not initialized |
| Empirical Campaign Status | Not executed |
| CAMP-0001 Status | Not authorized |
| Decision Candidate Status | Not created |
| Decision Freeze Status | Not created |

This document selects an initial engineering stack and development blueprint for the future empirical validation platform. It does not write production code, initialize a repository, create migrations, define API endpoints, execute empirical validation, authorize CAMP-0001, create a Decision Candidate, or create a Decision Freeze.

---

## 2. Purpose and Scope

The purpose of MILESTONE-002 is to translate MILESTONE-001's technology-independent architecture into concrete engineering choices that are suitable for a first implementation milestone.

In scope:

- technology evaluation;
- stack selection;
- deployment model selection;
- storage model selection;
- messaging and workflow approach;
- module boundary strategy;
- development standards;
- implementation sequencing blueprint;
- traceability from MILESTONE-001 subsystems and quality attributes to selected technologies.

Out of scope:

- production code;
- repository scaffolding;
- database migrations;
- API implementation;
- infrastructure-as-code;
- empirical campaign execution;
- vendor testing;
- vendor comparison;
- CAMP-0001 authorization;
- Decision Candidate creation;
- Decision Freeze.

---

## 3. Inputs from MILESTONE-001

MILESTONE-001 defines the logical system as a governance-aware empirical validation platform.

Load-bearing inputs:

| MILESTONE-001 Area | Requirement Carried into MILESTONE-002 |
|---|---|
| Vision | Platform must manage campaigns, preserve evidence, support review/audit, and separate evidence from decisions |
| Major Systems | Campaign Management, Governance Integration, Vendor Adapter Layer, Acquisition Engine, Dataset Management, Normalization Engine, Validation Engine, Evidence Store, Review, Audit, Decision, Archive |
| System Boundaries | External, internal, governance, and execution boundaries must remain distinct |
| Module Map | Future implementation must preserve logical modules without prematurely distributing them |
| Responsibility Allocation | Each subsystem must own a narrow responsibility and avoid decision leakage |
| Information Flow | Vendor -> Acquisition -> Raw Dataset -> Normalization -> Validation -> Evidence -> Review -> Audit |
| Integration Points | Governance registries must feed gate evaluation and execution authorization |
| Trust Boundaries | Vendor, raw evidence, transformation, validation, review, audit, and decision boundaries require controls |
| Failure Domains | Failures must remain scoped to campaign/run/dataset/evidence/review/audit |
| Scalability Model | Multiple campaigns, vendors, datasets, runs, reviewers, and archives must coexist |
| Extensibility Model | L2, L3, options, futures, crypto, and new vendors must not require core redesign |
| Quality Attributes | Reproducibility, traceability, auditability, determinism, modularity, maintainability, extensibility |

---

## 4. Engineering Decision Principles

Technology choices must follow these principles:

1. Select for traceability and reproducibility before throughput.
2. Prefer boring, inspectable technologies for core metadata and audit state.
3. Avoid distributed-system complexity until the workload requires it.
4. Preserve raw evidence outside mutable transactional stores.
5. Keep governance and execution logically separate even if initially deployed together.
6. Make identifiers first-class across every boundary.
7. Prefer open file formats and portable storage contracts.
8. Defer decisions that are not required to build the foundational platform.
9. Record reversal conditions for every load-bearing decision.
10. Do not choose a technology merely because it is popular or familiar.

---

## 5. Non-Functional Requirements Translation

| Quality Attribute | Engineering Translation |
|---|---|
| Reproducibility | Immutable evidence packages, checksums, deterministic transformation logs, versioned execution environment metadata |
| Traceability | Relational metadata with explicit CAMP/RUN/DATASET/EVID/REVIEW/AUD/DCAND links |
| Auditability | Append-only audit events, immutable evidence artifacts, registry snapshots |
| Determinism | Version-pinned execution, pure validation functions where possible, recorded calibration boundaries |
| Modularity | Modular monolith boundaries first; extraction to services only when justified |
| Maintainability | Typed contracts, small modules, explicit dependency direction |
| Extensibility | Adapter layer and validation plugin boundaries for future asset classes and vendors |
| Vendor Neutrality | Vendor-specific acquisition logic isolated behind adapters |
| Evidence Integrity | Object storage for raw and evidence artifacts, hash manifests, metadata references |
| Governance Compliance | Gate checks required before execution actions |
| Failure Isolation | Campaign/run-scoped state and artifacts |
| Review Independence | Review workflows and evidence custody separated |

---

## 6. Technology Evaluation Criteria

Every load-bearing technology is evaluated against:

- governance traceability;
- reproducibility support;
- auditability;
- data-volume fit;
- operational simplicity;
- local development ergonomics;
- long-term maintainability;
- portability;
- maturity and ecosystem support;
- reversibility;
- security posture;
- fit with MILESTONE-001 trust boundaries;
- ability to support future L2, L3, options, futures, crypto, and additional vendors.

---

## 7. Candidate Technology Categories

Load-bearing categories:

1. Runtime and primary programming language.
2. Service and module architecture.
3. Database and metadata storage.
4. Raw dataset and evidence object storage.
5. Analytical file format and local query engine.
6. Messaging, queueing, and workflow orchestration.
7. Validation and compute execution model.
8. API and internal contract strategy.
9. Authentication, authorization, and secrets.
10. Audit logging and observability.
11. Deployment and environment model.
12. Local development and reproducibility.
13. Testing strategy.
14. Repository and module boundaries.
15. Configuration and versioning.
16. Backup, recovery, and retention.

---

## 8. Runtime and Primary Programming Language Evaluation

### 8.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| Python 3.13 | Python 3.13 is stable and has active bugfix/security lifecycle; strong data ecosystem; aligns with Polars, DuckDB, Pydantic, FastAPI | Less compile-time safety than Rust/Go; packaging discipline required | Dynamic typing errors; performance bottlenecks in hot loops | Initial workloads are IO, governance, validation, and data transformation heavy rather than ultra-low-latency | If validation throughput or type-safety defects dominate, isolate hot path in Rust or move selected modules |
| TypeScript / Node.js | Strong web and API ecosystem; excellent frontend alignment if UI grows | Weaker fit for analytical data processing and scientific validation; Python ecosystem stronger for data work | More impedance with columnar analytics | UI/API productivity could matter more later | If UI-heavy product dominates and Python data path stays small |
| Go | Strong concurrency and deployment simplicity | Less natural for data science/analytical validation; fewer native dataframe tools | Faster services but slower validation development | Runtime simplicity may matter later | If acquisition becomes high-throughput network service bottleneck |
| Rust | Strong correctness/performance; Polars core ecosystem | Higher development cost; slower iteration; not ideal as primary governance app language | Over-engineering early | Hot loops may eventually benefit from Rust | If proven performance-critical modules emerge |

### 8.2 Selection

Selected: Python 3.13 as primary runtime.

Reasoning:

- best fit for validation, normalization, data inspection, and reproducibility tooling;
- strong ecosystem for Parquet, dataframe processing, contracts, and APIs;
- sufficient maturity and support window for a first implementation generation;
- easier to bridge governance documents, evidence files, and analytical validation.

Deferred: Rust or Go for future hot-path components.

Primary sources:

- Python 3.13 stable release and support lifecycle: https://docs.python.org/3/whatsnew/3.13.html
- Python version status: https://devguide.python.org/versions/

---

## 9. Service and Module Architecture Evaluation

### 9.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| Modular monolith | Preserves module boundaries without distributed complexity; simplest for audit trails and transactions | Requires discipline to prevent boundary erosion | Module coupling if boundaries are weak | Initial team and workload do not require independent service scaling | If campaign execution, acquisition, validation, and review require independent deployment/scaling |
| Distributed services | Strong isolation and independent scaling | Introduces network, orchestration, observability, transaction, and deployment complexity early | Premature distributed-system failures; harder reproducibility | System complexity is already justified | If multiple high-volume campaigns require independent service ownership |
| Plugin-oriented monolith | Supports adapters and validation extensions | Plugin interface design can overfit too early | Unstable extension contracts | Adapter/validation extension needs are clear enough | If domain expansion becomes primary driver |

### 9.2 Selection

Selected: modular monolith with explicit internal boundaries.

Boundary modules:

- campaign;
- governance;
- identifiers;
- registries;
- acquisition;
- datasets;
- normalization;
- validation;
- evidence;
- review;
- audit;
- decision-candidate;
- archive.

Reversal condition: extract modules into services only after measured scaling, security, ownership, or deployment constraints require it.

---

## 10. Database and Metadata Storage Evaluation

### 10.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| PostgreSQL 17 | Mature relational integrity; transactions; JSON capabilities; broad tooling; PostgreSQL 17 added SQL/JSON and logical replication improvements | Requires operational care; not ideal for large raw artifacts | Schema governance and migration discipline needed later | Metadata, identifiers, state, audit events fit relational model | If graph-like lineage queries dominate beyond relational practicality |
| SQLite | Simple local development; file-based; low ops burden | Poorer multi-user concurrency and production governance posture | Outgrows quickly for campaign collaboration | Single-user prototype only | If project remains single-user/local-only |
| Document database | Flexible JSON documents | Weaker relational constraints for identifier/state integrity | Orphan references and weak joins | Schema flexibility more valuable than strict integrity | If evidence metadata becomes highly variable and relational constraints are counterproductive |
| Graph database | Natural lineage traversal | Adds specialized ops; not needed initially | Over-specialization | Traceability graph becomes central and complex | If lineage traversal becomes a proven bottleneck |

### 10.2 Selection

Selected: PostgreSQL 17 for transactional metadata.

Owns:

- campaigns;
- runs;
- dataset metadata;
- evidence package metadata;
- criterion result metadata;
- review/audit metadata;
- decision-candidate metadata;
- identifier allocation records;
- gate states;
- registry snapshots;
- audit event ledger.

Does not own:

- raw vendor data files;
- immutable evidence artifact bodies;
- large normalized datasets;
- binary logs;
- archive bundles.

Primary source:

- PostgreSQL 17 release notes: https://www.postgresql.org/docs/release/17.0/

---

## 11. Raw Dataset and Evidence Object Storage Evaluation

### 11.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| S3-compatible object storage | Portable abstraction; works locally and in cloud; fits immutable artifacts | Requires object-key discipline and metadata DB | Misconfigured retention or access control | Evidence artifacts are file/object-oriented | If regulatory or operational constraints require a different archival store |
| Local filesystem only | Simple for first developer machine | Weak multi-user, retention, access control, and future scaling | Hard migration if paths leak into metadata | Project remains local-only | If no near-term collaboration or large artifacts |
| Database BLOB storage | Strong transaction coupling | Poor fit for large raw/evidence artifacts; bloats metadata DB | Backup and performance pain | Artifacts small and tightly transactional | If artifact sizes remain tiny and DB simplicity dominates |

### 11.2 Selection

Selected: S3-compatible object storage abstraction.

Initial local development may use a local S3-compatible service or filesystem-backed object-store adapter, but application contracts must use object-storage semantics.

Object boundaries:

- raw vendor data -> object storage;
- normalized datasets -> object storage;
- evidence packages -> object storage;
- manifests and hashes -> object storage with metadata references in PostgreSQL;
- archive packages -> object storage with retention metadata.

Primary sources:

- MinIO S3 compatibility: https://www.min.io/product/aistor/s3-api
- MinIO object storage project: https://github.com/minio/minio

---

## 12. Messaging, Queueing, and Workflow-Orchestration Evaluation

### 12.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| PostgreSQL-backed job ledger / transactional outbox | Simple; keeps state and auditability together; no extra broker initially | Not ideal for high-throughput queues or very long durable workflows | Could become custom workflow system if abused | Initial platform needs controlled jobs, not massive event streams | If long-running retries, external failures, and parallel campaigns require durable orchestration |
| Temporal | Durable execution, recovery, long-running workflow model | Adds platform complexity and operational dependency early | Premature orchestration complexity | Campaign workflows will become long-running and failure-prone later | Adopt when execution workload proves need for durable orchestration |
| Celery + broker | Familiar Python task queue | Requires broker/result backend and careful idempotency | Split-brain task/evidence state | Simple background tasks dominate | If PostgreSQL job ledger is insufficient but Temporal is too heavy |
| Kafka | Strong event streaming | Overkill for initial governance/evidence platform; operationally heavy | Complexity without need | High-volume event stream emerges | If multi-producer event streaming becomes central |

### 12.2 Selection

Selected now: PostgreSQL-backed job ledger and transactional outbox for foundational platform scaffolding.

Deferred: Temporal for durable execution if campaign execution proves long-running, retry-heavy, and operationally complex.

Rejected now: Kafka and distributed event streaming.

Primary source:

- Temporal durable workflow documentation: https://docs.temporal.io/workflow-execution

---

## 13. Validation and Compute Execution Model

### 13.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| In-process Python workers with Polars/DuckDB | Fits modular monolith; strong local analytical workflows; Parquet support; simple reproducibility | Single-node limits; careful memory management needed | Large datasets may exceed local resources | Initial validation samples fit single-node execution | If L2/L3 or multi-vendor datasets exceed node capacity |
| Distributed compute framework | Scales large datasets | Complex; heavy ops; harder reproducibility early | Premature scale architecture | Data volume already demands it | If measured workload requires distributed compute |
| Database-only validation | Centralized SQL and metadata | Not ideal for raw Parquet/file validation; risks mixing artifacts with metadata | DB becomes overloaded | Criteria mostly relational | If validation remains simple metadata checks |

### 13.2 Selection

Selected: in-process Python validation workers using Polars for dataframe transformations and DuckDB for SQL inspection/querying of Parquet evidence where useful.

Parquet is selected as the primary normalized dataset file format because it is columnar, broadly supported, and efficient for analytical scans.

Primary sources:

- Polars Parquet scan and LazyFrame behavior: https://docs.pola.rs/user-guide/io/parquet/
- DuckDB Parquet support: https://duckdb.org/docs/lts/data/parquet/overview.html
- DuckDB overview: https://duckdb.org/

---

## 14. API and Internal Contract Strategy

### 14.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| Typed Python contracts with Pydantic; FastAPI only for HTTP boundary | Strong validation and OpenAPI support if APIs are exposed; keeps contracts explicit | Pydantic/FastAPI coupling must be managed | Contract churn early | Internal contracts can be Python-native first | If non-Python clients require strict language-neutral contracts |
| OpenAPI-first contracts | Strong external API discipline | Premature because no public API required yet | API design freezes too early | External clients not yet needed | If UI/external clients become priority |
| gRPC/protobuf | Strong typed cross-language RPC | Overkill for modular monolith; more tooling | Premature service boundary | Distributed services become necessary | If service extraction and multi-language clients become real |

### 14.2 Selection

Selected: Pydantic v2 for internal command/result contracts, with FastAPI reserved for future HTTP/admin/API boundary.

No API endpoint is defined by this milestone.

Primary sources:

- Pydantic validation documentation: https://pydantic.dev/docs/validation/latest/get-started/
- Pydantic settings documentation: https://pydantic.dev/docs/validation/latest/concepts/pydantic_settings/
- FastAPI OpenAPI and standards support: https://fastapi.tiangolo.com/features/

---

## 15. Authentication, Authorization, and Secrets Strategy

### 15.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| Local role model with external identity deferred | Simple for initial single-operator scaffolding; avoids premature identity platform | Not sufficient for multi-user production | Later migration required | Initial use is local/dev governance operation | If multiple human users need access control immediately |
| OIDC provider integration | Standard enterprise identity pattern | Requires identity provider selection and setup | Premature operational complexity | Multi-user review workflows need it later | If reviewer/project-owner workflows require authenticated multi-user access |
| Static secrets files | Simple but unsafe | Poor audit/security posture | Secret leakage | Only disposable local dev secrets | Must be replaced before real vendor credentials |

### 15.2 Selection

Selected now: no production identity provider selected. Define role and permission model in architecture; implement local development-only identity later if needed.

Secrets strategy:

- no vendor API keys in repository;
- environment-based secret injection for local development;
- production secrets manager deferred until deployment environment is selected;
- every secret use must be tied to entitlement and audit records.

Deferred decision: OIDC provider and production secrets manager.

---

## 16. Audit Logging and Observability Strategy

### 16.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| Structured application logs + PostgreSQL audit event ledger | Simple, queryable, traceable; aligns with governance requirements | Requires discipline and retention rules | Audit table growth | Initial scale is manageable | If event volume grows beyond DB comfort |
| OpenTelemetry-first observability | Strong standard for traces/metrics/logs | More setup; backend selection needed | Tooling complexity | Distributed services not yet present | Adopt when service boundaries or production ops demand it |
| Log files only | Easy locally | Weak queryability and audit structure | Missing traceability | Temporary developer diagnostics only | Not acceptable for governance events |

### 16.2 Selection

Selected now:

- structured logs for operational diagnostics;
- PostgreSQL append-only audit event ledger for governance-significant events;
- object-storage manifests for evidence artifact auditability.

Deferred:

- OpenTelemetry and external observability backend until deployment/operations requirements mature.

---

## 17. Deployment and Environment Model

### 17.1 Alternatives

| Alternative | Supporting Evidence | Opposing Evidence | Risks | Assumptions | Reversal Conditions |
|---|---|---|---|---|---|
| Local-first containerized development environment | Reproducible dev services; clear dependencies | Requires container runtime; not production architecture by itself | Container setup drift | Next milestone initializes local platform scaffolding | If target users cannot run containers |
| Native local process only | Lowest setup for simple scripts | Harder to reproduce Postgres/object-store dependencies | Environment drift | Very small prototype | If object store/DB not needed early |
| Cloud-first deployment | Production-like early | Premature cost/security/ops choices | Locks environment too early | Production constraints known | If project needs shared hosted environment immediately |

### 17.2 Selection

Selected: local-first development environment with containerized dependencies for infrastructure services, while keeping application deployment model undecided.

Important boundary: selecting containers for local reproducibility does not select Docker as the permanent production deployment model.

Deferred:

- production hosting;
- cloud provider;
- orchestration platform;
- network topology.

---

## 18. Local Development and Reproducibility Model

Selected model:

- Python 3.13 runtime;
- isolated dependency environment;
- local PostgreSQL dependency;
- local S3-compatible object storage dependency;
- deterministic configuration through typed settings;
- test fixtures for governance registries and evidence manifests;
- generated evidence samples only after later implementation milestones permit test fixtures.

Reproducibility controls:

- dependency lock file in future repo;
- environment capture;
- versioned config;
- no credentials in source;
- deterministic test data generation later;
- no real vendor data in development fixtures unless separately authorized.

---

## 19. Testing Strategy

Testing categories:

| Test Class | Purpose |
|---|---|
| Unit tests | Validate module behavior and contract parsing |
| Contract tests | Verify Pydantic command/result objects and identifier flow |
| Repository tests | Verify metadata persistence once implemented |
| Object-store tests | Verify artifact write/read/hash behavior |
| Integration tests | Verify module interactions against local dependencies |
| Governance gate tests | Verify blocked gates prevent execution |
| Reproducibility tests | Verify evidence packages can be reconstructed |
| Property tests | Exercise validation invariants where applicable |
| Golden-file tests | Verify stable manifest and audit outputs |

No tests are created by this milestone.

---

## 20. Repository and Module-Boundary Strategy

Selected strategy: single repository, modular monolith.

Future top-level logical modules:

- campaign;
- governance;
- registry;
- identifiers;
- acquisition;
- datasets;
- normalization;
- validation;
- evidence;
- review;
- audit;
- decision_candidate;
- archive;
- shared contracts;
- shared test utilities.

Boundary rules:

1. Vendor adapters must not write governance state.
2. Validation must not mutate evidence.
3. Review must not mutate evidence.
4. Audit must not create Decision Freeze.
5. Metadata stores must not contain raw artifact bodies.
6. Object storage must not be the source of truth for lifecycle state.

No repository is initialized by this milestone.

---

## 21. Configuration and Versioning Strategy

Configuration model:

- typed settings;
- environment-specific profiles;
- no secrets in static config;
- config values captured in run/evidence metadata when relevant;
- governance document versions recorded in campaign metadata.

Versioning model:

- application semantic versioning after repository initialization;
- evidence schema versioning;
- manifest versioning;
- validation criterion version references;
- adapter version references;
- migration versioning later when database migrations are introduced.

No versioning file or config file is created by this milestone.

---

## 22. Backup, Recovery, and Data-Retention Strategy

Storage classes:

| Data Class | Storage | Backup / Recovery Approach |
|---|---|---|
| Transactional metadata | PostgreSQL | Database backups and point-in-time recovery design later |
| Raw vendor data | S3-compatible object storage | Immutable objects, hashes, retention policy |
| Normalized datasets | S3-compatible object storage | Regenerable from raw data when license permits; otherwise retained with limitation |
| Evidence packages | S3-compatible object storage | Immutable archive, hash manifest |
| Logs | Structured logs plus audit event ledger | Retention policy and export later |
| Derived results | Metadata DB plus evidence artifacts | Regenerate where possible and retain result artifacts |

Retention rules must follow license and entitlement constraints. No retention policy is finalized until legal/entitlement review is complete.

---

## 23. Security and Trust-Boundary Controls

Controls mapped to MILESTONE-001 trust boundaries:

| Trust Boundary | Control |
|---|---|
| Vendor to Acquisition | Entitlement check, adapter boundary, acquisition log |
| Acquisition to Dataset | Raw hash, raw manifest, immutable object write |
| Raw to Normalized | Transformation log and raw source references |
| Normalized to Validation | Criterion mapping and calibration boundary |
| Validation to Evidence | Result manifest and evidence package hash |
| Evidence to Review | Read-only evidence view and reviewer declaration |
| Review to Audit | Audit trace over immutable evidence |
| Audit to Decision Candidate | Eligibility gate and explicit non-Decision-Freeze boundary |
| Governance to Execution | Gate check before execution action |

Security decisions deferred:

- production authentication provider;
- production secrets manager;
- encryption-at-rest implementation;
- network segmentation;
- deployment hardening.

---

## 24. Scalability and Extensibility Compatibility

The selected architecture supports:

- multiple campaigns through CAMP-scoped metadata;
- multiple runs through RUN-scoped metadata;
- multiple vendors through adapter boundaries;
- multiple datasets through object storage and dataset metadata;
- L2/L3/options/futures/crypto through domain-specific dataset and validation modules;
- future distributed execution by extracting modules if justified;
- future workflow orchestration by adopting Temporal or equivalent if long-running workflows require it.

No core redesign should be required to add:

- L2;
- L3;
- options;
- futures;
- crypto;
- additional vendors.

Required extension mechanism:

- new adapter;
- new dataset definition;
- new criterion mapping;
- new validation module;
- same evidence/review/audit pipeline.

---

## 25. Technology Decision Matrix

| Category | Selected | Alternatives Considered | Decision Timing | Confidence |
|---|---|---|---|---|
| Primary runtime | Python 3.13 | TypeScript, Go, Rust | Required now | High |
| Service architecture | Modular monolith | Distributed services, plugin-first architecture | Required now | High |
| Metadata store | PostgreSQL 17 | SQLite, document DB, graph DB | Required now | High |
| Raw/evidence storage | S3-compatible object storage | Local filesystem, DB BLOBs | Required now | High |
| Normalized format | Parquet | CSV, database tables only | Required now | High |
| Analytical engine | Polars + DuckDB | Pandas only, distributed compute | Required now | Medium-High |
| Workflow orchestration | PostgreSQL job ledger / transactional outbox | Temporal, Celery, Kafka | Required now for initial; Temporal deferred | Medium |
| Internal contracts | Pydantic v2 | OpenAPI-first, protobuf | Required now | High |
| HTTP framework | FastAPI if/when HTTP boundary is needed | Flask, Django, no HTTP | Deferred until API/UI milestone | Medium |
| Identity provider | Deferred | Local role model, OIDC | Deferred | Medium |
| Secrets manager | Deferred | Environment-only, cloud manager, Vault | Deferred | Medium |
| Observability | Structured logs + DB audit ledger | OpenTelemetry-first, logs only | Required now | Medium-High |
| Deployment | Local-first with containerized dependencies | Native-only, cloud-first | Required now | Medium |
| Repository model | Single repository modular monolith | Multi-repo, service repos | Required next milestone | High |

---

## 26. Selected Engineering Stack

Selected required-now stack:

- Primary language/runtime: Python 3.13.
- Architecture model: modular monolith.
- Transactional metadata: PostgreSQL 17.
- Raw/evidence storage: S3-compatible object storage abstraction.
- Local object storage candidate: MinIO or compatible substitute.
- Normalized/evidence analytical file format: Parquet.
- Dataframe/validation tooling: Polars.
- Local analytical SQL over files: DuckDB.
- Internal validation/contracts: Pydantic v2.
- Initial workflow model: PostgreSQL job ledger and transactional outbox.
- Audit model: PostgreSQL audit event ledger plus evidence hash manifests.
- Local development model: local-first environment with containerized dependencies.
- Repository model: single repository with strict module boundaries.

Deferred stack choices:

- HTTP/API framework selection for external interface, though FastAPI is the leading candidate.
- Production authentication provider.
- Production secrets manager.
- Production deployment platform.
- Temporal or other durable workflow engine.
- Distributed compute framework.

---

## 27. Rejected Alternatives and Reasons

| Rejected Alternative | Reason |
|---|---|
| Distributed services as initial architecture | Premature operational complexity; modular monolith preserves boundaries with lower failure surface |
| Kafka as initial messaging backbone | Event-stream scale is not yet proven; governance platform needs traceability more than high-throughput streaming |
| Database BLOB storage for evidence | Raw/evidence artifacts should remain immutable objects, not inflate transactional metadata store |
| SQLite as primary metadata store | Insufficient confidence for multi-user governance and campaign lifecycle integrity |
| Cloud-first deployment | Premature environment commitment before implementation and security requirements stabilize |
| Rust as primary language | Strong performance, but higher development friction for governance/data-validation iteration |
| TypeScript as primary runtime | Strong web ecosystem but weaker fit for analytical validation core |
| OpenAPI-first as initial internal contract model | External API is not yet required; internal typed contracts should stabilize first |

---

## 28. Architecture Decision Records

### ADR-002-001 - Primary Runtime

Decision: Use Python 3.13 as the primary runtime.

Supporting evidence: stable Python release lifecycle; strong data, validation, and evidence tooling ecosystem.

Opposing evidence: weaker compile-time guarantees than Rust/Go.

Risk: dynamic runtime errors.

Assumption: validation and evidence workflows benefit more from data ecosystem than low-level performance.

Reversal condition: measured performance or correctness issues justify moving selected modules to Rust/Go.

### ADR-002-002 - Architecture Model

Decision: Start as a modular monolith.

Supporting evidence: best fit for traceability, auditability, and low operational complexity.

Opposing evidence: distributed services may scale independently later.

Risk: module boundaries erode.

Assumption: initial campaign volume does not require distributed services.

Reversal condition: independent scaling or ownership needs emerge.

### ADR-002-003 - Metadata Store

Decision: Use PostgreSQL 17 for transactional metadata.

Supporting evidence: mature relational integrity, JSON capabilities, transactions, broad tooling.

Opposing evidence: not suitable for large raw artifacts.

Risk: schema governance complexity later.

Assumption: metadata is relational and identifier-heavy.

Reversal condition: lineage queries require graph-native storage.

### ADR-002-004 - Evidence Storage

Decision: Use S3-compatible object storage abstraction for raw and evidence artifacts.

Supporting evidence: portable object model, immutable artifact fit, local/cloud flexibility.

Opposing evidence: object stores require metadata coordination.

Risk: object keys and metadata can drift.

Assumption: evidence artifacts are file/object oriented.

Reversal condition: retention or compliance demands a different archive store.

### ADR-002-005 - Workflow Model

Decision: Use PostgreSQL job ledger / transactional outbox initially; defer Temporal.

Supporting evidence: simpler and traceable for early platform scaffolding.

Opposing evidence: Temporal offers durable execution for long-running workflows.

Risk: custom job ledger becomes too complex.

Assumption: early platform does not require durable distributed workflow orchestration.

Reversal condition: execution proves long-running, retry-heavy, and failure-prone.

---

## 29. Assumption Register Updates

This document does not allocate new global ASS identifiers. Proposed assumptions for future registry update:

| Proposed Assumption | Owner | Validation Method | Risk if False |
|---|---|---|---|
| Initial validation workloads fit single-node Python/Polars/DuckDB execution | Research Lead | First dry-run workload measurement | Distributed compute may be required earlier |
| PostgreSQL can support metadata and audit event volume for early campaigns | Research Lead | Load test during implementation phase | Metadata store may need partitioning or event-store pattern |
| S3-compatible object storage satisfies raw/evidence artifact needs | Evidence Custodian | Evidence package prototype | Archive/storage model may need revision |
| Modular monolith boundaries can be preserved by code ownership and tests | Project Owner | Architecture review after scaffolding | Premature service extraction may be needed |

---

## 30. Risk Register

This document does not allocate new global RISK identifiers. Architecture risks for later registry import:

| Risk | Severity | Owner | Mitigation | Blocking Condition |
|---|---|---|---|---|
| Python ecosystem dependency drift affects reproducibility | Medium | Research Lead | Lock dependencies and capture environment | Blocks evidence reproducibility if unpinned |
| PostgreSQL job ledger becomes ad hoc workflow engine | Medium-High | Research Lead | Keep workflow surface narrow; revisit Temporal trigger | Blocks reliable execution if retries/state become complex |
| Object metadata and object bodies diverge | High | Evidence Custodian | Hash manifests and consistency checks | Blocks evidence review |
| Modular monolith boundaries erode | Medium | Project Owner | Boundary tests and module ownership | Blocks maintainability if cross-module writes proliferate |
| Deferred authentication/secrets choices delay real vendor acquisition | Medium | Project Owner | Decide before any real credentials | Blocks acquisition authorization |
| Single-node validation does not scale to future L2/L3 | Medium | Research Lead | Measure early; keep compute boundary replaceable | Blocks future high-volume campaigns |

---

## 31. Deferred Decisions

| Deferred Decision | Reason Deferred | Trigger for Decision |
|---|---|---|
| Production hosting platform | No production deployment requirement yet | Before shared multi-user deployment |
| Production identity provider | No production user model yet | Before reviewer/project-owner multi-user access |
| Production secrets manager | No real vendor credentials authorized | Before any credential-bearing acquisition workflow |
| Temporal adoption | Durable workflow need not yet proven | Before long-running empirical execution |
| Distributed compute | Workload size not measured | When dataset volume exceeds single-node model |
| External API surface | No UI/client requirements yet | Before building external user interface or integration clients |
| Schema migration tooling | Repository not initialized | Next implementation milestone |

---

## 32. Dependency and Traceability Matrix

| MILESTONE-001 Subsystem / Attribute | Selected Technology / Strategy |
|---|---|
| Campaign Management | Python modular module + PostgreSQL metadata |
| Governance Integration | Python module reading registries + PostgreSQL audit ledger |
| Vendor Adapter Layer | Python adapter boundary; no vendor implementation yet |
| Acquisition Engine | Python module; execution deferred |
| Dataset Management | PostgreSQL metadata + S3-compatible object storage |
| Normalization Engine | Python + Polars + Parquet |
| Validation Engine | Python + Polars/DuckDB + Pydantic contracts |
| Evidence Store | S3-compatible object storage + PostgreSQL metadata |
| Exception and Conflict System | PostgreSQL metadata + audit ledger |
| Review System | PostgreSQL metadata + reviewer declaration artifacts |
| Audit System | PostgreSQL audit ledger + evidence manifests |
| Decision Engine | Python module boundary; no Decision Freeze |
| Archive System | S3-compatible archive packages + retention metadata |
| Reproducibility | Dependency locks, environment capture, object hashes |
| Traceability | Relational identifiers and object metadata |
| Auditability | Append-only audit event ledger and manifests |
| Determinism | Versioned config, pinned dependencies, pure validation boundary |
| Modularity | Single repo modular monolith |
| Extensibility | Adapter and validation module boundaries |
| Failure Isolation | Campaign/run/dataset/evidence scoped objects |

---

## 33. Implementation Sequencing Blueprint

This is a sequencing blueprint only. It does not begin implementation.

1. Initialize repository with Python 3.13 project metadata and module skeleton only.
2. Add dependency management and formatting/linting/test tooling.
3. Define internal Pydantic contracts for identifiers and core object commands.
4. Add PostgreSQL metadata persistence foundation.
5. Add object-storage abstraction and local development adapter.
6. Add governance registry read models.
7. Add campaign/run/dataset/evidence metadata modules.
8. Add audit event ledger.
9. Add evidence manifest and checksum model.
10. Add job ledger / transactional outbox foundation.
11. Add validation module boundary without implementing campaign business logic.
12. Add review/audit module boundaries.
13. Add local integration tests using synthetic non-vendor fixtures.
14. Reassess deferred decisions before any empirical campaign logic.

Next milestone may initialize repository and build foundational platform scaffolding only.

---

## 34. Exit Criteria

MILESTONE-002 is complete only if:

- every load-bearing technology category compares credible alternatives;
- selected stack is traceable to MILESTONE-001 subsystems and quality attributes;
- required-now and deferred decisions are distinguished;
- modular monolith vs distributed services is decided with justification;
- transactional metadata, raw data, normalized data, logs, evidence, and derived results have separate boundaries;
- identifier flow is defined for campaign, run, dataset, evidence package, criterion result, review, audit, and decision candidate;
- scalability and extensibility for L2, L3, options, futures, crypto, and additional vendors are preserved;
- implementation sequence is defined;
- no production code is written;
- no repository is initialized;
- no database schema or migration is created;
- no API is defined;
- no empirical campaign or vendor testing is executed;
- CAMP-0001 is not authorized;
- no Decision Candidate or Decision Freeze is created.

---

## 35. Quality Rubric

| Criterion | Score | Justification |
|---|---:|---|
| MILESTONE-001 traceability | 10 / 10 | Maps selections to subsystems, quality attributes, trust boundaries, and failure domains |
| Alternative evaluation | 10 / 10 | Compares credible alternatives for each load-bearing category |
| Evidence-based decisions | 9 / 10 | Uses primary-source evidence; some deployment/security choices intentionally deferred |
| Required vs deferred separation | 10 / 10 | Distinguishes immediate decisions from safe deferrals |
| Implementation readiness | 10 / 10 | Defines concrete stack and sequencing without scaffolding |
| Governance preservation | 10 / 10 | Does not modify prior documents or authorize CAMP-0001 |
| Technology restraint | 10 / 10 | Avoids distributed services, Kafka, cloud, and durable orchestration until justified |
| Extensibility | 10 / 10 | Preserves future L2/L3/options/futures/crypto support |
| Security boundary awareness | 9 / 10 | Defines strategy and deferrals; production controls remain future decisions |
| Scope control | 10 / 10 | No code, no APIs, no migrations, no empirical execution |

Overall score: 98 / 100.

---

## 36. Final Status

Status: DRAFT / ENGINEERING BLUEPRINT UNDER REVIEW.

This document selects an implementation-ready engineering blueprint.

It does not initialize a repository.

It does not create production code.

It does not create infrastructure code.

It does not create database migrations.

It does not define APIs.

It does not execute empirical campaigns or vendor testing.

It does not authorize CAMP-0001.

It does not create a Decision Candidate.

It does not create a Decision Freeze.
