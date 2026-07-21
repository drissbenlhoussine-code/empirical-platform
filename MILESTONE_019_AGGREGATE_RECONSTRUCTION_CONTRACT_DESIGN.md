# MILESTONE-019 - Aggregate Reconstruction Contract Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-019 |
| Title | Aggregate Reconstruction Contract Design |
| Version | 1.0 |
| Status | DESIGN READY FOR INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Design baseline | `4d0deed0e5b9a844e3c14400aec84ba85385fc63` |
| Scope authority | `MILESTONE_019_AGGREGATE_RECONSTRUCTION_CONTRACT_SCOPE_SELECTION.md` |
| Mission type | Design only |
| Implementation performed | No |
| Source modified | No |
| State-record source created | No |
| Repository, schema, migration, API, or worker created | No |

## 2. Baseline and Authority

This design is governed by the hardened M019 scope-selection baseline:

```text
4d0deed0e5b9a844e3c14400aec84ba85385fc63
```

Authoritative frozen inputs:

| Input | Authority |
| --- | --- |
| `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` | Canonical runtime aggregate model and persistence boundary |
| `MILESTONE_013_PROCESS_LOCAL_DOMAIN_PRIMITIVE_FOUNDATION.md` | Identity, lifecycle, version, transition, Dataset Manifest, and Criterion Result primitives |
| `MILESTONE_014_PROCESS_LOCAL_EVIDENCE_PACKAGE_AGGREGATE_BEHAVIOR.md` | Frozen Evidence Package aggregate behavior |
| `MILESTONE_015_PROCESS_LOCAL_REVIEW_AGGREGATE_BEHAVIOR.md` | Frozen Review aggregate behavior |
| `MILESTONE_016_RUN_AGGREGATE_BOUNDARY_RECONCILIATION_DECISION.md` | Run package and Dataset Manifest boundary |
| `MILESTONE_017_PROCESS_LOCAL_RUN_AGGREGATE_BEHAVIOR.md` | Frozen Run aggregate behavior |
| `MILESTONE_018_PROCESS_LOCAL_CAMPAIGN_AGGREGATE_BEHAVIOR.md` | Frozen Campaign aggregate behavior |
| `tools/check_architecture.py` | Current source package dependency boundary |

This document does not supersede M012-M018. It defines only the reconstruction contract that a future implementation may use to restore existing aggregate state.

## 3. Problem Statement

The frozen aggregates currently support creation and process-local mutation, but not restoration from durable metadata. Public constructors create only initial aggregate state:

- Campaign: `DRAFT`, version `0`, next transition sequence `1`, empty history.
- Run: `CREATED`, version `0`, next transition sequence `1`, empty history, empty manifests.
- EvidencePackage: `INITIALIZED`, version `0`, next transition sequence `1`, empty history, empty results, empty artifact references.
- Review: `ASSIGNED`, version `0`, next transition sequence `1`, empty history, empty findings, unset terminal metadata.

Restoring persisted state by replaying public methods is unsafe because replay would increment versions, consume transition sequences, append new transition records, require historical command inputs, and fail against terminal-state guards. Persistence adapters mutating private fields directly would also be unsafe because it would leak infrastructure authority into domain internals.

M019 therefore defines a persistence-neutral reconstruction contract.

## 4. Frozen Aggregate Inventory

| Aggregate | Current state fields | Owned values and collections | Terminal metadata |
| --- | --- | --- | --- |
| Campaign | `DomainIdentity[CampaignId]`, `CampaignScopeStatement`, `CampaignLifecycleState`, `AggregateVersion`, next `TransitionSequence`, transition history | Current scope statement only | Reasons are carried only in transition history |
| Run | `DomainIdentity[RunId]`, `CampaignId`, `RunLifecycleState`, `AggregateVersion`, next `TransitionSequence`, transition history | Ordered `DatasetManifest` tuple; `current_manifest` is derived from the last item | Failure/cancellation reasons are carried only in transition history |
| EvidencePackage | `DomainIdentity[EvidencePackageId]`, `RunId`, `EvidencePackageLifecycleState`, `AggregateVersion`, next `TransitionSequence`, transition history | Ordered `CriterionResult` tuple; ordered `ArtifactReference` tuple | Invalidation reason is carried only in transition history |
| Review | `DomainIdentity[ReviewId]`, `ReviewTargetReference`, `ReviewerReference`, `ReviewLifecycleState`, `AggregateVersion`, next `TransitionSequence`, transition history | Ordered `ReviewFinding` tuple | `disposition`, final rationale, and cancellation reason are stored as current fields |

No aggregate currently exposes `save`, `load`, repository, mapper, serializer, reconstruction, or state-record APIs.

## 5. Design Principles

1. Reconstruction restores existing historical aggregate state; it never creates new business history.
2. Creation and reconstruction are separate paths.
3. Reconstruction must be trusted, narrow, and visibly non-ordinary.
4. Aggregate modules may not import persistence, SQL, ORM, storage, repository, mapper, runtime composition, or infrastructure adapter types.
5. Public lifecycle/content methods must not be used to rebuild aggregate state.
6. Reconstruction must not increment `AggregateVersion`.
7. Reconstruction must not advance `TransitionSequence`.
8. Reconstruction must not append `StateTransitionRecord`.
9. Reconstruction must not emit domain events, audit events, outbox records, logs, or external calls.
10. Malformed state is rejected atomically; no partially reconstructed aggregate escapes.

## 6. Options Evaluated

| Option | Encapsulation | Authority control | Type safety | Domain purity | Testability | Risk | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A. Aggregate-specific class method | Medium | Medium | High | High if inputs are neutral | High | Could become normal public creation path | Rejected |
| B. Aggregate-specific internal reconstructor/factory | High | High | High | High | High | Requires one small internal module per aggregate later | Selected |
| C. Shared generic reconstruction protocol | Medium | Medium | Medium | Medium | Medium | Overgeneralizes four non-identical aggregates | Rejected |
| D. Persistence adapter private-field mutation | Low | Low | Low | Low | Low | Leaks infrastructure and bypasses domain validation | Rejected |
| E. Immutable state snapshot passed to aggregate constructor | Medium | Medium | High | Medium | High | Pollutes creation constructor with restoration semantics | Rejected |

## 7. Selected Reconstruction Architecture

Selected architecture:

```text
Aggregate-specific internal reconstructor/factory
```

Future implementation may introduce package-internal reconstructors, conceptually:

- Campaign internal reconstructor;
- Run internal reconstructor;
- EvidencePackage internal reconstructor;
- Review internal reconstructor.

The reconstructors are trusted domain-side construction helpers. They receive persistence-neutral state data, validate it, allocate a fully restored aggregate, set its internal state atomically, and return the aggregate without invoking public behavior methods.

The design does not require a shared generic reconstruction protocol. Each aggregate has distinct owned state and terminal metadata, so generic reconstruction would add abstraction before evidence supports it.

## 8. Authority Model

Allowed future callers:

| Caller | May invoke reconstruction? | Notes |
| --- | --- | --- |
| Future domain repository or mapper layer | Yes, through the internal reconstructor boundary | Repository/mapper contract is deferred; adapters do not call aggregates directly |
| Persistence adapter such as PostgreSQL service | No | Adapter remains infrastructure connectivity and must not know aggregate internals |
| Ordinary application service | No | Application services use repositories or command handlers later |
| Aggregate public constructor caller | No | Constructors remain creation-oriented |
| Domain unit tests | Yes, only in reconstruction implementation tests | Tests may exercise malformed and valid states |
| Cross-aggregate services | No | Cross-aggregate checks remain deferred |

Authority is structural and conventional:

- structural: future reconstructors should live in aggregate-owned domain packages and expose an underscore-prefixed internal surface or equivalent package-internal convention;
- conventional: documentation and tests must treat reconstruction as a privileged repository/mapper path, not a general public factory.

Python cannot enforce true private access. The implementation must therefore make reconstruction visibly internal, covered by architecture tests, and absent from normal creation examples.

## 9. Creation Versus Reconstruction

| Concern | Creation | Reconstruction |
| --- | --- | --- |
| Purpose | New aggregate | Existing persisted aggregate |
| Entry point | Public constructor | Internal aggregate-specific reconstructor |
| Lifecycle | Initial state only | Restored state |
| Version | `AggregateVersion.initial()` | Restored exactly |
| Next transition sequence | `TransitionSequence.initial()` | Restored or derived according to Section 17 |
| Transition history | Empty | Restored exactly after validation |
| Owned collections | Empty except constructor-owned values | Restored ordered tuples |
| Terminal metadata | Unset | Restored according to lifecycle compatibility |
| Effects | None outside aggregate | None outside aggregate |

Public constructors remain creation-oriented. They must not accept state snapshots, lifecycle overrides, version overrides, history, or persisted collection inputs.

## 10. State-Representation Decision

Selected relationship:

```text
CONTRACT-PLUS-STATE-DESIGN
```

M019 designs documentation-level, persistence-neutral, aggregate-specific state records. It does not create source classes.

Documentation-level record names:

| Record | Purpose |
| --- | --- |
| `CampaignReconstructionState` | Complete Campaign restoration input |
| `RunReconstructionState` | Complete Run restoration input |
| `EvidencePackageReconstructionState` | Complete Evidence Package restoration input |
| `ReviewReconstructionState` | Complete Review restoration input |

These are not implementation classes. A later implementation milestone may choose dataclasses, typed dicts, protocols, or another Python representation after independent review.

The state records are aggregate-specific because the four aggregates do not share the same collections, terminal metadata, or context identity.

## 11. Shared Contract

Every reconstruction state must provide:

- canonical `DomainIdentity[...]`;
- canonical lifecycle enum;
- canonical `AggregateVersion`;
- canonical next `TransitionSequence`;
- ordered tuple or iterable of canonical `StateTransitionRecord[...]`;
- aggregate-specific owned values and collections;
- aggregate-specific terminal metadata.

Shared guarantees:

- no version increment during reconstruction;
- no sequence advancement during reconstruction;
- no transition-history append during reconstruction;
- no domain event, audit event, outbox event, external lookup, repository call, clock access, or persistence call;
- defensive tuple copies for histories and collections;
- deterministic preservation of supplied order;
- no sorting, deduplication, merge, repair, or normalization;
- malformed state rejected atomically;
- persistence-neutral errors only.

## 12. Campaign Contract

Documentation-level `CampaignReconstructionState` fields:

| Field | Classification | Rule |
| --- | --- | --- |
| `identity: DomainIdentity[CampaignId]` | STRUCTURALLY VALIDATED | Governance ID must be `CampaignId` |
| `scope_statement: CampaignScopeStatement` | STRUCTURALLY VALIDATED | Must be valid current scope statement |
| `state: CampaignLifecycleState` | STRUCTURALLY VALIDATED | Must be canonical lifecycle state |
| `version: AggregateVersion` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Must be non-negative and sufficient for visible restored state |
| `next_transition_sequence: TransitionSequence` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Must follow transition-history rule |
| `transition_history` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Ordered tuple of Campaign transition records |

Lifecycle transition path:

```text
DRAFT -> READY_FOR_AUTHORIZATION -> AUTHORIZED -> ACTIVE -> SUSPENDED -> ACTIVE
ACTIVE -> COMPLETED
DRAFT/READY_FOR_AUTHORIZATION/AUTHORIZED/ACTIVE/SUSPENDED -> CANCELLED
```

Empty history is compatible only with `DRAFT`, version `0`, next sequence `1`, unless a future data migration is explicitly documented. Campaign scope revisions are not reconstructable as historical records because the current aggregate stores only the current `CampaignScopeStatement`; reconstruction must not invent scope-revision audit history.

Campaign terminal reasons live only in transition history. No hidden owner, authorization, archive, Audit, or Decision Candidate state is restored.

## 13. Run Contract

Documentation-level `RunReconstructionState` fields:

| Field | Classification | Rule |
| --- | --- | --- |
| `identity: DomainIdentity[RunId]` | STRUCTURALLY VALIDATED | Governance ID must be `RunId` |
| `campaign_id: CampaignId` | STRUCTURALLY VALIDATED | Immutable context only; no Campaign lookup |
| `state: RunLifecycleState` | STRUCTURALLY VALIDATED | Must be canonical lifecycle state |
| `manifests` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Ordered `DatasetManifest` values |
| `version: AggregateVersion` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Must be sufficient for restored lifecycle and manifests |
| `next_transition_sequence: TransitionSequence` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Must follow history rule |
| `transition_history` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Ordered Run transition records |

Run lifecycle path:

```text
CREATED -> AUTHORIZED -> ACQUIRING -> NORMALIZING -> VALIDATING -> EXECUTION_COMPLETED
AUTHORIZED -> CANCELLED
ACQUIRING/NORMALIZING/VALIDATING -> FAILED
```

Manifest rules:

- supplied manifest order is preserved exactly;
- `current_manifest` is never supplied separately and is derived as the last manifest, or `None`;
- every manifest `run_id` must match the Run governance ID;
- duplicate non-null `manifest_id` values are rejected;
- multiple unidentified manifests remain allowed, matching frozen Run behavior;
- no sorting, deduplication, repair, or Campaign lookup occurs.

Run failure/cancellation reasons live only in transition history. `EXECUTION_COMPLETED` has no separate terminal metadata field.

## 14. EvidencePackage Contract

Documentation-level `EvidencePackageReconstructionState` fields:

| Field | Classification | Rule |
| --- | --- | --- |
| `identity: DomainIdentity[EvidencePackageId]` | STRUCTURALLY VALIDATED | Governance ID must be `EvidencePackageId` |
| `run_id: RunId` | STRUCTURALLY VALIDATED | Immutable Run context only; no Run lookup |
| `state: EvidencePackageLifecycleState` | STRUCTURALLY VALIDATED | Must be canonical lifecycle state |
| `criterion_results` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Ordered `CriterionResult` values |
| `artifact_references` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Ordered `ArtifactReference` values |
| `version: AggregateVersion` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Must be sufficient for restored lifecycle and contents |
| `next_transition_sequence: TransitionSequence` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Must follow history rule |
| `transition_history` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Ordered Evidence Package transition records |

Lifecycle path:

```text
INITIALIZED -> COLLECTING -> SEALED -> INVALIDATED
```

Content rules:

- every `CriterionResult.evidence_package_id` must match the aggregate governance ID;
- duplicate `criterion_id` values are rejected;
- duplicate exact `ArtifactReference.value` values are rejected;
- supplied order is preserved exactly;
- no artifact existence, object-storage, checksum, bucket, or key lookup is performed.

Lifecycle/content compatibility:

- `INITIALIZED`: no results and no artifact references.
- `COLLECTING`: any current collection state allowed, including empty.
- `SEALED`: at least one Criterion Result and one ArtifactReference required.
- `INVALIDATED`: at least one Criterion Result and one ArtifactReference required, with invalidation reason carried in transition history.

## 15. Review Contract

Documentation-level `ReviewReconstructionState` fields:

| Field | Classification | Rule |
| --- | --- | --- |
| `identity: DomainIdentity[ReviewId]` | STRUCTURALLY VALIDATED | Governance ID must be `ReviewId` |
| `target: ReviewTargetReference` | STRUCTURALLY VALIDATED | Evidence Package target only |
| `reviewer: ReviewerReference` | STRUCTURALLY VALIDATED | Opaque non-empty reviewer reference |
| `state: ReviewLifecycleState` | STRUCTURALLY VALIDATED | Must be canonical lifecycle state |
| `findings` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Ordered `ReviewFinding` values |
| `disposition` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Required only when completed |
| `final_disposition_rationale` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Required only when completed |
| `cancellation_reason` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Required only when cancelled |
| `version: AggregateVersion` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Must be sufficient for restored lifecycle and findings |
| `next_transition_sequence: TransitionSequence` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Must follow history rule |
| `transition_history` | STRUCTURALLY VALIDATED and INTERNALLY CONSISTENCY-VALIDATED | Ordered Review transition records |

Lifecycle path:

```text
ASSIGNED -> IN_PROGRESS -> COMPLETED
ASSIGNED/IN_PROGRESS -> CANCELLED
```

Finding rules:

- every finding sequence must be positive;
- finding sequences must be strictly increasing in supplied order;
- contiguous finding sequences are required because the frozen aggregate uses `_next_finding_sequence = previous + 1`;
- duplicate finding text remains allowed because frozen behavior does not reject it;
- evidence reference strings remain opaque and structurally validated only.

No reviewer authority, reviewer independence, or target existence check occurs during reconstruction.

## 16. Version Rules

`AggregateVersion` is restored exactly from persisted state.

Rules:

- version `0` is allowed only for initial observable aggregate state;
- positive versions are restored exactly;
- version may exceed transition-history length because content mutations increment version without lifecycle history;
- version-history equality is not required;
- persistence does not increment version;
- reconstruction does not increment version;
- negative or non-integer versions are rejected by the canonical primitive;
- no missing version is inferred from history.

Minimum version rule:

| Aggregate evidence | Minimum version |
| --- | --- |
| Initial state, empty history, empty mutable content | `0` |
| Any non-initial lifecycle transition history | at least the highest transition record version |
| Run manifests present | at least manifest count, adjusted upward for transition history |
| EvidencePackage content present | at least content mutation count, adjusted upward for transition history |
| Review findings present | at least finding count, adjusted upward for transition history |
| Review terminal metadata set | at least highest terminal transition record version |

This is an internal consistency floor, not a reconstruction of the full mutation count. Historical version truth beyond visible aggregate state remains trusted from persistence.

## 17. Sequence Rules

Canonical decision:

```text
TransitionSequence stored on the aggregate is the next sequence to use.
```

Rules:

- initial next sequence is `TransitionSequence(1)`;
- empty transition history requires next sequence `1`;
- non-empty history requires strict ascending sequence values beginning at `1`;
- no duplicate sequences are allowed;
- no sequence gaps are allowed;
- next transition sequence must equal the final history sequence plus one;
- reconstruction must not repair sequence gaps or reorder history;
- next sequence is not the latest consumed sequence.

This eliminates off-by-one ambiguity: a history whose last record sequence is `TransitionSequence(3)` requires aggregate `next_transition_sequence == TransitionSequence(4)`.

## 18. History Validation

Every supplied `StateTransitionRecord` must be structurally valid and internally consistent with the aggregate:

- record type is canonical;
- identity reference is absent or matches the aggregate identity;
- `from_state` and `to_state` are valid lifecycle values for the aggregate;
- transition is allowed by the frozen lifecycle matrix;
- sequence order follows Section 17;
- record version is an `AggregateVersion`;
- record timestamp is preserved exactly;
- record actor, reason, and correlation ID are preserved exactly;
- final record `to_state` matches restored current lifecycle state;
- terminal transitions are not followed by later records.

Timestamp monotonicity is not required. The repository currently does not prove a monotonic timestamp invariant, and reconstructors must not invent one.

Transition history is not an event-sourcing stream. It is historical lifecycle data only and cannot be replayed to restore content mutations.

## 19. Collection Validation

| Collection | Input type | Element type | Ordering | Duplicate rule | Identity rule | Error condition |
| --- | --- | --- | --- | --- | --- | --- |
| Campaign current scope | single value | `CampaignScopeStatement` | Not a collection | Not applicable | Campaign-local only | wrong type or invalid statement |
| Run manifests | iterable copied to tuple | `DatasetManifest` | preserve supplied order | duplicate non-null `manifest_id` rejected; repeated `None` allowed | manifest `run_id` equals Run ID | wrong type, wrong run, duplicate non-null ID |
| EvidencePackage Criterion Results | iterable copied to tuple | `CriterionResult` | preserve supplied order | duplicate `criterion_id` rejected | result package ID equals Evidence Package ID | wrong type, wrong package, duplicate criterion |
| EvidencePackage ArtifactReferences | iterable copied to tuple | `ArtifactReference` | preserve supplied order | duplicate exact `value` rejected | package-local only | wrong type or duplicate value |
| Review findings | iterable copied to tuple | `ReviewFinding` | preserve supplied order | duplicate text allowed | Review-local only | wrong type or non-contiguous sequence |

No reconstruction path may normalize, sort, merge, deduplicate, overwrite, or silently discard collection elements.

## 20. Terminal Metadata Matrices

Campaign:

| State | Metadata compatibility |
| --- | --- |
| `COMPLETED` | Completion reason, if any, exists only in final transition record |
| `CANCELLED` before authorization | Cancellation reason may be absent or present in final transition record |
| `CANCELLED` after authorization boundary | Cancellation reason must be present in final transition record |
| Other states | No terminal metadata field exists |

Run:

| State | Metadata compatibility |
| --- | --- |
| `EXECUTION_COMPLETED` | No separate terminal metadata; final transition may carry reason |
| `FAILED` | Final transition reason required |
| `CANCELLED` | Final transition reason required |
| Other states | No terminal metadata field exists |

EvidencePackage:

| State | Metadata compatibility |
| --- | --- |
| `SEALED` | At least one result and one artifact reference; no separate terminal metadata |
| `INVALIDATED` | At least one result and one artifact reference; final transition reason required |
| Other states | No invalidation metadata |

Review:

| State | Disposition | Final rationale | Cancellation reason |
| --- | --- | --- | --- |
| `ASSIGNED` | unset | unset | unset |
| `IN_PROGRESS` | unset | unset | unset |
| `COMPLETED` | set | set | unset |
| `CANCELLED` | unset | unset | set |

No terminal metadata may be invented during reconstruction.

## 21. Error Model

M019 designs conceptual reconstruction errors only. No source errors are implemented.

Future reconstruction errors should be domain-level and persistence-neutral:

| Error category | Meaning |
| --- | --- |
| `WrongReconstructionInput` | caller supplied a non-state or wrong aggregate state |
| `InvalidAggregateIdentity` | identity type or governance identifier is wrong |
| `InvalidLifecycleState` | lifecycle value is not canonical for the aggregate |
| `InvalidAggregateVersion` | version is malformed or internally inconsistent |
| `InvalidTransitionSequence` | next sequence or history sequence is malformed |
| `InvalidTransitionHistory` | history path, identity, state, order, or terminal placement is invalid |
| `InconsistentCurrentState` | current lifecycle conflicts with final history record |
| `InvalidCollectionElement` | owned collection contains wrong element type or malformed element |
| `DuplicateOwnedValue` | owned collection violates frozen duplicate rule |
| `InconsistentTerminalMetadata` | terminal metadata conflicts with lifecycle state |
| `UnauthorizedReconstructionPath` | reconstruction was attempted outside the approved internal boundary |

Database, ORM, SQLAlchemy, psycopg, S3, object-storage, and runtime exceptions must not appear in domain reconstruction errors.

## 22. Defensive Copying

Future reconstruction must:

- create immutable tuples from supplied transition histories and collections;
- never retain mutable list references;
- never retain iterator or generator state;
- preserve canonical immutable value objects by reference only when they are already frozen/immutable;
- expose only tuple properties already present in frozen aggregate behavior;
- keep input state records separate from aggregate internals.

If an input iterable cannot be safely materialized exactly once, reconstruction rejects it or copies it before validation.

## 23. Visibility

Selected intended visibility:

```text
factory-only, aggregate-package-internal, underscore-prefixed internal
```

Future implementation should not add unrestricted public `from_state` methods to aggregate classes. If Python naming exposes an internal symbol, tests and architecture review must still treat it as privileged.

The reconstruction path must not appear in normal creation examples, public README usage, command-handler examples, or ordinary application-service flows.

## 24. Testing Strategy

Future implementation tests must cover:

Successful reconstruction:

- one case per lifecycle state for each aggregate;
- empty and populated owned collections;
- terminal states;
- exact version preservation;
- exact next-sequence preservation;
- exact transition-history preservation;
- continued mutation after reconstruction uses restored version and sequence correctly.

Malformed state:

- wrong input type;
- identity mismatch;
- invalid lifecycle value;
- invalid transition path;
- duplicate or gapped transition sequences;
- lifecycle/history mismatch;
- invalid owned collection element;
- duplicate owned value;
- invalid finding order;
- terminal metadata mismatch;
- mutable-input defensive copying.

Non-effects:

- no version increment;
- no sequence advancement;
- no new transition record;
- no clock access;
- no external lookup;
- no repository access;
- no persistence-specific type.

No implementation tests are added by this design mission.

## 25. Compatibility Guarantees

Future reconstruction implementation must not:

- change public business behavior;
- change normal constructors;
- alter lifecycle transitions;
- change version semantics;
- change transition-sequence semantics;
- change duplicate rules;
- modify value-object semantics;
- add SQL, ORM, repository, mapper, storage, or runtime dependencies to domain aggregates;
- require schema decisions;
- define repository save semantics;
- define optimistic-concurrency save behavior;
- define Audit runtime, Decision Candidate runtime, Decision Freeze, event sourcing, or outbox behavior.

## 26. Deferred Work

Deferred:

- concrete reconstruction implementation;
- concrete state-record implementation;
- repository contracts;
- not-found semantics;
- optimistic concurrency and save contracts;
- Unit of Work;
- mappers;
- PostgreSQL schema;
- migrations;
- serializers;
- APIs;
- workers;
- outbox;
- event sourcing;
- audit storage;
- runtime composition;
- campaign execution and empirical validation.

## 27. Risks and Mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Internal reconstructor becomes ordinary public API | MAJOR | Keep factory-only internal naming and require review of usage examples |
| Documentation-level state records become accidental schema | MAJOR | Keep names field-level and persistence-neutral; no table/column names |
| Version/history relationship overvalidated | MAJOR | Use minimum consistency floors and trust historical facts that cannot be proven locally |
| Timestamp monotonicity invented | MINOR | Explicitly do not require monotonicity |
| Generic abstraction introduced too early | MAJOR | Reject shared protocol until implementation evidence supports it |
| Private-field mutation by adapters | CRITICAL | Persistence adapters are explicitly forbidden from mutating aggregates |
| Collection repair hides corruption | MAJOR | Reconstruction rejects malformed state and never repairs or normalizes |

## 28. Hostile Self-Review

| ID | Severity | Section | Finding | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| M019-DESIGN-ISSUE-0001 | MAJOR | 7 | Initial architecture risked implying repositories call aggregate internals directly. | Could blur mapper/repository boundary. | Authority model states future repository/mapper layer invokes internal domain reconstructor; adapters do not. | Resolved |
| M019-DESIGN-ISSUE-0002 | MAJOR | 10 | State-record design could be mistaken for implementation. | Could authorize source state records. | Marked state records documentation-level only and deferred concrete representation. | Resolved |
| M019-DESIGN-ISSUE-0003 | MAJOR | 16 | Version minimums could imply full mutation-count reconstruction. | Could overvalidate historical truth. | Added minimum consistency floor and classified full mutation truth as trusted. | Resolved |
| M019-DESIGN-ISSUE-0004 | MINOR | 18 | Timestamp ordering was tempting but not proven. | Could reject valid historical data. | Explicitly rejected monotonicity requirement. | Resolved |
| M019-DESIGN-ISSUE-0005 | MINOR | 20 | Campaign cancellation reason differs before and after authorization. | Could overreject draft cancellations. | Terminal matrix distinguishes pre- and post-authorization cancellation. | Resolved |
| M019-DESIGN-ISSUE-0006 | MAJOR | 19 | Review findings needed exact sequence policy. | Could allow inconsistent `_next_finding_sequence`. | Required positive, strictly increasing, contiguous sequences. | Resolved |

No MAJOR or CRITICAL self-review issue remains open.

## 29. Acceptance Gate

| Criterion | Result |
| --- | --- |
| Baseline verified | PASS |
| All four aggregate contracts complete | PASS |
| Reconstruction authority selected | PASS |
| Reconstruction location selected | PASS |
| State-representation relationship selected | PASS |
| Validation/trust rules explicit | PASS |
| Version rules explicit | PASS |
| Sequence rules explicit | PASS |
| History validation explicit | PASS |
| Collection validation explicit | PASS |
| Terminal metadata matrices complete | PASS |
| Hostile self-review resolved | PASS |
| No implementation introduced | PASS |
| No repository, mapper, schema, migration, API, worker, or runtime behavior introduced | PASS |

Validation commands must pass before commit.

## 30. Final Decision

MILESTONE-019 selects aggregate-specific internal reconstructors/factories, backed by documentation-level aggregate-specific persistence-neutral state records, as the approved reconstruction contract design.

Final status:

```text
DESIGN READY FOR INDEPENDENT REVIEW
```
