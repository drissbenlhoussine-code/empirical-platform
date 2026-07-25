# MILESTONE-021 - Aggregate Persistence Mapper Contract Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-021 |
| Title | Aggregate Persistence Mapper Contract Design |
| Version | 1.0 |
| Status | DESIGN READY FOR INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Design baseline | `40dd6b6a0c02e710e3f7efe84e8959af51f839f9` |
| Scope authority | `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_SCOPE_SELECTION.md` |
| Mission type | Contract design only |
| Mapper interfaces implemented | No |
| Mapper implementations implemented | No |
| Schemas, migrations, SQL, repositories, APIs, workers, Unit of Work, runtime composition created | No |

## 2. Baseline

Repository facts at design time (verified live, not assumed):

- MILESTONE-019 aggregate reconstruction contract is frozen and implemented; `_reconstruct_campaign`, `_reconstruct_run`, `_reconstruct_evidence_package`, `_reconstruct_review` exist as internal factories in each aggregate's `_reconstruction.py`, each accepting an aggregate-specific `*ReconstructionState`.
- MILESTONE-020 domain repository and concurrency contract is frozen and implemented: `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` Protocols (`get`/`add`/`save`); `LoadedAggregate`, `SaveOperation`, `SaveResult`; `RepositoryContractError` and its five subclasses, all in `empirical_platform.shared.contracts`.
- `empirical_platform.shared.interfaces.persistence` provides `PersistenceService`/`PersistenceUnitOfWork` — connectivity, bounded raw-SQL execution, commit/rollback/health/close. No schema, no ORM model, no domain awareness.
- `empirical_platform.shared.persistence.postgres` is a SQLAlchemy Engine/Core adapter implementing those infrastructure Protocols. It has no knowledge of Campaign, Run, EvidencePackage, or Review.
- `migrations/versions/` is empty; `migrations/env.py` sets `target_metadata = None` and states no business schema exists yet.
- No mapper, no repository implementation, no schema, and no migration revision exists anywhere in the repository.

## 3. Problem Statement

MILESTONE-020 froze *what* a repository may be asked to do and *what optimistic concurrency means*, but deliberately left open *how* a future repository implementation turns a durable row into an aggregate and back. MILESTONE-020's own Section 24 already froze the **direction** of that flow:

```text
Load:  repository implementation -> mapper -> aggregate-specific ReconstructionState -> internal _reconstruct_* factory -> aggregate root
Save:  aggregate root -> mapper -> persistence representation -> atomic persistence
```

MILESTONE-021 defines the **mapper contract** that flow depends on: what a mapper is, what it produces and consumes, how its failures relate to the frozen repository error taxonomy, and where it may live — without yet choosing a database schema, a table layout, or SQL.

## 4. Frozen Facts This Design Must Not Contradict

- Repository contracts (M020) are already frozen: `get` returns `LoadedAggregate[AggregateT]`; `add`/`save` accept an aggregate and return `SaveResult`. A mapper contract must fit *underneath* these unchanged; it must not require any repository method signature to change.
- Reconstruction (M019) is already frozen: each aggregate's internal `_reconstruct_*` factory accepts exactly that aggregate's `*ReconstructionState` and performs its own structural validation, raising `ReconstructionError` on malformed input. A mapper must produce a `*ReconstructionState` (or fail before doing so) rather than duplicate reconstruction's own validation.
- `_reconstruction` modules are internal; M019 and M020 both keep them out of public exports. This design must name exactly which future code is authorized to import them (mapper implementation modules) without lifting that restriction generally.
- Repository save atomicity (M020 Section 25) already requires identity, lifecycle state, version, transition history, root scalar state, owned value objects, owned collections, and terminal metadata to be persisted atomically as one unit. A mapper's save-direction output must carry enough information for a future repository implementation to satisfy that atomicity guarantee; the mapper contract must not fragment that guarantee.

## 5. Design Principles

1. A mapper is domain-facing on one side (it knows aggregates and reconstruction states) and persistence-neutral on the other (it knows only a field-level durable record shape, never SQL, ORM sessions, or column types).
2. Mapping direction is symmetric in responsibility but asymmetric in mechanism: save-direction mapping is pure data transformation (aggregate to durable record); load-direction mapping produces a `*ReconstructionState` and then delegates to the already-frozen, already-validating `_reconstruct_*` factory — mapping does not re-implement reconstruction's structural validation.
3. A mapper never talks to a database, a session, a transaction, or an infrastructure adapter. It is a pure function boundary, callable and testable with in-memory values only.
4. A mapper never mutates an aggregate, never increments a version, and never appends transition history. Those remain aggregate-owned behaviors (frozen since M013-M018).
5. The mapper contract is intentionally minimal: one load-direction operation and one save-direction operation per aggregate.
6. No schema, table, column, index, SQL, or ORM type is named anywhere in this design.
7. No generic cross-aggregate mapper base class is selected without the same explicit generic-versus-specific comparison M020 required for repositories.

## 6. Mapper Architecture Options

| Option | Description | Type safety | Domain terminology | Genericity risk | Testability | Decision |
| --- | --- | --- | --- | --- | --- | --- |
| A | Generic `Mapper[AggregateT, DurableRecordT]` | Medium | Low | High | Medium | Rejected |
| B | Aggregate-specific mapper contracts | High | High | Low | High | Selected |
| C | Shared generic transform helpers plus aggregate-specific contracts | High | High | Medium | High | Rejected as premature framework, mirrors M020's rejection of the analogous Option C |
| D | Single shared mapper service with aggregate-kind branching | Low | Low | High | Low | Rejected |

Selected for the same reason M020 selected aggregate-specific repositories: the four aggregates' durable shapes are genuinely different (Run's ordered manifest collection, EvidencePackage's dual collections, Review's disposition metadata), and a generic mapper would either erase that domain vocabulary or be parameterized so loosely it enforces nothing. No aggregate-kind branching (Option D) is introduced; this also keeps the design consistent with M020 Section 8.1's explicit rejection of any `AggregateKind`-style discriminator.

## 7. Selected Mapper Architecture

```text
Aggregate-specific mapper contracts
```

Future contract names:

- `CampaignMapper`
- `RunMapper`
- `EvidencePackageMapper`
- `ReviewMapper`

Each exposes exactly two operations:

- `to_durable_record(aggregate) -> <Aggregate>DurableRecord` (save direction);
- `from_durable_record(record: <Aggregate>DurableRecord) -> <Aggregate>ReconstructionState` (load direction, feeding the already-frozen `_reconstruct_*` factory — the mapper does not call the factory itself; that remains the future repository implementation's responsibility, preserving M020 Section 24's frozen call direction).

No generic base Protocol is selected. A later implementation may extract shared field-level helpers (e.g. tuple materialization) only if it does not erase aggregate-specific contracts, mirroring M020 Section 7's identical allowance for repositories.

## 8. Contract Placement

| Option | Future module path | Strength | Risk | Decision |
| --- | --- | --- | --- | --- |
| Aggregate package mapper module | `empirical_platform.<aggregate>.mapper` | Consistent with M020's `<aggregate>.repository` placement; keeps mapper near aggregate and reconstruction-state vocabulary | Must not let aggregate modules import it back | Selected with import-direction rule |
| Shared persistence package | `empirical_platform.shared.persistence` | Reuses existing persistence boundary | Would require persistence to import aggregate-specific reconstruction state, inverting dependency direction (persistence has no `ALLOWED` entry for any domain package) | Rejected |
| New top-level mapper package | e.g. `empirical_platform.mapping` | Explicit separation | Adds a package not justified by evidence; M020 rejected the analogous option for repository contracts | Rejected |
| Application package | `empirical_platform.application` | Use-case ownership | Application layer does not yet exist | Rejected |

Selected future module paths:

- `empirical_platform.campaign.mapper`
- `empirical_platform.run.mapper`
- `empirical_platform.evidence.mapper`
- `empirical_platform.review.mapper`

Placement rules, mirroring M020 Section 8 exactly:

- aggregate modules must not import mapper modules;
- mapper modules may import their aggregate, its `_reconstruction` module (this is the one, explicit, narrow authorization this design grants — mapper modules are the "future mapper implementation" M019 and M020 both anticipated), identity, version, and durable-record types;
- mapper modules must not import SQLAlchemy, psycopg, boto3, PostgreSQL adapters, object storage adapters, schemas, or runtime composition;
- repository implementation modules (deferred) may depend on mapper contracts later.

Under `tools/check_architecture.py`'s `module_for_path`, a file at `src/empirical_platform/campaign/mapper.py` is classified under the existing "campaign" top-level module, exactly as `campaign/repository.py` was in M020. No new entry in `ALLOWED` is required: "campaign" already permits `identifiers` and `shared`, and same-top-level-module imports (`campaign.mapper` importing `campaign._reconstruction`) are already permitted regardless of the `ALLOWED` table. **No architecture-checker change is proposed or required by this design**, mirroring M020's identical outcome.

### 8.1 Durable-Record Type Placement

Following M020 Section 8.1's precedent of not over-freezing contract-support placement: the exact module for each `<Aggregate>DurableRecord` type is not frozen here. It must satisfy, at implementation time: dependency direction, architecture-checker compliance, no import cycle, and no leakage of aggregate-specific types into `shared`. The design's requirement is only that durable records remain field-level, persistence-neutral value objects, not their exact file location.

## 9. Aggregate Coverage

All four aggregates are covered, matching M020 Section 10-11's identical requirement and its rationale: a mapper contract inconsistent across aggregates would invite incompatible future mapper implementations.

| Mapper | Aggregate | Reconstruction state target | Durable record concept |
| --- | --- | --- | --- |
| `CampaignMapper` | `Campaign` | `CampaignReconstructionState` | Identity pair, scope statement text, lifecycle state text, version, transition history |
| `RunMapper` | `Run` | `RunReconstructionState` | Identity pair, Campaign context identifier, lifecycle state text, version, transition history, ordered manifest records |
| `EvidencePackageMapper` | `EvidencePackage` | `EvidencePackageReconstructionState` | Identity pair, Run context identifier, lifecycle state text, version, transition history, ordered criterion-result records, ordered artifact-reference records |
| `ReviewMapper` | `Review` | `ReviewReconstructionState` | Identity pair, target/reviewer references, lifecycle state text, version, transition history, ordered finding records, disposition/cancellation metadata |

## 10. Durable Record Concept (Field Level, Not Schema)

A durable record is a persistence-neutral, immutable value object naming the *fields* a mapper reads and writes, in domain vocabulary. It is not a table, not a SQLAlchemy model, not a column list, and specifies no SQL type, index, constraint, or normalization decision (single table versus multiple tables, JSON column versus relational rows for collections, and similar layout questions are explicitly deferred to a future schema-design milestone).

Worked example (Campaign; the same pattern applies to Run, EvidencePackage, and Review per Section 9's table, and is not repeated four times here to avoid schema-adjacent over-specification at contract-design stage):

```text
CampaignDurableRecord
- governance_id: str
- runtime_id: str
- scope_statement: str
- lifecycle_state: str
- version: int
- transition_history: tuple[CampaignTransitionDurableRecord, ...]

CampaignTransitionDurableRecord
- from_state: str | None
- to_state: str
- version: int
- sequence: int
- actor: str
- occurred_at: <persistence-neutral timestamp representation, exact type deferred>
- correlation_id: str | None
- reason: str | None
```

This is deliberately at the same level of detail M019's `*ReconstructionState` records already use (plain field values, no aggregate behavior) — a durable record is structurally close to a reconstruction state, differing only in that it is the mapper's I/O shape rather than the reconstruction factory's input shape. Whether they are ultimately the *same* type or two distinct types is an explicit open question this design resolves in Section 11, not assumed away.

## 11. Mapping Direction Detail

### 11.1 Save Direction

```text
aggregate -> mapper.to_durable_record(aggregate) -> <Aggregate>DurableRecord
```

- Pure transformation: reads the aggregate's public properties only (identity, version, lifecycle state, owned collections, transition history) — the same properties already exposed today for reconstruction-state comparison and testing.
- Never mutates the aggregate, never increments its version, never appends to its transition history.
- Produces one durable record covering everything M020 Section 25 already requires to be persisted atomically for that aggregate (root state, owned collections, transition history) — the mapper's output shape must not force a future repository implementation to split that atomic unit across separate, independently-failable writes.

### 11.2 Load Direction

```text
<Aggregate>DurableRecord -> mapper.from_durable_record(record) -> <Aggregate>ReconstructionState -> (future repository implementation calls) _reconstruct_<aggregate>(state) -> aggregate
```

- The mapper's `from_durable_record` produces a `*ReconstructionState`, not an aggregate. It does not call `_reconstruct_*` itself — that call remains the future repository implementation's responsibility, preserving M020 Section 24's exact frozen call chain (`repository implementation -> mapper -> ReconstructionState -> _reconstruct_* -> aggregate`) without collapsing two responsibilities into the mapper.
- `from_durable_record` may raise a mapper-level error for durable data that is structurally malformed *before* reconstruction even gets a chance to validate it (for example, a stored lifecycle-state string that matches no known enum member). It must not silently coerce or repair such data.
- Reconstruction's own validation (version floors, transition-history well-formedness, terminal-metadata rules — all frozen by M019) is not duplicated by the mapper. The mapper's job ends at producing a structurally-typed `*ReconstructionState`; `_reconstruct_*` remains the sole authority on domain-level validity.

## 12. Are Durable Records and Reconstruction States the Same Type?

Evaluated explicitly rather than assumed:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| Durable record *is* the `*ReconstructionState` type (mapper only does I/O, no separate type) | No duplicate type; less code | Couples the persistence-facing shape to M019's reconstruction-input shape; a future storage-driven need (e.g. a field present only for storage bookkeeping) would force reopening a frozen M019 type | Rejected |
| Durable record is a distinct, mapper-owned type; `from_durable_record` performs a second, purely mechanical transformation into `*ReconstructionState` | Keeps M019 reconstruction contracts fully frozen and untouched; isolates any future persistence-only concern inside the mapper's own type | One additional value type per aggregate | Selected |

Selected model: durable records are distinct, mapper-owned types. `*ReconstructionState` (M019, frozen) and `<Aggregate>DurableRecord` (M021) are related but not identical; the mapper is precisely the seam between them. This is the same reasoning M020 applied when it rejected exposing reconstruction state directly through repository contracts (Section 24: "repository interfaces do not expose reconstruction state records") — the same discipline now applies one layer deeper, keeping reconstruction state un-exposed to durable-record concerns as well.

## 13. Error Boundary

Mapper-level failures are distinguished from repository-level failures, and neither duplicates the other:

| Failure | Raised by | Surfaces to caller as |
| --- | --- | --- |
| Durable data structurally malformed (unknown enum string, wrong field type) before reconstruction can run | Mapper (`from_durable_record`) | Wrapped into the frozen `InvalidPersistedAggregateState` (M020) by the future repository implementation — the mapper itself raises a mapper-local error category, not the repository error type directly, keeping the mapper persistence-neutral and repository-error-vocabulary-free |
| Well-formed durable data but domain-invalid (bad version floor, malformed transition history) | `_reconstruct_*` factory (frozen, M019) via `ReconstructionError` | Also eventually wrapped into `InvalidPersistedAggregateState` by the future repository implementation, exactly as M020 Section 23 already specifies for `ReconstructionError` |
| Aggregate not valid for the save direction (e.g. an invariant a future mapper chooses to double-check) | Mapper (`to_durable_record`) | Wrapped into the frozen `InvalidAggregateForPersistence` (M020) by the future repository implementation |

The mapper contract itself defines a small, persistence-neutral error category for its own layer (name and exact shape deferred to implementation, mirroring M020 Section 8.1's identical deferral for contract-support placement) — it does not raise `RepositoryContractError` or any of its subclasses directly, since the mapper is not a repository and must remain callable and testable independent of any repository implementation.

## 14. Concurrency Semantics

The mapper contract has no concurrency semantics of its own. `AggregateVersion` is carried as plain data through the durable record (Section 10); optimistic-concurrency comparison remains entirely a repository-level concern, unchanged and unduplicated from M020 Sections 14-21. This design does not introduce, weaken, or reinterpret any concurrency rule already frozen by M020.

## 15. Persistence and Transaction Semantics

The mapper never opens a connection, session, or transaction, and never calls `PersistenceService`/`PersistenceUnitOfWork`. It is pure data transformation. Atomicity (M020 Section 25: root, collections, and history persisted together) is a constraint on the mapper's *output shape* (Section 11.1) but not a behavior the mapper itself performs; actually writing atomically remains a future repository implementation's responsibility using the existing infrastructure Unit of Work primitive. This design introduces no new transaction boundary and does not touch `PersistenceUnitOfWork`.

## 16. Reconstruction Integration

Preserves M020 Section 24's frozen direction exactly (see Section 4 and Section 11.2 above); does not alter it. `_reconstruct_*` factories remain internal; this design's only architecture authorization is that a future `<aggregate>/mapper.py` module may import its aggregate's `_reconstruction` module, narrowly, in addition to the reconstruction module itself (which already could import it, being in the same package).

## 17. Test Strategy (for a future Implementation milestone)

Required future test categories, defined here but not implemented:

- round-trip fidelity: `from_durable_record(to_durable_record(aggregate))` produces a `*ReconstructionState` that, once passed through the frozen `_reconstruct_*` factory, yields an aggregate indistinguishable from the original (same identity, version, lifecycle state, collections, and history) for every aggregate;
- malformed durable data raises the mapper's own error category rather than silently repairing or coercing it;
- mapper output never omits any field required for the repository-level atomicity guarantee (M020 Section 25);
- mappers do not mutate the aggregate passed to `to_durable_record`;
- no mapper module exposes `_reconstruction` factories or reconstruction state records as part of its own public surface beyond the one narrow, documented internal import;
- architecture tests proving mapper modules cannot import SQLAlchemy/psycopg/boto3/persistence, mirroring M020's three new fixtures.

## 18. Architecture Enforcement

No `tools/check_architecture.py` change is proposed or required (Section 8). A future Implementation milestone should add negative fixtures analogous to M020's (`bad_repository_boto3_import.py` etc.) proving mapper-shaped files still cannot import infrastructure — this design anticipates that obligation but does not create the fixtures itself, since no source exists yet to protect.

## 19. Security Considerations

No credential material, connection string, or secret ever appears in a durable record or mapper contract; those remain entirely the concern of the existing, unchanged `PersistenceService` infrastructure layer. This design introduces no new security surface.

## 20. Migration Implications

None. `migrations/versions/` remains empty after this design; no schema exists for a migration to target. This design's durable-record concept is deliberately field-level and storage-agnostic precisely so that a future schema-design milestone can choose table layout without this design constraining it more than field existence and domain meaning.

## 21. Compatibility with M019 and M020

- No frozen M019 aggregate, lifecycle, or reconstruction source file is modified or reinterpreted by this design.
- No frozen M020 repository contract, error type, or `SaveResult`/`LoadedAggregate` shape is modified.
- `_reconstruct_*` factories remain internal, called only by a future repository implementation (per M020 Section 24), never by the mapper itself (Section 11.2 above).
- Repository save atomicity (M020 Section 25) is preserved as a constraint on mapper output shape (Section 11.1), not reinterpreted.

## 22. Explicit Non-Goals

MILESTONE-021 must not:

- implement mappers;
- implement repositories;
- create schemas, migrations, tables, columns, indexes, or constraints;
- write SQL;
- alter PostgreSQL connectivity or the existing infrastructure Unit of Work primitive;
- implement multi-aggregate Unit of Work;
- implement runtime composition, APIs, workers;
- introduce Audit, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior;
- weaken, bypass, or duplicate any M019 reconstruction validation or M020 repository/concurrency semantics.

## 23. Deferred Work

Deferred after MILESTONE-021:

- mapper contract implementation;
- durable-record type implementation;
- repository implementations using the mapper contract;
- PostgreSQL schema and migrations;
- SQL and ORM mapping;
- Unit of Work integration beyond the existing single-statement primitive;
- application services, runtime composition, API and worker integration;
- read models and projections;
- Audit runtime, Decision Candidate, Decision Freeze.

## 24. Implementation Acceptance Gate (for a future Implementation milestone, not satisfied by this design)

A future MILESTONE-021 implementation must demonstrate, before it may be considered for freeze:

- all four mapper contracts exist with exactly the two operations each (Section 7);
- durable-record types are field-level and persistence-neutral, with no SQL/ORM/schema leakage;
- round-trip fidelity tests pass for all four aggregates (Section 17);
- error boundary tests confirm mapper errors are distinct from, and correctly wrapped into, the M020 repository error taxonomy;
- architecture checker and new negative fixtures pass with no rule weakened;
- no frozen M019 or M020 file is modified.

## 25. Hostile Self-Review

| ID | Severity | Section | Issue considered | Impact | Decision | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| M021-DESIGN-ISSUE-0001 | MAJOR | 11.2 | Initial draft risked letting the mapper call `_reconstruct_*` directly, collapsing two responsibilities M020 kept separate. | Would blur the frozen `repository implementation -> mapper -> state -> factory` chain from M020 Section 24. | Restricted the mapper's load-direction output to `*ReconstructionState` only; the future repository implementation calls the factory, not the mapper. | Resolved |
| M021-DESIGN-ISSUE-0002 | MAJOR | 12 | Considered making durable records identical to `*ReconstructionState` to avoid a second type. | Would couple frozen M019 reconstruction-input shape to future persistence-only concerns, risking pressure to reopen frozen M019 types later. | Selected a distinct, mapper-owned durable-record type; `*ReconstructionState` stays untouched and frozen. | Resolved |
| M021-DESIGN-ISSUE-0003 | MAJOR | 13 | Initial draft risked having the mapper raise `InvalidPersistedAggregateState` directly, coupling the mapper to repository-contract vocabulary. | Would make the mapper depend on `shared.contracts.repository` for its own error handling, blurring "mapper is persistence-neutral and repository-independent." | Mapper raises its own, smaller, mapper-local error category; wrapping into the M020 repository taxonomy is explicitly the future repository implementation's job. | Resolved |
| M021-DESIGN-ISSUE-0004 | MINOR | 10 | Considered fully specifying every field for all four aggregates. | Full column-by-column specification for four aggregates risks drifting into schema-adjacent detail this milestone must not decide. | Specified the concept once in full (Campaign) and named the equivalent concept for the other three via Section 9's table, deferring exhaustive enumeration to implementation. | Resolved |
| M021-DESIGN-ISSUE-0005 | MINOR | 8 | Considered whether mapper modules should live in a new top-level package instead of alongside each aggregate. | A new package was rejected for repositories in M020 for the same reason (unjustified package sprawl); nothing changed to justify it now for mappers. | Selected `<aggregate>.mapper`, mirroring `<aggregate>.repository` exactly. | Resolved |

All CRITICAL and MAJOR issues recorded in this self-review have proposed resolutions. Independent verification remains pending.

## 26. Acceptance Gate

| Gate | Result |
| --- | --- |
| Mapper architecture selected | PASS |
| Contract placement selected, no architecture-checker change required | PASS |
| All four aggregates covered | PASS |
| Load and save direction defined, consistent with frozen M020 Section 24 | PASS |
| Durable-record concept defined at field level only, no schema/SQL | PASS |
| Durable record vs. reconstruction state relationship explicitly decided | PASS |
| Error boundary defined and distinguished from M020 repository errors | PASS |
| Concurrency semantics unchanged from M020 | PASS |
| Transaction/persistence semantics unchanged from existing infrastructure primitive | PASS |
| Compatibility with M019 and M020 stated explicitly | PASS |
| Test strategy defined for a future implementation | PASS |
| Explicit non-goals stated | PASS |
| Hostile self-review performed | PASS |
| Independent review of this design | PENDING |
| MILESTONE-021 frozen | NO |

## 27. Final Decision

MILESTONE-021 selects aggregate-specific, persistence-neutral mapper contracts for Campaign, Run, EvidencePackage, and Review, each with exactly a save-direction and a load-direction operation, producing a distinct, mapper-owned durable-record type per aggregate, with mapper-local error handling wrapped into the frozen M020 repository error taxonomy only by a future repository implementation.

This document does not mark MILESTONE-021 approved, designed-frozen, or implemented. It requires independent review, then (if approved) a separate implementation milestone following the same design-then-implementation-then-freeze discipline used for MILESTONE-019 and MILESTONE-020.

Final status:

```text
DESIGN READY FOR INDEPENDENT REVIEW

NOT APPROVED
NOT FROZEN
```
