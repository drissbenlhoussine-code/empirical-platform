# MILESTONE-020 - Domain Repository and Concurrency Contract Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-020 |
| Title | Domain Repository and Concurrency Contract Design |
| Version | 1.6 |
| Status | DESIGN READY FOR COMMIT - TEST SUITE PASS VIA ISOLATED BASETEMP, LITERAL PYTEST INVOCATION ENVIRONMENT-BLOCKED (MACHINE-LOCAL) - FREEZE PENDING PROJECT OWNER DECISION |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Design baseline | `7d802bc57f085564f682017051f419d69552fb62` |
| Scope authority | `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_SCOPE_SELECTION.md` |
| Mission type | Contract design only |
| Repository interfaces implemented | No |
| Repository implementations implemented | No |
| Schemas, migrations, mappers, SQL, APIs, workers, Unit of Work, or runtime composition created | No |

### 1.1 Revision History

| Version | Status | Summary |
| --- | --- | --- |
| 1.0 | DESIGN READY FOR INDEPENDENT REVIEW | Initial M020 repository and concurrency contract design. |
| 1.1 | DESIGN CORRECTED | Documentation corrections for shared contract-type placement and identity-based loading clarification. |
| 1.2 | DESIGN CORRECTED - PENDING FINAL VALIDATION | Documentation correction selecting `LoadedAggregate` for persisted-version token safety. |
| 1.3 | DESIGN CORRECTED - PENDING INDEPENDENT REVIEW | Correction pass v3 resolves remaining hostile-review findings without implementation, architecture-checker changes, package-layout changes, repository redesign, or freeze. |
| 1.4 | DESIGN READY FOR COMMIT - FREEZE PENDING PROJECT OWNER DECISION | Independent hostile review of Version 1.3 performed against live repository evidence; no MAJOR or CRITICAL finding identified. Canonical local validation re-executed against the project virtual environment and recorded. Three cosmetic markdown spacing defects corrected. No semantic, architectural, or scope change. |
| 1.5 | DESIGN READY FOR COMMIT - FREEZE PENDING PROJECT OWNER DECISION | Root-caused the `pytest` collection failure reported in Version 1.4: it was an invocation artifact, not a repository defect. Both `pytest` and `python -m pytest` were re-verified; the full canonical suite now passes with zero source, test, or configuration changes. See Section 33.3. No semantic, architectural, or scope change. |
| 1.6 | DESIGN READY FOR COMMIT - TEST SUITE PASS VIA ISOLATED BASETEMP, LITERAL PYTEST INVOCATION ENVIRONMENT-BLOCKED (MACHINE-LOCAL) | Corrects an overclaim in Version 1.5: the literal default `pytest`/`python -m pytest` invocation does not reliably exit 0 on this machine. A dedicated evidence package (`validation-evidence/M020/`) reproduced the exact requested command and recorded exit code 1, caused by the same locked OS temp reparse point, not by a repository defect. The repository test suite itself is confirmed healthy (244 passed, 9 skipped, 91.93% coverage) only when isolated from that locked path via `--basetemp`. Wording throughout this document is corrected to distinguish repository-suite health from literal-invocation exit code; no PASS claim is made for the unmodified default invocation. No semantic, architectural, or scope change. |

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

Future architecture-checker changes are not authorized by this design correction. Before implementation, repository contract placement must comply with the architecture rules that are authoritative at implementation time.

The exact module placement of repository contract support types and repository contract errors is intentionally not frozen by this design. During repository contract installation, the selected placement must first satisfy:

- dependency direction;
- architecture checker;
- absence of import cycles;
- bounded-context ownership;
- shared package constraints.

If a candidate placement violates repository architecture, the implementation must select the narrowest compliant location without changing repository semantics.

This design therefore freezes repository semantics, not package-layout mechanics for contract-support types.

### 8.1 Contract-Support Type Placement

Version 1.2 named `empirical_platform.shared.contracts` as the selected future location for shared repository contract-support types. Independent hostile review identified that this froze placement too early because the existing architecture checker treats the `shared` package as having no allowed imports, while some contemplated contract-support types may need identity or version typing.

Version 1.3 corrects that over-freeze.

The following contract-support concepts remain selected as part of the repository contract model:

- `SaveOperation`
- `SaveResult`
- `LoadedAggregate`
- `RepositoryContractError`
- `AggregateNotFound`
- `AggregateAlreadyExists`
- `OptimisticConcurrencyConflict`
- `InvalidAggregateForPersistence`
- `InvalidPersistedAggregateState`

However, their exact implementation module is not frozen by MILESTONE-020.

Implementation must place these concepts in the narrowest compliant location that preserves all of the following:

- aggregate-specific public repository contracts remain the domain-facing ports;
- repository semantics do not change;
- dependency direction remains valid;
- architecture-checker rules are not bypassed;
- no import cycle is introduced;
- aggregate root modules do not import repository modules;
- repository contracts do not import infrastructure packages;
- shared packages do not become dumping grounds for unrelated contracts.

This correction does not authorize modifying architecture rules. If the current architecture rules make a candidate placement non-compliant, implementation must choose a compliant placement rather than weakening architecture boundaries.

This correction does not introduce any retry enum, retry field, retry policy type, or aggregate-kind enum. Callers may retry after reloading current state when an optimistic-concurrency conflict is reported, but retry policy remains application-owned.
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

Canonical identity uniqueness is frozen as repository-domain semantics.

Within one aggregate type:

- `governance_id` is unique;
- `runtime_id` is unique;
- both form one canonical `DomainIdentity` pairing.

`add()` must reject:

- duplicate `DomainIdentity`;
- duplicate `governance_id`;
- duplicate `runtime_id`.

This rule defines repository contract behavior only. It does not prescribe database schema, indexes, constraints, locking, storage layout, or mapper implementation.

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

Calling `save()` for an aggregate identity that has no persisted aggregate state shall raise `AggregateNotFound`.

`save()` must never:

- create;
- upsert;
- silently insert;
- reinterpret the operation as `add()`;
- report an optimistic-concurrency conflict for absence of persisted aggregate state.

Absence of persisted aggregate state is therefore distinguished from stale-write conflict. A stale-write conflict requires an existing persisted aggregate whose durable version does not match the caller-supplied expected persisted version.

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
- callers may retry after reloading current state;
- retry policy remains application-owned;
- no automatic retry;
- no blind overwrite;
- no aggregate mutation;
- no database exception leakage.

The conflict is optimistic-concurrency failure, not aggregate validation failure.

A missing persisted aggregate state is not an optimistic-concurrency conflict. `save()` on a non-persisted aggregate identity raises `AggregateNotFound` as defined in Section 17.

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

`SaveOperation` is a closed immutable enumeration containing exactly:

- `CREATED`
- `UPDATED`
- `UNCHANGED`

The exact implementation representation of `SaveOperation` remains implementation-defined, but no additional operation value is permitted by this contract.

No database metadata, row count, transaction ID, ETag, timestamp, session object, lock token, mapper record, or schema information is returned.

## 23. Error Taxonomy

Selected base:

```text
RepositoryContractError
```

Selected contract errors:

| Error | Base | Required context | Message rule |
| --- | --- | --- | --- |
| `AggregateNotFound` | `RepositoryContractError` | aggregate kind as descriptive text, identity | Safe message, no storage details |
| `AggregateAlreadyExists` | `RepositoryContractError` | aggregate kind as descriptive text, identity | Safe message, no uniqueness/index details |
| `OptimisticConcurrencyConflict` | `RepositoryContractError` | aggregate kind as descriptive text, identity, expected persisted version, aggregate current version, optional actual persisted version | Safe message, no SQL/driver details |
| `InvalidAggregateForPersistence` | `RepositoryContractError` | aggregate kind as descriptive text, identity if available, reason | Safe message |
| `InvalidPersistedAggregateState` | `RepositoryContractError` | aggregate kind as descriptive text, identity if available, reconstruction category/field when safe | Safe message |

`ReconstructionError` handling:

- ordinary callers do not receive raw reconstruction state;
- future repository implementations translate `ReconstructionError` to `InvalidPersistedAggregateState`;
- exception chaining may preserve original exception for logs/debugging, but the public contract error remains persistence-neutral.

Repository contract errors describe repository-domain semantics only.

Infrastructure failures are not repository-domain semantics. Failures such as:

- database unavailable;
- transaction failure;
- timeout;
- storage backend failure;
- ORM failure;
- driver failure;

must be translated into the existing persistence-neutral foundation/infrastructure exception hierarchy.

SQLAlchemy exceptions, psycopg exceptions, database-specific exceptions, SQLSTATE values, backend-specific details, storage-driver details, driver-specific details, and ORM-specific details must never cross the repository boundary.

This design does not introduce a new retry policy.

`LoadedAggregate` is a repository contract-support value type, not an error. Its exact implementation module is not frozen by this design and must follow Section 8.1 placement constraints.

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

- duplicate `DomainIdentity`;
- duplicate `governance_id`;
- duplicate `runtime_id`;
- duplicate identity;
- simulated concurrent create;
- no aggregate mutation by repository.

Required save tests:

- successful mutated aggregate save;
- save accepts aggregate plus explicit expected persisted version from `LoadedAggregate.persisted_version`;

- save on an aggregate identity with no persisted aggregate state raises `AggregateNotFound`;
- save on an aggregate identity with no persisted aggregate state does not create, upsert, silently insert, reinterpret as `add`, or raise `OptimisticConcurrencyConflict`;
- stale expected persisted version;
- unchanged save returns `UNCHANGED`;
- repeated save requires updated expected persisted version;
- save result operation and persisted version;
- atomic root, owned-collection, metadata, and history boundary.

Required error tests:

- exact contract error types;
- identity/version context;

- infrastructure failures do not leak SQLAlchemy, psycopg, SQLSTATE, database-specific, ORM-specific, driver-specific, or backend-specific details;
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
- require architecture-checker changes as a precondition of this design;
- freeze contract-support package placement before implementation-time architecture validation;

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

| ID | Severity | Section | Issue considered | Impact | Decision | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| M020-DESIGN-ISSUE-0001 | MAJOR | 15 | Initial draft risked conflating expected persisted version with aggregate current version. | Could allow blind overwrite or ambiguous repeated saves. | Added four-term version vocabulary and explicit expected-version save rule. | Resolved |
| M020-DESIGN-ISSUE-0002 | MAJOR | 14, 16 | Creation semantics initially risked requiring version zero for first persistence. | Would contradict process-local mutation before persistence. | Selected `add` and allowed any valid current aggregate version. | Resolved |
| M020-DESIGN-ISSUE-0003 | MAJOR | 18, 19 | Unchanged and repeated save behavior needed deterministic token propagation. | Future implementations could diverge. | Selected `UNCHANGED` SaveResult and required caller to use latest persisted version after save. | Resolved |
| M020-DESIGN-ISSUE-0004 | MAJOR | 26, 27 | Tracked repositories could smuggle Unit of Work behavior into contracts. | Hidden state and transaction coupling. | Selected detached aggregates and explicit expected-version passing. | Resolved |
| M020-DESIGN-ISSUE-0005 | MAJOR | 8, 24 | Repository placement near aggregate packages could expose reconstruction internals. | Public callers might import `_reconstruction`. | Selected aggregate-local repository modules but kept reconstruction internal and required future architecture checks. | Resolved |
| M020-DESIGN-ISSUE-0006 | MINOR | 23 | Infrastructure availability errors were tempting to add to domain taxonomy. | Could leak foundation error concerns into domain contracts. | Kept domain repository errors focused and deferred infrastructure failure classification. | Resolved |
| M020-DESIGN-ISSUE-0007 | MAJOR | 23 | Infrastructure failures could leak database/ORM/driver details. | Callers could become coupled to backend-specific exception behavior. | Require translation into the existing persistence-neutral foundation/infrastructure exception hierarchy. | Resolved |
| M020-DESIGN-ISSUE-0008 | MINOR | 22 | `SaveOperation` conceptual shape could vary. | Repository implementations could expose incompatible public result shapes. | Select a closed immutable enumeration containing exactly `CREATED`, `UPDATED`, and `UNCHANGED`. | Resolved |
| M020-DESIGN-ISSUE-0009 | MINOR | 28 | `exists()` could sneak in as creation convenience. | A preflight check could be mistaken for an atomic concurrency guarantee. | Exclude `exists()` and make atomic `add` authoritative. | Resolved |
| M020-DESIGN-ISSUE-0010 | MINOR | 20, 23 | Retry behavior could become a repository-owned policy or public enum. | Repository contracts could improperly prescribe application orchestration. | Define no retry enum or field; callers may retry only after reload, while policy remains application-owned. | Resolved |

All CRITICAL and MAJOR issues recorded in this self-review have proposed resolutions. Independent verification remains pending.

### 33.1 Independent Hostile Review Correction Log

| ID | Severity | Section | Finding | Correction | Disposition |
| --- | --- | --- | --- | --- | --- |
| M020-INDEPENDENT-0001 | MAJOR | 8, 22, 23, 29 | Shared contract value/error types had no exact placement. | Version 1.1 named `shared.contracts`; Version 1.3 supersedes that over-freeze and leaves exact implementation module placement subject to dependency direction, architecture checker, import-cycle, bounded-context, and shared-package constraints. | Resolved |
| M020-INDEPENDENT-0002 | MAJOR | 11 | Identity-based loading versus governance-ID-only discovery was implicit. | Section 11.1 explicitly states repositories support identity-based loading only and defer identity discovery. | Resolved |
| M020-INDEPENDENT-0003 | MAJOR | 12, 19, 27 | Bare aggregate loading made persisted-version token capture unsafe after mutation. | `LoadedAggregate[AggregateT]` with immutable `persisted_version` selected. | Resolved |
| M020-HOSTILE-0001 | MAJOR | 8, 8.1 | `shared.contracts` was frozen too early and may conflict with current architecture rules. | Exact module placement is no longer frozen. Implementation must choose the narrowest compliant placement without changing repository semantics and without requiring architecture-checker changes. | Resolved |
| M020-HOSTILE-0002 | MAJOR | 17, 20, 29 | `save()` on a missing persisted aggregate was not explicitly frozen. | `save()` on absent persisted aggregate state raises `AggregateNotFound`; it never creates, upserts, silently inserts, reinterprets as `add`, or reports optimistic-concurrency conflict. | Resolved |
| M020-HOSTILE-0003 | MAJOR | 16, 29 | DomainIdentity uniqueness was ambiguous between full pair, governance ID, and runtime ID. | Per aggregate type, `governance_id` is unique, `runtime_id` is unique, and both form one canonical `DomainIdentity`; `add()` rejects duplicate pair, duplicate governance ID, and duplicate runtime ID. | Resolved |
| M020-HOSTILE-0004 | MAJOR | 23, 29 | Infrastructure failure surface was undefined. | Repository contract errors are limited to repository-domain semantics; infrastructure failures must be translated into the existing persistence-neutral foundation/infrastructure exception hierarchy without leaking backend details. | Resolved |
| M020-HOSTILE-0005 | MINOR | 22 | `SaveOperation` exact conceptual API was under-frozen. | `SaveOperation` is a closed immutable enumeration containing exactly `CREATED`, `UPDATED`, and `UNCHANGED`; exact implementation representation remains implementation-defined. | Resolved |
| M020-HOSTILE-0006 | MINOR | 8, 20, 23 | A retry marker could be mistaken for a public contract field or enum. | The marker is removed. The design states only that callers may retry after reloading current state, while retry policy remains application-owned. | Resolved |

All CRITICAL and MAJOR findings recorded for Correction Pass v3 have proposed resolutions. Independent verification remains pending.

### 33.2 Correction Pass v3 Hostile Self-Review

1. Did any correction widen scope?

No. The corrections only clarify repository contract design semantics already within M020: placement constraints, save absence behavior, identity uniqueness, infrastructure failure boundary, save result operation vocabulary, and application ownership of retry policy. No implementation, schema, mapper, query, API, worker, Unit of Work, retry-policy implementation, or storage design is introduced.

2. Did any correction redesign M020?

No. M020 remains an aggregate-specific, synchronous, domain-facing repository contract design with explicit optimistic concurrency. The corrections remove ambiguity without changing the selected architecture, operation model, tracking model, or deferred implementation scope.

3. Did any correction modify frozen M019 behavior?

No. Reconstruction remains internal to mapper/repository implementation flow. No reconstruction state record, `_reconstruct_*` factory, aggregate behavior, or M019 contract is changed.

4. Did any correction require changing architecture rules?

No. Version 1.3 explicitly avoids authorizing architecture-checker changes. If a candidate module placement violates architecture rules, implementation must choose a compliant placement rather than weakening the checker.

5. Are any unresolved architectural ambiguities still present?

No unresolved architecture ambiguity remains that blocks design approval. Exact code module placement for contract-support types remains intentionally implementation-defined, but the selection criteria are now constrained: dependency direction, architecture checker, import-cycle absence, bounded-context ownership, and shared package constraints. That is an implementation placement decision, not an unresolved repository semantics decision.

6. Is implementation now sufficiently constrained?

Yes. Implementation is constrained on repository operations, identity inputs, creation uniqueness, save-on-missing behavior, optimistic concurrency, unchanged save, repeated save, loaded-version token preservation, error taxonomy, infrastructure failure translation, `SaveOperation` vocabulary, contract-test obligations, application-owned retry policy, and forbidden leakage of storage details.

### 33.3 Independent Hostile Review (Version 1.3, Session Pass)

An independent review was performed against Version 1.3 with live repository evidence, cross-checking every claim in this document against current source:

- `AggregateVersion` (`src/empirical_platform/shared/domain/versioning.py`) is a frozen, `order=True` dataclass with a non-negative `int` value and `initial()`/`next()` helpers. This supports the equality and ordering comparisons Section 17 relies on (`current >= expected`), confirming the concurrency comparison is technically realizable as described.
- `DomainIdentity[GovernanceIdentifierT]` (`src/empirical_platform/identifiers/pairs.py`) confirms the frozen `governance_id`/`runtime_id` pairing exactly as described in Sections 11 and 11.1.
- `PersistenceService`/`PersistenceUnitOfWork` (`src/empirical_platform/shared/interfaces/persistence.py`) confirm the infrastructure-only, domain-repository-free state described in Section 4 and the Scope Selection document's persistence inventory.
- `src/empirical_platform/shared/contracts/__init__.py` is confirmed empty (docstring only), consistent with Section 8.1's statement that no contract-support type placement is yet frozen or occupied.

No MAJOR or CRITICAL finding was identified. Three MINOR markdown spacing defects were found and corrected (duplicated blank lines before Section 16's closing sentence and before Section 22's closing sentence; a missing blank line before the `ReconstructionError` handling paragraph in Section 23, which ran directly against the preceding table row). These are formatting-only corrections with no semantic, architectural, or scope effect.

Canonical local validation was re-executed directly (not assumed from a prior report) against the project's pinned virtual environment (`.venv`, Python 3.13.14, matching `requires-python = ">=3.13,<3.14"`):

| Check | Result |
| --- | --- |
| `ruff format --check .` | PASS (110 files already formatted) |
| `ruff check .` | PASS (all checks passed) |
| `mypy` | PASS (0 issues, 63 source files) |
| `tools/check_architecture.py .` | PASS (0 violations) |
| `tools/check_architecture.py tests/fixtures/illegal_imports` (negative fixture) | PASS (9 violations correctly detected) |
| `python -m compileall -q src tests tools migrations` | PASS |
| `python -m pip_audit` | PASS (no known vulnerabilities; own unpublished package correctly skipped) |
| `python -m detect_secrets scan <discovered targets>` | PASS (0 findings across 200 discovered targets) |
| `git diff --check` | PASS (CRLF-conversion notices only, no whitespace errors) |
| `python -m build` | PASS |
| `python -c "import empirical_platform; print(...__version__)"` | PASS (`0.0.0`) |
| `pytest` (repository test suite, isolated from the machine-local locked temp path via `--basetemp`) | PASS (244 passed, 9 skipped, 91.93% coverage) |
| `pytest` (literal default invocation, no `--basetemp`, on this machine) | ENVIRONMENT-BLOCKED — exits 1 during teardown; not PASS; see Section 33.4 and Section 33.5 |

This independent review's raw command evidence was captured locally under `.validation-proof-m020/` (session-local, not part of this commit).

### 33.4 Root Cause of the Initially Reported `pytest` Failure

Version 1.4 reported a `pytest` collection failure (`ModuleNotFoundError: No module named 'tools'`) as a pre-existing, unrelated repository risk. Explicit instruction was given not to assume `tools/__init__.py` is the correct fix and to determine the true root cause before touching anything. Investigation, in order:

1. **pytest configuration** (`[tool.pytest.ini_options]` in `pyproject.toml`): no `pythonpath` setting, no `rootdir` override.
2. **Repository layout**: no `conftest.py` anywhere in the repository; no `__init__.py` under `tests/` at any level; `tools/` has no `__init__.py` either.
3. **Import path mechanics**: pytest's default `prepend` import mode inserts, for each test module, the nearest ancestor directory that does *not* contain `__init__.py`. For `tests/architecture/test_module_boundaries.py`, since `tests/architecture/` itself has no `__init__.py`, pytest inserts only `tests/architecture` onto `sys.path`, never the repository root, so a bare-package import like `from tools.check_architecture import ...` cannot resolve.
4. **`pyproject.toml` packaging**: `[tool.setuptools.packages.find] where = ["src"]` confirms `empirical_platform` is installed editable (hence importable from anywhere), while `tools/` is intentionally never packaged or installed — it is a repository-root developer/CI tool, not a distributed package.
5. **Historical commits**: `git log` confirms `tests/architecture/test_module_boundaries.py` and `tests/unit/test_secret_scan_targets.py` were added by the MILESTONE-017 and MILESTONE-019 commits respectively, unchanged since.
6. **Canonical invocation, per `scripts/verify.ps1` (line 24)**: the repository's own authoritative validation script invokes `python @("-m", "pytest")`, never the bare `pytest` console-script entry point.

Reproducing both invocations confirmed the first part of the root cause: **the `ModuleNotFoundError: No module named 'tools'` collection failure reported in Version 1.4 is fixed by invocation alone, with zero repository changes.** Python's `-m` flag inserts the current working directory onto `sys.path[0]` before the module runs, which is sufficient by itself to make the repository-root `tools` namespace package importable — no `__init__.py`, no `pythonpath` setting, and no other configuration change is needed or correct. That specific failure was produced by invoking the bare `pytest` console-script (which does not add the working directory to `sys.path`), not by any defect in the repository. Adding `tools/__init__.py` would not have been the true fix and was correctly not applied.

A second, unrelated issue surfaced once collection succeeded: `python -m pytest` completed all 244 tests (9 skipped) and then crashed during its own teardown (`_pytest/pathlib.py: cleanup_dead_symlinks`) with `PermissionError: WinError 5` while purging a stale, OS-level, locked reparse point (`%LOCALAPPDATA%\Temp\pytest-of-LuxSy\pytest-current`) left over from prior validation runs on this machine. This directory is pytest's own disposable scratch space, entirely outside the git repository, and the lock could not be released by this session (verified undeletable via `rm`, PowerShell `Remove-Item`, .NET `Directory.Delete`, and `cmd /c rmdir`, all denied — consistent with an external process, such as antivirus real-time scanning, holding the handle). This is a local-machine condition, not a repository defect, not business logic, and not something a source or configuration change should work around. Passing `--basetemp` to point pytest at a clean scratch directory for the invocation avoided the locked location without changing any tracked file. All 244 tests pass, 9 skipped (tests marked `integration`, requiring local external dependencies not running in this session), coverage 91.93% against an 80% gate.

No repository file was created, deleted, or modified to reach this result. The repository was never broken; the collection-time invocation artifact was corrected by understanding, not by code change. The teardown lock, addressed in Section 33.5, remains a live, reproducible, machine-local limitation rather than a one-time fluke.

### 33.5 Correction: the Literal Default Invocation Remains Environment-Blocked

A dedicated validation evidence package was subsequently generated at `validation-evidence/M020/`, capturing the complete, unedited output of the exact literal command:

```text
python -m pytest tests -ra --cov=empirical_platform --cov-report=term-missing
```

This literal invocation, with no `--basetemp` override, was run again on this machine and **exited 1**, reproducing the identical `cleanup_dead_symlinks` / `PermissionError: WinError 5` teardown crash against the same locked `%LOCALAPPDATA%\Temp\pytest-of-LuxSy\pytest-current` path described above. Confirmed via direct inspection of the raw output (`validation-evidence/M020/02_pytest.txt`): all 244 tests completed, `[100%]` progress reached, zero `F`/`FAILED` markers, and the failure occurs strictly after test execution, in pytest's own teardown hook.

This corrects an overclaim made earlier in this section and in Version 1.5: it is not accurate to say the literal default invocation "already succeeds" on this machine. The lock is persistent across sessions, not transient, and the literal invocation will keep exiting 1 on this machine until whatever external process holds that handle releases it, or the stale temp directory is cleared outside this session. A supplementary capture using `--basetemp` (`validation-evidence/M020/02b_pytest_supplementary_clean_basetemp.txt`) confirms the repository test suite itself remains healthy (244 passed, 9 skipped, 91.93% coverage) once isolated from the locked path.

The distinction this document now holds precisely:

- repository test suite: **PASS** — 244 passed, 9 skipped, 91.93% coverage, verified using an isolated `--basetemp`;
- literal default `pytest` invocation on this machine: **ENVIRONMENT-BLOCKED** during teardown by a locked OS temp path — not PASS, exit code 1, honestly recorded and not relabeled;
- repository defect: none identified;
- machine-local limitation: remains open and documented; it is outside the repository and outside this document's scope to fix.

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
| Exact contract-support module placement intentionally deferred to implementation-time architecture validation | PASS (Version 1.3) |
| Identity-based loading versus identity discovery distinguished | PASS (Version 1.1) |
| Persisted-version token acquisition safely preserved by `LoadedAggregate` | PASS (Version 1.2) |
| Independent hostile review performed against live repository evidence | PASS (Version 1.2) |
| Canonical DomainIdentity uniqueness semantics frozen | PASS (Version 1.3) |
| Save on missing persisted aggregate state explicitly raises `AggregateNotFound` | PASS (Version 1.3) |
| Retry policy remains application-owned without public retry enum or field | PASS (Version 1.3) |
| `SaveOperation` closed conceptual enumeration frozen | PASS (Version 1.3) |
| Infrastructure failure boundary clarified without new retry policy | PASS (Version 1.3) |
| M019 frozen behavior preserved | PASS |
| No architecture-checker change authorized | PASS |
| Independent hostile review findings addressed in documentation | PASS (Version 1.3) |
| Independent review of Version 1.3 completed | PASS (Version 1.4, Section 33.3) |
| M020 frozen | NO |
| Canonical local validation (ruff, mypy, `tools/check_architecture.py`, `compileall`, `pip_audit`, `detect_secrets`, `git diff --check`, `build`) rerun after correction against project virtual environment | PASS (Version 1.5, Sections 33.3-33.4) |
| `pytest` repository test suite (244 passed, 9 skipped, 91.93% coverage), isolated from the machine-local locked temp path via `--basetemp` | PASS (Version 1.6, Section 33.5) |
| `pytest` literal default invocation (`python -m pytest tests -ra --cov=empirical_platform --cov-report=term-missing`, no `--basetemp`) on this machine | ENVIRONMENT-BLOCKED — exits 1 during teardown; not PASS (Version 1.6, Section 33.5; raw evidence `validation-evidence/M020/02_pytest.txt`) |

## 35. Final Decision

MILESTONE-020 selects aggregate-specific, synchronous, aggregate-local future repository contracts with explicit optimistic-concurrency semantics.

Version 1.3 applies documentation-only corrections identified by independent hostile review:

- exact contract-support module placement is no longer frozen prematurely;
- `save()` on a missing persisted aggregate state explicitly raises `AggregateNotFound`;
- per-aggregate canonical `DomainIdentity` uniqueness is frozen across `governance_id`, `runtime_id`, and their pairing;
- infrastructure failures are excluded from repository-domain contract errors and must be translated into the existing persistence-neutral foundation/infrastructure exception hierarchy;
- `SaveOperation` is frozen as a closed immutable conceptual enumeration containing exactly `CREATED`, `UPDATED`, and `UNCHANGED`;
- no retry enum or retry field is introduced; callers may retry after reloading current state, while retry policy remains application-owned.

No architecture-checker change, no source implementation, no tests, no package-layout change, no schema, no mapper, no migration, no repository implementation, no previous frozen milestone document, and no M019 behavior is changed by this correction pass.

Version 1.4 performs the independent hostile review of Version 1.3 and the canonical local validation rerun that Version 1.3 left pending, both against live repository evidence and the project's pinned virtual environment. No MAJOR or CRITICAL finding was raised; three cosmetic markdown spacing defects were corrected. Version 1.4 reported a `pytest` collection failure as an open repository risk.

Version 1.5 root-causes that reported failure per Section 33.4: it was not a repository defect. The collection-time `ModuleNotFoundError` was produced by invoking the bare `pytest` console-script instead of `python -m pytest` (the invocation the repository's own `scripts/verify.ps1` already uses); a second, separate issue is a stale, locked, OS-level pytest temp directory on this machine that is outside the repository entirely. No `__init__.py`, `pythonpath` setting, or any other repository change was made or was needed for either finding.

Version 1.6 corrects an overclaim in Version 1.5. A dedicated evidence package (`validation-evidence/M020/`) reproduced the exact literal default `pytest` invocation and recorded that it still exits 1 on this machine, honestly and without relabeling: all 244 tests complete with zero `FAILED` markers, and the failure occurs strictly in pytest's own teardown against the locked temp path, reproducibly, not as a one-time fluke. The repository test suite itself is confirmed healthy — 244 passed, 9 skipped, 91.93% coverage — only when verified with an isolated `--basetemp`. This document therefore holds two distinct, non-conflated facts: the repository test suite passes, and the literal default invocation on this machine is environment-blocked. Canonical local validation covering ruff, mypy, the architecture checker, `compileall`, `pip_audit`, `detect_secrets`, `git diff --check`, and `build` passes without qualification.

This document does not mark MILESTONE-020 frozen. Freezing requires a clean repository status and an authorized freeze decision by the Project Owner. Independent review and canonical local validation are complete; the repository test suite passes; the literal default `pytest` invocation remains environment-blocked on this machine by a condition outside the repository, and this document does not claim otherwise.

Final status:

```text
DESIGN READY FOR COMMIT - TEST SUITE PASS VIA ISOLATED BASETEMP,
LITERAL PYTEST INVOCATION ENVIRONMENT-BLOCKED (MACHINE-LOCAL) -
FREEZE PENDING PROJECT OWNER DECISION
```
