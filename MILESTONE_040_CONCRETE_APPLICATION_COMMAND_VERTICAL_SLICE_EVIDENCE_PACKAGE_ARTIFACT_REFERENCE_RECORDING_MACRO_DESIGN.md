# MILESTONE-040 - Concrete Application Command Vertical Slice (EvidencePackage Artifact-Reference Recording) Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced within the same consolidated Macro Milestone Mission as the M040 Macro Scope. Not independently frozen.

## 2. Architectural Context

`EvidencePackage` currently has four proven application-layer verbs (`add()` M036, `get()` M037, `save()`/`start_collection()` M038, `save()`/`add_criterion_result()` M039). This milestone adds the second owned-collection-append write, completing the aggregate's collection-append vocabulary and clearing the path for `seal()` at M041.

## 3. Repository-Verified Facts

Verified live against the frozen baseline:

- `EvidencePackage.add_artifact_reference(reference: ArtifactReference) -> None` — requires `state == COLLECTING`, rejects a duplicate `value`, advances `version`, **does not change `state`** (`src/empirical_platform/evidence/package.py`).
- `ArtifactReference(value: str)` — single-field frozen dataclass; `__post_init__` requires a non-empty string (`src/empirical_platform/evidence/package.py`). No `evidence_package_id` field exists.
- `EvidencePackage.add_criterion_result()` (M039, now frozen) has the identical shape (`COLLECTING`-only, state-preserving, version-advancing) — usable as the interfering write for a deterministic conflict test, the reverse pairing of M039's own mechanism.

## 4. Command Field Analysis

Unlike M039's `RecordEvidencePackageCriterionResultCommand` (which needed six fields to construct a seven-field `CriterionResult`, minus the derived `evidence_package_id`), `ArtifactReference` needs exactly one field (`value`). The command therefore carries only: `identity` (for `get()`), `expected_persisted_version`, `value`. No ownership-derivation question arises (scope Section 6) — there is no `evidence_package_id` to derive or supply.

## 5. Selected Command Contract

```python
@dataclass(frozen=True, slots=True)
class RecordEvidencePackageArtifactReferenceCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    value: str
```

## 6. Deterministic PostgreSQL Conflict Mechanism — Reverse Pairing of M039

`add_artifact_reference()` operates on `COLLECTING`, which has a genuine, now-frozen sibling method — `add_criterion_result()` — usable as a state-preserving, version-advancing interfering write, exactly mirroring M039's own mechanism in reverse.

**Mechanism:**

1. Persist one `EvidencePackage` (M036) and transition it to `COLLECTING` (M038) — `persisted_version = 1`.
2. Independently load it twice: `loaded_a`, `loaded_b` — both see `persisted_version = 1`, both see `COLLECTING`.
3. Call `loaded_b.aggregate.add_criterion_result(CriterionResult(evidence_package_id=loaded_b.aggregate.identity.governance_id, criterion_id="interfering-writer", recorded_at=..., result_label="N/A"))` (domain-valid, preserves `COLLECTING`, advances in-memory version to 2). Test scaffolding only, direct repository/domain calls — never the frozen M039 production command itself, mirroring M039's own use of `add_artifact_reference()` as scaffolding rather than invoking a second real application command.
4. Save `loaded_b.aggregate` via `repo.save(loaded_b.aggregate, expected_persisted_version=AggregateVersion(1))` — **succeeds**, durable `persisted_version` becomes 2.
5. Invoke the command under test against the same identity, with `expected_persisted_version=AggregateVersion(1)` (the version captured before step 3's interference).
6. The handler loads the now-`COLLECTING`-with-version-2 durable state, calls `add_artifact_reference(...)` — **domain-valid** (state is still `COLLECTING`), advances the in-memory version further.
7. `save()` is called with `expected_persisted_version=AggregateVersion(1)`, but the durable version is now 2 — `OptimisticConcurrencyConflict` is raised genuinely, through the real application call sequence.

## 7. Exact Handler Contract

```python
class RecordEvidencePackageArtifactReferenceHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: RecordEvidencePackageArtifactReferenceCommand) -> SaveResult:
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        package.add_artifact_reference(ArtifactReference(value=command.value))
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository`. Simpler than M039's handler — `ArtifactReference` is constructed inline with no intermediate ownership derivation.

## 8. Exact Sequence

1. Receive command.
2. Call `evidence_package_repository.get(command.identity)` exactly once.
3. Construct exactly one `ArtifactReference(value=command.value)`.
4. Call `package.add_artifact_reference(reference)` exactly once.
5. Call `evidence_package_repository.save(package, expected_persisted_version=command.expected_persisted_version)` exactly once.
6. Return the `SaveResult` unchanged.

No `add()` call. No second `get()`/`save()` call. No `add_criterion_result`/`seal`/`invalidate`/`start_collection` call.

## 9. Result Contract

`SaveResult`, mirroring every prior `save()`-based command (M032, M035, M038, M039).

## 10. Error Semantics

Transparent, unchanged propagation of `AggregateNotFound`, the domain `ValueError` (invalid-state call, or duplicate `value`), `OptimisticConcurrencyConflict` (genuinely reproducible per Section 6), and `InvalidAggregateForPersistence`. No handler-level `try`/`except`.

## 11. Validation Ownership

`DomainIdentity`/`EvidencePackageId`/`AggregateVersion` own their own format validation at construction. `ArtifactReference.__post_init__` owns `value` validation. `EvidencePackage.add_artifact_reference()` owns its own state-precondition and duplicate-`value` validation. The handler performs no additional validation.

## 12. Transaction Ownership

No application-level transaction orchestration — one repository-owned `save()` call, already atomic via its own `unit_of_work()`.

## 13. CommandEntryPoint Binding

Test-only direct construction, mirroring every prior command milestone. No production composition root.

## 14. Architecture-Checker Impact

None expected: `usecases` already has `evidence` in `ALLOWED["usecases"]` (since M036). To be independently re-verified live during implementation, not assumed.

## 15. PostgreSQL Success Strategy

Fresh disposable `postgres:17` container: create one `EvidencePackage` (M036), transition to `COLLECTING` (M038), record one `ArtifactReference` via this milestone's handler, assert `SaveResult.persisted_version == AggregateVersion(2)`, then independently reload and assert exactly one `ArtifactReference` present with the exact recorded `value`, `state` still `COLLECTING`.

## 16. PostgreSQL Invalid-State Strategy

Fresh disposable `postgres:17` container: persist an `EvidencePackage` still `INITIALIZED` (never transitioned), invoke the command against it — `add_artifact_reference()` raises `ValueError` ("may be added only while COLLECTING") before `save()` is ever reached.

## 17. PostgreSQL Duplicate-Value Strategy

Fresh disposable `postgres:17` container: record one `ArtifactReference` with `value="s3://bucket/ref-1"`, then attempt a second command with the identical `value` — `add_artifact_reference()` raises `ValueError` ("artifact reference already exists") before the second `save()` is ever reached.

## 18. PostgreSQL Missing-Identity Strategy

Fresh disposable `postgres:17` container: invoke the command against a `DomainIdentity` with no persisted `EvidencePackage`, asserting `AggregateNotFound`.

## 19. PostgreSQL Deterministic-Conflict Strategy

Exactly the mechanism in Section 6, executed live against a fresh disposable `postgres:17` container: asserts a genuine `OptimisticConcurrencyConflict` is raised, with the interfering writer's `CriterionResult` and version-2 state independently confirmed via a post-attempt reload, and confirms the command-under-test's own attempted `ArtifactReference` was **not** persisted despite `add_artifact_reference()` itself having succeeded in memory before the failed `save()`.

## 20. Test Strategy

Unit tests (fake repository): golden-path `get()`-then-`add_artifact_reference()`-then-`save()` sequence proof; exact call-count and call-order proofs; no-`add()`/no-`add_criterion_result()`/no-`seal()`/no-`start_collection()` proof; propagation of `AggregateNotFound`; propagation of the domain `ValueError` (invalid state, duplicate `value`) via a real `EvidencePackage` fixture; propagation of `OptimisticConcurrencyConflict` via a fake repository. Contract tests: typed-conformance to `CommandHandler`, `handle` signature shape, no-inheritance. Integration tests (PostgreSQL, opt-in): golden path; invalid-state; duplicate-`value`; missing-identity; genuine deterministic conflict (Section 19).

## 21. Alternatives and Rejections

A caller-supplied `evidence_package_id`-style field considered and rejected — `ArtifactReference` has no such field to populate (Section 4), so the question that required careful resolution in M039 does not arise here at all.

## 22. Risks

None. This milestone's conflict evidence is a genuine, unqualified `OptimisticConcurrencyConflict` reproduction, and the command shape is the simplest of any milestone to date.

## 23. Hostile Self-Review

Reviewed against every established pitfall from M032/M035/M038/M039: no second `get()`/`save()` call; no `add()` call; no `add_criterion_result`/`seal`/`invalidate`/`start_collection` call; no `Review` reference; the interfering write in the integration test remains test scaffolding only, never a second real application command.

## 24. M041 Boundary

This design authorizes work through MILESTONE-040 implementation only. `seal()` is identified as the natural M041 candidate (scope Section 7) but no MILESTONE-041 field, command, or contract is introduced anywhere in this document.

## 25. Final Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.** Proceeds directly into implementation within this same mission, per the active protocol.
