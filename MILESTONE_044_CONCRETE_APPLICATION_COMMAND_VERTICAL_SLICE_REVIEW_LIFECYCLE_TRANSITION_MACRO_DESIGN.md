# MILESTONE-044 - Concrete Application Command Vertical Slice: Review Lifecycle Transition - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN.** Produced in the same consolidated M044 mission as the scope document.

## 2. Design Goal

Transition an existing, `ASSIGNED` `Review` to `IN_PROGRESS`, via `Review.start()`, mirroring `StartEvidencePackageCollectionCommand`/`StartEvidencePackageCollectionHandler` (M038) field-for-field and mechanism-for-mechanism.

## 3. Command Contract

```python
@dataclass(frozen=True, slots=True)
class StartReviewCommand:
    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Six fields, field-for-field identical in shape to `StartEvidencePackageCollectionCommand`. `expected_persisted_version` is caller-supplied, never silently replaced by the handler's own internal `get()` result — this is the only path by which a stale-write scenario can surface as `OptimisticConcurrencyConflict` at all (frozen design principle, established M035 Section on caller-supplied vs. handler-derived version).

## 4. Handler Contract

```python
class StartReviewHandler:
    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: StartReviewCommand) -> SaveResult:
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.start(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `ReviewRepository`. Exactly one `get()`, one `start()`, one `save()`.

## 5. Identity and Expected-Version Semantics

`command.identity` passed to `get()` unchanged. `command.expected_persisted_version` — never `loaded.persisted_version` — passed to `save()`.

## 6. Conflict Mechanism — Resolved, Not Assumed

Independently re-derived (scope document Section 17): `Review` has no state-preserving mutation reachable while `ASSIGNED`. The only candidate interfering write is `start()` itself, which changes state away from `ASSIGNED`. Consequently:

- **PostgreSQL evidence (real, caller-driven):** two independently-loaded callers race to `start()` the same `ASSIGNED` Review. The first succeeds. The second's own handler performs its own **fresh** `get()` (sees `IN_PROGRESS` already — not the stale in-memory state a naive "two stale copies" scenario would assume), and its own `start()` call fails the domain precondition check (`allowed_states=(ASSIGNED,)`) with a `ValueError`, **before ever reaching `save()`**. This is the honest, reproducible scenario and is the primary PostgreSQL race test for this milestone — mirroring M038's identical, already-accepted resolution for `start_collection()`.
- **`OptimisticConcurrencyConflict` propagation (unit level):** proven via a fake `ReviewRepository` whose `save()` raises `OptimisticConcurrencyConflict` directly, unconstrained by `Review`'s own domain preconditions — isolating the pure repository-contract-propagation proof, identical in kind to M038's own unit-level resolution (`tests/unit/test_start_evidence_package_collection_usecase.py`).

No repository-level version bypass, invalid row, or patched aggregate internals are used to fabricate a conflict that is not genuinely reachable via a real caller path.

## 7. Result Contract

`SaveResult`, returned exactly as received from `ReviewRepository.save()` — no wrapping, no reconstruction.

## 8. Exact Sequence

1. Receive `StartReviewCommand`.
2. Call `review_repository.get(command.identity)` exactly once.
3. Call `review.start(...)` exactly once.
4. Call `review_repository.save(review, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the exact `SaveResult`, unchanged.

No second `get()`/`save()`, no retry, no transaction orchestration, no second capability.

## 9. Transition Semantics

A successful `start()` call transitions `ASSIGNED -> IN_PROGRESS`, advances `version` by exactly one, and appends exactly one `StateTransitionRecord` (`from_state="ASSIGNED"`, `to_state="IN_PROGRESS"`). `findings` remain empty (not touched by `start()`).

## 10. Error Propagation

No `try`/`except` anywhere in `StartReviewHandler`. `AggregateNotFound` (missing identity), the domain `ValueError` (invalid-state `start()` call), `OptimisticConcurrencyConflict` (stale `expected_persisted_version` via fake-repository unit test — see Section 6), and `InvalidAggregateForPersistence` all propagate transparently, unchanged.

## 11. Validation Ownership

None owned by `StartReviewCommand` itself — a plain, unvalidated data carrier. All validation is owned by `Review.start()`'s own precondition checks and `Review._transition()`'s shared invariant checks (`occurred_at` must be a `datetime`, `actor`/`correlation_id`/`reason` non-empty-if-present).

## 12. Transaction Ownership

None owned by the handler; `PostgresReviewRepository.save()` opens its own `unit_of_work()` scope internally, identical to every other frozen `save()`-pattern repository.

## 13. Architecture Impact

None. `usecases` already permits `review` (added M042). `tools/check_architecture.py` requires zero change; no fixture maintenance required.

## 14. PostgreSQL Success/Invalid-State Strategy

Success: a genuinely `ASSIGNED` Review (seeded via the frozen M030→M033→M036→M042 command chain), transitioned to `IN_PROGRESS`, `SaveResult.persisted_version` and the reloaded aggregate's state/transition-history independently confirmed. Invalid-state: an already-`IN_PROGRESS` Review (via one prior `start()` call) rejects a second `start()` attempt with a domain `ValueError`, never reaching `save()`, independently reproduced against real PostgreSQL, never mocked.

## 15. Real Conflict Feasibility / Fake-Versus-Real Boundary

See Section 6. Real PostgreSQL evidence proves the domain-`ValueError` race. `OptimisticConcurrencyConflict` propagation is proven exclusively at the unit level via a fake repository — this boundary is explicit, disclosed, and precedented (M038), not a gap.

## 16. Test Strategy

Unit tests (deterministic recording fake `ReviewRepository`, mirroring `test_start_evidence_package_collection_usecase.py`'s structure): command immutability/shape, exactly-one `get()`/`start()`/`save()` call, exact identity and `expected_persisted_version` passed unchanged, no `add()` call, `SaveResult` returned unchanged, error propagation (`AggregateNotFound`, domain `ValueError` from an already-`IN_PROGRESS` fake aggregate, `OptimisticConcurrencyConflict` via a fake repository whose `save()` raises it directly), `CommandEntryPoint` invocability, handler-bound-once-not-per-call.

Contract test (mirroring `test_start_evidence_package_collection_handler_contract.py`): mypy-checked `CommandHandler[StartReviewCommand, SaveResult]` typed-assignment conformance; runtime `handle` signature shape; no base-class inheritance.

Integration tests (real PostgreSQL, opt-in, fresh disposable `postgres:17` container): golden path (Campaign→Run→EvidencePackage→Review seeded via the frozen command chain, `start()`'d, state/version/transition-history verified); two-racing-callers domain-`ValueError` race (Section 6); missing-identity `AggregateNotFound`; no-production-composition.

## 17. Alternatives Considered

Deriving `expected_persisted_version` from the handler's own internal `get()` — rejected, identical reasoning to M035: would make the field structurally redundant and eliminate the only path to a genuine stale-write scenario. Fabricating a PostgreSQL-level `OptimisticConcurrencyConflict` via a repository-level version bypass — rejected, would not reflect any genuine caller path (this project's PostgreSQL evidence must always exercise a real, domain-valid call sequence).

## 18. Risks

Minimal — identical infrastructure-readiness profile to M032/M035/M038.

## 19. M045 Boundary

This design document authorizes work through MILESTONE-044 only. No MILESTONE-045 capability, terminology, or forward commitment is made anywhere in this document.
