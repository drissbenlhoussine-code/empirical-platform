# MILESTONE-045 - Concrete Application Command Vertical Slice: Review Finding Recording - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN.** Produced in the same consolidated M045 mission as the scope document.

## 2. Design Goal

Append one new finding to an existing, `IN_PROGRESS` `Review`, via `Review.add_finding()`, mirroring `RecordEvidencePackageCriterionResultCommand`/`Handler` (M039) in shape, adapted for `add_finding()`'s own simpler signature (no pre-constructed value object passed in — `add_finding()` takes raw fields directly).

## 3. Command Contract

```python
@dataclass(frozen=True, slots=True)
class AddReviewFindingCommand:
    identity: DomainIdentity[ReviewId]
    expected_persisted_version: AggregateVersion
    text: str
    rationale: str | None = None
    evidence_references: tuple[str, ...] = ()
```

Five fields. No `actor`/`occurred_at`/`correlation_id`/`reason` — `add_finding()` does not call `_transition()` (no `StateTransitionRecord` produced), so none of the transition-record fields `start()`/`seal()` require are meaningful here, mirroring `RecordEvidencePackageCriterionResultCommand`'s own omission of `actor` for the identical reason... **correction, verified against source**: `RecordEvidencePackageCriterionResultCommand` does carry `recorded_at` (a domain timestamp owned by `CriterionResult` itself, not a transition record). `ReviewFinding` has no such field — `add_finding()`'s signature is `text`, `rationale`, `evidence_references` only, with no timestamp of any kind. This command's field set matches `add_finding()`'s actual signature exactly, not `RecordEvidencePackageCriterionResultCommand`'s by blind analogy.

## 4. Handler Contract

```python
class AddReviewFindingHandler:
    __slots__ = ("_review_repository",)

    def __init__(self, *, review_repository: ReviewRepository) -> None:
        self._review_repository = review_repository

    def handle(self, command: AddReviewFindingCommand) -> SaveResult:
        loaded = self._review_repository.get(command.identity)
        review = loaded.aggregate
        review.add_finding(
            text=command.text,
            rationale=command.rationale,
            evidence_references=command.evidence_references,
        )
        return self._review_repository.save(
            review, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `ReviewRepository`. Exactly one `get()`, one `add_finding()`, one `save()`. No separate `ReviewFinding` construction in the handler — `add_finding()` constructs it internally from the raw fields, using its own internally-generated `sequence`.

## 5. Identity and Expected-Version Semantics

Identical to M044: `command.identity` passed to `get()` unchanged; `command.expected_persisted_version` — never `loaded.persisted_version` — passed to `save()`.

## 6. Conflict Mechanism — Resolved via Empirical Verification, Not Assumed

`add_finding()` does not call `_transition()` and does not change `state` — a state-preserving mutation, structurally identical in kind to `add_criterion_result()`/`add_artifact_reference()` (M039/M040). Because `add_finding()` is the only reachable interfering write for an `IN_PROGRESS` Review (no second state-preserving method exists at this milestone), the interfering write for the deterministic conflict test is a **second, independently-loaded `add_finding()` call** — not a different method, unlike M039's own resolution (which used `add_artifact_reference()` as an already-existing, distinct interfering write). This was empirically verified during implementation (Section 19) rather than assumed: because the second caller's own fresh `get()` still observes `IN_PROGRESS` (state-preserving), its own domain-level `add_finding()` call succeeds locally — it only fails when `save()` rejects the stale `expected_persisted_version`, producing a genuine, unqualified `OptimisticConcurrencyConflict` — no disclosed real-PostgreSQL boundary of the kind M038/M044 required.

## 7. Result Contract

`SaveResult`, returned exactly as received from `ReviewRepository.save()` — no wrapping, no reconstruction.

## 8. Exact Sequence

1. Receive `AddReviewFindingCommand`.
2. Call `review_repository.get(command.identity)` exactly once.
3. Call `review.add_finding(...)` exactly once.
4. Call `review_repository.save(review, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the exact `SaveResult`, unchanged.

No second `get()`/`save()`, no retry, no transaction orchestration, no second capability.

## 9. Owned-Collection Semantics

A successful `add_finding()` call advances `version` by exactly one, appends exactly one `ReviewFinding` to `findings` (with an internally-generated, monotonically increasing `sequence`), and does **not** append a `StateTransitionRecord` or change `state`.

## 10. Error Propagation

No `try`/`except` anywhere in `AddReviewFindingHandler`. `AggregateNotFound` (missing identity), the domain `ValueError` (invalid-state `add_finding()` call — target not `IN_PROGRESS`), `OptimisticConcurrencyConflict` (stale `expected_persisted_version` against a genuine interfering write), and `InvalidAggregateForPersistence` all propagate transparently, unchanged.

## 11. Validation Ownership

None owned by `AddReviewFindingCommand` itself — a plain, unvalidated data carrier. All validation is owned by `Review.add_finding()`'s own precondition check and `ReviewFinding.__post_init__`'s invariant checks (non-empty `text`, non-empty `rationale` if present, non-empty each `evidence_references` entry if present).

## 12. Transaction Ownership

None owned by the handler; `PostgresReviewRepository.save()` opens its own `unit_of_work()` scope internally.

## 13. Architecture Impact

None. `usecases` already permits `review` (added M042). `tools/check_architecture.py` requires zero change.

## 14. PostgreSQL Success/Invalid-State Strategy

Success: an `IN_PROGRESS` Review (seeded via the frozen M030→M033→M036→M042→M044 command chain), one finding appended, `findings` length/content/`sequence` independently confirmed. Invalid-state: a still-`ASSIGNED` Review (never `start()`'d) rejects `add_finding()` with a domain `ValueError`, never reaching `save()`, independently reproduced against real PostgreSQL, never mocked.

## 15. Duplicate Strategy

Not applicable — see scope document Section 5/17. `sequence` is never caller-supplied; no duplicate scenario is domain-reachable via the application layer.

## 16. Real Conflict Feasibility / Fake-Versus-Real Boundary

See Section 6. To be empirically confirmed during implementation (Section 19) via a genuine, caller-driven, real-PostgreSQL two-caller sequence — not assumed by analogy to M039/M040 without independent re-verification, mirroring the discipline every prior milestone's own design applied to its own conflict claim.

## 17. Test Strategy

Unit tests (deterministic recording fake `ReviewRepository`, mirroring `test_record_evidence_package_criterion_result_usecase.py`'s structure): command immutability/shape, exactly-one `get()`/`add_finding()`/`save()` call, exact identity and `expected_persisted_version` passed unchanged, no `add()` call, `SaveResult` returned unchanged, finding fields (`text`/`rationale`/`evidence_references`) passed through unchanged, error propagation (`AggregateNotFound`, domain `ValueError` from a still-`ASSIGNED` fake aggregate, `OptimisticConcurrencyConflict` via a fake repository), `CommandEntryPoint` invocability, handler-bound-once-not-per-call.

Contract test: mypy-checked `CommandHandler[AddReviewFindingCommand, SaveResult]` typed-assignment conformance; runtime `handle` signature shape; no base-class inheritance.

Integration tests (real PostgreSQL, opt-in, fresh disposable `postgres:17` container): golden path (finding appended, `sequence`/`text`/`rationale`/`evidence_references` verified via reload); invalid-state (still-`ASSIGNED` Review); missing-identity `AggregateNotFound`; genuine deterministic conflict (two independently-loaded callers, second `add_finding()` used as the interfering write against the command-under-test); no-production-composition.

## 18. Alternatives Considered

Exposing `sequence` as a caller-supplied command field — rejected: `add_finding()`'s own signature does not accept it, and `ReviewFinding.sequence` is an internal aggregate-invariant concern, not caller data. Constructing `ReviewFinding` in the handler (mirroring `RecordEvidencePackageCriterionResultCommand`'s pattern) — rejected: `add_finding()`'s own signature takes raw fields directly and constructs the value object internally; constructing it externally would require duplicating `add_finding()`'s own internal `sequence` derivation, which the aggregate alone owns.

## 19. Conflict Feasibility — Result (Implementation-Time Verification)

**Independently confirmed genuine** during implementation: a real, caller-driven, two-independently-loaded-caller PostgreSQL sequence produces an unqualified `OptimisticConcurrencyConflict` — no domain-`ValueError` obstacle exists, because `add_finding()` is state-preserving and the second caller's own fresh `get()` still observes `IN_PROGRESS`. See implementation document Section 7 and integration test evidence.

## 20. Risks

Minimal — identical infrastructure-readiness profile to M039/M040.

## 21. M046 Boundary

This design document authorizes work through MILESTONE-045 only. No MILESTONE-046 capability, terminology, or forward commitment is made anywhere in this document.
