# MILESTONE-012 - Canonical Runtime Domain Kernel Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Milestone | MILESTONE-012 |
| Document | MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md |
| Version | 1.2 / Authority and Freeze Readiness Correction |
| Status | APPROVED AND FROZEN |
| Repository Baseline | 274a3ffbaac19ea449f80bc6c87befa46fb89c7c |
| Correction Input | MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_INDEPENDENT_REVIEW.md |
| Mission Type | DESIGN CORRECTION ONLY |
| Implementation Performed | No |

## 2. Scope

This corrected draft defines the initial canonical runtime domain kernel needed before implementation of domain schemas, repositories, APIs, workers, job ledger, transactional outbox, governance registry, audit ledger, or campaign execution.

The initial kernel is intentionally smaller than the first draft. It defines only the minimum runtime aggregates needed to safely design later persistence and behavior:

- Campaign;
- Run;
- Evidence Package;
- Review.

It also defines Dataset Manifest as an immutable owned record under Run and Criterion Result as an owned entity under Evidence Package.

## 3. Non-Goals

This document does not implement code or authorize implementation.

It does not create schemas, migrations, tables, columns, repositories, APIs, workers, schedulers, runtime entities, job ledger, transactional outbox, governance registry, audit event ledger, object-storage layouts, bucket conventions, key conventions, retention policy, trading behavior, vendor behavior, market-data behavior, empirical validation execution, Decision Candidate behavior, or Decision Freeze behavior.

## 4. Governing Documents

Repository documents:

| Document | Availability | Use |
| --- | --- | --- |
| MILESTONE_004_REPOSITORY_SCAFFOLDING_AND_TOOLCHAIN_BOOTSTRAP.md | Present in repository | Repository and toolchain boundaries |
| MILESTONE_005_INFRASTRUCTURE_ARCHITECTURE.md | Present in repository | Infrastructure/domain separation |
| MILESTONE_006_FOUNDATION_CONTRACTS.md | Present in repository | Foundation identifier, persistence, storage, error, health, and orchestration boundaries |
| MILESTONE_001_006_DOCUMENT_INTEGRATION_REVIEW.md | Present in repository | Lineage bridge for 001-006 |
| MILESTONE_007_FIRST_INFRASTRUCTURE_IMPLEMENTATION_SLICE.md | Present in repository | Runtime identifier evidence |
| MILESTONE_008_PERSISTENCE_CONNECTIVITY_FOUNDATION_SLICE.md | Present in repository | Persistence access without schema |
| MILESTONE_009_OBJECT_STORAGE_CONNECTIVITY_FOUNDATION_SLICE.md | Present in repository | Object storage without layout |
| MILESTONE_010_SCOPE_SELECTION_AND_ARCHITECTURE_GAP_REVIEW.md | Present in repository | Unified runtime scope selection |
| MILESTONE_010_UNIFIED_INFRASTRUCTURE_RUNTIME_COMPOSITION.md | Present in repository | Unified runtime boundary |
| MILESTONE_011_SCOPE_SELECTION_AND_ARCHITECTURE_GAP_REVIEW.md | Present in repository | Domain-kernel design selection |

Located external artifacts:

| Artifact | Path | SHA-256 | Status / Authority Limitation |
| --- | --- | --- | --- |
| MILESTONE-000D | `C:\Users\LuxSy\Desktop\MILESTONE_000D_EMPIRICAL_CAMPAIGN_ARCHITECTURE.md` | `6D42C95D326AC8A39460CA63435B429BF96196220D6E6B88A0C63ACB2912FDA0` | DRAFT / ARCHITECTURE UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| MILESTONE-001 | `C:\Users\LuxSy\Desktop\MILESTONE_001_SYSTEM_IMPLEMENTATION_ARCHITECTURE.md` | `0840DE137D2DF7D97B9B2F24C84F0DBC3B0356B9A6E2F1C133D7965A768FB85C` | DRAFT / SYSTEM ARCHITECTURE UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| MILESTONE-002 | `C:\Users\LuxSy\Desktop\MILESTONE_002_TECHNOLOGY_SELECTION_AND_ENGINEERING_BLUEPRINT.md` | `EDBAF15F0BE1D50589A4C6910635091FCF906D0BABAF71E9515F606F2BFBD75C` | DRAFT / ENGINEERING BLUEPRINT UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| MILESTONE-003 | `C:\Users\LuxSy\Desktop\MILESTONE_003_PLATFORM_FOUNDATION_INITIALIZATION.md` | `82C05ACE8771C3E0B205E12156883065E6A5F3A23184D67ABDD3E3107775933E` | DRAFT / FOUNDATION UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| MILESTONE-000C Framework | `C:\Users\LuxSy\Desktop\MILESTONE_000C_EMPIRICAL_VALIDATION_FRAMEWORK.md` | `9599631C7FC4D443E3EA754FB02D8F0BEB906FEBC626561CD1971E91020C0ECF` | DRAFT / FRAMEWORK UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| MILESTONE-000C Campaign Standard | `C:\Users\LuxSy\Desktop\MILESTONE_000C_EMPIRICAL_VALIDATION_CAMPAIGN_STANDARD.md` | `7CAF2E0D2CBCD2DAFBAAC8B4FCB2085D2A50F1D917C85ACB20E794FEA7188855` | DRAFT / CAMPAIGN STANDARD UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| Empirical Validation Protocol | `C:\Users\LuxSy\Desktop\MILESTONE_000B_4_PHASE2_CATEGORY1_EMPIRICAL_VALIDATION_PROTOCOL.md` | `C7434A843A197480D81E737AEFF53DC7B37DC1C42067D255DECF15E5741393A7` | DRAFT / PROTOCOL UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| Evidence Artifact Specification | `C:\Users\LuxSy\Desktop\MILESTONE_000B_4_PHASE2_EVIDENCE_ARTIFACT_SPECIFICATION.md` | `B66C05CDFDBC74BF40C98D70F493E2A7F562645A5EEDD2974110E0B44E10BC74` | DRAFT / ARTIFACT SPECIFICATION UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| Empirical Test Execution Runbook | `C:\Users\LuxSy\Desktop\MILESTONE_000B_4_PHASE2_EMPIRICAL_TEST_EXECUTION_RUNBOOK.md` | `3A04E4BA880EDA08CAF966462DB528B6FF07676CE3F2B928542B4082BC76522A` | DRAFT / RUNBOOK UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| Master Governance Integration Standard | `C:\Users\LuxSy\Desktop\MASTER_GOVERNANCE_INTEGRATION_STANDARD.md` | `C2D6CA59034F36C531FB9D2B243F2BE5BA3911EF9B11130A987470D1D6BB1DAC` | DRAFT / VERSION 1.1 ACCEPTANCE CORRECTION PASS UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| Master Governance Gate Classification Standard | `C:\Users\LuxSy\Desktop\MASTER_GOVERNANCE_GATE_CLASSIFICATION_STANDARD.md` | `2477644BC7BAA15C214B6F817DB41D96265329BDF1DB85E39D96FC0EBE7D2413` | DRAFT / GATE CLASSIFICATION STANDARD UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| Master Governance Registry Synchronization Standard | `C:\Users\LuxSy\Desktop\MASTER_GOVERNANCE_REGISTRY_SYNCHRONIZATION_STANDARD.md` | `4DC5E7348435C40CF98CD168E381614CB8838117A0DA993F5DF275E4D7481513` | DRAFT / REGISTRY SYNCHRONIZATION STANDARD UNDER REVIEW; registered in `docs/governance/baseline`; informative, not frozen |
| Baseline Registration Package | `C:\Users\LuxSy\Desktop\BASELINE_REGISTRATION_PACKAGE\` | Multiple hashes in baseline manifest | Operational evidence package; registered in `docs/governance/baseline`; authority unresolved |
| CAMP-0001 Proposal | `C:\Users\LuxSy\Desktop\CAMP-0001_CAMPAIGN_PROPOSAL.md` | `0130233E7D324E0AF90D1523E91DB0F0B25F8B6F8FDBFF8918B9C39A045FC3F5` | DRAFT; registered in `docs/governance/baseline`; informative only |
| CAMP-0001 Authorization Review | `C:\Users\LuxSy\Desktop\CAMP-0001_AUTHORIZATION_REVIEW.md` | `7593AFF633C506FFC366BAA90A26931695EFE2DB7A5C81C0BEB3E2378A26361B` | DRAFT REVIEW COMPLETE / REMAIN_IN_DRAFT; registered in `docs/governance/baseline`; informative only |

External baseline registration evidence is recorded in `docs/governance/baseline/manifest/MILESTONE_012_EXTERNAL_BASELINE_MANIFEST.md`.

DOMAIN-DESIGN-ISSUE-0001 is resolved for MILESTONE-012 freeze. External artifacts are repository-registered and reconciled as non-normative evidence, design context, or informative traceability inputs. They are not authoritative freeze prerequisites for this runtime domain-kernel design. MILESTONE-012 freezes against the repository evidence chain, the registered artifact manifest, and this corrected authority classification.

## 5. Repository Baseline

Baseline:

```text
7fd8a306bb3a2e33e9087d9415355284fdab0441
```

Observed repository facts:

- `CampaignId`, `RunId`, `DatasetId`, `EvidencePackageId`, `ReviewId`, `AuditId`, and `DecisionCandidateId` exist as typed identifier value objects.
- opaque UUIDv4 runtime identifiers exist separately and carry no domain meaning.
- domain packages are empty boundary modules.
- `migrations/versions` is empty.
- persistence interfaces contain no domain schema semantics.
- object-storage interfaces contain no domain key semantics.
- README states campaign execution, Decision Candidate creation, and Decision Freeze are not implemented.

## 6. Terminology

| Term | Meaning |
| --- | --- |
| Initial kernel | Corrected minimum runtime model for the first safe domain implementation design |
| Deferred concept | Concept intentionally excluded from the initial runtime kernel |
| Governance identifier | Human-readable project identifier such as `CAMP-0001` |
| Runtime UUID | Opaque UUIDv4 technical identifier with no domain prefix or meaning |
| AggregateVersion | Optimistic-concurrency version for one aggregate root |
| TransitionSequence | Append-only ordering for lifecycle transition records inside one aggregate |
| StateTransitionRecord | Immutable record of a lifecycle transition; not an event and not a value object in isolation |
| Dataset Manifest | Immutable owned record under Run describing source/acquisition/normalization facts |
| Criterion Result | Owned entity under Evidence Package |
| Decision Candidate | Deferred governance-preparation concept, not part of the initial runtime kernel |

## 7. Identifier Inventory and Reconciliation

Initial kernel identifier rules:

| Concept | Governance ID | Runtime UUID | Allocation Authority | Reservation Timing | Scope | Display Use | Persistence Use |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Campaign | Required `CAMP-####` | Required | Campaign governance operator | Reserved atomically with Campaign creation | Global | Primary human reference | Internal persistence identity plus governance ID |
| Run | Required `RUN-####` | Required | Campaign operator under authorized Campaign | Reserved atomically with Run creation | Global | Human run reference | Internal persistence identity plus governance ID |
| Evidence Package | Required `EVID-####` | Required | Evidence manager under Run | Reserved atomically with Evidence Package creation | Global | Evidence package reference | Internal persistence identity plus governance ID |
| Review | Required `REVIEW-####` | Required | Review coordinator | Reserved atomically with Review assignment | Global | Review/audit trail reference | Internal persistence identity plus governance ID |
| Dataset Manifest | Optional `DATASET-####`, deferred unless external reference/reuse is required | Optional, owned under Run | Run operator if needed | Allocated only when manifest requires external reference | Run-local by default | Usually displayed through Run context | Owned manifest identity under Run |
| Criterion Result | No global ID by default | Optional aggregate-local technical identity | Evidence Package aggregate | Created with result record before package seal | Evidence-package-local | Displayed through criterion identity and Evidence Package | Owned result identity |
| Audit | Deferred | Deferred | Deferred | Deferred | Deferred | Deferred | Deferred |
| Decision Candidate | Deferred | Deferred | Deferred | Deferred | Deferred | Deferred | Deferred |

Pre-persistence allocation behavior:

- identifier reservation and aggregate creation must be atomic from the domain perspective;
- abandoned reservation handling is deferred to the future persistence design;
- collisions reject creation and require a new reservation;
- governance IDs are immutable after creation;
- runtime UUIDs are never displayed as replacement governance references.

Unsupported identifiers for deferred concepts are not required in the initial kernel.

## 8. Canonical Entity Inventory

Initial canonical kernel:

| Concept | Corrected Classification | Purpose |
| --- | --- | --- |
| Campaign | Aggregate root | Governs campaign scope, authorization status, and high-level lifecycle |
| Run | Aggregate root | Represents one execution attempt under one Campaign |
| Dataset Manifest | Immutable owned record under Run | Records source/acquisition/normalization facts without broad lifecycle |
| Evidence Package | Aggregate root | Owns seal, invalidation, artifact references, and Criterion Results |
| Criterion Result | Owned entity under Evidence Package | Records one criterion evaluation result within one Evidence Package |
| Review | Aggregate root | Records independent review assignment, lifecycle, immutable findings, and disposition |

Deferred from initial kernel:

| Concept | Corrected Classification | Reason |
| --- | --- | --- |
| Audit | Deferred future aggregate or specialized process-compliance Review | Distinct process-compliance authority and lifecycle require more governance baselining |
| Decision Candidate | Deferred governance-preparation concept | Not required before evidence/review implementation and must not become premature schema |
| Vendor Candidate | Deferred value object / later concern | No vendor behavior authorized |
| Calibration Record | Deferred record | Requires validation execution model |
| Statistical Boundary Record | Deferred record | Requires validation/statistical model |
| Reviewer Declaration | Owned record under Review | Not an aggregate root |
| Exception Record | Owned record under Run or Review depending on context | Not an aggregate root |
| Conflict Record | Owned record under Review | Not an aggregate root |
| Rerun Record | Owned record linking Runs | Not an aggregate root |

## 9. Entity Classification

| Item | Classification | Mutable Fields | Immutable Fields | Creation Authority | Transition Authority |
| --- | --- | --- | --- | --- | --- |
| Campaign | Aggregate root | Draft scope before authorization, readiness status, lifecycle | `CampaignId`, runtime UUID, creation timestamp | Campaign Owner | Campaign Owner or authorization reviewer by transition |
| Run | Aggregate root | execution progress, failure/cancellation status before terminal state | `RunId`, runtime UUID, Campaign reference, authorized scope snapshot | Campaign Operator | Run Operator; Review may create disposition records but not mutate execution history |
| Dataset Manifest | Immutable owned record | None after creation; superseded by new manifest | source/acquisition/normalization facts, optional manifest ID | Run Operator | Run aggregate only |
| Evidence Package | Aggregate root | collection state before seal; invalidation/archival records after seal | `EVID`, runtime UUID, Run reference, sealed object references | Evidence Manager | Evidence Manager for seal/invalidation; Review only references it |
| Criterion Result | Owned entity | pre-seal result metadata | criterion identity, result payload after seal, evidence references | Evidence Package aggregate | Evidence Package aggregate |
| Review | Aggregate root | assignment before completion, lifecycle, revision records | `REVIEW`, runtime UUID, target reference, completed findings | Review Coordinator | Reviewer |

## 10. Aggregate Roots

Initial aggregate roots:

- Campaign;
- Run;
- Evidence Package;
- Review.

Rationale:

- Campaign controls scope and authorization but does not own every Run.
- Run controls one execution attempt and owns Dataset Manifests.
- Evidence Package controls immutable evidence and owns Criterion Results.
- Review controls independence, findings, and disposition without mutating evidence.

Deferred aggregate roots:

- Audit, pending process-compliance design and authority reconciliation;
- Decision Candidate, pending evidence/review/audit sufficiency design.

## 11. Aggregate Ownership Boundaries

| Aggregate | Owns | References | Does Not Own | Transaction Boundary | Collection Loading |
| --- | --- | --- | --- | --- | --- |
| Campaign | campaign scope, authorization state, lifecycle, bounded current-state summary | Runs by ID, Reviews by ID | Run internals, evidence contents, review findings | One Campaign state/scope change | Must not load all Runs |
| Run | execution attempt state, authorized scope snapshot, Dataset Manifests, rerun link records | Campaign, Evidence Packages, Reviews | Campaign authorization, evidence seal, review findings | One Run transition or manifest append | Must not load all historical manifests by default |
| Evidence Package | package lifecycle, object references, integrity records, Criterion Results, invalidation records | Run, Dataset Manifests, Reviews | Run execution history, Review findings | One package transition or result append | May load bounded package contents; large collections require read model later |
| Review | assignment records, conflict records, findings, disposition, revision/supersession records | target Run or Evidence Package | sealed evidence contents, Run execution history | One Review transition/finding append | Findings must remain bounded or paged later |

No aggregate may mutate another aggregate directly. Cross-aggregate effects occur through command-time checks, reconciliation, or later event handling.

## 12. Entity Relationships

| Relationship | Cardinality | Ownership | Reference Mutability | Propagation |
| --- | --- | --- | --- | --- |
| Campaign to Run | One to many | Run references Campaign | immutable after Run creation | Campaign summary may be recalculated from Run status |
| Run to Dataset Manifest | One to many | Run owns manifests | immutable after manifest creation | supersession creates a new manifest record |
| Run to Evidence Package | One to many | Evidence Package references Run | immutable after package creation | evidence invalidation may affect Run qualification through reconciliation |
| Evidence Package to Criterion Result | One to many | Evidence Package owns results | immutable after seal | invalidation is additive |
| Review to target | One Review to one primary Run or Evidence Package | Review owns findings only | target reference immutable | review disposition may qualify target but not mutate it |
| Rerun link | One prior Run to one or more new Runs | New Run records prior Run reference | immutable | old Run remains historical |

Deletion of referenced records is prohibited after external references exist. Archival does not erase references.

## 13. Campaign Lifecycle

Corrected Campaign lifecycle states:

- `DRAFT`;
- `READY_FOR_AUTHORIZATION`;
- `AUTHORIZED`;
- `ACTIVE`;
- `SUSPENDED`;
- `COMPLETED`;
- `CANCELLED`.

Allowed transitions:

| From | To | Preconditions | Authority | Reversible | Transition Record |
| --- | --- | --- | --- | --- | --- |
| DRAFT | READY_FOR_AUTHORIZATION | Scope and prerequisites complete | Campaign Owner | Yes, by correction back to DRAFT | CampaignPreparedForAuthorization |
| READY_FOR_AUTHORIZATION | AUTHORIZED | Authorization review passes | Authorization Reviewer | No silent reversal | CampaignAuthorized |
| AUTHORIZED | ACTIVE | At least one Run authorized or campaign operation opened | Campaign Operator | Yes, to SUSPENDED | CampaignActivated |
| ACTIVE | SUSPENDED | governed pause condition | Campaign Owner or authorized governance actor | Yes, to ACTIVE | CampaignSuspended |
| SUSPENDED | ACTIVE | restoration conditions met | Campaign Owner plus required reviewer if applicable | Yes | CampaignResumed |
| ACTIVE | COMPLETED | no active Runs remain; required Review dispositions complete | Campaign Owner | No, except governed correction | CampaignCompleted |
| DRAFT | CANCELLED | campaign abandoned before authorization | Campaign Owner | No | CampaignCancelled |
| READY_FOR_AUTHORIZATION | CANCELLED | campaign abandoned before authorization | Campaign Owner | No | CampaignCancelled |
| AUTHORIZED | CANCELLED | campaign abandoned before execution | Campaign Owner with reason | No | CampaignCancelled |
| ACTIVE | CANCELLED | campaign stopped before completion | Campaign Owner with reason | No | CampaignCancelled |
| SUSPENDED | CANCELLED | campaign not restored | Campaign Owner with reason | No | CampaignCancelled |

Removed from Campaign lifecycle:

- `REVIEW_IN_PROGRESS`;
- `AUDIT_IN_PROGRESS`;
- `COMPLETED_EVIDENCE_VALID`;
- `COMPLETED_EVIDENCE_INVALID`;
- `RUNNING`.

Those are derived from related Runs, Reviews, or qualification records. Archival is an orthogonal archival status or archival record, not a Campaign business lifecycle state.

## 14. Run Lifecycle

Corrected Run lifecycle states:

- `CREATED`;
- `AUTHORIZED`;
- `ACQUIRING`;
- `NORMALIZING`;
- `VALIDATING`;
- `EXECUTION_COMPLETED`;
- `FAILED`;
- `CANCELLED`.

Allowed transitions:

| From | To | Preconditions | Authority | Transition Record |
| --- | --- | --- | --- | --- |
| CREATED | AUTHORIZED | parent Campaign is AUTHORIZED or ACTIVE; Run scope snapshot approved | Campaign Operator | RunAuthorized |
| AUTHORIZED | ACQUIRING | entitlement/license prerequisites recorded | Run Operator | RunAcquisitionStarted |
| ACQUIRING | NORMALIZING | acquisition completed or acquisition exception captured | Run Operator | RunNormalizationStarted |
| NORMALIZING | VALIDATING | normalization completed or exception captured | Run Operator | RunValidationStarted |
| VALIDATING | EXECUTION_COMPLETED | evidence package initialized/sealed path completed or terminal execution record created | Run Operator | RunExecutionCompleted |
| AUTHORIZED | CANCELLED | no execution should begin | Campaign Operator | RunCancelled |
| ACQUIRING | FAILED | execution failure prevents completion | Run Operator | RunFailed |
| NORMALIZING | FAILED | execution failure prevents completion | Run Operator | RunFailed |
| VALIDATING | FAILED | execution failure prevents completion | Run Operator | RunFailed |

Removed from Run lifecycle:

- `VALID`;
- `INVALID`;
- `RERUN_REQUIRED`;
- `ARCHIVED`.

`VALID` and `INVALID` are evidence/review dispositions. `RERUN_REQUIRED` is an immutable Review disposition or rerun link record. Archival is orthogonal. A rerun always creates a new `RunId`, references the prior Run, preserves prior evidence, and never restarts the old Run.

## 15. Dataset Lifecycle

Dataset is corrected to Dataset Manifest, an immutable owned record under Run.

Dataset Manifest records:

- owning Run;
- optional `DatasetId` only if external reference or reuse is required;
- source references;
- acquisition facts;
- normalization facts;
- integrity facts;
- creation timestamp;
- producing actor/process reference;
- supersession reference when a replacement manifest is created.

Dataset Manifest has no independent lifecycle in the initial kernel. Minimal status, if later needed, is limited to `RECORDED` or `SUPERSEDED` as record qualification, not a broad entity state machine.

Runs must not load all historical Dataset Manifests by default. Transition commands load only manifests relevant to the transition.

## 16. Evidence Package Lifecycle

Corrected Evidence Package lifecycle states:

- `INITIALIZED`;
- `COLLECTING`;
- `SEALED`;
- `INVALIDATED`.

Allowed transitions:

| From | To | Preconditions | Authority | Transition Record |
| --- | --- | --- | --- | --- |
| INITIALIZED | COLLECTING | Run is active and collection scope is known | Evidence Manager | EvidenceCollectionStarted |
| COLLECTING | SEALED | required references and Criterion Results are present; writes are closed | Evidence Manager | EvidencePackageSealed |
| SEALED | INVALIDATED | integrity failure, missing object, digest mismatch, or governed invalidation | Evidence Manager or authorized reviewer process | EvidencePackageInvalidated |

Integrity verification is corrected to an immutable verification record, not a lifecycle state. It may qualify a sealed package as verified, failed, or not yet verified. `REVIEWED` is removed from Evidence Package lifecycle; Review outcome belongs to Review.

Rules:

- sealed contents, Criterion Results, and object references are immutable;
- corrections require a new Evidence Package identity or a governed supersession record;
- invalidation is additive and never rewrites sealed evidence;
- support object references become immutable at seal;
- archived status is orthogonal.

## 17. Criterion Result Model

Criterion Result is an owned entity under Evidence Package.

It contains:

- criterion identity;
- observed result;
- evaluator/process reference;
- evaluation timestamp;
- supporting object references;
- limitation/exception references if applicable;
- local result identity inside the Evidence Package.

Criterion Result is immutable after Evidence Package sealing. It is not owned by Run and is not an aggregate root.

## 18. Review Lifecycle

Corrected Review lifecycle states:

- `ASSIGNED`;
- `IN_PROGRESS`;
- `COMPLETED`;
- `CANCELLED`.

Review disposition is separate from lifecycle:

- `ACCEPTED`;
- `REJECTED`;
- `CHANGES_REQUESTED`;
- `INCONCLUSIVE`.

Conflict is an assignment/independence record or status, not a lifecycle state. Findings are immutable owned records. Review revisions are created through new revision records or superseding Reviews, not destructive edits.

Allowed lifecycle transitions:

| From | To | Preconditions | Authority | Transition Record |
| --- | --- | --- | --- | --- |
| ASSIGNED | IN_PROGRESS | reviewer assignment and independence records exist | Reviewer | ReviewStarted |
| IN_PROGRESS | COMPLETED | findings and disposition recorded | Reviewer | ReviewCompleted |
| ASSIGNED | CANCELLED | assignment withdrawn before work | Review Coordinator | ReviewCancelled |
| IN_PROGRESS | CANCELLED | governed cancellation reason recorded | Review Coordinator | ReviewCancelled |

Review never mutates sealed evidence. It can request changes before evidence sealing or create findings/dispositions after sealing.

## 19. Audit Lifecycle

Audit is deferred from the initial runtime kernel.

Reason:

- Audit must be process-compliance focused, not duplicate evidence-content Review;
- located governance artifacts are outside the repository and draft;
- authority, scope, and output rules need a dedicated later design;
- the first runtime implementation can proceed with Review as the independent evidence assessment aggregate.

Deferred Audit prerequisites:

- authoritative campaign/audit governance baseline registered;
- distinct audit inputs, outputs, and authority defined;
- immutable audit findings model defined;
- no direct mutation of Campaign, Run, Evidence Package, or Review;
- stricter independence rules defined where required.

Audit identifiers remain available in the codebase but are not required by the initial kernel.

## 20. Decision Candidate Lifecycle

Decision Candidate is deferred from the initial runtime aggregate model.

Conceptual boundary retained:

- pre-freeze governance-preparation artifact;
- no execution authority;
- no vendor-selection authority;
- no trading, investment, or commercial recommendation authority;
- requires accepted Review evidence and later audit/governance prerequisites;
- invalidated support invalidates eligibility;
- withdrawal, supersession, expiration, revision, and stale-support handling are required before runtime implementation;
- a later dedicated design milestone is required before persistence or implementation.

Decision Candidate identifiers remain available in the codebase but are not required by the initial kernel.

## 21. Cross-Aggregate Invariants

| Invariant | Classification | Owning Boundary | Required References | Enforcement Authority | Violation Result |
| --- | --- | --- | --- | --- | --- |
| A Run belongs to exactly one Campaign | LOCAL SYNCHRONOUS | Run | Campaign ID at creation | Run aggregate command handler | Reject Run creation |
| Run authorized scope snapshot is immutable | LOCAL SYNCHRONOUS | Run | Run state and scope snapshot | Run aggregate command handler | Reject mutation; require governed correction/new Run |
| Rerun creates new Run identity | LOCAL SYNCHRONOUS | Run | Prior Run reference | Run aggregate command handler | Reject overwrite |
| Dataset Manifest is immutable after creation | LOCAL SYNCHRONOUS | Run | Manifest record | Run aggregate command handler | Create superseding manifest instead |
| Sealed Evidence Package cannot mutate contents/references | LOCAL SYNCHRONOUS | Evidence Package | Package state | Evidence Package aggregate command handler | Reject mutation |
| Criterion Result cannot change after seal | LOCAL SYNCHRONOUS | Evidence Package | Package state | Evidence Package aggregate command handler | Reject mutation |
| Review target must exist and be reviewable | CROSS-AGGREGATE COMMAND-TIME | Review | target Run or Evidence Package reference | Review start/completion application service | Reject Review start/completion |
| Reviewer independence must be recorded | GOVERNANCE GATE | Review | assignment and conflict records | Reviewer-assignment gate | Reject Review start or mark conflict |
| Evidence invalidation makes prior Review stale or qualified | EVENTUAL / RECONCILIATION | Evidence Package + Review | Evidence Package reference | reconciliation process or governed review update | create review-staleness/reconciliation record |
| Campaign completion requires no active Runs | CROSS-AGGREGATE COMMAND-TIME | Campaign | bounded active-run summary or query | Campaign completion application service | Reject completion |
| Decision Candidate evidence sufficiency | GOVERNANCE GATE | Deferred | support set | future Decision Candidate governance gate | Deferred; not enforced in initial kernel |

No invariant is claimed locally enforceable when it requires data outside the aggregate.

## 22. Value Objects

Retained value objects:

- CampaignId;
- RunId;
- EvidencePackageId;
- ReviewId;
- RuntimeEntityId;
- AggregateVersion;
- TransitionSequence;
- Timestamp;
- ActorId;
- ScopeDefinition;
- IntegrityDigest;
- ObjectReference;
- CorrelationId for operational context only.

Deferred or narrowed:

- DatasetId is optional for Dataset Manifest external reference/reuse;
- AuditId is deferred with Audit;
- DecisionCandidateId is deferred with Decision Candidate;
- PersistenceRevision is deferred as an implementation concern;
- StateTransition is corrected to immutable StateTransitionRecord;
- CorrelationId is not domain identity.

## 23. Domain Event Vocabulary

Retained conceptual events:

| Event | Producer | Trigger | Minimum Payload | Future Outbox Requirement |
| --- | --- | --- | --- | --- |
| CampaignAuthorized | Campaign | READY_FOR_AUTHORIZATION to AUTHORIZED | Campaign ID, runtime UUID, AggregateVersion, TransitionSequence, actor, timestamp | Maybe |
| RunAuthorized | Run | CREATED to AUTHORIZED | Run ID, Campaign ID, AggregateVersion, TransitionSequence, actor, timestamp | Maybe |
| RunExecutionCompleted | Run | VALIDATING to EXECUTION_COMPLETED | Run ID, Evidence Package references if known, AggregateVersion, TransitionSequence | Maybe |
| EvidencePackageSealed | Evidence Package | COLLECTING to SEALED | Evidence Package ID, Run ID, AggregateVersion, TransitionSequence, digest summary | Likely later |
| EvidencePackageInvalidated | Evidence Package | SEALED to INVALIDATED | Evidence Package ID, invalidation reason, AggregateVersion, TransitionSequence | Likely later |
| ReviewCompleted | Review | IN_PROGRESS to COMPLETED | Review ID, target reference, disposition, AggregateVersion, TransitionSequence | Maybe |

Everything else is an internal transition record unless a later consumer or invariant purpose is identified. No outbox schema, event store, queue, or dispatcher is designed here.

## 24. Persistence Boundaries

Persistence requirements:

- Campaign, Run, Evidence Package, and Review require transactional metadata persistence.
- Dataset Manifest is persisted within Run boundary.
- Criterion Result is persisted within Evidence Package boundary.
- every aggregate root has one AggregateVersion.
- every lifecycle transition appends a StateTransitionRecord with TransitionSequence.
- PostgreSQL is authoritative for identities, lifecycle state, versions, transition history, references, and qualification records.
- object storage is not metadata source of truth.

Loading boundaries:

- Campaign does not load all Runs; completion uses bounded summaries, targeted queries, or future read models.
- Run does not load all historical manifests by default.
- Evidence Package may load package-scoped Criterion Results and artifact references; large collections require future read model/pagination.
- Review loads only target reference, assignment records, and bounded findings needed for a transition.

No schema, table, column, migration, ORM mapping, or repository API is defined.

## 25. Object-Storage Boundaries

PostgreSQL metadata is the authoritative index of artifact references. Object storage is the binary artifact store.

Disagreement rules:

| Case | Detected By | Domain Effect | Health Effect | Result/Error | Remediation Authority |
| --- | --- | --- | --- | --- | --- |
| metadata reference exists, object missing | integrity verification or review | Evidence Package cannot be verified; may be invalidated | object-storage dependency may remain healthy if service works | object-reference integrity failure | Evidence Manager or reviewer process |
| object exists, metadata missing | reconciliation or cleanup | object is not valid evidence | no domain health failure by itself | orphan-object reconciliation record | Evidence Manager / operations |
| digest mismatch | integrity verification | Evidence Package invalidation required or verification fails | no liveness failure by itself | digest-integrity failure | Evidence Manager |
| object replaced after seal | integrity verification | evidence invalidation; replacement is prohibited | no liveness failure by itself | sealed-object mutation violation | Evidence Manager plus audit/review authority |
| temporary object not finalized | collection reconciliation | cannot seal package | no health failure by itself | package-seal precondition failure | Evidence Manager |
| invalidated evidence object retained | retention policy | remains retained but disqualified | no health failure | retained-invalidated-artifact record | Archive/retention authority |
| cleanup failure | operations/reconciliation | record cleanup exception; evidence validity depends on seal/reference state | may affect dependency health only if service fails | cleanup exception record | operations authority |

ETag is not a cryptographic checksum. IntegrityDigest is stored and validated independently. No bucket, key, directory, or retention layout is defined.

## 26. Concurrency and Versioning

Corrected model:

- AggregateVersion: optimistic-concurrency token for aggregate mutation.
- TransitionSequence: append-only ordering of StateTransitionRecords inside an aggregate.
- StateTransitionRecord: immutable record, not a domain event by default.
- CorrelationId: operational trace context only.
- PersistenceRevision: deferred implementation concern.

Rules:

- stale AggregateVersion rejects mutation;
- duplicate command handling requires a future idempotency key design;
- rerun creates a new Run identity;
- review revision uses revision/supersession records;
- sealed Evidence Package cannot be edited into a new version; correction requires new package or invalidation/supersession record.

## 27. Deletion, Invalidation, and Archival

Lifecycle state, archival status, and invalidation records are separate concepts.

| Concept | Hard Delete | Invalidation | Archival | Restoration |
| --- | --- | --- | --- | --- |
| Campaign | only before external references and authorization | qualification may change through related evidence/review records | orthogonal archival record/status | future governed restoration only |
| Run | prohibited after authorization | failure/cancellation records; rerun creates new Run | orthogonal archival record/status | no restart; new Run only |
| Dataset Manifest | prohibited after creation | supersession record only | archived with Run | no direct restoration |
| Evidence Package | prohibited after seal | immutable invalidation record; contents unchanged | orthogonal archival record/status | no mutation restoration; new package/supersession required |
| Criterion Result | prohibited after seal | through package invalidation | archived with package | no direct restoration |
| Review | prohibited after start | supersession/revision record | orthogonal archival record/status | new Review/revision only |

Minimum tombstone data for any deleted pre-reference draft: governance ID if allocated, runtime UUID if allocated, deletion actor, timestamp, reason, and proof that no external reference exists.

## 28. Roles and Independence

Initial roles:

| Role | Type | Assignment Scope | Effective Time | Revocation/Reassignment | Delegation Rule | Conflict Constraint | Transition Authority |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Campaign Owner | Governance/domain role | Campaign | from assignment record until revocation or campaign terminal governance closure | allowed by governed assignment update | delegation requires recorded delegate and scope | cannot approve own independent Review | Campaign draft/readiness/cancellation |
| Campaign Operator | Domain assignment | Campaign or Run | from assignment record until revocation, Run terminal state, or Campaign closure | allowed before terminal state | delegation requires Campaign Owner approval record | cannot satisfy reviewer independence for own execution | Run creation/authorization request |
| Run Operator | Domain assignment | Run | from assignment record until revocation or Run terminal state | allowed with transition record | delegation requires Campaign Operator or Campaign Owner approval record | cannot independently review own Run | Run execution progression |
| Evidence Manager | Capability assignment | Evidence Package | from assignment record until revocation or package seal; post-seal authority limited to invalidation/supersession requests | allowed before seal; after seal requires supersession/invalidation authority | delegation requires recorded evidence-custody transfer | cannot independently review evidence they controlled | package collection/seal/invalidation request |
| Reviewer | Governance/domain role | Review | from assignment record until Review completion, cancellation, or reassignment | reassignment creates record; completed review not transferred | delegation prohibited for completed findings; reassignment only through Review Coordinator | cannot review evidence they executed, controlled, managed, calibrated, statistically approved, or own as outcome | Review lifecycle and disposition |
| Archive Authority | Governance/domain role | terminal aggregates | from assignment record until revocation or archive action completion | governed reassignment only | delegation requires archive governance record | cannot erase evidence/review history to resolve own conflict | archival records |

Deferred roles:

- Auditor;
- Decision-Preparation Authority.

Conflict-of-interest restrictions:

- Reviewer cannot review evidence they executed, controlled, or managed where independence applies.
- conflict records are immutable.
- conflict blocks Review start or completion until resolved by authorized reassignment or cancellation.
- no authorization system is implemented by this design.

## 29. Error and Failure Semantics

Domain failure concepts:

- invalid transition: reject command, no state change;
- invariant violation: reject command, no state change;
- stale AggregateVersion: reject command, no state change;
- independence conflict: block Review or require reassignment/cancellation;
- missing object or digest mismatch: fail verification and may invalidate Evidence Package;
- persistence/object-storage driver failures remain foundation errors at infrastructure boundaries and are not reclassified here.

No new foundation error category is introduced.

## 30. Deferred Concepts

Deferred:

- Audit runtime aggregate;
- Decision Candidate runtime aggregate;
- job ledger;
- transactional outbox;
- audit event ledger;
- governance registry ingestion;
- repository interfaces;
- APIs;
- workers;
- storage layouts;
- retention policy;
- physical persistence schema;
- authorization implementation;
- validation execution;
- vendor/trading behavior;
- Decision Freeze.

## 31. Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| External prior artifacts could be overclassified as freeze prerequisites | RESOLVED | registered artifacts are classified as non-normative evidence/design context unless explicitly marked authoritative |
| Dataset may later need global reuse | MINOR | optional DatasetId retained only when external reference/reuse is proven |
| Audit may need to return earlier than expected | MINOR | AuditId remains available; future process-compliance design can promote Audit |
| Decision Candidate may influence later storage | MINOR | boundary retained but runtime aggregate deferred |
| Read models may be needed early | MINOR | persistence boundary flags read models as future concern |

## 32. Design Issue Register

Original design issues preserved:

| Issue ID | Disposition |
| --- | --- |
| DOMAIN-DESIGN-ISSUE-0001 | Resolved by repository registration plus authority dependency classification |
| DOMAIN-DESIGN-ISSUE-0002 | Resolved by reduced entity model |
| DOMAIN-DESIGN-ISSUE-0003 | Resolved by Campaign/Run/Evidence/Review roots only |
| DOMAIN-DESIGN-ISSUE-0004 | Resolved by immutable findings and additive invalidation |
| DOMAIN-DESIGN-ISSUE-0005 | Resolved by deferring Decision Candidate |
| DOMAIN-DESIGN-ISSUE-0006 | Resolved by reduced event vocabulary |
| DOMAIN-DESIGN-ISSUE-0007 | Resolved by explicit no-layout object-storage rules |

Independent review issue dispositions:

| Review Issue | Disposition | Corrected Section | Remaining External Dependency |
| --- | --- | --- | --- |
| DOMAIN-REVIEW-ISSUE-0001 | Accepted and resolved | 4 | none for MILESTONE-012 freeze; external artifacts are informative/design context |
| DOMAIN-REVIEW-ISSUE-0002 | Accepted and resolved | 13 | none for MILESTONE-012 freeze |
| DOMAIN-REVIEW-ISSUE-0003 | Accepted and resolved | 13 | none for MILESTONE-012 freeze |
| DOMAIN-REVIEW-ISSUE-0004 | Accepted | 15 | none |
| DOMAIN-REVIEW-ISSUE-0005 | Accepted | 16, 18 | none |
| DOMAIN-REVIEW-ISSUE-0006 | Accepted | 18 | none |
| DOMAIN-REVIEW-ISSUE-0007 | Accepted and resolved for initial kernel | 19 | later Audit design requires its own authority review |
| DOMAIN-REVIEW-ISSUE-0008 | Accepted | 20 | later Decision Candidate design |
| DOMAIN-REVIEW-ISSUE-0009 | Accepted | 21 | none |
| DOMAIN-REVIEW-ISSUE-0010 | Accepted | 22, 26 | none |
| DOMAIN-REVIEW-ISSUE-0011 | Accepted | 23 | future outbox design |
| DOMAIN-REVIEW-ISSUE-0012 | Accepted | 24 | future repository design |
| DOMAIN-REVIEW-ISSUE-0013 | Accepted | 25 | future artifact policy may refine |
| DOMAIN-REVIEW-ISSUE-0014 | Accepted | 27 | future archive policy may refine |
| DOMAIN-REVIEW-ISSUE-0015 | Accepted | 28 | future authorization design |

## 33. Acceptance Criteria

| Criterion | Result |
| --- | --- |
| Review issues addressed | PASS |
| Reduced aggregate model adopted | PASS |
| Dataset over-modeling removed | PASS |
| Decision Candidate aggregate deferred | PASS |
| Audit treatment explicit | PASS |
| Campaign lifecycle no longer contains derived Review/Audit states | PASS |
| Run lifecycle separates execution from review outcome | PASS |
| Evidence Package no longer has REVIEWED state | PASS |
| Review lifecycle separated from disposition | PASS |
| Invariants classified by enforcement mode | PASS |
| Aggregate loading boundaries defined | PASS |
| Object-storage disagreement rules defined | PASS |
| Version model simplified | PASS |
| Archive/invalidation modeled orthogonally | PASS |
| Event vocabulary reduced | PASS |
| No implementation introduced | PASS |
| External baseline authority classified | PASS |

## 34. Quality Rubric

| Category | Max | Score | Rationale |
| --- | ---: | ---: | --- |
| Scope control | 20 | 20 | Design-only boundary preserved |
| Identifier integrity | 10 | 9 | dual identity corrected; optional DatasetId clarified |
| Entity necessity | 15 | 14 | reduced kernel removes premature entities |
| Aggregate correctness | 15 | 14 | initial roots are bounded and enforceable |
| Lifecycle correctness | 15 | 15 | derived/outcome states removed; authority classification confirms no external lifecycle blocker |
| Invariant enforceability | 10 | 10 | invariants classified by enforcement mode and authority boundary |
| Persistence/storage boundaries | 10 | 10 | no schema/layout; disagreement and loading rules added |
| Reversibility and anti-overengineering | 5 | 5 | Audit and Decision Candidate deferred |

Overall corrected score: 98 / 100.

## 35. Final Status

APPROVED AND FROZEN
