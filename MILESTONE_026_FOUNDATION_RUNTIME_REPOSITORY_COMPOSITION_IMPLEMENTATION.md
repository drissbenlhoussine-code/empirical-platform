# MILESTONE-026 - Foundation Runtime Repository Composition Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-026-IMPLEMENTATION |
| Title | Foundation Runtime Repository Composition Implementation |
| Status | IMPLEMENTATION COMPLETE - READY FOR INDEPENDENT REVIEW |
| Frozen design | `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_DESIGN.md` (Version 1.1) |
| Design freeze | `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_DESIGN_FREEZE.md` |

## 2. Scope

Extends the existing `FoundationRuntime` process-startup composition root and
its `initialize_infrastructure_runtime`/`initialize_foundation_runtime_with_postgresql`
functions to construct and expose exactly one frozen M025
`PostgresRepositoryRuntime`, gated by an `isinstance` check against the
persistence service instance actually in use. No M020-M025 contract changed.
No application services, retry policy, APIs, workers, or MILESTONE-027 work.

## 3. Files Changed

| File | Change |
| --- | --- |
| `src/empirical_platform/shared/bootstrap.py` | One new import, one new dataclass field, conditional construction in two functions |
| `tests/unit/test_m026_bootstrap_repository_runtime.py` | New — 17 unit tests |
| `tests/integration/test_m026_foundation_runtime_repository_composition.py` | New — 5 real-PostgreSQL integration tests |
| `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_IMPLEMENTATION_SCOPE.md` | New |
| `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_IMPLEMENTATION.md` | New (this document) |
| `PROJECT_CHECKPOINT.md` | Updated (checkpoint-content-baseline semantics) |

No M020 Repository Protocol, M021 mapper contract, M022 schema/migration,
M023 concrete adapter, M024 `run_composed`, or M025 `PostgresRepositoryRuntime`
source file is touched.

## 4. Runtime Construction Graph

Exact frozen field, added immediately after `object_storage`:

```python
repository_runtime: PostgresRepositoryRuntime | None = None
```

Construction sites, exactly as frozen (Design Section 8):

- `initialize_infrastructure_runtime`: constructed immediately after
  `_require_dependency_ready(persistence_service, layer="persistence")`
  succeeds and before `object_storage_service` construction begins.
- `initialize_foundation_runtime_with_postgresql`: constructed immediately
  after `persistence_service.initialize()`.
- `initialize_foundation_runtime` and
  `initialize_foundation_runtime_with_object_storage`: unchanged; neither
  constructs persistence, so `repository_runtime` stays at its dataclass
  default of `None`.

Both construction sites use the identical frozen expression:

```python
repository_runtime = (
    PostgresRepositoryRuntime(persistence_service)
    if isinstance(persistence_service, PostgresPersistenceService)
    else None
)
```

## 5. Public API

No new public method on `FoundationRuntime`. `repository_runtime` is a plain,
`Optional`-typed dataclass field, consumed exactly as M025 froze
`PostgresRepositoryRuntime`'s own public surface
(`campaigns`/`runs`/`evidence_packages`/`reviews`/`run_composed`/`close`). No
repository shortcut, service locator, or global runtime was added to
`FoundationRuntime`.

## 6. Same-Service Identity

`repository_runtime._service is runtime.persistence` holds for every
non-`None` construction, proven directly in both the unit tests (SQLite
engine override) and the integration tests (real PostgreSQL) — see Section
10. No second `PostgresPersistenceService` instance is ever created by this
milestone.

## 7. Conditional Construction and Fake Compatibility

The `isinstance(persistence_service, PostgresPersistenceService)` guard is
false for every `FakePersistenceService`-based override (proven directly:
`FakePersistenceService` is a standalone `@dataclass`, not a
`PostgresPersistenceService` subclass) and true for every real
`PostgresPersistenceService` instance or subclass. All 17 pre-existing tests
in `tests/unit/test_bootstrap.py`, `tests/unit/test_persistence_bootstrap.py`,
`tests/unit/test_infrastructure_runtime.py`, and
`tests/unit/test_object_storage_bootstrap.py` pass unmodified (Section 10).

## 8. Failure and Cleanup Semantics

- Persistence initialization/readiness failure: `repository_runtime` is
  never constructed; existing cleanup/exception behavior unchanged.
- Later-step failure after construction (object-storage
  construction/initialization/readiness, or health aggregation, inside
  `initialize_infrastructure_runtime`): no `FoundationRuntime` is returned;
  the discarded local `repository_runtime` receives no separate cleanup call;
  the existing `initialized`-resource cleanup path closes `persistence` (and
  `object_storage`, if constructed) exactly as before; no double close; no
  global or cached partial state remains. Proven directly by
  `test_object_storage_failure_after_repository_runtime_construction_returns_no_runtime`
  and
  `test_health_aggregation_failure_after_repository_runtime_construction_returns_no_runtime`.
- An injected `PostgresRepositoryRuntime` constructor failure (structurally
  unreachable under the frozen design once the `isinstance` guard has passed,
  but exercised defensively) still results in no runtime returned and the
  existing persistence cleanup executing, proven by
  `test_injected_repository_runtime_constructor_failure_returns_no_runtime_and_cleans_up`.

## 9. Close/Post-Close Semantics

`FoundationRuntime.close()`'s cleanup list is unmodified —
`[("object_storage", ...), ("persistence", ...)]` — with no new entry for
`repository_runtime`. Proven directly:
`test_close_does_not_separately_close_repository_runtime` spies on
`PostgresRepositoryRuntime.close` and asserts it is never called by
`FoundationRuntime.close()`. After `close()`, `repository_runtime` remains a
non-`None`, stable reference; further operations through it (e.g.
`run_composed`) fail via the existing, unmodified
`PostgresPersistenceService._ensure_can_work` closed-service guard — proven
by `test_repository_runtime_operations_fail_after_close` (unit) and
`test_close_makes_repository_operations_fail_safely` (real PostgreSQL).

## 10. Tests Added

**Unit** (`tests/unit/test_m026_bootstrap_repository_runtime.py`,
17 tests, SQLite-backed real `PostgresPersistenceService` instances via the
constructor's existing `engine=` override — mirroring the
`tests/unit/test_m025_repository_runtime.py` pattern):

- foundation field default/manual-construction compatibility (2);
- real-service construction paths for both functions, ordering, and
  exactly-once construction via a call-count spy on
  `bootstrap.PostgresRepositoryRuntime` (3);
- fake/non-Postgres paths leaving `repository_runtime` as `None` for both
  functions, the bare function, and the object-storage-only function, with an
  explicit zero-call-count assertion (4);
- failure paths: persistence initialization failure, persistence readiness
  failure, injected repository-runtime constructor failure, object-storage
  failure after construction, health-aggregation failure after construction
  (5);
- close/post-close behavior: no separate `repository_runtime.close()` call,
  post-close operations fail through the closed-service guard (2);
- repr/credential-safety: a unique secret marker embedded in a real
  `PostgreSQLConfigSnapshot` password is proven absent from
  `repr(runtime)`, `repr(runtime.repository_runtime)`, and `repr()` of all
  four repository adapter properties, alongside an assertion that the full
  rendered SQLAlchemy URL (with the real password) never appears either (1).

All 17 pass; combined with the 40 pre-existing bootstrap/M025 unit tests
(`test_bootstrap.py`, `test_persistence_bootstrap.py`,
`test_infrastructure_runtime.py`, `test_object_storage_bootstrap.py`,
`test_m025_repository_runtime.py`), 57/57 pass with zero modification to any
pre-existing test file.

**Integration**
(`tests/integration/test_m026_foundation_runtime_repository_composition.py`,
5 tests, opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, real PostgreSQL,
never mocked):

- `initialize_foundation_runtime_with_postgresql` produces a working
  `repository_runtime` (same-service identity, standalone campaign add/get);
- `initialize_infrastructure_runtime` produces a working `repository_runtime`
  (real PostgreSQL persistence, `FakeObjectStorageService` for the orthogonal
  object-storage dependency — M026 does not touch object storage, so no
  MinIO/S3 dependency is required to exercise the repository-composition
  path);
- same-root `run_composed` commits two aggregates (Campaign, Run) atomically
  through the bootstrap-composed runtime;
- `close()` makes both `add` and `get` fail through the existing closed-service
  guard;
- repr/credential safety against a genuine, live-connected
  `PostgresPersistenceService`: the real configured password is proven absent
  from every repr checked.

## 11. PostgreSQL Evidence Detail

Fresh, disposable PostgreSQL 16.10 instance (self-generated `secrets.token_hex(16)`
password, `initdb`/`pg_ctl`-managed on an unused port, migrated via
`alembic upgrade head` to the unchanged, frozen M022 schema — 13 relations
including `alembic_version`), torn down with `pg_ctl stop -m fast` and full
data-directory removal after use.

Combined M022-M026 real-PostgreSQL regression, single run against one
instance:

| Suite | Passed |
| --- | --- |
| `test_m022_schema_migration.py` | 49 |
| `test_m023_postgres_repositories.py` | 26 |
| `test_m024_postgres_composed_unit_of_work.py` | 12 |
| `test_m025_postgres_repository_runtime.py` | 9 |
| `test_m026_foundation_runtime_repository_composition.py` | 5 |
| **Total** | **101** |

No new table, migration revision, or schema change was introduced by M026 —
verified by `git diff --name-status` showing no file under `migrations/`
changed, and by the same 13-relation schema serving all five suites above
unmodified.

## 12. Architecture and Security

- `tools/check_architecture.py .` — 0 violations. `bootstrap.py`'s new
  import (`persistence.postgres_repositories.runtime`) is the identical
  same-top-level-module (`shared`) import class already used for
  `PostgresPersistenceService`; no `ALLOWED`/`FORBIDDEN` table change
  required.
- No domain package (`campaign`/`run`/`evidence`/`review`) imports the new
  field or `PostgresRepositoryRuntime`.
- No import cycle: `bootstrap.py` depends on
  `postgres_repositories/runtime.py`, never the reverse.
- No global mutable runtime, service locator, or module-level singleton was
  introduced.
- Secret scan (`scripts/security.ps1`): clean, 267 targets (Section 13).
- Repr/credential safety: verified both via direct source inspection (no
  custom `__repr__`/`__str__` on `PostgresPersistenceService`,
  `PostgresRepositoryRuntime`, or any of the four repository adapters) and
  via passing regression tests using real secret markers, in both the
  SQLite-backed unit test and the live-PostgreSQL integration test (Section
  10).

## 13. Full Validation Loop

| Gate | Result |
| --- | --- |
| Python | 3.13.14 |
| `python -m compileall -q src tests tools migrations` | PASS |
| `ruff format --check .` / `ruff check .` | PASS |
| `mypy` | PASS, 0 issues, 80 source files |
| `scripts/security.ps1` | PASS — pip-audit clean, secret scan 267 targets |
| `scripts/verify.ps1` | PASS — see exact counts in the implementation commit's final validation run |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS (sdist + wheel) |
| `git diff --check` | PASS |
| M026 unit tests | PASS — 17/17 |
| M026 real-PostgreSQL integration tests | PASS — 5/5 |
| Combined M022-M026 real-PostgreSQL regression | PASS — 101/101 |

## 14. Hostile Self-Review

1. **Wrong service identity?** No — both construction sites pass the exact
   `persistence_service` local variable already stored on
   `FoundationRuntime.persistence`; proven by an `is`-identity assertion in
   both unit and integration tests.
2. **Duplicate persistence service?** No — no second
   `PostgresPersistenceService` is constructed anywhere in this milestone.
3. **Repository runtime constructed for a fake service?** No —
   `test_infrastructure_runtime_leaves_repository_runtime_none_for_fake_persistence`
   and its `with_postgresql` counterpart assert a zero call-count on
   `PostgresRepositoryRuntime` via a spy, not merely a `None` result.
4. **Missing construction site?** No — all four `initialize_*` functions are
   covered by the bootstrap matrix (Design Section 8) and exercised by tests.
5. **Construction before initialization?** No — both construction sites are
   placed strictly after the existing `persistence_service.initialize()`
   (and, in `initialize_infrastructure_runtime`, after
   `_require_dependency_ready`) calls; proven by event-ordering assertions in
   `RecordingPostgresPersistenceService`-based tests.
6. **Partial bootstrap leak?** No — the failure-path tests (Section 8 above)
   prove no `FoundationRuntime` is ever returned or cached on any failure
   branch, and that the discarded `repository_runtime` local triggers no
   separate cleanup call.
7. **Double close?** No —
   `test_close_does_not_separately_close_repository_runtime` spies on
   `PostgresRepositoryRuntime.close` directly and asserts it is never called.
8. **Separate repository-runtime ownership?** No — `repository_runtime`
   holds no resource independent of `persistence`; closing `persistence`
   alone (the existing, unmodified cleanup entry) fully disposes of
   everything `repository_runtime` depends on.
9. **Unstable optionality behavior?** No — the field is `Optional`,
   `mypy`-checked, and its `None`/non-`None` behavior per function is fully
   enumerated and tested (Design Section 8 table; Section 10 above).
10. **Repr/credential leakage?** No — proven by direct source inspection
    (no custom repr anywhere in the object graph) and by passing secret-marker
    regression tests against both a SQLite-backed and a live PostgreSQL
    service.
11. **Global publication?** No — no module-level global, `ContextVar`, or
    singleton was introduced; `repository_runtime` lives only on the
    `FoundationRuntime` instance that owns it.
12. **Application-service leakage?** No — `FoundationRuntime` never calls a
    repository method or `run_composed` itself; it only holds and exposes the
    object, exactly as it already does for `persistence`/`object_storage`.
13. **Retry leakage?** No — no retry logic was introduced anywhere.
14. **M027 leakage?** No — nothing in this implementation presumes or wires
    any named future milestone; scope is exactly the frozen Design's Sections
    3-26.

No genuine finding required a correction; no source, test, or documentation
change resulted from this pass beyond what Sections 4-13 already describe.

## 15. Deferred Work

Application service orchestration, retry-on-`OptimisticConcurrencyConflict`
policy, APIs, workers, Audit runtime, Decision Candidate, Decision Freeze,
market-data/vendor/trading/campaign execution behavior, and any
MILESTONE-027 work — all unchanged from the frozen Design's Section 19/20
deferred list.

## 16. Final Status

```text
M026 FOUNDATION RUNTIME REPOSITORY COMPOSITION IMPLEMENTATION COMPLETE
READY FOR INDEPENDENT REVIEW
NOT APPROVED
NOT FROZEN
M027 NOT STARTED
```

## 17. Post-Freeze Correction — Resource-Lifecycle Defect in `initialize_foundation_runtime_with_postgresql` / `initialize_foundation_runtime_with_object_storage`

Identified during MILESTONE-052 exploratory architecture review (unrelated scope), reported against this already-frozen milestone, and independently reproduced before correction.

**Finding.** Item 5 of the Section 14 hostile self-audit above checked construction *ordering* relative to `initialize()` and found no defect, but never checked whether `close()` runs when `initialize()` itself raises. It does not, in two of `bootstrap.py`'s four `initialize_*` functions:

- `initialize_foundation_runtime_with_postgresql`: `persistence_service = persistence or PostgresPersistenceService(config.postgresql)` followed immediately by `persistence_service.initialize()`, with no surrounding `try`/`except`/`finally`. If `initialize()` raises (e.g. unreachable/misconfigured database), the constructed service is never closed.
- `initialize_foundation_runtime_with_object_storage`: the identical pattern with `object_storage_service`.

(`initialize_infrastructure_runtime`, the third `initialize_*` function that constructs a persistence/object-storage service, already wraps its whole body in `try`/`except Exception` with `_cleanup_initialized` on the failure path — it does not have this defect. `initialize_foundation_runtime` constructs no persistence or object-storage service at all and is unaffected.)

This is the same defect class as finding M050-Y-1 (`MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_IMPLEMENTATION.md` Section 12): a constructed resource is not closed when its own `initialize()` fails. Reproduced independently with `FakePersistenceService(reachable=False)` / `FakeObjectStorageService(reachable=False)`: both `initialize_foundation_runtime_with_postgresql` and `initialize_foundation_runtime_with_object_storage` raised the expected `FoundationError` while leaving `close()` uncalled.

**Practical impact: none in production today.** No production entrypoint (`health.py`, `version.py`, `get_campaign.py`, `cancel_campaign.py`) invokes any `bootstrap.py` `initialize_*` function — only test modules do (`test_bootstrap.py`, `test_m026_bootstrap_repository_runtime.py`, `test_persistence_bootstrap.py`, `test_object_storage_bootstrap.py`, `test_unified_infrastructure_runtime.py`). The leak has zero live consequence unless `bootstrap.py` is wired into a real long-running entrypoint in the future.

**Correction applied.** In both functions, `initialize()` was moved inside a `try` block whose `except Exception` branch calls the service's `close()` before re-raising — the same pattern `initialize_infrastructure_runtime` already used correctly for its (list-based, multi-resource) case, applied here to the single-resource case. This differs in shape from the M050-Y-1 `try`/`finally` fix: `get_campaign.py`'s service is closed unconditionally because ownership never leaves the function, whereas here a successful `initialize()` hands the service to the returned `FoundationRuntime`, whose caller owns its lifecycle via `FoundationRuntime.close()` — so `close()` must fire only on the failure path, not on success. No context manager, resource-manager framework, or new exception policy was introduced.

**Verification.**

1. *Pre-fix reproduction*: a temporarily-restored pre-correction copy of `bootstrap.py`, run against both new regression tests below, confirmed both fail (`close_calls == []` / `persistence.closed is False`) against the original source.
2. *Post-fix confirmation*: the corrected source, run against the same two tests, passes.
3. *Regression tests added*: `tests/unit/test_persistence_bootstrap.py::test_bootstrap_with_unreachable_persistence_closes_service_on_failure` and `tests/unit/test_object_storage_bootstrap.py::test_bootstrap_with_unreachable_object_storage_closes_service_on_failure`.
4. Full unit suite: `805 passed` (up from 803), zero regression.

**Scope discipline.** This is a narrow correction to already-frozen M026 source, not a new milestone: it changes no scope, design, or public contract of `FoundationRuntime`; it is mechanically identical in kind to the already-precedented M050-Y-1 fix; and the affected code path has no live production caller. `M026_STATUS` remains `APPROVED_AND_FROZEN`; no MILESTONE-052 material is introduced by this correction.
