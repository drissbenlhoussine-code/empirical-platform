# MILESTONE-035 - Concrete Application Command Vertical Slice (Run Lifecycle Transition) Scope Freeze

## 1. Milestone Identity

MILESTONE-035 — Concrete Application Command Vertical Slice: Run Lifecycle Transition.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `159403cc5e60d179f4e367fefc7a7479cd84e24f` |

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Run Creation) | APPROVED_AND_FROZEN |
| M034 (Run Retrieval) | APPROVED_AND_FROZEN (implementation freeze `3056e3010b4f20f3cf7bf2ab2e3fbbc43fcff825`) |

## 4. M035 Scope Candidate Authority

`MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE.md`, candidate commit `26aab1acb1d08150144b8ce52d63f17796f121ef`. Selected one capability — one Run lifecycle-transition command vertical slice — via a fresh, from-source architecture inventory, a 16-criterion candidate comparison matrix, and an 11-question hostile sequencing attack (scope document Sections 4-11).

## 5. Independent Scope-Review Authority

The independent hostile scope review verified: repository truth; the governance-only candidate delta; the fresh architecture inventory; `Campaign` add/get/save proof; `Run` add/get proof; the absence of any Run application-layer save/update proof; frozen `RunRepository.save()` support; real optimistic-concurrency enforcement; deterministic PostgreSQL conflict feasibility; one-capability scope purity; absence of a hidden transition selection, retry policy, composition, or transport decision; no frozen-contract modification requirement; current architecture-permission sufficiency; independent PostgreSQL testability; and that M036 remains not started.

**Decision: M035 SCOPE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains.

## 6. Non-Blocking Observation

`PROJECT_CHECKPOINT.md` Section 2 ("Current State") contained a stale top-level field:

```
LATEST_FROZEN_MILESTONE=MILESTONE-028
```

Independently verified genuine before acting on it (not taken on faith): `grep -n "LATEST_FROZEN_MILESTONE" PROJECT_CHECKPOINT.md` confirmed this exact stale value in the live file. Cross-checked against the document's own detailed per-milestone sections (Sections 3-27), which correctly and consistently show M020 through M034 as `APPROVED_AND_FROZEN` at every stage — the detailed records were never wrong; only this one top-level summary field had gone stale, apparently never updated across the M029-M034 milestone sequence.

## 7. Observation Resolution

`LATEST_FROZEN_MILESTONE` corrected to `MILESTONE-034` — the actual latest milestone that is fully `APPROVED_AND_FROZEN` at every stage (scope, design, and implementation), per Section 27 of `PROJECT_CHECKPOINT.md` and this document's own Section 3. **Not** set to `MILESTONE-035`, because M035 is scope-frozen only at this point — design and implementation remain `NOT_STARTED`, and this field records the latest *fully* frozen milestone, not the latest milestone with any activity.

The adjacent `CHECKPOINT_CONTENT_BASELINE_*` fields (`_HEAD`, `_ORIGIN`, `_BRANCH`, `_STATUS`) were inspected and deliberately **not** corrected: the document's own Section 1 text (line 16) explicitly defines these as describing "the repository state this checkpoint content was **authored against**" — a fixed historical anchor point (the M028 implementation-freeze commit), not a live tracker of current HEAD. Correcting them to the current HEAD would misrepresent them as something they are explicitly documented not to be, and risks rewriting a historical record rather than fixing a genuine staleness defect. Only `LATEST_FROZEN_MILESTONE`, whose plain meaning is a current-truth claim with no such historical-anchor disclaimer, was corrected.

## 8. Owner Approval

The owner formally freezes the M035 scope via this document.

**M035 SCOPE APPROVED_AND_FROZEN.**

## 9. Official Milestone Name

Concrete Application Command Vertical Slice (Run Lifecycle Transition).

## 10. Frozen Mission Statement

Prove, with one concrete, minimal, real command, that the frozen `usecases` write-side application-invocation pattern's `save()`/`OptimisticConcurrencyConflict` contract — established and validated exclusively against `Campaign` via `PrepareCampaignForAuthorizationHandler` (M032) — genuinely generalizes to a second aggregate, without introducing a second Run transition, without introducing a third or fourth aggregate, and without introducing any framework, registry, or abstraction beyond what is already frozen.

## 11. Verified Architectural Gap

Of the three CQRS verbs the `usecases` layer exercises against a repository (`add()`, `get()`, `save()`), `add()` has generalized across two aggregates (`Campaign` M030, `Run` M033) and `get()` has generalized across two aggregates (`Campaign` M031, `Run` M034). `save()`/`OptimisticConcurrencyConflict` has been exercised exactly once — `Campaign` only, M032 — and never for any second aggregate. Independently verified: a repository-wide search finds zero reference to `RunRepository.save()`, `EvidencePackageRepository.save()`, or `ReviewRepository.save()` anywhere in `src/empirical_platform/usecases/`.

## 12. Frozen In-Scope Capability

- One concrete command representing "transition an existing Run from its current lifecycle state to the next state," carrying the minimal data `RunRepository.save()` and the target `Run` transition method already require.
- One concrete handler conforming to the frozen `CommandHandler` Protocol that loads the Run (via `RunRepository.get()` where the final design requires it), invokes one already-frozen `Run` transition method, and persists the result via `RunRepository.save(..., expected_persisted_version=...)`.
- Binding this handler to a `CommandEntryPoint` and invoking it, proving `save()`/`OptimisticConcurrencyConflict` holds for a second aggregate.
- Contract tests proving `CommandHandler` conformance.
- Real PostgreSQL success evidence, real PostgreSQL deterministic stale-version conflict evidence, and persisted-state verification.
- Narrowly required architecture evidence only, if genuinely justified.

## 13. Frozen Out-of-Scope Capabilities

A second Run transition; a generic Run lifecycle framework; Run creation changes; Run retrieval changes; Run listing/filtering/pagination; retry or backoff; automatic conflict recovery; runtime-ID regeneration; any Campaign command/query change, lookup, or mutation; `EvidencePackage` creation or retrieval; `Review` creation or retrieval; any generic save abstraction or concurrency framework; composition root; registry; dispatcher; mediator; query bus; command bus; service locator; DI framework; transport/API; caching; worker/queue/scheduler; audit integration; schema or migration changes; market-data/vendor/trading/execution behavior; MILESTONE-036 work of any kind.

## 14. Frozen Non-Goals

This milestone is not a general-purpose Run-mutation capability — it exercises exactly one lifecycle transition, not a generic state-machine framework. It is not the `EvidencePackage`/`Review` milestone. It does not decide whether `EvidencePackage` creation, a second Run transition, or retry-policy work comes next.

## 15. Frozen Dependencies

**Depends on (frozen, read-only):** M020 `RunRepository` Protocol (`get()`/`save()`) and `Run` aggregate, including all seven frozen transition methods; M023 concrete PostgreSQL `Run` repository adapter's `save()` implementation; M020/M023 `OptimisticConcurrencyConflict` contract, already proven for `Campaign` (M032); M027 `CommandHandler` Protocol; M029 `CommandEntryPoint`; M032's delivered `Campaign` lifecycle-transition slice (pattern reference only); M033's delivered `Run` creation slice (seeding); M034's delivered `Run` retrieval slice (usable for independent post-transition verification, not required).

**Does not depend on:** any `EvidencePackage`/`Review` material, any Campaign mutation work, any transport/entrypoint code, any composition-root abstraction.

## 16. Frozen Contracts Preserved

`Run` aggregate, its constructor, and all seven transition methods (M020/M012); `RunRepository` Protocol `get()`/`save()` signatures (M020); the concrete PostgreSQL `Run` repository adapter (M023); `CommandHandler[_CommandT_contra, _ResultT_co]` (M027); `CommandEntryPoint[CommandT, ResultT]` (M029); everything M030-M034 delivered.

## 17. Run Lifecycle Facts

Verified directly, not decided here: `Run` has seven frozen transition methods — `authorize` (CREATED→AUTHORIZED), `start_acquisition` (AUTHORIZED→ACQUIRING), `start_normalization` (ACQUIRING→NORMALIZING), `start_validation` (NORMALIZING→VALIDATING), `complete_execution` (VALIDATING→EXECUTION_COMPLETED), `cancel` (AUTHORIZED→CANCELLED), `fail` (ACQUIRING/NORMALIZING/VALIDATING→FAILED). Every transition advances `Run.version` and appends one `StateTransitionRecord` to `Run.transition_history`. `Run.append_manifest()` also advances `Run.version` while the aggregate remains in one of the `_MANIFEST_APPEND_STATES` (CREATED, AUTHORIZED, ACQUIRING, NORMALIZING, VALIDATING) — a fact preserved here because it establishes that version-advancement is not exclusive to lifecycle transitions, relevant to (but not resolving) the Design Mission's deterministic-conflict-mechanism question (Section 22). Which transition this milestone targets is **not decided by this freeze**.

## 18. Save and Optimistic-Concurrency Facts

`RunRepository.save(aggregate: Run, *, expected_persisted_version: AggregateVersion) -> SaveResult` is a frozen M020 signature, implemented by the concrete M023 `PostgresRunRepository.save()`. It raises `AggregateNotFound` when no persisted Run exists for the aggregate's identity, `OptimisticConcurrencyConflict` when the durable version does not match `expected_persisted_version`, and `InvalidAggregateForPersistence` when the in-memory aggregate is not valid for persistence — identical in kind to `CampaignRepository.save()`, already exercised by M032.

## 19. Identity Considerations

`RunRepository.get()` requires full `DomainIdentity[RunId]` (frozen identity model, established by M033/M034 precedent for Run operations). The exact identity representation this command's own contract carries is an open Design Mission question (Section 24) — not decided here.

## 20. Referential-Integrity Considerations

No cross-aggregate referential-integrity concern exists for this capability — it operates entirely within one already-existing `Run` row, requiring no `CampaignRepository` or any other aggregate's repository.

## 21. Existing Failure Paths

Repository-verified facts only: `RunRepository.get()` raises `AggregateNotFound` for a missing identity (already exercised, M034). `Run`'s transition methods raise `ValueError` when the current state does not permit the requested transition (frozen, M020, verified directly in `run/aggregate.py`'s `_transition()`). `RunRepository.save()` raises `AggregateNotFound`, `OptimisticConcurrencyConflict`, or `InvalidAggregateForPersistence` (frozen, M020/M023, already exercised for `Campaign`, M032). How the handler treats each is an open Design Mission question (Section 24).

## 22. PostgreSQL Conflict Feasibility

`PostgresRunRepository.save()` already implements the identical optimistic-concurrency mechanism M023 established and M032 already proved deterministic and testable for `Campaign` (via an independently-loaded second aggregate instance performing an interfering write before the first instance's `save()` call). Feasibility for `Run` is established by this identical mechanism existing and being already proven at the infrastructure level. The **exact** interfering-write mechanism for `Run` — which frozen transition or Run-owned mutation (e.g. a second `authorize()`-path instance, or `append_manifest()`, per Section 17's fact that both advance `Run.version`) will serve as the deterministic conflict producer — is an open Design Mission question (Section 24), genuinely unresolved because `Run` has no direct analogue to `Campaign.revise_scope_statement()` (a non-transition mutator M032 used for its own interfering write).

## 23. Architecture-Boundary Implications

`ALLOWED["usecases"] = {"shared", "identifiers", "campaign", "run"}` already grants `"run"` — verified directly in `tools/check_architecture.py`. No new permission is required on current evidence, since this capability uses only `RunRepository` and `Run`, both already importable from `usecases`. Whether any narrowly-scoped architecture-checker evidence is genuinely required (e.g. a new fixture proving something not already covered) is an open Design Mission question, not decided here.

## 24. Open Design Mission Questions

Not decided by this freeze: which of the seven frozen `Run` transition methods this milestone targets; the exact command type name, shape, and fields; the exact handler type name and module path; the exact identity representation the command carries; the `actor`/`occurred_at`/`correlation_id`/`reason` field choices; the `expected_persisted_version` acquisition model; the exact load/mutate/save sequence; the exact return type and whether `SaveResult` is exposed; error propagation or translation for `AggregateNotFound`/the transition-`ValueError`/`OptimisticConcurrencyConflict`; invalid-transition handling; transaction ownership; the exact deterministic PostgreSQL conflict-reproduction mechanism (Section 22); package exports; any architecture-test changes; exact test filenames; PostgreSQL fixture layout.

## 25. Acceptance Boundaries

This freeze is complete when: exactly one capability is frozen (Run lifecycle transition via `save()`); no class name, method signature, module path, transition-method selection, dependency-injection mechanism, transaction behavior, error hierarchy, or result-shape decision is fixed; every excluded capability is explicit; the freeze is independently reviewable without requiring the reviewer to resolve any open design question themselves.

## 26. Stop Conditions

This milestone stops at: one concrete command, one concrete handler, using `RunRepository.get()`/`save()` only; proof that the `usecases`/`CommandHandler`/`CommandEntryPoint` `save()`/`OptimisticConcurrencyConflict` pattern composes correctly for a second aggregate; contract, unit, architecture, and PostgreSQL integration test evidence. It does not continue into any second Run transition, `EvidencePackage`/`Review` work, composition-root work, retry-policy work, or transport work, regardless of how natural such an extension might appear during design or implementation.

## 27. Prohibited Expansion

No second Run transition or Run mutation beyond the one selected; no `EvidencePackage`/`Review` command or query; no composition root, registry, dispatcher, mediator, or service locator; no transport layer of any kind; no retry/backoff/idempotency policy; no generic read-model or projection framework; no MILESTONE-036 work.

## 28. Deferred Work

`EvidencePackage` creation and retrieval (future milestone, once Run's application-layer maturity — including this milestone — is complete); `Review` creation and retrieval (blocked behind `EvidencePackage`); retry-on-`OptimisticConcurrencyConflict` policy (genuinely closer to justifiable after this milestone provides a second data point, but still not authorized here); any composition-root abstraction beyond direct binding; any transport/entrypoint adapter; a second Campaign lifecycle transition (lower priority — does not close a cross-aggregate generalization gap); MILESTONE-036 and beyond.

## 29. M036 Boundary

This freeze authorizes work through MILESTONE-035 only. No MILESTONE-036 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 28's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-036's scope — that determination is explicitly reserved for MILESTONE-036's own independent, from-source scope-selection mission.

## 30. Design and Implementation Prohibition

This freeze authorizes scope only. It does not authorize design or implementation. No design document or implementation source for M035 exists as of this freeze (verified: no new command/handler module exists anywhere in `src/empirical_platform/usecases/` beyond the five already-frozen M030-M034 modules).

## 31. Preserved M020-M034 Authority

This freeze makes no change to any M020-M034 frozen contract, source file, test, or governance document. All M020-M034 authority remains exactly as previously frozen.

## 32. Final Status

**M035 SCOPE APPROVED_AND_FROZEN.**

M035 Design: NOT_STARTED.
M035 Implementation: NOT_STARTED.
M036: NOT_STARTED.

## 33. Next Permitted Action

**MILESTONE-035 DESIGN MISSION.**
