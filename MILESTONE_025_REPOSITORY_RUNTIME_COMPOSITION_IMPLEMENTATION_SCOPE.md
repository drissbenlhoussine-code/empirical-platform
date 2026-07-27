# MILESTONE-025 - Repository Runtime Composition Implementation Scope

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-025-IMPL-SCOPE |
| Title | Repository Runtime Composition Implementation Scope |
| Version | 1.0 |
| Status | IMPLEMENTATION SCOPE SELECTED |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `fe4f04483cb5fdc6b5cf08e0fe0eeebbe4e827ad` |
| Baseline status | MILESTONE-025 DESIGN APPROVED AND FROZEN |
| Mission type | Implementation scope confirmation only |

## 2. Purpose

MILESTONE-025's Design (Version 1.1, frozen) already fully specifies what an implementation must build (Sections 5-14), including exact frozen source code for the constructor and public surface (Section 7). This document does not re-derive scope; it confirms the frozen design is implementable exactly as written, with zero deviation.

## 3. Confirmed Implementable Without Design Contradiction

Verified against live repository evidence before writing any code:

- `PostgresPersistenceService` (`src/empirical_platform/shared/persistence/postgres.py`) read in full: confirmed a plain class (not `@dataclass`), so `isinstance()` validation works normally; confirmed `close()` is idempotent (`if self._closed: return`); confirmed `check()` performs a live connectivity probe (unsuitable for construction-time readiness, exactly as the frozen design states); confirmed `_initialized`/`_closed` are private; confirmed `_ensure_can_work` raises the exact `FoundationError` messages the design cites; confirmed no `__enter__`/`__exit__` exists on the service class itself; confirmed `scope.owner_service is self` (the M024 same-service-identity rule) is unchanged.
- All four M023 repository adapter constructors (`PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository`) read in full: confirmed each defaults `mapper: XMapper | None = None` to the correct concrete mapper internally, confirming the frozen design's claim that no new mapper-wiring responsibility exists.
- `tools/check_architecture.py` read in full: confirmed same-top-level-module (`shared`) imports are unconditionally exempt from the `ALLOWED` check outside `shared/domain/`, confirming the frozen design's implicit claim that zero architecture-checker changes are required.
- The sibling `postgres_repositories/__init__.py` read in full: confirmed it exports none of the four existing repository adapters (only submodule imports are used throughout the codebase), establishing the precedent followed here — `PostgresRepositoryRuntime` is likewise not re-exported at the package level.

No contradiction between the frozen Design and live M020-M024 code was found. Implementation proceeded without a stop-condition trigger.

## 4. Scope Confirmed

Exactly the frozen Design's Sections 5-14:

- `PostgresRepositoryRuntime` class at `src/empirical_platform/shared/persistence/postgres_repositories/runtime.py`, matching the frozen constructor and public-surface code in Design Section 7 verbatim;
- `tests/unit/test_m025_repository_runtime.py` (SQLite-backed, mechanism-level);
- `tests/integration/test_m025_postgres_repository_runtime.py` (real-PostgreSQL, using the actual frozen M023 adapters).

## 5. Non-Goals (unchanged from Design)

Application services, retry policy, APIs, workers, schema/migration changes, M020-M024 behavior changes, and any MILESTONE-026 work remain out of scope, exactly as the frozen Design Section 16 states.

## 6. Final Status

```text
IMPLEMENTATION SCOPE SELECTED — PROCEEDING TO IMPLEMENTATION
```
