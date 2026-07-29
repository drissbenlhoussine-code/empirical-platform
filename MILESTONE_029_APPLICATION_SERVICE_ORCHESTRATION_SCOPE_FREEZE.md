# MILESTONE-029 - Application Service Orchestration Scope Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-029-SCOPE-FREEZE |
| Title | Application Service Orchestration Scope Freeze |
| Status | Scope approved and frozen |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Milestone | MILESTONE-029 |
| Responsibility | Application Service Orchestration |
| Frozen authority chain | M020-M028 APPROVED_AND_FROZEN → M029 scope selected → M029 scope re-reviewed → M029 scope approved and frozen (this document) |
| Baseline HEAD | `fc5e8659d5a35b609c96a689b8b250f7f869d73d` (M028 implementation freeze commit) |
| Baseline origin/master | `fc5e8659d5a35b609c96a689b8b250f7f869d73d` (M028 implementation freeze commit) |

This document records the owner's authorization to freeze the MILESTONE-029 Application Service Orchestration scope following independent review approval. This freeze is final; any later change to the frozen scope requires explicit owner re-authorization.

---

## 2. Frozen Milestone Identity

**MILESTONE:** MILESTONE-029

**Title:** Application Service Orchestration

**Responsibility:** Establish the application-layer invocation boundary that coordinates routing of commands to `CommandHandler` implementations and queries to `QueryHandler` implementations, defining transaction lifecycle boundaries, error handling discipline, and handler lifecycle semantics without freezing implementation details.

---

## 3. Frozen Scope-Selection Commit

**Commit:** `449d7ef3005402e4c92052fc8720dbd19b623102`

**Message:** `docs: select corrected M029 application orchestration scope`

**Date:** 2026-07-29 23:26:11 +0300

**Author:** Driss Benlhoussine <drissbenlhoussine@gmail.com>

**Scope content:** `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_SCOPE_SELECTION.md` at this commit defined the corrected, final scope selection incorporating hostile independent review feedback.

---

## 4. Governance Recording Commit

**Commit:** `b8c1e8e9b59318138e42d106cebd3e389e03fba5`

**Message:** `docs: record M029 scope-selection commit hash in checkpoint`

**Date:** 2026-07-29 23:26:33 +0300

**Author:** Driss Benlhoussine <drissbenlhoussine@gmail.com>

**Purpose:** Recorded scope-selection commit hash in `PROJECT_CHECKPOINT.md`, confirming repository truth alignment with governance intent.

---

## 5. Independent Review Decision

**Review Type:** Hostile independent re-review of corrected M029 scope selection

**Verdict:** **M029 SCOPE APPROVED WITH NON-BLOCKING OBSERVATIONS**

**Observations:** Two non-blocking documentation corrections identified:

1. Replace remaining `M030+` wording with generic future references.
2. Correct stale duplicate checkpoint baseline metadata.

Both observations have been addressed in this freeze commit.

---

## 6. Owner Freeze Declaration

I, the owner, declare the corrected MILESTONE-029 Application Service Orchestration scope **APPROVED AND FROZEN** effective immediately upon this commit.

No further changes to the frozen scope are permitted without:
- Explicit owner re-authorization
- Documented reason
- Independent review where material
- A new governance commit recording the change

The corrected scope, as defined in `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_SCOPE_SELECTION.md` (commit `449d7ef`), is the canonical and authoritative frozen scope for MILESTONE-029.

---

## 7. Frozen Responsibility

MILESTONE-029 establishes the application service orchestration layer — a thin, coherent responsibility boundary that:

1. **Defines the application invocation interface:** the point where external callers (transport layers, workers, integration points) hand off commands and queries to the application layer.

2. **Coordinates invocation:** routes commands to `CommandHandler` implementations and queries to `QueryHandler` implementations following the frozen M027-M028 Protocols.

3. **Preserves semantic intent:** maintains the CQRS distinction between command (write) and query (read) handling throughout the orchestration boundary.

4. **Unifies error handling:** establishes a single point of error translation, wrapping, or passthrough strategy (to be determined by M029 design).

5. **Owns transaction lifecycle:** determines whether transaction boundaries are orchestrated explicitly or delegated to handlers (to be determined by M029 design).

6. **Manages handler lifecycle:** determines instantiation, discovery, registration, and disposal semantics (to be determined by M029 design).

This responsibility is **bounded**: orchestration does not implement persistence, domain logic, transport concerns, audit runtime, retry policies, or business execution. Those are outside M029's scope.

---

## 8. Frozen Boundaries

### In Scope

**Application Service Orchestration responsibility:**

- Define the application invocation boundary between external callers and frozen domain/persistence layers (M020-M028).
- Coordinate invocation of frozen `CommandHandler[C, R]` and `QueryHandler[Q, R]` Protocols (M027-M028).
- Preserve semantic distinction between command (write) handling and query (read) handling.
- Establish compatibility requirements with M027 and M028.
- Identify transaction ownership questions that design must resolve.
- Identify error propagation and translation questions that design must resolve.
- Identify handler lifecycle questions (instantiation, disposal, callbacks) that design must resolve.
- Define architectural boundaries to prevent transport, infrastructure, audit, retry, and business-use-case concerns from leaking into the orchestration layer.
- Establish testing obligations (contract tests, error propagation tests, orchestration-layer-only tests).

**What M029 design must determine:**

- How handlers are discovered or instantiated (factory? DI? static? method reference?).
- Whether transaction boundaries are orchestrated explicitly or delegated to handlers.
- How errors from handlers are translated, wrapped, or passed through.
- Whether orchestration is synchronous, asynchronous, or supports both.
- What module structure and public API shape the orchestration layer takes.
- Whether new architecture rules are needed for the application package boundary.

### Out of Scope

**Explicitly out of scope:**

- Concrete `CreateCampaignCommand`, `GetCampaignQuery`, etc.
- Concrete `CommandHandler` or `QueryHandler` implementations.
- Application error hierarchy (uses existing M020 domain errors).
- Runtime handler registry or service locator implementation.
- Dependency injection container.
- HTTP transport layer, API routing, or API-specific concerns.
- Worker or background job execution.
- Retry and idempotency policies.
- Audit or event logging runtime.
- Observability, tracing, or metrics collection.
- Market-data, vendor, trading, or empirical campaign execution.
- Async/await or coroutine support (synchronous or deferred).

### Non-Goals

- Inventing a new application error taxonomy (reuse M020 domain errors).
- Implementing a dependency injection framework.
- Implementing a query language or DSL.
- Implementing caching, pagination, result transformation, or result envelopes.
- Implementing saga, event-sourcing, or saga patterns.
- Implementing authorization or authentication.
- Implementing observability or structured logging (application layer concern, not orchestration).

### Deferred Items

- All concrete application commands and handlers (later concrete business-handler milestones).
- Handler instantiation strategies and DI (later concrete business-handler milestones).
- Transaction implementation and ownership semantics (M029 design determines; later milestones implement).
- Error taxonomy extensions (if needed; later milestones; reuse M020 for now).
- Async orchestration (if needed; later enhancement).
- Retry and idempotency policies (later infrastructure milestones).
- APIs, HTTP transport, routing (later infrastructure milestones).
- Workers and background execution (later infrastructure milestones).
- Audit and event runtime (later observability milestones).
- Business use cases (market-data, trading, empirical campaign execution; much later).

---

## 9. Compatibility Constraints

**M029 must respect frozen M027-M028 Protocols:**

- `CommandHandler[_CommandT_contra, _ResultT_co]` from M027 is a immutable frozen contract.
- `QueryHandler[_QueryT_contra, _QueryResultT_co]` from M028 is an immutable frozen contract.
- M029 orchestration must invoke these Protocols without modifying them.
- No inheritance, reimplementation, or re-export of M027-M028 types.

**M029 must preserve M020-M026 persistence foundation:**

- No changes to repository Protocols (M020).
- No changes to mapper contracts (M021).
- No changes to PostgreSQL schema or migrations (M022).
- No changes to concrete PostgreSQL mappers (M023).
- No changes to multi-aggregate unit of work (M024).
- No changes to repository runtime composition (M025).
- No changes to foundation runtime composition (M026).

**M029 is a peer of M027-M028:**

- M029 defines the orchestration boundary that uses M027-M028.
- M029 does not modify, extend, or depend on any future milestone (M030+).
- M029 design must be complete before M030+ can be considered.

---

## 10. Architecture Obligations

**Positive architecture impact:**

- Establishes the application layer as a well-defined, distinct boundary.
- Separates domain/persistence (M020-M026) from application invocation semantics.
- Sets the pattern for all future application-layer responsibilities.
- Enables coherent error handling and lifecycle management across the entire application.

**Architecture questions M029 design must resolve:**

- Does the application package require new architecture enforcement rules?
- What imports are forbidden from the orchestration module?
- What must remain isolated to orchestration, and what may be delegated to handlers?

**No changes required to M020-M028:**

- Frozen contracts remain exactly as defined.
- Orchestration uses them; does not modify them.
- All architecture rules for M020-M028 remain in effect.

---

## 11. Validation Obligations

**Expected validation gates for M029 design and implementation** (scope selection does not freeze specifics; gates must be confirmed during design):

- Python 3.13 compilation.
- Ruff format and linting.
- MyPy type checking (0 issues; full strict mode on application module).
- Unit and contract tests (to be specified during design).
- Architecture checker (validates package boundary rules determined by M029 design).
- Build (sdist + wheel).

**No PostgreSQL regression tests required** (orchestration does not implement persistence).

**No new test fixtures required** (orchestration reuses existing domain/persistence test fixtures).

---

## 12. Success Criteria — Met

The frozen M029 scope is complete when:

- [x] Scope defines a coherent application invocation boundary between M027-M028 (frozen) and future business logic.
- [x] Scope identifies all design questions (transaction, error handling, instantiation, discovery, lifecycle) without freezing answers.
- [x] No implementation details are frozen (class names, method signatures, module structure, concrete classes).
- [x] No unsupported estimates appear (implementation size, duration, complexity).
- [x] Architecture constraints are framed as design questions, not frozen decisions.
- [x] Error handling strategy is identified as a design question, not frozen.
- [x] Handler lifecycle and instantiation are identified as design questions, not frozen.
- [x] All future milestone references (M030+, M031+, etc.) are replaced with generic language.
- [x] Scope is narrower and more coherent than the first draft.
- [x] Command and query semantics remain distinguishable.
- [x] No M020-M028 files are touched.
- [x] Document quality is normalized (encoding, consistency, clarity).

---

## 13. Explicitly Unresolved Design Questions

Scope freeze confirms that the following design questions **remain unresolved** and must be determined during M029 design:

- **Concrete class names:** No public class names are frozen; design determines them.
- **Concrete public method names:** Orchestration's public API signatures remain open; design determines them.
- **Concrete signatures or generics:** Method parameter types, return types, and type variable definitions are design decisions.
- **Module/package placement:** Where orchestration code lives in `src/` and `tests/` is a design decision.
- **Handler registration:** How handlers are registered, discovered, or made available to orchestration is a design decision.
- **Handler discovery:** Whether by explicit registration, service locator, DI container, static factory, or other mechanism is a design decision.
- **Dependency injection:** Whether orchestration uses explicit DI, implicit service locator, static composition, or factory pattern is a design decision.
- **Provider or service-locator mechanisms:** If needed, what provider pattern or service locator design is used is a design decision.
- **Handler construction:** How handlers are instantiated (eager, lazy, singleton, per-request, etc.) is a design decision.
- **Transaction ownership:** Whether orchestration owns transactions, delegates to handlers, or shares ownership is a design decision.
- **run_composed caller:** Whether orchestration or handlers call `PostgresPersistenceService.run_composed()` is a design decision.
- **Implicit or explicit transaction wrapping:** Whether transactions wrap handlers implicitly or handlers must request them explicitly is a design decision.
- **Query transaction policy:** Whether queries can use transactions, must use transactions, or transaction behavior is unspecified for queries is a design decision.
- **Error mapping, translation, wrapping, or passthrough:** How handler exceptions are transformed into application-layer responses is a design decision.
- **New application error classes:** Whether to create error classes or reuse M020 domain errors is a design decision.
- **Lifecycle implementation:** How handler lifecycle callbacks (if any) are implemented is a design decision.
- **Synchronous or asynchronous mechanics:** Whether orchestration is synchronous, asynchronous, or supports both is a design decision.
- **Retry or idempotency policy:** Whether and how orchestration implements or enables retry is a design decision.
- **Transport adapters:** HTTP, gRPC, event-driven, or other transport adapters are outside M029; design determines orchestration's boundary with them.
- **Concrete business commands, queries, or handlers:** Any specific domain logic or business use case is outside M029; design determines none of them.

---

## 14. Change-Control Rule

Any later change to the frozen M029 scope requires:

1. **Explicit owner authorization** — the owner must approve the change by name and rationale.
2. **Documented reason** — the change request must state why the scope change is necessary.
3. **Independent review where material** — if the change affects core responsibility boundaries or design questions, independent review is required.
4. **A new governance commit** — the change must be recorded in `PROJECT_CHECKPOINT.md` and any new freeze record.
5. **No silent alteration** — scope changes cannot be discovered retroactively; they must be announced and tracked.

Until such a change is authorized, the frozen scope is the sole source of truth for MILESTONE-029's boundaries.

---

## 15. Next Permitted Action

**M029 DESIGN** is now permitted.

**Explicit permissions:**

- MILESTONE-029 design phase may proceed.
- Design must identify which of the unresolved design questions (Section 13) it addresses.
- Design must propose answers to unresolved questions without modifying the frozen responsibility boundaries.
- Design must respect all frozen M027-M028 Protocols and M020-M026 foundation.

**Explicit prohibitions:**

- **Implementation is NOT permitted** until design is approved and frozen.
- **Source code changes are NOT permitted** during design phase.
- **Tests may not be added** during design (test obligation confirmation yes; implementation no).
- **Later milestones (M030+) are NOT permitted** until M029 design is complete and approved.
- **No changes to M020-M028** are permitted under any circumstance.

---

## 16. Repository State

**Repository:** `C:\Users\LuxSy\Documents\trading`

**Branch:** `master`

**Baseline:** `fc5e8659d5a35b609c96a689b8b250f7f869d73d` (M028 implementation freeze commit)

**Scope freeze record commit:** (to be recorded upon successful push)

---

## 17. Closed Milestone State

```text
MILESTONE-020   APPROVED_AND_FROZEN (design, implementation, freeze)
MILESTONE-021   APPROVED_AND_FROZEN (design, implementation, freeze)
MILESTONE-022   APPROVED_AND_FROZEN (design, implementation, freeze)
MILESTONE-023   APPROVED_AND_FROZEN (design, implementation, freeze)
MILESTONE-024   APPROVED_AND_FROZEN (design, implementation, freeze)
MILESTONE-025   APPROVED_AND_FROZEN (design, implementation, freeze)
MILESTONE-026   APPROVED_AND_FROZEN (design, implementation, freeze)
MILESTONE-027   APPROVED_AND_FROZEN (design, implementation, freeze)
MILESTONE-028   APPROVED_AND_FROZEN (design, implementation, freeze)
MILESTONE-029   SCOPE_APPROVED_AND_FROZEN (design NOT_STARTED, implementation NOT_STARTED)
MILESTONE-030+  NOT_STARTED (awaiting M029 design completion)
```

---

## 18. Final Status

```
M029 APPLICATION SERVICE ORCHESTRATION SCOPE APPROVED AND FROZEN

Independent Review:    M029 SCOPE APPROVED WITH NON_BLOCKING_OBSERVATIONS
Freeze Authority:      OWNER
Scope Selection:       449d7ef3005402e4c92052fc8720dbd19b623102
Governance Recording:  b8c1e8e9b59318138e42d106cebd3e389e03fba5
Scope Freeze Status:   APPROVED_AND_FROZEN

NEXT PERMITTED ACTION: MILESTONE-029 DESIGN

Implementation:        NOT_STARTED
Later Milestones:      NOT_STARTED
M020-M028:             UNCHANGED
```
