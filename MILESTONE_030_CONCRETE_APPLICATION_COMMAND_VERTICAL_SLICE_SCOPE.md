# MILESTONE-030 - Concrete Application Command Vertical Slice Scope

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW**

This document is a scope candidate. It has not been reviewed, approved, or frozen. No design or implementation of MILESTONE-030 is authorized by this document. This is a scope-selection artifact only.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at scope selection | `f8482bbccbb1de8ea61f8f1237767280c8e91930` |
| Milestone | MILESTONE-030 |

---

## 3. Frozen Predecessor Chain

| Milestone | Status | Delivered |
| --- | --- | --- |
| M020 | APPROVED_AND_FROZEN | Persistence-neutral domain repository and optimistic-concurrency contracts (Campaign, Run, EvidencePackage, Review) |
| M021 | APPROVED_AND_FROZEN | Mapper contracts and durable-record shapes |
| M022 | APPROVED_AND_FROZEN | PostgreSQL schema and Alembic migration |
| M023 | APPROVED_AND_FROZEN | Concrete PostgreSQL mappers and repository adapters |
| M024 | APPROVED_AND_FROZEN | Multi-aggregate persistence Unit of Work (`run_composed`) |
| M025 | APPROVED_AND_FROZEN | Repository runtime composition (`PostgresRepositoryRuntime`) |
| M026 | APPROVED_AND_FROZEN | Foundation runtime repository composition (`FoundationRuntime.repository_runtime`) |
| M027 | APPROVED_AND_FROZEN | `CommandHandler[C, R]` Protocol |
| M028 | APPROVED_AND_FROZEN | `QueryHandler[Q, R]` Protocol |
| M029 | APPROVED_AND_FROZEN (scope, design, implementation) | Application service orchestration boundary (`CommandEntryPoint`, `QueryEntryPoint`) |

All ten prior milestones remain untouched by this scope-selection mission.

---

## 4. Architectural Context

### 4.1 What the repository already contains (evidence-based inventory)

**Implemented and frozen:**

1. Four domain aggregates with complete lifecycle behavior: `Campaign` (`src/empirical_platform/campaign/aggregate.py` — construction plus `revise_scope_statement`, `prepare_for_authorization`, `record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel`), `Run`, `EvidencePackage`, `Review`.
2. Four domain repository Protocols (`CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository`), each persistence-neutral, each frozen at M020.
3. Four concrete PostgreSQL repository adapters implementing those Protocols, frozen at M023.
4. `PostgresRepositoryRuntime` composing all four adapters over one shared `PostgresPersistenceService`, with `run_composed()` for atomic multi-repository operations, frozen at M024-M025.
5. `FoundationRuntime.repository_runtime: PostgresRepositoryRuntime | None`, wired by `initialize_foundation_runtime_with_postgresql`, frozen at M026.
6. `CommandHandler[_CommandT_contra, _ResultT_co]` and `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocols, each a single `handle()` method, frozen at M027-M028.
7. `CommandEntryPoint[CommandT, ResultT]` and `QueryEntryPoint[QueryT, QueryResultT]` in `src/empirical_platform/application/` — each binds one handler at construction and invokes it exactly once per call, propagating results and exceptions unchanged, frozen at M029.

**Partially present:**

- `src/empirical_platform/entrypoints/` contains only `health.py` and `version.py` — static diagnostic payload generators with no business dispatch. No transport, no HTTP, no CLI command surface beyond these two.

**Absent (verified by direct search):**

- **Zero concrete commands, queries, or handlers exist anywhere in the repository.** A repository-wide search for any type conforming to `CommandHandler[...]` or `QueryHandler[...]` beyond the Protocol definitions themselves and the M029 entry-point generics returns no results.
- No composition-root code binds any concrete handler to a `CommandEntryPoint` or `QueryEntryPoint` instance — because no concrete handler exists to bind.
- No `FoundationRuntime` field or method exposes any application-layer entry point.

**Explicitly deferred (per `PROJECT_CHECKPOINT.md` Section 9 and the M029 scope document's dependency chain):**

- "Later concrete business-handler milestones → define actual commands and handlers" (M029 scope document, Section 3, dependency chain).
- Retry-on-`OptimisticConcurrencyConflict` policy, explicitly deferred until "concrete business handlers exist."
- APIs, workers, Audit runtime, Decision Candidate, Decision Freeze.
- Market-data, vendor, trading, or empirical campaign execution behavior.

### 4.2 The architectural gap this scope addresses

Every layer of the CQRS/persistence stack is frozen, but **no two adjacent layers have ever been exercised together with a real, concrete operation.** `CommandHandler`, `QueryHandler`, and the M029 entry points were validated exclusively against mock/fake handlers in their own unit and contract tests (by design — each milestone froze a structural contract, not a concrete use). There is currently no evidence in the repository that a real command, invoked through the real M029 boundary, calling a real domain aggregate, persisted through the real frozen repository stack, actually works end-to-end.

This is the smallest coherent next capability: a single, narrow, concrete vertical slice proving the entire frozen stack composes correctly for one real write operation.

---

## 5. Problem Statement

The platform has ten frozen milestones of structural scaffolding — Protocols, an invocation boundary, and a persistence stack — and zero evidence that any of it functions together for a real operation. Every future business capability (market-data ingestion, campaign execution, decision review) depends on this composition working. MILESTONE-030 closes that gap with the smallest possible proof: one concrete command, one concrete handler, exercised end-to-end.

---

## 6. Selected Scope

**Concrete Application Command Vertical Slice: Campaign Creation.**

A single write-side (command) operation — creating a new `Campaign` — implemented as one concrete command type and one concrete handler conforming to the frozen M027 `CommandHandler` Protocol, invoked through the frozen M029 `CommandEntryPoint`, persisting through the frozen M023 `PostgresCampaignRepository` via the frozen M025 `PostgresRepositoryRuntime`.

**Why Campaign, and why creation:**

- `Campaign` is the only domain aggregate with zero dependency on any other domain aggregate (`campaign: {shared, identifiers, governance, registry}` in `tools/check_architecture.py` — no `run`, `evidence`, or `review`). It is the most self-contained subject available.
- `Campaign.__init__` already performs full construction with existing validation (`_require_non_empty`, `_require_optional_non_empty`); `CampaignRepository.add()` already exists for first-time persistence (`AggregateAlreadyExists` on duplicate). Both are frozen, unmodified by this milestone.
- Creation is the narrowest possible write operation: it requires no prior aggregate state, no optimistic-concurrency handling, and no `run_composed()` multi-aggregate coordination.

---

## 7. Mission Statement

Prove, with one concrete, minimal, real command, that the frozen application invocation boundary, the frozen `CommandHandler` Protocol, and the frozen persistence stack compose correctly end-to-end — without introducing transport, without introducing a second aggregate, and without introducing any framework, registry, or abstraction beyond what M029 already provides.

---

## 8. In-Scope Capabilities

1. Define one concrete command type representing "create a new Campaign" with the minimal data `Campaign.__init__` already requires.
2. Define one concrete handler conforming to the frozen `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol that: constructs a `Campaign` aggregate from the command's data, persists it via the frozen `CampaignRepository.add()` (through `PostgresRepositoryRuntime.campaigns`), and returns the new Campaign's identity.
3. Demonstrate binding this handler to a `CommandEntryPoint` and invoking it, proving the M029 boundary's contract holds for a real (not mock) handler.
4. Contract tests proving the concrete handler conforms to the frozen `CommandHandler` Protocol.
5. Integration tests proving the full path (`CommandEntryPoint` → concrete handler → `Campaign` aggregate → `PostgresCampaignRepository` → PostgreSQL) succeeds for the golden path and fails correctly for the one already-frozen failure mode this operation can hit (`AggregateAlreadyExists` on duplicate identity).
6. Identify (not answer) the design questions concrete handlers raise that M029's design intentionally left open (module/package placement for concrete commands and handlers; how the command's input is validated before aggregate construction; how the handler obtains its `PostgresRepositoryRuntime` dependency).

---

## 9. Out-of-Scope Capabilities

- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any Campaign operation other than creation (no `activate`, `suspend`, `resume`, `complete`, `cancel`, or scope revision).
- Any query (read-side) vertical slice. Read-side proof is deferred to a later, separate milestone, consistent with the established project precedent of freezing `CommandHandler` (M027) and `QueryHandler` (M028) as separate, sequential milestones rather than paired.
- Any composition-root abstraction, handler registry, service locator, or dependency-injection framework. The handler is bound to its `CommandEntryPoint` directly, exactly as the M029 design's own illustrative binding pattern demonstrates (Section 5 of `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN.md`: a handler instance passed directly to the entry point's constructor at composition time). This scope names no concrete class for that handler; naming is a design decision.
- Any transport layer: no HTTP endpoint, no CLI command, no worker, no queue consumer. The vertical slice is proven by tests invoking the bound entry point directly, the same way M029's own tests do.
- Any retry, idempotency, or optimistic-concurrency-conflict handling (creation via `add()` has no prior version to conflict with).
- Any `run_composed()` multi-aggregate atomic operation (creation touches exactly one aggregate).
- Any new architecture-checker package or dependency rule beyond what M029 already established, unless design discovers a genuine gap (in which case that gap is a design question for MILESTONE-030 design to raise, not an authorization granted by this scope document).
- Any market-data, vendor, trading-strategy, order-execution, or brokerage-integration behavior.
- Any change to M020-M029 frozen contracts, source files, or governance documents.
- Any MILESTONE-031 work of any kind.

---

## 10. Non-Goals

- This is not "application layer completion." It is one narrow proof, not a general-purpose command/query authoring framework.
- This is not a business-requirements milestone. Campaign creation's validation rules are already frozen in `Campaign.__init__`; this milestone adds no new business rule.
- This is not a performance, scalability, or production-readiness milestone.
- This is not an attempt to anticipate or design for every future concrete command. Whatever pattern this milestone establishes is a precedent to evaluate, not a framework to enforce on future milestones.

---

## 11. Dependencies

**Depends on (frozen, read-only):**

- M020 `CampaignRepository` Protocol and `Campaign` aggregate.
- M023 `PostgresCampaignRepository` concrete adapter.
- M025 `PostgresRepositoryRuntime` (specifically the `campaigns` property).
- M026 `FoundationRuntime.repository_runtime`.
- M027 `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol.
- M029 `CommandEntryPoint[CommandT, ResultT]`.

**Does not depend on:** M028 `QueryHandler` (out of scope), any `Run`/`EvidencePackage`/`Review` material, any transport or entrypoint code.

---

## 12. Frozen Contracts That Must Remain Unchanged

- `src/empirical_platform/campaign/aggregate.py` (`Campaign`, `CampaignScopeStatement`) — M020.
- `src/empirical_platform/campaign/repository.py` (`CampaignRepository` Protocol) — M020.
- `src/empirical_platform/shared/persistence/postgres_repositories/campaign_repository.py` (`PostgresCampaignRepository`) — M023.
- `src/empirical_platform/shared/persistence/postgres_repositories/runtime.py` (`PostgresRepositoryRuntime`) — M025.
- `src/empirical_platform/shared/bootstrap.py` (`FoundationRuntime`) — M026.
- `src/empirical_platform/shared/contracts/command.py` (`CommandHandler`) — M027.
- `src/empirical_platform/application/command.py` (`CommandEntryPoint`) — M029.
- `tools/check_architecture.py` — M029, extendable only if design proves a genuine new boundary is needed; not assumed by this scope.

MILESTONE-030 design and implementation must use these exactly as they exist today. No modification, no reinterpretation, no compatibility shim.

---

## 13. Expected Design Questions

This scope selection identifies these as open; it answers none of them:

1. Where do concrete commands and concrete handlers live in the package structure (new top-level package? subpackage of an existing one?), consistent with `tools/check_architecture.py`'s existing rules and M029's Package Rule 6 (composition root).
2. How does the concrete handler obtain its `PostgresRepositoryRuntime` dependency — constructor parameter, some other injection point?
3. What is the command's exact data shape, and how/where is it validated before constructing the `Campaign` aggregate (does the command perform its own validation, or does it rely entirely on `Campaign.__init__`'s existing checks)?
4. What identity-generation mechanism supplies the new `CampaignId` (the repository already-frozen `RuntimeIdentifierGenerator` exists in `FoundationRuntime`; does the handler receive it, or the command)?
5. What does "binding" look like concretely for this one handler — a bare `CommandEntryPoint(ConcreteHandler(...))` call site in a test/example, or something else — and where does that call site live?
6. Does this handler's test suite reveal any gap in M029's frozen design that needs a documented interpretation (not a redesign)?

---

## 14. Acceptance Boundaries

MILESTONE-030 is complete when, and only when:

- One concrete command type and one concrete handler exist, conforming to the frozen `CommandHandler` Protocol.
- The handler is invoked through a `CommandEntryPoint` bound to it (not called directly), proving the M029 boundary functions with a real handler.
- The handler persists a new `Campaign` via the frozen `PostgresCampaignRepository.add()` and returns its identity.
- Contract tests prove Protocol conformance; integration tests prove the golden path and the `AggregateAlreadyExists` failure path both work end-to-end against real PostgreSQL.
- No M020-M029 frozen file is modified.
- No second aggregate, no query, no transport, and no registry/DI framework is introduced.
- All existing repository validation gates pass (mypy strict, ruff, architecture checker, full test suite, build).

---

## 15. Scope-Compliance Rules

- Design may answer the open questions in Section 13. Design may not reopen any decision M029 already froze (transaction ownership, error propagation, handler-resolution posture, sync-only execution).
- Implementation may only touch: one new command type, one new handler, their tests, and (if design determines it necessary and justifies it) one narrowly-scoped architecture-checker addition for wherever the concrete command/handler package lives.
- Any discovery during design or implementation that this scope is too narrow, too broad, or wrongly bounded must be escalated as a scope-change request under the standard governance rule (Section 16), not silently absorbed.

---

## 16. Prohibited Implementation Expansion

Silent expansion of this scope during design or implementation — adding a second command, adding the query side, adding transport, adding a registry, adding retry logic, adding a second aggregate — requires explicit owner authorization, a documented reason, independent review, and a new governance commit. It may not happen inside a MILESTONE-030 design or implementation commit without that authorization.

---

## 17. Deferred Capabilities

- The symmetric query-side vertical slice (Campaign retrieval via `QueryHandler`/`QueryEntryPoint`) — a separate future milestone.
- Any composition-root abstraction beyond direct binding, if repeated concrete handlers later reveal a genuine need for one.
- Retry-on-`OptimisticConcurrencyConflict` policy (requires a "save" operation on an existing aggregate, which this milestone does not include).
- Any transport/entrypoint adapter exposing this or any future command.
- All `Run`, `EvidencePackage`, and `Review` commands and queries.
- All market-data, vendor, trading, and campaign-execution business behavior.
- MILESTONE-031 and beyond.

---

## 18. Review Criteria

Independent scope review should evaluate:

1. Is Campaign creation genuinely the narrowest available concrete vertical slice, or does a narrower one exist?
2. Does this scope smuggle in any design decision it claims to defer?
3. Does this scope duplicate or reopen any M029 frozen decision?
4. Is the exclusion of the query side correctly justified, or does excluding it create an incoherent half-slice?
5. Are the acceptance boundaries objectively verifiable without further scope interpretation?
6. Does this scope avoid every category the mission explicitly prohibited (transport, registries, DI frameworks, trading/market-data/execution behavior)?

---

## 19. Owner Decision Status

**CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW**

Not approved. Not frozen. No design or implementation of MILESTONE-030 is authorized.

---

## 20. Next Permitted Action After Scope Approval

If and only if this scope is approved by independent review and owner-frozen: **MILESTONE-030 DESIGN.**

Until that freeze occurs, the next permitted action is **MILESTONE-030 INDEPENDENT SCOPE REVIEW** only.
