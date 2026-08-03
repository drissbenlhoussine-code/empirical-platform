# MILESTONE-038 - Concrete Application Command Vertical Slice (EvidencePackage Collection Start) Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49), used in M036 and M037. Not independently frozen.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `4674601db269da2e2b554e13e16bc62564aeaa08` (`docs: record M037 owner freeze commit hash`, pushed) |

## 3. Frozen Predecessor Chain

M020-M037 all `APPROVED_AND_FROZEN` at every stage, including M037's Owner Freeze (`MILESTONE_037_EVIDENCE_PACKAGE_RETRIEVAL_MACRO_MILESTONE_FREEZE.md`, freeze commit `9c53e1de89093bc12244ccb50ce2ced11947f396`, hash-recording commit `4674601db269da2e2b554e13e16bc62564aeaa08`).

## 4. Fresh Architecture Inventory

Rebuilt directly against `src/empirical_platform/usecases/` (8 modules, verified via directory listing at the frozen baseline) and the frozen repository Protocols:

| Aggregate | `add()` (create) | `get()` (retrieve) | `save()` (transition) | Optimistic-conflict proof |
| --- | --- | --- | --- | --- |
| Campaign | M030 | M031 | M032 | Yes (M032, `revise_scope_statement`) |
| Run | M033 | M034 | M035 | Yes (M035, `append_manifest`) |
| EvidencePackage | M036 | M037 | **none** | none |
| Review | none | none | none | none |

Verified live: `grep -l "evidence" src/empirical_platform/usecases/*.py` matches only `create_evidence_package.py`/`get_evidence_package.py`; `grep -l "review" src/empirical_platform/usecases/*.py` matches nothing. `EvidencePackageRepository.save()` and `PostgresEvidencePackageRepository.save()` are both already implemented and frozen at M020/M023 (verified: `def save(` present in `src/empirical_platform/shared/persistence/postgres_repositories/evidence_package_repository.py`) — application-layer proof is the only missing piece, exactly the situation M032 and M035 each resolved for their own aggregate.

## 5. Verified Architectural Gap

`save()`/`OptimisticConcurrencyConflict` remains completely unproven at the application layer for `EvidencePackage` — the single largest remaining unproven-generalization gap now that `add()`/`get()` are each independently proven across three aggregates (Campaign, Run, EvidencePackage). All three verbs remain unproven for `Review`.

## 6. Aggregate Dependency Graph

Unchanged since M037 (Section 6 of that scope document): `run.campaign_id -> campaign.governance_id`, `evidence_package.run_id -> run.governance_id`, `review.target_evidence_package_id -> evidence_package.governance_id` — all real FKs, re-verified live in this session against `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py`.

## 7. EvidencePackage Aggregate Method Inventory (Verified Live)

Read directly from `src/empirical_platform/evidence/package.py`: `start_collection()` (INITIALIZED -> COLLECTING, no preconditions beyond state), `add_criterion_result()` (requires COLLECTING), `add_artifact_reference()` (requires COLLECTING), `seal()` (requires COLLECTING, requires at least one criterion result and one artifact reference), `invalidate()` (requires SEALED).

**Critical fresh finding, independently derived — not assumed by analogy to M032/M035:** unlike `Campaign` (which has `revise_scope_statement()`, a non-transition, version-advancing method available in `DRAFT`) and `Run` (which has `append_manifest()`, available in `CREATED`), `EvidencePackage` has **no non-transition mutation available while `INITIALIZED`**. The only method that operates on an `INITIALIZED` package is `start_collection()` itself. This means the M032/M035 "unrelated interfering write" deterministic-conflict pattern cannot be reused unmodified for `EvidencePackage` — the conflict mechanism must be independently derived in the Design Mission (Section 14 below flags this as the central open design question).

## 8. Candidates Considered

1. **EvidencePackage lifecycle transition (`start_collection`)** — the literal first lifecycle transition, reachable directly from the `INITIALIZED` state M036 already produces; completes the `save()`/`OptimisticConcurrencyConflict` proof for a third aggregate.
2. **EvidencePackage criterion-result or artifact-reference mutation** — operates only on a `COLLECTING` package, which is not reachable via any frozen application command yet (gated behind Candidate 1); selecting this first would require test setup to reach into the domain aggregate directly rather than through a full command-based vertical slice, breaking this project's established pattern of exercising every precondition through already-frozen application commands.
3. **Review creation** — FK-viable (Section 6), but the `Review` constructor requires two additional value objects (`ReviewTargetReference`, `ReviewerReference`, verified live against `src/empirical_platform/review/aggregate.py`), a heavier design surface than closing `EvidencePackage`'s own trio; also breaks the project's twice-repeated per-aggregate completion cadence (Candidate 1 is the direct continuation of that cadence, exactly as M037's own scope document reasoned for retrieval over Review).
4. **Review retrieval** — depends on Review creation existing first; not independently viable.
5. **Retry-on-`OptimisticConcurrencyConflict` policy** — would now have three data points (M032, M035, and this milestone) if deferred once more, but still no evidenced concrete need; every prior milestone's design explicitly deferred it for this reason and nothing has changed.
6. **Composition root / registry / dispatcher / transport-neutral invocation** — no repeated-handler-need evidence; all 8 existing `usecases` modules use direct test-only construction with zero friction.
7. **Audit/governance runtime** — no scope authority or frozen contract exists for this.
8. **Additional Campaign/Run capability** — both aggregates already have all three verbs proven twice over; no architectural gap remains.

## 9. Selected M038 Scope

One concrete command transitioning an existing `EvidencePackage` from `INITIALIZED` to `COLLECTING` via `EvidencePackage.start_collection()` — `StartEvidencePackageCollectionCommand`/`StartEvidencePackageCollectionHandler` in `empirical_platform.usecases.start_evidence_package_collection`, using the already-frozen `EvidencePackageRepository.get()`/`save()` (M020/M023).

## 10. Why This Scope Is Next

Continues the exact cadence M037's own scope document established: complete one aggregate's create-retrieve-transition trio before opening a new aggregate. `EvidencePackage` now has `add()` (M036) and `get()` (M037); `save()` is the final verb needed to close its trio, exactly mirroring Campaign's M030-M032 and Run's M033-M035 sequences. `start_collection()` is the only domain-valid first transition, with zero alternative in the `INITIALIZED` state, making the scope selection unambiguous once Candidate 2 is correctly identified as premature (Section 8).

## 11. In-Scope Capability

Transition of exactly one `EvidencePackage` from `INITIALIZED` to `COLLECTING`, via `EvidencePackageRepository.get()` then `.save()`, guarded by caller-supplied `expected_persisted_version`.

## 12. Out-of-Scope Capabilities

`add_criterion_result()`, `add_artifact_reference()`, `seal()`, `invalidate()`; any `Review` work; retry policy; composition root; transport/API layer; any second command or capability.

## 13. Frozen Dependencies

`EvidencePackageRepository` (M020), `PostgresEvidencePackageRepository.get()`/`.save()` (M023), `EvidencePackage.start_collection()` (M020), `EvidencePackageLifecycleState` (M020), `SaveResult`/`OptimisticConcurrencyConflict`/`AggregateNotFound` (M020), `CommandHandler` Protocol (M027), `CommandEntryPoint` (M029).

## 14. Open Design Questions

Deferred to the Macro Design document: exact command field set (mirroring `AuthorizeRunCommand`'s `identity`/`expected_persisted_version`/`actor`/`occurred_at`/`correlation_id`/`reason` shape, or narrower); **the deterministic PostgreSQL conflict mechanism, which cannot mirror M032/M035 unmodified per Section 7's finding and must be independently derived**; result contract (`SaveResult`, mirroring M032/M035).

## 15. Architecture-Boundary Considerations

None expected: `usecases` already has `evidence` in `ALLOWED` (since M036); this is a write-side command using an already-permitted import edge. To be independently re-verified live during implementation, not assumed.

## 16. Stop Conditions / Prohibited Expansion

No `add_criterion_result`/`add_artifact_reference`/`seal`/`invalidate` call of any kind. No `Review` module reference. No composition root, registry, or dispatcher. No MILESTONE-039 work.

## 17. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Not independently reviewed or frozen — proceeds directly into the Macro Design within this same mission, per the active protocol.
