# MILESTONE-041 - Concrete Application Command Vertical Slice (EvidencePackage Sealing) Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced within the same consolidated Macro Milestone Mission as the M041 Macro Scope. Not independently frozen.

## 2. Architectural Context

`EvidencePackage` currently has five proven application-layer verbs (`add()` M036, `get()` M037, `save()`/`start_collection()` M038, `save()`/`add_criterion_result()` M039, `save()`/`add_artifact_reference()` M040). This milestone adds the aggregate's lifecycle-completion transition, the last unproven `COLLECTING`-reachable capability.

## 3. Repository-Verified Facts

Verified live against the frozen baseline:

- `EvidencePackage.seal(*, actor, occurred_at, correlation_id=None, reason=None)` — requires `criterion_results` non-empty, requires `artifact_references` non-empty, requires `state == COLLECTING` (via `_transition`'s `expected_state` check); transitions to `SEALED`, advances `version`, appends one `StateTransitionRecord` (`from_state="COLLECTING"`, `to_state="SEALED"`).
- `AuthorizeRunCommand`/`StartEvidencePackageCollectionCommand` are the direct structural precedent for a transition command's field shape: `identity`, `expected_persisted_version`, `actor`, `occurred_at`, `correlation_id`, `reason`.
- Both `add_criterion_result()` (M039) and `add_artifact_reference()` (M040) are frozen, state-preserving, version-advancing methods — either is a legitimate interfering write for a deterministic conflict test.

## 4. Command Field Analysis

`seal()` requires exactly `actor`/`occurred_at`/`correlation_id`/`reason`, identical to `start_collection()`'s signature. No additional domain data is required — the two-collection precondition is enforced entirely by the aggregate's own existing state, not by anything the caller supplies.

## 5. Selected Command Contract

```python
@dataclass(frozen=True, slots=True)
class SealEvidencePackageCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Field-for-field identical to `StartEvidencePackageCollectionCommand` (M038) — the same transition-command shape, now applied to the aggregate's final `COLLECTING`-reachable transition.

## 6. Exact Handler Contract

```python
class SealEvidencePackageHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: SealEvidencePackageCommand) -> SaveResult:
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        package.seal(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository`. Structurally identical to `StartEvidencePackageCollectionHandler` (M038) — the two-collection precondition is entirely `EvidencePackage.seal()`'s own concern, never duplicated in the handler.

## 7. Exact Sequence

1. Receive command.
2. Call `evidence_package_repository.get(command.identity)` exactly once.
3. Call `package.seal(...)` exactly once on the loaded aggregate.
4. Call `evidence_package_repository.save(package, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the `SaveResult` unchanged.

No `add()` call. No second `get()`/`save()` call. No `add_criterion_result`/`add_artifact_reference`/`invalidate`/`start_collection` call.

## 8. Result Contract

`SaveResult`, mirroring every prior transition command (M032, M035, M038).

## 9. Error Semantics

Transparent, unchanged propagation of `AggregateNotFound`, the domain `ValueError` (empty `criterion_results`, empty `artifact_references`, or invalid `state`), `OptimisticConcurrencyConflict`, and `InvalidAggregateForPersistence`. No handler-level `try`/`except`. **Three distinct domain-`ValueError` scenarios exist for this transition** (unlike any prior single-precondition transition), each independently tested (Section 18).

## 10. Deterministic PostgreSQL Conflict Mechanism

Either `add_criterion_result()` or `add_artifact_reference()` (both frozen, state-preserving, version-advancing) is a legitimate interfering write. **Selected: `add_artifact_reference()`** — arbitrary but fixed choice, since either is equally valid; picking one keeps the test unambiguous. Mechanism, mirroring M039/M040 exactly:

1. Persist an `EvidencePackage`, transition to `COLLECTING`, record one `CriterionResult` and one `ArtifactReference` (all via frozen commands) — `persisted_version = 3`.
2. Independently load it twice: `loaded_a`, `loaded_b` — both see `persisted_version = 3`, both see `COLLECTING` with both collections non-empty.
3. Call `loaded_b.aggregate.add_artifact_reference(ArtifactReference(value="interfering-writer"))` (domain-valid, preserves `COLLECTING`, advances in-memory version to 4). Test scaffolding only, direct repository/domain calls.
4. Save `loaded_b.aggregate` via `repo.save(loaded_b.aggregate, expected_persisted_version=AggregateVersion(3))` — succeeds, durable `persisted_version` becomes 4.
5. Invoke the command under test with `expected_persisted_version=AggregateVersion(3)` (stale).
6. The handler loads the now-version-4 `COLLECTING` state (both collections still non-empty), calls `seal(...)` — domain-valid.
7. `save()` is called with the stale `expected_persisted_version=AggregateVersion(3)`, but the durable version is now 4 — `OptimisticConcurrencyConflict` is raised genuinely.

## 11. Validation Ownership

`DomainIdentity`/`EvidencePackageId`/`AggregateVersion` own their own format validation at construction. `EvidencePackage.seal()` owns its own two-collection-precondition and state-precondition validation. The handler performs no additional validation and duplicates none of it.

## 12. Transaction Ownership

No application-level transaction orchestration — one repository-owned `save()` call, already atomic via its own `unit_of_work()`.

## 13. CommandEntryPoint Binding

Test-only direct construction, mirroring every prior command milestone. No production composition root.

## 14. Architecture-Checker Impact

None expected: `usecases` already has `evidence` in `ALLOWED["usecases"]` (since M036). To be independently re-verified live during implementation, not assumed.

## 15. PostgreSQL Success Strategy

Fresh disposable `postgres:17` container: create an `EvidencePackage`, transition to `COLLECTING`, record one `CriterionResult` and one `ArtifactReference` (all frozen commands), seal it via this milestone's handler, assert `SaveResult.persisted_version == AggregateVersion(4)`, then independently reload and assert `state == SEALED`, exactly one transition record with `from_state="COLLECTING"`/`to_state="SEALED"`, and both collections still present unchanged.

## 16. PostgreSQL Empty-Criterion-Results Strategy

Fresh disposable `postgres:17` container: create an `EvidencePackage`, transition to `COLLECTING`, record **only** an `ArtifactReference` (no `CriterionResult`), invoke the command — `seal()` raises `ValueError` ("requires at least one Criterion Result") before `save()` is ever reached.

## 17. PostgreSQL Empty-Artifact-References Strategy

Fresh disposable `postgres:17` container: create an `EvidencePackage`, transition to `COLLECTING`, record **only** a `CriterionResult` (no `ArtifactReference`), invoke the command — `seal()` raises `ValueError` ("requires at least one artifact reference") before `save()` is ever reached.

## 18. PostgreSQL Invalid-State and Missing-Identity Strategy

Fresh disposable `postgres:17` container: an `EvidencePackage` still `INITIALIZED` (never transitioned) rejects `seal()` with a domain `ValueError` (state precondition) before either collection precondition is even reached; a `DomainIdentity` with no persisted `EvidencePackage` raises `AggregateNotFound`.

## 19. PostgreSQL Deterministic-Conflict Strategy

Exactly the mechanism in Section 10, executed live against a fresh disposable `postgres:17` container.

## 20. Test Strategy

Unit tests (fake repository): golden-path `get()`-then-`seal()`-then-`save()` sequence proof; exact call-count and call-order proofs; no-`add_criterion_result`/`add_artifact_reference`/`invalidate`/`start_collection` proof; propagation of `AggregateNotFound`; propagation of all three domain-`ValueError` scenarios (empty criterion results, empty artifact references, invalid state) via real `EvidencePackage` fixtures constructed at each precondition boundary; propagation of `OptimisticConcurrencyConflict` via a fake repository. Contract tests: typed-conformance to `CommandHandler`, `handle` signature shape, no-inheritance. Integration tests (PostgreSQL, opt-in): golden path; empty-criterion-results; empty-artifact-references; invalid-state; missing-identity; genuine deterministic conflict (Section 19) — six tests, the largest integration surface of any EvidencePackage milestone to date, proportional to the transition's three-part precondition.

## 21. Alternatives and Rejections

Using both `add_criterion_result()` and `add_artifact_reference()` together as a combined interfering write (to more thoroughly exercise both collections during interference) was considered and rejected as unnecessary complexity — a single interfering write of either kind is sufficient to prove the deterministic conflict mechanism, exactly matching the precedent set by every prior conflict test (M032, M035, M039, M040), each of which used exactly one interfering write.

## 22. Risks

None beyond those already inherent in the frozen design. The three-part precondition surface (two collections plus state) requires proportionally more integration-test coverage than any prior transition, but each precondition is independently well-understood and already domain-validated since M020.

## 23. Hostile Self-Review

Reviewed against every established pitfall from M032/M035/M038/M039/M040: no second `get()`/`save()` call; no `add()` call; no `add_criterion_result`/`add_artifact_reference`/`invalidate`/`start_collection` call; no `Review` reference; both empty-collection precondition paths are independently tested, not conflated into a single "invalid" case; the interfering write remains test scaffolding only.

## 24. M042 Boundary

This design authorizes work through MILESTONE-041 implementation only. Review creation is identified as the natural M042 candidate (scope Section 7) but no MILESTONE-042 field, command, or contract is introduced anywhere in this document.

## 25. Final Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.** Proceeds directly into implementation within this same mission, per the active protocol.
