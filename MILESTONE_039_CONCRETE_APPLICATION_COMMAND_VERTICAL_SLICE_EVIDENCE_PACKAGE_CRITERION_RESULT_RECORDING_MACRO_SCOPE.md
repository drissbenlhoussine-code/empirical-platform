# MILESTONE-039 - Concrete Application Command Vertical Slice (EvidencePackage Criterion-Result Recording) Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used in M036, M037, and M038. Not independently frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `35cbdd09792abedb41382098241f1c39eb889f25` (`docs: record M038 owner freeze commit hash`, pushed) |

## 3. Frozen Predecessor Chain

M020-M038 all `APPROVED_AND_FROZEN` at every stage, including M038's Owner Freeze (`MILESTONE_038_EVIDENCE_PACKAGE_COLLECTION_START_MACRO_MILESTONE_FREEZE.md`, freeze commit `cf3907a30ddbea6609be8ba322ff3f3c7cfb6bd7`, hash-recording commit `35cbdd09792abedb41382098241f1c39eb889f25`).

## 4. Fresh Architecture Inventory

Rebuilt directly against `src/empirical_platform/usecases/` (9 modules, verified via directory listing at the frozen baseline) and the frozen aggregate/repository contracts:

| Aggregate | Create | Retrieve | Transition/Save | Owned-collection append | Optimistic-conflict proof |
| --- | --- | --- | --- | --- | --- |
| Campaign | M030 | M031 | M032 | n/a | Yes (M032, `revise_scope_statement`) |
| Run | M033 | M034 | M035 | n/a | Yes (M035, `append_manifest`) |
| EvidencePackage | M036 | M037 | M038 (`start_collection`) | **none** | **disclosed non-goal for M038** (see Section 7) |
| Review | none | none | none | n/a | none |

Verified live: `grep -l "review" src/empirical_platform/usecases/*.py` matches nothing (9 modules, none touching `review`). `EvidencePackage.state == COLLECTING` is now reachable via a frozen application command (M038) for the first time — this unlocks two previously-premature capabilities (`add_criterion_result`, `add_artifact_reference`), both of which require `COLLECTING`.

## 5. Verified Architectural Gap

Two distinct gaps remain visible from live source:

1. **Owned-collection-append write pattern** — never proven anywhere in this project. Every write capability built so far (M030, M032, M033, M035, M036, M038) is either "create a new aggregate" or "transition aggregate lifecycle state." `add_criterion_result()`/`add_artifact_reference()` are a structurally different write: append an immutable value to an owned collection while **preserving** the current lifecycle state, advancing only the aggregate version.
2. **`Review` aggregate** — zero application-layer proof of any verb.

## 6. EvidencePackage Owned-Collection Method Inventory (Verified Live)

Read directly from `src/empirical_platform/evidence/package.py`: `add_criterion_result(result: CriterionResult)` — requires `state == COLLECTING`, requires `result.evidence_package_id == identity.governance_id`, rejects duplicate `criterion_id`, advances version, **does not change state**. `add_artifact_reference(reference: ArtifactReference)` — requires `state == COLLECTING`, rejects duplicate `value`, advances version, **does not change state**. `seal()` requires **both** at least one `CriterionResult` and at least one `ArtifactReference` present (verified directly: `seal()` raises `ValueError` on either being empty) — both owned-collection-append capabilities are therefore genuine prerequisites for `seal()`, not merely plausible next steps.

## 7. Critical Fresh Finding — Closes M038's Disclosed Gap

M038's own Owner Freeze (Section 32/33) disclosed that `EvidencePackage` had no non-transition, state-preserving mutation available while `INITIALIZED`, so no genuine PostgreSQL `OptimisticConcurrencyConflict` reproduction was possible for `start_collection()`. **Once a package reaches `COLLECTING` (now reachable via M038), both `add_criterion_result()` and `add_artifact_reference()` are themselves non-transition, state-preserving, version-advancing mutations** — exactly the shape `Campaign.revise_scope_statement()` and `Run.append_manifest()` provided for their own aggregates. Selecting either capability as M039's scope closes the real-conflict gap M038 could not close, using a second call to the **other** owned-collection method (or a second call to the same method with a non-colliding value) as the interfering write.

## 8. Candidates Considered

1. **EvidencePackage criterion-result recording (`add_criterion_result`)** — closes a genuinely new write-pattern gap (Section 5.1); unlocks a real PostgreSQL `OptimisticConcurrencyConflict` reproduction (Section 7); `CriterionResult` is the primary evidentiary content the aggregate exists to hold; a hard prerequisite for `seal()`.
2. **EvidencePackage artifact-reference recording (`add_artifact_reference`)** — structurally identical value to Candidate 1; equally valid; not selected this milestone only because exactly one capability must be chosen (Section 10) and criterion results are the primary evaluative content, artifact references the supporting evidence.
3. **EvidencePackage collection completion (`seal`)** — requires **both** Candidates 1 and 2 to have already produced at least one record each; not independently reachable this milestone (Section 6).
4. **EvidencePackage invalidation (`invalidate`)** — requires `SEALED`, itself gated behind Candidate 3; not reachable.
5. **Review creation** — now FK-viable and, by the strict "complete one aggregate's create-retrieve-transition trio before opening the next" cadence M037/M038 both used, arguably no longer blocked (`EvidencePackage`'s own trio closed at M038). Considered seriously, not dismissed by reflex. Rejected this milestone because: (a) it would repeat the already-three-times-proven create/retrieve/transition CQRS generalization pattern rather than close the still-fully-open owned-collection-append gap (Section 5.1), the higher-leverage architectural question by this project's own repeated evaluation criterion (reject repeating an already-proven pattern when an unproven one remains); (b) semantically, creating a `Review` against an `EvidencePackage` that cannot yet be `SEALED` (no criterion results/artifact references exist) does not reflect the real business flow ("review completed evidence"), even though nothing at the persistence layer would reject it.
6. **Retry-on-conflict policy** — still no evidenced concrete need; deferred by every milestone since M029 for the identical reason.
7. **Composition root / registry / dispatcher / transport-neutral invocation** — no repeated-handler-need evidence; all 9 existing `usecases` modules use direct test-only construction with zero friction.
8. **Audit/governance runtime** — no scope authority or frozen contract exists for this.

## 9. Selected M039 Scope

One concrete command recording a `CriterionResult` on an existing, `COLLECTING` `EvidencePackage`, via `EvidencePackage.add_criterion_result()` then `EvidencePackageRepository.save()`.

## 10. Why This Scope Is Next

Candidate 1 closes the highest-value remaining architectural gap (a genuinely new, never-proven write pattern), is a hard prerequisite for the aggregate's own eventual completion (`seal()`), and — uniquely among every open candidate — restores this project's ability to genuinely reproduce `OptimisticConcurrencyConflict` against real PostgreSQL for `EvidencePackage`, closing the gap M038 explicitly disclosed rather than silently left open. Candidate 2 is deferred, not rejected, as the direct symmetric follow-on. Candidate 5 (Review creation) is deferred on architectural-leverage grounds, independently reasoned rather than assumed premature by reflex.

## 11. In-Scope Capability

Recording of exactly one new `CriterionResult` on an existing `EvidencePackage`, via `EvidencePackageRepository.get()` then `.save()`, guarded by caller-supplied `expected_persisted_version`.

## 12. Out-of-Scope Capabilities

`add_artifact_reference()`, `seal()`, `invalidate()`; any `Review` work; retry policy; composition root; transport/API layer; any second command or capability; listing/retrieval of recorded `CriterionResult`s.

## 13. Frozen Dependencies

`EvidencePackageRepository` (M020), `PostgresEvidencePackageRepository.get()`/`.save()` (M023), `EvidencePackage.add_criterion_result()` (M020), `CriterionResult` (M020), `SaveResult`/`OptimisticConcurrencyConflict`/`AggregateNotFound` (M020), `CommandHandler` Protocol (M027), `CommandEntryPoint` (M029), `StartEvidencePackageCollectionHandler` (M038, used only as test-fixture scaffolding to reach `COLLECTING`).

## 14. Open Design Questions

Deferred to the Macro Design document: exact command field set (`CriterionResult` has `evidence_package_id`, `criterion_id`, `recorded_at`, `result_label`, `summary`, `evidence_references` — how these map to command fields and how `evidence_package_id` is derived); the deterministic PostgreSQL conflict mechanism (now genuinely available per Section 7, exact interfering write to be selected); duplicate-`criterion_id` behavior; invalid-state (`not COLLECTING`) behavior; result contract (`SaveResult`, mirroring M032/M035/M038).

## 15. Architecture-Boundary Considerations

None expected: `usecases` already has `evidence` in `ALLOWED` (since M036); this is a write-side command using an already-permitted import edge. To be independently re-verified live during implementation, not assumed.

## 16. Concurrency Feasibility

Confirmed live (Section 7): a genuine PostgreSQL `OptimisticConcurrencyConflict` reproduction is feasible for this capability, using an independently loaded second instance calling a different owned-collection method (`add_artifact_reference()`) as the interfering write — the exact mechanism to be finalized in the Macro Design.

## 17. Stop Conditions / Prohibited Expansion

No `add_artifact_reference`/`seal`/`invalidate` call of any kind. No `Review` module reference. No composition root, registry, or dispatcher. No MILESTONE-040 work.

## 18. M040 Boundary

This scope document authorizes work through MILESTONE-039 candidate scope selection only. No MILESTONE-040 capability, terminology, or forward commitment is made anywhere in this document.

## 19. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Not independently reviewed or frozen — proceeds directly into the Macro Design within this same mission, per the active protocol.
