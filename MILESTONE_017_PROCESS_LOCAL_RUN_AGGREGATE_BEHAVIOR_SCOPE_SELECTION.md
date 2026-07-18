# MILESTONE-017 - Process-Local Run Aggregate Behavior Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-017 |
| Title | Process-Local Run Aggregate Behavior Scope Selection |
| Version | 1.0 |
| Status | SCOPE CANDIDATE SELECTED |
| Baseline | `17e4a43fe97ca3fa23b5c9aedc54f65a7b7d0d52` |
| Baseline meaning | MILESTONE-016 approved and frozen |
| Mission type | Scope selection only |
| Implementation performed | None |
| Source modified | No |
| Run package created | No |
| Architecture rules modified | No |
| Schemas or migrations created | No |

## 2. Baseline Verification

Required baseline:

```text
17e4a43fe97ca3fa23b5c9aedc54f65a7b7d0d52
```

Observed before this document:

| Check | Result |
| --- | --- |
| Branch | `master` |
| HEAD | `17e4a43fe97ca3fa23b5c9aedc54f65a7b7d0d52` |
| Working tree | Clean |

## 3. Repository Evidence Reviewed

| Evidence ID | Repository evidence | Relevance |
| --- | --- | --- |
| M017-EVID-0001 | `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` | Defines Run as aggregate root, Run lifecycle, Run-owned Dataset Manifest records, local invariants, and deferred persistence/schema boundaries |
| M017-EVID-0002 | `MILESTONE_013_PROCESS_LOCAL_DOMAIN_PRIMITIVE_FOUNDATION.md` | Implements `RunLifecycleState`, `DatasetManifest`, `DomainIdentity`, `AggregateVersion`, `TransitionSequence`, and `StateTransitionRecord` |
| M017-EVID-0003 | `MILESTONE_014_PROCESS_LOCAL_EVIDENCE_PACKAGE_AGGREGATE_BEHAVIOR.md` | Freezes Evidence Package behavior and its immutable parent `RunId` context |
| M017-EVID-0004 | `MILESTONE_015_PROCESS_LOCAL_REVIEW_AGGREGATE_BEHAVIOR.md` | Freezes Evidence-Package-target Review behavior and keeps Run-target Review deferred |
| M017-EVID-0005 | `MILESTONE_016_RUN_AGGREGATE_BOUNDARY_RECONCILIATION_DECISION.md` | Freezes future Run package location, DatasetManifest placement, and Campaign dependency limits |
| M017-EVID-0006 | `src/empirical_platform/datasets/manifest.py` | Defines immutable `DatasetManifest` with `RunId`, optional `DatasetId`, source, acquisition method, normalization method, and notes |
| M017-EVID-0007 | `src/empirical_platform/campaign/lifecycle.py` | Defines current `RunLifecycleState` values matching M012 |
| M017-EVID-0008 | `src/empirical_platform/identifiers` | Defines `RunId`, `CampaignId`, and governance/runtime identity pairing |
| M017-EVID-0009 | `src/empirical_platform/shared/domain` | Defines aggregate versioning and transition-history primitives |
| M017-EVID-0010 | `tools/check_architecture.py` | Current architecture checker has no `run` package rule yet |

## 4. Scope Selection Rationale

MILESTONE-016 resolved the package boundary that previously blocked Run work. The next bounded scope can now select Process-Local Run Aggregate Behavior because:

- Run is a frozen aggregate root in MILESTONE-012;
- Run lifecycle states already exist;
- Run identity and Campaign contextual identity already exist;
- Dataset Manifest is already immutable and conceptually Run-owned;
- Evidence Package and Review are already frozen and do not require Run internals;
- persistence, repositories, schemas, APIs, workers, Audit, Decision Candidate, and Campaign behavior remain explicitly deferred.

This scope does not authorize implementation. It only defines the exact behavior a later MILESTONE-017 implementation mission may build after independent review.

## 5. Selected Scope

Selected scope:

```text
MILESTONE-017 - Process-Local Run Aggregate Behavior
```

One-sentence purpose:

```text
Define the bounded process-local Run aggregate behavior needed to manage one execution attempt, its lifecycle, immutable Campaign context, and Run-owned Dataset Manifest records without persistence or cross-aggregate orchestration.
```

Architectural layer:

```text
Domain aggregate behavior / process-local only
```

## 6. Scope Boundary

MILESTONE-017 may select a future implementation that includes only:

- a future `empirical_platform.run` package;
- a process-local `Run` aggregate root;
- Run construction with `DomainIdentity[RunId]` and immutable parent `CampaignId`;
- initial Run lifecycle state;
- allowed Run lifecycle transitions from M012;
- terminal behavior for completed, failed, and cancelled Runs;
- aggregate version advancement;
- transition sequence advancement;
- immutable transition-history records;
- append-only Dataset Manifest ownership;
- Dataset Manifest supersession as creation of a new immutable record;
- rejection atomicity for invalid commands;
- focused unit tests;
- architecture-boundary tests for the new `run` package;
- documentation/reporting for M017 implementation evidence.

## 7. Required Scope Answers

| Question | Scope answer |
| --- | --- |
| 1. Run aggregate identity | Future Run aggregate uses `DomainIdentity[RunId]`; identity is immutable after construction. |
| 2. Campaign contextual identity | Future Run aggregate stores immutable parent `CampaignId`; it does not load or mutate Campaign. |
| 3. DatasetManifest relationship | Future Run aggregate owns a bounded collection of immutable `DatasetManifest` records. |
| 4. Initial lifecycle state | `RunLifecycleState.CREATED`. |
| 5. Allowed lifecycle transitions | `CREATED -> AUTHORIZED`; `AUTHORIZED -> ACQUIRING`; `ACQUIRING -> NORMALIZING`; `NORMALIZING -> VALIDATING`; `VALIDATING -> EXECUTION_COMPLETED`; `AUTHORIZED -> CANCELLED`; `ACQUIRING -> FAILED`; `NORMALIZING -> FAILED`; `VALIDATING -> FAILED`. |
| 6. Terminal states | `EXECUTION_COMPLETED`, `FAILED`, and `CANCELLED`. |
| 7. Aggregate-local invariants | identity immutable; Campaign context immutable; lifecycle transition legality; Dataset Manifest records match Run ID; Dataset Manifest records immutable; rerun overwrites prohibited; terminal states immutable. |
| 8. Versioning rules | Construction starts at `AggregateVersion.initial()`; every accepted lifecycle transition or manifest append/supersession advances version exactly once. |
| 9. Transition sequence rules | Construction starts at `TransitionSequence.initial()`; accepted lifecycle transitions consume current sequence and advance to next sequence. Manifest content changes do not create lifecycle transition records unless explicitly modeled as lifecycle transitions. |
| 10. Transition history rules | Accepted lifecycle transitions append immutable `StateTransitionRecord`; rejected commands append nothing. |
| 11. DatasetManifest ownership semantics | Dataset Manifest is Run-owned domain data, physically defined and exported by `empirical_platform.datasets`. |
| 12. One or multiple manifests | Multiple manifests are allowed as a bounded tuple ordered by append sequence; future persistence/read-model paging remains deferred. |
| 13. Manifest replacement/supersession rules | Replacement is modeled as appending a new immutable `DatasetManifest`; destructive mutation is prohibited. |
| 14. Content mutation rules | Run identity, Campaign context, transition history entries, and existing Dataset Manifest records are never mutated in place. |
| 15. Rejection atomicity | Invalid transition, wrong manifest Run ID, duplicate manifest identity where present, invalid actor/timestamp/reason, and terminal mutation attempts leave observable aggregate state unchanged. |
| 16. Local vs cross-aggregate invariants | Local invariants are enforced in Run; Campaign authorization, entitlement/license validity, Evidence Package seal, Review dispositions, Audit, and Decision Candidate sufficiency remain external/deferred. |
| 17. Package location | Future implementation belongs under `src/empirical_platform/run/`. |
| 18. Import direction | Future `run` may import `datasets`, `identifiers`, `shared`, and the chosen Run lifecycle source; `campaign -> datasets` remains forbidden. |
| 19. RunLifecycleState placement/import strategy | M017 implementation must decide before code whether to import `RunLifecycleState` from `campaign`, re-export it from `run`, or relocate it through reviewed change. This scope permits the decision but performs no move. |
| 20. Explicit non-goals | Persistence, repositories, schemas, migrations, APIs, workers, runtime orchestration, Campaign implementation, Audit, Decision Candidate, Decision Freeze, trading, market data, Evidence Package behavior, Review behavior. |

## 8. Candidate Implementation Boundary

The future implementation may define a `Run` aggregate with behavior analogous in style to the existing Evidence Package and Review aggregates:

- explicit constructor validation;
- read-only properties for identity, Campaign ID, state, version, next transition sequence, transition history, and manifests;
- named transition methods only;
- no arbitrary transition method;
- no external service calls;
- no persistence dependencies;
- no object-storage dependencies;
- no event dispatch.

Exact method names are left to the implementation mission, but behavior must remain limited to the selected local boundary.

## 9. Lifecycle Scope

The future Run aggregate may select named methods for the M012 transitions:

| From | To | Scope classification |
| --- | --- | --- |
| `CREATED` | `AUTHORIZED` | Local transition using recorded Campaign context only; no Campaign lookup |
| `AUTHORIZED` | `ACQUIRING` | Local lifecycle marker only; no acquisition behavior |
| `ACQUIRING` | `NORMALIZING` | Local lifecycle marker only; no normalization behavior |
| `NORMALIZING` | `VALIDATING` | Local lifecycle marker only; no validation behavior |
| `VALIDATING` | `EXECUTION_COMPLETED` | Local lifecycle marker only; no Evidence Package validation or seal check |
| `AUTHORIZED` | `CANCELLED` | Local terminal transition |
| `ACQUIRING` | `FAILED` | Local terminal transition with reason |
| `NORMALIZING` | `FAILED` | Local terminal transition with reason |
| `VALIDATING` | `FAILED` | Local terminal transition with reason |

Execution-stage names must not introduce acquisition, normalization, validation, vendor, market-data, or campaign-execution behavior.

## 10. Dataset Manifest Scope

Future Run behavior may:

- accept a `DatasetManifest` whose `run_id` equals the Run aggregate `RunId`;
- append the manifest to an immutable manifest collection;
- reject a manifest for another Run;
- reject duplicate `DatasetId` values when both existing and incoming manifests define one;
- treat supersession as appending a new immutable manifest;
- expose manifests through immutable tuple views.

Future Run behavior must not:

- edit an existing manifest;
- infer object-storage layout;
- assign retention policy;
- create a persistence schema;
- load all historical manifests from storage;
- validate vendor data content.

## 11. Local and Cross-Aggregate Boundary

| Invariant or rule | Classification | M017 treatment |
| --- | --- | --- |
| Run has one immutable `RunId` identity | Local | Included |
| Run belongs to one immutable `CampaignId` context | Local reference | Included without Campaign lookup |
| Parent Campaign is authorized or active | Cross-aggregate | Deferred; caller/application service responsibility |
| Authorized scope snapshot exists | Cross-aggregate or future value object | Deferred unless represented only as opaque local text/reference |
| Dataset Manifest belongs to this Run | Local | Included |
| Dataset Manifest immutable after append | Local | Included |
| Rerun creates new Run identity | Local prohibition against overwrite | Include as no restart/reopen behavior; rerun link record deferred |
| Evidence Package references Run | Cross-aggregate | Deferred; existing Evidence Package remains unchanged |
| Review disposition qualifies Run | Cross-aggregate | Deferred |
| Campaign completion requires no active Runs | Cross-aggregate | Deferred |

## 12. Package and Architecture Scope

The future implementation must create or update only M017-authorized domain files and tests.

Potential future file locations:

```text
src/empirical_platform/run/
tests/unit/test_run_aggregate.py
tests/architecture/
```

Required future architecture-checker decision:

- add `run` as a top-level domain package;
- allow `run -> datasets`;
- allow `run -> identifiers`;
- allow `run -> shared`;
- handle `RunLifecycleState` source explicitly;
- keep `campaign -> datasets` forbidden;
- keep `datasets -> run` forbidden;
- keep `run -> evidence` and `run -> review` forbidden for the initial Run aggregate.

This scope-selection mission does not modify the checker.

## 13. Explicit Non-Goals

MILESTONE-017 must not implement or select:

- persistence;
- repositories;
- schemas;
- migrations;
- APIs;
- workers;
- runtime orchestration;
- Campaign aggregate behavior;
- Campaign authorization behavior;
- Evidence Package behavior changes;
- Review behavior changes;
- Audit;
- Decision Candidate;
- Decision Freeze;
- job ledger;
- outbox;
- event dispatch;
- object-storage layout;
- data acquisition;
- normalization logic;
- validation logic;
- market-data behavior;
- vendor behavior;
- trading logic.

## 14. Validation Expectations for Future Implementation

A future implementation mission must include:

- focused unit tests for construction, transitions, terminal behavior, versioning, transition sequence, transition history, manifest append, manifest supersession, and rejection atomicity;
- architecture-boundary tests covering allowed and forbidden `run` imports;
- tests proving no Campaign, Evidence Package, Review, persistence, repository, schema, API, worker, outbox, vendor, market-data, or trading behavior was introduced;
- full `security.ps1`;
- full `verify.ps1`;
- `git diff --check`.

## 15. Deferred Items

| Deferred item | Reason |
| --- | --- |
| Run implementation | This is scope selection only |
| `empirical_platform.run` package creation | Deferred to implementation mission |
| Run architecture-checker rules | Deferred to implementation mission with negative fixtures |
| `RunLifecycleState` import/re-export/relocation choice | Must be resolved before code in implementation mission |
| Authorized scope snapshot value object | Requires separate scope if not represented as opaque local reference |
| Rerun link record behavior | M012 preserves concept, but implementation details are not required for first Run aggregate behavior |
| Campaign aggregate behavior | Coordination-heavy and downstream of Run |
| Run-target Review behavior | Deferred by M015 |
| Evidence Package changes | Already frozen by M014 |
| Persistence/repository/schema | Explicitly deferred by M012 and M016 |
| Audit and Decision Candidate | Explicitly deferred |

## 16. Stop Conditions

Stop any future M017 implementation if:

- Run code is implemented outside `empirical_platform.run` without superseding M016;
- `DatasetManifest` is moved;
- `campaign -> datasets` is introduced;
- `datasets -> run` is introduced;
- Run behavior imports Evidence Package or Review internals;
- lifecycle placement remains unresolved at the point code would be written;
- execution-stage names introduce actual acquisition, normalization, validation, vendor, or market-data behavior;
- persistence, schemas, repositories, APIs, workers, job ledger, or outbox appear.

## 17. Final Decision

The selected next implementation scope is:

```text
MILESTONE-017 - Process-Local Run Aggregate Behavior
```

Final scope-selection status:

```text
SCOPE CANDIDATE SELECTED
```

This document does not implement Run behavior. It defines the exact local aggregate boundary for independent review and a later implementation mission.
