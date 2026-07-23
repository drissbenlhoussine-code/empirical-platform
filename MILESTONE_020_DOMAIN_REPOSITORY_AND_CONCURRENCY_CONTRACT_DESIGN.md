# MILESTONE-020 - Domain Repository and Concurrency Contract Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-020 |
| Title | Domain Repository and Concurrency Contract Design |
| Version | 1.2 |
| Status | DESIGN CORRECTED - PENDING FINAL VALIDATION |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Design baseline | `7d802bc57f085564f682017051f419d69552fb62` |
| Scope authority | `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_SCOPE_SELECTION.md` |
| Mission type | Contract design only |
| Repository interfaces implemented | No |
| Repository implementations implemented | No |
| Schemas, migrations, mappers, SQL, APIs, workers, Unit of Work, or runtime composition created | No |

## 2. Baseline

Baseline verification required the repository to be on `master` at:

```text
7d802bc57f085564f682017051f419d69552fb62
```

Repository facts at design time:

- M012 canonical runtime domain kernel is approved and frozen.
- M013 process-local domain primitives are implemented.
- M014 EvidencePackage aggregate behavior is frozen.
- M015 Review aggregate behavior is frozen.
- M016 Run aggregate boundary decision is frozen.
- M017 Run aggregate behavior is frozen.
- M018 Campaign aggregate behavior is frozen.
- M019 aggregate reconstruction contract is frozen and implemented.
- PostgreSQL connectivity and low-level infrastructure unit-of-work behavior exist.
- `migrations/versions` is empty.
- No domain repository contracts, domain repository implementations, mappers, schemas, migrations, query models, APIs, workers, outbox, Audit runtime, Decision Candidate, or Decision Freeze behavior exists.

## 3. Problem Statement

The platform now has process-local aggregate behavior and persistence-neutral reconstruction paths, but it still lacks the domain-facing contract that future persistence code must obey. Without a frozen repository and optimistic-concurrency design, the next implementation milestone could accidentally encode hidden choices about load shape, create/update semantics, stale-write handling, expected persisted versions, transaction scope, mapper access, or schema structure.

MILESTONE-020 therefore defines repository contracts and optimistic-concurrency semantics together, without implementing them.

## 4. Frozen Persistence-Readiness Inventory

| Aggregate | Identity | Current version source | Owned state | Reconstruction state | Repository readiness |
| --- | --- | --- | --- | --- | --- |
| Campaign | `DomainIdentity[CampaignId]` | Domain-managed `AggregateVersion` | `CampaignScopeStatement`, lifecycle, transition history | `CampaignReconstructionState` | Ready for contract design |
| Run | `DomainIdentity[RunId]` plus `CampaignId` context | Domain-managed `AggregateVersion` | ordered `DatasetManifest` tuple, lifecycle, transition history | `RunReconstructionState` | Ready for contract design |
| EvidencePackage | `DomainIdentity[EvidencePackageId]` plus `RunId` context | Domain-managed `AggregateVersion` | ordered `CriterionResult` and `ArtifactReference` tuples, lifecycle, transition history | `EvidencePackageReconstructionState` | Ready for contract design |
| Review | `DomainIdentity[ReviewId]` | Domain-managed `AggregateVersion` | `ReviewTargetReference`, `ReviewerReference`, ordered `ReviewFinding` tuple, disposition metadata, lifecycle, transition history | `ReviewReconstructionState` | Ready for contract design |

Frozen constraints:

- public constructors create initial aggregate state only;
- public mutation methods increment `AggregateVersion` after validation succeeds;
- rejected aggregate commands leave state unchanged;
- reconstruction restores exact historical state without incrementing versions or appending history;
- reconstruction modules are internal and not public exports;
- infrastructure persistence services currently expose connectivity and low-level transaction primitives only;
- no schema or mapper exists.

## 5. Design Principles

1. Repository contracts are domain-facing, persistence-neutral, and explicit.
2. Repository load operations return persistence-neutral loaded-aggregate envelopes, not reconstruction records.
3. Repository contracts must not mutate aggregate state or increment aggregate versions.
4. Expected persisted version is explicit caller-supplied concurrency data.
5. New aggregate creation and existing aggregate save are separate operations.
6. Load returns detached aggregate state plus an immutable persisted-version token.
7. No repository contract exposes SQL, ORM, PostgreSQL, mapper, schema, database session, transaction object, cache object, object storage, or health types.
8. The contract is intentionally minimal: identity load, create, and save only.
9. Cross-aggregate orchestration, Unit of Work implementation, queries, projections, and read models remain deferred.
10. Future implementations must translate infrastructure failures without leaking database-driver details through domain repository contracts.

## 6. Repository Architecture Options

| Option | Description | Type safety | Domain terminology | Generic-abstraction risk | Concurrency consistency | Testability | Decision |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | Generic `Repository[AggregateType, IdentityType]` | Medium | Low | High | High if carefully parameterized | Medium | Rejected |
| B | Aggregate-specific repositories | High | High | Low | Medium unless shared primitives are defined | High | Selected |
| C | Shared generic save/load primitives plus aggregate-specific contracts | High | High | Medium | High | High | Rejected as too framework-like for first contract |
| D | One shared repository service | Low | Low | High | Medium | Low | Rejected |
| E | Repository-free mapper/persistence functions | Low | Low | Medium | Low | Medium | Rejected |

Option A gives a neat-looking abstraction but hides aggregate vocabulary and encourages CRUD expansion. Option C is attractive, but a shared primitive layer would be an implementation framework before evidence proves the four contracts need one. Option D collapses aggregate boundaries. Option E bypasses a domain-facing port and would force callers to know mapper/persistence functions.

## 7. Selected Repository Architecture

Selected architecture:

```text
Aggregate-specific repository contracts
```

Future contract names:

- `CampaignRepository`
- `RunRepository`
- `EvidencePackageRepository`
- `ReviewRepository`

The four contracts must expose the same minimal operation classes:

- load by identity;
- create a new aggregate;
- save an existing aggregate with an expected persisted version.

Aggregate-specific contracts are selected because they preserve domain vocabulary, precise identity types, aggregate-specific future evolution, and simple contract tests without over-abstracting prematurely.

No generic base repository protocol is selected in this design. A later implementation may extract shared test helpers or shared error/result value objects only if it does not erase aggregate-specific contracts.

## 8. Contract Placement

Placement options evaluated:

| Option | Future module path | Strength | Risk | Decision |
| --- | --- | --- | --- | --- |
| Aggregate package repository module | `empirical_platform.<aggregate>.repository` | Keeps contract near aggregate language and types | Could tempt aggregates to import repositories | Selected with import-direction rule |
| Persistence contracts package | `empirical_platform.persistence.contracts` | Separates contracts from aggregates | New top-level package not yet present and risks storage-facing naming | Rejected |
| Shared persistence package | `empirical_platform.shared.persistence` | Existing persistence boundary | Would leak aggregate concepts into infrastructure primitives | Rejected |
| Application package | `empirical_platform.application` | Use-case-facing ownership | Application layer does not yet exist | Rejected |
| New aggregate-specific contract packages | e.g. `empirical_platform.campaign_repository` | Strong separation | Adds package sprawl before implementation evidence | Rejected |

Selected future module paths:

- `empirical_platform.campaign.repository`
- `empirical_platform.run.repository`
- `empirical_platform.evidence.repository`
- `empirical_platform.review.repository`

Placement rules:

- aggregate modules must not import repository modules;
- repository modules may import their aggregate, identity, version, and shared repository-contract value types;
- repository implementation modules may depend on repository contracts later;
- repository contracts must not import SQLAlchemy, psycopg, PostgreSQL adapters, object storage adapters, schemas, mappers, runtime composition, health, or infrastructure-specific errors;
- repository contracts must not expose internal `_reconstruction` modules.

Future architecture-checker changes are required before implementation to ensure aggregate modules do not import repository modules and repository modules do not import infrastructure packages. Live evidence confirms the existing checker already blocks `campaign`, `run`, `evidence`, and `review` from importing `empirical_platform.shared.persistence`, `sqlalchemy`, `psycopg`, and `boto3` (`tools/check_architecture.py`, `FORBIDDEN_IMPORT_PREFIXES`). That evidence supports the selected placement candidate, but absence from `FORBIDDEN_IMPORT_PREFIXES` is not, by itself, full architectural proof. Implementation scope must still verify that `shared.contracts` remains cycle-safe, that it can reference `AggregateVersion` and `DomainIdentity` without reversing dependency direction, that aggregate repository modules may import it, and that it does not become a dumping ground for unrelated contracts.

### 8.1 Shared Contract-Type Placement

Independent review confirmed a gap: this design describes `SaveOperation`, `SaveResult`, and the `RepositoryContractError` hierarchy conceptually (Sections 22-23) and assumes in the placement rules above that repository modules may import "shared repository-contract value types," but no version of this document before Version 1.1 named an exact module for those shared types. Per Section 29, the same contract suite and the same result/error shapes must apply to all four aggregate repositories, so these types cannot be duplicated per aggregate package; they must live in exactly one shared, already-permitted location.

Selected placement:

```text
empirical_platform.shared.contracts
```

Rationale, grounded in live repository evidence:

- `src/empirical_platform/shared/contracts/__init__.py` already exists in the frozen repository tree as an empty, purpose-declared module ("Shared typed contract boundary"), so this placement adds no new top-level package and no package sprawl.
- `tools/check_architecture.py` already permits `campaign`, `run`, `evidence`, and `review` to import anything under `empirical_platform.shared` except `empirical_platform.shared.persistence` (and `sqlalchemy`/`psycopg`/`boto3`); `empirical_platform.shared.contracts` is not on the forbidden list, so it is a supported placement candidate for all four aggregate repository modules.
- Placing these types under `shared.persistence` was considered and rejected: it would violate the existing forbidden-import rule that keeps aggregate packages away from persistence-adapter code, contradicting Section 8's own placement rule that repository contracts must not import PostgreSQL/SQLAlchemy-adjacent modules.

Implementation-scope verification remains mandatory before source code is created:

- prove there is no import cycle involving `shared.contracts`, `shared.domain`, `identifiers`, and aggregate repository modules;
- prove `shared.contracts` can use `AggregateVersion` and `DomainIdentity` without breaking current dependency direction;
- prove aggregate repository modules may import `shared.contracts` while aggregate root modules do not import repositories;
- keep `shared.contracts` limited to coherent repository-contract value types and errors.

Selected future module paths for shared contract types:

- `empirical_platform.shared.contracts.SaveOperation`
- `empirical_platform.shared.contracts.SaveResult`
- `empirical_platform.shared.contracts.LoadedAggregate`
- `empirical_platform.shared.contracts.RepositoryContractError`
- `empirical_platform.shared.contracts.AggregateNotFound`
- `empirical_platform.shared.contracts.AggregateAlreadyExists`
- `empirical_platform.shared.contracts.OptimisticConcurrencyConflict`
- `empirical_platform.shared.contracts.InvalidAggregateForPersistence`
- `empirical_platform.shared.contracts.InvalidPersistedAggregateState`

No retryability enum type is introduced by this correction; Section 20's `RETRYABLE_AFTER_RELOAD` remains a described concept attached to `OptimisticConcurrencyConflict`, not a new frozen type, consistent with the implementation-scope deferral in Section 31.

## 9. Sync/Async Decision

Options evaluated:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| Synchronous repository contracts | Matches current SQLAlchemy Engine/Core foundation, current tests, and process-local aggregate style | Future async API may require adapter boundary | Selected |
| Asynchronous repository contracts | Aligns with possible future async API/workers | Current persistence foundation is synchronous; would require async driver and dual mental model | Rejected |
| Dual sync and async contracts | Flexible | Duplicates contract surface and test matrix | Rejected |

Selected model:

```text
Synchronous contracts only
```

The current platform uses synchronous process-local domain behavior and a synchronous PostgreSQL connectivity foundation. The repository contract must not preselect an async runtime before workers or APIs exist. Future async entrypoints may call synchronous repository implementations through an explicit application/infrastructure boundary if needed.

## 10. Aggregate Coverage

The design covers exactly:

- Campaign;
- Run;
- EvidencePackage;
- Review.

Each aggregate receives an aggregate-specific repository contract with the same minimal operation categories. No aggregate-specific query method is approved. Differences are limited to identity and aggregate types:

| Repository | Identity input | Load output / save input |
| --- | --- | --- |
| CampaignRepository | `DomainIdentity[CampaignId]` | `LoadedAggregate[Campaign]` / `Campaign` |
| RunRepository | `DomainIdentity[RunId]` | `LoadedAggregate[Run]` / `Run` |
| EvidencePackageRepository | `DomainIdentity[EvidencePackageId]` | `LoadedAggregate[EvidencePackage]` / `EvidencePackage` |
| ReviewRepository | `DomainIdentity[ReviewId]` | `LoadedAggregate[Review]` / `Review` |

Context identifiers such as `CampaignId` on Run or `RunId` on EvidencePackage remain aggregate state; they are not separate repository lookup keys in this contract.

## 11. Identity Inputs

Selected identity rule:

```text
Repository load/create/save operations use canonical DomainIdentity[AggregateId].
```

Rationale:

- aggregate roots already expose `DomainIdentity[...]`;
- M012 requires governance ID plus runtime UUID separation;
- using raw governance IDs would lose runtime identity and identity-kind validation;
- using runtime UUID alone would lose governance traceability;
- using `DomainIdentity[...]` keeps repository keys aligned with aggregate identity.

No aggregate-specific exception is selected.

### 11.1 Identity-Based Loading Versus Identity Discovery

Independent review checked whether callers can realistically possess a complete `DomainIdentity[AggregateId]` before calling `get`. Live evidence from `src/empirical_platform/identifiers/pairs.py` confirms `DomainIdentity` requires both `governance_id` (for example `CampaignId`, a human-facing value such as `CAMP-0001`) and `runtime_id` (an opaque `RuntimeIdentifier` UUID). `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` records the runtime UUID as the internal persistence identity paired with the governance ID, and separately defers "governance registry ingestion" as future work, not part of the initial kernel.

This means no governance-ID-only resolution service exists yet anywhere in the frozen repository. This design's identity input is not circular: a caller that just executed `add` already holds the full `DomainIdentity` it supplied, and any caller performing a later `get` must already have propagated or persisted that same pair from creation time (for example through session state, a workflow context, or an application-level reference) rather than starting from a bare governance ID. This is an explicit, load-bearing constraint that Version 1.0 of this document left implicit.

Selected clarification:

```text
Repository load/create/save operations support identity-based loading only.
Resolving a bare governance identifier into a DomainIdentity (identity discovery)
is out of scope for MILESTONE-020 and remains deferred until a future
governance-registry or identity-resolution milestone is authorized.
```

## 12. Load Semantics

Selected load operation semantics:

- method name: `get`;
- input: `DomainIdentity[AggregateId]`;
- successful result: immutable `LoadedAggregate[AggregateT]`;
- `LoadedAggregate.aggregate` contains detached aggregate state;
- `LoadedAggregate.persisted_version` contains the immutable version observed from durable storage at load time;
- missing identity: raises `AggregateNotFound`;
- malformed persisted state or reconstruction failure: raises `InvalidPersistedAggregateState`;
- repository interfaces do not expose reconstruction state records;
- repository interfaces do not expose internal `_reconstruct_*` factories;
- loaded aggregate does not carry a persistence token inside itself;
- row locking is excluded from the contract;
- caching is excluded from the contract;
- no transaction context is accepted by the public repository contract.

The name `get` is selected because the operation is direct identity retrieval, not a broad query or search. The absence of a matching aggregate is exceptional for this contract because callers must already hold a canonical identity.

Load followed by save is not assumed to occur in one database transaction. The caller must supply the expected persisted version obtained from `LoadedAggregate.persisted_version` or a prior successful `SaveResult.persisted_version`.

### 12.1 Persisted-Version Token Acquisition

Independent review reopened the token-acquisition issue as MAJOR. The plain-aggregate load model:

```text
get(identity) -> aggregate
```

requires callers to capture `aggregate.version` immediately after `get` and before any mutation. That is not strong enough because a caller can accidentally write:

```text
aggregate = repository.get(identity)
aggregate.mutate()
repository.save(aggregate, expected_persisted_version=aggregate.version)
```

In that mistake, the caller supplies the post-mutation aggregate current version instead of the persisted version observed at load time. Live reconstruction evidence proves the aggregate version is correct at the instant of load, but it does not enforce safe capture after the aggregate is returned.

Options reassessed:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| A. `get(identity) -> aggregate`, caller-managed version capture | Smallest return surface | Persisted-version token can be accidentally captured after mutation | Rejected |
| B. `get(identity) -> LoadedAggregate[AggregateT]` | Separates aggregate current version from loaded persisted version | Adds one small persistence-neutral wrapper | Selected |

Selected load result:

```text
LoadedAggregate[AggregateT]
- aggregate: AggregateT
- persisted_version: AggregateVersion
```

`LoadedAggregate` is persistence-neutral. It contains no session, tracking object, mapper, transaction, database metadata, lock token, row metadata, health state, or storage reference. Its `persisted_version` is immutable and is not affected when the detached aggregate is mutated. The aggregate itself remains free of persistence metadata.

Save still accepts:

```text
save(existing aggregate, expected_persisted_version: AggregateVersion)
```

The expected version is normally taken from `loaded.persisted_version` or the previous `SaveResult.persisted_version`, never from the aggregate after mutation.

## 13. Not-Found Semantics

Options evaluated:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| Optional return | Simple | Missing identity can be ignored accidentally | Rejected |
| Contract-level exception | Clear failure, easy API translation, consistent with identity-required load | Selected |
| Result type | Explicit but verbose | Adds wrapper type before broader result model exists | Rejected |

Selected behavior:

```text
Missing aggregate identity raises AggregateNotFound.
```

`AggregateNotFound` is persistence-neutral and contains the requested identity context. Implementations must not leak database no-row, SQLAlchemy, or driver details.

## 14. Create/Save Operation Model

Options evaluated:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| Separate `add` and `save` | Caller intent is explicit; duplicate-create and stale-update are distinct | Two operations instead of one | Selected |
| Single save with creation marker | One method surface | Creation and update intent become less legible | Rejected |
| Upsert | Convenient | Destroys concurrency intent and can hide duplicates | Rejected |

Selected operation model:

- `add` persists a new aggregate that must not already exist.
- `save` persists an existing aggregate only when the expected persisted version matches the durable version.

`add` and `save` are conceptually distinct even if a future implementation shares lower-level code.

## 15. Version Vocabulary

Frozen vocabulary:

| Term | Meaning |
| --- | --- |
| Aggregate current version | The `AggregateVersion` currently held by the in-memory aggregate after domain mutations. |
| Loaded persisted version | The immutable `AggregateVersion` carried by `LoadedAggregate.persisted_version` after `get`. |
| Expected persisted version | The `AggregateVersion` supplied to `save`, normally copied from `LoadedAggregate.persisted_version` or the previous `SaveResult.persisted_version`, against which `save` must compare atomically. |
| Persisted version after save | The aggregate current version successfully stored by the repository. |
| New aggregate state | The condition where no persisted version exists yet for the aggregate identity. |

Selected expected-version model:

```text
save(existing aggregate, expected_persisted_version: AggregateVersion)
```

`AggregateVersion | None` is rejected for existing save because `None` overloads update and create semantics. A dedicated persistence-neutral value object is also rejected for this design because `AggregateVersion` already represents the concurrency token and there is no separate persisted revision yet.

Creation does not pass `None`; creation uses `add`.

## 16. New Aggregate Creation

Selected creation semantics:

- creation intent is expressed by `add`;
- `add` accepts an aggregate with canonical `DomainIdentity[...]`;
- the aggregate must not already be persisted;
- duplicate identity raises `AggregateAlreadyExists`;
- concurrent insert races must result in exactly one success and one `AggregateAlreadyExists`;
- database uniqueness errors are translated and hidden;
- no preflight `exists()` check may be treated as the concurrency guarantee;
- a newly created aggregate may have any valid non-negative current `AggregateVersion`;
- version zero is not required for first persistence;
- `add` returns a `SaveResult` with operation `CREATED` and persisted version equal to the aggregate current version.

This respects frozen aggregate behavior where local domain mutations can occur before first persistence.

## 17. Existing Aggregate Save

Selected existing-save semantics:

- `save` accepts an aggregate and explicit `expected_persisted_version`;
- the repository atomically compares the durable version to `expected_persisted_version`;
- on match, it persists the aggregate's current version and complete aggregate state;
- on mismatch, it raises `OptimisticConcurrencyConflict`;
- repository save never increments aggregate version;
- repository save never mutates aggregate state;
- repository save does not repair malformed aggregate state;
- repository save does not emit domain events, outbox records, Audit records, logs as business evidence, or external calls;
- persisted aggregate state must preserve reconstruction fidelity.

The current aggregate version must be greater than or equal to the expected persisted version. Greater-than covers accepted local mutations. Equal-to covers unchanged saves.

## 18. Unchanged Save

Options evaluated:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| Idempotent no-op success | Simple repeated-save behavior; no unnecessary write required | Caller may not notice no change unless result says so | Rejected in favor of explicit result |
| Explicit no-change result | Deterministic and visible | Requires result object | Selected |
| Contract rejection | Forces callers to know mutation state | Makes repeated-save workflows brittle | Rejected |
| Storage write allowed but not required | Portable implementation | Ambiguous to callers without result | Rejected |

Selected behavior:

```text
aggregate current version == expected persisted version
```

is a valid unchanged save that returns `SaveResult(operation=UNCHANGED, persisted_version=current_version)`.

Implementations may avoid physical writes for unchanged saves, but they must still validate that the expected persisted version matches durable state.

## 19. Repeated Save

Deterministic repeated-save rule:

1. Repository returns `LoadedAggregate(aggregate, persisted_version=5)`.
2. Caller mutates `loaded.aggregate` locally to current version 7.
3. Caller saves `loaded.aggregate` with expected persisted version `loaded.persisted_version` (5).
4. Repository persists version 7 and returns persisted version 7.
5. A second save without mutation must use expected persisted version 7.
6. Reusing expected version 5 must raise `OptimisticConcurrencyConflict` if durable version is 7.
7. Saving again with expected version 7 returns `UNCHANGED`.

Repositories do not track state internally. The caller owns propagation of the latest persisted version through `LoadedAggregate.persisted_version` and `SaveResult.persisted_version`.

## 20. Stale-Write Semantics

Selected stale-write behavior:

- error type: `OptimisticConcurrencyConflict`;
- includes aggregate identity;
- includes expected persisted version;
- includes aggregate current version;
- includes actual persisted version when safely available;
- actual persisted version is optional because not all storage backends may return it without a second read;
- retryability is `RETRYABLE_AFTER_RELOAD`;
- no automatic retry;
- no blind overwrite;
- no aggregate mutation;
- no database exception leakage.

The conflict is optimistic-concurrency failure, not aggregate validation failure.

## 21. Concurrent Creation

Selected concurrent-creation behavior:

- `add` is atomic for one aggregate identity;
- if the identity already exists, raise `AggregateAlreadyExists`;
- if two creators race, exactly one succeeds and the other receives `AggregateAlreadyExists`;
- database uniqueness errors are translated;
- no overwrite occurs;
- no repository preflight `exists()` method is selected as a correctness mechanism;
- retry ownership stays with caller/application policy, not repository contract.

## 22. Save Result

Options evaluated:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| No return | Smallest API | Repeated saves need an external token source | Rejected |
| Persisted version only | Good for token propagation | Does not distinguish create/update/unchanged | Rejected |
| Aggregate-neutral `SaveResult` | Explicit operation and version without database metadata | Adds small value type | Selected |
| Return aggregate | Familiar in some ORMs | Implies repository mutation or tracking | Rejected |

Selected result:

```text
SaveResult
```

Conceptual fields:

| Field | Meaning |
| --- | --- |
| `operation` | One of `CREATED`, `UPDATED`, `UNCHANGED` |
| `persisted_version` | Aggregate current version successfully made durable |

No database metadata, row count, transaction ID, ETag, timestamp, session object, lock token, mapper record, or schema information is returned.

## 23. Error Taxonomy

Selected base:

```text
RepositoryContractError
```

Selected contract errors:

| Error | Base | Required context | Retryability | Message rule |
| --- | --- | --- | --- | --- |
| `AggregateNotFound` | `RepositoryContractError` | aggregate kind, identity | Not retryable without new identity | Safe message, no storage details |
| `AggregateAlreadyExists` | `RepositoryContractError` | aggregate kind, identity | Not retryable without new identity or caller policy | Safe message, no uniqueness/index details |
| `OptimisticConcurrencyConflict` | `RepositoryContractError` | aggregate kind, identity, expected persisted version, aggregate current version, optional actual persisted version | Retryable after reload | Safe message, no SQL/driver details |
| `InvalidAggregateForPersistence` | `RepositoryContractError` | aggregate kind, identity if available, reason | Not retryable without code/data correction | Safe message |
| `InvalidPersistedAggregateState` | `RepositoryContractError` | aggregate kind, identity if available, reconstruction category/field when safe | Not retryable without data correction | Safe message |

`ReconstructionError` handling:

- ordinary callers do not receive raw reconstruction state;
- future repository implementations translate `ReconstructionError` to `InvalidPersistedAggregateState`;
- exception chaining may preserve original exception for logs/debugging, but the public contract error remains persistence-neutral.

Infrastructure availability failures remain outside the domain repository error taxonomy unless a later application-service boundary needs a separate infrastructure-facing classification.

`LoadedAggregate` is a shared persistence-neutral contract value type, not an error. It lives with `SaveResult` and the repository error hierarchy in `empirical_platform.shared.contracts`.

## 24. Reconstruction Integration

Frozen load flow:

```text
repository implementation
-> mapper
-> aggregate-specific ReconstructionState
-> internal _reconstruct_* factory
-> aggregate root
```

Frozen save flow:

```text
aggregate root
-> mapper
-> persistence representation
-> atomic persistence
```

Contract rules:

- repository load interfaces expose `LoadedAggregate[AggregateT]`, whose only aggregate-bearing field is a detached aggregate root;
- reconstruction state records remain internal to mapper/reconstruction integration;
- `_reconstruct_*` factories remain internal;
- mapper design is deferred;
- repository implementation is deferred;
- public exports do not change in this design;
- architecture-checker changes are deferred until implementation scope.

## 25. Atomic Save Boundary

A successful `add` or `save` is atomic across one aggregate root:

- identity and context identifiers;
- lifecycle state;
- current aggregate version;
- next transition sequence;
- transition history;
- root scalar state;
- owned immutable value objects;
- ordered owned collections;
- terminal metadata.

No partial save may be observable through future repository contracts. This is a contract guarantee only; it does not prescribe database transactions, table layout, locks, isolation level, or schema.

## 26. Transaction Boundary

Selected transaction boundary:

- one aggregate `add` or `save` is atomic;
- repository contracts do not accept database sessions;
- repository contracts do not expose transaction objects;
- repository contracts do not expose Unit of Work objects;
- load followed by save is not assumed to run in one transaction;
- row locking is deferred;
- automatic retry is deferred;
- multi-aggregate transactions are deferred;
- application orchestration remains deferred.

The existing low-level `PersistenceUnitOfWork` remains an infrastructure primitive, not a domain repository contract surface.

## 27. Tracking Model

Options evaluated:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| Detached aggregates | Transparent expected-version passing; no hidden Unit of Work | Caller must carry persisted version | Selected |
| Tracked aggregates | Convenient save after load | Hidden identity map, transaction coupling, lifecycle complexity | Rejected |

Selected model:

```text
Detached
```

Repositories do not track loaded aggregate instances. They do not remember expected persisted versions. They do not maintain identity maps. They do not mutate aggregate objects after save. `LoadedAggregate.persisted_version` preserves the load-time token without repository-side tracking. Repeated-save correctness depends on caller-supplied expected persisted version from `LoadedAggregate` or `SaveResult`.

## 28. Query/Delete Exclusions

The following are explicitly excluded:

- delete;
- list/search/filter/pagination;
- lifecycle queries;
- `exists()` as a contract operation;
- Campaign-to-Run lookup;
- Run-to-EvidencePackage lookup;
- EvidencePackage-to-Review lookup;
- read models;
- projections;
- analytics;
- reporting;
- repository methods that cross aggregate boundaries.

Repository contracts manage aggregate-root identity load and persistence only.

## 29. Contract Testing

Future implementation must define contract tests independent of storage technology.

Required load tests:

- successful load for each aggregate;
- returned value is `LoadedAggregate[AggregateT]`;
- `LoadedAggregate.persisted_version` equals the durable version at load time;
- mutating `LoadedAggregate.aggregate` does not change `LoadedAggregate.persisted_version`;
- missing identity raises `AggregateNotFound`;
- malformed persisted state raises `InvalidPersistedAggregateState`;
- reconstruction failures are translated;
- loaded aggregate state matches durable state exactly.

Required create tests:

- successful create;
- create with positive aggregate current version;
- duplicate identity;
- simulated concurrent create;
- no aggregate mutation by repository.

Required save tests:

- successful mutated aggregate save;
- save accepts aggregate plus explicit expected persisted version from `LoadedAggregate.persisted_version`;
- stale expected persisted version;
- unchanged save returns `UNCHANGED`;
- repeated save requires updated expected persisted version;
- save result operation and persisted version;
- atomic root, owned-collection, metadata, and history boundary.

Required error tests:

- exact contract error types;
- identity/version context;
- no database exception leakage;
- no SQL/ORM type exposure.

The same contract suite must apply to Campaign, Run, EvidencePackage, and Review repositories.

## 30. Compatibility Guarantees

Future repository contracts must not:

- modify frozen aggregates;
- modify reconstruction contracts;
- increment aggregate versions;
- store expected persisted version inside aggregate objects;
- expose reconstruction state records;
- expose internal reconstruction factories;
- expose SQL, ORM, PostgreSQL, object storage, or schema types;
- introduce delete/query semantics;
- require schemas yet;
- define mapping yet;
- require Unit of Work;
- define multi-aggregate transactions;
- add APIs or workers;
- introduce Audit, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior.

## 31. Deferred Work

Deferred after M020:

- source implementation of repository contracts;
- shared repository result/error value implementation;
- repository implementations;
- mappers;
- serialization format;
- PostgreSQL schema and migrations;
- SQL;
- ORM mapping;
- Unit of Work integration;
- row locking;
- retry policy;
- application services;
- runtime composition;
- API and worker integration;
- read models and projections;
- Audit runtime;
- Decision Candidate;
- Decision Freeze.

## 32. Risks and Mitigations

| Risk | Severity | Mitigation |
| --- | --- | --- |
| Aggregate-specific contracts duplicate common shapes | MINOR | Permit shared test helpers later, but keep public contracts aggregate-specific. |
| Detached model burdens callers with expected-version propagation | MAJOR | `LoadedAggregate` preserves the load-time token and `SaveResult` propagates the post-save token; future application services must carry one of those explicit values. |
| No raw `exists()` method complicates creation prechecks | MINOR | Correctness belongs to atomic `add`; optional user-facing prechecks can be read-model work later. |
| Synchronous contracts may need async wrapping later | MINOR | Keep async conversion at application/runtime boundary if APIs or workers require it. |
| Contract placement inside aggregate package could pollute domain modules | MAJOR | Add architecture-checker rule before implementation: aggregates cannot import repositories; repositories cannot import infrastructure. |
| Error taxonomy may overfit before implementation | MINOR | Keep errors minimal and persistence-neutral; defer infrastructure failure taxonomy. |

## 33. Hostile Self-Review

| ID | Severity | Section | Finding | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| M020-DESIGN-ISSUE-0001 | MAJOR | 15 | Initial draft risked conflating expected persisted version with aggregate current version. | Could allow blind overwrite or ambiguous repeated saves. | Added four-term version vocabulary and explicit expected-version save rule. | Resolved |
| M020-DESIGN-ISSUE-0002 | MAJOR | 14, 16 | Creation semantics initially risked requiring version zero for first persistence. | Would contradict process-local mutation before persistence. | Selected `add` and allowed any valid current aggregate version. | Resolved |
| M020-DESIGN-ISSUE-0003 | MAJOR | 18, 19 | Unchanged and repeated save behavior needed deterministic token propagation. | Future implementations could diverge. | Selected `UNCHANGED` SaveResult and required caller to use latest persisted version after save. | Resolved |
| M020-DESIGN-ISSUE-0004 | MAJOR | 26, 27 | Tracked repositories could smuggle Unit of Work behavior into contracts. | Hidden state and transaction coupling. | Selected detached aggregates and explicit expected-version passing. | Resolved |
| M020-DESIGN-ISSUE-0005 | MAJOR | 8, 24 | Repository placement near aggregate packages could expose reconstruction internals. | Public callers might import `_reconstruction`. | Selected aggregate-local repository modules but kept reconstruction internal and required future architecture checks. | Resolved |
| M020-DESIGN-ISSUE-0006 | MINOR | 23 | Infrastructure availability errors were tempting to add to domain taxonomy. | Could leak foundation error concerns into domain contracts. | Kept domain repository errors focused and deferred infrastructure failure classification. | Resolved |
| M020-DESIGN-ISSUE-0007 | MINOR | 28 | `exists()` could sneak in as creation convenience. | Could become false concurrency guarantee. | Excluded `exists()` from contract and made atomic `add` authoritative. | Resolved |

No unresolved design issue remains from the original self-review.

### 33.1 Independent Hostile Review (Version 1.1 and 1.2 Correction Passes)

| ID | Severity | Section | Design statement | Repository evidence | Finding | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| M020-INDEPENDENT-0001 | MAJOR | 8, 22, 23, 29 | Placement rules assumed repository modules "may import ... shared repository-contract value types" without naming that module. | `src/empirical_platform/shared/contracts/__init__.py` exists, empty, purpose-declared; `tools/check_architecture.py` `FORBIDDEN_IMPORT_PREFIXES` blocks only `shared.persistence`/`sqlalchemy`/`psycopg`/`boto3` for `campaign`/`run`/`evidence`/`review`, not `shared.contracts`. | `LoadedAggregate`, `SaveOperation`, `SaveResult`, and the `RepositoryContractError` hierarchy had no exact module location, which the acceptance criteria treat as blocking for implementation readiness. | An implementer would have to invent placement, risking inconsistent per-aggregate duplication of shared result/error shapes. | Added Section 8.1 naming `empirical_platform.shared.contracts` as the exact future location for all shared contract types, while narrowing the claim to selected placement subject to implementation-scope cycle and dependency verification. | Resolved |
| M020-INDEPENDENT-0002 | MAJOR | 11 | "Repository load/create/save operations use canonical `DomainIdentity[AggregateId]`," justified only on type-safety/traceability grounds. | `identifiers/pairs.py` requires both `governance_id` and `runtime_id`; `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` defers "governance registry ingestion" and records the runtime UUID as internal persistence identity. | The design did not state whether a caller holding only a governance ID (for example `CAMP-0001`) can load through this contract, leaving an implicit, undocumented dependency on out-of-scope future capability. | A future implementer or application-layer author could assume `get` supports governance-ID-only lookup, which it does not, or could be blocked without realizing why. | Added Section 11.1 confirming the identity model is not circular (creators already hold the full pair) and explicitly deferring identity discovery/governance-ID resolution to a future governance-registry milestone. | Resolved |
| M020-INDEPENDENT-0003 | MAJOR | 12, 19, 27 | Version 1.1 required callers to capture `aggregate.version` immediately after `get`. | Reconstruction restores aggregate version correctly at load time, but aggregate mutation can advance that same property before save. | Bare-aggregate loading left the persisted-version token vulnerable to accidental post-mutation capture. | A caller could pass the aggregate current version as `expected_persisted_version`, producing incorrect unchanged-save or conflict behavior. | Reassessed bare aggregate versus `LoadedAggregate`; selected `LoadedAggregate[AggregateT]` with immutable `persisted_version`, detached aggregate state, and no persistence metadata on the aggregate. | Resolved |

No unresolved CRITICAL or MAJOR finding remains after this correction pass. All three independent-review findings above are documentation-only corrections to this file; no source, test, architecture-checker, or other milestone document was modified.

## 34. Acceptance Gate

| Gate | Result |
| --- | --- |
| Repository architecture selected | PASS |
| Contract placement selected | PASS |
| Sync/async model selected | PASS |
| All four aggregates covered | PASS |
| Identity input selected | PASS |
| Load and not-found semantics selected | PASS |
| Create/save model selected | PASS |
| Expected persisted version semantics complete | PASS |
| New aggregate creation semantics complete | PASS |
| Existing save semantics complete | PASS |
| Unchanged and repeated save semantics complete | PASS |
| Stale-write and concurrent creation semantics complete | PASS |
| Save result selected | PASS |
| Error taxonomy selected | PASS |
| Reconstruction integration preserved | PASS |
| Atomicity and transaction boundaries limited | PASS |
| Tracking model selected | PASS |
| Query/delete exclusions explicit | PASS |
| Mapper/schema/migration/implementation deferred | PASS |
| No source code introduced | PASS |
| Shared contract-type module location selected | PASS (Version 1.1) |
| Identity-based loading versus identity discovery distinguished | PASS (Version 1.1) |
| Persisted-version token acquisition safely preserved by `LoadedAggregate` | PASS (Version 1.2) |
| `shared.contracts` placement classified as selected design placement subject to implementation-scope architecture verification | PASS (Version 1.2) |
| Independent hostile review performed against live repository evidence | PASS (Version 1.2) |
| Canonical local validation (`scripts/security.ps1`, `scripts/verify.ps1`, ruff, mypy, `tools/check_architecture.py`) rerun after correction | PENDING |

## 35. Final Decision

MILESTONE-020 selects aggregate-specific, synchronous, aggregate-local future repository contracts with explicit optimistic-concurrency semantics.

Version 1.2 applies documentation-only corrections identified by independent hostile review conducted directly against live repository evidence: shared contract-type placement is narrowed to selected design placement subject to implementation-scope architecture verification, identity-based loading is distinguished from identity discovery, and persisted-version token capture is moved from caller-managed bare aggregate capture to immutable `LoadedAggregate.persisted_version`. No architecture-checker change, no source implementation, and no other milestone document is changed by this correction pass.

This document does not mark MILESTONE-020 frozen. Freezing requires the canonical local validation suite (`scripts/security.ps1`, `scripts/verify.ps1`, `python -m ruff format --check .`, `python -m ruff check .`, `python -m mypy`, `python tools/check_architecture.py .`) to be rerun and pass on the corrected repository state, plus a clean `git status` and a successful correction commit. That validation step requires a native Windows PowerShell environment and has not been executed as part of this correction pass.

Final status:

```text
DESIGN CORRECTED - PENDING FINAL VALIDATION
```
