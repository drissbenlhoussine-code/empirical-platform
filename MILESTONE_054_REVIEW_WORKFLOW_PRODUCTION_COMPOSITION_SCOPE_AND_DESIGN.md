# MILESTONE-054 - Review Workflow Production Composition - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony process established in M053.

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M054 frozen baseline: `9a30f817b26b0580c2cabc98bae15b2a42f87242` (the final M053 Owner Freeze hash-recording HEAD; M053 fully `APPROVED_AND_FROZEN`), independently re-verified via `git fetch` before any work began.

## 2. Fresh Product Capability Inventory

Independently re-derived from source (not from prior governance prose):

- **Review aggregate** (`review/aggregate.py`): complete, frozen — `ReviewTargetReference` (an opaque `EvidencePackageId` reference, no state precondition on the target), `ReviewerReference`, `ReviewFinding`, and the `Review` aggregate root with `start()`, `add_finding()`, `complete()`, `cancel()`, each enforcing its own lifecycle precondition (e.g. `complete()` requires `IN_PROGRESS` and at least one finding).
- **Review usecases**: all 6 already frozen and fully tested — `create_review` (M042), `get_review` (M043), `start_review` (M044), `add_review_finding` (M045), `complete_review` (M046), `cancel_review` (M049). Zero new domain design required.
- **Review repository/persistence**: `PostgresReviewRepository` and the `.reviews` property on the frozen `PostgresRepositoryRuntime` (M025) already exist and are already exercised by each usecase's own test suite.
- **Production entrypoints**: zero. `ls src/empirical_platform/entrypoints/*.py` lists exactly 13 files (health, version, 3 Campaign, 8 M053 Run/EvidencePackage) — no `*review*` entrypoint exists.
- **Run execution/authorization gaps**: `authorize_run`/`fail_run` usecases exist but are not composed; the forward pipeline (`start_acquisition`/`start_normalization`/`start_validation`/`complete_execution`) has no usecases at all. Classified **USEFUL LATER** — a separate, larger design effort, not required to prove a Review can happen.
- **Campaign lifecycle gaps**: `prepare_for_authorization` usecase exists, uncomposed; remaining authorization/execution lifecycle has no usecases. Classified **USEFUL LATER**.
- **`EvidencePackage.invalidate()`**: domain method exists, no usecase, no repository-level exercise beyond the aggregate's own unit tests. Classified **ARCHITECTURAL COMPLETENESS ONLY** — a post-seal reversal path, not required for a first Review to happen.
- **Composition/integration infrastructure required**: none new. Reuses the M053 `entrypoints._composition.postgres_repository_runtime()` helper unchanged.

## 3. Candidate Comparison

| Candidate | Classification | Why |
| --- | --- | --- |
| Review Workflow Production Composition | **PRODUCT BLOCKER** | The only aggregate with 100% frozen usecase coverage and zero production reachability; the literal next step after M053's sealed evidence has nowhere to go. |
| Run execution/authorization pipeline | USEFUL LATER | No usecases exist yet for the forward pipeline; a genuinely separate, larger domain-design effort. |
| Campaign authorization/execution lifecycle | USEFUL LATER | Same reasoning — usecases don't exist yet beyond what's already composed. |
| `EvidencePackage.invalidate()` | ARCHITECTURAL COMPLETENESS ONLY | A narrow post-seal reversal path; no product workflow depends on it existing yet. |
| Any transport/HTTP/dispatcher/event-bus layer | NOT CURRENTLY NECESSARY | No repository truth demonstrates genuine need; explicitly rejected per mission instruction. |

**Selected: Review Workflow Production Composition — extended to a full cross-milestone continuation.** `CreateReviewCommand` targets an `EvidencePackageId` with no state precondition (enforced only by the DB foreign key, exactly like M053's own `create_run`/`create_evidence_package`), which makes it safe and clean to chain directly from a real, M053-composed, genuinely SEALED EvidencePackage into a full Review lifecycle in one coherent, real, PostgreSQL-backed capability — the larger continuation this mission asks to prefer when frozen contracts allow it cleanly. They do.

## 4. BEFORE/AFTER Statement

**Before M054**, a caller can produce sealed evidence, but cannot perform a production Review of that evidence — every Review usecase exists only in test fixtures. **After M054**, a caller can create a Review against an existing (including a genuinely sealed) EvidencePackage, start it, record one or more findings, complete it with a final disposition, or cancel it, and retrieve the final Review state — entirely through real CLI commands against real PostgreSQL, with an automated end-to-end test proving the continuous chain from a sealed EvidencePackage through a completed Review.

## 5. Selected Scope

Six new production entrypoints, composing the six already-frozen Review usecases (M042, M043, M044, M045, M046, M049) through the frozen M053 `_composition.py` helper:

1. `entrypoints.create_review` — `CreateReviewCommand`/`CreateReviewHandler` (M042)
2. `entrypoints.get_review` — `GetReviewQuery`/`GetReviewHandler` (M043)
3. `entrypoints.start_review` — `StartReviewCommand`/`StartReviewHandler` (M044)
4. `entrypoints.add_review_finding` — `AddReviewFindingCommand`/`AddReviewFindingHandler` (M045)
5. `entrypoints.complete_review` — `CompleteReviewCommand`/`CompleteReviewHandler` (M046)
6. `entrypoints.cancel_review` — `CancelReviewCommand`/`CancelReviewHandler` (M049)

`cancel_review` is included because it is the aggregate's own complete alternate terminal lifecycle path (already frozen, identical composition cost to every other entrypoint here) — not an unrelated capability added merely to inflate scope. Zero new business/domain capability; every command, handler, aggregate, and repository this milestone touches is already frozen and unmodified.

## 6. Architecture Decisions

**Reuse, no new abstraction.** The M053 `entrypoints._composition.postgres_repository_runtime()` helper is reused unchanged for all six new entrypoints — six more entrypoints repeating the identical resource-lifecycle skeleton is exactly the case that helper was built for; there is nothing new to extract. M050-M053's own entrypoints remain untouched.

**No exception translation, no dispatcher, no registry.** Identical discipline to M050-M053: `AggregateAlreadyExists`, `AggregateNotFound`, domain `ValueError` (invalid lifecycle transition, missing findings before completion), and `OptimisticConcurrencyConflict` all propagate to the caller unchanged.

**No new infrastructure.** No transport/HTTP layer, no generic workflow engine, no event bus. Nothing in repository truth demonstrates a need for any of these.

## 7. Transaction/Concurrency Boundary

Every write command (`create`, `start`, `add_finding`, `complete`, `cancel`) is a single-aggregate `get()`→mutate→`save()` sequence guarded by `expected_persisted_version` — the same, already-proven optimistic-concurrency mechanism reused unmodified since M047. A genuine concurrency boundary is naturally exposed exactly once in this workflow: recording a second finding (or attempting to complete) against a stale version after a first finding has already been recorded, which is proven directly rather than fabricated. No additional OCC scenarios are manufactured beyond what this slice's own architecture exposes.

## 8. Failure Semantics

No exception translation anywhere. Meaningful failures tested: `AggregateNotFound` (missing Review), domain `ValueError` (completing without any recorded finding; completing/starting a Review not in the required prior state; adding a finding to a non-`IN_PROGRESS` Review), `OptimisticConcurrencyConflict` (stale expected version), and resource-initialization failure with guaranteed cleanup (already proven once, centrally, by M053's own `_composition.py` test suite — not re-proven per entrypoint here).

## 9. In-Scope

Six production entrypoint modules, six matching `[project.scripts]` entries, focused unit tests (CLI parsing per entrypoint), and one comprehensive PostgreSQL end-to-end acceptance test proving the full cross-milestone continuation — seal a real EvidencePackage (reusing M053's own entrypoints) → create a Review against it → start it → record two findings (the second proving a genuine optimistic-concurrency conflict via a stale retry, then a corrected retry) → complete it → retrieve it — verified via direct SQL, plus focused tests for the genuinely new failure modes this slice introduces (complete without any finding; add finding outside `IN_PROGRESS`; start a non-`ASSIGNED` Review).

## 10. Out-of-Scope

Run's own authorization/execution pipeline; Campaign's remaining authorization/execution lifecycle; `EvidencePackage.invalidate()`; any transport/HTTP layer; any transaction orchestration beyond single-aggregate `save()`; any change to `tools/check_architecture.py`; any change to M050-M053's own entrypoints; MILESTONE-055 work of any kind.

## 11. M055 Boundary

This scope selects exactly one MILESTONE-054 capability. No MILESTONE-055 capability, terminology, or sequencing decision is made anywhere in this document.

## 12. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
