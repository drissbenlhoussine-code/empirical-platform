# MILESTONE-034 - Concrete Application Query Vertical Slice (Run Retrieval) Scope Freeze

## 1. Milestone Identity

MILESTONE-034 — Concrete Application Query Vertical Slice: Run Retrieval.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `e34642403f78204d21350fceca3a4fbb15871b5b` |

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Concrete Application Command Vertical Slice — Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Concrete Application Command Vertical Slice — Run Creation) | APPROVED_AND_FROZEN (scope, design, implementation — implementation freeze commit `38ed45518d8a2068d29e7375c2c09ea2af80963c`) |

All prior milestones remain untouched by this freeze.

## 4. Original M034 Scope Candidate Commit

`3ee8485143f1397cad9d14bc55744e97f60aa9d3` — `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE.md` defined the candidate: one Run-retrieval query vertical slice, selected over a Run lifecycle-transition command, `EvidencePackage` creation, `Review` creation, retry policy, composition-root wiring, transport, and stub-package work, via an explicit nine-criterion comparison matrix (scope document Sections 6-8).

## 5. Initial Independent Scope-Review Decision

The initial hostile independent scope review found the selected capability directionally correct and the sole candidate, but issued one blocking finding.

## 6. Blocking Finding

`M034-SCOPE-REVIEW-0001` — MAJOR, BLOCKING. Sections 9 and 13 of the scope document, and equivalent wording elsewhere, prematurely committed the retrieval handler's result to a "read value" / "minimal, immutable, milestone-local read value" shape. That is a design decision and must not be frozen during scope selection; the scope was required to leave all result-shape options open for the Design Mission.

## 7. Scope Correction Commit

`60178d3d1caf96d1fe33f318e57e94c708e8896f` — `docs: correct M034 scope result-shape neutrality`. Removed every premature result-shape commitment from Sections 6, 9, 13, 14, 18, and 23, replacing each with neutral language: the handler returns one retrieval result, with the exact type and representation left open for the Design Mission. The selected capability (one Run retrieval query vertical slice) was not reopened. Hash recorded in follow-up commit `e34642403f78204d21350fceca3a4fbb15871b5b` (`docs: record M034 scope correction commit hash`).

## 8. Final Independent Scope Re-Review Decision

The final independent scope re-review verified: repository truth; the correction-only two-file delta; reproduction of the original blocking finding; full removal of the premature result-shape commitment; true result-shape neutrality; preservation of exactly one Run retrieval capability; full `DomainIdentity[RunId]` repository truth; existing `AggregateNotFound` repository behavior; no hidden design replacement; no architecture-boundary change; sequencing correctness; independent testability; checkpoint consistency; and that no MILESTONE-035 work exists.

**Decision: M034 SCOPE APPROVED FOR OWNER FREEZE.** No corrections remain.

## 9. Owner Approval

The owner formally freezes the M034 scope via this document.

**M034 SCOPE APPROVED_AND_FROZEN.**

## 10. Official Milestone Name

Concrete Application Query Vertical Slice (Run Retrieval).

## 11. Frozen Mission Statement

Prove, with one concrete, minimal, real query, that the frozen `usecases` read-side application-invocation pattern — established and validated exclusively against `Campaign` via `GetCampaignHandler` (M031) — genuinely generalizes to a second aggregate, without introducing any Run mutation capability, without introducing a third aggregate, and without introducing any framework, registry, or abstraction beyond what is already frozen.

## 12. Frozen In-Scope Capability

- One concrete query representing "retrieve an existing Run by its full identity," carrying the minimal data the frozen repository's `get()` method already requires.
- One concrete handler conforming to the frozen `QueryHandler` Protocol that calls the frozen repository's `get()` method and returns one retrieval result. The exact result type and representation are not selected by this scope; that decision belongs to the Design Mission.
- Binding this handler to a `QueryEntryPoint` and invoking it, proving the frozen read-side boundary's contract holds for a second aggregate.
- Contract tests proving the concrete handler conforms to the frozen `QueryHandler` Protocol.
- Integration tests proving the golden path (retrieval of a Run created via the frozen M033 slice) and the already-frozen `AggregateNotFound` failure path both work end-to-end against real PostgreSQL.
- Identification (not resolution) of the design questions a `Run`-specific query handler raises that M031's `Campaign`-specific design did not need to independently re-answer.

## 13. Frozen Out-of-Scope Capabilities

- Run creation changes; any Run lifecycle-transition command (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`); any Run mutation of any kind; Run save/update.
- Any second Run query; any Run listing, filtering, pagination, or searching.
- Any Campaign lookup/join or cross-aggregate enrichment.
- Any additional Campaign command or query beyond M030-M032.
- Any command or query for `EvidencePackage` or `Review`.
- Any retry, idempotency, backoff, or optimistic-concurrency-conflict handling.
- Any composition-root abstraction, handler registry, dispatcher, mediator, service locator, or dependency-injection framework — direct construction only.
- Any transport/API layer of any kind, and any transport serialization contract.
- Any caching.
- Any audit/registry/governance integration.
- Any generic read-model framework or generic projection framework.
- Any schema or migration change.
- Any market-data, vendor, trading-strategy, order-execution, or brokerage-integration behavior.
- Any change to MILESTONE-020 through MILESTONE-033 frozen contracts, source files, or governance documents.
- Any MILESTONE-035 work of any kind.

## 14. Frozen Non-Goals

- This milestone is not a general-purpose "Run management" read capability; it exercises exactly one operation (`get()`-based retrieval-by-identity), not a generic query framework.
- This milestone is not the Run-lifecycle-transition milestone; it does not attempt to prove `save()`/`OptimisticConcurrencyConflict` generalization.
- This milestone does not decide whether Run lifecycle transition or EvidencePackage/Review work comes next.

## 15. Frozen Dependencies

**Depends on (frozen, read-only):**

- MILESTONE-020 `RunRepository` Protocol (`get()` method) and `Run` aggregate.
- MILESTONE-023 concrete PostgreSQL `Run` repository adapter's `get()` implementation.
- MILESTONE-025 repository runtime composition.
- MILESTONE-028 `QueryHandler` Protocol.
- MILESTONE-029 `QueryEntryPoint`.
- MILESTONE-031's already-delivered `Campaign` retrieval vertical slice (pattern reference only, not a result-shape mandate).
- MILESTONE-033's already-delivered `Run` creation vertical slice, used to seed a real Run for retrieval evidence.

**Does not depend on:** any `EvidencePackage`/`Review` material, any Run mutation work, any transport or entrypoint code, any composition-root abstraction.

## 16. Frozen Contracts Preserved

The following remain exactly as frozen, unmodified, throughout this milestone's design and implementation:

- `Run` aggregate and its constructor (MILESTONE-020).
- `RunRepository` Protocol, including its existing `get()` method signature (MILESTONE-020).
- The concrete PostgreSQL `Run` repository adapter (MILESTONE-023).
- `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol (MILESTONE-028).
- `QueryEntryPoint[QueryT, QueryResultT]` (MILESTONE-029).
- Everything MILESTONE-030 through MILESTONE-033 delivered: their concrete commands/queries, their concrete handlers, `CampaignSnapshot`, and the `usecases` package's existing architecture-checker rules (including `"run"`, already granted, verified directly in `tools/check_architecture.py`).

## 17. Identity Truth

`RunRepository.get(identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]` — verified directly in `src/empirical_platform/run/repository.py`. Retrieval is by full `DomainIdentity[RunId]`, mirroring `CampaignRepository.get()`.

## 18. Existing Not-Found Truth

A missing identity raises `AggregateNotFound` — verified directly in `src/empirical_platform/shared/contracts/repository.py`. This behavior is already frozen (M023) and is not a new decision; the Design Mission determines only how the handler propagates it, not whether it exists.

## 19. Result-Shape Neutrality

The exact result type and representation are explicitly OPEN and NOT selected by this freeze. The Design Mission may evaluate, without scope preference: a raw `Run`; `LoadedAggregate[Run]`; an immutable snapshot; a milestone-local read value/DTO; an existing frozen type; or another narrow, justified result type. This freeze does not authorize a generic read-model framework, a generic projection framework, listing, filtering, pagination, Campaign joins, cross-aggregate enrichment, or transport serialization — the result decision must be resolved within the single-Run-by-identity capability boundary, not used to expand it.

## 20. Open Design Mission Questions

Not decided by this freeze:

- The exact query type's name, shape, and fields.
- The exact handler type's name and shape.
- The exact module path and package exports.
- The exact result type, its name, representation, and which fields or data it carries.
- Whether the result is an existing frozen type or a new milestone-local type.
- Whether `persisted_version` or other write-side metadata is included or excluded in the result, and why.
- The exact identity representation used by the query (expected: full `DomainIdentity[RunId]`, mirroring `GetCampaignQuery`, but not frozen here).
- The exact error-treatment / `AggregateNotFound` propagation mechanics at the handler boundary.
- The exact `QueryEntryPoint` binding pattern (expected: test-only direct construction, mirroring M031, but not frozen here).
- Exact constructor dependencies, test filenames, and PostgreSQL test setup.
- Any narrowly-scoped architecture-checker evidence the design determines is required (none is currently expected, since `"run"` is already granted under `ALLOWED["usecases"]`).

## 21. Architecture-Boundary Implications

`ALLOWED["usecases"] = {"shared", "identifiers", "campaign", "run"}` already grants `"run"` (added by M033) — verified directly in `tools/check_architecture.py`. A Run-query module needs zero further checker change on current evidence. This freeze does not authorize any change to `tools/check_architecture.py`; any change the Design Mission later determines is genuinely required must be independently justified and reviewed at that time.

## 22. Acceptance Boundaries

This freeze is complete when:

- Exactly one read-side capability is frozen (Run retrieval by identity).
- No class name, method signature, module path, package structure, dependency-injection mechanism, registry, transaction behavior, error hierarchy, or result type/representation is fixed by this document.
- Every excluded capability is explicit.
- The freeze is independently reviewable without requiring the reviewer to resolve any open design question themselves.

## 23. Stop Conditions

This milestone stops at:

- One concrete query, one concrete handler, using `RunRepository.get()` only.
- Proof that the `usecases`/`QueryHandler`/`QueryEntryPoint` pattern composes correctly for a second aggregate.
- Contract, unit, architecture, and PostgreSQL integration test evidence, mirroring M031's established patterns.

It does not continue into any Run mutation, any Run lifecycle transition, any second aggregate beyond Run, composition-root work, or transport work, regardless of how natural such an extension might appear during design or implementation.

## 24. Prohibited Expansion

- No Run mutation or lifecycle-transition command.
- No `EvidencePackage`/`Review` command or query.
- No composition root, registry, dispatcher, mediator, or service locator.
- No transport layer of any kind.
- No listing/filtering/pagination.
- No generic read-model or projection framework.
- No MILESTONE-035 work.

## 25. Deferred Work

- Run lifecycle-transition command (mirroring M032's role, for a future milestone).
- `EvidencePackage` creation (a future milestone once its architectural leverage is reassessed).
- `Review` creation (blocked behind EvidencePackage).
- Retry-on-`OptimisticConcurrencyConflict` policy.
- Any composition-root abstraction beyond direct binding.
- Any transport/entrypoint adapter.
- MILESTONE-035 and beyond.

## 26. Design and Implementation Prohibition

This freeze authorizes scope only. It does not authorize design or implementation. No design document or implementation source for M034 exists as of this freeze (verified: no `get_run.py` or equivalent module exists anywhere in `src/`).

## 27. Preserved M020-M033 Authority

This freeze makes no change to any M020-M033 frozen contract, source file, test, or governance document. All M020-M033 authority remains exactly as previously frozen.

## 28. Final Status

**M034 SCOPE APPROVED_AND_FROZEN.**

M034 Design: NOT_STARTED.
M034 Implementation: NOT_STARTED.
M035: NOT_STARTED.

## 29. Next Permitted Action

**MILESTONE-034 DESIGN MISSION.**
