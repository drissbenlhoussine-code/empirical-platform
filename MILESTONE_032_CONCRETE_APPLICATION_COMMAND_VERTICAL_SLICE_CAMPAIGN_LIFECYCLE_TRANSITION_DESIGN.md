# MILESTONE-032 - Concrete Application Command Vertical Slice (Campaign Lifecycle Transition) Design

## 1. Document Status

**Status: CANDIDATE_FOR_FINAL_INDEPENDENT_DESIGN_RE_REVIEW**

This document is a design candidate. An independent hostile design review evaluated the prior version and returned **M032 DESIGN REQUIRES CORRECTION**, citing one MAJOR finding (M032-DESIGN-REVIEW-0001: the PostgreSQL conflict-test strategy's interfering-write mechanism was under-specified and, if implemented as originally described, would not reach `OptimisticConcurrencyConflict`). Section 21's conflict scenario and Section 31's corresponding self-review row have been corrected to resolve that finding; no other decision in this document was reopened. It has not been re-reviewed, approved, or frozen. No implementation of MILESTONE-032 is authorized by this document.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at design | `c1c888e306981346025ce3e5ac9d5b07c07fc1e9` |
| Frozen scope commit | `5ea62d02d65945f0976e42b8c011217d895723e4` |
| Scope freeze commit | `b18878a514694d6663026e11d98859023c04a136` |

---

## 3. Frozen Authority Chain

| Milestone | Status | Delivered |
| --- | --- | --- |
| M020 | APPROVED_AND_FROZEN | `Campaign` aggregate (8 mutation methods), `CampaignRepository` Protocol (`get`/`add`/`save`), `LoadedAggregate[AggregateT]`, `SaveResult`, `AggregateVersion`, `OptimisticConcurrencyConflict` and sibling exceptions |
| M023 | APPROVED_AND_FROZEN | Concrete PostgreSQL `Campaign` repository adapter, including `save()`'s atomic version-guarded `UPDATE` |
| M027 | APPROVED_AND_FROZEN | `CommandHandler[_CommandT_contra, _ResultT_co]` Protocol |
| M029 | APPROVED_AND_FROZEN | `CommandEntryPoint[CommandT, ResultT]` |
| M030 | APPROVED_AND_FROZEN | `CreateCampaignCommand`/`CreateCampaignHandler` in `empirical_platform.usecases`; the `usecases` package's architecture-checker rules |
| M031 | APPROVED_AND_FROZEN | `GetCampaignQuery`/`GetCampaignHandler`/`CampaignSnapshot` in `empirical_platform.usecases` |
| M032 scope | APPROVED_AND_FROZEN | Concrete Application Command Vertical Slice — Campaign lifecycle mutation via `save()` (this design's authority) |

**Exact frozen contracts verified by direct source inspection:**

```python
# empirical_platform.campaign.aggregate — Campaign, verified in full
class Campaign:
    def revise_scope_statement(self, scope_statement: CampaignScopeStatement) -> None: ...  # DRAFT only, no state change
    def prepare_for_authorization(self, *, actor: str, occurred_at: datetime,
                                   correlation_id: str | None = None, reason: str | None = None) -> None: ...  # DRAFT -> READY_FOR_AUTHORIZATION
    def record_authorization(self, *, reason: str, actor: str, occurred_at: datetime,
                              correlation_id: str | None = None) -> None: ...  # READY_FOR_AUTHORIZATION -> AUTHORIZED
    def activate(self, *, reason: str, actor: str, occurred_at: datetime,
                 correlation_id: str | None = None) -> None: ...  # AUTHORIZED -> ACTIVE
    def suspend(self, *, reason: str, actor: str, occurred_at: datetime,
                correlation_id: str | None = None) -> None: ...  # ACTIVE -> SUSPENDED
    def resume(self, *, reason: str, actor: str, occurred_at: datetime,
               correlation_id: str | None = None) -> None: ...  # SUSPENDED -> ACTIVE
    def complete(self, *, reason: str, actor: str, occurred_at: datetime,
                 correlation_id: str | None = None) -> None: ...  # ACTIVE -> COMPLETED
    def cancel(self, *, actor: str, occurred_at: datetime, reason: str | None = None,
               correlation_id: str | None = None) -> None: ...  # {DRAFT,READY_FOR_AUTHORIZATION,AUTHORIZED,ACTIVE,SUSPENDED} -> CANCELLED

# empirical_platform.campaign.repository
class CampaignRepository(Protocol):
    def get(self, identity: DomainIdentity[CampaignId]) -> LoadedAggregate[Campaign]: ...
    def add(self, aggregate: Campaign) -> SaveResult: ...
    def save(self, aggregate: Campaign, *, expected_persisted_version: AggregateVersion) -> SaveResult: ...

# empirical_platform.shared.contracts.repository
@dataclass(frozen=True, slots=True)
class LoadedAggregate[AggregateT]:
    aggregate: AggregateT
    persisted_version: AggregateVersion

@dataclass(frozen=True, slots=True)
class SaveResult:
    operation: SaveOperation  # CREATED | UPDATED | UNCHANGED
    persisted_version: AggregateVersion

class OptimisticConcurrencyConflict(RepositoryContractError):
    def __init__(self, *, aggregate_kind: str, identity: object,
                 expected_persisted_version: AggregateVersion,
                 aggregate_current_version: AggregateVersion,
                 actual_persisted_version: AggregateVersion | None = None) -> None: ...

# empirical_platform.shared.domain.versioning
@dataclass(frozen=True, slots=True, order=True)
class AggregateVersion:
    value: int
    @classmethod
    def initial(cls) -> AggregateVersion: ...  # value=0
    def next(self) -> AggregateVersion: ...

# empirical_platform.shared.contracts.command
class CommandHandler(Protocol[_CommandT_contra, _ResultT_co]):
    def handle(self, command: _CommandT_contra) -> _ResultT_co: ...

# empirical_platform.application.command
class CommandEntryPoint[CommandT, ResultT]:
    def __init__(self, handler: CommandHandler[CommandT, ResultT]) -> None: ...
    def __call__(self, command: CommandT) -> ResultT: ...

# empirical_platform.usecases.create_campaign (M030, frozen)
class CreateCampaignHandler:
    def handle(self, command: CreateCampaignCommand) -> DomainIdentity[CampaignId]: ...
```

**Concrete `save()` verified behavior** (`shared/persistence/postgres_repositories/campaign_repository.py`): the `UPDATE ... WHERE runtime_id = :runtime_id AND governance_id = :governance_id AND version = :expected_persisted_version` statement is the sole authoritative concurrency gate — a mismatch between the caller-supplied `expected_persisted_version` and the database's actual current row version causes zero rows to update, which the adapter distinguishes from "not found" and raises as `OptimisticConcurrencyConflict(expected_persisted_version=..., aggregate_current_version=record.version, actual_persisted_version=<diagnostic re-read>)`.

**`tools/check_architecture.py`'s current, verified `usecases` rules (unchanged since M030):**

```python
ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}
FORBIDDEN_IMPORT_PREFIXES["usecases"] = (
    "empirical_platform.shared.persistence", "sqlalchemy", "psycopg", "boto3",
)
```

---

## 4. Architectural Context

M030 proved the create/`add()` path. M031 proved the read/`get()` path. Neither has ever exercised `save()` or `OptimisticConcurrencyConflict` at the application layer — independently verified via `grep` during scope review (zero `.save(` call sites and zero `OptimisticConcurrencyConflict` references anywhere in `usecases/`, `application/`, or `entrypoints/`). This design closes that gap with the smallest coherent write-side capability that genuinely exercises `save()`'s optimistic-concurrency guard.

---

## 5. Mutation Candidate Analysis

All 8 `Campaign` mutation methods evaluated against: required current state, required input, domain preconditions, whether it changes lifecycle state, additional business context required, unrelated authorization/audit concerns, provability with one load→mutate→save path, PostgreSQL setup complexity, negative-path testability, and scope risk.

| Candidate | Required state | Extra fields beyond identity/version | Changes state? | Reachable from a freshly-created (DRAFT) Campaign? | Verdict |
| --- | --- | --- | --- | --- | --- |
| `record_authorization` | READY_FOR_AUTHORIZATION | `reason` (mandatory), `actor`, `occurred_at`, `correlation_id` | Yes | **No** — requires `prepare_for_authorization` first | **Disqualified** — needs a second, prior `save()` to reach its precondition state, violating "one load→mutate→save path" |
| `activate` | AUTHORIZED | `reason` (mandatory), `actor`, `occurred_at`, `correlation_id` | Yes | **No** — requires two prior transitions | **Disqualified** — same reason, deeper chain |
| `suspend` | ACTIVE | `reason` (mandatory), `actor`, `occurred_at`, `correlation_id` | Yes | **No** — requires three prior transitions | **Disqualified** |
| `resume` | SUSPENDED | `reason` (mandatory), `actor`, `occurred_at`, `correlation_id` | Yes | **No** — requires four prior transitions | **Disqualified** |
| `complete` | ACTIVE | `reason` (mandatory), `actor`, `occurred_at`, `correlation_id` | Yes | **No** — requires two prior transitions | **Disqualified** |
| `revise_scope_statement` | DRAFT | `scope_statement` only | **No** (stays DRAFT) | Yes | Viable but does not literally transition lifecycle state |
| `cancel` | DRAFT (or 4 other states) | `actor`, `occurred_at` (mandatory); `reason` optional from DRAFT | Yes (→ CANCELLED, terminal) | Yes | Viable |
| `prepare_for_authorization` | DRAFT | `actor`, `occurred_at` (mandatory); `reason` optional | Yes (→ READY_FOR_AUTHORIZATION) | Yes | **Selected** |

Five of the eight candidates (`record_authorization`, `activate`, `suspend`, `resume`, `complete`) require a lifecycle state unreachable from a freshly-created `Campaign` without one or more prior `save()` calls — disqualified outright, since satisfying their precondition would require multiple round trips, violating the frozen scope's "one load→mutate→save path" and inflating this milestone into a multi-command slice.

The three remaining candidates — `revise_scope_statement`, `cancel`, `prepare_for_authorization` — are all reachable directly from the `DRAFT` state M030's `CreateCampaignHandler` already produces, and all three are compared in detail in Section 6.

---

## 6. Selected Mutation

**`Campaign.prepare_for_authorization()`.**

### Why not `revise_scope_statement`

`revise_scope_statement` requires the fewest fields (only the new scope statement) and no actor/timestamp context, and it does still bump `AggregateVersion` (proving the concurrency-relevant version mechanics work even without a state change). However, it never changes `_state` — it is a domain mutation, not a lifecycle *transition*. The frozen scope's own official milestone name is "Campaign Lifecycle Transition," and its Open Design Questions explicitly kept `revise_scope_statement` in play as "the non-state-transition" alternative, not as the presumed default. Given a genuine state-transition candidate is available with no disqualifying cost (see below), this design selects the literal state-transition to fully honor the frozen milestone name rather than the narrower-but-non-transitioning alternative.

### Why not `cancel`

`cancel` is reachable from `DRAFT` and does transition state (→ `CANCELLED`), with an identical field cost to `prepare_for_authorization` (`actor`, `occurred_at` mandatory; `reason` optional from `DRAFT`). It was seriously considered. It was not selected because `CANCELLED` is a terminal state reachable from five different source states — an "exit" transition that is architecturally peripheral to the Campaign lifecycle's forward progression, whereas `prepare_for_authorization` is the literal first transition in the lifecycle graph (`DRAFT → READY_FOR_AUTHORIZATION`), giving this milestone's proof genuine narrative and architectural centrality: it demonstrates the platform can advance a Campaign forward through its intended lifecycle, not merely terminate one.

### Why `prepare_for_authorization`

- Reachable directly from `DRAFT`, the exact state M030's frozen `CreateCampaignHandler` already produces — no chained transitions, satisfying "one load→mutate→save path" cleanly.
- Its extra fields (`actor: str`, `occurred_at: datetime`, `correlation_id: str | None`, `reason: str | None`) are plain, already-validated-by-the-aggregate primitive types — no new value-object wrapper, no new collaborator (no `Clock` dependency; `occurred_at` is caller-supplied data, directly analogous to M030's own raw-field command style).
- Represents the literal first lifecycle transition, giving the milestone's proof genuine architectural centrality rather than testing a peripheral "exit" path.
- Its negative domain-precondition path is honestly and simply testable: invoke the command twice against the same identity — the first succeeds (`DRAFT → READY_FOR_AUTHORIZATION`), the second fails with the aggregate's own `ValueError` (state is no longer `DRAFT`) — no test-only aggregate manipulation required.

---

## 7. Selected Architecture

One concrete command and one concrete handler, in the existing `empirical_platform.usecases` package, in a new module dedicated to this one use case — mirroring M030's/M031's file-per-use-case precedent exactly. The handler depends on `CampaignRepository` only (no `Clock`, no `RuntimeIdentifierGenerator` — nothing is generated). No architecture-checker change is required.

---

## 8. Exact Command Contract

**Type name:** `PrepareCampaignForAuthorizationCommand`

**Module:** `src/empirical_platform/usecases/prepare_campaign_for_authorization.py`

**Shape:**

```python
@dataclass(frozen=True, slots=True)
class PrepareCampaignForAuthorizationCommand:
    identity: DomainIdentity[CampaignId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

**Fields, exact and exhaustive:**

- `identity: DomainIdentity[CampaignId]` — the full frozen identity object, carried unchanged, exactly mirroring `GetCampaignQuery`'s precedent (Design Question 1). Required because `CampaignRepository.get()` requires it verbatim; no decomposition, no reconstruction.
- `expected_persisted_version: AggregateVersion` — the caller's belief about the currently-persisted version, passed unchanged to `save()`. See Section 11 for the full justification of caller-supplied (not handler-derived) version ownership.
- `actor: str`, `occurred_at: datetime`, `correlation_id: str | None = None`, `reason: str | None = None` — raw, unvalidated data carried verbatim into `Campaign.prepare_for_authorization()`'s existing parameters; all validation (`isinstance` checks, non-empty checks) is owned entirely by the aggregate method itself (Section 16).

No pagination, filter, sort, projection, authorization-framework, transport, serialization, tracing, or metadata field is present.

---

## 9. Exact Handler Contract

**Type name:** `PrepareCampaignForAuthorizationHandler`

**Module:** same file as the command, `src/empirical_platform/usecases/prepare_campaign_for_authorization.py`.

**Shape:**

```python
class PrepareCampaignForAuthorizationHandler:
    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, command: PrepareCampaignForAuthorizationCommand) -> SaveResult:
        loaded = self._campaign_repository.get(command.identity)
        campaign = loaded.aggregate
        campaign.prepare_for_authorization(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._campaign_repository.save(
            campaign, expected_persisted_version=command.expected_persisted_version
        )
```

**Constructor dependency:** `campaign_repository: CampaignRepository` only — no second collaborator. No `Clock` is injected; `occurred_at` is caller-supplied command data (Section 6).

**`CommandHandler` generic relationship:** structurally satisfies `CommandHandler[PrepareCampaignForAuthorizationCommand, SaveResult]` — no inheritance, matching M030's/M031's precedent exactly.

**Exact call counts:** exactly one `get()`, exactly one call to `prepare_for_authorization()`, exactly one `save()`. No `add()`, no `delete()`, no second `get()`.

---

## 10. Identity Semantics

Identical to M031's frozen precedent: `command.identity` is passed to `CampaignRepository.get()` unchanged — no reconstruction, no splitting/rejoining, no runtime-ID generation, no governance-ID-only fallback. Tests must prove `repository_received_identity is command.identity` (object identity, not equality).

---

## 11. Expected-Version Semantics

**This is the design's most load-bearing decision.**

### Options evaluated

**A. Caller supplies `expected_persisted_version` in the command** — the value is set once, independently of whatever `get()` happens to return when the handler eventually runs, and passed straight through to `save()`.

**B. Handler loads the Campaign and uses `loaded.persisted_version`** (the value the same `get()` call just returned) as the `expected_persisted_version` passed to `save()`.

**C. Handler receives version through another collaborator** — e.g., a version-tracking service. No such collaborator exists anywhere in this codebase; rejected immediately as inventing new infrastructure with zero repository evidence.

**D. Another existing frozen mechanism** — none exists; `AggregateVersion` and `LoadedAggregate.persisted_version` are the only frozen version-carrying types, already covered by A/B.

### Why B fails the concurrency-proof requirement

Under Option B, `get()` and `save()` happen in immediate sequence inside one handler invocation, with nothing able to intervene between them in a single-threaded, sequential test. The `expected_persisted_version` passed to `save()` would always equal the database's *actual current* version at that instant, because it was read a few lines earlier in the same call. **A real `OptimisticConcurrencyConflict` becomes structurally unreachable** without introducing a deterministic interleaving hook (e.g., pausing the handler mid-execution to let a second write occur) — exactly the kind of test-only mechanism Phase 4 of the design mission explicitly warns risks introducing unauthorized abstraction. Option B is correct textbook "read-modify-write within one call" but makes the milestone's own stated purpose (proving the conflict path) untestable by ordinary means.

### Why A succeeds, with direct repository precedent

Under Option A, the command's `expected_persisted_version` is set once — independently of the handler's own internal `get()` — so a test can deliberately make it stale:

1. Persist a Campaign via M030's frozen `CreateCampaignHandler` (persisted version 0).
2. Advance the persisted version to 1 by independently loading the same identity and calling `Campaign.revise_scope_statement(...)` on that separately-loaded aggregate, then `campaign_repository.save()` **directly** (bypassing the M032 command entirely) — using the same frozen repository optimistic-concurrency semantics M023's own `test_campaign_save_stale_version_raises_optimistic_concurrency_conflict` (`tests/integration/test_m023_postgres_repositories.py`) already proves at the repository layer, with an M032-specific interfering write (`revise_scope_statement()`) that preserves `DRAFT` so the command under test can still execute `prepare_for_authorization()` afterward. See Section 21 for the exact scenario.
3. Construct `PrepareCampaignForAuthorizationCommand` with `expected_persisted_version=AggregateVersion(0)` (now stale).
4. Invoke it: the handler's `get()` still returns the current (version-1) aggregate to mutate correctly in memory, but `save(campaign, expected_persisted_version=AggregateVersion(0))` is rejected by the database's atomic `UPDATE ... WHERE version = 0` (zero rows match, since the true row is at version 1) — `OptimisticConcurrencyConflict` is raised, deterministically, with zero threading, mocking, or interleaving machinery.

This is not merely theoretically sound — it builds on the same frozen repository-layer conflict semantics this repository's own M023 test suite already established, adapted with an M032-specific state-preserving interfering write (Section 21).

### Selected: Option A

The handler never derives `expected_persisted_version` from its own `get()` call. `loaded.persisted_version` is read (implicitly, as part of `LoadedAggregate`) but never consulted for the `save()` call — it exists only so the handler can access `loaded.aggregate` to mutate. This intentional non-use exactly mirrors M031's own precedent of reading but never exposing `LoadedAggregate.persisted_version`.

**No pre-flight concurrency check is added in the handler.** The handler does not compare `command.expected_persisted_version` against `loaded.persisted_version` before mutating or saving — doing so would duplicate the repository's own atomic check non-atomically (a genuine TOCTOU risk: the database could change again between such a pre-check and the actual `save()` call) and would violate the transparent-propagation precedent M030/M031 both established. The single source of truth for the concurrency decision is the repository's own atomic `save()` call.

---

## 12. Load-Mutate-Save Sequence

**Exact sequence, frozen:**

```
1. handler.handle(command) receives PrepareCampaignForAuthorizationCommand
2. loaded = self._campaign_repository.get(command.identity)      # exactly one get() call
3. campaign = loaded.aggregate                                    # in-memory mutable reference
4. campaign.prepare_for_authorization(                            # exactly one mutation call
       actor=command.actor, occurred_at=command.occurred_at,
       correlation_id=command.correlation_id, reason=command.reason,
   )
5. result = self._campaign_repository.save(                       # exactly one save() call
       campaign, expected_persisted_version=command.expected_persisted_version,
   )
6. return result
```

- **No pre-read beyond the single `get()`.** No second `get()`. No `add()`. No `delete()`.
- **`loaded.persisted_version` is read as part of `LoadedAggregate` but never passed to `save()`** — see Section 11.
- If `campaign.prepare_for_authorization()` raises (domain precondition violated — state is not `DRAFT`), **`save()` is never called**; no write of any kind reaches the database.
- If `save()` raises (`OptimisticConcurrencyConflict`, `AggregateNotFound`, `InvalidPersistedAggregateState`, or `InvalidAggregateForPersistence`), it propagates unchanged (Section 15).

---

## 13. Return Contract

**Selected: the frozen `SaveResult` type, returned exactly as received from `campaign_repository.save()`, unchanged.**

### Alternatives considered

| Option | Advantages | Disadvantages | Selected/Rejected |
| --- | --- | --- | --- |
| **`DomainIdentity` (M030's own return shape)** | Precedent from M030 | For an *update*, the identity never changes — returning it conveys zero new information; the caller already supplied it | **Rejected** — no information value |
| **`Campaign` aggregate directly** | Full state visible | Mutable aggregate leakage through a write boundary — the same leakage risk M031 rejected for the read side, equally applicable here | **Rejected** — aggregate leakage |
| **`LoadedAggregate[Campaign]`** | Zero new code | Still wraps the mutable `Campaign`; `persisted_version` on it is the *pre-mutation* value, not the new one — actively misleading for a caller who wants the post-mutation version | **Rejected** — aggregate leakage plus stale version metadata |
| **New narrow milestone-local value (`CampaignSnapshot`-style)** | Consistent with M031's read-side style | M031's read-side reasoning does not transfer: a write-side caller's genuine need (the *new* persisted version, for chaining a subsequent write) is exactly what `SaveResult` already provides; inventing a parallel type would duplicate it for no benefit | **Rejected** — no value over the existing frozen type |
| **`SaveResult` (frozen M020 type)** | Already exists; already returned by `save()` itself; carries exactly `operation: SaveOperation` (`UPDATED`/`UNCHANGED` — genuinely variable for a save, unlike M030's always-`CREATED` case) and `persisted_version: AggregateVersion` (the *new* version, essential for any caller performing a follow-up write); persistence-neutral (lives in `shared.contracts.repository`, not `shared.persistence`) — no boundary risk | Introduces a "raw pass-through" of a repository-defined type into the return contract | **Selected** |
| **No return value** | Simplest possible | Discards the new persisted version, which a write-side caller genuinely needs for correct follow-up optimistic-concurrency writes (unlike M031's pure-read case, which had no such need) | **Rejected** — loses load-bearing information a real write caller needs |

### Why the write side differs from M031's read-side reasoning

M031 deliberately avoided returning `LoadedAggregate`/raw repository types because a *reader* has no legitimate use for write-side metadata (`persisted_version` from a read has no consumer). A *writer*, by contrast, has an immediate, legitimate use for the version its own write just produced: to perform a correct, non-stale follow-up `save()` later. `SaveResult` is precisely and only that — it introduces no aggregate-mutability leakage (both its fields are already-frozen, immutable value types) and no persistence-infrastructure leakage (it is a `shared.contracts` type, not a `shared.persistence` type).

---

## 14. Optimistic-Concurrency Behavior

**Selected: fully transparent propagation — no translation, no wrapping, no retry.**

`OptimisticConcurrencyConflict` raised by `CampaignRepository.save()` propagates through `PrepareCampaignForAuthorizationHandler` and the frozen, unmodified `CommandEntryPoint` completely unchanged — the handler contains zero `try`/`except` blocks, exactly matching M030's/M031's transparent-propagation precedent and M029's frozen invariant.

### Alternatives considered

| Option | Selected/Rejected |
| --- | --- |
| Transparent propagation | **Selected** — matches M029's frozen invariant; zero new code; exact conflict metadata (`expected_persisted_version`, `aggregate_current_version`, `actual_persisted_version`) already reaches the caller unchanged |
| Translation to a command-specific conflict type | **Rejected** — introduces a new exception type this scope does not authorize; duplicates information `OptimisticConcurrencyConflict` already carries |
| Retry / automatic recovery | **Rejected** — explicitly out of scope (frozen scope Sections 13/17); retry policy is the *next* milestone this one unblocks, not this one |
| Result/outcome wrapper | **Rejected** — introduces a generic result-wrapper framework the frozen scope explicitly excludes |

There is exactly one `save()` attempt. Retry is explicitly and permanently absent from this design.

---

## 15. Domain and Repository Error Semantics

**Domain-precondition failure** (`campaign.prepare_for_authorization()` raises `ValueError` because the current state is not `DRAFT`, or `TypeError` for a malformed `occurred_at`/empty `actor`): propagates unchanged; `save()` is never reached; no database write of any kind occurs.

**Repository failures** (`get()` may raise `AggregateNotFound` or `InvalidPersistedAggregateState`; `save()` may raise `AggregateNotFound`, `OptimisticConcurrencyConflict`, or `InvalidAggregateForPersistence`): all propagate unchanged, with exact exception-instance identity preserved. No handler-level `try`/`except` exists anywhere. No generic application-level error hierarchy is introduced — every exception surfaced is one already frozen by M020.

---

## 16. Validation Ownership

- **Command construction:** no validation of its own — a plain carrier for already-typed (`DomainIdentity`, `AggregateVersion`) and raw (`str`, `datetime`) data.
- **Handler:** no validation of its own — orchestration only (load, mutate, save, return).
- **`Campaign.prepare_for_authorization()`:** owns all domain-precondition validation (current-state check, `actor`/`reason`/`correlation_id` non-empty checks, `occurred_at` type check) — entirely unmodified, exactly as already frozen (M020).
- **`DomainIdentity`/`Identifier`:** own identity format validation, unmodified.
- **`AggregateVersion`:** owns its own non-negative-integer validation, unmodified.
- **Repository:** owns existence and concurrency validation (`AggregateNotFound`, `OptimisticConcurrencyConflict`, `InvalidPersistedAggregateState`, `InvalidAggregateForPersistence`), unmodified.

No validation is duplicated anywhere in this design.

---

## 17. Transaction Ownership

**No new transaction orchestration.** `get()` and `save()` each already own their own `unit_of_work()` internally (verified directly in `PostgresCampaignRepository`'s source) — exactly the same pattern M030's single `add()` call and M031's single `get()` call already rely on. The two calls are **not** wrapped in one shared, larger transaction: there is no atomicity requirement spanning them, since optimistic concurrency's entire purpose is to tolerate this non-atomic read-then-write gap and *detect* conflicts at `save()`-time rather than *prevent* them via locking. `run_composed()` (M024, for multi-repository atomic coordination) is not used and not needed — this design touches exactly one repository.

---

## 18. CommandEntryPoint Binding

- Structural `CommandHandler[PrepareCampaignForAuthorizationCommand, SaveResult]` conformance proven by a mypy-checked typed assignment and a runtime structural-shape check, mirroring M030's/M031's exact contract-test pattern.
- `CommandEntryPoint(PrepareCampaignForAuthorizationHandler(...))` constructed directly, in tests only — exactly matching M030's/M031's precedent. No production composition code.
- No registry, command bus, dispatcher, mediator, service locator, or dependency-injection framework of any kind.

---

## 19. Package and Dependency Boundaries

**New module:** `src/empirical_platform/usecases/prepare_campaign_for_authorization.py` — within the already-authorized `empirical_platform.usecases` package.

**Imports required, verified against frozen source, all under packages already in `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}`:**

- `empirical_platform.campaign.repository` (`CampaignRepository`) — top-level `campaign`.
- `empirical_platform.identifiers.pairs` (`DomainIdentity`) — top-level `identifiers`.
- `empirical_platform.identifiers.types` (`CampaignId`) — top-level `identifiers`.
- `empirical_platform.shared.domain.versioning` (`AggregateVersion`) — top-level `shared`.
- `empirical_platform.shared.contracts.repository` (`SaveResult`) — top-level `shared`.
- `datetime` (stdlib) for the `occurred_at` field's type annotation.

No import of `shared.persistence`, no concrete Postgres adapter, no `sqlalchemy`/`psycopg`/`boto3`, no `Clock` interface — matching `FORBIDDEN_IMPORT_PREFIXES["usecases"]` exactly, with zero new risk beyond what M030 already closed.

---

## 20. Architecture-Checker Impact

**Selected: no checker change of any kind.**

Verified directly: every import this command/handler needs already resolves under the existing `ALLOWED["usecases"]`/`FORBIDDEN_IMPORT_PREFIXES["usecases"]` pair M030 established. The existing `test_current_source_tree_respects_boundaries` check alone proves the real implementation stays within the already-frozen boundary once implemented. No new architecture fixture is warranted — the existing 7 `usecases`-scoped illegal-import fixtures already prove the boundary generically, not tied to any specific file.

---

## 21. PostgreSQL Evidence Strategy

Reuses the exact opt-in fixture pattern `tests/integration/test_m030_create_campaign_usecase.py` and `tests/integration/test_m031_get_campaign_usecase.py` already established (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, the same `engine`/`upgraded_schema`/`clean_tables`/`service`/`campaign_repo` fixture chain). No new schema, container, or composition wiring.

**Exact scenarios:**

1. **Golden path:** persist a `Campaign` via M030's `CreateCampaignHandler` (`DRAFT`, version 0); invoke `PrepareCampaignForAuthorizationCommand` through `CommandEntryPoint` with `expected_persisted_version=AggregateVersion(0)`; verify the returned `SaveResult.operation == SaveOperation.UPDATED` and `SaveResult.persisted_version == AggregateVersion(1)`; independently reload via `campaign_repository.get()` and verify `state == CampaignLifecycleState.READY_FOR_AUTHORIZATION` and `version == AggregateVersion(1)`.
2. **Optimistic-concurrency conflict:** persist a `Campaign` (version 0). Simulate an interfering writer by independently loading the same identity a second time (`campaign_repository.get(identity)`, yielding a second, separate `LoadedAggregate`/`Campaign` in-memory object for the same row), calling `Campaign.revise_scope_statement(...)` on that second object, and persisting it via `campaign_repository.save(interfering_campaign, expected_persisted_version=AggregateVersion(0))` — bypassing the command entirely. This advances the row to version 1 while leaving it in `DRAFT`, because `revise_scope_statement()` is the one existing `Campaign` mutation that bumps `AggregateVersion` without changing lifecycle state. Then invoke `PrepareCampaignForAuthorizationCommand` through `CommandEntryPoint` with the now-stale `expected_persisted_version=AggregateVersion(0)`; verify `OptimisticConcurrencyConflict` is raised with the exact expected/actual version metadata.

   **`revise_scope_statement()` is the required mechanism, not `prepare_for_authorization()` itself.** `Campaign.prepare_for_authorization()` requires the aggregate to be in `DRAFT` (Section 8's frozen contract matrix, verified against `campaign/aggregate.py`); it transitions the aggregate to `READY_FOR_AUTHORIZATION`. If the interfering write instead used `prepare_for_authorization()`, the row would already be `READY_FOR_AUTHORIZATION` by the time the command under test runs its own `campaign.prepare_for_authorization(...)` call in Section 12's load-mutate-save sequence — that call would immediately raise the aggregate's own domain `ValueError` ("cannot transition from READY_FOR_AUTHORIZATION; expected DRAFT"), and execution would never reach `save()` at all. The test would then observe a domain-precondition failure, not `OptimisticConcurrencyConflict`, and the milestone's central proof — that the application boundary correctly surfaces a real, repository-detected version conflict — would go unexercised. `revise_scope_statement()` is the only existing `Campaign` mutation that advances `AggregateVersion` while leaving `_state` at `DRAFT` unchanged, which is exactly what is required to reach the concurrency check inside `save()` rather than the earlier domain-precondition check inside `prepare_for_authorization()` itself. This correction resolves independent design review finding M032-DESIGN-REVIEW-0001; it does not change the selected mutation, command shape, handler, return type, repository interaction, transaction model, expected-version ownership, or any other frozen design decision in this document — it clarifies only the previously under-specified interfering-write mechanism.
3. **Domain-invalid transition:** invoke the command successfully once (`DRAFT → READY_FOR_AUTHORIZATION`); invoke it again against the same identity; verify the aggregate's own `ValueError` propagates unchanged and no further database write occurs.
4. **No migration or schema change** — verified no `migrations/` file is touched.
5. **Full relevant regression** (`tests/integration/`) remains green, run unmodified alongside the new tests.

---

## 22. Test Strategy

**A. Command tests (unit):** exact fields accepted (`identity`, `expected_persisted_version`, `actor`, `occurred_at`, `correlation_id`, `reason`); exact objects/values preserved unchanged; immutability (`AttributeError` on mutation attempt); no unrelated fields; no duplicated business validation at construction.

**B. Handler success (unit, deterministic recording fakes, no mocks):** `get()` called exactly once with the exact `command.identity` object (`is`, not `==`); the chosen mutation (`prepare_for_authorization`) called exactly once with the command's `actor`/`occurred_at`/`correlation_id`/`reason` values; `save()` called exactly once with the exact mutated aggregate and `expected_persisted_version=command.expected_persisted_version` (not `loaded.persisted_version`); no `add()`/`delete()`/second `get()`; the handler's own return value is exactly the `SaveResult` `save()` produced (`is`, not `==`); the aggregate reaches `READY_FOR_AUTHORIZATION`.

**C. Domain failure (unit):** a fake repository whose `get()` returns a `Campaign` already in a non-`DRAFT` state — verify the aggregate's `ValueError` propagates unchanged and the fake's `save()` (configured to raise `AssertionError` if called) is never invoked.

**D. Repository failures (unit, deterministic failing fakes):** `get()` failure (`AggregateNotFound`) propagates with exact instance identity preserved, `save()` never called; `save()` arbitrary failure propagates with exact instance identity preserved; `OptimisticConcurrencyConflict` from `save()` propagates with exact instance identity preserved; no retry, no second `save()` attempt.

**E. `CommandEntryPoint` (unit):** structural `CommandHandler` conformance (mypy-checked typed assignment); exact command object reaches the handler unchanged; exactly-once invocation; exact result/exception propagation unchanged.

**F. Architecture:** real implementation passes the unmodified checker with 0 violations; the 7 pre-existing `usecases`-scoped illegal-import fixtures still trigger unmodified; no new fixture added; `campaign` still cannot import `usecases`.

**G. PostgreSQL integration:** the four scenarios in Section 21.

No arbitrary coverage percentage is introduced; the project's existing repository-wide coverage gate applies unchanged.

---

## 23. Alternatives Considered

| Decision | Alternatives | Selected |
| --- | --- | --- |
| Mutation selection | `revise_scope_statement` / `cancel` / `prepare_for_authorization` / 5 disqualified state-unreachable methods | `prepare_for_authorization` — Section 6 |
| Expected-version ownership | Caller-supplied / handler-derived from own `get()` / new collaborator / no other frozen mechanism | Caller-supplied (Option A) — Section 11 |
| Return contract | `DomainIdentity` / raw `Campaign` / `LoadedAggregate` / new milestone-local snapshot / `SaveResult` / no return | `SaveResult`, unchanged — Section 13 |
| Conflict propagation | Transparent / translated / retried / wrapped | Transparent — Section 14 |
| Handler dependency | `CampaignRepository` only / `+Clock` / `+RuntimeIdentifierGenerator` | `CampaignRepository` only — Section 9 |
| Transaction ownership | No new orchestration / shared transaction across get+save / `run_composed()` | No new orchestration — Section 17 |
| Architecture-checker change | No change / narrow addition / fixture-only | No change — Section 20 |
| Production composition | Build a composition-root helper now / defer entirely | Defer entirely — unchanged from M030/M031 |

---

## 24. Rejected Alternatives (Consolidated Reasons)

- **`record_authorization`/`activate`/`suspend`/`resume`/`complete`** — rejected outright; each requires a lifecycle state unreachable from a freshly-created Campaign without one or more prior `save()` calls, violating the frozen "one load→mutate→save path" scope boundary.
- **`revise_scope_statement`** — rejected as the primary selection (though technically viable) because it never changes lifecycle state, undercutting the frozen milestone's own name and narrative purpose when a genuine, equally low-cost state-transition candidate (`prepare_for_authorization`) exists.
- **`cancel`** — rejected as the primary selection because it is a terminal "exit" transition, architecturally peripheral compared to the lifecycle's literal first forward transition.
- **Handler-derived `expected_persisted_version`** — rejected; makes the frozen conflict path structurally untestable without an unauthorized interleaving hook.
- **Raw `Campaign`/`LoadedAggregate` return** — rejected for aggregate-mutability leakage (write-side analog of M031's read-side rejection).
- **New milestone-local return type** — rejected; `SaveResult` already provides exactly what a write-side caller needs, with no new type required.
- **Any retry/translation of `OptimisticConcurrencyConflict`** — rejected; explicitly out of this milestone's frozen scope.
- **Any architecture-checker change** — rejected; every needed import is already covered.

---

## 25. In Scope

- One command (`PrepareCampaignForAuthorizationCommand`), one handler (`PrepareCampaignForAuthorizationHandler`).
- One `get()` → one `prepare_for_authorization()` → one `save()` sequence.
- Caller-supplied `expected_persisted_version`, transparent `OptimisticConcurrencyConflict` propagation.
- `SaveResult` returned unchanged.
- `CommandEntryPoint` compatibility, proven by direct test-only binding.
- Focused unit, contract, architecture, and PostgreSQL integration tests, mirroring M030/M031's established patterns.
- No architecture-checker change.

---

## 26. Out of Scope

Any retry, backoff, or automatic conflict-resolution policy; any other Campaign mutation (a second transition, batch transition, or bulk update); any `Run`/`EvidencePackage`/`Review` command or query; any composition-root/registry/dispatcher/mediator/service-locator/DI framework; any transport layer; any new architecture-checker rule beyond what M030 already established; any market-data/vendor/trading/execution behavior; any MILESTONE-033 work.

---

## 27. Deferred Work

- Retry-on-`OptimisticConcurrencyConflict` policy — now unblocked by this milestone's own future implementation, but not itself in scope.
- Any additional Campaign mutation command (`record_authorization`, `activate`, `suspend`, `resume`, `complete`, `cancel`, `revise_scope_statement`).
- Any command or query for `Run`, `EvidencePackage`, or `Review`.
- Any composition-root abstraction beyond direct binding.
- Any transport/entrypoint adapter.
- MILESTONE-033 and beyond.

---

## 28. Risks

| Risk | Mitigation |
| --- | --- |
| Conflict path becoming untestable | Resolved by design: caller-supplied `expected_persisted_version` (Option A, Section 11). The M032 conflict evidence uses the same frozen repository optimistic-concurrency semantics proven in M023, but its interfering write is M032-specific: `revise_scope_statement()` is used to advance the persisted version while preserving `DRAFT` so the command under test can still execute `prepare_for_authorization()` before the stale-version `save()` fails (Section 21) |
| Lost version metadata | Resolved: `SaveResult.persisted_version` (the *new* version) is returned unchanged, not discarded (Section 13) |
| Stale-write semantics confusion | Explicitly documented (Section 11): the aggregate mutation always operates on the freshly-loaded (current) state; only the `save()` guard uses the caller-supplied expected version |
| Mutation-selection bias | Addressed via a full 8-candidate comparison (Section 5) and an honest three-way trade-off among the viable candidates (Section 6), not a first-plausible-option choice |
| Accidental retry introduction | Explicitly and permanently excluded (Section 14, 26); exactly one `save()` attempt |
| Transaction overreach | Explicitly rejected (Section 17): no shared transaction spans `get()` and `save()`; each repository call owns its own unit of work, unchanged from M030/M031 |
| Domain-rule duplication | Explicitly rejected (Section 16): zero validation logic duplicated from the aggregate |
| Generic lifecycle-framework pressure | This design freezes one command for one mutation; Section 27 explicitly defers every other mutation to its own future, independently-scoped milestone |
| Package-boundary drift | Verified: zero new architecture-checker change; every import already covered (Section 19-20) |
| Test-only binding becoming accidental precedent | Consistent with M030's/M031's own explicit position: evaluated later with more evidence, not enforced as a framework now |
| Future milestones copying this pattern without independent review | Section 23-24 explicitly document that every decision here was independently re-derived for this specific mutation, not merely copied from M030/M031 |
| M033 leakage | None found; Sections 26-27 explicitly exclude and defer all such work |

---

## 29. Cross-Milestone Compatibility

- Uses M020's `Campaign.prepare_for_authorization()` and `CampaignRepository.save()` exactly as frozen — no signature change, no reinterpretation.
- Uses M023's concrete PostgreSQL adapter's `save()`/`OptimisticConcurrencyConflict` behavior exactly as frozen.
- Uses M027's `CommandHandler` Protocol exactly as frozen — structural conformance only.
- Uses M029's `CommandEntryPoint` exactly as frozen — direct construction, no modification.
- Coexists with M030's `CreateCampaignCommand`/`CreateCampaignHandler` and M031's `GetCampaignQuery`/`GetCampaignHandler`/`CampaignSnapshot` in the same package without modifying any of them; the new module is additive only.
- Does not modify `tools/check_architecture.py`.
- Does not modify any M020-M032 governance document.

---

## 30. Acceptance Gate

This design is complete and ready for independent review when:

- [x] All required design questions (Phase 3, items 1-13) are answered with justification, not left open.
- [x] Every load-bearing decision documents alternatives, advantages, disadvantages, and a rejection/selection reason.
- [x] The exact command type, handler type, module placement, field names/types, constructor dependencies, expected-version model, load-mutate-save sequence, return type, conflict/error behavior, validation ownership, transaction ownership, `CommandEntryPoint` usage, architecture-checker impact, and test obligations are all frozen — nothing is left for implementation to invent.
- [x] No M020-M031 frozen contract is reopened.
- [x] No prohibited capability (retry, second mutation, composition root, registry, dispatcher, transport, generic framework) appears anywhere in this design.

---

## 31. Hostile Self-Review

Adversarial sweep performed against this document's own content before finalizing:

| Attack | Finding |
| --- | --- |
| Mutation not actually valid from a reproducible initial state | Not found — `prepare_for_authorization` requires only `DRAFT`, which M030's frozen `CreateCampaignHandler` already reliably produces (Section 5-6) |
| Unresolved expected-version source | Not found — Option A frozen explicitly with full justification (Section 11) |
| Impossible conflict reproduction | Not found — Section 21 scenario 2 specifies the exact interfering-write mechanism (`revise_scope_statement()` on an independently loaded aggregate for the same identity), explicitly distinguishing it from `prepare_for_authorization()`, which cannot serve this role without invalidating its own domain precondition before the command under test reaches the concurrency check |
| Hidden retry | Not found — Section 14/26 explicitly and permanently exclude retry; exactly one `save()` attempt (Section 12) |
| Hidden second capability | Not found — exactly one command, one handler, one mutation method (Section 25) |
| Return contract losing version metadata | Not found — `SaveResult.persisted_version` (the new version) is preserved, not discarded (Section 13) |
| `SaveResult` leaking persistence details | Not found — `SaveResult` is a `shared.contracts` type, persistence-neutral, already used by `usecases` transitively via `save()`'s own return type; no `shared.persistence` import anywhere (Section 13, 19) |
| Extra repository calls | Not found — exactly one `get()`, one `save()`, verified in Section 12's exact sequence |
| Missing write suppression after domain failure | Not found — Section 12/15 explicitly confirm `save()` is never reached if the domain mutation raises |
| Transaction orchestration without authority | Not found — Section 17 explicitly rejects any shared transaction or `run_composed()` usage |
| Generic lifecycle abstraction | Not found — no base class, no generic `LifecycleTransitionCommand[T]`, one concrete command for one concrete mutation |
| Infrastructure import | Not found — Section 19's import list contains no persistence, no third-party infrastructure library, no `Clock` |
| Architecture-checker mismatch | Not found — Section 19-20 verify every needed import already resolves under the existing, unmodified rule |
| Production composition leakage | Not found — Section 18 confirms binding is demonstrated in tests only |
| M033 leakage | Not found — Sections 26-27 explicitly exclude and defer all such work |

No genuine issue survived this sweep requiring correction. No decision in this document is deferred to "implementation will decide."

---

## 32. Final Status

```
═══════════════════════════════════════════════════════════════════════════════

              MILESTONE-032 DESIGN CANDIDATE

═══════════════════════════════════════════════════════════════════════════════

Status:                          CANDIDATE_FOR_FINAL_INDEPENDENT_DESIGN_RE_REVIEW
Correction Applied:              M032-DESIGN-REVIEW-0001 (Section 21 conflict-scenario mechanism)
Design Questions Answered:       13 / 13
Load-Bearing Decisions Justified: 8 / 8 (Section 23)
Prohibited Items Introduced:     0
Frozen Contracts Reopened:       0
Architecture-Checker Changes:    0 (verified unnecessary, Section 20)

Selected Mutation:               Campaign.prepare_for_authorization()
Selected Command Type:           PrepareCampaignForAuthorizationCommand
Selected Handler Type:           PrepareCampaignForAuthorizationHandler
Selected Return Type:            SaveResult (frozen M020 type, unchanged)
Selected Module:                 usecases/prepare_campaign_for_authorization.py
Selected Dependency Style:       Constructor injection (CampaignRepository only)
Selected Binding:                Direct CommandEntryPoint(handler) construction, test-only
Selected Version Model:          Caller-supplied expected_persisted_version (Option A)
Selected Conflict Strategy:      Fully transparent propagation (no handler-level try/except, no retry)

NEXT PERMITTED ACTION: MILESTONE-032 FINAL INDEPENDENT DESIGN RE-REVIEW

═══════════════════════════════════════════════════════════════════════════════
```
