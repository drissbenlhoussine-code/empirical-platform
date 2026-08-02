# MILESTONE-034 - Concrete Application Query Vertical Slice (Run Retrieval) Scope

## 1. Document Status

**Status: CANDIDATE_FOR_FINAL_INDEPENDENT_SCOPE_RE_REVIEW**

This document is a scope candidate. It has not been reviewed, approved, or frozen. It does not authorize design or implementation.

**Correction history:** An independent hostile scope review (finding `M034-SCOPE-REVIEW-0001`, MAJOR/BLOCKING) found that Sections 9 and 13, and equivalent wording elsewhere, prematurely committed the result of the retrieval handler to a "read value" / "immutable, milestone-local read value" shape. That is a design decision and must not be frozen at scope selection. This correction removed every such commitment and replaced it with neutral language: the handler returns one retrieval result, and the exact result type/representation is resolved during the Design Mission (Section 18), without expanding the capability into listing, filtering, pagination, joins, projections, transport serialization, or a generic read-model framework. The selected capability itself (one Run-retrieval query vertical slice) is unchanged.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at scope selection | `496c690d60c86fd187e1c71d4e7bf004090bf7bd` |

---

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Concrete Application Command Vertical Slice — Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Concrete Application Command Vertical Slice — Run Creation) | APPROVED_AND_FROZEN (scope, design, implementation — implementation freeze commit `38ed45518d8a2068d29e7375c2c09ea2af80963c`) |

All prior milestones remain untouched by this scope-selection mission.

---

## 4. Architectural Inventory Summary

Rebuilt entirely from source in this mission, not reused from any prior milestone's text:

| # | Capability | Classification | Evidence |
| --- | --- | --- | --- |
| 1 | Domain aggregates | IMPLEMENTED_AND_FROZEN | `Campaign`, `Run`, `EvidencePackage`, `Review` — all frozen since M020, verified directly by listing `src/empirical_platform/{campaign,run,evidence,review}/*.py` |
| 2 | Repository Protocols | IMPLEMENTED_AND_FROZEN | `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` — identical `get`/`add`/`save` shape (M020) |
| 3 | PostgreSQL repository adapters | IMPLEMENTED_AND_FROZEN | All four concrete adapters exist under `shared/persistence/postgres_repositories/` (M023) |
| 4 | Concrete use cases | IMPLEMENTED_AND_FROZEN (four modules) | `CreateCampaignHandler` (M030, `add()`), `GetCampaignHandler` (M031, `get()`), `PrepareCampaignForAuthorizationHandler` (M032, `get()`+`save()`), `CreateRunHandler` (M033, `add()`) — confirmed by direct listing of `src/empirical_platform/usecases/*.py` |
| 5 | Exact repository-method exercise, per aggregate | Verified by direct grep of every `usecases/*.py` file for `_repository.` call sites | **Campaign:** `add()` ✓ (M030), `get()` ✓ (M031), `save()` ✓ (M032) — all three methods proven. **Run:** `add()` ✓ (M033) only — `get()` and `save()` unproven. **EvidencePackage:** zero methods proven. **Review:** zero methods proven. |
| 6 | `CommandHandler`/`CommandEntryPoint` generalization | PROVEN for a second aggregate | M033 proved a concrete `CommandHandler` (`CreateRunHandler`) and `CommandEntryPoint` binding work correctly for `Run`, not just `Campaign` — via the simplest write operation, `add()`. No `save()`/`OptimisticConcurrencyConflict` generalization was exercised (M033's `add()` has no version-guard concern). |
| 7 | `QueryHandler`/`QueryEntryPoint` generalization | **NOT PROVEN for any aggregate beyond Campaign** | Verified directly: `GetCampaignHandler` (M031) is the only concrete `QueryHandler` implementation anywhere in the codebase (confirmed by listing `usecases/*.py` — no `get_run.py`, `get_evidence_package.py`, or `get_review.py` module exists). Whether the read-side application pattern (query type, handler shape, snapshot-style return-value discipline, `QueryEntryPoint` binding) generalizes beyond the one aggregate that has ever exercised it is completely unknown. |
| 8 | `usecases` architecture-checker boundary | `ALLOWED["usecases"] = {"shared", "identifiers", "campaign", "run"}` | Verified directly in `tools/check_architecture.py` line 29 — `"run"` was added by M033; a Run-query module needs **zero** further checker change, since `RunRepository`/`Run`/`RunId` are all already reachable under the existing grant |
| 9 | Cross-aggregate dependency graph | Campaign (root) ← `Run` (references `CampaignId`) ← `EvidencePackage` (references `RunId`) ← `Review` (references `EvidencePackageId`) | Re-verified fresh via direct import inspection of each aggregate's constructor dependencies in this mission — unchanged since M033's own analysis |
| 10 | `EvidencePackage` constructor complexity | `EvidencePackage.__init__(identity: DomainIdentity[EvidencePackageId], run_id: RunId)` | Minimal, but references `RunId` — an EvidencePackage-creation milestone would depend on a real, persisted `Run` (now possible after M033, but this would be the *third* aggregate to receive the already-twice-proven `add()` treatment, not a new architectural proof) |
| 11 | `Review` constructor complexity | `Review.__init__(*, identity, target: ReviewTargetReference, reviewer: ReviewerReference)` | `ReviewTargetReference` wraps an `EvidencePackageId` — Review creation depends on an EvidencePackage existing, which itself does not yet exist at the application layer; two dependency hops away from ready |
| 12 | Composition-root readiness | Unchanged, still unmet | Four concrete handlers now exist (`CreateCampaignHandler`, `GetCampaignHandler`, `PrepareCampaignForAuthorizationHandler`, `CreateRunHandler`), all still bound via an identical trivial direct-construction test pattern — no genuine repeated-handler-need evidence has emerged across four consecutive milestones |
| 13 | Retry-on-conflict policy readiness | Unchanged, still unmet | Exactly one concrete conflict-producing command exists anywhere (`PrepareCampaignForAuthorizationHandler`, M032); generalizing a retry policy from a single data point remains premature |
| 14 | Transport/entrypoint behavior | Unchanged | `entrypoints/health.py`, `entrypoints/version.py` remain static stdout scripts |
| 15 | Stub packages | Unchanged, all still single-file docstring-only | Freshly re-verified in this mission: `acquisition/`, `archive/`, `audit/`, `decision_candidate/`, `governance/`, `normalization/`, `registry/`, `validation/` each contain exactly one `__init__.py` with a one-line docstring and zero implementation |
| 16 | `PROJECT_CHECKPOINT.md` deferred capabilities | — | Verified directly (Section 9, current text): lists "any Run lifecycle-transition command **or Run query**" together with equal weight, deferred by M033's own scope — no breadcrumb favors one over the other; this scope selection rests on independent comparative analysis, not an explicit pointer |
| 17 | TODO/FIXME source markers | None found | A repository-wide grep for `TODO`/`FIXME`/`XXX` across `src/` returned zero matches — no hidden signal exists in the source itself |
| 18 | Frozen `RunRepository.get()` contract | `get(identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]`, raises `AggregateNotFound(aggregate_kind="Run", ...)` on a missing identity | Verified directly in `src/empirical_platform/run/repository.py` and the concrete `PostgresRunRepository.get()` implementation — identical shape to `CampaignRepository.get()`, already exercised once for Campaign (M031) |

---

## 5. Verified Gap

Two distinct, unproven "does this frozen application-layer pattern generalize beyond Campaign" questions remain open:

1. **Does `CommandHandler`'s harder, version-guarded write path (`save()` + `OptimisticConcurrencyConflict`) generalize to a second aggregate?** Unproven — only Campaign (M032) has exercised it.
2. **Does `QueryHandler`/`QueryEntryPoint` (the entire read side of the application boundary) generalize to *any* second aggregate at all?** Unproven — `GetCampaignHandler` (M031) is the only concrete query handler that has ever existed in this codebase; no read-side capability has been implemented for `Run`, `EvidencePackage`, or `Review`.

Both are genuine gaps. This scope selection's central finding is that gap (2) is more architecturally fundamental than gap (1): M033 already demonstrated that `CommandHandler`/`CommandEntryPoint` generalizes to a second aggregate (via the simplest possible write operation, `add()`) — establishing that the *write-side* boundary is not accidentally coupled to `Campaign`. No equivalent proof exists for the *read-side* boundary at all. Closing gap (2) first — using the identical minimal-first discipline this project has followed since M030 (prove the simplest operation before the harder one) — is the narrower, lower-risk, and more foundational next step, and it directly completes the same create→read progression for `Run` that M030→M031 already established for `Campaign`.

A third possible gap — a third aggregate (`EvidencePackage`) receiving the already-twice-proven `add()` treatment — is evidence-supported but architecturally weaker: it would not answer any currently-open generalization question, since `add()`-based creation across two different aggregates (Campaign, Run) has already established that the write-creation pattern is not aggregate-specific.

---

## 6. Candidate Inventory

**Candidate A — `Run` retrieval (`get()`-based), first Run query.**
- Architectural problem solved: proves the `QueryHandler`/`QueryEntryPoint` pattern and its architecture-checker boundary genuinely generalize beyond the one aggregate (`Campaign`) that has ever exercised it — the single largest unproven-generalization gap in the current inventory.
- Why it follows M033 directly: mirrors the exact M030→M031 sequencing (Campaign creation → Campaign retrieval) for `Run`; `Run`'s own application-layer proof is otherwise incomplete after M033 proved only `add()`.
- Dependencies: `Run` aggregate (frozen), `RunRepository.get()` (frozen), `QueryHandler`/`QueryEntryPoint` (frozen, M028/M029), `usecases` package with `"run"` already in `ALLOWED["usecases"]` (M033) — **zero new architecture-checker change required**, an even narrower footprint than M033 itself.
- Repository evidence: `RunRepository.get()` has the identical shape to `CampaignRepository.get()`, already exercised once for Campaign; `AggregateNotFound` behavior is already frozen and proven (M023).
- Probable future implementation surface: one query type, one handler, in `usecases/`, mirroring M031's exact shape for a different aggregate.
- Explicit inclusions: one retrieval query; `get()` call; transparent `AggregateNotFound` propagation; one retrieval result (exact result type and representation left to the Design Mission).
- Explicit exclusions: any Run mutation; any other aggregate; any transport; any composition root.
- Risks: none requiring a new architecture-checker decision — genuinely the narrowest possible next step.
- Prerequisite gaps: none — every dependency is already frozen and ready.
- Scope size: narrow, single capability, matches M030-M033's own discipline exactly.
- Testability: high — the exact M031 test pattern (unit, contract, architecture, PostgreSQL integration) transfers directly, seeding a Run via M033's own frozen `CreateRunHandler`.
- Genuine vertical progression: yes — the first proof that the frozen read-side pattern is not accidentally coupled to `Campaign` specifically.

**Candidate B — `Run` lifecycle-transition command (e.g. `authorize()`), mirroring M032 for Run.**
- Architectural problem solved: would prove `save()`/`OptimisticConcurrencyConflict` generalizes to a second aggregate.
- Why it is not selected now: a harder, higher-complexity generalization question than the read side; requires its own systematic mutation-candidate analysis (`Run` has seven lifecycle-transition methods: `authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`) mirroring M032's own 8-candidate Campaign analysis; sequencing-wise, this project has consistently proven the simpler operation before the harder one for a given aggregate (M030 `add()` before M032 `save()` for Campaign) — the same discipline favors proving `Run` `get()` before `Run` `save()`.
- Rejected at Phase 8 below (dominated by Candidate A on sequencing correctness and implementation complexity, not on architectural necessity — both remain valid future candidates).

**Candidate C — `EvidencePackage` creation (`add()`-based), third aggregate to receive the creation treatment.**
- Architectural problem solved: would extend `add()`-based creation to a third aggregate.
- Why it is not selected now: `add()`-based creation across two different aggregates (Campaign, M030; Run, M033) has already established that the write-creation pattern generalizes — proving it a third time answers no currently-open architectural question. Dependency-wise it is ready (Run now exists to reference), but its architectural leverage is the lowest of the serious candidates.
- Rejected at Phase 8 below (dominated by Candidate A on architectural leverage).

**Candidate D — `Review` creation.**
- Architectural problem solved: same category as Candidate C, one dependency hop further away.
- Why it is not selected now: depends on an `EvidencePackage` existing at the application layer, which does not yet exist; even less ready than Candidate C.
- Rejected at Phase 8 below (dominated by Candidate A on dependency readiness).

**Candidate E — Retry-on-`OptimisticConcurrencyConflict` policy.**
- Rejected — unchanged reasoning from M032/M033: exactly one concrete conflict-producing command exists; generalizing from a single data point remains premature.

**Candidate F — Composition-root wiring.**
- Rejected — unchanged reasoning: four handlers, one still-trivial, unchanging test-only binding pattern; the repeated-handler-need evidence bar remains unmet.

**Candidate G — Transport/API layer.**
- Rejected — silently depends on the already-rejected composition-root candidate.

**Candidate H — Audit/registry/governance/decision_candidate/archive/acquisition/normalization/validation work.**
- Rejected — each remains an empty single-file stub requiring an entire new foundational milestone chain before any command/query work is possible.

---

## 7. Candidate Comparison

| Criterion | A (Run retrieval) | B (Run lifecycle transition) | C (EvidencePackage creation) | D (Review creation) | E (retry policy) | F (composition root) | G (transport) | H (audit/registry/etc.) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Architectural necessity | High — closes the largest unproven-generalization gap (read side, any aggregate) | Medium-high — closes a real gap, but a harder one | Low — repeats an already-twice-proven pattern | Low — same as C, less ready | Low — insufficient evidence | Not yet evidenced | Depends on rejected F | Very low — foundational work not started |
| Dependency readiness | Perfect — zero new checker change, all dependencies frozen | Ready, but requires its own mutation-candidate analysis | Ready (Run now exists) | Not ready — EvidencePackage doesn't exist at application layer | Blocked on more conflict evidence | Evidence threshold unmet | Blocked on F | Blocked on new foundational work |
| Leverage / future-unlock value | High — proves the read-side pattern for any future aggregate | High, but for the write side, already partially proven via M033 | Medium | Medium, but blocked | Depends on B/others existing first | Medium, premature | Low, premature | Low near-term |
| Sequencing correctness | Perfect — mirrors M030→M031's exact create→read order for a second aggregate | Skips ahead of the read side for the same aggregate | Correctly sequenced after A conceptually, but unnecessary given C's low leverage | Must follow C | Must follow more evidence | No clear predecessor met | Must follow F | Must follow new foundation |
| Risk | Lowest — narrowest possible next step, no new checker decision | Medium — requires selecting among 7 transition methods | Low-medium | Low-medium | High — premature generalization | Medium | High | High |
| Implementation complexity | Low — near-identical to M031's own shape | Medium-high — near-identical to M032's own multi-candidate analysis | Low | Low | Medium-high | Medium | High | High |
| Precedent consistency | Perfect — completes the identical create→read progression M030→M031 established | Diverges from that ordering (would be create→update, skipping read) | Repeats create for a new subject rather than progressing the same subject | Same as C | N/A | N/A | N/A | N/A |

**Rank:** A > B > C > D > E > F > G > H.

**Selected: Candidate A.**

---

## 8. Rejected Candidates

- **B (Run lifecycle transition):** rejected as the *primary* selection — while a real, legitimate future gap, it is a harder generalization question than the read side, requires its own systematic multi-candidate mutation analysis, and diverges from this project's established create→read→update sequencing discipline for a single aggregate. Remains a strong candidate for a future milestone once Run's read side is proven.
- **C (EvidencePackage creation):** rejected — `add()`-based creation has already been proven to generalize across two aggregates (Campaign, Run); a third instance answers no open architectural question, only extends coverage.
- **D (Review creation):** rejected — depends on EvidencePackage existing at the application layer, which it does not; two dependency hops from ready.
- **E (retry policy):** rejected — unchanged reasoning from M032/M033, still only one concrete conflict-producing command exists.
- **F (composition root):** rejected — unchanged reasoning, repeated-handler-need bar still unmet after four consecutive milestones of trivial test-only bindings.
- **G (transport):** rejected — depends on the rejected composition-root candidate.
- **H (audit/registry/governance/decision_candidate/archive/acquisition/normalization/validation):** rejected — each is an empty stub requiring an entire new foundational milestone chain.

---

## 9. Selected Scope

**Concrete Application Query Vertical Slice: Run Retrieval.**

A single read-side (query) operation — retrieving an existing `Run` by its full frozen identity — implemented as one concrete query and one concrete handler conforming to the frozen MILESTONE-028 `QueryHandler` Protocol, invoked through the frozen MILESTONE-029 `QueryEntryPoint`, reading via the frozen MILESTONE-023 concrete `Run` repository adapter's `get()` method — the first time any application-layer code has exercised the read side of the frozen CQRS boundary for any aggregate other than `Campaign`.

The handler returns exactly one retrieval result. This scope does not select the result's exact type or representation — whether a raw `Run`, a `LoadedAggregate[Run]`, an existing frozen type, a new narrow milestone-local type, or another justified shape — that decision belongs entirely to the Design Mission (see Section 18).

---

## 10. Mission Statement

Prove, with one concrete, minimal, real query, that the frozen `usecases` read-side application-invocation pattern — established and validated exclusively against `Campaign` via `GetCampaignHandler` (M031) — genuinely generalizes to a second aggregate, without introducing any Run mutation capability, without introducing a third aggregate, and without introducing any framework, registry, or abstraction beyond what is already frozen.

---

## 11. Architectural Problem

`GetCampaignHandler` (M031) is the only concrete `QueryHandler` implementation that has ever existed in this codebase. Whether the established query/handler/entry-point pattern, the read-value-extraction discipline (`CampaignSnapshot`'s deliberate exclusion of write-side metadata), and the architecture-checker rule shape that governs it genuinely generalize — or whether they have an undiscovered, accidental coupling to `Campaign` specifically — remains completely unverified for any other aggregate. `Run`, `EvidencePackage`, and `Review` each already have a fully frozen, `Campaign`-parallel repository Protocol and concrete PostgreSQL adapter `get()` method with zero read-side application-layer proof of any kind.

---

## 12. Why M034 Is Next

- It closes the single largest unproven-generalization gap this repository's own architectural inventory reveals: the entire read side of the CQRS application boundary has never been exercised for any aggregate but `Campaign`.
- `Run` already has a proven write-side vertical slice (M033); completing its read side directly mirrors the identical create→read sequencing this project used for `Campaign` (M030→M031), rather than skipping ahead to a harder write-side generalization (Run lifecycle transition) or repeating an already-proven creation pattern for a third aggregate (EvidencePackage).
- Every dependency it needs (`Run` aggregate, `RunRepository.get()`, `QueryHandler`, `QueryEntryPoint`, the `usecases` package with `"run"` already granted) is already frozen and ready — this is the narrowest possible next step, requiring **zero** new architecture-checker decision, an even smaller footprint than M033 itself needed.
- It preserves the exact single-aggregate-per-milestone, single-capability, test-only-binding discipline M030-M033 all established.

---

## 13. In-Scope Capability

- One concrete query representing "retrieve an existing Run by its full identity," carrying the minimal data the frozen repository's `get()` method already requires.
- One concrete handler conforming to the frozen `QueryHandler` Protocol that calls the frozen repository's `get()` method and returns one retrieval result. The exact result type and representation are not selected by this scope; that decision belongs to the Design Mission (see Section 18).
- Binding this handler to a `QueryEntryPoint` and invoking it, proving the frozen read-side boundary's contract holds for a second aggregate.
- Contract tests proving the concrete handler conforms to the frozen `QueryHandler` Protocol.
- Integration tests proving the golden path (retrieval of a Run created via the frozen M033 slice) and the already-frozen `AggregateNotFound` failure path both work end-to-end against real PostgreSQL.
- Identification (not resolution) of the design questions a `Run`-specific query handler raises that M031's `Campaign`-specific design did not need to independently re-answer (in particular: the exact result type/shape and which fields or data it carries, and whether it excludes write-side metadata — none of which is assumed to mirror `CampaignSnapshot`).

---

## 14. Out-of-Scope Capabilities

- Any Run lifecycle-transition command (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`).
- Any Run mutation of any kind.
- Any additional Campaign command or query beyond M030-M032.
- Any command or query for `EvidencePackage` or `Review`.
- Any listing/filtering/pagination/searching (retrieval-by-identity only, mirroring M031).
- Any Campaign join, cross-aggregate enrichment, projection framework, generic read-model infrastructure, or transport serialization contract — the open result-contract question (Section 18) must be resolved within the single-Run-by-identity capability boundary, not used to expand it.
- Any composition-root abstraction, handler registry, service locator, or dependency-injection framework — direct construction only.
- Any transport layer: no HTTP endpoint, no CLI command, no worker, no queue consumer.
- Any retry, idempotency, or optimistic-concurrency-conflict handling.
- Any market-data, vendor, trading-strategy, order-execution, or brokerage-integration behavior.
- Any change to MILESTONE-020 through MILESTONE-033 frozen contracts, source files, or governance documents.
- Any MILESTONE-035 work of any kind.

---

## 15. Non-Goals

- This milestone is not a general-purpose "Run management" read capability; it exercises exactly one operation (`get()`-based retrieval-by-identity), not a generic query framework.
- This milestone is not the Run-lifecycle-transition milestone; it does not attempt to prove `save()`/`OptimisticConcurrencyConflict` generalization.
- This milestone does not decide whether Run lifecycle transition or EvidencePackage/Review work comes next — that determination belongs to a future, independently-scoped milestone once Run's own read-side vertical slice exists as precedent.

---

## 16. Dependencies

**Depends on (frozen, read-only):**

- MILESTONE-020 `RunRepository` Protocol (`get()` method) and `Run` aggregate.
- MILESTONE-023 concrete PostgreSQL `Run` repository adapter's `get()` implementation.
- MILESTONE-025 repository runtime composition.
- MILESTONE-028 `QueryHandler` Protocol.
- MILESTONE-029 `QueryEntryPoint`.
- MILESTONE-031's already-delivered `Campaign` retrieval vertical slice, whose exact pattern (query/handler shape, return-value discipline, test strategy) this milestone directly mirrors for a second aggregate.
- MILESTONE-033's already-delivered `Run` creation vertical slice, which this milestone's own PostgreSQL evidence will use to seed a real Run for retrieval.

**Does not depend on:** any `EvidencePackage`/`Review` material, any Run mutation work, any transport or entrypoint code, any composition-root abstraction.

---

## 17. Frozen Contracts Preserved

The following must remain exactly as frozen, unmodified, throughout this milestone's design and implementation:

- `Run` aggregate and its constructor (MILESTONE-020).
- `RunRepository` Protocol, including its existing `get()` method signature (MILESTONE-020).
- The concrete PostgreSQL `Run` repository adapter (MILESTONE-023).
- `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol (MILESTONE-028).
- `QueryEntryPoint[QueryT, QueryResultT]` (MILESTONE-029).
- Everything MILESTONE-030 through MILESTONE-033 delivered: their concrete commands/queries, their concrete handlers, `CampaignSnapshot`, and the `usecases` package's existing architecture-checker rules (including `"run"`, already granted).

---

## 18. Open Design Questions (Explicitly Not Resolved by This Scope)

- The exact query type's name, shape, and fields.
- The exact handler type's name and shape.
- The exact result contract: its type, name, and representation — including whether it is a raw `Run`, a `LoadedAggregate[Run]`, an existing frozen type, a new narrow milestone-local type, or another justified shape — and, once that shape is chosen, which fields or data it carries. Nothing here is selected or preferred by this scope.
- Whether `persisted_version` or any other write-side metadata is included or excluded in the result, and why — an independent Design Mission determination, not assumed from M031's `CampaignSnapshot` precedent.
- Whether the query is looked up by full `DomainIdentity[RunId]` (mirroring `GetCampaignQuery`) or some other identity shape.
- The exact `QueryEntryPoint` binding pattern (expected: identical test-only direct construction, mirroring M031).

---

## 19. Acceptance Boundaries

MILESTONE-034 scope selection is complete and ready for independent review when:

- Exactly one read-side capability is proposed (Run retrieval by identity), matching the same narrowness discipline M030-M033 established.
- No class name, method signature, module path, package structure, dependency-injection mechanism, registry, transaction behavior, error hierarchy, or other design/implementation decision is fixed by this document.
- Every excluded capability is explicit, and every excluded capability's reason traces to either a genuine unmet prerequisite or a deliberate narrowness choice consistent with M030-M033's own precedent.
- The scope is independently reviewable without requiring the reviewer to first resolve any open design question themselves.

---

## 20. Stop Conditions

This milestone stops at:

- One concrete query, one concrete handler, using `RunRepository.get()` only.
- Proof that the `usecases`/`QueryHandler`/`QueryEntryPoint` pattern composes correctly for a second aggregate.
- Contract, unit, architecture, and PostgreSQL integration test evidence, mirroring M031's established patterns.

It does not continue into any Run mutation, any Run lifecycle transition, any second aggregate beyond Run, composition-root work, or transport work, regardless of how natural such an extension might appear during design or implementation.

---

## 21. Prohibited Expansion

- No Run mutation or lifecycle-transition command.
- No `EvidencePackage`/`Review` command or query.
- No composition root, registry, dispatcher, mediator, or service locator.
- No transport layer of any kind.
- No listing/filtering/pagination.
- No MILESTONE-035 work.

---

## 22. Deferred Work

- Run lifecycle-transition command (mirroring M032's role, for a future milestone).
- `EvidencePackage` creation (a future milestone once its architectural leverage is reassessed against whatever remains unproven at that time).
- `Review` creation (blocked behind EvidencePackage).
- Retry-on-`OptimisticConcurrencyConflict` policy — the evidence base remains one concrete conflict-producing command.
- Any composition-root abstraction beyond direct binding.
- Any transport/entrypoint adapter.
- MILESTONE-035 and beyond.

---

## 23. Risks

- **Second-generalization-question risk:** the read-side pattern may reveal an accidental `Campaign`-specific assumption when applied to `Run` for the first time, exactly as the write-side risk M033 existed to surface. Mitigation: this is precisely the risk this milestone exists to test — a genuine architectural proof point.
- **Return-shape symmetry pressure:** risk of the Design Mission defaulting to `CampaignSnapshot`'s exact shape and field-exclusion reasoning for Run's result contract without independently evaluating the available options on their own merits. Mitigation: the Design Mission must independently evaluate and justify Run's result contract — including its type category and fields — not merely restate M031's reasoning.
- **Scope-creep pressure toward Run mutation:** having proven Run creation and retrieval invites "just add the lifecycle transition too." Mitigation: explicitly excluded above (Sections 14, 21-22); any such addition requires its own scope-change authorization.
- **Symmetry-driven premature EvidencePackage expansion:** proving Run's full read+write CRUD-lite surface might tempt an immediate jump to EvidencePackage. Mitigation: explicitly deferred (Section 22); the next milestone after this one requires its own independent scope selection.

---

## 24. Independent Review Criteria

A hostile independent scope review should verify:

- The verified gap (Section 5) is genuinely unsolved and genuinely evidenced by direct repository inspection, not asserted.
- The comparative reasoning favoring read-side generalization (Candidate A) over write-side generalization (Candidate B) and over a third `add()`-based aggregate (Candidate C) is independently defensible.
- Every rejected candidate (Section 8) has a specific, evidence-based rejection reason, not a generic dismissal.
- No class name, method signature, module path, or other implementation/design decision is prematurely fixed anywhere in this document.
- Every frozen M020-M033 contract this scope depends on is accurately described and unmodified.
- The scope is narrow enough to be independently designable, testable, reviewable, and freezable as a single milestone.

---

## 25. Owner Decision Status

**CANDIDATE_FOR_FINAL_INDEPENDENT_SCOPE_RE_REVIEW.** Not approved. Not frozen. Does not authorize design or implementation. Owner Scope Freeze is not authorized until the final independent re-review decision.

---

## 26. Next Permitted Action

**MILESTONE-034 FINAL INDEPENDENT SCOPE RE-REVIEW.**
