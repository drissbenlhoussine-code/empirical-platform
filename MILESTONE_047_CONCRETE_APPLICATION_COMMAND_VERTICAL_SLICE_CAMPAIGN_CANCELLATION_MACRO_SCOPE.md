# MILESTONE-047 - Concrete Application Command Vertical Slice: Campaign Cancellation - Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31) as part of one consolidated M047 mission: scope, design, and implementation together, followed by one independent review checkpoint.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M047 frozen baseline | `3ecd75e68d6cac5c6c6661376684a3eba3045f4b` (the final M046 Owner Freeze hash-recording HEAD; M046 fully `APPROVED_AND_FROZEN` at scope, design, and implementation) |

## 3. Fresh, Complete Architecture Inventory

A from-source rebuild, not a copy of prior governance prose, found the following per-aggregate application-layer proof state:

| Aggregate | `create`/`add()` | `get()` | `save()`/transition proof |
| --- | --- | --- | --- |
| Campaign | M030 | M031 | M032 (`prepare_for_authorization()` only) |
| Run | M033 | M034 | M035 (`authorize()` only) |
| EvidencePackage | M036 | M037 (`get_evidence_package`) | M038-M041 (`start_collection`/`add_criterion_result`/`add_artifact_reference`/`seal`) |
| Review | M042 | M043 | M044-M046 (`start`/`add_finding`/`complete`) |

All four aggregates now have at least one proven `save()`/`OptimisticConcurrencyConflict` transition — this generalization axis (does `get()`→mutate→`save()` genuinely work per aggregate) is now closed for every aggregate.

Full domain-method inventory (transition/mutation methods only, properties excluded) versus application-layer proof:

| Aggregate | Domain methods | Proven as a usecase | Unproven |
| --- | --- | --- | --- |
| Campaign | `revise_scope_statement`, `prepare_for_authorization`, `record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel` (8) | `prepare_for_authorization` (1) | 7 |
| Run | `authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`, `append_manifest` (8) | `authorize` (1) | 7 |
| EvidencePackage | `start_collection`, `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate` (5) | 4 | `invalidate` (1) |
| Review | `start`, `add_finding`, `complete`, `cancel` (4) | 3 | `cancel` (1) |

Campaign and Run each carry the largest remaining absolute gap (7 unproven domain methods each), against EvidencePackage's and Review's single remaining gap each.

## 4. A Second, Cross-Cutting Architectural Gap

Independent of per-aggregate method counts, a fresh read of every aggregate's transition methods found a gap that spans all four aggregates equally: **no negative/terminal (cancellation, invalidation, or failure) transition has ever been proven at the application layer**, for any aggregate. Every application-layer command implemented so far (M030-M046) has proven only forward, success-path transitions. `Review.cancel()`, `EvidencePackage.invalidate()`, `Campaign.cancel()`, and `Run.cancel()`/`Run.fail()` are all equally unproven along this specific axis.

A direct source comparison of these five candidate methods found they are not architecturally equivalent:

| Method | `allowed_states`/`expected_state` shape | Conditional validation |
| --- | --- | --- |
| `EvidencePackage.invalidate()` | single `expected_state=SEALED` | none — same shape as every already-proven transition |
| `Run.cancel()` | single `allowed_states=(AUTHORIZED,)` | none |
| `Review.cancel()` | 2-element `allowed_states=(ASSIGNED, IN_PROGRESS)` | none |
| `Run.fail()` | 3-element `allowed_states=(ACQUIRING, NORMALIZING, VALIDATING)` | none |
| `Campaign.cancel()` | 5-element `allowed_states=(DRAFT, READY_FOR_AUTHORIZATION, AUTHORIZED, ACTIVE, SUSPENDED)` | **yes** — `reason` is required (non-empty `str`, `TypeError` if `None`) when cancelling from `AUTHORIZED`/`ACTIVE`/`SUSPENDED`, but optional (may be `None`, forbidden to be empty-string) when cancelling from `DRAFT`/`READY_FOR_AUTHORIZATION`; this state-dependent branch is evaluated by `cancel()` itself, before `_transition()` is ever called |

Every transition proven at M030-M046 uses a single-element `allowed_states` (or the equivalent single `expected_state`, EvidencePackage's own variant). `Campaign.cancel()` is the only candidate that exercises `_transition()`'s `allowed_states` mechanism with more than a single reachable source state at the widest possible scale (5 of Campaign's 7 non-terminal states), and it is the only candidate anywhere in the codebase whose own precondition validation branches on which specific source state the aggregate is currently in — a genuinely new precondition shape, distinct from every fixed-field-presence check proven so far (M030-M046).

## 5. Selected Scope

One concrete command cancelling an existing Campaign from any of its five non-terminal, non-completed states (`DRAFT`, `READY_FOR_AUTHORIZATION`, `AUTHORIZED`, `ACTIVE`, `SUSPENDED`), via `Campaign.cancel()` — the sixth proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, the first proof of a negative/terminal transition at the application layer for any aggregate, the first proof of a multi-state (`allowed_states` with more than one element) transition reaching this magnitude (5 states), and the first proof of state-dependent conditional domain validation.

This closes both the largest remaining absolute per-aggregate gap (Campaign, 7 unproven methods, untouched at the application layer since M032) and the cross-cutting cancellation-semantics gap shared by every aggregate, using the single richest available exemplar of that gap.

## 6. Rejected Alternatives

- **`Review.cancel()` / `Run.cancel()` / `Run.fail()` / `EvidencePackage.invalidate()`** — each proves the same cancellation-semantics gap, but with a strictly narrower `allowed_states` set and no conditional validation; selecting any of these instead of `Campaign.cancel()` would prove a strictly weaker version of the same architectural question.
- **A second Campaign forward transition** (`record_authorization`, `activate`, `suspend`, `resume`, `complete`) — each is architecturally identical in shape to already-proven transitions (single `allowed_states` element, unconditional field-presence validation); would not close the cancellation-semantics gap and would not exercise any new mechanism.
- **Retry-on-conflict policy, composition root, transport-neutral invocation, audit/governance runtime, registry/dispatcher** — each is a multi-command, framework-level capability spanning the entire application layer, not a single vertical slice; explicitly deferred in every prior milestone's own "Deferred Work" section (M032 Section 31, M035 Section 31, M045 Section 31, M046 Section 52) as premature ahead of broader per-aggregate proof. Selecting any of these now would depart from this project's established one-capability-per-milestone discipline.

## 7. In-Scope

- `CancelCampaignCommand`/`CancelCampaignHandler` in `empirical_platform.usecases.cancel_campaign`.
- Focused unit, contract, and PostgreSQL integration tests for this one command.
- Independent, empirical (not assumed) confirmation of genuine `OptimisticConcurrencyConflict` reachability, reusing `Campaign.revise_scope_statement()` (M032's own interfering write) as the interferer — independently re-verified for this new target transition, not assumed by analogy: `revise_scope_statement()` requires `DRAFT` and does not change `state`, so a Campaign cancelled from `DRAFT` remains a domain-valid interference target (the interferer's write leaves `state=DRAFT`, still within `cancel()`'s own `allowed_states`).

## 8. Out-of-Scope

- `Review.cancel()`, `EvidencePackage.invalidate()`, `Run.cancel()`/`Run.fail()`.
- Any other Campaign transition (`record_authorization`, `activate`, `suspend`, `resume`, `complete`).
- Any Run/EvidencePackage/Review capability.
- Retry-on-conflict policy, composition root, transport-neutral invocation, audit/governance runtime, registry/dispatcher, or any other cross-cutting framework work.
- Any schema/migration change.
- MILESTONE-048 work of any kind.

## 9. Frozen Dependencies

`Campaign` aggregate (M012/M020), `CampaignRepository` Protocol (M020), `PostgresCampaignRepository` (M023), `CommandHandler`/`CommandEntryPoint` (M027/M029) — all unmodified, all already proven for Campaign at M030-M032.

## 10. Lifecycle Prerequisites

`Campaign.cancel()` is reachable directly from `DRAFT` (M030's own creation state) — no additional predecessor transition is required to reach at least one of the five allowed source states, unlike `complete()` (M046) or `seal()` (M041), which each required two prior milestones to become reachable at all. This is architecturally simpler to set up than M046, while still proving new mechanism (multi-state reachability, conditional validation).

## 11. Conflict Feasibility — Open Question, Not Assumed

Whether `Campaign.revise_scope_statement()` (from `DRAFT`) genuinely serves as a state-preserving interfering write against `cancel()` (also reachable from `DRAFT`) is asserted here as architecturally plausible — `revise_scope_statement()` does not call `_transition()` and never changes `_state` — but is explicitly deferred to empirical confirmation during implementation, exactly as M032, M035, M039, M045, and M046 each deferred and then confirmed their own conflict claims rather than assuming them from a governance description.

## 12. Architectural Leverage

Closes the CQRS-verb generalization axis's remaining loose end (a multi-state, conditionally-validated transition, never exercised before) while reusing an already-frozen, already-proven interfering-write mechanism (`revise_scope_statement()`), minimizing net-new domain risk while maximizing net-new proof of `_transition()`'s own general-purpose `allowed_states` mechanism.

## 13. Risks

- `revise_scope_statement()`'s `DRAFT`-only precondition constrains the conflict-reproduction scenario to specifically the `DRAFT` source state (one of `cancel()`'s five allowed states) — this is disclosed here, not hidden, and does not weaken the `cancel()` capability itself, which remains reachable from all five states regardless of which one is used for the conflict-reproduction test.
- The state-dependent conditional `reason` validation inside `cancel()` itself (Section 4) must be exercised by both branches (required-and-present, optional-and-absent) in the test suite to avoid a false claim of full precondition coverage.

## 14. M048 Boundary

This scope selects exactly one MILESTONE-047 capability. No MILESTONE-048 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 15. Hostile Self-Review

A full re-read of `Campaign.aggregate.py`, `Run.aggregate.py`, `review/aggregate.py`, and `evidence/package.py` confirms the method-shape comparison in Section 4 is accurate (verified via direct `sed`/`grep` extraction, not summarized from memory). The claim that Campaign carries the largest per-aggregate gap (7 unproven methods) was independently re-counted against `usecases/*.py`'s actual file list (17 existing usecase files, none named for any Campaign method beyond `create_campaign`/`get_campaign`/`prepare_campaign_for_authorization`). No hidden design, implementation, sequencing, or governance decision is present in this document; all detailed load-bearing decisions (exact command fields, conflict mechanism internals, PostgreSQL evidence strategy) are deferred to the Design section of this same consolidated mission.

## 16. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE.**
