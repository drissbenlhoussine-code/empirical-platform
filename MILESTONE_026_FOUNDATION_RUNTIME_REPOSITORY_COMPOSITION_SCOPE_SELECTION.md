# MILESTONE-026 - Foundation Runtime Repository Composition Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-026-SCOPE-SELECTION |
| Title | Foundation Runtime Repository Composition Scope Selection |
| Version | 1.0 |
| Status | SCOPE SELECTED - PENDING INDEPENDENT REVIEW |
| Repository baseline | `0d57c36adf8b60ea3be9e86fa3814d1e2b459253` |
| Mission type | Scope selection and design authorization only |

## 2. Objective

Select the single best bounded milestone after frozen M025 using live repository evidence.

## 3. Current Repository Evidence

Frozen prerequisites now present:

- M020 repository contracts;
- M021 mapper contracts;
- M022 PostgreSQL schema and migration;
- M023 concrete PostgreSQL repository adapters;
- M024 multi-aggregate persistence Unit of Work primitive (`run_composed`);
- M025 repository runtime composition (`PostgresRepositoryRuntime`).

Live evidence in `src/empirical_platform/shared/bootstrap.py` (read in full before selecting scope):

- `FoundationRuntime` is the repository's one existing process-startup composition root, already composing `config`, `wall_clock`, `monotonic_clock`, `identifiers`, `logger`, `health`, and optionally `persistence: PersistenceService | None` and `object_storage: ObjectStorageService | None`, with an explicit `RuntimeLifecycleState` machine, a `close()` method that tears down owned resources in reverse initialization order via `_cleanup_initialized`, and a `refresh_health()` method that re-probes owned dependencies.
- Two of its four composition functions, `initialize_infrastructure_runtime` and `initialize_foundation_runtime_with_postgresql`, already construct a `PostgresPersistenceService` from `config.postgresql` (a `PostgreSQLConfigSnapshot` already resolved by `resolve_foundation_config`), call `.initialize()` on it, and store it on `FoundationRuntime.persistence`.
- **Neither function, nor `FoundationRuntime` itself, constructs or exposes a `PostgresRepositoryRuntime`.** A caller of either function today can only obtain the four M023 repository adapters by reaching into `runtime.persistence` and hand-constructing `PostgresRepositoryRuntime(runtime.persistence)` themselves — and `runtime.persistence`'s declared type is the abstract `PersistenceService` Protocol, not the concrete `PostgresPersistenceService` that `PostgresRepositoryRuntime.__init__` requires, so even that manual construction cannot be typed safely without an unchecked cast.
- `FoundationRuntime.close()`'s existing cleanup list is `[("object_storage", self.object_storage), ("persistence", self.persistence)]` — closing `persistence` already fully releases the engine/connection pool a `PostgresRepositoryRuntime` would depend on, since `PostgresRepositoryRuntime.close()` itself only ever delegates to that same `persistence.close()`.
- Existing test files `tests/unit/test_bootstrap.py`, `tests/unit/test_persistence_bootstrap.py`, and `tests/unit/test_object_storage_bootstrap.py` already establish the test pattern for this composition root, confirming this milestone is independently testable using the existing pattern.

M025's own Design Section 15 explicitly rejected "Application service first" as premature "because application services need a stable repository runtime composition boundary" and rejected "Bootstrap integration now" as premature "because no application entrypoint consumes the repository runtime yet." Both of those blockers were about the *repository runtime itself* not existing. It now does (M025). But a second, distinct blocker remains, revealed only by reading `bootstrap.py`: the one process-startup composition root that *does* exist has no way to obtain one. That is exactly the same class of "manual wiring gap" M025 itself was created to close for the four repository adapters over one `PostgresPersistenceService` — this milestone closes the same gap one layer up, for the `PostgresRepositoryRuntime` over the existing `FoundationRuntime`.

## 4. Candidate Inventory

| Candidate | Layer | Dependencies | Scope size | Risk | Decision |
| --- | --- | --- | --- | --- | --- |
| Foundation Runtime Repository Composition | Infrastructure composition | M025 frozen; `FoundationRuntime` already exists | Small | Low | Selected |
| Application Service Orchestration | Application layer | Requires a stable, bootable way to obtain `PostgresRepositoryRuntime` — not yet true even after M025 | Large | High | Rejected as premature |
| Application Command/Handler Contracts | Application layer | Same unmet precondition as above; would have to invent bootstrap wiring ad hoc inside the handler design | Medium | Medium-High | Rejected as premature |
| Optimistic-Concurrency Handling at Service Layer | Application policy | Requires application services to exist first (there is no "service layer" yet) | Medium | Medium | Rejected as premature |
| Retry Policy | Application policy | Explicitly depends on application services (M024/M025 designs both state this) | Medium | High | Rejected as premature |
| Audit Runtime Composition | Governance/runtime | Requires application-level evidence/review flows that do not exist yet | Large | High | Rejected as premature |

## 5. Candidate Comparison

| Criterion | Foundation Runtime Repository Composition | Application Services | Command/Handler Contracts | Retry Policy |
| --- | --- | --- | --- | --- |
| Architectural ordering | Directly follows M025 | Depends on this milestone | Depends on this milestone | Depends on application services |
| Dependency readiness | Ready | Not ready | Not ready | Not ready |
| Isolation | High (touches one existing file) | Medium | Medium | Medium |
| Independent testability | High (existing bootstrap test pattern) | Medium | Medium | Medium |
| Reversibility | High | Medium | Medium | Medium |
| Scope-creep risk | Low | High | High | High |
| Implementation confidence | High | Medium | Medium | Medium |

## 6. Selected Scope

MILESTONE-026 selects **Foundation Runtime Repository Composition**.

Purpose: extend the existing `FoundationRuntime` process-startup composition root, and its `initialize_infrastructure_runtime`/`initialize_foundation_runtime_with_postgresql` functions, to also construct and expose exactly one `PostgresRepositoryRuntime` alongside the persistence service it is already built from — using the identical eager-construction, stable-identity, and delegated-close discipline M025 already froze — so that a fully booted process has the four repository adapters available without any caller hand-wiring them.

## 7. Scope Boundary

Included:

- adding a `PostgresRepositoryRuntime`-typed field to `FoundationRuntime`;
- constructing it, exactly once, inside `initialize_infrastructure_runtime` and `initialize_foundation_runtime_with_postgresql`, from the exact same `PostgresPersistenceService` instance already constructed there;
- an explicit, frozen decision on whether `FoundationRuntime.close()` calls the new field's own `close()` or relies solely on the existing `persistence` cleanup entry (both are safe given `PostgresRepositoryRuntime.close()`'s pure delegation and `PostgresPersistenceService.close()`'s idempotence, but exactly one must be frozen, not left ambiguous);
- an explicit, frozen decision on whether `initialize_foundation_runtime` (the bare, no-persistence function) and `initialize_foundation_runtime_with_object_storage` require any change (evaluated in the Design);
- unit test coverage using the existing bootstrap test pattern;
- real-PostgreSQL integration coverage proving the composed runtime's repository adapters function against a real database end-to-end.

Excluded:

- application services, use-case orchestration, command/handler contracts;
- retry policy;
- APIs, workers, CLI entrypoints;
- any change to M020-M025 frozen contracts, adapters, mappers, schema, or the `PostgresRepositoryRuntime`/`run_composed` public surfaces themselves;
- Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior.

## 8. Dependencies

| Dependency | Role | Status |
| --- | --- | --- |
| M020 | Repository Protocol contracts | APPROVED AND FROZEN |
| M021 | Mapper contracts and durable records | APPROVED AND FROZEN |
| M022 | PostgreSQL schema/migration | APPROVED AND FROZEN |
| M023 | Concrete PostgreSQL repository adapters | APPROVED AND FROZEN |
| M024 | Multi-aggregate Unit of Work primitive | APPROVED AND FROZEN |
| M025 | Repository runtime composition | APPROVED AND FROZEN |

## 9. Architecture Constraints

- The new field and its construction must live entirely inside `src/empirical_platform/shared/bootstrap.py`; no new module is required.
- `bootstrap.py` already imports `PostgresPersistenceService` from `shared.persistence.postgres`; importing `PostgresRepositoryRuntime` from `shared.persistence.postgres_repositories.runtime` is a same-top-level-module (`shared`) import and requires no `tools/check_architecture.py` change, by the same exemption verified during M025's own review.
- No domain package (`campaign`/`run`/`evidence`/`review`) may import `bootstrap.py`'s new field or the `PostgresRepositoryRuntime` type — this milestone does not touch any domain package.

## 10. Transaction Constraints

- No new transaction coordinator, no reimplementation of `run_composed`, no retry. `FoundationRuntime` merely holds and exposes the object; it does not call `run_composed` itself.

## 11. Concurrency Constraints

- `PostgresRepositoryRuntime` and `PostgresPersistenceService` are unchanged by this milestone; their existing single-process, `ContextVar`-based concurrency semantics apply unmodified. `FoundationRuntime` itself introduces no new concurrency primitive.

## 12. Security Constraints

- No new credential handling; the `PostgresPersistenceService` instance is reused verbatim, and `PostgresRepositoryRuntime`'s existing repr-safety (no custom `__repr__`/`__str__`) is unaffected by being referenced from `FoundationRuntime`.

## 13. Test Obligations

A future implementation must prove:

- `FoundationRuntime`'s new field is constructed exactly once per `initialize_infrastructure_runtime`/`initialize_foundation_runtime_with_postgresql` call, over the exact same `PostgresPersistenceService` instance stored on `.persistence`;
- `initialize_foundation_runtime` (bare) and `initialize_foundation_runtime_with_object_storage` behave exactly as frozen by the Design's explicit decision for each;
- `FoundationRuntime.close()`'s frozen cleanup behavior for the new field;
- real PostgreSQL end-to-end: a runtime initialized via the real composition function exposes a working repository runtime whose four adapters can `get`/`add`/`save` against a real, migrated database;
- all existing `test_bootstrap.py`/`test_persistence_bootstrap.py`/`test_object_storage_bootstrap.py` tests pass unmodified;
- no M020-M025 regression.

## 14. Stop Conditions

STOP design work and return to scope selection if:

- `FoundationRuntime`'s existing lifecycle/cleanup contract cannot represent the new field without contradiction;
- the frozen close-cleanup decision cannot be made without inventing new lifecycle states beyond the existing `RuntimeLifecycleState` enum.

## 15. Acceptance Gate

The design is acceptance-ready only if it freezes, with no remaining ambiguity: the exact field name and type; exact construction order relative to `persistence`; the exact close-cleanup decision; the exact behavior of all four `initialize_*` functions; and exact test obligations.

## 16. Hostile Self-Review

1. **Does this quietly become "application services"?** No — `FoundationRuntime` never calls a repository method itself; it only holds and exposes the composition object, exactly as it already does for `persistence`/`object_storage`. Rejected as a scope concern.
2. **Does this require a new lifecycle state?** No — `PostgresRepositoryRuntime` has no independent lifecycle beyond the service it wraps; the existing `RuntimeLifecycleState` machine and `_cleanup_initialized` helper are sufficient, confirmed by reading both in full.
3. **Does this silently authorize bootstrap for workers/APIs?** No — no worker, API, or CLI entrypoint is touched; this milestone only extends an existing, already-process-agnostic composition root.
4. **Is double-close a real risk?** Reviewed: `PostgresRepositoryRuntime.close()` delegates purely to `persistence.close()`, which is already idempotent; calling both in `close()`'s cleanup list is provably harmless, but the Design must still pick one and freeze it explicitly rather than leaving both as equally-valid options.

## 17. Final Decision

```text
M026 FOUNDATION RUNTIME REPOSITORY COMPOSITION SCOPE SELECTED
M026 DESIGN READY FOR INDEPENDENT REVIEW
M026 NOT APPROVED
M026 NOT FROZEN
M026 IMPLEMENTATION NOT STARTED
```
