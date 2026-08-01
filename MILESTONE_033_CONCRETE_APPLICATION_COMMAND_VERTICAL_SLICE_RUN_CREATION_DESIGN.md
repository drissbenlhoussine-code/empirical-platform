# MILESTONE-033 - Concrete Application Command Vertical Slice (Run Creation) Design

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW**

This document is a design candidate. It has not been reviewed, approved, or frozen. It does not authorize implementation.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at design candidate | `c0cef32ce3d18f2056068d60ee2d6fa89def941c` |

## 3. Frozen Authority Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Concrete Application Command Vertical Slice — Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 Scope | APPROVED_AND_FROZEN (`MILESTONE_033_..._SCOPE.md`, candidate commit `04e274240f7958d80bc0cb87f92f825b563fbd5a`) |
| M033 Scope Freeze | APPROVED_AND_FROZEN (`MILESTONE_033_..._SCOPE_FREEZE.md`, freeze commit `44dd29e34f6150bd37bc466eed14098d75ac57ab`) |

## 4. Architectural Context

`Run` has an identical repository-Protocol shape to `Campaign` (`get`/`add`/`save`, M020) and an identical concrete PostgreSQL adapter shape (M023), but zero application-layer proof. This milestone proves the frozen `usecases`/`CommandHandler`/`CommandEntryPoint` pattern — validated exclusively against `Campaign` across M030-M032 — generalizes to a second aggregate, using the narrowest operation (`add()`-based creation), directly mirroring M030's own original role.

## 5. Run Creation Semantics

Verified by direct inspection of `src/empirical_platform/run/aggregate.py`:

- **Constructor:** `Run.__init__(self, *, identity: DomainIdentity[RunId], campaign_id: CampaignId) -> None`. Exactly two required keyword-only arguments.
- **Constructor validation:** structural `isinstance` checks only — `identity` must be a `DomainIdentity`, `identity.governance_id` must be a `RunId`, `campaign_id` must be a `CampaignId`. No business-rule validation beyond what `RunId`/`CampaignId`'s own `__post_init__` (regex format checks, e.g. `RUN-\d{4}`) already performs when those value objects are constructed.
- **Initial lifecycle state:** `RunLifecycleState.CREATED`, set unconditionally inside `__init__` — not produced via `_transition()`.
- **Initial aggregate version:** `AggregateVersion.initial()`.
- **No context fields at construction:** unlike every `_transition()`-driven mutation (`authorize`, `start_acquisition`, `cancel`, etc., and unlike M032's `prepare_for_authorization()`), the constructor takes no `actor`, `occurred_at`, `correlation_id`, or `reason`. Construction does not append a `StateTransitionRecord`; `_transition_history` starts as an empty tuple.
- **No derived fields:** `_manifests` starts as an empty tuple; `_next_transition_sequence` starts at `TransitionSequence.initial()`.
- **No collaborator beyond identity supply and persistence:** the aggregate itself requires nothing beyond its two constructor arguments.

**Conclusion:** Run creation is a pure value-construction operation with no timestamp/actor/reason semantics — architecturally simpler than M032's `prepare_for_authorization()` and directly analogous to M030's `Campaign(identity=..., scope_statement=...)` construction.

## 6. Campaign Existence Decision

**This is the design's hardest question. Selected: Option A — no application-level Campaign lookup; persistence-enforced referential integrity.**

### 6.1 Verified Database Constraint

Direct inspection of `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py` line 148 confirms:

```python
sa.ForeignKeyConstraint(["campaign_id"], ["campaign.governance_id"])
```

on the `run` table (frozen since M022). A `Run` row referencing a nonexistent `campaign.governance_id` is rejected by PostgreSQL itself at `INSERT` time (SQLSTATE `23503`, foreign-key violation) under the naming convention `"fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s"` (line 41 of the same file), producing constraint `fk_run_campaign_id_campaign`.

### 6.2 Verified Exact Propagation Path

Direct inspection of `src/empirical_platform/shared/persistence/postgres.py` (`PostgresConnectionUnitOfWork.execute()`, lines 98-113) confirms every SQL exception raised during `work.execute(...)` — including a foreign-key violation — is wrapped via `translate_persistence_error(exc, operation="execute", context={...})` into a `FoundationError` (`category=FoundationErrorCategory.PERSISTENCE`).

Direct inspection of `src/empirical_platform/shared/persistence/postgres_repositories/run_repository.py::PostgresRunRepository.add()` (lines 196-249) confirms its `except FoundationError as exc:` block calls `unique_violation_constraint_name(exc)` (from `_errors.py`), which — per direct inspection of that helper (lines 17-32) — checks `diag.sqlstate != "23505"` (the unique-violation SQLSTATE) and returns `None` for any other SQLSTATE, including `23503` (foreign-key violation). Since `constraint_name` is `None`, `None not in _ROOT_UNIQUE_CONSTRAINTS`, so the bare `raise` at the end of the `except` block re-raises the original `FoundationError` **unchanged** — no translation, no wrapping, no Run-specific or Campaign-specific error type.

**Exact propagation chain for a nonexistent Campaign reference:** `INSERT INTO run ...` (FK violation) → SQLAlchemy `IntegrityError` → `translate_persistence_error()` → `FoundationError(category=PERSISTENCE, layer="persistence", operation="execute")` → re-raised unchanged by `PostgresRunRepository.add()`'s `except FoundationError` block (constraint name does not match `_ROOT_UNIQUE_CONSTRAINTS`) → propagates unchanged through the handler (no `try`/`except`) → propagates unchanged through `CommandEntryPoint.__call__`.

### 6.3 Option Comparison

| Criterion | A: No lookup, persistence-enforced | B: Handler calls `CampaignRepository.get()` first |
| --- | --- | --- |
| Frozen domain semantics | `Run.__init__` never required Campaign validation | Same |
| Database referential integrity | Already exists and is authoritative (Section 6.1) | Redundant with the same guarantee — the FK still fires even if a pre-check passes |
| Error behavior | One well-defined failure path: `FoundationError` on FK violation | Two failure paths for the same problem: `AggregateNotFound` from the pre-check, or the same FK violation if the pre-check race-loses |
| Repository call count | One (`RunRepository.add()`) | Two (`CampaignRepository.get()` + `RunRepository.add()`) |
| Cross-aggregate coupling | None — handler depends on `RunRepository` only | Handler gains a `CampaignRepository` dependency for a check the database already performs |
| Transaction implications | Single atomic `INSERT`, no read-then-write window | A read-then-write window exists unless explicitly transaction-wrapped; no existing frozen primitive spans two different repositories' calls without `run_composed()` |
| Race/TOCTOU behavior | None — the FK check is part of the same atomic `INSERT` that creates the Run row | A pre-check-then-insert has a structural TOCTOU window (mitigated only because nothing in this codebase deletes a Campaign, but this is incidental, not designed-in) |
| Testability | Fully deterministic against real PostgreSQL — insert a Run referencing an unseeded governance id | Fully deterministic, but exercises two collaborators for one guarantee |
| Scope purity | Introduces no second capability | Introduces a de facto "verify Campaign exists" capability inside a Run-creation handler — a hidden second responsibility the scope freeze (Section 17) explicitly warns against treating as a design question, not a hidden scope item |
| Architecture-checker impact | Handler needs `run` only (plus `identifiers`, `shared`) | Handler would also need `campaign` import for `CampaignRepository` (already allowed, but adds an unjustified dependency) |

**Selected: Option A.** It requires strictly fewer dependencies, fewer repository calls, and produces one deterministic failure path, while relying on a database guarantee that already exists and cannot be bypassed even if Option B were also implemented. Option B would not eliminate the FK failure path — it would only add a redundant, race-exposed pre-check on top of a guarantee the database already enforces atomically.

### 6.4 Frozen Failure Specification

A `CreateRunCommand` referencing a `campaign_governance_id` with no corresponding persisted Campaign produces a `FoundationError` with `category=FoundationErrorCategory.PERSISTENCE`, raised by `RunRepository.add()`, propagating transparently and unmodified through `CreateRunHandler.handle()` and `CommandEntryPoint.__call__`. It is explicitly **not** `AggregateNotFound`, **not** `AggregateAlreadyExists`, and **not** any Run- or Campaign-specific application error — it is the same class of raw infrastructure failure any other constraint violation not covered by `_ROOT_UNIQUE_CONSTRAINTS` would produce.

## 7. Identity Candidate Analysis

| Option | Description | Assessment |
| --- | --- | --- |
| A | Caller supplies full `DomainIdentity[RunId]` | Forces the caller to generate or obtain a `runtime_id` — a responsibility M030 deliberately kept inside the handler via `RuntimeIdentifierGenerator` |
| **B** | **Caller supplies governance `RunId` (raw string); handler generates `runtime_id`** | **Directly mirrors `CreateCampaignCommand`/`CreateCampaignHandler` (M030), the only existing precedent for aggregate creation in this codebase** |
| C | Handler generates both governance and runtime identity components | No precedent; governance identifiers are meaningful business identifiers a caller must control (mirroring `CampaignId`'s own caller-supplied model) |
| D | Another existing frozen mechanism | No other identity-generation mechanism exists in the frozen codebase |

## 8. Selected Identity Model

**Option B**, mirroring M030 exactly: `CreateRunCommand` carries a raw `run_governance_id: str`; `CreateRunHandler` constructs `RunId(command.run_governance_id)` (format validation via the frozen `Identifier.__post_init__`) and obtains `runtime_id` from the injected `RuntimeIdentifierGenerator.generate()`, then pairs them via `DomainIdentity(...)`. This preserves deterministic testing (a `DeterministicRuntimeIdentifierGenerator` test double already exists and is used by M030's own tests), duplicate-identity behavior is unchanged (still enforced by `RunRepository.add()`'s `AggregateAlreadyExists`), and caller usability matches the existing Campaign-creation precedent exactly.

## 9. Selected Architecture

One concrete command, `CreateRunCommand`, and one concrete handler, `CreateRunHandler`, in a new module `usecases/create_run.py`, alongside the three existing Campaign-only modules. The handler depends on `RunRepository` and `RuntimeIdentifierGenerator` only (both frozen Protocols) via constructor injection — no `CampaignRepository` (Section 6). It performs exactly one `RunRepository.add()` call and returns `DomainIdentity[RunId]`. Exactly one architecture-checker addition is required: `"run"` added to `ALLOWED["usecases"]` (Section 23).

## 10. Exact Command Contract

```python
@dataclass(frozen=True, slots=True)
class CreateRunCommand:
    """Request to create a new Run for an existing Campaign.

    Carries raw, unvalidated data; `CreateRunHandler` translates it into the
    already-frozen `RunId` and `CampaignId` value objects, which perform all
    format validation. Campaign existence is not validated here or in the
    handler -- it is enforced by the database foreign-key constraint on the
    `run.campaign_id` column (see the design's Campaign Existence Decision).
    """

    run_governance_id: str
    campaign_governance_id: str
```

Exactly two fields, both raw strings, mirroring `CreateCampaignCommand`'s style exactly. No transport metadata, tracing metadata, retry metadata, pagination/query fields, serialization behavior, authorization context, or speculative future fields — none are required by the frozen `Run` constructor (Section 5), and the mission's Phase 5 explicitly prohibits inventing any.

## 11. Exact Handler Contract

```python
class CreateRunHandler:
    """Creates and persists a new Run for one `CreateRunCommand`."""

    __slots__ = ("_run_repository", "_runtime_identifier_generator")

    def __init__(
        self,
        *,
        run_repository: RunRepository,
        runtime_identifier_generator: RuntimeIdentifierGenerator,
    ) -> None:
        self._run_repository = run_repository
        self._runtime_identifier_generator = runtime_identifier_generator

    def handle(self, command: CreateRunCommand) -> DomainIdentity[RunId]:
        """Create and persist a new Run; return its identity."""
        identity = DomainIdentity(
            governance_id=RunId(command.run_governance_id),
            runtime_id=self._runtime_identifier_generator.generate(),
        )
        run = Run(
            identity=identity,
            campaign_id=CampaignId(command.campaign_governance_id),
        )
        self._run_repository.add(run)
        return run.identity
```

- **Package/module:** `empirical_platform.usecases.create_run`, alongside `create_campaign.py`, `get_campaign.py`, `prepare_campaign_for_authorization.py`.
- **`CommandHandler` conformance:** structural — `CreateRunHandler` satisfies `CommandHandler[CreateRunCommand, DomainIdentity[RunId]]` by having a matching `handle()` signature, exactly like every prior concrete handler; no explicit inheritance.
- **Collaborators:** `RunRepository` (for `add()`) and `RuntimeIdentifierGenerator` (for `runtime_id` generation) only. No `CampaignRepository`, no concrete persistence or runtime adapter type anywhere in the module.

## 12. Campaign Reference Semantics

`campaign_governance_id: str` on the command is translated into a `CampaignId` value object by the handler (format-validated by `CampaignId.__post_init__`, unchanged), then passed directly to `Run.__init__(campaign_id=...)`. No `DomainIdentity[CampaignId]` is constructed or required — `Run.campaign_id` is typed as a bare `CampaignId`, not a `DomainIdentity`, confirmed directly in `run/aggregate.py` line 43-47. No `CampaignRepository` interaction of any kind occurs (Section 6).

## 13. Identity Generation Semantics

`runtime_id` is generated exactly once per `handle()` invocation via the injected `RuntimeIdentifierGenerator.generate()`, identical in mechanism, ownership, and testability to M030's `CreateCampaignHandler`. `governance_id` (the `RunId`) is caller-supplied via `command.run_governance_id`, never generated by the handler.

## 14. Exact Creation Sequence

1. Read `command.run_governance_id` and `command.campaign_governance_id` unchanged.
2. Construct `RunId(command.run_governance_id)` — raises `ValueError` on format violation; `add()` is never reached if this fails.
3. Call `self._runtime_identifier_generator.generate()` — raises `FoundationError` (category `TIME_IDENTIFIER`) on failure, per the frozen `UuidRuntimeIdentifierGenerator` implementation; `add()` is never reached if this fails.
4. Construct `DomainIdentity(governance_id=<RunId>, runtime_id=<generated>)`.
5. Construct `CampaignId(command.campaign_governance_id)` — raises `ValueError` on format violation; `add()` is never reached if this fails.
6. Construct `Run(identity=<DomainIdentity>, campaign_id=<CampaignId>)`.
7. Call `self._run_repository.add(run)` exactly once.
8. Return `run.identity` — read directly off the constructed aggregate (not the local `identity` variable), matching M030's exact pattern, proving the aggregate accepted precisely that identity.

No secondary repository lookup at any step. No transaction orchestration beyond `add()`'s own internal atomic unit of work (M023, unchanged). If any step before `add()` fails, `add()` is never called — no partial write is possible. If `add()` itself fails (duplicate identity, nonexistent Campaign, or any other infrastructure failure), the exception propagates immediately; no retry, no second `add()` attempt is ever made.

## 15. Return Contract

| Option | Assessment |
| --- | --- |
| A: `DomainIdentity[RunId]` | Selected — matches M030's own resolution for the identical question |
| B: the `Run` aggregate | Rejected — aggregate-mutability leakage through the write boundary, the same principle M031 formalized for the read side |
| C: `SaveResult` | Rejected — for creation, `SaveOperation` is always `CREATED` (no other value is reachable via `add()`), so exposing it conveys zero information; `persisted_version` is always `AggregateVersion.initial()` for a newly created aggregate, equally uninformative. This mirrors M030's own rejection of `SaveResult` for `CreateCampaignHandler` exactly — unlike M032's `save()`-based mutation, where the *new* version is genuinely actionable for a caller's next write |
| D: milestone-local immutable result type | Rejected — no field beyond identity is needed; introducing a new type for a single field would be an unjustified abstraction |
| E: no return value | Rejected — the caller has no way to address the newly created Run in any future call, defeating the milestone's own purpose |

**Selected: Option A, `DomainIdentity[RunId]`.**

## 16. Duplicate Identity Behavior

Handled entirely by the database's existing unique constraints on the `run` table (`pk_run`, `uq_run_governance_id` — the same `_ROOT_UNIQUE_CONSTRAINTS` set `PostgresRunRepository.add()` already checks, unchanged since M023). A duplicate `runtime_id` or `governance_id` raises `AggregateAlreadyExists(aggregate_kind="Run", identity=...)`, propagating transparently through the handler (no `try`/`except`). No application-level duplicate check is added — mirroring M030's own reliance on the identical mechanism for `Campaign`.

## 17. Missing Campaign Behavior

See Section 6.4 — a `FoundationError` (category `PERSISTENCE`) from the foreign-key violation, propagating transparently and unmodified.

## 18. Error Semantics

| Failure | Origin | Exception | Propagation |
| --- | --- | --- | --- |
| Duplicate Run identity | `RunRepository.add()` | `AggregateAlreadyExists` | Transparent |
| Nonexistent Campaign reference | `RunRepository.add()` (FK violation) | `FoundationError` (category `PERSISTENCE`) | Transparent (Section 6.4) |
| Invalid `run_governance_id`/`campaign_governance_id` format | `RunId`/`CampaignId.__post_init__` | `ValueError` | Transparent; `add()` never reached |
| Identifier generation failure | `RuntimeIdentifierGenerator.generate()` | `FoundationError` (category `TIME_IDENTIFIER`) | Transparent; `add()` never reached |
| Arbitrary repository/infrastructure failure | `RunRepository.add()` | Whatever the repository raises | Transparent |

No `try`/`except` anywhere in `CreateRunHandler`, matching M029's frozen transparent-error-propagation invariant and M030/M031/M032's own precedent exactly. No new application error type, no result/status wrapper, no error translation.

## 19. Validation Ownership

| Concern | Owner |
| --- | --- |
| `run_governance_id`/`campaign_governance_id` format | `RunId`/`CampaignId` value objects (frozen, unchanged) |
| Identity/campaign_id structural type | `Run.__init__`'s own `isinstance` checks (frozen, unchanged) |
| Campaign existence (referential integrity) | Database foreign-key constraint (frozen schema, M022) |
| Duplicate identity | Database unique constraints (frozen schema, M022), surfaced via `AggregateAlreadyExists` (frozen, M020/M023) |
| Command-level validation | None — `CreateRunCommand` carries raw unvalidated strings, deferring entirely to the value objects and aggregate the handler constructs, exactly matching `CreateCampaignCommand`'s precedent |

The handler performs no validation duplicating any of the above.

## 20. Transaction Ownership

No application-level transaction orchestration is introduced. Exactly one `RunRepository.add()` call, already atomic via `PostgresRunRepository.add()`'s own internal `unit_of_work()` (M023, unchanged) — for creation this covers only the root `run` row insert (zero manifests, zero transitions exist at creation, per Section 5). `run_composed()` (M024) is not used: that primitive exists to coordinate multiple repository operations across aggregates atomically, and this milestone has exactly one repository call to one repository — introducing it would be an unjustified dependency the mission's Phase 11 explicitly warns against. The Campaign-existence guarantee (Section 6) is enforced by the database as part of the same atomic `INSERT`, so no read-then-write window exists that would otherwise require transaction-spanning coordination.

## 21. CommandEntryPoint Binding

Identical pattern to M030/M031/M032: `CommandEntryPoint(CreateRunHandler(run_repository=..., runtime_identifier_generator=...))`, constructed directly in tests only. No production composition code, no registry, no command bus, no dispatcher, no mediator, no service locator, no DI framework. The command instance reaches the handler unchanged; the result or exception returns to the caller unchanged — proven by the identical structural/behavioral test pattern M030 established (`tests/unit/test_command_entry_point.py` already covers `CommandEntryPoint` generically; no `CommandEntryPoint` change is needed).

## 22. Package and Dependency Boundaries

`usecases/create_run.py` imports: `Run` and `RunRepository` from `empirical_platform.run` (new — requires the Section 23 checker addition); `RunId`, `CampaignId`, `DomainIdentity` from `empirical_platform.identifiers` (already allowed); `RuntimeIdentifierGenerator` from `empirical_platform.shared.identifiers` (already allowed); `dataclass` from stdlib. **Zero import from `empirical_platform.campaign`** — under the selected Campaign-existence model (Option A, Section 6), the module needs only the `CampaignId` value object (already covered by the existing `identifiers` grant), not `CampaignRepository` or anything else from the `campaign` package. The three existing Campaign-only modules (`create_campaign.py`, `get_campaign.py`, `prepare_campaign_for_authorization.py`) are unmodified and retain their existing `campaign` imports unchanged.

## 23. Architecture-Checker Impact

Direct inspection of `tools/check_architecture.py` (lines 11-29) confirms `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` — `"run"` is absent. Exactly one line changes:

```python
"usecases": {"shared", "identifiers", "campaign", "run"},
```

`FORBIDDEN_IMPORT_PREFIXES["usecases"]` (lines 68-73) already exists with the full `("empirical_platform.shared.persistence", "sqlalchemy", "psycopg", "boto3")` tuple, applying regardless of which packages are in `ALLOWED["usecases"]` — **no change needed there**, unlike M030's original addition, which had to introduce both the `ALLOWED` entry and the `FORBIDDEN_IMPORT_PREFIXES` entry because the `usecases` package did not exist yet. This milestone's checker change is strictly narrower than M030's.

**New negative fixtures required:** at minimum one fixture proving `usecases` still cannot import `empirical_platform.evidence` or `empirical_platform.review` (neither is in `ALLOWED["usecases"]` even after this addition) — demonstrating the addition of `"run"` was exact and did not accidentally broaden the boundary beyond what this milestone needs. All 7 pre-existing `usecases`-scoped fixtures (persistence/sqlalchemy/psycopg/boto3 imports) remain valid unmodified, since `FORBIDDEN_IMPORT_PREFIXES["usecases"]` does not change.

## 24. PostgreSQL Evidence Strategy

Using the established disposable `postgres:17` container pattern (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1` opt-in, frozen Alembic migration chain, identical to M030-M032):

1. **Successful Run creation:** seed one real Campaign (direct `PostgresCampaignRepository.add()` call, test scaffolding only — mirroring how M031/M032 seed a Campaign), invoke `CreateRunCommand` through a bound `CommandEntryPoint`, assert the returned `DomainIdentity[RunId]` matches the supplied governance id.
2. **Persisted identity:** reload via `RunRepository.get(identity)`; assert `loaded.aggregate.identity == identity`.
3. **Correct Campaign association:** assert `loaded.aggregate.campaign_id == CampaignId(seeded_campaign_governance_id)`.
4. **Initial state/version:** assert `loaded.aggregate.state is RunLifecycleState.CREATED` and `loaded.persisted_version == AggregateVersion.initial()`.
5. **Duplicate Run identity:** invoke the command twice with the same `run_governance_id` against the same seeded Campaign; assert the second invocation raises `AggregateAlreadyExists`.
6. **Nonexistent Campaign reference:** invoke the command with a syntactically valid but never-persisted `campaign_governance_id` (e.g. `"CAMP-9999"`); assert a `FoundationError` with `category=FoundationErrorCategory.PERSISTENCE` is raised, and explicitly assert it is **not** an instance of `AggregateAlreadyExists`, `AggregateNotFound`, or any other repository-contract error — a raw, untranslated infrastructure failure.
7. **Exact error propagation:** for every failure test, assert on the exact exception class/category — no wrapping anywhere in the handler layer.
8. **No schema/migration change:** `git diff -- migrations/` is empty (verified at commit time, not merely asserted).
9. **Existing Run repository regression:** the Run-specific tests in `tests/integration/test_m023_postgres_repositories.py` remain green, unmodified.
10. **M030-M032 regression:** the full real-PostgreSQL integration suite remains green.

All repository/runtime construction in these tests is test scaffolding only (direct `PostgresRunRepository`/`PostgresCampaignRepository` construction over a real `PostgresPersistenceService`), matching M030-M032's own established pattern — no production composition wiring is introduced.

## 25. Test Strategy

**A. Command tests:** exact two fields (`run_governance_id`, `campaign_governance_id`); value preservation; immutability (`frozen=True`); no extra fields; no validation performed at the command layer (deferred entirely to value objects/aggregate).

**B. Handler success:** exact two dependencies (`RunRepository`, `RuntimeIdentifierGenerator`) via deterministic recording fakes (no mocks); exact `RunId`/`CampaignId` construction from command fields; exact identity generation via the injected generator; exact `Run` construction (`identity`, `campaign_id`); exactly one `RunRepository.add()` call with the exact constructed aggregate; selected return contract (`run.identity`, read off the aggregate, not the local variable); no unrelated repository operation (`get()`/`save()` never called); synchronous behavior.

**C. Campaign existence behavior:** a deterministic recording fake `RunRepository` cannot itself simulate a real foreign-key violation (that is inherently a database-level guarantee) — this is proven at the integration level only (Section 24, item 6). Unit-level tests instead prove the handler performs **no** `CampaignRepository` interaction of any kind (structural assertion: the handler's `__slots__`/constructor signature carries no `campaign_repository` parameter), confirming Option A's "no application-level lookup" decision is genuinely implemented, not merely designed.

**D. Failure behavior:** duplicate identity (`AggregateAlreadyExists` from a failing fake `RunRepository.add()`, propagates unchanged); malformed `run_governance_id`/`campaign_governance_id` (`ValueError` from value-object construction, `add()` never called — verified via a recording fake asserting zero invocations); identifier-generator failure (`FoundationError` from a failing fake generator, `add()` never called); arbitrary repository failure (propagates unchanged); no retry; no second `add()` call in any failure path.

**E. `CommandEntryPoint`:** structural conformance (`CreateRunHandler` satisfies `CommandHandler[CreateRunCommand, DomainIdentity[RunId]]`, mypy-checked); exact command object reaches the handler unchanged; exactly-once invocation; exact result/exception propagates unchanged — reusing the existing generic `CommandEntryPoint` test pattern, no new `CommandEntryPoint` behavior to test.

**F. Architecture:** real source tree passes `tools/check_architecture.py` with 0 violations; `usecases` may import `run` (new, positively exercised by the real `create_run.py` module) but not `evidence`/`review` (new negative fixture, Section 23); no persistence import anywhere in `create_run.py` (verified by the unchanged `FORBIDDEN_IMPORT_PREFIXES["usecases"]` fixtures continuing to trigger); domain packages (`run`, `campaign`, etc.) still cannot import `usecases` (unchanged, pre-existing enforcement by omission).

**G. PostgreSQL:** exactly the ten items enumerated in Section 24.

No arbitrary coverage percentage is set as a target; coverage is reported as evidence, not gated to a specific number, matching M030-M032's own precedent.

## 26. Alternatives Considered

| Decision | Alternatives | Selected | Rejection reason for alternatives |
| --- | --- | --- | --- |
| Campaign existence validation | A: persistence-enforced (selected); B: handler `CampaignRepository.get()`; C: another mechanism; D: new abstraction | A | See Section 6.3 — B is redundant and race-exposed, C/D have no frozen precedent or justification |
| Run identity supply | A: full `DomainIdentity` caller-supplied; B: governance caller-supplied, runtime handler-generated (selected); C: both handler-generated; D: other | B | See Section 7 — mirrors M030 exactly |
| Runtime identifier generation | Handler-owned via `RuntimeIdentifierGenerator` (selected); command-supplied | Handler-owned | Mirrors M030; keeps runtime identity opaque and handler-controlled |
| Command shape | Raw strings (selected); typed value objects on the command; extra context fields | Raw strings | Mirrors `CreateCampaignCommand`; defers all validation to value objects, avoiding duplicated validation logic |
| Handler dependencies | `RunRepository` only; `RunRepository` + `RuntimeIdentifierGenerator` (selected); `RunRepository` + `CampaignRepository` | `RunRepository` + `RuntimeIdentifierGenerator` | `RunRepository`-only cannot generate identity; `+CampaignRepository` rejected per Section 6 |
| Return contract | `Run` aggregate; `SaveResult`; `DomainIdentity[RunId]` (selected); no value; new result type | `DomainIdentity[RunId]` | See Section 15 |
| Error handling | Transparent propagation (selected); translation; result wrapper | Transparent propagation | Matches M029's frozen invariant and M030-M032's own precedent |
| Transaction ownership | No orchestration (selected); `run_composed()`; explicit wrapping | No orchestration | Single repository call, already atomic; `run_composed()` unjustified for one repository (Section 20) |
| Architecture-checker extension | Add `"run"` to `ALLOWED["usecases"]` (selected); broader package restructuring; new top-level package | Add `"run"` to `ALLOWED["usecases"]` | Narrowest correct change; mirrors precedent |
| Production composition | Deferred (selected); introduce composition root now | Deferred | Repeated-handler-need evidence bar still unmet (four handlers, still test-only binding) — unchanged from M030-M032's own consistent judgment |

## 27. Rejected Alternatives

Fully detailed per decision in Section 26; the single most consequential rejection is Option B for Campaign-existence validation (Section 6.3), rejected because it duplicates a guarantee the database FK constraint already provides atomically, adds an unjustified `CampaignRepository` dependency, and introduces a TOCTOU window with no corresponding benefit.

## 28. In Scope

- Exactly one Run creation command (`CreateRunCommand`).
- Exactly one Run creation handler (`CreateRunHandler`).
- `Run` aggregate construction (unmodified aggregate).
- `RunRepository.add()` (unmodified repository method).
- The selected identity model (Section 8) and Campaign-existence model (Section 6).
- The selected return/error behavior (Sections 15, 18).
- `CommandEntryPoint` compatibility (unmodified `CommandEntryPoint`).
- Focused unit/contract/PostgreSQL evidence (Sections 24-25).
- The narrowly required architecture-checker evidence (Section 23).

## 29. Out of Scope

Run retrieval; Run lifecycle transitions; Run save/update; a second Run command; Campaign mutation/query beyond what already exists; `EvidencePackage`; `Review`; retry/backoff; composition root; registry; dispatcher; mediator; service locator; DI framework; transport/API; audit runtime; schema/migration changes; market data; trading; MILESTONE-034.

## 30. Deferred Work

Run retrieval (a future query-side milestone, mirroring M031's role for Campaign); Run lifecycle transitions (`authorize`, `start_acquisition`, etc. — a future command-side milestone, mirroring M032's role); `EvidencePackage`/`Review` creation; retry-on-`OptimisticConcurrencyConflict` policy; composition-root abstraction; transport; audit integration; MILESTONE-034 and beyond.

## 31. Risks

| Risk | Mitigation |
| --- | --- |
| Hidden cross-aggregate coupling | Section 6/22 confirm zero `CampaignRepository`/`campaign` package dependency in the new module; verified structurally in tests (Section 25.C) |
| Campaign existence race | Eliminated by design — the FK check is part of the same atomic `INSERT` that creates the Run row (Section 6.3); no separate check-then-act window exists |
| Foreign-key error leakage | Explicitly specified and tested (Section 6.4, 24.6) rather than left as an undocumented surprise; the exact exception type and category are frozen by this design |
| Identity-generation inconsistency | Reuses the identical, already-proven `RuntimeIdentifierGenerator` mechanism from M030 |
| Duplicate identity semantics | Reuses the identical, already-proven `AggregateAlreadyExists` mechanism from M023/M030 |
| Architecture-rule broadening | The checker change is exactly one set-literal addition (Section 23), narrower than M030's own original two-part addition |
| Generic creation-framework pressure | Explicitly rejected (Section 26); one command, one handler, no abstraction layer |
| Test-only binding becoming unreviewed precedent | Consistent with M030-M032's own explicitly reasoned, repeatedly-revisited judgment that the repeated-handler-need evidence bar remains unmet — not a silent default |
| Persistence-enforced validation becoming accidental policy | Section 6 documents the decision explicitly, with its exact mechanism, exact failure type, and exact rejection of the alternative — not an implicit fallback |
| Future milestones copying the Run pattern without independent review | Each future milestone (Run retrieval, Run lifecycle transitions, EvidencePackage/Review) is explicitly deferred (Section 30), requiring its own scope selection and independent review, not silent extension of this one |
| MILESTONE-034 leakage | No MILESTONE-034 material referenced or introduced anywhere in this document |

## 32. Cross-Milestone Compatibility

No M020-M032 frozen contract is modified: `Run.__init__`, `RunRepository`, `PostgresRunRepository`, `CampaignId`, `RunId`, `DomainIdentity`, `RuntimeIdentifierGenerator`, `CommandHandler`, `CommandEntryPoint`, and all three existing `usecases` modules remain byte-identical. The one architecture-checker change (Section 23) is additive only — no existing `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` entry is narrowed or removed, and all pre-existing fixtures continue to trigger unmodified.

## 33. Acceptance Gate

This design is implementation-ready when: every load-bearing decision (Sections 6-23) is fully resolved with no open question left to implementation; every test category (Section 25) is concretely specified; the architecture-checker change is exact and minimal (Section 23); the PostgreSQL evidence strategy (Section 24) deterministically reproduces both the golden path and both failure paths (duplicate identity, missing Campaign); and no frozen M020-M032 contract requires modification (Section 32).

## 34. Hostile Self-Review

Attacked against the mission's full list:

- **Hidden Campaign validation capability:** none — Option A explicitly excludes any `CampaignRepository` interaction; verified structurally (Section 22) and by a dedicated unit test (Section 25.C).
- **Unresolved Campaign existence behavior:** resolved exactly, with exact exception type/category and exact propagation chain (Section 6).
- **Invalid foreign-key assumptions:** the FK constraint was verified directly in the real migration file (Section 6.1), not assumed from a description.
- **Unresolved identity source:** resolved (Sections 7-8, 13).
- **Runtime ID generation ambiguity:** resolved — handler-owned via the injected `RuntimeIdentifierGenerator`, mirroring M030.
- **Duplicate identity ambiguity:** resolved (Section 16) — unchanged database-enforced mechanism.
- **Return contract leakage:** resolved (Section 15) — `DomainIdentity[RunId]` only, no aggregate or persistence-metadata leakage.
- **Architecture checker mismatch:** resolved and verified directly against the live `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` dictionaries (Section 23), not assumed.
- **Extra repository calls:** none — exactly one `RunRepository.add()` call (Section 14); explicitly tested (Section 25.B).
- **Transaction overreach:** none — no `run_composed()`, no explicit wrapping (Section 20).
- **Generic creation abstraction:** none — one command, one handler, no shared base, no generic factory.
- **Production composition leakage:** none — `CommandEntryPoint` binding remains test-only (Section 21).
- **Second aggregate behavior:** none — `Run` only; `CampaignId` is used solely as an inert value carried on `Run`, never queried, mutated, or otherwise acted upon.
- **MILESTONE-034 leakage:** none — no M034 reference anywhere in this document.

No issue survived requiring correction before this design candidate was written.

## 35. Final Status

**CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW.** Not approved. Not frozen. Does not authorize implementation.

**Next permitted action:** MILESTONE-033 INDEPENDENT DESIGN REVIEW.
