# MILESTONE-034 - Concrete Application Query Vertical Slice (Run Retrieval) Design Freeze

## 1. Milestone Identity

MILESTONE-034 — Concrete Application Query Vertical Slice: Run Retrieval, Design stage.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `d28295ebc1c1c5f59c85cface6ba18fadd96b3ab` |

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Run Creation) | APPROVED_AND_FROZEN (implementation freeze `38ed45518d8a2068d29e7375c2c09ea2af80963c`) |

## 4. M034 Scope Authority

`MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE.md` — scope candidate commit `3ee8485143f1397cad9d14bc55744e97f60aa9d3`. Selects exactly one capability: one concrete Run-retrieval query vertical slice via the frozen `RunRepository.get()`.

## 5. M034 Scope-Correction Authority

Correction commit `60178d3d1caf96d1fe33f318e57e94c708e8896f` (`docs: correct M034 scope result-shape neutrality`, finding `M034-SCOPE-REVIEW-0001`) removed a premature result-shape commitment from the scope, leaving the exact result contract open for the Design Mission.

## 6. M034 Scope-Freeze Authority

`MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE_FREEZE.md`, commit `e6ad2c0e976ad0eb1cd00f8e15544d58ac45de7e`. **M034 SCOPE APPROVED_AND_FROZEN.** This design freeze makes no change to the scope, scope-correction, or scope-freeze authority.

## 7. Original Design Candidate Commit

`d343e38cba9b5a49db278c72ca1650dd50839bd2` (`docs: define M034 Run retrieval design candidate`) — selected the full-`DomainIdentity[RunId]` query model and, as the central load-bearing decision, a new milestone-local `RunSnapshot` result contract over the raw `Run` aggregate, `LoadedAggregate[Run]`, and existing frozen types.

## 8. Initial Independent Design-Review Decision

**M034 DESIGN REQUIRES CORRECTION.** Two findings: `M034-DESIGN-REVIEW-0001` (MAJOR, BLOCKING) — the design conflated `Run.version` (the aggregate's own domain-state field, advancing through lifecycle transitions and `append_manifest()`, embedded in `StateTransitionRecord`) with `LoadedAggregate.persisted_version` (the separate repository-loaded concurrency token `RunRepository.save()` consumes). `M034-DESIGN-REVIEW-0002` (MINOR) — an overstatement that a plain Python dataclass runtime-enforces its annotated field type. Every other decision (capability, query identity model, handler shape, single-`get()` sequence, transparent error behavior, architecture boundary, PostgreSQL strategy) was independently verified sound.

## 9. Design Correction Commit

`993144e4361372e6978b11d96d6e1fe98e722c73` (`docs: correct M034 Run version design semantics`; hash recorded in follow-up `d28295ebc1c1c5f59c85cface6ba18fadd96b3ab`). `Run.version` and `LoadedAggregate.persisted_version` are now distinguished precisely by name and definition throughout the design document. An explicit Aggregate-Version Decision independently evaluates and selects excluding `Run.version` from `RunSnapshot` on Run-specific grounds (numerical coincidence with `persisted_version` at load time creates a concurrency-token confusability hazard), not by M031 symmetry. The `persisted_version` exclusion is independently justified against M032's own frozen caller-supplied `expected_persisted_version` precedent (`PrepareCampaignForAuthorizationCommand`). The dataclass runtime-enforcement overstatement is corrected. No other design decision was reopened.

## 10. Final Independent Design Re-Review Decision

The final independent design re-review verified: repository truth; the correction-only two-file delta; reproduction of the original MAJOR and MINOR findings; the correct, precise distinction between `Run.version` and `persisted_version` throughout; coherent, independently-justified exclusion of both version fields from `RunSnapshot`; explicit deferral of read-to-update concurrency-token acquisition; truthful bounded header/status result semantics; deliberate (not dismissive) exclusion of Run-owned `manifests`/`transition_history`; corrected dataclass runtime-type wording; preservation of `GetRunQuery`/`GetRunHandler` contracts, the exact one-`get()` sequence, transparent not-found/error behavior, no transaction orchestration, no architecture-checker permission change, no scope creep, checkpoint consistency, and that no MILESTONE-035 work exists.

**Decision: M034 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL or MAJOR findings remain.

## 11. Non-Blocking Observations

1. A future implementation test should preferably construct a `LoadedAggregate` whose `aggregate.version` and `persisted_version` are deliberately distinguishable values, proving neither leaks into `RunSnapshot` and that the two version concepts are never conflated in test evidence (strengthens Section 32 below; does not change the result contract).
2. `RunSnapshot` is a broad name, but the approved design (Section 15 below) explicitly and truthfully defines it as a bounded Run header/status result, not a complete Run-state representation — consistent with `CampaignSnapshot`'s own established precedent of excluding an aggregate's own version field. Renaming is not required.

These observations do not authorize redesign and are carried forward as explicit implementation-test obligations (Section 32).

## 12. Owner Approval

The owner formally freezes the M034 design via this document.

**M034 DESIGN APPROVED_AND_FROZEN.**

## 13. Frozen Run Retrieval Semantics

`RunRepository.get(identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]` (MILESTONE-020). `PostgresRunRepository.get()` (MILESTONE-023) unconditionally loads the `run` root row plus all `run_manifest`/`run_transition` rows, reconstructs a full `Run` aggregate, and raises `AggregateNotFound(aggregate_kind="Run", identity=identity)` when no matching root row exists. No query against the `campaign` table occurs. No secondary repository call occurs.

## 14. Frozen Query Identity Model

`GetRunQuery` carries the full `DomainIdentity[RunId]` `RunRepository.get()` already requires — selected over a split-field model, a raw-string model (would force an unused `RuntimeIdentifierGenerator` dependency), and a governance-ID-only model (no resolution mechanism exists in the frozen codebase).

## 15. Frozen Result Contract

**`RunSnapshot`** — a new milestone-local, immutable, bounded Run header/status result — selected over the raw `Run` aggregate (mutability leakage: seven lifecycle-transition methods plus `append_manifest`), `LoadedAggregate[Run]` (same leakage plus `persisted_version` exposure), and any existing frozen type (none carries the needed shape).

Exact fields:

```python
@dataclass(frozen=True, slots=True)
class RunSnapshot:
    identity: DomainIdentity[RunId]
    campaign_id: CampaignId
    state: RunLifecycleState
```

Exactly three fields. No defaults. No mutable collections. No raw `Run` aggregate. No `LoadedAggregate` leakage.

## 16. Bounded RunSnapshot Semantics

`RunSnapshot` is explicitly frozen as a **bounded Run header/status application result** — it is not, and must not be reinterpreted as, a complete representation of every Run-owned field. It intentionally excludes `Run.version`, `LoadedAggregate.persisted_version`, `next_transition_sequence`, `transition_history`, and `manifests`. This bounded-result framing is the correction's own resolution to the "misleading snapshot completeness" concern the independent design review's MAJOR finding raised, and is preserved unchanged by Non-Blocking Observation 2 (Section 11), which confirms no rename is required.

## 17. Aggregate-Version Decision

`Run.version` (`AggregateVersion`) is frozen as: meaningful aggregate domain state, advanced by `Run._transition()` and `Run.append_manifest()`, embedded in every `StateTransitionRecord`, and distinct from `persisted_version` — **not** persistence metadata and **not** the optimistic-concurrency token itself. It is deliberately excluded from `RunSnapshot`. The omission is a bounded result-contract decision (concurrency-token confusability at load time, and the Mission Statement's proof obligation not requiring it), not a conceptual reclassification of what `Run.version` is.

## 18. Persisted-Version Decision

`LoadedAggregate.persisted_version` is frozen as: repository-loaded persistence/concurrency metadata, distinct from `Run.version`, used as `expected_persisted_version` for optimistic-concurrency writes (`RunRepository.save()`). It is excluded from `RunSnapshot`. **M034 does not provide read-to-update concurrency-token acquisition** — a caller needing `expected_persisted_version` for a future M032-style Run update must obtain it independently (mirroring M032's own caller-supplied-command-field precedent); that capability remains deferred (Section 36).

## 19. Manifest/History Representation Decision

`manifests` and `transition_history` are Run-owned state, eagerly reconstructed by `RunRepository.get()` as an unavoidable side effect of the frozen M020/M023 contract. They are deliberately not exposed by this bounded first Run-retrieval result — a scope/design choice about how much of one aggregate's own state a minimal first read-side proof needs to expose, not a judgment that they are irrelevant or cross-aggregate. Their future exposure remains deferred (Section 36).

## 20. Exact Query Contract

Module: `src/empirical_platform/usecases/get_run.py`

```python
@dataclass(frozen=True, slots=True)
class GetRunQuery:
    """Request to retrieve a Run by its full frozen identity."""

    identity: DomainIdentity[RunId]
```

Exactly one field. No defaults. No extra metadata. A passive, immutable typed carrier — plain dataclass mechanics do not runtime-enforce the annotated field type; no `__post_init__`; no duplicated identifier validation.

## 21. Exact Handler Contract

```python
class GetRunHandler:
    """Retrieves a Run for one `GetRunQuery`."""

    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, query: GetRunQuery) -> RunSnapshot:
        loaded = self._run_repository.get(query.identity)
        return RunSnapshot(
            identity=loaded.aggregate.identity,
            campaign_id=loaded.aggregate.campaign_id,
            state=loaded.aggregate.state,
        )
```

Sole constructor dependency: `run_repository: RunRepository`. No `CampaignRepository`. No identifier generator. No concrete persistence/runtime adapter. Structurally conforms to `QueryHandler[GetRunQuery, RunSnapshot]`. Synchronous only.

## 22. Exact Retrieval Sequence

1. Receive one `GetRunQuery`.
2. Call `RunRepository.get(query.identity)` exactly once, passing `query.identity` unchanged.
3. Receive one `LoadedAggregate[Run]`.
4. Read `loaded.aggregate.identity`, `loaded.aggregate.campaign_id`, `loaded.aggregate.state` only.
5. Construct exactly one `RunSnapshot`.
6. Return the snapshot.

No second `get()`. No Campaign lookup. No retry. No cache. No transaction orchestration. No use of `loaded.persisted_version`, `loaded.aggregate.version`, `manifests`, or `transition_history`.

## 23. Return Semantics

Exactly one `RunSnapshot` per successful `handle()` call.

## 24. Not-Found Behavior

Transparent, unchanged propagation of `AggregateNotFound` — required by the already-frozen `QueryEntryPoint` contract, which propagates results and exceptions unchanged. No handler `try`/`except`. No translation. No nullable result. No envelope. No retry.

## 25. Error Semantics

Transparent, unchanged propagation of `InvalidPersistedAggregateState` and any arbitrary repository error, identically to `AggregateNotFound`. No new error hierarchy.

## 26. Validation Ownership

Callers construct a valid `DomainIdentity[RunId]`; `RunId`/`DomainIdentity` own all value validation via their own frozen `__post_init__` checks; static typing expresses intended `GetRunQuery` usage; Python dataclass annotations are not automatically runtime-enforced; the repository owns all persisted-reconstruction validation; the handler orchestrates only, performing no duplicate validation; `RunSnapshot` performs no new business validation.

## 27. Transaction Non-Ownership

No application-level transaction orchestration. No `run_composed()`. One repository-owned read operation only (`RunRepository.get()`'s own internal `unit_of_work()`).

## 28. QueryEntryPoint Binding

Direct construction in tests only (`QueryEntryPoint(GetRunHandler(run_repository=...))`). No registry, query bus, dispatcher, mediator, service locator, DI framework, or production composition root.

## 29. Package and Dependency Boundaries

Approved production module: `src/empirical_platform/usecases/get_run.py`. Required imports: `dataclasses.dataclass`; `empirical_platform.identifiers.pairs.DomainIdentity`; `empirical_platform.identifiers.types.{RunId, CampaignId}`; `empirical_platform.run.repository.RunRepository`; `empirical_platform.campaign.lifecycle.RunLifecycleState`. Necessary `usecases` package exports may be updated narrowly during implementation to expose `GetRunQuery`/`GetRunHandler`/`RunSnapshot`.

## 30. Architecture-Checker Impact

**None required.** `ALLOWED["usecases"]` already includes `"run"` (and `"campaign"`, needed for the `RunLifecycleState` import) — verified directly against live `tools/check_architecture.py` source. Existing `FORBIDDEN_IMPORT_PREFIXES["usecases"]` protections remain unchanged and sufficient. Focused architecture evidence may be added during implementation only if it provides genuine new proof beyond what existing `usecases` fixtures already cover.

## 31. PostgreSQL Evidence Strategy

Mirrors `tests/integration/test_m031_get_campaign_usecase.py`'s established pattern: seed a Campaign via the frozen M030 `CreateCampaignHandler`, seed a Run via the frozen M033 `CreateRunHandler`, obtain a real `PostgresRunRepository` externally, bind `GetRunHandler` through `QueryEntryPoint`, and assert: golden-path snapshot field correctness; `AggregateNotFound` for a missing identity; no Campaign-table query occurs; no schema/migration change; M033 creation and M023 repository regression; no production composition machinery is required.

## 32. Test Obligations

All obligations from the design document (Section 25 A-G) are frozen, with the two non-blocking observations incorporated as explicit strengthened obligations:

- `set(RunSnapshot.__slots__) == {"identity", "campaign_id", "state"}`, explicitly proving both `Run.version` and `LoadedAggregate.persisted_version` are absent.
- **New (Observation 1):** unit-test evidence must construct a `LoadedAggregate[Run]` whose `aggregate.version` and `persisted_version` are deliberately different, distinguishable values, and assert that neither appears anywhere on the returned `RunSnapshot` — proving the two version concepts are not conflated in evidence, not merely in prose.
- Exactly one `get()` call per `handle()` invocation; no second call after a failed `get()`.
- Transparent `AggregateNotFound`/arbitrary-error propagation, verified by `excinfo.value is exc` identity checks.
- `RunSnapshot` immutability (`AttributeError` on assignment) and no mutable-collection aliasing.
- Structural `QueryHandler[GetRunQuery, RunSnapshot]` conformance (mypy-checked typed assignment).
- Real `tools/check_architecture.py` run over the actual new source, zero permission change.
- The full twelve-item PostgreSQL evidence strategy (Section 31).

No arbitrary coverage-percentage threshold is imposed.

## 33. Implementation Authorization Boundary

A future M034 implementation mission may touch only what is narrowly required for:

- `src/empirical_platform/usecases/get_run.py`
- necessary `usecases` package exports
- focused unit tests
- focused contract tests
- PostgreSQL integration tests
- narrowly justified architecture evidence (only if it provides genuine new proof)
- the M034 implementation document
- `PROJECT_CHECKPOINT.md`
- the mandatory external-review package

It must not modify: `Run` aggregate; `RunRepository`; `PostgresRunRepository`; Campaign contracts; `DomainIdentity`/`RunId` contracts; `LoadedAggregate`; `QueryHandler`; `QueryEntryPoint`; architecture permissions; schemas or migrations; M030-M033 source; any frozen governance authority.

## 34. Prohibited Expansion

No Run listing, filtering, pagination, Campaign lookup/join, cross-aggregate enrichment, Run creation changes, Run lifecycle transition, Run save/update, second Run query, generic read-model framework, projection framework, generic result envelope, caching, retry, composition root, registry, query bus, dispatcher, mediator, service locator, DI framework, transport/API layer, audit integration, `EvidencePackage`/`Review` work, market-data/trading behavior, schema/migration change, or MILESTONE-035 work of any kind.

## 35. Preserved M020-M033 Authority

This freeze makes no change to any M020-M033 frozen contract, source file, test, or governance document, and no change to the M034 scope, scope-correction, or scope-freeze authority (Sections 4-6). All prior authority remains exactly as previously frozen.

## 36. Deferred Work

- Exposing `Run.version`, `manifests`, or `transition_history` through a Run read model — a future, independently-scoped milestone.
- Read-to-update `expected_persisted_version` acquisition for a future Run update workflow — a future, independently-scoped milestone, if genuinely evidenced.
- Run lifecycle-transition command (M032's role, for Run).
- `EvidencePackage`/`Review` creation.
- Retry-on-`OptimisticConcurrencyConflict` policy.
- Any composition-root abstraction beyond direct binding.
- MILESTONE-035 and beyond.

## 37. Final Status

**M034 DESIGN APPROVED_AND_FROZEN.**

M034 Implementation: NOT_STARTED.
M035: NOT_STARTED.

## 38. Next Permitted Action

**MILESTONE-034 IMPLEMENTATION MISSION.**
