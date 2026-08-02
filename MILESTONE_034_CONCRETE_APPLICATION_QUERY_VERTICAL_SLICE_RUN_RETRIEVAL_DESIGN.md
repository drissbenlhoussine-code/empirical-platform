# MILESTONE-034 - Concrete Application Query Vertical Slice (Run Retrieval) Design

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW**

This document is a design candidate. It has not been reviewed, approved, or frozen. It does not authorize implementation.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at design | `1d755f088ffe14e53a4c37796dc52ca7d99c526e` |

---

## 3. Frozen Authority Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Run Creation) | APPROVED_AND_FROZEN (implementation freeze `38ed45518d8a2068d29e7375c2c09ea2af80963c`) |
| M034 Scope | APPROVED_AND_FROZEN (`MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE_FREEZE.md`, commit `e6ad2c0e976ad0eb1cd00f8e15544d58ac45de7e`) |

This design makes no change to any M020-M034-scope artifact.

---

## 4. Architectural Context

The frozen M034 scope authorizes exactly one capability: a query vertical slice retrieving one `Run` by its full identity via the frozen `RunRepository.get()` method, proving the `QueryHandler`/`QueryEntryPoint` pattern — established and validated exclusively against `Campaign` via `GetCampaignHandler` (M031) — generalizes to a second aggregate. The scope explicitly left the result contract open; this design resolves that question, and every other open design question the scope-freeze document (Section 20) enumerated, using only the frozen dependencies it lists (Section 15/16 of the scope-freeze document).

---

## 5. Run Retrieval Semantics

Verified directly against `src/empirical_platform/run/repository.py` and the concrete adapter `src/empirical_platform/shared/persistence/postgres_repositories/run_repository.py`:

- **Exact input identity:** `DomainIdentity[RunId]` — a frozen pairing of a governance `RunId` and a runtime UUID (`RuntimeIdentifier`). `RunRepository.get(identity: DomainIdentity[RunId]) -> LoadedAggregate[Run]`.
- **Exact repository return type:** `LoadedAggregate[Run]`, a frozen `@dataclass(frozen=True, slots=True)` pairing a detached `Run` aggregate with its load-time `persisted_version: AggregateVersion`.
- **Aggregate contents returned:** `PostgresRunRepository.get()` unconditionally loads the `run` root row, all `run_manifest` rows (ordered by `position`), and all `run_transition` rows (ordered by `sequence`), then reconstructs a full `Run` aggregate via `_reconstruct_run`. There is no partial-load path — manifests and transition history are always loaded internally regardless of what the caller ultimately uses.
- **Persisted-version semantics:** `LoadedAggregate.persisted_version` is the root row's current `version` column value at load time — write-side optimistic-concurrency metadata, identical in kind to `CampaignRepository.get()`'s own `persisted_version`.
- **Manifests/history loading:** always eager, always full (verified: no `LIMIT`, no manifest/transition filtering in the adapter's `get()` SQL).
- **Missing-Run behavior:** `AggregateNotFound(aggregate_kind="Run", identity=identity)` is raised when no root row matches both `runtime_id` and `governance_id` (verified at `run_repository.py:149`). A separate diagnostic path raises `InvalidPersistedAggregateState` if a `runtime_id` exists but its `governance_id` does not match — an existing frozen behavior, not a new decision.
- **Campaign data:** `PostgresRunRepository.get()` issues no query against the `campaign` table. Only `run`, `run_manifest`, and `run_transition` are read. No Campaign data of any kind is loaded.
- **Secondary repository calls:** none — `get()` is a single `unit_of_work()` block issuing only `run`/`run_manifest`/`run_transition` reads.
- **Collaborators genuinely required:** `RunRepository` only. No other Protocol or concrete type is needed to satisfy the frozen scope's capability.

No Run behavior is invented or modified by this design; every fact above is quoted from already-frozen M020/M023 source.

---

## 6. Query Identity Candidate Analysis

| Candidate | Description | Assessment |
| --- | --- | --- |
| A | Query carries full `DomainIdentity[RunId]` | Directly compatible with `RunRepository.get()`'s exact signature with zero translation. Validation (format, type) is already fully owned by `RunId`/`DomainIdentity`'s own frozen `__post_init__` checks, performed before a query can even be constructed. Deterministic to test (pass an object, assert it reaches the repository `is`-identical). Identical in shape to `GetCampaignQuery.identity: DomainIdentity[CampaignId]` (M031). |
| B | Query carries `RunId` plus a separate runtime identifier field | Requires the handler (or query) to reconstruct a `DomainIdentity[RunId]` from two loose fields before calling `get()` — adds a translation step and a second validation surface for no benefit, since the caller already possesses (or can already construct) a `DomainIdentity[RunId]` before issuing a retrieval request. |
| C | Query carries raw governance/runtime strings; handler constructs frozen identifier types | This is `CreateRunCommand`'s (M033) pattern, justified there because the command *creates a new* `RunId`/`DomainIdentity` as part of persisting a brand-new aggregate, and needs a `RuntimeIdentifierGenerator` collaborator to mint the runtime half. Retrieval creates nothing — the identity already exists. Forcing raw strings here would require `GetRunHandler` to carry a `RuntimeIdentifierGenerator` dependency it has no legitimate use for (generating a *new* runtime UUID for an *existing* Run would be a bug, not a translation), or to accept a runtime-id string it can only pass through verbatim — an unjustified detour that adds a validation surface without adding capability. |
| D | Governance ID only, requiring a new identity-resolution capability | Rejected on direct repository evidence: `RunRepository` exposes only `get`/`add`/`save`, all of which require or produce a full `DomainIdentity[RunId]`; no governance-ID-only lookup mechanism exists anywhere in the frozen codebase (verified: no such method on `RunRepository`, `PostgresRunRepository`, or any other frozen Protocol). Introducing one would be new architectural capability, not a design decision within this milestone's frozen scope. |

---

## 7. Selected Query Identity Model

**Candidate A.** `GetRunQuery` carries `identity: DomainIdentity[RunId]` — the exact, already-validated pairing `RunRepository.get()` requires, with no translation step. This exactly mirrors `GetCampaignQuery`'s shape, and is independently justified above by `RunRepository.get()`'s own signature and by the absence of any evidence for a lighter-weight identity representation.

---

## 8. Result Contract Candidate Analysis

This is the central load-bearing design question the frozen scope deliberately left open (scope-freeze Section 19).

| Candidate | Description | Assessment |
| --- | --- | --- |
| A | Return the raw `Run` aggregate | `Run` exposes seven mutating methods (`authorize`, `start_acquisition`, `start_normalization`, `start_validation`, `complete_execution`, `cancel`, `fail`) plus `append_manifest` (verified in `run/aggregate.py`). A caller holding the returned `Run` could call any of these locally, mutating in-memory state with no path back to persistence (no `save()` is ever invoked by a query handler) — a phantom-mutation hazard. Independently verified true for `Run`'s own public surface, not merely asserted by analogy. Rejected. |
| B | Return `LoadedAggregate[Run]` directly | Same mutability leakage as A (the `.aggregate` field is the same mutable `Run`), plus it additionally exposes `persisted_version` — write-side optimistic-concurrency metadata that `RunRepository.save()` consumes identically to `CampaignRepository.save()`. A read-only query caller has no legitimate use for this value; exposing it invites an out-of-band `save()` call that bypasses the intended command-handler write path this project has consistently kept separate (M030-M033). Rejected. |
| C | A new immutable, milestone-local `RunSnapshot` | No mutation surface, no `persisted_version`. Fields are independently derived in Section 9 below from Run's own aggregate shape, not copied from `CampaignSnapshot`. Selected. |
| D | An existing frozen type | Searched directly: no existing frozen type carries exactly `{identity, campaign_id, state}` for `Run`. `Run` itself is rejected as A; `LoadedAggregate[Run]` is rejected as B; no `get_run.py` module or Run-specific DTO exists anywhere in the frozen codebase (confirmed: `find . -iname "get_run*"` returns nothing). Rejected — no candidate exists. |
| E | Another narrow, justified result type | Collapses into C; no alternative narrow shape was identified that isn't already covered by the candidates above. |

---

## 9. Selected Result Contract

**Candidate C: a new milestone-local `RunSnapshot`.**

Fields, independently derived from `Run`'s own aggregate shape (`src/empirical_platform/run/aggregate.py`), each justified on its own merits — not by restating M031's `CampaignSnapshot` reasoning:

**Included:**

- `identity: DomainIdentity[RunId]` — the caller's own request echoed back with confirmation the Run exists; needed to correlate the result with the request.
- `campaign_id: CampaignId` — the Run's owning-Campaign relationship; immutable for the lifetime of a Run (no mutator on `Run` ever changes `_campaign_id`); the minimal relationship fact a caller needs.
- `state: RunLifecycleState` — the Run's current lifecycle position; the minimal descriptive fact answering "what is this Run's status."

**Excluded, each independently justified:**

- `version` (`AggregateVersion`): write-side optimistic-concurrency metadata consumed only by `RunRepository.save(aggregate, *, expected_persisted_version=...)`. A retrieval-only caller has no legitimate use for it; exposing it invites an out-of-band write attempt bypassing the command-handler path (same reasoning independently re-derived in Section 8, Candidate B).
- `next_transition_sequence` (`TransitionSequence`): a pure write-side bookkeeping counter consumed only internally by `Run._transition()` to stamp the next `StateTransitionRecord`. It answers no question about the Run's current state.
- `transition_history` (`tuple[StateTransitionRecord, ...]`): an unbounded, growing audit trail carrying `actor`/`correlation_id`/`reason` governance metadata for every past lifecycle transition. Including it would make the result's size grow without bound over a Run's operational lifetime — a genuine scope-size risk this milestone's minimal-first discipline exists to avoid — and would expose internal audit fields through a boundary whose only proven purpose (Mission Statement) is validating pattern generalization, not delivering an audit view.
- `manifests` (`tuple[DatasetManifest, ...]`): unlike `transition_history`, this is genuine domain content (not audit metadata), so it is addressed independently rather than by the same reasoning. It is excluded because: (a) it is unbounded and grows with a Run's operational history, so including it would make "one retrieval result" open-ended in size; (b) how to represent `DatasetManifest` data across a query boundary (full objects, a summary, a count) is itself an independent, currently unevaluated design question, and the frozen scope explicitly forbids this milestone from introducing a projection or generic read-model decision (scope-freeze Section 13, Section 19); (c) no in-scope capability in the frozen scope requires manifest visibility — the Mission Statement's sole proof obligation (`QueryHandler`/`QueryEntryPoint` generalization) is fully discharged by the three included fields. Manifest exposure is deferred to a future, independently-scoped milestone (Section 30).

`RunSnapshot` is a `@dataclass(frozen=True, slots=True)` — immutable, no default values, exactly three fields, mirroring `CampaignSnapshot`'s dataclass posture (verified in `usecases/get_campaign.py`) because that posture (frozen, slots, no extra machinery) is independently the correct choice for any minimal read-value in this codebase, not because of blind mirroring.

---

## 10. Persisted-Version Decision

`persisted_version` is excluded from `RunSnapshot` (Section 9). `GetRunHandler` reads it from the `LoadedAggregate[Run]` returned by `RunRepository.get()` (it is present on the object) but never places it on the constructed `RunSnapshot`, exactly as `GetCampaignHandler` reads but never exposes it for Campaign (verified: `CampaignSnapshot.__slots__` contains no `persisted_version`, confirmed by the existing test `test_snapshot_contains_no_persisted_version`).

---

## 11. Run State/Manifest/History Representation

`manifests` and `transition_history` are loaded by `PostgresRunRepository.get()` as an unavoidable side effect of full aggregate reconstruction (Section 5) but are never read by `GetRunHandler` and never appear on `RunSnapshot`. This is a real, acknowledged cost (the repository does strictly more I/O than the query result needs) accepted because: `RunRepository.get()` is a frozen M020/M023 contract this milestone must not modify, and it has no partial-load variant. PostgreSQL evidence (Section 24) must still confirm this loading occurs correctly (regression coverage), even though its result is discarded.

---

## 12. Selected Architecture

One query type (`GetRunQuery`), one handler type (`GetRunHandler`), one result type (`RunSnapshot`), one module (`empirical_platform/usecases/get_run.py`), bound to the frozen `QueryEntryPoint` at test-construction time only. No new package, no new Protocol, no new collaborator type. This is structurally identical in shape (not content) to `usecases/get_campaign.py`.

---

## 13. Exact Query Contract

Module: `empirical_platform/usecases/get_run.py`

```python
@dataclass(frozen=True, slots=True)
class GetRunQuery:
    """Request to retrieve a Run by its full frozen identity."""

    identity: DomainIdentity[RunId]
```

- Exactly one field: `identity`.
- No defaults.
- Immutable (`frozen=True`), no extra attributes possible (`slots=True`).
- No validation beyond what `DomainIdentity[RunId]`'s own construction already performs.
- No listing/filter/pagination/Campaign/projection/transport/tracing fields of any kind.

---

## 14. Exact Handler Contract

```python
class GetRunHandler:
    """Retrieves a Run for one `GetRunQuery`."""

    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, query: GetRunQuery) -> RunSnapshot:
        """Load a Run by identity and return its read-side snapshot."""
        loaded = self._run_repository.get(query.identity)
        return RunSnapshot(
            identity=loaded.aggregate.identity,
            campaign_id=loaded.aggregate.campaign_id,
            state=loaded.aggregate.state,
        )
```

- Module path: `empirical_platform.usecases.get_run`.
- Sole constructor dependency: `run_repository: RunRepository` (Protocol, persistence-neutral). No `CampaignRepository`, no persistence adapter, no runtime/composition collaborator — every one of these is independently ruled out because the frozen `RunRepository.get()` contract alone supplies everything `RunSnapshot` needs (Section 5: no Campaign query is ever issued by `get()`, and this design does not add one).
- Structurally satisfies `QueryHandler[GetRunQuery, RunSnapshot]` (`_QueryT_contra`/`_QueryResultT_co` per `shared/contracts/query.py`) via `handle(self, query: GetRunQuery) -> RunSnapshot` — no inheritance, matching the Protocol's own documented structural-typing contract.

---

## 15. Exact Retrieval Sequence

1. `GetRunHandler.handle(query)` receives one `GetRunQuery`.
2. Calls `self._run_repository.get(query.identity)` exactly once, passing `query.identity` unchanged (the same object, not a copy or reconstruction).
3. Receives one `LoadedAggregate[Run]`.
4. Constructs exactly one new `RunSnapshot` by reading `loaded.aggregate.identity`, `loaded.aggregate.campaign_id`, and `loaded.aggregate.state`. `identity` and `campaign_id` are themselves frozen, immutable value objects, and `state` is an immutable enum member — referencing them directly (not deep-copying) is safe; no aliasing risk exists for the fields actually carried forward.
5. `manifests` and `transition_history`, though loaded internally by step 2 (Section 11), are never read; they are discarded when `loaded`/`aggregate` go out of scope at the end of `handle()`. No aliasing concern arises because they are never referenced by the returned `RunSnapshot`.
6. Returns the one `RunSnapshot`. No secondary repository call. No Campaign access. No retry. No caching. No application-level transaction orchestration (Section 20).

This sequence is the complete implementation obligation; implementation must not invent additional steps.

---

## 16. Return Semantics

Exactly one `RunSnapshot` per successful `handle()` call, satisfying `QueryHandler`'s `_QueryResultT_co` and `QueryEntryPoint[QueryT, QueryResultT]`'s `__call__` return type unchanged (the frozen `QueryEntryPoint` performs no wrapping — verified in `application/query.py`).

---

## 17. Not-Found Behavior

**Transparent propagation**, selected as the only option compatible with the already-frozen `QueryEntryPoint` contract, which documents that "its result or exception propagates to the caller unchanged" (`application/query.py`). `RunRepository.get()` raises `AggregateNotFound(aggregate_kind="Run", identity=identity)` (verified at `run_repository.py:149`); `GetRunHandler` performs no catch, no translation, no nullable-result wrapping, no result envelope. This is not a restatement of M031's choice for its own sake — Options B/C/D of Phase 8 (translation, nullable result, envelope) would each require `GetRunHandler` to intercept an exception that `QueryEntryPoint` is frozen to propagate unchanged, which this milestone has no authority to alter.

---

## 18. Error Semantics

Any other exception raised by `RunRepository.get()` — `InvalidPersistedAggregateState` (durable-state reconstruction failure) or an arbitrary lower-level failure — propagates unchanged through `GetRunHandler` and `QueryEntryPoint`, identically to `AggregateNotFound`. No new error hierarchy, no wrapper type, no generic query-error base class is introduced.

---

## 19. Validation Ownership

- **Query construction:** `GetRunQuery` performs no validation of its own; field typing is enforced only by the dataclass mechanism itself.
- **`RunId`/`DomainIdentity`:** already fully validated at construction time by their own frozen `__post_init__` checks (`Identifier.__post_init__` regex match, `DomainIdentity.__post_init__` isinstance checks) — a `GetRunQuery` cannot be constructed with an invalid identity in the first place.
- **`Run` aggregate:** no new validation; reconstruction validation is entirely owned by the frozen mapper/reconstruction path (M021/M023), unmodified here.
- **Repository:** all existing frozen validation (foreign-key, uniqueness, reconstruction) is unchanged.
- **Handler:** performs no independent validation of its own.
- **`RunSnapshot`:** as a `frozen=True, slots=True` dataclass with no `__post_init__`, it performs no validation beyond field assignment type-checking Python itself does not enforce at runtime for plain dataclasses — identical posture to `CampaignSnapshot`, which also defines no `__post_init__`.

No frozen identifier or repository validation is duplicated anywhere in this design.

---

## 20. Transaction Ownership

No application-level transaction orchestration. `RunRepository.get()` owns its own read transaction internally via `self._service.unit_of_work()` (verified in `PostgresRunRepository.get()`). This milestone requires exactly one repository call (Section 5), so there is no cross-repository operation and therefore no basis for using `run_composed()` — that primitive (M024/M025) exists specifically to atomically compose *multiple* repository operations sharing one `PostgresPersistenceService`, which does not apply to a single `get()` call. `run_composed()` is not introduced.

---

## 21. QueryEntryPoint Binding

Test-only direct construction, mirroring M031's exact pattern (`tests/unit/test_get_campaign_usecase.py::test_handler_is_invocable_through_query_entry_point`, `::test_handler_bound_at_construction_not_per_call`):

```python
handler = GetRunHandler(run_repository=run_repository)
entry_point = QueryEntryPoint(handler)
result = entry_point(GetRunQuery(identity=identity))
```

- The bound handler is invoked exactly once per call, receives the exact query object, and its result/exception propagates unchanged (frozen `QueryEntryPoint` invariant, unmodified).
- No registry, query bus, dispatcher, mediator, service locator, DI framework, or production composition root is introduced — consistent with every prior milestone's binding discipline (M030-M033).
- Structural `QueryHandler[GetRunQuery, RunSnapshot]` conformance is proven the same way M031 proved it for `GetCampaignHandler`: a typed assignment statement exercised under mypy (`test_typed_conformance_check` precedent), not runtime `isinstance` introspection (the Protocol is not `@runtime_checkable`).

---

## 22. Package and Dependency Boundaries

- **Module:** `src/empirical_platform/usecases/get_run.py` — the naming precedent already established (`create_campaign.py`, `get_campaign.py`, `prepare_campaign_for_authorization.py`, `create_run.py`) is `<verb>_<aggregate>.py`; `get_run.py` follows directly.
- **Imports required:** `dataclasses.dataclass`; `empirical_platform.identifiers.pairs.DomainIdentity`; `empirical_platform.identifiers.types.{RunId, CampaignId}`; `empirical_platform.run.repository.RunRepository`; `empirical_platform.campaign.lifecycle.RunLifecycleState` (verified: `RunLifecycleState` is defined in `campaign/lifecycle.py`, the same module `run/aggregate.py` itself imports it from — not re-exported by `run/__init__.py`).
- **Package-boundary check:** `ALLOWED["usecases"] = {"shared", "identifiers", "campaign", "run"}` (verified directly in `tools/check_architecture.py`) already grants both `"campaign"` (needed for the `RunLifecycleState` import, exactly as `get_campaign.py` already imports `CampaignLifecycleState` from the same top-level package) and `"run"` (needed for `RunRepository`, added by M033). **Zero new `ALLOWED` entry is required.**
- **Forbidden-prefix check:** `FORBIDDEN_IMPORT_PREFIXES["usecases"]` already blocks `empirical_platform.shared.persistence`, `sqlalchemy`, `psycopg`, `boto3` (verified directly). `get_run.py` imports none of these — identical posture to every existing `usecases` module.

---

## 23. Architecture-Checker Impact

**None.** No change to `ALLOWED`, `ALLOWED_EXACT_IMPORTS`, or `FORBIDDEN_IMPORT_PREFIXES` is required or authorized by this design — every import `get_run.py` needs is already permitted under grants M033 (and earlier) already established. This is narrower than every prior milestone in this chain (M030-M033 each required at least one new checker line; M034 requires none), confirming the scope document's own prediction (Section 21 of the corrected scope, Section 6 candidate-inventory "zero new architecture-checker change required").

Existing architecture-fixture test coverage (positive: `usecases` may import `run`/`campaign`; negative: `usecases` may not import persistence) already exercises the exact permission this module relies on — verified by inspecting `tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_postgres_runtime_import.py`, which already codifies the forbidden-persistence-import negative case for the whole `usecases` package. No new fixture is required; the real, non-fixture architecture-checker run over the actual new source file (Section 25.F) is itself the positive-case evidence, exactly as M031 relied on.

---

## 24. PostgreSQL Evidence Strategy

Mirrors `tests/integration/test_m031_get_campaign_usecase.py`'s established pattern, opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, against a freshly migrated real database (never mocked):

1. **Campaign seeding:** via the frozen M030 `CreateCampaignHandler`/`CreateCampaignCommand`, exactly reusing the existing fixture pattern already proven in `test_m030_create_campaign_usecase.py`/`test_m031_get_campaign_usecase.py`.
2. **Run seeding:** via the frozen M033 `CreateRunHandler`/`CreateRunCommand`, bound through a `CommandEntryPoint`, targeting the seeded Campaign's `governance_id` — reusing M033's own frozen creation vertical slice rather than inserting rows directly.
3. **Real `RunRepository` obtained externally:** `PostgresRunRepository(service)` constructed by the test's own fixtures (mirroring `campaign_repo` fixture in the M031 integration test) — `usecases` itself never constructs or imports a persistence adapter (Section 22/23).
4. **`QueryEntryPoint` binding:** `GetRunHandler(run_repository=...)` wrapped in `QueryEntryPoint`, invoked with a `GetRunQuery` carrying the identity returned by step 2.
5. **Golden-path assertions:** `snapshot.identity == identity`; `snapshot.campaign_id == CampaignId(<seeded governance id>)`; `snapshot.state is RunLifecycleState.CREATED` (the post-creation initial state, per `Run.__init__`).
6. **Manifests/history regression:** confirms `PostgresRunRepository.get()` still loads `run_manifest`/`run_transition` rows without error for a freshly created Run (which has none of either), proving the always-eager load path (Section 5/11) does not break even though its result is unused by this query.
7. **Missing-Run path:** construct a `DomainIdentity[RunId]` for a governance/runtime pair that was never persisted; assert `AggregateNotFound` propagates through `QueryEntryPoint` unchanged.
8. **No Campaign lookup:** assertable indirectly — the test never grants `GetRunHandler`/`PostgresRunRepository.get()` any `CampaignRepository`, and Section 5 already confirms the adapter's SQL never touches the `campaign` table.
9. **No schema/migration change:** the same `alembic upgrade head` fixture already used by every prior integration test suite is reused unmodified.
10. **M033 regression:** the Run-seeding step (2) itself is a live regression check that `CreateRunHandler` still functions correctly against the real schema.
11. **Existing repository regression:** `PostgresRunRepository.add()` (via step 2) and `.get()` (via step 4) are both exercised against the real database in the same test module, extending — not replacing — M023's own repository-level coverage.
12. **No production composition wiring:** as in M031's own `test_no_production_composition_machinery_is_required`, a companion test constructs `GetRunHandler` directly from the externally-obtained repository with no `FoundationRuntime`, no registry, no composition root of any kind.

---

## 25. Test Strategy

**A. Query tests** — exact single field (`identity`); object-identity preservation (`query.identity is <original identity object>`); immutability (`AttributeError` on assignment, `pytest.raises`); no extra fields (`__slots__ == ("identity",)`); no duplicated validation.

**B. Handler success** — sole dependency is `RunRepository` (a recording fake, mirroring `_RecordingCampaignRepository`); `get()` called exactly once; exact identity object passed through unchanged (`is` comparison); no `CampaignRepository` dependency exists to call; no second repository operation; `RunSnapshot` fields match the loaded aggregate's `identity`/`campaign_id`/`state` exactly; the source `Run` aggregate is not mutated by retrieval (`campaign_id`/`state`/version-equivalent check, mirroring `test_campaign_aggregate_is_not_mutated`); synchronous behavior.

**C. Not-found behavior** — `AggregateNotFound` raised by a failing fake repository propagates through `handle()` unchanged (`excinfo.value is exc`); no `RunSnapshot` conversion is attempted after a failed `get()`; no retry; no second `get()` call.

**D. Arbitrary failure behavior** — an arbitrary `RuntimeError` from the fake repository propagates unchanged; no wrapper; no retry; no second `get()`.

**E. QueryEntryPoint/Protocol** — mypy-checked structural `QueryHandler[GetRunQuery, RunSnapshot]` conformance (typed-assignment precedent, not runtime `isinstance`); exact query object reaches the handler through the entry point; handler invoked exactly once per `entry_point()` call; bound once at construction, reused across multiple invocations (mirroring `test_handler_bound_at_construction_not_per_call`); result/exception propagate through the entry point unchanged.

**F. Architecture** — real `python tools/check_architecture.py .` run over the actual new `get_run.py` source passes with zero change to `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES`; `usecases` may import `run`/`campaign` (already true); no persistence import appears in `get_run.py`; no concrete adapter or runtime import; no `external-review`/evidence import; `run`/`campaign` still cannot import `usecases` (unchanged, unaffected by this module); no checker permission widened.

**G. PostgreSQL** — the twelve items in Section 24.

No arbitrary coverage-percentage threshold is set; sufficiency is measured against the behavioral obligations enumerated in A-G, matching M031's own precedent (no numeric coverage gate was used there either).

---

## 26. Alternatives Considered

| Decision | Alternatives | Selected | Rejection reason (summary) |
| --- | --- | --- | --- |
| Query identity representation | B (split RunId + runtime field), C (raw strings + handler construction), D (governance-only) | A (full `DomainIdentity[RunId]`) | B adds an unnecessary translation/validation step; C would force an unused `RuntimeIdentifierGenerator` dependency or an unjustified pass-through string; D has no repository evidence of a resolution mechanism. |
| Result contract | A (raw `Run`), B (`LoadedAggregate[Run]`), D (existing frozen type) | C (new `RunSnapshot`) | A/B leak mutability (and B additionally leaks `persisted_version`); D — no existing type carries the needed shape. |
| Persisted-version exposure | Include on `RunSnapshot` | Excluded | Write-side metadata with no legitimate read-only use; risk of inviting out-of-band writes. |
| Snapshot fields | Include `manifests`/`transition_history`/`version`/`next_transition_sequence` | Excluded, all four | Unbounded size growth, audit-metadata exposure, and (for `manifests`) an independent unresolved representation question outside this milestone's authorized scope. |
| Handler dependency | Add `CampaignRepository` "for future-proofing" | `RunRepository` only | No Campaign data is ever read by `RunRepository.get()`; adding an unused dependency would be speculative and contradicts the frozen scope's explicit exclusion of Campaign lookup/join. |
| Error handling | Translate `AggregateNotFound`, return `None`, wrap in an envelope | Transparent propagation | The frozen `QueryEntryPoint` contract requires exceptions to propagate unchanged; none of the alternatives are compatible with that already-frozen invariant. |
| Validation ownership | Duplicate identifier/format validation in the handler | None duplicated | `RunId`/`DomainIdentity` already perform all necessary validation at construction; duplicating it would violate this project's established validation-ownership discipline (M030-M033). |
| Transaction ownership | Introduce `run_composed()` around the single `get()` call | No application transaction orchestration | Only one repository operation exists; `run_composed()` exists for multi-repository atomic composition, which does not apply here. |
| Module placement | A different package (e.g. a new `queries` package) | `empirical_platform.usecases.get_run` | Matches the exact precedent of every other concrete command/query module in this chain (M030-M033); no evidence justifies a new package. |
| Architecture-checker evidence | Add a new positive/negative fixture pair | None added | Existing `usecases` positive/negative fixtures already cover the exact permission this module relies on (import `run`/`campaign`, forbid persistence); the real source file itself is the positive-case proof, mirroring M031. |
| Production composition | Introduce composition-root wiring for `GetRunHandler` | Deferred (test-only direct construction) | No repeated-handler-need evidence exists after five consecutive milestones of trivial direct construction (unchanged reasoning from M030-M033). |

---

## 27. Rejected Alternatives

Restated for clarity from Section 26 with full reasoning: raw `Run` (Section 8-A); `LoadedAggregate[Run]` (Section 8-B); any existing frozen type as the result (Section 8-D); governance-ID-only query identity (Section 6-D); split-field query identity (Section 6-B); raw-string query identity (Section 6-C); `manifests`/`transition_history`/`version`/`next_transition_sequence` on the snapshot (Section 9); any error-translation or nullable-result not-found behavior (Section 17); any application-level transaction orchestration (Section 20); any composition-root, registry, dispatcher, mediator, or service-locator binding (Section 21); any new architecture-checker permission (Section 23).

---

## 28. In Scope

- Exactly one `GetRunQuery` and one `GetRunHandler`, in `empirical_platform.usecases.get_run`.
- Exactly one `RunRepository.get()` call per `handle()` invocation.
- The selected `RunSnapshot` result contract (Section 9).
- Transparent `AggregateNotFound`/arbitrary-error propagation (Sections 17-18).
- `QueryEntryPoint` compatibility, test-only direct construction (Section 21).
- Focused unit, contract, and PostgreSQL integration evidence (Sections 24-25).
- Zero architecture-checker change (Section 23).

---

## 29. Out of Scope

Run creation changes; Run lifecycle transition; Run save/update; a second Run query; Run listing/filtering/pagination; Campaign lookup or join; cross-aggregate enrichment; `EvidencePackage`/`Review` usecases; retry/backoff; composition root/registry/dispatcher/mediator/service locator/DI framework; transport/API layer; caching; audit integration; schema/migration changes; market-data/trading behavior; MILESTONE-035 work of any kind. (Restated from the frozen scope-freeze document Section 13; unchanged by this design.)

---

## 30. Deferred Work

- Exposing `manifests` (or a manifest summary/count) through a Run read model — a future, independently-scoped milestone, once its own representation question (full objects vs. summary vs. count) has been evaluated on its own merits.
- Exposing `transition_history` (or an audit view) — a future, independently-scoped milestone, if a genuine caller need is ever evidenced.
- Run lifecycle-transition command (M032's role, for Run) — unchanged from the frozen scope's own deferral.
- `EvidencePackage`/`Review` creation — unchanged from the frozen scope's own deferral.
- Retry-on-`OptimisticConcurrencyConflict` policy — unchanged.
- Any composition-root abstraction beyond direct binding — unchanged.
- MILESTONE-035 and beyond.

---

## 31. Risks

- **Aggregate mutability leakage:** mitigated by rejecting Candidates A/B in Section 8; `RunSnapshot` exposes no mutating method and is itself immutable.
- **Persistence metadata leakage:** mitigated by excluding `persisted_version` (Section 10).
- **Snapshot drift:** `RunSnapshot`'s three fields are read directly from the just-loaded `loaded.aggregate` inside `handle()`, not cached or computed elsewhere — no drift window exists within a single call.
- **Omission of important Run state:** the exclusion of `manifests`/`transition_history` is a deliberate, independently justified narrowing (Section 9), not an oversight; it is recorded explicitly as deferred work (Section 30), not silently dropped.
- **Manifests/history aliasing:** none — neither is ever referenced by `RunSnapshot` or returned to the caller (Section 15, step 5); the objects are discarded with the local `loaded`/`aggregate` variables.
- **Result-type symmetry pressure from M031:** actively guarded against — Section 9's exclusions for `manifests` are independently derived from `Run`'s own shape (Campaign has no equivalent field), not copied from `CampaignSnapshot`'s reasoning, satisfying the frozen scope's own risk mitigation instruction (scope-freeze Section 19, "Return-shape symmetry pressure").
- **Architecture-test duplication:** avoided — no new fixture is added; existing `usecases` fixtures already cover the relevant permission (Section 23).
- **Generic read-model pressure:** avoided — `RunSnapshot` is a single, narrow, milestone-local type with no shared base, no generic envelope, no projection abstraction.
- **Future query patterns copying M034 without independent review:** flagged explicitly here as a standing risk for whichever milestone next queries `EvidencePackage` or `Review` — that milestone must independently re-derive its own result contract, not copy this one's field list by default.
- **Production composition deferral:** unchanged risk profile from M030-M033; accepted per the same unmet-repeated-need evidence bar.
- **M035 leakage:** none — this design introduces no capability beyond one Run retrieval query; no M035 material is referenced or anticipated.

---

## 32. Cross-Milestone Compatibility

- Fully compatible with frozen `RunRepository`/`PostgresRunRepository`/`Run`/`QueryHandler`/`QueryEntryPoint` (M020, M023, M028, M029) — no signature or behavior of any of these is touched.
- Fully compatible with M033's `CreateRunCommand`/`CreateRunHandler` — used unmodified as PostgreSQL-evidence seeding (Section 24), proving no regression.
- Fully compatible with M031's `GetCampaignQuery`/`GetCampaignHandler`/`CampaignSnapshot` — no shared base, import, or coupling is introduced between the two; the structural similarity is a design choice, not a code dependency.
- No change to `ALLOWED`/`ALLOWED_EXACT_IMPORTS`/`FORBIDDEN_IMPORT_PREFIXES` in `tools/check_architecture.py`.

---

## 33. Acceptance Gate

This design is ready for independent review when:

- Every open question the scope-freeze document (Section 20) enumerated has an explicit, justified answer above.
- No decision expands the frozen scope's In-Scope Capability (listing, filtering, pagination, Campaign join, cross-aggregate enrichment, transport serialization, generic read-model/projection framework all remain absent).
- Every alternative considered has a specific, evidence-based rejection reason (Section 26-27), not a generic dismissal.
- The design is implementable without requiring the implementer to make any further load-bearing architectural decision.

---

## 34. Hostile Self-Review

Attacked directly against the Phase 20 attack list:

- **Governance-ID-only lookup:** absent — `GetRunQuery` carries full `DomainIdentity[RunId]` (Section 7); no resolution-by-governance-id-alone capability is introduced.
- **Identity reconstruction ambiguity:** absent — the query's identity is passed to `RunRepository.get()` as the exact same object, never reconstructed (Section 15, step 2).
- **More than one `get()`:** absent — exactly one call per `handle()` invocation (Section 15, step 2); no retry, no secondary lookup.
- **Campaign lookup:** absent — `RunRepository.get()` never queries `campaign` (Section 5); `GetRunHandler` has no `CampaignRepository` dependency (Section 14).
- **Raw aggregate leakage:** absent — `Run` is rejected as the result type (Section 8-A); `RunSnapshot` carries no aggregate reference.
- **`LoadedAggregate`/persistence leakage:** absent — `LoadedAggregate[Run]` is rejected as the result type (Section 8-B); `persisted_version` is excluded (Section 10).
- **Incomplete snapshot fields:** the three included fields (`identity`, `campaign_id`, `state`) fully discharge the Mission Statement's proof obligation; every exclusion is independently justified (Section 9), not an oversight.
- **Dropped persisted version without justification:** justified explicitly (Section 10, Section 9 "Excluded" list).
- **Manifests/history aliasing:** addressed explicitly (Section 15 step 5, Section 31) — neither is ever referenced by the result.
- **Not-found translation ambiguity:** resolved explicitly — transparent propagation only, justified by the frozen `QueryEntryPoint` contract itself (Section 17), no alternative left open.
- **Result wrapper creep:** absent — `RunSnapshot` is returned directly, no envelope, no `Result`/`Either` wrapper.
- **Listing/filtering/projection leakage:** absent — single-identity retrieval only; no such parameter exists on `GetRunQuery` (Section 13).
- **Generic read-model abstraction:** absent — `RunSnapshot` has no shared base class, no generic type parameter, no registry.
- **Checker mismatch:** verified directly against live `tools/check_architecture.py` source (Section 22-23), not asserted from memory; confirmed zero new permission required.
- **Production composition leakage:** absent — test-only direct construction only (Section 21); no `FoundationRuntime`/registry reference anywhere in this design.
- **M035 leakage:** absent — no M035 capability, terminology, or forward reference appears anywhere in this document.

No load-bearing ambiguity remains open.

---

## 35. Final Status

**CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW.** Not approved. Not frozen. Does not authorize implementation.

**Next permitted action:** MILESTONE-034 INDEPENDENT DESIGN REVIEW.
