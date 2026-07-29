# MILESTONE-029 - Application Service Orchestration Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-029-SCOPE-SELECTION |
| Title | Application Service Orchestration Scope Selection |
| Status | Scope selected, ready for independent re-review |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen authority chain up to this point | M020-M028 all APPROVED_AND_FROZEN |
| Baseline HEAD | `fc5e8659d5a35b609c96a689b8b250f7f869d73d` (M028 implementation freeze commit) |

## 2. Purpose

Scope the application service orchestration layer — the bridge that coordinates invocation of command handlers and query handlers, defining responsibility boundaries and architectural constraints without freezing implementation details.

## 3. Why M029 Exists

**Dependency chain after M028:**

M020-M026 provide **persistence foundation**: domain repository contracts, mapper contracts, concrete PostgreSQL mappers, multi-aggregate unit of work, repository runtime composition, and foundation runtime setup.

M027 provides **write-side application vocabulary**: `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol — a structural type contract, no concrete implementation, no invocation mechanism.

M028 provides **read-side application vocabulary**: `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol — a structural type contract, no concrete implementation, no invocation mechanism.

**What is missing after M028:**

No defined application-layer boundary exists for:
- Receiving a command instance and invoking its handler.
- Receiving a query instance and invoking its handler.
- Managing handler lifecycle semantics (instantiation, disposal, lifecycle callbacks).
- Coordinating error handling and propagation across the application boundary.
- Defining transaction ownership — which layer initiates, commits, or rolls back transactions involving handler execution.

M029 fills this gap by defining **application service orchestration** — the smallest coherent responsibility boundary that:

1. Establishes the interface between external callers (transport, workers, integration points) and domain/persistence layers.
2. Coordinates invocation of frozen `CommandHandler` and `QueryHandler` types.
3. Preserves semantic distinction between command (write) and query (read) handling.
4. Identifies design questions that must be resolved before implementation.

## 4. Architectural Importance

**Why it matters:**

- **Highest leverage**: Everything above this layer (APIs, workers, business execution, observability, retry logic) depends on a well-defined orchestration boundary. Without M029, no coherent application layer exists.
- **Minimal coupling**: Orchestration coordinates frozen, domain-agnostic types; it does not duplicate or re-implement those contracts.
- **Maximum reuse**: Once orchestration boundary is defined, every concrete business handler (later concrete business-handler milestones) reuses it without modification to the boundary.
- **Unblocks future work**: Future application and infrastructure layers can only be built on top of a stable orchestration interface.

## 5. Business Importance

**Flow enabled by M029:**

```
External Caller
    |
    v
Application Invocation Interface (M029)
    |
    ├─ Coordinate handler discovery and instantiation
    ├─ Invoke CommandHandler or QueryHandler
    ├─ Manage transaction lifecycle (determined by M029 design)
    ├─ Handle errors (strategy determined by M029 design)
    |
    v
Persistence and Domain Layers (M020-M028)
    |
    v
Result to Caller
```

Without M029, no defined boundary exists between external callers and frozen domain/persistence layers. This blocks all application layer development.

## 6. Architectural Scope Selection Correction

This is a scope selection, not a design. The corrected scope does NOT freeze:

- class or method names
- concrete signatures or generics
- error class definitions
- handler instantiation mechanisms
- handler discovery or registration strategies
- transaction implementation or ownership model
- synchronous vs. asynchronous execution semantics
- package or module placement

These remain design questions.

## 7. IN SCOPE

**Application Service Orchestration responsibility:**

- Define the application invocation boundary between external callers and frozen domain/persistence layers.
- Coordinate invocation of frozen `CommandHandler[C, R]` and `QueryHandler[Q, R]` Protocols.
- Preserve semantic distinction between command (write) handling and query (read) handling.
- Establish compatibility requirements with M027 and M028.
- Identify transaction ownership questions that design must resolve.
- Identify error propagation and translation questions that design must resolve.
- Identify handler lifecycle questions (instantiation, disposal, callbacks) that design must resolve.
- Define architectural boundaries to prevent transport, infrastructure, audit, retry, and business-use-case concerns from leaking into the orchestration layer itself.
- Establish testing obligations (contract tests, error propagation tests, orchestration-layer-only tests).

**What M029 design must determine:**

- How handlers are discovered or instantiated (factory? DI? static? method reference?).
- Whether transaction boundaries are orchestrated explicitly or delegated to handlers.
- How errors from handlers are translated, wrapped, or passed through.
- Whether orchestration is synchronous, asynchronous, or supports both.
- What module structure and public API shape the orchestration layer takes.
- Whether new architecture rules are needed for the application package boundary.

## 8. OUT OF SCOPE

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

## 9. NON-GOALS

- Inventing a new application error taxonomy (reuse M020 domain errors).
- Implementing a dependency injection framework.
- Implementing a query language or DSL.
- Implementing caching, pagination, result transformation, or result envelopes.
- Implementing saga, event-sourcing, or saga patterns.
- Implementing authorization or authentication.
- Implementing observability or structured logging (application layer concern, not orchestration).

## 10. DEFERRED ITEMS

- All concrete application commands and handlers (later application milestones).
- Handler instantiation strategies and DI (later application milestones).
- Transaction implementation and ownership semantics (M029 design determines; later application milestones implement).
- Error taxonomy extensions (if needed; later application milestones; reuse M020 for now).
- Async orchestration (if needed; later enhancement).
- Retry and idempotency policies (later infrastructure milestones).
- APIs, HTTP transport, routing (later infrastructure milestones).
- Workers and background execution (later infrastructure milestones).
- Audit and event runtime (later observability milestones).
- Business use cases (market-data, trading, empirical campaign execution; much later).

## 11. EXPECTED FILES

**New source files (to be determined by M029 design):**
- Application orchestration module/package (location and structure determined during design).
- Error handling or translation layer (if needed; determined during design).

**New test files (to be determined by M029 design):**
- Orchestration contract tests (signature and location determined during design).
- Orchestration-layer error propagation tests (determined during design).
- Integration tests with M027/M028 (determined during design).

**New documentation:**
- `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_IMPLEMENTATION_SCOPE.md` (after design).
- `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_IMPLEMENTATION.md` (after implementation).

**No modified files:**
- M020-M028 remain frozen.
- Existing implementation and tests remain untouched.

## 12. EXPECTED TESTS

Test obligations to be determined during M029 design, including:
- Orchestration boundary conformance tests (validates frozen `CommandHandler`/`QueryHandler` compatibility).
- Error propagation semantics tests (validates design's choice of error handling strategy).
- Orchestration-layer-only behavior tests (isolated to orchestration responsibility).
- No M027/M028 modification tests (proves compatibility with frozen contracts).

## 13. VALIDATION GATES

**Expected gates for M029 implementation (to be confirmed in scope implementation document):**
- Python 3.13 compilation.
- Ruff format and linting.
- MyPy type checking (0 issues; full strict mode on application module).
- Unit and contract tests.
- Architecture checker (validates package boundary rules determined by M029 design).
- Build (sdist + wheel).

**No PostgreSQL regression tests required** (orchestration does not implement persistence).

## 14. ARCHITECTURE IMPACT

**Positive:**
- Establishes the application layer as a well-defined, distinct boundary.
- Separates domain/persistence (M020-M026) from application invocation semantics.
- Sets the pattern for all future application-layer responsibilities.

**Architecture questions M029 design must resolve:**
- Does the application package require new architecture enforcement rules?
- What imports are forbidden from the orchestration module?
- What must remain isolated to orchestration, and what may be delegated to handlers?

**No changes required to M020-M028:**
- Frozen contracts remain exactly as defined.
- Orchestration uses them; does not modify them.

## 15. RISKS

**Risks for this milestone:**

1. **Scope creep into design**: Freezing class names, method signatures, error types, or registry mechanisms.
   - **Mitigation**: This scope selection identifies design questions; implementation scope confirms design answers without this scope selection re-opening them.

2. **Transaction ownership ambiguity**: Leaving transaction semantics undefined until too late.
   - **Mitigation**: M029 design must explicitly resolve transaction ownership (M024 delegates; handlers may call it; or orchestration wraps it).

3. **Error handling contradiction**: Claiming to both introduce new error classes and reuse M020 hierarchy.
   - **Mitigation**: M029 design determines error strategy (translation layer, passthrough, wrapped exceptions, etc.); implementation follows that design decision.

4. **Handler instantiation undefined**: Leaving orchestration with no defined way to get handler instances.
   - **Mitigation**: M029 design determines instantiation strategy (or defers it to later application layer); implementation follows.

5. **Premature architecture rules**: Inventing new architecture constraints before understanding concrete use cases.
   - **Mitigation**: M029 design may identify new architecture rules; implementation proves them necessary before locking them in.

## 16. SUCCESS CRITERIA

M029 scope selection is complete and ready for independent re-review when:

- [x] Scope defines a coherent application invocation boundary between M027-M028 (frozen) and future business logic.
- [x] Scope identifies all design questions (transaction, error handling, instantiation, discovery, lifecycle) without freezing answers.
- [x] No implementation details are frozen (class names, method signatures, module structure, concrete classes).
- [x] No unsupported estimates appear (implementation size, duration, complexity).
- [x] Architecture constraints are framed as design questions, not frozen decisions.
- [x] Error handling strategy is identified as a design question, not frozen.
- [x] Handler lifecycle and instantiation are identified as design questions, not frozen.
- [x] All future milestone references (M030+, M031+, etc.) are replaced with generic language (later application milestone, future infrastructure).
- [x] Scope is narrower and more coherent than the first draft.
- [x] Command and query semantics remain distinguishable.
- [x] No M020-M028 files are touched.
- [x] Document quality is normalized (encoding, consistency, clarity).

## 17. Final Status

```text
M029 SCOPE SELECTION CORRECTED

READY FOR INDEPENDENT SCOPE RE-REVIEW
```
