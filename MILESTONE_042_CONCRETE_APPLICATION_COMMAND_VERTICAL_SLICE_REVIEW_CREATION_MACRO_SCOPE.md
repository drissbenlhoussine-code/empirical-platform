# MILESTONE-042 - Concrete Application Command Vertical Slice (Review Creation) Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used in M036 through M041. Not independently frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `95c52eaeeb28c65f8eabf8feccace7d24cb6967f` (`docs: record M041 owner freeze commit hash`, pushed) |

## 3. Frozen Predecessor Chain

M020-M041 all `APPROVED_AND_FROZEN` at every stage, including M041's Owner Freeze (`MILESTONE_041_EVIDENCE_PACKAGE_SEALING_MACRO_MILESTONE_FREEZE.md`, freeze commit `22cd0afdb84c9a789f380b67db72614b8231bd39`, hash-recording commit `95c52eaeeb28c65f8eabf8feccace7d24cb6967f`).

## 4. Fresh, Complete Architecture Inventory

Rebuilt directly against live source, not assumed from any prior milestone's own conclusions.

**Directory-level inventory** (`src/empirical_platform/`): `acquisition`, `archive`, `audit`, `decision_candidate`, `governance`, `normalization`, `registry`, `validation` are all empty namespace placeholders (zero non-`__init__.py` files) — confirmed via direct `find`, out of scope for any CQRS vertical-slice work. `application` (`command.py`/`query.py`, frozen M027/M029), `datasets` (`manifest.py`, frozen M021), `identifiers` (frozen M020), `entrypoints` (`health.py`/`version.py`, unrelated infra) are all frozen, stable infrastructure with no open gaps.

**Aggregate-level capability matrix** (verified live against `src/empirical_platform/usecases/*.py`, 12 modules):

| Aggregate | Create | Retrieve | Transition/Save | Owned-collection append | Conflict proof |
| --- | --- | --- | --- | --- | --- |
| Campaign | M030 | M031 | M032 (`prepare_for_authorization`) | n/a | Yes (M032) |
| Run | M033 | M034 | M035 (`authorize`) | n/a | Yes (M035) |
| EvidencePackage | M036 | M037 | M038 (`start_collection`), M041 (`seal`) | M039 (`add_criterion_result`), M040 (`add_artifact_reference`) | Yes (M039, M040, both genuine) |
| Review | **none** | **none** | **none** | **none** | **none** |

`Review` is the only aggregate in the entire domain model with **zero** application-layer proof of any verb. This is the single largest remaining architectural gap.

## 5. Review Aggregate — Fully Re-Inspected Live

`src/empirical_platform/review/aggregate.py`: constructor `Review(*, identity: DomainIdentity[ReviewId], target: ReviewTargetReference, reviewer: ReviewerReference)`, starting state `ASSIGNED`. Lifecycle: `ASSIGNED` → (`start()`) → `IN_PROGRESS` → (`add_finding()`, owned-collection append, mirrors `EvidencePackage`'s M039/M040 pattern) → (`complete()`, requires ≥1 finding) → `COMPLETED`; `cancel()` reachable from `ASSIGNED` or `IN_PROGRESS` → `CANCELLED`. `ReviewTargetReference(evidence_package_id: EvidencePackageId)` and `ReviewerReference(value: str)` are both simple, already-frozen (M020) value objects.

## 6. Review Infrastructure — Fully Re-Verified Live, Already Frozen

`ReviewRepository` Protocol (`add`/`get`/`save`, M020) — identical shape to every other repository. `PostgresReviewRepository` (`src/empirical_platform/shared/persistence/postgres_repositories/review_repository.py`) — `get`/`add`/`save` all implemented (M023). `ConcreteReviewMapper` (M021/M023) — fully implemented `to_durable_record`/`from_durable_record`. Schema (`migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py`): `review` table with `governance_id` (unique), `target_evidence_package_id` (FK → `evidence_package.governance_id`, no state constraint), `reviewer_reference`, `lifecycle_state`, `disposition`/`final_disposition_rationale`/`cancellation_reason` (all nullable), `version`, `next_transition_sequence`; `review_finding` (FK → `review.runtime_id`) and `review_transition` (FK → `review.runtime_id`) tables already exist. **Zero infrastructure work required for Review creation** — the identical situation every prior "create" milestone (M030, M033, M036) started from.

## 7. Why Review Was Not Selected Sooner — Verified, Not Assumed

M037, M039, M040, and M041 each independently evaluated Review creation and deferred it — every time for a verifiable, evidence-based reason, re-confirmed here rather than taken on faith: M037/M039/M040 deferred it because `EvidencePackage`'s own create-retrieve-transition/owned-collection vocabulary was still incomplete, preserving this project's twice-then-repeatedly-validated "complete one aggregate before opening the next" cadence. M041 deferred it a fourth time specifically because `EvidencePackage` could not yet reach a genuinely `SEALED` state via frozen commands — and explicitly named this as the reason Review would become appropriate *after* M041, not before (M041 scope Section 7). M041 is now frozen; `EvidencePackage.seal()` is a real, frozen, production capability. The precondition every prior deferral was waiting on is now satisfied.

## 8. Candidates Considered

1. **Review creation** — closes the last completely unproven aggregate; zero new infrastructure required; explicitly and repeatedly pre-justified as the correct next step once `EvidencePackage` could reach `SEALED` (Section 7), which is now true.
2. **`EvidencePackage.invalidate()`** — the one remaining unproven `EvidencePackage` transition (`SEALED` → `INVALIDATED`). Domain-reachable via frozen commands (M036 → M038 → M039 → M040 → M041 → `invalidate()`). Rejected: `EvidencePackage` already has full CQRS proof (create/retrieve/transition/owned-collection-append, with genuine conflict evidence twice over); `invalidate()` would merely repeat an already-four-times-proven single-precondition-transition pattern (M032, M035, M038, M041) on an aggregate with no remaining architectural gap, versus closing the one aggregate with zero proof of anything. Lower leverage by a wide margin.
3. **Review retrieval** (`GetReviewQuery`) — depends on Review creation existing first. Not reachable as a standalone milestone; deferred to a future milestone once creation is frozen, mirroring the M030→M031, M033→M034, M036→M037 create-then-retrieve cadence.
4. **Review lifecycle transitions** (`start()`, `add_finding()`, `complete()`, `cancel()`) — each depends on Review creation existing first. Not reachable this milestone.
5. **Retry-on-`OptimisticConcurrencyConflict` policy** — still no evidenced concrete need; deferred by every milestone since M029 for the identical reason, re-verified here: no repeated-handler-need evidence exists anywhere in the 12 existing `usecases` modules.
6. **Composition root / registry / dispatcher / transport-neutral invocation** — no repeated-handler-need evidence; every milestone since M030 has used direct test-only construction with zero friction.
7. **Audit/governance runtime** — `audit`/`governance` are empty placeholder namespaces (Section 4) with no scope authority or frozen contract; selecting either would require its own from-scratch architecture-inventory justification, not a byproduct of this one.
8. **Any further Campaign/Run capability** — both aggregates already have all proven verbs with genuine conflict evidence; no architectural gap remains for either.

## 9. Selected M042 Scope

One concrete command creating a new `Review` targeting an existing `EvidencePackage`, via `ReviewRepository.add()` — mirroring the exact `add()`-only, FK-enforced, referential-integrity-via-real-database-constraint pattern already twice-proven by M033 (`Run` → `Campaign` FK) and M036 (`EvidencePackage` → `Run` FK), now applied to `Review` → `EvidencePackage`.

## 10. Why This Scope Is Next

Review creation is the only candidate that (a) closes a genuine, currently-zero architectural gap rather than repeating an already-proven pattern on a fully-proven aggregate, (b) requires zero new infrastructure (repository, adapter, mapper, and schema are all already frozen), and (c) was explicitly, repeatedly, and verifiably pre-justified by name across four prior scope documents as the correct next step once `EvidencePackage` reached `SEALED` — a condition M041 just satisfied. No other candidate is simultaneously this well-prepared and this high-leverage.

## 11. In-Scope Capability

Creation of exactly one new `Review`, targeting an existing `EvidencePackage` by governance ID, with a caller-supplied reviewer reference, via `ReviewRepository.add()`.

## 12. Out-of-Scope Capabilities

`Review` retrieval, `start()`, `add_finding()`, `complete()`, `cancel()`; `EvidencePackage.invalidate()`; retry policy; composition root; transport/API layer; any second command or capability.

## 13. Frozen Dependencies

`ReviewRepository` (M020), `PostgresReviewRepository.add()` (M023), `Review`/`ReviewTargetReference`/`ReviewerReference` constructors (M020), `EvidencePackageId` (M020), `SaveResult`/`AggregateAlreadyExists`/`FoundationError` (M020), `CommandHandler` Protocol (M027), `CommandEntryPoint` (M029), `CreateEvidencePackageHandler` (M036)/`StartEvidencePackageCollectionHandler` (M038)/`RecordEvidencePackageCriterionResultHandler` (M039)/`RecordEvidencePackageArtifactReferenceHandler` (M040)/`SealEvidencePackageHandler` (M041) — as frozen test-fixture scaffolding to reach a real, sealed `EvidencePackage` target for PostgreSQL evidence.

## 14. Open Design Questions

Deferred to the Macro Design document: exact command field set (likely mirroring `CreateEvidencePackageCommand`'s caller-supplied-governance/handler-generated-runtime identity model, given the direct structural parallel); whether the target `EvidencePackage` must be `SEALED` at the domain/application level or only FK-referenced (the schema enforces no state constraint — verified in Section 6); duplicate governance-ID/runtime-ID/missing-target evidence strategy (mirroring M033/M036).

## 15. Lifecycle Prerequisites

An existing `EvidencePackage` referenced by governance ID (the schema's FK requires only that the row exist, not any particular lifecycle state — verified in Section 6). No `Review`-side precondition, since this is a creation command.

## 16. Architecture-Boundary Considerations

`usecases` does **not** currently have `review` in `ALLOWED` — verified live against `tools/check_architecture.py` (`"usecases": {"shared", "identifiers", "campaign", "run", "evidence"}`). Exactly one narrow addition (`"review"`) will be required, mirroring the identical M033/M036 precedent. Required fixture maintenance identified live: `tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_review_import.py` (proves `usecases` cannot import `review`) will become obsolete and must be removed along with its corresponding assertion in `test_module_boundaries.py`; a new reverse-direction fixture (`review` may not import `usecases`) does not yet exist for `review` (unlike `campaign`/`run`/`evidence`, which all already have this fixture) and should be added to close that gap, mirroring the M036 precedent exactly.

## 17. Concurrency Feasibility

Not applicable to this milestone — `add()` has no `expected_persisted_version` concept; duplicate-governance-ID and duplicate-runtime-ID behavior (both proven via the real database's `UNIQUE` constraints) are the relevant evidence categories, mirroring M033/M036.

## 18. Risks

Low. This is the best-precedented candidate available: two prior milestones (M033, M036) have already proven the exact `add()`-with-real-FK pattern this milestone applies a third time, to a different aggregate pair.

## 19. M043 Boundary

This scope document authorizes work through MILESTONE-042 candidate scope selection only. No MILESTONE-043 capability, terminology, or forward commitment is made anywhere in this document. `Review` retrieval and lifecycle transitions are identified as natural future candidates (Section 8, Candidates 3-4) but this is descriptive, not a binding selection.

## 20. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Not independently reviewed or frozen — proceeds directly into the Macro Design within this same mission, per the active protocol.
