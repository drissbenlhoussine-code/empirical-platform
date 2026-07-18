# MILESTONE-018 - Process-Local Campaign Aggregate Behavior Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-018 |
| Title | Process-Local Campaign Aggregate Behavior Scope Selection |
| Version | 1.0 |
| Status | SCOPE CANDIDATE SELECTED |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Baseline | `f09ade88e687c0198473ce1cda35ad01707f7f5c` |
| Baseline meaning | MILESTONE-017 approved and frozen |
| Mission type | Repository analysis and scope discovery only |
| Implementation performed | None |
| Source modified | No |
| Schemas or migrations created | No |
| Repository contracts created | No |
| APIs or workers created | No |

## 2. Baseline Verification

Required baseline:

```text
f09ade88e687c0198473ce1cda35ad01707f7f5c
```

Observed before this document:

| Check | Result |
| --- | --- |
| Branch | `master` |
| HEAD | `f09ade88e687c0198473ce1cda35ad01707f7f5c` |
| Working tree | Clean |

## 3. Repository Evidence Reviewed

| Evidence ID | Repository evidence | MILESTONE-018 relevance |
| --- | --- | --- |
| M018-EVID-0001 | `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` | Defines Campaign as an initial aggregate root, Campaign lifecycle, ownership boundaries, cross-aggregate invariants, and persistence deferrals |
| M018-EVID-0002 | `MILESTONE_013_PROCESS_LOCAL_DOMAIN_PRIMITIVE_FOUNDATION.md` | Implements `CampaignLifecycleState`, `CampaignId`, identity pairing, versioning, and transition-history primitives |
| M018-EVID-0003 | `MILESTONE_014_PROCESS_LOCAL_EVIDENCE_PACKAGE_AGGREGATE_BEHAVIOR.md` | Freezes Evidence Package behavior and leaves Campaign deferred |
| M018-EVID-0004 | `MILESTONE_015_PROCESS_LOCAL_REVIEW_AGGREGATE_BEHAVIOR.md` | Freezes Evidence-Package-target Review behavior and leaves Campaign deferred |
| M018-EVID-0005 | `MILESTONE_016_RUN_AGGREGATE_BOUNDARY_RECONCILIATION_DECISION.md` | Resolves Run/Campaign/Dataset direction, forbids Campaign importing Run or Dataset |
| M018-EVID-0006 | `MILESTONE_017_PROCESS_LOCAL_RUN_AGGREGATE_BEHAVIOR.md` | Freezes Run behavior and lists Campaign aggregate behavior as deferred |
| M018-EVID-0007 | `src/empirical_platform/campaign/lifecycle.py` | Defines canonical `CampaignLifecycleState` values; no Campaign aggregate exists |
| M018-EVID-0008 | `tools/check_architecture.py` | Allows `campaign -> shared, identifiers, governance, registry`; forbids `campaign -> run` and `campaign -> datasets` |
| M018-EVID-0009 | repository TODO/FIXME scan | No TODO/FIXME marker justifies a cleanup milestone ahead of Campaign |

## 4. Current Domain Inventory

| Domain capability | Implemented | Frozen | Process-local | Cross-aggregate | Persistence-ready | Remaining work |
| --- | --- | --- | --- | --- | --- | --- |
| Governance/runtime identifiers | Yes | Yes | Yes | No | Value-object ready only | No allocation registry runtime |
| Lifecycle enums | Yes | Yes | Yes | No | Value-object ready only | Campaign enum exists without Campaign aggregate |
| `AggregateVersion` | Yes | Yes | Yes | No | Value-object ready only | No stale-version command layer |
| `TransitionSequence` | Yes | Yes | Yes | No | Value-object ready only | No reconstruction logic |
| `StateTransitionRecord` | Yes | Yes | Yes | No | Value-object ready only | Not an event/outbox record |
| `DatasetManifest` | Yes | Yes | Yes, owned by Run conceptually | No | No schema defined | Rich supersession reference deferred |
| `CriterionResult` | Yes | Yes | Yes, owned by Evidence Package | No | No schema defined | Scoring engine deferred |
| Evidence Package aggregate | Yes | Yes | Yes | References Run by ID | No schema/repository | Persistence and object layout deferred |
| Review aggregate | Yes | Yes | Yes | References Evidence Package by ID | No schema/repository | Run-target Review and independence gate deferred |
| Run aggregate | Yes | Yes | Yes | References Campaign by ID | No schema/repository | Campaign authorization check, scope snapshot, rerun link deferred |
| Campaign aggregate | No | Designed in M012 | Candidate | References Runs/Reviews by ID only | No schema/repository | Selected as M018 scope candidate |
| Audit runtime | No | Deferred | No | Yes | No | Requires process-compliance authority design |
| Decision Candidate runtime | No | Deferred | No | Yes | No | Requires Review/Audit sufficiency governance |
| Repository contracts | No | Deferred | No | Cross-layer | Not ready | Needs aggregate boundary set completed |
| Domain schemas/migrations | No | Deferred | No | Cross-layer | Not ready | Needs repository contracts first |
| Projection/read model | No | Deferred | No | Yes | Not ready | Needs persistence contracts and query ownership |

## 5. Remaining Candidate Milestones

| Candidate | Purpose | Dependencies | Prerequisites | Scope size | Architectural risk | Implementation risk | Coupling risk | Repository evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Process-local Campaign aggregate behavior | Implement remaining initial aggregate root locally | M012, M013, M017 | Must avoid importing Run/Dataset and defer cross-aggregate completion checks | Medium | Medium | Medium | Medium | M012 defines Campaign root; M017 leaves Campaign deferred; architecture forbids `campaign -> run` |
| Campaign boundary reconciliation | Resolve Campaign-local versus cross-aggregate summary ownership before implementation | M012-M017 | Needed only if local Campaign scope cannot be narrowed directly | Small | Low | Low | Low | M012 already provides enough local/cross-aggregate separation |
| Run-target Review scope | Extend Review target model to Run IDs | M015, M017 | Needs decision on mixed target reference model and reviewability checks | Medium | Medium | Medium | Medium | M015 explicitly deferred Run-target Review until Run exists |
| Repository contract scope | Define aggregate repository interfaces | M012-M017, future Campaign | Campaign aggregate absent | Large | High | Medium | High | M012 defers repository APIs; initial aggregate set not complete |
| Domain schema/migration scope | Define persistence schema for aggregates | repository contracts | Repositories absent | Large | High | High | High | `migrations/versions` intentionally empty |
| Aggregate reconstruction scope | Rehydrate aggregate state from records | persistence model | No schemas/repositories/events | Large | High | High | High | Transition history is explicitly not reconstruction/event source |
| Audit runtime scope | Define/implement process-compliance audit | Evidence, Review, governance authority | Campaign and repository layers absent | Large | High | Medium | High | M012 defers Audit pending authority reconciliation |
| Decision Candidate scope | Define decision-support runtime artifact | Review, Audit, sufficiency gates | Audit absent | Large | High | Medium | High | M012 explicitly defers Decision Candidate |
| Projection/read model scope | Define derived query state | schemas/repositories | No persistence model | Medium | High | Medium | High | M012 allows summaries but no read-model ownership exists |

## 6. Dependency Graph

```text
M012 Runtime Domain Kernel Design
        |
M013 Domain Primitives
        |
        +--> M014 Evidence Package aggregate
        |
        +--> M015 Review aggregate
        |
        +--> M016 Run boundary reconciliation
                  |
                  +--> M017 Run aggregate
                            |
                            +--> M018 Campaign aggregate scope
                                      |
                                      +--> Repository contracts
                                      +--> Domain schema/migrations
                                      +--> Application services / cross-aggregate command checks
                                      +--> Run-target Review
                                      +--> Audit runtime
                                      +--> Decision Candidate runtime
```

Unlock analysis:

| Question | Result |
| --- | --- |
| Unlocks largest number of future milestones | Campaign aggregate behavior, because it completes the initial aggregate-root set |
| Smallest bounded scope | Campaign boundary reconciliation, but current evidence does not show a blocker requiring a separate reconciliation milestone |
| Removes highest architectural uncertainty | Campaign aggregate behavior, if scoped to local lifecycle/scope state and explicit cross-aggregate deferrals |

## 7. Candidate Comparison

| Criterion | Campaign aggregate | Campaign boundary reconciliation | Run-target Review | Repository contracts | Schema/migration | Audit | Decision Candidate | Projection model |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Architectural ordering | 9 | 7 | 7 | 5 | 3 | 4 | 2 | 4 |
| Dependency readiness | 8 | 9 | 7 | 4 | 2 | 4 | 2 | 3 |
| Isolation | 7 | 10 | 6 | 5 | 3 | 4 | 4 | 5 |
| Independent testability | 8 | 9 | 7 | 6 | 5 | 5 | 5 | 5 |
| Reversibility | 7 | 9 | 7 | 5 | 3 | 4 | 4 | 5 |
| Future maintainability | 9 | 7 | 7 | 8 | 6 | 7 | 6 | 7 |
| Implementation confidence | 8 | 9 | 6 | 4 | 3 | 4 | 3 | 4 |
| Scope-creep risk, lower is better | 5 | 2 | 6 | 7 | 8 | 8 | 8 | 7 |

Rejected candidates:

- Campaign boundary reconciliation is too small and redundant unless Campaign implementation scope cannot be made local.
- Run-target Review is now possible but less foundational than completing Campaign, and it risks broadening the Review target model before Campaign ownership is represented.
- Repository contracts and schema/migration work remain premature until all initial aggregate-root boundaries are implemented.
- Aggregate reconstruction is premature because transition history is not an event source and no persistence representation exists.
- Audit and Decision Candidate remain explicitly deferred and depend on review, audit authority, sufficiency, and governance gates.
- Projection/read model work is premature without repository and schema ownership decisions.

## 8. Selected Next Milestone

Selected scope:

```text
MILESTONE-018 - Process-Local Campaign Aggregate Behavior
```

One-sentence purpose:

```text
Define the bounded process-local Campaign aggregate behavior needed to manage campaign lifecycle, immutable identity, local scope/readiness data, and transition history without importing Run, Dataset, Evidence, Review, Audit, Decision Candidate, persistence, or execution behavior.
```

Architectural layer:

```text
Domain aggregate behavior / process-local only
```

## 9. Scope Boundary

MILESTONE-018 may select a future implementation that includes only:

- a process-local `Campaign` aggregate root under `empirical_platform.campaign`;
- construction with `DomainIdentity[CampaignId]`;
- initial lifecycle state `CampaignLifecycleState.DRAFT`;
- local lifecycle transitions from M012;
- Campaign-local draft scope data represented by bounded immutable value objects or opaque text/reference values;
- readiness markers needed to move from `DRAFT` to `READY_FOR_AUTHORIZATION` only if they are local facts, not governance gate outcomes;
- aggregate version advancement;
- transition sequence advancement;
- immutable transition-history records;
- cancellation reason capture where M012 requires reason;
- rejection atomicity for invalid commands;
- focused unit tests;
- architecture-boundary tests preserving `campaign -> run` and `campaign -> datasets` prohibitions;
- implementation reporting for a later M018 implementation mission.

MILESTONE-018 must not include:

- importing `empirical_platform.run`, `empirical_platform.datasets`, `empirical_platform.evidence`, or `empirical_platform.review` into Campaign;
- Run creation or Run state inspection;
- active-run counting;
- Campaign completion based on loaded Runs or Reviews;
- authorization-gate execution;
- reviewer assignment;
- reviewer independence or COI validation;
- evidence sufficiency checks;
- Audit runtime;
- Decision Candidate runtime;
- Decision Freeze;
- persistence;
- repositories;
- schemas;
- migrations;
- APIs;
- workers;
- job ledger;
- outbox;
- event dispatch;
- campaign execution;
- market-data behavior;
- vendor behavior;
- trading logic.

## 10. Required Scope Answers For Future Implementation

A future M018 implementation scope must answer before code:

1. Campaign aggregate identity.
2. Initial lifecycle state.
3. Exact lifecycle transition method names.
4. Whether `DRAFT -> READY_FOR_AUTHORIZATION` is local readiness marking or external authorization readiness.
5. Whether `READY_FOR_AUTHORIZATION -> AUTHORIZED` is allowed as local state recording without executing authorization.
6. How `AUTHORIZED -> ACTIVE` avoids Run lookup while preserving M012 preconditions as caller responsibility.
7. How `ACTIVE -> COMPLETED` is represented without active-run or review queries, or whether completion is deferred.
8. Cancellation reason requirements by state.
9. Campaign-local scope data representation.
10. Versioning rules.
11. Transition sequence rules.
12. Transition history rules.
13. Rejection atomicity snapshot.
14. Package/export boundaries.
15. Architecture-checker changes, if any.
16. Explicit non-goals.

## 11. Local Versus Cross-Aggregate Boundary

| Rule or invariant | Classification | M018 treatment |
| --- | --- | --- |
| Campaign has immutable `CampaignId` identity | Local | Include |
| Campaign lifecycle state changes | Local with caller-supplied authority facts | Include only as state recording |
| Draft scope text/reference is mutable before authorization | Local | Include if bounded and immutable after transition |
| Campaign owns all Runs | False | Exclude; Run references Campaign |
| Campaign imports Run aggregate | Forbidden | Exclude |
| Campaign imports Dataset Manifest | Forbidden | Exclude |
| Campaign completion requires no active Runs | Cross-aggregate command-time | Defer or require caller-supplied summary without query behavior |
| Required Review dispositions complete | Cross-aggregate command-time | Defer |
| Authorization review passes | Governance gate / command-time | Defer execution; local state recording only if caller supplies authorization fact |
| Campaign activation requires at least one Run authorized or operation opened | Cross-aggregate or local operation marker | Must be explicitly narrowed before implementation |

## 12. Validation Expectations For Future Implementation

A future M018 implementation mission must include:

- focused Campaign aggregate unit tests;
- tests for every accepted lifecycle transition;
- tests for every rejected lifecycle transition;
- tests for cancellation from every allowed state;
- tests proving Campaign does not import Run, Dataset, Evidence, Review, persistence, repository, schema, API, worker, outbox, vendor, market-data, trading, Audit, Decision Candidate, or Decision Freeze behavior;
- architecture-boundary tests preserving forbidden directions;
- full `security.ps1`;
- full `verify.ps1`;
- `git diff --check`.

## 13. Deferred Items

| Deferred item | Reason |
| --- | --- |
| Campaign implementation | This is scope selection only |
| Campaign completion command details | Requires active-run/review summary boundary to be explicitly narrowed |
| Campaign authorization gate execution | Governance/application-service responsibility |
| Campaign owner and reviewer assignment records | Requires authorization/workflow scope |
| Campaign to Run orchestration | Cross-aggregate and execution behavior |
| Run-target Review | Separate Review target-model scope |
| Repository contracts | Depends on completed aggregate boundaries |
| Schema/migration design | Depends on repository contracts |
| Projection/read models | Depends on persistence ownership |
| Audit runtime | Deferred by M012 |
| Decision Candidate runtime | Deferred by M012 |

## 14. Stop Conditions

Stop any future M018 implementation if:

- Campaign imports `run`, `datasets`, `evidence`, or `review`;
- Campaign loads or mutates another aggregate;
- Campaign completion queries active Runs or Review dispositions inside the aggregate;
- authorization review, reviewer independence, or COI checks are executed inside the aggregate;
- persistence, repositories, schemas, migrations, APIs, workers, job ledger, or outbox appear;
- event dispatch or reconstruction behavior is introduced;
- Audit, Decision Candidate, or Decision Freeze behavior appears;
- market-data, vendor, trading, or empirical campaign execution behavior appears.

## 15. Final Decision

The selected next milestone is:

```text
MILESTONE-018 - Process-Local Campaign Aggregate Behavior
```

Final scope-selection status:

```text
SCOPE CANDIDATE SELECTED
```

This document does not implement Campaign behavior. It defines the exact next local aggregate boundary for independent review and a later implementation mission.
