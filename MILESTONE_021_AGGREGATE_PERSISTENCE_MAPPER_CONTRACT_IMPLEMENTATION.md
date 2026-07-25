# MILESTONE-021 - Aggregate Persistence Mapper Contract Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-021 |
| Title | Aggregate Persistence Mapper Contract Implementation |
| Version | 1.0 |
| Status | IMPLEMENTATION COMPLETE - PENDING INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Baseline | `abeba5a1407a8d31ce6d07fe3e071804d2385457` |
| Frozen design authority | `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_DESIGN.md` (Version 1.0, OWNER APPROVED, DESIGN FROZEN) |
| Mission type | Implementation only |
| Schemas, migrations, SQL, concrete repository implementations, Unit of Work, runtime composition created | No |
| Aggregate source files (`aggregate.py`, lifecycle, reconstruction) modified | No |

## 2. Scope

This implementation provides the persistence-neutral mapper contract layer frozen by MILESTONE-021 for exactly four aggregates: Campaign, Run, EvidencePackage, Review. It implements aggregate-specific mapper Protocols, their durable-record types, and a mapper-local error type. It does not implement a concrete mapper against any storage technology, a repository, a schema, a migration, or any MILESTONE-022 work.

## 3. Files Changed

Created:

- `src/empirical_platform/shared/contracts/mapping.py` (`MapperError`, `MapperErrorCategory`, `IdentityDurableRecord`, `TransitionDurableRecord`);
- `src/empirical_platform/campaign/mapper.py` (`CampaignMapper`, `CampaignDurableRecord`);
- `src/empirical_platform/run/mapper.py` (`RunMapper`, `RunDurableRecord`, `DatasetManifestDurableRecord`);
- `src/empirical_platform/evidence/mapper.py` (`EvidencePackageMapper`, `EvidencePackageDurableRecord`, `CriterionResultDurableRecord`);
- `src/empirical_platform/review/mapper.py` (`ReviewMapper`, `ReviewDurableRecord`, `ReviewFindingDurableRecord`);
- `tests/contract/_mapper_fakes.py` (test-only concrete fakes; not shipped, not exported);
- `tests/contract/test_campaign_mapper_contract.py`;
- `tests/contract/test_run_mapper_contract.py`;
- `tests/contract/test_evidence_package_mapper_contract.py`;
- `tests/contract/test_review_mapper_contract.py`;
- `tests/contract/test_mapper_contract_common.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/campaign/bad_mapper_sqlalchemy_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/run/bad_mapper_persistence_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/evidence/bad_mapper_boto3_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/review/bad_mapper_psycopg_import.py`;
- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_IMPLEMENTATION_SCOPE_SELECTION.md`;
- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_IMPLEMENTATION.md`.

Modified:

- `src/empirical_platform/shared/contracts/__init__.py` (export the new mapping-support types);
- `src/empirical_platform/campaign/__init__.py`, `run/__init__.py`, `evidence/__init__.py`, `review/__init__.py` (export each Mapper Protocol and its durable-record type(s));
- `tests/architecture/test_module_boundaries.py` (assert the four new negative fixtures);
- `tests/contract/test_repository_contract_common.py` (widened `test_shared_contracts_public_exports` from exact-equality to a subset check, since `shared.contracts.__all__` now also carries M021's mapping-support names — a legitimate, minimal correction, not a weakening: the M020 names it asserts are unchanged).

`tools/check_architecture.py` was not modified. No architecture-checker rule change was required or made.

## 4. Mapper-Local Error Type

Implemented in `empirical_platform.shared.contracts.mapping`, resolved narrowly per the Design Freeze's accepted observation (rather than left further deferred):

- `MapperErrorCategory` — closed `StrEnum`: `INVALID_DURABLE_RECORD`, `INVALID_AGGREGATE_FOR_MAPPING`;
- `MapperError` — plain `Exception` subclass with `category`, `safe_message`, `aggregate_kind`, `field`.

This mirrors `ReconstructionError`/`ReconstructionErrorCategory` (M019 precedent) exactly rather than `RepositoryContractError`'s shape, and is verified NOT a subclass of `RepositoryContractError` (`tests/contract/test_mapper_contract_common.py::test_mapper_errors_are_distinct_from_repository_errors`), preserving the frozen Design's requirement that the mapper stay independent of repository-contract vocabulary (Design Section 13). No broad error framework was introduced — two categories, one exception class.

## 5. Shared Mapping-Support Types

`IdentityDurableRecord` (`governance_id: str`, `runtime_id: str`) and `TransitionDurableRecord` (mirrors `StateTransitionRecord`'s fields exactly, with `identity_reference: IdentityDurableRecord | None`) are shared across all four aggregates' durable records, placed in `shared.contracts.mapping` alongside the mapper error type. This is justified, not a "generic mapper base": it reuses the same genericity `StateTransitionRecord[IdentityReferenceT]` already has in `shared.domain.transitions`, applied to its persistence-neutral durable counterpart. Verified via `test_no_generic_mapper_base_is_exposed` that no aggregate package exports a generic `Mapper` name.

## 6. Aggregate-Specific Mapper Contracts and Durable Records

| Mapper | Module | Durable record | Nested durable record(s) |
| --- | --- | --- | --- |
| `CampaignMapper` | `empirical_platform.campaign.mapper` | `CampaignDurableRecord` | — |
| `RunMapper` | `empirical_platform.run.mapper` | `RunDurableRecord` | `DatasetManifestDurableRecord` |
| `EvidencePackageMapper` | `empirical_platform.evidence.mapper` | `EvidencePackageDurableRecord` | `CriterionResultDurableRecord` (artifact references represented as a plain `tuple[str, ...]` — a nested record was judged unnecessary for a single-field value object, per the Design's "nested records only where necessary" instruction) |
| `ReviewMapper` | `empirical_platform.review.mapper` | `ReviewDurableRecord` | `ReviewFindingDurableRecord` |

Each Protocol exposes exactly the two operations the Design specifies:

- `to_durable_record(aggregate) -> <Aggregate>DurableRecord`;
- `from_durable_record(record) -> <Aggregate>ReconstructionState`.

No mapper calls its aggregate's internal `_reconstruct_*` factory; `from_durable_record` stops at producing a `*ReconstructionState`, preserving the frozen call chain `repository implementation -> mapper -> ReconstructionState -> _reconstruct_* -> aggregate` (Design Section 11.2, M020 Design Section 24).

### 6.1 Exact Field Preservation

Verified field-by-field against the live `*ReconstructionState` types (`src/empirical_platform/{campaign,run,evidence,review}/_reconstruction.py`) before writing any durable-record type:

- Campaign: `DomainIdentity[CampaignId]`, `CampaignScopeStatement`, lifecycle state, `AggregateVersion`, `TransitionSequence`, transition history;
- Run: `DomainIdentity[RunId]`, `CampaignId` context, lifecycle state, ordered `DatasetManifest` values, `AggregateVersion`, `TransitionSequence`, transition history;
- EvidencePackage: `DomainIdentity[EvidencePackageId]`, `RunId` context, lifecycle state, ordered `CriterionResult` values, ordered `ArtifactReference` values, `AggregateVersion`, `TransitionSequence`, transition history;
- Review: `DomainIdentity[ReviewId]`, target/reviewer references, lifecycle state, ordered `ReviewFinding` values, `ReviewDisposition | None`, `final_disposition_rationale`/`cancellation_reason`, `AggregateVersion`, `TransitionSequence`, transition history.

No field present in any live `*ReconstructionState` or its owned value objects was omitted; no field not present in any of them was invented.

## 7. Module Placement

Exactly as the Design specified (Section 8): `<aggregate>.mapper`, mirroring `<aggregate>.repository` from MILESTONE-020. No architecture-checker change was required: `tools/check_architecture.py`'s `module_for_path` classifies `campaign/mapper.py` under the existing "campaign" top-level module (identical mechanism already verified for `campaign/repository.py` in M020), and each mapper module's imports (its own aggregate's `_reconstruction` module, `identifiers`, `shared`) already fall within that module's existing `ALLOWED` set.

## 8. Architecture Enforcement

No `tools/check_architecture.py` rule was added, removed, or weakened. Four new negative fixtures extend real, previously-unproven coverage of mapper-shaped files specifically:

- `campaign/bad_mapper_sqlalchemy_import.py` — proves `campaign may not import sqlalchemy` (previously only proven for a repository-shaped file, and only via a review-shaped file for sqlalchemy specifically; not yet from campaign);
- `run/bad_mapper_persistence_import.py` — proves `run may not import empirical_platform.shared.persistence` (not previously proven for `run` at all);
- `evidence/bad_mapper_boto3_import.py` — proves `evidence may not import boto3` (not previously proven for `evidence` at all);
- `review/bad_mapper_psycopg_import.py` — proves `review may not import psycopg` (previously only proven via a review-shaped `bad_sqlalchemy_import.py`, not psycopg).

`tests/architecture/test_module_boundaries.py` was extended with four new assertions. `test_current_source_tree_respects_boundaries` (zero violations on `src/`) continues to pass unchanged.

### 8.1 Known, Disclosed Enforcement Limitation

The Design's placement rule "aggregate modules must not import mapper modules" (Section 8) is not, and cannot currently be, mechanically enforced by `tools/check_architecture.py`: the checker only detects cross-*top-level-module* imports, and `campaign/aggregate.py` importing `campaign/mapper.py` would be a same-module (`campaign` importing `campaign`) reference, which the checker's existing logic always permits regardless of the `ALLOWED` table. This is an identical, pre-existing limitation to M020's analogous "aggregate modules must not import repository modules" rule, not something newly introduced or newly discovered as a defect by this milestone. No aggregate module in fact imports its mapper module (verified: `campaign/aggregate.py`, `run/aggregate.py`, `evidence/package.py`, `review/aggregate.py` are unmodified since M018), so the rule holds in practice; it is disclosed here as a documentation-enforced, not tool-enforced, convention.

## 9. Tests

25 new tests across 5 files in `tests/contract/`, using concrete in-memory fakes (`tests/contract/_mapper_fakes.py`) rather than a database adapter, per the Design's explicit instruction. The fakes are test-only scaffolding — not exported from `empirical_platform`, not the mapper *implementation* the Design defers to a future milestone.

Per-aggregate coverage:

- round-trip structural fidelity: `aggregate -> to_durable_record -> from_durable_record -> _reconstruct_*` yields an aggregate with identical identity, version, lifecycle state, and history to the original;
- non-trivial transition history (multiple transitions, non-zero version/sequence) round-trips correctly, including `identity_reference` on each transition record;
- ordered collections (Run manifests, EvidencePackage criterion results/artifact references, Review findings) preserve order and per-element optional fields (e.g. a manifest with no `manifest_id`, a criterion result with no `summary`, a finding with no `rationale`);
- durable records (and nested transition durable records) are immutable — attribute assignment raises `dataclasses.FrozenInstanceError`;
- a durable record with a malformed `lifecycle_state` string raises `MapperError` with category `INVALID_DURABLE_RECORD` and the correct `aggregate_kind`;
- Review additionally: a malformed `disposition` string raises `MapperError` with `field="disposition"`; cancellation and completion metadata both round-trip correctly.

Cross-cutting coverage (`test_mapper_contract_common.py`):

- `shared.contracts` exports all four new mapping-support names;
- each aggregate package exports its Mapper Protocol and durable-record type(s);
- no aggregate package exports a generic `Mapper` base;
- no aggregate package exports anything resembling a reconstruction factory;
- `MapperError` is confirmed **not** a subclass of `RepositoryContractError`;
- all four fakes are assignable to their respective Protocol-typed variables (structural conformance, verified by mypy if a future milestone extends its scope to `tests/` — see Section 10).

## 10. mypy Scope Note (carried forward from M020, unchanged)

The project's `[tool.mypy]` configuration (`packages = ["empirical_platform"]`) type-checks `src/empirical_platform` only. All new Protocol and durable-record types under `src/` are fully annotated and pass `mypy --strict` (73 source files, 0 issues). The Protocol-conformance assignments in `tests/contract/test_mapper_contract_common.py` document structural correctness for a reader; this milestone does not change mypy's scope, consistent with M020's identical, disclosed limitation.

## 11. Validation Evidence

Full commands, raw output, and exit codes are in `external-review/M021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_IMPLEMENTATION/evidence/`. Summary:

- Python: `3.13.14` (`.venv`, matching `requires-python = ">=3.13,<3.14"`);
- `ruff format --check .` / `ruff check .`: PASS;
- `mypy`: PASS, 0 issues, 73 source files;
- `tools/check_architecture.py .`: PASS, 0 violations;
- `tools/check_architecture.py tests/fixtures/illegal_imports`: PASS, all violations (including the 4 new mapper fixtures) correctly detected;
- `security.ps1` / `verify.ps1`: PASS (exit 0 end-to-end, using the M020-corrected isolated `--basetemp` pattern already in `scripts/verify.ps1`);
- `pytest` (full suite): PASS;
- `python -m build`: PASS;
- `git diff --check`: PASS.

## 12. Hostile Self-Review

See the implementation's hostile-review pass, recorded in full in this session's report rather than duplicated here; no MAJOR or CRITICAL finding required a source change beyond what Sections 4-9 above already reflect (the mapper-local error naming and shared-support placement decisions were made once, correctly, during implementation rather than corrected afterward).

## 13. Explicit Non-Goals Confirmed

Not implemented:

- a concrete mapper implementation against any storage technology;
- repository implementations;
- PostgreSQL schema or migrations (`migrations/versions` remains empty);
- SQL or ORM mapping;
- Unit of Work beyond the existing single-statement infrastructure primitive;
- application services, runtime composition, APIs, or workers;
- Audit runtime, Decision Candidate, Decision Freeze;
- any MILESTONE-022 work.

No frozen M019 (aggregate/lifecycle/reconstruction) or M020 (repository contract) source file was modified.

## 14. Final Status

```text
IMPLEMENTATION COMPLETE - PENDING INDEPENDENT REVIEW
```

MILESTONE-021 is NOT marked APPROVED beyond the frozen design, and this implementation is NOT FROZEN. MILESTONE-022 has NOT started.
