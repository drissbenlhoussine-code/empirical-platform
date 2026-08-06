# MILESTONE-049 - Concrete Application Command Vertical Slice: Review Cancellation - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced in the same consolidated M049 mission as the scope document.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M049 frozen baseline | `f8fb8c41488d243fa22a48ad55979eb191046f4d` |

## 3. Command Shape

`Review.cancel()`'s own actual signature is `cancel(self, *, reason: str, actor: str, occurred_at: datetime, correlation_id: str | None = None)` — `reason` unconditionally required (no default), mirroring `Run.fail()`'s own shape (M048) rather than `Campaign.cancel()`'s state-dependent optionality (M047). The command mirrors this exactly, adding only the two universal command-level fields every prior milestone has required (`identity`, `expected_persisted_version`), in the same relative order as `cancel()`'s own parameter list:

```python
@dataclass(frozen=True, slots=True)
class CancelReviewCommand:
    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    reason: str
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
```

Six fields. Not copying `CancelCampaignCommand`'s shape (optional `reason`) — `Review.cancel()`'s own signature has no such optionality.

## 4. Handler Shape

```python
class CancelReviewHandler:
    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: CancelReviewCommand) -> SaveResult:
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.cancel(
            reason=command.reason,
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `ReviewRepository`. Exactly one `.get(`, one `.cancel(`, one `.save(` — identical load-mutate-save shape to every prior command (M030-M048), differing only in which domain method is invoked and which repository is used.

## 5. Identity and Expected-Version Semantics

`command.identity` passed to `get()` unchanged. `command.expected_persisted_version` — never `loaded.persisted_version` — passed to `save()`. Both to be independently re-verified via a non-tautological adversarial script during implementation's own hostile self-audit, mirroring M046/M047/M048's own technique.

## 6. Validation Ownership

All domain validation — the two-state `allowed_states` check, the `reason`/`actor`/`occurred_at`/`correlation_id` presence checks — lives entirely inside `Review.cancel()`'s own `_require_non_empty` call and `_transition()`. The command performs zero business validation at construction: `CancelReviewCommand(reason="", ...)` is always constructible regardless of what state the identified Review is actually in — only `Review.cancel()`'s own internal validation rejects it downstream.

## 7. Repository Interaction Sequence

1. Receive `CancelReviewCommand`.
2. `review_repository.get(command.identity)` exactly once.
3. `review.cancel(reason=..., actor=..., occurred_at=..., correlation_id=...)` exactly once.
4. `review_repository.save(review, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the exact `SaveResult`, unchanged.

No second `get()`/`save()`, no retry, no transaction orchestration, no second capability.

## 8. Error Propagation

No `try`/`except` anywhere in the handler. Three distinct failure scenarios must propagate transparently, unmodified:

1. `AggregateNotFound` from `get()` (missing Review).
2. Domain `ValueError` from `cancel()`/`_transition()` — Review in a state outside the two allowed states (`COMPLETED` or already `CANCELLED`).
3. Domain `ValueError` from `cancel()`'s own `_require_non_empty` — empty-string `reason`.
4. `OptimisticConcurrencyConflict` from `save()` (stale `expected_persisted_version`).

Mirroring M048's `Run.fail()`, there is no `TypeError` branch — `reason` is unconditionally required and always a `str` at the type level; only its emptiness is validated at the domain layer.

## 9. Result Contract

`SaveResult`, returned exactly as received from `ReviewRepository.save()` — no wrapping, no reconstruction. To be independently re-verified via an `is`-identity check.

## 10. Transaction Ownership

The handler owns no transaction, retry, or unit-of-work construct. `PostgresReviewRepository.save()`'s own `unit_of_work()` context manager (frozen since M023) is the sole transactional boundary.

## 11. `CommandEntryPoint` Binding

`CommandEntryPoint(CancelReviewHandler(...))` must work unmodified, mirroring every prior command handler's binding.

## 12. Architecture Impact

None. `usecases` already permits `review` in `ALLOWED["usecases"]` since M042. `python tools/check_architecture.py .` must remain exit 0 with zero fixture change.

## 13. Real Conflict Mechanism — the Central Design Decision

`Review.add_finding()` (M045's own frozen interfering write, already reused once by M046 for `complete()`) requires `state` to be `IN_PROGRESS` and does not call `_transition()` — it never changes `_state`, only `_findings` and `_version`. `cancel()`'s own `allowed_states` includes `IN_PROGRESS`. Therefore: a Review in `IN_PROGRESS`, cancelled by a stale caller while an independently-loaded interferer calls `add_finding()` first, should reach a genuine, unqualified `OptimisticConcurrencyConflict` — the interferer's write leaves `state=IN_PROGRESS` (still within `cancel()`'s own allowed set) and only advances `version`, so the stale caller's own `cancel()` call still passes its own domain preconditions and only fails at the `save()` layer's version guard. This is the **third** reuse of `add_finding()` as an interferer (after M045's self-reuse and M046's reuse for `complete()`), applied here to a fourth target transition and must be empirically re-confirmed during implementation, not assumed by analogy.

## 14. Test Strategy

- **Unit/contract**: identity/version pass-through (non-tautological), no second `get()`/`save()`, no `add()` call, `SaveResult` identity pass-through, transparent propagation of all failure scenarios (Section 8) including two adversarially-chosen exception types beyond the domain's own vocabulary, and structural `CommandHandler` conformance.
- **PostgreSQL integration**: golden-path cancellation from both `ASSIGNED` (directly reachable via the existing, frozen M042 `CreateReviewHandler`) and `IN_PROGRESS` (reached via the existing, frozen M044 `StartReviewHandler`); invalid-state rejection (from `COMPLETED`, reached via the existing, frozen M045/M046 handlers); empty-reason rejection; missing-Review rejection (`AggregateNotFound`); genuine `OptimisticConcurrencyConflict` reproduction (Section 13).

## 15. Rejected Alternatives

- An optional `reason` field mirroring `CancelCampaignCommand` — rejected, `Review.cancel()`'s own signature has no such optionality; `reason` is unconditionally required, matching `Run.fail()`'s shape instead.

## 16. Risks

Both allowed states (`ASSIGNED`, `IN_PROGRESS`) must be exercised in the test suite to avoid a false claim of full precondition coverage, carried forward from the scope document's own Section 13 risk disclosure.

## 17. M050 Boundary

This design resolves exactly one MILESTONE-049 capability. No MILESTONE-050 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 18. Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.**
