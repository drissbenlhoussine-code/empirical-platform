# MILESTONE-053 - Evidence Submission Workflow - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design per the reduced-ceremony process now in effect (PROJECT_CHECKPOINT.md Section 31 amendment). One consolidated mission: scope, design, and implementation together, followed by one independent review checkpoint.

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M053 frozen baseline: `f4a2cefc61564025653a459d4fd55397fac26ed0` (the final M052 Owner Freeze hash-recording HEAD; M052 fully `APPROVED_AND_FROZEN`).

## 2. Product-Oriented Architecture Inventory

**A. Already strong/frozen internal foundation.** All four aggregates (Campaign, Run, EvidencePackage, Review) have complete, independently-tested domain models. `EvidencePackage` and `Review` each have **100% usecase (application-layer) coverage** — every command/query they support already has a frozen, tested handler. `Run` has usecases for `create`, `get`, `authorize`, `fail` (4 of 8 domain methods); its forward-pipeline transitions (`start_acquisition`/`start_normalization`/`start_validation`/`complete_execution`) have no usecases at all yet. `Campaign` has usecases for `create`, `get`, `prepare_for_authorization`, `cancel` (4 of 8); the rest of its authorization/execution lifecycle has no usecases yet.

**B. Capabilities exposed through real production composition (as of the M052 freeze).** Exactly 3 of 20 already-frozen usecases are reachable by any real external caller: `create_campaign`, `get_campaign`, `cancel_campaign` — all M050-M052. Every other usecase, including the *entire* application layers of Run, EvidencePackage, and Review, remains reachable only from test fixtures.

**C. Missing links preventing an end-to-end workflow.** A Campaign can be created and cancelled, but nothing can be *done* with it — no Run can be created against it, no evidence can be recorded, nothing can be reviewed. The shortest credible path from "external invocation" to "produce an observable result" that (a) reuses 100% already-frozen application logic and (b) requires zero new domain design is: **create a Run → create an EvidencePackage against it → record evidence (criteria + artifacts) → seal the package → retrieve the final sealed state.** Every step in that chain already has a frozen, tested usecase; none has ever been composed into a production entrypoint.

**D. Infrastructure genuinely required now.** Nothing new. `PostgresRepositoryRuntime` (M025), `CommandEntryPoint`/`QueryEntryPoint` (M029), `resolve_foundation_config` (foundation), `UuidRuntimeIdentifierGenerator` (foundation) — all already frozen and already proven in production by M050-M052.

**E. Infrastructure that is merely speculative (explicitly rejected).** Run's own authorization/execution pipeline (`authorize`, `start_acquisition`, etc.) — a real, but *separate*, product story ("can a Run actually execute its pipeline") not required to prove evidence can be submitted and sealed. Review's own workflow (`start`/`add_finding`/`complete`) — the natural *next* capability once evidence exists to review, explicitly out of scope here. Any transport/HTTP layer, retry policy, generic dispatcher, or workflow-orchestration engine — no repository truth demonstrates any of these are required now.

**F. Remaining domain methods unnecessary for this workflow.** `EvidencePackage.invalidate()` (post-seal reversal — a different capability). All of Campaign's and Run's remaining transitions beyond `create`/`get`.

## 3. Selected Capability

**Before M053, the platform cannot record or seal any evidence for any Run — every EvidencePackage usecase, and Run creation itself, exists only in test fixtures. After M053, an external caller can create a Run against an existing Campaign, create an EvidencePackage for that Run, record criterion results and artifact references against it, seal it, and retrieve the final sealed state — entirely through real CLI commands against real PostgreSQL — with an automated end-to-end test proving the whole chain, not just its individual steps.**

Composes, in one coherent vertical slice, the following already-frozen usecases through eight new production entrypoints:

1. `entrypoints.create_run` — `CreateRunCommand`/`CreateRunHandler` (M033)
2. `entrypoints.get_run` — `GetRunQuery`/`GetRunHandler` (M034)
3. `entrypoints.create_evidence_package` — `CreateEvidencePackageCommand`/`CreateEvidencePackageHandler` (M036)
4. `entrypoints.start_evidence_package_collection` — `StartEvidencePackageCollectionCommand`/`Handler` (M038)
5. `entrypoints.record_evidence_package_criterion_result` — `RecordEvidencePackageCriterionResultCommand`/`Handler` (M039)
6. `entrypoints.record_evidence_package_artifact_reference` — `RecordEvidencePackageArtifactReferenceCommand`/`Handler` (M040)
7. `entrypoints.seal_evidence_package` — `SealEvidencePackageCommand`/`Handler` (M041)
8. `entrypoints.get_evidence_package` — `GetEvidencePackageQuery`/`GetEvidencePackageHandler` (M037)

Zero new business/domain capability. Every command, handler, aggregate, and repository this milestone touches is already frozen and unmodified.

## 4. Anti-Abstraction Gate — One Narrow Exception, Explicitly Justified

M050, M051, and M052 each explicitly measured cross-entrypoint duplication and found it too small (2-3 files, ~10 shared lines) to justify any abstraction. **That conclusion changes at eight new entrypoints in one milestone**, all repeating the identical `construct service → try{initialize, build runtime} → finally{close}` skeleton — the exact shape class that has already produced one real, independently-found defect (M050-Y-1) and one more in dormant code (the M026 bootstrap correction). Repeating that bug-prone skeleton eight more times, by hand, is a genuine, demonstrable correctness risk this milestone can eliminate at the source instead of accepting.

**Decision:** extract exactly one narrow helper, `entrypoints._composition.postgres_repository_runtime()` — a context manager owning *only* the resource-lifecycle boundary (construct, initialize inside `try`, yield the repository runtime, close in `finally`). It has zero handler/command awareness, performs no dispatch, and is not a registry, service locator, or generic framework — each entrypoint still explicitly constructs its own specific handler and command. This lets resource-lifecycle correctness be proven rigorously **once**, inherited by all eight entrypoints, rather than eight times independently. `get_campaign.py`/`cancel_campaign.py`/`create_campaign.py` (M050-M052) are **not** retrofitted to use it — they remain exactly as independently reviewed and frozen; introducing this helper only where eight new files newly justify it.

## 5. Command Construction, Identity, and Result Contracts

Every entrypoint mirrors the exact `run_<verb>_<noun>()` + thin `main()` shape established by M050-M052: keyword-only parameters matching the composed command/query's own fields, an optional `config` override, zero exception handling beyond `main()`'s own argument-count check, and a `_*_payload()` JSON-rendering helper. Identity/version fields (`expected_persisted_version`, `identity`) flow from the caller unchanged into the command — no entrypoint re-derives or refreshes them, identical discipline to M051.

## 6. Transaction/Concurrency Boundary

Every write command in this slice (`start_collection`, `record_criterion_result`, `record_artifact_reference`, `seal`) is a single-aggregate `get()`→mutate→`save()` sequence guarded by `expected_persisted_version` — the identical, already-proven optimistic-concurrency mechanism from M047-M052. This milestone does **not** introduce multi-repository transaction orchestration (`run_composed()` remains unused and unneeded — nothing here requires atomicity across more than one aggregate at a time). Genuine OCC evidence is required only where this milestone actually exposes a concurrency boundary: recording two criterion results in sequence (each is its own independent `get()`→mutate→`save()`, so a real stale-version race is reachable and will be proven against real PostgreSQL) — fabricating additional OCC scenarios beyond what this slice's own architecture exposes is explicitly out of scope.

## 7. Failure Semantics

No exception translation anywhere. `AggregateAlreadyExists` (duplicate Run/EvidencePackage), `AggregateNotFound` (missing Run/EvidencePackage), domain `ValueError` (invalid state — e.g. sealing without any recorded criterion/artifact, or recording evidence on a non-`COLLECTING` package), and `OptimisticConcurrencyConflict` all propagate to the caller unchanged, exactly as M047-M052 established.

## 8. In-Scope

Eight production entrypoint modules, one shared resource-lifecycle helper, eight matching `[project.scripts]` entries, focused unit tests (CLI parsing + the shared helper's own resource-lifecycle correctness), and one comprehensive PostgreSQL end-to-end integration test proving the full chain — create Run, create package, start collection, record two criterion results (proving genuine OCC via the second), record an artifact reference, seal, retrieve both final states — verified via direct SQL, plus focused tests for the genuinely new failure modes this slice introduces (seal without evidence; record on a sealed/non-collecting package).

## 9. Out-of-Scope

Run's own authorization/execution pipeline; Review's own workflow; `EvidencePackage.invalidate()`; any remaining Campaign/Run domain transition; any transport/HTTP layer; any transaction orchestration beyond single-aggregate `save()`; any change to `tools/check_architecture.py` (already-permitted per M050); any change to `get_campaign.py`/`cancel_campaign.py`/`create_campaign.py`; MILESTONE-054 work of any kind.

## 10. M054 Boundary

This scope selects exactly one MILESTONE-053 capability. No MILESTONE-054 capability, terminology, or sequencing decision is made anywhere in this document.

## 11. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
