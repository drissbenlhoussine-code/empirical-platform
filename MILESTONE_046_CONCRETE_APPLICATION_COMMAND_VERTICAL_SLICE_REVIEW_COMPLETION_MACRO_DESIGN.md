# MILESTONE-046 - Concrete Application Command Vertical Slice: Review Completion - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN.** Produced in the same consolidated M046 mission as the scope document.

## 2. Design Goal

Complete an existing, `IN_PROGRESS` `Review` with non-empty `findings`, via `Review.complete()`, mirroring `SealEvidencePackageCommand`/`SealEvidencePackageHandler` (M041) in shape — the closest architectural precedent, being the only other multi-precondition transition in this project's lineage.

## 3. Command Contract

```python
@dataclass(frozen=True, slots=True)
class CompleteReviewCommand:
    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    disposition: ReviewDisposition
    final_disposition_rationale: str
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
```

Seven fields. `disposition` is the caller-supplied `ReviewDisposition` enum directly — `Review.complete()`'s own signature already requires this type, and no identifier-style value object or string-to-enum translation exists or is needed at the application layer (unlike governance-ID-style fields elsewhere in this codebase, `ReviewDisposition` is a plain frozen enum with no format-validation wrapper). No separate `reason` field: `Review.complete()`'s own implementation passes `final_disposition_rationale` as `_transition()`'s `reason` argument internally — duplicating it as a second caller-supplied field would be redundant and would raise the question of which value wins if they diverged.

## 4. Handler Contract

```python
class CompleteReviewHandler:
    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: CompleteReviewCommand) -> SaveResult:
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.complete(
            disposition=command.disposition,
            final_disposition_rationale=command.final_disposition_rationale,
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `ReviewRepository`. Exactly one `get()`, one `complete()`, one `save()`.

## 5. Identity and Expected-Version Semantics

Identical to M044/M045: `command.identity` passed to `get()` unchanged; `command.expected_persisted_version` — never `loaded.persisted_version` — passed to `save()`.

## 6. Conflict Mechanism — Resolved via Empirical Verification, Not Assumed

`complete()` changes `state` (`IN_PROGRESS -> COMPLETED`). Mirroring M038's/M044's independently-established reasoning: using `complete()` itself as the interfering write against a second `complete()` command-under-test would make the second caller's own fresh `get()` observe `COMPLETED` already, failing its own precondition check before ever reaching `save()` — a domain `ValueError`, not `OptimisticConcurrencyConflict`.

However, `Review` now has a second, distinct, state-preserving mutation — `add_finding()` (M045) — available as a genuinely different interfering write, mirroring M039's own resolution (`add_criterion_result()` interfered against by `add_artifact_reference()`, a *different* method). An interfering `add_finding()` call advances `version` without changing `state` and does not invalidate `complete()`'s own preconditions (an additional finding only helps satisfy "non-empty `findings`"). This was empirically verified during implementation (Section 19): the command-under-test's own fresh `get()` still observes `IN_PROGRESS` with the interferer's finding already present, so its own `complete()` call succeeds domain-validly — it only fails when `save()` rejects the stale `expected_persisted_version`, producing a genuine, unqualified `OptimisticConcurrencyConflict` — no disclosed real-PostgreSQL boundary of the kind M038/M044 required.

## 7. Result Contract

`SaveResult`, returned exactly as received from `ReviewRepository.save()` — no wrapping, no reconstruction.

## 8. Exact Sequence

1. Receive `CompleteReviewCommand`.
2. Call `review_repository.get(command.identity)` exactly once.
3. Call `review.complete(...)` exactly once.
4. Call `review_repository.save(review, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the exact `SaveResult`, unchanged.

No second `get()`/`save()`, no retry, no transaction orchestration, no second capability.

## 9. Transition and Disposition Semantics

A successful `complete()` call transitions `IN_PROGRESS -> COMPLETED`, advances `version` by exactly one, appends exactly one `StateTransitionRecord` (`from_state="IN_PROGRESS"`, `to_state="COMPLETED"`, `reason=final_disposition_rationale`), and sets `disposition`/`final_disposition_rationale`. `findings` are read (for the non-empty precondition) but not mutated; `cancellation_reason` remains `None`.

## 10. Error Propagation

No `try`/`except` anywhere in `CompleteReviewHandler`. `AggregateNotFound` (missing identity), the domain `ValueError` (invalid-state `complete()` call, or empty `findings`), `TypeError` (non-`ReviewDisposition` value — structurally unreachable given the command's own type annotation, but still a real propagation path if violated), `OptimisticConcurrencyConflict` (stale `expected_persisted_version` against a genuine interfering write), and `InvalidAggregateForPersistence` all propagate transparently, unchanged.

## 11. Validation Ownership

None owned by `CompleteReviewCommand` itself — a plain, unvalidated data carrier. All validation is owned by `Review.complete()`'s own precondition checks (`state`, non-empty `findings`, `disposition` type, non-empty `final_disposition_rationale`) and `Review._transition()`'s shared invariant checks.

## 12. Transaction Ownership

None owned by the handler; `PostgresReviewRepository.save()` opens its own `unit_of_work()` scope internally.

## 13. Architecture Impact

None. `usecases` already permits `review` (added M042). `tools/check_architecture.py` requires zero change.

## 14. PostgreSQL Success/Invalid-State Strategy

Success: an `IN_PROGRESS` Review with one prior finding (seeded via the frozen M030→M033→M036→M042→M044→M045 command chain), completed with a `disposition`, `final_disposition_rationale`, `version`/state/transition-history/disposition independently confirmed. Invalid-state: an `IN_PROGRESS` Review with **zero** findings rejects `complete()` with a domain `ValueError` distinct from the state-precondition message; a still-`ASSIGNED` Review (never started) rejects `complete()` with the state-precondition `ValueError`; both independently reproduced against real PostgreSQL, never mocked.

## 15. Real Conflict Feasibility / Fake-Versus-Real Boundary

See Section 6. To be empirically confirmed during implementation via a genuine, caller-driven, real-PostgreSQL two-caller sequence, using `add_finding()` as a distinct interfering write — not assumed by analogy to M039 without independent re-verification.

## 16. Test Strategy

Unit tests (deterministic recording fake `ReviewRepository`, mirroring `test_seal_evidence_package_usecase.py`'s structure): command immutability/shape, exactly-one `get()`/`complete()`/`save()` call, exact identity and `expected_persisted_version` passed unchanged, no `add()` call, `SaveResult` returned unchanged, disposition/rationale fields passed through unchanged, error propagation (`AggregateNotFound`, domain `ValueError` from a still-`ASSIGNED` fake aggregate, domain `ValueError` from an `IN_PROGRESS`-but-empty-findings fake aggregate, `OptimisticConcurrencyConflict` via a fake repository), `CommandEntryPoint` invocability, handler-bound-once-not-per-call.

Contract test: mypy-checked `CommandHandler[CompleteReviewCommand, SaveResult]` typed-assignment conformance; runtime `handle` signature shape; no base-class inheritance.

Integration tests (real PostgreSQL, opt-in, fresh disposable `postgres:17` container): golden path (Review completed, disposition/rationale/version/transition-history verified via reload); invalid-state — still `ASSIGNED`; invalid-state — `IN_PROGRESS` but zero findings; missing-identity `AggregateNotFound`; genuine deterministic conflict (two independently-loaded callers, `add_finding()` used as the interfering write against the `complete()` command-under-test); no-production-composition.

## 17. Alternatives Considered

Passing `disposition` as a raw string requiring handler-side conversion — rejected: `Review.complete()`'s own signature requires the `ReviewDisposition` enum directly; introducing a string-to-enum conversion step in the handler would duplicate validation `Review.complete()`'s own `isinstance()` check already performs, and would risk silent divergence between the command's string and the enum's canonical values. Adding a separate `reason` field distinct from `final_disposition_rationale` — rejected: `Review.complete()` itself uses `final_disposition_rationale` as the transition's `reason`; a second field would be redundant and ambiguous.

## 18. Risks

Minimal — identical infrastructure-readiness profile to M032/M035/M038/M041/M044.

## 19. Conflict Feasibility — Result (Implementation-Time Verification)

**Independently confirmed genuine** during implementation: a real, caller-driven, two-independently-loaded-caller PostgreSQL sequence, using `add_finding()` as the interfering write, produces an unqualified `OptimisticConcurrencyConflict` — no domain-`ValueError` obstacle, because the interference is state-preserving and does not invalidate `complete()`'s own preconditions. See implementation document Section 7 and integration test evidence.

## 20. M047 Boundary

This design document authorizes work through MILESTONE-046 only. No MILESTONE-047 capability, terminology, or forward commitment is made anywhere in this document.
