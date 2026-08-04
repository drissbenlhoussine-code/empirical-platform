# MILESTONE-041 - Concrete Application Command Vertical Slice (EvidencePackage Sealing) Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used in M036 through M040. Not independently frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `917bd9aa80ce5168d416a0501ae72befad7bd8a8` (`docs: record M040 owner freeze commit hash`, pushed) |

## 3. Frozen Predecessor Chain

M020-M040 all `APPROVED_AND_FROZEN` at every stage, including M040's Owner Freeze (`MILESTONE_040_EVIDENCE_PACKAGE_ARTIFACT_REFERENCE_RECORDING_MACRO_MILESTONE_FREEZE.md`, freeze commit `62dd6595ce6d039f67c25ebc891b1cd4efab1e73`, hash-recording commit `917bd9aa80ce5168d416a0501ae72befad7bd8a8`).

## 4. Fresh Architecture Inventory

Rebuilt directly against `src/empirical_platform/usecases/` (11 modules, verified via directory listing at the frozen baseline) and the frozen aggregate/repository contracts:

| Aggregate | Create | Retrieve | Transition/Save | Owned-collection append | Conflict proof |
| --- | --- | --- | --- | --- | --- |
| Campaign | M030 | M031 | M032 | n/a | Yes |
| Run | M033 | M034 | M035 | n/a | Yes |
| EvidencePackage | M036 | M037 | M038 (`start_collection`) | `add_criterion_result` (M039), `add_artifact_reference` (M040) | Yes (M039, M040 — both genuine) |
| Review | none | none | none | n/a | none |

`EvidencePackage`'s owned-collection-append vocabulary is now complete. `seal()` and `invalidate()` remain the only unproven `EvidencePackage` capabilities.

## 5. seal() Reachability — Verified Live, Newly Unlocked

Read directly from `src/empirical_platform/evidence/package.py`: `seal(*, actor, occurred_at, correlation_id=None, reason=None)` requires **both** `criterion_results` and `artifact_references` non-empty (each independently raises `ValueError` if empty), and requires `state == COLLECTING` (enforced by `_transition`'s `expected_state` check). **For the first time**, all of `seal()`'s own preconditions are satisfiable using only frozen application commands: M036 (`add`) → M038 (`start_collection`) → M039 (`add_criterion_result`) → M040 (`add_artifact_reference`) → `seal()`. This is the exact completion the M040 scope document (Section 9) anticipated but did not select.

## 6. invalidate() Reachability — Verified Live, Still Gated

`invalidate(*, reason, actor, occurred_at, correlation_id=None)` requires `state == SEALED`. Since `seal()` is not yet frozen, `invalidate()` remains unreachable via frozen commands this milestone — gated behind Candidate 1 below, exactly as `seal()` was gated behind M039/M040 until now.

## 7. Review Re-Evaluated a Fourth Time — Verified Live

`ReviewRepository` (`add`/`get`/`save`) frozen since M020. FK: `review.target_evidence_package_id -> evidence_package.governance_id`, no state constraint enforced at the persistence layer (re-verified against `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py`). `Review`'s constructor (`ReviewTargetReference`, `ReviewerReference`) unchanged since first inspected at M038.

**Still not selected, for the strongest reason yet:** after this milestone freezes `seal()`, `EvidencePackage` will finally be able to reach a genuinely `SEALED` state via frozen commands — meaning a *future* Review-creation milestone can, for the first time, construct integration-test fixtures that target a truly completed package, matching the real-world semantics this project's own domain models imply (reviewing finished evidence, not an in-progress collection). Selecting Review now, one milestone early, would forfeit that alignment for no compensating benefit — `seal()` itself remains an open, high-value, fully-reachable gap regardless.

## 8. Candidates Considered

1. **EvidencePackage sealing (`seal`)** — the last unproven `COLLECTING`-reachable transition; closes `EvidencePackage`'s remaining lifecycle-completion gap; now fully reachable via frozen commands only (Section 5); a genuinely novel pattern never proven before (a transition gated by two independent, cross-collection, non-empty preconditions simultaneously).
2. **EvidencePackage invalidation (`invalidate`)** — requires `SEALED`, itself gated behind Candidate 1 (Section 6). Not reachable.
3. **Review creation** — FK-viable but deliberately deferred a fourth time (Section 7) to preserve semantic alignment with a genuinely `SEALED` target.
4. **Review retrieval** — depends on Review creation. Not reachable.
5. **Review lifecycle/save** — depends on Review creation. Not reachable.
6. **Retry-on-conflict policy** — still no evidenced concrete need; deferred by every milestone since M029 for the identical reason.
7. **Composition root / registry / dispatcher / transport-neutral invocation** — no repeated-handler-need evidence; all 11 existing `usecases` modules use direct test-only construction with zero friction.
8. **Audit/governance runtime** — no scope authority or frozen contract exists for this.

## 9. Selected M041 Scope

One concrete command transitioning an existing, `COLLECTING` `EvidencePackage` to `SEALED`, via `EvidencePackage.seal()`, guarded by the frozen two-collection precondition already enforced by the domain model itself.

## 10. Why This Scope Is Next

Candidate 1 is the only candidate reachable this milestone using exclusively frozen application commands for its own precondition setup (Section 5) — exactly the discipline M040's own scope document established when excluding `seal()` there. It closes `EvidencePackage`'s lifecycle-completion gap and, uniquely, unlocks a semantically sound Review-creation milestone as the natural next step after this one, rather than before it.

## 11. In-Scope Capability

Transition of exactly one existing, `COLLECTING` `EvidencePackage` (with non-empty `criterion_results` and `artifact_references`) to `SEALED`, via `EvidencePackageRepository.get()` then `.save()`, guarded by caller-supplied `expected_persisted_version`.

## 12. Out-of-Scope Capabilities

`invalidate()`; any `Review` work; retry policy; composition root; transport/API layer; any second command or capability; any further `EvidencePackage` mutation beyond the transition itself.

## 13. Frozen Dependencies

`EvidencePackageRepository` (M020), `PostgresEvidencePackageRepository.get()`/`.save()` (M023), `EvidencePackage.seal()` (M020), `SaveResult`/`OptimisticConcurrencyConflict`/`AggregateNotFound` (M020), `CommandHandler` Protocol (M027), `CommandEntryPoint` (M029), `CreateEvidencePackageHandler` (M036)/`StartEvidencePackageCollectionHandler` (M038)/`RecordEvidencePackageCriterionResultHandler` (M039)/`RecordEvidencePackageArtifactReferenceHandler` (M040) — all as frozen test-fixture scaffolding to reach a sealable `COLLECTING` state, no scaffolding compromise required for the first time in this lineage.

## 14. Open Design Questions

Deferred to the Macro Design document: exact command field set (likely mirroring `AuthorizeRunCommand`/`StartEvidencePackageCollectionCommand`'s `identity`/`expected_persisted_version`/`actor`/`occurred_at`/`correlation_id`/`reason` shape); the deterministic PostgreSQL conflict mechanism (both `add_criterion_result()` and `add_artifact_reference()` are now available, proven, state-preserving interfering writes — exact selection to be finalized); empty-precondition behavior evidence strategy; result contract (`SaveResult`).

## 15. Lifecycle Prerequisites

`EvidencePackage` must already be `COLLECTING` with at least one `CriterionResult` and at least one `ArtifactReference` — all reachable via frozen commands only (Section 5).

## 16. Architecture-Boundary Considerations

None expected: `usecases` already has `evidence` in `ALLOWED` (since M036); this is a write-side command using an already-permitted import edge. To be independently re-verified live during implementation, not assumed.

## 17. Concurrency Feasibility

Confirmed live (Section 5): a genuine PostgreSQL `OptimisticConcurrencyConflict` reproduction is feasible, using either `add_criterion_result()` or `add_artifact_reference()` (both proven, state-preserving) as the interfering write — the exact mechanism to be finalized in the Macro Design.

## 18. Risks

None beyond those already inherent in the frozen design. Two-sided precondition evidence (both empty-criterion and empty-artifact rejection paths) must each be independently tested — a slightly larger PostgreSQL evidence surface than any prior single-precondition transition (M032, M035, M038), but a low-risk, well-understood extension of already-proven patterns.

## 19. M042 Boundary

This scope document authorizes work through MILESTONE-041 candidate scope selection only. No MILESTONE-042 capability, terminology, or forward commitment is made anywhere in this document. Review creation is identified as the natural M042 candidate (Section 7) but this is descriptive, not a binding selection.

## 20. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Not independently reviewed or frozen — proceeds directly into the Macro Design within this same mission, per the active protocol.
