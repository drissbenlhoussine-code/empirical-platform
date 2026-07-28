# MILESTONE-027 - Application Command/Handler Contracts Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-027-SCOPE-SELECTION |
| Title | Application Command/Handler Contracts Scope Selection |
| Version | 1.0 |
| Status | SCOPE SELECTED - PENDING INDEPENDENT REVIEW |
| Repository baseline | `45f4916d1fcdd76b28fffa81c23704f6b0355c3d` |
| Mission type | Scope selection and design authorization only |

## 2. Objective

Select the single best bounded milestone after frozen M026 using live repository evidence.

## 3. Authority

This mission is authorized by the Project Owner's acceptance of the final independent recommendation `M026 IMPLEMENTATION APPROVED FOR OWNER FREEZE`, and the Owner's explicit instruction to select the correct MILESTONE-027 scope from live repository evidence, produce its Scope Selection and Design documents, and stop before implementation.

## 4. Frozen Baseline

All of M020 through M026 are `APPROVED_AND_FROZEN` (see `PROJECT_CHECKPOINT.md` Section 2). In particular:

- M020 froze the persistence-neutral repository Protocols and `OptimisticConcurrencyConflict`/`AggregateNotFound`/`AggregateAlreadyExists` contract error taxonomy in `shared/contracts/repository.py`.
- M024 froze `PostgresPersistenceService.run_composed(operations)` for atomic multi-repository execution.
- M025 froze `PostgresRepositoryRuntime`, composing the four M023 repository adapters over one shared `PostgresPersistenceService`.
- M026 froze `FoundationRuntime.repository_runtime`, so a fully booted process now obtains a working `PostgresRepositoryRuntime` with zero manual wiring.

## 5. Live Repository Evidence

Live evidence gathered directly from the repository (not from memory of prior milestones):

- `grep -rln "class.*Command\|class.*Handler" src/empirical_platform` returns **no results**. No command, handler, or application-orchestration type exists anywhere in the codebase today.
- `src/empirical_platform/audit/`, `src/empirical_platform/decision_candidate/`, and `src/empirical_platform/governance/` each contain only an empty `__init__.py` — confirmed by direct listing. These packages are placeholders with zero implemented behavior.
- `src/empirical_platform/entrypoints/` contains only `health.py` and `version.py` — no API, worker, or CLI entrypoint that consumes a repository or the application layer exists.
- `OptimisticConcurrencyConflict` (frozen M020, `shared/contracts/repository.py`) is already raised by all four concrete M023 repository adapters on a version-mismatch save conflict (`grep` confirms all four `postgres_repositories/*.py` files raise it), but **nothing in the repository catches, retries, or otherwise consumes it** — there is no application-layer caller of any kind yet.
- `PROJECT_CHECKPOINT.md`'s own Deferred Capabilities list (updated at the M026 freeze) explicitly orders remaining work as: application service orchestration → retry-on-`OptimisticConcurrencyConflict` policy (explicitly gated on application services existing first) → APIs/workers/Audit runtime/Decision Candidate/Decision Freeze → market-data/vendor/trading/campaign execution. Retry policy, APIs, workers, and Audit runtime are each explicitly ordered *after* an application-layer boundary that does not yet exist.
- `shared/contracts/` (containing `repository.py` and `mapping.py`) is the repository's established, precedent-setting location for domain-agnostic, Protocol-level contracts consumed by aggregate-specific implementations — exactly the pattern M020 set for repository contracts before M023 implemented concrete adapters.
- `shared/interfaces/orchestration.py` exists today with a single `JobLedgerHealth` Protocol stub — evidence that an orchestration/job-ledger boundary is anticipated but not yet built, and is a distinct, narrower concern from application command/handler contracts (job-ledger health is a dependency-health concept, not a command-dispatch concept).

M025 Design Section 15 and M026 Design Section 4/21 both explicitly rejected "application services" as premature at their respective stages because "application services need a stable repository runtime composition boundary" (M025) and because introducing orchestration logic before that boundary was bootstrap-accessible would have been scope inflation (M026). Both of those blockers are now resolved by M025+M026. A third, narrower blocker remains, revealed only by directly searching the codebase: there is no shared vocabulary — no `Command`, no `CommandHandler`, no result/error contract — for what an application-layer caller of the now-available `PostgresRepositoryRuntime` even looks like. That is exactly the class of gap M020 closed for repositories before M023 could implement them.

## 6. Candidate Inventory

| Candidate | Layer | Dependencies | Scope size | Risk | Decision |
| --- | --- | --- | --- | --- | --- |
| Application Command/Handler Contracts | Application (contracts only) | M020, M024, M025, M026 frozen; no existing command/handler vocabulary | Small | Low | Selected |
| Application Service Orchestration (full) | Application (implementation) | Requires command/handler contracts to exist first — not yet true | Large | High | Rejected as premature |
| Optimistic-Concurrency Handling at Service Layer | Application policy | Explicitly requires application services to exist first (checkpoint's own deferred-capabilities ordering) | Medium | Medium | Rejected as premature |
| Retry Policy | Application policy | Explicitly depends on application services (checkpoint's own deferred-capabilities ordering) | Medium | High | Rejected as premature |
| Runtime/Bootstrap Access Above FoundationRuntime | Infrastructure/entrypoint | Would require inventing an API/worker/CLI entrypoint ahead of any application layer to consume it | Medium | High | Rejected as premature |
| Audit Runtime Composition | Governance/runtime | `audit`/`decision_candidate`/`governance` packages are empty placeholders; explicitly ordered after APIs/workers in the deferred list | Large | High | Rejected as premature |

## 7. Candidate Comparison

| Criterion | Command/Handler Contracts | Application Service Orchestration | Optimistic-Concurrency Policy | Retry Policy | Audit Runtime |
| --- | --- | --- | --- | --- | --- |
| Architectural ordering | Directly follows M026 | Depends on this milestone | Depends on application services | Depends on application services | Depends on APIs/workers |
| Dependency readiness | Ready | Not ready | Not ready | Not ready | Not ready |
| Isolation | High (new contracts-only file, no existing file touched) | Low (would touch bootstrap, repositories, and invent orchestration in one pass) | Low | Low | Low |
| Independent testability | High (pure types/Protocols, in-memory fakes) | Medium | Medium | Medium | Low |
| Reversibility | High | Medium | Medium | Medium | Low |
| Scope-creep risk | Low | High | High | High | High |
| Implementation confidence | High | Medium | Low | Low | Low |

## 8. Selected Scope

MILESTONE-027 selects **Application Command/Handler Contracts**.

Purpose: freeze the persistence-neutral, domain-agnostic vocabulary for an application-layer command and its handler — a `Command` marker Protocol, a `CommandHandler[CommandT, ResultT]` Protocol, and a minimal, narrow error/result contract for handler-level failures distinct from the existing M020 repository-contract errors — with **zero implementation of any concrete command, handler, or orchestration logic**, exactly mirroring how M020 froze repository Protocols before M023 implemented any concrete adapter.

## 9. Non-Goals

- any concrete `Command` or `CommandHandler` implementation for any aggregate;
- application service orchestration, transaction ownership decisions, or any wiring to `PostgresRepositoryRuntime`/`run_composed`;
- retry-on-`OptimisticConcurrencyConflict` policy;
- APIs, workers, CLI entrypoints, or any change to `entrypoints/`;
- Audit runtime, Decision Candidate, Decision Freeze;
- market-data, vendor, trading, or campaign execution behavior;
- any change to M020-M026 frozen contracts, adapters, mappers, schema, `run_composed`, `PostgresRepositoryRuntime`, or `FoundationRuntime`.

## 10. Dependencies

| Dependency | Role | Status |
| --- | --- | --- |
| M020 | Repository Protocol contracts and `RepositoryContractError` taxonomy | APPROVED AND FROZEN |
| M024 | Multi-aggregate Unit of Work primitive | APPROVED AND FROZEN |
| M025 | Repository runtime composition | APPROVED AND FROZEN |
| M026 | Foundation Runtime Repository Composition | APPROVED AND FROZEN |

## 11. Architecture Constraints

- New contracts live in `src/empirical_platform/shared/contracts/`, alongside the existing `repository.py`/`mapping.py`, following the identical placement precedent M020 set.
- No new top-level package is introduced; `tools/check_architecture.py`'s `ALLOWED` table requires no change, since `shared` is already importable by every domain package.
- No domain package (`campaign`/`run`/`evidence`/`review`) is required to import the new contracts as part of this milestone — they are pure, standalone types with no forced consumer yet.
- No import from `shared.persistence`, `sqlalchemy`, `psycopg`, or `boto3` — these contracts are, like the M020 repository Protocols, persistence-neutral.

## 12. Transaction Constraints

No transaction coordinator, no `run_composed` reimplementation, no wiring to any repository or persistence service. The contracts describe only the *shape* of a command and its handler — never how a handler obtains or uses a repository.

## 13. Concurrency Constraints

None. No concurrency primitive is introduced; the contracts are pure Protocol/type definitions with no runtime state.

## 14. Security Constraints

No credential, connection, or persistence-adjacent concern is introduced; these contracts touch no configuration, secret, or connection string.

## 15. Test Obligations

A future implementation must prove:

- the `Command` and `CommandHandler[CommandT, ResultT]` Protocols are structurally satisfiable by a minimal in-memory example handler with no persistence dependency;
- the new handler-level error contract is distinct from, and does not duplicate or shadow, the existing M020 `RepositoryContractError` hierarchy;
- no existing M020-M026 test is affected;
- `tools/check_architecture.py` reports zero violations with the new file present.

## 16. Stop Conditions

STOP design work and return to scope selection if:

- freezing a useful command/handler contract turns out to require deciding transaction ownership or repository access patterns (that would mean this milestone has silently become "Application Service Orchestration" and must be re-scoped);
- the frozen M020 error taxonomy already fully covers what a handler-level error needs to express (in which case this milestone's error-contract component should be dropped rather than duplicated).

## 17. Acceptance Gate

The design is acceptance-ready only if it freezes, with no remaining ambiguity: the exact `Command` and `CommandHandler` shapes; the exact package/file placement; the exact handler-error contract (or an explicit, justified decision that none is needed beyond M020's existing taxonomy); and exact test obligations.

## 18. Hostile Self-Review

1. **Does this quietly become "application services"?** No — no concrete handler, no repository access, no transaction ownership decision is made. The contracts are pure types, consumed by nothing in this milestone.
2. **Does this presume a specific application framework or dispatch mechanism?** No — a `CommandHandler` Protocol describes a callable shape, not a registry, bus, or dispatcher; building any of those is explicitly deferred.
3. **Does this leak into APIs/workers?** No — `entrypoints/` is untouched; nothing here wires a command to any transport.
4. **Does this leak into retry policy?** No — retry-on-`OptimisticConcurrencyConflict` remains explicitly deferred behind "application services exist," and this milestone does not constitute application services, only their vocabulary.
5. **Is this milestone narrow enough to actually finish in one pass, unlike a full "application services" milestone would be?** Yes — it is contracts-only, matching M020's proven, narrow precedent exactly.
6. **Does this leak into M028?** No — nothing here presumes or requires any named future milestone; it only unblocks "Application Service Orchestration" as a future candidate, exactly as M020 unblocked M023.

## 19. Final Decision

```text
M027 APPLICATION COMMAND/HANDLER CONTRACTS SCOPE SELECTED
M027 DESIGN READY FOR INDEPENDENT REVIEW
M027 NOT APPROVED
M027 NOT FROZEN
M027 IMPLEMENTATION NOT STARTED
```
