# MILESTONE-024 - Multi-Aggregate Persistence Unit of Work Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-024-IMPL |
| Title | Multi-Aggregate Persistence Unit of Work Implementation |
| Version | 1.1 (narrow correction) |
| Status | IMPLEMENTATION COMPLETE — NOT APPROVED — NOT FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen design baseline | `ed0a4198dab515c4d204f3046ea2cfc114390bef` (M024 DESIGN APPROVED AND FROZEN) |
| Original implementation commit | `5fd00247bdb25b01a4f5de831b5b9baa483af6a5` (`feat: implement M024 multi-aggregate unit of work`) |
| Implementation scope record | `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_IMPLEMENTATION_SCOPE.md` |

Version 1.1 records a narrow correction responding to an independent implementation review's finding `M024-IMPL-REVIEW-0001` (Section 19) and a governance-truth correction (Section 20). No design, public API, M020 Protocol, M023 adapter, or schema change was made. The correction is committed separately from `5fd0024...`; see this repository's own `git log` for the exact correction commit hash rather than a value embedded here, since a document cannot cite the hash of the commit that first carries it without an unbounded self-reference cycle.

## 2. Scope

Exactly the frozen Design's Sections 5-14 (see Implementation Scope record Section 4). No M020 Protocol change, no M023 adapter change, no schema change, no application service, no MILESTONE-025 work.

## 3. Files Changed

### 3.1 Original Implementation (commit `5fd0024`)

| File | Change |
| --- | --- |
| `src/empirical_platform/shared/persistence/postgres.py` | +138 / -3 lines: new imports (`Callable`, `Enum`, `PersistenceUnitOfWork`); `_ComposedScopeState`; `_ActiveComposedScope`; `_active_composed_scope` ContextVar; `_JoinedUnitOfWork`; `_ComposedTransaction`; `unit_of_work()` return-type correction and join branch; new `run_composed()` method. |
| `tests/unit/test_m024_composed_unit_of_work.py` | New. 17 SQLite-backed mechanism-level unit tests. |
| `tests/integration/test_m024_postgres_composed_unit_of_work.py` | New. 12 real-PostgreSQL tests using the actual frozen M023 `PostgresCampaignRepository`/`PostgresRunRepository` adapters. |
| `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_IMPLEMENTATION_SCOPE.md` | New. |
| `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_IMPLEMENTATION.md` | New (this document). |

### 3.2 Narrow Correction (this correction, separate commit)

| File | Change |
| --- | --- |
| `src/empirical_platform/shared/persistence/postgres.py` | `_ComposedTransaction.__enter__` now wraps ambient-scope construction and `ContextVar` publication in a `try`/`except`; on failure, rolls back and closes the already-entered real `PostgresUnitOfWork` before re-raising (Section 19). |
| `tests/unit/test_m024_composed_unit_of_work.py` | 5 new targeted tests proving the cleanup fix (Section 19); fixture teardown now calls `service.close()`/`other_service.close()` to dispose each test's SQLite `StaticPool` connection, eliminating 19 `ResourceWarning`s (Section 21). |
| `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_IMPLEMENTATION.md` | This document, bumped to Version 1.1. |
| `PROJECT_CHECKPOINT.md` | Corrected post-commit governance truth (Section 20). |

No file under `src/empirical_platform/{campaign,run,evidence,review}/` or `src/empirical_platform/shared/persistence/postgres_repositories/` was touched, in either the original implementation or this correction. No migration, no application-service, no API file was added or changed. The public `run_composed` signature and every frozen design decision are unchanged.

## 4. Public API

Exactly one new public method:

```python
def run_composed(self, operations: Sequence[Callable[[], object]]) -> tuple[object, ...]:
```

`operations` is executed sequentially, in the exact order supplied, inside one real PostgreSQL transaction. The returned tuple — in the same order — is constructed only after that transaction has actually committed. On any failure the method raises instead of returning; no partial or intermediate result tuple is ever produced.

`PostgresPersistenceService.unit_of_work()` is corrected to return the `PersistenceUnitOfWork` Protocol type (not the concrete `PostgresUnitOfWork` class), since it can now return either a real `PostgresUnitOfWork` or a `_JoinedUnitOfWork`.

There is no other new public surface. `_ComposedScopeState`, `_ActiveComposedScope`, `_JoinedUnitOfWork`, `_ComposedTransaction`, and `_active_composed_scope` are all private (leading underscore, not exported, never returned to a caller).

## 5. Lifecycle

`run_composed` opens `_ComposedTransaction(self)` as a context manager:

1. `__enter__` constructs a real `PostgresUnitOfWork` **directly** (never via the public `unit_of_work()` factory — see Section 7) and enters it, opening one real SQLAlchemy connection and transaction;
2. wraps it in an `_ActiveComposedScope(owner_service=self, unit_of_work=<real uow>, state=ACTIVE)` and publishes it via `_active_composed_scope.set(...)`, capturing the `Token`;
3. `run_composed`'s own `results = tuple(operation() for operation in operations)` runs entirely inside this open scope;
4. `__exit__` commits once if `exc_type is None` **and** `state is ACTIVE`; otherwise rolls back once, and if no exception was already propagating (the swallowed-failure case), raises a synthetic `FoundationError("Composed transaction poisoned by a failed operation")`;
5. a `finally` block unconditionally resets the ContextVar via the captured `Token`, covering every exit path — successful commit, rollback, or an exception raised by commit/rollback itself.

## 6. Poisoning

`_JoinedUnitOfWork.__exit__(exc_type, exc, tb)` sets `scope.state = POISONED` whenever `exc_type is not None` — this is the **only** place poisoning is triggered, and it requires zero change to any M023 adapter: every one of `get`/`add`/`save` already runs inside `with self._service.unit_of_work() as work:`, and Python's own `with`-statement protocol guarantees `__exit__` receives the propagating exception whenever the adapter's own code raises inside that block, whether the exception is a translated `AggregateAlreadyExists`/`AggregateNotFound`/etc. or a bare `FoundationError`.

Two poisoning scenarios were both implemented and proven, matching Design Section 10 exactly:

- **Exception propagates out of `run_composed`'s own `results = tuple(...)` line** — `_ComposedTransaction.__exit__` sees a real `exc_type`, rolls back, and lets that original exception propagate (no separate synthetic message).
- **Caller swallows the failing operation's exception with its own `try/except`, so nothing propagates out of `results = tuple(...)`** — the scope was already `POISONED` the instant the failing operation's own inner block exited, *before* the exception reached the caller's `try/except`. `_ComposedTransaction.__exit__` sees `exc_type is None` but checks `state` first, takes the rollback branch anyway, and raises the synthetic `FoundationError("Composed transaction poisoned by a failed operation")` itself, so `run_composed` never falls through to constructing a result tuple.

A third, more subtle case is deliberately **not** special-cased, per frozen Design Section 10 row 3: if a *later* operation attempts `execute()` again after the scope is already poisoned by an earlier, swallowed failure, `_JoinedUnitOfWork.execute()` does not pre-flight-block it — it forwards the SQL, and PostgreSQL's own aborted-transaction state (SQLSTATE 25P02) rejects it, which the existing `translate_persistence_error()` wraps into a generic `FoundationError` ("Persistence execute failed in the database driver") uniformly, without a new special-purpose check. The eventual rollback and ContextVar cleanup are unaffected by whether this second, independent failure occurs. This exact scenario is proven against real PostgreSQL in `test_composed_execute_after_poisoning_fails_at_the_database_and_still_rolls_back`.

## 7. Ownership and Cross-Service Safety

`_ActiveComposedScope.owner_service` is compared by Python object identity (`is`), never equality. `unit_of_work()`:

```python
scope = _active_composed_scope.get()
if scope is not None and scope.owner_service is self:
    return _JoinedUnitOfWork(scope)
return PostgresUnitOfWork(self)
```

A different service instance's `unit_of_work()` call falls through to constructing its own `PostgresUnitOfWork`, which is then rejected — before any SQL executes — by the pre-existing, module-level, all-instances-shared `_active_unit_of_work` reentrancy guard, with the same "Nested persistence units of work are not supported" message M023 already froze. No new error message was needed. `_ComposedTransaction.__enter__` constructs `PostgresUnitOfWork` directly rather than through `unit_of_work()` for exactly this reason: calling the public factory from inside the composed scope's own entry would let a *second* composed scope on the *same* service silently join through the new branch instead of raising, since the ambient scope is not yet published at the moment `unit_of_work()` would be called on the owner's behalf.

## 8. Typing

`unit_of_work() -> PersistenceUnitOfWork`, not the concrete `PostgresUnitOfWork`. `mypy` (full project, default config) confirms both `PostgresUnitOfWork` and `_JoinedUnitOfWork` structurally satisfy the Protocol (`__enter__`, `__exit__`, `execute`, `commit`, `rollback`) with zero errors, and that every M023 repository adapter remains type-correct with zero source edits. `run_composed`'s return type remains exactly `tuple[object, ...]`; no generics or overloads were added beyond what the frozen design specifies.

## 9. Cleanup

`_ComposedTransaction.__enter__` captures the `Token` returned by `_active_composed_scope.set(...)`; `__exit__`'s `finally` block unconditionally calls `_active_composed_scope.reset(token)`. This covers every exit path once `__enter__` has returned successfully: successful commit, poisoned-scope rollback (with or without a live exception), and an exception raised by `commit()`/`rollback()` themselves (the `finally` still runs). If `PostgresUnitOfWork.__enter__` itself fails during composed-scope entry, `_active_composed_scope.set(...)` is never reached, so there is nothing to reset — no leak.

**Correction (Version 1.1, Section 19):** the gap was in the window *between* `PostgresUnitOfWork.__enter__` succeeding and `_active_composed_scope.set(...)` completing — a failure there is not covered by `__exit__`'s `finally` at all, since Python's `with` statement never calls `__exit__` unless `__enter__` itself returns successfully. `_ComposedTransaction.__enter__` now wraps ambient-scope construction and publication in its own `try`/`except`, rolling back and closing the already-entered real unit of work before re-raising. Confirmed by unit tests `test_context_reset_after_successful_commit`, `test_context_reset_after_operation_failure`, `test_context_reset_after_poisoned_scope`, and (Version 1.1) `test_publication_failure_rolls_back_and_resets_reentrancy_guard`, `test_publication_failure_leaves_no_stale_composed_scope_for_next_call`, and `test_cleanup_rollback_failure_surfaces_with_original_publication_failure_chained`, each of which performs a fresh, independent standalone `unit_of_work()` call immediately afterward to prove no stale scope or leaked reentrancy-guard state survives.

## 10. Callback Side-Channel Limitation (Disclosed, Not Enforced)

`run_composed`'s own official return path never exposes a result before commit. A caller who leaks an intermediate result out of their own `operations` callable via a captured variable, a log line, or a network call cannot be prevented from doing so by any API shape in Python; this is stated explicitly in the method's own docstring rather than implying a stronger guarantee than is achievable, exactly matching the frozen Design's Section 21 disclosure.

## 11. Same-Identity Behavior

Proven against real PostgreSQL with the actual M023 `PostgresCampaignRepository`:

- **add-then-get within the same operation** (`test_composed_read_your_own_writes_within_same_operation`): a `get()` immediately after an `add()`, both inside one operation callable, correctly observes the just-inserted row — ordinary single-connection transaction visibility, no special-casing needed;
- **add-then-save across two sequential operations** (`test_composed_add_then_save_same_repository_instance_sequentially`): the same repository instance used for both `add()` in the first operation and `get()`/`save()` in the second, both against the one shared transaction, correctly sequences `CREATED` then `UPDATED`.

## 12. Nesting Behavior

All rows of the frozen Design Section 11 matrix relevant to mechanism-level (not requiring real repositories) behavior are covered by the SQLite unit suite; the same-service-join and different-service-rejection rows are additionally proven against real PostgreSQL:

- standalone `unit_of_work()` alone — unchanged;
- plain nested `unit_of_work()` outside any composed scope — still raises, unchanged from M023;
- `unit_of_work()` inside an active composed scope, same service — joins via `_JoinedUnitOfWork`;
- `unit_of_work()` inside an active composed scope, different service — rejected before any SQL, no partial state;
- nested `run_composed` (same or different service) — rejected via the same reentrancy guard.

## 13. Test Evidence

### 13.1 Unit Tests (`tests/unit/test_m024_composed_unit_of_work.py`, 22 tests, SQLite, no real database)

Public API (zero/one/multiple operations, ordering, exception propagation), result semantics (no result before/without commit), standalone-unaffected, plain-nesting regression, same-service join, cross-service rejection, nested `run_composed` (same and different service), poisoned-scope (swallowed failure, no further SQL), ContextVar cleanup on every exit path (success, operation failure, poisoned scope), and (Version 1.1, Section 19) ambient-scope publication-failure cleanup: rollback and reentrancy-guard reset, no operation invoked, no result tuple, no stale scope for the next call, and cleanup-failure precedence when rollback itself also fails. **22/22 passed**, zero `ResourceWarning`s (Section 21).

### 13.2 Real PostgreSQL Integration Tests (`tests/integration/test_m024_postgres_composed_unit_of_work.py`, 12 tests)

Using the actual, frozen M023 `PostgresCampaignRepository` and `PostgresRunRepository` adapters against a real, migrated, disposable PostgreSQL 17.10 Docker Compose instance:

- cross-aggregate atomic commit (Campaign + Run in one composed scope, both durable, visible from a fresh independent connection);
- cross-aggregate atomic rollback (an operation raising after an earlier operation's insert leaves **no** partial state for either aggregate);
- poisoned scope via a swallowed real DB uniqueness-constraint violation, with no further SQL attempted afterward — raises the synthetic "Composed transaction poisoned" message, full rollback;
- poisoned scope via a swallowed failure **followed by** a later operation's own real `execute()` attempt — raises PostgreSQL's own aborted-transaction-derived `FoundationError` instead (Design Section 10 row 3), still full rollback, proving the two poisoning paths are both correctly wired to the same rollback/cleanup guarantee;
- same-identity read-your-own-writes and add-then-save sequencing;
- cross-service rejection before any SQL executes;
- zero-operation and one-operation parity with standalone behavior;
- standalone M023 usage and plain nested-`unit_of_work()` rejection, unaffected.

**12/12 passed.**

### 13.3 Full Regression

- `tests/unit`, `tests/contract`, `tests/architecture`: **366 passed** (361 + 5 new correction tests), coverage 92.90% (subset run) / see Section 15 for the full `verify.ps1` run including skipped opt-in suites;
- `tests/integration/test_m023_postgres_repositories.py` (26 tests) and `tests/integration/test_m022_schema_migration.py` (49 tests), run against a fresh disposable PostgreSQL instance, **unmodified**: **75/75 passed**, proving zero regression in any M022/M023 behavior.

## 14. PostgreSQL Evidence Detail

| Item | Value |
| --- | --- |
| PostgreSQL version | 17.10 (`postgres:17` Docker image, Debian build) |
| Instance | Fresh, disposable Docker Compose project `m024corr`, port `55433`, repository `infra/local/compose.yaml` PostgreSQL service only, migrated via `alembic upgrade head`, torn down via `docker compose down -v --remove-orphans` after the run (re-provisioned fresh for this correction) |
| M024 integration tests | 12/12 passed |
| M023 integration tests (regression) | 26/26 passed |
| M022 integration tests (regression) | 49/49 passed |
| Combined single run (this correction) | 87/87 passed (12 + 26 + 49) |
| Atomic commit (cross-aggregate) | Proven |
| Atomic rollback (cross-aggregate) | Proven |
| Poisoned scope (silent swallow, no further SQL) | Proven — synthetic FoundationError |
| Poisoned scope (swallow + later real SQL attempt) | Proven — DB-driver-level FoundationError, same rollback guarantee |
| Cross-service rejection before SQL | Proven |
| Same-identity sequencing / read-your-own-writes | Proven |
| Cleanup / standalone compatibility | Proven |
| Ambient-scope publication-failure cleanup (Section 19) | Proven — unit-level, real transaction rollback + connection close + reentrancy-guard reset |
| Teardown | Clean (`pg_ctl stop -m fast`, data directory removed) |

## 15. Full Validation Loop

| Gate | Result |
| --- | --- |
| Python | 3.13.14 (`.venv`) |
| `python -m compileall -q src tests tools migrations` | PASS |
| `ruff format --check .` / `ruff check .` | PASS |
| `mypy` (default config, 79 source files) | PASS, 0 issues |
| `scripts/security.ps1` | PASS — 0 known vulnerabilities, secret scan target count 254, 0 findings |
| `scripts/verify.ps1` (fresh, end-to-end) | PASS — `366 passed, 96 skipped`, coverage `82.15%` |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS |
| `git diff --check` | PASS |

## 16. Hostile Self-Review

Attacked for all 14 failure modes named in the mission's Phase 14, against the actual implementation and its test evidence (Section 13):

1. **Result exposure before commit** — checked: `results = tuple(...)` is computed strictly inside `_ComposedTransaction`'s `with` block; `run_composed`'s `return results` executes only after that block exits via commit. No defect.
2. **Callback side-channel overclaim** — checked: the docstring and Section 10 of this document state the limitation explicitly rather than a stronger guarantee. No defect.
3. **Swallowed error still committing** — checked: `_ComposedTransaction.__exit__`'s commit branch requires **both** `exc_type is None` **and** `state is ACTIVE`; a poisoned scope can never reach commit even with no exception in flight. Proven by both SQLite and real-PostgreSQL tests. No defect.
4. **Poison not propagated** — checked: poisoning fires on any propagating exception out of the operation's own `with` block, regardless of source (translated adapter error or bare `FoundationError`). No defect.
5. **Cross-service join** — checked: ownership compared by Python identity only; a different service instance is rejected before SQL, proven against real PostgreSQL. No defect.
6. **Stale ContextVar** — **originally checked and cleared incorrectly.** The Version 1.0 self-review claimed the `try/finally` reset covered every exit path, but it only covered paths reachable once `_ComposedTransaction.__enter__` had already returned successfully — it did not check whether `__enter__` itself could leave the real unit of work entered (connection open, transaction started, global reentrancy guard set) without ever reaching that `finally` block. It can: a failure between `PostgresUnitOfWork.__enter__()` succeeding and `_active_composed_scope.set(...)` completing is exactly this gap, found by the independent implementation review (`M024-IMPL-REVIEW-0001`, Section 19) and missed by this document's own original hostile self-review. **Corrected** in Version 1.1: `__enter__` now wraps ambient-scope construction and publication in its own `try`/`except`, rolling back and closing the already-entered real unit of work before re-raising. Proven by five new unit tests (Section 13.1).
7. **Cleanup failure** — checked: when the Section 19 correction's own rollback-on-publication-failure itself fails, that failure surfaces (matching `PostgresUnitOfWork.rollback()`'s existing contract of always completing — closing the connection and resetting the reentrancy guard — even when the underlying rollback raises), with the original publication failure preserved via Python's automatic exception chaining (`__context__`). Proven by `test_cleanup_rollback_failure_surfaces_with_original_publication_failure_chained`. No further defect found.
8. **Inaccurate typing** — checked: `unit_of_work() -> PersistenceUnitOfWork`; `mypy` confirms both concrete implementations structurally satisfy the Protocol; no consumer depends on a concrete-only attribute. No defect.
9. **Nested-scope regression** — checked: plain nested `unit_of_work()` outside a composed scope still raises exactly as M023 froze it; the full M022/M023 regression suite passes unmodified. No defect.
10. **Same-identity conflict error** — checked: sequential add/get/save against the same shared transaction behaves per ordinary transaction-visibility semantics, proven against real PostgreSQL. No defect.
11. **Standalone M023 regression** — checked: 75/75 M022+M023 integration tests and 361 unit/contract tests pass unmodified. No defect.
12. **Adapter-source modification** — checked: `git diff` against the frozen baseline touches exactly one source file; zero M023 adapter files changed. No defect.
13. **Hidden application service** — checked: no application-service-layer code was added; `run_composed` lives entirely inside the existing `PostgresPersistenceService`. No defect.
14. **M025 leakage** — checked: no repository-runtime-composition, application-service, or retry-policy code was added. No defect.

One issue was found and corrected during this phase, but in the **test suite**, not the implementation: an initial real-PostgreSQL test asserted the synthetic "Composed transaction poisoned" message for a three-operation sequence where a *third* operation attempted further SQL after an earlier swallowed failure. Per frozen Design Section 10 row 3, that scenario deliberately surfaces PostgreSQL's own aborted-transaction-derived error instead. The test's expectation, not the implementation, was corrected; the corrected test (`test_composed_execute_after_poisoning_fails_at_the_database_and_still_rolls_back`) now documents and proves the frozen row-3 behavior explicitly, alongside a separate test for the true swallow-with-no-further-SQL row-2 case.

No implementation defect was found. Full validation was already fresh (Section 15) at the time this review concluded; no re-run was required.

**This conclusion was itself incomplete** — see Section 19.

## 17. Deferred Work

Unchanged from the frozen Design's Section 22 and the Design Freeze's Section 6 accepted observations: repository runtime composition (Candidate E), application services (Candidate F), retry-on-conflict policy (Candidate J), an enforced operation-count/timeout cap, and any MILESTONE-025 work all remain out of scope and undone.

## 19. Correction: Ambient-Scope Publication-Failure Cleanup (`M024-IMPL-REVIEW-0001`)

**Finding.** An independent implementation review of commit `5fd0024` found that `_ComposedTransaction.__enter__` entered the real `PostgresUnitOfWork` (opening a connection, starting a transaction, and setting the module-level `_active_unit_of_work` reentrancy guard) *before* constructing the `_ActiveComposedScope` record and publishing it via `_active_composed_scope.set(...)`. If either of those two steps had raised, `__enter__` itself would raise — and because Python's `with` statement only calls `__exit__` when `__enter__` returns successfully, nothing would ever roll back the already-open transaction, close the connection, or reset `_active_unit_of_work`. Since that guard is a single module-level `ContextVar` shared by every `PostgresPersistenceService` instance in the same thread/task context, this was not a per-call leak: it would permanently lock out *all* persistence work in that context until the process or context ended, since every subsequent `unit_of_work()` call anywhere would hit the stuck guard and raise "Nested persistence units of work are not supported".

**Reproduction.** Confirmed by reading `_ComposedTransaction.__enter__` directly (no try/except existed around scope construction or `_active_composed_scope.set(...)`) and by writing a unit test that monkeypatches the module-level `_active_composed_scope` global to raise on `.set(...)`; against the pre-correction code, this test failed exactly as predicted, and every subsequent test in the same file then failed too, for exactly the reason above (proven by reverting the fix, rerunning, and observing the cascade, then restoring the fix).

**Correction.** `_ComposedTransaction.__enter__` now wraps ambient-scope construction and `ContextVar` publication in a `try`/`except`:

```python
unit_of_work = PostgresUnitOfWork(self._service)
unit_of_work.__enter__()
self._unit_of_work = unit_of_work
try:
    scope = _ActiveComposedScope(
        owner_service=self._service,
        unit_of_work=unit_of_work,
        state=_ComposedScopeState.ACTIVE,
    )
    self._token = _active_composed_scope.set(scope)
    self._scope = scope
except Exception:
    unit_of_work.rollback()
    raise
return self
```

`unit_of_work.rollback()` reuses the existing, unmodified `PostgresUnitOfWork.rollback()`/`_complete()` contract: it always closes the connection and resets `_active_unit_of_work` via the token-based `_reset_context()`, even if the real database-level rollback itself fails (in which case `rollback()` raises its own translated `FoundationError`, which surfaces in place of the original publication failure with that original preserved via Python's automatic `__context__` chaining — the same precedence this file's `PostgresUnitOfWork.__exit__` already uses elsewhere, so no new precedence rule was invented). If `PostgresUnitOfWork.__enter__` itself fails (the pre-existing case, unaffected by this correction), it is already handled entirely within that method's own try/except, so no `_ComposedTransaction` state exists yet and no cleanup is needed there.

**No public API, design decision, M020 Protocol, or M023 adapter changed.** The fix is confined to a five-line control-flow change inside one private method.

**Tests added** (`tests/unit/test_m024_composed_unit_of_work.py`): `test_publication_failure_rolls_back_and_resets_reentrancy_guard`, `test_publication_failure_never_invokes_any_operation`, `test_publication_failure_returns_no_result_tuple`, `test_publication_failure_leaves_no_stale_composed_scope_for_next_call`, `test_cleanup_rollback_failure_surfaces_with_original_publication_failure_chained`. Each uses a `_RaisingComposedScopeVar` stand-in swapped in for the module-level `_active_composed_scope` global via `monkeypatch.setattr` (a real `contextvars.ContextVar.set` cannot be monkeypatched directly — it is a read-only C-level attribute — so the whole module global is swapped instead), proving: the real transaction rolls back and never commits; the connection closes; `_active_unit_of_work` resets; a subsequent standalone `service.unit_of_work()` succeeds; no operation callback ever executes; no result tuple is ever returned; the original publication failure propagates when cleanup itself succeeds; and the cleanup failure (with the original chained via `__context__`) propagates when cleanup itself also fails.

A real-PostgreSQL regression for this exact failure mode was considered and rejected: forcing a `ContextVar.set` or dataclass-construction failure against a real instance would require the same global-monkeypatching technique used at the unit level, with no additional real-database behavior to observe (the fix never touches SQL) — so unit-level proof plus the unchanged, still-passing 12-test real-PostgreSQL suite (Section 14) is the evidence basis for this correction, per this mission's own Phase 4 allowance.

## 20. Correction: Post-Commit Governance Truth

`PROJECT_CHECKPOINT.md` and the `external-review/M024_MULTI_AGGREGATE_UNIT_OF_WORK_IMPLEMENTATION/` package's `repository-truth.txt` and `review-instructions.md` were all authored and packaged *before* implementation commit `5fd0024` existed, and described the implementation as uncommitted working-tree state with an expected HEAD of `ed0a4198...` (the design-freeze commit). They were never updated after the commit landed, so both became factually stale the moment `5fd0024` was created — mirroring, and repeating, the exact self-reference staleness pattern already found and root-caused during the M023 lifecycle. `PROJECT_CHECKPOINT.md` is corrected in this same correction (Section 2's `CHECKPOINT_CONTENT_BASELINE_*` fields and Section 5.4 updated to cite `5fd0024` as the current implementation commit with status `COMMITTED_LOCALLY_REQUIRES_NARROW_CORRECTION`); the external review package is fully regenerated against the two-commit lineage (`ed0a4198...`..`HEAD`) as part of this correction's own packaging step, not left describing the prior, now-inaccurate state.

## 21. ResourceWarning Disposition (Non-Blocking Observation)

19 `ResourceWarning: unclosed database in <sqlite3.Connection...>` warnings were traced to the `service` fixture (and two inline `other_service` instances) in `tests/unit/test_m024_composed_unit_of_work.py` never calling `.close()`. Each test's SQLite engine uses `StaticPool` (a single shared underlying `sqlite3.Connection` for the whole engine); without an explicit `service.close()` (which disposes the pool), that connection is only closed on eventual garbage collection, which Python's `sqlite3` module reports as a `ResourceWarning`. `tests/unit/test_postgres_persistence.py` already established the correct convention of calling `.close()` explicitly. **Corrected narrowly**, entirely inside the test file: the `service` fixture is now a generator fixture with a `finally: svc.close()` teardown, and the two inline `other_service` instances are now wrapped in `try/finally: other_service.close()`. Confirmed eliminated by running the full file with `-W error::ResourceWarning`: 22/22 tests pass with zero warnings (previously 17/17 passed with 19 warnings). No production code was touched.

## 22. Implementation Review Issue Register

| Issue ID | Severity | Source | Status | Resolution |
| --- | --- | --- | --- | --- |
| M024-IMPL-REVIEW-0001 | MAJOR | Independent hostile implementation review of commit `5fd00247bdb25b01a4f5de831b5b9baa483af6a5` | RESOLVED IN NARROW CORRECTION | `_ComposedTransaction.__enter__` now rolls back and closes the already-entered real `PostgresUnitOfWork` if ambient composed-scope construction or `ContextVar` publication fails; five targeted unit tests prove cleanup, no operation execution, no result tuple, no stale scope, and cleanup-failure precedence. |
| M024-IMPL-REVIEW-0002 | MAJOR | Independent hostile implementation review of commit `5fd00247bdb25b01a4f5de831b5b9baa483af6a5` | RESOLVED IN NARROW CORRECTION / PACKAGE REGENERATION | `PROJECT_CHECKPOINT.md` now uses checkpoint-content-baseline semantics for implementation commit `5fd00247bdb25b01a4f5de831b5b9baa483af6a5` and correctly states the active correction is uncommitted until the correction commit exists; the external-review package is regenerated after this correction commit from the committed two-commit lineage, with live Git truth captured in `repository-truth.txt`. |
| M024-IMPL-REVIEW-0003 | OBSERVATION | Independent hostile implementation review of commit `5fd00247bdb25b01a4f5de831b5b9baa483af6a5` | RESOLVED IN NARROW CORRECTION | SQLite `StaticPool` test services are now explicitly closed in fixture teardown and inline `other_service` cleanup; `tests/unit/test_m024_composed_unit_of_work.py` passes with `-W error::ResourceWarning`. |

## 23. Final Status

```text
M024 MULTI-AGGREGATE UNIT OF WORK IMPLEMENTATION COMPLETE — READY FOR INDEPENDENT RE-REVIEW / NOT APPROVED / NOT FROZEN / M025 NOT STARTED
```
