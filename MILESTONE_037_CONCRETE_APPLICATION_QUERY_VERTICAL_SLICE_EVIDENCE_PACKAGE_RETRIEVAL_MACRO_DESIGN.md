# MILESTONE-037 - Concrete Application Query Vertical Slice (EvidencePackage Retrieval) Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced within the same consolidated Macro Milestone Mission as the M037 Macro Scope. Not independently frozen.

## 2. Architectural Context

`EvidencePackage` currently has one proven application-layer verb (`add()`, M036). `EvidencePackageRepository.get()` is frozen (M020) and already implemented at the adapter level (`PostgresEvidencePackageRepository.get`, M023) — this milestone adds only the application-layer query and handler.

## 3. Repository-Verified Facts

Verified live against the frozen baseline:

- `EvidencePackageRepository.get(identity) -> LoadedAggregate[EvidencePackage]`, raising `AggregateNotFound` when no persisted `EvidencePackage` exists and `InvalidPersistedAggregateState` when durable state cannot be safely restored (`src/empirical_platform/evidence/repository.py`).
- `EvidencePackage` exposes `identity`, `run_id`, `state`, `version`, `next_transition_sequence`, `transition_history`, `criterion_results`, `artifact_references` (`src/empirical_platform/evidence/package.py`).
- `EvidencePackageLifecycleState` values: `INITIALIZED`, `COLLECTING`, `SEALED`, `INVALIDATED` (verified against `src/empirical_platform/evidence/lifecycle.py`).
- `GetRunQuery`/`GetRunHandler`/`RunSnapshot` (`src/empirical_platform/usecases/get_run.py`) is the direct structural precedent: caller-supplied full `DomainIdentity`, handler with one repository dependency, bounded snapshot excluding `version`/`persisted_version`/collections/history.

## 4. Query Identity Candidate Analysis

Two options: (a) caller-supplied full `DomainIdentity[EvidencePackageId]` (governance ID + runtime ID), mirroring `GetRunQuery`/`GetCampaignQuery`; (b) governance-ID-only lookup. Option (b) would require a new repository method (`get_by_governance_id`) not present in the frozen M020 `EvidencePackageRepository` Protocol — out of scope, since this milestone may not alter frozen repository contracts. Option (a) uses the existing frozen `get()` signature unchanged.

## 5. Selected Query Identity Model

Caller-supplied full `DomainIdentity[EvidencePackageId]`, passed unchanged to `EvidencePackageRepository.get()`.

## 6. Result Contract Analysis

Mirroring `RunSnapshot`'s deliberately bounded shape (identity + FK-parent reference + lifecycle state only, excluding `version`, `persisted_version`, collections, and `transition_history`), the same exclusions apply for `EvidencePackage`: `criterion_results` and `artifact_references` are omitted (unbounded collections, no milestone-local consumer, would require their own read-model versioning decision) exactly as `RunSnapshot` omitted `manifests`.

## 7. Selected Result Contract

`EvidencePackageSnapshot(identity: DomainIdentity[EvidencePackageId], run_id: RunId, state: EvidencePackageLifecycleState)`.

## 8. Exact Query Contract

```python
@dataclass(frozen=True, slots=True)
class GetEvidencePackageQuery:
    identity: DomainIdentity[EvidencePackageId]
```

## 9. Exact Handler Contract

```python
class GetEvidencePackageHandler:
    __slots__ = ("_evidence_package_repository",)

    def __init__(self, *, evidence_package_repository: EvidencePackageRepository) -> None:
        self._evidence_package_repository = evidence_package_repository

    def handle(self, query: GetEvidencePackageQuery) -> EvidencePackageSnapshot:
        loaded = self._evidence_package_repository.get(query.identity)
        return EvidencePackageSnapshot(
            identity=loaded.aggregate.identity,
            run_id=loaded.aggregate.run_id,
            state=loaded.aggregate.state,
        )
```

Sole dependency: `EvidencePackageRepository`. No `RunRepository`, no mutation call of any kind.

## 10. Exact Sequence

1. Receive query.
2. Call `evidence_package_repository.get(query.identity)` exactly once.
3. Construct exactly one `EvidencePackageSnapshot` from `loaded.aggregate`.
4. Return the snapshot.

No write, no `save()`/`add()` call, no second `get()` call.

## 11. Error Semantics

Transparent, unchanged propagation of `AggregateNotFound` and `InvalidPersistedAggregateState`. No handler-level `try`/`except`.

## 12. Validation Ownership

`DomainIdentity`/`EvidencePackageId` own identity-shape validation at construction (already frozen). The handler performs no additional validation.

## 13. Transaction Ownership

No application-level transaction orchestration — one repository-owned `get()` call.

## 14. QueryEntryPoint Binding

Test-only direct construction, mirroring `GetRunHandler`/`GetCampaignHandler`. No production composition root.

## 15. Architecture-Checker Impact

None expected: `usecases` already has `evidence` in `ALLOWED["usecases"]` (added in M036). To be independently re-verified live during implementation (Section B7 of the mission), not assumed from this design alone.

## 16. PostgreSQL Success Strategy

Fresh disposable `postgres:17` container: create one `EvidencePackage` via the already-frozen M036 `CreateEvidencePackageHandler`, then retrieve it via `GetEvidencePackageHandler`, asserting `identity`, `run_id`, and `state == INITIALIZED` all match.

## 17. PostgreSQL Not-Found Strategy

Fresh disposable `postgres:17` container: attempt retrieval of a `DomainIdentity` that was never persisted, asserting `AggregateNotFound` is raised.

## 18. Test Strategy

Unit tests (fake repository): golden-path snapshot construction; exactly-one-`get()`-call proof; no-mutation-call proof (constructor shape excludes any write dependency); `AggregateNotFound`/`InvalidPersistedAggregateState` propagation; `QueryEntryPoint` binding and reuse. Contract tests: typed-conformance to `QueryHandler`, `handle` signature shape, no-inheritance. Integration tests (PostgreSQL, opt-in): golden path; not-found; no-production-composition.

## 19. Alternatives and Rejections

Governance-ID-only lookup (Section 4) rejected — would require altering the frozen M020 repository Protocol, out of scope for a milestone that only adds an application-layer query. Exposing `criterion_results`/`artifact_references` on the snapshot rejected (Section 6) — mirrors `RunSnapshot`'s own established exclusion of unbounded collections.

## 20. Risks

None beyond those already inherent in the frozen design: the persistence-layer `get()` implementation is unchanged since M023 and already exercised by 5 M036 integration tests via a different code path (`AggregateNotFound` reload-check), so this milestone's PostgreSQL risk is low.

## 21. Hostile Self-Review

Reviewed against every established pitfall from M031/M034 (the two prior retrieval milestones): no second `get()` call; no write call of any kind; no exposure of `version`/`persisted_version` on the snapshot; no `Review` reference; no listing/pagination; identity model uses the existing frozen `get()` signature without requiring any repository Protocol change.

## 22. Final Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.** Proceeds directly into implementation within this same mission, per the active protocol.
