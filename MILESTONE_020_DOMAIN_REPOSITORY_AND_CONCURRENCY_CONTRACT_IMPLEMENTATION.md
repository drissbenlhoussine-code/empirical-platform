# MILESTONE-020 - Domain Repository and Concurrency Contract Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-020 |
| Title | Domain Repository and Concurrency Contract Implementation |
| Version | 1.0 |
| Status | IMPLEMENTATION COMPLETE - PENDING INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Baseline | `fd96b70366a7bbed2172a8f51d7d7cc52b60bc41` |
| Frozen design authority | `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_DESIGN.md` (Version 1.6, OWNER APPROVED, DESIGN FROZEN) |
| Mission type | Implementation only |
| Schemas, migrations, mappers, SQL, PostgreSQL adapters, Unit of Work, runtime composition created | No |
| Aggregate source files (`aggregate.py`, lifecycle, reconstruction) modified | No |

## 2. Scope

This implementation provides the domain-facing repository contract layer frozen by MILESTONE-020 for exactly four aggregates:

- Campaign;
- Run;
- EvidencePackage;
- Review.

It implements aggregate-specific repository Protocols and their shared, persistence-neutral contract-support types (`LoadedAggregate`, `SaveOperation`, `SaveResult`, and the `RepositoryContractError` hierarchy). It does not implement repositories, persistence mappers, schemas, migrations, SQL, PostgreSQL adapters, Unit of Work, transaction managers, caches, event buses, APIs, workers, or any M021 work.

## 3. Files Changed

Created:

- `src/empirical_platform/shared/contracts/repository.py`;
- `src/empirical_platform/campaign/repository.py`;
- `src/empirical_platform/run/repository.py`;
- `src/empirical_platform/evidence/repository.py`;
- `src/empirical_platform/review/repository.py`;
- `tests/contract/_fakes.py`;
- `tests/contract/test_campaign_repository_contract.py`;
- `tests/contract/test_run_repository_contract.py`;
- `tests/contract/test_evidence_package_repository_contract.py`;
- `tests/contract/test_review_repository_contract.py`;
- `tests/contract/test_repository_contract_common.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/campaign/bad_repository_boto3_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/evidence/bad_repository_psycopg_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/run/bad_repository_campaign_aggregate_import.py`;
- `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_IMPLEMENTATION.md`.

Modified:

- `src/empirical_platform/shared/contracts/__init__.py` (export the new contract-support types);
- `src/empirical_platform/campaign/__init__.py` (export `CampaignRepository`);
- `src/empirical_platform/run/__init__.py` (export `RunRepository`);
- `src/empirical_platform/evidence/__init__.py` (export `EvidencePackageRepository`);
- `src/empirical_platform/review/__init__.py` (export `ReviewRepository`);
- `tests/architecture/test_module_boundaries.py` (assert the three new negative fixtures).

`tools/check_architecture.py` was not modified. No architecture-checker rule change was required or made.

## 4. Contract-Support Types

Implemented in:

```text
empirical_platform.shared.contracts.repository
```

and re-exported from `empirical_platform.shared.contracts`:

- `SaveOperation` — closed `StrEnum` with exactly `CREATED`, `UPDATED`, `UNCHANGED`;
- `LoadedAggregate[AggregateT]` — immutable, slots-based, generic load-result envelope with `aggregate` and `persisted_version`;
- `SaveResult` — immutable, slots-based, with `operation: SaveOperation` and `persisted_version: AggregateVersion`;
- `RepositoryContractError` — persistence-neutral base exception with `safe_message`, `aggregate_kind`, `identity`;
- `AggregateNotFound`, `AggregateAlreadyExists`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, `InvalidPersistedAggregateState` — the exact five contract errors frozen by the design's Section 23 error taxonomy.

### 4.1 Module Placement Justification

Per the design's Section 8.1 deferral, placement was selected against the live architecture checker rather than assumed:

- `shared` has an empty `ALLOWED` import set (`tools/check_architecture.py`), so contract-support types cannot import `DomainIdentity` from `identifiers` without reversing the frozen shared-to-identifiers dependency direction — the same defect MILESTONE-019 corrected for `shared.domain.reconstruction` (see that implementation's hostile-review issue 0002). Identity is therefore accepted as an opaque `object` on every error type, matching that precedent exactly.
- `AggregateVersion` is imported from `empirical_platform.shared.domain.versioning`; because both modules resolve to the same top-level `shared` package under the checker's `module_for_path`, this import is permitted regardless of the `ALLOWED` table (same-top-level-module imports are always allowed).
- `empirical_platform.shared.contracts` already existed as an empty package from MILESTONE-020's design corrections and required no new top-level package, no architecture-checker table changes, and introduces no import cycle.

### 4.2 Exception Naming

`AggregateNotFound`, `AggregateAlreadyExists`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, and `InvalidPersistedAggregateState` trigger ruff's `N818` ("exception name should end in Error") rule. These names are frozen exactly by the approved design and are not renamed; each is marked with a documented `# noqa: N818`, with the rationale recorded once at the top of `repository.py`. This is a narrow, explicit, reviewed exception to a style rule — not a weakening of any validation gate — and no other file, and no other rule, is affected.

## 5. Aggregate-Specific Repository Contracts

Implemented as `typing.Protocol` classes (no base class, no shared generic repository, per the design's explicit rejection of a generic abstraction):

| Repository | Module | Identity input | Aggregate |
| --- | --- | --- | --- |
| `CampaignRepository` | `empirical_platform.campaign.repository` | `DomainIdentity[CampaignId]` | `Campaign` |
| `RunRepository` | `empirical_platform.run.repository` | `DomainIdentity[RunId]` | `Run` |
| `EvidencePackageRepository` | `empirical_platform.evidence.repository` | `DomainIdentity[EvidencePackageId]` | `EvidencePackage` |
| `ReviewRepository` | `empirical_platform.review.repository` | `DomainIdentity[ReviewId]` | `Review` |

Each Protocol exposes exactly three operations, matching the design precisely:

- `get(identity) -> LoadedAggregate[AggregateT]`;
- `add(aggregate) -> SaveResult`;
- `save(aggregate, *, expected_persisted_version) -> SaveResult`.

Each is re-exported from its aggregate package's `__init__.py` (`CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository`), matching the existing public-export convention used for every other aggregate type.

No repository contract imports SQLAlchemy, psycopg, boto3, PostgreSQL adapters, object storage adapters, schemas, mappers, runtime composition, health, or reconstruction internals. No aggregate module imports any repository module.

## 6. Semantics Implemented

These are Protocol method signatures and docstrings only — no concrete repository logic ships in `src/`. The following semantics are documented on each Protocol method and independently verified against the fakes in `tests/contract/`:

- `get` raises `AggregateNotFound` for a missing identity and `InvalidPersistedAggregateState` for malformed durable state;
- `add` is creation-only and raises `AggregateAlreadyExists` on duplicate `DomainIdentity`, duplicate `governance_id`, or duplicate `runtime_id`;
- `save` is update-only: it raises `AggregateNotFound` when no persisted state exists for the aggregate's identity, and never creates, upserts, or silently inserts;
- `save` requires an explicit `expected_persisted_version`, atomically compared against durable state; a mismatch raises `OptimisticConcurrencyConflict` carrying `expected_persisted_version`, `aggregate_current_version`, and `actual_persisted_version`;
- an unchanged save (`aggregate.version == expected_persisted_version` and durable state matches) returns `SaveResult(operation=UNCHANGED, ...)`;
- `LoadedAggregate.persisted_version` is fixed at load time and does not change when the loaded aggregate is subsequently mutated — verified directly in every aggregate's contract test suite;
- `LoadedAggregate` and `SaveResult` are immutable (slots, property-only access, no setters — attribute assignment raises `AttributeError`);
- retry policy remains application-owned; no `Retryability` type or field exists anywhere in the contract surface;
- no governance-ID-only or runtime-ID-only lookup, no identity-resolution registry, and no repository factory were added.

## 7. Concurrency Semantics

Verified per-aggregate in the contract test suites:

- expected version is always taken from `LoadedAggregate.persisted_version` or a prior `SaveResult.persisted_version`, never from the aggregate's live current version after mutation;
- a stale expected version raises `OptimisticConcurrencyConflict` with all three version facts populated and distinct from each other;
- repeated saves require the latest `SaveResult.persisted_version` as the next expected version; reusing a stale value is rejected even after an intervening successful save.

## 8. Error Boundary

`RepositoryContractError` and its five subclasses carry only aggregate-kind text, an opaque identity reference, and version facts where relevant. No SQLAlchemy, psycopg, SQLSTATE, ORM session, transaction object, or backend-specific detail is constructed, imported, or referenced anywhere in the contract layer, matching the design's Section 23 boundary.

## 9. Architecture Enforcement

No architecture-checker rule was added, removed, or weakened. `tools/check_architecture.py` is unchanged. The existing `ALLOWED` and `FORBIDDEN_IMPORT_PREFIXES` tables already cover every new file correctly because `campaign/repository.py`, `run/repository.py`, `evidence/repository.py`, and `review/repository.py` are each classified by the checker under their existing top-level module ("campaign", "run", "evidence", "review"), and each new file's imports (`identifiers`, `shared`, and its own aggregate package) already fall within that module's existing `ALLOWED` set.

Three new negative fixtures were added to extend real, previously-unproven coverage:

- `campaign/bad_repository_boto3_import.py` — proves `campaign may not import boto3` (boto3 was listed in `FORBIDDEN_IMPORT_PREFIXES` but had no fixture before this milestone);
- `evidence/bad_repository_psycopg_import.py` — proves `evidence may not import psycopg` (same gap, for psycopg);
- `run/bad_repository_campaign_aggregate_import.py` — proves that `run`'s narrow `ALLOWED_EXACT_IMPORTS` allowlist (only `empirical_platform.campaign.lifecycle`) still blocks a repository-shaped file from importing `empirical_platform.campaign.aggregate` directly, guarding specifically against the cross-aggregate coupling a careless `RunRepository` implementation could introduce later.

`tests/architecture/test_module_boundaries.py` was extended with two new assertions for the first two (the third reuses the existing `"run may not import campaign"` assertion, since the checker reports at top-level-module granularity). `test_current_source_tree_respects_boundaries` (zero violations on `src/`) continues to pass unchanged.

## 10. Tests

61 new tests across 5 files in `tests/contract/`, using in-memory fakes (`tests/contract/_fakes.py`) rather than a database adapter, per the design's explicit instruction. `InMemoryRepositoryFake` is test-only scaffolding — not exported from `empirical_platform`, not the generic repository the design forbids as a product abstraction — parameterized once and wrapped in four thin, Protocol-conformant classes (`FakeCampaignRepository`, `FakeRunRepository`, `FakeEvidencePackageRepository`, `FakeReviewRepository`).

Per-aggregate coverage (13 tests each for Campaign, Run, Review; 13 for EvidencePackage with an added `start_collection` lifecycle step since artifact/criterion mutation requires the `COLLECTING` state):

- missing-identity load raises `AggregateNotFound`;
- successful `add` returns `SaveResult(CREATED, ...)`;
- duplicate full identity, duplicate `governance_id`, and duplicate `runtime_id` each raise `AggregateAlreadyExists`;
- `get` after `add` returns a `LoadedAggregate` matching the added aggregate and its initial version;
- the loaded `persisted_version` does not change when the live aggregate is mutated afterward;
- `LoadedAggregate` field assignment raises `AttributeError` (immutability);
- `save` on an identity with no persisted state raises `AggregateNotFound`;
- `save` after mutation with the correct expected version returns `SaveResult(UPDATED, ...)`;
- a stale expected version raises `OptimisticConcurrencyConflict` with expected, current, and actual versions all populated and distinct;
- an unchanged save returns `SaveResult(UNCHANGED, ...)`;
- repeated saves require the latest `SaveResult.persisted_version`.

Cross-cutting coverage (7 tests in `test_repository_contract_common.py`):

- `SaveOperation` has exactly three closed values;
- `empirical_platform.shared.contracts.__all__` matches the nine frozen contract-support names exactly;
- each aggregate package exports its repository Protocol;
- no `Retryability` concept and no `AggregateKind` enum exists anywhere in the contract surface;
- no aggregate package exports a generic `Repository` base;
- all four fakes are assignable to their respective Protocol-typed variables (structural conformance, verified by mypy when this file is type-checked).

## 11. mypy Scope Note

The project's `[tool.mypy]` configuration (`packages = ["empirical_platform"]`) type-checks `src/empirical_platform` only; it did not check `tests/` before this milestone and is not changed to do so by this milestone. All new Protocol implementations under `src/` are fully annotated and pass `mypy --strict` (68 source files, 0 issues). The Protocol-conformance assignments in `tests/contract/test_repository_contract_common.py` document structural correctness for a reader and would be verified by mypy if a future milestone extends its scope to `tests/`; that scope change is not made here.

## 12. Validation Evidence

Full commands, raw output, and exit codes are in `external-review/M020_REPOSITORY_CONTRACT_IMPLEMENTATION/evidence/`. Summary:

- Python: `3.13.14` (`.venv`, matching `requires-python = ">=3.13,<3.14"`);
- `ruff format --check .`: PASS;
- `ruff check .`: PASS;
- `mypy`: PASS, 0 issues, 68 source files;
- `tools/check_architecture.py .`: PASS, 0 violations;
- `tools/check_architecture.py tests/fixtures/illegal_imports`: PASS, violations correctly detected including the 3 new fixtures;
- `pytest` (full suite, isolated `--basetemp` per the known machine-local locked temp path documented in the frozen design Section 33.5): PASS;
- `pip_audit`: PASS;
- `detect-secrets`: PASS, 0 findings;
- `python -m build`: PASS;
- `git diff --check`: PASS.

The machine-local locked `%LOCALAPPDATA%\Temp\pytest-of-LuxSy\pytest-current` condition documented in the frozen design remains unresolved on this machine; it is unrelated to this implementation and is worked around identically (isolated `--basetemp`), not fixed, per that design's own scope boundary.

## 13. Hostile Self-Review

| ID | Severity | Finding | Correction | Disposition |
| --- | --- | --- | --- | --- |
| M020-IMPL-ISSUE-0001 | MINOR | `LoadedAggregate` and `SaveResult` were initially written as manual `__slots__` classes with property accessors, inconsistent with every other value object in this codebase (`DomainIdentity`, `AggregateVersion`, `ArtifactReference`, `CampaignScopeStatement`), which all use `@dataclass(frozen=True, slots=True)`. | Refactored both to `@dataclass(frozen=True, slots=True)` with `__post_init__` validation, matching `DomainIdentity`'s exact pattern. Gains correct structural `__eq__`/`__repr__` for free. Re-verified: ruff, mypy, and all 61 contract tests still pass unchanged (frozen-dataclass attribute assignment raises `dataclasses.FrozenInstanceError`, a subclass of `AttributeError`, so the immutability tests still pass without modification). | Resolved |
| M020-IMPL-ISSUE-0002 | MINOR | `AggregateNotFound`, `AggregateAlreadyExists`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, and `InvalidPersistedAggregateState` trigger ruff's `N818` exception-naming rule, but these names are frozen exactly by the approved design. | Added a documented `# noqa: N818` on each class, with a single rationale comment at the top of the module rather than five repeated ones. This is a narrow, explicit exception to a style rule for five specific, reviewed names — not a global or category-wide suppression, and no other rule is affected. | Resolved |
| M020-IMPL-ISSUE-0003 | MINOR | `tests/contract/_fakes.py` uses a `Protocol`-bounded generic (`_IdentifiedVersionedAggregate`) to type the shared in-memory fake engine, but the project's mypy configuration (`packages = ["empirical_platform"]`) does not type-check `tests/`, so this structural typing is currently unverified by the type checker. | Not changed: expanding mypy's scope to `tests/` is a repository-wide tooling decision outside MILESTONE-020's contract-design-only mandate. Documented explicitly in Section 11 rather than silently left implicit, so a reviewer knows the Protocol-conformance assertions are currently structural documentation, not a currently-enforced gate. | Acknowledged, not corrected (out of scope) |
| M020-IMPL-ISSUE-0004 | INFORMATIONAL | Considered whether a dedicated runtime test was needed to prove repository operations require a *complete* `DomainIdentity` (both `governance_id` and `runtime_id`), per Phase 3's "complete DomainIdentity requirement" coverage item. | `DomainIdentity.__post_init__` (frozen since MILESTONE-012/013) already enforces both fields are required and type-correct; every contract test constructs identities through it. A redundant test in this milestone would duplicate existing MILESTONE-012/013 coverage rather than test new M020 behavior. No new test added; reasoning recorded here instead of silently omitted. | Acknowledged, no action needed |

No MAJOR or CRITICAL finding was identified. Full validation (Section 12) was re-run after the two corrective changes (Issues 0001 and 0002) and remained green.

## 14. Explicit Non-Goals Confirmed

Not implemented:

- repository implementations or persistence mappers;
- serialization format;
- PostgreSQL schema or migrations;
- SQL or ORM mapping;
- Unit of Work integration;
- row locking or retry-policy implementation;
- application services or runtime composition;
- APIs, workers, read models, or projections;
- Audit runtime, Decision Candidate, Decision Freeze;
- any MILESTONE-021 work.

`migrations/versions` remains empty. No frozen aggregate, lifecycle, or reconstruction source file was modified.

## 15. Final Status

```text
IMPLEMENTATION COMPLETE - PENDING INDEPENDENT REVIEW
```

MILESTONE-020 is NOT marked APPROVED beyond the frozen design, and this implementation is NOT FROZEN. MILESTONE-021 has NOT started.
