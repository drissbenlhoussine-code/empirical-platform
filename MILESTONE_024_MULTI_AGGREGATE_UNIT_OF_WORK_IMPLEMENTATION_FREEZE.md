# MILESTONE-024 - Multi-Aggregate Persistence Unit of Work Implementation Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-024-IMPLEMENTATION-FREEZE |
| Title | Multi-Aggregate Persistence Unit of Work Implementation Freeze |
| Version | 1.0 |
| Status | M024 APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Freeze closure only |
| New source code, tests, or runtime changes made during this closure | No |

## 2. Authority Chain

| Role | Commit | Summary |
| --- | --- | --- |
| Initial Design | `f2a22817cb433142960dba6509c50b4b39066ebe` | Design MILESTONE-024 Multi-Aggregate Persistence Unit of Work |
| Design Correction | `03d640fa8e0f34fb3348226c4bc0eeaa386832b4` | Harden MILESTONE-024 multi-aggregate unit of work design |
| Design Freeze | `ed0a4198dab515c4d204f3046ea2cfc114390bef` | chore: freeze MILESTONE-024 multi-aggregate unit of work design |
| Implementation | `5fd00247bdb25b01a4f5de831b5b9baa483af6a5` | feat: implement M024 multi-aggregate unit of work |
| Narrow Correction | `9f8bb60507f52ee410f1fd3010ad11641884f329` | fix: harden M024 composed scope entry cleanup |

Authoritative documents for this freeze:

- `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_SCOPE_SELECTION.md`;
- `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_DESIGN.md` (Version 1.1);
- `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_DESIGN_FREEZE.md`;
- `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_IMPLEMENTATION_SCOPE.md`;
- `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_IMPLEMENTATION.md` (Version 1.1);
- `external-review/M024_MULTI_AGGREGATE_UNIT_OF_WORK_IMPLEMENTATION/`;
- `external-review/M024_MULTI_AGGREGATE_UNIT_OF_WORK_IMPLEMENTATION.zip` (SHA-256 `4f4a69150fa12902ba03ca5fa74124df8104998402c0ae1d436d8d8e3ab1a1d6`).

Frozen baseline this implementation built on: MILESTONE-023 implementation freeze commit `4ce800d3609ba7c621eadffc338bc5bc2503228d`, plus MILESTONE-024 design freeze commit `ed0a4198dab515c4d204f3046ea2cfc114390bef`. None are reopened, rewritten, or reinterpreted by this freeze.

## 3. Independent Review Outcome

The M024 implementation went through one implementation review round and one narrow correction round:

1. Initial implementation commit `5fd00247bdb25b01a4f5de831b5b9baa483af6a5` implemented the frozen design's private composed-transaction machinery and its public `PostgresPersistenceService.run_composed(operations)` entry point.
2. Independent hostile review found one MAJOR implementation defect (`M024-IMPL-REVIEW-0001`): after the real `PostgresUnitOfWork` entered successfully, ambient scope construction or `_active_composed_scope.set(...)` could fail before `_ComposedTransaction.__enter__` returned, leaving no guaranteed rollback/close/reset path because Python does not call `__exit__` when `__enter__` itself raises.
3. Correction commit `9f8bb60507f52ee410f1fd3010ad11641884f329` resolved the defect by wrapping active-scope construction and publication in a `try`/`except` that calls the existing real `unit_of_work.rollback()` cleanup path before re-raising. It also corrected post-commit governance/package truth (`M024-IMPL-REVIEW-0002`) and removed non-blocking SQLite `ResourceWarning`s from the focused unit-test fixture (`M024-IMPL-REVIEW-0003`).
4. Final independent re-review returned:

```text
M024 IMPLEMENTATION APPROVED FOR OWNER FREEZE
```

The Project Owner accepted that recommendation and authorized this implementation freeze closure.

## 4. What Was Frozen

This freeze covers exactly the M024 multi-aggregate persistence Unit of Work implementation:

- `_ComposedScopeState`, `_ActiveComposedScope`, `_active_composed_scope`, `_JoinedUnitOfWork`, and `_ComposedTransaction` in `src/empirical_platform/shared/persistence/postgres.py`;
- `PostgresPersistenceService.unit_of_work() -> PersistenceUnitOfWork`, including the same-service join branch while a composed scope is active;
- `PostgresPersistenceService.run_composed(operations: Sequence[Callable[[], object]]) -> tuple[object, ...]`;
- atomic multi-repository execution over one real `PostgresUnitOfWork`;
- owner-service isolation, cross-service rejection, same-identity transaction visibility, poisoned-scope rollback, official result tuple only after commit, token-based ContextVar reset, and partial-entry cleanup for ambient-scope publication failure;
- 22 focused unit tests covering public API, same-service join, cross-service rejection, nesting, poisoned-scope semantics, ContextVar cleanup, partial-entry cleanup, no callback execution, no result tuple on failed entry, and cleanup-failure precedence;
- 12 real-PostgreSQL M024 integration tests using the frozen M023 Campaign and Run repository adapters;
- unchanged M022/M023 real-PostgreSQL regression behavior.

## 5. Final Validation Evidence

Captured fresh as part of this freeze closure:

| Gate | Result |
| --- | --- |
| Python | 3.13.14 (`.venv`) |
| `python -m compileall -q src tests tools migrations` | PASS |
| `ruff format --check .` / `ruff check .` | PASS (152 files formatted, 0 lint issues) |
| `mypy` | PASS, 0 issues, 79 source files |
| `scripts/security.ps1` | PASS (pip-audit clean; secret scan 255 targets, 0 findings) |
| `scripts/verify.ps1` (fresh, end-to-end) | PASS - `366 passed, 96 skipped`, coverage `82.15%` |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS (sdist + wheel) |
| `git diff --check` | PASS |
| M024 focused unit tests with `-W error::ResourceWarning --no-cov` | PASS - 22/22 passed |
| M024 real PostgreSQL integration tests | PASS - 12/12 passed |
| M024 + M023 + M022 real PostgreSQL regression tests | PASS - 87/87 passed |

Real PostgreSQL validation used a fresh disposable Docker Compose PostgreSQL `17.10` instance, migrated with `alembic upgrade head`, then torn down with `docker compose down -v --remove-orphans`.

## 6. Accepted Non-Blocking Observations

Carried forward explicitly, not silently:

1. Focused subset pytest runs require `--no-cov` when the project-wide coverage fail-under is not meaningful for a single test file; the tests themselves pass without failures.
2. PostgreSQL integration tests remain opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`.
3. `mypy` does not type-check `tests/` under the current project configuration.
4. `setuptools` emits a non-blocking `project.license` TOML-table deprecation warning during `python -m build`; the warning remains tracked for a future packaging metadata cleanup before the upstream deadline.
5. Retry-on-`OptimisticConcurrencyConflict` remains application-owned. M024 introduces no retry policy.
6. Repository runtime composition and application-service orchestration remain deferred; M024 only provides the low-level persistence composition primitive.

## 7. What This Freeze Does Not Authorize

Freezing M024 does not authorize:

- repository runtime composition or a repository provider/factory;
- application services, use-case orchestration, APIs, or workers;
- automatic retry policy;
- new schema, table, migration, mapper, or repository adapter behavior;
- Audit runtime, Decision Candidate, or Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- any MILESTONE-025 implementation.

## 8. Final Status

```text
M024 APPROVED AND FROZEN
```

No frozen historical MILESTONE-024 document is rewritten by this closure; this document only records the owner-approved implementation freeze decision on top of the reviewed lineage.
