# MILESTONE-031 - Concrete Application Query Vertical Slice Scope

**Status: CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW**

---

## Problem Statement

MILESTONE-030 proved the write side of the application invocation boundary: a real command, invoked through the real `CommandEntryPoint`, calling a real domain aggregate, persisted through the real frozen repository stack. The read-side counterpart of that same boundary — the `QueryHandler` Protocol (MILESTONE-028) and the `QueryEntryPoint` (MILESTONE-029) — remains frozen since its own milestone but has never been exercised by anything other than mock/fake handlers in its own contract tests. A repository-wide search confirms zero concrete query handlers exist anywhere in the codebase.

The practical consequence: a Campaign created through the MILESTONE-030 vertical slice can currently be read back only by reaching around the application boundary and calling the repository's `get()` method directly. No proof exists that the read-side application boundary works end-to-end for a real caller, the same gap MILESTONE-030 closed for the write side.

---

## Objective

Prove, with one concrete, minimal, real query, that the frozen read-side application invocation boundary composes correctly end-to-end — completing the CQRS proof MILESTONE-030 began, without introducing transport, without introducing a second aggregate, and without introducing any framework, registry, or abstraction beyond what is already frozen.

---

## Scope

**Concrete Application Query Vertical Slice: Campaign Retrieval.**

A single read-side (query) operation — retrieving a previously created `Campaign` by its identity — implemented as one concrete query and one concrete handler conforming to the frozen MILESTONE-028 `QueryHandler` Protocol, invoked through the frozen MILESTONE-029 `QueryEntryPoint`, reading through the frozen MILESTONE-023 concrete `Campaign` repository adapter.

**Why Campaign, and why retrieval-by-identity:**

- `Campaign` is the same aggregate MILESTONE-030 already exercised on the write side, and remains the only domain aggregate with zero dependency on any other domain aggregate — the narrowest available subject.
- The frozen `CampaignRepository` Protocol (MILESTONE-020) already defines a `get()` method taking exactly a `DomainIdentity`; no new repository capability is required.
- Retrieval-by-identity is the narrowest possible read operation: it requires no filtering, no pagination, no sorting, and no cross-aggregate join.

---

## In Scope

- One concrete query representing "retrieve a Campaign by its identity," carrying the minimal data the frozen repository's `get()` method already requires.
- One concrete handler conforming to the frozen `QueryHandler` Protocol that reads a `Campaign` via the frozen repository's `get()` method and returns it (or the data a caller needs from it).
- Binding this handler to a `QueryEntryPoint` and invoking it, proving the frozen read-side boundary's contract holds for a real (not mock) handler.
- Contract tests proving the concrete handler conforms to the frozen `QueryHandler` Protocol.
- Integration tests proving the golden path (reading a Campaign created via the MILESTONE-030 write-side slice) and the already-frozen not-found failure path both work end-to-end against real PostgreSQL.
- Identification (not resolution) of the design questions a concrete query handler raises that MILESTONE-030's design did not need to answer (e.g., whether the query returns the domain aggregate itself or a narrower read-shaped value, and where that decision's boundary lies).

---

## Out of Scope

- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any Campaign query other than retrieval-by-identity (no listing, filtering, searching, or pagination).
- Any additional Campaign command (creation was already delivered by MILESTONE-030; no update, activation, suspension, or cancellation command).
- Any composition-root abstraction, handler registry, service locator, or dependency-injection framework — the handler is bound to its `QueryEntryPoint` by direct construction, exactly as MILESTONE-030 already established for the write side.
- Any transport layer: no HTTP endpoint, no CLI command, no worker, no queue consumer.
- Any retry, idempotency, or optimistic-concurrency-conflict handling — this remains blocked on a `save()`-based command that does not yet exist, unchanged from MILESTONE-030's own deferral.
- Any new architecture-checker package or dependency rule beyond what MILESTONE-030 already established, unless design discovers a genuine gap.
- Any market-data, vendor, trading-strategy, order-execution, or brokerage-integration behavior.
- Any change to MILESTONE-020 through MILESTONE-030 frozen contracts, source files, or governance documents.
- Any MILESTONE-032 work of any kind.

---

## Dependencies

**Depends on (frozen, read-only):**

- MILESTONE-020 `CampaignRepository` Protocol and `Campaign` aggregate.
- MILESTONE-023 concrete PostgreSQL Campaign repository adapter.
- MILESTONE-025 repository runtime composition.
- MILESTONE-028 `QueryHandler` Protocol.
- MILESTONE-029 `QueryEntryPoint`.
- MILESTONE-030's already-delivered write-side vertical slice, whose own tests already demonstrate the exact PostgreSQL fixture pattern this milestone's integration tests will reuse.

**Does not depend on:** any `Run`/`EvidencePackage`/`Review` material, any transport or entrypoint code, any composition-root abstraction.

---

## Risks

- **Return-shape ambiguity:** whether the query handler returns the domain aggregate itself or a narrower, read-oriented value is a genuine open question this scope does not resolve; an uninformed default risks either leaking internal aggregate mutability to callers or under-specifying what "the read side" actually promises. Mitigation: this scope explicitly identifies the question for the design phase rather than silently choosing an answer.
- **Symmetry pressure:** because this milestone deliberately mirrors MILESTONE-030's shape, there is a risk of copying its dependency-injection and error-propagation choices without independently re-justifying them for the read side, where the failure modes differ (not-found is a read-side-specific outcome that MILESTONE-030's create-only slice never had to consider). Mitigation: design must re-derive these decisions for the query side, not merely restate MILESTONE-030's write-side reasoning.
- **Scope-creep pressure toward listing/filtering:** a minimal retrieval-by-identity query invites "just add a list query too" expansion. Mitigation: explicitly excluded above; any such addition requires its own scope-change authorization.

---

## Deferred Work

- Any query for `Run`, `EvidencePackage`, or `Review`.
- Any Campaign query beyond retrieval-by-identity (listing, filtering, searching, pagination).
- Any additional Campaign command beyond creation (already delivered) and this milestone's query (activation, suspension, cancellation, scope revision, etc.).
- Retry-on-optimistic-concurrency-conflict policy (still blocked on a `save()`-based command that does not yet exist).
- Any composition-root abstraction beyond direct binding.
- Any transport/entrypoint adapter exposing this or any other command/query.
- MILESTONE-032 and beyond.

---

## Frozen Contracts

The following must remain exactly as frozen, unmodified, throughout this milestone's design and implementation:

- `Campaign` aggregate and its value objects (MILESTONE-020).
- `CampaignRepository` Protocol, including its existing `get()` method signature (MILESTONE-020).
- The concrete PostgreSQL Campaign repository adapter (MILESTONE-023).
- `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol (MILESTONE-028).
- `QueryEntryPoint[QueryT, QueryResultT]` (MILESTONE-029).
- Everything MILESTONE-030 delivered: its concrete command, its concrete handler, and the architecture-checker rules it established.

---

## Success Criteria

MILESTONE-031 scope selection is complete and ready for independent review when:

- Exactly one read-side capability is proposed (retrieval-by-identity for one aggregate), matching the same narrowness discipline MILESTONE-030 established for the write side.
- No class name, method signature, module path, package structure, dependency-injection mechanism, registry, transaction behavior, error hierarchy, retry policy, or other design/implementation decision is fixed by this document.
- Every excluded capability is explicit, and every excluded capability's reason traces to either a genuine unmet prerequisite (composition-root need not yet evidenced, `save()`-based command not yet built) or a deliberate narrowness choice consistent with MILESTONE-030's own precedent.
- The scope is independently reviewable without requiring the reviewer to first resolve any open design question themselves.
