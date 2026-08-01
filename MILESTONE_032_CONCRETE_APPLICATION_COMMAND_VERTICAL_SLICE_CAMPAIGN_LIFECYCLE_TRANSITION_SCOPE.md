# MILESTONE-032 - Concrete Application Command Vertical Slice (Campaign Lifecycle Transition) Scope

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW**

This document is a scope candidate. It has not been reviewed, approved, or frozen. It does not authorize design or implementation.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at scope selection | `b009e14cd49ec33161c87da354dd756b1a3bbd94` |

---

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN (scope, design, implementation) |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN (scope, design, implementation) |

All prior milestones remain untouched by this scope-selection mission.

---

## 4. Architectural Inventory Summary

Verified by direct inspection of source, not inferred from filenames or milestone titles:

| # | Capability | Classification | Evidence |
| --- | --- | --- | --- |
| 1 | Domain aggregates/lifecycle | IMPLEMENTED_AND_FROZEN (domain layer only) | `Campaign` (8 methods: `revise_scope_statement`, `prepare_for_authorization`, `record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel`), `Run` (7 methods), `EvidencePackage` (3 methods), `Review` (3 methods) — all frozen domain code |
| 2 | Repository Protocols | IMPLEMENTED_AND_FROZEN | `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` — each with `get`/`add`/`save` (M020) |
| 3 | PostgreSQL repository adapters | IMPLEMENTED_AND_FROZEN | `PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository` (M023) |
| 4 | Transaction/repository runtime | IMPLEMENTED_AND_FROZEN | `PostgresPersistenceService.run_composed()` (M024), `PostgresRepositoryRuntime` (M025) |
| 5 | Foundation runtime composition | IMPLEMENTED_AND_FROZEN | `FoundationRuntime.repository_runtime` (M026) |
| 6 | `CommandHandler`/`QueryHandler` contracts | IMPLEMENTED_AND_FROZEN | M027/M028 Protocols only |
| 7 | `CommandEntryPoint`/`QueryEntryPoint` | IMPLEMENTED_AND_FROZEN | M029 |
| 8 | Concrete use cases | IMPLEMENTED_AND_FROZEN (exactly two) | `CreateCampaignHandler` (M030, calls `add()` only), `GetCampaignHandler` (M031, calls `get()` only) |
| 9 | Command-side vertical slices | PARTIALLY_PRESENT | Exactly one exists (`add()`-based creation). A `save()`-based command is **ABSENT** — verified: zero occurrences of `campaign_repository.save(` or any repository `.save(` call anywhere in `src/empirical_platform/usecases/` |
| 10 | Query-side vertical slices | PARTIALLY_PRESENT | Exactly one exists (retrieval-by-identity). No other query exists |
| 11 | Composition-root behavior | ABSENT | Explicitly deferred by both M030 and M031 scopes pending evidence of genuine repeated-handler need |
| 12 | Transport/entrypoint behavior | TEST_SUPPORT_ONLY | `entrypoints/health.py`, `entrypoints/version.py` are static stdout scripts; no HTTP/CLI framework; not wired to any command or query |
| 13 | Application-layer error/concurrency behavior | ABSENT (at application layer) | `OptimisticConcurrencyConflict` is frozen at the repository layer (M020/M023) but has never propagated through any command handler, because no command ever calls `save()` |
| 14 | Retry/idempotency behavior | ABSENT, explicitly blocked | M030's own frozen scope: "blocked on a `save()`-based command that does not yet exist" |
| 15 | Audit/governance runtime behavior | ABSENT | `audit/`, `governance/`, `registry/`, `decision_candidate/`, `archive/`, `acquisition/`, `normalization/`, `validation/` are all single-file stub packages containing only a docstring declaring "no behavior is implemented" |
| 16 | Application result/read contracts | IMPLEMENTED_AND_FROZEN (exactly one) | `CampaignSnapshot` (M031) — narrow, milestone-local, not a framework |
| 17 | Integration coverage | PARTIALLY_PRESENT | Repository-level PostgreSQL integration tests exist for all four aggregates (M023); usecase-level integration tests exist only for Campaign (M030 create, M031 retrieve) |
| 18 | PROJECT_CHECKPOINT.md deferred capabilities | — | "retry-on-`OptimisticConcurrencyConflict` policy after a concrete handler exists that saves an existing aggregate"; APIs, workers, Audit runtime, Decision Candidate, Decision Freeze; market-data/vendor/trading/campaign-execution behavior; composition-root abstraction beyond direct binding |

---

## 5. Verified Gap

`CampaignRepository.save()` — and every other aggregate's `.save()` method — has been frozen since M020 and implemented since M023, together with the `OptimisticConcurrencyConflict` contract it guards. Neither has ever been exercised by any application-layer code: `CreateCampaignHandler` (M030) calls only `add()`; `GetCampaignHandler` (M031) calls only `get()`. This is not a speculative or invented gap — it is the literal, explicitly named next dependency in two consecutive frozen scope documents:

- M030's frozen scope: "Any retry, idempotency, or optimistic-concurrency-conflict handling — this remains blocked on a `save()`-based command that does not yet exist."
- M031's `PROJECT_CHECKPOINT.md` deferred-capabilities entry: "retry-on-`OptimisticConcurrencyConflict` policy after a concrete handler exists that saves an existing aggregate."

The gap is architecturally real (a frozen, implemented repository method with zero application-layer proof), not already solved, not merely desirable, dependent on nothing unresolved (every collaborator it needs is already frozen), and narrow enough for a single milestone (one command, one aggregate, no new persistence/schema/runtime work).

---

## 6. Candidate Inventory

**Candidate A — First `save()`-based Campaign lifecycle-transition command vertical slice.**
- Architectural problem solved: proves the update/`save()` path and the `OptimisticConcurrencyConflict` contract work end-to-end through the application boundary, completing the CRUD-adjacent proof M030 (create) and M031 (read) began.
- Why it follows M031: it is the explicitly named next dependency in both predecessors' own frozen text.
- Exact single capability added: one concrete command invoking one existing `Campaign` lifecycle-transition method, persisted via `CampaignRepository.save()`.
- Dependencies: `Campaign` aggregate (frozen), `CampaignRepository.save()` (frozen), `CommandHandler`/`CommandEntryPoint` (frozen), `usecases` package (established by M030).
- Repository evidence: `Campaign` already has 7 lifecycle-transition methods with zero application-layer callers; `save()` is fully implemented and tested at the repository/integration level (M023) but has zero usecase-level proof.
- Probable future implementation surface: one command type, one handler, in `usecases/`, mirroring M030's shape.
- Explicit inclusions: one state-transition command; `save()` call; transparent `OptimisticConcurrencyConflict` propagation.
- Explicit exclusions: retry policy; any other aggregate; any transport; any composition root.
- Risks: choosing an unnecessarily complex transition; conflating "prove save() works" with "build a retry policy."
- Prerequisite gaps: none identified.
- Why it may be premature: none found — every dependency is already frozen.
- Scope size: narrow, single capability, matches M030/M031 discipline exactly.
- Testability: high — mirrors M030/M031's exact test patterns (unit, contract, architecture, PostgreSQL integration).
- Reviewability: high — identical review pattern already twice validated in this repository.
- Genuine vertical progression: yes — a `save()`-based command is materially different from `add()` (requires load-then-mutate-then-save, exercises optimistic concurrency for the first time).

**Candidate B — Optimistic-concurrency-conflict handling / retry policy foundation.**
- Architectural problem solved: would define how the application layer responds to `OptimisticConcurrencyConflict`.
- Why it may be premature: no `save()`-based command exists yet to generate a real conflict to respond to; M030's own frozen scope explicitly blocks this on Candidate A first.
- Rejected at Phase 5 (sequencing) below.

**Candidate C — Application composition-root wiring.**
- Architectural problem solved: would give commands/queries a production binding mechanism instead of test-only direct construction.
- Why it may be premature: M030 and M031 each explicitly declined this pending "evidence of genuine repeated-handler need" — with only 2 concrete handlers existing, that evidence bar is not yet met; a 3rd handler (Candidate A) does not by itself establish a *pattern* requiring a root, since it is still Campaign-only.
- Rejected at Phase 5 below.

**Candidate D — Another aggregate's command vertical slice (Run/EvidencePackage/Review creation).**
- Architectural problem solved: would prove the `add()` path for a second aggregate.
- Why it may be premature: repeats M030's already-proven pattern on a different aggregate without closing any new architectural gap; the `save()`/optimistic-concurrency gap remains open regardless, and is more architecturally significant since it is a distinct code path (not merely a second instance of an already-proven one).
- Rejected at Phase 4 below (dominated by Candidate A on architectural necessity).

**Candidate E — Another aggregate's query vertical slice (Run/EvidencePackage/Review retrieval).**
- Architectural problem solved: would prove the `get()` path for a second aggregate.
- Why it may be premature: same as Candidate D — repeats an already-proven pattern; additionally, none of these aggregates has any command yet, so a query would have nothing to retrieve outside of test-only seeded data, unlike Campaign where M030 already provides a real write path to read back.
- Rejected at Phase 4 below.

**Candidate F — Transport-neutral invocation adapter / real API.**
- Architectural problem solved: would expose commands/queries outside test code.
- Why it may be premature: `entrypoints/` contains only two static stdout scripts, no HTTP/CLI framework; this candidate silently depends on composition-root wiring (Candidate C), itself already rejected as premature — two unresolved layers stacked.
- Rejected at Phase 5 below.

---

## 7. Candidate Comparison

| Criterion | A (save-based transition) | B (retry policy) | C (composition root) | D (2nd aggregate command) | E (2nd aggregate query) | F (transport) |
| --- | --- | --- | --- | --- | --- | --- |
| Architectural necessity | High — explicitly named gap | Depends on A | Not yet evidenced | Low — repeats proven pattern | Low — repeats proven pattern | Depends on C |
| Logical sequencing | Correct — directly next | Must follow A | Unclear predecessor | No blocking predecessor, but lower value | No blocking predecessor, but lower value | Must follow C |
| Dependency readiness | All frozen and ready | Blocked (needs A) | Evidence threshold unmet | All frozen and ready | Blocked (no writer yet) | Blocked (needs C) |
| Scope cohesion | One capability | One capability, but premature | One capability, but premature | One capability | One capability | Two capabilities (root + transport) |
| Single-capability purity | Yes | Yes (if scoped alone) | Yes | Yes | Yes | No |
| Isolation | Campaign only | Cross-cutting by nature | Cross-cutting by nature | New aggregate | New aggregate | Cross-cutting |
| Testability | High, proven pattern | Cannot test without A | Hard to test in isolation | High, proven pattern | Medium (no writer) | Low, many unknowns |
| Reviewability | High, proven pattern | N/A until A exists | Low, ill-defined boundary | High | Medium | Low |
| Risk containment | Low risk | High risk (premature policy) | Medium risk | Low risk | Low risk | High risk |
| Frozen-contract compatibility | Uses only frozen `save()` | N/A | N/A | Uses only frozen `add()` | Uses only frozen `get()` | Unknown |
| New persistence/schema work | None | None | None | None | None | Unknown |
| New runtime/composition work | None | None | Yes (by definition) | None | None | Yes |
| Unresolved error policy needed | No — transparent propagation, same as M030/M031 | Yes, by definition | N/A | No | No | Unknown |
| Unresolved transaction policy needed | No — `save()` owns its own unit of work | N/A | N/A | No | N/A | Unknown |
| Speculative-abstraction risk | Low | High if scoped now | High if scoped now | Low | Low | High |
| Future architectural leverage | High — unlocks retry-policy work explicitly deferred pending this | High, but only after A | Medium | Low — no new proof | Low — no new proof | Medium, but premature |
| Product progression value | High — closes the last unproven CRUD-adjacent path | Depends on A | Low near-term | Medium | Medium | Medium |
| Clean stop boundary | Yes — one command, no retry logic itself | No — retry is open-ended without A first | No — root design is open-ended | Yes | Yes | No |

**Rank:** A > D ≈ E > C > B > F.

**Selected: Candidate A.**

---

## 8. Rejected Candidates

- **B (retry policy):** rejected — explicitly and literally blocked by M030's own frozen scope on a `save()`-based command not yet existing; scoping it now would violate the frozen predecessor's own stated dependency order.
- **C (composition root):** rejected — the evidence bar M030/M031 both set ("genuine repeated-handler need") is not met by 2 (soon 3) handlers all scoped to one aggregate; scoping this now would be speculative framework-building ahead of evidence, which the frozen predecessor scopes explicitly warned against.
- **D (2nd aggregate command):** rejected — dominated by Candidate A on architectural necessity and future leverage; it would add a second instance of an already-proven pattern instead of closing the more significant, explicitly-deferred `save()`/optimistic-concurrency gap.
- **E (2nd aggregate query):** rejected — same reasoning as D, with the added weakness that no writer exists yet for any of Run/EvidencePackage/Review, making a query for them less evidenced than Candidate A (where Campaign already has a real, frozen writer).
- **F (transport):** rejected — silently depends on Candidate C (composition root), which is itself rejected as premature; would also require resolving authentication/framework/protocol choices with zero prior evidence in this repository, stacking multiple unresolved layers.

---

## 9. Selected Scope

**Concrete Application Command Vertical Slice: Campaign Lifecycle Transition.**

A single write-side (command) operation — transitioning a previously created `Campaign` from one lifecycle state to another using one of its existing, frozen lifecycle-transition methods — implemented as one concrete command and one concrete handler conforming to the frozen MILESTONE-027 `CommandHandler` Protocol, invoked through the frozen MILESTONE-029 `CommandEntryPoint`, persisting the transition through the frozen MILESTONE-023 concrete `Campaign` repository adapter's `save()` method for the first time anywhere in the application layer.

---

## 10. Mission Statement

Prove, with one concrete, minimal, real command, that the frozen `save()`-based update path and its optimistic-concurrency-conflict contract compose correctly end-to-end through the application invocation boundary — completing the create/read/update proof M030 and M031 began, without introducing a retry policy, without introducing transport, without introducing a second aggregate, and without introducing any framework, registry, or abstraction beyond what is already frozen.

---

## 11. Architectural Problem

The `save()` method on every frozen repository Protocol, and the `OptimisticConcurrencyConflict` exception it can raise, have existed since M020/M023 with zero proof that either works when invoked from a real application-layer command rather than a repository-level test. Without this proof, the explicitly deferred retry-policy work (named in M030's own scope) has no foundation to build on, and the platform cannot yet demonstrate a complete write-side lifecycle for any aggregate — only creation.

---

## 12. Why M032 Is Next

- It is the literal next item named by two consecutive frozen predecessor scopes, not an invented or speculative choice.
- Every dependency it needs (`Campaign`'s lifecycle-transition methods, `CampaignRepository.save()`, `CommandHandler`, `CommandEntryPoint`, the `usecases` package) is already frozen and implemented — no prerequisite gap exists.
- It is narrower and more architecturally necessary than every other candidate considered (Section 7-8).
- It preserves the exact single-aggregate, single-capability, test-only-binding discipline M030 and M031 both established, so it is independently designable, testable, reviewable, and freezable using an already-proven review methodology.

---

## 13. In-Scope Capability

- One concrete command representing "transition a Campaign's lifecycle state," carrying the minimal data the frozen repository's `save()` method and the targeted lifecycle-transition method already require.
- One concrete handler conforming to the frozen `CommandHandler` Protocol that loads a `Campaign` (however the design determines is necessary to obtain a valid `expected_persisted_version`), invokes exactly one existing, frozen `Campaign` lifecycle-transition method, and persists the result via the frozen repository's `save()` method.
- Binding this handler to a `CommandEntryPoint` and invoking it, proving the frozen write-side boundary's contract holds for a `save()`-based (not `add()`-based) operation.
- Contract tests proving the concrete handler conforms to the frozen `CommandHandler` Protocol.
- Integration tests proving the golden path (transitioning a Campaign created via the MILESTONE-030 write-side slice) and the already-frozen `OptimisticConcurrencyConflict` failure path both work end-to-end against real PostgreSQL.
- Identification (not resolution) of the design questions a `save()`-based concrete command handler raises that MILESTONE-030's `add()`-based design did not need to answer.

---

## 14. Out-of-Scope Capabilities

- Any retry, backoff, or automatic conflict-resolution policy for `OptimisticConcurrencyConflict` — this milestone proves the conflict path exists and propagates correctly; it does not decide how callers should react to it.
- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any additional Campaign command beyond this one lifecycle transition (no second transition, no batch transition, no bulk update).
- Any composition-root abstraction, handler registry, service locator, or dependency-injection framework — the handler is bound to its `CommandEntryPoint` by direct construction, exactly as M030/M031 already established.
- Any transport layer: no HTTP endpoint, no CLI command, no worker, no queue consumer.
- Any new architecture-checker package or dependency rule beyond what M030 already established, unless design discovers a genuine gap.
- Any market-data, vendor, trading-strategy, order-execution, or brokerage-integration behavior.
- Any change to MILESTONE-020 through MILESTONE-031 frozen contracts, source files, or governance documents.
- Any MILESTONE-033 work of any kind.

---

## 15. Non-Goals

- This milestone is not a general-purpose "Campaign update" capability; it exercises exactly one existing lifecycle-transition method, not a generic setter or arbitrary field-update mechanism.
- This milestone is not the retry-policy milestone that M030 deferred; it is the prerequisite that unblocks that future milestone.
- This milestone does not attempt to justify or introduce a composition root; direct test-only binding remains the pattern until repeated evidence (now three handlers, still one aggregate) is judged sufficient by a future milestone.

---

## 16. Dependencies

**Depends on (frozen, read-only):**

- MILESTONE-020 `CampaignRepository` Protocol (`save()` method) and `Campaign` aggregate (its lifecycle-transition methods).
- MILESTONE-023 concrete PostgreSQL Campaign repository adapter's `save()` implementation.
- MILESTONE-025 repository runtime composition.
- MILESTONE-027 `CommandHandler` Protocol.
- MILESTONE-029 `CommandEntryPoint`.
- MILESTONE-030's already-delivered `add()`-based write-side vertical slice, whose own tests already demonstrate the exact PostgreSQL fixture pattern this milestone's integration tests will reuse, and which this milestone will use to create the precondition Campaign to transition.

**Does not depend on:** any `Run`/`EvidencePackage`/`Review` material, any transport or entrypoint code, any composition-root abstraction, any retry-policy work.

---

## 17. Frozen Contracts Preserved

The following must remain exactly as frozen, unmodified, throughout this milestone's design and implementation:

- `Campaign` aggregate and its lifecycle-transition methods, including their existing allowed-state preconditions (MILESTONE-020).
- `CampaignRepository` Protocol, including its existing `save()` method signature (MILESTONE-020).
- The concrete PostgreSQL Campaign repository adapter, including its existing `save()`/`OptimisticConcurrencyConflict` behavior (MILESTONE-023).
- `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol (MILESTONE-027).
- `CommandEntryPoint[CommandT, ResultT]` (MILESTONE-029).
- Everything MILESTONE-030 and MILESTONE-031 delivered: their concrete command/query, their concrete handlers, `CampaignSnapshot`, and the `usecases` package's architecture-checker rules.

---

## 18. Open Design Questions

- Which specific `Campaign` lifecycle-transition method this milestone targets (e.g. `revise_scope_statement`, `prepare_for_authorization`, `activate`, or another) — not resolved by this scope.
- How the handler obtains a valid `expected_persisted_version` for the `save()` call — whether by loading the aggregate via `get()` inside the same handler, or by some other frozen-contract-compatible means.
- The exact command type's name, shape, and fields.
- The exact handler type's name and shape.
- Whether `OptimisticConcurrencyConflict` propagates transparently (expected, mirroring M030/M031's transparent-propagation precedent) or requires any milestone-specific consideration given it is a genuinely new failure mode for the application layer.
- Whether any architecture-checker change is needed (expected to be none, since the command lives alongside the already-authorized `usecases` package, but this is a design-phase determination).

---

## 19. Acceptance Boundaries

MILESTONE-032 scope selection is complete and ready for independent review when:

- Exactly one write-side capability is proposed (one lifecycle transition for one aggregate), matching the same narrowness discipline M030/M031 established.
- No class name, method signature, module path, package structure, dependency-injection mechanism, registry, transaction behavior, error hierarchy, retry policy, or other design/implementation decision is fixed by this document.
- Every excluded capability is explicit, and every excluded capability's reason traces to either a genuine unmet prerequisite or a deliberate narrowness choice consistent with M030/M031's own precedent.
- The scope is independently reviewable without requiring the reviewer to first resolve any open design question themselves.

---

## 20. Stop Conditions

This milestone stops at:

- One concrete command, one concrete handler, using one existing lifecycle-transition method.
- Proof that `save()` and `OptimisticConcurrencyConflict` compose correctly through the application boundary.
- Contract, unit, architecture, and PostgreSQL integration test evidence, mirroring M030/M031's established patterns.

It does not continue into retry policy, a second transition, a second aggregate, transport, or composition-root work, regardless of how natural such an extension might appear during design or implementation.

---

## 21. Prohibited Expansion

- No retry, backoff, or idempotency-key mechanism.
- No generic "update Campaign" capability beyond the one targeted transition.
- No composition root, registry, dispatcher, mediator, or service locator.
- No transport layer of any kind.
- No `Run`/`EvidencePackage`/`Review` command or query.
- No MILESTONE-033 work.

---

## 22. Deferred Work

- Retry-on-`OptimisticConcurrencyConflict` policy (now unblocked by this milestone's own completion, but not itself in scope).
- Any additional Campaign lifecycle-transition command beyond the one selected during design.
- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any composition-root abstraction beyond direct binding, pending evidence of genuine repeated-handler need (now three Campaign-only handlers; still not yet judged sufficient).
- Any transport/entrypoint adapter.
- MILESTONE-033 and beyond.

---

## 23. Risks

- **Transition-selection ambiguity:** `Campaign` has 8 candidate methods; choosing one that is either too trivial (undermining the "real" nature of the proof) or too complex (requiring unresolved precondition state) is a genuine open design question this scope does not resolve. Mitigation: this scope explicitly identifies the question for the design phase (Section 18) rather than silently choosing an answer.
- **Read-then-write ambiguity:** unlike M030 (pure write) and M031 (pure read), this milestone's handler most likely needs to both load and save an aggregate, which is a pattern neither predecessor exercised. Mitigation: explicitly flagged as an open design question (Section 18); the design phase must independently derive this, not merely assume symmetry with M030 or M031.
- **Symmetry pressure:** risk of copying M030's/M031's dependency-injection and error-propagation choices without independently re-justifying them for a `save()`-based operation, where the failure modes (optimistic concurrency) differ from both `add()`'s duplicate-identity failure and `get()`'s not-found failure. Mitigation: design must re-derive these decisions for the update side, not merely restate prior reasoning.
- **Scope-creep pressure toward retry policy:** a milestone that finally exercises `OptimisticConcurrencyConflict` invites "just add retry logic too" expansion. Mitigation: explicitly excluded above (Sections 14, 21); any such addition requires its own scope-change authorization.

---

## 24. Independent Review Criteria

A hostile independent scope review should verify:

- The verified gap (Section 5) is genuinely unsolved and genuinely evidenced by direct repository inspection, not asserted.
- Every rejected candidate (Section 8) has a specific, evidence-based rejection reason, not a generic dismissal.
- No class name, method signature, module path, or other implementation/design decision is prematurely fixed anywhere in this document.
- Every frozen M020-M031 contract this scope depends on is accurately described and unmodified.
- The scope is narrow enough to be independently designable, testable, reviewable, and freezable as a single milestone.

---

## 25. Owner Decision Status

**CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW.** Not approved. Not frozen. Does not authorize design or implementation.

---

## 26. Next Permitted Action

**MILESTONE-032 INDEPENDENT SCOPE REVIEW.**
