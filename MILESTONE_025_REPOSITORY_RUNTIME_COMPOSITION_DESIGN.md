# MILESTONE-025 - Repository Runtime Composition Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-025-DESIGN |
| Title | Repository Runtime Composition Design |
| Version | 1.1 (narrow correction) |
| Status | DESIGN READY FOR INDEPENDENT RE-REVIEW |
| Repository baseline | `b2283281f670703c95de0b6fe8ee83d58c5e3ac1` |
| Implementation authorized | No |

Version 1.1 responds to an independent hostile review that returned "M025 DESIGN REQUIRES NARROW CORRECTION" (1 MAJOR + 4 MINOR findings). See Section 19 for the full account. No scope change, no implementation, no source-code modification.

## 2. Purpose

Define the repository runtime composition boundary that future implementation will use to obtain the four concrete PostgreSQL repository adapters as one coherent infrastructure unit backed by a single `PostgresPersistenceService`.

## 3. Design Inputs

| Input | Required by this design |
| --- | --- |
| M020 | Repository Protocol surfaces and error taxonomy remain unchanged |
| M021 | Mapper contracts and durable-record reconstruction remain unchanged |
| M022 | PostgreSQL schema/migration remains unchanged |
| M023 | Concrete PostgreSQL repository adapters are reused unchanged |
| M024 | `PostgresPersistenceService.run_composed(operations)` is the only cross-repository atomic execution primitive |

## 4. Architectural Problem

After M024, callers can compose multiple repository operations atomically only if they manually construct the correct repository adapter instances over the exact same `PostgresPersistenceService`. That manual wiring is now the next architectural gap: it is easy to accidentally mix services, construct only part of the repository set, or hide M024's same-service rule inside future application code.

M025 solves only that wiring gap.

## 5. Selected Design

Introduce a narrow PostgreSQL repository runtime composition object in the infrastructure layer.

The future object is conceptually named `PostgresRepositoryRuntime`. It owns no domain behavior. It exposes:

- `campaigns`;
- `runs`;
- `evidence_packages`;
- `reviews`;
- `run_composed(operations)`;
- `close()`.

The four repository attributes are concrete M023 PostgreSQL adapters constructed with the same `PostgresPersistenceService` instance. `run_composed(operations)` delegates directly to that same service's frozen M024 method.

**Frozen (Version 1.1, responding to `M025-DESIGN-REVIEW-0001`, MAJOR): construction is eager, once, and identity-stable.** All four concrete repository adapters are constructed exactly once, inside `PostgresRepositoryRuntime.__init__`, each receiving the exact same supplied `PostgresPersistenceService` instance. Each adapter is stored in one private final attribute. Every subsequent access to `.campaigns` / `.runs` / `.evidence_packages` / `.reviews` returns the identical object, by Python object identity (`is`), for the lifetime of the runtime instance. No repository is ever reconstructed lazily on property access. No repository cache, registry, reflection, string-keyed lookup, or dynamic mapper lookup is introduced anywhere in this design — the properties are plain read-only accessors over attributes fixed at construction time.

## 6. Package Placement

Future implementation belongs under:

```text
src/empirical_platform/shared/persistence/postgres_repositories/runtime.py
```

This placement is intentional because:

- the concrete repository adapters already live under `shared.persistence.postgres_repositories`;
- `shared` is the current infrastructure composition boundary for PostgreSQL persistence;
- no domain package should import a concrete PostgreSQL repository runtime;
- no application-service package exists yet.

## 7. Public Surface

The future public surface is intentionally small:

```text
PostgresRepositoryRuntime(
    service: PostgresPersistenceService,
)

.campaigns -> PostgresCampaignRepository
.runs -> PostgresRunRepository
.evidence_packages -> PostgresEvidencePackageRepository
.reviews -> PostgresReviewRepository
.run_composed(operations) -> tuple[object, ...]
.close() -> None
```

This is an infrastructure composition surface, not a domain contract. It must not alter or replace M020 repository Protocols.

**Frozen exact construction graph (Version 1.1, responding to `M025-DESIGN-REVIEW-0001`):**

```python
class PostgresRepositoryRuntime:
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

    @property
    def campaigns(self) -> PostgresCampaignRepository:
        return self._campaigns

    @property
    def runs(self) -> PostgresRunRepository:
        return self._runs

    @property
    def evidence_packages(self) -> PostgresEvidencePackageRepository:
        return self._evidence_packages

    @property
    def reviews(self) -> PostgresReviewRepository:
        return self._reviews

    def run_composed(self, operations: Sequence[Callable[[], object]]) -> tuple[object, ...]:
        return self._service.run_composed(operations)

    def close(self) -> None:
        self._service.close()
```

Exact names may follow repository-module conventions at implementation time, but the eager-construction, stable-attribute, plain-property shape above is frozen and must not be left open. No concrete mapper argument is passed to any repository constructor: all four M023 adapter constructors already default `mapper: XMapper | None = None` to the correct concrete mapper internally (verified directly against `campaign_repository.py`, `run_repository.py`, `evidence_package_repository.py`, `review_repository.py`), so this design introduces no new mapper-wiring responsibility.

**Underlying service exposure (Version 1.1, responding to `M025-DESIGN-REVIEW-0005`/`M025-DESIGN-REVIEW-0002`): the underlying `PostgresPersistenceService` is not publicly exposed.** `self._service` is a private attribute used only internally by `run_composed` and `close`. Nothing in this design's accepted responsibility (Section 8) requires exposing it, and not exposing it keeps `run_composed`/`close` as the only two sanctioned paths to the service, consistent with Section 9's requirement that the runtime not become a second transaction coordinator.

**No context-manager protocol (Version 1.1, responding to `M025-DESIGN-REVIEW-0002`, MINOR): `PostgresRepositoryRuntime` does not implement `__enter__`/`__exit__` and is not a context manager.** Lifecycle is managed explicitly through `close()` only, exactly matching `PostgresPersistenceService` itself, which likewise implements no context-manager protocol (verified directly against `postgres.py`: only `PostgresUnitOfWork`, `_JoinedUnitOfWork`, and `_ComposedTransaction` implement `__enter__`/`__exit__`; the service class does not). No hidden or automatic close occurs on any code path.

## 8. Ownership Rules

The runtime object owns:

- eager, one-time construction of the four concrete repository adapter instances at `__init__` time (Section 7), each stored on a stable private attribute;
- guarantee that all four adapters share the exact same `PostgresPersistenceService` object identity;
- mandatory validation that the supplied `service` constructor argument is an actual `PostgresPersistenceService` instance (Version 1.1, responding to `M025-DESIGN-REVIEW-0004`, MINOR);
- delegation of composed execution to that same service;
- idempotent close forwarding to the service.

**Frozen constructor validation (Version 1.1):** `service` must be an actual `PostgresPersistenceService` instance. `None` and any other incompatible value is rejected immediately, via `TypeError`, before any repository is constructed — no repository or other owned object is left partially constructed on this path (Section 7's frozen constructor performs the check as its first statement). `TypeError` is selected, not `FoundationError`, because no existing repository or persistence-service constructor in this codebase performs any runtime argument validation at all (verified directly: `PostgresCampaignRepository.__init__`, `PostgresRunRepository.__init__`, `PostgresEvidencePackageRepository.__init__`, `PostgresReviewRepository.__init__`, and `PostgresPersistenceService.__init__` all assign constructor arguments directly with no isinstance/None check) — there is no established repository convention requiring `FoundationError` for this case, so the standard Python convention for an incompatible constructor argument applies. `FoundationError` remains reserved, exactly as today, for persistence-operation failures surfaced through `unit_of_work()`/`run_composed()`, not for this constructor-time type check.

The runtime object does not own:

- configuration loading;
- secret handling;
- database migrations;
- schema creation;
- aggregate reconstruction;
- repository method semantics;
- application workflow decisions;
- retry policy;
- readiness or connectivity validation of the supplied service (Section 11).

## 9. Transaction Semantics

Single repository calls keep their existing M023 behavior: each method opens its own Unit of Work through `self._service.unit_of_work()`.

Cross-repository atomic work must use:

```text
runtime.run_composed(operations)
```

The runtime must not implement its own transaction manager. It must call:

```text
self._service.run_composed(operations)
```

and return the tuple produced by M024 only after the underlying composed transaction commits.

## 10. Error Semantics

Repository methods continue to surface the frozen M020 repository error taxonomy through the frozen M023 adapters.

M024 composition failures continue to surface through `FoundationError` or the already-translated repository error raised by the failing operation.

M025 must not add a new error taxonomy unless a future implementation review proves a narrow construction-time error cannot be represented by existing foundation errors. The one narrow exception is the constructor's `TypeError` for an incompatible `service` argument (Section 8), which is a Python-level argument-type check preceding any persistence operation, not a persistence-domain error, and is therefore correctly outside the `FoundationError` taxonomy rather than an addition to it.

## 11. Lifecycle Semantics

Construction is side-effect light:

- it must validate that the supplied `service` is an actual `PostgresPersistenceService` instance, raising `TypeError` immediately otherwise (Section 8) — this replaces the prior permissive "may validate ... is not `None`" wording (Version 1.1, responding to `M025-DESIGN-REVIEW-0004`);
- it must not open a database connection merely to prove readiness;
- it must not run migrations;
- it must not emit health status.

**Frozen readiness policy (Version 1.1, responding to `M025-DESIGN-REVIEW-0005`, MINOR).** `PostgresRepositoryRuntime` performs no independent readiness check of the supplied service at all, and does not call `service.initialize()`. This was decided by inspecting the actual `PostgresPersistenceService` implementation rather than inventing a new API: the only currently-public readiness-adjacent method, `check()`, performs a live connectivity probe (`self._probe()`, opening a real connection and executing `SELECT 1`) — exactly the kind of readiness probe this design already forbids the runtime from performing — and the only fields that record initialized/closed state, `_initialized`/`_closed`, are private. No new public readiness property is introduced merely for this design.

Instead, the runtime relies entirely on the existing, unmodified `PostgresPersistenceService._ensure_can_work` guard, which every M023 repository method already triggers internally via `self._service.unit_of_work()` (and which `run_composed` also triggers directly). If the supplied service has not yet had `initialize()` called on it, the first repository operation attempted through the runtime raises the existing `FoundationError("Persistence service is not initialized")`; if the service has been closed, the first operation raises the existing `FoundationError("Persistence service is closed")`. Both are produced by code already frozen by M023/M024, unchanged by this design.

**The caller owns `PostgresPersistenceService` creation and initialization.** The service supplied to `PostgresRepositoryRuntime` must already have had `initialize()` called on it successfully before construction, exactly as any other caller of the frozen M023 adapters or the frozen M024 `run_composed` primitive is already required to do today. This design does not change that precondition; it only makes explicit that the runtime does not perform it on the caller's behalf.

`close()` delegates to the shared `PostgresPersistenceService.close()` exactly once and is idempotent because the service close operation is already expected to be safe to call repeatedly (verified: `PostgresPersistenceService.close()` returns immediately if `self._closed` is already `True`).

**Frozen post-close behavior (Version 1.1, responding to `M025-DESIGN-REVIEW-0001`/`M025-DESIGN-REVIEW-0002`).** The repository properties continue to return the exact same stored objects after `close()` — closing does not clear, invalidate, or replace the stored attributes, since Section 5 already requires their identity to remain stable for the runtime's whole lifetime regardless of lifecycle state. Attempting to actually *use* a returned repository (calling `get`/`add`/`save`, which internally opens a unit of work) fails through the existing, unmodified `_ensure_can_work` guard exactly as it already does for any other caller of a closed `PostgresPersistenceService` — this is the same mechanism named above for the uninitialized case, not a new one. `PostgresRepositoryRuntime` does not invent a second lifecycle state machine layered on top of the service's own.

Repeated `close()` calls are safe (idempotent via the service's own idempotence). `run_composed()` after close fails the same way any other post-close service operation does today, through the same guard.

Two independent runtime roots, each wrapping its own distinct `PostgresPersistenceService`, are fully independent: closing one has no effect on the other, since each root's `close()` only ever touches the one service instance it was constructed with. (If a caller deliberately constructs two `PostgresRepositoryRuntime` instances over the *same* shared service object, closing either affects both, because both share the one underlying service — this is the same caller-introduced-sharing hazard already accepted, and not specially defended against, elsewhere in this codebase's frozen designs, e.g. M024 Design Section 21's disclosed non-goals; it is not a defect in this design.)

## 12. Identity and Scope Integrity

The runtime composition must preserve:

- governance/runtime identity separation;
- `DomainIdentity[...]` inputs at repository boundaries;
- runtime UUID behavior already frozen in aggregate and repository layers;
- M024 same-service owner isolation.

It must not add cross-aggregate invariants or validate that a Campaign, Run, EvidencePackage, and Review belong together. Those are future application-service concerns.

## 13. Compatibility With M020 Through M024

| Prior milestone | Compatibility rule |
| --- | --- |
| M020 | No Protocol signature changes |
| M021 | No mapper Protocol or durable-record changes |
| M022 | No schema or migration changes |
| M023 | No repository adapter behavior changes |
| M024 | No transaction mechanism reimplementation |

## 14. Validation Obligations for Future Implementation

Future implementation must include tests proving:

**Construction and identity**

- all four repositories are exposed, of the exact concrete types named in Section 7;
- all four repositories are constructed exactly once, during `__init__`, not lazily;
- repeated access to each property returns the exact same object, verified via `is`;
- all four repositories share the exact same `PostgresPersistenceService` object identity;
- no dynamic registry, cache, reflection, or string-keyed lookup is used to obtain a repository.

**Constructor validation (Version 1.1)**

- `service=None` is rejected immediately with `TypeError`, before any repository is constructed;
- a non-`PostgresPersistenceService` value is rejected the same way;
- a valid `PostgresPersistenceService` instance constructs successfully.

**Readiness precondition (Version 1.1)**

- a service that has not had `initialize()` called on it is accepted at construction time (no readiness check performed), but the first repository operation attempted through it raises the existing `FoundationError("Persistence service is not initialized")`;
- a closed service is likewise accepted at construction time, but the first repository operation raises the existing `FoundationError("Persistence service is closed")`.

**Lifecycle**

- `run_composed` delegates exactly once to the service primitive;
- `close()` is idempotent and delegates to the service's own idempotent `close()`;
- repository properties still return the same stored objects after `close()`, but attempting an operation through them fails via the existing service guard;
- `run_composed()` after `close()` fails the same way;
- `PostgresRepositoryRuntime` does not implement `__enter__`/`__exit__`.

**Independent roots (Version 1.1, responding to `M025-DESIGN-REVIEW-0003`, MINOR)**

- two `PostgresRepositoryRuntime` instances, each constructed over its own distinct `PostgresPersistenceService`, coexist in one process without interference;
- each root's four repositories remain distinct from the other root's;
- closing one root does not close, invalidate, or otherwise affect the other root or its repositories;
- a repository from one root and a repository from a different root's service cannot participate in the same `run_composed` call — this is rejected by the existing, unmodified M024 same-service-identity rule (`scope.owner_service is self`), not by any new check this design introduces.

**Regression**

- no repository Protocol signature changes;
- no schema, migration, API, worker, retry, Audit, Decision Candidate, Decision Freeze, market-data, vendor, trading, or campaign execution behavior;
- all existing M023 and M024 tests pass unmodified.

Real PostgreSQL validation is required because the object composes concrete PostgreSQL adapters. The minimum integration proof is one composed operation involving at least two exposed repositories over the same disposable PostgreSQL instance, plus one test constructing and exercising two independent runtime roots against that same instance.

## 15. Rejected Alternatives

| Alternative | Rejection reason |
| --- | --- |
| Application service first | Premature; application services need a stable repository runtime composition boundary |
| Global dependency injection container | Too broad and likely to obscure ownership |
| Retry policy first | Depends on application service orchestration and would risk hidden transaction retries |
| Generic repository factory | Broader than needed and weaker than a concrete PostgreSQL runtime over frozen adapters |
| Bootstrap integration now | Premature; no application entrypoint consumes the repository runtime yet |

## 16. Deferred Items

- application services;
- retry-on-optimistic-concurrency policy;
- bootstrap wiring into an application entrypoint;
- APIs and workers;
- query/read-model projections;
- Audit runtime;
- Decision Candidate and Decision Freeze;
- market-data, vendor, trading, and empirical campaign execution behavior.

## 17. Risk Register

| Issue | Severity | Mitigation |
| --- | --- | --- |
| M025-DESIGN-RISK-0001: runtime composition drifts into application orchestration | MAJOR | Keep surface limited to repository exposure and M024 delegation |
| M025-DESIGN-RISK-0002: future implementation reimplements transaction semantics | MAJOR | Require direct delegation to `PostgresPersistenceService.run_composed` |
| M025-DESIGN-RISK-0003: future implementation silently changes M020/M023 behavior | MAJOR | Require unchanged Protocols/adapters and regression tests |
| M025-DESIGN-RISK-0004: generic DI container scope creep | MINOR | Reject global container until real consumers exist |
| M025-DESIGN-RISK-0005 (Version 1.1): future implementation reconstructs a repository lazily on each property access instead of once at construction | RESOLVED | Section 5/7 freeze eager, one-time construction with stable-identity properties; Section 14 requires an `is`-based regression test |
| M025-DESIGN-RISK-0006 (Version 1.1): future implementation invents a new readiness/initialization API on `PostgresPersistenceService` merely to support this design | RESOLVED | Section 11 freezes reliance on the existing, unmodified `_ensure_can_work` guard; no new service API introduced |

## 18. Acceptance Criteria

M025 design is acceptable only if an independent review confirms:

- the selected scope follows M024's deferred Candidate E;
- no implementation is present;
- no frozen prior milestone is rewritten;
- the design preserves all M020-M024 contracts;
- the future implementation boundary is narrow and independently testable;
- M025 remains not approved, not frozen, and not implemented.

## 19. Version 1.1 Independent Review Correction Record

An independent hostile review of Version 1.0 returned "M025 DESIGN REQUIRES NARROW CORRECTION" with 1 MAJOR and 4 MINOR findings, plus one non-blocking OBSERVATION. All five findings are corrected in this version; no scope change, no implementation, and no source-code modification was made.

| Finding | Severity | Section | Correction |
| --- | --- | --- | --- |
| `M025-DESIGN-REVIEW-0001`: repeated-access identity and eager-vs-lazy construction undefined | MAJOR | §5, §7, §14 | Froze eager, one-time construction at `__init__`; froze the exact constructor code; froze stable-identity properties; added an `is`-based test obligation |
| `M025-DESIGN-REVIEW-0002`: context-manager behavior undefined | MINOR | §7 | Froze that `PostgresRepositoryRuntime` does not implement `__enter__`/`__exit__`, consistent with `PostgresPersistenceService` itself (verified: neither implements the protocol) |
| `M025-DESIGN-REVIEW-0003`: independent composition roots not explicitly tested | MINOR | §11, §14 | Froze independent-root close semantics explicitly; added test obligations for coexistence, independent closing, and cross-root rejection under the existing M024 rule |
| `M025-DESIGN-REVIEW-0004`: service validation permissive, exception type undefined | MINOR | §8, §11 | Froze mandatory `TypeError` validation of the `service` constructor argument, justified against the verified absence of any existing repository/service constructor-validation convention |
| `M025-DESIGN-REVIEW-0005`: service initialization precondition unstated | MINOR | §11 | Froze that the runtime performs no readiness check and relies entirely on the existing, unmodified `_ensure_can_work` guard; froze that the caller owns calling `service.initialize()` before construction; explicitly declined to invent a new readiness API, after inspecting the real `PostgresPersistenceService` implementation and confirming `check()` performs a live probe (unsuitable) and `_initialized`/`_closed` are private |
| `M025-DESIGN-REVIEW-0006`: "service-level optimistic-concurrency handling" not named as its own compared scope-selection candidate | OBSERVATION | Scope Selection §4 | No correction required — the underlying concern is already fully handled at the M020/M023 adapter level (`save(expected_persisted_version=...)`); this was a naming gap only, not a substantive omission |

### 19.1 Hostile Self-Review of This Correction

Attacked the corrected design for every failure mode the correction mission named:

- **Lazy repository reconstruction still possible** — checked: Section 7's frozen constructor assigns all four repositories to private attributes at `__init__`; the properties are plain read-only accessors with no reconstruction logic. No defect.
- **Mismatched service instance** — checked: the frozen constructor passes the single `service` parameter to all four repository constructors verbatim; there is no second code path or parameter through which a different instance could enter. No defect.
- **Accidental global singleton** — checked: no module-level state was introduced by this correction; the frozen constructor is a plain instance method. No defect.
- **Incomplete runtime after constructor failure** — checked: the frozen constructor validates `service` as its first statement, before any repository is constructed, so a `TypeError` leaves no partially-constructed runtime. No defect.
- **Uninitialized service silently accepted with unsafe behavior** — checked: it is accepted at construction (by design, to avoid a new readiness API), but the first real operation fails safely through the existing, unmodified `FoundationError` guard; this is unchanged M023/M024 behavior, not a new gap. No defect.
- **Hidden service initialization** — checked: Section 11 explicitly states the runtime never calls `initialize()`. No defect.
- **Ambiguous close behavior** — checked: Section 11 now states the exact behavior for repeated close, post-close property access, post-close operation attempts, and independent-root closing. No defect.
- **Context-manager invention** — checked: Section 7 explicitly states no `__enter__`/`__exit__` is implemented. No defect.
- **Dynamic registry** — checked: Section 5/7 explicitly rule out any cache, registry, reflection, or string-keyed lookup. No defect.
- **Application-service leakage** — checked: no change to Section 8's "does not own" list or Section 9's transaction-delegation requirement. No defect.
- **Retry ownership** — checked: retry policy remains explicitly excluded (Section 8, Section 16, unchanged). No defect.
- **M026 leakage** — checked: no MILESTONE-026 concept, scope, or code appears anywhere in this correction. No defect.

No further defect found. This correction is documentation-only: no file under `src/`, `tests/`, or `tools/` was read for the purpose of modification, only for verification of claims made in this document against the real, current, frozen source.

## 20. Final Status

```text
M025 DESIGN NARROW CORRECTION COMPLETE
M025 DESIGN READY FOR INDEPENDENT RE-REVIEW
M025 NOT APPROVED
M025 NOT FROZEN
M025 IMPLEMENTATION NOT STARTED
```
