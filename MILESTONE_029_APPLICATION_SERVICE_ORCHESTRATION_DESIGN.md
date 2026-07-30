# MILESTONE-029 - Application Service Orchestration Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-029-DESIGN |
| Title | Application Service Orchestration Design |
| Status | **APPROVED_AND_FROZEN** |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen scope authority | Commit `22cec98d4bd724e00754551034b896236989acec` (MILESTONE-029 scope freeze) |
| Scope status | APPROVED_AND_FROZEN |
| Design correction history | Correction Pass I (options catalogue → decisions), Correction Pass II (M024/M025 exact contracts, transaction/error/handler decisions), Correction Pass III (meaningful boundary, error policy, runtime validation, package rules, sync/async wording) |
| Independent final review decision | M029 DESIGN APPROVED FOR OWNER FREEZE |
| Owner freeze date | 2026-07-30 |
| Design freeze commit | See `MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN_FREEZE.md` for the authoritative commit hash record |
| Implementation status | **NOT_STARTED** — this document freezes architecture only; no implementation is authorized by this freeze |

---

## 2. Frozen Foundation

**M027 CommandHandler:** `def handle(self, command: C) -> R`
**M028 QueryHandler:** `def handle(self, query: Q) -> R`
**M024 run_composed:** `def run_composed(self, operations: Sequence[Callable[[], object]]) -> tuple[object, ...]`
**M025 Runtime:** `PostgresRepositoryRuntime` with four repositories and `run_composed()` delegation

---

## 3. M029 Architectural Role (Not Just Forwarding)

**M029 is the application invocation gateway.**

M029 owns a minimal but real application-boundary responsibility:

1. **Stable invocation policy:** All commands enter through one command boundary, all queries through one query boundary
2. **Exactly-once handler invocation:** Each accepted request invokes its bound handler exactly once
3. **Command/query distinction:** Maintains CQRS semantics; transport cannot treat them identically
4. **Input/output identity:** Command and result reach handler unchanged; handler exceptions propagate unchanged
5. **Boundary validation:** Rejects structurally invalid invocation shapes using ordinary Python semantics (not custom errors)
6. **Transport isolation:** Transport adapters call M029 entry points, not handlers or persistence directly
7. **Architecture enforcement:** Package dependencies make this boundary testable and architecture-checkable
8. **Future policy seam:** Application-level policy can evolve here (retry, tracing, etc.) without changing transport contracts
9. **Failure transparency:** Handler, domain, and persistence failures propagate unchanged

**Why this is not redundant:**

- **Without M029:** Each transport adapter would directly instantiate handlers or use ad hoc discovery; command/query semantics would blur
- **With M029:** All transport adapters call stable entry points; command/query semantics are centrally preserved; package rules prevent direct transport→domain dependencies
- **Testability:** M029 boundary is testable in isolation; architecture rules are enforceable
- **Reusability:** M030+ handlers all use the same M029 boundary; no transport-specific adapters per handler needed
- **Consistency:** All callers experience one stable invocation policy

---

## 4. Composition and Handler Binding

**Composition root constructs handlers:**

- Creates concrete handler instances
- Supplies handler dependencies (repositories, runtime, services)
- Binds each handler to one use-case responsibility

**Transport adapter invokes M029 entry points:**

- Translates transport input into a command or query instance
- Calls the pre-bound M029 entry point (no handler discovery)
- Does NOT construct handlers per request
- Does NOT import persistence runtime directly
- Does NOT invoke repositories directly

**M029 application boundary:**

- Receives a command/query and a pre-bound handler dependency
- Invokes the handler exactly once: `handler.handle(input)`
- Returns the result or propagates the handler exception

**Handler executes use-case logic:**

- Accesses repository runtime (already bound by composition)
- Performs persistence operations
- Calls `run_composed()` if atomicity is needed
- Returns result or raises exception

**Composition is centralized:**

Transport adapters do NOT:
- ❌ Perform handler resolution per request
- ❌ Use service locators, registries, or factories to select handlers
- ❌ Construct handlers ad hoc

Transport adapters DO:
- ✓ Receive pre-bound M029 entry points from composition
- ✓ Translate input and invoke entry points
- ✓ Handle transport-level concerns (serialization, routing, etc.)

---

## 5. Public Invocation Boundaries (Concrete Shape)

**Two distinct entry points, bound at composition time:**

**Command entry point:**
- Receives: one command instance
- Bound to: one CommandHandler[C, R]
- Invokes: `handler.handle(command)`
- Returns: result R

**Query entry point:**
- Receives: one query instance
- Bound to: one QueryHandler[Q, R]
- Invokes: `handler.handle(query)`
- Returns: result R

**Invocation pattern:**

```
Composition time:
  command_entry = bind(handler=CreateCampaignHandler(...))
  query_entry = bind(handler=GetCampaignHandler(...))

Invocation time:
  campaign_id = command_entry(CreateCampaignCommand(...))
  campaign = query_entry(GetCampaignQuery(...))
```

**No handler is supplied by transport at invocation time.** Handler is bound once during composition and reused.

**Concrete implementation** (function vs. object vs. class) is not frozen by this design. The binding semantics are:
- Handler dependency is captured at composition
- Transport invocation provides only the input
- M029 calls the bound handler exactly once

---

## 6. Error Policy

**No custom error hierarchy in M029.**

**Transparent propagation:**

- Handler exceptions propagate unchanged to caller
- Domain errors (from M020) propagate unchanged
- Persistence errors (from M024/M025) propagate unchanged
- Transaction errors propagate unchanged

**Structurally invalid invocation:**

- Missing required argument → Python `TypeError` (normal language behavior)
- None passed where handler expected → Python `TypeError` or `AttributeError` (normal language behavior)
- Non-callable target → Python `TypeError` (normal language behavior)

**M029 does NOT:**
- ❌ Create `ApplicationBoundaryError` or any custom exception
- ❌ Wrap handler exceptions
- ❌ Translate exception types
- ❌ Define error categories

**M029 enforces conformance through:**
- ✓ Static type checking (mypy)
- ✓ Tests (bound handlers verified to conform)
- ✓ Python's natural runtime behavior (TypeErrors on misuse)

---

## 7. Runtime Protocol Validation

**No runtime Protocol introspection in M029.**

**M027/M028 conformance is enforced by:**

- Static type checking (mypy verifies `handler: CommandHandler[C, R]`)
- Implementation structure (handlers implement `def handle()` method)
- Tests (mock handlers verify Protocol contract)

**M029 does NOT:**
- ❌ Use `@runtime_checkable`
- ❌ Inspect handler members at runtime
- ❌ Verify Protocol conformance with `isinstance()` checks
- ❌ Translate non-conformance to custom errors

**If a malformed object is passed as a handler:**
- Invocation fails with natural Python error (`AttributeError`, `TypeError`)
- Error is NOT wrapped or translated
- Failure is caught by tests, not by M029 runtime logic

---

## 8. Transaction Architecture

**Handlers own transaction execution.**

**When atomicity is needed:**

Handler calls `run_composed()` on the repository runtime:

```
def handle(self, command):
    def atomic_operations():
        # Capture repository runtime; perform operations
        result1 = self.runtime.repos.create(...)
        result2 = self.runtime.repos.update(...)
        return result1

    return self.runtime.run_composed([atomic_operations])[0]
```

**M029 does NOT:**
- ❌ Open transactions
- ❌ Wrap handler invocation in `run_composed()`
- ❌ Make transaction decisions based on command type
- ❌ Create nested transactions

**Why handlers own transactions:**

- Handlers know which operations are atomic
- M029 is generic; it cannot infer required atomicity
- Central wrapping would impose false uniformity
- Handler-owned transactions respect use-case semantics

**Consequence:**

Transaction conformance is enforced through:
- Handler design (handlers call `run_composed()` correctly)
- Tests (verify atomic operations work)
- Frozen M024 runtime (enforces no-nesting rule)

---

## 9. Sync/Async Architecture

**M029 is synchronous.**

**Why:**
- M027 CommandHandler.handle() is synchronous
- M028 QueryHandler.handle() is synchronous
- M024 run_composed() is synchronous
- M025 repository runtime is synchronous

**No async in M029:**
- M029 does not use `async def`
- M029 does not use `await`
- M029 does not schedule tasks
- M029 does not manage event loops

**Async execution is NOT M029's concern:**
- Transport adapters may use their own concurrency (thread pools, event loops)
- Wrapping synchronous M029 with async does not change its blocking semantics
- A future asynchronous application boundary would require a separate architectural design
- No promise of async compatibility

---

## 10. Package Dependency Rules (Implementable)

**Repository package structure:**
- `src/empirical_platform/application/` (M029, new)
- `src/empirical_platform/shared/contracts/` (M027-M028)
- `src/empirical_platform/shared/persistence/` (M024-M025)
- `src/empirical_platform/entrypoints/` (transport: HTTP, CLI, workers)
- `src/empirical_platform/campaign/`, `run/`, `evidence/`, `review/` (domain)
- `src/empirical_platform/audit/`, `archive/`, `acquisition/`, etc. (infrastructure)

**Package rule 1: Application invocation boundary**

`empirical_platform.application` may import:
- ✓ `empirical_platform.shared.contracts` (frozen M027-M028 Protocols)
- ✓ Standard library (typing, collections, etc.)
- ✓ Application-local modules (within application package)

`empirical_platform.application` must NOT import:
- ❌ `empirical_platform.entrypoints` (transport)
- ❌ `empirical_platform.shared.persistence` (database)
- ❌ `empirical_platform.campaign`, `run`, `evidence`, `review` (domain)
- ❌ `empirical_platform.audit`, `archive`, `acquisition` (infrastructure)

**Package rule 2: Transport adapters**

`empirical_platform.entrypoints` may import:
- ✓ `empirical_platform.application` (invokes entry points)
- ✓ Transport-specific frameworks (FastAPI, Click, Celery, etc.)
- ✓ Concrete handler implementations (bound during composition)
- ✓ Application-specific DTOs/mappers

`empirical_platform.entrypoints` must NOT directly import:
- ❌ `empirical_platform.shared.persistence` (use repository runtime instead)
- ❌ Bypass M029 application boundary to call handlers directly

**Package rule 3: Domain packages**

`empirical_platform.campaign`, `run`, `evidence`, `review` must NOT import:
- ❌ `empirical_platform.entrypoints`
- ❌ `empirical_platform.application` (invocation entry points)

(Handlers within domain packages may import application boundary Protocols, but domain packages themselves do not.)

**Package rule 4: Persistence**

`empirical_platform.shared.persistence` must NOT import:
- ❌ `empirical_platform.entrypoints`
- ❌ `empirical_platform.application`

**Package rule 5: Infrastructure/auxiliary**

`empirical_platform.audit`, `archive`, `acquisition`, etc. must NOT import:
- ❌ `empirical_platform.entrypoints` (transport-specific)

**Package rule 6: Composition root**

Composition modules may import:
- ✓ `empirical_platform.application` (entry points)
- ✓ Concrete handler implementations
- ✓ Persistence/repository implementations
- ✓ Transport setup

**Package rule 7: Tests**

Tests may import:
- ✓ `empirical_platform.application` (for unit tests)
- ✓ Test support, fixtures, mocks
- ✓ Frozen contracts

**Architecture enforcement:**

Implementation must extend `tools/check_architecture.py` to verify:
1. `empirical_platform.application` has no imports from `entrypoints`, `persistence`, or domain packages
2. `entrypoints` does not import `shared.persistence` directly (uses handler-bound runtime)
3. Domain packages do not import `entrypoints` or application entry points
4. No circular dependencies between application, domain, persistence

---

## 11. Design Invariants

1. **Exactly-once invocation:** Every accepted command invocation calls its bound handler exactly once
2. **Exactly-once query invocation:** Every accepted query invocation calls its bound handler exactly once
3. **Handler binding at composition:** Transport does not choose or discover handlers at invocation time
4. **No handler discovery in M029:** Handler dependencies are bound before M029 invocation
5. **Result passthrough:** Handler result returns to caller unchanged
6. **Error passthrough:** Handler exception propagates to caller unchanged (not wrapped, not translated)
7. **No M029 exception hierarchy:** M029 creates no custom exception classes or error categories
8. **No runtime Protocol introspection:** M029 does not inspect handler at runtime for conformance
9. **Handler owns transactions:** M029 does not open or wrap transactions; handlers call `run_composed()` if needed
10. **No nested transactions:** M029 respects M024's no-nesting rule; handlers must also respect it
11. **No transport coupling:** M029 imports nothing from entrypoints or transport frameworks
12. **No persistence coupling:** M029 imports nothing from shared.persistence
13. **CQRS distinction maintained:** Command and query invocation remain architecturally separate
14. **Synchronous execution:** M029 invocation is blocking; no async/await in M029
15. **No business logic:** M029 performs no domain validation, calculations, or use-case behavior
16. **One responsibility per entry point:** Each command or query entry point is bound to one handler responsibility
17. **Stable boundary:** Transport calls one consistent application boundary; changing handlers does not affect transport

---

## 12. Testing Strategy

**Unit tests verify M029 boundary behavior:**

- Bound handler is invoked exactly once per request
- Command object reaches handler unchanged
- Query object reaches handler unchanged
- Handler result returns unchanged
- Handler exception instance propagates unchanged (identity preserved)
- No custom M029 error translation occurs
- Malformed call targets fail with Python errors (not wrapped)

**Contract tests verify Protocol compatibility:**

- Mock CommandHandler conforming to M027 works with command entry point
- Mock QueryHandler conforming to M028 works with query entry point
- Handler must have `handle()` method with correct signature

**Integration tests verify end-to-end flows:**

- Command entry point → handler → repository operations → result
- Query entry point → handler → repository read → result
- Handler exception propagates through M029 to caller

**Architecture tests verify package rules:**

- `empirical_platform.application` has no forbidden imports
- `empirical_platform.entrypoints` does not import `shared.persistence` directly
- Domain packages do not import entrypoints or application entry points
- No circular dependencies

**Synchronous execution tests:**

- M029 blocks on handler invocation (no thread spawning)
- Transport timeout is external to M029

**No arbitrary coverage requirements:** Use project-wide gates, not M029-specific percentages

---

## 13. Acceptance Criteria

Implementation readiness:

- ✓ M029 provides meaningful application invocation boundary (not just forwarding)
- ✓ Transport calls M029 entry points rather than handlers directly
- ✓ Composition owns handler construction and binding
- ✓ M029 invokes exactly one bound handler per request
- ✓ No runtime handler discovery or registry in M029
- ✓ No custom M029 exception category
- ✓ No runtime Protocol validation (enforced by static typing and tests)
- ✓ Package dependency rules are explicit (real package names, not milestone numbers)
- ✓ Architecture rules are enforceable (architecture checker extended)
- ✓ Sync-only semantics explicit (no async, no future async promise)
- ✓ Transaction ownership clear (handlers own via `run_composed()`)
- ✓ Implementation will not need additional architectural choices

---

## 14. Rejected Alternatives

| Alternative | Why Rejected | Consequence |
| --- | --- | --- |
| M029 provides handler discovery | Composition is cleaner; transport becomes ad hoc if each request chooses handlers | Composition is centralized; transport receives pre-bound entry points |
| M029 wraps handlers in transactions | Would require handlers to receive parameters; explicit is better | Handlers call `run_composed()` themselves when atomicity needed |
| M029 wraps handler exceptions | Domain errors are well-formed; no value added by wrapping | Transparent propagation; errors reach caller unchanged |
| Runtime Protocol validation in M029 | Static typing and tests already enforce conformance | Malformed handlers fail at invocation time with Python errors |
| Async support in M029 | Frozen Protocols are synchronous; would require separate architecture | M029 is sync-only; async support deferred to future layer |

---

## 15. Scope Compliance

- ✓ No source code changes (design document only)
- ✓ No test files modified
- ✓ No fixture changes
- ✓ No configuration changes
- ✓ No tools/check_architecture.py modifications (deferred to implementation phase)
- ✓ No M020-M028 frozen records modified
- ✓ No M029 scope modifications (scope remains frozen at commit `22cec98`)
- ✓ This freeze commits only the design document; no implementation is included

---

## 16. Final Status

```
═══════════════════════════════════════════════════════════════════════════════

                    M029 DESIGN APPROVED AND FROZEN

═══════════════════════════════════════════════════════════════════════════════

Independent Review History:
  Pass I:  Options catalogue → architectural decisions required
  Pass II: M024/M025 exact contracts restated; transaction/error/handler decisions made
  Pass III: [1] Architectural emptiness → CORRECTED: Meaningful boundary defined
            [2] ApplicationBoundaryError → CORRECTED: Removed entirely
            [3] Runtime Protocol validation → CORRECTED: No runtime validation
            [4] Architecture rules not implementable → CORRECTED: Real package rules defined
            [5] Async wording inaccurate → CORRECTED: Sync-only, no async promise

Final Independent Review Decision: M029 DESIGN APPROVED FOR OWNER FREEZE

Architectural Shape:
  ✓ Two entry points (command, query), bound at composition
  ✓ Transport calls entry points, not handlers directly
  ✓ Composition centralizes handler construction
  ✓ M029 invokes exactly one bound handler per request
  ✓ No discovery or construction in M029
  ✓ No custom exceptions
  ✓ Errors propagate unchanged
  ✓ Synchronous execution
  ✓ Handlers own transactions via run_composed()
  ✓ Package rules explicit (real namespace paths)
  ✓ Boundary prevents direct transport→persistence imports

Design Completeness:
  ✓ Real application-boundary responsibility (not just forwarding)
  ✓ Composition and handler-binding model (clear)
  ✓ Error policy (transparent, no custom exceptions)
  ✓ Runtime validation policy (none; static typing)
  ✓ Transaction architecture (handlers own)
  ✓ Sync/async posture (sync only, no promise)
  ✓ Package dependency rules (implementable)
  ✓ Public boundary shape (pre-bound entry points)
  ✓ Invariants (15 testable/checkable)
  ✓ Testing strategy (boundary, contract, integration, architecture)
  ✓ Acceptance criteria (implementation readiness)

Baseline Repository State (at freeze):
  HEAD before freeze commit:     8fff723a26b1bf283e60f96bf03be39314be1118
  Scope freeze commit:           22cec98d4bd724e00754551034b896236989acec
  Design freeze commit:          Recorded in MILESTONE_029_APPLICATION_SERVICE_ORCHESTRATION_DESIGN_FREEZE.md

Governance State:
  M029 Scope Status:             APPROVED_AND_FROZEN
  M029 Design Status:            APPROVED_AND_FROZEN (this document)
  M029 Implementation Status:    NOT_STARTED

═══════════════════════════════════════════════════════════════════════════════

M029 DESIGN APPROVED_AND_FROZEN

M029 IMPLEMENTATION NOT_STARTED

NEXT PERMITTED ACTION: MILESTONE-029 IMPLEMENTATION

═══════════════════════════════════════════════════════════════════════════════
```

---

**M029 DESIGN APPROVED_AND_FROZEN**

**M029 IMPLEMENTATION NOT_STARTED**

**NEXT PERMITTED ACTION: MILESTONE-029 IMPLEMENTATION**
