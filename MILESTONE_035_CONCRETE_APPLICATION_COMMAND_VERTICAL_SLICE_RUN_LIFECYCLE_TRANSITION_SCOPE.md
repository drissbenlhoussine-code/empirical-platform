# MILESTONE-035 - Concrete Application Command Vertical Slice (Run Lifecycle Transition) Scope

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW**

This document is a scope candidate. It has not been reviewed, approved, or frozen. It does not authorize design or implementation.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at scope selection | `56c103fe75946bfcbf13194e9dc95c4fc347c28b` |

---

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Concrete Application Command Vertical Slice — Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Concrete Application Command Vertical Slice — Run Creation) | APPROVED_AND_FROZEN |
| M034 (Concrete Application Query Vertical Slice — Run Retrieval) | APPROVED_AND_FROZEN (implementation freeze `3056e3010b4f20f3cf7bf2ab2e3fbbc43fcff825`) |

---

## 4. Fresh Architecture Inventory

Rebuilt directly from live source, tests, migrations, and `tools/check_architecture.py` — not reused from prior milestone tables.

| Package/capability | Classification | Evidence |
| --- | --- | --- |
| `campaign/` (aggregate, repository Protocol) | IMPLEMENTED_AND_FROZEN | `campaign/aggregate.py`, `campaign/repository.py` |
| `run/` (aggregate, repository Protocol) | IMPLEMENTED_AND_FROZEN | `run/aggregate.py`, `run/repository.py` |
| `evidence/` (`EvidencePackage` aggregate, repository Protocol) | INFRASTRUCTURE_ONLY | `evidence/package.py`, `evidence/repository.py` — full domain aggregate and Protocol exist; zero application-layer usecase references it anywhere |
| `review/` (`Review` aggregate, repository Protocol) | INFRASTRUCTURE_ONLY | `review/aggregate.py`, `review/repository.py` — same as above |
| `identifiers/` | IMPLEMENTED_AND_FROZEN | value objects for all five identifier kinds |
| `shared/domain/` | IMPLEMENTED_AND_FROZEN | `AggregateVersion`, `TransitionSequence`, `StateTransitionRecord`, `ReconstructionError` |
| `shared/contracts/` (`CommandHandler`, `QueryHandler`, repository contracts) | IMPLEMENTED_AND_FROZEN | `shared/contracts/command.py`, `query.py`, `repository.py` |
| `shared/persistence/postgres_repositories/` | IMPLEMENTED_AND_FROZEN, all four aggregates | `campaign_repository.py`, `run_repository.py`, `evidence_package_repository.py`, `review_repository.py` all exist as concrete adapters |
| `usecases/` | PARTIALLY_IMPLEMENTED | exactly five modules: `create_campaign.py` (M030), `get_campaign.py` (M031), `prepare_campaign_for_authorization.py` (M032), `create_run.py` (M033), `get_run.py` (M034) — verified by direct directory listing; zero reference to `evidence` or `review` packages anywhere in `usecases/` |
| `application/` (`CommandEntryPoint`, `QueryEntryPoint`) | IMPLEMENTED_AND_FROZEN | `application/command.py`, `application/query.py` |
| `entrypoints/` | INFRASTRUCTURE_ONLY | `health.py`, `version.py` only — no transport, no usecase-facing HTTP/CLI layer |
| `governance/`, `registry/`, `audit/`, `decision_candidate/`, `archive/` | EMPTY_STUB | each contains only `__init__.py`, verified by direct directory listing |
| `acquisition/`, `normalization/`, `validation/` | EMPTY_STUB | each contains only `__init__.py` |
| `migrations/` | IMPLEMENTED_AND_FROZEN | single migration `5b58cdd7751b_create_m022_postgresql_schema.py` creates all tables for all four aggregates, including `run_manifest`, `run_transition`, `evidence_package_criterion_result`, `evidence_package_artifact_reference`, `evidence_package_transition`, `review_finding`, `review_transition` |
| `tools/check_architecture.py` | IMPLEMENTED_AND_FROZEN | `ALLOWED["usecases"] = {"shared", "identifiers", "campaign", "run"}` — verified live; `"evidence"`/`"review"` are **not** granted to `usecases` |

---

## 5. Verified Architectural Gap

An application-capability matrix (Section below) shows a specific, precisely-scoped asymmetry: of the three CQRS verbs this project's `usecases` layer exercises against a repository (`add()`, `get()`, `save()`), two — `add()` and `get()` — have now each been independently proven to generalize across two different aggregates (`Campaign` and `Run`). The third — `save()`, together with its `OptimisticConcurrencyConflict` contract — has been exercised exactly **once**, against `Campaign` only (M032), and has never been tested against any second aggregate. This is independently verified: a repository-wide search finds no reference to `RunRepository.save()`, `EvidencePackageRepository.save()`, or `ReviewRepository.save()` anywhere in `src/empirical_platform/usecases/`.

This is the same class of gap M034 itself closed for `get()` (query generalization, proven once for `Campaign` via M031, unproven for `Run` until M034), and the class of gap M033 closed for `add()` (command generalization, proven once for `Campaign` via M030, unproven for `Run` until M033). The `save()`/`OptimisticConcurrencyConflict` verb is now the last of the three to remain single-aggregate-only, and is therefore the single largest unproven-generalization gap remaining in the application-layer CQRS pattern space.

This reading is also directly supported by already-frozen governance text, not merely inferred: M034's own frozen scope document (checkpoint narrative, Section 25) explicitly named a Run lifecycle-transition command as a real candidate it rejected only for immediate sequencing reasons ("a harder write-side generalization question, and a departure from this project's established create→read→update sequencing discipline for **one aggregate**"). That same document explicitly frames Run's own sequencing as create (M033) → read (M034) → update — mirroring `Campaign`'s own already-completed create (M030) → read (M031) → update (M032) sequence. M035 is the literal next step in that named sequence.

---

## 6. Application-Capability Matrix

| Aggregate | `add()` proven | `get()` proven | `save()`/conflict proven | Duplicate-identity proven | `CommandEntryPoint` compat. | `QueryEntryPoint` compat. | Real PostgreSQL evidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `Campaign` | Yes (M030) | Yes (M031) | Yes (M032) | Yes (M030) | Yes (M030, M032) | Yes (M031) | Yes, all three verbs |
| `Run` | Yes (M033) | Yes (M034) | **No** | Yes (M033) | Yes (M033) | Yes (M034) | Yes, for `add()`/`get()` only |
| `EvidencePackage` | No | No | No | No | No | No | No — infrastructure-only |
| `Review` | No | No | No | No | No | No | No — infrastructure-only |

**Asymmetries identified:**
- `Run.save()`/`OptimisticConcurrencyConflict` is the only cell in the `Campaign`/`Run` block that remains unproven — a single, precise, closeable gap.
- `EvidencePackage` and `Review` have zero application-layer proof of any verb — a missing capability, not an asymmetry within an already-started aggregate. Distinguished explicitly from the `Run` gap: extending to a third/fourth aggregate for an already-twice-proven verb (`add()` or `get()`) would repeat a proven pattern; proving `save()` on a second aggregate closes a genuinely open question.
- A repeated pattern whose architectural value is already proven: a third `add()`-based creation command (`EvidencePackage`) or a third `get()`-based retrieval query (`EvidencePackage`) — neither would answer any currently-open architectural question, since the `CommandHandler`/`CommandEntryPoint` and `QueryHandler`/`QueryEntryPoint` generalization is already independently proven twice each.
- Speculative framework work: retry-on-conflict policy, composition root, transport, registry/dispatcher, and audit/governance foundations all remain premature — see Section 4 gap list below.

---

## 7. Aggregate Dependency Graph

Reconstructed directly from constructor signatures and live migration foreign keys (`migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py`), not inferred from names:

```
Campaign  (no parent)
  ← Run            [Run(identity, campaign_id: CampaignId); run.campaign_id → campaign.governance_id FK]
      ← EvidencePackage  [EvidencePackage(identity, run_id: RunId); evidence_package.run_id → run.governance_id FK]
          ← Review        [Review(identity, target: ReviewTargetReference[EvidencePackageId], reviewer); review.target_evidence_package_id → evidence_package.governance_id FK]
```

For every downstream aggregate:

- **Run:** constructor dependency is `CampaignId` only; parent-existence is persistence-enforced (real FK, verified M033), not application-enforced. Creation requires exactly one repository call.
- **EvidencePackage:** constructor dependency is `RunId` only; parent-existence is persistence-enforced via the real `evidence_package.run_id → run.governance_id` FK (verified directly in the M022 migration, mirroring the exact mechanism M033 already proved for `Run`/`Campaign`). Creation would require exactly one repository call, no cross-aggregate lookup.
- **Review:** constructor dependency is `ReviewTargetReference` (wrapping an `EvidencePackageId`) plus a `ReviewerReference`; parent-existence is persistence-enforced via the real `review.target_evidence_package_id → evidence_package.governance_id` FK (verified directly in the M022 migration). Review creation is therefore gated behind `EvidencePackage` existing, both architecturally and for any real database-backed evidence.
- **Run lifecycle transition** (this milestone's candidate) requires no cross-aggregate dependency at all — it operates entirely within the already-created `Run` aggregate using only `RunRepository.get()`/`save()`, both already frozen (M020/M023) and already proven at the `Campaign` level (M032). It has zero dependency-graph distance from the fully-proven state — strictly less cross-aggregate risk than `EvidencePackage` creation (one FK hop) or `Review` creation (two FK hops).

---

## 8. Remaining Architectural Gaps (Full Inventory)

| # | Gap | Frozen dependencies available | Unresolved prerequisite | Risk | Scope size | Future leverage | Already deferred by governance? | Repeats proven pattern or proves new one? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Run lifecycle-transition command (`RunRepository.save()`) | Yes — fully frozen since M020/M023; `Run` transition methods frozen since M012 | None | Low — identical shape to M032, already-proven mechanism | Small — one command, one handler | Closes the sole remaining unproven CQRS-verb/aggregate cell; establishes the mutation pattern needed before any Run-execution-stage work | Yes — explicitly named and deferred by M034's own frozen text | **Proves a new generalization** (2nd aggregate for `save()`/conflict) |
| 2 | `EvidencePackage` creation (`add()`) | Yes — fully frozen | None technical; architecturally follows Run maturation | Low | Small | Unlocks the `EvidencePackage`/`Review` chain | Yes — deferred by M033/M034 | Repeats an already-twice-proven pattern |
| 3 | `EvidencePackage` retrieval (`get()`) | Yes — fully frozen | Requires #2 to have real data to retrieve for meaningful integration evidence | Low | Small | Read-side proof for `EvidencePackage` | Yes — deferred | Repeats an already-twice-proven pattern |
| 4 | `Review` creation (`add()`) | Yes — fully frozen | Requires #2 (real FK to `evidence_package`) | Low | Small | — | Yes — deferred | Repeats an already-twice-proven pattern |
| 5 | `Review` retrieval (`get()`) | Yes — fully frozen | Requires #4 | Low | Small | — | Yes — deferred | Repeats an already-twice-proven pattern |
| 6 | Retry-on-`OptimisticConcurrencyConflict` policy | Partial — only one save()-based command (`Campaign`) exists | Needs at least two independently-proven save()-based commands to generalize responsibly | Medium — premature abstraction risk | Unknown until evidenced | — | Yes — explicitly excluded by every milestone from M030 onward as premature | Would be new work, but with insufficient evidence base until gap #1 closes |
| 7 | Production composition root | No repeated-handler-need evidence (5 trivial direct-construction handlers, unchanged pattern) | — | Medium — premature framework risk | Unknown | — | Yes — explicitly excluded every milestone | New work, unjustified |
| 8 | Transport-neutral invocation adapter | Depends on #7 | #7 | Medium | Unknown | — | Yes | New work, unjustified |
| 9 | Audit/governance runtime foundation | `governance/`, `audit/`, `registry/` are empty stubs | Requires an entire new foundational milestone chain | High — out of proportion to a single vertical slice | Large | — | Yes | Entirely new capability class |
| 10 | Registry/dispatcher/query-bus infrastructure | Same as #7/#9 | #7 | Medium-High | Unknown | — | Yes | New work, unjustified |
| 11 | Additional Campaign lifecycle capability (a second transition) | Yes | None | Low | Small | Low — `save()`/conflict already proven for `Campaign` | Not explicitly deferred, but implicitly lower priority | Repeats an already-once-proven-for-this-aggregate pattern; does not close the cross-aggregate generalization gap |
| 12 | Additional Run query (listing/filtering) | Partial (`get()` proven) | Explicitly out of scope per every prior milestone's own frozen exclusions | Medium — scope-creep risk | Unknown | — | Yes — explicitly excluded | Not a vertical-slice pattern, a framework concern |
| 13 | Any repository capability never reaching the application layer | `EvidencePackage.save()`, `Review.save()`, `Review.get()`/`add()`, `Campaign.add()`(N/A, done) | — | — | — | — | — | — |
| 14 | Any further prerequisite revealed by source | None found beyond the above — inventory in Section 4 is exhaustive for the current repository state | — | — | — | — | — | — |

---

## 9. Candidate Milestones Considered

**Candidate A — Run Lifecycle Transition (one command, `RunRepository.save()`).** Closes gap #1. Reuses `RunRepository`, `Run`'s already-frozen transition methods, `AggregateVersion`, `OptimisticConcurrencyConflict`, `CommandHandler`/`CommandEntryPoint` — all already frozen. No cross-aggregate FK dependency. Principal risk: none beyond what M032 already resolved for the identical mechanism at the `Campaign` level. Explicit exclusions: no second transition, no Run creation/retrieval change, no `EvidencePackage`/`Review` work.

**Candidate B — EvidencePackage Creation (`EvidencePackageRepository.add()`).** Closes gap #2. Reuses the real `evidence_package.run_id → run.governance_id` FK exactly as M033 used the `run.campaign_id → campaign.governance_id` FK. Principal risk: repeats an already-twice-proven `add()` pattern, closing no open architectural question. Explicit exclusions: no `EvidencePackage` retrieval/mutation, no Run/Campaign work, no `Review` work.

**Candidate C — EvidencePackage Retrieval (`EvidencePackageRepository.get()`).** Closes gap #3, but is strictly weaker than B alone (nothing to retrieve without B first) and repeats an already-twice-proven `get()` pattern.

**Candidate D — Review Creation.** Closes gap #4, but is gated two FK hops behind readiness (`EvidencePackage` must exist first) and repeats an already-twice-proven `add()` pattern.

**Candidate E — Review Retrieval.** Same gating as D, plus repeats an already-twice-proven `get()` pattern.

**Candidate F — Retry-on-conflict policy.** Rejected: only one save()-based command exists; generalizing a retry policy from a single data point repeats the premature-abstraction mistake every prior milestone has explicitly avoided.

**Candidate G — Production composition root / transport.** Rejected: the repeated-handler-need evidence bar this project has consistently applied (unchanged since M030) remains unmet at five trivial, unchanging direct-construction handlers.

**Candidate H — Audit/governance/registry foundation.** Rejected: each is an empty stub requiring an entirely new foundational milestone chain before any command/query work is even possible there — wildly out of proportion to a single vertical slice.

**Candidate I — A second Campaign lifecycle transition.** Rejected: `save()`/conflict is already proven once for `Campaign` (M032); a second `Campaign` transition would not close the cross-aggregate generalization gap that Candidate A closes, and offers materially less architectural leverage.

---

## 10. Candidate Comparison Matrix

| Criterion | A (Run transition) | B (EvidencePackage create) | D (Review create) | F (Retry policy) | G (Composition root) |
| --- | --- | --- | --- | --- | --- |
| 1. Architectural necessity | High — last unproven verb/aggregate cell | Medium — extends breadth, not depth | Low — gated | Low — insufficient evidence base | Low — unmet evidence bar |
| 2. Dependency readiness | Full — zero cross-aggregate hop | Full — one FK hop, already-proven mechanism | Partial — two FK hops, needs B first | Partial — needs ≥2 save() commands | Partial — needs repeated-handler evidence |
| 3. Sequencing correctness | Matches Run's own create→read→**update** sequence, explicitly named by M034 | Would jump ahead of completing Run's own sequence | Requires B first — cannot be M035 | Requires A (or B+transition) first | Requires repeated concrete need first |
| 4. New architectural proof | Yes — `save()`/conflict on 2nd aggregate | No — 3rd instance of proven `add()` | No — 3rd instance of proven `add()`, plus gated | No — insufficient data points | No — no new handler pattern |
| 5. Repetition vs. generalization value | Generalization | Repetition | Repetition | N/A — premature | N/A — premature |
| 6. Cross-aggregate leverage | None needed (self-contained) | Extends coverage to a 3rd aggregate | Extends coverage to a 4th aggregate | N/A | N/A |
| 7. Risk containment | Very low — mechanism already proven once | Low | Low, but gated | Medium — abstraction-from-one-example risk | Medium — framework-before-need risk |
| 8. Scope coherence | One capability, one sentence | One capability, one sentence | One capability, one sentence (but not ready) | Would require ≥2 commands to design around | Cross-cutting, not one capability |
| 9. Independent testability | Yes — mirrors M032 exactly | Yes | Yes, once B exists | Difficult with one data point | Difficult, ill-defined scope |
| 10. PostgreSQL testability | Yes — real conflict scenario provable, mirroring M032's `revise_scope_statement()`-as-interfering-write mechanism, adapted for `Run` | Yes | Yes, once B exists | N/A | N/A |
| 11. Frozen-contract preservation | Full — zero contract change needed | Full | Full | Full | Full |
| 12. Architecture-boundary impact | None expected (`usecases` already imports `run`) | One narrow addition (`"evidence"` to `ALLOWED["usecases"]`) | One narrow addition (`"review"`) plus `"evidence"` transitively for the FK-target type | None | Large, cross-cutting |
| 13. Future milestone leverage | Completes Run's app-layer proof; makes retry-policy generalization (gap #6) evidenced by 2 data points instead of 1 | Unlocks Review | Would depend on B | Blocked until ≥2 save() commands exist | Blocked until repeated need exists |
| 14. Premature-framework risk | None | None | None | High | High |
| 15. Implementation cost | Small, mirrors M032 exactly | Small, mirrors M033 exactly | Small, but blocked | Unknown, unbounded without evidence | Unknown, unbounded |
| 16. Governance clarity | Explicitly named next step in already-frozen M034 text | Named but explicitly deprioritized twice already (M033, M034) | Not yet reachable | Explicitly deferred every milestone | Explicitly deferred every milestone |

**Candidate A (Run Lifecycle Transition) wins on every criterion where the candidates differ**, and ties on the criteria where none of the candidates have an advantage (frozen-contract preservation, scope coherence in isolation).

---

## 11. Sequencing Attack (Hostile Challenge to Candidate A)

- **Does another capability logically need to exist first?** No. `RunRepository.get()`/`save()`, `Run`'s transition methods, `AggregateVersion`, and `OptimisticConcurrencyConflict` are all already frozen and already exercised at the `Campaign` level. Nothing new needs to be built or proven before this capability can be attempted.
- **Is the candidate merely copying a pattern already proven twice?** No — this is the opposite case: `save()`/conflict has been proven exactly **once**. This is the second instance, which is precisely what makes it a genuine generalization test rather than a repetition.
- **Does it unlock a downstream dependency?** Indirectly: it completes Run's own application-layer maturity (create/read/update all proven, matching Campaign), and it is the second data point retry-policy generalization (gap #6) would need before that work could ever be responsibly scoped. It does not technically unlock `EvidencePackage` (whose constructor has no Run-state precondition), so this is not claimed as a hard technical gate — only as a genuine maturity/evidence contribution.
- **Does it close a larger asymmetry than alternatives?** Yes, per the matrix in Section 6 — it is the only remaining cell in the fully-proven `Campaign`/`Run` block.
- **Does it require a hidden second capability?** No — one `get()` plus one `save()` call, identical shape to M032.
- **Does it depend on unresolved error/transaction/identity semantics?** No — all already frozen and already exercised for `Campaign`.
- **Is composition now justified by repeated concrete handlers, or still premature?** Still premature — five handlers exist, all trivially direct-constructed; this milestone would make it six, still no repeated-need evidence for a registry/composition root. Confirmed excluded from this scope.
- **Is retry policy now justified by multiple save-based commands, or still premature?** Still premature for *this* milestone — only one save()-based command (`Campaign`, M032) exists at scope-selection time. If M035 is approved, a second will exist, but retry-policy generalization from two data points is a decision for a *future* milestone to independently justify, not something this scope authorizes.
- **Would EvidencePackage creation provide more leverage than another Run transition?** No — it would extend aggregate *breadth* while leaving the *deepest* remaining pattern-generalization gap (`save()`/conflict) untouched. This project's own established discipline (M033 explicitly rejecting `EvidencePackage` in favor of the narrower-dependency `Run`; M034 explicitly rejecting `EvidencePackage` in favor of closing the `get()` gap) has consistently favored closing verb-generalization gaps over aggregate-breadth expansion when both are available.
- **Would a Run lifecycle transition be required before EvidencePackage can be meaningfully created?** Not technically (no FK/constructor gate), but it is the natural completion of Run's own create→read→update sequence before moving to a new aggregate — consistent with, not contradicted by, this project's own sequencing discipline.
- **Would Review work be incorrectly sequenced before EvidencePackage?** Yes, obviously (real FK dependency) — but this is not a consideration that favors or disfavors Candidate A; it only further disqualifies Candidates D/E for M035.
- **Does any frozen governance document explicitly name a prerequisite?** Yes — M034's own frozen scope narrative explicitly named this exact capability as the next step in Run's create→read→update sequence, deferring it only for immediate M034-vs-M035 sequencing reasons, not rejecting its priority.

**Candidate A survives every attack. Selected.**

---

## 12. Selected M035 Scope

**One concrete application command vertical slice for transitioning an existing Run from its current lifecycle state to the next state in its frozen lifecycle, via the frozen `RunRepository.save()` method and `OptimisticConcurrencyConflict` contract.**

---

## 13. Why This Scope Is Next

`RunRepository.save()` and `OptimisticConcurrencyConflict`, frozen since M020/M023 and already proven once (for `Campaign`, M032), have never been exercised by any application-layer command for `Run`. This is the single largest remaining unproven-generalization gap in the CQRS-vertical-slice pattern space: `add()` and `get()` have each independently generalized across two aggregates; `save()` has not. Closing it requires no new frozen dependency, no cross-aggregate FK hop, and is the literal next step in Run's own create (M033) → read (M034) → update (M035) sequence — explicitly named by M034's own frozen text as the reason Run retrieval, not Run transition, was chosen for M034.

---

## 14. In-Scope Capability

- One concrete command representing "transition an existing Run from its current lifecycle state to the next state," carrying the minimal data `RunRepository.save()` and the target `Run` transition method already require.
- One concrete handler conforming to the frozen `CommandHandler` Protocol that loads the Run via `RunRepository.get()`, invokes the appropriate already-frozen `Run` transition method, and persists the result via `RunRepository.save(..., expected_persisted_version=...)`.
- Binding this handler to a `CommandEntryPoint` and invoking it, proving the frozen write-side boundary's `save()`/`OptimisticConcurrencyConflict` contract holds for a second aggregate.
- Contract tests proving the concrete handler conforms to the frozen `CommandHandler` Protocol.
- Integration tests proving the golden path (transition of a Run created via the frozen M033 slice), the not-found path, the invalid-transition path (frozen `Run._transition()` behavior, unmodified), and a genuine, deterministic `OptimisticConcurrencyConflict` path, mirroring M032's own established real-database evidence discipline — all against real PostgreSQL.
- Identification (not resolution) of the design questions a `Run`-specific transition handler raises that M032's `Campaign`-specific design did not need to independently re-answer.

---

## 15. Out-of-Scope Capabilities

- Any second Run lifecycle transition, any Run creation/retrieval change, any additional Campaign command or query beyond M030-M032.
- Any command or query for `EvidencePackage` or `Review`.
- Any Run listing, filtering, pagination, or searching.
- Any retry, idempotency, or backoff policy of any kind.
- Any composition-root abstraction, handler registry, dispatcher, mediator, or service locator — direct construction only.
- Any transport/API layer of any kind, and any transport serialization contract.
- Any caching.
- Any audit/registry/governance integration.
- Any generic read-model or projection framework.
- Any schema or migration change.
- Any market-data, vendor, trading-strategy, order-execution, or brokerage-integration behavior.
- Any change to MILESTONE-020 through MILESTONE-034 frozen contracts, source files, or governance documents.
- Any MILESTONE-036 work of any kind.

---

## 16. Non-Goals

- This milestone is not a general-purpose "Run mutation" capability; it exercises exactly one lifecycle transition, not a generic state-machine framework.
- This milestone is not the `EvidencePackage`/`Review` milestone; it does not attempt to prove `add()`/`get()` generalization to a third/fourth aggregate.
- This milestone does not decide whether `EvidencePackage` creation, a second Run transition, or retry-policy work comes next.

---

## 17. Frozen Dependencies

**Depends on (frozen, read-only):**

- MILESTONE-020 `RunRepository` Protocol (`get()`/`save()` methods) and `Run` aggregate, including all of `Run`'s frozen transition methods (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`).
- MILESTONE-023 concrete PostgreSQL `Run` repository adapter's `save()` implementation.
- MILESTONE-020/023 `OptimisticConcurrencyConflict` contract, already proven for `Campaign` (MILESTONE-032).
- MILESTONE-027 `CommandHandler` Protocol.
- MILESTONE-029 `CommandEntryPoint`.
- MILESTONE-032's already-delivered `Campaign` lifecycle-transition vertical slice (pattern reference only, not a mandate).
- MILESTONE-033's already-delivered `Run` creation vertical slice, used to seed a real Run for transition evidence.
- MILESTONE-034's already-delivered `Run` retrieval vertical slice (usable, not required, for independent post-transition state verification in tests).

**Does not depend on:** any `EvidencePackage`/`Review` material, any Campaign mutation work, any transport or entrypoint code, any composition-root abstraction.

---

## 18. Frozen Contracts Preserved

The following remain exactly as frozen, unmodified, throughout this milestone's design and implementation:

- `Run` aggregate, its constructor, and all seven transition methods (MILESTONE-020/012).
- `RunRepository` Protocol, including its existing `get()`/`save()` method signatures (MILESTONE-020).
- The concrete PostgreSQL `Run` repository adapter (MILESTONE-023).
- `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol (MILESTONE-027).
- `CommandEntryPoint[CommandT, ResultT]` (MILESTONE-029).
- Everything MILESTONE-030 through MILESTONE-034 delivered: their concrete commands/queries, their concrete handlers, `CampaignSnapshot`/`RunSnapshot`, and the `usecases` package's existing architecture-checker rules.

---

## 19. Identity and Referential-Integrity Considerations

Repository-verified facts only, not design decisions: `RunRepository.get()` requires full `DomainIdentity[RunId]` (MILESTONE-034 precedent already established this as the frozen identity model for Run operations). `RunRepository.save()` requires the in-memory `Run` aggregate plus a caller-supplied `expected_persisted_version: AggregateVersion` (identical shape to `CampaignRepository.save()`, already exercised by M032's `PrepareCampaignForAuthorizationCommand`, which sources this value as a caller-supplied command field). No cross-aggregate referential-integrity concern exists for this capability — it operates entirely within one already-existing `Run` row.

---

## 20. Error/Failure Considerations

Repository-verified facts only: `RunRepository.get()` raises `AggregateNotFound` when the identity does not exist (already exercised, MILESTONE-034). `Run`'s transition methods raise `ValueError` when the current state does not permit the requested transition (already frozen, MILESTONE-020, verified directly in `run/aggregate.py`'s `_transition()` method). `RunRepository.save()` raises `AggregateNotFound`, `OptimisticConcurrencyConflict`, or `InvalidAggregateForPersistence` (already frozen, MILESTONE-020/023, already exercised for `Campaign` in MILESTONE-032). How the handler propagates or does not propagate each of these is an unresolved Design Mission question (Section 20 below), not decided here.

---

## 21. Architecture-Boundary Considerations

`ALLOWED["usecases"] = {"shared", "identifiers", "campaign", "run"}` already grants `"run"` — verified directly in `tools/check_architecture.py`. A Run-transition module needs no further checker permission on current evidence, since it uses only `RunRepository` and `Run`, both already importable from `usecases`. Whether any narrowly-scoped architecture-checker evidence is genuinely required is an open Design Mission question, not decided here.

---

## 22. PostgreSQL Testability

Repository-verified fact: `PostgresRunRepository.save()` already exists and implements the identical optimistic-concurrency mechanism M023 established and M032 already proved deterministic and testable for `Campaign` (via an independently-loaded second aggregate instance performing an interfering write). The exact interfering-write mechanism for `Run` (which frozen transition or field-level Run mutation will serve as the deterministic conflict producer) is an open Design Mission question, not decided here — `Run` has no non-state-transition mutator analogous to `Campaign.revise_scope_statement()`, so this genuinely requires independent design analysis, not a mechanical restatement of M032's mechanism.

---

## 23. Open Design Questions

Not decided by this scope:

- Which specific `Run` lifecycle-transition method this milestone targets — one of the seven (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`) — not resolved here, mirroring M032's own scope-stage precedent of leaving the exact `Campaign` transition method open.
- The exact command type name, shape, and fields (including whether `actor`/`occurred_at`/`correlation_id`/`reason` are caller-supplied, mirroring M032's `PrepareCampaignForAuthorizationCommand`, or something else).
- The exact handler type name, module path, and package exports.
- The exact result contract (mirroring M032's `SaveResult` return, or another justified shape).
- The exact identity representation the command carries.
- The exact error-propagation mechanics for `AggregateNotFound`, the transition-invalid `ValueError`, and `OptimisticConcurrencyConflict`.
- The exact deterministic PostgreSQL conflict-scenario mechanism for `Run` (see Section 22) — genuinely unresolved, since `Run` lacks a `Campaign.revise_scope_statement()`-equivalent non-transition mutator.
- Whether any narrowly-scoped architecture-checker evidence is genuinely required.
- Exact constructor dependencies, test filenames, and PostgreSQL test setup.

---

## 24. Risks

- **Premature specific-transition selection:** mitigated by explicitly deferring the choice to the Design Mission (Section 23), exactly mirroring M032's own successful precedent.
- **Conflating this milestone's mechanism with M032's `Campaign` mechanism without independent justification:** flagged explicitly (Section 22) as a genuine open question requiring fresh analysis, since `Run` has no direct analogue to `Campaign.revise_scope_statement()`.
- **Scope creep into retry-policy or composition-root territory:** explicitly excluded (Section 15); the existence of a second save()-based command after this milestone must not be silently read as authorizing retry-policy work within this same milestone.
- **Confusing this milestone's `save()` proof with M034's already-frozen `RunSnapshot` result-shape decisions:** the two are unrelated; this milestone's result contract is an independent, unresolved Design Mission question, not a re-application of M034's read-side reasoning.

---

## 25. Acceptance Boundaries

This scope is complete when:

- Exactly one capability is frozen (Run lifecycle transition via `save()`).
- No class name, method signature, module path, transition-method selection, dependency-injection mechanism, transaction behavior, error hierarchy, or result-shape decision is fixed by this document.
- Every excluded capability is explicit.
- The scope is independently reviewable without requiring the reviewer to resolve any open design question themselves.

---

## 26. Stop Conditions

This milestone stops at:

- One concrete command, one concrete handler, using `RunRepository.get()` and `RunRepository.save()` only.
- Proof that the `usecases`/`CommandHandler`/`CommandEntryPoint` `save()`/`OptimisticConcurrencyConflict` pattern composes correctly for a second aggregate.
- Contract, unit, architecture, and PostgreSQL integration test evidence, mirroring M032's established patterns where genuinely applicable, and independently derived where not (Section 22).

It does not continue into any second Run transition, any `EvidencePackage`/`Review` work, composition-root work, retry-policy work, or transport work, regardless of how natural such an extension might appear during design or implementation.

---

## 27. Prohibited Expansion

- No second Run transition or Run mutation beyond the one selected.
- No `EvidencePackage`/`Review` command or query.
- No composition root, registry, dispatcher, mediator, or service locator.
- No transport layer of any kind.
- No retry/backoff/idempotency policy.
- No generic read-model or projection framework.
- No MILESTONE-036 work.

---

## 28. Deferred Work

- `EvidencePackage` creation and retrieval (a future milestone, once Run's own application-layer maturity — including this milestone — is complete).
- `Review` creation and retrieval (blocked behind `EvidencePackage`).
- Retry-on-`OptimisticConcurrencyConflict` policy, now genuinely closer to justifiable (two data points instead of one after this milestone), but still not authorized by this scope.
- Any composition-root abstraction beyond direct binding.
- Any transport/entrypoint adapter.
- A second Campaign lifecycle transition (lower priority than this milestone; does not close a cross-aggregate generalization gap).
- MILESTONE-036 and beyond.

---

## M036 Boundary

This document, and the milestone it scopes, authorizes work through MILESTONE-035 only. No MILESTONE-036 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. The "Deferred Work" list above (Section 28) is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-036's scope — that determination is explicitly reserved for MILESTONE-036's own independent, from-source scope-selection mission, exactly as this document was itself independently derived rather than assumed.

---

## Governance Status

**Status:** `CANDIDATE_FOR_INDEPENDENT_SCOPE_REVIEW`. Not approved. Not frozen. Does not authorize design or implementation.

---

## Next Permitted Action

**MILESTONE-035 INDEPENDENT SCOPE REVIEW.**
