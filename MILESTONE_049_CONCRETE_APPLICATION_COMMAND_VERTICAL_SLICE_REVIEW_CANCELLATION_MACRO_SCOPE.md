# MILESTONE-049 - Concrete Application Command Vertical Slice: Review Cancellation - Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31) as part of one consolidated M049 mission: scope, design, and implementation together, followed by one independent review checkpoint.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M049 frozen baseline | `f8fb8c41488d243fa22a48ad55979eb191046f4d` (the final M048 Owner Freeze hash-recording HEAD; M048 fully `APPROVED_AND_FROZEN` at scope, design, and implementation) |

## 3. Fresh, Complete Architecture Inventory

A from-source rebuild, not a copy of prior governance prose, found the following per-aggregate application-layer proof state:

| Aggregate | `create`/`add()` | `get()` | Proven transitions |
| --- | --- | --- | --- |
| Campaign | M030 | M031 | `prepare_for_authorization` (M032), `cancel` (M047) |
| Run | M033 | M034 | `authorize` (M035), `fail` (M048) |
| EvidencePackage | M036 | M037 | `start_collection`/`add_criterion_result`/`add_artifact_reference`/`seal` (M038-M041) |
| Review | M042 | M043 | `start`/`add_finding`/`complete` (M044-M046) |

The negative/terminal-transition axis (opened by M047's `Campaign.cancel()`) has now been proven on two aggregates (Campaign, Run via M048's `Run.fail()`). Two aggregates remain with zero negative/terminal proof: EvidencePackage (`invalidate()`) and Review (`cancel()`).

Full domain-method inventory (transition/mutation methods only) versus application-layer proof, independently re-derived from source:

| Aggregate | Domain methods | Proven | Unproven |
| --- | --- | --- | --- |
| Campaign | `revise_scope_statement`, `prepare_for_authorization`, `record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel` (8) | 2 | 6 |
| Run | `authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`, `append_manifest` (8) | 2 | 6 |
| EvidencePackage | `start_collection`, `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate` (5) | 4 | 1 (`invalidate`) |
| Review | `start`, `add_finding`, `complete`, `cancel` (4) | 3 | 1 (`cancel`) |

EvidencePackage and Review are each exactly one method away from **complete** application-layer proof (100% of domain transition/mutation methods proven) — neither Campaign nor Run is anywhere close (6 unproven methods each). Proving either `EvidencePackage.invalidate()` or `Review.cancel()` would make that aggregate the **first** in the project with fully-proven application-layer coverage.

## 4. Comparing the Two Completion Candidates

| Method | `_transition()` mechanism | Precondition width | Mechanism already proven for this aggregate | Real conflict interferer available |
| --- | --- | --- | --- | --- |
| `EvidencePackage.invalidate()` | singular `expected_state` | 1 state (`SEALED`) | Yes — 2 prior proofs (`start_collection`, `seal`) | None identified: `add_criterion_result()`/`add_artifact_reference()` both require `COLLECTING`, not `SEALED`; no state-preserving mutation is reachable from `SEALED` |
| `Review.cancel()` | tuple `allowed_states` | 2 states (`ASSIGNED`, `IN_PROGRESS`) | No — Review's own transitions (`start`, `complete`) are each single-state; `cancel()` would be Review's own first multi-state proof | Yes — `Review.add_finding()` (M045's own frozen interfering write), state-preserving, reachable from `IN_PROGRESS` (one of `cancel()`'s two allowed states), already twice-proven as a genuine interferer (M045 self-reuse, M046 reuse for `complete()`) |

`Review.cancel()` is the stronger candidate on every axis that matters: it proves Review's own first multi-state transition (a genuine novelty for this aggregate, mirroring the widening pattern already demonstrated by `Campaign.cancel()` and `Run.fail()`), and it has a directly available, already-precedented conflict interferer. `EvidencePackage.invalidate()`, by contrast, would be the third proof of an already-established single-state mechanism for this aggregate, and no genuine, real (non-fabricated) interfering write is reachable from `SEALED` — `EvidencePackage`'s remaining domain methods after sealing offer no state-preserving mutation, meaning a genuine conflict reproduction would not be achievable without inventing one, unlike every prior milestone's disciplined "verify feasibility, don't fabricate" practice.

## 5. Selected Scope

One concrete command cancelling an existing Review from either of its two non-terminal states (`ASSIGNED`, `IN_PROGRESS`), via `Review.cancel()` — the eighth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, the second generalization of the negative/terminal-transition axis to a third aggregate, and the completion of Review's application-layer proof (4 of 4 domain methods now proven) — the first aggregate in the project to reach full coverage.

## 6. Rejected Alternatives

- **`EvidencePackage.invalidate()`** — would also complete an aggregate's proof, but reuses an already-thrice-proven mechanism for this aggregate and has no genuinely reachable interfering write from `SEALED` (see Section 4); selecting it would either produce a weaker, non-conflict-tested command or force a fabricated conflict scenario, violating this project's established discipline.
- **A Campaign or Run forward-pipeline transition** (`record_authorization`, `activate`, `start_acquisition`, etc.) — each is architecturally identical in shape to already-proven transitions (single `allowed_states` element, unconditional validation); would not close either remaining-gap aggregate to completion and would not exercise any new mechanism.
- **Retry-on-conflict policy, composition root, transport-neutral invocation, audit/governance runtime, registry/dispatcher** — each is a multi-command, framework-level capability spanning the entire application layer, not a single vertical slice; explicitly deferred in every prior milestone's own "Deferred Work" section (M032 Section 31, M035 Section 31, M045 Section 31, M046 Section 52, M047 Section 49, M048 Section 50) as premature ahead of broader per-aggregate proof. Two aggregates (Campaign, Run) still have 6 unproven methods each, so this deferral remains clearly justified.

## 7. In-Scope

- `CancelReviewCommand`/`CancelReviewHandler` in `empirical_platform.usecases.cancel_review`.
- Focused unit, contract, and PostgreSQL integration tests for this one command.
- Independent, empirical (not assumed) confirmation of genuine `OptimisticConcurrencyConflict` reachability, reusing `Review.add_finding()` (M045's own frozen interfering write, already reused once by M046 for `complete()`) as the interferer — independently re-verified for this new target transition, not assumed by analogy: `add_finding()` requires `IN_PROGRESS` and never changes `_state`, so a Review cancelled from `IN_PROGRESS` remains a domain-valid interference target.

## 8. Out-of-Scope

- `EvidencePackage.invalidate()`, `Run.cancel()`, any Run forward-pipeline transition, any Campaign forward transition.
- Retry-on-conflict policy, composition root, transport-neutral invocation, audit/governance runtime, registry/dispatcher, or any other cross-cutting framework work.
- Any schema/migration change.
- MILESTONE-050 work of any kind.

## 9. Frozen Dependencies

`Review` aggregate (M012/M020), `ReviewRepository` Protocol (M020), `PostgresReviewRepository` (M023), `CommandHandler`/`CommandEntryPoint` (M027/M029) — all unmodified, all already proven for Review at M042-M046.

## 10. Lifecycle Prerequisites

`Review.cancel()` is reachable directly from `ASSIGNED` (M042's own creation state) — no additional predecessor transition is required to reach at least one of the two allowed source states. Reaching `IN_PROGRESS` (the second allowed state, and the one needed for conflict reproduction) requires the existing, frozen M044 `StartReviewHandler` — already proven and directly reusable.

## 11. Conflict Feasibility — Open Question, Not Assumed

Whether `Review.add_finding()` (from `IN_PROGRESS`) genuinely serves as a state-preserving interfering write against `cancel()` (also reachable from `IN_PROGRESS`) is asserted here as architecturally plausible — `add_finding()` does not call `_transition()` and never changes `_state` — but is explicitly deferred to empirical confirmation during implementation, exactly as M032, M035, M039, M045, M046, M047, and M048 each deferred and then confirmed their own conflict claims rather than assuming them from a governance description.

## 12. Architectural Leverage

Completes Review's application-layer proof (the first aggregate in the project to reach 4/4 domain methods proven), proves Review's own first multi-state `allowed_states` transition, and reuses an already-frozen, twice-proven interfering-write mechanism (`add_finding()`), minimizing net-new domain risk while maximizing net-new architectural completeness.

## 13. Risks

- `cancel()`'s two allowed states (`ASSIGNED`, `IN_PROGRESS`) both must be exercised in the test suite to avoid a false claim of full precondition coverage — carried forward as an explicit test-strategy requirement into the design document.
- The conflict-reproduction test must specifically use `IN_PROGRESS` (the only allowed state from which `add_finding()` is reachable) — disclosed here, not hidden.

## 14. M050 Boundary

This scope selects exactly one MILESTONE-049 capability. No MILESTONE-050 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 15. Hostile Self-Review

A full re-read of `review/aggregate.py` and `evidence/package.py` confirms the mechanism comparison in Section 4 is accurate (verified via direct `grep`/`sed` extraction, not summarized from memory). The claim that `EvidencePackage` has no reachable interfering write from `SEALED` was independently checked against every EvidencePackage domain method's own precondition (`add_criterion_result`/`add_artifact_reference` both require `COLLECTING`; no other state-preserving mutation exists on the aggregate). The claim that Review and EvidencePackage are each one method from full application-layer completion was independently re-counted against `usecases/*.py`'s actual file list (19 existing usecase files at baseline). No hidden design, implementation, sequencing, or governance decision is present in this document; all detailed load-bearing decisions (exact command fields, conflict mechanism internals, PostgreSQL evidence strategy) are deferred to the Design section of this same consolidated mission.

## 16. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE.**
