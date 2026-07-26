# MILESTONE-024 - Multi-Aggregate Persistence Unit of Work Design Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-024-DESIGN-FREEZE |
| Title | Multi-Aggregate Persistence Unit of Work Design Freeze |
| Version | 1.0 |
| Status | M024 DESIGN APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Freeze closure only |
| New source code, tests, or repository-adapter changes made during this closure | No |

## 2. Authority Chain

| Role | Commit | Summary |
| --- | --- | --- |
| Frozen baseline | `4ce800d3609ba7c621eadffc338bc5bc2503228d` | chore: freeze MILESTONE-023 PostgreSQL repository adapters (M023 APPROVED AND FROZEN) |
| Initial Design | `f2a22817cb433142960dba6509c50b4b39066ebe` | Design MILESTONE-024 Multi-Aggregate Persistence Unit of Work |
| Design Correction | `03d640fa8e0f34fb3348226c4bc0eeaa386832b4` | Harden MILESTONE-024 multi-aggregate unit of work design |

Authoritative documents for this freeze:

- `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_SCOPE_SELECTION.md` (unchanged since initial design; the correction round required no scope-selection change);
- `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_DESIGN.md` (Version 1.1, the corrected and final design, including its Section 23 hostile self-review with 12 total findings across both rounds).

Frozen baseline this design built on: MILESTONE-023 (implementation freeze commit `4ce800d3609ba7c621eadffc338bc5bc2503228d`), and, transitively, MILESTONE-020 through MILESTONE-022. None are reopened, rewritten, or reinterpreted by this design or its freeze.

## 3. Independent Review Outcome

The design went through one independent review round:

1. First round returned `M024 DESIGN REQUIRES NARROW CORRECTION` against initial design commit `f2a2281`, with two CRITICAL findings (a public API shape that could expose a frozen-success-typed `SaveResult` before the composed transaction committed; an ambient `ContextVar` with no owning-service check, permitting cross-service transaction joining) and four MAJOR findings (failure-unsafe `ContextVar` cleanup; a dishonest concrete return-type annotation; an undefined same-identity operation matrix; an undefined mechanism for poisoning a composed scope after a swallowed inner failure) plus one MINOR finding (an unenforceable "handful of calls" phrasing). All seven were resolved in correction commit `03d640f`, recorded in full in `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_DESIGN.md` Section 23 (`M024-DESIGN-ISSUE-0006` through `0012`).
2. A second, final independent review of the corrected design returned:

```text
M024 DESIGN APPROVED FOR OWNER FREEZE
```

The Project Owner accepted that recommendation and authorized this design freeze closure.

## 4. Canonical Design Decisions (What Was Frozen)

- **Public API:** exactly one new public method, `PostgresPersistenceService.run_composed(operations: Sequence[Callable[[], object]]) -> tuple[object, ...]`. There is no other sanctioned public composition entry point; the composed-transaction machinery is private.
- **No M020 Repository Protocol signature change.** `get`/`add`/`save` remain exactly as frozen.
- **No M023 concrete repository adapter source-file change required.** All four adapters participate correctly with zero modification, since they only ever call `self._service.unit_of_work()` without inspecting its concrete type.
- **Exactly one real PostgreSQL transaction backs a composed scope**, however many operations run inside it.
- **The official result tuple is returned only after a successful commit.** No caller-visible result — including the result of an operation that itself already completed inside the transaction — is observable via `run_composed`'s own return path before that point.
- **Rollback and commit failure both produce no official result tuple**; the underlying exception propagates instead.
- **Callback side-channel leakage is explicitly disclosed and outside mechanical enforcement.** A caller who leaks an intermediate result out of their own `operations` callable via a captured variable, log line, or network call cannot be prevented from doing so by any API shape; this design guarantees only that its own official return path never does so.
- **The active composed scope is owned by the exact `PostgresPersistenceService` instance that opened it**, compared by Python object identity (`is`), never by configuration equality or a derived identity value.
- **A different service's `unit_of_work()` call is rejected with a safe `FoundationError`, before any SQL executes, and never joins.**
- **A poisoned scope forbids commit and further meaningful use**, even if the caller catches and swallows the failing operation's exception — the poisoning happens inside `_JoinedUnitOfWork.__exit__` the instant the failing operation's own `with` block exits, before the exception ever reaches the caller's own `try/except`.
- **`ContextVar` cleanup uses the token-based `set`/`reset` pattern inside `try`/`finally`**, covering entry failure, commit failure, and rollback failure, mirroring the pattern M023's own `_active_unit_of_work` already uses.
- **`PostgresPersistenceService.unit_of_work()` returns `PersistenceUnitOfWork`** (the existing, structurally-sufficient Protocol), not the concrete `PostgresUnitOfWork` class, since it can return either a real `PostgresUnitOfWork` or a `_JoinedUnitOfWork`.
- **Same-identity and nesting/service-identity behavior matrices are fully frozen** (Design Sections 11-12): 10 nesting/service rows and 8 same-identity rows, each with one deterministic, mechanism-traced outcome.
- **Standalone M023 behavior (no composed scope active) is unchanged, byte-for-byte**, from today's frozen behavior.

## 5. Final Validation Evidence

Captured fresh as part of this freeze closure (Phase 2):

| Gate | Result |
| --- | --- |
| Python | 3.13.14 (`.venv`) |
| `python -m compileall -q src tests tools migrations` | PASS |
| `ruff format --check .` / `ruff check .` | PASS |
| `mypy` | PASS, 0 issues, 79 source files |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `scripts/security.ps1` | PASS |
| `scripts/verify.ps1` (fresh, end-to-end) | PASS — `344 passed, 84 skipped`, coverage `81.69%` |
| `python -m build` | PASS |
| `git diff --check` | PASS |

(No implementation exists yet; this is a design-only closure. No M024-specific real-PostgreSQL evidence is captured at this freeze, since no implementation has been built — that evidence belongs to the future implementation milestone this freeze authorizes.)

## 6. Accepted Non-Blocking Observations

Carried forward explicitly into the future implementation milestone, not silently:

1. **Arbitrary Python callback side channels cannot be sandboxed.** A caller can always leak an intermediate, not-yet-committed result out of their own `operations` callable through ordinary Python side effects (a captured variable, a log call, a network call); this design's guarantee is scoped to its own official API surface, not to preventing all conceivable caller misuse. `ACCEPTED, DISCLOSED IN DESIGN SECTION 21`.
2. **The long-transaction operation-count/timeout concern remains non-enforced operational guidance**, not a mechanically enforced policy; an arbitrary enforced numeric cap was deliberately not invented without real usage data to justify one. `ACCEPTED, MAY BE REVISITED IF REAL USAGE DATA LATER JUSTIFIES A CONCRETE LIMIT`.
3. **Manually copied `contextvars.Context` objects reused concurrently elsewhere are outside this design's safe-concurrent-use guarantee.** `contextvars.ContextVar` isolation across independently-created threads/tasks is relied upon as-is; explicit context copying while a composed scope is active is a caller-introduced hazard this design does not defend against. `ACCEPTED, DISCLOSED IN DESIGN SECTION 21`.
4. **`mypy` does not type-check `tests/`**, unchanged from M020 through M023.
5. **PostgreSQL integration tests remain opt-in** (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`), unchanged convention from M022/M023.
6. **`setuptools`'s `project.license` TOML-table deprecation remains tracked**, unrelated to M024, unchanged from every prior freeze record.

## 7. What This Freeze Does Not Authorize

Freezing the M024 design authorizes exactly the composition mechanism specified in Section 4. It does not authorize, by this freeze alone:

- writing the implementation (authorized separately, by the same Owner decision, as the next mission phase — see Section 8);
- repository runtime composition (Candidate E);
- application services (Candidate F);
- retry-on-`OptimisticConcurrencyConflict` policy (Candidate J);
- any change to M020 Repository Protocols, M021 Mapper Protocols, or M022 schema;
- any change to any M023 concrete repository adapter's `get`/`add`/`save` external behavior;
- any MILESTONE-025 work.

## 8. Final Status

```text
M024 DESIGN APPROVED AND FROZEN
```

No frozen historical MILESTONE-024 document is rewritten by this closure; this document only adds the closure decision on top of them. The Project Owner has separately authorized MILESTONE-024 implementation to proceed immediately under this same mission, subject to its own hostile self-review, complete test coverage, and external review package before any implementation-approval or freeze decision — which remains a separate, later decision, not made by this document.
