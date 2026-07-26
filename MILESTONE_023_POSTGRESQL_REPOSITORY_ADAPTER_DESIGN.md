# MILESTONE-023 - PostgreSQL Repository Adapter Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-023 |
| Title | PostgreSQL Repository Adapter Design |
| Version | 1.1 (narrow correction) |
| Status | DESIGN READY FOR INDEPENDENT RE-REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `10425e85b63a0b6f18b73b962355f22176cb279c` |
| Baseline status | MILESTONE-022 APPROVED AND FROZEN |
| Mission type | Design correction only |
| Repository code, mapper code, migrations, Unit of Work created | No |

**Version 1.1 note:** an independent hostile review of Version 1.0 (design commit `a6e1350b8c37467d3a33b73c6e254c34ce4aab1b`) returned "M023 DESIGN REQUIRES NARROW CORRECTION" with defects in save version semantics, unchanged-save detection, identity predicates, add-duplicate translation, a self-contradictory module-placement statement, an under-specified field mapping, ambiguous transaction ownership, a potential zero-row race, and possible error-detail leakage. This version corrects all of them in place; Section 21 records each finding and its resolution. The selected scope (Section 8 of the Scope Selection) is unchanged and was not reopened.

## 2. Baseline

This design builds on, without altering:

- M019's frozen `_reconstruct_<aggregate>(state) -> <Aggregate>` factories and `<Aggregate>ReconstructionState` types, and the frozen `ReconstructionError`/`ReconstructionErrorCategory` (no dedicated `safe_message` field; its only message accessor is `str(exc)`, via the base `Exception.__init__(message)`);
- M020's frozen `<Aggregate>Repository` Protocols (`get`/`add`/`save`) and `LoadedAggregate`/`SaveOperation`/`SaveResult`/`RepositoryContractError` hierarchy (`AggregateNotFound`, `AggregateAlreadyExists`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, `InvalidPersistedAggregateState`), and, critically, M020 Design Sections 17-19's own frozen prose:
  - "the repository atomically compares the durable version to `expected_persisted_version`... on match, it persists the aggregate's current version and complete aggregate state... **repository save never increments aggregate version**";
  - "the current aggregate version must be greater than or equal to the expected persisted version. Greater-than covers accepted local mutations. **Equal-to covers unchanged saves**";
  - "`aggregate current version == expected persisted version` is a valid unchanged save that returns `SaveResult(operation=UNCHANGED, persisted_version=current_version)`. Implementations may avoid physical writes for unchanged saves, but they must still validate that the expected persisted version matches durable state";
  - live verification of `AggregateVersion` (`src/empirical_platform/shared/domain/versioning.py`) confirms `.next()` is the only mutator (`value + 1`) and is called exclusively by aggregate business methods (verified live in `campaign/aggregate.py`: `self._version = self._version.next()`), never by anything outside the aggregate itself — the repository never sees a raw version integer to increment, only the already-current value the aggregate/durable record already carries;
- M021's frozen `<Aggregate>Mapper` Protocols (`to_durable_record`/`from_durable_record`), `<Aggregate>DurableRecord` types (and nested `DatasetManifestDurableRecord`, `CriterionResultDurableRecord`, `ReviewFindingDurableRecord`, shared `IdentityDurableRecord`/`TransitionDurableRecord`), and `MapperError`/`MapperErrorCategory` (which does carry a dedicated `.safe_message` field, verified live in `shared/contracts/mapping.py`);
- M022's frozen twelve-table PostgreSQL schema and single migration revision (`5b58cdd7751b`), including the exact frozen constraint names captured empirically in its Implementation/Implementation Freeze records;
- `empirical_platform.shared.persistence.postgres.PostgresPersistenceService`/`PostgresUnitOfWork`, verified live: `unit_of_work()` returns a context-managed `PostgresUnitOfWork` with `execute(statement, parameters) -> Sequence[Mapping[str, object]]`, `commit()`, `rollback()`; `__enter__` raises `FoundationError` (category `PERSISTENCE`) if a unit of work is already active on the same context (`_active_unit_of_work` context-var guard — nesting is already a hard, existing runtime error, not something this design invents); every exception raised inside `execute()` is translated via `translate_persistence_error()` into a `FoundationError`, which preserves the original exception only via Python's standard `__cause__` chaining.

## 3. Problem Statement

Unchanged from Version 1.0: nothing yet specifies how a concrete repository implementation bridges M020, M021, and M022 — the `DurableRecord`-to-SQL translation, the real-PostgreSQL-to-M020-error-vocabulary translation, the actual optimistic-concurrency mechanism, and legal module placement. This design answers those questions without writing the implementation itself.

## 4. Design Principles

1. **No frozen artifact is altered.**
2. **The frozen call chain is completed, not changed:** `repository implementation -> mapper -> ReconstructionState -> _reconstruct_* -> aggregate`.
3. **One repository operation is one transaction**, owned by that operation alone (Section 11).
4. **Full-replace for owned collections** on `save()`, justified by the frozen `DurableRecord` shape carrying no per-item version/removal marker (Design Issue 0003, Section 21) — except when the save is classified as `UNCHANGED` (Section 8), in which case owned-collection tables are not touched at all, because an unchanged aggregate version proves no owned-collection content could have changed either (an aggregate's version advances on every state-changing business method, and every business method that could alter an owned collection is itself state-changing).
5. **The repository never increments a version.** It writes exactly the version value the durable record already carries (already advanced, if at all, by the aggregate's own business methods before `to_durable_record()` was called) and uses `expected_persisted_version` only as the atomic-comparison guard, never as an input to arithmetic.
6. **Every predicate that identifies a specific persisted aggregate uses the full `DomainIdentity` (both `governance_id` and `runtime_id`), never one component alone** — see Section 6/8/12 for why a `runtime_id`-only predicate would silently hide a genuine identity mismatch.
7. **`SaveOperation` classification is an integer comparison, never a content diff.** Whether a `save()` is `UNCHANGED` or `UPDATED` is decided by comparing `durable_record.version` to `expected_persisted_version` as integers (Section 8); no owned-collection content is ever compared element-by-element to decide this, which also means collection ordering can never produce a false classification either way.

## 5. Repository Placement and Architecture Boundary

### 5.1 The Problem

`tools/check_architecture.py`'s `FORBIDDEN_IMPORT_PREFIXES` table forbids `campaign`, `run`, `evidence`, `review`, and `shared` (outside `shared.domain`) from importing `sqlalchemy`, `psycopg`, `boto3`, or `empirical_platform.shared.persistence`. A concrete repository implementation inherently needs `sqlalchemy` and `empirical_platform.shared.persistence`. It also needs to import each aggregate's `mapper`/`repository`/`aggregate` modules (to construct `DurableRecord`s, declare Protocol conformance, and call the reconstruction factory indirectly through the mapper).

### 5.2 Resolution (Option B — corrected)

**Version 1.0 of this design stated both "no architecture-checker change of any kind is required" and, in the same section, that `ALLOWED["shared"]` needed a new entry — a direct self-contradiction (Design Issue 0005, Section 21). This is corrected here: exactly one narrow, disclosed architecture-checker change is required, and this design states that once, consistently, everywhere it is relevant.**

A concrete repository implementation for aggregate `X` lives at `empirical_platform.shared.persistence.postgres_repositories.<x>_repository` (one module per aggregate). This placement is chosen over the two alternatives the Scope Selection named:

- **Option A (aggregate-local, e.g. `campaign/repository_postgres.py`)** is rejected: it would place `sqlalchemy`/persistence imports inside a package `FORBIDDEN_IMPORT_PREFIXES` already, correctly, forbids from having them — reopening exactly the domain-purity boundary M019-M022 have consistently protected, for the sake of avoiding one narrow `ALLOWED` addition elsewhere. This is a worse trade, not a free one.
- **Option C (an existing, unrelated infrastructure package such as `acquisition` or `audit`)** is rejected: no existing top-level package's `ALLOWED` entry already includes all four of `campaign`, `run`, `evidence`, and `review` (verified live against the full `ALLOWED` table — the closest, `acquisition`, has `campaign` and `evidence` but not `run` or `review`; `audit` has `evidence` and `review` but not `campaign` or `run`), and none of them is a semantically honest home for a persistence adapter — it would still require an `ALLOWED` change (to add the missing aggregate names to that package) while additionally misrepresenting what that package is for.
- **Option B (this design's choice)** requires exactly one `ALLOWED` change and places the code in the one package whose entire purpose is persistence infrastructure.

The two independent facts, stated once and consistently:

1. **`FORBIDDEN_IMPORT_PREFIXES` requires no change.** `check_architecture.py`'s `module_for_path` classifies every file under `src/empirical_platform/<top-level>/...` by `<top-level>` alone; a new `shared/persistence/postgres_repositories/` subdirectory remains classified as `"shared"`. `shared`'s forbidden-import check is skipped entirely when `"domain" not in path.parts` (`check_architecture.py`, `check_path()`: `if source_module == "shared" and "domain" not in path.parts: forbidden_prefixes = ()`) — a file under `shared/persistence/...` (not `shared/domain/...`) is already exempt from the `sqlalchemy`/`psycopg`/`boto3`/`persistence` forbidden-prefix check by the checker's own existing logic, unchanged.
2. **`ALLOWED["shared"]` requires exactly one change.** The same checker separately verifies, for every cross-top-level-module import, that the imported module is in `ALLOWED[source_module]`. `ALLOWED["shared"]` is `set()` today; a `shared.persistence.postgres_repositories.campaign_repository` module importing `empirical_platform.campaign.mapper`/`empirical_platform.campaign.repository`/`empirical_platform.campaign.aggregate` needs `"campaign"` in `ALLOWED["shared"]`, and analogously for `run`/`evidence`/`review`. **The required change is exactly:** `"shared": {"campaign", "run", "evidence", "review"}` (from `"shared": set()`). This widens only what `shared` may import; it does not touch `FORBIDDEN_IMPORT_PREFIXES` and does not grant `campaign`/`run`/`evidence`/`review` any new ability — the restriction on domain packages reaching into persistence is completely unaffected, in either direction.

### 5.3 Required Negative Fixture

A future implementation milestone must add exactly one new architecture negative fixture proving the widening is precisely these four names and nothing broader: a file classified as `"shared"` (e.g. `tests/fixtures/illegal_imports/src/empirical_platform/shared/bad_shared_import_audit.py`) importing a fifth top-level package not in the widened set (e.g. `empirical_platform.audit`, chosen because it is unrelated to persistence and not among the four newly-allowed names) must still be reported as a violation. The four existing M021 negative fixtures (`campaign/bad_mapper_sqlalchemy_import.py`, `run/bad_mapper_persistence_import.py`, `evidence/bad_mapper_boto3_import.py`, `review/bad_mapper_psycopg_import.py`) already prove the `FORBIDDEN_IMPORT_PREFIXES` side is unaffected by this widening (an orthogonal check) and need no change.

### 5.4 What This Design Does Not Decide

Whether the four concrete repository classes share a common base class or duplicate a small amount of structurally-identical code is an implementation-time decision; Sections 6-8 specify the exact steps and their order, which a future implementation may factor however it chooses.

## 6. Operation Design: `get`

For aggregate `X` with root table `x`, owned child tables `x_c1, x_c2, ...` (each with a `position` or `sequence` ordering column per M022), given `identity: DomainIdentity[XId]` with `identity.governance_id` and `identity.runtime_id`:

1. Open one `PostgresUnitOfWork`.
2. Execute:
   ```sql
   SELECT *
   FROM x
   WHERE runtime_id = :runtime_id
     AND governance_id = :governance_id
   ```
   If exactly one row: proceed to step 4.
3. If zero rows: execute a diagnostic follow-up, in the same transaction, to distinguish absence from identity mismatch:
   ```sql
   SELECT governance_id
   FROM x
   WHERE runtime_id = :runtime_id
   ```
   - Zero rows: raise `AggregateNotFound(aggregate_kind=..., identity=identity)`, roll back, return.
   - One row, whose `governance_id` differs from `identity.governance_id`: raise `InvalidPersistedAggregateState(aggregate_kind=..., reason="persisted governance_id does not match the requested identity's governance_id for this runtime_id", identity=identity)`, roll back, return. This condition should never arise under correct system operation (M020's frozen uniqueness rule guarantees one canonical `DomainIdentity` pairing per aggregate); when it does, it indicates persisted-data corruption or a caller supplying a stale/incorrect `DomainIdentity`, and `InvalidPersistedAggregateState` is the frozen taxonomy's correct fit ("durable state cannot be safely reconstructed into an aggregate" — a row whose stored identity disagrees with the requested identity cannot be safely treated as that identity's aggregate).
4. For each owned child table, in creation order (M022 Section 12.5):
   ```sql
   SELECT *
   FROM x_c
   WHERE <parent_fk_column> = :runtime_id
   ORDER BY position
   ```
   (or `ORDER BY sequence`, per Section 10's table).
5. Assemble an `<X>DurableRecord` (Section 10).
6. Call `mapper.from_durable_record(record)`. If it raises `MapperError`: raise `InvalidPersistedAggregateState(aggregate_kind=..., reason=mapper_error.safe_message, identity=identity)` from it, roll back, return.
7. Call `_reconstruct_x(state)`. If it raises `ReconstructionError`: raise `InvalidPersistedAggregateState(aggregate_kind=..., reason=str(reconstruction_error), identity=identity)` from it, roll back, return. (`ReconstructionError` has no dedicated safe-message field; `str(exc)` is its only, already-safe, message accessor — verified live, Section 2.)
8. Commit.
9. Return `LoadedAggregate(aggregate=aggregate, persisted_version=AggregateVersion(root.version))`.

## 7. Operation Design: `add`

1. Call `mapper.to_durable_record(aggregate)`. If it raises `MapperError`: raise `InvalidAggregateForPersistence(aggregate_kind=..., reason=mapper_error.safe_message)`, no transaction opened yet.
2. Open one `PostgresUnitOfWork`.
3. Execute `INSERT INTO x (...) VALUES (...)` using the durable record's root-level fields (both `governance_id` and `runtime_id` from `record.identity`).
4. For each owned collection, in creation order, one `INSERT` per element (Section 10's ordering rule).
5. If any `INSERT` raises: it surfaces as a `FoundationError` (Section 9). Classify it there; if it classifies as a duplicate-identity violation, raise `AggregateAlreadyExists(aggregate_kind=..., identity=identity)` — the transaction is already rolled back by `PostgresUnitOfWork.__exit__`'s existing exception path. Any failure that does not classify as a known duplicate-identity condition propagates as the `FoundationError` it already is.
6. Commit.
7. Return `SaveResult(operation=SaveOperation.CREATED, persisted_version=AggregateVersion(record.version))` — `record.version` is whatever value the durable record already carries (normally `0`, per `AggregateVersion.initial()`, for a newly-constructed aggregate that has never been saved; this design does not assume it, only writes it).

`add()` performs no pre-check `SELECT`: the root table's `UNIQUE`/`PRIMARY KEY` constraints are the actual source of truth, avoiding a check-then-insert race.

## 8. Operation Design: `save`

Given `aggregate` and `expected_persisted_version: AggregateVersion`:

1. Call `mapper.to_durable_record(aggregate)` to obtain `record`. If it raises `MapperError`: raise `InvalidAggregateForPersistence(aggregate_kind=..., reason=mapper_error.safe_message)`, no transaction opened yet.
2. Open one `PostgresUnitOfWork`.
3. Execute the single guarded write-or-fail statement, unconditionally (Section 9's race-safety reasoning explains why this always executes, even when the save will classify as `UNCHANGED`):
   ```sql
   UPDATE x
   SET <every non-key root column> = <value from record>,
       version = :record_version
   WHERE runtime_id = :runtime_id
     AND governance_id = :governance_id
     AND version = :expected_persisted_version
   RETURNING version
   ```
   `:record_version` is `record.version` exactly — never `version + 1`, never any repository-computed increment (Design Principle 5).
4. **If the `UPDATE` returned zero rows**, classify the failure with one diagnostic follow-up in the same transaction:
   ```sql
   SELECT governance_id, version
   FROM x
   WHERE runtime_id = :runtime_id
   ```
   - Zero rows: raise `AggregateNotFound(aggregate_kind=..., identity=identity)`.
   - One row, whose `governance_id` differs from the aggregate's own `identity.governance_id`: raise `InvalidPersistedAggregateState(aggregate_kind=..., reason="persisted governance_id does not match the aggregate's identity for this runtime_id", identity=identity)`.
   - One row, whose `governance_id` matches but whose `version` differs from `expected_persisted_version`: raise `OptimisticConcurrencyConflict(aggregate_kind=..., identity=identity, expected_persisted_version=expected_persisted_version, aggregate_current_version=AggregateVersion(record.version), actual_persisted_version=AggregateVersion(that row's version))`.
   All three paths roll back before raising. See Section 9 for why this two-statement (guarded-`UPDATE`-then-diagnostic-`SELECT`) ordering, rather than a `SELECT`-then-`UPDATE` ordering, is the race-safe choice.
5. **If the `UPDATE` returned exactly one row**, classify the operation by comparing integers, never content (Design Principle 7):
   - `record.version == expected_persisted_version`: this is a valid **unchanged save** (M020 Design Section 18, verbatim: "equal-to covers unchanged saves"). The guarded `UPDATE` already ran and already re-wrote the same version value — this design accepts that harmless, idempotent single-row rewrite as the cost of race-safety (Section 9) rather than attempting to skip it; M020 Design Section 18 permits but does not require avoiding physical writes for unchanged saves ("implementations may avoid physical writes... but must still validate"). **Owned-collection tables are not touched**: skip step 6 entirely and proceed to step 7. Return `SaveResult(operation=SaveOperation.UNCHANGED, persisted_version=AggregateVersion(record.version))`.
   - `record.version > expected_persisted_version`: this is a real update (one or more accepted local mutations occurred since load). Proceed to step 6.
6. Delete every owned-collection row for this parent (`DELETE FROM x_c WHERE <parent_fk_column> = :runtime_id`, one statement per child table, in reverse creation order) and re-insert the durable record's current collection state (identical rule to `add()` step 4).
7. Commit.
8. Return `SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(record.version))` (only reached from step 5's second branch, after step 6 completes).

`record.version < expected_persisted_version` is not a case this algorithm needs to distinguish specially: `AggregateVersion` only ever advances (`.next()` has no inverse, verified live, Section 2), so a correctly-behaving caller can never observe this; the guarded `UPDATE`'s `WHERE version = :expected_persisted_version` clause would simply fail to match (falling into step 4) exactly as it would for a genuinely stale version, which is the correct outcome regardless of how the caller arrived at an inconsistent `expected_persisted_version`.

## 9. Error Translation

### 9.1 Race-Safety Rationale for `save()`'s Statement Ordering

A **`SELECT`-then-`UPDATE`** ordering (read the current version, decide in application code whether to write, then write) is not race-safe: another transaction could commit between the `SELECT` and the `UPDATE`, making the decision stale by the time the `UPDATE` executes. This design therefore always executes the guarded `UPDATE ... WHERE version = :expected_persisted_version RETURNING version` **first** (Section 8 step 3) — this statement is itself PostgreSQL's atomic compare-and-set primitive: whether it matches a row is decided and acted upon in one indivisible operation, with no window in which another writer could invalidate the decision after it was made. The **only** thing decided *after* the write attempt is which error to report when it affected zero rows (Section 8 step 4) — a diagnostic classification, not a decision about whether to write. Even if a concurrent transaction commits between the failed `UPDATE` and the diagnostic `SELECT`, every possible outcome of that `SELECT` still describes a real, valid state of the row at-or-after the `UPDATE`'s own evaluation instant, so the caller always receives a truthful rejection (`AggregateNotFound`, `OptimisticConcurrencyConflict`, or `InvalidPersistedAggregateState`) — never an incorrect success and never a silently-wrong `SaveResult`. This is the same pattern used by conditional-update-based optimistic concurrency generally; it is chosen over a single CTE-based statement combining the write and the diagnostic read because PostgreSQL does not guarantee a same-statement `SELECT` in a `WITH` clause observes a data-modifying CTE's own effects (the write and read sub-statements of one `WITH` execute against a shared snapshot, not a read-after-write view of each other), which would make a CTE-based version *harder* to reason about correctly, not easier, for a purely diagnostic follow-up.

### 9.2 Duplicate-Identity Detection on `add()` (SQLSTATE and constraint name only)

Detection uses only stable, structural facts — never parsed error message text:

1. `FoundationError.__cause__` is a `sqlalchemy.exc.IntegrityError`.
2. Its `.orig` is the underlying `psycopg.errors.Error`.
3. Its `.orig.diag.sqlstate == "23505"` (PostgreSQL's standard, stable `unique_violation` SQLSTATE code).
4. Its `.orig.diag.constraint_name` (a stable, structured diagnostic field — verified live to exist on `psycopg.errors.Diagnostic`) identifies which constraint fired:

| `constraint_name` | Meaning | Classification |
| --- | --- | --- |
| `pk_campaign` / `pk_run` / `pk_evidence_package` / `pk_review` | duplicate `runtime_id` | `AggregateAlreadyExists` |
| `uq_campaign_governance_id` / `uq_run_governance_id` / `uq_evidence_package_governance_id` / `uq_review_governance_id` | duplicate `governance_id` | `AggregateAlreadyExists` |
| any other value, or `sqlstate != "23505"` | an unrecognized or unrelated uniqueness failure (e.g. a future schema change adding an unrelated unique index) — an "impossible or unknown uniqueness failure" this design does not attempt to classify | **not translated**; the original `FoundationError` propagates unchanged |

PostgreSQL reports the first constraint violation it detects for a given statement; a caller attempting to `add()` an aggregate whose full identity (both `governance_id` and `runtime_id`) already exists will observe exactly one of the two named constraints fire (which one is a PostgreSQL implementation detail, not something this design assumes an order for) — either way the correct classification is `AggregateAlreadyExists`, so no distinct "duplicate full identity" case needs its own row in this table.

### 9.3 Complete Table

| Failure | Detected how | Raised as |
| --- | --- | --- |
| `mapper.to_durable_record()` raises `MapperError` | Direct catch, no transaction involved | `InvalidAggregateForPersistence(aggregate_kind, reason=mapper_error.safe_message)` |
| `mapper.from_durable_record()` raises `MapperError` | Direct catch, inside the `get()` transaction | `InvalidPersistedAggregateState(aggregate_kind, reason=mapper_error.safe_message, identity)` |
| `_reconstruct_x()` raises `ReconstructionError` | Direct catch, inside the `get()` transaction | `InvalidPersistedAggregateState(aggregate_kind, reason=str(reconstruction_error), identity)` |
| Root row absent on `get()` (Section 6 step 3) | Zero rows from the runtime_id-only diagnostic `SELECT` | `AggregateNotFound(aggregate_kind, identity)` |
| Persisted identity mismatch on `get()` (Section 6 step 3) | Diagnostic `SELECT` finds a row with a different `governance_id` | `InvalidPersistedAggregateState(aggregate_kind, reason, identity)` |
| Root row absent on `save()` (Section 8 step 4) | Zero rows from the runtime_id-only diagnostic `SELECT` | `AggregateNotFound(aggregate_kind, identity)` |
| Persisted identity mismatch on `save()` (Section 8 step 4) | Diagnostic `SELECT` finds a row with a different `governance_id` | `InvalidPersistedAggregateState(aggregate_kind, reason, identity)` |
| Stale expected version on `save()` (Section 8 step 4) | Diagnostic `SELECT` finds the identity matches but `version` differs | `OptimisticConcurrencyConflict(..., actual_persisted_version=<that row's version>)` |
| Duplicate identity on `add()` (Section 9.2) | `sqlstate == "23505"` and `constraint_name` matches a known root-table constraint | `AggregateAlreadyExists(aggregate_kind, identity)` |
| Any other persistence failure | `FoundationError` not matching a case above | Not translated; propagates unchanged |

### 9.4 No Leakage Through Repository-Domain Errors

Every `RepositoryContractError` subtype's message is produced entirely by its own frozen `__init__` (`repository.py`), which accepts only `aggregate_kind`/`identity`/(for the two `Invalid*` types) a `reason: str` this design controls — never raw SQL text, `sqlstate`, `constraint_name`, driver exception class names, or SQLAlchemy statement objects. `reason=` values are always either `mapper_error.safe_message` (`MapperError`'s dedicated safe field), `str(reconstruction_error)` (`ReconstructionError`'s only, already-safe, message accessor), or a repository-authored literal string (e.g. the identity-mismatch messages in Sections 6/8) — never an f-string interpolating any driver/SQL detail. The structural facts in Sections 9.1-9.2 (`sqlstate`, `constraint_name`) are used only internally, to decide *which* frozen exception type and *which* already-safe message to raise; they are never themselves embedded in any raised error's text.

## 10. DurableRecord-to-Schema Field Mapping

Every mapping rule is exhaustive for its table; no field of any `<Aggregate>DurableRecord` (M021, frozen) lacks a named column below, and no listed column lacks a source field.

**Shared conversions**, used throughout:

| DurableRecord type | SQL type | To SQL | From SQL |
| --- | --- | --- | --- |
| `str` (identity component) | `UUID` (`runtime_id`) / `TEXT` (`governance_id`) | bind the string directly (`postgresql.UUID(as_uuid=False)` accepts a string; no UUID-object marshaling) | read the column value as `str` directly |
| `str` (free text) | `TEXT` | bind directly, parameterized (never string-interpolated — Section 17) | read directly |
| `str \| None` | nullable `TEXT` | `None` binds to SQL `NULL`; otherwise the string | SQL `NULL` reads as `None`; otherwise the string |
| `tuple[str, ...]` | `TEXT[]` | bind the tuple as a list; an empty tuple binds to `{}` (matching the column's `NOT NULL DEFAULT '{}'::text[]`) | read the array value, convert to `tuple(...)` |
| `datetime` | `TIMESTAMPTZ` | bind the timezone-aware `datetime` directly | read the column's timezone-aware value directly |
| `int` (`version`, `next_transition_sequence`, `sequence`, `position`) | `INTEGER` | bind directly | read directly |
| `IdentityDurableRecord \| None` (`TransitionDurableRecord.identity_reference`) | two nullable columns (`identity_governance_id`, `identity_runtime_id`) | `None` binds both to `NULL`; otherwise `.governance_id`/`.runtime_id` to their respective columns | both `NULL` reads back as `None`; otherwise construct `IdentityDurableRecord(governance_id=..., runtime_id=...)` |

**Per-table field mapping** (table name; PK columns; ordering column; DurableRecord field -> SQL column):

| Table | PK | Order column | Field -> Column |
| --- | --- | --- | --- |
| `campaign` | `runtime_id` | — | `identity.runtime_id -> runtime_id`; `identity.governance_id -> governance_id`; `scope_statement -> scope_statement`; `lifecycle_state -> lifecycle_state`; `version -> version`; `next_transition_sequence -> next_transition_sequence` |
| `campaign_transition` | `(campaign_runtime_id, sequence)` | `sequence` (the element's own `TransitionDurableRecord.sequence` field — **not** the tuple index) | parent `identity.runtime_id -> campaign_runtime_id`; `.from_state -> from_state`; `.to_state -> to_state`; `.version -> version`; `.sequence -> sequence`; `.actor -> actor`; `.occurred_at -> occurred_at`; `.identity_reference -> identity_governance_id, identity_runtime_id`; `.correlation_id -> correlation_id`; `.reason -> reason` |
| `run` | `runtime_id` | — | `identity.runtime_id -> runtime_id`; `identity.governance_id -> governance_id`; `campaign_id -> campaign_id`; `lifecycle_state -> lifecycle_state`; `version -> version`; `next_transition_sequence -> next_transition_sequence` |
| `run_manifest` | `(run_runtime_id, position)` | `position` (the element's own **tuple index** — `DatasetManifestDurableRecord` has no frozen sequence field of its own) | parent `identity.runtime_id -> run_runtime_id`; tuple index `-> position`; `.manifest_id -> manifest_id`; `.recorded_at -> recorded_at`; `.source -> source`; `.acquisition_method -> acquisition_method`; `.normalization_method -> normalization_method`; `.notes -> notes` |
| `run_transition` | `(run_runtime_id, sequence)` | `sequence` (own field) | same shape as `campaign_transition`, keyed by `run_runtime_id` |
| `evidence_package` | `runtime_id` | — | `identity.runtime_id -> runtime_id`; `identity.governance_id -> governance_id`; `run_id -> run_id`; `lifecycle_state -> lifecycle_state`; `version -> version`; `next_transition_sequence -> next_transition_sequence` |
| `evidence_package_criterion_result` | `(evidence_package_runtime_id, position)` | `position` (tuple index — `CriterionResultDurableRecord` has no frozen sequence field) | parent `identity.runtime_id -> evidence_package_runtime_id`; tuple index `-> position`; `.criterion_id -> criterion_id`; `.recorded_at -> recorded_at`; `.result_label -> result_label`; `.summary -> summary`; `.evidence_references -> evidence_references` |
| `evidence_package_artifact_reference` | `(evidence_package_runtime_id, position)` | `position` (tuple index — `artifact_references` is a plain `tuple[str, ...]`, no per-element record) | parent `identity.runtime_id -> evidence_package_runtime_id`; tuple index `-> position`; element value `-> value` |
| `evidence_package_transition` | `(evidence_package_runtime_id, sequence)` | `sequence` (own field) | same shape as `campaign_transition`, keyed by `evidence_package_runtime_id` |
| `review` | `runtime_id` | — | `identity.runtime_id -> runtime_id`; `identity.governance_id -> governance_id`; `target_evidence_package_id -> target_evidence_package_id`; `reviewer_reference -> reviewer_reference`; `lifecycle_state -> lifecycle_state`; `disposition -> disposition`; `final_disposition_rationale -> final_disposition_rationale`; `cancellation_reason -> cancellation_reason`; `version -> version`; `next_transition_sequence -> next_transition_sequence` |
| `review_finding` | `(review_runtime_id, sequence)` | `sequence` (own field — `ReviewFindingDurableRecord.sequence`) | parent `identity.runtime_id -> review_runtime_id`; `.sequence -> sequence`; `.text -> text`; `.rationale -> rationale`; `.evidence_references -> evidence_references` |
| `review_transition` | `(review_runtime_id, sequence)` | `sequence` (own field) | same shape as `campaign_transition`, keyed by `review_runtime_id` |

Reading order for every owned child table (Sections 6/7/8) is always `SELECT ... FROM ... WHERE ... ORDER BY <order column>` — clause order corrected from Version 1.0's malformed prose (Design Issue 0006, Section 21).

## 11. Transaction Ownership and Boundary

1. **Each repository operation owns exactly one `PostgresUnitOfWork`, opened internally by that operation.** No caller-supplied or externally-owned Unit of Work is accepted by, or threaded through, `get`/`add`/`save` — there is no "external application Unit of Work" concept in this design at all; that would be the still-correctly-deferred multi-statement/multi-aggregate Unit of Work (Scope Selection Candidate D).
2. **Execution order:** open (`__enter__`, which begins a connection and a transaction) -> execute every statement listed for that operation in Sections 6-8, in the order given -> `commit()` on success, or the transaction is rolled back by `PostgresUnitOfWork.__exit__`'s existing behavior when any exception propagates out of the `with` block (including every `RepositoryContractError` this design raises).
3. **Commit/rollback owner:** the repository method itself, via the `with ... unit_of_work() as work:` block — never the caller.
4. **Connection lifetime:** exactly the lifetime of one operation's `with` block; `PostgresUnitOfWork._complete()` (existing behavior) closes the connection when the block exits, whether by commit or rollback.
5. **Nested-call behavior:** calling a repository operation while another unit of work is already active on the same context raises the existing `FoundationError` from `PostgresUnitOfWork.__enter__`'s own `_active_unit_of_work` guard; this design does not catch, reinterpret, or suppress that error — a repository operation must not be invoked reentrantly from within another already-open unit of work.
6. **Error propagation:** every failure this design does not explicitly classify (Section 9) propagates as the `FoundationError` `PostgresUnitOfWork.execute()`/`commit()` already produces; this design adds no additional wrapping layer for infrastructure-level failures.
7. **Rollback failure:** if `rollback()` itself raises (e.g. the connection was already lost), that exception propagates from `PostgresUnitOfWork.rollback()`'s own existing `translate_persistence_error()` call, unmodified by this design.

Candidate D (multi-statement/multi-aggregate Unit of Work) remains correctly deferred; nothing above requires it.

## 12. Identity Handling

Every predicate that must identify one specific persisted aggregate (Sections 6, 8) uses **both** `governance_id` and `runtime_id` from the full `DomainIdentity` — never `runtime_id` alone (Design Principle 6). Matching on `runtime_id` alone would silently succeed even if a caller's `governance_id` disagreed with the persisted row's, hiding exactly the kind of identity-pairing corruption M020's frozen uniqueness rule ("per aggregate type, `governance_id` is unique, `runtime_id` is unique, and both form one canonical `DomainIdentity`") exists to prevent from going undetected. `add(aggregate)` writes both components and relies on the schema's own constraints, rather than a separate lookup, for duplicate detection (Section 7). Cross-aggregate context fields already stored as `governance_id` strings in the durable record (`RunDurableRecord.campaign_id`, `EvidencePackageDurableRecord.run_id`, `ReviewDurableRecord.target_evidence_package_id`) are written and read as opaque strings, unchanged from Version 1.0.

## 13. Migration Revision Strategy

None. This design creates no migration; `migrations/versions/` remains exactly the one M022 revision.

## 14. Reconstruction and Mapper Integration

Unchanged from Version 1.0: this design is precisely the "future repository implementation" M019, M020, and M021's own frozen documents and docstrings anticipate and explicitly defer to.

## 15. Test Strategy (for a future Implementation milestone)

- real-PostgreSQL round-trip fidelity per aggregate (`add`, `get`, `save`, re-`get`);
- **unchanged save**: `add()`, `get()`, `save()` immediately with the just-loaded `expected_persisted_version` and no aggregate mutation — assert `SaveResult(operation=UNCHANGED, persisted_version=<unchanged version>)` and that no owned-collection row was rewritten (e.g. by asserting each child row's own database-internal transaction/creation marker, if available, is untouched, or simply that row contents are byte-identical);
- **unchanged save with a concurrent conflict**: two independent `LoadedAggregate`s at the same version; the first `save()`s a real mutation; the second then attempts an "unchanged" `save()` (no local mutation, but a now-stale `expected_persisted_version`) and must receive `OptimisticConcurrencyConflict`, not `UNCHANGED` — proving Section 8 step 4/5's ordering never lets a stale caller slip through as unchanged;
- optimistic-concurrency conflict on a real mutation (Version 1.0's existing case, retained);
- `add()` duplicate rejection, both by duplicate `governance_id` and by duplicate `runtime_id` independently, each asserting the specific constraint-name branch in Section 9.2 fired;
- `get()`/`save()` not-found (identity never added);
- **identity mismatch**: a `get()`/`save()` against a `runtime_id` that exists but paired with a different `governance_id` than requested (constructed by direct SQL setup, since this cannot arise through the frozen mapper/aggregate contracts alone) must raise `InvalidPersistedAggregateState`, not `AggregateNotFound`;
- owned-collection ordering preserved end-to-end through the full mapper-and-schema round trip;
- atomicity of a simulated mid-write failure during `add()`/`save()`;
- every row of Section 9.3's error-translation table, proven against real PostgreSQL.

All tests must run against real PostgreSQL, not a mock, consistent with M022's established discipline.

## 16. Architecture Enforcement

Exactly one narrow, explicit, disclosed change is required, stated once and consistently (Section 5.2): `ALLOWED["shared"]` changes from `set()` to `{"campaign", "run", "evidence", "review"}` in `tools/check_architecture.py`. `FORBIDDEN_IMPORT_PREFIXES` is unchanged for every package. This design does not modify `tools/check_architecture.py` itself (it is design-only); a future implementation milestone makes this exact, narrow change alongside the code that needs it, and adds the one new negative fixture Section 5.3 specifies.

## 17. Security Considerations

Unchanged from Version 1.0: every SQL statement in Sections 6-8 is parameterized; no credential handling or connection-string construction is introduced. Section 9.4 additionally freezes that no SQL/driver/diagnostic detail is ever leaked through a raised `RepositoryContractError`'s message.

## 18. Compatibility with M019, M020, M021, and M022

Unchanged from Version 1.0: no frozen file in any of the four milestones is modified; every operation uses only already-frozen types and schema objects.

## 19. Explicit Non-Goals

This design does not:

- write repository implementation code, concrete mapper implementation code, or a migration;
- introduce multi-statement or multi-aggregate Unit of Work, runtime composition, application services, or M024 work;
- touch Audit runtime, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior.

`SaveOperation.UNCHANGED` is fully specified by this version (Section 8) and is no longer an open non-goal.

## 20. Deferred Work

- concrete mapper implementation (independent, ready, non-blocking — M023 Scope Selection Candidate A);
- concrete repository implementation following this design, including making the one `ALLOWED["shared"]` change and adding the one new negative fixture (Sections 5.2-5.3) — both specified exactly here, applied by that future milestone, not by this design;
- multi-statement/multi-aggregate Unit of Work, repository runtime composition, application services (all still correctly deferred).

## 21. Hostile Self-Review

Cumulative record across both versions; Version 1.0's four findings remain resolved as originally recorded, reproduced here for a complete, self-contained history:

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M023-DESIGN-ISSUE-0001 | MAJOR | 9 | Initial framing assumed a repository implementation could catch `sqlalchemy.exc.IntegrityError` directly from a call through `PostgresUnitOfWork.execute()`. | Live inspection of `postgres.py` shows `execute()` translates every exception into a generic `FoundationError` via `translate_persistence_error()`, preserving the original only as `__cause__`. | An implementer following an untested assumption here would either fail to distinguish `AggregateAlreadyExists` from other failures, or would need to rediscover this translation behavior mid-implementation without a reviewed design to guide it. | Added the error-translation table, keyed explicitly on `FoundationError.__cause__` / `.orig.diag`, verified against the real `translate_persistence_error`/`FoundationError.wrap` source. | Resolved |
| M023-DESIGN-ISSUE-0002 | MAJOR | 5 | Initial framing treated repository module placement as obviously fine anywhere convenient, without checking the architecture checker's actual rules. | `campaign`/`run`/`evidence`/`review` are forbidden from importing `sqlalchemy`/persistence; a naive placement inside those packages would either violate the checker or require weakening a domain-purity rule this project has consistently protected since M019. | Could have produced a design that implicitly required an unreviewed, broad architecture-checker weakening at implementation time. | Traced `check_architecture.py`'s actual `module_for_path`/`ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` logic and confirmed `shared/persistence/...` placement requires exactly one narrow, disclosed addition and no change to any forbidden-import rule. | Resolved |
| M023-DESIGN-ISSUE-0003 | MINOR | 8 | Considered specifying an incremental-diff strategy for owned collections to avoid delete-and-reinsert's apparent inefficiency. | The frozen `DurableRecord` types (M021) carry no per-item identity, version, or removal marker distinguishing "unchanged" from "new" elements; an incremental diff would require inventing such metadata, out of scope. | Attempting this would either silently invent new mapper-contract surface or produce an under-specified, ambiguous design. | Adopted and justified full-replace explicitly (Design Principle 4), with the reasoning recorded rather than left implicit. | Resolved |
| M023-DESIGN-ISSUE-0004 | MINOR | 12 | Considered having `get`/`save` accept and resolve `governance_id` as an alternative lookup key for flexibility. | M022 Design Section 6 already establishes `runtime_id` as every table's own primary key; supporting a second lookup path adds surface area no frozen caller actually requires. | Would add an unrequested, unreviewed degree of freedom beyond what M020's frozen Protocol signatures need. | Fixed `runtime_id` as the primary structural key (Design Principle 5's predecessor, now superseded in emphasis by Principle 6's full-identity predicate requirement, which does not reintroduce `governance_id`-only lookup — both components are always used together). | Resolved |
| M023-DESIGN-ISSUE-0005 | MAJOR | 8 | Version 1.0 specified `SET version = version + 1` in the guarded `UPDATE`, a repository-owned version increment. | Live verification: `AggregateVersion.next()` is called only by aggregate business methods (`campaign/aggregate.py`); M020 Design Section 17 states verbatim "repository save never increments aggregate version." | An implementation following this would double-increment (once in the aggregate, again in SQL), corrupting the optimistic-concurrency invariant and violating a directly frozen rule. | Corrected to `SET version = :record_version` (the durable record's already-current value); added Design Principle 5 and cited M020 Design Sections 17-19 verbatim in Section 2. | Resolved |
| M023-DESIGN-ISSUE-0006 | MAJOR | 8 | Version 1.0 explicitly deferred `SaveOperation.UNCHANGED` as unsolved, despite M020 Design Section 18 already freezing its exact semantics. | M020 Design Section 18: "`aggregate current version == expected persisted version` is a valid unchanged save... Implementations may avoid physical writes for unchanged saves, but they must still validate." | Left unresolved, a future implementer would either invent an inconsistent algorithm or skip the required expected-version validation for the equal-version case, risking a false `UNCHANGED` under a concurrent conflict. | Added the full canonical algorithm (Section 8, steps 3-5): the guarded `UPDATE` always runs (so validation always happens), classification is a post-hoc integer comparison, and owned-collection tables are skipped only in the `UNCHANGED` branch. Added the corresponding test case (Section 15). | Resolved |
| M023-DESIGN-ISSUE-0007 | MAJOR | 6, 8, 12 | Version 1.0's `get`/`save` predicates matched on `runtime_id` alone. | `runtime_id`-only matching cannot detect a persisted row whose `governance_id` disagrees with the requested identity — exactly the corruption M020's uniqueness rule is meant to make impossible, silently hidden instead of surfaced. | A caller with a stale/incorrect `DomainIdentity` pairing could silently operate on the wrong logical identity's data. | Added Design Principle 6; corrected every predicate to include both components; added the identity-mismatch diagnostic branch and its `InvalidPersistedAggregateState` classification (Sections 6, 8, 9.3); added the corresponding test case (Section 15). | Resolved |
| M023-DESIGN-ISSUE-0008 | MAJOR | 7, 9 | Version 1.0's `add()` duplicate detection referenced `.orig.diag.constraint_name` only in prose, without a stable, exhaustive dispatch table, and without stating the SQLSTATE precondition. | An implementer could parse error message text (unstable across PostgreSQL versions/locales) instead of the stable `sqlstate`/`constraint_name` diagnostic fields, or could incorrectly map an unrelated future unique-constraint violation to `AggregateAlreadyExists`. | Fragile, locale/version-dependent detection, or silent misclassification of an unrelated failure as identity duplication. | Added Section 9.2's exact SQLSTATE (`23505`) precondition and exhaustive constraint-name dispatch table, with an explicit "unknown uniqueness violation remains untranslated" fallback. | Resolved |
| M023-DESIGN-ISSUE-0009 | MAJOR | 5 | Version 1.0 stated, within the same section, both "no architecture-checker change of any kind is required" and that `ALLOWED["shared"]` needed a new entry. | Direct re-reading of Version 1.0 Section 5.2 confirms the contradiction verbatim. | A reviewer or implementer could reasonably act on either half of the contradiction and be wrong either way; independent review correctly flagged this. | Rewrote Section 5 to state the one required change (`ALLOWED["shared"]` gaining four names) exactly once, consistently, cross-referenced from every section that touches it (5.2, 16, 20), with an explicit comparison against Options A and C explaining why B is still correct despite requiring this one change. | Resolved |
| M023-DESIGN-ISSUE-0010 | MINOR | 9 | Version 1.0 did not explicitly analyze whether its zero-row handling was race-safe, despite already using an `UPDATE`-first ordering. | Independent review asked for an explicit race analysis; the ordering was already correct but undefended in the text. | A reader could not distinguish "correct by design" from "correct by accident" without the reasoning being stated. | Added Section 9.1, explicitly contrasting the chosen `UPDATE`-then-diagnostic-`SELECT` ordering against both a `SELECT`-then-`UPDATE` race and a same-statement CTE alternative, with the reasoning for rejecting the latter (cross-CTE snapshot visibility is not guaranteed to reflect the write). | Resolved |
| M023-DESIGN-ISSUE-0011 | MINOR | 10 | Version 1.0 deferred the field-by-field mapping entirely to M021/M022's own documents rather than restating it, and its prose example had `ORDER BY` before `WHERE` (invalid SQL clause order). | Independent review required a complete, self-contained mapping table and correct clause order. | An implementer would need to reconstruct the mapping by cross-referencing two other documents, and a naive prose reading could produce invalid SQL. | Added the complete per-table field mapping (Section 10) and corrected every query's clause order to `SELECT ... FROM ... WHERE ... ORDER BY`. | Resolved |
| M023-DESIGN-ISSUE-0012 | MINOR | 9 | Version 1.0 did not explicitly state that repository-domain error messages never leak SQL/driver/diagnostic detail, even though its own design did not actually leak any. | Independent review required this to be frozen explicitly, not left implicit. | An implementer without this stated explicitly might reasonably embed `sqlstate`/`constraint_name`/raw driver text into a `reason=` string for debugging convenience, leaking infrastructure detail through a domain-facing error. | Added Section 9.4, freezing that `reason=` values are always `mapper_error.safe_message`, `str(reconstruction_error)`, or a repository-authored literal — never SQL/driver text. | Resolved |

No unresolved design finding remains.

## 22. Implementation Acceptance Gate (for a future Implementation milestone, not satisfied by this design)

A future implementation milestone must demonstrate, before it may be considered for freeze:

- every operation in Sections 6-8 implemented exactly as specified, for all four aggregates, including the corrected version semantics (never incrementing), the `UNCHANGED` algorithm, and the full-identity predicates;
- every row of Section 9.3's error-translation table proven against real PostgreSQL, including both duplicate-identity sub-cases (Section 9.2) and both identity-mismatch sub-cases (Sections 6/8);
- the concurrent-conflict-during-unchanged-save test (Section 15) passing, proving no stale caller can be misclassified as `UNCHANGED`;
- the one narrow `ALLOWED["shared"]` architecture-checker change made, together with the one new negative fixture (Section 5.3), verified not to weaken any `FORBIDDEN_IMPORT_PREFIXES` rule;
- no frozen M019, M020, M021, or M022 file modified.

## 23. Final Decision

```text
DESIGN READY FOR INDEPENDENT RE-REVIEW
```

NOT APPROVED. NOT FROZEN. No repository, mapper, migration, or Unit of Work code was created by this design.
