# MILESTONE-026 - Foundation Runtime Repository Composition Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-026-DESIGN |
| Title | Foundation Runtime Repository Composition Design |
| Version | 1.0 |
| Status | DESIGN READY FOR INDEPENDENT REVIEW / NOT APPROVED / NOT FROZEN |
| Repository baseline | `0d57c36adf8b60ea3be9e86fa3814d1e2b459253` |
| Authoritative scope input | `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_SCOPE_SELECTION.md` |
| Mission type | Design only |

**Do not implement source code. Do not start M027.**

## 2. Purpose

Freeze exactly how `src/empirical_platform/shared/bootstrap.py`'s existing
`FoundationRuntime` composition root, and its `initialize_infrastructure_runtime`
and `initialize_foundation_runtime_with_postgresql` functions, gain the ability
to construct and expose exactly one frozen M025 `PostgresRepositoryRuntime`
alongside the `PostgresPersistenceService` they already construct — with no
change to M020 through M025 frozen contracts, and with an explicit, tested
compatibility rule for callers that inject a non-PostgreSQL persistence fake.

## 3. Design Inputs

- `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_SCOPE_SELECTION.md`
  (frozen scope: extend `FoundationRuntime` only; no application services, no
  API/worker wiring, no M020-M025 contract change).
- `src/empirical_platform/shared/bootstrap.py` (read in full; exact current
  structure reproduced in Section 6 below).
- `src/empirical_platform/shared/persistence/postgres_repositories/runtime.py`
  (frozen M025 `PostgresRepositoryRuntime`: `__init__(self, service:
  PostgresPersistenceService)` raises `TypeError` for any other type, before
  constructing any repository).
- `tests/unit/test_persistence_bootstrap.py` (proves
  `initialize_foundation_runtime_with_postgresql` is deliberately called today
  with `persistence=FakePersistenceService(...)` for dependency-free unit
  testing).
- `tests/unit/test_infrastructure_runtime.py` (proves every single test in
  this file calls `initialize_infrastructure_runtime` with
  `persistence=RecordingPersistence(...)`, a `FakePersistenceService`
  subclass — not one test in this file uses a real
  `PostgresPersistenceService`).
- `tests/integration/test_unified_infrastructure_runtime.py` (proves
  `initialize_infrastructure_runtime` is also called, opt-in, with a real
  `PostgresPersistenceService` against a real database).

## 4. Architectural Problem

M025 froze `PostgresRepositoryRuntime` as a composition boundary over one
caller-supplied `PostgresPersistenceService`. Nothing in the repository's one
process-startup composition root (`FoundationRuntime`) constructs or exposes
one. A caller of `initialize_infrastructure_runtime` or
`initialize_foundation_runtime_with_postgresql` today can only obtain the four
M023 repository adapters by reaching into `runtime.persistence` — typed as the
abstract `PersistenceService` Protocol — and hand-constructing
`PostgresRepositoryRuntime(runtime.persistence)` themselves, which cannot even
be typed safely without an unchecked cast, since `PostgresRepositoryRuntime.__init__`
requires the concrete `PostgresPersistenceService` type.

A second, distinct problem, discovered only by reading the existing test
suite (Section 3): both functions that construct a `PostgresPersistenceService`
are deliberately exercised today, in the overwhelming majority of their
existing tests, with a `persistence=` override that is a `FakePersistenceService`
subclass, not a `PostgresPersistenceService`. `PostgresRepositoryRuntime.__init__`
raises `TypeError` for any other type (frozen, unmodified M025 behavior). A
naive design that unconditionally constructs
`PostgresRepositoryRuntime(persistence_service)` inside either function would
raise `TypeError` on every one of those existing tests, breaking passing,
frozen test suites that this milestone's own Scope Selection Section 13
requires to keep passing unmodified. This is the central constraint this
design must resolve.

## 5. Selected Design

`FoundationRuntime` gains one new optional field,
`repository_runtime: PostgresRepositoryRuntime | None`. It is constructed,
exactly once, **only when the persistence service instance in use is actually
a `PostgresPersistenceService`**, immediately after that persistence service
has been constructed (and, where the function already performs one, after it
has passed its existing readiness check) — never before, never lazily, never
re-constructed. When the function's persistence service is not a
`PostgresPersistenceService` (a `FakePersistenceService` or any other
`PersistenceService` implementation supplied via a `persistence=` override),
`repository_runtime` stays `None`, exactly mirroring the existing pattern
already used for `persistence`/`object_storage` themselves in the two
functions that never construct them.

This is a pure additive composition change: `FoundationRuntime` never calls a
repository method itself; it only holds and exposes the object, exactly as it
already does for `persistence` and `object_storage`.

## 6. Package Placement

No new module. Everything lives inside the existing
`src/empirical_platform/shared/bootstrap.py`, which already imports
`PostgresPersistenceService` from `empirical_platform.shared.persistence.postgres`.
One new import is added:

```python
from empirical_platform.shared.persistence.postgres_repositories.runtime import (
    PostgresRepositoryRuntime,
)
```

This is a same-top-level-module (`shared`) import, requiring no
`tools/check_architecture.py` change — verified during M025's own design and
implementation review, and re-confirmed here by inspection: no domain package
(`campaign`/`run`/`evidence`/`review`) imports `bootstrap.py`'s new field or
`PostgresRepositoryRuntime`, and `bootstrap.py` itself does not move layers.

## 7. Contracts and Types

Exact frozen field addition to the `FoundationRuntime` dataclass
(`@dataclass(slots=True)`), inserted immediately after the existing
`object_storage` field and before the private `_state`/`_lifecycle_events`
fields (all three remaining default-valued fields, so dataclass field
ordering rules are unaffected):

```python
@dataclass(slots=True)
class FoundationRuntime:
    """Composed process-local foundation runtime."""

    config: FoundationConfigSnapshot
    wall_clock: WallClock
    monotonic_clock: MonotonicClock
    identifiers: RuntimeIdentifierGenerator
    logger: FoundationLogger
    health: HealthReport
    persistence: PersistenceService | None = None
    object_storage: ObjectStorageService | None = None
    repository_runtime: PostgresRepositoryRuntime | None = None
    _state: RuntimeLifecycleState = RuntimeLifecycleState.READY
    _lifecycle_events: list[RuntimeLifecycleState] = field(
        default_factory=lambda: [
            RuntimeLifecycleState.NEW,
            RuntimeLifecycleState.STARTING,
            RuntimeLifecycleState.READY,
        ]
    )
```

No new Protocol, no new error type, no new public method on
`FoundationRuntime`. `PostgresRepositoryRuntime` itself is frozen and
unmodified by this milestone; its four adapter properties
(`campaigns`/`runs`/`evidence_packages`/`reviews`), `run_composed`, and
`close` are consumed exactly as M025 froze them.

## 8. Ownership

`FoundationRuntime` owns `repository_runtime` in the same sense it owns
`persistence`: it holds the reference for the runtime's lifetime and is
responsible for disposal (Section 11), but it does not create new lifecycle
semantics for it — `PostgresRepositoryRuntime` has no independent lifecycle
beyond the `PostgresPersistenceService` it wraps (frozen M025 fact, verified
again here).

Construction ownership by function, frozen exactly as follows:

| Function | Constructs `PostgresPersistenceService`? | Constructs `repository_runtime`? |
| --- | --- | --- |
| `initialize_foundation_runtime` | No | No — stays `None` (unchanged: this function has no `persistence` parameter at all) |
| `initialize_infrastructure_runtime` | Yes (or accepts override via `persistence=`) | Only if `isinstance(persistence_service, PostgresPersistenceService)` — constructed from that exact same instance, immediately after `_require_dependency_ready(persistence_service, layer="persistence")` succeeds and before `object_storage_service` construction begins |
| `initialize_foundation_runtime_with_postgresql` | Yes (or accepts override via `persistence=`) | Only if `isinstance(persistence_service, PostgresPersistenceService)` — constructed from that exact same instance, immediately after `persistence_service.initialize()` |
| `initialize_foundation_runtime_with_object_storage` | No | No — stays `None` (unchanged: this function has no `persistence` parameter at all) |

The `isinstance` check is the single frozen rule that resolves the Section 4
conflict: it is false for every `FakePersistenceService`-based test in
`tests/unit/test_infrastructure_runtime.py` and
`tests/unit/test_persistence_bootstrap.py` (so `repository_runtime` stays
`None` there, exactly as today, with zero behavior change to those tests), and
true for every real `PostgresPersistenceService` call site, including the
real-PostgreSQL integration tests in
`tests/integration/test_unified_infrastructure_runtime.py`. No caller-supplied
flag, no configuration switch — the decision is derived entirely from the
concrete runtime type already in hand, requiring no new parameter on either
function's public signature.

No repository is ever constructed by hand outside `PostgresRepositoryRuntime`;
this milestone introduces no direct use of the four M023 repository adapter
classes.

## 9. Call Direction

`bootstrap.py` depends on `postgres_repositories/runtime.py` (an existing,
frozen M025 dependency direction — `bootstrap.py` gains an import from it, not
the reverse). `PostgresRepositoryRuntime` and `PostgresPersistenceService`
remain entirely unaware that `FoundationRuntime` exists; no new coupling is
introduced in the other direction. No application, API, or worker code is
touched; nothing outside `bootstrap.py` calls the new field-population logic.

## 10. Transaction Semantics

None introduced. `FoundationRuntime` never calls `run_composed` or any
repository method itself; it exposes `repository_runtime` for a caller to use
exactly as M025 already permits. No new transaction coordinator, no
reimplementation of `run_composed`, no retry.

## 11. Repository/Runtime Interaction

A caller holding a `FoundationRuntime` with a non-`None` `repository_runtime`
obtains the four repository adapters via
`runtime.repository_runtime.campaigns` / `.runs` / `.evidence_packages` /
`.reviews`, and cross-aggregate atomic execution via
`runtime.repository_runtime.run_composed(operations)` — both exactly the
frozen, unmodified M025 public surface. `FoundationRuntime` performs no
wrapping, filtering, or additional validation of these calls.

## 12. Concurrency Semantics

Unchanged. `PostgresRepositoryRuntime` and `PostgresPersistenceService`
introduce no new concurrency primitive of their own (frozen M024/M025 fact);
`FoundationRuntime` introduces none either. The existing single-process,
`ContextVar`-based `run_composed` concurrency semantics apply exactly as
before, regardless of whether the repository runtime was hand-constructed by
a caller or constructed by `FoundationRuntime` on the caller's behalf.

## 13. Error Taxonomy

No new `FoundationError` category, layer, or operation value is introduced.
Construction of `repository_runtime` cannot itself fail in a way requiring new
error handling: `PostgresRepositoryRuntime.__init__` only raises `TypeError`
for an incompatible `service` argument (frozen M025 behavior), and this design
only ever calls it after `isinstance(persistence_service,
PostgresPersistenceService)` has already been confirmed true — so that
`TypeError` path is structurally unreachable from either composition
function. No `try`/`except` is added around `PostgresRepositoryRuntime`
construction; none is needed.

## 14. Failure Behavior

- If `persistence_service` is a `PostgresPersistenceService`:
  `PostgresRepositoryRuntime(persistence_service)` is constructed
  unconditionally once the `isinstance` check passes; this constructor call
  cannot raise under the frozen M025 contract given a value that already
  passed the `isinstance` check, so it introduces no new failure path into
  either function's existing `try`/`except`-based startup-failure handling
  (`initialize_infrastructure_runtime`) or its non-try-wrapped body
  (`initialize_foundation_runtime_with_postgresql`, which has none today and
  gains none from this change).
- If `persistence_service` is not a `PostgresPersistenceService`:
  `repository_runtime` is simply never assigned away from its dataclass
  default of `None`. No error, no warning, no log line — identical silent
  behavior to how `object_storage` already stays `None` in
  `initialize_foundation_runtime_with_postgresql` today.
- If `persistence_service.initialize()` or, in
  `initialize_infrastructure_runtime`, `_require_dependency_ready` fails
  first, `repository_runtime` is never constructed at all (construction is
  placed strictly after those existing checks in Section 8's ordering table),
  and the function's existing cleanup/exception behavior is completely
  unmodified by this milestone — `repository_runtime` was never assigned, so
  there is nothing new to clean up.

## 15. Close and Cleanup Semantics

`FoundationRuntime.close()`'s existing cleanup list —
`[("object_storage", self.object_storage), ("persistence", self.persistence)]`
— is **not modified**. `repository_runtime` gets no new entry in this list.
This is a frozen, deliberate decision, not an oversight: `PostgresRepositoryRuntime.close()`
delegates purely to `self._service.close()` (the identical
`PostgresPersistenceService` instance already stored on `self.persistence`,
frozen M025 fact) and `PostgresPersistenceService.close()` is already
idempotent (established during M022/M025 review). Closing `persistence` alone
therefore already fully releases everything `repository_runtime` depends on.
Adding a second, redundant cleanup-list entry for `repository_runtime` would
call `.close()` on the same underlying engine twice per shutdown for no
additional resource release, and would falsely suggest `repository_runtime`
owns a resource independent from `persistence` — it does not. After
`FoundationRuntime.close()` runs, `repository_runtime` (if not `None`) remains
a non-`None`, `is`-stable reference on the dataclass — exactly as
`persistence` and `object_storage` themselves remain non-`None`,
already-closed references after `close()` today; no field is set to `None` on
shutdown by the existing code, and this design does not change that pattern
for the new field either.

## 16. Architecture Rules

- `repository_runtime`'s type and construction logic live entirely inside
  `src/empirical_platform/shared/bootstrap.py`; no new module.
- No domain package (`campaign`/`run`/`evidence`/`review`) may import
  `bootstrap.py`'s new field or `PostgresRepositoryRuntime` as a result of
  this milestone; none is touched.
- No change to any M020 Repository Protocol, M021 mapper contract, M022
  schema/migration, M023 concrete adapter, M024 `run_composed` primitive, or
  M025 `PostgresRepositoryRuntime` public surface.
- `tools/check_architecture.py` requires no update (same exemption class as
  the existing `PostgresPersistenceService` import already in `bootstrap.py`).

## 17. Test Strategy for Future Implementation

A future implementation must add tests proving:

1. `initialize_infrastructure_runtime` and
   `initialize_foundation_runtime_with_postgresql`, called with their default
   (real) `PostgresPersistenceService` construction path, populate
   `repository_runtime` with a `PostgresRepositoryRuntime` instance wrapping
   the exact same `persistence` instance (`runtime.repository_runtime` is not
   `None`, and an internal identity check confirms it was built from
   `runtime.persistence`).
2. Both functions, called with a `persistence=FakePersistenceService(...)` (or
   any subclass) override, leave `runtime.repository_runtime` as `None`,
   with zero change to any existing assertion in
   `tests/unit/test_infrastructure_runtime.py` or
   `tests/unit/test_persistence_bootstrap.py`.
3. `initialize_foundation_runtime` and
   `initialize_foundation_runtime_with_object_storage` leave
   `runtime.repository_runtime` as `None` unconditionally (they never
   construct persistence at all).
4. `repository_runtime` is constructed exactly once per call (no
   reconstruction on repeated attribute access — inherited for free from it
   being a plain dataclass field, but must still be asserted).
5. `FoundationRuntime.close()`'s cleanup-list behavior is unchanged: closing
   `persistence` alone renders `repository_runtime`'s underlying service
   unusable for further work, with no new cleanup-list entry and no new
   failure mode introduced.
6. A real-PostgreSQL integration test (opt-in, following the existing
   `test_unified_infrastructure_runtime.py` pattern) proving that a runtime
   initialized via `initialize_infrastructure_runtime` with a real
   `PostgresPersistenceService` exposes a `repository_runtime` whose four
   adapters can `add`/`get` against a real, migrated database, and whose
   `run_composed` commits atomically across two aggregates.
7. All existing `test_bootstrap.py`, `test_persistence_bootstrap.py`,
   `test_infrastructure_runtime.py`, `test_object_storage_bootstrap.py`, and
   `test_unified_infrastructure_runtime.py` tests pass unmodified.
8. No M020-M025 regression (existing PostgreSQL regression suites unchanged).

## 18. Compatibility With M020 Through M025

No source file governed by M020 (Repository Protocols), M021 (mapper
contracts), M022 (schema/migration), M023 (concrete adapters), M024
(`run_composed`), or M025 (`PostgresRepositoryRuntime` itself) is modified by
this design. This milestone only adds one field and its conditional
construction to `bootstrap.py`, consuming M025's frozen public constructor and
public surface exactly as documented, with no new subclass, no monkey-patch,
and no reinterpretation of any prior milestone's frozen behavior.

## 19. Deferred Items

Explicitly out of scope for M026, carried forward unchanged from the Scope
Selection document:

- application services, use-case orchestration, command/handler contracts;
- retry-on-`OptimisticConcurrencyConflict` policy;
- APIs, workers, CLI entrypoints;
- Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- any change to `RuntimeLifecycleState` (no new state is needed — confirmed
  by Section 15's analysis that `repository_runtime` requires no independent
  lifecycle tracking).

## 20. Acceptance Criteria

The design is acceptance-ready only if it freezes, with no remaining
ambiguity:

1. the exact field name and type (`repository_runtime: PostgresRepositoryRuntime | None = None`) — frozen, Section 7;
2. the exact construction order relative to `persistence` in both functions that construct it — frozen, Section 8;
3. the exact conditional-construction rule protecting existing
   `FakePersistenceService`-based tests — frozen, Section 8/14;
4. the exact close-cleanup decision (no new entry; relies solely on the
   existing `persistence` entry) — frozen, Section 15;
5. the exact behavior of all four `initialize_*` functions — frozen, Section 8;
6. exact test obligations for the future implementation — frozen, Section 17.

## 21. Rejected Alternatives

1. **Always construct `PostgresRepositoryRuntime`, letting `TypeError`
   propagate for fake-persistence callers.** Rejected: this would break every
   test in `tests/unit/test_infrastructure_runtime.py` and the
   `FakePersistenceService`-based test in
   `tests/unit/test_persistence_bootstrap.py`, none of which this milestone
   is authorized to modify or accept as a regression.
2. **Add a new `bool` parameter (e.g. `compose_repository_runtime: bool =
   True`) to opt out.** Rejected: unnecessary — the `isinstance` check already
   derives the correct behavior from the concrete type already present at the
   call site, with no new public parameter, no new caller burden, and no way
   for the two states (opted in vs. opted out) to drift out of sync with
   what persistence instance is actually in use.
3. **Give `repository_runtime` its own cleanup-list entry in `close()`.**
   Rejected in Section 15: provably redundant given
   `PostgresRepositoryRuntime.close()`'s pure delegation to the same
   `persistence` object, and would misrepresent `repository_runtime` as owning
   an independent resource.
4. **Construct `repository_runtime` lazily on first access via a property.**
   Rejected: would depart from the eager-construction discipline M025 itself
   froze for `PostgresRepositoryRuntime`'s own four adapters, and would
   introduce a new construction-timing question (thread-safety of
   first-access) that eager, `__init__`-time-equivalent construction avoids
   entirely.
5. **Type `repository_runtime` as `PostgresRepositoryRuntime` (non-Optional),
   raising instead of leaving it `None` for non-PostgreSQL personas.**
   Rejected: `persistence` and `object_storage` are themselves already
   `Optional` on `FoundationRuntime` for the identical reason (not every
   composition function constructs every dependency); an
   unconditionally-required `repository_runtime` would contradict that
   existing, frozen pattern and reintroduce the exact `TypeError`-breaks-fakes
   problem this design exists to avoid.

## 22. Risk Register

| Risk | Mitigation |
| --- | --- |
| A future caller assumes `repository_runtime` is always non-`None` after `initialize_infrastructure_runtime` | Documented explicitly in Section 8's table and Section 14; type remains `Optional` so `mypy` forces callers to narrow it |
| Double-close confusion | Addressed explicitly in Section 15 with the underlying idempotence argument, not left as an implicit assumption |
| Scope creep into application services | Rejected explicitly in Section 21, Item 2, and bounded by Section 19 |
| A future implementation forgets the `isinstance` guard and reintroduces the `TypeError`-breaks-fakes defect | Section 17, Item 2 makes this an explicit, named test obligation, not an incidental side effect of other tests |

## 23. Hostile Self-Review

1. **Does this quietly become "application services"?** No —
   `FoundationRuntime` never calls a repository method or `run_composed`
   itself; Section 5 and Section 11 both state it only holds and exposes the
   object.
2. **Does this require a new lifecycle state?** No — Section 19 explicitly
   confirms no new `RuntimeLifecycleState` value is introduced;
   `PostgresRepositoryRuntime` has no independent lifecycle to track.
3. **Does this silently authorize bootstrap for workers/APIs?** No — no
   worker, API, or CLI entrypoint file is touched; only
   `bootstrap.py` itself changes.
4. **Is the fake-persistence compatibility rule actually testable, or just
   asserted?** Testable and required: Section 17, Item 2 names the exact
   existing test files whose current passing behavior (with
   `repository_runtime` simply absent from their assertions today) must
   remain unbroken, and requires a new, explicit assertion that
   `repository_runtime` stays `None` under a fake-persistence override.
5. **Does the close-cleanup decision introduce ambiguity for a future
   reader?** No — Section 15 freezes exactly one behavior (no new
   cleanup-list entry) with an explicit reason, rather than presenting both
   options as equally valid.
6. **Does this leak into M027?** No — Section 19's deferred list is identical
   in kind to M025's own deferred list; nothing here presumes or requires any
   named future milestone.

## 24. Final Status

```text
M026 DESIGN READY FOR INDEPENDENT REVIEW
M026 NOT APPROVED
M026 NOT FROZEN
M026 IMPLEMENTATION NOT STARTED
```

Do not implement source code. Do not start M027.
