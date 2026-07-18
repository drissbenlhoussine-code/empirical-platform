# MILESTONE-015 - Process-Local Review Aggregate Behavior Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-015 |
| Title | Process-Local Review Aggregate Behavior Scope Selection |
| Version | 1.0 |
| Status | SCOPE CANDIDATE SELECTED |
| Repository baseline | `7df44603bfc3dc4096449417f6e343eee15ed919` |
| Baseline meaning | MILESTONE-014 approved, frozen, and committed |
| Mission type | Independent scope selection only |
| Implementation performed | None |
| Source modified | No |
| Schemas or migrations created | No |
| Commit intent | Documentation-only scope-selection commit |

## 2. Starting Baseline

The starting baseline is `7df44603bfc3dc4096449417f6e343eee15ed919`, whose commit message is `Harden MILESTONE-014 evidence package aggregate behavior`.

Baseline verification before this document:

| Check | Result |
| --- | --- |
| Branch | `master` |
| HEAD | `7df44603bfc3dc4096449417f6e343eee15ed919` |
| Working tree | Clean |
| Last frozen implementation milestone | MILESTONE-014 |

This document does not alter the frozen MILESTONE-014 implementation or any earlier milestone.

## 3. Repository Evidence Reviewed

| Evidence ID | Repository evidence | Scope relevance |
| --- | --- | --- |
| M015-EVID-0001 | `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md`, Section 18 | Freezes Review lifecycle states, Review disposition values, and local Review transition shape |
| M015-EVID-0002 | `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md`, Section 23 | Classifies target existence and reviewer independence as cross-aggregate or governance-gate checks |
| M015-EVID-0003 | `MILESTONE_013_PROCESS_LOCAL_DOMAIN_PRIMITIVE_FOUNDATION.md` | Implements Review lifecycle enum, Review disposition enum, transition records, identity pairing, versioning, and sequencing primitives |
| M015-EVID-0004 | `MILESTONE_014_PROCESS_LOCAL_AGGREGATE_BEHAVIOR_SCOPE_SELECTION.md`, Candidate D | States Review aggregate behavior should follow Evidence Package behavior |
| M015-EVID-0005 | `MILESTONE_014_PROCESS_LOCAL_EVIDENCE_PACKAGE_AGGREGATE_BEHAVIOR.md` | Freezes Evidence Package aggregate behavior and leaves Review aggregate behavior deferred |
| M015-EVID-0006 | `src/empirical_platform/review/lifecycle.py` | Contains Review lifecycle and disposition primitives but no Review aggregate behavior |
| M015-EVID-0007 | `src/empirical_platform/review/__init__.py` | States the Review boundary has no aggregate behavior implemented |
| M015-EVID-0008 | `tools/check_architecture.py` | Allows `review` to depend on `shared`, `identifiers`, and `evidence` only |
| M015-EVID-0009 | `migrations/versions` | Remains empty, preserving no-schema scope |

## 4. Completed Capability Context

The repository has already completed:

| Capability | Current state |
| --- | --- |
| Repository and toolchain foundation | Implemented and committed |
| Configuration, logging, errors, health, identifiers | Implemented and committed |
| PostgreSQL connectivity foundation | Implemented without domain schema |
| Object-storage connectivity foundation | Implemented without domain layout or retention policy |
| Unified infrastructure runtime composition | Implemented |
| Domain kernel design | Approved and frozen |
| Process-local domain primitives | Implemented and committed |
| Process-local Evidence Package aggregate behavior | Implemented and frozen |

MILESTONE-014 changed the Review readiness picture. Earlier scope selection deferred Review because target aggregate behavior did not yet exist. Evidence Package behavior now exists and is frozen, so a Review aggregate can reference an Evidence Package identity without inventing a target abstraction.

## 5. Candidate Scopes Considered

This review considered five serious candidates only:

| Candidate | Description | Initial disposition |
| --- | --- | --- |
| Candidate A | Process-local Review aggregate behavior | Selected |
| Candidate B | Process-local Run aggregate behavior | Deferred |
| Candidate C | Process-local Campaign aggregate behavior | Deferred |
| Candidate D | Domain persistence, schema, and repository design | Deferred |
| Candidate E | Audit or Decision Candidate runtime design | Deferred |

## 6. Evaluation Matrix

| Criterion | A. Review | B. Run | C. Campaign | D. Persistence | E. Audit/Decision |
| --- | ---: | ---: | ---: | ---: | ---: |
| Traceability to frozen MILESTONE-012 /20 | 20 | 20 | 18 | 14 | 12 |
| Prerequisite implementation readiness /15 | 14 | 11 | 9 | 8 | 5 |
| Local invariant concentration /15 | 13 | 11 | 8 | 7 | 6 |
| Cross-aggregate dependency avoidance /15 | 12 | 8 | 5 | 5 | 4 |
| Architecture-boundary fit /10 | 10 | 6 | 8 | 7 | 5 |
| No-schema compatibility /10 | 10 | 10 | 10 | 3 | 10 |
| Testability without implementation overreach /10 | 9 | 8 | 6 | 5 | 5 |
| Enables next capability /5 | 5 | 4 | 3 | 4 | 3 |
| Total /100 | 93 | 78 | 67 | 53 | 50 |

Candidate A is the only candidate above the implementation-readiness threshold.

## 7. Rejected Candidates

### Candidate B: Process-local Run aggregate behavior

Run remains architecturally central, but its aggregate behavior is not the safest next slice. It owns Dataset Manifest records, while the current architecture checker places `datasets` downstream of `campaign`; a Run aggregate implementation that directly imports `DatasetManifest` from the campaign package would violate the current dependency direction. Run also carries execution-stage names that can easily drift into acquisition, normalization, validation, and campaign execution behavior before those capabilities are ready.

Candidate B is deferred until package placement and Run-owned Dataset Manifest handling can be narrowed without changing frozen architecture accidentally.

### Candidate C: Process-local Campaign aggregate behavior

Campaign behavior is coordination-heavy. Completion and readiness depend on Runs, Reviews, authorization context, and derived status rules. Implementing Campaign before Run and Review behavior would encourage fake summaries, cross-aggregate queries, or governance authorization behavior.

Candidate C is deferred.

### Candidate D: Domain persistence, schema, and repository design

Persistence and repository design are premature. MILESTONE-012 states that no schema, table, column, migration, ORM mapping, or repository API is defined. Only one aggregate behavior has been implemented so far. The repository should not freeze persistence contracts before at least the next review-side aggregate pattern exists.

Candidate D is deferred.

### Candidate E: Audit or Decision Candidate runtime design

Audit and Decision Candidate are explicitly deferred in MILESTONE-012. They require evidence sufficiency, review completion semantics, audit authority, and decision-governance rules that are not part of the initial runtime kernel.

Candidate E is deferred.

## 8. Selected Scope

The selected next milestone is:

```text
MILESTONE-015 - Process-Local Review Aggregate Behavior
```

The future implementation milestone may implement exactly one process-local Review aggregate root. It must use frozen Review lifecycle and disposition primitives and may reference an Evidence Package target by immutable identity only.

This scope is selected because:

- MILESTONE-012 freezes the Review lifecycle and separates Review disposition from lifecycle;
- MILESTONE-013 implements the Review primitives required to build the aggregate;
- MILESTONE-014 implements the Evidence Package behavior that Review can target;
- architecture rules already permit `review` to depend on `evidence`;
- local Review behavior can be tested without persistence, APIs, workers, or cross-aggregate loading.

## 9. Scope Boundary

The selected scope is limited to process-local Review aggregate behavior.

Allowed future behavior:

- construct a Review with `DomainIdentity[ReviewId]`;
- record one immutable primary review target reference;
- allow an Evidence Package target reference without loading or validating that target;
- store reviewer assignment context as local immutable value data;
- transition `ASSIGNED` to `IN_PROGRESS`;
- transition `IN_PROGRESS` to `COMPLETED`;
- transition `ASSIGNED` or `IN_PROGRESS` to `CANCELLED`;
- record bounded immutable Review findings;
- record exactly one Review disposition at completion;
- keep Review lifecycle separate from Review disposition;
- maintain aggregate version and transition sequence;
- append transition history as historical process-local data only.

The selected scope must not validate target existence, target sealed state, reviewer independence, conflict-of-interest sufficiency, evidence staleness, or campaign authorization. Those are cross-aggregate, governance-gate, or reconciliation concerns.

## 10. Allowed Deliverables

A future MILESTONE-015 implementation may create or modify only:

- Review aggregate source files under `src/empirical_platform/review/`;
- Review aggregate exports under `src/empirical_platform/review/__init__.py`;
- focused unit tests for Review aggregate behavior;
- architecture-boundary tests if needed;
- a MILESTONE-015 implementation report.

The implementation report must include:

- baseline;
- scope traceability;
- lifecycle and disposition evidence;
- local versus cross-aggregate boundary audit;
- requirement-to-test matrix;
- validation evidence;
- issue register;
- deferred items;
- final status.

## 11. Explicit Non-Goals

MILESTONE-015 must not implement:

- Campaign aggregate behavior;
- Run aggregate behavior;
- Audit runtime behavior;
- Decision Candidate behavior;
- Decision Freeze behavior;
- target existence lookup;
- reviewable-target qualification;
- reviewer independence enforcement;
- conflict-of-interest gate execution;
- evidence invalidation reconciliation;
- stale-review reconciliation;
- persistence schemas, tables, columns, migrations, ORM mappings, or repositories;
- object-storage layout, bucket, key, checksum, or retention semantics;
- APIs, workers, schedulers, event dispatch, job ledger, transactional outbox, or audit ledger;
- trading behavior, vendor behavior, market-data behavior, empirical validation, or campaign execution.

## 12. Dependencies

| Dependency | Required role |
| --- | --- |
| MILESTONE-012 | Frozen Review model, lifecycle, disposition, and cross-aggregate boundary classification |
| MILESTONE-013 | Review lifecycle enum, Review disposition enum, `AggregateVersion`, `TransitionSequence`, `StateTransitionRecord`, and identity pairing |
| MILESTONE-014 | Evidence Package aggregate behavior available as a concrete downstream review target |
| Architecture checker | Confirms `review` may depend on `evidence` without reversing dependency direction |
| Identifier package | Provides `ReviewId`, `EvidencePackageId`, and `DomainIdentity` |

No additional external governance artifact is required before selecting the scope.

## 13. Assumptions Prohibited

The future implementation must not assume:

- a database schema exists;
- a repository interface exists;
- a Review can query or load an Evidence Package;
- a Review can prove the target is sealed;
- reviewer independence can be proven inside the aggregate;
- a disposition authorizes vendor selection;
- a completed Review creates a Decision Candidate;
- a cancelled Review mutates the target;
- archival is a lifecycle state;
- invalidation is a lifecycle state;
- Review transition records are domain events or outbox messages.

## 14. Local Versus Cross-Aggregate Boundary

| Rule or behavior | Classification | MILESTONE-015 treatment |
| --- | --- | --- |
| Review identity is immutable | Local synchronous | In scope |
| Review target reference is immutable | Local synchronous | In scope |
| Review lifecycle transition shape | Local synchronous | In scope |
| Review disposition recorded at completion | Local synchronous | In scope |
| Findings are immutable owned records | Local synchronous | In scope if bounded |
| Target exists | Cross-aggregate command-time | Deferred |
| Target is reviewable or sealed | Cross-aggregate command-time | Deferred |
| Reviewer independence is recorded | Governance gate | Deferred |
| Evidence invalidation affects prior Review | Eventual reconciliation | Deferred |
| Completed Review affects Decision Candidate sufficiency | Governance gate | Deferred |

## 15. Architecture Compliance

The selected scope fits current architecture rules:

- `review` may import `shared`, `identifiers`, and `evidence`;
- `review` must not import `campaign`, `datasets`, `persistence`, `storage`, `entrypoints`, `audit`, or `decision_candidate`;
- evidence-package targeting can use an identity reference only;
- no source package dependency direction must be changed for scope selection;
- no schema ownership moves into the Review package.

If implementation discovers that Review target modeling requires a new shared primitive, the implementation must stop and produce a revision rather than widening the slice.

## 16. Risks

| Risk ID | Severity | Risk | Mitigation |
| --- | --- | --- | --- |
| M015-SCOPE-RISK-0001 | MAJOR | Review target reference could become an implicit repository lookup | Store identity reference only; defer target validation |
| M015-SCOPE-RISK-0002 | MAJOR | Reviewer independence could be implemented inside the aggregate without required governance evidence | Treat independence as external gate evidence only |
| M015-SCOPE-RISK-0003 | MAJOR | Review disposition could be confused with lifecycle state | Use separate primitives and tests that prohibit disposition values as lifecycle states |
| M015-SCOPE-RISK-0004 | MINOR | Finding model could become unbounded or schema-like | Keep findings bounded, immutable, and process-local |
| M015-SCOPE-RISK-0005 | MINOR | Completion could imply Decision Candidate readiness | State explicitly that Review completion has no decision authority |

## 17. Required Design Questions

The implementation mission must answer before coding:

1. Should the selected target type be limited to Evidence Package for MILESTONE-015, with Run target Review deferred?
2. What is the minimal immutable representation of a Review target reference?
3. What fields are required for a bounded Review finding without creating audit-ledger semantics?
4. Does cancellation require a reason, an actor, and a transition record?
5. Does completion require at least one finding, or only a disposition?
6. Which rejected transitions must be tested for atomicity?

If any answer requires persistence, repository lookup, target loading, campaign execution, audit behavior, or Decision Candidate behavior, implementation must stop.

## 18. Validation Expectations

The future implementation must pass:

- focused Review aggregate unit tests;
- lifecycle/disposition separation tests;
- transition-history and versioning tests;
- rejection atomicity tests;
- architecture checker;
- security scanner;
- project verification script;
- `git diff --check`;
- confirmation that `migrations/versions` remains empty.

Expected test coverage must remain above the project threshold. New tests must prove no schema, repository, API, worker, outbox, audit-ledger, trading, vendor, or execution behavior was introduced.

## 19. Hostile-Review Criteria

The scope must be rejected if any of the following is true:

- it requires a database schema;
- it requires a repository interface;
- it requires loading an Evidence Package;
- it validates target existence inside the Review aggregate;
- it treats reviewer independence as locally provable;
- it treats disposition as lifecycle;
- it creates Audit or Decision Candidate behavior;
- it mutates Evidence Package state;
- it introduces campaign execution or vendor behavior.

Hostile-review findings during this scope selection:

| Finding ID | Severity | Finding | Correction |
| --- | --- | --- | --- |
| M015-SCOPE-ISSUE-0001 | MAJOR | Initial Review scope could overclaim target reviewability. | Scope narrowed to immutable target reference only; target existence and reviewability are deferred. |
| M015-SCOPE-ISSUE-0002 | MAJOR | Reviewer independence could be read as an aggregate invariant. | Independence is classified as governance-gate evidence outside the aggregate. |
| M015-SCOPE-ISSUE-0003 | MINOR | Run-target Review could require Run aggregate behavior before it exists. | Implementation design must decide whether MILESTONE-015 is Evidence-Package-target only and stop if Run target is required. |

All hostile-review findings are resolved for scope selection.

## 20. Acceptance Gate

MILESTONE-015 may move from scope selection to implementation only if:

- this scope-selection document is committed;
- the working tree is clean;
- MILESTONE-014 remains frozen;
- no schema, repository, API, worker, outbox, audit-ledger, trading, vendor, campaign execution, Decision Candidate, or Decision Freeze work has started;
- the implementation mission restates all non-goals;
- the implementation mission keeps Review target validation and reviewer independence outside the aggregate.

## 21. Stop Conditions

Stop implementation immediately if:

- a database schema is needed;
- a repository or query is needed;
- target existence must be checked;
- target sealed state must be checked;
- reviewer independence must be enforced inside the aggregate;
- Review must update Evidence Package;
- Review must create Audit or Decision Candidate artifacts;
- architecture checker requires broadening dependencies beyond the current review boundary;
- any code path introduces trading, vendor, market-data, or campaign execution behavior.

## 22. Deferred Work

Deferred beyond MILESTONE-015:

- Run aggregate behavior;
- Campaign aggregate behavior;
- Run-target Review behavior if not safely local;
- reviewer independence gate execution;
- conflict-of-interest workflow execution;
- target reviewability checks;
- stale-review reconciliation after evidence invalidation;
- Audit runtime;
- Decision Candidate runtime;
- persistence schema and repository design;
- object-storage layout and retention policy;
- API, worker, job ledger, outbox, and audit-ledger design.

## 23. Final Decision

The next implementation-ready scope is:

```text
MILESTONE-015 - Process-Local Review Aggregate Behavior
```

Final scope-selection status:

```text
SCOPE CANDIDATE SELECTED
```

No implementation has been performed. No code, schema, migration, repository, API, worker, job ledger, outbox, Audit runtime, Decision Candidate runtime, Decision Freeze, trading behavior, vendor behavior, market-data behavior, or campaign execution behavior is introduced by this document.
