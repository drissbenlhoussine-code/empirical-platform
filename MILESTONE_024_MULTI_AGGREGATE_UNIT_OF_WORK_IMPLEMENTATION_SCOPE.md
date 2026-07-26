# MILESTONE-024 - Multi-Aggregate Persistence Unit of Work Implementation Scope

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-024-IMPL-SCOPE |
| Title | Multi-Aggregate Persistence Unit of Work Implementation Scope |
| Version | 1.0 |
| Status | IMPLEMENTATION SCOPE SELECTED |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `ed0a4198dab515c4d204f3046ea2cfc114390bef` |
| Baseline status | M024 DESIGN APPROVED AND FROZEN |
| Mission type | Implementation scope confirmation only |

## 2. Purpose

MILESTONE-024's Design (Version 1.1, frozen) already fully specifies what an implementation must build (Sections 5-22). This document does not re-derive scope; it confirms the frozen design was implementable exactly as written, with zero deviation, against the real M023 repository adapters and the real `PostgresUnitOfWork`.

## 3. Confirmed Implementable Without Design Contradiction

Verified against live repository evidence before writing any code:

- `PostgresUnitOfWork` (`src/empirical_platform/shared/persistence/postgres.py`) read in full: its module-level `_active_unit_of_work: ContextVar[bool]` reentrancy guard, its `__enter__`/`__exit__`/`execute`/`commit`/`rollback`/`_ensure_active`/`_complete`/`_reset_context` methods, and its existing `translate_persistence_error`/`_safe_message_for` error-translation helpers, all confirmed unchanged in shape and reusable as-is;
- `PersistenceUnitOfWork` Protocol (`empirical_platform.shared.interfaces.persistence`) read and confirmed structurally satisfied by both `PostgresUnitOfWork` (already) and a new `_JoinedUnitOfWork` (via Python structural typing, no explicit inheritance needed);
- all four M023 repository adapters (`PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository`) read in full: every `get`/`add`/`save` method calls exactly `with self._service.unit_of_work() as work:` and never inspects the concrete type of `work`, confirming zero adapter source changes are required for those adapters to participate correctly in a composed scope;
- `tools/check_architecture.py` read and confirmed the new private types require no new architecture-boundary carve-out, since they live inside the already-permitted `shared.persistence` module;
- no field, method, or invariant in any of the above required a durable-record or repository-contract concept the frozen Design did not anticipate.

No contradiction between the frozen Design and live M020/M023 code was found. Implementation proceeded without a stop-condition trigger.

## 4. Scope Confirmed

Exactly the frozen Design's Sections 5-14, implemented entirely within one existing file, `src/empirical_platform/shared/persistence/postgres.py`:

- `_ComposedScopeState` (`Enum`: `ACTIVE`, `POISONED`);
- `_ActiveComposedScope` (`@dataclass(slots=True)`: `owner_service`, `unit_of_work`, `state`);
- module-level `_active_composed_scope: ContextVar[_ActiveComposedScope | None]`;
- `_JoinedUnitOfWork` (private, structurally satisfies `PersistenceUnitOfWork`);
- `_ComposedTransaction` (private, owns exactly one real `PostgresUnitOfWork` per composed scope);
- `PostgresPersistenceService.unit_of_work()` modified to return `PersistenceUnitOfWork` and to join an owned active composed scope;
- `PostgresPersistenceService.run_composed(operations: Sequence[Callable[[], object]]) -> tuple[object, ...]` (the one new public method).

## 5. Non-Goals (unchanged from Design)

No M020 Repository Protocol change, no M023 concrete adapter source change, no schema/migration change, no application service, no retry-on-conflict policy, no repository runtime composition (Candidate E), and no MILESTONE-025 work. Confirmed: `git diff` against the frozen baseline touches exactly one source file (`src/empirical_platform/shared/persistence/postgres.py`, +138/-3 lines); zero files under `src/empirical_platform/{campaign,run,evidence,review}/` or `src/empirical_platform/shared/persistence/postgres_repositories/` were modified.

## 6. Final Status

```text
IMPLEMENTATION SCOPE SELECTED — PROCEEDING TO IMPLEMENTATION
```
