# MILESTONE-020 - Domain Repository and Concurrency Contract Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-020 |
| Title | Domain Repository and Concurrency Contract Scope Selection |
| Version | 1.0 |
| Status | SCOPE CANDIDATE SELECTED |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `22c064691564955b0a1f2a3e9cb6791b61dd8261` |
| Baseline status | MILESTONE-019 APPROVED AND FROZEN |
| Mission type | Scope selection only |
| Implementation performed | No |
| Source modified | No |
| Schemas, migrations, repositories, mappers, APIs, workers, runtime composition created | No |

## 2. Frozen Baseline

MILESTONE-019 freezes the aggregate reconstruction contract for Campaign, Run, EvidencePackage, and Review. The repository now contains:

- frozen aggregate creation and mutation behavior from M014 through M018;
- frozen `AggregateVersion`, `TransitionSequence`, and `StateTransitionRecord` primitives;
- internal aggregate-specific reconstruction modules;
- immutable reconstruction state records;
- reconstruction validation and malformed-state rejection;
- PostgreSQL connectivity and unit-of-work foundation without domain schemas;
- empty `migrations/versions`.

The next milestone may therefore select a persistence-facing contract boundary, but must not implement repositories, mapping, schema, runtime orchestration, or storage behavior.

## 3. Current Persistence-Readiness Inventory

| Aggregate | Creation available | Mutation behavior frozen | Reconstruction available | Reconstruction state available | Identity | Version | Owned collections | Transition history | Terminal metadata | Potential repository operations | Potential concurrency boundary | Mapping uncertainty | Schema uncertainty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Campaign | Yes | Yes | Yes | Yes | `DomainIdentity[CampaignId]` | Domain-managed `AggregateVersion` | Current `CampaignScopeStatement` only | Tuple of Campaign transition records | Reasons in transition history only | Load by `CampaignId`; save aggregate; create conflict detection | Expected persisted aggregate version | Scope/value encoding and history storage | Table shape, unique keys, history layout |
| Run | Yes | Yes | Yes | Yes | `DomainIdentity[RunId]` plus `CampaignId` context | Domain-managed `AggregateVersion` | Ordered `DatasetManifest` tuple | Tuple of Run transition records | Reasons in transition history only | Load by `RunId`; save aggregate; create conflict detection | Expected persisted aggregate version | Manifest child encoding and order | Root/manifest/history table choices |
| EvidencePackage | Yes | Yes | Yes | Yes | `DomainIdentity[EvidencePackageId]` plus `RunId` context | Domain-managed `AggregateVersion` | Ordered `CriterionResult` and `ArtifactReference` tuples | Tuple of EvidencePackage transition records | Invalidation reason in transition history | Load by `EvidencePackageId`; save aggregate; create conflict detection | Expected persisted aggregate version | Result/reference encoding and uniqueness | Root/result/reference/history table choices |
| Review | Yes | Yes | Yes | Yes | `DomainIdentity[ReviewId]` | Domain-managed `AggregateVersion` | Ordered `ReviewFinding` tuple | Tuple of Review transition records | Disposition, rationale, cancellation reason | Load by `ReviewId`; save aggregate; create conflict detection | Expected persisted aggregate version | Finding and terminal metadata encoding | Root/finding/history table choices |

Supporting persistence inventory:

| Area | Repository evidence | Readiness |
| --- | --- | --- |
| Shared persistence interface | `PersistenceService` and `PersistenceUnitOfWork` provide connectivity, bounded SQL execution, commit, rollback, health, and close. | Infrastructure-ready, not domain-repository-ready |
| PostgreSQL adapter | SQLAlchemy Engine/Core connectivity, probing, safe error translation, and unit-of-work lifecycle exist. | Connectivity-ready, no domain schema or mapper |
| Transaction support | Single low-level unit of work exists; nested units rejected. | Available as infrastructure primitive, not yet domain transaction policy |
| Migration state | `migrations/versions` is empty. | No schema exists |
| Architecture permissions | Domain packages may not import persistence/SQLAlchemy/psycopg/boto3; reconstruction remains internal. | Correct for domain purity; future repository/mapping authorization must be explicit |

## 4. Remaining Uncertainty

The largest unresolved persistence boundary is not table shape. It is the domain-facing contract: what callers may ask repositories to load/save, what concurrency protection means, what errors are domain-facing, and how reconstruction remains internal while repository implementations restore aggregates.

Unresolved questions that block implementation:

- whether `save` covers both create and update or whether `add` and `save` are separate;
- whether load returns an optional result or raises a not-found error;
- how duplicate identity on create is represented;
- how expected persisted version is supplied;
- how stale writes are rejected;
- whether save returns no value, a version, or an aggregate;
- whether unchanged aggregate saves are permitted;
- whether list/query operations belong in repositories or future read models;
- how reconstruction errors are wrapped or surfaced;
- which layer owns repository contract errors;
- which future mapper path may call underscore reconstruction modules.

## 5. Candidate Milestones

| Candidate | Purpose | Disposition |
| --- | --- | --- |
| A. Domain Repository Contract Design | Define load/save contracts only. | Rejected: cannot define save honestly without concurrency semantics. |
| B. Optimistic Concurrency Contract Design | Define expected-version and stale-write semantics only. | Rejected: concurrency semantics need repository operation context. |
| C. Repository and Concurrency Contract Design | Define repository operations and optimistic-concurrency contract together, without mapping/schema/implementation. | Selected. |
| D. Persistence Mapping Design | Define reconstruction-state-to-storage mapping without schemas. | Rejected as premature until repository contract and concurrency boundary are known. |
| E. Transaction Boundary / Unit-of-Work Design | Define transaction ownership and atomicity across aggregate persistence. | Rejected as premature beyond single-aggregate repository contract atomicity. |
| F. PostgreSQL Schema and Migration Design | Define tables, constraints, indexes, and history storage. | Rejected as premature schema lock-in. |
| G. One-Aggregate Repository Pilot | Implement one aggregate repository. | Rejected; implementation before contract would encode hidden semantics. |
| H. Serialization Contract Design | Define persistence-neutral serialization for reconstruction states. | Rejected; mapping/serialization follows repository contract decisions. |
| I. Reconstruction Hardening Follow-Up | Add more reconstruction tests/architecture hardening. | Rejected; M019 hostile review froze reconstruction with no remaining blocker. |
| J. No Implementation-Ready Next Scope | Stop because no prerequisite is ready. | Rejected; repository/concurrency contract design is ready and bounded. |

## 6. Candidate Comparison

| Candidate | Architectural risk | Implementation risk | Unsupported-assumption risk | Schema lock-in risk | Scope-creep risk | Independent reviewability | Future milestones unlocked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | MEDIUM | LOW | HIGH | LOW | MEDIUM | HIGH | Partial only |
| B | MEDIUM | LOW | HIGH | LOW | LOW | MEDIUM | Partial only |
| C | LOW | LOW | MEDIUM | LOW | MEDIUM | HIGH | Repository design, mapper design, schema design, implementation |
| D | MEDIUM | LOW | HIGH | MEDIUM | HIGH | MEDIUM | Mapping only |
| E | MEDIUM | LOW | HIGH | LOW | HIGH | MEDIUM | Later orchestration |
| F | HIGH | LOW | HIGH | HIGH | HIGH | MEDIUM | Schema implementation, but prematurely |
| G | HIGH | HIGH | HIGH | HIGH | HIGH | LOW | Fragile pilot only |
| H | MEDIUM | LOW | HIGH | MEDIUM | MEDIUM | MEDIUM | Serialization only |
| I | LOW | LOW | LOW | LOW | LOW | HIGH | None material |
| J | LOW | LOW | LOW | LOW | LOW | HIGH | None |

## 7. Rejected Candidates

Candidate A is too narrow because a repository contract that says `save(aggregate)` but leaves expected-version semantics open would invite incompatible implementations.

Candidate B is too abstract because concurrency without repository operations cannot decide create conflicts, not-found behavior, unchanged saves, or save results.

Candidates D, F, and H are storage-shape work. They depend on whether repositories expose aggregates only, reconstruction state, result objects, or lower-level mapper contracts.

Candidate E is deferred because current frozen behavior is process-local and single-aggregate; multi-aggregate transactions are not yet authorized.

Candidate G is implementation before contract and would likely hard-code mapper, schema, and concurrency decisions.

Candidate I is unnecessary because M019 is frozen with reconstruction evidence and an external-review package.

Candidate J is not supported because the next contract-design scope is reviewable using current repository evidence.

## 8. Selected Milestone

Selected milestone:

```text
MILESTONE-020 - Domain Repository and Concurrency Contract Design
```

The milestone is a design milestone. It must define domain-facing repository contracts and optimistic-concurrency semantics together for Campaign, Run, EvidencePackage, and Review. It must remain persistence-neutral and must not define storage mapping, database schemas, migrations, concrete SQL, infrastructure adapters, runtime composition, APIs, workers, or Unit-of-Work implementation.

## 9. Milestone Type

MILESTONE-020 is:

```text
CONTRACT DESIGN ONLY
```

It is not implementation, schema design, mapper design, runtime integration, repository coding, or persistence testing.

## 10. Exact Scope Boundary

In scope:

- repository contract purpose and placement;
- repository contract layer-location comparison;
- aggregate coverage and identity inputs;
- synchronous versus asynchronous contract shape;
- load/not-found semantics;
- load identity shape, locking, tracking, and caching semantics;
- create/update/save semantics;
- duplicate identity semantics;
- optimistic-concurrency contract;
- expected persisted version semantics;
- explicit aggregate-version vocabulary;
- stale-write and create-conflict errors;
- invalid persisted state boundary;
- save result shape;
- aggregate version ownership;
- reconstruction integration direction;
- future mapper authority;
- architecture checker implications;
- test expectations for contract-only design.

Out of scope:

- repository implementation;
- mapper implementation;
- serialization format;
- PostgreSQL schema;
- migration revisions;
- SQL;
- concrete transaction orchestration;
- runtime composition;
- APIs, workers, outbox, Audit, Decision Candidate, Decision Freeze, trading, vendor behavior, or empirical execution.

## 11. Aggregate Coverage

MILESTONE-020 covers all four frozen aggregate roots:

- Campaign;
- Run;
- EvidencePackage;
- Review.

All-four coverage is justified because the repository/concurrency contract must be consistent for every reconstructed aggregate. Aggregate-specific differences may be expressed as separate interfaces or type parameters, but no one-aggregate pilot is authorized.

## 12. Repository Operation Questions

MILESTONE-020 must answer:

- whether repositories are aggregate-specific, generic, or shared primitives plus aggregate-specific interfaces;
- whether repository contracts are synchronous or asynchronous;
- whether load accepts canonical `DomainIdentity[...]`, raw aggregate IDs, or aggregate-specific identity parameters;
- whether load returns aggregate roots only;
- whether repository interfaces expose reconstruction states;
- whether `get`/`load` returns optional, result type, or raises not-found;
- whether repository load behavior is tracked, detached, or explicitly outside identity-map semantics;
- whether repository contracts include locking terms or defer lock mechanics to later implementation design;
- whether repository contracts include cache semantics or explicitly prohibit cache assumptions;
- whether `add` and `save` are separate;
- whether update requires an expected persisted version;
- whether create requires proof of non-existence;
- whether unchanged save is allowed and what it returns;
- whether repeated idempotent saves are valid, rejected, or implementation-defined;
- whether save accepts an explicit transaction context or remains transaction-context-neutral;
- whether delete is prohibited;
- whether list/query/read-model operations are excluded;
- whether cross-aggregate loading is prohibited;
- whether repository methods mutate aggregate versions.

## 13. Generic Versus Aggregate-Specific Analysis

MILESTONE-020 must evaluate:

| Option | Strength | Risk |
| --- | --- | --- |
| Generic `Repository[Identity, Aggregate]` | Consistent operation names and reusable tests | May erase domain language and overfit before aggregate query needs are known |
| Aggregate-specific contracts | Strong type safety and domain vocabulary | Repetition if operations are truly identical |
| Shared save/load primitives plus aggregate-specific interfaces | Balances consistency and domain specificity | Requires careful boundary to avoid a premature framework |

No generic repository abstraction may be selected merely because operations look similar.

MILESTONE-020 must also compare repository contract placement options:

| Location option | Strength | Risk |
| --- | --- | --- |
| Aggregate domain packages | Keeps contracts next to aggregate vocabulary | May pull persistence-facing concerns into pure domain packages |
| Application package | Keeps domain pure and expresses use-case-facing ownership | May create an application layer before use cases exist |
| Shared persistence package | Reuses existing persistence boundary | Would likely leak aggregate concepts into infrastructure primitives |
| New repository-contract package | Creates an explicit stable contract layer | Adds a package that must be justified by architecture rules |
| Aggregate-specific repository packages | Preserves aggregate isolation and type clarity | May duplicate common contract concepts |

The design must select or defer contract location with explicit dependency-direction reasoning. It must not rely on package convenience, and it must identify any future architecture-checker rule changes required by the selected location.

## 14. Concurrency Questions

MILESTONE-020 must define:

- expected persisted state for a new aggregate;
- insert/create conflict behavior;
- existing aggregate expected version;
- compare-and-swap boundary in contract terms, not SQL terms;
- stale-write rejection;
- persistence-managed versus domain-managed version ownership;
- idempotent repeated save semantics;
- save of unchanged aggregate;
- concurrent creation;
- transaction retry ownership;
- conflict error ownership.

The initial evidence favors domain-managed `AggregateVersion`: aggregate public behavior increments versions before save. Repository save must not increment aggregate versions unless a later design explicitly supersedes this.

MILESTONE-020 must keep these version concepts distinct:

- aggregate current domain version: the version currently held by the in-memory aggregate after domain behavior has run;
- persisted version observed when loaded: the version known to have existed in storage at reconstruction/load time;
- expected persisted version supplied on save: the caller-provided concurrency precondition for update;
- new-aggregate no-persisted-version state: the create precondition for an aggregate that must not already exist.

The design must explicitly reject or justify blind overwrite saves. It must also compare save result shapes including no return value, persisted-version return, typed save-result object, updated aggregate return, and repository-token return.

## 15. Reconstruction Integration

The selected design must preserve this direction:

```text
future repository implementation
    -> future persistence mapper
        -> aggregate-owned internal _reconstruction module
            -> aggregate
```

MILESTONE-020 must decide whether repository contracts know only aggregates and identities, while mappers know reconstruction state. The default assumption to test is:

- domain-facing repositories return aggregate roots;
- mappers translate durable state into reconstruction states;
- only authorized mapper/repository implementation code imports underscore reconstruction modules;
- internal reconstruction factories remain absent from public exports.

Reconstruction failures must be classified at the repository boundary. The design must decide whether malformed durable state becomes a contract-level invalid-persisted-state error, a wrapped reconstruction error, or another explicit result, without exposing `_reconstruction` modules through public repository contracts.

## 16. Error Taxonomy Boundary

MILESTONE-020 must define contract-level errors or result states for:

- aggregate not found;
- aggregate already exists;
- optimistic concurrency conflict;
- invalid persisted state;
- repository contract violation;
- persistence unavailable or infrastructure failure.

It must distinguish domain-facing contract errors from infrastructure-specific SQLAlchemy, psycopg, PostgreSQL, network, and health errors. Reconstruction errors may be wrapped or propagated only after the design selects a safe boundary.

Save-result design must account for successful create, successful update, unchanged save, stale-write rejection, duplicate-create rejection, invalid-persisted-state rejection, and infrastructure failure without requiring schema or SQL design.

## 17. Architecture Boundary

MILESTONE-020 may propose future architecture-checker changes but must not apply them unless separately authorized. The design must keep:

- domain aggregates free of persistence imports;
- reconstruction modules internal;
- shared persistence adapters free of aggregate internals unless a later mapper layer is approved;
- no direct persistence-adapter private-field mutation of aggregates.

## 18. Transaction Boundary

MILESTONE-020 must define only contract-level atomicity expectations:

- aggregate root state, owned collections, and transition history must be persisted atomically for one aggregate save;
- repository contracts must decide whether they accept an explicit transaction context, hide transaction participation, or defer transaction context to later Unit-of-Work design;
- cross-aggregate transactions remain deferred;
- Unit of Work implementation remains deferred;
- transaction retry policy remains deferred unless needed for conflict semantics.

## 19. Compatibility Guarantees

MILESTONE-020 must preserve:

- frozen aggregate constructors and public mutation behavior;
- frozen reconstruction contracts;
- domain-managed aggregate version semantics unless explicitly and independently justified;
- transition history as historical data, not Audit or outbox;
- empty `migrations/versions`;
- no storage layout or schema lock-in;
- no public exposure of reconstruction factories.

## 20. Explicit Non-Goals

MILESTONE-020 must not:

- implement repositories;
- implement persistence mappers;
- create schemas, migrations, tables, columns, indexes, or constraints;
- write SQL;
- alter PostgreSQL connectivity;
- implement Unit of Work;
- implement runtime composition;
- create APIs, workers, outbox, Audit runtime, Decision Candidate, Decision Freeze, trading logic, vendor behavior, or empirical execution.

## 21. Testing Strategy

As a design milestone, MILESTONE-020 must define future tests, not write implementation tests. Required future test categories:

- contract conformance tests for each aggregate repository;
- not-found behavior;
- duplicate create behavior;
- stale-write behavior;
- unchanged save behavior;
- successful create/update result shape;
- invalid persisted state handling through reconstruction;
- no public reconstruction exposure;
- no schema/migration side effects in contract-only scope.

## 22. Risks and Mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Repository contract selected by habit | MAJOR | Compare generic, aggregate-specific, and hybrid options explicitly. |
| Concurrency semantics omitted | MAJOR | Make expected-version/stale-write behavior acceptance-gate material. |
| Schema assumptions leak into contracts | MAJOR | Prohibit tables, columns, SQL, and storage format. |
| Reconstruction internals become public | MAJOR | Keep factories internal and define mapper authority separately. |
| Unit-of-Work overreach | MAJOR | Limit M020 to single-aggregate atomicity expectations. |
| CRUD scope creep | MINOR | Exclude delete/list/query/read models unless evidence requires them. |

## 23. Hostile-Review Criteria

Independent review must verify:

- repository operations are not speculative CRUD;
- concurrency semantics are explicit;
- not-found and duplicate identity semantics are not omitted;
- stale-write semantics are precise;
- save result shape is selected or explicitly deferred with justification;
- generic abstraction is not selected without evidence;
- reconstruction state records are not exposed as public repository inputs/outputs without justification;
- mapper/schema/SQL assumptions are absent;
- cross-aggregate transactions and Unit of Work implementation are not smuggled in;
- implementation is not hidden inside design language.

## 24. Acceptance Gate

MILESTONE-020 scope is acceptable only if:

- all four aggregates are covered;
- repository contract questions are enumerated;
- optimistic-concurrency questions are enumerated;
- reconstruction integration direction is preserved;
- error boundary is included;
- transaction boundary is limited;
- mapping, schema, migration, implementation, and runtime work remain deferred;
- validation passes;
- only this scope-selection document is changed.

## 25. Stop Conditions

Stop MILESTONE-020 design if:

- repository contract design requires schema or mapper decisions first;
- optimistic-concurrency semantics contradict frozen `AggregateVersion`;
- save semantics require aggregate source changes;
- reconstruction factories would need public exposure;
- cross-aggregate transaction semantics become required;
- implementation work becomes necessary to answer the design questions.

## 26. Deferred Work

Deferred after MILESTONE-020:

- repository contract implementation;
- persistence mapper design and implementation;
- serialization format;
- PostgreSQL schema and migration design;
- migration revisions;
- SQL implementation;
- Unit of Work integration;
- runtime composition;
- application services;
- read models and query APIs;
- cross-aggregate orchestration;
- Audit runtime;
- Decision Candidate;
- Decision Freeze.

## 27. Hostile Self-Review

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M020-SCOPE-ISSUE-0001 | MAJOR | 8, 10, 14 | Initial selection risked combining repository contracts with broad persistence design. | Candidate C can be misread as mapper/schema work. | Could authorize premature storage decisions. | Bounded M020 to domain-facing repository and concurrency contract design only; mapping/schema/implementation explicitly out of scope. | Resolved |
| M020-SCOPE-ISSUE-0002 | MAJOR | 12, 14 | Save semantics could remain underdefined if concurrency were treated as separate. | Repository readiness gate requires expected-version and stale-write decisions. | Future implementations could diverge. | Made expected persisted version, stale-write, create conflict, unchanged save, and result shape required design questions. | Resolved |
| M020-SCOPE-ISSUE-0003 | MINOR | 13 | Generic repository abstraction could be selected by familiarity. | Four aggregate operations appear superficially similar. | Type safety and domain vocabulary could be lost. | Required explicit generic versus aggregate-specific versus hybrid analysis. | Resolved |
| M020-SCOPE-ISSUE-0004 | MINOR | 18 | Existing low-level Unit of Work could tempt transaction-scope expansion. | `PersistenceUnitOfWork` exists in shared interfaces. | Multi-aggregate transaction policy could be introduced prematurely. | Limited M020 to single-aggregate atomicity expectations and deferred Unit of Work implementation. | Resolved |
| M020-SCOPE-ISSUE-0005 | MAJOR | 13, 17 | Contract placement was named but not independently compared. | Repository contracts could land in domain, application, persistence, or a new package. | Wrong placement could invert dependency direction or contaminate domain packages. | Added mandatory layer-location comparison and architecture-checker implication review. | Resolved |
| M020-SCOPE-ISSUE-0006 | MAJOR | 12, 14, 18 | Operational contract shape was under-enumerated. | Async/sync, load identity shape, tracking, locking, caching, and transaction-context handling were only implicit. | Future design could skip core repository contract decisions. | Added explicit required decisions for contract shape, identity inputs, tracking, locking, caching, and transaction context. | Resolved |
| M020-SCOPE-ISSUE-0007 | MAJOR | 14, 16 | Version vocabulary and save-result alternatives needed sharper separation. | Aggregate current version, observed persisted version, expected persisted version, and create precondition can be confused. | Concurrency contract could permit blind overwrites or ambiguous save outcomes. | Added four-part version vocabulary and mandatory save-result comparison. | Resolved |

No unresolved scope-selection finding remains.

## 28. Final Decision

The selected next milestone is:

```text
MILESTONE-020 - Domain Repository and Concurrency Contract Design
```

Final status:

```text
SCOPE CANDIDATE SELECTED
```
