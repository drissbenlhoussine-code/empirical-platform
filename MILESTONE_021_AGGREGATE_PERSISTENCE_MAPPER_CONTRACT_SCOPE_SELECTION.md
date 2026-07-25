# MILESTONE-021 - Aggregate Persistence Mapper Contract Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-021 |
| Title | Aggregate Persistence Mapper Contract Scope Selection |
| Version | 1.0 |
| Status | SCOPE SELECTED - PENDING INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `40dd6b6a0c02e710e3f7efe84e8959af51f839f9` |
| Baseline status | MILESTONE-020 APPROVED AND FROZEN |
| Mission type | Scope selection only |
| Implementation performed | No |
| Source modified | No |
| Schemas, migrations, mappers, repositories, APIs, workers, runtime composition created | No |

## 2. Frozen Baseline

MILESTONE-020 freezes the domain-facing repository and optimistic-concurrency contract for Campaign, Run, EvidencePackage, and Review. The repository now contains, and this scope selection treats as authoritative:

- frozen aggregate creation and mutation behavior (M014-M018);
- frozen `AggregateVersion`, `TransitionSequence`, `StateTransitionRecord` primitives;
- frozen, internal, aggregate-specific reconstruction modules and `ReconstructionError`/`ReconstructionErrorCategory` (M019);
- frozen `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` Protocols exposing exactly `get`/`add`/`save` (M020);
- frozen `LoadedAggregate`, `SaveOperation`, `SaveResult`, and the five-member `RepositoryContractError` hierarchy (M020);
- PostgreSQL connectivity and low-level, single-statement unit-of-work primitives (`PersistenceService`, `PersistenceUnitOfWork` in `empirical_platform.shared.interfaces.persistence`; SQLAlchemy Engine/Core adapter in `empirical_platform.shared.persistence.postgres`) — verified live, connectivity-only, no domain schema or mapper;
- `migrations/versions/` verified empty (0 files) and `migrations/env.py` verified to declare `target_metadata = None` with an explicit "no business schemas or domain metadata are defined in this milestone" statement;
- no repository implementation, no persistence mapper, no schema, no migration revision, no serialization format, and no Unit of Work above the single low-level primitive exists anywhere in the repository.

The next milestone may therefore select a mapping-facing contract boundary, but must not implement mappers, schemas, migrations, concrete repositories, or storage behavior.

## 3. Current Persistence-Readiness Inventory

| Aggregate | Repository contract | Reconstruction state | Mapper exists | Schema exists | Mapping uncertainty |
| --- | --- | --- | --- | --- | --- |
| Campaign | `CampaignRepository` (frozen) | `CampaignReconstructionState` (frozen, internal) | No | No | How scope statement, lifecycle, and transition history become a persistence-neutral durable representation and back |
| Run | `RunRepository` (frozen) | `RunReconstructionState` (frozen, internal) | No | No | How the ordered `DatasetManifest` collection and Campaign-context identity are represented durably |
| EvidencePackage | `EvidencePackageRepository` (frozen) | `EvidencePackageReconstructionState` (frozen, internal) | No | No | How `CriterionResult`/`ArtifactReference` collections and Run-context identity are represented durably |
| Review | `ReviewRepository` (frozen) | `ReviewReconstructionState` (frozen, internal) | No | No | How ordered findings and terminal disposition metadata are represented durably |

Supporting inventory:

| Area | Repository evidence | Readiness |
| --- | --- | --- |
| Repository contracts | Frozen Protocols; `get`/`add`/`save`, `LoadedAggregate`, `SaveResult`, error taxonomy | Contract-ready, no implementation |
| Reconstruction | Frozen, internal `_reconstruct_*` factories per aggregate; only mapper/repository implementation code may call them (per M020 Design Section 24) | Ready for mapper design to target |
| PostgreSQL adapter | SQLAlchemy Engine/Core connectivity, probing, safe error translation, single-statement unit-of-work exist | Connectivity-ready, no schema or mapper |
| Migrations | `migrations/versions/` empty; `env.py` has no target metadata | No schema exists; nothing to migrate toward yet |
| Architecture permissions | Domain aggregate packages may not import persistence/SQLAlchemy/psycopg/boto3; this was verified unchanged through M020 | Correct for domain purity; mapper authorization must be explicit and narrow |

## 4. Remaining Uncertainty

MILESTONE-020's own Scope Selection document (Section 6, Candidate D) explicitly deferred persistence mapping as premature "until repository contract and concurrency boundary are known," and Candidate H (serialization contract alone) as premature because "mapping/serialization follows repository contract decisions." Both blockers are now resolved: the repository contract and concurrency boundary are frozen. The largest unresolved boundary is no longer repository semantics — it is: what a mapper is allowed to know, what it produces, how it fails, and where it lives, without yet choosing column types, tables, or SQL.

Unresolved questions that block implementation:

- whether a mapper operates directly on `_reconstruction` state records or on some other persistence-neutral intermediate representation;
- whether one mapper type exists per aggregate or a shared mapper contract-support shape is justified;
- what a "durable record" looks like in mapper-contract terms (field-level, not column-level);
- how mapper failures relate to the already-frozen `InvalidPersistedAggregateState`/`InvalidAggregateForPersistence` repository errors;
- whether mapping is symmetric (one type handles both directions) or split into separate load-mapping and save-mapping responsibilities;
- which module may import both a mapper and the internal `_reconstruction` factories, and how that stays consistent with the architecture checker;
- whether mapper contracts should anticipate multiple storage backends or assume PostgreSQL implicitly (still without specifying schema);
- how partial/atomic-write expectations already frozen at the repository level (M020 Design Section 25) constrain mapper output shape.

## 5. Candidate Milestones

| Candidate | Purpose | Disposition |
| --- | --- | --- |
| A. Persistence Mapper Contract Design | Define mapper responsibility, direction, failure boundary, and module placement for all four aggregates, without schema, SQL, or implementation. | Selected. |
| B. PostgreSQL Schema and Migration Design | Define tables, columns, constraints, indexes, history storage. | Rejected: schema shape depends on mapping decisions not yet made; would lock in storage layout prematurely, repeating the exact mistake M020 avoided for repository semantics. |
| C. Concrete Aggregate Repository Adapters | Implement `CampaignRepository` etc. against PostgreSQL. | Rejected: cannot implement a repository honestly without a mapper contract; would hard-code ad hoc mapping decisions inside adapter code, exactly the outcome M020 Candidate G rejected for repositories themselves. |
| D. Application-Service Orchestration | Define use-case-facing services calling repositories. | Rejected: no concrete repository exists yet for any service to call; multiple milestones premature. |
| E. Unit of Work / Transaction Boundary (multi-aggregate) | Define cross-aggregate transaction ownership. | Rejected: M020 Design Sections 18 and 26 explicitly defer multi-aggregate transactions and Unit of Work integration until single-aggregate mapper and repository implementation exist; still premature. |
| F. Serialization Format Only | Define wire/storage encoding without mapper responsibility boundary. | Rejected as its own milestone: M020's own scope selection already found this inseparable from mapping direction (Candidate H reasoning); splitting it out again would re-fragment one coherent decision into two artificially thin ones. |
| G. Repository Implementation Hardening Follow-Up | Add more M020 contract tests/hardening. | Rejected: M020 hostile review (implementation, then independent Codex correction) froze with no remaining blocker; nothing outstanding to harden. |
| H. No Implementation-Ready Next Scope | Stop because no prerequisite is ready. | Rejected: mapper contract design is ready and bounded now that M020 is frozen. |

## 6. Candidate Comparison

| Candidate | Architectural risk | Implementation risk | Unsupported-assumption risk | Schema lock-in risk | Scope-creep risk | Independent reviewability | Future milestones unlocked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | LOW | LOW | MEDIUM | LOW | MEDIUM | HIGH | Schema design, repository implementation, Unit of Work |
| B | HIGH | LOW | HIGH | HIGH | HIGH | MEDIUM | Concrete implementation, but prematurely |
| C | HIGH | HIGH | HIGH | HIGH | HIGH | LOW | Fragile pilot only, encodes hidden mapping choices |
| D | MEDIUM | MEDIUM | HIGH | LOW | HIGH | MEDIUM | Nothing yet buildable |
| E | MEDIUM | LOW | HIGH | LOW | HIGH | MEDIUM | Later orchestration, prematurely |
| F | MEDIUM | LOW | HIGH | MEDIUM | MEDIUM | MEDIUM | Partial only, re-fragments a coherent decision |
| G | LOW | LOW | LOW | LOW | LOW | HIGH | None material |
| H | LOW | LOW | LOW | LOW | LOW | HIGH | None |

## 7. Rejected Candidates

Candidate B is storage-shape work that depends entirely on whether mappers expose field-level durable records, reconstruction-state-shaped records, or something else; choosing tables first would repeat the exact premature-lock-in mistake M020's own scope selection explicitly avoided for repository semantics.

Candidate C is implementation before contract. A repository adapter written directly against PostgreSQL without a frozen mapper contract would hard-code serialization, null-handling, and durable-shape decisions inside adapter code — the same failure mode M020 Candidate G rejected for repository operations themselves.

Candidate D requires a concrete, working repository implementation to orchestrate against. None exists. Two milestones premature.

Candidate E requires multi-aggregate transaction semantics that M020 explicitly, deliberately deferred (Design Sections 18, 26); nothing about freezing M020 changes that.

Candidate F was already evaluated and rejected as a standalone unit by M020's own Candidate H reasoning; nothing has changed to make serialization separable from mapping direction now.

Candidate G is unnecessary: M020 is frozen with an independent-review correction cycle already completed and no outstanding finding.

Candidate H is not supported: the mapper-contract scope is reviewable now using live, frozen M019/M020 evidence, exactly as M020's own design anticipated.

## 8. Selected Milestone

Selected milestone:

```text
MILESTONE-021 - Aggregate Persistence Mapper Contract Design
```

The milestone is a design milestone. It must define, for Campaign, Run, EvidencePackage, and Review together, the persistence-neutral mapper contract that will eventually translate between frozen aggregate/reconstruction state and durable storage representation — without defining schemas, SQL, concrete repository implementations, or Unit of Work.

## 9. Milestone Type

MILESTONE-021 is:

```text
CONTRACT DESIGN ONLY
```

It is not implementation, schema design, migration authoring, repository coding, or persistence testing.

## 10. Exact Scope Boundary

In scope:

- mapper responsibility and placement relative to repository contracts and internal reconstruction factories;
- mapper contract layer-location comparison, mirroring the rigor M020 applied to repository placement;
- direction: load-mapping (durable representation to `_reconstruction` state to aggregate) and save-mapping (aggregate to durable representation);
- whether one bidirectional mapper contract exists per aggregate or load/save responsibilities split;
- the shape of a persistence-neutral "durable record" concept at the field level (not column/table level);
- how mapper-detected malformed durable data relates to the frozen `InvalidPersistedAggregateState`/`InvalidAggregateForPersistence` repository errors;
- which code may import both a mapper module and an aggregate's internal `_reconstruction` module, and the architecture-checker implications of that authorization;
- test expectations for a contract-only mapper design;
- explicit non-goals preventing schema/SQL/serialization-wire-format lock-in.

Out of scope:

- mapper implementation;
- PostgreSQL schema, tables, columns, indexes, constraints;
- migration revisions;
- SQL;
- concrete repository implementation;
- Unit of Work implementation or multi-aggregate transactions;
- runtime composition, APIs, workers;
- Audit, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior.

## 11. Aggregate Coverage

MILESTONE-021 covers all four frozen aggregate roots: Campaign, Run, EvidencePackage, Review. All-four coverage is required for the same reason M020 required it: a mapper contract that is consistent for only some aggregates would invite incompatible future mapper implementations. Aggregate-specific differences (owned collections, context identifiers) may be expressed as aggregate-specific mapper types or type parameters, but no one-aggregate pilot is authorized, mirroring M020 Section 11's equivalent constraint.

## 12. Required Deliverables (of the Design milestone, not of this scope selection)

The MILESTONE-021 Design document must deliver:

- exact mapper contract shape (methods, direction, inputs, outputs) for all four aggregates;
- exact module placement candidates and a placement decision, with architecture-checker impact analysis;
- exact error-translation boundary between mapper failures and the frozen repository error taxonomy;
- exact durable-record concept at field level, explicitly excluding column/table/SQL types;
- explicit compatibility statement against M019 (reconstruction) and M020 (repository) frozen contracts;
- deferred-work list matching this scope selection's "out of scope" section;
- a hostile self-review before the design is offered for independent review.

## 13. Test Obligations (to be defined by the Design, executed only in a future Implementation milestone)

The Design must specify, not implement, future test categories: mapper contract conformance per aggregate, error-translation correctness, absence of schema/SQL leakage, and no public exposure of `_reconstruction` factories through the mapper's public surface (mirroring M020 Section 29's equivalent obligations).

## 14. Architecture Constraints

The Design must:

- preserve `tools/check_architecture.py`'s existing `ALLOWED` and `FORBIDDEN_IMPORT_PREFIXES` tables as authoritative unless it explicitly proposes a narrow, justified addition (mirroring M020's approach of proposing no change where the existing tables already suffice);
- keep domain aggregate packages free of persistence/SQLAlchemy/psycopg/boto3 imports;
- keep `_reconstruction` factories internal, with mapper access explicitly authorized and narrow;
- not introduce a generic cross-aggregate mapper base class without explicit generic-versus-specific analysis, mirroring M020 Section 13's treatment of repository genericity.

## 15. Security Constraints

The Design must not introduce credential handling, connection-string construction, or secret material into the mapper contract; those remain the concern of the existing `PersistenceService`/`PersistenceUnitOfWork` infrastructure layer, unchanged by this milestone.

## 16. Stop Conditions

Stop MILESTONE-021 design if:

- mapper contract design requires schema or SQL decisions to be made first (would indicate the boundary was drawn wrong);
- mapper semantics would require changing frozen M019 reconstruction contracts or frozen M020 repository contracts;
- durable-record shape cannot be defined without picking a concrete storage technology;
- implementation work becomes necessary to answer a design question.

## 17. Acceptance Gate

MILESTONE-021 scope is acceptable only if:

- all four aggregates are covered;
- mapper responsibility and direction questions are enumerated;
- error-boundary integration with the frozen M020 taxonomy is included;
- schema, SQL, migration, implementation, and runtime work remain deferred;
- validation passes;
- only this scope-selection document is changed.

## 18. Hostile Self-Review

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M021-SCOPE-ISSUE-0001 | MAJOR | 8, 10 | Initial framing risked conflating mapper design with serialization-format design as two separate future milestones. | M020's own Candidate H reasoning already found these inseparable. | Could re-fragment one coherent decision, inviting a later milestone to redefine mapping direction. | Folded serialization-shape questions into this milestone's scope explicitly (Section 10) rather than deferring them to a distinct future milestone. | Resolved |
| M021-SCOPE-ISSUE-0002 | MAJOR | 3, 4 | Risk of assuming PostgreSQL-only mapping without stating that assumption explicitly. | Repository connectivity today is PostgreSQL-only (`shared.persistence.postgres`), but repository contracts (M020) are storage-neutral by design. | An implicit PostgreSQL assumption baked into mapper design could contradict the storage-neutral repository contracts it must serve. | Added explicit design question (Section 4) on whether mapper contracts anticipate multiple backends; left as a required Design-stage decision, not pre-decided here. | Resolved |
| M021-SCOPE-ISSUE-0003 | MINOR | 11 | Aggregate-specific collection differences (Run manifests, EvidencePackage dual collections, Review findings) could tempt a one-size mapper generic. | M020 Section 13 precedent explicitly warns against generic abstraction selected by habit. | Could produce a mapper abstraction that overfits before evidence justifies it. | Required explicit generic-versus-aggregate-specific analysis in the Design (Section 14), mirroring M020's own requirement. | Resolved |
| M021-SCOPE-ISSUE-0004 | MINOR | 2 | `migrations/env.py`'s "no business schemas" statement needed direct verification rather than assumed carry-forward from M020. | Read live: `target_metadata = None`, explicit comment confirmed. | Low; would have been a citation-accuracy gap only. | Verified directly and cited with file evidence in Section 2/3. | Resolved |

No unresolved scope-selection finding remains.

## 19. Final Decision

Selected next milestone:

```text
MILESTONE-021 - Aggregate Persistence Mapper Contract Design
```

Final status:

```text
SCOPE SELECTED - PENDING INDEPENDENT REVIEW
```
