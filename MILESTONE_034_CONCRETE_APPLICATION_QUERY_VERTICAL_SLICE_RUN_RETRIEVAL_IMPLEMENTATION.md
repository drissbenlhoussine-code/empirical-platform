# MILESTONE-034 - Concrete Application Query Vertical Slice (Run Retrieval) Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW**

This document is an implementation candidate. It has not been reviewed, approved, or frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `8c324ca9896e033dc7ac0d56fbfd91a05781fe8e` |

## 3. Frozen Scope/Design Authority

- Scope: `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE.md` (candidate `3ee8485143f1397cad9d14bc55744e97f60aa9d3`, correction `60178d3d1caf96d1fe33f318e57e94c708e8896f`), frozen via `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE_FREEZE.md` (`e6ad2c0e976ad0eb1cd00f8e15544d58ac45de7e`).
- Design: `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_DESIGN.md` (candidate `d343e38cba9b5a49db278c72ca1650dd50839bd2`, correction `993144e4361372e6978b11d96d6e1fe98e722c73`), frozen via `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_DESIGN_FREEZE.md` (`072fcee1d75c3f13547a6033c689786f2a110ab3`).

This implementation introduces nothing beyond what those documents authorize.

## 4. Baseline Validation

Recorded before any change, against HEAD `8c324ca9896e033dc7ac0d56fbfd91a05781fe8e`, using the project `.venv` (Python 3.13.14):

| Command | Result |
| --- | --- |
| `python tools/check_architecture.py .` | exit 0 |
| `python -m ruff check .` | All checks passed |
| `python -m mypy` (canonical: `packages = ["empirical_platform"]`) | Success: no issues found in 89 source files |
| `python -m pytest -q -m "not integration"` | 540 passed, 124 deselected, coverage 83.28% (gate 80.0%) |

No pre-existing failure was hidden or worked around.

## 5. Implementation Map

Exactly three new production symbols in one new module, one export-only change to the package `__init__.py`, three new test files (unit, contract, integration), no other production or test file touched.

## 6. Production Implementation

New file: `src/empirical_platform/usecases/get_run.py`. Changed file: `src/empirical_platform/usecases/__init__.py` (export-only addition of `GetRunHandler`, `GetRunQuery`, `RunSnapshot`, mirroring the existing `get_campaign` export block exactly).

## 7. Query Contract

```python
@dataclass(frozen=True, slots=True)
class GetRunQuery:
    """Request to retrieve a Run by its full frozen identity."""

    identity: DomainIdentity[RunId]
```

Exactly one field, no default, no extra metadata. A passive typed carrier: `frozen=True` enforces immutability after construction, not the field's type (per the frozen design's own correction, Section 19/26 of the design document).

## 8. Result Contract

```python
@dataclass(frozen=True, slots=True)
class RunSnapshot:
    identity: DomainIdentity[RunId]
    campaign_id: CampaignId
    state: RunLifecycleState
```

Exactly three fields, no defaults, no mutable collections, no raw `Run` reference, no `LoadedAggregate` reference.

## 9. Bounded RunSnapshot Semantics

`RunSnapshot`'s docstring states explicitly, matching the frozen design (Section 16 of the design freeze): it is a bounded Run header/status read value, deliberately excluding `Run.version`, `LoadedAggregate.persisted_version`, `manifests`, and `transition_history` — not a complete representation of Run's own state.

## 10. Handler Contract

```python
class GetRunHandler:
    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, query: GetRunQuery) -> RunSnapshot:
        loaded = self._run_repository.get(query.identity)
        return RunSnapshot(
            identity=loaded.aggregate.identity,
            campaign_id=loaded.aggregate.campaign_id,
            state=loaded.aggregate.state,
        )
```

Sole constructor dependency: `run_repository: RunRepository`. No `CampaignRepository`, no identifier generator, no persistence/runtime adapter — verified by hostile self-audit (Section 28) that none of these symbols appear anywhere in the module.

## 11. Identity Semantics

`query.identity` is passed to `run_repository.get()` unchanged — the exact same object, never reconstructed. Proven by `test_exact_query_identity_object_is_passed_to_repository_unchanged` (`repository.get_calls[0] is query.identity`).

## 12. Exact Retrieval Sequence

Implemented exactly as frozen: receive query → call `get()` once → receive `LoadedAggregate[Run]` → read `identity`/`campaign_id`/`state` only → construct one `RunSnapshot` → return it. No second `get()`, no Campaign lookup, no retry, no cache, no transaction orchestration — each proven by dedicated tests (Section 23).

## 13. Return Semantics

Exactly one `RunSnapshot` per successful `handle()` call; proven by `test_returned_object_is_a_run_snapshot` and the `QueryEntryPoint`-bound tests.

## 14. Aggregate-Version Exclusion

`RunSnapshot` never carries `Run.version`. Proven with deliberately distinguishable values by `test_aggregate_version_and_persisted_version_are_distinct_and_neither_leaks` (unit) — see Section 23.D and Section 26.

## 15. Persisted-Version Exclusion

`RunSnapshot` never carries `LoadedAggregate.persisted_version`. Proven by the same test (Section 14), which constructs `LoadedAggregate` with a `persisted_version` deliberately different from `aggregate.version` and asserts neither is reachable on the result.

## 16. Manifest/History Exclusion

Proven with non-empty source data by `test_manifests_and_transition_history_are_not_exposed_even_when_non_empty` — the source `Run` has one manifest and one transition record; `RunSnapshot` exposes neither, and the source aggregate's own data remains untouched.

## 17. Not-Found Behavior

Transparent, unchanged propagation of `AggregateNotFound`. Proven by `test_aggregate_not_found_propagates_with_identity_preserved` (`excinfo.value is exc`, no snapshot constructed, `get()` called exactly once).

## 18. Error Semantics

Transparent, unchanged propagation of any arbitrary repository exception. Proven by `test_arbitrary_repository_exception_propagates_with_identity_preserved`.

## 19. Validation Ownership

No `__post_init__` on `GetRunQuery` or `RunSnapshot`; no duplicated identifier validation in the handler — verified directly by reading the implementation (Section 6) and by the hostile self-audit (Section 28).

## 20. Transaction Non-Ownership

No `run_composed()`, no unit-of-work, session, engine, or connection reference anywhere in `get_run.py` — verified by hostile self-audit (Section 28).

## 21. QueryEntryPoint Binding

`GetRunHandler` is bound via `QueryEntryPoint` in tests only (`test_handler_is_invocable_through_query_entry_point`, `test_handler_bound_at_construction_not_per_call`); no production composition root exists anywhere in this change.

## 22. Architecture Impact

**None.** `python tools/check_architecture.py .` passes at exit 0 with zero change to `ALLOWED`, `ALLOWED_EXACT_IMPORTS`, or `FORBIDDEN_IMPORT_PREFIXES`. `tools/check_architecture.py` itself is byte-identical to the frozen baseline (unmodified — confirmed by `git diff --stat -- tools/`, which shows no output).

## 23. Tests Added and Reused

**Added** (21 tests, all passing):

- `tests/contract/test_get_run_handler_contract.py` (3 tests): typed-conformance proof, `handle` signature shape, no-inheritance proof.
- `tests/unit/test_get_run_usecase.py` (18 tests): query field/immutability/slots (3); `get()`-called-once and identity-pass-through (2); no `add()`/`save()` call (1); result-type and field-mapping (2); exact field-set assertion (1); result immutability (1); source-aggregate-not-mutated (1); **aggregate-version/persisted-version distinction proof** (1); **manifest/transition-history exclusion-with-non-empty-data proof** (1); `AggregateNotFound` propagation (1); arbitrary-exception propagation (1); `QueryEntryPoint` binding and reuse-across-calls (2).
- `tests/integration/test_m034_get_run_usecase.py` (4 tests, PostgreSQL, opt-in): golden path; missing-identity `AggregateNotFound`; no-production-composition; manifest/history/version non-exposure regression. **Written and verified to collect/import cleanly (`pytest --collect-only` succeeds, 4 tests collected); not executed against a live database in this environment — see Section 24.**

**Reused/re-run for regression** (all passing, zero change to any of these files):

- `tests/unit/test_get_campaign_usecase.py`, `tests/contract/test_get_campaign_handler_contract.py` (M031)
- `tests/unit/test_create_run_usecase.py`, `tests/contract/test_create_run_handler_contract.py` (M033)
- `tests/architecture/test_module_boundaries.py`

## 24. PostgreSQL Success Evidence

**Honest limitation, disclosed rather than fabricated.** This environment has no accessible live PostgreSQL instance: a native `postgresql-x64-16`/`postgresql-x64-18` Windows service is running on `localhost:5432`, but no valid credentials for it are available to this session, and Docker Desktop's daemon is not running (so the disposable-container pattern M023/M031/M033 used could not be started either). The integration test file was written to the identical, already-established pattern (`tests/integration/test_m031_get_campaign_usecase.py`), verified to:

- import every symbol correctly (`ruff check` and `ruff format --check` both pass),
- collect cleanly under pytest (`pytest tests/integration/test_m034_get_run_usecase.py --collect-only -q` → "4 tests collected", zero collection error),
- fail only at the connection step when actually attempted (`FATAL: password authentication failed` / `role "empirical" does not exist` against the real local server), confirming the test reaches real connection code, not a stub.

The user was asked how to proceed (provide credentials, start Docker, or proceed without live evidence) and explicitly chose to let this implementation proceed with the limitation disclosed rather than blocking on it. **This test suite has not been executed against a live database and its assertions are unverified until an environment with real PostgreSQL access runs it** (e.g. CI, or a later local session with working credentials/Docker).

## 25. PostgreSQL Missing-Run Evidence

Same limitation as Section 24: `test_missing_full_identity_raises_aggregate_not_found` is written and collects cleanly but is unexecuted here.

## 26. Version-Distinction Evidence

Executed and passing in this environment (unit-level, Section 23): `test_aggregate_version_and_persisted_version_are_distinct_and_neither_leaks` constructs a `Run`, advances it via `authorize()` to `version == AggregateVersion(1)`, wraps it in `LoadedAggregate(aggregate=run, persisted_version=AggregateVersion(0))` — a deliberately different value — and asserts `RunSnapshot` exposes neither `version` nor `persisted_version` and that its field set remains exactly `{"identity", "campaign_id", "state"}`.

## 27. Non-Empty Run-State Evidence

Executed and passing in this environment (unit-level, Section 23): `test_manifests_and_transition_history_are_not_exposed_even_when_non_empty` authorizes the Run (producing one transition record) and appends one `DatasetManifest` (producing one manifest), then asserts `RunSnapshot` exposes neither collection while the source `Run`'s own `manifests`/`transition_history` remain intact and unaliased. The equivalent PostgreSQL-level scenario (`test_no_campaign_table_query_and_manifests_history_load_without_error`) is written but subject to the Section 24 limitation.

## 28. Hostile Self-Audit

Grepped `src/empirical_platform/usecases/get_run.py` directly for every prohibited pattern the implementation mission listed: `CampaignRepository`, `shared.persistence`, `PostgresRunRepository`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `sqlalchemy`, `psycopg`, `boto3`, `try`/`except`, `for`/`while` loops, `retry`, `cache`, a second `.get(`, `run_composed`, transaction/session/engine/connection references, `.save(`/`.add(` calls, `Run` mutation, listing/filter/pagination, `version`/`persisted_version`/`manifests`/`transition_history` outside the docstring, `EvidencePackage`, `Review`, registry/dispatcher/mediator/service-locator/DI/composition-root references, transport, and `M035`. **Zero matches beyond the single expected `.get()` call and the docstring's own accurate description of what is excluded.** `grep -c "\.get("` confirms exactly 1 occurrence in the file.

## 29. Validation Gates

Rerun fresh from final implementation state (all against the project `.venv`):

| Gate | Result |
| --- | --- |
| `git status --short` before staging | exactly the 5 expected files (1 modified, 4 new) |
| `python tools/check_architecture.py .` | exit 0 |
| `python -m ruff check .` | All checks passed |
| `python -m ruff format --check .` | 215 files already formatted |
| `python -m mypy` (canonical) | Success: no issues found in 91 source files |
| `python -m pytest -q -m "not integration"` | 561 passed, 128 deselected, coverage 83.38% (gate 80.0%) — no regression, +21 tests, +4 integration tests deselected as expected |
| `python -m pytest tests/unit/test_get_campaign_usecase.py tests/contract/test_get_campaign_handler_contract.py tests/unit/test_create_run_usecase.py tests/contract/test_create_run_handler_contract.py tests/architecture/test_module_boundaries.py` | 39 passed (M031/M033/architecture regression) |
| `python -m build --sdist --wheel` | succeeded; `get_run.py` present in the built wheel's file list |
| `python -m pytest tests/unit/test_secret_scan_targets.py` | 3 passed (security/repository-verification coverage; included in the full-suite run above) |
| `python -m mypy --explicit-package-bases` on the new test files | 4 "unused type: ignore" findings — reproduced identically against the pre-existing, already-accepted M031 precedent file (`test_get_campaign_usecase.py`) under the same non-canonical invocation; not a defect specific to this change, and outside canonical mypy scope (`pyproject.toml`: `packages = ["empirical_platform"]`, i.e. `src/` only) |

## 30. Changed Files

```
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/get_run.py
A  tests/contract/test_get_run_handler_contract.py
A  tests/integration/test_m034_get_run_usecase.py
A  tests/unit/test_get_run_usecase.py
```

Plus this implementation document and `PROJECT_CHECKPOINT.md`, added/updated in the same commit per the mission's authorization.

## 31. Explicit Non-Changes

No change to: `Run` aggregate; `RunRepository`; `PostgresRunRepository`; Campaign contracts; `DomainIdentity`/`RunId`/`CampaignId`; `LoadedAggregate`/`AggregateVersion`; `QueryHandler`; `QueryEntryPoint`; `tools/check_architecture.py`; any schema or migration; any M030-M033 source or test file; any M034 scope/design/freeze authority document; any M035 material. Verified directly: `git status --short` shows only the five files in Section 30.

## 32. Known Limitations

1. **PostgreSQL integration evidence is unexecuted in this environment** (Section 24) — no accessible live database. This is the primary open item for independent review to resolve (run the suite in an environment with real PostgreSQL access) before implementation can be considered fully evidenced.
2. The `mypy --explicit-package-bases` per-file invocation against the new test files reports 4 "unused type: ignore" findings that do not occur under the canonical project mypy configuration; documented in Section 29 as a pre-existing, non-blocking artifact shared with the M031 precedent file.

## 33. Remaining Risks

- Until Section 24's PostgreSQL evidence is executed, the real-database behavior (schema round-trip, `AggregateNotFound` from the real adapter, absence of a `campaign` table query) rests on the frozen M023 adapter's own M023-level evidence plus this milestone's unit-level fakes, not a fresh M034-specific database run.
- No other risk beyond those already accepted at design-freeze (Section 31 of the design freeze document, e.g. deferred read-to-update version acquisition) is introduced by this implementation.

## 34. Review Status

**CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW.** Not approved. Not frozen.

## 35. Next Permitted Action

**MILESTONE-034 INDEPENDENT IMPLEMENTATION REVIEW.**
