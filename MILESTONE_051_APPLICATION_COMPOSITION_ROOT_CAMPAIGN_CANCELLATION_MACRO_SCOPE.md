# MILESTONE-051 - Application Composition Root: Real End-to-End Campaign Cancellation - Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31) as part of one consolidated M051 mission: scope, design, and implementation together, followed by one independent review checkpoint.

**This is the second platform-integration milestone in the project's history, and the first to compose a write command — deliberately continuing, not repeating, the pivot M050 opened.**

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M051 frozen baseline | `6151fee11479a02207c271e84e79e430209705d0` (the final M050 Owner Freeze hash-recording HEAD; M050 fully `APPROVED_AND_FROZEN` at scope, design, and implementation) |

## 3. Fresh, Complete Architecture Inventory

Every prior milestone conclusion was independently re-derived from live source, not assumed.

### 3.A Domain-Completion Remaining Gaps

| Aggregate | Mutation methods | Proven | Unproven |
| --- | --- | --- | --- |
| Campaign | 8 | 2 (`prepare_for_authorization`, `cancel`) | 6 |
| Run | 8 | 2 (`authorize`, `fail`) | 6 |
| EvidencePackage | 5 | 4 | 1 (`invalidate`) |
| Review | 4 | 4 | 0 — complete (since M049) |

Every remaining Campaign/Run forward-pipeline transition (`record_authorization`, `activate`, `suspend`, `resume`, `complete`; `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`) independently confirmed to use a single-element `allowed_states` tuple against `_transition()` — the same shape already proven 10+ times since M030. `EvidencePackage.invalidate()` — the sole remaining gap for that aggregate — was independently re-verified this milestone: `add_criterion_result()`, `add_artifact_reference()`, and `seal()` all require `COLLECTING` explicitly (raise `ValueError` otherwise); none is reachable once a package is `SEALED`. **`EvidencePackage.invalidate()` has zero genuine, state-preserving interfering write available for a real `OptimisticConcurrencyConflict` reproduction** — the same finding M049's own review independently reached, reconfirmed fresh here rather than assumed by citation. Selecting it now would be the first "negative-transition axis" milestone in this project unable to meet the evidentiary bar every predecessor (M047, M048, M049) met.

One partial exception was found: `Run.cancel()` (`allowed_states=(RunLifecycleState.AUTHORIZED,)`) does have a genuine interferer — `append_manifest()` is independently confirmed reachable from `AUTHORIZED` (`_MANIFEST_APPEND_STATES` includes `CREATED`, `AUTHORIZED`, `ACQUIRING`, `NORMALIZING`, `VALIDATING`), a state M048's own `Run.fail()` never exercised it in (`Run.fail()`'s `allowed_states` is `(ACQUIRING, NORMALIZING, VALIDATING)` — `AUTHORIZED` is absent). `Run.cancel()` remains a legitimate future domain-transition candidate but repeats the same single-state `_transition()` shape structurally.

### 3.B Platform/Application-Integration Gaps — Independently Verified from Live Source

- `src/empirical_platform/entrypoints/` contains exactly `health.py`, `version.py`, and `get_campaign.py` (M050, frozen). **Exactly one composition root exists, and it composes a read-only query.** No write command has ever been composed through a production entrypoint — the `expected_persisted_version`/`OptimisticConcurrencyConflict` dimension, side-effect ordering, and `SaveResult` return handling remain completely unproven outside test fixtures.
- `CommandEntryPoint` (M029, frozen, `src/empirical_platform/application/command.py`) is the exact structural mirror of `QueryEntryPoint` (used by M050) — already frozen, never yet composed into a production entrypoint.
- M050's own Macro Scope document (Section 6, "Rejected Alternatives") explicitly named a write-command composition as **"a natural, well-motivated candidate for a future milestone, once the read-side pattern is independently reviewed and frozen."** M050 has now cleared two independent hostile macro reviews and an Owner Freeze — the condition M050 itself set is now satisfied.
- `registry/`, `audit/`, `governance/` remain literal empty stub packages (`"No business behavior is implemented."`), confirmed unchanged.

## 4. Leverage Reassessment

**Question, in the spirit of M050's own mandated reassessment: does composing the first write command through the platform-integration axis now offer higher leverage than either another domain transition or a repeat read-composition?**

**Answer: yes**, for four independently-verified reasons:

1. **A completely unproven architectural dimension.** M050 proved the read-composition shape works; it proved nothing about how a write command's `expected_persisted_version`/`OptimisticConcurrencyConflict` semantics, or a `SaveResult` return value, behave when routed through a real production entrypoint rather than a test fixture. This is the single largest remaining gap in the platform-integration axis, not a second data point on an already-answered question.
2. **Every remaining domain-transition candidate repeats an already-proven shape** (Section 3.A) — none would prove anything new about the domain layer.
3. **`EvidencePackage.invalidate()` cannot meet this project's own evidentiary bar** for genuine `OptimisticConcurrencyConflict` reproduction (Section 3.A) — selecting it now would be a regression in rigor, not a completion worth claiming.
4. **This exact next step was explicitly pre-authorized by M050's own governance**, conditioned on M050 itself being independently reviewed and frozen — a condition now met. Building it now closes the specific gap M050 itself named, rather than leaving it open indefinitely.

**This milestone deliberately deepens, not repeats, the M050 pivot.**

## 5. Selected Scope

One concrete, narrow composition: a real, production `entrypoints.cancel_campaign` module that composes — for the first time in production code — `resolve_foundation_config()` → `PostgresPersistenceService` → `PostgresRepositoryRuntime` (M025) → the already-frozen `CancelCampaignHandler`/`CancelCampaignCommand`/`SaveResult` (M047) → the already-frozen `CommandEntryPoint` (M029), invocable as a real CLI command (mirroring `get_campaign.py`'s own established style, registered as a new `[project.scripts]` entry) and proven end-to-end against real PostgreSQL, **including a genuine `OptimisticConcurrencyConflict` reproduction flowing through the entrypoint itself.**

`CancelCampaignCommand`/`CancelCampaignHandler` is selected over every other already-frozen write command because: (a) it pairs naturally with M050's own `get_campaign` composition — the same aggregate now has both a read and a write production entry point, the clearest possible demonstration that the pattern generalizes; (b) its own genuine `OptimisticConcurrencyConflict` evidence (via `revise_scope_statement()` reuse, from `DRAFT`) is already frozen since M047 — this milestone proves the entrypoint propagates that conflict correctly, without re-deriving any new domain-level conflict evidence; (c) it is the single most-precedented "cancel"-family command in the project (the first of the negative-transition axis, M047), lowering the risk that some unexamined domain edge case surfaces during composition.

**Zero new business capability.** Every domain type, command, handler, repository, and entry point this milestone touches is already frozen and unmodified. This milestone adds only the missing composition glue for exactly one write command — the second, deliberately different data point completing the platform-integration pattern M050 opened.

## 6. Rejected Alternatives

- **`EvidencePackage.invalidate()`** — rejected per Section 3.A/4; no genuine interfering write exists, so no genuine `OptimisticConcurrencyConflict` reproduction is possible; selecting it would be a rigor regression relative to M047-M049.
- **`Run.cancel()` or any other remaining domain transition** — rejected; repeats an already-proven single-state `_transition()` shape and would not close the platform-integration gap that is now this project's single largest unproven dimension.
- **A second read-composition (e.g., `entrypoints.get_review`, `entrypoints.get_run`)** — rejected; would repeat M050's own already-proven read shape and would not prove the unproven write/OCC dimension.
- **A generic command dispatcher or registry composing multiple commands** — rejected as premature framework-building; this milestone proves the wiring pattern for exactly one already-existing write command, explicitly, by hand, with no reflection, no dynamic handler discovery, and no registry lookup — identical discipline to M050.
- **Composing all remaining write commands in one milestone** — rejected; would violate the one-capability-per-milestone discipline maintained since M030, and would make the independent review's job disproportionate to the value of proving the write-composition pattern once.
- **A full HTTP/transport-layer API** — rejected as premature; a CLI entrypoint mirroring `get_campaign.py`'s own established pattern remains the narrowest possible real invocation surface.
- **Retry-on-conflict policy** — rejected; orthogonal to this milestone's goal (proving composition, not resilience), and every prior milestone has correctly deferred it.

## 7. In-Scope

- `src/empirical_platform/entrypoints/cancel_campaign.py`: a `run_cancel_campaign()` composition function (settings → service → repository runtime → handler → entry point → result, with deterministic cleanup identical in shape to `get_campaign.py`'s own corrected M050-Y-1 resource-lifecycle pattern) and a thin `main()` CLI wrapper (argument parsing, JSON output).
- One new `[project.scripts]` entry: `empirical-platform-cancel-campaign`.
- No architecture-checker change: `entrypoints` already permits `usecases`/`identifiers` (M050); `CancelCampaignCommand`/`CancelCampaignHandler` live in the already-permitted `usecases` package, and no new raw-driver import is introduced.
- Focused unit tests for the CLI argument-parsing/error-handling layer and for the composition function's own resource-lifecycle shape (using fake/stub composition, never touching real persistence), mirroring the M050-Y-1-corrected pattern from the start.
- A real PostgreSQL integration test exercising `run_cancel_campaign()` itself end-to-end: golden-path cancellation, missing-Campaign `AggregateNotFound`, invalid-state domain `ValueError`, and — the dimension M050 could not exercise — a genuine `OptimisticConcurrencyConflict` reproduction flowing through the entrypoint, reusing `revise_scope_statement()` as the interferer exactly as M047 established.

## 8. Out-of-Scope

- Any new business/domain capability of any kind (no new command, no new query, no domain-method change).
- Composition for any command/query beyond `CancelCampaignCommand`.
- A generic dispatcher, registry, or handler-discovery mechanism.
- Retry-on-conflict policy, transaction orchestration beyond what `PostgresPersistenceService`/`PostgresRepositoryRuntime` already provide.
- Any transport/HTTP/API layer.
- Any change to `Campaign`, `CampaignRepository`, `PostgresCampaignRepository`, `CancelCampaignCommand`, `CancelCampaignHandler`, `PostgresRepositoryRuntime`, `resolve_foundation_config`, `CommandEntryPoint`, `get_campaign.py`, or any other already-frozen contract.
- Any schema/migration change.
- MILESTONE-052 work of any kind.

## 9. Frozen Dependencies

`CancelCampaignCommand`/`CancelCampaignHandler` (M047), `PostgresCampaignRepository` (M023), `PostgresRepositoryRuntime` (M025), `PostgresPersistenceService` (M008/M023), `resolve_foundation_config`/`FoundationConfigSnapshot`/`PostgreSQLConfigSnapshot` (foundation), `CommandEntryPoint` (M029), `DomainIdentity`/`CampaignId`/`RuntimeIdentifier` (foundation), `AggregateVersion` (foundation), `SaveResult`/`AggregateNotFound`/`OptimisticConcurrencyConflict` (foundation) — all unmodified.

## 10. Failure Model

`run_cancel_campaign()` performs no exception translation. `AggregateNotFound` (missing Campaign), the domain `ValueError` (invalid source state), `OptimisticConcurrencyConflict` (stale `expected_persisted_version`), configuration errors, and any repository/connectivity failure propagate to the caller unchanged. The `try`/`finally` resource-ownership boundary is drawn exactly as corrected in M050 (M050-Y-1): the `try` block opens immediately after `PostgresPersistenceService` construction, `.initialize()` is its first statement, `.close()` runs unconditionally in `finally` — this milestone starts from the corrected shape, not the defective pre-M050-Y-1 one.

## 11. Persistence/Transaction Implications

`PostgresPersistenceService` is constructed once per invocation; its entire lifetime, including `.initialize()`, is owned by one `try`/`finally` block whose `finally` unconditionally calls `.close()`. `CancelCampaignHandler`'s own single `get()`→mutate→`save()` sequence (frozen since M047) is the entire unit of work; no new transaction primitive is introduced.

## 12. Risks

- This is the first production code path to compose a write command with real optimistic-concurrency semantics — the independent review must scrutinize the entrypoint's `OptimisticConcurrencyConflict` propagation with at least the same rigor as M050's read-side `AggregateNotFound` propagation, and with the same rigor M047's own review applied to the original domain-level conflict.
- Reusing `revise_scope_statement()` as the interferer requires the seeded Campaign to be cancelled from `DRAFT` specifically (the one allowed-state/interferer pairing that produces a genuine conflict without a second production command) — this must be verified, not assumed by citation from M047.
- The M050-Y-1 resource-lifecycle lesson must be applied from the start, not discovered by a second independent review: `.initialize()` must be the first statement inside the `try`, verified before any code is written, not retrofitted after.

## 13. M052 Boundary

This scope selects exactly one MILESTONE-051 capability. No MILESTONE-052 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. In particular, this scope does not commit to composing any further command/query in M052 — the next milestone's own scope mission must independently re-derive the next highest-leverage capability, exactly as this document did.

## 14. Hostile Self-Review

Every claim in Section 3 was independently verified by direct source inspection during this scope mission: `grep`/`Read` on all four aggregate files confirmed the exact mutation-method inventory and every `allowed_states`/`expected_state` argument cited; `EvidencePackage.invalidate()`'s lack of a genuine interferer was re-derived from `add_criterion_result()`/`add_artifact_reference()`/`seal()`'s own explicit `COLLECTING`-only guards, not assumed from M049's prior conclusion; `Run.cancel()`'s `append_manifest()` interferer availability was independently discovered via `_MANIFEST_APPEND_STATES`, cross-checked against `Run.fail()`'s own different `allowed_states` to confirm it would be a genuinely new state-context reuse; `entrypoints/` directory contents were read directly; M050's own scope document was read directly to confirm the write-command-as-next-step framing is genuinely present in its own text, not invented for this document.

## 15. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE.**
