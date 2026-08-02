# MILESTONE-035 - Concrete Application Command Vertical Slice (Run Lifecycle Transition) Design

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW**

This document is a design candidate. It has not been reviewed, approved, or frozen. It does not authorize implementation.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at design | `6ca576eca0dbd266f9b52672be80326a42ee138d` |

---

## 3. Frozen Authority Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Run Creation) | APPROVED_AND_FROZEN |
| M034 (Run Retrieval) | APPROVED_AND_FROZEN (implementation freeze `3056e3010b4f20f3cf7bf2ab2e3fbbc43fcff825`) |
| M035 Scope | APPROVED_AND_FROZEN (`MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE_FREEZE.md`, commit `cebbd945107f4242cada86eea29e210e7b7c701c`) |

---

## 4. Architectural Context

The frozen M035 scope authorizes exactly one capability: a command vertical slice performing one Run lifecycle transition via the frozen `RunRepository.save()` and `OptimisticConcurrencyConflict` contract, proving the `save()`/optimistic-concurrency pattern — established and validated exclusively against `Campaign` via `PrepareCampaignForAuthorizationHandler` (M032) — generalizes to a second aggregate. The scope explicitly left the transition selection, identity model, expected-version model, result contract, and conflict mechanism open; this design resolves every one of those questions.

---

## 5. Run Lifecycle Method Inventory

Verified directly against `src/empirical_platform/run/aggregate.py`:

| Method | Allowed source state(s) | Result state | `reason` | Manifest-append compatible before/after |
| --- | --- | --- | --- | --- |
| `authorize` | `CREATED` | `AUTHORIZED` | optional | CREATED: yes; AUTHORIZED: yes |
| `start_acquisition` | `AUTHORIZED` | `ACQUIRING` | optional | AUTHORIZED: yes; ACQUIRING: yes |
| `start_normalization` | `ACQUIRING` | `NORMALIZING` | optional | ACQUIRING: yes; NORMALIZING: yes |
| `start_validation` | `NORMALIZING` | `VALIDATING` | optional | NORMALIZING: yes; VALIDATING: yes |
| `complete_execution` | `VALIDATING` | `EXECUTION_COMPLETED` | optional | VALIDATING: yes; EXECUTION_COMPLETED: no (terminal, not in `_MANIFEST_APPEND_STATES`) |
| `cancel` | `AUTHORIZED` | `CANCELLED` | **required** | AUTHORIZED: yes; CANCELLED: no |
| `fail` | `ACQUIRING`, `NORMALIZING`, `VALIDATING` | `FAILED` | **required** | source: yes; FAILED: no |

All seven signatures take `*, actor: str, occurred_at: datetime, correlation_id: str | None = None`, plus `reason` (optional for `authorize`/`start_acquisition`/`start_normalization`/`start_validation`/`complete_execution`; required for `cancel`/`fail`). Every transition advances `Run.version` by one and appends exactly one `StateTransitionRecord` to `Run.transition_history` — verified directly in `Run._transition()`.

The only non-transition Run mutator is `Run.append_manifest()`: advances `Run.version` by one, does **not** change `Run.state`, and is permitted only while `Run.state` is one of `_MANIFEST_APPEND_STATES = (CREATED, AUTHORIZED, ACQUIRING, NORMALIZING, VALIDATING)` — verified directly.

---

## 6. Transition Candidate Analysis

| Candidate | Reachability from freshly created Run | Extra setup beyond frozen M033 `CreateRunHandler` | `reason` required | Assessment |
| --- | --- | --- | --- | --- |
| `authorize` (CREATED→AUTHORIZED) | Directly reachable — `CREATED` is `Run`'s post-creation state | None | No | Zero-setup PostgreSQL evidence; simplest field surface |
| `start_acquisition` (AUTHORIZED→ACQUIRING) | Requires a prior `authorize()` | Direct repository/domain test scaffolding to reach `AUTHORIZED` first | No | Adds test-setup complexity for no additional architectural proof |
| `start_normalization` (ACQUIRING→NORMALIZING) | Requires prior `authorize()`+`start_acquisition()` | Deeper scaffolding chain | No | Same class of unnecessary complexity, worse |
| `start_validation` (NORMALIZING→VALIDATING) | Three prior transitions | Deepest scaffolding chain among the "start_*" group | No | Same, worse |
| `complete_execution` (VALIDATING→EXECUTION_COMPLETED) | Four prior transitions | Deepest scaffolding chain overall | No | Same, worst |
| `cancel` (AUTHORIZED→CANCELLED) | Requires a prior `authorize()` | Scaffolding to reach `AUTHORIZED` | **Yes** | Adds setup and a mandatory field for no additional proof; also terminal, foreclosing later reuse of the same seeded Run for other test scenarios in this milestone |
| `fail` (ACQUIRING/NORMALIZING/VALIDATING→FAILED) | Requires 2-4 prior transitions | Deep scaffolding | **Yes** | Same disadvantages as `cancel`, compounded |

None of these differences affect the *architectural* proof this milestone exists to deliver (that `save()`/`OptimisticConcurrencyConflict` generalizes to `Run`) — every transition exercises the identical `get()`→mutate→`save()` mechanism identically. The selection is therefore made on reachability/simplicity grounds, not architectural necessity, exactly mirroring M032's own selection criteria for `Campaign.prepare_for_authorization()`.

---

## 7. Selected Run Transition

**`Run.authorize()`: `CREATED` → `AUTHORIZED`.**

Directly reachable from the state `CreateRunHandler` (M033) already produces — zero additional setup beyond the already-frozen M033 creation slice, exactly mirroring M032's own selection of `Campaign.prepare_for_authorization()` as "the literal first lifecycle transition, reachable directly from the `DRAFT` state M030 already produces." `reason` is optional, keeping the command's minimal field surface identical in shape to `PrepareCampaignForAuthorizationCommand`. Every other candidate was rejected solely for requiring additional test-setup depth with no corresponding architectural benefit (Section 6) — not for any domain-behavior deficiency.

---

## 8. Source and Target State

Source: `RunLifecycleState.CREATED`. Target: `RunLifecycleState.AUTHORIZED`. Both frozen since M012 (`campaign/lifecycle.py`). No schema or migration implication — `run.lifecycle_state` already stores this value as free text validated by a frozen `CHECK` constraint (verified in `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py`).

---

## 9. Domain Argument Semantics

`Run.authorize(*, actor: str, occurred_at: datetime, correlation_id: str | None = None, reason: str | None = None) -> None`. `actor` must be non-empty (`_require_non_empty`); `occurred_at` must be a `datetime`; `correlation_id`/`reason` are optional but must be non-empty strings if provided (`_require_optional_non_empty`). All validation is owned by `Run._transition()`/`_require_non_empty`/`_require_optional_non_empty` — frozen, unmodified, unmodified by this design.

---

## 10. Query/Command Identity Candidate Analysis

| Candidate | Description | Assessment |
| --- | --- | --- |
| A | Command carries full `DomainIdentity[RunId]` | Directly compatible with `RunRepository.get()`'s exact signature, zero translation. Identical to `GetRunQuery` (M034) and `PrepareCampaignForAuthorizationCommand` (M032). |
| B | Raw governance/runtime strings; handler reconstructs the identity | Would require the handler to carry a `RuntimeIdentifierGenerator`-like dependency it has no use for (this command does not mint a new identity — it operates on an existing one), or accept a pass-through runtime-id string with no validation benefit over accepting the already-constructed pair. |
| C | `RunId` plus a separate runtime identifier field | Adds an unnecessary reconstruction step the caller could perform once, before constructing the command, with no benefit. |
| D | Governance ID only, requiring identity resolution | No resolution mechanism exists anywhere in the frozen codebase (confirmed by M034's own identical analysis, unchanged since). Rejected on the same repository evidence. |

---

## 11. Selected Identity Model

**Candidate A.** `AuthorizeRunCommand.identity: DomainIdentity[RunId]` — the exact, already-validated pairing `RunRepository.get()` requires, mirroring `GetRunQuery` and `PrepareCampaignForAuthorizationCommand` exactly.

---

## 12. Expected Persisted Version Candidate Analysis

This is the central load-bearing decision, mirroring M032's own most consequential choice.

| Candidate | Description | Assessment |
| --- | --- | --- |
| A | Caller supplies `expected_persisted_version` as a command field | Matches `RunRepository.save()`'s own frozen signature intent — the parameter exists specifically to be supplied by whoever calls `save()`, i.e. the application layer, not internally recomputed. Genuinely testable without an interleaving hook: an interfering writer can land between the caller's original read and this command's invocation, and the command legitimately carries a now-stale value. |
| B | Handler uses `loaded.persisted_version` (from its own internal `get()` call) automatically | Since the handler's own `get()` happens immediately before its own `save()`, the "expected" value would always equal the value the handler just read — a stale-write conflict could then only ever be reached via an artificial interleaving *inside* the handler's own method body (e.g. monkeypatching between the internal `get()` and `save()` calls), which is a materially weaker, more artificial form of test evidence than a real caller-driven scenario. It would also make `expected_persisted_version` structurally redundant as a caller-supplied concept, contradicting why `RunRepository.save()`'s signature requires an explicit parameter at all. |
| C | Handler performs another read or version-resolution operation | Adds a second repository call with no benefit over A; not evidenced by any frozen dependency. |
| D | A runtime collaborator supplies the version | No such collaborator exists or is frozen; would be new, unjustified infrastructure. |

---

## 13. Selected Expected-Version Model

**Candidate A: caller-supplied `expected_persisted_version: AggregateVersion` command field**, exactly mirroring `PrepareCampaignForAuthorizationCommand`. The handler must not silently replace it with `loaded.persisted_version` — doing so would eliminate the only path by which a genuine stale-write scenario (an interfering writer between when the caller's originating knowledge of the Run's state was formed and when this command executes) can ever surface as `OptimisticConcurrencyConflict`, undermining this milestone's entire proof obligation. (Known, already-accepted limitation, not solved here: M034's `RunSnapshot` does not expose `persisted_version`, so a real caller currently has no usecases-layer-sanctioned way to obtain the value to populate this field — identical to the gap M034's own design freeze already disclosed and deferred as a separate future capability; this command's contract is unaffected by how the caller eventually obtains the value.)

---

## 14. Result Contract Candidate Analysis

| Candidate | Description | Assessment |
| --- | --- | --- |
| A | Return `SaveResult` | Already exists as a frozen type (`shared/contracts/repository.py`); exactly mirrors `PrepareCampaignForAuthorizationHandler`'s own return contract; gives the caller the resulting `persisted_version` and `SaveOperation`, both genuinely useful on a write path (unlike M031/M034's read-side reasoning for excluding `persisted_version`, a write-side caller has legitimate use for confirming the new persisted version — the same reasoning M032 already applied). |
| B | Return `DomainIdentity[RunId]` | Loses whether the operation updated or was a no-op, and loses the new persisted version — strictly less useful than A for no simplicity benefit, since `SaveResult` already exists. |
| C | Return the mutated `Run` aggregate | `Run` remains mutable after this call (the handler mutated it in place via `authorize()`); returning it hands the caller a live, further-mutable object with no path back to persistence for any additional in-place changes — the same class of aggregate-mutability-leakage risk M034 already rejected for its own (read-side) result contract. |
| D | A new immutable transition-result type | Unjustified — `SaveResult` already exists and fully suffices; introducing a new type here would violate this project's established minimalism discipline for zero added benefit. |
| E | Return `None` | Discards genuinely useful information (the new persisted version) for no benefit. |

---

## 15. Selected Result Contract

**Candidate A: `SaveResult`.** Already-frozen type, already-proven-once return contract (M032), no new type introduced. `SaveOperation`/`persisted_version` give the caller confirmation of the mutation's outcome.

---

## 16. Selected Architecture

One command type (`AuthorizeRunCommand`), one handler type (`AuthorizeRunHandler`), one module (`empirical_platform/usecases/authorize_run.py`), bound to the frozen `CommandEntryPoint` at test-construction time only. No new package, no new Protocol, no new collaborator type. Structurally identical in shape (not content) to `usecases/prepare_campaign_for_authorization.py`.

---

## 17. Exact Command Contract

Module: `empirical_platform/usecases/authorize_run.py`

```python
@dataclass(frozen=True, slots=True)
class AuthorizeRunCommand:
    """Request to transition an existing Run from CREATED to AUTHORIZED."""

    identity: DomainIdentity[RunId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Exactly six fields, all directly required by `Run.authorize()` and/or `RunRepository.save()` — no extraneous field. Immutable (`frozen=True`), no extra attributes possible (`slots=True`). No transport metadata, tracing infrastructure, retry policy, idempotency framework, second-transition selector, generic mutation name, or projection option.

---

## 18. Exact Handler Contract

```python
class AuthorizeRunHandler:
    """Authorizes an existing Run for one `AuthorizeRunCommand`."""

    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, command: AuthorizeRunCommand) -> SaveResult:
        """Load, authorize, and persist the identified Run."""
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

Sole constructor dependency: `run_repository: RunRepository`. No `CampaignRepository` (this capability touches only the already-existing Run row; no Campaign lookup is needed or performed by `RunRepository.get()`/`save()`, verified in Section 5 of the M034 design and unchanged here), no `EvidencePackageRepository`, no concrete persistence adapter, no `RuntimeIdentifierGenerator` (this command operates on an existing identity, mints nothing new), no retry service, no `Clock` collaborator (`occurred_at` is caller-supplied, mirroring `PrepareCampaignForAuthorizationCommand`'s own established precedent — no frozen evidence anywhere in this codebase favors a handler-owned time source over a caller-supplied one), no transaction manager, no composition framework. The module needs no explicit import of the `Run` class itself — mirroring `prepare_campaign_for_authorization.py`'s own precedent exactly, since no new `Run` instance is constructed here, only a method called on the loaded instance.

---

## 19. Exact Load–Mutate–Save Sequence

1. `AuthorizeRunHandler.handle(command)` receives one `AuthorizeRunCommand`.
2. Calls `self._run_repository.get(command.identity)` exactly once, passing `command.identity` unchanged.
3. Receives one `LoadedAggregate[Run]`; binds `run = loaded.aggregate`.
4. Calls `run.authorize(actor=command.actor, occurred_at=command.occurred_at, correlation_id=command.correlation_id, reason=command.reason)` exactly once — this mutates `run` in place (frozen `Run._transition()` behavior, unmodified), advancing `run.version` by one and appending one `StateTransitionRecord`.
5. Calls `self._run_repository.save(run, expected_persisted_version=command.expected_persisted_version)` exactly once — passing `command.expected_persisted_version`, **not** `loaded.persisted_version` (Section 13).
6. Returns the resulting `SaveResult` unchanged.

No second `get()`. No second mutation. No retry. No save retry. No runtime-ID regeneration (identity is preserved unchanged throughout — `Run.authorize()` never touches `_identity`). No Campaign access. No application-level transaction orchestration (Section 29).

---

## 20. Return Semantics

Exactly one `SaveResult` per successful `handle()` call, satisfying `CommandHandler`'s `_ResultT_co` and `CommandEntryPoint[CommandT, ResultT]`'s `__call__` return type unchanged (the frozen `CommandEntryPoint` performs no wrapping — verified in `application/command.py`, unmodified).

---

## 21. Aggregate-Version Semantics

`run.version` advances by exactly one in memory when `authorize()` is called (Section 5). `RunRepository.save()` receives `expected_persisted_version=command.expected_persisted_version` — a value the caller supplied, independent of what `run.version` happens to equal at save time. `PostgresRunRepository.save()` (unmodified, verified directly) compares the caller-supplied `expected_persisted_version` against the currently *persisted* version via `WHERE ... AND version = :expected_persisted_version`; it does not compare against `run.version` directly. This design does not conflate `run.version` with `expected_persisted_version` or with `persisted_version` anywhere — each is named and used precisely, consistent with the M034 design correction's own precedent for this exact class of error.

---

## 22. Persisted-Version Semantics

`loaded.persisted_version` (from the handler's own `get()` call) is read but never used in the `save()` call — `command.expected_persisted_version` is used instead (Section 13). This is a deliberate, explicitly-justified design choice, not an oversight.

---

## 23. Transition-History Semantics

`Run.authorize()` appends exactly one `StateTransitionRecord` (frozen, unmodified `Run._transition()` behavior) carrying `from_state="CREATED"`, `to_state="AUTHORIZED"`, the new version, the transition sequence, `actor`, `occurred_at`, `identity_reference=run.identity`, `correlation_id`, and `reason` — all sourced directly from the command's own fields, with no handler-level transformation. `PostgresRunRepository.save()` persists the full `transition_history` on every `save()` call when the operation is `UPDATED` (verified directly — it deletes and re-inserts `run_transition` rows), unmodified by this design.

---

## 24. Domain Invalid-Transition Behavior

If the persisted Run's current state is not `CREATED` when `run.authorize()` is called, `Run._transition()` raises `ValueError` (frozen, unmodified) **before** any repository `save()` call is reached — `save()` is never invoked in this path, so no persisted state changes. Transparent, unchanged propagation through `AuthorizeRunHandler`/`CommandEntryPoint` — no `try`/`except`, no translation, no wrapper.

---

## 25. Not-Found Behavior

Transparent, unchanged propagation of `AggregateNotFound` from `RunRepository.get()` — required by the already-frozen `CommandEntryPoint` contract itself, which propagates results and exceptions unchanged (identical reasoning to M034's own not-found decision for `QueryEntryPoint`). No mutation and no `save()` call occur in this path.

---

## 26. Optimistic-Concurrency Behavior

Transparent, unchanged propagation of `OptimisticConcurrencyConflict` from `RunRepository.save()` when the caller-supplied `command.expected_persisted_version` does not match the currently persisted version. Exactly one `save()` attempt is made — no retry, no second attempt, no automatic conflict recovery (explicitly out of scope, Section 41).

---

## 27. Arbitrary Error Semantics

Any other exception from `RunRepository.get()` (e.g. `InvalidPersistedAggregateState`) or `RunRepository.save()` (e.g. `InvalidAggregateForPersistence`, or an arbitrary lower-level failure) propagates unchanged through `AuthorizeRunHandler`/`CommandEntryPoint`, identically to every other error class. No new error hierarchy, no wrapper type, no generic mutation-error base class is introduced.

---

## 28. Validation Ownership

- **Command construction:** `AuthorizeRunCommand` performs no validation of its own; field typing is a dataclass mechanism only (does not runtime-enforce types, mirroring the M034 design correction's own precise wording).
- **`RunId`/`DomainIdentity`/`AggregateVersion`:** already fully validated at construction time by their own frozen `__post_init__` checks — a `AuthorizeRunCommand` cannot be constructed with a malformed identity or a negative version in the first place, because those types themselves reject invalid values.
- **`actor`/`occurred_at`/`reason`/`correlation_id`:** validated entirely by `Run._transition()`/`_require_non_empty`/`_require_optional_non_empty` (frozen, unmodified) when `authorize()` is called — not duplicated by the handler.
- **`Run` aggregate mutation:** no new validation; entirely owned by the frozen `Run.authorize()`/`_transition()` path.
- **Repository reconstruction/persistence:** all existing frozen validation (foreign-key, version-floor, reconstruction) is unchanged.
- **Handler:** performs no independent or duplicate validation of its own — it trusts the command's fields exactly as received, mirroring `PrepareCampaignForAuthorizationHandler`.
- **`SaveResult`:** an existing frozen type; this design adds no new validation to it.

No frozen identifier, aggregate, or repository validation is duplicated anywhere in this design.

---

## 29. Transaction Ownership

No application-level transaction orchestration. `RunRepository.get()` and `RunRepository.save()` each own their own transaction internally via `self._service.unit_of_work()` (verified directly in `PostgresRunRepository`, unmodified) — this milestone performs exactly one `get()` and exactly one `save()`, each already atomic at the repository level. No `run_composed()` (that primitive exists for atomically composing *multiple* repository operations sharing one `PostgresPersistenceService`, which does not apply here — identical reasoning to M034's own transaction-ownership decision, and matching M032's own explicit "No application transaction orchestration" decision for the structurally identical `Campaign` case). The consistency model remains sound under optimistic concurrency precisely because `save()`'s own `WHERE ... AND version = :expected_persisted_version` clause — not an application-level transaction spanning `get()` and `save()` — is what detects and rejects a stale write; this is the entire mechanism optimistic concurrency exists to provide, and wrapping `get()`+`save()` in one additional transaction would neither add nor remove any safety property already guaranteed by that clause.

---

## 30. CommandEntryPoint Binding

Test-only direct construction, mirroring M032's exact pattern:

```python
handler = AuthorizeRunHandler(run_repository=run_repository)
entry_point = CommandEntryPoint(handler)
result = entry_point(AuthorizeRunCommand(...))
```

The bound handler is invoked exactly once per call, receives the exact command instance, and its result/exception propagates unchanged (frozen `CommandEntryPoint` invariant, unmodified). No registry, command bus, dispatcher, mediator, service locator, DI framework, or production composition root is introduced — consistent with every prior milestone's binding discipline (M030-M034).

---

## 31. Package and Dependency Boundaries

- **Module:** `src/empirical_platform/usecases/authorize_run.py` — follows the established `<verb>_<aggregate>.py` precedent (`create_campaign.py`, `get_campaign.py`, `prepare_campaign_for_authorization.py`, `create_run.py`, `get_run.py`).
- **Imports required:** `dataclasses.dataclass`; `datetime.datetime`; `empirical_platform.identifiers.pairs.DomainIdentity`; `empirical_platform.identifiers.types.RunId`; `empirical_platform.run.repository.RunRepository`; `empirical_platform.shared.contracts.repository.SaveResult`; `empirical_platform.shared.domain.versioning.AggregateVersion`. No import of `empirical_platform.run.aggregate.Run` is required (Section 18).
- **Package-boundary check:** `ALLOWED["usecases"] = {"shared", "identifiers", "campaign", "run"}` (verified directly, unchanged since M034) already grants `"run"` (for `RunRepository`) and `"shared"` (for `SaveResult`/`AggregateVersion`). **Zero new `ALLOWED` entry is required.**
- **Forbidden-prefix check:** `FORBIDDEN_IMPORT_PREFIXES["usecases"]` already blocks `empirical_platform.shared.persistence`, `sqlalchemy`, `psycopg`, `boto3` (verified directly, unchanged). `authorize_run.py` imports none of these.

---

## 32. Architecture-Checker Impact

**None.** No change to `ALLOWED`, `ALLOWED_EXACT_IMPORTS`, or `FORBIDDEN_IMPORT_PREFIXES` is required or authorized by this design. Existing `usecases` positive/negative fixtures already cover the exact permissions this module relies on (import `run`/`shared`, forbid persistence) — no new fixture is required; the real, non-fixture architecture-checker run over the actual new source file is itself the positive-case evidence, exactly as M033/M034 relied on.

---

## 33. PostgreSQL Success Strategy

Mirrors `tests/integration/test_m032_prepare_campaign_for_authorization_usecase.py`'s established pattern, opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, against a freshly migrated real database:

1. **Campaign seeding:** via the frozen M030 `CreateCampaignHandler`.
2. **Run seeding:** via the frozen M033 `CreateRunHandler`, targeting the seeded Campaign — the resulting Run is at `CREATED`, `persisted_version == AggregateVersion(0)`.
3. **Real `RunRepository` obtained externally:** `PostgresRunRepository(service)` constructed by the test's own fixtures — `usecases` itself never constructs or imports a persistence adapter.
4. **`CommandEntryPoint` binding:** `AuthorizeRunHandler(run_repository=...)` wrapped in `CommandEntryPoint`, invoked with `AuthorizeRunCommand(identity=..., expected_persisted_version=AggregateVersion(0), actor="tester", occurred_at=..., correlation_id="corr-golden", reason="ready for acquisition")`.
5. **Golden-path assertions:** `SaveResult.operation is SaveOperation.UPDATED`; `SaveResult.persisted_version == AggregateVersion(1)`; independently reloading the Run via `run_repo.get(identity)` and asserting `state is RunLifecycleState.AUTHORIZED`, `persisted_version == AggregateVersion(1)`, and that `transition_history[-1]` carries `from_state="CREATED"`, `to_state="AUTHORIZED"`, the supplied `actor`/`correlation_id`/`reason`.

---

## 34. PostgreSQL Invalid-Transition Strategy

1. Seed Campaign and Run as in Section 33, leaving the Run at `CREATED`.
2. Independently advance the *persisted* Run past `CREATED` first — e.g. reload it and call `authorize()` directly via the repository (test scaffolding, not through `AuthorizeRunHandler`, exactly mirroring how M032's invalid-transition test independently pre-advances the Campaign before exercising the command under test), so the persisted state becomes `AUTHORIZED`.
3. Invoke `AuthorizeRunCommand` (targeting `authorize()`, source state `CREATED`) against this now-`AUTHORIZED` Run through `CommandEntryPoint`.
4. Assert the domain `ValueError` (Section 24) propagates unchanged; assert `save()` was never reached (no version change beyond step 2's own advancement); assert the persisted state remains exactly what step 2 produced.

---

## 35. PostgreSQL Missing-Run Strategy

1. Construct a `DomainIdentity[RunId]` for a governance/runtime pair that was never persisted.
2. Invoke `AuthorizeRunCommand` through `CommandEntryPoint`.
3. Assert `AggregateNotFound` propagates unchanged; assert no mutation and no `save()` call occurred (nothing to assert against persisted state, since nothing was ever created).

---

## 36. Deterministic PostgreSQL Conflict Strategy

Independently derived for `Run`'s own available mutator — not a restatement of M032's mechanism, since `Run` has no method named `revise_scope_statement()`. The only Run mutator that advances `AggregateVersion` while leaving `RunLifecycleState` unchanged is `Run.append_manifest()` (Section 5), permitted while the Run is `CREATED` — exactly the state the command under test requires. This makes `append_manifest()` the Run-specific structural analogue of `Campaign.revise_scope_statement()`, independently confirmed by direct inspection of `run/aggregate.py`, not assumed by symmetry.

Exact numbered sequence:

1. Seed Campaign (M030) and Run (M033) as in Section 33; the Run is `CREATED`, `persisted_version == AggregateVersion(0)`.
2. Simulate an interfering writer: independently reload the same identity via `run_repo.get(identity)` (test scaffolding — direct repository access, not through any usecase; `usecases` provides no mechanism to append a manifest and none is introduced here).
3. Call `append_manifest(...)` on that independently-loaded aggregate with a valid `DatasetManifest` for the same Run's `governance_id`. This advances the aggregate's in-memory version to `1` while `state` remains `CREATED` (Section 5).
4. `run_repo.save(interfering.aggregate, expected_persisted_version=AggregateVersion(0))` — succeeds (the persisted version was still `0`, matching); the persisted version becomes `1`; the persisted `lifecycle_state` remains `CREATED` (`append_manifest()` never touches it). **Test setup only — this does not authorize `append_manifest()` as a second production use case for M035** (Section 41).
5. Independently reload and assert `persisted_version == AggregateVersion(1)` and `state is RunLifecycleState.CREATED`, confirming step 4's effect before proceeding.
6. Invoke `AuthorizeRunCommand` through `CommandEntryPoint`, carrying `expected_persisted_version=AggregateVersion(0)` (now stale) and the same identity.
7. Internally, the handler's own `get()` loads a fresh instance still at `CREATED` (unaffected by step 3's in-memory-only advancement on a *different* Python object) — `run.authorize()` succeeds domain-validly in memory (source state `CREATED` is still satisfied), advancing this instance's own in-memory version. `save(..., expected_persisted_version=AggregateVersion(0))` then finds the real persisted version is `1` (from step 4) — the `WHERE ... AND version = 0` clause matches zero rows, and `OptimisticConcurrencyConflict` is raised (frozen `PostgresRunRepository.save()` behavior, unmodified).
8. Assert `OptimisticConcurrencyConflict` propagates unchanged through `CommandEntryPoint`; assert `excinfo.value.expected_persisted_version == AggregateVersion(0)` and `excinfo.value.actual_persisted_version == AggregateVersion(1)`; assert no retry and no second `save()` attempt occurred; independently reload and assert the persisted state remains exactly what step 4 produced (`state is CREATED`, `persisted_version == AggregateVersion(1)`, and the manifest from step 3 is present) — proving the failed conditional `UPDATE` changed nothing.

---

## 37. Test Strategy

**A. Command tests** — exact six fields; object/value preservation (`command.identity is <original>`, `command.expected_persisted_version is <original>`); immutability (`AttributeError` on assignment); no defaults beyond `correlation_id`/`reason`; no extra fields (`__slots__` set check); no duplicated validation.

**B. Handler success** — sole dependency is `RunRepository` (a recording fake); `get()` called exactly once with `command.identity` unchanged; `authorize()` called exactly once on the loaded aggregate with exactly the command's `actor`/`occurred_at`/`correlation_id`/`reason`; `save()` called exactly once with the mutated aggregate and exactly `command.expected_persisted_version` (**not** `loaded.persisted_version` — assert these are deliberately different values in the test, mirroring the M034 non-blocking-observation discipline of using genuinely distinguishable values, not defaults); exact `SaveResult` returned unchanged; no second repository operation; synchronous behavior.

**C. Expected-version proof** — construct a fake `LoadedAggregate` whose `persisted_version` differs from the command's `expected_persisted_version`; assert the fake repository's recorded `save()` call received the command's value, proving the design rule of Section 13 exactly, not merely asserting it in prose.

**D. Domain-invalid transition** — a fake repository returning a `Run` already in `AUTHORIZED`; assert the exact `ValueError` propagates; assert the fake's `save()` was never called (raises `AssertionError` if invoked, mirroring the established fake-repository pattern from every prior milestone's tests).

**E. `AggregateNotFound`** — a failing fake repository; assert exact exception-instance propagation (`excinfo.value is exc`); assert no mutation attempted (nothing to mutate — the fake's `get()` itself raises); assert `save()` never called.

**F. `OptimisticConcurrencyConflict`** — a fake repository whose `save()` raises; assert exact exception-instance propagation; assert `get()` and `save()` each called exactly once; no retry, no second `save()`.

**G. Arbitrary repository failures** — separate fake-repository scenarios for `get()` failure and `save()` failure; exact exception-instance propagation in each; no wrapper.

**H. `CommandEntryPoint`/Protocol** — mypy-checked structural `CommandHandler[AuthorizeRunCommand, SaveResult]` conformance (typed-assignment precedent, not runtime `isinstance`, mirroring M032/M034); exact command object reaches the handler through the entry point; handler invoked exactly once per call; bound once at construction, reused across multiple invocations; result/exception propagate through the entry point unchanged. Honest mypy-scope statement: canonical `mypy` (`packages = ["empirical_platform"]`) covers `src/` only; contract-test conformance is proven by the same typed-assignment pattern already established and documented as non-canonical-scope in M034's own implementation.

**I. Architecture** — real `python tools/check_architecture.py .` run over the actual new `authorize_run.py` source passes with zero change to `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES`; `usecases` may import `run`/`shared` (already true); no persistence import appears in `authorize_run.py`; no concrete adapter or runtime import; no `EvidencePackage`/`Review` import; `run`/`campaign` still cannot import `usecases` (unaffected); no checker permission widened.

**J. PostgreSQL** — the items in Sections 33-36: golden-path success, transition-history/actor/correlation/reason verification, invalid-transition (no persistence), missing-Run, deterministic conflict (Section 36's full eight-step sequence), plus M033/M034 regression (both already-frozen slices exercised as seeding dependencies in every PostgreSQL test here) and existing `Run` repository regression.

No arbitrary coverage-percentage threshold is set, matching every prior milestone's own precedent.

---

## 38. Alternatives Considered

| Decision | Alternatives | Selected | Rejection reason (summary) |
| --- | --- | --- | --- |
| Run transition | `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail` | `authorize` | Each alternative requires additional test-setup depth (1-4 prior transitions) or a mandatory `reason` field, with no additional architectural proof over `authorize`. |
| Identity representation | B (raw strings + reconstruction), C (split RunId + runtime field), D (governance-only) | A (full `DomainIdentity[RunId]`) | B forces an unused identifier-generator-style dependency or an unjustified pass-through string; C adds an unnecessary reconstruction step; D has no repository evidence of a resolution mechanism. |
| Expected-version model | B (handler auto-uses `loaded.persisted_version`), C (second read), D (runtime collaborator) | A (caller-supplied command field) | B eliminates the only path to a genuine stale-write scenario and contradicts `save()`'s own parameter-design intent; C adds an unjustified repository call; D requires unfrozen infrastructure. |
| Result contract | B (`DomainIdentity[RunId]`), C (raw `Run`), D (new type), E (`None`) | A (`SaveResult`) | B loses useful information; C leaks aggregate mutability; D is an unjustified new type when an existing one suffices; E discards useful information. |
| Handler dependency | Add `CampaignRepository` "for future-proofing" | `RunRepository` only | No Campaign data is ever read or needed by this capability; adding an unused dependency would be speculative. |
| Handler dependency | Add a `Clock` collaborator | `occurred_at` caller-supplied | No frozen precedent favors handler-owned time generation over caller-supplied `occurred_at`; `PrepareCampaignForAuthorizationCommand` already established caller-supplied as the pattern. |
| Error handling | Translate any of the four error classes, return a status/nullable result, wrap in an envelope | Transparent propagation, all four classes | The frozen `CommandEntryPoint` contract requires exceptions to propagate unchanged; no alternative is compatible with that already-frozen invariant. |
| Transaction ownership | Introduce `run_composed()` or a new unit-of-work boundary around `get()`+`save()` | No application transaction orchestration | Only two independently-atomic repository operations exist; `save()`'s own optimistic-concurrency guard, not an app-level transaction, is the actual consistency mechanism. |
| Deterministic conflict mechanism | A second `authorize()`-path instance as the interfering write; direct repository/domain test scaffolding without a real mutator; reusing an existing frozen application capability | `append_manifest()` on an independently-loaded instance | A second `authorize()` call would move the persisted state past `CREATED`, causing the command under test to hit the domain `ValueError` instead of `OptimisticConcurrencyConflict` — exactly the failure mode M032's own initial (later-corrected) design mistakenly risked; `append_manifest()` is the only frozen Run mutator that avoids this, independently verified by inspecting every Run method. |
| Module placement | A different package (e.g. a new `commands` package) | `empirical_platform.usecases.authorize_run` | Matches the exact precedent of every other concrete command/query module in this chain (M030-M034); no evidence justifies a new package. |
| Architecture-checker evidence | Add a new positive/negative fixture pair | None added | Existing `usecases` positive/negative fixtures already cover the exact permission this module relies on; the real source file itself is the positive-case proof, mirroring M031/M034. |
| Production composition | Introduce composition-root wiring for `AuthorizeRunHandler` | Deferred (test-only direct construction) | No repeated-handler-need evidence exists after six consecutive milestones of trivial direct construction. |

---

## 39. Rejected Alternatives

Restated for clarity from Section 38 with full reasoning: every non-`authorize` transition (Section 6); split-field/raw-string/governance-only query identity (Section 10); handler-internal `persisted_version` reuse, a second read, or a runtime collaborator for expected-version (Section 12); `DomainIdentity[RunId]`, raw `Run`, a new result type, or `None` as the result (Section 14); an added `CampaignRepository` or `Clock` dependency (Section 18); any error-translation, nullable-result, or envelope not-found/error behavior (Sections 24-27); any application-level transaction orchestration (Section 29); any composition-root, registry, dispatcher, mediator, or service-locator binding (Section 30); any new architecture-checker permission (Section 32); a second `authorize()`-path instance or non-real-mutator scaffolding as the deterministic-conflict interfering write (Section 36).

---

## 40. In Scope

- Exactly one `AuthorizeRunCommand` and one `AuthorizeRunHandler`, in `empirical_platform.usecases.authorize_run`.
- Exactly one `RunRepository.get()` and exactly one `RunRepository.save()` call per `handle()` invocation.
- The selected `SaveResult` result contract (Section 15).
- Transparent `AggregateNotFound`/domain-`ValueError`/`OptimisticConcurrencyConflict`/arbitrary-error propagation (Sections 24-27).
- `CommandEntryPoint` compatibility, test-only direct construction (Section 30).
- Focused unit, contract, and PostgreSQL integration evidence (Sections 33-37).
- Zero architecture-checker change (Section 32).

---

## 41. Out of Scope

A second Run transition; a generic Run lifecycle framework; Run creation changes; Run retrieval changes; Run listing/filtering/pagination; retry/backoff; automatic conflict recovery; runtime-ID regeneration; any Campaign command/query change, lookup, or mutation; `EvidencePackage`/`Review` command or query; any generic save/concurrency framework; composition root/registry/command bus/dispatcher/mediator/service locator/DI framework; transport/API layer; caching; worker/queue/scheduler; audit integration; schema/migration changes; market-data/vendor/trading/execution behavior; MILESTONE-036 work of any kind. `append_manifest()`'s use in the conflict test's interfering write (Section 36) is test scaffolding only and does not authorize it as a second production use case.

---

## 42. Deferred Work

- A second Run lifecycle-transition command (e.g. `start_acquisition`), a future milestone once genuinely evidenced.
- `EvidencePackage`/`Review` creation and retrieval — unchanged from the frozen scope's own deferral.
- Retry-on-`OptimisticConcurrencyConflict` policy — now genuinely closer to justifiable (two independently-proven save()-based commands exist after this milestone), but still not authorized here.
- Read-to-update `expected_persisted_version` acquisition for a real caller workflow (Section 13's known limitation) — unchanged from M034's own deferral.
- Any composition-root abstraction beyond direct binding.
- MILESTONE-036 and beyond.

---

## 43. Risks

- **Selecting a transition with a hidden prerequisite:** mitigated — `authorize()` is directly reachable from the state M033's frozen `CreateRunHandler` already produces, independently verified (Section 5/7), zero extra setup.
- **`Run.version`/`persisted_version` confusion:** mitigated by precisely naming and using each throughout (Sections 21-22), applying the same discipline the M034 design correction established.
- **Using `loaded.persisted_version` and accidentally eliminating conflicts:** explicitly rejected (Section 12-13); the handler contract (Section 18) uses `command.expected_persisted_version` only.
- **Domain failure occurring before the repository conflict can be reached:** addressed directly by selecting `append_manifest()` (state-preserving) over any transition-based interfering write (Section 36) — the exact failure mode this risk describes is what M032's own initial design mistakenly risked and later corrected; this design avoids it from the outset by independent analysis of Run's own mutator set.
- **Manifest-based conflict setup mutating unintended state:** the interfering write only appends one manifest and advances version; it does not alter `campaign_id` or `state`, verified directly against `append_manifest()`'s implementation (Section 5).
- **Duplicate mutation or `save()`:** the sequence (Section 19) performs exactly one of each; tests assert call counts directly (Section 37.B).
- **Retry-policy or transaction-framework creep:** explicitly excluded (Sections 29, 41); the existence of a second save()-based command after this milestone must not be read as authorizing either within this milestone.
- **Test-only setup leaking into production:** `append_manifest()`'s conflict-test role is explicitly labeled test scaffolding only, never invoked by `AuthorizeRunHandler` or any other production code (Section 41).
- **Result metadata leakage:** none — `SaveResult` carries only `operation`/`persisted_version`, both already-frozen, already-justified fields (Section 15); no aggregate or mutability leakage (Section 14).
- **Architecture-test duplication:** avoided — no new fixture added (Section 32).
- **M036 leakage:** none — no M036 capability, terminology, or forward reference appears anywhere in this document.

---

## 44. Cross-Milestone Compatibility

- Fully compatible with frozen `RunRepository`/`PostgresRunRepository`/`Run`/`CommandHandler`/`CommandEntryPoint` (M020, M023, M027, M029) — no signature or behavior of any of these is touched.
- Fully compatible with M033's `CreateRunCommand`/`CreateRunHandler` — used unmodified as PostgreSQL-evidence seeding, proving no regression.
- Fully compatible with M034's `GetRunQuery`/`GetRunHandler`/`RunSnapshot` — no shared base, import, or coupling introduced; usable (not required) for independent post-transition verification in tests.
- Fully compatible with M032's `PrepareCampaignForAuthorizationCommand`/`PrepareCampaignForAuthorizationHandler` — structural pattern reference only, no code dependency; the deterministic-conflict mechanism is independently re-derived for Run's own mutator set (Section 36), not copied.
- No change to `ALLOWED`/`ALLOWED_EXACT_IMPORTS`/`FORBIDDEN_IMPORT_PREFIXES` in `tools/check_architecture.py`.

---

## 45. Acceptance Gate

This design is ready for independent review when: every open question the scope-freeze document (Section 24) enumerated has an explicit, justified answer above; no decision expands the frozen scope's In-Scope Capability (a second transition, retry, composition root, transport, `EvidencePackage`/`Review` work all remain absent); every alternative considered has a specific, evidence-based rejection reason (Sections 38-39), not a generic dismissal; the design is implementable without requiring the implementer to make any further load-bearing architectural decision.

---

## 46. Hostile Self-Review

Attacked directly against the Phase 25 attack list:

- **Unreachable transition:** absent — `authorize()` is directly reachable from `CREATED`, the state M033's frozen creation slice already produces (Sections 5/7).
- **Hidden predecessor transition:** absent — no prior M035 command or transition is required; the invalid-transition and conflict test scenarios (Sections 34/36) each independently pre-advance the *persisted* row via direct repository/domain test scaffolding, not via any production command.
- **More than one mutation:** absent — exactly one `run.authorize()` call per `handle()` invocation (Section 19, step 4).
- **More than one `get()` or `save()`:** absent — exactly one of each (Section 19, steps 2 and 5).
- **Expected-version ambiguity:** resolved explicitly — Candidate A selected with full Run-specific reasoning (Sections 12-13), not left implicit.
- **Loaded-version substitution:** absent — the handler contract (Section 18) uses `command.expected_persisted_version`, never `loaded.persisted_version`, verified directly in the frozen code block.
- **Aggregate/persisted version conflation:** absent — Sections 21-22 name and use each precisely, applying the M034-established discipline.
- **Domain failure before conflict:** actively avoided by design — `append_manifest()` selected specifically because it does not disturb `RunLifecycleState`, independently verified (Section 5), not merely asserted.
- **Invalid conflict setup:** the eight-step sequence (Section 36) is fully specified, numbered, and independently verified against `append_manifest()`'s and `PostgresRunRepository.save()`'s actual frozen behavior.
- **Hidden retry:** absent — explicitly excluded (Sections 26, 41) and verified absent from the handler contract (Section 18).
- **Transaction orchestration:** absent — explicitly justified as unneeded (Section 29).
- **Second Run capability:** absent — exactly one command, one handler, one transition (Section 40).
- **`EvidencePackage`/`Review` leakage:** absent — no reference anywhere in this document's frozen decisions.
- **Architecture mismatch:** verified directly against live `tools/check_architecture.py` source (Sections 31-32), not asserted from memory.
- **Production composition leakage:** absent — test-only direct construction only (Section 30).
- **M036 leakage:** absent — no M036 capability, terminology, or forward reference appears anywhere in this document.

No load-bearing ambiguity remains open.

---

## 47. Final Status

**CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW.** Not approved. Not frozen. Does not authorize implementation.

**Next permitted action:** MILESTONE-035 INDEPENDENT DESIGN REVIEW.
