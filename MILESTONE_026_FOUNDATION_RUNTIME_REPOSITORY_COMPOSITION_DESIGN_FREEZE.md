# MILESTONE-026 - Foundation Runtime Repository Composition Design Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-026-DESIGN-FREEZE |
| Title | Foundation Runtime Repository Composition Design Freeze |
| Status | M026 DESIGN APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Freeze closure only |
| New source code, tests, or runtime changes made by this closure | No |

## 2. Authority Chain

| Role | Commit | Summary |
| --- | --- | --- |
| Initial Design | `110bdab25a7867798ec1d14faba816f22738a7d2` | Design MILESTONE-026 Foundation Runtime Repository Composition |
| Design Correction | `1664c8e17cedac80715b9eb82ffff14620423191` | Harden MILESTONE-026 Foundation Runtime Repository Composition design |

Independent review outcomes:

1. First independent hostile review of the initial design (`110bdab`) found exactly two MINOR documentation-completeness findings — repr/credential-safety rule and test obligation not stated explicitly; post-construction failure-and-cleanup semantics not explicitly narrated — and no scope, ownership, construction-order, or close-semantics defect. Recommendation: `M026 DESIGN REQUIRES NARROW CORRECTION`.
2. The Project Owner authorized a narrow correction addressing exactly those two findings. Commit `1664c8e` added Section 16 (Repr and Credential Safety), a fourth bullet to Section 14 (Failure Behavior) covering the post-construction-failure case, two new Test Strategy obligations (Section 18 Items 9-10), two new Acceptance Criteria items (Section 21 Items 7-8), two new Risk Register rows (Section 23), and a Version 1.1 correction record with its own hostile self-review (Section 24/24.1). No canonical Version 1.0 decision was reopened, reversed, or reinterpreted.
3. The Project Owner's final independent recommendation, accepted in this mission's authorization, is:

```text
M026 DESIGN APPROVED FOR OWNER FREEZE
```

Authoritative documents for this freeze:

- `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_SCOPE_SELECTION.md`;
- `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_DESIGN.md` (Version 1.1);
- `PROJECT_CHECKPOINT.md` (M026 review-status fields).

Frozen baseline this design built on: MILESTONE-025 implementation freeze commit `0d57c36adf8b60ea3be9e86fa3814d1e2b459253`. That freeze is not reopened, rewritten, or reinterpreted by this closure.

## 3. Canonical Frozen Decisions

The following are frozen exactly as specified by the corrected Version 1.1 design and may not be reinterpreted or redesigned during implementation without a fresh design correction:

1. `FoundationRuntime` gains exactly one new field:

   ```python
   repository_runtime: PostgresRepositoryRuntime | None = None
   ```

   positioned immediately after `object_storage` and before the private
   `_state`/`_lifecycle_events` fields.

2. `initialize_foundation_runtime` produces `repository_runtime=None` (this function never constructs persistence at all).
3. `initialize_foundation_runtime_with_object_storage` produces `repository_runtime=None` (this function never constructs persistence at all).
4. `initialize_infrastructure_runtime` constructs `PostgresRepositoryRuntime` only when `isinstance(persistence_service, PostgresPersistenceService)` is true.
5. `initialize_foundation_runtime_with_postgresql` follows the identical `isinstance` rule.
6. Construction happens only after persistence initialization/readiness has already succeeded (immediately after `_require_dependency_ready(persistence_service, layer="persistence")` in `initialize_infrastructure_runtime`; immediately after `persistence_service.initialize()` in `initialize_foundation_runtime_with_postgresql`).
7. The exact same `PostgresPersistenceService` instance is passed to `PostgresRepositoryRuntime` and stored on `FoundationRuntime.persistence` — no second persistence service is ever created.
8. `FakePersistenceService` and any other non-`PostgresPersistenceService` implementation produce `repository_runtime=None`, silently, with no error, warning, or log line.
9. No transaction semantics change; no new coordinator; no reimplementation of `run_composed`.
10. No retry policy is introduced.
11. No application services, APIs, workers, domain behavior, or any MILESTONE-027 work is introduced or authorized.
12. `repository_runtime` owns no independent external resource beyond the `PostgresPersistenceService` it wraps.
13. `FoundationRuntime.close()` continues to close `persistence` only, through its existing, unmodified cleanup list; no separate `repository_runtime` cleanup entry is added.
14. No double-close path is introduced by this milestone.
15. After `close()`, `repository_runtime` remains an accessible, `is`-stable reference; operations attempted through it subsequently fail via the existing, unmodified `PostgresPersistenceService._ensure_can_work` closed-service guard.
16. If a later bootstrap step fails after `repository_runtime` has already been constructed: no `FoundationRuntime` is returned; the local `repository_runtime` reference is discarded with the failing stack; `persistence` remains the single resource owner; the existing `initialized`-resource cleanup path closes `persistence` (and `object_storage`, if constructed); no separate `repository_runtime` cleanup call is made; no global or cached partial runtime remains.
17. `FoundationRuntime`'s repr, and every nested `repository_runtime`/repository-adapter repr, must not expose database URLs, credentials, `Engine` configuration, or connection details.
18. The future implementation must add secret-marker repr regression tests proving Item 17.

## 4. Accepted Non-Blocking Observations

Carried forward explicitly, not silently:

1. PostgreSQL integration tests remain opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`.
2. `mypy` does not type-check `tests/` under the current project configuration.
3. Focused subset pytest runs may require `--no-cov` when the project-wide coverage fail-under is not meaningful for a single test file.
4. `setuptools` emits a non-blocking `project.license` TOML-table deprecation warning during `python -m build`; tracked for a future packaging cleanup, unrelated to M026.
5. Deliberately sharing one `PostgresPersistenceService` across two independently constructed repository-composition roots (whether hand-built via M025 or bootstrap-composed via M026) remains a caller-created hazard, already disclosed by the M025 design and unchanged by this milestone.

## 5. What This Freeze Does Not Authorize

Freezing the M026 design does not authorize:

- any implementation deviating from Section 3's canonical decisions without a fresh design correction;
- application services, use-case orchestration, APIs, or workers;
- automatic retry policy;
- any change to M020-M025 frozen contracts, adapters, mappers, schema, or the `PostgresRepositoryRuntime`/`run_composed` public surfaces;
- Audit runtime, Decision Candidate, or Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- MILESTONE-027 work of any kind;
- approval or freeze of the M026 *implementation* — that remains a separate, later gate.

## 6. Final Status

```text
M026 DESIGN APPROVED AND FROZEN
```

Implementation may now proceed strictly within the boundaries frozen in Section 3, subject to its own independent review, approval, and freeze before any MILESTONE-027 work begins.
