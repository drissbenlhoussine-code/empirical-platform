# MILESTONE-033 - Concrete Application Command Vertical Slice (Run Creation) Scope

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW**

This document is a scope candidate. It has not been reviewed, approved, or frozen. It does not authorize design or implementation.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at scope selection | `5c89931d263b9c6e13626810d633a10d292807b5` |

---

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN (scope, design, implementation) |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN (scope, design, implementation) |
| M032 (Concrete Application Command Vertical Slice — Campaign Lifecycle Transition) | APPROVED_AND_FROZEN (scope, design, implementation — implementation freeze commit `84fcf35082aafc1a02358f2e3aa8f7de81841cc9`) |

All prior milestones remain untouched by this scope-selection mission.

---

## 4. Architectural Inventory Summary

Verified by direct inspection of source, not inferred from filenames or milestone titles:

| # | Capability | Classification | Evidence |
| --- | --- | --- | --- |
| 1 | Domain aggregates | IMPLEMENTED_AND_FROZEN | `Campaign` (M020), `Run` (M020), `EvidencePackage` (M020), `Review` (M020) — all frozen domain code |
| 2 | Repository Protocols | IMPLEMENTED_AND_FROZEN | `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` — each with identical `get`/`add`/`save` shape (M020) |
| 3 | PostgreSQL repository adapters | IMPLEMENTED_AND_FROZEN | `PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository` (M023) — all four exist, none exercised at the application layer except Campaign's |
| 4 | Transaction/repository runtime | IMPLEMENTED_AND_FROZEN | `PostgresPersistenceService.run_composed()` (M024), `PostgresRepositoryRuntime` (M025) |
| 5 | Foundation runtime composition | IMPLEMENTED_AND_FROZEN | `FoundationRuntime.repository_runtime` (M026) |
| 6 | `CommandHandler`/`QueryHandler` contracts | IMPLEMENTED_AND_FROZEN | M027/M028 Protocols only |
| 7 | `CommandEntryPoint`/`QueryEntryPoint` | IMPLEMENTED_AND_FROZEN | M029 |
| 8 | Concrete use cases | IMPLEMENTED_AND_FROZEN (exactly three, all Campaign) | `CreateCampaignHandler` (M030, `add()`), `GetCampaignHandler` (M031, `get()`), `PrepareCampaignForAuthorizationHandler` (M032, `get()`+`save()`) |
| 9 | Campaign application-layer proof | COMPLETE | All three `CampaignRepository` methods (`get`/`add`/`save`) have each been exercised by a real, frozen application-layer command/query at least once; `OptimisticConcurrencyConflict` proven (M032) |
| 10 | Run/EvidencePackage/Review application-layer proof | **ABSENT** | Verified: zero `.get(`/`.add(`/`.save(` call sites anywhere in `src/empirical_platform/usecases/` reference `Run`, `EvidencePackage`, or `Review` — every existing usecase imports and touches `Campaign` exclusively |
| 11 | `usecases` architecture-checker boundary | `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` | Verified directly in `tools/check_architecture.py` line 29 — `"run"`, `"evidence"`, `"review"` are **not** present; any Run/EvidencePackage/Review usecase would require a new, currently-unmade addition |
| 12 | Cross-aggregate dependency graph | Campaign (root) ← `Run` (references `CampaignId`) ← `EvidencePackage` (references `RunId`) ← `Review` (references `EvidencePackageId`) | Verified via direct import inspection of each aggregate's constructor dependencies — a strict linear chain, `Run` is the aggregate closest to the already-fully-proven `Campaign` |
| 13 | `Run` aggregate constructor complexity | Minimal | `Run.__init__(*, identity: DomainIdentity[RunId], campaign_id: CampaignId)` — exactly two required arguments, no manifests or sub-collections required at construction (`_manifests` starts as an empty tuple) |
| 14 | Transport/entrypoint behavior | TEST_SUPPORT_ONLY | `entrypoints/health.py`, `entrypoints/version.py` remain static stdout scripts; no HTTP/CLI framework |
| 15 | Composition-root behavior | ABSENT | Still deferred; now three concrete handlers exist (all Campaign-only, all bound via identical direct-construction test patterns) — evidence bar for a genuine repeated-handler need remains unmet, unchanged from M030/M031/M032's own consistent judgment |
| 16 | Retry/idempotency policy | ABSENT, unblocked but not built | M032 completion removed the structural blocker (a `save()`-based command now exists), but exactly one concrete conflict-producing command exists — insufficient concrete evidence to generalize a retry policy without repeating the premature-abstraction mistake M030/M031/M032 all explicitly avoided |
| 17 | Audit/governance/registry runtime behavior | ABSENT | `audit/`, `governance/`, `registry/`, `decision_candidate/`, `archive/`, `acquisition/`, `normalization/`, `validation/` remain single-file stub packages with zero implementation — each would require an entire new M020-equivalent foundation (aggregate + repository + adapter + schema) before any command/query work is possible |
| 18 | `PROJECT_CHECKPOINT.md` deferred capabilities | — | Verified directly (Section 9, current text): lists both "any additional Campaign lifecycle-transition command beyond the one MILESTONE-032 targets" **and** "any command or query for `Run`, `EvidencePackage`, or `Review`" with equal weight — no single explicit breadcrumb favors one over the other, unlike the M031→M032 transition |

---

## 5. Verified Gap

Campaign's application-layer proof is now **complete**: `add()` (M030), `get()` (M031), and `save()` with optimistic concurrency (M032) have each been exercised by a real, frozen command or query. By contrast, `Run`, `EvidencePackage`, and `Review` — despite having identical, already-frozen repository Protocols (`get`/`add`/`save`, M020) and already-frozen concrete PostgreSQL adapters (M023) — have **zero** application-layer proof of any kind. This is not a speculative gap: it is directly, independently verified by a repository-wide search finding zero references to `Run`, `EvidencePackage`, or `Review` anywhere in `src/empirical_platform/usecases/`.

Unlike the M031→M032 transition (where M030's own frozen scope and M031's own deferred-capabilities entry each explicitly named the exact next dependency), no single frozen document singles out this gap over the alternative of a fourth Campaign-only milestone — `PROJECT_CHECKPOINT.md`'s deferred-capabilities list carries both with equal weight. This scope selection therefore rests on independent comparative analysis (Sections 7-8), not on locating an explicit breadcrumb.

---

## 6. Candidate Inventory

**Candidate A — `Run` creation command (`add()`-based), first Run vertical slice.**
- Architectural problem solved: proves the `usecases`/CQRS pattern and its architecture-checker boundary genuinely generalize beyond the one aggregate (`Campaign`) that has exercised it so far.
- Why it follows M032: `Run` is the aggregate architecturally closest to the fully-proven `Campaign` (references only `CampaignId`, no other aggregate) — the same "narrowest available subject" reasoning M030 originally used to select `Campaign` over `Run`/`EvidencePackage`/`Review`.
- Exact single capability added: one concrete command creating a new `Run`, persisted via `RunRepository.add()`.
- Dependencies: `Run` aggregate (frozen, minimal constructor), `RunRepository.add()` (frozen), `CommandHandler`/`CommandEntryPoint` (frozen), `usecases` package (established by M030).
- Repository evidence: `Run.__init__` requires only `identity` and `campaign_id` — no manifests, no sub-collections, directly mirroring `Campaign.__init__`'s own minimal two-argument shape.
- Probable future implementation surface: one command type, one handler, in `usecases/`, mirroring M030's exact shape for a different aggregate.
- Explicit inclusions: one create command; `add()` call; transparent error propagation.
- Explicit exclusions: any Run lifecycle transition; any query; any other aggregate; any transport; any composition root.
- Risks: requires one genuine, new `tools/check_architecture.py` addition (adding `"run"` to `ALLOWED["usecases"]`) — a real decision, not yet made by any prior milestone, though fully precedented by M030's own addition process.
- Prerequisite gaps: none identified — every dependency is already frozen and ready.
- Scope size: narrow, single capability, matches M030's own discipline exactly for a second aggregate.
- Testability: high — the exact M030 test pattern (unit, contract, architecture, PostgreSQL integration) transfers directly.
- Reviewability: high — identical review pattern already three times validated in this repository.
- Genuine vertical progression: yes — the first proof that the frozen `usecases` pattern is not accidentally coupled to `Campaign` specifically.

**Candidate B — `Campaign.record_authorization()` command, fourth Campaign-only milestone.**
- Architectural problem solved: would extend the Campaign lifecycle one step further (`READY_FOR_AUTHORIZATION → AUTHORIZED`), now reachable via the M030→M032 chain.
- Why it may be premature relative to A: repeats an already-proven pattern (`save()`-based update, optimistic concurrency) for a third time on the same aggregate; proves nothing architecturally new — M032 already established that this project's `save()`/conflict path works correctly.
- Rejected at Phase 8 below (dominated by Candidate A on architectural necessity and future-unlock value).

**Candidate C — `EvidencePackage` or `Review` creation command.**
- Architectural problem solved: same generalization proof as Candidate A, but for an aggregate one or two hops further down the dependency chain (`EvidencePackage` references `RunId`; `Review` references `EvidencePackageId`).
- Why it may be premature: less ready than `Run` — proving the pattern on `Run` first establishes direct precedent before attempting an aggregate whose own natural creation path plausibly depends on a `Run` already existing (`EvidencePackage`) or an `EvidencePackage` already existing (`Review`).
- Rejected at Phase 8 below (dominated by Candidate A on dependency-graph readiness).

**Candidate D — Retry-on-`OptimisticConcurrencyConflict` policy.**
- Architectural problem solved: would define how the application layer responds to a real conflict, now technically unblocked by M032's existence.
- Why it may be premature: exactly one concrete conflict-producing command exists (M032); generalizing a policy from a single data point repeats the premature-abstraction mistake M030/M031/M032 all explicitly and repeatedly avoided.
- Rejected at Phase 8 below.

**Candidate E — Composition-root wiring.**
- Architectural problem solved: would give commands/queries a production binding mechanism instead of test-only direct construction.
- Why it may be premature: three concrete handlers now exist, all still scoped to one aggregate (`Campaign`), all still following an identical trivial three-line direct-construction test pattern — the "repeated-handler-need" evidence bar M030/M031/M032 each independently declined to consider met remains unmet by this same standard.
- Rejected at Phase 8 below.

**Candidate F — Transport/API layer.**
- Architectural problem solved: would expose commands/queries outside test code.
- Why it may be premature: `entrypoints/` remains two static stdout scripts; this candidate silently depends on the already-rejected composition-root candidate, stacking two unresolved layers.
- Rejected at Phase 8 below.

**Candidate G — Audit runtime, registry, or governance behavior.**
- Architectural problem solved: would begin one of the currently-empty cross-cutting boundary packages.
- Why it may be premature: each is a single-file stub with zero implementation, requiring an entire new M020-equivalent foundation before any command/query work is even possible — many layers further away than any Campaign-adjacent or Run/EvidencePackage/Review candidate.
- Rejected at Phase 8 below.

---

## 7. Candidate Comparison

| Criterion | A (Run creation) | B (Campaign record_authorization) | C (EvidencePackage/Review creation) | D (retry policy) | E (composition root) | F (transport) | G (audit/registry) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Architectural necessity | High — closes the only remaining unproven-aggregate gap | Low — Campaign's proof is already complete | Medium — same gap, but less ready | Low — insufficient evidence to generalize | Not yet evidenced | Depends on rejected E | Very low — foundational work not yet started |
| Dependency readiness | All frozen and ready | All frozen and ready | Frozen but one/two dependency hops further | Blocked on more conflict-producing commands | Evidence threshold unmet | Blocked on E | Blocked on an entire new foundation |
| Leverage / future-unlock value | High — first proof the pattern generalizes; unlocks future Run queries/transitions exactly as M030 unlocked M031/M032 | Low — no new proof | Medium, but lower than A | Depends on A/C existing first | Medium, premature | Low, premature | Low, many layers away |
| Sequencing | Correct — no blocking predecessor | No blocking predecessor, but lower necessity | Correctly sequenced after A | Must follow more concrete conflict evidence | No clear predecessor met | Must follow E | Must follow its own foundation work |
| Risk | Low — one well-precedented architecture-checker addition | Very low | Low-medium | High — premature generalization | Medium | High | High |
| Scope purity | One capability | One capability | One capability | One capability, but premature | One capability, but premature | Multiple unresolved dependencies | Multiple unresolved dependencies |
| Predecessor compatibility | Perfect — no M020-M032 contract touched | Perfect | Perfect | Perfect | Perfect | Unknown | Perfect |
| Implementation complexity | Low — near-identical to M030's own shape | Low — near-identical to M032's own shape | Low-medium | Medium-high | Medium | High | High |
| Future unlock value | High | Low | Medium | Depends on A/C | Medium | Medium | Low near-term |

**Rank:** A > C > B > D > E > F > G.

**Selected: Candidate A.**

---

## 8. Rejected Candidates

- **B (Campaign `record_authorization()`):** rejected — Campaign's application-layer proof (`add`/`get`/`save`+conflict) is already complete after M030-M032; a fourth Campaign-only milestone would add no new architectural proof, only repeat an already-validated pattern, while the more architecturally necessary gap (the `usecases` pattern's untested generalization to a second aggregate) remains open.
- **C (`EvidencePackage`/`Review` creation):** rejected as the *primary* selection — dominated by Candidate A's superior dependency-graph readiness (`Run` references only `CampaignId`, the sole already-fully-proven aggregate; `EvidencePackage`/`Review` sit one or two hops further down a chain whose intermediate links are not yet proven at the application layer).
- **D (retry policy):** rejected — exactly one concrete conflict-producing command exists; generalizing a policy from a single data point is the exact premature-abstraction risk M030/M031/M032 each explicitly flagged and avoided.
- **E (composition root):** rejected — the "repeated-handler-need" evidence bar this repository has consistently applied (three times now) remains unmet; three handlers, one aggregate, one trivial and unchanging binding pattern.
- **F (transport):** rejected — silently depends on the already-rejected composition-root candidate, stacking unresolved layers.
- **G (audit/registry/governance):** rejected — each is an empty stub requiring an entire new foundational milestone chain (aggregate, repository, adapter, schema) before any command/query work becomes possible at all.

---

## 9. Selected Scope

**Concrete Application Command Vertical Slice: Run Creation.**

A single write-side (command) operation — creating a new `Run` associated with an existing `Campaign` — implemented as one concrete command and one concrete handler conforming to the frozen MILESTONE-027 `CommandHandler` Protocol, invoked through the frozen MILESTONE-029 `CommandEntryPoint`, persisting via the frozen MILESTONE-023 concrete `Run` repository adapter's `add()` method — the first time any application-layer code has ever exercised any capability of the `Run`, `EvidencePackage`, or `Review` aggregates.

---

## 10. Mission Statement

Prove, with one concrete, minimal, real command, that the frozen `usecases` application-invocation pattern — established and validated exclusively against `Campaign` across M030, M031, and M032 — genuinely generalizes to a second aggregate, without introducing any Run lifecycle-transition capability, without introducing the query side, without introducing a third aggregate, and without introducing any framework, registry, or abstraction beyond what is already frozen.

---

## 11. Architectural Problem

Every use case implemented so far (M030, M031, M032) has been `Campaign`-specific. The `usecases` package's architecture-checker boundary (`ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}`) has never needed to admit a second aggregate. Whether the established command/handler/entry-point pattern, and the architecture-checker rule shape that governs it, genuinely generalizes — or whether it has an undiscovered, accidental coupling to `Campaign` specifically — remains unverified. `Run`, `EvidencePackage`, and `Review` each already have a fully frozen, `Campaign`-parallel repository Protocol and concrete PostgreSQL adapter with zero application-layer proof of any kind.

---

## 12. Why M033 Is Next

- It closes the only remaining *unproven-generalization* gap this repository's own architectural inventory reveals — every other candidate either repeats an already-proven pattern (Campaign's fourth milestone) or requires unmet prerequisites (retry policy, composition root, transport, audit/registry work).
- `Run` is the architecturally closest, least-cross-aggregate-dependent candidate among the three unproven aggregates — it depends only on `CampaignId`, the identifier of the one aggregate already fully proven.
- Every dependency it needs (`Run` aggregate, `RunRepository.add()`, `CommandHandler`, `CommandEntryPoint`, the `usecases` package) is already frozen and implemented.
- It preserves the exact single-aggregate-per-milestone, single-capability, test-only-binding discipline M030/M031/M032 all established, so it is independently designable, testable, reviewable, and freezable using an already-proven review methodology.
- It requires exactly one small, genuinely new, but fully precedented architecture-checker addition — a real decision this milestone's design must justify, not a speculative one.

---

## 13. In-Scope Capability

- One concrete command representing "create a new Run for an existing Campaign," carrying the minimal data the frozen repository's `add()` method and `Run`'s constructor already require.
- One concrete handler conforming to the frozen `CommandHandler` Protocol that constructs a new `Run` and persists it via the frozen repository's `add()` method.
- Binding this handler to a `CommandEntryPoint` and invoking it, proving the frozen write-side boundary's contract holds for a second aggregate.
- Contract tests proving the concrete handler conforms to the frozen `CommandHandler` Protocol.
- Integration tests proving the golden path and the already-frozen duplicate-identity failure path both work end-to-end against real PostgreSQL.
- Identification (not resolution) of the design questions a `Run`-specific concrete command handler raises that M030's `Campaign`-specific design did not need to answer (in particular: how the command supplies or validates the referenced `campaign_id`, and the exact, minimal architecture-checker addition required).

---

## 14. Out-of-Scope Capabilities

- Any `Run` lifecycle-transition command (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`, or manifest-append behavior).
- Any `Run` query (retrieval-by-identity or otherwise).
- Any command or query for `Campaign` beyond what M030/M031/M032 already delivered.
- Any command or query for `EvidencePackage` or `Review`.
- Any composition-root abstraction, handler registry, service locator, or dependency-injection framework — direct construction only, exactly as M030/M031/M032 established.
- Any transport layer: no HTTP endpoint, no CLI command, no worker, no queue consumer.
- Any retry, idempotency, or optimistic-concurrency-conflict handling beyond what `add()` already frozen-ly provides (creation has no prior version to conflict with, mirroring M030's own precedent).
- Any validation that the referenced `Campaign` actually exists, unless repository evidence proves this is required by an already-frozen contract (an open design question, not resolved here).
- Any market-data, vendor, trading-strategy, order-execution, or brokerage-integration behavior.
- Any change to MILESTONE-020 through MILESTONE-032 frozen contracts, source files, or governance documents.
- Any MILESTONE-034 work of any kind.

---

## 15. Non-Goals

- This milestone is not a general-purpose "Run management" capability; it exercises exactly one operation (`add()`-based creation), not a generic aggregate-creation framework.
- This milestone is not the retry-policy milestone; it does not attempt to generalize conflict handling from a still-singular data point.
- This milestone does not attempt to justify or introduce a composition root; direct test-only binding remains the pattern until repeated evidence across multiple aggregates is judged sufficient by a future milestone.
- This milestone does not decide whether `EvidencePackage` or `Review` should be next — that determination belongs to a future, independently-scoped milestone once `Run`'s own vertical slice exists as precedent.

---

## 16. Dependencies

**Depends on (frozen, read-only):**

- MILESTONE-020 `RunRepository` Protocol (`add()` method) and `Run` aggregate.
- MILESTONE-023 concrete PostgreSQL `Run` repository adapter's `add()` implementation.
- MILESTONE-025 repository runtime composition.
- MILESTONE-027 `CommandHandler` Protocol.
- MILESTONE-029 `CommandEntryPoint`.
- MILESTONE-030's already-delivered `Campaign` creation vertical slice, whose exact pattern (command/handler shape, test strategy, architecture-checker addition process) this milestone directly mirrors for a second aggregate.

**Does not depend on:** any `EvidencePackage`/`Review` material, any Campaign lifecycle-transition work beyond M032, any transport or entrypoint code, any composition-root abstraction.

---

## 17. Frozen Contracts Preserved

The following must remain exactly as frozen, unmodified, throughout this milestone's design and implementation:

- `Run` aggregate and its constructor (MILESTONE-020).
- `RunRepository` Protocol, including its existing `add()` method signature (MILESTONE-020).
- The concrete PostgreSQL `Run` repository adapter (MILESTONE-023).
- `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol (MILESTONE-027).
- `CommandEntryPoint[CommandT, ResultT]` (MILESTONE-029).
- Everything MILESTONE-030, MILESTONE-031, and MILESTONE-032 delivered: their concrete commands/queries, their concrete handlers, `CampaignSnapshot`, and the `usecases` package's existing architecture-checker rules for `Campaign`.

---

## 18. Open Design Questions (Explicitly Not Resolved by This Scope)

- The exact command type's name, shape, and fields.
- The exact handler type's name and shape.
- Whether the command carries a raw `campaign_governance_id: str` (mirroring `CreateCampaignCommand`'s raw-field style) or the already-frozen `CampaignId`/`DomainIdentity[CampaignId]` type directly.
- Whether the handler validates that the referenced Campaign exists (e.g., via a `CampaignRepository.get()` call) or defers entirely to whatever the persistence layer's foreign-key/constraint behavior already enforces — a decision requiring direct repository-behavior evidence, not assumption.
- The runtime-ID generation mechanism for the new Run's identity (expected to reuse the already-frozen `RuntimeIdentifierGenerator`, mirroring M030's precedent, but not frozen here).
- The exact, minimal `tools/check_architecture.py` addition required (expected: adding `"run"` to `ALLOWED["usecases"]`, mirroring M030's own addition shape) — a design-phase determination, not a scope-freeze decision.

---

## 19. Acceptance Boundaries

MILESTONE-033 scope selection is complete and ready for independent review when:

- Exactly one write-side capability is proposed (Run creation), matching the same narrowness discipline M030/M031/M032 established.
- No class name, method signature, module path, package structure, dependency-injection mechanism, registry, transaction behavior, error hierarchy, retry policy, or other design/implementation decision is fixed by this document.
- Every excluded capability is explicit, and every excluded capability's reason traces to either a genuine unmet prerequisite or a deliberate narrowness choice consistent with M030/M031/M032's own precedent.
- The scope is independently reviewable without requiring the reviewer to first resolve any open design question themselves.

---

## 20. Stop Conditions

This milestone stops at:

- One concrete command, one concrete handler, using `Run.__init__` and `RunRepository.add()` only.
- Proof that the `usecases`/`CommandHandler`/`CommandEntryPoint` pattern composes correctly for a second aggregate.
- Contract, unit, architecture, and PostgreSQL integration test evidence, mirroring M030's established patterns.

It does not continue into any Run lifecycle transition, any Run query, any second aggregate beyond Run, composition-root work, or transport work, regardless of how natural such an extension might appear during design or implementation.

---

## 21. Prohibited Expansion

- No Run lifecycle-transition command.
- No Run query.
- No `EvidencePackage`/`Review` command or query.
- No composition root, registry, dispatcher, mediator, or service locator.
- No transport layer of any kind.
- No retry/backoff/idempotency policy.
- No MILESTONE-034 work.

---

## 22. Deferred Work

- Any Run lifecycle-transition command (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`).
- Any Run query (retrieval-by-identity or otherwise).
- Any additional Campaign lifecycle-transition command beyond M032.
- Any command or query for `EvidencePackage` or `Review`.
- Retry-on-`OptimisticConcurrencyConflict` policy — the evidence base remains one concrete conflict-producing command; a second one (from a future Run lifecycle-transition milestone) would strengthen the case for generalizing.
- Any composition-root abstraction beyond direct binding.
- Any transport/entrypoint adapter.
- MILESTONE-034 and beyond.

---

## 23. Risks

- **Second-aggregate coupling risk:** the frozen `usecases` pattern may reveal an accidental `Campaign`-specific assumption when applied to `Run` for the first time. Mitigation: this is precisely the risk this milestone exists to surface and resolve — a genuine architectural proof point, not a reason to avoid the milestone.
- **Architecture-checker addition risk:** this is the first `usecases`-boundary change since M030's own addition; an incautious change could broaden the boundary more than necessary. Mitigation: the design phase must justify the exact, minimal addition (expected: `"run"` added to `ALLOWED["usecases"]` only) using the same evidence-based process M030's own hostile design review already validated.
- **Cross-aggregate reference-validation ambiguity:** whether the handler must verify the referenced Campaign exists before creating a Run is a genuine open question (Section 18) this scope does not resolve. Mitigation: explicitly flagged for the design phase rather than silently assumed either way.
- **Symmetry pressure:** risk of copying M030's `Campaign`-specific decisions (raw-string command fields, `RuntimeIdentifierGenerator` dependency, no pre-read) onto `Run` without independently re-justifying them, given `Run` carries a genuinely new element (a foreign-aggregate reference) `Campaign`'s own creation command never had. Mitigation: design must independently re-derive these decisions for `Run`, not merely restate M030's `Campaign`-side reasoning.
- **Scope-creep pressure toward a second Run capability:** having proven `Run` creation invites "just add the query too" or "just add the first lifecycle transition too" expansion. Mitigation: explicitly excluded above (Sections 14, 21-22); any such addition requires its own scope-change authorization.

---

## 24. Independent Review Criteria

A hostile independent scope review should verify:

- The verified gap (Section 5) is genuinely unsolved and genuinely evidenced by direct repository inspection, not asserted.
- Every rejected candidate (Section 8) has a specific, evidence-based rejection reason, not a generic dismissal.
- No class name, method signature, module path, or other implementation/design decision is prematurely fixed anywhere in this document.
- Every frozen M020-M032 contract this scope depends on is accurately described and unmodified.
- The scope is narrow enough to be independently designable, testable, reviewable, and freezable as a single milestone.
- The comparative ranking of candidates (Section 7) is independently defensible, not merely asserted.

---

## 25. Owner Decision Status

**CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW.** Not approved. Not frozen. Does not authorize design or implementation.

---

## 26. Next Permitted Action

**MILESTONE-033 INDEPENDENT SCOPE REVIEW.**
