# MILESTONE-024 - Multi-Aggregate Persistence Unit of Work Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-024-DESIGN |
| Title | Multi-Aggregate Persistence Unit of Work Design |
| Version | 1.1 (narrow correction) |
| Status | DESIGN READY FOR INDEPENDENT RE-REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `4ce800d3609ba7c621eadffc338bc5bc2503228d` (MILESTONE-023 APPROVED AND FROZEN) |
| Mission type | Design only |
| Source code, migrations, repository adapters modified | No |

**Version 1.1 note:** an independent hostile review of Version 1.0 returned "M024 DESIGN REQUIRES NARROW CORRECTION" with two CRITICAL findings, four MAJOR findings, and one MINOR finding. This version replaces the transparent ambient-join public API (Section 5-9 of v1.0) with a callback/batch API that never exposes a committed-looking result before the composed transaction actually commits, freezes an ownership-aware ambient-scope record preventing cross-service joining, freezes failure-safe token-based `ContextVar` cleanup, corrects the dishonest return-type annotation, and adds explicit nesting/service-identity and same-identity operation matrices. See Section 23 for the full correction record.

## 2. Baseline

Verified live against the frozen M023 state:

- `src/empirical_platform/shared/persistence/postgres.py` defines `PostgresPersistenceService.unit_of_work() -> PostgresUnitOfWork`, which unconditionally constructs `PostgresUnitOfWork(self)` and returns it, un-entered;
- `PostgresUnitOfWork.__enter__` checks a module-level `_active_unit_of_work: ContextVar[bool]` (default `False`, shared globally across **every** `PostgresPersistenceService` instance in the same execution context — it is declared once at module scope, not per-instance); if already `True`, raises `FoundationError(message="Nested persistence units of work are not supported")`; otherwise sets it to `True` via `_active_unit_of_work.set(True)` (capturing the returned `Token`), opens a real SQLAlchemy `Connection`, and begins a transaction;
- `PostgresUnitOfWork.__exit__` commits on success or rolls back on exception, then `_complete()` closes the connection and `_reset_context()` resets the ContextVar via the captured `Token` — this token-based reset pattern already exists in frozen M023 code and this design reuses it exactly for the new ContextVar it introduces;
- `execute()` binds named parameters via SQLAlchemy's `text()`, wraps every failure via `translate_persistence_error()` into `FoundationError`, and returns `list[dict[str, object]]` (or `[]` for non-row-returning statements);
- `empirical_platform.shared.interfaces.persistence.PersistenceUnitOfWork` is a `Protocol` with exactly `__enter__`, `__exit__`, `execute`, `commit`, `rollback` — structurally satisfied today by `PostgresUnitOfWork` without explicit inheritance;
- all four M023 concrete repository adapters (`PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository`) call `with self._service.unit_of_work() as work:` exactly once per `get`/`add`/`save` invocation, use only `work.execute(...)`, never inspect its concrete type, and construct their return value (`LoadedAggregate` or `SaveResult`) only after that `with` block exits without exception;
- `LoadedAggregate` and `SaveResult` (`src/empirical_platform/shared/contracts/repository.py`) are frozen, unconditional-success dataclasses — nothing in their shape or M020's contract distinguishes a "provisional" from a "durable" instance; every existing caller is entitled to treat any instance of either as representing committed durable state;
- the frozen M020 Repository Protocols (`get(identity)` / `add(aggregate)` / `save(aggregate, *, expected_persisted_version)`) take no session, transaction, or Unit-of-Work parameter anywhere;
- no application service, runtime composition root, or dependency-injection container exists anywhere in the repository.

## 3. Problem Statement

A caller today cannot compose two repository operations — whether on the same aggregate repository or across different aggregate repositories — into one atomic transaction. Calling a second repository operation while a first is still open raises `FoundationError` by design (M023 Design Section 11 point 5), because each operation unconditionally opens its own `PostgresUnitOfWork` and the reentrancy guard forbids more than one being active at once.

This design defines a composition mechanism that lets a caller group multiple repository operations into one atomic transaction, without changing the M020 Repository Protocol surface, without changing any M023 concrete repository adapter's source code, and — corrected in this version — without ever handing the caller a normal `SaveResult`/`LoadedAggregate` that could be mistaken for committed durable state before the composed transaction has actually committed.

## 4. Design Principles

1. **The M020 Repository Protocol surface is immutable.** `get`/`add`/`save` accept exactly the parameters they accept today. No session, transaction, or Unit-of-Work object is ever passed to or returned from a repository method.
2. **No M023 concrete repository adapter file changes.** All four adapters keep calling `with self._service.unit_of_work() as work:` exactly as written today. The composition mechanism is invisible to them.
3. **Single-operation behavior is unchanged when no composed scope is open.** Every M023 test that exercises `get`/`add`/`save` in isolation must continue to pass unmodified.
4. **Only the new, explicit composition entry point enables joining.** A caller who nests two `with service.unit_of_work():` blocks *without* using the new entry point still gets today's exact `FoundationError`.
5. **Exactly one real transaction backs a composed scope, owned by exactly the `PostgresPersistenceService` instance that opened it.** A different service instance must never join it.
6. **A caller-visible success result must never be observable before the composed transaction actually commits.** This is the corrected core guarantee of this version (Section 9).

## 5. Canonical Composition API

Version 1.0 exposed a raw, public `service.composed_unit_of_work()` context manager a caller could open directly and put arbitrary code inside, calling repository methods that returned real `SaveResult`/`LoadedAggregate` objects immediately, inline, before the block's own commit. That shape cannot guarantee Principle 6 — a caller with direct access to a real `SaveResult` the instant `repo.save(...)` returns has no way to be prevented from acting on it as if it were already durable, regardless of what documentation says about a later, invisible commit.

**This version replaces that public shape entirely** with exactly one canonical entry point:

```python
def run_composed(
    self, operations: Sequence[Callable[[], object]]
) -> tuple[object, ...]:
    """Execute repository operations atomically; return all results only after commit."""
```

added to `PostgresPersistenceService`. A caller supplies a sequence of zero-argument callables (typically small closures wrapping one repository call each); `run_composed` executes them all against one shared, ambient transaction and returns their results, **in the exact order supplied**, as a tuple — but only once that transaction has actually committed. If any operation raises, or the scope is otherwise poisoned (Section 10), `run_composed` raises instead of returning, and no result tuple is ever produced.

The context-manager machinery that opens and closes the one real transaction (`_ComposedTransaction`, Sections 7-8) is now **private** — not exported, not part of the public surface, used only internally by `run_composed`. There is no other sanctioned way for a caller to obtain a composed scope. This is the one canonical API this design selects; no alternative is offered.

Exact usage — successful two-repository transaction:

```python
def _op_save_campaign() -> SaveResult:
    return campaign_repo.save(campaign, expected_persisted_version=loaded_campaign.persisted_version)

def _op_add_run() -> SaveResult:
    return run_repo.add(new_run)

campaign_result, run_result = service.run_composed([_op_save_campaign, _op_add_run])
# Reached only after both operations' SQL committed together. Both results are
# now genuinely durable; neither existed as a caller-visible value before this line.
```

Exact usage — rollback when the second operation fails:

```python
try:
    service.run_composed([_op_save_campaign, _op_add_duplicate_run])
except AggregateAlreadyExists:
    pass
# No result tuple was ever produced. Campaign's save was never committed either,
# even though _op_save_campaign's own inner call already returned a SaveResult
# object internally — that object never escaped to this caller (Section 9).
```

Exact usage — access to final results only after commit (restating the successful case's own guarantee explicitly): the assignment `campaign_result, run_result = service.run_composed(...)` is the **first** point at which this caller's code can observe either result; there is no earlier hook, callback, or partial-result API that exposes them sooner.

Exact usage — commit failure: if the underlying `PostgresUnitOfWork.commit()` itself raises (e.g. the connection drops between the last operation and commit), `run_composed` does not catch it — the `FoundationError` `commit()` already produces propagates directly to the caller, and, as above, no result tuple is ever constructed or returned.

Exact usage — poisoned scope after a swallowed inner failure:

```python
def _op_add_duplicate() -> None:
    try:
        run_repo.add(duplicate_run)
    except AggregateAlreadyExists:
        pass  # caller swallows the inner repository error

def _op_add_other() -> SaveResult:
    return campaign_repo.save(campaign, expected_persisted_version=v1)

service.run_composed([_op_add_duplicate, _op_add_other])
# Raises FoundationError("Composed transaction poisoned by a failed operation").
# _op_add_other's own SQL may have already executed against the shared
# connection, but the whole transaction rolls back; no result tuple is produced,
# and the swallowed AggregateAlreadyExists cannot convert this into success.
```

## 6. Ambient Scope Ownership Record

A second module-level `ContextVar` is added, holding an owned record rather than a bare unit of work:

```python
class _ComposedScopeState(Enum):
    ACTIVE = "active"
    POISONED = "poisoned"


@dataclass(slots=True)
class _ActiveComposedScope:
    owner_service: PostgresPersistenceService
    unit_of_work: PostgresUnitOfWork
    state: _ComposedScopeState


_active_composed_scope: ContextVar[_ActiveComposedScope | None] = ContextVar(
    "active_persistence_composed_scope", default=None
)
```

`owner_service` is compared by **Python object identity** (`is`), never by equality, configuration, or any derived "identity" value: `PostgresPersistenceService.unit_of_work()`'s join branch only joins when `scope.owner_service is self`. Two distinct `PostgresPersistenceService` instances are always distinct Python objects — even if constructed against identical connection parameters — so this comparison can never falsely match across services, and requires no new identity/UUID scheme.

`state` starts `ACTIVE` and becomes `POISONED` the first time any joined operation's own `with self._service.unit_of_work() as work:` block exits with a propagating exception (Section 10) — this is a property of Python's own context-manager protocol (`__exit__` always receives `exc_type`/`exc`/`tb` when its block raises), so it requires **no** change to any M023 repository adapter's source to observe.

## 7. Lifecycle State Machine

Only two states are frozen on `_ActiveComposedScope` itself (`ACTIVE`, `POISONED`) — commit/rollback/close are not separately observable states on the record because they are instantaneous transitions fully owned by `_ComposedTransaction.__exit__` (Section 8), not something joined operations or `run_composed` ever need to inspect mid-flight. Before `_ComposedTransaction.__enter__` runs, no `_ActiveComposedScope` exists at all (there is nothing to be in a "CREATED" state); after `_ComposedTransaction.__exit__` runs, the ContextVar is reset to `None` and the just-closed scope object is never referenced again — there is no "CLOSED" state to protect against reuse because `_ComposedTransaction` is never exposed publicly and `run_composed` always constructs a fresh one per call; no caller can ever obtain a reference to reuse.

`_ComposedTransaction` (private, used only by `run_composed`):

```python
class _ComposedTransaction:
    def __init__(self, service: PostgresPersistenceService) -> None: ...
    def __enter__(self) -> _ComposedTransaction: ...
    def __exit__(self, exc_type, exc, traceback) -> Literal[False]: ...
```

`__enter__`:

1. constructs `PostgresUnitOfWork(self._service)` **directly** (never through `self._service.unit_of_work()`, the public factory — see Section 8's boxed warning, carried forward unchanged from Version 1.0's `M024-DESIGN-ISSUE-0005` finding) and enters it;
2. constructs an `_ActiveComposedScope(owner_service=self._service, unit_of_work=<the just-opened PostgresUnitOfWork>, state=ACTIVE)`;
3. sets `_active_composed_scope` via `token = _active_composed_scope.set(scope)`, capturing the token (Section 14).

`__exit__(exc_type, exc, traceback)`:

1. if `exc_type is None` **and** the scope's `state` is still `ACTIVE` (never poisoned): calls `commit()` on the real `PostgresUnitOfWork`;
2. otherwise (an exception propagated, **or** the scope was poisoned with no exception propagating — the swallowed-inner-failure case, Section 10): calls `rollback()` on the real `PostgresUnitOfWork`; if no exception was already propagating, raises a new `FoundationError("Composed transaction poisoned by a failed operation")` after rollback completes, so `run_composed` never falls through to constructing a result tuple;
3. resets `_active_composed_scope` via `_active_composed_scope.reset(token)` in a `finally` block guaranteeing this runs regardless of whether steps 1-2 raised (Section 14).

## 8. Ambient-Scope Join Mechanism

`PostgresPersistenceService.unit_of_work()` gains exactly one new branch, checked first, now honestly typed (Section 13):

```python
def unit_of_work(self) -> PersistenceUnitOfWork:
    self._ensure_can_work("unit_of_work")
    scope = _active_composed_scope.get()
    if scope is not None and scope.owner_service is self:
        return _JoinedUnitOfWork(scope)
    return PostgresUnitOfWork(self)
```

> **Why the ownership check matters:** if a *different* `PostgresPersistenceService` instance calls `unit_of_work()` while some scope is active, `scope.owner_service is self` is `False`, so this branch is skipped and `PostgresUnitOfWork(self)` is constructed instead — which then goes through `PostgresUnitOfWork.__enter__`'s own, unmodified check against the **global** `_active_unit_of_work` ContextVar (Section 2: this ContextVar is module-level, shared across every service instance). Since the ambient scope's real `PostgresUnitOfWork` already set that guard `True`, the different service's attempt correctly raises `FoundationError("Nested persistence units of work are not supported")` — **before any SQL executes**, without joining, and without leaking any connection detail. The safety property CRITICAL 2 requires falls directly out of the existing global reentrancy guard once the join branch correctly excludes non-owning services; no separate error message or mechanism was needed.

> **Why not call `self._service.unit_of_work()` from `_ComposedTransaction.__enter__`** (carried forward from Version 1.0's `M024-DESIGN-ISSUE-0005`): that public factory is the one with the join branch above. If `_ComposedTransaction.__enter__` called it, opening a *second* composed scope with the *same* service while the first is still active would incorrectly find `_active_composed_scope` already populated with a scope owned by that same service and silently join rather than raise. Constructing `PostgresUnitOfWork` directly bypasses the join branch entirely and forces every composed-scope entry through the one, unmodified `_active_unit_of_work` guard, which has no notion of "composed" or "owner" at all and simply refuses any second concurrent unit of work of any kind, regardless of service.

`_JoinedUnitOfWork` (private, constructed with the `_ActiveComposedScope` record rather than a bare unit of work, so it can poison it):

```python
class _JoinedUnitOfWork:
    def __init__(self, scope: _ActiveComposedScope) -> None: ...
    def __enter__(self) -> _JoinedUnitOfWork: ...
    def __exit__(self, exc_type, exc, traceback) -> Literal[False]: ...
    def execute(self, statement, parameters=None) -> Sequence[Mapping[str, object]]: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...
```

- `__enter__`: does **not** touch `_active_unit_of_work` and does **not** open a new connection — returns itself;
- `execute(...)`: forwards directly to `self._scope.unit_of_work.execute(...)` (delegation, not re-implementation — no double-wrapped `FoundationError`, carried forward from Version 1.0's `M024-DESIGN-ISSUE-0004`);
- `commit()` / `rollback()`: no-ops — ownership of the real transaction belongs exclusively to `_ComposedTransaction`;
- `__exit__(exc_type, exc, traceback)`: if `exc_type is not None`, sets `self._scope.state = _ComposedScopeState.POISONED` **before** returning `False` (never suppresses the exception) — this is the one and only place poisoning is triggered, and it requires no change to any M023 repository adapter, because every one of them already uses `with self._service.unit_of_work() as work:` and Python's `with`-statement protocol hands `__exit__` the propagating exception automatically whenever the adapter's own code raises inside that block (whether the adapter's own translated `AggregateAlreadyExists`/`AggregateNotFound`/etc., or a bare `FoundationError`) — this holds for all four adapters' `get`/`add`/`save` uniformly, since every classification/raise in M023's frozen implementation happens inside that same `with` block, never after it.

Because all four M023 adapters only ever call `self._service.unit_of_work()` and use it via `with ... as work:` — never inspecting its concrete type — every one of them participates in a composed scope, and poisons it correctly on failure, with **zero source changes**.

## 9. Result Semantics

Every operation passed to `run_composed` executes to completion (return a real `SaveResult`/`LoadedAggregate`, or raise) while the composed transaction is still open and uncommitted — this cannot be avoided, since Design Principle 1 forbids changing what `get`/`add`/`save` themselves return, and Design Principle 2 forbids changing how they compute it. The real object exists in memory the instant the operation's own inner `with self._service.unit_of_work() as work:` block completes.

**The corrected guarantee is at the `run_composed` API boundary, not inside operation bodies**: `run_composed`'s own `results = tuple(op() for op in operations)` line runs entirely inside `_ComposedTransaction`'s `with` block; the local `results` tuple is not returned to `run_composed`'s own caller until execution reaches the `return results` statement **after** that `with` block has exited via a successful commit (Section 7). Nothing available to code outside `run_composed`'s own call — no callback, no partial-result accessor, no early-return path — can observe any operation's result before that point. A caller who chooses to leak a result out of their own `operations` callable via a side channel (a mutable variable captured by closure, a log line, a network call) is not something any API shape can prevent in Python; this design guarantees the **official** result-producing path never does so, and states this limitation explicitly rather than implying a stronger guarantee than is achievable (see Section 21, Explicit Non-Goals).

Ordering: results are returned in exactly the order `operations` was supplied, one result per operation, using ordinary sequential execution — no concurrency, no reordering.

On rollback (any operation raises, or the scope is poisoned with no exception propagating): `run_composed` never reaches its `return results` statement; the exception from `_ComposedTransaction.__exit__` (Section 7) propagates to `run_composed`'s own caller instead. No result tuple is constructed. This is unconditional, including for operations whose own individual calls (e.g. an `add()` invoked *before* the failing one) already completed and returned a real object internally — that object is discarded with the rest of the local `results` computation; it was never returned to anyone outside `run_composed`.

`get()` calls behave identically for uniformity: a `LoadedAggregate` produced by a `get()` inside `operations` is likewise only returned to the caller after commit. This does not misrepresent anything `LoadedAggregate` itself claims (it never claimed "durable," only "what was read"), but treating all four operation kinds identically avoids a special case a future implementer could get wrong.

## 10. Poisoned-Scope Semantics

| Situation | Effect |
| --- | --- |
| A joined operation raises inside its own `with self._service.unit_of_work() as work:` block | `_JoinedUnitOfWork.__exit__` sets `state = POISONED` (Section 8); the exception itself still propagates normally out of the operation and out of `run_composed`'s `results = tuple(...)` line — `_ComposedTransaction.__exit__` sees a real `exc_type` and rolls back (Section 7 branch 2), no separate poisoned-only path needed here. |
| The caller's own `operations` callable catches and swallows that same exception, so nothing propagates out of `results = tuple(op() for op in operations)` | The scope is **already** `POISONED` (set the instant the failing operation's own inner block exited, *before* the exception ever reached the caller's `try/except`) — regardless of the swallow, `_ComposedTransaction.__exit__` receives `exc_type is None` but checks `state` first (Section 7 branch 1's explicit `and` condition) and takes branch 2 instead: rolls back, then raises a new `FoundationError("Composed transaction poisoned by a failed operation")`. `run_composed` never reaches `return results`. |
| A caller-supplied operation attempts to `execute()` again through the same joined connection *after* the scope was poisoned by an earlier operation, but before `run_composed`'s own `results = tuple(...)` line finishes evaluating the remaining callables | Permitted to execute the SQL itself (this design does not add a pre-flight poisoned check inside `_JoinedUnitOfWork.execute()`, since PostgreSQL's own transaction-aborted state already rejects further statements on an aborted transaction with its own SQLSTATE, which the existing `translate_persistence_error()` already wraps into `FoundationError` uniformly) — the scope was already `POISONED` from the first failure, so the eventual rollback in `_ComposedTransaction.__exit__` is unaffected by whether a second operation's own attempt independently failed too. |
| Commit is attempted on a `POISONED` scope with `exc_type is None` | Forbidden — Section 7 branch 1 requires **both** `exc_type is None` **and** `state is ACTIVE`; a poisoned scope always takes branch 2 (rollback), never commit, regardless of whether any exception is currently propagating. |
| Rollback itself raises | Propagates from `PostgresUnitOfWork.rollback()`'s own existing `translate_persistence_error()` call, unmodified by this design (identical to M023 Design Section 11 point 7's already-frozen behavior) — the `finally`-guaranteed ContextVar reset (Section 14) still runs regardless. |

## 11. Nesting and Service-Identity Matrix

| Row | Caller sequence | Result |
| --- | --- | --- |
| 1 | `service.unit_of_work()` used alone, no composed scope anywhere | Unchanged: opens and closes exactly as in M023. |
| 2 | `service.unit_of_work()` nested inside another `service.unit_of_work()` on the **same** service, no composed scope | Unchanged: raises `FoundationError("Nested persistence units of work are not supported")`, exactly as M023 froze it. |
| 3 | `service.run_composed([...])` open (a composed scope active), and one of the `operations` callables calls `service.unit_of_work()` on the **same** `service` | Joins (Section 8's branch); no error. |
| 4 | A composed scope active (owned by `service_a`), and code reachable from *outside* `service_a`'s own `operations` calls `service_a.unit_of_work()` directly (bypassing `run_composed`) | Still joins — ownership is per-`service`-instance, not per-call-path; any code holding a reference to the exact same `service_a` object joins its active scope. This is intentional: the guarantee is about *which service*, not *which code path*. |
| 5 | A composed scope active, owned by `service_a`; **different** `service_b.unit_of_work()` is called while it is active | Raises `FoundationError("Nested persistence units of work are not supported")` **before any SQL executes** — `service_b`'s ownership check fails (`scope.owner_service is not service_b`), so `service_b` falls through to constructing its own `PostgresUnitOfWork`, which is rejected by the global `_active_unit_of_work` guard (Section 8's boxed note). No join, no leak. |
| 6 | `service_a.run_composed([...])` called again (nested) from inside another `run_composed([...])`'s `operations`, same service | Raises `FoundationError("Nested persistence units of work are not supported")` — `_ComposedTransaction.__enter__` always constructs `PostgresUnitOfWork` directly (Section 8's boxed warning), never via the join branch, so composed scopes never stack regardless of which service is involved. |
| 7 | Same as row 6, but the inner `run_composed` call uses a **different** service | Same result as row 6 — the direct-construction path in `_ComposedTransaction.__enter__` hits the same global `_active_unit_of_work` guard irrespective of service identity; composed scopes never stack, full stop. |
| 8 | A composed scope opened in one OS thread or one `asyncio` Task, and unrelated code running in a genuinely independent thread/Task (no explicit `contextvars.Context` copying) calls `unit_of_work()` on the same or a different service | `ContextVar` values do not cross independently-created threads or freshly-spawned `asyncio` Tasks by default (each gets its own copy of the context at creation time, diverging from that point). The unrelated code sees `_active_composed_scope.get()` as `None` and behaves per row 1/2 — it cannot observe or join a scope from a genuinely separate context. |
| 9 | A caller explicitly calls `contextvars.copy_context()` while a composed scope is active and runs that copied context concurrently elsewhere (e.g. via `Context.run(...)` in another thread) | **Not defended against.** The copy observes the same `_ActiveComposedScope` (including its real `PostgresUnitOfWork`, wrapping a non-thread-safe SQLAlchemy `Connection`) and could attempt concurrent use of it. This is a caller-introduced hazard from manual `contextvars` manipulation, explicitly out of scope for this design to prevent (Section 21). |
| 10 | Attempting to reuse a `_ComposedTransaction` reference after its `__exit__` already ran | Not reachable: `_ComposedTransaction` is private, never returned or exposed by `run_composed`, and a fresh instance is constructed on every `run_composed` call — no caller can hold or reuse a reference. Resolved by encapsulation, not by a runtime check. |

## 12. Same-Identity Operation Matrix

All rows below assume operations run sequentially (never concurrently) within one `run_composed` call, against one shared connection and transaction — ordinary single-connection SQL semantics apply throughout: a transaction always sees its own uncommitted writes (read-your-own-writes), and PostgreSQL enforces uniqueness constraints against other rows already inserted in the *same*, still-open transaction.

| Row | Sequence (same identity `A`, one composed scope) | Result |
| --- | --- | --- |
| 1 | `add(A)` then `get(A)` | `get(A)` succeeds and reflects the just-added, still-uncommitted state — standard read-your-own-writes within one transaction. |
| 2 | `add(A)` then `add(A)` again | The second `add` raises `AggregateAlreadyExists` — PostgreSQL's unique constraint rejects the duplicate insert against the first, already-visible (though uncommitted) row in the same transaction, exactly as it would across two committed, separate transactions. Poisons the scope (Section 10). |
| 3 | `save(A, v2, expected=v1)` then `get(A)` | `get(A)` reflects the just-saved `v2` state — read-your-own-writes again; the guarded `UPDATE`'s effect is visible to a subsequent read on the same connection even though nothing has committed yet. |
| 4 | `save(A, v2, expected=v1)` then `save(A, v3, expected=v2)` | Both succeed, cascading exactly as two standalone sequential saves would: the second save's guarded `UPDATE ... WHERE version = 2` matches the row because the first save's (uncommitted) `UPDATE` already advanced it to `2`, visible within the same transaction. No special-casing required — this is the existing M023 optimistic-concurrency mechanism operating correctly on real, transaction-visible row state. |
| 5 | `save(A, v2, expected=v1)` then `save(A, v2, expected=v1)` again (duplicate expected version) | The second save's guard `WHERE version = 1` matches zero rows, because the row's version is already `2` (from the first save, visible in-transaction) — M023's existing zero-row diagnostic path reads the actual version (`2`), finds it does not match the caller's expected `1`, and raises `OptimisticConcurrencyConflict` exactly as standalone. Poisons the scope. |
| 6 | `save(A, ...)` whose owned children are then replaced by a second `save(A, ...)` in the same scope | Each `save()` independently deletes and re-inserts its own aggregate's mapped owned-child rows as part of its own guarded-update-success branch (M023 Design Section 8) — two sequential saves on the same identity compose exactly as two standalone sequential saves would; no cross-call interaction beyond ordinary transaction visibility. |
| 7 | Two separately-constructed repository instances (e.g. two `PostgresCampaignRepository(service)` objects) operating on the same identity, backed by the **same** `service` | Both instances call `self._service.unit_of_work()` — since `service` is the same object, both correctly join the same `_ActiveComposedScope` (Section 8's ownership check passes for both, since it is per-`service`, not per-repository-instance). Behaves identically to using one repository instance twice. |
| 8 | The same identity operated on through a **different** `service` inside the same `operations` sequence | Not directly possible without also calling that other service's own `unit_of_work()` — which, per Section 11 row 5, is rejected with a safe `FoundationError` before any SQL executes; it cannot silently operate on the identity through an unrelated connection. |

## 13. Type and Protocol Correctness

`empirical_platform.shared.interfaces.persistence.PersistenceUnitOfWork` (existing, frozen, unmodified) is structurally sufficient: it declares exactly `__enter__`, `__exit__`, `execute`, `commit`, `rollback` — the same five members both `PostgresUnitOfWork` and the new `_JoinedUnitOfWork` implement. This design freezes:

```python
def unit_of_work(self) -> PersistenceUnitOfWork: ...
```

as the corrected, honest return annotation on `PostgresPersistenceService.unit_of_work()` — replacing the Version 1.0 annotation of the concrete `PostgresUnitOfWork`, which was already inaccurate the moment the method could return a `_JoinedUnitOfWork` instead.

`run_composed`'s own signature (Section 5) already uses `Sequence[Callable[[], object]] -> tuple[object, ...]`; this is the exact, final signature this design freezes — no narrower generic typing is claimed, since `operations` is inherently heterogeneous (an `add()` returns `SaveResult`, a `get()` returns `LoadedAggregate[SomeAggregate]`, etc.) and forcing a single type parameter across a heterogeneous sequence would either be dishonest or require per-call overloads this design does not need.

Verified: no existing consumer (any of the four M023 repository adapters, or any existing test) relies on the concrete `PostgresUnitOfWork` type returned by `unit_of_work()` — every call site uses it exclusively through the `with ... as work: work.execute(...)` pattern, which only requires the `PersistenceUnitOfWork` Protocol's members. Changing the annotation from the concrete class to the Protocol requires no change to any of them.

Future mypy obligation (implementation milestone): confirm `_JoinedUnitOfWork` satisfies `PersistenceUnitOfWork` structurally (Python `Protocol` conformance requires no explicit inheritance, only matching method signatures) and that `mypy --strict` raises no new error from the changed `unit_of_work()` return annotation anywhere in the four repository adapter modules.

## 14. Cleanup and Context Isolation

Both `ContextVar`s this design touches use the identical token-based pattern already frozen in M023's own `_active_unit_of_work`/`_reset_context()` handling:

```python
token = _active_composed_scope.set(scope)
try:
    ...  # __enter__'s remaining work, or the with-block body
finally:
    _active_composed_scope.reset(token)
```

Applied precisely to `_ComposedTransaction`:

- if the inner `PostgresUnitOfWork(self._service).__enter__()` call itself fails (Section 7 step 1) — e.g. the global reentrancy guard rejects it, or the connection cannot be opened — `_active_composed_scope` is never set at all (the token is only captured after that inner `__enter__` succeeds), so there is nothing to clean up and no stale scope can leak;
- if constructing/publishing the `_ActiveComposedScope` record itself somehow failed after the inner unit of work was already opened (a pathological case, since the constructor call is a plain dataclass instantiation that cannot itself raise for any reason relevant here) — the design specifies that `__enter__` must roll back and close the already-opened inner `PostgresUnitOfWork` before propagating, so no orphaned open connection survives a failed `__enter__`;
- `__exit__`'s commit/rollback/context-reset sequence (Section 7) is wrapped so that the `_active_composed_scope.reset(token)` call is in a `finally` block guaranteeing it runs whether `commit()` raises, `rollback()` raises, or neither does — no stale or closed unit of work can remain ambient after any exit path;
- `_JoinedUnitOfWork` never calls `.set()`/`.reset()` on any `ContextVar` at all (Section 8) — it has nothing of its own to clean up; all cleanup responsibility stays with the one `_ComposedTransaction` that owns the real unit of work.

Context/task isolation is exactly `contextvars.ContextVar`'s own built-in behavior (Section 11 rows 8-9): isolated by default across independently-created threads and freshly-spawned `asyncio` Tasks, but shared if a caller explicitly copies and reuses a `Context`. This design relies on, but does not modify or strengthen, that built-in behavior, and does not claim any guarantee beyond it.

## 15. Cross-Aggregate Worked Example

Restated using the corrected canonical API (Section 5), demonstrating a genuine two-aggregate transaction (required by Scope Selection Section 11):

```python
campaign_repo = PostgresCampaignRepository(service)
run_repo = PostgresRunRepository(service)

loaded_campaign = campaign_repo.get(campaign_identity)
campaign = loaded_campaign.aggregate
campaign.activate(actor="ops", occurred_at=now)

new_run = Run(identity=run_identity, campaign_id=campaign_identity.governance_id)

campaign_result, run_result = service.run_composed([
    lambda: campaign_repo.save(campaign, expected_persisted_version=loaded_campaign.persisted_version),
    lambda: run_repo.add(new_run),
])
# Both results are returned together, only after both operations' SQL committed
# atomically. Neither is observable to this caller any earlier.
```

If `run_repo.add(new_run)` raises `AggregateAlreadyExists`, `service.run_composed([...])` itself raises (the exception propagates through `_ComposedTransaction.__exit__`'s rollback branch), the assignment statement never completes, and the `Campaign`'s activation is not durably committed — even though `campaign_repo.save(...)`'s own inner call already produced a real `SaveResult` object internally, moments earlier, that object was never returned to this caller (Section 9).

## 16. Error Translation

Unchanged from M023 (Section 9): SQLSTATE + constraint-name based translation, never parsed message text. A failure on any joined operation surfaces through that operation's own existing error-translation path (each repository adapter's own `except FoundationError` / diagnostic-query logic, untouched by this design) exactly as it would standalone; the only difference is that the transaction rolled back as a side effect is the shared one, and the scope is marked poisoned (Section 10).

## 17. Architecture Enforcement

`_ComposedTransaction`, `_JoinedUnitOfWork`, `_ActiveComposedScope`, `_ComposedScopeState`, and `_active_composed_scope` all live in `src/empirical_platform/shared/persistence/postgres.py` — the same module as the existing `PostgresUnitOfWork` and `PostgresPersistenceService`. `ALLOWED["shared"]` already permits everything this design needs (last widened by M023 to include `identifiers`, unrelated to this change). No entry in `ALLOWED` or `FORBIDDEN_IMPORT_PREFIXES` requires modification. Running `tools/check_architecture.py .` against a repository with this design implemented is expected to report the same 0 violations as today.

## 18. Security Considerations and Long-Transaction Constraint

No new credential handling, connection-string construction, or secret storage. `execute()`'s existing parameter-binding behavior is unchanged and reused unmodified by every joined operation.

**On the long-transaction concern (corrected):** Version 1.0 described "a handful of repository calls" as a design "constraint," which is not a testable or enforceable statement. This version corrects that: **no enforced operation-count or timeout limit is frozen by this design.** The recommendation that `run_composed` be used for a small, bounded number of operations — never batch/bulk processing — is classified explicitly as a **non-enforced operational recommendation** for a future implementation's documentation and code review discipline, not a constraint the design or its future implementation mechanically enforces. Inventing an arbitrary enforced cap (e.g. "at most 10 operations") without real operational data to justify a specific number would itself be an unjustified, untestable-in-any-meaningful-sense rule; if real usage data later justifies a concrete enforced limit, that would be a narrow, separate future correction, not something this design fabricates now.

## 19. Test Strategy (for a future Implementation milestone)

- two-repository-operation atomic commit against real PostgreSQL (Section 15's worked example; both rows verified present only after `run_composed` returns);
- two-repository-operation atomic rollback when the second operation fails (verify neither row is present, and that `run_composed` raised rather than returned);
- **no normal committed-looking result is observable before `run_composed` returns** — a positive test asserting no caller-visible value exists between operation execution and the function's return;
- results are available to the caller only via `run_composed`'s own return value, never earlier;
- commit failure (simulated, e.g. a dropped connection between the last operation and commit) produces no result tuple and propagates the underlying `FoundationError`;
- calling `service_a.unit_of_work()` from an operation while `run_composed` is active on `service_a` joins correctly (same-service case);
- calling a **different** `service_b.unit_of_work()` while `service_a`'s composed scope is active raises `FoundationError` before any SQL executes (cross-service rejection, CRITICAL 2);
- `_active_composed_scope` is reset (verified via a subsequent, independent `run_composed`/`unit_of_work()` call succeeding normally) after a commit failure, after a rollback failure, and after ordinary success — three separate cleanup-path tests;
- a scope poisoned by a failed-then-swallowed inner operation still rolls back and still raises from `run_composed`, producing no result tuple (Section 10);
- a later `execute()` attempted after the scope is already poisoned by an earlier operation does not resurrect the scope into a committable state;
- nested `run_composed` (same service) raises `FoundationError`, matching Section 11 row 6;
- nested `run_composed` (different service) raises `FoundationError`, matching Section 11 row 7;
- a plain `unit_of_work()` nested inside another plain `unit_of_work()`, no composed scope, still raises exactly as M023 froze it (row 2, regression proof);
- every same-identity operation-matrix row in Section 12, executed against real PostgreSQL, produces exactly the stated result;
- every existing M023 single-operation test continues to pass completely unmodified (regression proof that "no composed scope active" behavior is byte-for-byte unchanged);
- real PostgreSQL evidence for every row above — none of this is mockable in a way that would prove the actual transaction-visibility claims in Sections 9-12.

## 20. Compatibility with M019 through M023

No frozen M019 reconstruction rule, M020 Repository Protocol, M021 Mapper Protocol, or M022 schema is touched. No M023 concrete repository adapter source file is modified — the four classes remain byte-for-byte as frozen. The behavioral extension (Sections 6-10) is additive and inactive by default: with no composed scope ever opened, `PostgresPersistenceService.unit_of_work()` takes the exact same code path it does today (`_active_composed_scope.get()` returns `None` unconditionally, falling through to `return PostgresUnitOfWork(self)`), and `PostgresUnitOfWork.__enter__`/`__exit__`'s own logic is not modified at all.

## 21. Explicit Non-Goals

This design does not:

- change any M020 Repository Protocol signature;
- modify any M023 concrete repository adapter's source code;
- design how a caller obtains repository instances (Candidate E, repository runtime composition — independent, deferred);
- design an application service or use-case orchestration layer (Candidate F — deferred, depends on this milestone and Candidate E);
- design retry-on-`OptimisticConcurrencyConflict` policy (Candidate J — deferred, depends on Candidate F);
- introduce a generic/shared concrete repository or mapper base class;
- prevent a caller from leaking an intermediate result out of their own `operations` callable via a side channel (a captured variable, a log line, a network call) — the guarantee is that `run_composed`'s own official return path never exposes one early, not that Python itself can sandbox arbitrary caller code (Section 9);
- defend against a caller manually copying and concurrently reusing a `contextvars.Context` while a composed scope is active (Section 11 row 9);
- freeze any enforced operation-count or timeout limit on `run_composed` (Section 18);
- touch APIs, workers, Audit, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior;
- start any MILESTONE-025 work.

## 22. Deferred Work

- the actual implementation of `run_composed`, `_ComposedTransaction`, `_JoinedUnitOfWork`, `_ActiveComposedScope`, `_ComposedScopeState`, and `_active_composed_scope` (this milestone is design-only);
- repository runtime composition (Candidate E);
- application services (Candidate F);
- service-level optimistic-concurrency retry policy (Candidate J);
- any enforced operation-count/timeout policy for composed transactions, should real usage data later justify one;
- any MILESTONE-025 work.

## 23. Hostile Self-Review

Version 1.0's five findings (`M024-DESIGN-ISSUE-0001` through `0005`) remain resolved and are carried forward by reference, not repeated here in full — all five concerned the ambient-join mechanism's internal correctness (Sections 6-8 of this version), which this correction preserves unchanged in substance while re-typing and re-scoping its public exposure.

This correction's own findings, responding directly to the independent review's CRITICAL/MAJOR/MINOR items:

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M024-DESIGN-ISSUE-0006 | CRITICAL | 5, 9 | Version 1.0's public `with service.composed_unit_of_work(): repo.save(...)` shape handed the caller a real `SaveResult` the instant a repository call returned, inline, mid-transaction — no API-level mechanism prevented the caller from acting on it as if durable, regardless of the disclosure text. | Traced the exact object lifecycle: `repo.save(...)` constructs and returns `SaveResult` synchronously inside the `with` block's body, fully in caller scope, the moment it is called. | A caller could reasonably (and without any code-level cue) treat a `SaveResult` returned from a frozen M020-shaped call as durable, since nothing about its type says otherwise — a real defect against a frozen success-type's meaning, not a documentation gap. | Replaced the public shape with the `run_composed` callback/batch API (Section 5); the composed context-manager machinery is now private and never exposed to callers, so no caller-visible result can exist before `run_composed`'s own `return results` statement, which is gated on a successful commit. | Resolved |
| M024-DESIGN-ISSUE-0007 | CRITICAL | 6, 8 | Version 1.0's `_active_composed_scope` ContextVar stored a bare `PostgresUnitOfWork` with no owner reference; `unit_of_work()`'s join branch joined *any* active scope regardless of which `PostgresPersistenceService` instance opened it, so a second, unrelated service could silently join and operate against the wrong connection/database. | Traced the join branch: `if joined is not None: return _JoinedUnitOfWork(joined)` had no service-identity check at all. | A caller using two independent `PostgresPersistenceService` instances (e.g. against two different databases, or even just two separately configured connections to the same database) could have one silently execute SQL against the other's connection with no error — a correctness and potential data-integrity hazard. | Replaced the bare ContextVar value with `_ActiveComposedScope` (Section 6), carrying `owner_service`; the join branch now requires `scope.owner_service is self` (Python object identity), and a mismatched service instead falls through to the existing global `_active_unit_of_work` guard, which safely rejects it before any SQL executes (Section 8's boxed note, Section 11 row 5). | Resolved |
| M024-DESIGN-ISSUE-0008 | MAJOR | 7, 14 | Version 1.0 described ContextVar reset only in prose ("resets `_active_composed_scope` back to `None`"), without freezing the token-based `set`/`reset` pattern or a `try/finally` guaranteeing it runs if commit/rollback itself raises — leaving open a path where a stale ambient scope survives a failed exit. | Compared against M023's own already-correct token-based handling of `_active_unit_of_work`/`_reset_context()`, which Version 1.0 did not carry over to the new ContextVar. | A commit or rollback failure could leave `_active_composed_scope` permanently populated, silently blocking or misdirecting all future composed/joined operations in that context — a real, latent defect. | Section 14 now freezes the exact `token = ...set(scope)` / `try: ... finally: ...reset(token)` pattern, explicitly covering entry failure (no token captured, nothing to clean up), commit failure, and rollback failure. | Resolved |
| M024-DESIGN-ISSUE-0009 | MAJOR | 13 | Version 1.0 annotated `unit_of_work() -> PostgresUnitOfWork` while the method could return a `_JoinedUnitOfWork` instead — an inaccurate, dishonest return type a type checker would not catch since Python does not enforce return-type accuracy at runtime. | Directly inspected the Version 1.0 code block; confirmed no existing consumer relies on the concrete type (all usage is via the `PersistenceUnitOfWork`-shaped `with ... as work: work.execute(...)` pattern). | A future implementer or type-checker run against this design would either need to silently work around the inaccurate annotation or introduce an unsound cast; left uncorrected, this compounds into real mypy friction at implementation time. | Section 13 freezes `unit_of_work() -> PersistenceUnitOfWork` (the existing, already-frozen, structurally-sufficient Protocol), confirms no consumer depends on the concrete type, and states the future mypy obligation explicitly. | Resolved |
| M024-DESIGN-ISSUE-0010 | MAJOR | 12 | Version 1.0 did not address what happens when the same aggregate identity is operated on more than once within one composed scope — a real gap, since composing operations across aggregates makes same-identity same-scope operations a foreseeable, not exotic, usage pattern. | Traced each concrete scenario (Section 12) against real single-connection SQL transaction-visibility semantics and M023's own frozen optimistic-concurrency mechanism. | Left unaddressed, a future implementer or reviewer would have to guess whether sequential same-identity saves "stack" correctly, whether duplicates are caught, or whether reads see uncommitted same-transaction writes — exactly the kind of ambiguity this project's own discipline exists to prevent. | Added the full Section 12 matrix (8 rows), each with a concrete, mechanism-traced, testable outcome — none requiring new code beyond what Sections 6-10 already specify. | Resolved |
| M024-DESIGN-ISSUE-0011 | MAJOR | 8, 10 | Version 1.0 did not explain how a joined operation's failure would be detected and used to poison the ambient scope without modifying M023 adapter source — a real, unanswered mechanism gap the independent review correctly flagged as needing either a concrete answer or an honest stop-and-report. | Confirmed via Python's context-manager protocol itself: `_JoinedUnitOfWork.__exit__` unconditionally receives `exc_type`/`exc`/`tb` whenever the repository's own `with work:` block raises, regardless of whether the adapter translates the exception internally — requiring no adapter change to observe. | Left unresolved, this would have been exactly the kind of contradiction the independent review's Phase 5 instruction demanded be reported and stopped on rather than silently assumed away. | Section 8's `_JoinedUnitOfWork.__exit__` now explicitly poisons the scope on any propagating exception, and Section 10's table traces every poisoning/swallowed-failure scenario end to end, confirming the mechanism is genuinely achievable without touching M023 adapters — not a contradiction requiring a stop. | Resolved |
| M024-DESIGN-ISSUE-0012 | MINOR | 18 | Version 1.0 called "a handful of repository calls" a design "constraint" without any enforceable definition — not a testable requirement as written. | Direct re-read of Version 1.0 Section 12 (security considerations) against the independent review's explicit instruction to choose one of "non-enforced recommendation" or "enforceable policy." | Low on its own, but calling an unenforceable phrase a "constraint" invites a false sense of a guarantee that does not exist. | Section 18 now explicitly classifies this as a non-enforced operational recommendation, and declines to fabricate an arbitrary enforced numeric cap without real usage data to justify one. | Resolved |

No unresolved design finding remains.

## 24. Implementation Acceptance Gate (for a future Implementation milestone, not satisfied by this design)

A future M024 implementation is acceptable only if:

- every M023 test passes completely unmodified;
- `run_composed`, `_ComposedTransaction`, `_JoinedUnitOfWork`, `_ActiveComposedScope`, `_ComposedScopeState`, and `_active_composed_scope` are implemented exactly as specified in Sections 5-14;
- the Section 15 worked example passes against real PostgreSQL, both for the commit case and the rollback-on-failure case;
- every row of Sections 11 and 12 is proven against real PostgreSQL, not asserted from reasoning alone;
- `tools/check_architecture.py .` reports 0 new violations;
- no M023 concrete repository adapter source file is modified;
- `mypy --strict` raises no new error anywhere in the repository from the corrected `unit_of_work()` return annotation.

## 25. Final Decision

```text
DESIGN READY FOR INDEPENDENT RE-REVIEW
NOT APPROVED
NOT FROZEN
```
