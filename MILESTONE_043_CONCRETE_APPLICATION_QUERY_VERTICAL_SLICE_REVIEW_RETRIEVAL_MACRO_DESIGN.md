# MILESTONE-043 - Concrete Application Query Vertical Slice: Review Retrieval - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN.** Produced in the same consolidated M043 mission as the scope document (`MILESTONE_043_..._MACRO_SCOPE.md`).

## 2. Design Goal

Retrieve one existing `Review` by full frozen identity, returning a bounded, immutable read-side snapshot — mirroring `GetEvidencePackageQuery`/`GetEvidencePackageHandler` (M037) field-for-shape, adapted for `Review`'s own identity/reference/state model.

## 3. Query Contract

```python
@dataclass(frozen=True, slots=True)
class GetReviewQuery:
    identity: DomainIdentity[ReviewId]
```

Exactly one field, identical shape to `GetEvidencePackageQuery`/`GetRunQuery`/`GetCampaignQuery`. No filter, no projection selector, no pagination.

## 4. Handler Contract

```python
class GetReviewHandler:
    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, query: GetReviewQuery) -> ReviewSnapshot:
        loaded = self._review_repository.get(query.identity)
        return ReviewSnapshot(
            identity=loaded.aggregate.identity,
            target_evidence_package_id=loaded.aggregate.target.evidence_package_id,
            reviewer_reference=loaded.aggregate.reviewer.value,
            state=loaded.aggregate.state,
        )
```

Exactly one dependency: `ReviewRepository`. No `EvidencePackageRepository`, no concrete adapter, no second repository of any kind.

## 5. Identity Model

`query.identity` (a `DomainIdentity[ReviewId]`) is passed to `review_repository.get()` unchanged — identical object identity, not a reconstructed copy, mirroring the frozen M037 pattern.

## 6. Result Contract Analysis

Mirroring `EvidencePackageSnapshot`'s deliberately bounded shape (identity + FK-parent reference + lifecycle state only, excluding `version`, `persisted_version`, owned collections, and `transition_history`), the same exclusions apply for `Review`:

- `findings` — excluded (unbounded owned collection, no milestone-local consumer, would require its own read-model versioning decision, exactly as `criterion_results`/`artifact_references` were excluded from `EvidencePackageSnapshot`).
- `transition_history` — excluded, identical reasoning to every prior snapshot.
- `version` / (repository) `persisted_version` — excluded; never exposed by any prior snapshot.
- `disposition` / `final_disposition_rationale` / `cancellation_reason` — excluded. Each is `None` for the majority of a `Review`'s lifecycle (only meaningful after `complete()` or `cancel()`, neither of which is in scope for this milestone) and has no milestone-local consumer.
- `reviewer_reference` — **included**, unlike the excluded fields above. It is a single immutable scalar set once at construction (not an unbounded, ever-growing collection), analogous in kind to `run_id`/`evidence_package_id` on the prior snapshots — a header field, not owned-collection state.

## 7. Selected Result Contract

```python
@dataclass(frozen=True, slots=True)
class ReviewSnapshot:
    identity: DomainIdentity[ReviewId]
    target_evidence_package_id: EvidencePackageId
    reviewer_reference: str
    state: ReviewLifecycleState
```

Four fields: identity, target reference (unwrapped to the raw `EvidencePackageId`, not the `ReviewTargetReference` wrapper — mirroring how `EvidencePackageSnapshot.run_id` is the raw `RunId`, not a wrapper type), reviewer reference (unwrapped to `str`, not the `ReviewerReference` wrapper), and lifecycle state.

## 8. Selected Domain Method

None — pure read, no domain mutation method invoked.

## 9. Repository Sequence

1. Receive `GetReviewQuery`.
2. Call `review_repository.get(query.identity)` exactly once.
3. Construct exactly one `ReviewSnapshot` from `loaded.aggregate`'s `identity`/`target.evidence_package_id`/`reviewer.value`/`state`.
4. Return the snapshot.

No `add()`, no `save()`, no second `get()`, no mutation of the loaded aggregate.

## 10. Lifecycle/Collection Semantics

Not applicable — retrieval does not depend on or expose lifecycle-transition or owned-collection state.

## 11. Error Propagation

No `try`/`except` anywhere in `GetReviewHandler`. `AggregateNotFound`, `InvalidPersistedAggregateState`, and any arbitrary repository exception propagate to the caller with exact instance identity preserved — identical to the frozen M037 pattern.

## 12. Validation Ownership

None owned by `GetReviewQuery` itself (plain, unvalidated data carrier — `identity` is already a validated `DomainIdentity[ReviewId]` by construction). No new validation logic anywhere in this slice.

## 13. Transaction Ownership

None owned by the handler; `PostgresReviewRepository.get()` opens its own `unit_of_work()` scope internally, identical to every other frozen `get()`-pattern repository.

## 14. Architecture Impact

None. `usecases` already permits `review` (added M042). `tools/check_architecture.py` requires zero change; no fixture maintenance required.

## 15. PostgreSQL Success/Failure Strategy

Success: retrieve a `Review` persisted via the frozen M042 `CreateReviewHandler`, confirm the returned `ReviewSnapshot`'s fields match the persisted row exactly. Failure: a missing full identity (governance ID and/or runtime ID not matching any persisted row) raises `AggregateNotFound`, identical to the frozen M037/M034/M031 pattern — independently reproduced against a real, migrated PostgreSQL database, never mocked.

## 16. Real Conflict Feasibility

Not applicable — `get()` is a pure read; no version guard, no `OptimisticConcurrencyConflict` is reachable through this slice.

## 17. Test Strategy

Unit tests (deterministic recording fake `ReviewRepository`, mirroring `test_get_evidence_package_usecase.py`'s structure exactly): query immutability/shape, exactly-one `get()` call, exact identity object passed unchanged, no `add()`/`save()` call, snapshot type and field values, snapshot immutability, exact snapshot field set (`findings`/`transition_history`/`version`/`disposition`/`final_disposition_rationale`/`cancellation_reason` all absent even when the source aggregate has them populated), source-aggregate non-mutation, error propagation (`AggregateNotFound` and an arbitrary exception), `QueryEntryPoint` invocability, handler-bound-once-not-per-call.

Contract test (mirroring `test_get_evidence_package_handler_contract.py`): mypy-checked `QueryHandler[GetReviewQuery, ReviewSnapshot]` typed-assignment conformance; runtime `handle` signature shape; no base-class inheritance.

Integration tests (real PostgreSQL, opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, fresh disposable `postgres:17` container): golden path (Campaign -> Run -> EvidencePackage -> Review seeded via the frozen M030/M033/M036/M042 command chain, retrieved, snapshot fields verified); missing full identity raises `AggregateNotFound`; no production composition machinery required; `review_finding`/`review_transition` tables load without error for a freshly created Review (regression proving the always-eager load path still succeeds even though its result is unused by this query, mirroring the identical M037 regression test for `evidence_package_criterion_result`/`evidence_package_artifact_reference`).

## 18. Alternatives Considered

Exposing `findings`/`transition_history` directly on the snapshot — rejected, identical reasoning to M037 (unbounded collection, no consumer, would require its own read-model versioning decision now rather than when an actual consumer exists). Exposing `disposition`/`final_disposition_rationale`/`cancellation_reason` — rejected as premature: these fields are only ever non-`None` after `complete()`/`cancel()`, neither of which exists at the application layer yet; adding them now would be speculative.

## 19. Risks

Minimal — identical infrastructure-readiness profile to M031/M034/M037.

## 20. M044 Boundary

This design document authorizes work through MILESTONE-043 only. No MILESTONE-044 capability, terminology, or forward commitment is made anywhere in this document.
