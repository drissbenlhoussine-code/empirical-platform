# MILESTONE-031 - Concrete Application Query Vertical Slice Design

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW**

This document is a design candidate. It has not been reviewed, approved, or frozen. No implementation of MILESTONE-031 is authorized by this document.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative HEAD at design | `87d4d047f535624a9de413b4c33fb0c10466c369` |
| Frozen scope commit | `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848` |
| Scope freeze commit | `b31b664e9395aa0a988ccd1aecc21d6b06436d39` |

---

## 3. Frozen Authority Chain

| Milestone | Status | Delivered |
| --- | --- | --- |
| M020 | APPROVED_AND_FROZEN | `Campaign` aggregate, `CampaignRepository` Protocol (`get`, `add`, `save`), `LoadedAggregate[AggregateT]`, `AggregateNotFound` |
| M023 | APPROVED_AND_FROZEN | Concrete PostgreSQL `Campaign` repository adapter |
| M025 | APPROVED_AND_FROZEN | Repository runtime composition |
| M028 | APPROVED_AND_FROZEN | `QueryHandler[_QueryT_contra, _QueryResultT_co]` Protocol |
| M029 | APPROVED_AND_FROZEN | `QueryEntryPoint[QueryT, QueryResultT]` |
| M030 | APPROVED_AND_FROZEN (scope, design, implementation) | `CreateCampaignCommand`/`CreateCampaignHandler` in `empirical_platform.usecases`; the `usecases` package's architecture-checker rules |
| M031 scope | APPROVED_AND_FROZEN | Concrete Application Query Vertical Slice — Campaign retrieval by identity (this design's authority) |

**Exact frozen contracts verified by direct source inspection (not summary):**

```python
# empirical_platform.shared.contracts.repository
@dataclass(frozen=True, slots=True)
class LoadedAggregate[AggregateT]:
    aggregate: AggregateT
    persisted_version: AggregateVersion

class AggregateNotFound(RepositoryContractError):
    def __init__(self, *, aggregate_kind: str, identity: object) -> None: ...

# empirical_platform.campaign.repository
class CampaignRepository(Protocol):
    def get(self, identity: DomainIdentity[CampaignId]) -> LoadedAggregate[Campaign]: ...
    def add(self, aggregate: Campaign) -> SaveResult: ...
    def save(self, aggregate: Campaign, *, expected_persisted_version: AggregateVersion) -> SaveResult: ...

# empirical_platform.shared.contracts.query
class QueryHandler(Protocol[_QueryT_contra, _QueryResultT_co]):
    def handle(self, query: _QueryT_contra) -> _QueryResultT_co: ...

# empirical_platform.application.query
class QueryEntryPoint[QueryT, QueryResultT]:
    def __init__(self, handler: QueryHandler[QueryT, QueryResultT]) -> None: ...
    def __call__(self, query: QueryT) -> QueryResultT: ...

# empirical_platform.identifiers.pairs
@dataclass(frozen=True, slots=True)
class DomainIdentity[GovernanceIdentifierT: Identifier]:
    governance_id: GovernanceIdentifierT
    runtime_id: RuntimeIdentifier

# empirical_platform.usecases.create_campaign (M030, frozen)
@dataclass(frozen=True, slots=True)
class CreateCampaignCommand:
    campaign_governance_id: str
    scope_statement: str

class CreateCampaignHandler:
    __slots__ = ("_campaign_repository", "_runtime_identifier_generator")
    def __init__(self, *, campaign_repository: CampaignRepository,
                 runtime_identifier_generator: RuntimeIdentifierGenerator) -> None: ...
    def handle(self, command: CreateCampaignCommand) -> DomainIdentity[CampaignId]: ...
```

`tools/check_architecture.py`'s current, verified `usecases` rules:

```python
ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}
FORBIDDEN_IMPORT_PREFIXES["usecases"] = (
    "empirical_platform.shared.persistence", "sqlalchemy", "psycopg", "boto3",
)
```

---

## 4. Architectural Context

M030 proved the write side of the application invocation boundary. The read side (`QueryHandler`, `QueryEntryPoint`) has been frozen since M028/M029 but exercised only by mock/fake handlers. A Campaign created via M030's slice can currently be read back only by reaching around the application boundary and calling `CampaignRepository.get()` directly. This design closes that gap with the smallest coherent read-side capability: retrieval-by-identity for the same aggregate M030 already used.

---

## 5. Selected Architecture

One concrete query and one concrete handler, in the same `empirical_platform.usecases` package M030 already established, in a new module dedicated to this one use case — mirroring M030's own file-per-use-case precedent exactly. The handler depends on `CampaignRepository` only (no second collaborator is needed, unlike the write side's need for `RuntimeIdentifierGenerator`, because retrieval creates no new identity). No architecture-checker change is required — every dependency this query/handler needs is already covered by the existing `usecases` `ALLOWED` entry.

---

## 6. Exact Query Contract

**Type name:** `GetCampaignQuery`

**Module:** `src/empirical_platform/usecases/get_campaign.py`

**Shape:**

```python
@dataclass(frozen=True, slots=True)
class GetCampaignQuery:
    identity: DomainIdentity[CampaignId]
```

**Field:** exactly one field, `identity: DomainIdentity[CampaignId]` — the already-frozen, already-validated identity type `CampaignRepository.get()` requires verbatim. No decomposition into raw governance-id/runtime-id strings, no reconstruction logic, no new identity-resolution capability of any kind (Design Question 1, resolved: **carries the full `DomainIdentity[CampaignId]` as a single existing frozen object**, not two primitive fields).

---

## 7. Exact Handler Contract

**Type name:** `GetCampaignHandler`

**Module:** same file as the query, `src/empirical_platform/usecases/get_campaign.py` — mirrors M030's one-file-per-use-case convention exactly.

**Shape:**

```python
class GetCampaignHandler:
    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, query: GetCampaignQuery) -> CampaignSnapshot:
        loaded = self._campaign_repository.get(query.identity)
        return CampaignSnapshot(
            identity=loaded.aggregate.identity,
            scope_statement=loaded.aggregate.scope_statement,
            state=loaded.aggregate.state,
        )
```

**Constructor dependency:** `campaign_repository: CampaignRepository` only — constructor injection, exactly matching M030's precedent, with one fewer collaborator (no `RuntimeIdentifierGenerator`, since nothing is generated on a read).

**`QueryHandler` generic relationship:** `GetCampaignHandler` structurally satisfies `QueryHandler[GetCampaignQuery, CampaignSnapshot]` — no inheritance, no base class, exactly matching `CreateCampaignHandler`'s relationship to `CommandHandler`.

---

## 8. Identity Semantics

The query's `identity` field is the caller-supplied `DomainIdentity[CampaignId]` a caller already possesses — most naturally, the exact value `CreateCampaignHandler.handle()` already returns, or the exact value a prior `GetCampaignHandler` invocation's `CampaignSnapshot.identity` already carries. The handler performs **zero** identity construction, parsing, or validation of its own: `DomainIdentity.__post_init__` and `Identifier.__post_init__` (both already frozen, M020) are the only validation that ever runs, and only if a caller constructs a malformed `DomainIdentity` themselves — the handler never touches raw strings.

This is a deliberate departure from M030's raw-string-carrying command shape, justified by the difference in what each side needs: creation must *construct* an identity that does not yet exist (raw input is unavoidable), while retrieval *consumes* an identity that must already exist and has, in every realistic case, already passed through `DomainIdentity`'s frozen validation once (at creation time or at a prior read). Reconstructing it from raw strings a second time would be redundant validation logic this design explicitly declines to introduce.

---

## 9. Return Contract

**Selected: a new narrow immutable read value — `CampaignSnapshot`.**

```python
@dataclass(frozen=True, slots=True)
class CampaignSnapshot:
    identity: DomainIdentity[CampaignId]
    scope_statement: CampaignScopeStatement
    state: CampaignLifecycleState
```

Composed entirely of already-frozen types (`DomainIdentity`, `CampaignId`, `CampaignScopeStatement`, `CampaignLifecycleState`) — no new primitive value type is introduced, only a new immutable carrier grouping three existing types. Not generic, not reusable across queries, not a framework: one concrete dataclass for one concrete query, matching the same non-generic-value-object style already used throughout this codebase (`SaveResult`, `LoadedAggregate` at the repository layer; `CampaignScopeStatement` at the domain layer).

### Alternatives Considered (Design Question 4)

| Option | Advantages | Disadvantages | Selected/Rejected |
| --- | --- | --- | --- |
| **A. Return `Campaign` aggregate directly** | Zero new types; the aggregate is the domain truth | `Campaign` is a mutable class with unrestricted lifecycle-transition methods (`activate()`, `suspend()`, etc.); returning it through a *read* boundary lets any caller mutate in-memory state without going through any command handler — a genuine CQRS violation, not merely a style preference | **Rejected** — aggregate leakage risk |
| **B. Return `LoadedAggregate[Campaign]` directly (zero new code, transparent pass-through)** | Simplest possible implementation; exact fidelity to what `CampaignRepository.get()` already returns; zero new types | Same mutability leakage as Option A (still wraps the same mutable `Campaign`); additionally exposes `persisted_version: AggregateVersion` — write-side optimistic-concurrency metadata — through a read-only boundary, blurring CQRS separation for a value this milestone's scope gives callers no sanctioned use for | **Rejected** — aggregate leakage plus write-metadata leakage |
| **C. Return a new narrow immutable read value** | No mutable aggregate exposed; no write-side metadata leakage; composed entirely of already-frozen types; mirrors M030's own precedent of returning the minimal useful slice (`campaign.identity`, not the full `SaveResult`) rather than the raw underlying type | Introduces one new type this design must freeze | **Selected** |
| **D. Another existing frozen type** | — | No other existing frozen type carries exactly `identity + scope_statement + state` without either more (leaking `Campaign`/`LoadedAggregate`) or less (no single existing type is this precise) | **Rejected** — no candidate exists |

**Why exactly these three fields, no more, no fewer:** `identity` and `scope_statement` are exactly the two fields `CreateCampaignCommand` accepts as input (module 6), creating a coherent round-trip: what a caller writes is what a caller reads back. `state` is added because a caller retrieving "the Campaign" without knowing its lifecycle state receives a result of limited practical use, and `CampaignLifecycleState` is a simple, already-frozen, immutable enum with no leakage risk of its own. `version`, `next_transition_sequence`, and `transition_history` are deliberately excluded: MILESTONE-030's own precedent already established that this vertical-slice discipline returns the minimal useful information, not the full aggregate shape, and none of these three fields has any use this milestone's frozen scope authorizes.

---

## 10. Repository Interaction

**Exact sequence:**

```
1. handler.handle(query) receives GetCampaignQuery
2. loaded = self._campaign_repository.get(query.identity)   # exactly one repository call
3. return CampaignSnapshot(
       identity=loaded.aggregate.identity,
       scope_statement=loaded.aggregate.scope_statement,
       state=loaded.aggregate.state,
   )
```

- **Exact repository method called:** `get()`, exactly once.
- **No pre-read, no secondary lookup, no other repository method** (`add()`, `save()` are never called by this handler).
- **`LoadedAggregate.persisted_version` is read from the repository result but intentionally not carried into `CampaignSnapshot`** — a deliberate exclusion (Section 9), not an oversight or accidental data loss.

---

## 11. Not-Found and Error Semantics

**Selected: fully transparent propagation — no translation, no wrapping, no query-specific error type.**

`AggregateNotFound` (raised by `CampaignRepository.get()` when no persisted Campaign matches `query.identity`) propagates through `GetCampaignHandler` and through the frozen `QueryEntryPoint` completely unchanged — the handler contains zero `try`/`except` blocks, exactly matching M030's write-side precedent and M029's frozen transparent-boundary invariant. Any other exception `get()` can raise (e.g. `InvalidPersistedAggregateState`, verified present in the frozen M020 error taxonomy) propagates identically.

### Alternatives Considered (Design Question 6)

| Option | Advantages | Disadvantages | Selected/Rejected |
| --- | --- | --- | --- |
| **Transparent propagation** | Matches M029's frozen invariant and M030's own precedent exactly; zero new code; callers see the exact, already-documented `AggregateNotFound` | None material | **Selected** |
| Translation to a query-specific error type | Could give callers a read-side-specific vocabulary | Introduces a new exception type this scope does not authorize; duplicates information `AggregateNotFound` already carries; M030's design freeze explicitly rejected the equivalent write-side pattern for the same reasons | **Rejected** |
| Nullable return (`CampaignSnapshot \| None`) | Avoids exceptions for an "expected" outcome | Changes the handler's return type contract conditionally, complicating every caller with a branch; diverges from how every other frozen repository-adjacent boundary in this codebase (M020-M030) already signals not-found via exception, not `None` | **Rejected** — inconsistent with established precedent |
| Result/outcome wrapper (e.g. `Result[CampaignSnapshot, NotFoundError]`) | Explicit success/failure typing | Introduces a generic result-wrapper *framework* this milestone's scope explicitly excludes; no precedent anywhere in M020-M030 | **Rejected** — explicitly excluded by scope |

---

## 12. Validation Ownership

- **Query construction:** no validation of its own. `GetCampaignQuery` is a plain carrier for an already-validated `DomainIdentity[CampaignId]`; if a caller supplies a malformed `DomainIdentity`, `DomainIdentity.__post_init__`/`Identifier.__post_init__` (both already frozen) reject it before the query is even constructed with a meaningful value.
- **Handler:** no validation of its own — translation and orchestration only (read, translate result, return).
- **Frozen identity/value types:** own all format/type validation, exactly as they already do (M020, unmodified).
- **Repository:** owns existence validation (`AggregateNotFound`) and persisted-state validation (`InvalidPersistedAggregateState`), exactly as already frozen (M020/M023, unmodified).

No validation is duplicated anywhere in this design.

---

## 13. QueryEntryPoint Binding

- The concrete handler's conformance to `QueryHandler[GetCampaignQuery, CampaignSnapshot]` is proven by a mypy-checked typed assignment (mirroring M030's `test_typed_conformance_check` pattern) and a runtime structural-shape check (mirroring M030's contract-test pattern) — not by inheritance, not by `@runtime_checkable`.
- `QueryEntryPoint(GetCampaignHandler(...))` is constructed directly, in tests only — exactly matching M030's `CommandEntryPoint` usage. No production composition code is required or authorized.
- No registry, dispatcher, query bus, service locator, or dependency-injection framework of any kind.

---

## 14. Package and Dependency Boundaries

**New module:** `src/empirical_platform/usecases/get_campaign.py` — within the already-authorized `empirical_platform.usecases` package.

**Imports required, verified against frozen source:**

- `empirical_platform.campaign.aggregate` (`CampaignScopeStatement`) — top-level `campaign`, already in `ALLOWED["usecases"]`.
- `empirical_platform.campaign.lifecycle` (`CampaignLifecycleState`) — same top-level `campaign` package.
- `empirical_platform.campaign.repository` (`CampaignRepository`) — same top-level `campaign` package.
- `empirical_platform.identifiers.pairs` (`DomainIdentity`) — top-level `identifiers`, already in `ALLOWED["usecases"]`.
- `empirical_platform.identifiers.types` (`CampaignId`) — same top-level `identifiers` package.

Every required import resolves to a top-level package already present in `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}`. No import of `shared.persistence`, no concrete Postgres adapter, no `sqlalchemy`/`psycopg`/`boto3` — matching `FORBIDDEN_IMPORT_PREFIXES["usecases"]` exactly, with zero new risk beyond what M030 already closed.

---

## 15. Architecture-Checker Impact

**Selected: no checker change of any kind.**

Verified directly: every import this query/handler needs already resolves under the existing `ALLOWED["usecases"]`/`FORBIDDEN_IMPORT_PREFIXES["usecases"]` pair M030 established. No new fixture is required for a *new* rule, because no new rule exists — the existing `test_current_source_tree_respects_boundaries` check alone is sufficient to prove the real implementation stays within the already-frozen boundary once implemented.

### Alternatives Considered (Design Question 9)

| Option | Advantages | Disadvantages | Selected/Rejected |
| --- | --- | --- | --- |
| **No checker change** | Matches "avoid speculative/unnecessary change" discipline; every needed import is already covered | None — verified by direct import-graph inspection | **Selected** |
| Narrow addition (e.g. an exact-import allowance) | Would future-proof against an import not yet needed | No unmet import exists to justify one; would be speculative | **Rejected** — no evidenced need |
| New fixture only, no rule change | Could demonstrate the existing rule also covers this module | Redundant with the existing `test_current_source_tree_respects_boundaries` check, which already covers every file under `src/`, including this future one | **Rejected** — no incremental value |

---

## 16. Transaction and Runtime Non-Ownership

- No transaction orchestration in the query handler; no `run_composed()` (a single-repository read needs no atomic multi-operation primitive).
- No retries.
- No exception suppression — every exception propagates unchanged (Section 11).
- No payload logging of any kind.
- No mutable global state; the handler's only state is its constructor-injected `_campaign_repository` reference.
- No runtime Protocol introspection (`isinstance`, `@runtime_checkable`) — conformance is structural and mypy-checked only, exactly matching M030.
- No dynamic handler discovery, registry, or dispatcher.
- No infrastructure import from `usecases` (Section 14).
- `LoadedAggregate.persisted_version` is read but not exposed (Section 9/10) — a deliberate CQRS-separation choice, not an accidental omission.

---

## 17. Test Strategy

**A. Query construction (unit):**
- A valid, well-formed `DomainIdentity[CampaignId]` is accepted.
- The identity object is preserved unchanged (identity-preserving, not reconstructed) inside the query.
- No unintended validation occurs at the query's own construction beyond what `DomainIdentity`/`Identifier` already enforce.

**B. Handler behavior (unit, deterministic recording/failing fakes — no mocks):**
- `CampaignRepository.get()` is called exactly once.
- The exact `query.identity` object is passed to `get()` unchanged (identity-preserving, verified via object identity, not equality).
- No `add()`/`save()` call occurs.
- The returned `CampaignSnapshot` carries exactly `identity`, `scope_statement`, and `state` sourced from the loaded aggregate, unchanged.
- `AggregateNotFound` from `get()` propagates with exact exception-instance identity preserved.
- An arbitrary exception from `get()` (not just `AggregateNotFound`) propagates with exact exception-instance identity preserved.
- The handler's execution is synchronous (no `async`/`await` anywhere).

**C. Contract test (Protocol conformance):**
- `GetCampaignHandler` structurally satisfies `QueryHandler[GetCampaignQuery, CampaignSnapshot]` (mypy-checked typed assignment).
- `handle()` has the frozen single-parameter shape.
- No inheritance from any `QueryHandler` base class.

**D. `QueryEntryPoint` compatibility (unit):**
- `QueryEntryPoint(GetCampaignHandler(...))` invokes the handler exactly once per call.
- The exact query object is passed unchanged.
- The exact result and exact exception-instance propagate unchanged through the entry point.

**E. Architecture (existing tests, no new fixture needed per Section 15):**
- `test_current_source_tree_respects_boundaries` continues to pass once the new module exists, proving it stays within the already-frozen `usecases` boundary — no new fixture required.

**F. PostgreSQL integration (real database, opt-in, mirroring M030's established fixture pattern exactly):**
- A Campaign is first persisted using the existing M030 `CreateCampaignHandler` (or the equivalent direct `CampaignRepository.add()` call the existing M023 integration fixtures already use) — no new persistence path is introduced for this purpose.
- `GetCampaignHandler`, constructed with the same externally-obtained real `PostgresCampaignRepository` M030's own integration tests already use, retrieves it through a directly-constructed `QueryEntryPoint`.
- The returned `CampaignSnapshot` is independently verified against the exact data that was persisted.
- Retrieval with a well-formed but never-persisted identity reproduces `AggregateNotFound`.
- No migration or schema change is required or introduced.
- The existing M023/M030 integration regression suite remains green, run unmodified alongside the new tests.

No arbitrary coverage percentage is introduced; the project's existing repository-wide coverage gate applies unchanged.

---

## 18. PostgreSQL Evidence Strategy

The integration test module reuses the exact fixture pattern `tests/integration/test_m030_create_campaign_usecase.py` already established (opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, the same disposable `postgres:17` container via `infra/local/compose.yaml`, the same Alembic-migrated schema, the same externally-obtained `PostgresCampaignRepository` fixture). No new composition wiring, no new runtime container, no new schema. The only new elements are the test module itself and its use of `GetCampaignHandler`/`GetCampaignQuery`/`CampaignSnapshot`.

---

## 19. Alternatives Considered (Summary Across All Load-Bearing Decisions)

| Decision | Alternatives Considered | Selected |
| --- | --- | --- |
| Query identity representation | Full `DomainIdentity[CampaignId]` object vs. decomposed raw governance/runtime strings | Full `DomainIdentity[CampaignId]` object — avoids reconstructing a new identity-resolution path |
| Handler placement | Same `usecases` package (new module) vs. a new package vs. co-located in `create_campaign.py` | Same package, new module — matches M030's one-file-per-use-case precedent, avoids bloating the existing module |
| Dependency injection | Constructor injection of `CampaignRepository` only vs. also injecting something for not-found handling | Constructor injection, `CampaignRepository` only — no second collaborator is needed for a pure read |
| Return shape | `Campaign` / `LoadedAggregate[Campaign]` / new narrow value / other existing type | New narrow immutable value (`CampaignSnapshot`) — see Section 9 |
| Not-found behavior | Transparent propagation / translation / nullable return / result wrapper | Transparent propagation — see Section 11 |
| Repository metadata handling | Expose `persisted_version` / discard it | Discard it — avoids write-side metadata leaking into the read side |
| Architecture-checker change | No change / narrow addition / fixture-only | No change — every needed import is already covered |
| Production composition | Build a composition-root helper now / defer entirely | Defer entirely — no evidenced repeated-handler need yet (unchanged from M030's own deferral) |

---

## 20. Rejected Alternatives (Consolidated Reasons)

- **Returning `Campaign` or `LoadedAggregate[Campaign]` directly** — rejected for aggregate-mutability leakage and (for `LoadedAggregate`) write-side metadata leakage through a read-only boundary.
- **Decomposed raw-string identity fields** — rejected as an unnecessary new identity-reconstruction path when the exact needed type already exists and is already produced by M030's own command.
- **Not-found translation, nullable return, or result-wrapper** — each rejected as either introducing an unauthorized new type/framework or diverging from this codebase's established not-found signaling convention.
- **Any architecture-checker change** — rejected as unnecessary; no unmet import exists.
- **Production composition-root code** — rejected as premature; unchanged from M030's own explicit deferral pending evidence of repeated-handler need.

---

## 21. In Scope

- One Campaign retrieval-by-identity query (`GetCampaignQuery`).
- One query handler (`GetCampaignHandler`).
- One new narrow immutable return value (`CampaignSnapshot`).
- Use of the frozen `QueryHandler`/`QueryEntryPoint` exactly as they exist.
- Use of the frozen `CampaignRepository.get()` exactly as it exists.
- Focused unit, contract, and integration test evidence, mirroring M030's established patterns.
- No architecture-checker change (Section 15).

---

## 22. Out of Scope

Listing; filtering; search; pagination; sorting; any projection or generic read-model framework; caching; authorization; any transport layer (HTTP, CLI, workers, queues); any query registry, query bus, mediator, dispatcher, or service locator; any dependency-injection framework; any composition root; any `Run`/`EvidencePackage`/`Review` query or command; any MILESTONE-032 work.

---

## 23. Deferred Work

- Any query for `Run`, `EvidencePackage`, or `Review`.
- Any Campaign query beyond retrieval-by-identity.
- Any composition-root abstraction beyond direct binding, pending evidence of genuine repeated-handler need (unchanged from M030).
- Retry-on-optimistic-concurrency-conflict policy (still blocked on a `save()`-based command that does not yet exist).
- Any transport/entrypoint adapter.
- MILESTONE-032 and beyond.

---

## 24. Risks

| Risk | Mitigation |
| --- | --- |
| Aggregate leakage (returning a mutable `Campaign` through a read boundary) | Resolved by design: `CampaignSnapshot` never carries the aggregate itself, only immutable value-typed fields (Section 9) |
| Read-model overengineering | `CampaignSnapshot` is one concrete, non-generic, non-reusable dataclass — not a framework; explicitly justified field-by-field (Section 9) |
| Loss of repository revision metadata | Documented as a deliberate exclusion, not an oversight (Sections 9-10); no current scope authorizes exposing `persisted_version` through a query |
| Identity misuse (governance-id-only lookup) | Explicitly rejected in Section 6/8; the query carries the full `DomainIdentity[CampaignId]`, matching `get()`'s exact frozen requirement |
| Query/write symmetry overreach (copying M030's choices without re-justifying them for the read side) | Every load-bearing decision in this design is independently re-derived and justified for the read side, not merely restated from M030 (Sections 6-11 each carry their own alternatives analysis) |
| Architecture-rule drift | No checker change is proposed; verified directly against the current, unmodified `tools/check_architecture.py` |
| Test-only `QueryEntryPoint` binding becoming accidental precedent for a permanent pattern | Consistent with M030's own explicit position: this is a precedent to evaluate later with more evidence, not a framework to enforce (unchanged) |
| Governance risk of treating this as a generic query pattern for future milestones | This design explicitly states (Section 19-20) that its choices are specific to this one query, not a generalized template; future milestones must independently re-derive their own decisions, exactly as this design did relative to M030 |

---

## 25. Cross-Milestone Compatibility

- Uses M020's `CampaignRepository.get()` exactly as frozen — no signature change, no reinterpretation.
- Uses M023's concrete PostgreSQL adapter exactly as frozen.
- Uses M028's `QueryHandler` Protocol exactly as frozen — structural conformance only.
- Uses M029's `QueryEntryPoint` exactly as frozen — direct construction, no modification.
- Coexists with M030's `CreateCampaignCommand`/`CreateCampaignHandler` in the same package without modifying either; the new module is additive only.
- Does not modify `tools/check_architecture.py`.
- Does not modify any M020-M030 governance document.

---

## 26. Acceptance Gate

This design is complete and ready for independent review when:

- [x] Every design question (Phase 2, items 1-10) is answered with justification, not left open.
- [x] Every load-bearing decision documents alternatives, advantages, disadvantages, and a rejection/selection reason.
- [x] The exact query type, handler type, module placement, field names/types, constructor dependencies, return type, repository call sequence, not-found behavior, validation ownership, `QueryEntryPoint` usage, architecture-checker impact, and test obligations are all frozen — nothing is left for implementation to invent.
- [x] No M020-M030 frozen contract is reopened.
- [x] No prohibited capability (listing, filtering, pagination, caching, transport, registry, dispatcher, mediator, service locator, DI framework, composition root, generic read-model framework) appears anywhere in this design.

---

## 27. Hostile Self-Review

Adversarial sweep performed against this document's own content before finalizing:

| Attack | Finding |
| --- | --- |
| Unresolved return type | Not found — `CampaignSnapshot` is fully specified with exact fields and types (Section 9) |
| Aggregate leakage | Not found — `Campaign` is never returned; only value-typed fields are carried (Section 9) |
| Accidental read-model framework | Not found — `CampaignSnapshot` is one concrete, non-generic type; no base class, no generic `QueryResult[T]` abstraction |
| Hidden DTO/serialization layer | Not found — no serialization code, no transport-facing shape, anywhere in this design |
| Governance-ID-only lookup despite full identity requirement | Not found — Section 6/8 explicitly select the full `DomainIdentity[CampaignId]` |
| Runtime-ID regeneration | Not found — no `RuntimeIdentifierGenerator` dependency exists anywhere in this design; nothing is generated on a read |
| Extra repository calls | Not found — exactly one `get()` call, verified in Section 10's exact sequence |
| Loss of `LoadedAggregate` revision metadata | Present, but explicitly deliberate and justified (Sections 9-10, 24) — not a silent loss |
| Not-found translation without authority | Not found — Section 11 explicitly selects transparent propagation, no translation |
| Query registry or dispatcher leakage | Not found — Section 13 explicitly excludes all such mechanisms |
| Infrastructure dependency | Not found — Section 14's import list contains no persistence, no third-party infrastructure library |
| Production composition leakage | Not found — Section 13 confirms binding is demonstrated in tests only |
| Architecture-checker mismatch | Not found — Section 14/15 verify every needed import already resolves under the existing, unmodified rule |
| MILESTONE-032 leakage | Not found — Section 22-23 explicitly exclude and defer all such work |

No genuine issue survived this sweep requiring correction. No decision in this document is deferred to "implementation will decide" — every design question the mission posed (Phase 2, items 1-10) has an explicit, justified answer above.

---

## 28. Final Status

```
═══════════════════════════════════════════════════════════════════════════════

              MILESTONE-031 DESIGN CANDIDATE

═══════════════════════════════════════════════════════════════════════════════

Status:                          CANDIDATE_FOR_INDEPENDENT_DESIGN_REVIEW
Design Questions Answered:       10 / 10
Load-Bearing Decisions Justified: 8 / 8 (Section 19)
Prohibited Items Introduced:     0
Frozen Contracts Reopened:       0
Architecture-Checker Changes:    0 (verified unnecessary, Section 15)

Selected Query Type:             GetCampaignQuery
Selected Handler Type:           GetCampaignHandler
Selected Return Type:            CampaignSnapshot
Selected Module:                 usecases/get_campaign.py
Selected Dependency Style:       Constructor injection (CampaignRepository only)
Selected Binding:                Direct QueryEntryPoint(handler) construction, test-only
Selected Not-Found Strategy:     Fully transparent propagation (no handler-level try/except)

NEXT PERMITTED ACTION: MILESTONE-031 INDEPENDENT DESIGN REVIEW

═══════════════════════════════════════════════════════════════════════════════
```
