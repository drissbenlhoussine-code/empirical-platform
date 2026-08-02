# MILESTONE-035 - Concrete Application Command Vertical Slice (Run Lifecycle Transition) Design Freeze

## 1. Milestone Identity

MILESTONE-035 — Concrete Application Command Vertical Slice: Run Lifecycle Transition, Design stage.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `0a039e730b7d16e4d6092898c24081e86330f1d6` |

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Run Creation) | APPROVED_AND_FROZEN |
| M034 (Run Retrieval) | APPROVED_AND_FROZEN (implementation freeze `3056e3010b4f20f3cf7bf2ab2e3fbbc43fcff825`) |

## 4. M035 Scope Authority

`MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE.md`, candidate commit `26aab1acb1d08150144b8ce52d63f17796f121ef`. Selects one Run lifecycle-transition command vertical slice, closing the sole remaining unproven `save()`/`OptimisticConcurrencyConflict` generalization gap.

## 5. M035 Scope-Freeze Authority

`MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE_FREEZE.md`, commit `cebbd945107f4242cada86eea29e210e7b7c701c`. **M035 SCOPE APPROVED_AND_FROZEN.** This design freeze makes no change to the scope or scope-freeze authority.

## 6. Original Design Candidate Commit

`bac7f202c4f6dca591702d4d1404a8390c4bb755` (`docs: define M035 Run lifecycle transition design candidate`) — selected `Run.authorize()` as the target transition, a caller-supplied `expected_persisted_version` command field, `SaveResult` as the result contract, and an independently-derived `append_manifest()`-based deterministic PostgreSQL conflict mechanism.

## 7. Independent Design-Review Decision

The independent hostile design review verified: repository truth; the design-only two-file delta; `Run.authorize()` reachability from `CREATED`; the exact full-identity command model; caller-supplied `expected_persisted_version`; the exact one-`get()`/one-mutation/one-`save()` sequence; `SaveResult` return; precise aggregate/persisted-version separation; transition-history semantics; transparent error behavior; no application transaction orchestration; genuine `append_manifest()`-based PostgreSQL conflict feasibility; complete success/invalid/not-found/conflict strategies; current architecture-boundary sufficiency; no scope creep; no M036 work.

**Decision: M035 DESIGN APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains.

## 8. Non-Blocking Observation

Design document Section 28 ("Validation Ownership") originally stated that `DomainIdentity`/`RunId`'s frozen `__post_init__` checks mean "a `AuthorizeRunCommand` cannot be constructed with a malformed identity" without distinguishing *what* is actually enforced at runtime versus only statically. Independently verified genuine before acting on it (not taken on faith): direct inspection of `src/empirical_platform/identifiers/pairs.py` confirms `DomainIdentity.__post_init__` checks only `isinstance(governance_id, Identifier)` — the *base* class — never the specific generic parameter (`RunId`). Python erases generic type parameters at runtime; nothing in `DomainIdentity`'s own code prevents constructing a `DomainIdentity` whose `governance_id` is some other `Identifier` subtype (e.g. `CampaignId`) and treating it, via static annotation only, as `DomainIdentity[RunId]`.

## 9. Observation Resolution

Section 28 corrected (in the design document, this same freeze mission, no other section touched) to state precisely: `RunId.__post_init__` validates governance-identifier format; `AggregateVersion.__post_init__` validates non-negativity; both genuinely reject invalid values at construction. `DomainIdentity.__post_init__` validates only the base identity-pair *structure* at runtime, not the specific `RunId` generic specialization — that specialization is expressed through static typing (mypy) only, and enforced downstream solely by whatever the `Run`/`RunRepository` contracts actually do with the value. No `__post_init__`, `isinstance` check, parser, or reconstruction logic was added to compensate — the handler performs no additional runtime type validation, consistent with every prior milestone's validation-ownership discipline.

## 10. Owner Approval

The owner formally freezes the M035 design via this document.

**M035 DESIGN APPROVED_AND_FROZEN.**

## 11. Frozen Run Transition

`Run.authorize()`: `CREATED` → `AUTHORIZED`. Directly reachable from the state M033's frozen `CreateRunHandler` already produces — zero additional setup. `reason` is optional. Selected over `start_acquisition`/`start_normalization`/`start_validation`/`complete_execution` (each requiring 1-4 prior transitions of test-setup scaffolding) and `cancel`/`fail` (each requiring prior setup plus a mandatory `reason` field) — none of which offer any additional architectural proof over `authorize()`.

## 12. Frozen Source and Target States

Source: `RunLifecycleState.CREATED`. Target: `RunLifecycleState.AUTHORIZED`. Both frozen since M012. No schema/migration implication.

## 13. Frozen Command Identity Model

`AuthorizeRunCommand.identity: DomainIdentity[RunId]` — the exact pairing `RunRepository.get()` requires, mirroring `GetRunQuery` (M034) and `PrepareCampaignForAuthorizationCommand` (M032). The exact identity object is passed unchanged to `RunRepository.get()`. No identity reconstruction, no governance-ID-only lookup, no runtime-ID generation.

## 14. Frozen Expected-Version Model

Caller-supplied `command.expected_persisted_version: AggregateVersion`. The handler must not substitute `loaded.persisted_version` — doing so would make a genuine stale-write scenario structurally unreachable and contradict `RunRepository.save()`'s own parameter-design intent. Verified directly against the frozen handler code block: `save(run, expected_persisted_version=command.expected_persisted_version)`.

## 15. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class AuthorizeRunCommand:
    identity: DomainIdentity[RunId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Exactly six fields, all directly required by `Run.authorize()` and/or `RunRepository.save()`. No transport metadata, tracing infrastructure, retry policy, idempotency framework, second-transition selector, or projection option.

## 16. Frozen Handler Contract

```python
class AuthorizeRunHandler:
    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, command: AuthorizeRunCommand) -> SaveResult:
        loaded = self._run_repository.get(command.identity)
        run = loaded.aggregate
        run.authorize(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._run_repository.save(
            run, expected_persisted_version=command.expected_persisted_version
        )
```

Sole constructor dependency: `run_repository: RunRepository`. No `CampaignRepository`, `EvidencePackageRepository`, concrete persistence adapter, `RuntimeIdentifierGenerator`, retry service, `Clock` collaborator, transaction manager, or composition framework. No explicit import of the `Run` class required.

## 17. Frozen Load–Mutate–Save Sequence

1. Receive one `AuthorizeRunCommand`.
2. Call `RunRepository.get(command.identity)` exactly once, unchanged identity.
3. Receive one `LoadedAggregate[Run]`; bind `run = loaded.aggregate`.
4. Call `run.authorize(actor=command.actor, occurred_at=command.occurred_at, correlation_id=command.correlation_id, reason=command.reason)` exactly once.
5. Call `RunRepository.save(run, expected_persisted_version=command.expected_persisted_version)` exactly once.
6. Return the resulting `SaveResult` unchanged.

No second `get()`. No second mutation. No retry. No Campaign access. No runtime-ID regeneration. No application-level transaction orchestration.

## 18. Frozen Result Contract

`SaveResult` (already-frozen type) — returned unchanged. Selected over raw `Run` (in-place-mutated, mutability leakage), `DomainIdentity[RunId]` (loses operation/version information), a new type (unjustified when `SaveResult` already exists), or `None` (discards useful information).

## 19. Aggregate-Version Semantics

`Run.version` (aggregate domain state) advances by exactly one when `authorize()` is called — distinct from `loaded.persisted_version` (load-time repository concurrency token) and distinct from `command.expected_persisted_version` (caller expectation, passed unchanged to `save()`). `PostgresRunRepository.save()` compares the caller-supplied `expected_persisted_version` against the currently *persisted* version, not against `run.version` directly.

## 20. Persisted-Version Semantics

`loaded.persisted_version` is read (available on the `LoadedAggregate`) but never used in the `save()` call — `command.expected_persisted_version` is used instead. A successful `save()` returns the repository's resulting persisted-version metadata through `SaveResult`.

## 21. Transition-History Semantics

`Run.authorize()` appends exactly one `StateTransitionRecord` (`from_state="CREATED"`, `to_state="AUTHORIZED"`, correct version, correct sequence, `actor`, `occurred_at`, `correlation_id`, `reason` — all sourced directly from the command's own fields). Frozen `PostgresRunRepository.save()` persists the full `transition_history` on every `UPDATED` operation, unmodified.

## 22. Invalid-Transition Behavior

If the persisted Run's current state is not `CREATED`, `Run._transition()` raises `ValueError` before any `save()` call is reached — `save()` is never invoked, no persisted state changes. Transparent, unchanged propagation.

## 23. Not-Found Behavior

Transparent, unchanged propagation of `AggregateNotFound` from `RunRepository.get()`. No mutation, no `save()` call.

## 24. Optimistic-Concurrency Behavior

Transparent, unchanged propagation of `OptimisticConcurrencyConflict` when `command.expected_persisted_version` does not match the currently persisted version. Exactly one `save()` attempt; no retry, no automatic conflict recovery.

## 25. Arbitrary Error Semantics

Any other exception (`InvalidPersistedAggregateState`, `InvalidAggregateForPersistence`, arbitrary lower-level failures) propagates unchanged. No new error hierarchy, no wrapper.

## 26. Validation Ownership

Command performs no validation of its own. `RunId`/`AggregateVersion` validate their own values at construction. `DomainIdentity` validates only the base identity-pair structure at runtime — `RunId` generic specialization is expressed statically, not runtime-enforced (Section 8-9). `actor`/`occurred_at`/`correlation_id`/`reason` validated entirely by `Run._transition()`. Handler performs no independent or duplicate validation.

## 27. Transaction Non-Ownership

No application-level transaction orchestration. `RunRepository.get()` and `RunRepository.save()` each own their own transaction internally. No `run_composed()`. `save()`'s own `WHERE ... AND version = :expected_persisted_version` clause is the consistency mechanism, not an app-level transaction spanning both calls.

## 28. CommandEntryPoint Binding

Test-only direct construction (`CommandEntryPoint(AuthorizeRunHandler(run_repository=...))`). No registry, command bus, dispatcher, mediator, service locator, DI framework, or production composition root.

## 29. Package and Dependency Boundaries

Approved production module: `src/empirical_platform/usecases/authorize_run.py`. Required imports: `dataclasses.dataclass`; `datetime.datetime`; `empirical_platform.identifiers.pairs.DomainIdentity`; `empirical_platform.identifiers.types.RunId`; `empirical_platform.run.repository.RunRepository`; `empirical_platform.shared.contracts.repository.SaveResult`; `empirical_platform.shared.domain.versioning.AggregateVersion`. No import of `empirical_platform.run.aggregate.Run` required.

## 30. Architecture-Checker Impact

**None required.** `ALLOWED["usecases"] = {"shared", "identifiers", "campaign", "run"}` already grants `"run"` and `"shared"` — verified directly against live `tools/check_architecture.py`. Zero new `ALLOWED` entry, zero `FORBIDDEN_IMPORT_PREFIXES` change.

## 31. PostgreSQL Success Strategy

Seed Campaign (M030) and Run (M033); Run starts `CREATED`, `persisted_version == AggregateVersion(0)`. Bind `AuthorizeRunHandler` through `CommandEntryPoint`; invoke with `expected_persisted_version=AggregateVersion(0)`. Assert `SaveResult.operation is SaveOperation.UPDATED`, `SaveResult.persisted_version == AggregateVersion(1)`; independently reload and assert `state is AUTHORIZED`, `persisted_version == AggregateVersion(1)`, and the correct `transition_history[-1]` record.

## 32. PostgreSQL Invalid-Transition Strategy

Seed as above; independently advance the *persisted* Run past `CREATED` first (direct repository/domain scaffolding, not through the command under test). Invoke `AuthorizeRunCommand`; assert the domain `ValueError` propagates unchanged, `save()` was never reached, and persisted state is unchanged from the independent advancement.

## 33. PostgreSQL Missing-Run Strategy

Construct a `DomainIdentity[RunId]` never persisted. Invoke `AuthorizeRunCommand`; assert `AggregateNotFound` propagates unchanged; no mutation, no `save()`.

## 34. Deterministic Conflict Strategy

Frozen, exact, thirteen-step sequence:

1. Persist a Run in `CREATED` at persisted version `0` (via frozen M030/M033 seeding).
2. Independently load a second `Run` aggregate instance for the same identity (direct repository access, test scaffolding only).
3. Call `append_manifest(...)` on that interfering instance with a valid `DatasetManifest`.
4. Confirm `append_manifest()` advances the aggregate's in-memory version while preserving `CREATED` (verified directly against `run/aggregate.py`).
5. Save the interfering aggregate with `expected_persisted_version=AggregateVersion(0)` — succeeds.
6. Confirm the persisted version advances to `1` while persisted state remains `CREATED` (independent reload).
7. Construct `AuthorizeRunCommand` with the now-stale `expected_persisted_version=AggregateVersion(0)`.
8. The handler's own `get()` loads a fresh instance still at `CREATED`.
9. `run.authorize()` succeeds domain-validly in memory (source-state precondition still satisfied).
10. The handler calls `save(..., expected_persisted_version=AggregateVersion(0))`.
11. The repository's `WHERE ... AND version = 0` clause matches zero rows against the real persisted version (`1`); `OptimisticConcurrencyConflict` is raised.
12. No retry, no second `save()` attempt occurs.
13. The persisted row remains exactly what step 5 produced (`CREATED`, `persisted_version == AggregateVersion(1)`, the step-3 manifest present) — independently reloaded and asserted.

`append_manifest()`'s use here is **test scaffolding only** — it does not authorize `append_manifest()` (or any second capability) as a production use case for M035.

## 35. Test Obligations

Frozen from the design document Section 37 (A-J): command field/immutability/slots tests; handler success with exact call-count and argument assertions (including the deliberate `command.expected_persisted_version` vs. `loaded.persisted_version` distinction proof); domain-invalid-transition; `AggregateNotFound`; `OptimisticConcurrencyConflict`; arbitrary `get()`/`save()` failures; `CommandHandler`/`CommandEntryPoint` structural conformance; architecture evidence; the full PostgreSQL strategy set (Sections 31-34) plus M033/M034 regression. No arbitrary coverage threshold.

## 36. Implementation Authorization Boundary

A future M035 implementation mission may touch only what is narrowly required for: `src/empirical_platform/usecases/authorize_run.py`; necessary `usecases` package exports; focused unit tests; focused contract tests; PostgreSQL integration tests; narrowly justified architecture evidence (only if it provides genuine new proof); the M035 implementation document; `PROJECT_CHECKPOINT.md`; the mandatory external-review package.

It must not modify: `Run` aggregate; `RunRepository`; `PostgresRunRepository`; identity/version contracts; `SaveResult`; `CommandHandler`; `CommandEntryPoint`; architecture permissions; schemas or migrations; M030-M034 source; any frozen governance authority.

## 37. Prohibited Expansion

No second Run transition; no generic lifecycle framework; no retry/backoff or automatic conflict recovery; no Campaign behavior change; no `EvidencePackage`/`Review` work; no generic save/concurrency framework; no composition root, registry, command bus, dispatcher, mediator, service locator, or DI framework; no transport/API; no caching; no worker/queue/scheduler; no audit integration; no schema/migration changes; no market-data/trading behavior; no MILESTONE-036 work.

## 38. Preserved M020-M034 Authority

This freeze makes no change to any M020-M034 frozen contract, source file, test, or governance document, and no change to the M035 scope or scope-freeze authority (Sections 4-5). All prior authority remains exactly as previously frozen.

## 39. Deferred Work

A second Run lifecycle-transition command (future milestone, once evidenced); `EvidencePackage`/`Review` creation and retrieval; retry-on-`OptimisticConcurrencyConflict` policy (closer to justifiable after this milestone, still not authorized); read-to-update `expected_persisted_version` acquisition for a real caller workflow (M034's own known limitation, unchanged); any composition-root abstraction beyond direct binding; MILESTONE-036 and beyond.

## 40. Final Status

**M035 DESIGN APPROVED_AND_FROZEN.**

M035 Implementation: NOT_STARTED.
M036: NOT_STARTED.

## 41. Next Permitted Action

**MILESTONE-035 IMPLEMENTATION MISSION.**
