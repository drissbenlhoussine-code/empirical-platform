# MILESTONE-039 - Concrete Application Command Vertical Slice (EvidencePackage Criterion-Result Recording) Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced within the same consolidated Macro Milestone Mission as the M039 Macro Scope. Not independently frozen.

## 2. Architectural Context

`EvidencePackage` currently has three proven application-layer verbs (`add()` M036, `get()` M037, `save()`/`start_collection()` M038). This milestone adds a second `save()`-based command — the first owned-collection-append write in this project — and, per the scope document (Section 7), finally closes the real-`OptimisticConcurrencyConflict` gap M038 explicitly disclosed.

## 3. Repository-Verified Facts

Verified live against the frozen baseline:

- `EvidencePackage.add_criterion_result(result: CriterionResult) -> None` — requires `state == COLLECTING`, requires `result.evidence_package_id == identity.governance_id`, rejects a duplicate `criterion_id`, advances `version`, **does not change `state`** (`src/empirical_platform/evidence/package.py`).
- `CriterionResult(evidence_package_id, criterion_id, recorded_at, result_label, summary=None, evidence_references=())` — frozen dataclass; `__post_init__` requires non-empty `criterion_id`/`result_label`, non-empty `summary` if present, non-empty entries in `evidence_references` (`src/empirical_platform/evidence/results.py`).
- `EvidencePackage.add_artifact_reference()` has the identical shape (`COLLECTING`-only, state-preserving, version-advancing) — usable as a genuine interfering write for a deterministic conflict test (scope Section 7).
- `StartEvidencePackageCollectionHandler` (M038, frozen) is the only existing way to reach `COLLECTING` through the application layer — used as test-fixture scaffolding only.

## 4. Command Field Analysis

The command must supply everything `CriterionResult` needs except `evidence_package_id`, which is derived from the loaded aggregate's own identity (mirroring this project's established principle — see M036 Section 15 — of deriving identity-linked fields from already-authoritative state rather than trusting a redundant caller-supplied value that could mismatch and silently succeed or silently fail depending on comparison order). The command therefore carries: `identity` (for `get()`), `expected_persisted_version`, `criterion_id`, `recorded_at`, `result_label`, `summary` (optional), `evidence_references` (optional).

## 5. Selected Command Contract

```python
@dataclass(frozen=True, slots=True)
class RecordEvidencePackageCriterionResultCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    criterion_id: str
    recorded_at: datetime
    result_label: str
    summary: str | None = None
    evidence_references: tuple[str, ...] = ()
```

## 6. Deterministic PostgreSQL Conflict Mechanism — Genuinely Available Again

Unlike M038's `start_collection()` (which had no non-transition interfering write available while `INITIALIZED`), `add_criterion_result()` operates on `COLLECTING`, which **does** have a genuine, state-preserving, version-advancing sibling method: `add_artifact_reference()`.

**Mechanism, mirroring M032/M035 exactly:**

1. Persist one `EvidencePackage` (M036) and transition it to `COLLECTING` (M038) — `persisted_version = 1`.
2. Independently load it twice: `loaded_a`, `loaded_b` — both see `persisted_version = 1`, both see `COLLECTING`.
3. Call `loaded_b.aggregate.add_artifact_reference(ArtifactReference(value="interfering-writer"))` (domain-valid, preserves `COLLECTING`, advances in-memory version to 2).
4. Save `loaded_b.aggregate` via `repo.save(loaded_b.aggregate, expected_persisted_version=AggregateVersion(1))` — **succeeds**, durable `persisted_version` becomes 2.
5. Invoke the command under test against the same identity, with `expected_persisted_version=AggregateVersion(1)` (the version captured before step 3's interference).
6. The handler loads the now-`COLLECTING`-with-version-2 durable state, calls `add_criterion_result(...)` — **domain-valid** (state is still `COLLECTING`, the interfering write did not change it), advances the in-memory version further.
7. `save()` is called with `expected_persisted_version=AggregateVersion(1)`, but the durable version is now 2 — `OptimisticConcurrencyConflict` is raised, **genuinely**, through the real application call sequence, with no repository bypass and no fabricated database state.

## 7. Exact Handler Contract

```python
class RecordEvidencePackageCriterionResultHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: RecordEvidencePackageCriterionResultCommand) -> SaveResult:
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        result = CriterionResult(
            evidence_package_id=package.identity.governance_id,
            criterion_id=command.criterion_id,
            recorded_at=command.recorded_at,
            result_label=command.result_label,
            summary=command.summary,
            evidence_references=command.evidence_references,
        )
        package.add_criterion_result(result)
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository`.

## 8. Exact Sequence

1. Receive command.
2. Call `evidence_package_repository.get(command.identity)` exactly once.
3. Construct exactly one `CriterionResult`, with `evidence_package_id` derived from `package.identity.governance_id` — never from a separate command field.
4. Call `package.add_criterion_result(result)` exactly once.
5. Call `evidence_package_repository.save(package, expected_persisted_version=command.expected_persisted_version)` exactly once.
6. Return the `SaveResult` unchanged.

No `add()` call. No second `get()`/`save()` call. No `add_artifact_reference`/`seal`/`invalidate`/`start_collection` call.

## 9. Result Contract

`SaveResult`, mirroring every prior `save()`-based command (M032, M035, M038) — the caller needs the new persisted version after a write.

## 10. Error Semantics

Transparent, unchanged propagation of `AggregateNotFound` (missing `EvidencePackage`), the domain `ValueError` (invalid-state `add_criterion_result()` call, or a duplicate `criterion_id`), `OptimisticConcurrencyConflict` (Section 6 — genuinely reproducible for this capability), and `InvalidAggregateForPersistence`. No handler-level `try`/`except`.

## 11. Validation Ownership

`DomainIdentity`/`EvidencePackageId`/`AggregateVersion` own their own format validation at construction. `CriterionResult.__post_init__` owns `criterion_id`/`result_label`/`summary`/`evidence_references` validation. `EvidencePackage.add_criterion_result()` owns its own state-precondition and duplicate-`criterion_id` validation. The handler performs no additional validation and does not duplicate any of the above.

## 12. Transaction Ownership

No application-level transaction orchestration — one repository-owned `save()` call, already atomic via its own `unit_of_work()`.

## 13. CommandEntryPoint Binding

Test-only direct construction, mirroring every prior command milestone. No production composition root.

## 14. Architecture-Checker Impact

None expected: `usecases` already has `evidence` in `ALLOWED["usecases"]` (since M036). To be independently re-verified live during implementation, not assumed.

## 15. PostgreSQL Success Strategy

Fresh disposable `postgres:17` container: create one `EvidencePackage` (M036), transition to `COLLECTING` (M038), record one `CriterionResult` via this milestone's handler, assert `SaveResult.persisted_version == AggregateVersion(2)`, then independently reload and assert exactly one `CriterionResult` present with the exact recorded fields, `state` still `COLLECTING`.

## 16. PostgreSQL Invalid-State Strategy

Fresh disposable `postgres:17` container: persist an `EvidencePackage` still `INITIALIZED` (never transitioned), invoke the command against it — `add_criterion_result()` raises `ValueError` ("may be added only while COLLECTING") before `save()` is ever reached.

## 17. PostgreSQL Duplicate-Criterion-ID Strategy

Fresh disposable `postgres:17` container: record one `CriterionResult` with `criterion_id="CRIT-001"`, then attempt a second command with the identical `criterion_id` — `add_criterion_result()` raises `ValueError` ("criterion_id already exists") before the second `save()` is ever reached.

## 18. PostgreSQL Missing-Identity Strategy

Fresh disposable `postgres:17` container: invoke the command against a `DomainIdentity` with no persisted `EvidencePackage`, asserting `AggregateNotFound`.

## 19. PostgreSQL Deterministic-Conflict Strategy

Exactly the mechanism in Section 6, executed live against a fresh disposable `postgres:17` container: asserts a genuine `OptimisticConcurrencyConflict` is raised, with the interfering writer's `ArtifactReference` and version-2 state independently confirmed via a post-attempt reload, and confirms the command-under-test's own attempted `CriterionResult` was **not** persisted despite `add_criterion_result()` itself having succeeded in memory before the failed `save()`.

## 20. Test Strategy

Unit tests (fake repository): golden-path `get()`-then-`add_criterion_result()`-then-`save()` sequence proof; exact call-count and call-order proofs; `evidence_package_id`-derived-not-supplied proof; no-`add()`/no-`add_artifact_reference()`/no-`seal()`/no-`start_collection()` proof; propagation of `AggregateNotFound`; propagation of the domain `ValueError` (invalid state, duplicate `criterion_id`) via a real `EvidencePackage` fixture; propagation of `OptimisticConcurrencyConflict` via a fake repository; `CommandEntryPoint` binding and reuse. Contract tests: typed-conformance to `CommandHandler`, `handle` signature shape, no-inheritance. Integration tests (PostgreSQL, opt-in): golden path; invalid-state; duplicate-`criterion_id`; missing-identity; genuine deterministic conflict (Section 19).

## 21. Alternatives and Rejections

`add_artifact_reference()` as this milestone's own primary capability (scope Section 8, Candidate 2) rejected in favor of `add_criterion_result()` — structurally identical value, deferred as the direct symmetric follow-on, not because it is inferior. A caller-supplied `evidence_package_id` field on the command (redundant with `command.identity.governance_id`) rejected — would require a handler-level consistency check duplicating validation `CriterionResult`/`EvidencePackage` already perform, and would introduce a mismatch failure mode with no legitimate caller use case (Section 4).

## 22. Risks

None beyond those already inherent in the frozen design. This milestone's own conflict evidence is now a genuine, unqualified `OptimisticConcurrencyConflict` reproduction (Section 6/19) — no disclosed boundary of the kind M038 required.

## 23. Hostile Self-Review

Reviewed against every established pitfall from M032/M035/M038: no second `get()`/`save()` call; no `add()` call; no `add_artifact_reference`/`seal`/`invalidate`/`start_collection` call; no `Review` reference; `evidence_package_id` is derived, never separately supplied and compared; the conflict mechanism is genuinely reproduced, not asserted by analogy without independent re-verification during implementation.

## 24. Final Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.** Proceeds directly into implementation within this same mission, per the active protocol.
