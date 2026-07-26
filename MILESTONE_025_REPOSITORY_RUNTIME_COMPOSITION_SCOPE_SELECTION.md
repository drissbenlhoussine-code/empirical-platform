# MILESTONE-025 - Repository Runtime Composition Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-025-SCOPE-SELECTION |
| Title | Repository Runtime Composition Scope Selection |
| Version | 1.0 |
| Status | SCOPE SELECTED - DESIGN READY FOR INDEPENDENT REVIEW |
| Repository baseline | `b2283281f670703c95de0b6fe8ee83d58c5e3ac1` |
| Mission type | Scope selection and design authorization only |

## 2. Objective

Select the single best bounded milestone after frozen M024 using live repository evidence.

## 3. Current Repository Evidence

Frozen prerequisites now present:

- M020 repository contracts;
- M021 mapper contracts;
- M022 PostgreSQL schema and migration;
- M023 concrete PostgreSQL repository adapters;
- M024 shared multi-aggregate Unit of Work primitive.

M024 explicitly deferred repository runtime composition as Candidate E, application services as Candidate F, and retry policy as Candidate J. Candidate F depends on M024 plus Candidate E. Candidate J depends on Candidate F.

## 4. Candidate Inventory

| Candidate | Layer | Dependencies | Scope size | Risk | Decision |
| --- | --- | --- | --- | --- | --- |
| Repository Runtime Composition | Infrastructure composition | M020-M024 frozen | Small/medium | Medium | Selected |
| Application Service Orchestration | Application layer | Requires repository runtime composition | Large | High | Rejected as premature |
| Retry Policy | Application policy | Requires application services | Medium | High | Rejected as premature |
| Generic Dependency Injection Container | Platform composition | Requires clearer consumers | Large | High | Rejected as too broad |
| Projection/Read Model | Query side | Requires use-case requirements | Large | High | Rejected as premature |
| Audit Runtime | Governance/runtime | Requires application flows | Large | High | Rejected as premature |
| Decision Candidate Runtime | Decision layer | Requires execution/review/audit outputs | Large | High | Rejected as premature |

## 5. Candidate Comparison

| Criterion | Repository Runtime Composition | Application Services | Retry Policy | Generic DI Container |
| --- | --- | --- | --- | --- |
| Architectural ordering | Directly follows M024 | Depends on selected candidate | Depends on application services | Too global |
| Dependency readiness | Ready | Not ready | Not ready | Partial |
| Isolation | High | Medium | Medium | Low |
| Independent testability | High | Medium | Medium | Low |
| Reversibility | High | Medium | Medium | Low |
| Auditability benefit | High | High | Medium | Low |
| Scope-creep risk | Medium | High | High | High |
| Implementation confidence | High | Medium | Medium | Low |

## 6. Selected Scope

MILESTONE-025 selects **Repository Runtime Composition**.

Purpose: define a narrow infrastructure composition boundary that creates and exposes the four frozen PostgreSQL repository adapters over one shared `PostgresPersistenceService`, and delegates cross-repository atomic execution to the frozen M024 `run_composed` primitive.

## 7. Scope Boundary

Included:

- repository runtime/provider boundary;
- exact ownership of one shared `PostgresPersistenceService`;
- exposure of Campaign, Run, EvidencePackage, and Review repository adapters;
- delegation to `PostgresPersistenceService.run_composed(operations)`;
- lifecycle and close semantics for the composition object;
- error propagation rules;
- unit and PostgreSQL integration validation expectations.

Excluded:

- application services;
- retry policy;
- APIs and workers;
- schema, migration, mapper, repository protocol, or adapter behavior changes;
- transaction semantics beyond delegation to M024;
- Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior.

## 8. Dependencies

| Dependency | Role | Status |
| --- | --- | --- |
| M020 | Repository Protocol contracts | APPROVED AND FROZEN |
| M021 | Mapper contracts and durable records | APPROVED AND FROZEN |
| M022 | PostgreSQL schema/migration | APPROVED AND FROZEN |
| M023 | Concrete PostgreSQL repository adapters | APPROVED AND FROZEN |
| M024 | Multi-aggregate Unit of Work primitive | APPROVED AND FROZEN |

## 9. Validation Expectations

A future implementation must prove:

- all four exposed repositories share exactly one `PostgresPersistenceService` instance;
- `run_composed` is delegated to the frozen M024 primitive rather than reimplemented;
- repository protocols and concrete adapter semantics remain unchanged;
- no application orchestration or retry behavior is introduced;
- no schemas, migrations, APIs, workers, Audit, Decision Candidate, or Decision Freeze are added.

## 10. Final Decision

```text
M025 REPOSITORY RUNTIME COMPOSITION SCOPE SELECTED
M025 DESIGN READY FOR INDEPENDENT REVIEW
M025 NOT APPROVED
M025 NOT FROZEN
M025 IMPLEMENTATION NOT STARTED
```
