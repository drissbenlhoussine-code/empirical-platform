# MILESTONE-032 - Concrete Application Command Vertical Slice (Campaign Lifecycle Transition) Design Freeze

## 1. Document Status

**Status: APPROVED_AND_FROZEN**

This document records the owner's formal freeze of the MILESTONE-032 design following independent hostile design review, a narrow design correction, and a final independent design re-review. It authorizes MILESTONE-032 implementation to begin. It does not itself constitute implementation authorization for anything beyond what Section 26 below specifies.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at freeze | `148507683f26b205b061e43e45ed7e60b1136f00` |
| Milestone | MILESTONE-032 |

---

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 | APPROVED_AND_FROZEN (scope, design, implementation) |
| M031 | APPROVED_AND_FROZEN (scope, design, implementation — implementation freeze commit `f144c963f6bcf90a8ada5cf14853fce5e73d48d8`) |

---

## 4. M032 Scope Authority

| Field | Value |
| --- | --- |
| Scope document | `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_SCOPE.md` |
| Scope candidate commit | `5ea62d02d65945f0976e42b8c011217d895723e4` |
| Scope freeze commit | `b18878a514694d6663026e11d98859023c04a136` |
| Status | `APPROVED_AND_FROZEN` |

---

## 5. Original Design Candidate Commit

**Commit:** `50f2cd829af2e10799ab3581b4c2e56e9e04d401` (`docs: define M032 lifecycle transition design candidate`).

---

## 6. First Hostile Design-Review Decision

**Decision: M032 DESIGN REQUIRES CORRECTION.**

The first independent hostile design review verified every load-bearing decision directly against actual frozen source — mutation selection, command contract, expected-version ownership, the exact `save()` concurrency guard, return contract, transaction ownership, and architecture impact — and found all of them sound, with one exception: finding **M032-DESIGN-REVIEW-0001** (MAJOR). The design's PostgreSQL conflict scenario (original Section 21) claimed its interfering-write mechanism "exactly mirrors" M023's own frozen `test_campaign_save_stale_version_raises_optimistic_concurrency_conflict`. Direct inspection of that real test showed it uses a fundamentally different mechanism (reusing one in-memory aggregate across two different, forward-progressing transitions) that does not transfer to M032's single-mutation command. As originally written, the scenario — if implemented literally by reusing `prepare_for_authorization()` itself as the interfering write — would cause the Campaign to leave `DRAFT` before the command under test ran, producing a domain `ValueError` instead of the intended `OptimisticConcurrencyConflict`, leaving the milestone's central proof unexercised.

---

## 7. Narrow Design Correction Commit

**Commit:** `2f48b1e4af1b039c3b2a7e3598f85e63e007b216` (`docs: correct M032 design conflict-scenario mechanism`).

The correction specified `Campaign.revise_scope_statement()` — performed through an independently loaded aggregate for the same identity — as the exact interfering-write mechanism, with an explicit explanation of why `prepare_for_authorization()` cannot serve that role: it would invalidate its own domain precondition before the command under test reaches the concurrency check. `revise_scope_statement()` is the only existing `Campaign` mutation that advances `AggregateVersion` while leaving `_state` at `DRAFT` unchanged. No other design decision was reopened by this correction.

**Hash-recording commit:** `148507683f26b205b061e43e45ed7e60b1136f00` (`docs: record M032 design correction commit hash`).

---

## 8. Final Independent Design Re-Review Decision

**Decision: M032 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS.**

The final independent design re-review confirmed the corrected conflict mechanism is genuine and deterministic, that no other design decision was disturbed by the correction, and that the design introduces no second application capability. It raised one non-blocking observation (Section 9).

---

## 9. Non-Blocking Observation and Handling

**M032-DESIGN-RE-REVIEW-0001:** The corrected design retained residual wording (in Section 11's reasoning and the Section 28 risk table, distinct from the already-corrected Section 21 scenario text) stating the conflict path "directly mirrors" or "exactly mirrors" M023's conflict-test pattern, without the M032-specific qualification the Section 21 correction already established.

**Handling: Option A selected** — a narrow wording correction was made in this same freeze mission, without reopening any architectural decision. Both residual instances (Section 11 steps 2 and its closing sentence, and the Section 28 "Conflict path becoming untestable" risk-mitigation row) now state that M032's conflict evidence uses the same frozen repository optimistic-concurrency semantics M023 already proves, but with an M032-specific, state-preserving interfering write (`revise_scope_statement()`) — matching the language and substance already frozen in Section 21. No selected mutation, command contract, handler contract, expected-version ownership, return contract, conflict sequence, transaction model, package placement, architecture impact, test obligation, or scope boundary was changed by this wording pass.

---

## 10. Owner Approval

I, the owner, declare the MILESTONE-032 design, as recorded in `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_DESIGN.md` at its corrected state (design candidate commit `50f2cd829af2e10799ab3581b4c2e56e9e04d401`, correction commit `2f48b1e4af1b039c3b2a7e3598f85e63e007b216`, with the non-blocking wording observation resolved in this same freeze), **APPROVED AND FROZEN** effective immediately upon this record.

**M032 DESIGN APPROVED_AND_FROZEN**

No further change to the frozen design is permitted without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit.

---

## 11. Frozen Mutation Selection

`Campaign.prepare_for_authorization()` — `DRAFT → READY_FOR_AUTHORIZATION`. Selected over five state-unreachable candidates (`record_authorization`, `activate`, `suspend`, `resume`, `complete`) and two viable-but-rejected DRAFT-reachable candidates (`revise_scope_statement`, `cancel`) after a systematic 8-candidate comparison.

---

## 12. Frozen Command Contract

**Type name:** `PrepareCampaignForAuthorizationCommand`, module `src/empirical_platform/usecases/prepare_campaign_for_authorization.py`.

**Fields, exact:**

```python
@dataclass(frozen=True, slots=True)
class PrepareCampaignForAuthorizationCommand:
    identity: DomainIdentity[CampaignId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

---

## 13. Frozen Handler Contract

**Type name:** `PrepareCampaignForAuthorizationHandler`, same module.

- Constructor dependency: `CampaignRepository` only.
- Synchronous `CommandHandler[PrepareCampaignForAuthorizationCommand, SaveResult]` structural conformance, no inheritance.
- Exactly one `get()`, exactly one `Campaign.prepare_for_authorization()` call, exactly one `save()`.
- No retry. No second read or write.

---

## 14. Identity Semantics

`command.identity` — the full `DomainIdentity[CampaignId]` object — is passed to `CampaignRepository.get()` unchanged. No reconstruction, no decomposition.

---

## 15. Expected-Version Semantics

The caller-supplied `AggregateVersion` on the command is passed unchanged to `save(campaign, expected_persisted_version=command.expected_persisted_version)`. No pre-flight comparison against `loaded.persisted_version` is performed in the handler. No handler-derived replacement of the caller-supplied value. This is the sole source of truth the repository's own atomic concurrency check consumes.

---

## 16. Load-Mutate-Save Sequence

```
1. loaded = campaign_repository.get(command.identity)
2. campaign = loaded.aggregate
3. campaign.prepare_for_authorization(actor=command.actor, occurred_at=command.occurred_at,
                                       correlation_id=command.correlation_id, reason=command.reason)
4. result = campaign_repository.save(campaign, expected_persisted_version=command.expected_persisted_version)
5. return result
```

If step 3 raises (domain precondition violated), step 4 never executes.

---

## 17. Return Contract

The frozen `SaveResult` type (`operation: SaveOperation`, `persisted_version: AggregateVersion`), returned exactly as received from `save()`, unchanged.

---

## 18. Optimistic-Concurrency Behavior

`OptimisticConcurrencyConflict` propagates through the handler and the frozen, unmodified `CommandEntryPoint` unchanged. No handler-level `try`/`except`. No translation. No retry.

---

## 19. Domain/Repository Error Behavior

`AggregateNotFound`, domain `ValueError`/`TypeError` from `prepare_for_authorization()`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, and `InvalidPersistedAggregateState` all propagate with exact exception-instance identity preserved. No wrapping, translation, nullable result, envelope, or suppression of any kind.

---

## 20. Validation Ownership

No validation in the command or handler. All domain-precondition and format validation is owned entirely by `Campaign.prepare_for_authorization()`, `DomainIdentity`/`Identifier`, and `AggregateVersion` — all unmodified, already-frozen types.

---

## 21. Transaction Ownership

No application-level transaction orchestration. No `run_composed()`. `get()` and `save()` each retain their own existing, independent `unit_of_work()` — unchanged from M030/M031's precedent. No atomicity spans the two calls; optimistic concurrency is designed to tolerate exactly this gap.

---

## 22. CommandEntryPoint Binding

`CommandEntryPoint(PrepareCampaignForAuthorizationHandler(...))` constructed directly, in tests only. No registry, command bus, dispatcher, mediator, service locator, or DI framework. No production composition root.

---

## 23. Package/Dependency Boundaries

New module `src/empirical_platform/usecases/prepare_campaign_for_authorization.py`, within the already-authorized `usecases` package. Imports limited to `campaign.repository`, `identifiers.pairs`, `identifiers.types`, `shared.domain.versioning`, `shared.contracts.repository`, and stdlib `datetime` — all already covered by `ALLOWED["usecases"]`.

---

## 24. Architecture-Checker Impact

**None.** Verified: every required import already resolves under the existing, unmodified `ALLOWED["usecases"]`/`FORBIDDEN_IMPORT_PREFIXES["usecases"]` pair M030 established.

---

## 25. PostgreSQL Conflict-Evidence Strategy (Frozen, Corrected)

The deterministic conflict scenario, exact:

1. Seed a `Campaign` at `DRAFT`, persisted version 0 (via M030's frozen `CreateCampaignHandler`).
2. Independently reload the same identity (`campaign_repository.get(identity)`), yielding a second, separate in-memory `Campaign` object for the same row.
3. Call `revise_scope_statement(...)` on that second object.
4. `save()` it with `expected_persisted_version=AggregateVersion(0)` — succeeds; persisted version becomes 1; `DRAFT` is preserved (this is test setup only; it does not authorize `revise_scope_statement` as a second production use case — Section 27).
5. Invoke `PrepareCampaignForAuthorizationCommand` through `CommandEntryPoint` with the now-stale `expected_persisted_version=AggregateVersion(0)`.
6. The command's handler loads the latest (`DRAFT`, version 1) Campaign.
7. `prepare_for_authorization()` succeeds in memory (the aggregate is still `DRAFT`).
8. `save(campaign, expected_persisted_version=AggregateVersion(0))` is rejected by the database's atomic `UPDATE ... WHERE version = 0` (zero rows match, since the true row is at version 1) — `OptimisticConcurrencyConflict` is raised.
9. No retry, no second `save()` attempt.
10. The exact exception propagates unchanged through the handler and `CommandEntryPoint`.

Plus: golden path (successful transition, reloaded and verified), domain-invalid-transition path (invoke twice, second fails with `ValueError`), no migration/schema change, full relevant regression remains green.

---

## 26. Implementation Authorization Boundary

**Authorized:** creating `src/empirical_platform/usecases/prepare_campaign_for_authorization.py` with exactly `PrepareCampaignForAuthorizationCommand`/`PrepareCampaignForAuthorizationHandler` as frozen in Sections 11-25; unit, contract, architecture, and PostgreSQL integration tests per Section 25 and the design document's Section 22; an External Review Package mirroring M030's/M031's established structure.

**Not authorized:** any deviation from the frozen names, module placement, field shapes, dependency style, return type, repository-call sequence, or error-propagation behavior above; any architecture-checker change; any production composition-root code; any modification to M020-M031 frozen contracts, source files, or governance documents; any MILESTONE-033 work.

---

## 27. Prohibited Expansion

No second Campaign mutation command; no retry/backoff/conflict-recovery policy; no generic lifecycle or concurrency framework; no registry, command bus, dispatcher, mediator, service locator, or DI framework; no production composition root; no transport/API; no audit runtime; no market-data/vendor/trading behavior; no `Run`/`EvidencePackage`/`Review` command or query; no MILESTONE-033 work. `revise_scope_statement()`'s use in the conflict-test's interfering write (Section 25) is test scaffolding only and does not authorize it as a second production use case.

---

## 28. Preserved M020-M031 Authority

`Campaign`, `CampaignRepository`, `PostgresCampaignRepository`, `CommandHandler`, `CommandEntryPoint`, `LoadedAggregate`, `SaveResult`, `AggregateVersion`, `OptimisticConcurrencyConflict`, and everything M030/M031 delivered remain exactly as frozen, unmodified — verified via `git diff --name-status` across the entire M032 design-mission lineage returning empty for every M020-M031 source path.

---

## 29. Deferred Work

- Retry-on-`OptimisticConcurrencyConflict` policy — now unblocked by this milestone's own future implementation, but not itself in scope.
- Any additional Campaign mutation command (`record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel`, `revise_scope_statement` as its own production use case).
- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any composition-root abstraction beyond direct binding.
- Any transport/entrypoint adapter.
- MILESTONE-033 and beyond.

---

## 30. Final Status

```
M032_SCOPE_STATUS=APPROVED_AND_FROZEN
M032_DESIGN_STATUS=APPROVED_AND_FROZEN
M032_DESIGN_FREEZE_STATUS=APPROVED_AND_FROZEN
M032_IMPLEMENTATION_STATUS=NOT_STARTED
M032_STATUS=DESIGN_APPROVED_AND_FROZEN
```

M020-M031 remain unchanged and untouched throughout M032's design lifecycle.

---

## 31. Next Permitted Action

**MILESTONE-032 IMPLEMENTATION MISSION.**

This freeze record does NOT authorize:

- Any further M032 design change without the re-authorization process in Section 10.
- Any MILESTONE-033 work.
- Any implementation deviating from the frozen decisions in Sections 11-25.

```
═══════════════════════════════════════════════════════════════════════════════

              MILESTONE-032 DESIGN FREEZE COMPLETE

═══════════════════════════════════════════════════════════════════════════════

M032 CONCRETE APPLICATION COMMAND VERTICAL SLICE (CAMPAIGN LIFECYCLE TRANSITION)

First Independent Review Decision:   M032 DESIGN REQUIRES CORRECTION
Correction Commit:                   2f48b1e4af1b039c3b2a7e3598f85e63e007b216
Final Independent Re-Review Decision: M032 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS
Owner Decision:                      APPROVED_AND_FROZEN
Design Candidate Commit:             50f2cd829af2e10799ab3581b4c2e56e9e04d401
Design Freeze Commit:                (recorded in a following governance commit)

M020-M031:                           UNCHANGED, ALL REMAIN APPROVED_AND_FROZEN
M032 Scope:                          APPROVED_AND_FROZEN
M032 Design:                         APPROVED_AND_FROZEN
M032 Implementation:                 NOT_STARTED
M033:                                NOT_STARTED

NEXT PERMITTED ACTION: MILESTONE-032 IMPLEMENTATION MISSION

═══════════════════════════════════════════════════════════════════════════════
```
