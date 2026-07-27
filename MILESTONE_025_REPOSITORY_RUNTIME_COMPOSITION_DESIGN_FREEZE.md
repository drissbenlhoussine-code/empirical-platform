# MILESTONE-025 - Repository Runtime Composition Design Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-025-DESIGN-FREEZE |
| Title | Repository Runtime Composition Design Freeze |
| Version | 1.0 |
| Status | M025 DESIGN APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Freeze closure only |
| New source code, tests, or repository-adapter changes made during this closure | No |

## 2. Authority Chain

| Role | Commit | Summary |
| --- | --- | --- |
| Frozen baseline | `b2283281f670703c95de0b6fe8ee83d58c5e3ac1` | chore: freeze MILESTONE-024 multi-aggregate unit of work (M024 APPROVED AND FROZEN) |
| Initial Design | `e9db9292982f3795cc51c29de290af2e34e1b33b` | Design MILESTONE-025 repository runtime composition |
| Design Correction | `ec6e8db23dddf20ae8ab2efec17908dc61a69be4` | Harden MILESTONE-025 repository runtime composition design |

Authoritative documents for this freeze:

- `MILESTONE_025_REPOSITORY_RUNTIME_COMPOSITION_SCOPE_SELECTION.md` (unchanged since initial design; the correction round required no scope-selection change beyond one non-blocking observation, `M025-DESIGN-REVIEW-0006`, requiring no correction);
- `MILESTONE_025_REPOSITORY_RUNTIME_COMPOSITION_DESIGN.md` (Version 1.1, the corrected and final design, including its Section 19 correction record and Section 19.1 hostile self-review).

Frozen baseline this design built on: MILESTONE-024 (implementation freeze commit `b2283281f670703c95de0b6fe8ee83d58c5e3ac1`), and, transitively, MILESTONE-020 through MILESTONE-023. None are reopened, rewritten, or reinterpreted by this design or its freeze.

## 3. Independent Review Outcome

The design went through one independent review round:

1. First round returned `M025 DESIGN REQUIRES NARROW CORRECTION` against initial design commit `e9db929`, with one MAJOR finding (repeated-access repository identity and eager-vs-lazy construction were left undefined) and four MINOR findings (context-manager behavior undefined; independent composition roots not explicitly tested; service-argument validation permissive with no exception type frozen; the service-initialization precondition left unstated), plus one non-blocking OBSERVATION (a scope-selection candidate-naming gap requiring no correction). All five findings were resolved in correction commit `ec6e8db`, recorded in full in `MILESTONE_025_REPOSITORY_RUNTIME_COMPOSITION_DESIGN.md` Section 19 (`M025-DESIGN-REVIEW-0001` through `0006`).
2. A second, final independent review of the corrected design returned:

```text
M025 DESIGN APPROVED FOR OWNER FREEZE
```

The Project Owner accepted that recommendation and authorized this design freeze closure.

## 4. Canonical Design Decisions (What Was Frozen)

- **Public class:** `PostgresRepositoryRuntime`, at module `empirical_platform.shared.persistence.postgres_repositories.runtime`.
- **Constructor:** `PostgresRepositoryRuntime(service: PostgresPersistenceService)`.
- **Constructor validates the exact `service` type before constructing any repository**, raising `TypeError` immediately for `None` or any non-`PostgresPersistenceService` value. No repository or other owned object is left partially constructed on this path.
- **The caller owns creation and initialization of `PostgresPersistenceService`.** The runtime performs no `initialize()` call, no connectivity probe, no migration, no schema check, no environment-variable parsing, and no engine creation. Readiness is enforced entirely by the existing, unmodified `PostgresPersistenceService._ensure_can_work` guard on first repository use — no new readiness API was invented.
- **All four concrete repository adapters (`PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository`) are constructed exactly once, inside `__init__`, each receiving the exact same supplied `PostgresPersistenceService` object.** No lazy reconstruction, no repository cache, no registry, no reflection, no string-keyed lookup, no generic `get_repository()`, no public service locator.
- **Repeated access to `.campaigns` / `.runs` / `.evidence_packages` / `.reviews` returns the identical object, by Python identity (`is`), for the runtime's whole lifetime**, including after `close()`.
- **`run_composed(operations)` delegates directly and exactly once to `self._service.run_composed(operations)`** — no second transaction coordinator, no reimplementation of M024 semantics.
- **`close()` delegates exactly once to `self._service.close()`** and is idempotent via the service's own existing idempotence. Repository properties keep returning the same stored objects after close; attempting an operation through them fails via the existing, unmodified service guard — no second lifecycle state machine.
- **Multiple independent `PostgresRepositoryRuntime` instances, each over its own distinct `PostgresPersistenceService`, may coexist in one process.** No global mutable runtime root exists anywhere in this design. Closing one root has no effect on another with a distinct service. Cross-root composition (a repository from one root's service joining another root's `run_composed` call) is rejected entirely by the existing, unmodified M024 same-service-identity rule (`scope.owner_service is self`) — this design introduces no new rejection mechanism.
- **No M020 Repository Protocol change, no M021 mapper/durable-record change, no M022 schema/migration change, no M023 concrete adapter behavior change, no M024 transaction-mechanism reimplementation.**
- **No application services, APIs, workers, retry policy, Audit runtime, Decision Candidate, Decision Freeze, or MILESTONE-026 work** is introduced or authorized by this design.

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
| `scripts/verify.ps1` (fresh, end-to-end) | PASS — `366 passed, 96 skipped`, coverage `82.15%` |
| `python -m build` | PASS |
| `git diff --check` | PASS |

(No implementation exists yet; this is a design-only closure. No M025-specific real-PostgreSQL evidence is captured at this freeze, since no implementation has been built — that evidence belongs to the implementation milestone this freeze authorizes.)

## 6. Accepted Non-Blocking Observations

Carried forward explicitly into the implementation milestone, not silently:

1. **A caller may deliberately construct two `PostgresRepositoryRuntime` instances sharing one `PostgresPersistenceService` object.** Closing either then affects both, since both share the one underlying service. This is a caller-introduced hazard, disclosed in Design Section 11, not defended against structurally — consistent with M024's own disclosed non-goals regarding caller misuse. `ACCEPTED, DISCLOSED IN DESIGN SECTION 11`.
2. **Service readiness is enforced entirely on first repository operation, through the existing `_ensure_can_work` guard, not through any new construction-time readiness API.** A caller who constructs the runtime against an uninitialized or already-closed service is not rejected at construction time. `ACCEPTED, DISCLOSED IN DESIGN SECTION 11`.
3. **PostgreSQL integration tests remain opt-in** (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`), unchanged convention from M022 through M024.
4. **`mypy` does not type-check `tests/`**, unchanged from M020 through M024.
5. **`setuptools`'s `project.license` TOML-table deprecation remains tracked**, unrelated to M025, unchanged from every prior freeze record.

## 7. What This Freeze Does Not Authorize

Freezing the M025 design authorizes exactly the composition mechanism specified in Section 4. It does not authorize, by this freeze alone:

- writing the implementation (authorized separately, by the same Owner decision, as the next mission phase — see Section 8);
- application services (Candidate F);
- retry-on-`OptimisticConcurrencyConflict` policy (Candidate J);
- any change to M020 Repository Protocols, M021 Mapper Protocols, M022 schema, or M023/M024 behavior;
- any MILESTONE-026 work.

## 8. Final Status

```text
M025 DESIGN APPROVED AND FROZEN
```

No frozen historical MILESTONE-025 document is rewritten by this closure; this document only adds the closure decision on top of them. The Project Owner has separately authorized MILESTONE-025 implementation to proceed immediately under this same mission, subject to its own hostile self-review, complete test coverage, and external review package before any implementation-approval or freeze decision — which remains a separate, later decision, not made by this document.
