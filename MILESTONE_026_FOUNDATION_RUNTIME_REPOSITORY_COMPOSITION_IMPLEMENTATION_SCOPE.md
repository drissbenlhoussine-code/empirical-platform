# MILESTONE-026 - Foundation Runtime Repository Composition Implementation Scope

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-026-IMPLEMENTATION-SCOPE |
| Title | Foundation Runtime Repository Composition Implementation Scope |
| Status | Implementation in progress against frozen design |
| Frozen design | `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_DESIGN.md` (Version 1.1) |
| Design freeze | `MILESTONE_026_FOUNDATION_RUNTIME_REPOSITORY_COMPOSITION_DESIGN_FREEZE.md` |

## 2. Purpose

Confirm the frozen M026 design (Version 1.1, Sections 1-26) can be
implemented exactly as specified, with no contradiction discovered against
live repository evidence, before writing source code.

## 3. Confirmed Implementable Without Design Contradiction

Read in full immediately before implementation: the frozen Scope Selection,
the frozen corrected Design, the Design Freeze, `bootstrap.py` in its
entirety, `PostgresRepositoryRuntime`, `PostgresPersistenceService`,
`FakePersistenceService`, every existing bootstrap/infrastructure-runtime
test file, the M025 test suite, `tools/check_architecture.py`, and the
validation scripts. No contradiction was found between the frozen design and
the live state of any of these files:

- `FoundationRuntime`'s field ordering (`persistence`, `object_storage`, then
  private lifecycle fields) exactly matches the frozen field-insertion point.
- Both functions that construct a `PostgresPersistenceService`
  (`initialize_infrastructure_runtime`,
  `initialize_foundation_runtime_with_postgresql`) have an exact,
  unambiguous insertion point for the frozen `isinstance`-gated construction,
  immediately after the frozen ordering point (Section 8 of the Design).
- `PostgresRepositoryRuntime.__init__`'s existing `TypeError` guard is
  unchanged and unreachable from either function once the `isinstance` check
  is applied first, exactly as the frozen Error Taxonomy (Section 13)
  requires.
- Every existing test in `tests/unit/test_infrastructure_runtime.py` and
  `tests/unit/test_persistence_bootstrap.py` uses a `FakePersistenceService`
  (or subclass) override, confirming the `isinstance` rule leaves
  `repository_runtime` as `None` for all of them with zero behavioral change.
- `FoundationRuntime.close()`'s existing cleanup list needed no new entry,
  confirming the frozen close/cleanup decision (Section 15) required no
  contradiction to implement.
- Neither `PostgresPersistenceService` nor `PostgresRepositoryRuntime` nor any
  of the four concrete repository adapter classes define a custom `__repr__`
  or `__str__`, confirming the frozen repr/credential-safety rule (Section 16)
  describes already-true behavior, not a mechanism still to be built.

## 4. Scope Confirmed

Implementation is scoped to exactly:

- one new field and its import on `FoundationRuntime` in
  `src/empirical_platform/shared/bootstrap.py`;
- conditional construction inside `initialize_infrastructure_runtime` and
  `initialize_foundation_runtime_with_postgresql`;
- unit tests (SQLite-backed, dependency-free) and real-PostgreSQL integration
  tests;
- implementation documentation and a checkpoint update.

## 5. Non-Goals (unchanged from Design)

Application services, retry policy, APIs, workers, domain behavior, Audit
runtime, Decision Candidate, Decision Freeze, market-data/vendor/trading/
campaign execution behavior, any M020-M025 contract change, and any
MILESTONE-027 work.

## 6. Final Status

```text
M026 IMPLEMENTATION SCOPE CONFIRMED - NO DESIGN CONTRADICTION FOUND
```
