# MILESTONE-031 - Concrete Application Query Vertical Slice Scope Freeze

## 1. Document Status

**Status: APPROVED_AND_FROZEN**

This document records the owner's formal freeze of the MILESTONE-031 scope following independent hostile scope review. It authorizes MILESTONE-031 design to begin. It does not authorize MILESTONE-031 implementation.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at freeze | `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848` |
| Milestone | MILESTONE-031 |

---

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 | APPROVED_AND_FROZEN (scope, design, implementation — implementation freeze commit `64682d1790ed3efacbdbdb6d99b3f3b4e7bbee90`) |

All ten prior milestones remain untouched by this scope-freeze mission.

---

## 4. M031 Scope-Candidate Commit

**Commit:** `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848` (`docs: define M031 scope candidate`)

**Scope document:** `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_SCOPE.md`

**Verified unchanged since review:** the scope document's most recent modifying commit is `68bd50d` — its own creation commit, which is also the HEAD this freeze mission verified at Phase 0. No edit occurred between independent review and this freeze.

---

## 5. Independent Scope-Review Decision

**Decision: M031 SCOPE APPROVED WITH NON-BLOCKING OBSERVATIONS**

The independent hostile scope review found the proposed scope represents exactly one coherent read-side capability, correctly follows the frozen M030 write-side slice, preserves every frozen predecessor contract, and identified two non-blocking governance observations (Section 6) — neither concerning the substance of the scope itself.

---

## 6. Non-Blocking Observations (Resolved by This Freeze)

**M031-SCOPE-REVIEW-0001:** `PROJECT_CHECKPOINT.md` recorded `M031_SCOPE_COMMIT=PENDING`. Resolved: the actual scope-candidate commit hash `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848` is recorded in this freeze's checkpoint update (Section 9 of this document; Phase 3 of the freeze mission).

**M031-SCOPE-REVIEW-0002:** An older current-state narrative sentence in `PROJECT_CHECKPOINT.md` still described M031 scope selection as "not yet started." Resolved: the stale sentence is corrected to reflect the current state (scope approved and frozen) in the same checkpoint update, while every genuinely historical statement about M020-M030 is preserved unaltered.

---

## 7. Owner Approval

I, the owner, declare the MILESTONE-031 scope, as recorded in `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_SCOPE.md` at commit `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848`, **APPROVED AND FROZEN** effective immediately upon this record.

**M031 SCOPE APPROVED_AND_FROZEN**

No further change to the frozen scope is permitted without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit.

---

## 8. Frozen Mission Statement

Prove, with one concrete, minimal, real query, that the frozen read-side application invocation boundary composes correctly end-to-end — completing the CQRS proof MILESTONE-030 began, without introducing transport, without introducing a second aggregate, and without introducing any framework, registry, or abstraction beyond what is already frozen.

---

## 9. Frozen In-Scope Capability

- Exactly one Campaign retrieval-by-identity query capability.
- In a future implementation: one concrete query and one concrete query handler — no additional query, no additional command.
- Use of the frozen `QueryHandler` Protocol (MILESTONE-028).
- Use of the frozen `QueryEntryPoint` (MILESTONE-029).
- Use of the existing, already-frozen `CampaignRepository.get()` method (MILESTONE-020) — no new repository capability.
- Contract tests proving Protocol conformance.
- Integration tests proving the golden path (reading a Campaign created via the MILESTONE-030 write-side slice) and the already-frozen not-found failure path against real PostgreSQL.
- Identification (not resolution) of the design questions a concrete query handler raises.

---

## 10. Frozen Out-of-Scope Capabilities

- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any Campaign query other than retrieval-by-identity: no listing, filtering, searching, pagination, or projection framework.
- Any additional Campaign command.
- Any composition-root abstraction, handler registry, dispatcher, service locator, caching layer, read-model framework, or dependency-injection framework.
- Any transport layer: no HTTP endpoint, no CLI command, no worker, no queue consumer.
- Any cross-aggregate access.
- Any retry, idempotency, or optimistic-concurrency-conflict handling.
- Any new architecture-checker package or dependency rule beyond what MILESTONE-030 already established, unless design discovers and justifies a genuine gap.
- Any market-data, vendor, trading-strategy, order-execution, or brokerage-integration behavior.
- Any change to MILESTONE-020 through MILESTONE-030 frozen contracts, source files, or governance documents.
- Any MILESTONE-032 work of any kind.

These boundaries are exactly as written in the reviewed scope document. This freeze record does not alter, narrow, or expand them.

---

## 11. Frozen Contract Preservation

The following must remain exactly as frozen, unmodified, throughout MILESTONE-031's design and implementation:

- `Campaign` aggregate and its value objects (M020).
- `CampaignRepository` Protocol, including its existing `get()` method signature (M020).
- The concrete PostgreSQL Campaign repository adapter (M023).
- `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol (M028).
- `QueryEntryPoint[QueryT, QueryResultT]` (M029).
- Everything M030 delivered: its concrete command, its concrete handler, and the architecture-checker rules it established.

---

## 12. Open Design Questions (Explicitly Not Resolved by This Freeze)

- Whether the query handler returns the domain aggregate itself or a narrower, read-oriented value.
- The exact query type's name and shape.
- The exact handler type's name and shape.
- Package/module placement for the concrete query and handler.
- The dependency-acquisition mechanism (expected to follow MILESTONE-030's constructor-injection precedent, but not frozen here).
- Not-found propagation policy (expected to follow MILESTONE-030's transparent-propagation precedent, but not frozen here — the read side's failure modes differ from the create-only write side and must be independently re-derived, not merely assumed symmetric).
- Whether any architecture-checker change is needed (expected to be none, since the query lives alongside the already-authorized `usecases` package, but this is a design-phase determination, not a scope-freeze decision).

---

## 13. Deferred Work

- Any query for `Run`, `EvidencePackage`, or `Review`.
- Any Campaign query beyond retrieval-by-identity.
- Any additional Campaign command beyond creation (M030) and this milestone's query.
- Retry-on-optimistic-concurrency-conflict policy (blocked on a `save()`-based command that does not yet exist).
- Any composition-root abstraction beyond direct binding.
- Any transport/entrypoint adapter.
- MILESTONE-032 and beyond.

---

## 14. Design/Implementation Prohibition

This freeze record does NOT authorize:

- Any MILESTONE-031 design.
- Any MILESTONE-031 implementation.
- Any modification to M020-M030 frozen material.
- Any MILESTONE-032 work.

Design must operate strictly within the frozen boundaries recorded in Sections 9-11, resolving only the open design questions in Section 12, without reopening any decision M020-M030 already froze.

---

## 15. Final Scope Status

```
M031_SCOPE_STATUS=APPROVED_AND_FROZEN
M031_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M031_DESIGN_STATUS=NOT_STARTED
M031_IMPLEMENTATION_STATUS=NOT_STARTED
M031_STATUS=SCOPE_APPROVED_AND_FROZEN
```

---

## 16. Next Permitted Action

**MILESTONE-031 DESIGN MISSION.**

---

## 17. Final Status

```
═══════════════════════════════════════════════════════════════════════════════

              MILESTONE-031 SCOPE FREEZE COMPLETE

═══════════════════════════════════════════════════════════════════════════════

M031 CONCRETE APPLICATION QUERY VERTICAL SLICE (CAMPAIGN RETRIEVAL)

Independent Review Decision:    M031 SCOPE APPROVED WITH NON-BLOCKING OBSERVATIONS
Owner Decision:                 APPROVED_AND_FROZEN
Scope Candidate Commit:         68bd50d1d2e2d38abb3e3e389e4a8dde6d996848
Scope Freeze Commit:            (recorded in a following governance commit)

M020-M030:                      UNCHANGED, ALL REMAIN APPROVED_AND_FROZEN
M031 Design:                    NOT_STARTED (now authorized)
M031 Implementation:            NOT_STARTED
M032:                           NOT_STARTED

NEXT PERMITTED ACTION: MILESTONE-031 DESIGN MISSION

═══════════════════════════════════════════════════════════════════════════════
```
