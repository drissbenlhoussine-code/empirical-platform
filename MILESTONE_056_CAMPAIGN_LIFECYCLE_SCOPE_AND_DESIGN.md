# MILESTONE-056 - Campaign Lifecycle End-to-End - Scope and Design

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN**

Combined scope+design, continuing the reduced-ceremony process established in M053-M055.

## 1. Repository Authority

Repository `C:\Users\LuxSy\Documents\trading`, branch `master`. M056 frozen baseline: `d4d5ea1cd8dd8c1dd64a11c1acdbb198c6af65b0` (the final M055 Owner Freeze hash-recording HEAD; M055 fully `APPROVED_AND_FROZEN`), independently re-verified via `git fetch` before any work began.

## 2. Fresh Campaign Architecture Inventory

Independently re-derived from source (`src/empirical_platform/campaign/aggregate.py`, `campaign/repository.py`, `usecases/*campaign*.py`, `entrypoints/*campaign*.py`), not from prior governance prose:

- **Lifecycle states** (`campaign.lifecycle.CampaignLifecycleState`, frozen M012): `DRAFT`, `READY_FOR_AUTHORIZATION`, `AUTHORIZED`, `ACTIVE`, `SUSPENDED`, `COMPLETED`, `CANCELLED` — 7 states.
- **All mutation methods already exist on the frozen `Campaign` aggregate**, unmodified, requiring zero new domain design: `revise_scope_statement()` (DRAFT-only, no transition, version bump), `prepare_for_authorization()` (DRAFT→READY_FOR_AUTHORIZATION), `record_authorization()` (READY_FOR_AUTHORIZATION→AUTHORIZED), `activate()` (AUTHORIZED→ACTIVE), `suspend()` (ACTIVE→SUSPENDED), `resume()` (SUSPENDED→ACTIVE), `complete()` (ACTIVE→COMPLETED), `cancel()` (DRAFT/READY_FOR_AUTHORIZATION/AUTHORIZED/ACTIVE/SUSPENDED→CANCELLED).
- **Existing usecases** (all frozen, unmodified): `create_campaign` (M030), `get_campaign` (M031), `prepare_campaign_for_authorization` (M032), `cancel_campaign` (M047). **`prepare_campaign_for_authorization` has zero production entrypoint** — already frozen, already exercised by its own integration test suite, never composed into a real CLI command.
- **Missing usecases** (confirmed absent from `src/empirical_platform/usecases/`): none exist for `revise_scope_statement`, `record_authorization`, `activate`, `suspend`, `resume`, or `complete`.
- **Repository/persistence**: `PostgresCampaignRepository.save()` already updates the `scope_statement` column on every save (frozen, tested) — no gap.
- **Existing production entrypoints**: `create_campaign`, `get_campaign`, `cancel_campaign` (all M050-M052, unmodified, deliberately not using the `_composition.py` helper — established precedent). Zero entrypoint exists for `prepare_campaign_for_authorization` or any state beyond `READY_FOR_AUTHORIZATION`.

## 3. Product Gap Analysis

**What prevents a real external caller from driving a Campaign through its legitimate business lifecycle today?** Everything past creation: a Campaign can be created, retrieved, and cancelled from anywhere, but cannot be prepared, authorized, activated, suspended, resumed, or completed by any real caller — every one of those six operations exists only in the frozen aggregate and its own unit tests.

| Capability | Classification |
| --- | --- |
| `prepare_for_authorization`, `record_authorization`, `activate`, `complete` | **REQUIRED FOR CORE FORWARD LIFECYCLE** |
| `cancel` | **REQUIRED TERMINAL/FAILURE PATH** — already frozen (M047/M051), reused unchanged |
| `suspend`/`resume` | **USEFUL BUT NON-BLOCKING** — a genuine, already-frozen alternate path from the same aggregate, cheap to compose alongside the forward lifecycle since it reuses the identical pattern; included because it belongs naturally to this same lifecycle, not because it is uncovered |
| `revise_scope_statement` | **USEFUL BUT NON-BLOCKING** — genuine Campaign-owned-data mutation; included because it gives the acceptance test a concrete way to prove Campaign-owned data survives every subsequent transition (the same role `append_run_manifest` played in M055) |

## 4. Candidate Comparison

The only candidate seriously considered was the complete Campaign lifecycle — this mission's own instruction names it directly, and repository truth confirms every domain method already exists with zero new design required. No alternative capability was evaluated; Campaign is the last of the four core aggregates (Campaign/Run/EvidencePackage/Review) not yet fully composed into production.

## 5. Selected M056 Scope

**Six new application-layer usecases** (zero new domain design; each composes an already-frozen `Campaign` aggregate method): `revise_campaign_scope_statement`, `record_campaign_authorization`, `activate_campaign`, `suspend_campaign`, `resume_campaign`, `complete_campaign`.

**Seven new production entrypoints**, all reusing the unmodified M053 `entrypoints._composition.postgres_repository_runtime()` helper: `prepare_campaign_for_authorization` (composes the already-frozen M032 usecase — zero new application code), `revise_campaign_scope_statement`, `record_campaign_authorization`, `activate_campaign`, `suspend_campaign`, `resume_campaign`, `complete_campaign`.

`create_campaign.py`/`get_campaign.py`/`cancel_campaign.py` (M050-M052) are **not** touched or retrofitted — they remain exactly as independently reviewed and frozen.

## 6. BEFORE/AFTER Statement

**Before M056**, a Campaign can be created and retrieved, and cancelled from anywhere, but a real external caller cannot drive it through its complete forward business lifecycle — six of the aggregate's own mutation methods exist only in test fixtures. **After M056**, a real external caller can create a Campaign, revise its scope while in DRAFT, prepare it for authorization, record its authorization, activate it, suspend and resume it, and complete it — the largest legal forward lifecycle the domain supports — entirely through real CLI commands against real PostgreSQL, with Campaign-owned data (the scope statement) verified to survive every transition, and retrieve the final persisted state.

## 7. Exact Legal Lifecycle Sequence

```
Campaign created (M050-M052, existing)
  -> revise_campaign_scope_statement   (DRAFT, version bump only, no transition)
  -> prepare_campaign_for_authorization DRAFT -> READY_FOR_AUTHORIZATION
  -> record_campaign_authorization      READY_FOR_AUTHORIZATION -> AUTHORIZED
  -> activate_campaign                  AUTHORIZED -> ACTIVE
  -> suspend_campaign                   ACTIVE -> SUSPENDED
  -> resume_campaign                    SUSPENDED -> ACTIVE
  -> complete_campaign                  ACTIVE -> COMPLETED
  -> get_campaign (existing) -> final state verified, scope statement preserved throughout
```

Negative path, reusing the already-frozen M047/M051 `cancel_campaign` unchanged, proven once from a legitimate active state as part of this milestone's own acceptance picture (not rebuilt, not re-proven exhaustively).

## 8. Architecture Decisions

**Reuse, no new abstraction.** The M053 `_composition.py` helper is reused unchanged for all seven new entrypoints. M050-M052's own entrypoints remain untouched.

**No exception translation, no dispatcher, no registry.** Identical discipline to M050-M055: `AggregateNotFound`, domain `ValueError` (invalid transition), and `OptimisticConcurrencyConflict` all propagate to the caller unchanged.

## 9. Concurrency

Campaign OCC is already strongly proven by frozen milestones (M047 `cancel_campaign`, and the same `expected_persisted_version`-guarded mechanism reused unmodified since M025). This milestone introduces no materially new concurrency boundary — every new command is the same single-aggregate `get()`→mutate→`save()` shape already exhaustively proven. No new PostgreSQL OCC scenario is added; frozen evidence is relied upon explicitly, and priority is given to lifecycle acceptance instead.

## 10. Cross-Aggregate Product Check

After M056, Campaign, Run (M055), EvidencePackage (M053), and Review (M054) are all independently composed into real production entrypoints. This milestone adds one additional high-value acceptance scenario proving a real caller can sequentially invoke the existing entrypoints across all four aggregates in one coherent chain (Campaign through ACTIVE → Run created and executed to completion → EvidencePackage sealed → Review completed → Campaign completed) — without building any new orchestration framework, dispatcher, or automation layer. This determines whether the core engine is now functionally closed.

## 11. In-Scope

Six usecase modules, seven production entrypoint modules, seven matching `[project.scripts]` entries, focused unit/contract tests for the six new usecases, focused CLI unit tests for the seven new entrypoints, one comprehensive PostgreSQL end-to-end acceptance test proving the complete legal Campaign lifecycle plus one cancellation from a legitimate active state, and one cross-aggregate acceptance test proving the full Campaign→Run→EvidencePackage→Review chain is sequentially usable.

## 12. Out-of-Scope

Any transport/HTTP layer; any orchestration/automation framework driving the cross-aggregate chain automatically; any change to `tools/check_architecture.py`; any change to M050-M055's own entrypoints; any change to `create_campaign.py`/`get_campaign.py`/`cancel_campaign.py`; MILESTONE-057 work of any kind.

## 13. M057 Boundary

This scope selects exactly one MILESTONE-056 capability. No MILESTONE-057 capability, terminology, or sequencing decision is made anywhere in this document.

## 14. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE_AND_DESIGN.**
