# MILESTONE-048 - Concrete Application Command Vertical Slice: Run Execution Failure - Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31) as part of one consolidated M048 mission: scope, design, and implementation together, followed by one independent review checkpoint.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M048 frozen baseline | `85706955abce892d14937ad00307717b6170085e` (the final M047 Owner Freeze hash-recording HEAD; M047 fully `APPROVED_AND_FROZEN` at scope, design, and implementation) |

## 3. Fresh, Complete Architecture Inventory

A from-source rebuild, not a copy of prior governance prose, found the following per-aggregate application-layer proof state:

| Aggregate | `create`/`add()` | `get()` | Proven transitions |
| --- | --- | --- | --- |
| Campaign | M030 | M031 | `prepare_for_authorization` (M032), `cancel` (M047) |
| Run | M033 | M034 | `authorize` (M035) |
| EvidencePackage | M036 | M037 | `start_collection`/`add_criterion_result`/`add_artifact_reference`/`seal` (M038-M041) |
| Review | M042 | M043 | `start`/`add_finding`/`complete` (M044-M046) |

`get()`/`add()`/`save()` are now each proven at least once for every aggregate — that generalization axis remains closed (confirmed M047 Section 3). M047 additionally proved a **negative/terminal transition** (`Campaign.cancel()`) for the first time in this project — a new generalization axis with exactly one proof point, on exactly one aggregate.

Full domain-method inventory (transition/mutation methods only) versus application-layer proof, independently re-derived from source:

| Aggregate | Domain methods | Proven | Unproven |
| --- | --- | --- | --- |
| Campaign | `revise_scope_statement`, `prepare_for_authorization`, `record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel` (8) | 2 (`prepare_for_authorization`, `cancel`) | 6 |
| Run | `authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`, `append_manifest` (8) | 1 (`authorize`) | 7 |
| EvidencePackage | `start_collection`, `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate` (5) | 4 | 1 (`invalidate`) |
| Review | `start`, `add_finding`, `complete`, `cancel` (4) | 3 | 1 (`cancel`) |

Run now carries the single largest remaining absolute gap (7 of 8 domain methods unproven), unchanged in rank since M033 first identified it and larger than Campaign's now-reduced gap (6, after M047).

## 4. The Negative/Terminal-Transition Generalization Axis — Still Open

M047 proved `Campaign.cancel()` is a genuine, workable pattern for a negative/terminal application-layer transition, but this was demonstrated on exactly one aggregate. Mirroring this project's own recurring generalization discipline — `get()`/`add()`/`save()` were each proven on Campaign first (M030-M032) and only later shown to generalize across Run/EvidencePackage/Review (M033-M046) — the negative/terminal-transition axis has not yet been shown to generalize beyond Campaign. A direct source comparison of the four remaining negative/terminal candidates (`Run.cancel()`, `Run.fail()`, `Review.cancel()`, `EvidencePackage.invalidate()`) against the now-frozen `Campaign.cancel()` precedent:

| Method | `allowed_states` shape | Conditional validation | Distinct real-world scenario vs `Campaign.cancel()` |
| --- | --- | --- | --- |
| `EvidencePackage.invalidate()` | single `expected_state=SEALED` | none | no — post-hoc invalidation of a completed artifact, same shape as every already-proven transition |
| `Run.cancel()` | single `allowed_states=(AUTHORIZED,)` | none | no — pre-execution abandonment, architecturally identical to `Campaign.cancel()`'s `DRAFT`/`READY_FOR_AUTHORIZATION` branch |
| `Review.cancel()` | 2-element `allowed_states=(ASSIGNED, IN_PROGRESS)` | none | no — pre-completion abandonment, same category as `Campaign.cancel()` |
| `Run.fail()` | 3-element `allowed_states=(ACQUIRING, NORMALIZING, VALIDATING)` | none | **yes** — models genuine mid-execution failure (something went wrong while acquiring/normalizing/validating data), a scenario `Campaign.cancel()` cannot express (Campaign has no analogous "went wrong during execution" state; its own `cancel()` only ever models deliberate abandonment, never failure) |

`Run.fail()` is the only remaining candidate with both a multi-state `allowed_states` (3 elements, the second-widest of any transition in the project after `Campaign.cancel()`'s 5) and a semantically distinct scenario from what M047 already proved (failure, not abandonment).

## 5. Selected Scope

One concrete command failing an existing Run from any of its three execution-stage states (`ACQUIRING`, `NORMALIZING`, `VALIDATING`), via `Run.fail()` — the seventh proof of the `get()`→mutate→`save()`/`OptimisticConcurrencyConflict` pattern, and the first generalization of the negative/terminal-transition axis (M047) to a second aggregate.

This closes both the largest remaining absolute per-aggregate gap (Run, 7 of 8 domain methods still unproven) and generalizes M047's own newly-opened architectural axis, using the richest available exemplar of that generalization (widest remaining `allowed_states`, genuinely distinct failure semantics).

## 6. Rejected Alternatives

- **`Run.cancel()` / `Review.cancel()` / `EvidencePackage.invalidate()`** — each would generalize the negative/terminal axis to a second aggregate, but each is architecturally narrower (single or 2-element `allowed_states`, no distinct scenario from `Campaign.cancel()`) than `Run.fail()`; selecting any of these would prove a weaker version of the same generalization question `Run.fail()` answers more thoroughly.
- **A Run forward-pipeline transition** (`start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`) — each is architecturally identical in shape to already-proven transitions (single `allowed_states` element, unconditional validation); would not generalize any open axis and would not exercise any new mechanism.
- **A Campaign forward transition** (`record_authorization`, `activate`, `suspend`, `resume`, `complete`) — same reasoning; Campaign's remaining gap is also architecturally uninteresting (single-state, unconditional), and Campaign was already the subject of the most recent milestone (M047).
- **Retry-on-conflict policy, composition root, transport-neutral invocation, audit/governance runtime, registry/dispatcher** — each is a multi-command, framework-level capability spanning the entire application layer, not a single vertical slice; explicitly deferred in every prior milestone's own "Deferred Work" section (M032 Section 31, M035 Section 31, M045 Section 31, M046 Section 52, M047 Section 49) as premature ahead of broader per-aggregate proof. Per-aggregate proof remains incomplete (Run alone still has 7 unproven methods after this milestone selects one), so this deferral remains justified; selecting any of these now would depart from this project's established one-capability-per-milestone discipline.

## 7. In-Scope

- `FailRunCommand`/`FailRunHandler` in `empirical_platform.usecases.fail_run`.
- Focused unit, contract, and PostgreSQL integration tests for this one command.
- Independent, empirical (not assumed) confirmation of genuine `OptimisticConcurrencyConflict` reachability, reusing `Run.append_manifest()` (M035's own interfering write) as the interferer — independently re-verified for this new target transition, not assumed by analogy: `append_manifest()`'s own `_MANIFEST_APPEND_STATES` tuple includes `ACQUIRING`, `NORMALIZING`, and `VALIDATING` (all three of `fail()`'s allowed states), and `append_manifest()` never changes `_state`, so a Run failed from any of these three states remains a domain-valid interference target.

## 8. Out-of-Scope

- `Run.cancel()`, `Review.cancel()`, `EvidencePackage.invalidate()`.
- Any Run forward-pipeline transition (`start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`).
- Any Campaign/EvidencePackage/Review capability.
- Retry-on-conflict policy, composition root, transport-neutral invocation, audit/governance runtime, registry/dispatcher, or any other cross-cutting framework work.
- Any schema/migration change.
- MILESTONE-049 work of any kind.

## 9. Frozen Dependencies

`Run` aggregate (M012/M020), `RunRepository` Protocol (M020), `PostgresRunRepository` (M023), `CommandHandler`/`CommandEntryPoint` (M027/M029) — all unmodified, all already proven for Run at M033-M035.

## 10. Lifecycle Prerequisites

`Run.fail()` is reachable only after `authorize()` (M035) and at least one of `start_acquisition()`/`start_normalization()`/`start_validation()` — none of which have a production command yet (this milestone's own scope, Section 8, explicitly excludes them). Test fixtures will drive these predecessor states via direct domain-method calls on an independently loaded aggregate, mirroring the identical pattern M047's own fixtures used to reach `AUTHORIZED` (test setup only, never through a production command).

## 11. Conflict Feasibility — Open Question, Not Assumed

Whether `Run.append_manifest()` (reachable from `ACQUIRING`/`NORMALIZING`/`VALIDATING`) genuinely serves as a state-preserving interfering write against `fail()` is asserted here as architecturally plausible — `append_manifest()` does not call `_transition()` and never changes `_state` — but is explicitly deferred to empirical confirmation during implementation, exactly as M032, M035, M039, M045, M046, and M047 each deferred and then confirmed their own conflict claims rather than assuming them from a governance description.

## 12. Architectural Leverage

Generalizes the negative/terminal-transition axis (opened by M047) to a second aggregate, closes Run's single largest remaining domain-method gap, and reuses an already-frozen, already-proven interfering-write mechanism (`append_manifest()`), minimizing net-new domain risk while maximizing net-new architectural proof (the widest remaining `allowed_states` reachability after `Campaign.cancel()`, and the first "failure" — as opposed to "abandonment" — semantics in the project).

## 13. Risks

- `append_manifest()`'s own precondition set (`_MANIFEST_APPEND_STATES`) is broader than `fail()`'s three allowed states (it also includes `CREATED`/`AUTHORIZED`), so the conflict-reproduction test must specifically choose one of the three overlapping states (`ACQUIRING`/`NORMALIZING`/`VALIDATING`) — disclosed here, not hidden.
- Reaching `ACQUIRING`/`NORMALIZING`/`VALIDATING` in integration tests requires driving `authorize()` + at least one of `start_acquisition()`/`start_normalization()`/`start_validation()` directly on the aggregate (no production command exists for these yet) — this is test setup only, exactly mirroring M047's own established pattern, not a hidden dependency on unbuilt production capability.

## 14. M049 Boundary

This scope selects exactly one MILESTONE-048 capability. No MILESTONE-049 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 15. Hostile Self-Review

A full re-read of `run/aggregate.py`, `campaign/aggregate.py`, `evidence/package.py`, and `review/aggregate.py` confirms the method-shape comparison in Section 4 is accurate (verified via direct `sed`/`grep` extraction, not summarized from memory). The claim that Run carries the largest per-aggregate gap (7 unproven methods) was independently re-counted against `usecases/*.py`'s actual file list (18 existing usecase files at baseline, none named for any Run transition beyond `authorize_run.py`). The claim that `append_manifest()`'s `_MANIFEST_APPEND_STATES` includes all three of `fail()`'s allowed states was independently verified by direct source inspection of both tuples side by side. No hidden design, implementation, sequencing, or governance decision is present in this document; all detailed load-bearing decisions (exact command fields, conflict mechanism internals, PostgreSQL evidence strategy) are deferred to the Design section of this same consolidated mission.

## 16. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE.**
