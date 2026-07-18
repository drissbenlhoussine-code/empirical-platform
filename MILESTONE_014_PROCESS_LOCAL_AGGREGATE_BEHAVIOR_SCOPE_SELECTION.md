# MILESTONE-014 - Process-Local Aggregate Behavior Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-014 |
| Title | Process-Local Aggregate Behavior Scope Selection |
| Version | 1.0 |
| Status | IMPLEMENTATION SLICE READY |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Repository baseline | `09bbce8e750deff730e250e35cd5a9cf8b1fe5e1` |
| Mission type | Scope selection and architecture gap review only |
| Implementation performed | None |
| Source code modified | No |
| Schema, migration, or table created | No |
| Commit policy | Not staged and not committed by this mission |

## 2. Scope

This document selects the safest first process-local aggregate behavior slice after MILESTONE-013.

It evaluates Campaign, Run, Evidence Package, Review, shared aggregate framework, and two-aggregate vertical-slice options against frozen MILESTONE-012 and actual repository state.

This document does not implement aggregate behavior, modify source code, create schemas, create migrations, define repositories, create APIs, add workers, add job ledger behavior, add outbox behavior, execute campaigns, validate vendors, create Audit runtime, create Decision Candidate runtime, or perform Decision Freeze.

## 3. Repository Baseline

Required and verified baseline:

```text
09bbce8e750deff730e250e35cd5a9cf8b1fe5e1
```

Observed repository state:

- branch: `master`;
- working tree before this report: clean;
- MILESTONE-013 process-local primitives are committed;
- `migrations/versions` remains empty;
- no aggregate behavior exists in `campaign`, `datasets`, `evidence`, or `review`;
- architecture checker rules remain unchanged.

## 4. Governing Documents

| Document | Status / role | MILESTONE-014 relevance |
| --- | --- | --- |
| `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` | APPROVED AND FROZEN | Defines aggregate roots, owned records, lifecycle states, invariants, persistence boundaries, and deferrals |
| `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_INDEPENDENT_REVIEW.md` | Independent review | Identifies prior over-modeling and correction rationale |
| `MILESTONE_013_DOMAIN_KERNEL_IMPLEMENTATION_SCOPE_SELECTION.md` | Committed scope-selection predecessor | Establishes aggregate behavior as the next capability after primitives |
| `MILESTONE_013_PROCESS_LOCAL_DOMAIN_PRIMITIVE_FOUNDATION.md` | APPROVED AND FROZEN | Implements lifecycle enums, versioning, transition records, identity pairing, Dataset Manifest, and Criterion Result primitives |
| `MILESTONE_005_INFRASTRUCTURE_ARCHITECTURE.md` | Approved infrastructure architecture | Confirms domain code may depend on foundation layers, not the reverse |
| `MILESTONE_006_FOUNDATION_CONTRACTS.md` | Approved foundation contracts | Defines foundation boundaries and prohibits domain leakage into infrastructure |
| `MILESTONE_007_FIRST_INFRASTRUCTURE_IMPLEMENTATION_SLICE.md` | Approved implementation evidence | Provides process-local foundation behavior and runtime IDs |
| `MILESTONE_010_UNIFIED_INFRASTRUCTURE_RUNTIME_COMPOSITION.md` | Approved implementation evidence | Confirms runtime composition without domain behavior |

## 5. Current Capability Inventory

| Capability | Classification | Evidence |
| --- | --- | --- |
| Campaign aggregate behavior | DESIGNED AND FROZEN / NOT IMPLEMENTED | MILESTONE-012 defines Campaign root; no Campaign class exists |
| Run aggregate behavior | DESIGNED AND FROZEN / NOT IMPLEMENTED | MILESTONE-012 defines Run root; no Run class exists |
| Evidence Package aggregate behavior | DESIGNED AND FROZEN / NOT IMPLEMENTED | MILESTONE-012 defines Evidence Package root; no aggregate class exists |
| Review aggregate behavior | DESIGNED AND FROZEN / NOT IMPLEMENTED | MILESTONE-012 defines Review root; no aggregate class exists |
| Lifecycle enums | IMPLEMENTED AND VERIFIED | MILESTONE-013 committed exact lifecycle primitives |
| Review disposition enum | IMPLEMENTED AND VERIFIED | MILESTONE-013 separates lifecycle from disposition |
| Identity pairing | IMPLEMENTED AND VERIFIED | `DomainIdentity` and `pair_identity` exist |
| AggregateVersion | IMPLEMENTED AND VERIFIED | Immutable primitive exists and rejects invalid values |
| TransitionSequence | IMPLEMENTED AND VERIFIED | Immutable primitive exists and rejects invalid values |
| StateTransitionRecord | IMPLEMENTED AND VERIFIED | Immutable transition record exists |
| Dataset Manifest | IMPLEMENTED AND VERIFIED | Immutable Run-owned primitive exists |
| Criterion Result | IMPLEMENTED AND VERIFIED | Immutable Evidence-Package-owned primitive exists |
| Transition authorization | DESIGNED ONLY / DEFERRED | Roles exist in MILESTONE-012; no authorization subsystem exists |
| Local synchronous invariants | DESIGNED AND PARTIALLY READY | Primitive-level invariants exist; aggregate-level invariants not implemented |
| Cross-aggregate invariants | DEFERRED | MILESTONE-012 classifies them as command-time or eventual |
| Command idempotency | NOT YET DESIGNED | No command model exists |
| Persistence | FOUNDATION ONLY / DOMAIN DEFERRED | PostgreSQL connectivity exists; no domain schema/repositories |
| Repositories | NOT YET DESIGNED | No repository contract or implementation |
| Events | VOCABULARY ONLY / DEFERRED | MILESTONE-012 lists event vocabulary; no event implementation |
| Outbox | DEFERRED | Explicitly deferred |
| APIs/workers | DEFERRED | Explicitly absent |

## 6. Frozen Aggregate Model Summary

MILESTONE-012 defines the initial aggregate roots as:

- Campaign;
- Run;
- Evidence Package;
- Review.

Owned records/entities:

- Dataset Manifest is an immutable owned record under Run;
- Criterion Result is an owned entity under Evidence Package.

Deferred runtime concepts:

- Audit;
- Decision Candidate;
- job ledger;
- transactional outbox;
- audit event ledger;
- domain schemas;
- repositories;
- APIs and workers.

## 7. Current Implementation Gap

The repository has process-local primitives but no aggregate root behavior.

The first gap is an aggregate that can:

- own identity;
- hold lifecycle state;
- enforce local synchronous invariants;
- update `AggregateVersion`;
- append `StateTransitionRecord` using `TransitionSequence`;
- use existing owned primitives;
- remain process-local, persistence-neutral, API-free, worker-free, and event-dispatch-free.

## 8. First Blocked Capability

The first blocked capability is safe process-local aggregate state transition behavior.

Without one aggregate implementation, later work cannot responsibly design:

- aggregate persistence schemas;
- repository contracts;
- command handlers;
- idempotency rules;
- event/outbox semantics;
- cross-aggregate coordination.

The selected aggregate should maximize local invariant value while minimizing dependency on other aggregates.

## 9. Candidate A Evaluation

Candidate A: Campaign Aggregate Behavior.

Possible scope:

- Campaign aggregate state;
- creation;
- lifecycle transitions;
- authorization readiness;
- suspension/resumption;
- completion/cancellation;
- `AggregateVersion` increments;
- `TransitionSequence` history;
- local invariants only.

Assessment:

Campaign is architecturally important, but it is coordination-heavy. Authorization readiness is governance-sensitive, and completion requires no active Runs plus required Review dispositions. Implementing Campaign first risks either weakening those preconditions or accidentally introducing derived status, authorization logic, or cross-aggregate query assumptions.

Score:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 19 | Campaign is a top-level root |
| Traceability to frozen MILESTONE-012 /15 | 15 | Lifecycle is fully frozen |
| Prerequisite readiness /15 | 11 | Primitives exist, but governance authorization remains external |
| Local invariant concentration /15 | 9 | Important rules depend on Runs and Reviews |
| Cross-aggregate dependency avoidance /10 | 4 | Completion and readiness are coordination-sensitive |
| Testability /10 | 8 | Local transitions are testable but incomplete |
| Reversibility /5 | 4 | Process-local implementation is reversible |
| Boundedness /5 | 3 | Scope would need careful exclusions |
| Enables next capability /5 | 4 | Enables Run sequencing later |
| Total /100 | 77 | Defer |

Decision: Candidate A is not recommended as the first aggregate behavior slice.

## 10. Candidate B Evaluation

Candidate B: Run Aggregate Behavior.

Possible scope:

- Run creation;
- authorization;
- execution-state progression;
- failure/cancellation;
- rerun reference semantics;
- immutable scope snapshot;
- `AggregateVersion` and transition history.

Assessment:

Run exercises Dataset Manifest ownership and has a clear lifecycle. However, Run authorization depends on Campaign authorization, execution-state terms can drift toward campaign execution, and the Run lifecycle references acquisition, normalization, and validation stages that are not yet behaviorally implemented.

Score:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 20 | Run is central to future campaigns |
| Traceability to frozen MILESTONE-012 /15 | 15 | Lifecycle is fully frozen |
| Prerequisite readiness /15 | 12 | Run lifecycle and Dataset Manifest primitives exist |
| Local invariant concentration /15 | 11 | Some rules are local, but authorization and evidence are external |
| Cross-aggregate dependency avoidance /10 | 5 | Requires Campaign context and later Evidence Package references |
| Testability /10 | 8 | Process-local tests possible but terminology risks overreach |
| Reversibility /5 | 4 | No schema needed |
| Boundedness /5 | 3 | Scope may expand into execution behavior |
| Enables next capability /5 | 5 | Enables Evidence and persistence sequencing |
| Total /100 | 83 | Strong but risky first slice |

Decision: Candidate B should follow a lower-risk aggregate behavior proof.

## 11. Candidate C Evaluation

Candidate C: Evidence Package Aggregate Behavior.

Possible scope:

- initialize Evidence Package;
- start collection;
- collect bounded Criterion Results;
- collect generic artifact references;
- seal;
- invalidate sealed package;
- enforce post-seal immutability;
- update `AggregateVersion`;
- append transition history.

Assessment:

Evidence Package has the strongest local invariant concentration. It owns Criterion Results, has a compact lifecycle, does not need to execute market-data acquisition, and can treat artifact references as opaque process-local strings without object-storage layout or retention semantics. It can validate versioning, transition history, sealing, and invalidation without persistence, APIs, workers, event dispatch, or cross-aggregate transactions.

Score:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 19 | Evidence Package is essential to later validation and review |
| Traceability to frozen MILESTONE-012 /15 | 15 | Lifecycle and owned Criterion Result model are frozen |
| Prerequisite readiness /15 | 15 | MILESTONE-013 supplies all needed primitives |
| Local invariant concentration /15 | 15 | Seal/immutability/invalidation are strongly local |
| Cross-aggregate dependency avoidance /10 | 9 | Requires Run reference only as immutable ID context |
| Testability /10 | 10 | Fully testable process-locally |
| Reversibility /5 | 5 | No schema or adapter lock-in |
| Boundedness /5 | 5 | One aggregate with one owned entity collection |
| Enables next capability /5 | 5 | Enables Review and later repository design |
| Total /100 | 98 | Recommended |

Decision: Candidate C is recommended for MILESTONE-014.

## 12. Candidate D Evaluation

Candidate D: Review Aggregate Behavior.

Possible scope:

- assign Review;
- begin Review;
- complete Review;
- cancel Review;
- immutable findings;
- disposition separation;
- conflict-of-interest record boundary;
- version/transition history.

Assessment:

Review is bounded and has clear lifecycle/disposition separation. The blocker is that Review depends on reviewable targets, particularly sealed Evidence Packages or completed Runs. Implementing it before Evidence Package behavior risks either inventing target abstractions or weakening target existence and independence semantics.

Score:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 17 | Review is required for evidence governance |
| Traceability to frozen MILESTONE-012 /15 | 15 | Lifecycle and disposition are frozen |
| Prerequisite readiness /15 | 12 | Review primitives exist, target aggregates do not |
| Local invariant concentration /15 | 12 | Findings/disposition are local, independence is partly external |
| Cross-aggregate dependency avoidance /10 | 5 | Requires reviewable target semantics |
| Testability /10 | 8 | Local tests possible but target checks would be fake |
| Reversibility /5 | 4 | Process-local implementation is reversible |
| Boundedness /5 | 4 | Narrow, but not independently useful yet |
| Enables next capability /5 | 4 | Enables review workflow after evidence exists |
| Total /100 | 81 | Defer |

Decision: Candidate D should follow Evidence Package behavior.

## 13. Candidate E Evaluation

Candidate E: Shared Aggregate Base or Framework.

Possible scope:

- generic aggregate base;
- generic transition engine;
- generic invariant dispatcher;
- generic transition history collection.

Assessment:

This candidate is attractive in name but dangerous in timing. The repository has not implemented even one aggregate. A generic base would likely encode guesses about transition policy, ownership, error style, and mutation semantics. Composition inside the first concrete aggregate is safer; duplication can be extracted after at least two aggregates reveal the real pattern.

Score:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 8 | May be useful later, not required now |
| Traceability to frozen MILESTONE-012 /15 | 6 | MILESTONE-012 does not mandate a framework |
| Prerequisite readiness /15 | 5 | No concrete aggregate pattern exists yet |
| Local invariant concentration /15 | 4 | Abstract framework does not enforce domain invariants |
| Cross-aggregate dependency avoidance /10 | 7 | Avoids domain dependencies but risks generic coupling |
| Testability /10 | 5 | Tests would validate framework assumptions |
| Reversibility /5 | 2 | Frameworks become sticky quickly |
| Boundedness /5 | 2 | Scope is deceptively broad |
| Enables next capability /5 | 3 | Could help later but not necessary |
| Total /100 | 42 | Reject |

Decision: Candidate E is rejected for MILESTONE-014.

## 14. Candidate F Evaluation

Candidate F: Two-Aggregate Vertical Slice.

Possible examples:

- Evidence Package plus Review;
- Campaign plus Run.

Assessment:

Two aggregates are not required to prove transition history, versioning, or local invariant enforcement. A vertical slice would immediately introduce cross-aggregate validation, fake target existence, or command orchestration. This is too large for the first aggregate behavior milestone.

Score:

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Architectural necessity /20 | 14 | Interactions matter later |
| Traceability to frozen MILESTONE-012 /15 | 13 | Multiple roots are frozen |
| Prerequisite readiness /15 | 8 | Primitive layer is ready, interaction layer is not |
| Local invariant concentration /15 | 8 | Local rules become mixed with coordination |
| Cross-aggregate dependency avoidance /10 | 1 | This candidate embraces cross-aggregate behavior |
| Testability /10 | 6 | Test burden expands quickly |
| Reversibility /5 | 2 | Multiple public APIs lock in at once |
| Boundedness /5 | 1 | Too broad |
| Enables next capability /5 | 4 | Enables interaction design but prematurely |
| Total /100 | 57 | Reject for now |

Decision: Candidate F is rejected for MILESTONE-014.

## 15. Additional Candidate Evaluation, if any

No additional candidate is introduced.

An "Evidence Package only with no cross-aggregate coordination" option is not separate from Candidate C; it is the recommended narrowing of Candidate C.

An "Aggregate Command Primitives" or "Transition Policy Objects" milestone would duplicate Candidate E's abstraction risk before a concrete aggregate reveals real needs.

## 16. Comparative Score Matrix

| Candidate | Architectural necessity /20 | Traceability /15 | Prerequisite readiness /15 | Local invariants /15 | Avoid cross-aggregate /10 | Testability /10 | Reversibility /5 | Boundedness /5 | Enables next /5 | Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A. Campaign Aggregate Behavior | 19 | 15 | 11 | 9 | 4 | 8 | 4 | 3 | 4 | 77 |
| B. Run Aggregate Behavior | 20 | 15 | 12 | 11 | 5 | 8 | 4 | 3 | 5 | 83 |
| C. Evidence Package Aggregate Behavior | 19 | 15 | 15 | 15 | 9 | 10 | 5 | 5 | 5 | 98 |
| D. Review Aggregate Behavior | 17 | 15 | 12 | 12 | 5 | 8 | 4 | 4 | 4 | 81 |
| E. Shared Aggregate Base/Framework | 8 | 6 | 5 | 4 | 7 | 5 | 2 | 2 | 3 | 42 |
| F. Two-Aggregate Vertical Slice | 14 | 13 | 8 | 8 | 1 | 6 | 2 | 1 | 4 | 57 |

## 17. Anti-Confirmation-Bias Review

The strongest argument for Campaign first is that Campaign is the parent object. That argument fails for this milestone because Campaign completion and readiness quickly become governance and Run coordination problems.

The strongest argument for Run first is that Run is the future execution center. That argument is real, but Run's lifecycle names can pull implementation toward acquisition, normalization, validation, and execution behavior before those capabilities are designed.

The strongest argument for Review first is independence and governance value. That argument is attractive but premature because Review target semantics become artificial without a sealed Evidence Package or completed Run behavior.

The strongest argument against Evidence Package first is that it references a Run. This can be handled as immutable ID context only, without loading or validating Run existence.

## 18. Aggregate Abstraction Risk

A shared aggregate framework is not justified yet.

Risks:

- generic transition engine locks in command semantics too early;
- base-class inheritance becomes hard to unwind;
- invariant dispatcher may obscure simple local methods;
- event vocabulary may be confused with actual event production;
- future persistence design could be shaped by framework convenience rather than aggregate needs.

Required posture:

- implement concrete aggregate behavior first;
- use composition over inheritance;
- extract shared abstractions only after at least two aggregate implementations reveal stable duplication.

## 19. Cross-Aggregate Dependency Analysis

| Aggregate | External dependency pressure | First-slice suitability |
| --- | --- | --- |
| Campaign | High: readiness, authorization, Run summaries, Review dispositions | Too coordination-heavy |
| Run | Medium-high: Campaign authorization, Evidence Package references, execution-stage semantics | Strong but risky |
| Evidence Package | Low: immutable Run ID context only; Review is downstream | Best fit |
| Review | Medium: target existence, sealed evidence, independence records | Better after Evidence Package |

Evidence Package can be implemented with Run reference as immutable identity context only. It must not query, validate, or mutate Run.

## 20. Recommended MILESTONE-014

Recommended MILESTONE-014:

```text
MILESTONE-014 - Process-Local Evidence Package Aggregate Behavior
```

Purpose:

Implement one process-local aggregate root that proves lifecycle transitions, version increments, transition history, owned Criterion Results, artifact-reference collection, sealing, and invalidation without persistence, storage layout, APIs, workers, event dispatch, or cross-aggregate transactions.

Recommended status at creation:

```text
DRAFT / EVIDENCE PACKAGE AGGREGATE BEHAVIOR UNDER REVIEW
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

- MILESTONE-012 freezes Evidence Package lifecycle and owned Criterion Result behavior;
- MILESTONE-013 provides all required primitives;
- the selected aggregate has strong local invariants;
- no schema, repository, API, worker, outbox, event dispatch, Audit, Decision Candidate, or campaign execution is required.

## 22. Exact Implementation Scope

Selected aggregate:

```text
Evidence Package
```

Likely affected packages:

- `src/empirical_platform/evidence/`;
- `tests/unit/`;
- milestone implementation report for MILESTONE-014.

Required implementation elements:

- process-local `EvidencePackage` aggregate root;
- constructor or factory for initialized package;
- `DomainIdentity[EvidencePackageId]` for aggregate identity;
- immutable `RunId` reference as parent context;
- current `EvidencePackageLifecycleState`;
- `AggregateVersion`;
- next `TransitionSequence`;
- immutable transition history collection;
- bounded collection of `CriterionResult`;
- bounded collection of opaque artifact references using a minimal local immutable value object if no existing primitive is available;
- operation to start collection;
- operation to add Criterion Result while mutable;
- operation to add artifact reference while mutable;
- operation to seal package;
- operation to invalidate sealed package with reason;
- no operation to unseal;
- no operation to edit sealed Criterion Results or artifact references;
- no operation to review evidence.

## 23. Exact Non-Goals

MILESTONE-014 must not implement:

- Campaign aggregate behavior;
- Run aggregate behavior;
- Review aggregate behavior;
- Audit runtime;
- Decision Candidate runtime;
- Decision Freeze behavior;
- command handlers or application services;
- authorization subsystem;
- cross-aggregate validation;
- repository protocols or concrete repositories;
- persistence schemas, migrations, tables, columns, indexes, or ORM mappings;
- object-storage layout, bucket hierarchy, key convention, retention policy, or checksum policy;
- event production, event dispatch, event store, job ledger, or transactional outbox;
- API routes or production endpoints;
- background workers;
- campaign execution;
- empirical validation;
- B3 criteria;
- vendor adapters;
- market-data acquisition;
- trading behavior.

## 24. Local Invariants Included

MILESTONE-014 should enforce only local synchronous Evidence Package invariants:

| Invariant | Required behavior |
| --- | --- |
| Evidence Package has exactly one identity | identity set at creation and immutable |
| Evidence Package references one Run by `RunId` | parent Run ID set at creation and immutable |
| Initial state is `INITIALIZED` | factory sets lifecycle state |
| Collection starts from `INITIALIZED` | transition to `COLLECTING` only from `INITIALIZED` |
| Criterion Results added only during collection | allowed only in `COLLECTING`; rejected in `INITIALIZED`, `SEALED`, or `INVALIDATED` |
| Criterion Result identity is package-local | duplicate `criterion_id` within one Evidence Package is rejected; replacement, overwrite, merge, and mutation are not in scope |
| Artifact references added only during collection | allowed only in `COLLECTING`; rejected in `INITIALIZED`, `SEALED`, or `INVALIDATED` |
| Artifact reference identity is opaque and local | duplicate exact reference values within one Evidence Package are rejected; no path, URI, bucket, key, checksum, retention, or existence semantics are introduced |
| Seal requires required contents | at minimum one Criterion Result and one artifact reference |
| Seal moves `COLLECTING` to `SEALED` | transition record appended |
| Sealed contents are immutable | no edit/add after seal |
| Invalidation allowed only after seal | `SEALED` to `INVALIDATED` with non-empty reason |
| Invalidation does not mutate sealed contents | contents remain preserved |
| Every lifecycle transition increments version | `AggregateVersion.next()` used |
| Every lifecycle transition appends history | `StateTransitionRecord` appended with current sequence |
| Transition sequence is append-only | next sequence increments once per transition |

## 25. Cross-Aggregate Invariants Deferred

Deferred invariants:

- Run must exist;
- Run must be active or execution-completed;
- Run owns or references the package;
- Dataset Manifest must be compatible with package contents;
- Review target must exist and be reviewable;
- Reviewer independence;
- evidence invalidation making prior Review stale or qualified;
- Campaign completion based on evidence/review status;
- Decision Candidate evidence sufficiency;
- object existence in storage;
- digest or checksum verification;
- durable transition history;
- repository-level uniqueness.

## 26. Lifecycle Operations Included

Included lifecycle operations:

- create initialized package;
- `start_collection`;
- `seal`;
- `invalidate`.

Included non-lifecycle mutations:

- add `CriterionResult` during `COLLECTING`;
- add opaque artifact reference during `COLLECTING`.

Excluded lifecycle operations:

- unseal;
- archive;
- review;
- audit;
- restore;
- supersede;
- complete Review;
- produce Decision Candidate.

## 27. Versioning and Transition-History Requirements

Required behavior:

- aggregate starts with `AggregateVersion.initial()`;
- aggregate starts with `TransitionSequence.initial()` available for first transition;
- aggregate creation sets empty immutable Criterion Result, artifact-reference, and transition-history collections;
- every accepted lifecycle transition increments version exactly once;
- every accepted lifecycle transition appends exactly one `StateTransitionRecord`;
- every accepted lifecycle transition advances the next `TransitionSequence` exactly once;
- every accepted Criterion Result append increments version exactly once and does not append transition history;
- every accepted artifact-reference append increments version exactly once and does not append transition history;
- rejected transitions do not change state, version, sequence, contents, or history;
- rejected collection operations do not change state, version, sequence, contents, or history.

Construction and rejection conventions:

- creation requires a `DomainIdentity[EvidencePackageId]` and `RunId`;
- invalid constructor arguments, empty artifact-reference values, duplicate Criterion Result identities, duplicate artifact-reference values, illegal lifecycle transitions, and illegal collection mutations are rejected with deterministic process-local exceptions matching the style of existing primitives;
- rejection is atomic: no partial state mutation is allowed;
- `StateTransitionRecord` remains historical lifecycle data only and must not be emitted as a domain event, job, outbox message, or audit ledger record.

## 28. Testing Strategy

Required focused tests:

- aggregate creation sets identity, Run ID, `INITIALIZED`, initial version, empty contents, and empty history;
- `start_collection` transitions to `COLLECTING`, increments version, appends history;
- Criterion Result can be added during `COLLECTING`;
- Criterion Result cannot be added before `start_collection`;
- duplicate Criterion Result identity is rejected without mutation;
- artifact reference can be added during `COLLECTING`;
- artifact reference cannot be added before `start_collection`;
- duplicate artifact reference is rejected without mutation;
- seal fails with no Criterion Result;
- seal fails with no artifact reference;
- seal succeeds from `COLLECTING`;
- seal increments version and appends history;
- adding Criterion Result after seal fails without mutation;
- adding artifact reference after seal fails without mutation;
- invalidation fails before seal;
- invalidation succeeds after seal with non-empty reason;
- invalidation preserves sealed contents;
- rejected transitions leave version/history unchanged;
- rejected content additions leave version/history/collections unchanged;
- aggregate exposes immutable views of collections;
- no persistence/import/storage dependency enters evidence aggregate package;
- full project verification passes.

## 29. Architecture Boundaries

Evidence Package aggregate may depend on:

- standard library;
- `empirical_platform.identifiers`;
- `empirical_platform.shared.identifiers`;
- `empirical_platform.shared.domain`;
- `empirical_platform.evidence.lifecycle`;
- `empirical_platform.evidence.results`.

Evidence Package aggregate must not depend on:

- `empirical_platform.shared.persistence`;
- `empirical_platform.shared.object_storage`;
- SQLAlchemy;
- psycopg;
- boto3/botocore;
- Alembic;
- entrypoints;
- bootstrap runtime composition;
- APIs;
- workers;
- registry;
- governance runtime;
- Campaign, Run, Review, Audit, or Decision Candidate aggregate implementations.

## 30. Risks

| ID | Severity | Risk | Mitigation |
| --- | --- | --- | --- |
| M014-SCOPE-ISSUE-0001 | MAJOR | Artifact references could become object-storage layout by another name | Keep references opaque strings or minimal local values; no bucket/key/path semantics |
| M014-SCOPE-ISSUE-0002 | MAJOR | Seal semantics could imply empirical validation completion | Define seal as package write closure only, not correctness or vendor validation |
| M014-SCOPE-ISSUE-0003 | MAJOR | Run reference could become cross-aggregate validation | Store `RunId` only; do not load or validate Run |
| M014-SCOPE-ISSUE-0004 | MINOR | Content mutation versioning could be ambiguous | Specify lifecycle vs content version behavior before implementation |
| M014-SCOPE-ISSUE-0005 | MINOR | Invalidation could be mistaken for content mutation | Preserve sealed contents and append invalidation transition only |

No blocker prevents Candidate C if these mitigations are honored.

## 31. Acceptance Criteria

This scope-selection report is complete if:

- repository baseline is verified;
- current capability inventory is classified;
- first blocked capability is identified;
- Candidate A through Candidate F are evaluated;
- comparative score arithmetic is correct;
- one recommended aggregate is selected;
- milestone type is exactly one allowed value;
- exact implementation scope and non-goals are defined;
- local and cross-aggregate invariants are separated;
- lifecycle operations are enumerated;
- versioning/history rules are stated;
- testing strategy is defined;
- architecture boundaries are stated;
- risks use `M014-SCOPE-ISSUE-####` identifiers;
- no source code is modified;
- no implementation is started;
- `git diff --check` passes.

Result: PASS.

## 32. Final Decision

Final decision:

```text
IMPLEMENTATION SLICE READY
```

Recommended next mission:

```text
MILESTONE-014 - Process-Local Evidence Package Aggregate Behavior
```

The next milestone may implement one process-local Evidence Package aggregate root. It must not implement Campaign, Run, Review, Audit, Decision Candidate, persistence, schemas, repositories, APIs, workers, job ledger, outbox, event dispatch, object-storage layout, trading behavior, vendor behavior, market-data behavior, campaign execution, or Decision Freeze.
