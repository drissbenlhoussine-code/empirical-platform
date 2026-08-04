# MILESTONE-042 - Concrete Application Command Vertical Slice (Review Creation) Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced within the same consolidated Macro Milestone Mission as the M042 Macro Scope. Not independently frozen.

## 2. Architectural Context

`Review` has zero application-layer proof of any verb (scope Section 4). This milestone adds the first: creation, mirroring the exact `add()`-with-real-FK pattern already twice-proven by M033 (`Run` → `Campaign`) and M036 (`EvidencePackage` → `Run`), now applied a third time to `Review` → `EvidencePackage`.

## 3. Repository-Verified Facts

Verified live against the frozen baseline:

- `Review(*, identity: DomainIdentity[ReviewId], target: ReviewTargetReference, reviewer: ReviewerReference)` — constructor validates `identity`/`target`/`reviewer` types only; starts in `ASSIGNED`.
- `ReviewTargetReference(evidence_package_id: EvidencePackageId)` — single-field frozen dataclass, validates `evidence_package_id` is an `EvidencePackageId`.
- `ReviewerReference(value: str)` — single-field frozen dataclass, validates non-empty string.
- `ReviewRepository.add(aggregate: Review) -> SaveResult` — raises `AggregateAlreadyExists` on duplicate `DomainIdentity`/`governance_id`/`runtime_id`, `InvalidAggregateForPersistence` otherwise (M020, identical shape to every other repository's `add()`).
- `review.target_evidence_package_id` — real database `ForeignKeyConstraint` to `evidence_package.governance_id`, no lifecycle-state constraint (migration, re-verified in scope Section 6).
- `CreateEvidencePackageCommand`/`CreateEvidencePackageHandler` (M036) is the direct structural precedent (re-read in full this session): caller-supplied governance ID translated into the frozen `Id` value object; handler-generated runtime ID via `RuntimeIdentifierGenerator.generate()`; target existence enforced by the real FK, no application-level target-repository dependency; result is the new aggregate's `DomainIdentity`.

## 4. Command Field Analysis

`Review`'s constructor needs three domain inputs beyond identity: `target` (an `EvidencePackageId`) and `reviewer` (a `str`). The command therefore carries: `review_governance_id` (caller-supplied, becomes `ReviewId`), `target_evidence_package_governance_id` (caller-supplied, becomes `EvidencePackageId` inside `ReviewTargetReference`), `reviewer_reference` (caller-supplied, becomes `ReviewerReference`). No `expected_persisted_version` — this is a creation command (`add()`, not `save()`), mirroring M033/M036 exactly.

## 5. Selected Command Contract

```python
@dataclass(frozen=True, slots=True)
class CreateReviewCommand:
    review_governance_id: str
    target_evidence_package_governance_id: str
    reviewer_reference: str
```

Field-for-field the same shape as `CreateEvidencePackageCommand` (two governance-ID-style fields) plus one additional plain-string field for the reviewer reference — no identity model departure.

## 6. Exact Handler Contract

```python
class CreateReviewHandler:
    __slots__ = ("_review_repository", "_runtime_identifier_generator")

    def __init__(
        self,
        *,
        review_repository: ReviewRepository,
        runtime_identifier_generator: RuntimeIdentifierGenerator,
    ) -> None:
        self._review_repository = review_repository
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: CreateReviewCommand) -> DomainIdentity[ReviewId]:
        identity = DomainIdentity(
            governance_id=ReviewId(command.review_governance_id),
            runtime_id=self._runtime_identifier_generator.generate(),
        )
        target = ReviewTargetReference(
            evidence_package_id=EvidencePackageId(command.target_evidence_package_governance_id)
        )
        reviewer = ReviewerReference(command.reviewer_reference)
        review = Review(identity=identity, target=target, reviewer=reviewer)
        self._review_repository.add(review)
        return review.identity
```

Sole dependencies: `ReviewRepository`, `RuntimeIdentifierGenerator` — identical dependency shape to `CreateEvidencePackageHandler`. No `EvidencePackageRepository` dependency; target existence is enforced entirely by the real database FK, mirroring M033/M036's own independently-re-verified pattern (scope Section 6), not assumed by analogy.

## 7. Exact Sequence

1. Receive `CreateReviewCommand`.
2. Construct `ReviewId(command.review_governance_id)`.
3. Call `runtime_identifier_generator.generate()` exactly once.
4. Construct `DomainIdentity`.
5. Construct `ReviewTargetReference(EvidencePackageId(command.target_evidence_package_governance_id))`.
6. Construct `ReviewerReference(command.reviewer_reference)`.
7. Construct exactly one `Review` aggregate.
8. Call `review_repository.add(review)` exactly once.
9. Return `review.identity` unchanged.

No `get()`/`save()` call of any kind. No retry. No `EvidencePackage` lookup.

## 8. Frozen Result Contract

`DomainIdentity[ReviewId]` — the newly created identity, returned unchanged. Mirrors `CreateEvidencePackageHandler`'s/`CreateRunHandler`'s return contract exactly.

## 9. Duplicate Governance-ID Behavior

`AggregateAlreadyExists` raised by the real `review.governance_id` `UNIQUE` constraint, propagated transparently — proven at unit level (fake repository) and genuinely reproduced against real PostgreSQL.

## 10. Duplicate Runtime-ID Behavior

Two different governance IDs sharing one generated runtime ID collide on the real `review` table's `PRIMARY KEY (runtime_id)` constraint, raising `AggregateAlreadyExists` — genuinely reproduced against real PostgreSQL, mirroring M033/M036.

## 11. Missing-Target Behavior

A foreign-key violation (SQLSTATE `23503`) on `target_evidence_package_id` is not classified as a unique violation by `unique_violation_constraint_name` (verified against `PostgresReviewRepository`'s exception-handling code, matching the identical, independently-re-verified pattern from M033/M036), so it reaches a bare `raise` — an unmodified `FoundationError`, never translated. Genuinely reproduced against real PostgreSQL, with independent confirmation via `AggregateNotFound` on reload that no row was persisted despite the failure.

## 12. Arbitrary Error Semantics

Transparent, unchanged propagation of `InvalidAggregateForPersistence` and any arbitrary `add()`/generator failure. No handler-level `try`/`except`.

## 13. Validation Ownership

`ReviewId`/`EvidencePackageId` own format validation at construction. `DomainIdentity` validates only base identity-pair structure. `ReviewTargetReference`/`ReviewerReference`/`Review.__init__` own their own type checks. The handler performs no duplicate validation.

## 14. Transaction Non-Ownership

No application-level transaction orchestration — one repository-owned `add()` call, already atomic via its own `unit_of_work()`.

## 15. CommandEntryPoint Binding

Test-only direct construction, mirroring every prior command milestone. No production composition root.

## 16. Architecture-Checker Impact

Exactly one narrow addition: `"review"` added to `ALLOWED["usecases"]` (scope Section 16, independently re-verified live: currently `{"shared", "identifiers", "campaign", "run", "evidence"}`). `FORBIDDEN_IMPORT_PREFIXES["usecases"]` unchanged. **Required fixture maintenance** (identified live, not assumed): the now-obsolete negative fixture `tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_review_import.py` (currently proves `usecases` cannot import `review`) will silently stop triggering once the ALLOWED change lands, and must be removed along with its corresponding assertion (`"usecases may not import review"`) in `test_module_boundaries.py`. A new reverse-direction fixture — `tests/fixtures/illegal_imports/src/empirical_platform/review/bad_usecases_import.py` (`review` may not import `usecases`) — will be added, mirroring the identical pattern already established for `campaign`/`run`/`evidence` (each of which already has this reverse-direction fixture; `review` is currently the only aggregate missing it).

## 17. PostgreSQL Success Strategy

Fresh disposable `postgres:17` container: create a Campaign → Run → `EvidencePackage` → transition to `COLLECTING` → record one `CriterionResult` and one `ArtifactReference` → `seal()` (all via frozen M030/M033/M036/M038/M039/M040/M041 commands, reaching a genuinely `SEALED` target — the real-world-aligned scenario scope Section 7 anticipated), then create a `Review` targeting it via this milestone's handler. Assert the returned `DomainIdentity` matches the constructed identity; independently reload via `ReviewRepository.get()` and assert `target.evidence_package_id`, `reviewer`, `state == ASSIGNED`, empty `findings`, `disposition is None`.

## 18. PostgreSQL Duplicate-Governance-ID Strategy

Fresh disposable `postgres:17` container: create one `Review`, then attempt a second command with the identical `review_governance_id` (targeting the same or a different `EvidencePackage`) — `AggregateAlreadyExists` raised by the real `UNIQUE` constraint.

## 19. PostgreSQL Duplicate-Runtime-ID Strategy

Fresh disposable `postgres:17` container: two different `review_governance_id` values sharing one deterministic runtime ID (via `DeterministicRuntimeIdentifierGenerator`) — the second `add()` collides on the real `PRIMARY KEY (runtime_id)` constraint, raising `AggregateAlreadyExists`.

## 20. PostgreSQL Missing-Target Strategy

Fresh disposable `postgres:17` container: invoke the command against a `target_evidence_package_governance_id` with no persisted `EvidencePackage` row — the real FK constraint violation reaches an unmodified `FoundationError`; independently confirm via `ReviewRepository.get()` raising `AggregateNotFound` that no `Review` row was persisted despite the failure.

## 21. Test Strategy

Unit tests (fake repository): identity/generator/aggregate-construction/`add()`-call-count/return-value proofs; constructor-shape proof of no `EvidencePackageRepository` dependency; malformed-ID propagation (all three fields); `AggregateAlreadyExists`/generator-failure propagation; no-pre-read proof (no `get()` call); `CommandEntryPoint` binding and reuse; plain-unvalidated-carrier proof (command performs no business validation). Contract tests: typed-conformance to `CommandHandler`, `handle` signature shape, no-inheritance. Integration tests (PostgreSQL, opt-in): golden path (against a genuinely `SEALED` target); duplicate governance-ID; duplicate runtime-ID; missing-target FK violation; no-production-composition.

## 22. Alternatives and Rejections

A caller-supplied `runtime_id` (bypassing `RuntimeIdentifierGenerator`) was not considered — every prior creation milestone (M030, M033, M036) uses handler-generated runtime IDs exclusively, and no evidenced need to deviate exists. Application-level `EvidencePackageRepository`-based target-existence validation (an explicit `get()` call before `add()`) was considered and rejected, mirroring M033/M036's own independently-re-verified rejection: it would duplicate what the real FK already enforces, introduce a redundant read, and risk a TOCTOU gap between the check and the `add()`.

## 23. Risks

None beyond those already inherent in the frozen design. This is the best-precedented candidate available (scope Section 18) — the identical `add()`-with-real-FK pattern has now succeeded twice (M033, M036) with zero deviation required.

## 24. Hostile Self-Review

Reviewed against every established pitfall from M033/M036: no `get()`/`save()` call; no `EvidencePackageRepository` dependency; no second capability (`start`/`add_finding`/`complete`/`cancel` all absent); no transport/composition-root reference; target existence relies entirely on the real FK, independently re-verified against live migration source, not assumed by analogy.

## 25. M043 Boundary

This design authorizes work through MILESTONE-042 implementation only. Review retrieval and lifecycle transitions are identified as natural future candidates (scope Section 8) but no MILESTONE-043 field, command, or contract is introduced anywhere in this document.

## 26. Final Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.** Proceeds directly into implementation within this same mission, per the active protocol.
