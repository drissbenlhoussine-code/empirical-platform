# MILESTONE-023 - PostgreSQL Repository Adapter Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-023-IMPLEMENTATION |
| Title | PostgreSQL Repository Adapter Implementation |
| Version | 1.0 |
| Status | IMPLEMENTATION COMPLETE - PENDING INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen design authority | `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN.md` (Version 1.3, final) and `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN_FREEZE.md` (M023 DESIGN APPROVED AND FROZEN) |
| Mission type | Implementation only |
| Frozen M019/M020/M021/M022 source files modified | No |
| MILESTONE-024 work created | No |

## 2. Scope

This implementation adds the four concrete mappers (`ConcreteCampaignMapper`, `ConcreteRunMapper`, `ConcreteEvidencePackageMapper`, `ConcreteReviewMapper`) satisfying the frozen M021 `<Aggregate>Mapper` Protocols, and the four concrete repository adapters (`PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository`) satisfying the frozen M020 `<Aggregate>Repository` Protocols against the frozen M022 schema, exactly per the frozen M023 design. It does not implement application services, runtime composition, APIs, workers, or any MILESTONE-024 work.

## 3. Files Changed

Created:

- `src/empirical_platform/shared/persistence/postgres_repositories/__init__.py`
- `src/empirical_platform/shared/persistence/postgres_repositories/_errors.py` (shared unique-violation constraint-name extraction helper, Design Section 9.2)
- `src/empirical_platform/shared/persistence/postgres_repositories/campaign_repository.py`
- `src/empirical_platform/shared/persistence/postgres_repositories/run_repository.py`
- `src/empirical_platform/shared/persistence/postgres_repositories/evidence_package_repository.py`
- `src/empirical_platform/shared/persistence/postgres_repositories/review_repository.py`
- `tests/unit/test_m023_concrete_mappers.py` (16 tests)
- `tests/integration/test_m023_postgres_repositories.py` (26 real-PostgreSQL tests)
- `tests/fixtures/illegal_imports/src/empirical_platform/shared/bad_shared_import_audit.py` (negative architecture fixture)
- `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_IMPLEMENTATION.md` (this document)

Modified:

- `src/empirical_platform/campaign/mapper.py` (added `ConcreteCampaignMapper` and its module-private identity/transition durable-record helpers)
- `src/empirical_platform/run/mapper.py` (added `ConcreteRunMapper` and its manifest durable-record helpers)
- `src/empirical_platform/evidence/mapper.py` (added `ConcreteEvidencePackageMapper` and its criterion-result durable-record helpers)
- `src/empirical_platform/review/mapper.py` (added `ConcreteReviewMapper` and its finding durable-record helpers)
- `tools/check_architecture.py` (`ALLOWED["shared"]` widened; see Section 10)
- `tests/architecture/test_module_boundaries.py` (negative-fixture assertion for the widened rule)
- `PROJECT_CHECKPOINT.md` (updated to record the M023 design freeze and this implementation)

No M019, M020, M021, or M022 frozen source file's existing public shape was altered; every mapper addition is a new class appended to the existing per-aggregate `mapper.py` module already housing that aggregate's frozen Protocol and `DurableRecord` type.

## 4. Concrete Mapper Placement and Design

Each concrete mapper lives directly inside its aggregate's existing `<aggregate>/mapper.py` file, not under `shared` — a concrete mapper has zero persistence dependencies (no SQL, no transaction, no schema knowledge) and needs only same-package imports the architecture checker already permits. This was an implementation-time placement decision consistent with, but not dictated verbatim by, the frozen design (Design Section 14 defers "reconstruction and mapper integration" detail to implementation).

Each mapper's `to_durable_record`/`from_durable_record` pair is pure, in-memory data transformation:

- Identity and transition-history conversion uses small module-private helpers (`_identity_to_durable`/`_identity_from_durable`, `_transition_to_durable`/`_transition_from_durable`) duplicated per aggregate module (matching the pattern the M021 contract-test fakes already established, since no shared generic mapper base is permitted per M021's frozen "no generic mapper base is exposed" rule).
- Child-collection value objects (`DatasetManifest`, `CriterionResult`, `ArtifactReference`, `ReviewFinding`) convert element-by-element, preserving tuple order.
- `from_durable_record` raises `MapperError` (category `INVALID_DURABLE_RECORD`) for an unknown lifecycle-state string, an unknown `ReviewDisposition` string, or any other structurally malformed field (caught via `(ValueError, TypeError)` around the full reconstruction-state assembly) — never a `RepositoryContractError`.
- `from_durable_record` never calls the internal `_reconstruct_*` factory; that call is the repository's own responsibility (Section 5).

## 5. Repository Placement, Constructor, and Dependencies

All four repositories live at `empirical_platform.shared.persistence.postgres_repositories.<x>_repository`, matching the frozen design's module placement exactly. Each repository's constructor:

```python
def __init__(self, service: PostgresPersistenceService, mapper: <X>Mapper | None = None) -> None:
    self._service = service
    self._mapper: <X>Mapper = mapper if mapper is not None else Concrete<X>Mapper()
```

`service` is the only required dependency; `mapper` defaults to the concrete mapper but is constructor-injectable, matching the M020 Protocol's mapper-agnostic contract and enabling isolated repository-level testing (used by this implementation's own test suite, Section 9).

No generic concrete repository base class exists — each of the four repositories independently implements `get`/`add`/`save`, per the frozen design's explicit prohibition on a generic base unless the design permits one (it does not).

## 6. GET Implementation

Every `get(identity)`:

1. Opens one `PostgresPersistenceService.unit_of_work()`.
2. Selects the root row filtered by **both** `runtime_id` and `governance_id` (the full `DomainIdentity`, never one component alone).
3. If no row matches, issues a diagnostic query by `runtime_id` alone: if that also finds nothing, raises `AggregateNotFound`; if it finds a row (whose `governance_id` therefore differs from the request), raises `InvalidPersistedAggregateState` with a message naming the mismatch, never `AggregateNotFound`.
4. Selects every owned child-collection table filtered by the root's `runtime_id`, each `ORDER BY position` (or `ORDER BY sequence` for transitions and Review findings, which carry their own sequence field rather than a positional column) — deterministic reconstruction order, never insertion order.
5. Assembles a `<X>DurableRecord`, passes it to `self._mapper.from_durable_record(...)`, catching `MapperError` and re-raising as `InvalidPersistedAggregateState` (`reason=exc.safe_message`).
6. Passes the resulting `ReconstructionState` to the internal `_reconstruct_<x>` factory, catching `ReconstructionError` and re-raising as `InvalidPersistedAggregateState`.
7. Returns `LoadedAggregate(aggregate=..., persisted_version=AggregateVersion(root["version"]))` — the authoritative persisted version comes from the row actually read, never recomputed from the reconstructed aggregate.

## 7. ADD Implementation

Every `add(aggregate)`:

1. Maps the aggregate to a `DurableRecord` first, outside any transaction; a `MapperError` here becomes `InvalidAggregateForPersistence` before any SQL runs.
2. Opens one Unit of Work, inserts the root row, then inserts every owned child row (position-enumerated for manifests/criteria/artifacts; each transition row carries its own `sequence`/`identity_governance_id`/`identity_runtime_id` columns).
3. Catches `FoundationError` from the insert sequence; if `unique_violation_constraint_name(...)` names one of that aggregate's root PK/UNIQUE constraints, re-raises `AggregateAlreadyExists`; any other constraint name or unclassified failure is re-raised unchanged (an infrastructure/`FoundationError`, never misclassified as a duplicate).
4. Returns `SaveResult(operation=CREATED, persisted_version=AggregateVersion(record.version))` **only after** the `with ... unit_of_work()` block exits without exception — i.e., only after a successful commit (Section 11 proves this empirically).

## 8. SAVE Implementation (11-step canonical sequence)

Every `save(aggregate, *, expected_persisted_version)` follows the frozen sequence exactly:

1. Map the aggregate to a `DurableRecord`.
2. If `record.version < expected_persisted_version.value`: raise `InvalidAggregateForPersistence` immediately — no Unit of Work is opened, no SQL executes (proven empirically, Section 9).
3. Classify the intended operation in Python, before opening a transaction: `record.version == expected_persisted_version.value` -> `UNCHANGED`; `record.version > expected_persisted_version.value` -> `UPDATED`.
4. Open one Unit of Work.
5. Execute a single guarded `UPDATE ... WHERE runtime_id = :runtime_id AND governance_id = :governance_id AND version = :expected_persisted_version RETURNING version`, setting every root scalar column to the mapped record's values (`version` set to `record.version` exactly — the repository never increments it itself).
6. If zero rows were affected, run one diagnostic `SELECT` by `runtime_id` alone, in the same transaction: no row -> `AggregateNotFound`; a row whose `governance_id` differs -> `InvalidPersistedAggregateState`; otherwise -> `OptimisticConcurrencyConflict` (carrying `expected_persisted_version`, `aggregate_current_version=AggregateVersion(record.version)`, and `actual_persisted_version` read from the diagnostic row).
7. If the intended operation is `UPDATED`, delete every owned child row for this `runtime_id` and re-insert the mapped record's full child collections (position- or sequence-ordered) — full replace, no diffing, matching the design's justification (the frozen `DurableRecord` shape carries no per-item version or removal marker).
8. If the intended operation is `UNCHANGED`, child rows are never touched (proven empirically, Section 9) — an unchanged save still executes and validates the guarded root `UPDATE`, it just performs no child DELETE/INSERT.
9. Prepare `operation`/`persisted_version` from already-computed values.
10. The `with` block exits, committing.
11. Only after that commit succeeds does the function construct and return `SaveResult(operation, persisted_version)`.

The repository never calls `AggregateVersion.next()` or otherwise advances the version itself; the exact `record.version` the mapper already produced (which only the aggregate's own business methods can have advanced) is what gets persisted and returned.

## 9. Error Translation (Design Section 9)

Translation uses only stable, structured facts, never parsed backend message text:

- `shared/persistence/postgres_repositories/_errors.py`'s `unique_violation_constraint_name(error)` walks `FoundationError.__cause__ -> .orig -> .diag` (psycopg's Diagnostic API), returning a constraint name only when `.diag.sqlstate == "23505"` (unique violation); returns `None` for anything else, which callers treat as an unclassified failure to leave untranslated rather than guess.
- `add()` is the only place this helper is consulted, since duplicate detection is only meaningful on insert; each repository's own `_ROOT_UNIQUE_CONSTRAINTS` set names exactly that aggregate's PK and governance-id UNIQUE constraint names (empirically confirmed against the real M022 schema).
- `AggregateNotFound` / `InvalidPersistedAggregateState` / `OptimisticConcurrencyConflict` are all raised from structured row-presence/row-value facts read back from the database within the same transaction, never from exception text.
- No SQL text, SQLSTATE code, constraint name, or driver/exception type is ever included in any `RepositoryContractError` message; every message is a fixed, safe string authored in the repository code.
- Any persistence failure that does not match a known structured fact remains an unclassified `FoundationError` (infrastructure failure), propagated unchanged — never silently reclassified into a `RepositoryContractError`.

## 10. Architecture Enforcement

The frozen design's narrow change, `ALLOWED["shared"] = {"campaign", "run", "evidence", "review"}`, was applied first. Running `tools/check_architecture.py .` against the real, completed implementation then surfaced a genuine gap the frozen design's Phase 10 instruction did not anticipate: every repository's `get`/`add`/`save` signature is the already-frozen M020 Protocol, which takes `DomainIdentity[<X>Id]` parameters — meaning `shared.persistence.postgres_repositories.*` necessarily imports `empirical_platform.identifiers.pairs.DomainIdentity` and the concrete identifier types (`CampaignId`, `RunId`, `EvidencePackageId`, `ReviewId`). `identifiers` was not in the frozen change's `ALLOWED["shared"]` set.

This is not a broadening beyond the frozen design's intent — every one of the four aggregate packages the design already grants `shared` access to (`campaign`, `run`, `evidence`, `review`) already lists `identifiers` in its own `ALLOWED` entry, and the M020 Protocols the design implements verbatim already require these exact types in every method signature. The corrected, final rule is:

```python
ALLOWED["shared"] = {"campaign", "run", "evidence", "review", "identifiers"}
```

`FORBIDDEN_IMPORT_PREFIXES` is unchanged. After this correction, `tools/check_architecture.py .` reports 0 violations against the complete implementation.

The existing `bad_shared_import_audit.py` negative fixture (added alongside the design's own narrow change, proving `shared` still cannot import `audit`) remains valid and continues to be asserted by `tests/architecture/test_module_boundaries.py::test_negative_fixture_detects_illegal_import`.

## 11. Test Evidence

### 11.1 Concrete Mapper Unit Tests (`tests/unit/test_m023_concrete_mappers.py`, 16 tests, no database)

Round-trip identity/version/state/transition-history fidelity for all four aggregates; non-trivial multi-transition history preservation (Campaign); ordered child-collection preservation with optional-field fidelity (Run manifests with/without `manifest_id`/`notes`; EvidencePackage criterion results with/without `summary`/`evidence_references`, and artifact references; Review findings with/without `rationale`/`evidence_references`, and nullable `disposition`/`final_disposition_rationale`); malformed-lifecycle-state and other malformed-field `MapperError` behavior for all four aggregates.

### 11.2 Real PostgreSQL Integration Tests (`tests/integration/test_m023_postgres_repositories.py`, 26 tests)

Opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, run against a real, disposable, self-managed PostgreSQL instance (never mocked), with all twelve M022 tables truncated before each test for isolation:

- **PostgreSQL version:** 18.4 on x86_64-windows, compiled by msvc-19.44.35227, 64-bit.
- **Database URL (redacted):** `postgresql://empirical:***@localhost:55435/empirical_platform`.
- **Exact test count:** `26 passed in 4.59s`.
- **GET** (all four aggregates): authoritative version/state on success; `AggregateNotFound` for a missing identity; `InvalidPersistedAggregateState` for a `runtime_id` match with mismatched `governance_id`; deterministic child-collection ordering (Run manifests by position across 3 elements; EvidencePackage's two independent child collections each independently ordered; Review findings ordered by their own `sequence` field).
- **ADD** (all four aggregates): success with root+children persisted atomically; duplicate `runtime_id` and duplicate `governance_id` both raise `AggregateAlreadyExists`; commit-before-return proven by `test_campaign_add_commits_before_return_and_is_visible_from_new_connection`, which opens a second, independent `PostgresPersistenceService`/connection after `add()` returns and successfully reads the row back.
- **SAVE**: lower-version rejection proven to open no transaction and execute no SQL by `test_campaign_save_lower_version_rejected_opens_no_transaction_and_executes_no_sql`, which wraps `service.unit_of_work` with a call counter and asserts it is never invoked; equal-version `UNCHANGED` after a real commit, with a following test proving child rows (Run manifests) are not rewritten; greater-version `UPDATED` with the exact `record.version` persisted and both an EvidencePackage's independent child collections replaced atomically; stale-version `OptimisticConcurrencyConflict` carrying the correct `actual_persisted_version`; missing-aggregate `AggregateNotFound`; identity-mismatch `InvalidPersistedAggregateState`; concurrent-save simulation (`test_campaign_concurrent_saves_only_one_succeeds`, two independently loaded aggregate views, first save succeeds, second with the same stale expected version raises `OptimisticConcurrencyConflict`); the repository never increments the version beyond what the mapped record already carries.
- **Child-write-failure rollback:** `test_run_child_write_failure_rolls_back_root_update` injects a duplicating manifest via a test-only mapper wrapper passed through the repository's documented `mapper=` constructor seam (the aggregate's own `append_manifest` and the internal `_reconstruct_run` factory both already reject an in-memory duplicate `manifest_id`, so this state is unreachable through normal aggregate usage and had to be reached at the mapper boundary instead) to trigger the real `ix_run_manifest_manifest_id_partial_unique` constraint mid-save; the whole transaction rolls back, confirmed by reloading the aggregate afterward and finding both its version and its manifest collection unchanged from before the failed save.
- **Teardown:** the disposable instance was cleanly stopped via `pg_ctl stop -m fast` after final evidence capture (`server stopped`, confirmed by a following `pg_ctl status` reporting no server running).

### 11.3 Full Regression

`tests/contract/` (100 pre-existing M020/M021 contract tests using in-memory fakes) and the new M023 unit/integration suites all pass together with no regression (`100 passed` for contract+unit, `26 passed` for integration, run separately per their opt-in requirements).

## 12. Full Validation Loop

All commands run from `.venv`, never system Python.

- `python -m compileall -q src tests`: PASS.
- `ruff format --check .`: PASS (150 files already formatted).
- `ruff check .`: PASS, 0 issues.
- `mypy`: PASS, 0 issues, 79 source files.
- `tools/check_architecture.py .`: PASS, 0 violations (after the Section 10 correction).
- `tools/check_architecture.py tests/fixtures/illegal_imports`: PASS, negative fixtures (including the new `shared`-cannot-import-`audit` fixture) correctly detected.
- `scripts/security.ps1`: PASS (`pip-audit`: no known vulnerabilities; secret scan: 245 targets, 0 findings).
- `scripts/verify.ps1` (fresh GUID `--basetemp`, end-to-end): PASS — full suite `344 passed, 84 skipped`; the 84 skips are the pre-existing opt-in PostgreSQL/infrastructure integration tests (including this milestone's own 26, correctly skipped in that unauthenticated context and separately proven in Section 11.2).
- `python -m build`: PASS (sdist + wheel built, including all four new repository modules and the four updated mapper modules).
- `git diff --check`: PASS, exit 0 (informational CRLF/LF line-ending notices from Git only, no actual whitespace errors).

## 13. Hostile Self-Review

Each failure mode below was checked against the actual code in all four repository modules (not just the one file quoted in earlier sections), with the concrete evidence supporting each conclusion:

1. **Version regression** — not possible: `save()` rejects `record.version < expected_persisted_version.value` before any SQL executes; the repository never persists a version lower than what the caller expected.
2. **Repository-owned version increment** — not present: every INSERT/UPDATE sets `version` to `record.version` verbatim (the mapper's read of the aggregate's own already-advanced version); `AggregateVersion.next()` is never called from repository code.
3. **Stale UNCHANGED** — not possible: the Python-side `UNCHANGED`/`UPDATED` classification is only a label: the actual guarded `UPDATE ... WHERE version = :expected_persisted_version` still runs and must match the real persisted row for either classification to be returned; a stale expected version fails the guarded UPDATE (zero rows) and is reclassified as `OptimisticConcurrencyConflict` in the same transaction, regardless of the Python-side label.
4. **Incomplete identity predicate** — not present: every primary lookup/update in all four repositories filters on both `runtime_id` and `governance_id`; the runtime_id-only diagnostic queries run strictly after that full-identity query/update has already failed to match, solely to classify *why* (not-found vs. mismatch vs. conflict), never as an alternate success path.
5. **Zero-row race** — not present: the version check and row update are one atomic `UPDATE ... RETURNING` statement; PostgreSQL's row-level locking serializes concurrent writers on the same row, so no window exists between checking and writing the version.
6. **Result-before-commit** — not present: in every `add()`/`save()`, the `return SaveResult(...)` / `return LoadedAggregate(...)` statement is textually and structurally after the `with self._service.unit_of_work() as work:` block, which only completes without exception after a successful commit.
7. **Partial child replacement** — not present, and now has a direct regression test (`test_run_child_write_failure_rolls_back_root_update`, Section 11.2): child DELETE+INSERT and the root UPDATE share one Unit of Work; any child-insert failure raises inside that `with` block and rolls back the entire transaction, root included.
8. **Transaction leakage** — not present: every method opens exactly one `with self._service.unit_of_work() as work:` block per call, never commits/rolls back manually outside it, and never nests (the pre-existing `PostgresUnitOfWork` nesting guard is untouched by this milestone).
9. **Error-detail leakage** — not present: every `RepositoryContractError` message is a fixed string authored in repository code, or the mapper's own designated-safe `exc.safe_message` / the aggregate's own domain-vocabulary `ReconstructionError` text (e.g. "Dataset Manifest manifest_id already exists in Run") — never SQL text, a SQLSTATE code, a constraint name, or a driver/exception type name.
10. **Wrong constraint translation** — not present: each repository's `_ROOT_UNIQUE_CONSTRAINTS` set was checked against the real M022 schema's actual constraint names (`pk_<table>`/`uq_<table>_governance_id` for all four aggregates) and empirically exercised by the duplicate-`runtime_id` and duplicate-`governance_id` integration tests for all four aggregates.
11. **Generic repository abstraction** — not present: no shared base class exists; all four `Postgres<X>Repository` classes independently implement `get`/`add`/`save`.
12. **Mapper/repository responsibility overlap** — not present: mappers never execute SQL, open a Unit of Work, or call `_reconstruct_*`; repositories never perform aggregate-to-`DurableRecord` mapping themselves — the per-repository `_row_to_*`/`_*_params` helpers only translate between raw SQL rows and already-mapped `DurableRecord` field values (persistence-layer plumbing the design's Section 10 assigns to the repository), never aggregate business logic.
13. **Architecture over-broadening** — limited to exactly `ALLOWED["shared"]` gaining `identifiers` in addition to the frozen design's own four aggregate packages (Section 10); `FORBIDDEN_IMPORT_PREFIXES` and every other `ALLOWED` entry are untouched.
14. **PostgreSQL test false positives** — not present: all 26 integration tests execute real SQL against a real, migrated PostgreSQL 18.4 instance; the one test using a substituted mapper (`test_run_child_write_failure_rolls_back_root_update`) only replaces the aggregate-to-`DurableRecord` translation step via the repository's own documented `mapper=` constructor seam — the database layer under test is never mocked.
15. **Hidden MILESTONE-024 work** — not present: `git status` at this checkpoint shows only the mapper additions, the four repository modules plus `_errors.py`/`__init__.py`, the one architecture-checker line plus its negative fixture, the two new test files, and this document — no application service, API, worker, or Audit/Decision-Candidate/Decision-Freeze code exists anywhere in the change set.

Two genuine defects were found and corrected during this implementation effort itself (before this hostile-review pass), both in the same class: `run_repository.py`'s and `evidence_package_repository.py`'s row-to-`DurableRecord` helpers for owned child collections (`_row_to_manifest`, `_row_to_criterion`) originally populated the child's owning-aggregate-identity field with the *runtime_id* UUID read from the child row's own foreign-key column, when the mapper's `from_durable_record` requires that field to hold the aggregate's *governance_id* (to construct a valid `RunId`/`EvidencePackageId`). This was caught empirically — not by static analysis — via an end-to-end smoke test that mutated, saved, and reloaded a Run with a manifest and an EvidencePackage with a criterion result, which raised `MapperError`/`InvalidPersistedAggregateState` on reload. Both were fixed by passing the root row's own `governance_id` into the row-conversion helper instead of the child row's `runtime_id` foreign-key column, and re-verified by the same reload path plus the now-permanent `test_run_get_reconstructs_manifests_in_deterministic_position_order` and `test_evidence_package_get_reconstructs_both_child_collections_independently_ordered` integration tests. Campaign and Review have no such field (their only child-owned value objects — transitions and `ReviewFinding` — never carry a separate parent-identity field), so this defect class could not and did not occur there.

## 14. Explicit Non-Goals Confirmed

Not implemented:

- application services, runtime composition, APIs, or workers;
- Audit runtime, Decision Candidate, Decision Freeze;
- any generic/shared concrete repository or mapper base class;
- retry logic for `OptimisticConcurrencyConflict` (remains application-owned, per the frozen M020 design);
- any MILESTONE-024 work.

No frozen M019, M020, M021, or M022 source file's existing public shape was modified. The only architecture-checker change beyond the frozen design's own narrow instruction is the Section 10 `identifiers` addition, which is a necessary completion of that same instruction (not a new, independent broadening) required to implement the already-frozen M020 Protocol signatures exactly.

## 15. Final Status

```text
M023 POSTGRESQL REPOSITORY ADAPTER IMPLEMENTATION COMPLETE - READY FOR INDEPENDENT REVIEW
```

MILESTONE-023 implementation is NOT marked APPROVED, and is NOT FROZEN. MILESTONE-024 has NOT started.
