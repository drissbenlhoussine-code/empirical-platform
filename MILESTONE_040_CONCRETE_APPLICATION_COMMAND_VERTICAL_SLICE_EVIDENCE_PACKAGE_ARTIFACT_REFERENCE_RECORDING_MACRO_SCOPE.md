# MILESTONE-040 - Concrete Application Command Vertical Slice (EvidencePackage Artifact-Reference Recording) Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used in M036 through M039. Not independently frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `0fc2e29b4420ec51b0fcda56d0d3892702d1d8ed` (`docs: record M039 owner freeze commit hash`, pushed) |

## 3. Frozen Predecessor Chain

M020-M039 all `APPROVED_AND_FROZEN` at every stage, including M039's Owner Freeze (`MILESTONE_039_EVIDENCE_PACKAGE_CRITERION_RESULT_RECORDING_MACRO_MILESTONE_FREEZE.md`, freeze commit `e7c1ae10bea6eada60a6ed4aa39cffa2b902bf6c`, hash-recording commit `0fc2e29b4420ec51b0fcda56d0d3892702d1d8ed`).

## 4. Fresh Architecture Inventory

Rebuilt directly against `src/empirical_platform/usecases/` (10 modules, verified via directory listing at the frozen baseline) and the frozen aggregate/repository contracts:

| Aggregate | Create | Retrieve | Transition/Save | Owned-collection append | Optimistic-conflict proof |
| --- | --- | --- | --- | --- | --- |
| Campaign | M030 | M031 | M032 | n/a | Yes (M032) |
| Run | M033 | M034 | M035 | n/a | Yes (M035) |
| EvidencePackage | M036 | M037 | M038 (`start_collection`) | `add_criterion_result` (M039) — `add_artifact_reference` **none** | Yes (M039, genuine) |
| Review | none | none | none | n/a | none |

Verified live: `grep -l "review" src/empirical_platform/usecases/*.py` matches nothing (10 modules). `add_artifact_reference()` is the only remaining `COLLECTING`-reachable `EvidencePackage` capability with zero application-layer proof.

## 5. EvidencePackage Method Inventory Re-Verified (Live)

`start_collection()` (M038, frozen), `add_criterion_result()` (M039, frozen), `add_artifact_reference()` (**unproven**), `seal()` (**unproven**, requires both `criterion_results` and `artifact_references` non-empty), `invalidate()` (**unproven**, requires `SEALED`).

**Critical fresh finding on `seal()` reachability:** `seal()`'s own precondition requires `artifact_references` to be non-empty. No frozen application command can currently produce that state — only `add_artifact_reference()` (unproven) can. Selecting `seal()` this milestone would require the integration test's own precondition setup to bypass the application layer (direct domain-object mutation) for one half of `seal()`'s two-collection precondition, breaking this project's established pattern (verified across M030-M039: every prior milestone's integration-test setup satisfies all of a command's own preconditions using already-frozen application commands, never a bypass for the very capability class being proven). `seal()` is therefore not independently reachable this milestone without a scaffolding compromise, matching exactly the same reasoning that made `add_criterion_result()`/`add_artifact_reference()` themselves unreachable before M038 proved `start_collection()`.

## 6. ArtifactReference Shape — Verified Live, Simpler Than CriterionResult

`ArtifactReference(value: str)` — a single-field frozen dataclass (`src/empirical_platform/evidence/package.py`), unlike `CriterionResult`'s seven fields. Critically, **`ArtifactReference` carries no `evidence_package_id` field at all** — the ownership-derivation question M039's design resolved (Section 16 of that freeze) does not arise here; there is nothing to derive. `add_artifact_reference()` itself mirrors `add_criterion_result()`'s structure exactly: requires `COLLECTING`, rejects a duplicate `value`, advances `version`, does not change `state`.

## 7. Candidates Considered

1. **EvidencePackage artifact-reference recording (`add_artifact_reference`)** — the direct symmetric follow-on to M039, deferred there for exactly this reason (M039 scope Section 8, Candidate 2). Closes the last unproven `COLLECTING`-reachable capability. Domain-reachable now via already-frozen commands only (M036 create → M038 start_collection).
2. **EvidencePackage completion/sealing (`seal`)** — genuinely higher architectural novelty (a two-collection precondition, never proven before) but not independently reachable without a scaffolding compromise (Section 5). Deferred, not rejected — becomes cleanly reachable once Candidate 1 is frozen.
3. **EvidencePackage failure/invalidation (`invalidate`)** — requires `SEALED`, itself gated behind Candidate 2. Not reachable.
4. **Review creation** — FK-viable (verified against `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py`: `review.target_evidence_package_id -> evidence_package.governance_id`, no state constraint at the persistence layer), and `Review`'s own constructor (`ReviewTargetReference`, `ReviewerReference`) was independently re-verified this session as unchanged. **Not selected merely because the FK exists** (explicitly considered and rejected on that basis): `EvidencePackage`'s owned-collection-append write vocabulary is still incomplete (`add_artifact_reference` unproven), and the real-world business flow this project's own domain models (`Review` targeting an `EvidencePackage`) implies reviewing *completed* evidence — `EvidencePackage` cannot even reach `SEALED` yet (Section 5), reinforcing rather than merely repeating M039's own identical reasoning for deferral.
5. **Review retrieval** — depends on Review creation. Not reachable.
6. **Review lifecycle/save** — depends on Review creation. Not reachable.
7. **Retry-on-conflict policy** — still no evidenced concrete need; deferred by every milestone since M029 for the identical reason.
8. **Composition root / registry / dispatcher / transport-neutral invocation** — no repeated-handler-need evidence; all 10 existing `usecases` modules use direct test-only construction with zero friction.
9. **Audit/governance runtime** — no scope authority or frozen contract exists for this.

## 8. Selected M040 Scope

One concrete command recording an `ArtifactReference` on an existing, `COLLECTING` `EvidencePackage`, via `EvidencePackage.add_artifact_reference()` then `EvidencePackageRepository.save()`.

## 9. Why This Scope Is Next

Candidate 1 is the only candidate reachable this milestone without a scaffolding compromise (Section 5), completes `EvidencePackage`'s owned-collection-append vocabulary (both collection types now proven), and is a hard, now-final prerequisite for `seal()` to become cleanly reachable at M041 using only frozen application commands for setup — exactly the same dependency discipline this project applied at every prior milestone boundary (M033 could not begin before M030-M032 closed; M036 could not begin before M030-M035 closed the `add()`/`get()`/`save()` generalization question; M038 could not close a real conflict gap before `COLLECTING` was reachable).

## 10. In-Scope Capability

Recording of exactly one new `ArtifactReference` on an existing `EvidencePackage`, via `EvidencePackageRepository.get()` then `.save()`, guarded by caller-supplied `expected_persisted_version`.

## 11. Out-of-Scope Capabilities

`add_criterion_result()` (already frozen, M039); `seal()`; `invalidate()`; any `Review` work; retry policy; composition root; transport/API layer; any second command or capability; listing/retrieval of recorded `ArtifactReference`s.

## 12. Frozen Dependencies

`EvidencePackageRepository` (M020), `PostgresEvidencePackageRepository.get()`/`.save()` (M023), `EvidencePackage.add_artifact_reference()` (M020), `ArtifactReference` (M020), `SaveResult`/`OptimisticConcurrencyConflict`/`AggregateNotFound` (M020), `CommandHandler` Protocol (M027), `CommandEntryPoint` (M029), `StartEvidencePackageCollectionHandler` (M038, test-fixture scaffolding to reach `COLLECTING`).

## 13. Open Design Questions

Deferred to the Macro Design document: exact command field set (no `evidence_package_id`-derivation question, per Section 6 — likely `identity`, `expected_persisted_version`, `value`); the deterministic PostgreSQL conflict mechanism (using `add_criterion_result()` as the interfering write — now available as a frozen sibling method, mirroring M039's own reverse pairing); duplicate-`value` behavior; invalid-state behavior; result contract (`SaveResult`).

## 14. Lifecycle Prerequisites

`EvidencePackage` must already be `COLLECTING` (reachable via the frozen M036 create + M038 `start_collection` commands, no scaffolding bypass required).

## 15. Architecture-Boundary Considerations

None expected: `usecases` already has `evidence` in `ALLOWED` (since M036); this is a write-side command using an already-permitted import edge. To be independently re-verified live during implementation, not assumed.

## 16. Concurrency Feasibility

Confirmed live (Section 6/13): a genuine PostgreSQL `OptimisticConcurrencyConflict` reproduction is feasible, using an independently loaded second instance calling `add_criterion_result()` (a legitimate, state-preserving, now-frozen-as-production-capability sibling method) as the interfering write — the exact mechanism to be finalized in the Macro Design.

## 17. Risks

None beyond those already inherent in the frozen design. This is the lowest-risk EvidencePackage candidate remaining: simplest command shape of any milestone to date (Section 6), identical proven pattern to M039, genuine conflict evidence available.

## 18. M041 Boundary

This scope document authorizes work through MILESTONE-040 candidate scope selection only. No MILESTONE-041 capability, terminology, or forward commitment is made anywhere in this document. `seal()` is identified as the natural M041 candidate (Section 7, Candidate 2) but this is descriptive, not a binding selection.

## 19. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Not independently reviewed or frozen — proceeds directly into the Macro Design within this same mission, per the active protocol.
