# MILESTONE-025 - Repository Runtime Composition Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-025-IMPL |
| Title | Repository Runtime Composition Implementation |
| Version | 1.0 |
| Status | IMPLEMENTATION COMPLETE — NOT APPROVED — NOT FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen design baseline | `fe4f04483cb5fdc6b5cf08e0fe0eeebbe4e827ad` (M025 DESIGN APPROVED AND FROZEN) |
| Implementation scope record | `MILESTONE_025_REPOSITORY_RUNTIME_COMPOSITION_IMPLEMENTATION_SCOPE.md` |

## 2. Scope

Exactly the frozen Design's Sections 5-14 (see Implementation Scope record Section 4). No M020 Protocol change, no M021 mapper change, no M022 schema change, no M023 adapter change, no M024 transaction-semantics change, no application service, no MILESTONE-026 work.

## 3. Files Changed

| File | Change |
| --- | --- |
| `src/empirical_platform/shared/persistence/postgres_repositories/runtime.py` | New. `PostgresRepositoryRuntime` class, matching Design Section 7's frozen constructor and public surface verbatim. |
| `tests/unit/test_m025_repository_runtime.py` | New. 23 SQLite-backed mechanism-level unit tests. |
| `tests/integration/test_m025_postgres_repository_runtime.py` | New. 9 real-PostgreSQL tests using the actual frozen M023 repository adapters and M024 `run_composed`. |
| `MILESTONE_025_REPOSITORY_RUNTIME_COMPOSITION_IMPLEMENTATION_SCOPE.md` | New. |
| `MILESTONE_025_REPOSITORY_RUNTIME_COMPOSITION_IMPLEMENTATION.md` | New (this document). |

No file under `src/empirical_platform/{campaign,run,evidence,review}/`, no existing file under `src/empirical_platform/shared/persistence/postgres_repositories/` (the four M023 adapters, `postgres.py`, `_errors.py`, `__init__.py`), and no migration file was touched. `postgres_repositories/__init__.py` was deliberately left unchanged, matching the established convention that none of the four existing repository adapters are re-exported there either — every consumer imports `PostgresRepositoryRuntime` directly from `runtime.py`, exactly as the four adapters are imported from their own submodules today.

## 4. Runtime Construction Graph

Implemented exactly as frozen in Design Section 7:

```python
class PostgresRepositoryRuntime:
    __slots__ = ("_service", "_campaigns", "_runs", "_evidence_packages", "_reviews")

    def __init__(self, service: PostgresPersistenceService) -> None:
        if not isinstance(service, PostgresPersistenceService):
            raise TypeError(
                "PostgresRepositoryRuntime requires a PostgresPersistenceService instance"
            )
        self._service = service
        self._campaigns = PostgresCampaignRepository(service)
        self._runs = PostgresRunRepository(service)
        self._evidence_packages = PostgresEvidencePackageRepository(service)
        self._reviews = PostgresReviewRepository(service)
```

`__slots__` is used (an addition beyond the design's illustrative pseudocode, not a deviation from any frozen requirement) purely to keep the object lightweight and to guarantee no attribute can be added outside the five frozen ones — consistent with Design Section 8's closed ownership list. Validation is the constructor's first statement; no repository is constructed until it passes. Since all four M023 adapter constructors are confirmed non-fallible (plain reference assignment, no I/O), no partial-construction cleanup path is needed beyond the type check itself — proven by `test_constructor_validation_happens_before_repository_construction`, which counts `PostgresCampaignRepository.__init__` invocations and confirms zero occur when validation rejects the `service` argument.

## 5. Public API

Exactly the four typed properties, `run_composed`, and `close()` frozen in Design Section 7 — no additions, no context-manager protocol, no public service accessor, no generic repository lookup:

```python
@property
def campaigns(self) -> PostgresCampaignRepository: ...
@property
def runs(self) -> PostgresRunRepository: ...
@property
def evidence_packages(self) -> PostgresEvidencePackageRepository: ...
@property
def reviews(self) -> PostgresReviewRepository: ...

def run_composed(self, operations: Sequence[Callable[[], object]]) -> tuple[object, ...]:
    return self._service.run_composed(operations)

def close(self) -> None:
    self._service.close()
```

Confirmed by `test_runtime_has_no_context_manager_protocol` and `test_runtime_has_no_generic_repository_lookup_or_public_service_locator` (both assert `hasattr` is `False` for `__enter__`, `__exit__`, `get_repository`, `service`, `persistence_service`).

## 6. Stable Identity

Since the four repository attributes are assigned exactly once, at `__init__`, to plain read-only `@property` accessors with no reconstruction logic, repeated access is trivially identity-stable. Proven directly: `test_repeated_property_access_returns_identical_object` and `test_identity_remains_stable_after_close` (identity survives `close()`, since closing never touches the stored attributes — only the underlying service's own state changes). `test_each_repository_is_constructed_exactly_once` additionally counts constructor invocations across repeated property access to prove no lazy reconstruction path exists, even in principle.

## 7. Service Validation and Readiness

`TypeError` is raised for `None` or any non-`PostgresPersistenceService` value, exactly as frozen. No readiness check, no `initialize()` call, no connectivity probe, no migration is performed by the runtime — confirmed by `test_construction_does_not_initialize_an_uninitialized_service` (construction against a never-initialized service succeeds without error) and `test_uninitialized_service_fails_on_first_repository_operation` / `test_uninitialized_service_fails_on_run_composed` (the first real operation raises the existing, unmodified `FoundationError("Persistence service is not initialized")` via `_ensure_can_work`, not a new error). The equivalent closed-service pair (`test_closed_service_fails_on_first_repository_operation` / `test_closed_service_fails_on_run_composed`) confirms the same for a closed service.

## 8. Close/Post-Close Semantics

`close()` delegates exactly once to `self._service.close()`. Idempotence is inherited entirely from the service's own existing idempotent `close()` — proven by `test_repeated_close_is_idempotent`. Repository property identity survives `close()` (Section 6); attempting an actual operation afterward fails through the same existing guard used for the uninitialized case, confirmed against real PostgreSQL by `test_repository_operation_after_close_fails_through_existing_guard` and `test_run_composed_after_close_fails_through_existing_guard`.

## 9. Independent Roots

Proven both at the unit level (SQLite, `test_two_independent_roots_coexist_with_distinct_services`, `test_closing_one_root_leaves_the_other_independent_root_usable`, `test_cross_root_repository_rejected_from_joining_a_different_roots_composed_scope`) and against real PostgreSQL (`test_two_independent_roots_operate_against_the_same_database_without_interference`, `test_closing_one_root_leaves_a_second_independent_root_operational`, `test_cross_root_repositories_rejected_from_one_composed_transaction`): two `PostgresRepositoryRuntime` instances over distinct `PostgresPersistenceService` objects coexist without interference; closing one has no effect on the other; a repository from one root's service cannot join another root's `run_composed` call — rejected entirely by the existing, unmodified M024 same-service-identity rule (`scope.owner_service is self`), with no new rejection mechanism added.

## 10. Tests Added

### 10.1 Unit Tests (`tests/unit/test_m025_repository_runtime.py`, 23 tests, SQLite, no real database)

Constructor validation (`None`, wrong type, validation-before-construction), construction graph (correct types, exactly-once construction, correct mapper defaults, same service identity), stable identity (repeated access, post-close), public API surface (no context manager, no generic lookup/service locator, `run_composed`/`close` delegation counted), readiness precondition (no initialize, uninitialized/closed first-use failure), and independent roots (coexistence, independent closing, cross-root rejection). **23/23 passed**, zero `ResourceWarning`s.

### 10.2 Real PostgreSQL Integration Tests (`tests/integration/test_m025_postgres_repository_runtime.py`, 9 tests)

Using the actual, frozen M023 repository adapters and M024 `run_composed`, against a real, migrated, disposable PostgreSQL 16.13 instance: construction from one initialized service; standalone add/get through all four exposed properties (Campaign, Run, EvidencePackage, Review); cross-aggregate atomic `run_composed` commit and rollback delegated through the runtime; two independent roots operating against the same database without interference; closing one root leaving a second operational; cross-root rejection under the existing M024 rule; post-close repository and `run_composed` failure through the existing guard. **9/9 passed.**

### 10.3 Full Regression

- `tests/unit`, `tests/contract`, `tests/architecture`: **389 passed**, coverage 82.60% (subset run);
- Full `tests/` tree including all integration suites, run against the same fresh disposable PostgreSQL instance: **488 passed, 6 skipped** (the 6 skipped belong to unrelated MinIO/other opt-in suites, not M020-M025), coverage 91.57%;
- `tests/integration/test_m022_schema_migration.py` (49 tests), `tests/integration/test_m023_postgres_repositories.py` (26 tests), `tests/integration/test_m024_postgres_composed_unit_of_work.py` (12 tests), run in the same session as the new M025 suite, **unmodified**: all passed, proving zero regression in any M022/M023/M024 behavior.

## 11. PostgreSQL Evidence Detail

| Item | Value |
| --- | --- |
| PostgreSQL version | 16.13 (Windows build) |
| Instance | Fresh, disposable, self-generated md5 credentials, data directory under the user profile, initialized via `initdb`, started via `pg_ctl`, migrated via `alembic upgrade head`, torn down via `pg_ctl stop -m fast` and directory removal after the run |
| M025 integration tests | 9/9 passed |
| M024 integration tests (regression) | 12/12 passed |
| M023 integration tests (regression) | 26/26 passed |
| M022 integration tests (regression) | 49/49 passed |
| Combined single run | 99 passed, 6 skipped (unrelated suites) across the full `tests/integration/` tree |
| Cross-aggregate atomic commit (via runtime) | Proven |
| Cross-aggregate atomic rollback (via runtime) | Proven |
| Independent-root coexistence | Proven |
| Independent-root closing | Proven |
| Cross-root rejection | Proven |
| Post-close behavior | Proven |
| Teardown | Clean (`pg_ctl stop -m fast`, data directory removed) |

## 12. Architecture and Security

`tools/check_architecture.py .` — **0 violations**. Verified directly against the tool's own source that zero changes were required: same-top-level-module (`shared`) imports are unconditionally exempt from the `ALLOWED` boundary check outside `shared/domain/` (`check_architecture.py` line 121-122), so `runtime.py` importing `postgres.py` and the four repository submodules needed no rule change, and no domain package (`campaign`/`run`/`evidence`/`review`) can import it either, per the existing, unmodified `FORBIDDEN_IMPORT_PREFIXES` entries for those packages.

`scripts/security.ps1` — **PASS**: 0 known vulnerabilities (`pip-audit`), secret scan target count 261, 0 findings. `PostgresRepositoryRuntime` defines no custom `__repr__`/`__str__`; verified directly that both fall back to the default `object.__repr__` (class name + memory address only), so no credential can leak through it even in the worst case — confirmed by an explicit smoke test constructing a service with a real-looking secret password and asserting it never appears in `repr()`/`str()` of the runtime.

## 13. Full Validation Loop

| Gate | Result |
| --- | --- |
| Python | 3.13.14 (`.venv`) |
| `python -m compileall -q src tests tools migrations` | PASS |
| `ruff format --check .` / `ruff check .` | PASS |
| `mypy` (default config, 80 source files) | PASS, 0 issues |
| `scripts/security.ps1` | PASS — 0 known vulnerabilities, secret scan target count 261, 0 findings |
| `scripts/verify.ps1` (fresh, end-to-end) | PASS |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS |
| `git diff --check` | PASS |

## 14. Hostile Self-Review

Attacked for every failure mode named in the mission's Phase 12, against the actual implementation and its test evidence (Section 10):

1. **Lazy repository construction** — checked: all four repositories are assigned in `__init__`; properties are plain reads with no reconstruction logic; proven by counting constructor invocations across repeated access. No defect.
2. **Wrong mapper/repository pairing** — checked: `runtime.campaigns._mapper` is `ConcreteCampaignMapper` (and the equivalent for the other three), proven directly against the real M023 default-mapper wiring, unmodified by this implementation. No defect.
3. **Mismatched service identity** — checked: the single `service` constructor parameter is passed verbatim to all four repository constructors, with no second code path; proven by asserting `._service is service` for all four. No defect.
4. **Accidental second service** — checked: no code path constructs a second `PostgresPersistenceService` anywhere in `runtime.py`. No defect.
5. **Global singleton** — checked: no module-level mutable state exists in `runtime.py`; proven by constructing and using two fully independent roots in the same process. No defect.
6. **Partial constructor state** — checked: validation is the first statement; a rejected `service` argument leaves zero repositories constructed, proven directly. No defect.
7. **Hidden `initialize()`/probe** — checked: `runtime.py` never references `initialize()` or `check()`; proven by constructing against a deliberately uninitialized service and confirming construction succeeds while the first real operation still correctly fails via the existing guard. No defect.
8. **Automatic migration** — checked: no Alembic/migration reference anywhere in `runtime.py`. No defect.
9. **Unstable property identity** — checked: Section 6, proven both before and after `close()`. No defect.
10. **Context-manager invention** — checked: no `__enter__`/`__exit__` defined; proven by `hasattr` assertions. No defect.
11. **Service exposure** — checked: no public `service`/`persistence_service` attribute; proven by `hasattr` assertion; `self._service` is accessed only internally by `run_composed`/`close`. No defect.
12. **Dynamic registry** — checked: no dict/cache/reflection-based lookup exists anywhere in `runtime.py`; the four properties are plain attribute reads. No defect.
13. **Close affecting another root** — checked: proven against real PostgreSQL and at the unit level with two independently-serviced roots; closing one never touches the other's service. No defect.
14. **Cross-root transaction joining** — checked: proven against real PostgreSQL and at the unit level; rejected by the existing, unmodified M024 `scope.owner_service is self` rule, before any SQL executes. No defect.
15. **M024 regression** — checked: 12/12 M024 integration tests and all M024 unit tests pass unmodified in the same session. No defect.
16. **Credential leakage** — checked: Section 12; no custom repr, no leak possible even under a deliberately adversarial smoke test. No defect.
17. **Application-service leakage** — checked: no workflow, orchestration, or cross-aggregate invariant logic exists anywhere in `runtime.py` — it is a plain composition wrapper. No defect.
18. **M026 leakage** — checked: no MILESTONE-026 concept, scope, or code appears anywhere in this implementation. No defect.

No implementation defect was found. Full validation was already fresh (Section 13) at the time this review concluded; no re-run was required.

## 15. Deferred Work

Unchanged from the frozen Design's Section 16: application services, retry-on-optimistic-concurrency policy, bootstrap wiring into an application entrypoint, APIs, workers, query/read-model projections, Audit runtime, Decision Candidate, Decision Freeze, market-data/vendor/trading/campaign execution behavior, and any MILESTONE-026 work all remain out of scope and undone.

## 16. Final Status

```text
M025 REPOSITORY RUNTIME COMPOSITION IMPLEMENTATION COMPLETE — READY FOR INDEPENDENT REVIEW / NOT APPROVED / NOT FROZEN / M026 NOT STARTED
```
