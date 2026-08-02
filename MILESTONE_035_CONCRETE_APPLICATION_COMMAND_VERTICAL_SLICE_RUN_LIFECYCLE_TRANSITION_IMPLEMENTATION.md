# MILESTONE-035 - Concrete Application Command Vertical Slice (Run Lifecycle Transition) Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW**

This document is an implementation candidate. It has not been reviewed, approved, or frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `4a68c24662d0bccdfa77be0a826eebab142a3aa9` |

## 3. Frozen Scope/Design Authority

- Scope: `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE.md` (candidate `26aab1acb1d08150144b8ce52d63f17796f121ef`), frozen via `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE_FREEZE.md` (`cebbd945107f4242cada86eea29e210e7b7c701c`).
- Design: `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_DESIGN.md` (candidate `bac7f202c4f6dca591702d4d1404a8390c4bb755`), frozen via `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_DESIGN_FREEZE.md` (`3227bba3d22756bc138cd45bbb0ac98824bc537c`).

This implementation introduces nothing beyond what those documents authorize.

## 4. Baseline Validation

Recorded before any change, against HEAD `4a68c24662d0bccdfa77be0a826eebab142a3aa9`, using the project `.venv` (Python 3.13.14):

| Command | Result |
| --- | --- |
| `python tools/check_architecture.py .` | exit 0 |
| `python -m ruff check .` | All checks passed |
| `python -m mypy` (canonical) | Success: no issues found in 91 source files |
| `python -m pytest -q -m "not integration"` | 561 passed, 128 deselected, coverage 83.38% (gate 80.0%) |

No pre-existing failure was hidden or worked around.

## 5. Implementation Map

Exactly three new production symbols in one new module, one export-only change to the package `__init__.py`, three new test files (unit, contract, integration), no other production or test file touched.

## 6. Production Implementation

New file: `src/empirical_platform/usecases/authorize_run.py`. Changed file: `src/empirical_platform/usecases/__init__.py` (export-only addition of `AuthorizeRunCommand`, `AuthorizeRunHandler`, mirroring the existing export blocks exactly).

## 7. Command Contract

```python
@dataclass(frozen=True, slots=True)
class AuthorizeRunCommand:
    identity: DomainIdentity[RunId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Exactly six fields, matching the frozen design and `Run.authorize()`'s own signature exactly.

## 8. Handler Contract

```python
class AuthorizeRunHandler:
    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, command: AuthorizeRunCommand) -> SaveResult:
        loaded = self._run_repository.get(command.identity)
        run = loaded.aggregate
        run.authorize(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._run_repository.save(
            run, expected_persisted_version=command.expected_persisted_version
        )
```

Sole constructor dependency: `run_repository: RunRepository`. No `CampaignRepository`, `EvidencePackageRepository`, `ReviewRepository`, `Clock`, identifier generator, persistence adapter, transaction manager, retry service, registry, dispatcher, mediator, or composition root — verified by hostile self-audit (Section 30).

## 9. Selected Transition

`Run.authorize()`: `CREATED` → `AUTHORIZED`. No other Run lifecycle method appears in `authorize_run.py` — verified directly (Section 30).

## 10. Identity Semantics

`command.identity` is passed to `run_repository.get()` unchanged — proven by `test_get_is_called_exactly_once_with_exact_identity` (`repository.get_calls[0] is command.identity`).

## 11. Expected-Version Semantics

`command.expected_persisted_version` — never `loaded.persisted_version` — is passed to `save()`. Proven with deliberately distinguishable values (`loaded.persisted_version = AggregateVersion(5)`, `command.expected_persisted_version = AggregateVersion(0)`) by `test_save_receives_command_version_not_loaded_persisted_version`, which asserts the saved value `is` the command's own object and `!=` the loaded aggregate's persisted version.

## 12. Exact Load–Mutate–Save Sequence

Implemented exactly as frozen: receive command → call `get()` once → call `authorize()` once → call `save()` once with `command.expected_persisted_version` → return the resulting `SaveResult` unchanged. No second `get()`/`save()`, no `add()`, no retry, no Campaign access, no transaction orchestration — each proven by dedicated tests (Section 25).

## 13. Result Contract

Exactly the `SaveResult` produced by `run_repository.save()` is returned, unchanged — proven by `test_returned_object_is_the_exact_save_result` (`result is save_result`).

## 14. Aggregate-Version Semantics

`Run.version` advances by exactly one on `authorize()` — proven directly against a genuine `Run` aggregate by `test_successful_authorize_produces_exactly_one_transition_record` (`run.version == version_before.next()`), never conflated with `loaded.persisted_version` or `command.expected_persisted_version` anywhere in the implementation.

## 15. Persisted-Version Semantics

`loaded.persisted_version` is never passed to `save()` (Section 11). `SaveResult.persisted_version` (the repository's resulting write metadata) is returned unchanged to the caller.

## 16. Transition-History Semantics

Exactly one `StateTransitionRecord` is appended on success, carrying `from_state="CREATED"`, `to_state="AUTHORIZED"`, and the command's own `actor`/`correlation_id`/`reason` — proven against a genuine `Run` aggregate (`test_successful_authorize_produces_exactly_one_transition_record`, `test_authorize_called_with_exact_command_arguments`) and independently against real PostgreSQL (Section 26).

## 17. Invalid-Transition Behavior

If the persisted Run's state is not `CREATED`, `Run.authorize()` raises `ValueError` before `save()` is reached. Proven at the unit level (`test_domain_invalid_transition_propagates_and_save_never_called`, `repository.save_calls == []`) and at the PostgreSQL level (Section 27, reusing the same command twice — the second attempt fails domain-validly with no persisted change).

## 18. Not-Found Behavior

Transparent, unchanged propagation of `AggregateNotFound` — proven by `test_aggregate_not_found_from_get_propagates_with_identity_preserved` (`excinfo.value is exc`) and by the PostgreSQL missing-Run test (Section 28).

## 19. Optimistic-Concurrency Behavior

Transparent, unchanged propagation of `OptimisticConcurrencyConflict` — proven at the unit level with a dedicated fake-repository test using the real exception type (`test_optimistic_concurrency_conflict_from_save_propagates_unchanged`) and, more importantly, genuinely reproduced against real PostgreSQL using the frozen `append_manifest()`-based deterministic mechanism (Section 29).

## 20. Arbitrary Error Semantics

Transparent, unchanged propagation of arbitrary `get()`/`save()` exceptions — proven by `test_arbitrary_get_exception_propagates_unchanged` and `test_arbitrary_save_exception_propagates_with_identity_preserved`.

## 21. Validation Ownership

No `__post_init__` on `AuthorizeRunCommand`; no duplicated identifier, version, or domain-argument validation in the handler — verified directly by reading the implementation (Section 8) and by hostile self-audit (Section 30). Matches the design freeze's corrected Section 26/8-9 wording precisely: `DomainIdentity` validates only the base identity-pair structure at runtime, `RunId` specialization is static-only, and no compensating runtime check was added.

## 22. Transaction Non-Ownership

No `run_composed()`, no unit-of-work, session, engine, or connection reference anywhere in `authorize_run.py` — verified by hostile self-audit (Section 30).

## 23. CommandEntryPoint Binding

`AuthorizeRunHandler` is bound via `CommandEntryPoint` in tests only (`test_handler_is_invocable_through_command_entry_point`, `test_handler_bound_at_construction_reused_across_invocations`); no production composition root exists anywhere in this change.

## 24. Architecture Impact

**None.** `python tools/check_architecture.py .` passes at exit 0 with zero change to `ALLOWED`, `ALLOWED_EXACT_IMPORTS`, or `FORBIDDEN_IMPORT_PREFIXES`. `tools/check_architecture.py` itself is untouched — confirmed by `git diff --name-status`, which shows no output for that file.

## 25. Tests Added and Reused

**Added** (29 tests, all passing):

- `tests/contract/test_authorize_run_handler_contract.py` (3 tests): typed-conformance proof, `handle` signature shape, no-inheritance proof.
- `tests/unit/test_authorize_run_usecase.py` (21 tests): command field/immutability/slots (5); typed-conformance/get-call/authorize-argument/save-argument/expected-version-distinction/no-add/no-second-call/return-value/entry-point/reuse-across-calls proofs (10); transition-history proof against a genuine aggregate (1); domain-invalid-transition (1); `AggregateNotFound`/arbitrary-`get()`-failure (2); `OptimisticConcurrencyConflict`/arbitrary-`save()`-failure (2).
- `tests/integration/test_m035_authorize_run_usecase.py` (5 tests, PostgreSQL, opt-in): golden path; invalid-transition (command reused, second attempt fails domain-validly); missing-Run; deterministic `append_manifest()`-based conflict (frozen thirteen-step sequence); no-production-composition.

**Reused/re-run for regression** (all passing, zero change to any of these files):

- `tests/unit/test_run_aggregate.py`, `tests/contract/test_prepare_campaign_for_authorization_handler_contract.py`, `tests/unit/test_prepare_campaign_for_authorization_usecase.py` (M032)
- `tests/unit/test_create_run_usecase.py` (M033)
- `tests/unit/test_get_run_usecase.py` (M034)
- `tests/architecture/test_module_boundaries.py`

## 26. PostgreSQL Success Evidence

**Executed live** against a fresh, disposable `postgres:17` Docker container (`m035-postgres-impl`, isolated non-default host port, stopped and removed after evidence capture). `test_golden_path_authorizes_run_via_command_entry_point_and_real_repository`: seeds a Campaign (M030) and Run (M033), invokes `AuthorizeRunCommand` through `CommandEntryPoint`, asserts `SaveResult.operation is SaveOperation.UPDATED`, `SaveResult.persisted_version == AggregateVersion(1)`, and — via an independent reload — `state is RunLifecycleState.AUTHORIZED`, `persisted_version == AggregateVersion(1)`, exactly one `transition_history` record with the correct `from_state`/`to_state`/`actor`/`correlation_id`/`reason`. **PASSED.**

## 27. PostgreSQL Invalid-Transition Evidence

**Executed live.** `test_invalid_transition_raises_domain_error_without_persisting`: the same `AuthorizeRunCommand` sequence used in M032's own precedent — the first invocation succeeds (`CREATED`→`AUTHORIZED`); a second invocation against the now-`AUTHORIZED` Run raises the domain `ValueError` (`"cannot transition from"`); independent reload confirms the persisted state, version, and transition-history count are unchanged by the failed second attempt. **PASSED.**

## 28. PostgreSQL Missing-Run Evidence

**Executed live.** `test_missing_run_raises_aggregate_not_found`: a `DomainIdentity[RunId]` for a governance/runtime pair that was never persisted; `AggregateNotFound` propagates through `CommandEntryPoint` unchanged. **PASSED.**

## 29. Deterministic Conflict Evidence

**Executed live**, implementing the frozen design's exact thirteen-step sequence (design freeze Section 34). `test_stale_expected_version_raises_optimistic_concurrency_conflict`: seeds Campaign+Run; independently reloads the Run and calls `append_manifest()` with a legitimate `DatasetManifest`, confirming this advances the aggregate version while preserving `CREATED` (asserted directly: `advanced.aggregate.state is RunLifecycleState.CREATED`, `len(advanced.aggregate.manifests) == 1`); saves the interfering instance with `expected_persisted_version=AggregateVersion(0)`, advancing the persisted version to `1`; then invokes `AuthorizeRunCommand` with the now-stale `expected_persisted_version=AggregateVersion(0)` — `authorize()` succeeds domain-validly in memory (the persisted state is still `CREATED`), but `save()` raises `OptimisticConcurrencyConflict` (`expected_persisted_version == AggregateVersion(0)`, `actual_persisted_version == AggregateVersion(1)`); an independent reload confirms the persisted row remains exactly what the interfering write produced (`CREATED`, `persisted_version == AggregateVersion(1)`, the interfering manifest present, zero transition-history records — proving `authorize()`'s in-memory mutation was never persisted). `append_manifest()`'s use here is explicitly test scaffolding only, never invoked by `AuthorizeRunHandler` or any other production code. **PASSED**, independently reproducing the exact mechanism the design freeze specified, not a restatement of M032's own `revise_scope_statement()`-based mechanism.

## 30. Hostile Self-Audit

Grepped `src/empirical_platform/usecases/authorize_run.py` directly for every prohibited pattern the implementation mission listed: `CampaignRepository`, `EvidencePackageRepository`, `ReviewRepository`, `shared.persistence`, `PostgresRunRepository`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `sqlalchemy`, `psycopg`, `boto3`, `try`/`except`, `for`/`while` loops, `retry`, `backoff`, `cache`, a second `.get(`/`.save(`, `.add(`/`.delete(`, `run_composed`, `loaded.persisted_version`, every other Run lifecycle method (`start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`), `EvidencePackage`, `Review`, registry/dispatcher/mediator/service-locator/DI/composition-root references, transport, and `M036`. **Zero matches beyond the single expected `.get()`/`.save()` call each and the docstring's own accurate "for one command" phrasing** (a false-positive substring match, not a `for` loop). `grep -c` confirms exactly 1 occurrence each of `.get(` and `.save(` in the file.

## 31. Validation Gates

Rerun fresh from final implementation state (all against the project `.venv`):

| Gate | Result |
| --- | --- |
| `git status --short` before staging | exactly the 5 expected files (1 modified, 4 new) |
| `python tools/check_architecture.py .` | exit 0 |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 219 files already formatted |
| `python -m mypy` (canonical) | Success: no issues found in 92 source files |
| `python -m pytest -q -m "not integration"` | 585 passed, 133 deselected, coverage 83.49% (gate 80.0%) — no regression, +24 tests, +5 integration tests deselected as expected |
| `python -m pytest tests/unit/test_run_aggregate.py tests/contract/test_prepare_campaign_for_authorization_handler_contract.py tests/unit/test_prepare_campaign_for_authorization_usecase.py tests/unit/test_create_run_usecase.py tests/unit/test_get_run_usecase.py tests/architecture/test_module_boundaries.py` | 91 passed (M032/M033/M034/architecture regression) |
| `python -m pytest tests/integration/test_m035_authorize_run_usecase.py -v` (PostgreSQL, live) | **5 passed** |
| `python -m pytest tests/integration/ -v` (PostgreSQL, live, full regression) | **127 passed, 6 skipped** (up from 122 passed pre-M035; 6 skips are pre-existing MinIO/unified-runtime opt-in gating, unrelated to M035) |
| `python -m pytest -q` (PostgreSQL opt-in, full suite) | **712 passed, 6 skipped** |
| `python -m build --sdist --wheel` | succeeded; `authorize_run.py` present in the built wheel's file list (verified directly) |
| `python tools/secret_scan_targets.py --root .` | 385 targets discovered (up from 376 pre-M035, consistent with the 4 new tracked files) |
| `python -m mypy --explicit-package-bases` on the new test files | 2 "unused type: ignore" findings — reproduced identically against the pre-existing, already-accepted M031/M034 precedent files under the same non-canonical invocation; not a defect specific to this change, and outside canonical mypy scope (`pyproject.toml`: `packages = ["empirical_platform"]`, i.e. `src/` only) |

## 32. Changed Files

```
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/authorize_run.py
A  tests/contract/test_authorize_run_handler_contract.py
A  tests/integration/test_m035_authorize_run_usecase.py
A  tests/unit/test_authorize_run_usecase.py
```

Plus this implementation document and `PROJECT_CHECKPOINT.md`, added/updated in the same commit per the mission's authorization.

## 33. Explicit Non-Changes

No change to: `Run` aggregate; `RunRepository`; `PostgresRunRepository`; identity/version contracts (`DomainIdentity`, `RunId`, `AggregateVersion`); `LoadedAggregate`; `SaveResult`; `OptimisticConcurrencyConflict`; `CommandHandler`; `CommandEntryPoint`; `tools/check_architecture.py`; any schema or migration; any M030-M034 source or test file; any M035 scope/design/freeze authority document; any M036 material. Verified directly: `git status --short` shows only the five files in Section 32.

## 34. Known Limitations

None identified. Unlike M034's implementation, this milestone's PostgreSQL evidence — including the deterministic conflict scenario — was fully executed live in this session; there is no disclosed-limitation gap to carry forward.

## 35. Remaining Risks

- The `mypy --explicit-package-bases` per-file invocation against the new test files reports 2 "unused type: ignore" findings that do not occur under the canonical project mypy configuration; documented in Section 31 as a pre-existing, non-blocking artifact shared with the M031/M034 precedent files, not specific to this change.
- No other risk beyond those already accepted at design-freeze (deferred read-to-update `expected_persisted_version` acquisition, deferred retry policy, etc.) is introduced by this implementation.

## 36. Review Status

**CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW.** Not approved. Not frozen.

## 37. Next Permitted Action

**MILESTONE-035 INDEPENDENT IMPLEMENTATION REVIEW.**
