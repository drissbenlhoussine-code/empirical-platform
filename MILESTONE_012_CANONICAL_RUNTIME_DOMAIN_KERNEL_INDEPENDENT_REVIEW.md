# MILESTONE-012 - Canonical Runtime Domain Kernel Independent Review

## 1. Document Control

| Field | Value |
| --- | --- |
| Review Document | MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_INDEPENDENT_REVIEW.md |
| Reviewed Document | MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md |
| Repository Baseline | 7fd8a306bb3a2e33e9087d9415355284fdab0441 |
| Review Type | INDEPENDENT DESIGN REVIEW ONLY |
| Review Posture | Hostile, evidence-based |
| Implementation Performed | No |
| Final Review Status | REVISION REQUIRED |

## 2. Review Scope

This review challenges the MILESTONE-012 draft before correction, approval, freeze, or commit. It audits entity necessity, aggregate boundaries, relationships, lifecycle states, invariants, identifiers, review/audit independence, Decision Candidate boundaries, persistence requirements, object-storage assumptions, concurrency, archival, and overengineering risk.

## 3. Files and Evidence Reviewed

Repository evidence reviewed:

| Evidence | Path | SHA-256 |
| --- | --- | --- |
| MILESTONE-004 | `C:\Users\LuxSy\Documents\trading\MILESTONE_004_REPOSITORY_SCAFFOLDING_AND_TOOLCHAIN_BOOTSTRAP.md` | `401CBC4E1BB4723ABB7...` |
| MILESTONE-005 | `C:\Users\LuxSy\Documents\trading\MILESTONE_005_INFRASTRUCTURE_ARCHITECTURE.md` | `A28EEDECC53B998EB5F...` |
| MILESTONE-006 | `C:\Users\LuxSy\Documents\trading\MILESTONE_006_FOUNDATION_CONTRACTS.md` | `7329607E232D45C0042...` |
| MILESTONE-001-006 Integration Review | `C:\Users\LuxSy\Documents\trading\MILESTONE_001_006_DOCUMENT_INTEGRATION_REVIEW.md` | `8A6670A5445AB42C9AF...` |
| MILESTONE-007 | `C:\Users\LuxSy\Documents\trading\MILESTONE_007_FIRST_INFRASTRUCTURE_IMPLEMENTATION_SLICE.md` | `1F1159F6AB82054D793...` |
| MILESTONE-008 | `C:\Users\LuxSy\Documents\trading\MILESTONE_008_PERSISTENCE_CONNECTIVITY_FOUNDATION_SLICE.md` | `770E58BF0C5E486F412...` |
| MILESTONE-009 | `C:\Users\LuxSy\Documents\trading\MILESTONE_009_OBJECT_STORAGE_CONNECTIVITY_FOUNDATION_SLICE.md` | `8973792D234144F6727...` |
| MILESTONE-010 Scope | `C:\Users\LuxSy\Documents\trading\MILESTONE_010_SCOPE_SELECTION_AND_ARCHITECTURE_GAP_REVIEW.md` | `02C91FBDBE04D522DFB...` |
| MILESTONE-010 Runtime | `C:\Users\LuxSy\Documents\trading\MILESTONE_010_UNIFIED_INFRASTRUCTURE_RUNTIME_COMPOSITION.md` | `D822141EBB0408A2FF7...` |
| MILESTONE-011 | `C:\Users\LuxSy\Documents\trading\MILESTONE_011_SCOPE_SELECTION_AND_ARCHITECTURE_GAP_REVIEW.md` | `E8DA81287F32DA5796C...` |
| MILESTONE-012 Draft | `C:\Users\LuxSy\Documents\trading\MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` | `2958E57500B3068D909...` |

Located external evidence:

| Evidence | Path | SHA-256 | Status |
| --- | --- | --- | --- |
| MILESTONE-000D | `C:\Users\LuxSy\Desktop\MILESTONE_000D_EMPIRICAL_CAMPAIGN_ARCHITECTURE.md` | `6D42C95D326AC8A39460CA63435B429BF96196220D6E6B88A0C63ACB2912FDA0` | DRAFT / ARCHITECTURE UNDER REVIEW |
| MILESTONE-001 | `C:\Users\LuxSy\Desktop\MILESTONE_001_SYSTEM_IMPLEMENTATION_ARCHITECTURE.md` | `0840DE137D2DF7D97B9B2F24C84F0DBC3B0356B9A6E2F1C133D7965A768FB85C` | DRAFT / SYSTEM ARCHITECTURE UNDER REVIEW |
| MILESTONE-002 | `C:\Users\LuxSy\Desktop\MILESTONE_002_TECHNOLOGY_SELECTION_AND_ENGINEERING_BLUEPRINT.md` | `EDBAF15F0BE1D50589A4C6910635091FCF906D0BABAF71E9515F606F2BFBD75C` | DRAFT / ENGINEERING BLUEPRINT UNDER REVIEW |
| MILESTONE-003 | `C:\Users\LuxSy\Desktop\MILESTONE_003_PLATFORM_FOUNDATION_INITIALIZATION.md` | `82C05ACE8771C3E0B205E12156883065E6A5F3A23184D67ABDD3E3107775933E` | DRAFT / FOUNDATION UNDER REVIEW |
| MILESTONE-000C Framework | `C:\Users\LuxSy\Desktop\MILESTONE_000C_EMPIRICAL_VALIDATION_FRAMEWORK.md` | `9599631C7FC4D443E3EA754FB02D8F0BEB906FEBC626561CD1971E91020C0ECF` | DRAFT / FRAMEWORK UNDER REVIEW |
| MILESTONE-000C Campaign Standard | `C:\Users\LuxSy\Desktop\MILESTONE_000C_EMPIRICAL_VALIDATION_CAMPAIGN_STANDARD.md` | `7CAF2E0D2CBCD2DAFBAAC8B4FCB2085D2A50F1D917C85ACB20E794FEA7188855` | DRAFT / CAMPAIGN STANDARD UNDER REVIEW |
| Empirical Validation Protocol | `C:\Users\LuxSy\Desktop\MILESTONE_000B_4_PHASE2_CATEGORY1_EMPIRICAL_VALIDATION_PROTOCOL.md` | `C7434A843A197480D81E737AEFF53DC7B37DC1C42067D255DECF15E5741393A7` | DRAFT / PROTOCOL UNDER REVIEW |
| Evidence Artifact Specification | `C:\Users\LuxSy\Desktop\MILESTONE_000B_4_PHASE2_EVIDENCE_ARTIFACT_SPECIFICATION.md` | `B66C05CDFDBC74BF40C98D70F493E2A7F562645A5EEDD2974110E0B44E10BC74` | DRAFT / ARTIFACT SPECIFICATION UNDER REVIEW |
| Empirical Test Execution Runbook | `C:\Users\LuxSy\Desktop\MILESTONE_000B_4_PHASE2_EMPIRICAL_TEST_EXECUTION_RUNBOOK.md` | `3A04E4BA880EDA08CAF966462DB528B6FF07676CE3F2B928542B4082BC76522A` | DRAFT / RUNBOOK UNDER REVIEW |
| Master Governance Integration Standard | `C:\Users\LuxSy\Desktop\MASTER_GOVERNANCE_INTEGRATION_STANDARD.md` | `C2D6CA59034F36C531FB9D2B243F2BE5BA3911EF9B11130A987470D1D6BB1DAC` | DRAFT / VERSION 1.1 ACCEPTANCE CORRECTION PASS UNDER REVIEW |
| CAMP-0001 Proposal | `C:\Users\LuxSy\Desktop\CAMP-0001_CAMPAIGN_PROPOSAL.md` | `0130233E7D324E0AF90D1523E91DB0F0B25F8B6F8FDBFF8918B9C39A045FC3F5` | DRAFT |
| CAMP-0001 Authorization Review | `C:\Users\LuxSy\Desktop\CAMP-0001_AUTHORIZATION_REVIEW.md` | `7593AFF633C506FFC366BAA90A26931695EFE2DB7A5C81C0BEB3E2378A26361B` | DRAFT REVIEW COMPLETE / REMAIN_IN_DRAFT |

Source evidence reviewed: `src/empirical_platform`, `tests`, `migrations`, `infra`, `scripts`, `tools`, `docs`, `README.md`, and `pyproject.toml`.

## 4. Review Limitations

The external upstream artifacts were located on Desktop but are not repository-registered. Most are draft or under review. They can inform correction, but they cannot support freeze until their authority and revision state are reconciled. No source code or migration was modified.

## 5. Draft Summary

The draft proposes eight canonical runtime concepts: Campaign, Run, Dataset, Evidence Package, Criterion Result, Review, Audit, and Decision Candidate. It makes Campaign, Run, Evidence Package, Review, Audit, and Decision Candidate aggregate roots; Dataset is owned by Run; Criterion Result is owned by Evidence Package. It distinguishes governance identifiers from runtime UUIDs and keeps schemas, storage layouts, APIs, workers, job ledger, outbox, and Decision Freeze deferred.

## 6. Identifier Audit

The governance/runtime identifier split is directionally correct. `CAMP`, `RUN`, `DATASET`, `EVID`, `REVIEW`, `AUD`, and `DCAND` already exist as typed human-readable identifiers, while runtime UUIDs exist as opaque technical identifiers. The draft correctly prevents UUIDs from replacing governance IDs.

Weaknesses:

- allocation authority is conceptual but not operationally precise;
- pre-persistence allocation and reservation behavior is not defined;
- `Version` and `PersistenceRevision` overlap;
- `CorrelationId` is operational, not domain identity;
- `DatasetId` as a global governance ID may be too heavy if Dataset becomes an immutable manifest or owned record rather than an independently referenced entity.

## 7. Entity Necessity Audit

| Item | Independent Classification | Finding |
| --- | --- | --- |
| Campaign | REQUIRED AGGREGATE ROOT | Needed for authorization, scope, and lifecycle boundary |
| Run | REQUIRED AGGREGATE ROOT | Needed for execution attempt and rerun identity |
| Dataset | UNRESOLVED | May be an immutable owned record or manifest, not necessarily an entity with a full lifecycle |
| Evidence Package | REQUIRED AGGREGATE ROOT | Needed for seal, integrity, artifact references, and immutable evidence |
| Criterion Result | REQUIRED OWNED ENTITY | Better owned by Evidence Package than Run if it supports sealed evidence |
| Review | REQUIRED AGGREGATE ROOT | Independence and finding lifecycle justify separate root |
| Audit | UNRESOLVED | May be separate aggregate, specialized independent review, or later aggregate depending on governance evidence |
| Decision Candidate | UNRESOLVED / PREMATURE | Boundary is clear, but runtime aggregate timing is not yet justified |

The design is close, but it overstates Dataset and Decision Candidate maturity.

## 8. Aggregate Boundary Audit

Campaign is correctly prevented from owning all downstream records, but the Campaign lifecycle still reflects derived status from Run/Review/Audit. Run is a reasonable aggregate root, but owning all Datasets can become unbounded unless Dataset is treated as an append-only manifest record. Evidence Package is correctly separated for immutability. Review is justified. Audit may be justified, but the distinction from Review needs sharper output and authority boundaries. Decision Candidate as an aggregate root is premature unless the next implementation slice requires candidate persistence.

## 9. Relationship Audit

The relationship table is broadly coherent and avoids circular ownership. The strongest defect is propagation ambiguity: invalidated evidence affects Run, Review, Audit, Campaign completion, and Decision Candidate support, but the draft does not specify whether this is synchronous, audit-time, or eventually consistent for each reference. Deletion is appropriately conservative.

## 10. Campaign Lifecycle Audit

Campaign lifecycle has several derived or overloaded states:

- `REVIEW_IN_PROGRESS` and `AUDIT_IN_PROGRESS` are likely derived from related Review/Audit aggregates, not Campaign states;
- `COMPLETED_EVIDENCE_VALID` and `COMPLETED_EVIDENCE_INVALID` conflate campaign lifecycle with evidence disposition;
- `RUNNING` may be derived from active Runs;
- completion should likely use campaign-level states such as `COMPLETED`, with evidence validity captured by Review/Audit outcomes.

The Campaign model needs restructuring before freeze.

## 11. Run Lifecycle Audit

Run lifecycle is mostly coherent. Weaknesses:

- `VALID` and `INVALID` are review/evidence outcomes, not necessarily Run states;
- `RERUN_REQUIRED` is a disposition of a Review or Audit, but can be terminal for the old Run if modeled explicitly;
- acquisition, normalization, and validation states may belong to future execution-step records if the Run becomes too broad;
- cancellation after partial execution needs evidence preservation rules.

## 12. Dataset Lifecycle Audit

Dataset is the weakest entity. `PROPOSED`, `ACQUISITION_READY`, and `ARCHIVED` may be metadata statuses rather than lifecycle states. Dataset may be better modeled as:

- immutable Dataset Manifest record owned by Run;
- Dataset Snapshot reference owned by Evidence Package;
- later entity only if multiple Runs reuse or compare the same dataset.

The draft should not assume a full Dataset lifecycle before the acquisition and evidence model is implemented.

## 13. Evidence Lifecycle Audit

Evidence Package is strong overall. Defects:

- `REVIEWED` belongs more naturally to Review completion, not Evidence Package state;
- `INTEGRITY_VERIFIED` needs a sharper guarantee: object existence, digest match, metadata consistency, or all of these;
- invalidation should be an immutable invalidation record attached to the package, not necessarily a destructive state replacement;
- archive should be orthogonal status, not a lifecycle transition that changes historical truth.

## 14. Review Lifecycle Audit

Review as an aggregate root is justified. However:

- `COMPLETED_ACCEPTED` and `COMPLETED_REJECTED` conflate lifecycle with outcome;
- `CONFLICT_DECLARED` may be an assignment condition or finding, not a lifecycle state;
- findings should be immutable child records or records under Review, not mutable fields;
- revision/supersession policy is too thin.

## 15. Audit Lifecycle Audit

Audit remains under-specified relative to Review. The draft needs a sharper distinction:

- Review examines evidence/run fitness;
- Audit examines process compliance, independence, traceability, and review sufficiency.

`FINDINGS_ISSUED`, `COMPLETED_ACCEPTED`, and `COMPLETED_REJECTED` repeat the Review outcome problem. Audit can remain a separate aggregate, but only after authority, inputs, and outputs are made distinct enough.

## 16. Decision Candidate Audit

The draft correctly prevents Decision Candidate from becoming Decision Freeze, vendor selection, or trading authority. Critical weakness: Decision Candidate as a runtime aggregate is not clearly required before the first domain implementation. It may be better deferred or treated as governance-only until evidence, review, and audit support rules are implemented.

Missing lifecycle concerns:

- withdrawal;
- supersession;
- expiration;
- revision;
- stale support;
- partial invalidation of support set.

## 17. Invariant Audit

Strong invariants include one Campaign per Run, sealed evidence immutability, rerun new identity, no self-review/audit, and Decision Candidate not being Decision Freeze.

Weaknesses:

- several invariants are cross-aggregate and not locally enforceable under the proposed boundaries;
- supporting-evidence invalidation propagation is aspirational without an event/notification or audit-time reconciliation model;
- evidence sufficiency for Decision Candidate is not defined;
- archive restoration is rejected but no governed restoration record is designed.

## 18. Value Object Audit

Most value objects are appropriate. Problems:

- `Version` and `PersistenceRevision` should be consolidated or clearly separated;
- `StateTransition` overlaps with conceptual domain events and transition history;
- `ObjectReference` must include digest authority or be paired with `IntegrityDigest`;
- `CorrelationId` is operational tracing, not domain kernel state.

## 19. Event Vocabulary Audit

The draft correctly avoids outbox design, but event vocabulary is too broad for a pre-implementation kernel.

Classification:

- Necessary domain/transition records: `CampaignAuthorized`, `RunAuthorized`, `EvidencePackageSealed`, `EvidenceInvalidated`, `ReviewCompleted`, `AuditCompleted`.
- Premature integration events: `RunAcquisitionStarted`, `DatasetAccepted`, `DecisionCandidateCreated`.
- Internal transition records rather than external events: `CampaignPreparedForAuthorization`, `CampaignRunStarted`.

Every event needs known consumer or invariant purpose before later outbox design.

## 20. Persistence Boundary Audit

The draft avoids schema names and table names, which is correct. Risks:

- Campaign to all Runs and Run to all Datasets can become unbounded if aggregate loading is naive;
- Evidence Package to all Criterion Results may become large but is more defensible because it is evidence-scoped;
- history retention is required but not distinguished from event vocabulary;
- read-model needs are not identified.

The correction pass should define aggregate loading rules: roots must load only state needed for a transition, not every child record by default.

## 21. Object-Storage Boundary Audit

The draft correctly states PostgreSQL is metadata authority and object storage is artifact authority. It correctly avoids ETag as cryptographic checksum.

Missing:

- missing-object behavior after seal;
- digest mismatch behavior;
- object replacement prohibition after seal;
- database/object disagreement handling;
- retention-deferred does not mean deletion-validity undefined.

## 22. Concurrency and Versioning Audit

Optimistic concurrency is directionally correct. Weaknesses:

- one clear version model is missing;
- aggregate version, persistence revision, transition sequence, review revision, audit revision, and evidence versioning overlap;
- duplicate command handling requires idempotency keys, but none are named conceptually;
- Decision Candidate revisions and supersession are missing.

Recommendation: use one aggregate version plus append-only transition sequence; treat `PersistenceRevision` as implementation concern unless a separate purpose is proven.

## 23. Deletion, Invalidation, and Archival Audit

The no-destructive-deletion posture is correct. Weaknesses:

- `ARCHIVED` is often orthogonal lifecycle status, not a lifecycle state;
- `INVALIDATED` should often be an immutable invalidation record, not a replacement for the prior state;
- restoration paths are deferred too generally;
- tombstone requirements need explicit minimum data.

## 24. Role and Independence Audit

Roles are useful but not yet cleanly classified. Campaign Owner and Operator are domain roles; Reviewer, Auditor, Decision-Preparation Authority, and Archive Authority are governance/domain roles. Evidence Manager may be a capability rather than a person-role.

Missing:

- reassignment;
- revocation;
- delegation;
- acting authority;
- conflict resolution owner;
- enforcement mechanism for independence.

Do not invent an authorization system, but define required authority records.

## 25. Anti-Overengineering Review

Model A: minimum viable kernel:

- Campaign aggregate root;
- Run aggregate root;
- Evidence Package aggregate root;
- Review aggregate root;
- Dataset as immutable manifest/value object;
- Criterion Result owned by Evidence Package;
- Audit deferred or modeled as specialized Review;
- Decision Candidate deferred.

Model B: recommended canonical kernel:

- Campaign, Run, Evidence Package, Review aggregate roots;
- Audit as separate aggregate only if corrected to process-compliance scope;
- Decision Candidate as deferred aggregate, not first implementation target;
- Dataset as owned immutable record unless reuse/comparison requirements appear;
- Criterion Result owned by Evidence Package.

Model C: deferred future model:

- Decision Candidate aggregate;
- Audit aggregate if process-compliance use cases need independent lifecycle;
- job ledger/outbox;
- storage layout;
- read models;
- governance registry ingestion.

The MILESTONE-012 draft should move toward Model B.

## 26. Missing Prior Artifact Impact

| Artifact | Located | Impact | Severity | Correction Can Proceed | Freeze Can Proceed |
| --- | --- | --- | --- | --- | --- |
| MILESTONE-000D | Desktop only | Campaign architecture terms may alter entity/lifecycle names | MAJOR | Yes | No, not until registered/authoritative |
| MILESTONE-001 | Desktop only | System architecture lineage not repo-verified | MAJOR | Yes | No |
| MILESTONE-002 | Desktop only | Stack/blueprint lineage not repo-verified | MINOR | Yes | No |
| MILESTONE-003 | Desktop only | foundation initialization lineage not repo-verified | MINOR | Yes | No |
| MILESTONE-000C Framework | Desktop only | campaign/review/audit governance terms may affect lifecycle | MAJOR | Yes | No |
| Campaign Standard | Desktop only | Campaign/Run hierarchy may affect aggregate boundaries | MAJOR | Yes | No |
| Protocol/Artifact/Runbook | Desktop only | evidence and run terms may affect Dataset/Evidence lifecycle | MAJOR | Yes | No |
| CAMP-0001 docs | Desktop only | draft campaign terms may inform future examples only | MINOR | Yes | No |

Correction can proceed. Approval/freeze should not proceed until a baseline registration or document import mission records these artifacts as authoritative inputs.

## 27. Independent Issue Register

| Issue ID | Affected Section | Exact Defect | Severity | Consequence | Correction | Prior Artifact Verification Required | Blocks Correction | Blocks Freeze |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DOMAIN-REVIEW-ISSUE-0001 | 4, 26 | Prior authoritative artifacts are Desktop-only and mostly draft | MAJOR | Freeze would rely on unregistered evidence | Register/import prior artifacts and reconcile statuses | Yes | No | Yes |
| DOMAIN-REVIEW-ISSUE-0002 | 13 | Campaign lifecycle contains derived Review/Audit states | MAJOR | Campaign state becomes coupled to child aggregates | Replace with campaign-level states and derive review/audit progress from related aggregates | Yes | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0003 | 13 | `COMPLETED_EVIDENCE_VALID/INVALID` conflate campaign completion and evidence disposition | MAJOR | Completion semantics become ambiguous | Separate Campaign completion from evidence validity outcomes | Yes | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0004 | 15 | Dataset is over-modeled as a full lifecycle entity | MAJOR | Premature schema and aggregate design pressure | Reclassify Dataset as owned immutable manifest/record unless reuse requires entity | Yes | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0005 | 16 | Evidence Package `REVIEWED` duplicates Review aggregate result | MAJOR | Cross-aggregate lifecycle contradiction | Remove `REVIEWED` or treat review status as derived/reference | Yes | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0006 | 18, 19 | Review/Audit outcomes are modeled as lifecycle states | MAJOR | Lifecycle and disposition semantics are conflated | Split lifecycle from outcome/disposition records | Yes | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0007 | 19 | Audit purpose is not distinct enough from Review | MAJOR | Duplicate aggregate root risk | Define Audit as process-compliance independent assessment or defer it | Yes | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0008 | 20 | Decision Candidate aggregate timing is premature | MAJOR | Pre-freeze governance concept may become premature runtime schema | Defer aggregate or mark as later aggregate with current reference rules only | Yes | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0009 | 21 | Several invariants require cross-aggregate data without enforcement path | MAJOR | Aspirational invariants cannot be enforced locally | Mark each invariant local, synchronous cross-reference check, or audit-time reconciliation | No | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0010 | 22, 26 | Version/PersistenceRevision/transition sequence overlap | MINOR | Confusing concurrency model | Use aggregate version plus transition sequence; defer persistence revision | No | No | Yes |
| DOMAIN-REVIEW-ISSUE-0011 | 23 | Event vocabulary includes premature integration events | MINOR | Outbox pressure before known consumers | Reclassify events as transition records unless consumer exists | No | No | No |
| DOMAIN-REVIEW-ISSUE-0012 | 24 | Aggregate loading boundaries are not specified | MAJOR | Future repositories may load unbounded child collections | Define transition-specific loading boundaries | No | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0013 | 25 | Object-storage disagreement behavior is incomplete | MAJOR | Missing object or digest mismatch validity is unclear | Define missing-object, digest mismatch, and replacement behavior | Yes | Yes | Yes |
| DOMAIN-REVIEW-ISSUE-0014 | 27 | ARCHIVED and INVALIDATED are overused as lifecycle states | MINOR | Lifecycle history and archival status may be distorted | Treat archive and invalidation as orthogonal records where appropriate | No | No | Yes |
| DOMAIN-REVIEW-ISSUE-0015 | 28 | Role authority lacks assignment/revocation/delegation model | MINOR | Independence enforcement remains vague | Define authority records without implementing auth | Yes | No | Yes |

## 28. Required Corrections

1. Register or explicitly reference the Desktop prior artifacts before any freeze decision.
2. Restructure Campaign lifecycle to remove derived review/audit and evidence-validity states.
3. Reclassify Dataset as immutable owned manifest/record unless prior artifacts prove entity reuse is required.
4. Remove Evidence Package `REVIEWED` as a native state or make it derived.
5. Split Review/Audit lifecycle from outcome/disposition.
6. Clarify Audit's unique purpose or defer it.
7. Defer Decision Candidate as a runtime aggregate or narrow it to a reference-only future aggregate.
8. Reclassify invariants by local, cross-reference, and audit-time enforcement.
9. Define one version/concurrency model.
10. Define aggregate loading boundaries.
11. Define missing-object and digest-mismatch behavior.
12. Clarify archive/invalidation as state versus orthogonal record.

## 29. Recommended Entity/Aggregate Model

Recommended correction target:

| Concept | Recommended Model |
| --- | --- |
| Campaign | Aggregate root |
| Run | Aggregate root |
| Dataset | Immutable owned manifest/record under Run for now |
| Evidence Package | Aggregate root |
| Criterion Result | Owned entity under Evidence Package |
| Review | Aggregate root with immutable findings |
| Audit | Separate aggregate only if narrowed to process-compliance assessment; otherwise defer |
| Decision Candidate | Deferred runtime aggregate; retain boundary rules and references only |

This model preserves future migration paths while reducing premature schema and lifecycle lock-in.

## 30. Approval Readiness

MILESTONE-012 is not ready for approval or freeze. It is ready for a correction pass. No CRITICAL issue was found. The design does not require a total rewrite, but it does require material restructuring of entity classification, lifecycle models, and enforceability language.

## 31. Independent Score

| Category | Max | Score | Rationale |
| --- | ---: | ---: | --- |
| Identifier integrity | 10 | 8 | Good governance/runtime split; allocation and version overlap remain |
| Entity necessity | 10 | 6 | Dataset, Audit, and Decision Candidate are not fully justified |
| Aggregate correctness | 15 | 10 | Main roots are plausible, but some are premature or duplicated |
| Lifecycle correctness | 15 | 8 | Several lifecycle/disposition/derived-state conflations |
| Invariant enforceability | 10 | 7 | Strong intent but cross-aggregate enforcement is vague |
| Review/Audit/independence model | 10 | 7 | Independence recognized; Audit/Review distinction weak |
| Decision Candidate boundary | 5 | 4 | Freeze boundary strong; runtime timing weak |
| Persistence/storage boundaries | 10 | 8 | Good no-schema discipline; loading/disagreement rules missing |
| Concurrency/versioning | 5 | 3 | Overlapping version terms |
| Anti-overengineering and reversibility | 5 | 3 | Over-modeled Dataset and premature Decision Candidate |
| Traceability/evidence completeness | 5 | 3 | Desktop artifacts found but not registered/authoritative |

Independent score: 67 / 100.

## 32. Final Review Status

REVISION REQUIRED
