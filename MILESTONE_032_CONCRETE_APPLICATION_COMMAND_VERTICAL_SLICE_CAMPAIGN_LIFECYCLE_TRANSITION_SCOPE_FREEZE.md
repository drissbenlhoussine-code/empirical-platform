# MILESTONE-032 - Concrete Application Command Vertical Slice (Campaign Lifecycle Transition) Scope Freeze

## 1. Document Status

**Status: APPROVED_AND_FROZEN**

This document records the owner's formal freeze of the MILESTONE-032 scope following independent hostile scope review. It authorizes MILESTONE-032 design to begin. It does not authorize MILESTONE-032 implementation.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at freeze | `7df0e5bab6dde382aa896ec6b416c305affeccba` |
| Milestone | MILESTONE-032 |

---

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN (scope, design, implementation) |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN (scope, design, implementation — implementation freeze commit `f144c963f6bcf90a8ada5cf14853fce5e73d48d8`) |

All prior milestones remain untouched by this scope-freeze mission.

---

## 4. M032 Scope-Candidate Commit

**Commit:** `5ea62d02d65945f0976e42b8c011217d895723e4` (`docs: define M032 scope candidate`)

**Scope document:** `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_SCOPE.md`

**Verified unchanged (substantively) since review:** `git diff --name-status 5ea62d0 HEAD -- MILESTONE_032_..._SCOPE.md` was empty immediately prior to this freeze's Phase 2 corrections, confirming the scope document independent review evaluated was untouched between the scope-candidate commit and this freeze mission's start. This freeze applies only the three approved non-blocking documentation corrections (Section 8) — no substantive scope decision was reopened.

---

## 5. Independent Scope-Review Method

The independent hostile scope review did not trust commit messages, milestone summaries, or `PROJECT_CHECKPOINT.md` in isolation. It derived every conclusion from direct inspection of the repository:

- Ran `grep -rn "\.save("` across the entire `src/empirical_platform/` tree — confirmed zero call sites anywhere outside the 8 method definitions themselves (4 repository Protocols + 4 concrete PostgreSQL adapters).
- Ran `grep -rln "OptimisticConcurrencyConflict"` across `src/` and `tests/` — confirmed matches only in the frozen repository/contract layer and M020/M023-era tests, zero occurrences in `usecases/`, `application/`, `entrypoints/`, or any M030/M031 test.
- Ran a repo-wide search for every Campaign lifecycle-mutation method call (`.activate(`, `.suspend(`, `.resume(`, `.complete(`, `.cancel(`, `.prepare_for_authorization(`, `.record_authorization(`, `.revise_scope_statement(`) across `usecases/`, `application/`, `entrypoints/` — confirmed zero matches.
- Independently re-read `audit/`, `governance/`, `registry/`, `entrypoints/` source directly, confirming stub-package and no-transport-framework claims.
- Independently verified every claimed citation of M030/M031 frozen scope text against the actual frozen documents — this is what surfaced the three findings recorded in Section 7.

---

## 6. Verified Application-Layer Gap

`CampaignRepository.save()` — and every other aggregate's `.save()` method — has been frozen since M020 and implemented since M023, together with the `OptimisticConcurrencyConflict` contract it guards. Independently confirmed: neither has ever been exercised by any application-layer code anywhere in this repository. `CreateCampaignHandler` (M030) calls only `add()`; `GetCampaignHandler` (M031) calls only `get()`. No command anywhere calls `save()`; no application-layer code anywhere references `OptimisticConcurrencyConflict`. This is the correct next architectural gap, independently reproven from primary source, not merely asserted by the scope document's own citations.

---

## 7. Independent Review Decision

**Decision: APPROVED FOR OWNER SCOPE FREEZE**

The independent hostile review verified repository truth, the frozen predecessor chain, the architectural inventory, the claimed gap (proven independently, not assumed), candidate comparison and sequencing, scope purity, the absence of hidden design/implementation, and frozen-contract preservation. It found the selected scope correct and found no candidate that should logically precede it. Three non-blocking documentation findings were raised (Section 8) — none affecting the substance of the selection, all independently reproven true from primary source regardless of the citation defects.

---

## 8. Review Findings and Documentation Corrections (Resolved by This Freeze)

**M032-SCOPE-REVIEW-0001:** The scope document and `PROJECT_CHECKPOINT.md` presented a fabricated verbatim quotation attributed to "M030's frozen scope" ("blocked on a `save()`-based command that does not yet exist") that does not appear anywhere in the actual M030 scope document. Resolved: the scope document's Section 4 (inventory table) and Section 5 (Verified Gap) now cite M030's actual verbatim text — "Retry-on-`OptimisticConcurrencyConflict` policy (requires a "save" operation on an existing aggregate, which this milestone does not include)" (Deferred Work section) and "Any retry, idempotency, or optimistic-concurrency-conflict handling (creation via `add()` has no prior version to conflict with)" (Out of Scope section) — both confirmed by direct `grep` against the real file. The underlying substantive conclusion (a `save()`-based command did not yet exist, and M030 explicitly deferred retry/concurrency handling pending one) is unchanged and remains independently verified true (Section 6).

**M032-SCOPE-REVIEW-0002:** The scope document attributed the phrase "genuine repeated-handler need" to both M030's and M031's scope documents as a verbatim quotation; that exact phrase appears in neither (it originates in M031's *design* document, not either scope document). Resolved: the scope document's Candidate C rejection (Section 6) and Section 8 (Rejected Candidates) now cite M030's actual verbatim text — "Any composition-root abstraction beyond direct binding, if repeated concrete handlers later reveal a genuine need for one" — and M031's actual verbatim text — "a genuine unmet prerequisite (composition-root need not yet evidenced, `save()`-based command not yet built)." The underlying composition-root-deferral decision is unchanged; both real predecessor scope documents do defer it, confirmed by direct `grep` against both files.

**M032-SCOPE-REVIEW-0003:** The scope document used both "8 methods" and "7 lifecycle-transition methods" for `Campaign` without reconciling the two counts. Resolved: Section 4 (inventory table) now explicitly states `Campaign` has "8 public mutation methods: 7 lifecycle-state-transition methods... plus `revise_scope_statement`, which mutates the scope statement without changing lifecycle state." Section 18 (Open Design Questions) updated correspondingly to offer both the 7 state-transition methods and `revise_scope_statement` as candidate targets without implying they are the same category. No mutation capability was selected by this clarification — the choice remains an open design question.

None of these three findings required scope reselection. All are documentation-accuracy corrections; the selected scope, its verified gap, its candidate comparison, and its rejection reasoning are unchanged in substance.

---

## 9. Owner Approval

I, the owner, declare the MILESTONE-032 scope, as recorded in `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_SCOPE.md` at commit `5ea62d02d65945f0976e42b8c011217d895723e4` (with the three non-blocking documentation corrections in Section 8 applied by this same freeze), **APPROVED AND FROZEN** effective immediately upon this record.

**M032 SCOPE APPROVED_AND_FROZEN**

No further change to the frozen scope is permitted without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit.

---

## 10. Official Milestone Name

**MILESTONE-032 — Concrete Application Command Vertical Slice (Campaign Lifecycle Transition).**

---

## 11. Frozen Mission Statement

Prove, with one concrete, minimal, real command, that the frozen `save()`-based update path and its optimistic-concurrency-conflict contract compose correctly end-to-end through the application invocation boundary — completing the create/read/update proof M030 and M031 began, without introducing a retry policy, without introducing transport, without introducing a second aggregate, and without introducing any framework, registry, or abstraction beyond what is already frozen.

---

## 12. Frozen In-Scope Capability

- One concrete command representing "transition a Campaign's lifecycle state" (or, if design selects `revise_scope_statement`, "revise a Campaign's scope statement"), carrying the minimal data the frozen repository's `save()` method and the targeted mutation method already require.
- One concrete handler conforming to the frozen `CommandHandler` Protocol that loads a `Campaign` (however design determines is necessary to obtain a valid `expected_persisted_version`), invokes exactly one existing, frozen `Campaign` mutation method, and persists the result via the frozen repository's `save()` method.
- Binding this handler to a `CommandEntryPoint` and invoking it, proving the frozen write-side boundary's contract holds for a `save()`-based (not `add()`-based) operation.
- Contract tests proving the concrete handler conforms to the frozen `CommandHandler` Protocol.
- Integration tests proving the golden path (transitioning a Campaign created via the MILESTONE-030 write-side slice) and the already-frozen `OptimisticConcurrencyConflict` failure path both work end-to-end against real PostgreSQL.
- Identification (not resolution) of the design questions a `save()`-based concrete command handler raises that MILESTONE-030's `add()`-based design did not need to answer.

---

## 13. Frozen Out-of-Scope Capabilities

- Any retry, backoff, or automatic conflict-resolution policy for `OptimisticConcurrencyConflict`.
- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any additional Campaign command beyond this one mutation (no second transition, no batch transition, no bulk update).
- Any composition-root abstraction, handler registry, service locator, or dependency-injection framework — direct construction only, exactly as M030/M031 established.
- Any transport layer: no HTTP endpoint, no CLI command, no worker, no queue consumer.
- Any new architecture-checker package or dependency rule beyond what M030 already established, unless design discovers a genuine gap.
- Any market-data, vendor, trading-strategy, order-execution, or brokerage-integration behavior.
- Any change to MILESTONE-020 through MILESTONE-031 frozen contracts, source files, or governance documents.
- Any MILESTONE-033 work of any kind.

---

## 14. Frozen Predecessor Contracts Preserved

The following must remain exactly as frozen, unmodified, throughout MILESTONE-032's design and implementation:

- `Campaign` aggregate and its lifecycle-transition/mutation methods, including their existing allowed-state preconditions (MILESTONE-020).
- `CampaignRepository` Protocol, including its existing `save()` method signature (MILESTONE-020).
- The concrete PostgreSQL Campaign repository adapter, including its existing `save()`/`OptimisticConcurrencyConflict` behavior (MILESTONE-023).
- `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol (MILESTONE-027).
- `CommandEntryPoint[CommandT, ResultT]` (MILESTONE-029).
- Everything MILESTONE-030 and MILESTONE-031 delivered: their concrete command/query, their concrete handlers, `CampaignSnapshot`, and the `usecases` package's architecture-checker rules.

---

## 15. Open Design Questions (Explicitly Not Resolved by This Freeze)

- Which specific `Campaign` mutation capability this milestone targets — one of the 7 lifecycle-state-transition methods, or the non-state-transition `revise_scope_statement`.
- How the handler obtains a valid `expected_persisted_version` for the `save()` call.
- The exact command type's name, shape, and fields.
- The exact handler type's name and shape.
- Whether `OptimisticConcurrencyConflict` propagates transparently (expected, mirroring M030/M031's transparent-propagation precedent) or requires any milestone-specific consideration.
- Whether any architecture-checker change is needed (expected to be none).

---

## 16. Stop Conditions

This milestone stops at:

- One concrete command, one concrete handler, using one existing Campaign mutation method.
- Proof that `save()` and `OptimisticConcurrencyConflict` compose correctly through the application boundary.
- Contract, unit, architecture, and PostgreSQL integration test evidence, mirroring M030/M031's established patterns.

It does not continue into retry policy, a second mutation, a second aggregate, transport, or composition-root work, regardless of how natural such an extension might appear during design or implementation.

---

## 17. Prohibited Expansion

- No retry, backoff, or idempotency-key mechanism.
- No generic "update Campaign" capability beyond the one targeted mutation.
- No composition root, registry, dispatcher, mediator, or service locator.
- No transport layer of any kind.
- No `Run`/`EvidencePackage`/`Review` command or query.
- No MILESTONE-033 work.

---

## 18. Deferred Work

- Retry-on-`OptimisticConcurrencyConflict` policy (unblocked by this milestone's own completion, but not itself in scope).
- Any additional Campaign mutation command beyond the one selected during design.
- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any composition-root abstraction beyond direct binding, pending evidence of genuine repeated-handler need.
- Any transport/entrypoint adapter.
- MILESTONE-033 and beyond.

---

## 19. Design and Implementation Prohibition

This freeze record does NOT authorize:

- Any MILESTONE-032 design.
- Any MILESTONE-032 implementation.
- Any modification to M020-M031 frozen material.
- Any MILESTONE-033 work.

Design must operate strictly within the frozen boundaries recorded in Sections 12-14, resolving only the open design questions in Section 15, without reopening any decision M020-M031 already froze.

---

## 20. Final Scope Status

```
M032_SCOPE_STATUS=APPROVED_AND_FROZEN
M032_SCOPE_FREEZE_STATUS=APPROVED_AND_FROZEN
M032_DESIGN_STATUS=NOT_STARTED
M032_IMPLEMENTATION_STATUS=NOT_STARTED
M032_STATUS=SCOPE_APPROVED_AND_FROZEN
```

---

## 21. Next Permitted Action

**MILESTONE-032 DESIGN MISSION.**

---

## 22. Final Status

```
═══════════════════════════════════════════════════════════════════════════════

              MILESTONE-032 SCOPE FREEZE COMPLETE

═══════════════════════════════════════════════════════════════════════════════

M032 CONCRETE APPLICATION COMMAND VERTICAL SLICE (CAMPAIGN LIFECYCLE TRANSITION)

Independent Review Decision:    APPROVED FOR OWNER SCOPE FREEZE
Owner Decision:                 APPROVED_AND_FROZEN
Scope Candidate Commit:         5ea62d02d65945f0976e42b8c011217d895723e4
Scope Freeze Commit:            (recorded in a following governance commit)

M020-M031:                      UNCHANGED, ALL REMAIN APPROVED_AND_FROZEN
M032 Design:                    NOT_STARTED (now authorized)
M032 Implementation:            NOT_STARTED
M033:                           NOT_STARTED

NEXT PERMITTED ACTION: MILESTONE-032 DESIGN MISSION

═══════════════════════════════════════════════════════════════════════════════
```
