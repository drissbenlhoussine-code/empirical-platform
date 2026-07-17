# MILESTONE-003 PLATFORM FOUNDATION INITIALIZATION

---

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | MILESTONE-003 |
| Title | MILESTONE-003 - Platform Foundation Initialization |
| Version | 1.0 |
| Status | DRAFT / FOUNDATION UNDER REVIEW |
| Document Owner | Research Lead |
| Primary Approver | Project Owner |
| Original Publication Date | 2026-07-13 |
| Current Revision Date | 2026-07-13 |
| Approval Date | Not applicable - not approved or frozen |
| Scope | Engineering foundation specification for future repository scaffolding |
| Primary Input | MILESTONE-002 Technology Selection and Engineering Blueprint |
| Implementation Status | No code created |
| Repository Status | Not initialized |
| Empirical Campaign Status | Not executed |
| CAMP-0001 Status | Not authorized |
| Decision Candidate Status | Not created |
| Decision Freeze Status | Not created |

This milestone defines the engineering foundation required before implementation begins. It does not modify prior milestones, initialize a repository, implement business logic, implement empirical validation, implement vendor adapters, download market data, execute campaigns, implement B3 criteria, implement statistical logic, create a UI, create production APIs beyond future health/version placeholders, create Decision Candidates, or create a Decision Freeze.

---

## 2. Purpose and Scope

The purpose of MILESTONE-003 is to convert the MILESTONE-002 engineering blueprint into a precise repository-foundation specification.

In scope:

- repository initialization plan;
- Python project structure;
- dependency groups;
- configuration foundation;
- logging foundation;
- database initialization plan;
- object-storage initialization plan;
- quality tooling standards;
- development workflow;
- container strategy;
- module dependency rules;
- architecture validation checklist;
- engineering readiness checklist;
- deferred implementation list;
- engineering-only risks;
- ADR updates;
- traceability to MILESTONE-002.

Out of scope:

- application code;
- business logic;
- empirical validation logic;
- vendor integrations;
- campaign execution;
- B3 criterion implementation;
- statistical logic;
- production API implementation;
- UI implementation;
- database schemas or migrations;
- Dockerfiles or infrastructure code.

---

## 3. Repository Initialization Plan

### 3.1 Proposed Directory Tree

The future repository should be initialized with the following non-business skeleton.

```text
trading/
  pyproject.toml
  README.md
  LICENSE
  .gitignore
  .env.example
  docs/
    architecture/
    adr/
    operations/
  src/
    empirical_platform/
      __init__.py
      campaign/
      governance/
      registry/
      identifiers/
      acquisition/
      datasets/
      normalization/
      validation/
      evidence/
      review/
      audit/
      decision_candidate/
      archive/
      shared/
        contracts/
        config/
        logging/
        errors/
  tests/
    unit/
    contract/
    integration/
    fixtures/
  tools/
  scripts/
```

### 3.2 Ownership Boundaries

| Area | Owner | Responsibility |
|---|---|---|
| `campaign` | Campaign Management owner | Campaign and run lifecycle scaffolding only |
| `governance` | Governance Integration owner | Gate and governance read-model boundaries |
| `registry` | Registry owner | Registry synchronization boundaries |
| `identifiers` | Identifier owner | Identifier value objects and allocation boundaries |
| `acquisition` | Acquisition owner | Future acquisition boundary only, no vendor adapters |
| `datasets` | Dataset owner | Dataset identity and lineage boundary |
| `normalization` | Normalization owner | Future transformation boundary only |
| `validation` | Validation owner | Future validation boundary only, no B3 logic |
| `evidence` | Evidence owner | Evidence manifest and artifact boundary |
| `review` | Review owner | Reviewer declaration and review boundary |
| `audit` | Audit owner | Audit trace boundary |
| `decision_candidate` | Decision owner | Candidate boundary only, no Decision Freeze |
| `archive` | Archive owner | Retention and archive boundary |
| `shared` | Platform owner | Cross-cutting contracts, config, logging, errors |

### 3.3 Dependency Rules

- Domain modules may depend on `shared`.
- Domain modules may not import later lifecycle modules unless explicitly allowed in Section 12.
- `validation` may read dataset/evidence contracts but must not mutate evidence.
- `review` and `audit` must not import acquisition or normalization implementation internals.
- `decision_candidate` may depend on audit contracts but must not perform Decision Freeze logic.
- `shared` must not depend on domain modules.

### 3.4 Naming Conventions

- Python package: `empirical_platform`.
- Module names: lowercase snake_case.
- Identifier classes: `CampaignId`, `RunId`, `DatasetId`, `EvidencePackageId`, `ReviewId`, `AuditId`, `DecisionCandidateId`.
- Commands: `VerbNounCommand`.
- Results: `NounResult`.
- Events: `NounPastTenseEvent`.
- Errors: `NounError`.
- Configuration classes: `NounSettings`.

---

## 4. Python Project Structure

### 4.1 pyproject.toml Specification

The future `pyproject.toml` should define:

- project metadata;
- Python version requirement;
- package discovery under `src/`;
- runtime dependencies;
- optional dependency groups;
- formatter configuration;
- linter configuration;
- type-checker configuration;
- test-runner configuration.

### 4.2 Python Version

Selected Python version:

```text
Python >=3.13,<3.14
```

Rationale: preserves the MILESTONE-002 runtime decision while keeping the first implementation generation on one major Python version.

### 4.3 Package Layout

Use `src/` layout to prevent accidental imports from the repository root and to keep tests honest about packaging.

No business code is created by this milestone.

---

## 5. Dependency Management

### 5.1 Runtime Dependencies

| Dependency | Purpose | Justification |
|---|---|---|
| `pydantic` | Typed contracts and validation | Selected in MILESTONE-002 for internal contracts |
| `pydantic-settings` | Typed configuration loading | Separates config from code and supports environment loading |
| `sqlalchemy` | Database access abstraction | Supports PostgreSQL metadata access without hardcoding raw SQL everywhere |
| `alembic` | Migration framework | Required later for migration strategy; no migrations now |
| `psycopg` | PostgreSQL driver | Supports selected PostgreSQL metadata store |
| `polars` | Dataframe and Parquet processing | Supports future normalization/validation execution |
| `duckdb` | Local analytical SQL over files | Supports future evidence inspection and Parquet queries |
| `structlog` | Structured logging | Supports audit-friendly operational logs |
| `python-dotenv` | Local environment loading | Supports local development without embedding secrets |
| `boto3` or S3-compatible client | Object storage access | Supports selected S3-compatible evidence storage abstraction |

### 5.2 Development Dependencies

| Dependency | Purpose |
|---|---|
| `ruff` | Linting and formatting |
| `mypy` | Static type checking |
| `pytest` | Test runner |
| `pytest-cov` | Coverage reporting |
| `pytest-xdist` | Parallel test execution when useful |
| `pre-commit` | Local quality hooks |
| `detect-secrets` or equivalent | Secret scanning |
| `pip-audit` or equivalent | Dependency vulnerability audit |

### 5.3 Testing Dependencies

| Dependency | Purpose |
|---|---|
| `pytest` | Unit and integration testing |
| `hypothesis` | Property-based tests for identifiers and invariants |
| `freezegun` or equivalent | Deterministic time testing where needed |
| `testcontainers` or equivalent | Future integration tests against local dependencies |

Dependency policy:

- all dependencies must be pinned by a lock file in the future repository;
- dependency additions require justification;
- no vendor SDK may be added until vendor adapter work is authorized;
- no web/UI framework may be added until an API/UI milestone authorizes it.

---

## 6. Configuration System

### 6.1 Environment Loading

Configuration should load from:

1. explicit runtime arguments where applicable;
2. environment variables;
3. local `.env` file for development only;
4. default safe values.

### 6.2 Typed Settings

Configuration should be represented by typed settings classes:

- `AppSettings`;
- `DatabaseSettings`;
- `ObjectStorageSettings`;
- `LoggingSettings`;
- `SecuritySettings`;
- `DevelopmentSettings`.

### 6.3 Configuration Precedence

Precedence order:

```text
explicit runtime override
  -> environment variable
    -> local .env
      -> default
```

### 6.4 Secrets Separation

Rules:

- secrets must never be committed;
- `.env.example` may include names but not values;
- real vendor credentials are prohibited until vendor acquisition work is authorized;
- secrets must not appear in logs;
- production secrets manager remains deferred.

No configuration code is created by this milestone.

---

## 7. Logging Foundation

Logging must be structured and machine-readable.

Required fields:

- timestamp;
- level;
- message;
- correlation_id;
- campaign_id;
- run_id;
- dataset_id;
- evidence_package_id;
- review_id;
- audit_id;
- module;
- event_type;

Log levels:

- DEBUG;
- INFO;
- WARNING;
- ERROR;
- CRITICAL.

Logging rules:

- governance-significant events must later be mirrored to the audit event ledger;
- secrets must never be logged;
- raw vendor data must never be logged;
- logs must identify campaign/run context when available;
- logs must distinguish operational diagnostics from audit events.

No logging implementation is created by this milestone.

---

## 8. Database Initialization Plan

Selected metadata store: PostgreSQL.

### 8.1 Migration Strategy

Future migration strategy:

- Alembic-managed migrations;
- one migration lineage for platform metadata;
- migrations reviewed before application;
- migration version recorded in environment metadata;
- downgrade policy defined before production use.

No migrations are created by this milestone.

### 8.2 Metadata Schema Ownership

Future logical schema ownership:

| Metadata Area | Owning Module |
|---|---|
| Campaign metadata | `campaign` |
| Run metadata | `campaign` |
| Identifier metadata | `identifiers` |
| Registry snapshots | `registry` |
| Dataset metadata | `datasets` |
| Evidence metadata | `evidence` |
| Criterion result metadata | `validation` |
| Review metadata | `review` |
| Audit metadata | `audit` |
| Decision Candidate metadata | `decision_candidate` |
| Archive metadata | `archive` |

### 8.3 Version Policy

- schema version must be queryable;
- schema version must be captured in evidence/reproducibility metadata;
- migration history must be append-only;
- schema changes must not silently rewrite audit history.

---

## 9. Object Storage Initialization

Selected storage model: S3-compatible object storage abstraction.

### 9.1 Bucket Layout

Future bucket classes:

```text
raw-datasets
normalized-datasets
evidence-packages
logs
archives
```

Bucket names may receive environment prefixes in implementation.

### 9.2 Artifact Hierarchy

Canonical object hierarchy:

```text
campaigns/<CAMP-ID>/
  runs/<RUN-ID>/
    datasets/<DATASET-ID>/
      raw/
      normalized/
    evidence/<EVID-ID>/
      manifests/
      criterion-results/
      transformation-logs/
      exception-logs/
      conflict-logs/
      review/
      audit/
      archive/
```

### 9.3 Evidence Storage Policy

- raw artifacts are immutable once registered;
- normalized artifacts must link to raw artifacts;
- evidence packages require hash manifests;
- deletion is prohibited except under approved retention policy;
- object metadata must not replace transactional metadata;
- object paths must include canonical identifiers.

No storage code or buckets are created by this milestone.

---

## 10. Repository Quality Standards

| Quality Tool | Standard |
|---|---|
| Formatter | `ruff format` |
| Linter | `ruff check` |
| Type checker | `mypy` |
| Test runner | `pytest` |
| Coverage | `pytest-cov` |
| Secret scanning | `detect-secrets` or equivalent |
| Dependency audit | `pip-audit` or equivalent |
| Pre-commit hooks | formatting, linting, type check subset, secret scan |

Quality gates:

- no code merges without formatting and lint checks;
- type-checking required for platform modules;
- tests required for any future business or infrastructure behavior;
- secret scan required before commit;
- dependency audit required before release.

No tool configuration files are created by this milestone.

---

## 11. Development Workflow

### 11.1 Local Workflow

Future local workflow:

1. create isolated Python environment;
2. install locked dependencies;
3. start local dependency services;
4. run formatting/lint/type/test checks;
5. run integration tests only when local dependencies are available;
6. never use real vendor credentials in default development flow.

### 11.2 Branch Strategy

- default branch remains stable;
- feature branches use `codex/` prefix unless user directs otherwise;
- no direct commits to stable branch without review;
- governance artifacts and code changes should be separated where practical.

### 11.3 Commit Conventions

Commit message pattern:

```text
type(scope): concise summary
```

Allowed types:

- `docs`;
- `build`;
- `test`;
- `refactor`;
- `feat`;
- `fix`;
- `chore`.

### 11.4 Review Process

Review must check:

- module boundary compliance;
- no unauthorized business logic;
- no vendor integration unless authorized;
- no credentials;
- no empirical execution;
- traceability to milestone requirement.

---

## 12. Container Strategy

### 12.1 Development Containers

Development containers may provide:

- PostgreSQL;
- S3-compatible object storage;
- optional admin tools;
- isolated local service dependencies.

Application containers are deferred until repository scaffolding.

### 12.2 Production Containers

Production container strategy remains deferred.

Production image policy must eventually define:

- base image policy;
- vulnerability scanning;
- minimal runtime image;
- non-root execution;
- reproducible build metadata;
- version labels;
- dependency provenance.

No Dockerfiles, compose files, or container build files are created by this milestone.

---

## 13. Module Dependency Rules

Allowed dependencies:

| Module | May Depend On |
|---|---|
| `shared` | No domain modules |
| `identifiers` | `shared` |
| `registry` | `shared`; `identifiers` |
| `governance` | `shared`; `identifiers`; `registry` |
| `campaign` | `shared`; `identifiers`; `governance`; `registry` |
| `acquisition` | `shared`; `identifiers`; `campaign`; `datasets`; `evidence` contracts only |
| `datasets` | `shared`; `identifiers`; `campaign` contracts |
| `normalization` | `shared`; `identifiers`; `datasets`; `evidence` contracts |
| `validation` | `shared`; `identifiers`; `datasets`; `normalization` contracts; `evidence` contracts |
| `evidence` | `shared`; `identifiers`; `datasets`; `validation` result contracts |
| `review` | `shared`; `identifiers`; `evidence` contracts |
| `audit` | `shared`; `identifiers`; `evidence`; `review`; `registry` |
| `decision_candidate` | `shared`; `identifiers`; `audit`; `evidence` contracts |
| `archive` | `shared`; `identifiers`; `evidence`; `audit`; `decision_candidate` contracts |

Forbidden dependencies:

- `shared` importing domain modules;
- `review` importing acquisition implementation;
- `audit` mutating evidence;
- `decision_candidate` importing vendor adapters;
- `validation` importing reviewer logic;
- any module bypassing `identifiers` for identifier parsing;
- any module bypassing governance gates for execution actions.

---

## 14. Architecture Validation Checklist

| MILESTONE-001 Requirement | Validation Check |
|---|---|
| Campaign Management exists | `campaign` module boundary defined |
| Governance Integration exists | `governance` and `registry` boundaries defined |
| Vendor Adapter Layer isolated | `acquisition` boundary defined; vendor adapters deferred |
| Acquisition Engine isolated | acquisition planning boundary defined without implementation |
| Dataset Management exists | `datasets` boundary defined |
| Normalization Engine exists | `normalization` boundary defined |
| Validation Engine exists | `validation` boundary defined, B3 logic deferred |
| Evidence Store exists | `evidence` boundary and object hierarchy defined |
| Exception and Conflict System supported | evidence logs and future modules accounted for |
| Review System exists | `review` boundary defined |
| Audit System exists | `audit` boundary defined |
| Decision Engine separated | `decision_candidate` boundary defined, no Decision Freeze |
| Archive System exists | `archive` boundary defined |
| Trust boundaries preserved | config/logging/storage/database boundaries defined |
| Failure domains preserved | module dependency rules prevent cross-domain mutation |
| Extensibility preserved | modules allow future L2/L3/options/futures/crypto additions |

---

## 15. Engineering Readiness Checklist

Everything required before the first line of business code:

| Readiness Item | Required State |
|---|---|
| pyproject specification approved | Required |
| package layout approved | Required |
| module boundaries approved | Required |
| dependency groups approved | Required |
| formatter/linter/type/test standards approved | Required |
| configuration precedence approved | Required |
| secrets separation approved | Required |
| logging field model approved | Required |
| database migration policy approved | Required |
| object-storage hierarchy approved | Required |
| module dependency rules approved | Required |
| no vendor SDKs added | Required |
| no business logic added | Required |
| no empirical execution code added | Required |
| no production APIs added beyond future health/version placeholders | Required |

---

## 16. Deferred Implementation List

The following are intentionally postponed:

- repository creation;
- actual `pyproject.toml`;
- package files;
- dependency lock file;
- formatter/linter/type-checker config files;
- application code;
- database schema;
- database migrations;
- object-storage client;
- health/version endpoint implementation;
- vendor adapters;
- acquisition logic;
- normalization logic;
- validation logic;
- B3 criterion logic;
- statistical logic;
- evidence package writer;
- review workflow implementation;
- audit workflow implementation;
- Decision Candidate builder;
- UI;
- production deployment files;
- Dockerfiles.

---

## 17. Risk Register

Engineering-only risks:

| Risk ID | Risk | Severity | Mitigation | Blocking Condition |
|---|---|---|---|---|
| ENG-RISK-0001 | Foundation skeleton may accidentally include business logic | High | Enforce deferred implementation list and review checklist | Blocks foundation approval if business logic appears |
| ENG-RISK-0002 | Module boundaries may be too broad or ambiguous | Medium | Apply dependency rules and architecture validation checklist | Blocks scaffolding if ownership unclear |
| ENG-RISK-0003 | Dependency set may become too large before need is proven | Medium | Require dependency justification and audits | Blocks adding optional libraries without owner |
| ENG-RISK-0004 | Local container assumptions may not fit user environment | Medium | Keep container strategy configurable and not production-binding | Blocks mandatory container-only workflow |
| ENG-RISK-0005 | Database migration policy may be under-specified before schema work | Medium | Require migration ADR before first schema | Blocks schema implementation |
| ENG-RISK-0006 | Object hierarchy may need adjustment after evidence prototype | Medium | Treat hierarchy as versioned and reversible | Blocks evidence implementation if path model breaks traceability |
| ENG-RISK-0007 | Health/version placeholder may expand into premature API | Medium | Restrict API scope by milestone gate | Blocks API expansion |

No global RISK identifiers are allocated by this milestone.

---

## 18. ADR Updates

### ADR-003-001 - Repository Layout

Decision: Future repository will use `src/` layout with package `empirical_platform`.

Rationale: improves import discipline and supports clear package boundaries.

Reversal condition: packaging tool or deployment model requires a different layout.

### ADR-003-002 - Quality Tooling

Decision: Use Ruff for formatting/linting, mypy for typing, pytest for testing.

Rationale: aligns with Python stack and keeps the first quality toolchain simple.

Reversal condition: tool limitations block required checks.

### ADR-003-003 - Configuration Foundation

Decision: Use typed settings with environment precedence and secrets separation.

Rationale: preserves reproducibility and prevents credential leakage.

Reversal condition: production environment requires different configuration injection.

### ADR-003-004 - No Business Logic in Foundation

Decision: MILESTONE-003 authorizes only scaffolding specification, not business implementation.

Rationale: protects architecture boundaries and avoids premature empirical logic.

Reversal condition: none inside this milestone.

### ADR-003-005 - Placeholder API Constraint

Decision: Future foundation may include health/version placeholders only if a later scaffolding milestone authorizes them.

Rationale: supports operational readiness without creating premature product APIs.

Reversal condition: external integration requirements are approved by a later milestone.

---

## 19. Traceability Matrix

| MILESTONE-002 Decision | MILESTONE-003 Foundation Mapping |
|---|---|
| Python 3.13 runtime | pyproject Python version and package layout |
| Modular monolith | single repository with module boundaries |
| PostgreSQL metadata | database initialization plan and migration strategy |
| S3-compatible object storage | bucket layout and artifact hierarchy |
| Parquet / Polars / DuckDB | dependency groups and future validation boundary |
| Pydantic v2 contracts | typed settings and future contract modules |
| PostgreSQL job ledger / transactional outbox | deferred implementation under database ownership |
| Structured logs + audit ledger | logging foundation and audit-event separation |
| Local-first development | local workflow and container dependency strategy |
| Single repository | repository initialization plan |
| No vendor integrations yet | vendor adapters deferred and dependency policy blocks SDKs |
| No API endpoints yet | placeholder-only API constraint |
| Governance integration | module map includes governance, registry, identifiers, audit |
| Evidence integrity | object hierarchy, hash policy, evidence package boundary |
| Extensibility | module boundaries support future domains |

---

## 20. Exit Criteria

MILESTONE-003 is complete only if:

- repository initialization plan is defined;
- directory tree is defined;
- module boundaries are defined;
- ownership boundaries are defined;
- dependency rules are defined;
- naming conventions are defined;
- pyproject specification is defined;
- dependency groups are justified;
- configuration strategy is defined;
- logging foundation is defined;
- database initialization plan is defined without schema implementation;
- object storage layout is defined without storage code;
- repository quality standards are defined;
- development workflow is defined;
- container strategy is defined without Dockerfiles;
- architecture validation checklist is complete;
- engineering readiness checklist is complete;
- deferred implementation list is explicit;
- engineering risks are documented;
- ADR updates are recorded;
- traceability to MILESTONE-002 is complete;
- no business logic is implemented;
- no empirical validation is implemented;
- no vendor adapter is implemented;
- no campaign is executed;
- no CAMP-0001 authorization occurs;
- no Decision Candidate or Decision Freeze is created.

---

## 21. Quality Rubric

| Criterion | Score | Justification |
|---|---:|---|
| MILESTONE-002 traceability | 10 / 10 | Every core engineering decision maps back to MILESTONE-002 |
| Repository foundation clarity | 10 / 10 | Directory tree, package layout, naming, ownership, and dependency rules defined |
| Scope control | 10 / 10 | Business logic, empirical logic, vendor adapters, APIs, UI, and migrations excluded |
| Dependency discipline | 9 / 10 | Dependency groups defined; exact versions deferred to repository initialization |
| Configuration/logging foundation | 10 / 10 | Typed settings, precedence, secrets separation, structured logging fields defined |
| Database/object-storage planning | 10 / 10 | Migration policy, schema ownership, bucket layout, and evidence hierarchy defined without implementation |
| Quality standards | 10 / 10 | Formatter, linter, type checker, tests, security scan, and dependency audit defined |
| Module boundary discipline | 10 / 10 | Allowed and forbidden dependencies are explicit |
| Readiness for scaffolding | 10 / 10 | Next milestone can generate scaffolding with minimal ambiguity |
| Risk awareness | 9 / 10 | Engineering risks identified; operational validation remains future work |

Overall score: 98 / 100.

---

## 22. Final Status

Status: DRAFT / FOUNDATION UNDER REVIEW.

This document defines the platform foundation specification only.

It does not initialize a repository.

It does not create application code.

It does not create infrastructure code.

It does not create database migrations.

It does not implement business logic.

It does not implement empirical validation.

It does not implement vendor adapters.

It does not implement B3 criteria.

It does not implement statistical logic.

It does not create production APIs beyond future health/version placeholders.

It does not create a UI.

It does not execute campaigns.

It does not authorize CAMP-0001.

It does not create a Decision Candidate.

It does not create a Decision Freeze.
