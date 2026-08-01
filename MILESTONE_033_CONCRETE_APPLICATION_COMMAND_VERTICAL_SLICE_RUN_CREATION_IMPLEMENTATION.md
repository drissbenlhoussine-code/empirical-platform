# MILESTONE-033 - Concrete Application Command Vertical Slice (Run Creation) Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW**

This document is an implementation candidate. It has not been reviewed, approved, or frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Governance HEAD immediately before implementation | `4fc6c041832362af87a6b0e77e661394b7a11eb5` |

## 3. Frozen Scope/Design Authority

| Document | Commit |
| --- | --- |
| M033 Scope | `04e274240f7958d80bc0cb87f92f825b563fbd5a` |
| M033 Scope Freeze | `44dd29e34f6150bd37bc466eed14098d75ac57ab` |
| M033 Design | `8edead3bc25d786cef8563f4fc4815a889a3a447` |
| M033 Design Freeze | `ec802143626e850dafe70ce9f0f561fa8516df94` |

Every load-bearing decision in this implementation traces directly to `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN_FREEZE.md` Sections 10-29.

## 4. Baseline Validation

Fresh run against governance HEAD `4fc6c041832362af87a6b0e77e661394b7a11eb5`, before any implementation edit:

| Gate | Result |
| --- | --- |
| `tools/check_architecture.py .` | 0 violations |
| `ruff format --check src tests tools` | 204 files already formatted |
| `ruff check src tests tools` | All checks passed |
| `mypy` | Success: no issues found in 89 source files |
| `pytest -q` (no PostgreSQL opt-in) | 522 passed, 119 skipped, coverage 83.18% |
| `pytest tests/unit/test_run_aggregate.py tests/contract/test_run_repository_contract.py tests/unit/test_runtime_identifiers.py -v` | 50 passed |
| `build` | sdist + wheel built successfully |

No pre-existing failure was found or hidden.

## 5. Implementation Map

Built by direct source inspection before any edit: `Run.__init__(*, identity, campaign_id)` (minimal, no context fields); `RunRepository.add()`/`get()`/`save()` (identical shape to `CampaignRepository`); `PostgresRunRepository.add()` (its `except FoundationError` block special-cases only `_ROOT_UNIQUE_CONSTRAINTS = {"pk_run", "uq_run_governance_id"}`, re-raising everything else, including foreign-key violations, unchanged); the real `run.campaign_id -> campaign.governance_id` foreign key (`migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py` line 148); `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` (missing `"run"`); the existing `bad_run_import.py` fixture (which would silently stop triggering once `"run"` is added — requiring removal/replacement, not merely an addition). No conflict was found between the frozen design and the live repository.

## 6. Production Implementation

Created `src/empirical_platform/usecases/create_run.py` (56 lines) exactly per the frozen design. Updated `src/empirical_platform/usecases/__init__.py` to export `CreateRunCommand`/`CreateRunHandler` and document the `Run`/`RunRepository` dependency. Modified `tools/check_architecture.py` with exactly one line: `"usecases": {"shared", "identifiers", "campaign", "run"}`.

## 7. Command Contract

```python
@dataclass(frozen=True, slots=True)
class CreateRunCommand:
    run_governance_id: str
    campaign_governance_id: str
```

Exactly two fields, frozen, slotted, no defaults, no metadata — byte-identical to the frozen design (Section 13 of the design freeze).

## 8. Handler Contract

```python
class CreateRunHandler:
    __slots__ = ("_run_repository", "_runtime_identifier_generator")

    def __init__(self, *, run_repository: RunRepository, runtime_identifier_generator: RuntimeIdentifierGenerator) -> None:
        ...
    def handle(self, command: CreateRunCommand) -> DomainIdentity[RunId]:
        ...
```

Constructor signature verified by `inspect.signature` in `tests/unit/test_create_run_usecase.py::test_handler_constructor_accepts_no_campaign_repository_parameter`: exactly `["self", "run_repository", "runtime_identifier_generator"]` — no `campaign_repository` parameter exists.

## 9. Campaign Existence Semantics

No `CampaignRepository` import, dependency, or lookup anywhere in `create_run.py` — verified by direct grep (Section 26) and by a dedicated structural unit test. Campaign existence is enforced exclusively by the real `run.campaign_id -> campaign.governance_id` foreign key. `tests/integration/test_m033_create_run_usecase.py::test_missing_campaign_raises_raw_foundation_error_not_translated` proves a nonexistent `campaign_governance_id` produces an unmodified `FoundationError` with `category=FoundationErrorCategory.PERSISTENCE` (explicitly not `AggregateAlreadyExists`), and that no Run row is persisted (`run_repo.get()` on the attempted identity raises `AggregateNotFound`).

## 10. Identity Semantics

`RunId(command.run_governance_id)` and `CampaignId(command.campaign_governance_id)` constructed by the handler; `runtime_id` generated once via the injected `RuntimeIdentifierGenerator.generate()`. Verified by `test_runtime_id_is_obtained_from_injected_generator` and `test_aggregate_supplied_to_add_has_expected_identity_and_campaign_id`.

## 11. Runtime Identifier Generation

Exactly one `generate()` call per `handle()` invocation — verified by `test_runtime_identifier_generator_failure_propagates_unchanged` (`generator.generate_calls == 1` even on failure) and by the PostgreSQL golden-path test using a `DeterministicRuntimeIdentifierGenerator` with a single value.

## 12. Exact Creation Sequence

Matches the frozen design (Section 17 of the design freeze) exactly: `RunId` construction → `generate()` → `DomainIdentity` construction → `CampaignId` construction → `Run` construction → `RunRepository.add()` (exactly once) → return `run.identity`. Verified by `test_malformed_run_governance_id_propagates_unchanged` (fails before `add()`, generator still called since `RunId` is constructed first) and `test_malformed_campaign_governance_id_propagates_unchanged` (fails after generator call but before `add()`).

## 13. Return Contract

Returns `run.identity` (read off the constructed aggregate) — verified by `test_handler_returns_the_persisted_aggregates_identity` (`result is repository.add_calls[0].identity`).

## 14. Duplicate Identity Behavior

Unit level: `test_repository_add_failure_propagates_with_identity_preserved` proves an `AggregateAlreadyExists` raised by a failing fake `add()` propagates with `is`-identical exception instance. PostgreSQL level: `test_duplicate_run_governance_id_raises_aggregate_already_exists` and `test_duplicate_runtime_id_raises_aggregate_already_exists` (two different governance IDs sharing one generated runtime ID collide on the real `pk_run` constraint) both prove `AggregateAlreadyExists` against a real database.

## 15. Missing Campaign Behavior

See Section 9. Real PostgreSQL evidence: `test_missing_campaign_raises_raw_foundation_error_not_translated`.

## 16. Error Semantics

No `try`/`except` anywhere in `create_run.py` — verified by direct grep (Section 26). All five failure classes (malformed `RunId`, malformed `CampaignId`, generator failure, `AggregateAlreadyExists`, missing-Campaign `FoundationError`) propagate transparently, each with a dedicated test proving exact exception-instance identity is preserved where applicable.

## 17. Validation Ownership

No validation duplicated in the command or handler — confirmed by `test_command_is_a_plain_unvalidated_data_carrier` (empty strings accepted at command construction, rejected only when the handler later constructs `RunId`/`CampaignId`).

## 18. Transaction Non-Ownership

No `run_composed()`, no transaction manager, no unit-of-work abstraction imported or referenced anywhere in `create_run.py` — verified by direct grep (Section 26). Exactly one `RunRepository.add()` call per invocation.

## 19. CommandEntryPoint Binding

`test_handler_is_invocable_through_command_entry_point` and `test_handler_bound_at_construction_not_per_call` prove the existing, unmodified `CommandEntryPoint` binds `CreateRunHandler` correctly, invokes it exactly once per call, and reuses the same bound handler across repeated invocations. No `CommandEntryPoint` source change.

## 20. Architecture Impact

Exactly one line changed in `tools/check_architecture.py`: `"usecases": {"shared", "identifiers", "campaign", "run"}`. `FORBIDDEN_IMPORT_PREFIXES["usecases"]` unchanged. The pre-existing `bad_run_import.py` fixture (which asserted `usecases` could not import `run`) was removed, since that import is now legitimately allowed, and replaced with `bad_evidence_import.py` (proving `usecases` still cannot import `evidence`). A new `run/bad_usecases_import.py` fixture was added, proving the reverse-direction boundary (`run` still cannot import `usecases`) remains intact. `tests/architecture/test_module_boundaries.py` was updated: the obsolete `"usecases may not import run"` assertion was removed and replaced with `"usecases may not import evidence"` and a new `"run may not import usecases"` assertion.

## 21. Tests Added and Reused

**Added:** `tests/unit/test_create_run_usecase.py` (16 tests), `tests/contract/test_create_run_handler_contract.py` (3 tests), `tests/integration/test_m033_create_run_usecase.py` (5 tests), `tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_evidence_import.py`, `tests/fixtures/illegal_imports/src/empirical_platform/run/bad_usecases_import.py`.

**Reused unmodified:** `tests/unit/test_run_aggregate.py`, `tests/contract/test_run_repository_contract.py`, `tests/integration/test_m023_postgres_repositories.py` (Run-specific cases), `tests/architecture/test_module_boundaries.py::test_current_source_tree_respects_boundaries`, `CommandEntryPoint`'s own generic tests.

**Removed (obsolete, not merely modified):** `tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_run_import.py` — its assertion became false once `"run"` was legitimately added to `ALLOWED["usecases"]`.

## 22. PostgreSQL Success Evidence

Fresh, disposable `postgres:17` Docker container (`m033-postgres`, port `55433`, container-specific password, never reused from any prior milestone), migrated with the frozen Alembic chain.

`test_golden_path_persists_via_command_entry_point_and_real_repository`: seeds a real Campaign via the frozen M030 `CreateCampaignHandler`, invokes `CreateRunCommand` through a bound `CommandEntryPoint`, asserts the returned `DomainIdentity[RunId]` matches the supplied governance ID and generated runtime ID, reloads via the real `RunRepository.get()`, and asserts identity, `campaign_id`, `state is RunLifecycleState.CREATED`, `persisted_version == AggregateVersion.initial()`, empty manifests, empty transition history. **PASSED.**

## 23. PostgreSQL Duplicate-Governance Evidence

`test_duplicate_run_governance_id_raises_aggregate_already_exists`: two `CreateRunCommand` invocations with the same `run_governance_id` against the same seeded Campaign; the second raises `AggregateAlreadyExists`. **PASSED.**

## 24. PostgreSQL Duplicate-Runtime Evidence

`test_duplicate_runtime_id_raises_aggregate_already_exists`: two different `run_governance_id` values, same `DeterministicRuntimeIdentifierGenerator`-supplied runtime ID for both — the second invocation collides on the real `pk_run` primary-key constraint and raises `AggregateAlreadyExists`. Deterministically feasible and genuinely reproduced; no infeasibility to report. **PASSED.**

## 25. PostgreSQL Missing-Campaign Evidence

`test_missing_campaign_raises_raw_foundation_error_not_translated`: no Campaign seeded; `campaign_governance_id="CAMP-9999"` triggers the real foreign-key violation; asserts `FoundationError` with `category is FoundationErrorCategory.PERSISTENCE`, explicitly not `AggregateAlreadyExists`, and confirms no Run row persisted via a follow-up `AggregateNotFound` on `run_repo.get()`. **PASSED.**

Also: `test_no_production_composition_machinery_is_required` — direct `handler.handle()` call with no `CommandEntryPoint`, no `FoundationRuntime`, no registry. **PASSED.**

## 26. Hostile Self-Audit

Direct grep of `src/empirical_platform/usecases/create_run.py` for: `CampaignRepository`, `shared.persistence`, `PostgresRunRepository`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `sqlalchemy`, `psycopg`, `boto3`, `try:`/`except`, `retry`, loops, `run_composed`, every Run lifecycle-transition method (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`, `append_manifest`), `.get(`/`.save(` calls, `EvidencePackage`, `Review`, registry/dispatcher/mediator/service-locator/composition/transport keywords, `M034` — **zero genuine matches** (the only textual hits were the word "Campaign" inside two prose docstring sentences, and "for " matched as a substring of docstring prose "for an existing Campaign"/"for one `CreateRunCommand`", neither a real for-loop). Exactly 7 imports (6 real + `__future__`), exactly one `.generate()` call, exactly one `.add()` call, zero `campaign` package import.

## 27. Validation Gates

Fresh run against the final working state:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| `git diff --check` | Clean |
| `tools/check_architecture.py .` | 0 violations |
| `ruff format --check src tests tools` | 209 files already formatted |
| `ruff check src tests tools` | All checks passed |
| `mypy` | Success: no issues found in 90 source files (was 89; +1 for `create_run.py`) |
| Focused M033 tests (unit + contract + architecture) | 20 passed |
| Full `pytest -q`, no PostgreSQL opt-in | 540 passed, 124 skipped, coverage 83.28% |
| Full `pytest -q`, **real PostgreSQL** | **658 passed**, 6 skipped, coverage **92.08%** |
| M033 PostgreSQL integration tests | 5 passed |
| Full `tests/integration/` regression, real PostgreSQL | 118 passed, 6 skipped (0 failed) |
| M030-M032 + M023 Run-specific regression, real PostgreSQL | 35 passed |
| `build` | sdist + wheel built; `create_run.py` present in wheel contents |
| `pip_audit` | No known vulnerabilities |
| `secret_scan_targets.py` | 365 targets discovered |

## 28. Changed Files

```
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/create_run.py
M  tests/architecture/test_module_boundaries.py
D  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_run_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_evidence_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/run/bad_usecases_import.py
A  tests/contract/test_create_run_handler_contract.py
A  tests/integration/test_m033_create_run_usecase.py
A  tests/unit/test_create_run_usecase.py
M  tools/check_architecture.py
A  MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
```

Twelve files. No M020-M032 source, test, governance, schema, or migration file touched. No M033 scope/design/freeze document touched.

## 29. Explicit Non-Changes

`Run` aggregate, `RunRepository`, `PostgresRunRepository`, `Campaign` aggregate, `CampaignRepository`, `PostgresCampaignRepository`, `CommandHandler`, `CommandEntryPoint`, database schema and Alembic migrations, `src/empirical_platform/usecases/create_campaign.py` (M030), `get_campaign.py` (M031), `prepare_campaign_for_authorization.py` (M032) — all unmodified. No production composition root, registry, dispatcher, mediator, or DI container. No second Run command. No Run query. No Run lifecycle-transition usecase. No `EvidencePackage`/`Review` usecase. No MILESTONE-034 work of any kind.

## 30. Known Limitations

None identified. Every PostgreSQL evidence obligation the design freeze specified (Section 27 of the design freeze) was genuinely and deterministically reproduced, including the duplicate-runtime-ID scenario, which the frozen design flagged as "where deterministically feasible" — it proved fully feasible using the existing `DeterministicRuntimeIdentifierGenerator` test double.

## 31. Remaining Risks

None load-bearing. The implementation matches every frozen design decision with no deviation; all validation gates pass; the architecture-checker change is exactly the one line the design freeze authorized; both fixture-set changes (`bad_run_import.py` removal, `bad_evidence_import.py`/`run/bad_usecases_import.py` addition) are narrowly justified consequences of the authorized checker change, not scope expansion.

## 32. Review Status

`CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW`. Not approved. Not frozen.

## 33. Next Permitted Action

**MILESTONE-033 INDEPENDENT IMPLEMENTATION REVIEW.**
