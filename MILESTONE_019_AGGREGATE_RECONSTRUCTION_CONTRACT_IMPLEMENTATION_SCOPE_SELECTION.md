# MILESTONE-019 - Aggregate Reconstruction Contract Implementation Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-019 |
| Title | Aggregate Reconstruction Contract Implementation Scope Selection |
| Version | 1.0 |
| Status | IMPLEMENTATION SCOPE CANDIDATE SELECTED |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen design baseline | `6afb28028197ffd77a11708e15a671b2a97e3837` |
| Design authority | `MILESTONE_019_AGGREGATE_RECONSTRUCTION_CONTRACT_DESIGN.md` |
| Mission type | Scope selection only |
| Implementation performed | No |
| Source modified | No |
| State records or factories created | No |
| Repositories, schemas, migrations, APIs, workers, runtime composition, or persistence implementations created | No |

## 2. Frozen Design Baseline

The authoritative frozen design baseline is:

```text
6afb28028197ffd77a11708e15a671b2a97e3837
```

That baseline approves an aggregate-specific internal reconstruction design for the four frozen process-local aggregates:

- Campaign;
- Run;
- EvidencePackage;
- Review.

The design authorizes future package-internal `_reconstruction` modules, persistence-neutral reconstruction state records, one common reconstruction error with reason/category enum, bounded shared helpers, architecture-checker enforcement, and focused tests. It explicitly excludes repositories, mappers, schemas, migrations, SQL, ORM, APIs, workers, runtime behavior, event sourcing, outbox, Audit runtime, Decision Candidate, Decision Freeze, trading logic, vendor behavior, and empirical execution.

## 3. Implementation Problem

The process-local aggregates are frozen for ordinary creation and mutation, but they cannot yet be safely restored from durable metadata. Public constructors create only initial state and public mutation methods would replay behavior, increment versions, consume transition sequences, append new transition records, and enforce terminal guards.

The implementation problem is therefore narrow:

```text
Implement the frozen persistence-neutral reconstruction contract without creating persistence.
```

The next implementation must provide enough domain-side reconstruction capability for later repository and mapper design while preserving the current public aggregate behavior.

## 4. Candidate Slices

| Candidate | Description | Initial disposition |
| --- | --- | --- |
| A. All Four Aggregate Reconstruction Contracts | Implement state records, common error/category, bounded helpers, aggregate-specific internal factories, architecture rules, tests, and report for Campaign, Run, EvidencePackage, and Review together. | Selected |
| B. Shared Reconstruction Foundation Only | Implement only common error/category types and shared helper primitives. | Rejected |
| C. One Aggregate Pilot | Implement reconstruction for only one aggregate. | Rejected |
| D. Two-Phase Implementation | Phase one implements state records, error model, and architecture boundaries; phase two implements factories and tests. | Rejected |
| E. Aggregate-by-Aggregate Milestones | Separate Campaign, Run, EvidencePackage, and Review reconstruction implementation into four milestones. | Rejected |

## 5. Comparison Matrix

| Candidate | Boundary | Files likely changed | Contracts implemented | Partial-state risk | Consistency risk | Implementation risk | Review complexity | Architecture impact | Future repository readiness | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A. All Four Aggregate Reconstruction Contracts | One bounded reconstruction layer for all frozen aggregates | Four `_reconstruction.py` modules, shared reconstruction error/helper module, aggregate modules if hooks are required, architecture checker, tests, report | Complete M019 design contract | LOW | LOW | MEDIUM | MEDIUM | MEDIUM | HIGH | Selected |
| B. Shared Reconstruction Foundation Only | Common types without aggregate reconstruction | Shared error/helper module, tests | Error/helper subset only | HIGH | MEDIUM | LOW | LOW | LOW | LOW | Rejected |
| C. One Aggregate Pilot | One aggregate reconstruction path | One `_reconstruction.py`, possibly one aggregate hook, tests | One partial contract | HIGH | HIGH | LOW | LOW | LOW | LOW | Rejected |
| D. Two-Phase Implementation | State records and boundaries first, factories later | State record modules, error/helper module, architecture checker, later factories | Incomplete until phase two | MEDIUM | MEDIUM | MEDIUM | MEDIUM | MEDIUM | MEDIUM | Rejected |
| E. Aggregate-by-Aggregate Milestones | Four sequential aggregate-specific implementations | One package per milestone plus repeated tests and checker changes | Complete only after final aggregate | HIGH | HIGH | LOW per slice, HIGH cumulative | MEDIUM | MEDIUM | MEDIUM delayed | Rejected |

## 6. Selected Scope

Selected implementation scope:

```text
MILESTONE-019 - Aggregate Reconstruction Contract Implementation
```

The repository convention supports retaining M019 because M019 already contains scope selection and frozen design for the same reconstruction bridge. Starting M020 would incorrectly imply a new architectural topic rather than implementation of the frozen M019 design.

The selected scope is Candidate A: implement the complete M019 reconstruction contract for Campaign, Run, EvidencePackage, and Review in one bounded milestone.

This remains one bounded milestone because:

- the frozen design already resolves the architecture and state fields;
- each aggregate receives one internal reconstruction module with the same narrow purpose;
- all four aggregates share one error shape and a small set of genuinely common validation helpers;
- splitting would leave partial reconstruction capability that later repository contracts could accidentally treat as complete;
- independent hostile review can focus on one coherent boundary: reconstruction only.

## 7. Aggregate Coverage

The implementation scope includes all four frozen process-local aggregates:

| Aggregate | Scope |
| --- | --- |
| Campaign | Restore identity, scope statement, lifecycle state, version, next transition sequence, and transition history. |
| Run | Restore identity, Campaign context ID, lifecycle state, version, next transition sequence, transition history, ordered DatasetManifest tuple, and derived current manifest. |
| EvidencePackage | Restore identity, Run context ID, lifecycle state, version, next transition sequence, transition history, ordered CriterionResult tuple, and ordered ArtifactReference tuple. |
| Review | Restore identity, target reference, reviewer reference, lifecycle state, version, next transition sequence, transition history, ordered findings, disposition, final rationale, cancellation reason, and derived next finding sequence. |

No Campaign, Run, EvidencePackage, or Review public business method behavior may be changed.

## 8. State Records

Concrete immutable state records are authorized in this implementation milestone.

Required records:

- `CampaignReconstructionState`;
- `RunReconstructionState`;
- `EvidencePackageReconstructionState`;
- `ReviewReconstructionState`.

Placement:

- `empirical_platform.campaign._reconstruction`;
- `empirical_platform.run._reconstruction`;
- `empirical_platform.evidence._reconstruction`;
- `empirical_platform.review._reconstruction`.

Implementation conventions:

- frozen dataclasses with slots, or an equivalent immutable typed Python representation if independently justified during implementation;
- exact fields from frozen M019 Sections 12 through 15;
- tuple fields for histories and owned collections;
- optional terminal metadata fields only where frozen design permits them;
- defensive tuple materialization for iterable inputs;
- no SQL, ORM, schema, column, table, mapper, serializer, repository, or persistence metadata;
- no object-storage key, bucket, checksum, retention, or layout metadata;
- no public package re-export from `__init__.py`.

State records are reconstruction inputs only. They are not persistence models, API DTOs, database rows, serialization contracts, or event payloads.

## 9. Internal Factories

Required internal factory functions:

| Aggregate | Module path | Factory name | Input | Output |
| --- | --- | --- | --- | --- |
| Campaign | `empirical_platform.campaign._reconstruction` | `reconstruct_campaign` | `CampaignReconstructionState` | `Campaign` |
| Run | `empirical_platform.run._reconstruction` | `reconstruct_run` | `RunReconstructionState` | `Run` |
| EvidencePackage | `empirical_platform.evidence._reconstruction` | `reconstruct_evidence_package` | `EvidencePackageReconstructionState` | `EvidencePackage` |
| Review | `empirical_platform.review._reconstruction` | `reconstruct_review` | `ReviewReconstructionState` | `Review` |

Factory responsibilities:

- validate the supplied state type;
- validate aggregate identity type;
- validate lifecycle type;
- validate version and transition sequence;
- validate transition history identity, order, sequence continuity, lifecycle path, terminal placement, and final state;
- validate aggregate-specific collections and terminal metadata;
- allocate and return a fully restored aggregate atomically;
- preserve supplied version, next transition sequence, transition history, collection order, and terminal metadata exactly;
- perform no version increment, sequence advancement, transition append, clock access, lookup, repository access, logging side effect, audit emission, event emission, or outbox write.

Factories may use a narrow package-internal aggregate reconstruction hook if direct allocation would otherwise require unsafe private mutation. They must not call public lifecycle or content mutation methods to replay state.

## 10. Error Model

The implementation scope authorizes:

- `ReconstructionError`;
- `ReconstructionErrorCategory`.

Placement should be shared and domain-neutral, preferably under `empirical_platform.shared.domain` or another existing shared domain boundary selected during implementation. The chosen placement must not import persistence, logging, configuration, health, runtime composition, SQL, ORM, object storage, repositories, APIs, or workers.

Required category values:

- `WrongReconstructionInput`;
- `InvalidAggregateIdentity`;
- `InvalidLifecycleState`;
- `InvalidAggregateVersion`;
- `InvalidTransitionSequence`;
- `InvalidTransitionHistory`;
- `InconsistentCurrentState`;
- `InvalidCollectionElement`;
- `DuplicateOwnedValue`;
- `InconsistentTerminalMetadata`;
- `UnauthorizedReconstructionPath`.

Required error shape:

- exception inheritance from `Exception`;
- required `category` property;
- human-readable message;
- optional safe field or context identifier;
- optional exception chaining is permitted for local validation causes only;
- no database, SQLAlchemy, psycopg, S3, MinIO, object-storage, runtime, or infrastructure category.

## 11. Allowed Aggregate Changes

Aggregate source changes are allowed only when strictly necessary for atomic reconstruction.

Allowed:

- a package-internal reconstruction constructor, hook, token, or helper used only by the same package's `_reconstruction` module;
- narrow internal assignment path that sets already-validated state exactly once;
- comments only where needed to distinguish public creation from internal reconstruction.

Required constraints:

- preserve normal public constructor behavior;
- preserve all public mutation behavior;
- do not add public `from_state`, `load`, `restore`, `reconstruct`, `save`, or repository-like APIs;
- do not export reconstruction hooks;
- do not import reconstruction modules from aggregate modules unless an internal token/hook pattern proves unavoidable and remains package-local;
- do not import persistence, SQL, ORM, object storage, logging, health, runtime composition, repositories, mappers, APIs, workers, Audit, Decision Candidate, or Decision Freeze concepts;
- do not broaden normal creation constructor signatures.

Broad refactoring is prohibited.

## 12. Architecture Rules

The implementation scope authorizes focused updates to `tools/check_architecture.py` and architecture tests.

Required enforceable rules:

- `_reconstruction` modules are not publicly re-exported from package `__init__.py`;
- `_reconstruction` modules may not import `shared.persistence`, concrete persistence adapters, object-storage adapters, SQLAlchemy, psycopg, boto3, runtime composition, repositories, mappers, APIs, workers, tests, or unrelated domain packages;
- aggregate modules may not import repositories, mappers, persistence, SQL, ORM, object storage, APIs, workers, Audit, Decision Candidate, or Decision Freeze;
- ordinary unrelated domain packages may not import another package's `_reconstruction` module;
- current negative fixtures should cover only currently enforceable forbidden directions.

The current checker skips underscore-prefixed modules. The implementation may adjust that behavior only as needed to enforce the rules above. It must not invent broad permissions for future repository or mapper packages that do not yet exist.

## 13. Unit-Test Requirements

State record tests must cover:

- immutability;
- exact field typing;
- defensive tuple materialization;
- no mutable input retention;
- no public package export.

Successful reconstruction tests must cover every aggregate:

- initial lifecycle state;
- each non-initial lifecycle state;
- terminal states;
- populated owned collections where applicable;
- exact version preservation;
- exact next sequence preservation;
- exact transition-history preservation;
- continued valid mutation after reconstruction.

Malformed state tests must cover:

- wrong input type;
- wrong identity type;
- lifecycle/history mismatch;
- invalid lifecycle transition edge;
- sequence gaps, duplicates, non-start-at-one histories, and next-sequence mismatch;
- history identity mismatch;
- final-state mismatch;
- under-versioned restored state;
- duplicate owned values;
- collection identity mismatch;
- terminal metadata mismatch.

Non-effect tests must cover:

- no version increment during reconstruction;
- no sequence increment during reconstruction;
- no history append during reconstruction;
- no clock access;
- no external lookup;
- no persistence dependency;
- no event or audit emission.

Private-field inspection is allowed only in reconstruction-specific tests where no public property exposes required restored internal state, such as Review next finding sequence.

## 14. Compatibility Guarantees

The implementation must preserve:

- all public constructors;
- all public lifecycle/content methods;
- all lifecycle enum values;
- `AggregateVersion` semantics;
- `TransitionSequence` semantics;
- `StateTransitionRecord` as historical data only;
- owned collection ordering and duplicate rules;
- terminal immutability;
- package import boundaries;
- absence of repository, schema, migration, API, worker, runtime, Audit, Decision Candidate, Decision Freeze, trading, vendor, and empirical execution behavior.

Future support for repository contracts must be enabled only by providing a domain-side reconstruction boundary, not by implementing repository contracts during this milestone.

## 15. Explicit Non-Goals

This implementation scope excludes:

- repository contracts;
- repository implementations;
- not-found behavior;
- save behavior;
- optimistic concurrency save behavior;
- Unit of Work;
- persistence mappers;
- serializers;
- schemas;
- migrations;
- SQL;
- ORM;
- PostgreSQL integration;
- APIs;
- workers;
- outbox;
- runtime composition;
- Audit;
- Decision Candidate;
- Decision Freeze;
- event sourcing;
- trading logic;
- vendor behavior;
- market-data behavior;
- empirical campaign execution.

`migrations/versions` must remain empty.

## 16. Risks

| Risk | Severity | Mitigation |
| --- | --- | --- |
| All-four-aggregate scope becomes too broad | MAJOR | Keep implementation limited to state records, factories, common error/helper code, architecture rules, tests, and report. |
| State records become persistence models | MAJOR | Prohibit SQL, ORM, schema, mapper, serializer, and storage metadata. |
| Generic helper framework grows beyond evidence | MAJOR | Permit only genuinely identical helpers; keep lifecycle, collection, terminal, and version floors aggregate-specific unless identical behavior is proven. |
| Reconstruction becomes public API | MAJOR | Use underscore modules, avoid `__init__.py` exports, and add architecture tests. |
| Aggregate hooks weaken public behavior | CRITICAL | Hooks must be package-internal, used only by reconstructors, and preserve all public constructor and mutation behavior. |
| Error model leaks infrastructure categories | MAJOR | Keep reconstruction errors domain-neutral and persistence-neutral. |
| Partial implementation misleads future repositories | MAJOR | Implement all four aggregate contracts together or stop before commit. |

## 17. Hostile-Review Criteria

Independent review must verify:

- all four aggregate contracts are implemented or the milestone remains revision required;
- no aggregate source was broadly refactored;
- no public reconstruction API was introduced;
- no reconstruction symbol is exported from package `__init__.py`;
- state records are immutable and persistence-neutral;
- factories reject malformed state atomically;
- continued mutation after reconstruction preserves version, sequence, history, and terminal guards;
- common helpers do not overgeneralize aggregate-specific lifecycle, collection, terminal metadata, or version-floor rules;
- architecture checker enforces currently enforceable boundaries;
- no repository, mapper, schema, migration, API, worker, runtime composition, Audit, Decision Candidate, Decision Freeze, trading, vendor, or execution behavior was added.

## 18. Acceptance Gate

| Gate | Required result |
| --- | --- |
| Frozen baseline verified | PASS |
| All four reconstruction state records implemented | PASS |
| All four internal factories implemented | PASS |
| Common reconstruction error/category implemented | PASS |
| Shared helpers limited to identical behavior | PASS |
| Aggregate source changes narrow and justified | PASS or NOT APPLICABLE |
| Architecture checker updated for reconstruction boundary | PASS |
| State-record tests complete | PASS |
| Successful reconstruction tests complete | PASS |
| Malformed-state tests complete | PASS |
| Non-effect tests complete | PASS |
| Public export checks complete | PASS |
| `security.ps1` passes | PASS |
| `verify.ps1` passes | PASS |
| Ruff, mypy, architecture checker, and `git diff --check` pass | PASS |
| `migrations/versions` remains empty | PASS |

## 19. Stop Conditions

Stop the implementation if:

- a repository, mapper, schema, migration, API, worker, runtime composition, outbox, Audit, Decision Candidate, or Decision Freeze concept is required;
- reconstruction requires persistence adapter private-field mutation;
- public constructors must accept persisted state;
- a public `from_state`, `load`, `save`, or repository-like aggregate API is introduced;
- one aggregate can be reconstructed but another requires a contradictory contract;
- common helpers require generic lifecycle or terminal metadata abstractions that obscure aggregate-specific rules;
- a source contradiction with frozen M019 design is discovered;
- validation fails and cannot be corrected inside the M019 reconstruction boundary.

## 20. Deferred Work

Deferred beyond this implementation scope:

- repository contract scope selection and design;
- repository implementation;
- persistence mapper design and implementation;
- schemas, migrations, tables, and ORM mapping;
- optimistic concurrency save behavior;
- Unit of Work integration;
- application services and command handlers;
- cross-aggregate invariant enforcement;
- idempotency keys;
- outbox and job ledger;
- Audit runtime;
- Decision Candidate runtime;
- Decision Freeze;
- campaign execution and empirical validation behavior.

## 21. Final Decision

The selected implementation scope is:

```text
MILESTONE-019 - Aggregate Reconstruction Contract Implementation
```

This scope implements all four frozen aggregate reconstruction contracts together because the frozen design already resolves their fields, authority, visibility, validation boundaries, error model, and compatibility constraints. Splitting would create partial-contract risk and delay repository readiness without reducing architectural uncertainty enough to justify the inconsistency.

Final status:

```text
IMPLEMENTATION SCOPE CANDIDATE SELECTED
```
