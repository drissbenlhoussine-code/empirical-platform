# MILESTONE-018 - Process-Local Campaign Aggregate Behavior Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-018 |
| Title | Process-Local Campaign Aggregate Behavior Scope Selection |
| Version | 1.0 |
| Status | SCOPE APPROVED FOR IMPLEMENTATION |
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

MILESTONE-018 selects a future implementation that includes only:

- a process-local `Campaign` aggregate root under `empirical_platform.campaign`;
- construction with `DomainIdentity[CampaignId]`;
- initial lifecycle state `CampaignLifecycleState.DRAFT`;
- exact local lifecycle transitions from M012 using the method names and semantics in Section 10;
- one Campaign-local `CampaignScopeStatement` value object, represented by a non-empty string and immutable after construction;
- scope-statement replacement only while the Campaign remains `DRAFT`;
- no owner, sponsor, reviewer, authorization, activation, completion, or Run collection fields on the aggregate;
- readiness represented only by the `READY_FOR_AUTHORIZATION` lifecycle state and its transition record;
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

## 10. Implementation-Ready Scope Decisions

The future M018 implementation is authorized to implement only the following process-local Campaign contract.

### Identity

Campaign aggregate identity:

```text
DomainIdentity[CampaignId]
```

The identity is immutable after construction. Campaign name, title, description, objective, owner, sponsor, reviewer, authorization reference, and Run relationship are not identity.

### Content Model

The only Campaign-local content selected for M018 is:

```text
CampaignScopeStatement(value: str)
```

Rules:

- `value` must be a string;
- `value.strip()` must be non-empty;
- the value object is immutable;
- it grants no authority;
- it contains no Run IDs, Dataset references, Evidence references, Review references, repository references, storage references, credentials, schedule, vendor, market-data, or trading behavior.

Construction requires one valid `CampaignScopeStatement`.

Scope mutation:

| Operation | Required state | Effect | Version | Sequence | History |
| --- | --- | --- | --- | --- | --- |
| `revise_scope_statement` | `DRAFT` | Replace scope statement with a new immutable `CampaignScopeStatement` | +1 | unchanged | unchanged |

Rejected scope mutation leaves identity, lifecycle state, version, sequence, transition history, and scope statement unchanged.

No other descriptive/contextual fields are authorized in M018.

### Readiness Model

M018 does not implement an independent readiness checklist, readiness boolean, readiness score, readiness object, or readiness calculation.

Readiness is represented only by the lifecycle transition:

```text
DRAFT -> READY_FOR_AUTHORIZATION
```

The transition records that a caller is asserting local readiness for authorization review. It does not verify governance gates, reviewer assignment, risk closure, dependencies, licenses, evidence, Runs, Datasets, Reviews, or external systems.

### Run Relationship

M018 Campaign stores no Run IDs and no Run summaries.

The future implementation must not define:

- `tuple[RunId, ...]`;
- active-run counters;
- run status summaries;
- run append/remove methods;
- run existence checks;
- run lifecycle inspection;
- DatasetManifest access.

Run relationship semantics remain cross-aggregate and deferred.

### Lifecycle Method Matrix

Allowed lifecycle operations:

| Current state | Method | Next state | Reason required | Reason semantics |
| --- | --- | --- | --- | --- |
| `DRAFT` | `prepare_for_authorization` | `READY_FOR_AUTHORIZATION` | No | Optional local readiness note only |
| `READY_FOR_AUTHORIZATION` | `record_authorization` | `AUTHORIZED` | Yes | Opaque authorization-review reference or rationale; no authorization execution |
| `AUTHORIZED` | `activate` | `ACTIVE` | Yes | Opaque activation basis supplied by caller; no Run lookup |
| `ACTIVE` | `suspend` | `SUSPENDED` | Yes | Opaque governed pause reason |
| `SUSPENDED` | `resume` | `ACTIVE` | Yes | Opaque restoration reason supplied by caller |
| `ACTIVE` | `complete` | `COMPLETED` | Yes | Opaque completion basis supplied by caller; no Run or Review query |
| `DRAFT` | `cancel` | `CANCELLED` | No | Optional abandonment note |
| `READY_FOR_AUTHORIZATION` | `cancel` | `CANCELLED` | No | Optional abandonment note |
| `AUTHORIZED` | `cancel` | `CANCELLED` | Yes | Required cancellation reason |
| `ACTIVE` | `cancel` | `CANCELLED` | Yes | Required cancellation reason |
| `SUSPENDED` | `cancel` | `CANCELLED` | Yes | Required cancellation reason |

All other state-operation pairs are rejected.

Terminal states:

```text
COMPLETED
CANCELLED
```

Terminal Campaigns reject all lifecycle and content mutation. No reopen, restart, retry, revision, archive, Decision Freeze, or supersession behavior is authorized.

### Version, Sequence, and History

Initial state:

```text
CampaignLifecycleState.DRAFT
```

Initial version:

```text
AggregateVersion.initial()
```

Initial next transition sequence:

```text
TransitionSequence.initial()
```

Accepted lifecycle transitions:

- increment `AggregateVersion` exactly once;
- record the current `TransitionSequence`;
- advance the next `TransitionSequence` exactly once;
- append exactly one `StateTransitionRecord`;
- store `reason` in the transition record when supplied or required.

Accepted scope-statement replacement:

- increments `AggregateVersion` exactly once;
- does not advance `TransitionSequence`;
- does not append transition history.

Construction, reads, and rejected operations do not increment version, advance sequence, or append history.

### Rejection Atomicity

Every rejected operation must leave unchanged:

- Campaign identity;
- lifecycle state;
- version;
- next transition sequence;
- transition history;
- scope statement.

### Package and Export Boundary

Future implementation location:

```text
src/empirical_platform/campaign/aggregate.py
src/empirical_platform/campaign/__init__.py
tests/unit/test_campaign_aggregate.py
```

Allowed imports for Campaign implementation:

- `empirical_platform.campaign.lifecycle`;
- `empirical_platform.identifiers`;
- `empirical_platform.shared.domain`;
- Python standard-library modules required for immutable values and timestamps.

The existing architecture checker already permits the selected implementation boundary. No architecture-rule change is selected unless a future independent review identifies an exact need without broadening `campaign -> run` or `campaign -> datasets`.

## 11. Local Versus Cross-Aggregate Boundary

| Rule or invariant | Classification | M018 treatment |
| --- | --- | --- |
| Campaign has immutable `CampaignId` identity | Local | Include |
| Campaign lifecycle state changes | Local with caller-supplied opaque reasons | Include only as state recording |
| Draft scope statement is replaceable before authorization | Local | Include as `CampaignScopeStatement` replacement in `DRAFT` only |
| Readiness checklist or score | Cross-aggregate/governance | Exclude; readiness is lifecycle state only |
| Owner, sponsor, reviewer, or authorization identity | Governance/application-service | Exclude; transition actor is history metadata only |
| Campaign owns all Runs | False | Exclude; Run references Campaign |
| Campaign stores Run IDs | Cross-aggregate relationship | Exclude from M018 |
| Campaign imports Run aggregate | Forbidden | Exclude |
| Campaign imports Dataset Manifest | Forbidden | Exclude |
| Campaign completion requires no active Runs | Cross-aggregate command-time | Defer enforcement; local `complete` records caller-supplied opaque completion basis only |
| Required Review dispositions complete | Cross-aggregate command-time | Defer |
| Authorization review passes | Governance gate / command-time | Defer execution; `record_authorization` records caller-supplied opaque reason only |
| Campaign activation requires at least one Run authorized or operation opened | Cross-aggregate or local operation marker | Defer enforcement; `activate` records caller-supplied opaque reason only |

## 12. Validation Expectations For Future Implementation

A future M018 implementation mission must include:

- focused Campaign aggregate unit tests;
- tests for every accepted lifecycle transition;
- tests for every rejected lifecycle transition;
- tests for cancellation from every allowed state;
- tests for `CampaignScopeStatement` validation, immutability, and DRAFT-only replacement;
- tests proving no readiness checklist, score, Run ID collection, owner authority, authorization execution, or completion query was introduced;
- tests for exact version, sequence, history, and rejection atomicity behavior;
- tests proving Campaign does not import Run, Dataset, Evidence, Review, persistence, repository, schema, API, worker, outbox, vendor, market-data, trading, Audit, Decision Candidate, or Decision Freeze behavior;
- architecture-boundary tests preserving forbidden directions;
- full `security.ps1`;
- full `verify.ps1`;
- `git diff --check`.

## 13. Deferred Items

| Deferred item | Reason |
| --- | --- |
| Campaign implementation | This is scope selection only |
| Campaign completion enforcement | Active-run and Review checks remain cross-aggregate and external to Campaign |
| Campaign authorization gate execution | Governance/application-service responsibility |
| Campaign owner and reviewer assignment records | Requires authorization/workflow scope |
| Campaign to Run orchestration | Cross-aggregate and execution behavior |
| Campaign Run ID collection | Deferred to a separate relationship/reference scope if needed |
| Run-target Review | Separate Review target-model scope |
| Repository contracts | Depends on completed aggregate boundaries |
| Schema/migration design | Depends on repository contracts |
| Projection/read models | Depends on persistence ownership |
| Audit runtime | Deferred by M012 |
| Decision Candidate runtime | Deferred by M012 |

## 14. Stop Conditions

Stop any future M018 implementation if:

- Campaign imports `run`, `datasets`, `evidence`, or `review`;
- Campaign stores Run IDs or Run summaries;
- Campaign loads or mutates another aggregate;
- Campaign completion queries active Runs or Review dispositions inside the aggregate;
- authorization review, reviewer independence, or COI checks are executed inside the aggregate;
- a readiness checklist, score, or external dependency check is implemented inside Campaign;
- persistence, repositories, schemas, migrations, APIs, workers, job ledger, or outbox appear;
- event dispatch or reconstruction behavior is introduced;
- Audit, Decision Candidate, or Decision Freeze behavior appears;
- market-data, vendor, trading, or empirical campaign execution behavior appears.

## 15. Scope Review Issue Register

| Issue ID | Severity | Finding | Correction | Disposition |
| --- | --- | --- | --- | --- |
| M018-SCOPE-REVIEW-ISSUE-0001 | MAJOR | Initial scope left Campaign-local scope/readiness data generic and not implementation-ready. | Selected a single `CampaignScopeStatement` content model and made readiness lifecycle-only. | Resolved |
| M018-SCOPE-REVIEW-ISSUE-0002 | MAJOR | Initial scope left lifecycle method names, authorization recording, activation, completion, and cancellation reason semantics to future implementation. | Added an exact lifecycle method matrix with opaque reason semantics and no authority execution. | Resolved |
| M018-SCOPE-REVIEW-ISSUE-0003 | MAJOR | Initial scope did not explicitly decide whether Campaign may hold Run IDs. | Excluded Run ID collections and Run summaries from M018. | Resolved |
| M018-SCOPE-REVIEW-ISSUE-0004 | MINOR | Initial scope did not explicitly define version, sequence, history, and content-mutation effects. | Added exact version, sequence, history, and rejection atomicity rules. | Resolved |

No CRITICAL or MAJOR scope issue remains open.

## 16. Final Decision

The selected next milestone is:

```text
MILESTONE-018 - Process-Local Campaign Aggregate Behavior
```

Final scope-selection status:

```text
SCOPE APPROVED FOR IMPLEMENTATION
```

This document does not implement Campaign behavior. It defines the exact next local aggregate boundary for independent review and a later implementation mission.
