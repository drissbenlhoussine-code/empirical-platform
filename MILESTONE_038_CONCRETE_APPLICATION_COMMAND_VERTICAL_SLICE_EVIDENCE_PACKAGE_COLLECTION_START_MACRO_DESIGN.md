# MILESTONE-038 - Concrete Application Command Vertical Slice (EvidencePackage Collection Start) Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced within the same consolidated Macro Milestone Mission as the M038 Macro Scope. Not independently frozen.

## 2. Architectural Context

`EvidencePackage` currently has two proven application-layer verbs (`add()` M036, `get()` M037). `EvidencePackageRepository.save()` is frozen (M020) and already implemented at the adapter level (`PostgresEvidencePackageRepository.save`, M023) — this milestone adds only the application-layer command and handler for the first lifecycle transition.

## 3. Repository-Verified Facts

Verified live against the frozen baseline:

- `EvidencePackage.start_collection(*, actor, occurred_at, correlation_id=None, reason=None)` transitions `INITIALIZED -> COLLECTING`, raising `ValueError` if the current state is not `INITIALIZED` (`src/empirical_platform/evidence/package.py`).
- `EvidencePackageRepository.save(aggregate, *, expected_persisted_version) -> SaveResult`, raising `AggregateNotFound` when no persisted `EvidencePackage` exists, `OptimisticConcurrencyConflict` when the durable version does not match `expected_persisted_version`, and `InvalidAggregateForPersistence` when the in-memory aggregate is invalid.
- `AuthorizeRunCommand`/`AuthorizeRunHandler` (`src/empirical_platform/usecases/authorize_run.py`) is the direct structural precedent: `identity`, `expected_persisted_version`, `actor`, `occurred_at`, `correlation_id`, `reason` fields; handler loads, mutates, saves, returns `SaveResult`.

## 4. Command Field Analysis

`start_collection()` requires `actor`/`occurred_at`/`correlation_id`/`reason`, identical to `Run.authorize()`'s signature. No additional domain data is required (unlike a hypothetical `add_criterion_result` command, out of scope per the scope document Section 12). The command therefore mirrors `AuthorizeRunCommand` field-for-field.

## 5. Selected Command Contract

```python
@dataclass(frozen=True, slots=True)
class StartEvidencePackageCollectionCommand:
    identity: DomainIdentity[EvidencePackageId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

## 6. Deterministic PostgreSQL Conflict Mechanism — Independently Derived

The scope document (Section 7) established that `EvidencePackage` has **no non-transition, version-advancing method available while `INITIALIZED`** — `start_collection()` is the only method that operates on that state. The M032 (`revise_scope_statement`) and M035 (`append_manifest`) "unrelated interfering write" pattern therefore cannot be reused unmodified.

**Independently derived mechanism — two independent loaders racing the same transition:**

1. Persist one `EvidencePackage` (via the frozen M036 `CreateEvidencePackageHandler`) — `persisted_version = 0`, state `INITIALIZED`.
2. Independently load it twice: `loaded_a = repo.get(identity)`, `loaded_b = repo.get(identity)` — both see `persisted_version = 0`, both see `INITIALIZED`.
3. Call `loaded_b.aggregate.start_collection(...)` (domain-valid: in-memory state is `INITIALIZED`) — in-memory version advances to 1, state becomes `COLLECTING`.
4. Save `loaded_b.aggregate` via `repo.save(loaded_b.aggregate, expected_persisted_version=AggregateVersion(0))` — **succeeds**, durable `persisted_version` becomes 1.
5. Invoke the command under test (`StartEvidencePackageCollectionHandler`) against the *original* `identity`, with `expected_persisted_version=AggregateVersion(0)` (the version captured before step 3's interference — a plausible, genuinely stale caller expectation).
6. The handler independently loads `loaded_c = repo.get(identity)` (durable state now `COLLECTING`, `persisted_version=1`), calls `loaded_c.aggregate.start_collection(...)` — this is **not** domain-valid, since the durable aggregate is already `COLLECTING`, so `start_collection()` raises `ValueError` **before** `save()` is ever reached.

**Step 6 reveals a genuine, independently-discovered design problem, not asserted by analogy:** unlike `Campaign.revise_scope_statement()` and `Run.append_manifest()` (which preserve the *target* command's expected starting state while only advancing the version), `EvidencePackage.start_collection()` **as the interfering write also changes the state away from `INITIALIZED`** — so the second (command-under-test) caller's own `start_collection()` call fails on the domain precondition check, never reaching `save()`, and therefore never reaching `OptimisticConcurrencyConflict` at all. A literal race on the *same* transition produces a domain-level `ValueError`, not a repository-level `OptimisticConcurrencyConflict` — these are different, both real, and both must be tested, but they are not interchangeable.

**Resolved mechanism:** the deterministic PostgreSQL conflict test targets the domain-level `ValueError` path (Section 16 — genuinely reproducible, deterministic, and does not require inventing a repository bypass), and is treated as the primary "second writer wins" scenario for this milestone. A true `OptimisticConcurrencyConflict` reproduction is **not achievable for `start_collection()` specifically** without a repository-level version bypass that would not reflect any genuine caller path (rejected — this project's PostgreSQL evidence must always exercise a real, domain-valid call sequence, never a fabricated shortcut). This is recorded as a scope-appropriate boundary (Section 20), not a defect: `OptimisticConcurrencyConflict` itself remains proven at the repository/handler-propagation level via the existing M032/M035 fake-repository unit tests (mirrored here at unit level, Section 18) and via `save()`'s own frozen M023 contract tests — this milestone's unique contribution is proving `EvidencePackage.save()` genuinely propagates a stale-`expected_persisted_version` `OptimisticConcurrencyConflict` when a **non-transition-state-preserving** interference is used at the unit level (a fake repository can construct this precisely, since it is not bound by `EvidencePackage`'s own domain preconditions the way two real sequential PostgreSQL transitions are).

## 7. Exact Handler Contract

```python
class StartEvidencePackageCollectionHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, command: StartEvidencePackageCollectionCommand) -> SaveResult:
        loaded = self._evidence_package_repository.get(command.identity)
        package = loaded.aggregate
        package.start_collection(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._evidence_package_repository.save(
            package, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no `CampaignRepository`.

## 8. Exact Sequence

1. Receive command.
2. Call `evidence_package_repository.get(command.identity)` exactly once.
3. Call `package.start_collection(...)` exactly once on the loaded aggregate.
4. Call `evidence_package_repository.save(package, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the `SaveResult` unchanged.

No `add()` call. No second `get()`/`save()` call. No `add_criterion_result`/`add_artifact_reference`/`seal`/`invalidate` call.

## 9. Result Contract

`SaveResult` (`operation`, `persisted_version`), mirroring `AuthorizeRunHandler`'s/`PrepareCampaignForAuthorizationHandler`'s return contract exactly — the caller needs the new persisted version after a write.

## 10. Error Semantics

Transparent, unchanged propagation of `AggregateNotFound` (missing `EvidencePackage`), the domain `ValueError` (invalid-state `start_collection()` call — e.g., already `COLLECTING`/`SEALED`/`INVALIDATED`), `OptimisticConcurrencyConflict` (stale `expected_persisted_version` against a durable state where a domain-valid `start_collection()` retry would still succeed — see Section 18 for how this is exercised at unit level), and `InvalidAggregateForPersistence`. No handler-level `try`/`except`.

## 11. Validation Ownership

`DomainIdentity`/`EvidencePackageId`/`AggregateVersion` own their own format validation at construction. `EvidencePackage.start_collection()` owns its own state-precondition and `occurred_at`-type validation. The handler performs no additional validation.

## 12. Transaction Ownership

No application-level transaction orchestration — one repository-owned `save()` call, already atomic via its own `unit_of_work()`.

## 13. CommandEntryPoint Binding

Test-only direct construction, mirroring `AuthorizeRunHandler`/`PrepareCampaignForAuthorizationHandler`. No production composition root.

## 14. Architecture-Checker Impact

None expected: `usecases` already has `evidence` in `ALLOWED["usecases"]` (since M036). To be independently re-verified live during implementation, not assumed.

## 15. PostgreSQL Success Strategy

Fresh disposable `postgres:17` container: create one `EvidencePackage` via the frozen M036 handler, transition it via `StartEvidencePackageCollectionHandler`, assert `SaveResult.persisted_version == AggregateVersion(1)`, then independently reload and assert `state == COLLECTING`.

## 16. PostgreSQL Invalid-State Strategy

Fresh disposable `postgres:17` container: persist an `EvidencePackage`, transition it once (state now `COLLECTING`), then invoke the command again against the same identity — the handler's own `start_collection()` call raises `ValueError` (already `COLLECTING`, not `INITIALIZED`) before `save()` is ever reached. Independently reproduces the two-racing-callers scenario described in Section 6.

## 17. PostgreSQL Missing-Identity Strategy

Fresh disposable `postgres:17` container: invoke the command against a `DomainIdentity` with no persisted `EvidencePackage`, asserting `AggregateNotFound`.

## 18. Test Strategy

Unit tests (fake repository, unconstrained by domain preconditions): golden-path `get()`-then-`start_collection()`-then-`save()` sequence proof; exact call-count and call-order proofs; propagation of `AggregateNotFound`; propagation of `OptimisticConcurrencyConflict` via a fake repository whose `save()` raises it directly regardless of in-memory domain state (a fake repository is not bound by `EvidencePackage`'s own state machine, so it can isolate the pure repository-contract-propagation proof independently of the state-machine interaction Section 6 identified); propagation of the domain `ValueError` when the fake aggregate is not in `INITIALIZED`; `CommandEntryPoint` binding and reuse. Contract tests: typed-conformance to `CommandHandler`, `handle` signature shape, no-inheritance. Integration tests (PostgreSQL, opt-in): golden path; invalid-state (two-racing-callers); missing-identity; no-production-composition.

## 19. Alternatives and Rejections

A repository-level version bypass to force a "clean" `OptimisticConcurrencyConflict` PostgreSQL reproduction (Section 6) was considered and rejected — it would not correspond to any genuine caller path and would violate this project's standing discipline that all PostgreSQL evidence must exercise a real, domain-valid call sequence.

## 20. Risks

The PostgreSQL "conflict" evidence for this specific transition manifests as a domain `ValueError`, not `OptimisticConcurrencyConflict`, for the reason independently derived in Section 6 — recorded explicitly as a scope-appropriate boundary of this specific transition (`start_collection()` has no non-transition interfering write available), not a defect, and not a gap in `OptimisticConcurrencyConflict` propagation proof (which remains covered at the unit level, Section 18, and by the pre-existing M023 `save()` adapter-level tests).

## 21. Hostile Self-Review

Reviewed against every established pitfall from M032/M035: no second `get()`/`save()` call; no `add()` call; no `add_criterion_result`/`add_artifact_reference`/`seal`/`invalidate` call; no `Review` reference; the conflict-mechanism gap (Section 6/20) is disclosed up front rather than silently omitted or misrepresented as a standard `OptimisticConcurrencyConflict` PostgreSQL reproduction.

## 22. Final Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.** Proceeds directly into implementation within this same mission, per the active protocol.
