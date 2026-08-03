# MILESTONE-037 - Concrete Application Query Vertical Slice (EvidencePackage Retrieval) Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced within the consolidated Macro Milestone Mission, per the protocol activated in M035's implementation freeze (Section 49) and used for the first time in M036. Not independently frozen — scope, design, and implementation are all candidates within this one mission, per `PROJECT_CHECKPOINT.md` Section 31.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Frozen baseline HEAD | `ce65d890404c975a10821224c501cd386fd63e6f` (`docs: record M036 owner freeze commit hash`, pushed) |

## 3. Frozen Predecessor Chain

M020-M036 all `APPROVED_AND_FROZEN` at every stage, including M036's Owner Freeze (`MILESTONE_036_EVIDENCE_PACKAGE_CREATION_MACRO_MILESTONE_FREEZE.md`, freeze commit `8c5f04cb2e4b32749fc6ba04806b33ac38c0216f`, hash-recording commit `ce65d890404c975a10821224c501cd386fd63e6f`).

## 4. Fresh Architecture Inventory

Rebuilt directly against `src/empirical_platform/usecases/` (7 modules, verified via directory listing at the frozen baseline HEAD) and the frozen `EvidencePackageRepository`/`ReviewRepository` Protocols:

| Aggregate | `add()` (create) | `get()` (retrieve) | `save()` (transition) | Optimistic-conflict proof |
| --- | --- | --- | --- | --- |
| Campaign | M030 | M031 | M032 | Yes (M032, `revise_scope_statement`) |
| Run | M033 | M034 | M035 | Yes (M035, `append_manifest`) |
| EvidencePackage | M036 | **none** | **none** | none |
| Review | none | none | none | none |

Verified live: `grep -rl "evidence" src/empirical_platform/usecases/*.py` matches only `create_evidence_package.py`; `grep -rl "review" src/empirical_platform/usecases/*.py` matches nothing. The `EvidencePackageRepository.get()` method itself is already implemented and frozen at the persistence-adapter level (`PostgresEvidencePackageRepository.get`, M023) — application-layer proof is the only missing piece, exactly the situation M031 and M034 each resolved for their own aggregate.

## 5. Verified Architectural Gap

Two verbs (`get()`, `save()`) remain completely unproven at the application layer for `EvidencePackage`, and all three verbs remain unproven for `Review`.

## 6. Aggregate Dependency Graph

Verified directly against `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py`:

- `run.campaign_id -> campaign.governance_id` (real FK, proven by M033/M035).
- `evidence_package.run_id -> run.governance_id` (real FK, proven by M036).
- `review.target_evidence_package_id -> evidence_package.governance_id` (real FK, verified live in this scope session; not yet exercised by any application-layer code).

`Review` creation is therefore FK-dependency-viable in principle (it does not require `EvidencePackage` retrieval as a technical prerequisite, mirroring the same referential-integrity-only pattern M033/M036 already proved) — but see Section 9 for why it is not selected this milestone.

## 7. Candidates Considered

1. **EvidencePackage retrieval** (`GetEvidencePackageQuery`/`GetEvidencePackageHandler`) — completes the `get()` proof for the third aggregate; near-zero technical risk (adapter already frozen at M023).
2. **EvidencePackage lifecycle transition / save()** (e.g. `start_collection`) — would be the third proof of `save()` + `OptimisticConcurrencyConflict`, a pattern already independently proven twice (M032, M035); marginal generalization value is now lower than for `get()`.
3. **Review creation** — FK-viable per Section 6, but would open a fourth aggregate before EvidencePackage's own create-retrieve-transition trio is complete, breaking the project's own twice-repeated per-aggregate completion cadence (Campaign: M030-M032 before Run began; Run: M033-M035 before EvidencePackage began).
4. **Review retrieval** — depends on Review creation existing first; not independently viable this milestone.
5. **Retry-on-`OptimisticConcurrencyConflict` policy** — still no evidenced concrete need; M029's design explicitly deferred it for this reason, and M035's freeze recorded the same observation unchanged.
6. **Composition root / registry / dispatcher / transport-neutral invocation** — no repeated-handler-need evidence; every milestone through M036 uses direct test-only construction with zero friction.
7. **Audit/governance runtime** — no scope authority or frozen contract exists for this; would require its own scope justification from a clean architecture inventory, not a byproduct of this one.
8. **Additional Campaign/Run capability** — both aggregates already have all three verbs proven twice over; no architectural gap remains for them.

## 8. Selected M037 Scope

One concrete query retrieving an existing `EvidencePackage` by full identity, returning a bounded, milestone-local `EvidencePackageSnapshot` read value — `GetEvidencePackageQuery`/`GetEvidencePackageHandler` in `empirical_platform.usecases.get_evidence_package`, using the already-frozen `EvidencePackageRepository.get()` (M020/M023).

## 9. Why This Scope Is Next

The project has, twice, completed one aggregate's full create-retrieve-transition trio before starting the next aggregate's first verb (Campaign M030-M032, then Run M033-M035, only then EvidencePackage M036). Candidate 3 (Review creation) would break that cadence while EvidencePackage still lacks two of its three verbs. Candidate 1 (EvidencePackage retrieval) is the direct continuation of the established cadence, mirrors the already-twice-validated `GetRunQuery`/`GetCampaignQuery` pattern exactly, and carries the lowest technical risk of any viable candidate since its persistence-layer dependency is already frozen and unchanged since M023.

## 10. In-Scope Capability

Retrieval of exactly one `EvidencePackage` by its full `DomainIdentity[EvidencePackageId]`, via `EvidencePackageRepository.get()`, returned as a bounded `EvidencePackageSnapshot`.

## 11. Out-of-Scope Capabilities

`EvidencePackage` mutation (`start_collection`, `add_criterion_result`, `add_artifact_reference`, `seal`, `invalidate`) or `save()`; any `Review` work; retry policy; composition root; transport/API layer; listing, filtering, or pagination of `EvidencePackage`s; exposure of `criterion_results`, `artifact_references`, `transition_history`, or `version`/`persisted_version` in the read model (mirrors M034's own `RunSnapshot` exclusions).

## 12. Frozen Dependencies

`EvidencePackageRepository` (M020), `PostgresEvidencePackageRepository.get()` (M023), `EvidencePackage` aggregate (`identity`, `run_id`, `state` properties — M020), `EvidencePackageLifecycleState` (M020), `LoadedAggregate`/`AggregateNotFound`/`InvalidPersistedAggregateState` (M020), `QueryHandler` Protocol (M028).

## 13. Identity and Referential-Integrity Considerations

Retrieval takes a caller-supplied full `DomainIdentity[EvidencePackageId]` (governance ID and runtime ID both required), mirroring `GetRunQuery`/`GetCampaignQuery` exactly — no partial-identity lookup is introduced. No referential-integrity concern arises: retrieval performs no write and enforces no FK.

## 14. Open Design Questions

Deferred to the Macro Design document: exact `EvidencePackageSnapshot` field set; not-found error semantics; whether `run_id` is exposed on the snapshot (precedent: `RunSnapshot` exposes `campaign_id`, its own FK-parent reference).

## 15. Architecture-Boundary Considerations

None expected: `usecases` already has `evidence` in `ALLOWED` (added in M036); this is a read-only query using an already-permitted import edge. To be independently re-verified live during design/implementation, not assumed.

## 16. Stop Conditions / Prohibited Expansion

No `EvidencePackage` mutation or `save()` call of any kind. No `Review` module reference. No listing/filtering/pagination. No composition root, registry, or dispatcher. No MILESTONE-038 work.

## 17. Governance Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE.** Not independently reviewed or frozen — proceeds directly into the Macro Design within this same mission, per the active protocol.
