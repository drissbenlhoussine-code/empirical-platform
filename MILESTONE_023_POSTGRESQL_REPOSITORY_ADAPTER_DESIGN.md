# MILESTONE-023 - PostgreSQL Repository Adapter Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-023 |
| Title | PostgreSQL Repository Adapter Design |
| Version | 1.3 (commit-before-return correction) |
| Status | DESIGN READY FOR INDEPENDENT FINAL RE-REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `10425e85b63a0b6f18b73b962355f22176cb279c` |
| Baseline status | MILESTONE-022 APPROVED AND FROZEN |
| Mission type | Design correction only |
| Repository code, mapper code, migrations, Unit of Work created | No |

**Version 1.1 note:** an independent hostile review of Version 1.0 (design commit `a6e1350b8c37467d3a33b73c6e254c34ce4aab1b`) returned "M023 DESIGN REQUIRES NARROW CORRECTION" with defects in save version semantics, unchanged-save detection, identity predicates, add-duplicate translation, a self-contradictory module-placement statement, an under-specified field mapping, ambiguous transaction ownership, a potential zero-row race, and possible error-detail leakage. Version 1.1 corrected all of them in place.

**Version 1.2 note:** an independent final re-review of Version 1.1 (correction commit `7dcc7c10e247163d6e029fb6520fd76846e328d6`) returned "M023 DESIGN REQUIRES ANOTHER NARROW CORRECTION" with exactly one remaining blocking defect: Version 1.1's `save()` design relied on a false claim that the guarded `UPDATE`'s `WHERE` clause would reject a `record.version` lower than `expected_persisted_version` — it does not, because that clause never references `record.version` at all, and the ordinary (non-stale) case would let such a write through, silently moving the persisted version backward. Version 1.2 added an explicit, unconditional precondition rejecting that case in Python before any SQL executes.

**Version 1.3 note:** an independent final re-review of Version 1.2 (correction commit `0f5c982a23f1b8c51ed5d56ff0a0cdab0c03c4bb`) returned "M023 DESIGN REQUIRES ANOTHER NARROW CORRECTION" with exactly one remaining documentation ambiguity: Version 1.2's canonical `save()` sequence described both success branches "Return `SaveResult(...)`" ahead of the separately-listed final "Commit" step, letting a reader conclude the result could be constructed before the transaction was durably committed. This version rewrites `save()`'s sequence so no step before a successful `commit()` ever constructs or returns a `SaveResult`. Section 21 records this and every prior finding; the selected scope (Section 8 of the Scope Selection) remains unchanged and was not reopened.

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
8. **A durable record whose version is lower than the caller's `expected_persisted_version` is invalid aggregate state for persistence, rejected before any SQL is executed** (Section 8 step 3) — it is not, and must never be classified as, a stale-write conflict (`OptimisticConcurrencyConflict`), because no SQL predicate can express a check against `record.version` (the value being written) the way the guarded `UPDATE`'s `WHERE` clause expresses a check against the durable, already-stored version.

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

Given `aggregate` and `expected_persisted_version: AggregateVersion`, in exactly this order. **No step below step 10 constructs or returns a `SaveResult`; `SaveResult` represents successfully committed durable state, never merely-attempted state, and is therefore never available to any branch before commit succeeds (Design Issue 0014, Section 21).**

1. Determine `aggregate_kind` and `identity` from the aggregate (both already carried by the frozen aggregate/identity types; no lookup required).
2. Call `mapper.to_durable_record(aggregate)` to obtain `record`. If it raises `MapperError`: raise `InvalidAggregateForPersistence(aggregate_kind=..., reason=mapper_error.safe_message)`. No transaction opened yet; nothing is returned.
3. **Reject `record.version < expected_persisted_version` before any transaction is opened** (this precondition check, and every step above it, happens entirely in Python, with no transaction open and no statement sent to PostgreSQL yet):
   ```text
   if record.version < expected_persisted_version:
       raise InvalidAggregateForPersistence(
           aggregate_kind=aggregate_kind,
           reason="aggregate current version is lower than expected persisted version",
           identity=identity,
       )
   ```
   **This check is not redundant with the guarded `UPDATE`'s `WHERE version = :expected_persisted_version` clause (step 6).** That clause compares the *durable, database-resident* version to `expected_persisted_version` — it says nothing at all about `record.version`, the value the SQL's `SET` clause is about to *write*. A design that omitted this check could let the `WHERE` clause match (whenever the durable version genuinely equals `expected_persisted_version`, the ordinary non-stale case) regardless of what `record.version` is, and the `SET version = :record_version` clause would then silently persist a version *lower* than what is already durably stored — corrupting the optimistic-concurrency invariant that `AggregateVersion` values only ever advance (Design Issue 0013, Section 21). This precondition, checked before opening a transaction, is the only place this corruption can be prevented, because no SQL predicate can express "reject based on a value (`record.version`) that does not participate in the `WHERE` clause at all." Nothing is returned here either.
4. Classify the *intended* outcome, assuming the guarded `UPDATE` below succeeds (Design Principle 7 — an integer comparison, never a content diff). This classification is recorded for use after commit (step 11); it is not returned now:
   - `record.version == expected_persisted_version` -> intended outcome is `SaveOperation.UNCHANGED`.
   - `record.version > expected_persisted_version` -> intended outcome is `SaveOperation.UPDATED`.
   (Step 3 has already excluded the third possibility, `record.version < expected_persisted_version`, so exactly one of these two branches is reachable here.)
5. Open one `PostgresUnitOfWork`.
6. Execute the single guarded write-or-fail statement, unconditionally, for both branches of step 4 alike (Section 9.1's race-safety reasoning explains why this always executes, even for the intended-`UNCHANGED` branch):
   ```sql
   UPDATE x
   SET <every non-key root column> = <value from record>,
       version = :record_version
   WHERE runtime_id = :runtime_id
     AND governance_id = :governance_id
     AND version = :expected_persisted_version
   RETURNING version
   ```
   `:record_version` is `record.version` exactly — never `version + 1`, never any repository-computed increment (Design Principle 5). Because step 3 already guaranteed `record.version >= expected_persisted_version`, this statement can only ever hold the durable version steady (intended-`UNCHANGED` branch) or advance it (intended-`UPDATED` branch); it can never move it backward.
7. **If the `UPDATE` returned zero rows**, classify the failure with one diagnostic follow-up in the same transaction — this is the genuine, distinct "stale expected version" case, never to be confused with step 3's "invalid aggregate state" rejection (which never reaches SQL at all):
   ```sql
   SELECT governance_id, version
   FROM x
   WHERE runtime_id = :runtime_id
   ```
   - Zero rows: raise `AggregateNotFound(aggregate_kind=..., identity=identity)`.
   - One row, whose `governance_id` differs from `identity.governance_id`: raise `InvalidPersistedAggregateState(aggregate_kind=..., reason="persisted governance_id does not match the aggregate's identity for this runtime_id", identity=identity)`.
   - One row, whose `governance_id` matches but whose `version` differs from `expected_persisted_version`: raise `OptimisticConcurrencyConflict(aggregate_kind=..., identity=identity, expected_persisted_version=expected_persisted_version, aggregate_current_version=AggregateVersion(record.version), actual_persisted_version=AggregateVersion(that row's version))`.
   All three paths roll back (via `PostgresUnitOfWork.__exit__`'s existing exception-path behavior, Section 11) before raising; **nothing is returned on any of these paths.** See Section 9.1 for why this two-statement (guarded-`UPDATE`-then-diagnostic-`SELECT`) ordering is race-safe.
8. **If the `UPDATE` returned exactly one row and step 4's intended outcome was `UPDATED`** (`record.version > expected_persisted_version`): delete every owned-collection row for this parent (`DELETE FROM x_c WHERE <parent_fk_column> = :runtime_id`, one statement per child table, in reverse creation order) and re-insert the durable record's current collection state (identical rule to `add()` step 4). If any of these statements raises, it is handled exactly as step 7 handles a failure: roll back, translate/raise per Section 9, **return nothing.** **If step 4's intended outcome was `UNCHANGED`, this step is skipped entirely — owned-collection tables are never touched for an unchanged save.**
9. Prepare, in memory only, the values `SaveResult` will need — `operation` (step 4's intended outcome, `SaveOperation.UNCHANGED` or `SaveOperation.UPDATED`) and `persisted_version` (`AggregateVersion(record.version)`) — **without constructing or returning a `SaveResult` yet.**
10. Commit. This is the one and only point at which the operation's durable success is real. If `commit()` raises, that exception (an untranslated-further `FoundationError`, per `PostgresUnitOfWork`'s existing contract) propagates from `save()` exactly as raised; **no `SaveResult` is constructed or returned on this path,** because a `SaveResult` represents committed durable state and none exists if commit itself failed.
11. **Only now**, after step 10's `commit()` has returned successfully, construct and return `SaveResult(operation=<step 9's operation>, persisted_version=<step 9's persisted_version>)`.

Explicitly, restated for clarity (each already established by a specific step above, gathered here as the acceptance criteria for a future implementation, Section 22):

- **`SaveResult` is returned by exactly one statement in this entire algorithm (step 11), and only after step 10's `commit()` has already succeeded** — no branch of steps 2-9 ever constructs or returns one; every failure path (steps 2, 3, 7, 8, and a step-10 commit failure) raises without ever producing a `SaveResult`;
- the repository never increments `AggregateVersion` — the value written and later reported is always `record.version` as-is (step 6, step 9);
- `record.version < expected_persisted_version` is invalid aggregate state for persistence, not a stale-write conflict — it is rejected in step 3, before any transaction is opened, and raises `InvalidAggregateForPersistence`, never `OptimisticConcurrencyConflict`;
- a stale `expected_persisted_version` (durable version differs from what the caller believes, with `record.version >= expected_persisted_version`) is still detected, atomically, by the guarded `UPDATE` in step 6/7 — step 3's precondition does not weaken or bypass this;
- lower-version rejection (step 3, `InvalidAggregateForPersistence`, no transaction opened) and optimistic-concurrency conflict (step 7, `OptimisticConcurrencyConflict`, inside an opened-and-rolled-back transaction) are distinct errors raised by distinct, non-overlapping conditions and can never be confused with each other;
- **an unchanged save (`UNCHANGED`) still commits the guarded root `UPDATE` (step 6) before step 11 returns** — "unchanged" describes the durable value, not whether a real `COMMIT` occurred;
- **an updated save (`UPDATED`) commits both the root row (step 6) and every owned-collection change (step 8) in the same transaction, atomically, before step 11 returns** — never partially;
- if `commit()` fails (step 10), or if the guarded `UPDATE`/child-collection statements fail before it (steps 6-8), the transaction is rolled back (`PostgresUnitOfWork`'s existing `__exit__`/`rollback()` behavior, Section 11) and the operation raises rather than returning — **no `SaveResult` is ever returned for an operation that did not durably commit**, and no repository-domain success is ever reported after a rollback or a failed commit;
- if `rollback()` itself fails, `PostgresUnitOfWork`'s own existing failure semantics apply unchanged (Section 11) — this design adds no additional handling and, consistent with every other failure path above, never reports success in that case either;
- the caller's aggregate object is never mutated by any branch of `save()`, including every rejection/failure path — `mapper.to_durable_record()` (step 2) is a pure read of the aggregate's current state (M021, frozen), and nothing in this design writes back to the aggregate afterward.

## 9. Error Translation

### 9.1 Race-Safety Rationale for `save()`'s Statement Ordering

A **`SELECT`-then-`UPDATE`** ordering (read the current version, decide in application code whether to write, then write) is not race-safe: another transaction could commit between the `SELECT` and the `UPDATE`, making the decision stale by the time the `UPDATE` executes. This design therefore always executes the guarded `UPDATE ... WHERE version = :expected_persisted_version RETURNING version` (Section 8 step 6) — this statement is itself PostgreSQL's atomic compare-and-set primitive: whether it matches a row is decided and acted upon in one indivisible operation, with no window in which another writer could invalidate the decision after it was made. (Section 8 step 3's `record.version < expected_persisted_version` precondition runs strictly *before* this, in Python, with no SQL involved at all — a separate, non-racing, purely in-memory check, not part of this race-safety analysis.) The **only** thing decided *after* the write attempt is which error to report when it affected zero rows (Section 8 step 7) — a diagnostic classification, not a decision about whether to write. Even if a concurrent transaction commits between the failed `UPDATE` and the diagnostic `SELECT`, every possible outcome of that `SELECT` still describes a real, valid state of the row at-or-after the `UPDATE`'s own evaluation instant, so the caller always receives a truthful rejection (`AggregateNotFound`, `OptimisticConcurrencyConflict`, or `InvalidPersistedAggregateState`) — never an incorrect success and never a silently-wrong `SaveResult`. This is the same pattern used by conditional-update-based optimistic concurrency generally; it is chosen over a single CTE-based statement combining the write and the diagnostic read because PostgreSQL does not guarantee a same-statement `SELECT` in a `WITH` clause observes a data-modifying CTE's own effects (the write and read sub-statements of one `WITH` execute against a shared snapshot, not a read-after-write view of each other), which would make a CTE-based version *harder* to reason about correctly, not easier, for a purely diagnostic follow-up.

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
| `record.version < expected_persisted_version` on `save()` (Section 8 step 3) | Direct comparison in Python, before any transaction is opened or SQL executed | `InvalidAggregateForPersistence(aggregate_kind, reason="aggregate current version is lower than expected persisted version", identity)` |
| Root row absent on `save()` (Section 8 step 7) | Zero rows from the runtime_id-only diagnostic `SELECT` | `AggregateNotFound(aggregate_kind, identity)` |
| Persisted identity mismatch on `save()` (Section 8 step 7) | Diagnostic `SELECT` finds a row with a different `governance_id` | `InvalidPersistedAggregateState(aggregate_kind, reason, identity)` |
| Stale expected version on `save()` (Section 8 step 7) | Diagnostic `SELECT` finds the identity matches but `version` differs (only reachable when `record.version >= expected_persisted_version`, per step 3) | `OptimisticConcurrencyConflict(..., actual_persisted_version=<that row's version>)` |
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
- **lower durable version is rejected before any SQL**: construct (via direct test-only means, since the frozen aggregate/mapper contracts cannot produce this on their own) a `record.version < expected_persisted_version` scenario and assert `InvalidAggregateForPersistence` is raised (Section 8 step 3), with a message equivalent to "aggregate current version is lower than expected persisted version" and no SQL/driver/backend detail in it (Section 9.4);
- **no SQL statement executes in the lower-version branch**: assert (e.g. via a query-count/spy on the connection, or by asserting no `PostgresUnitOfWork` was ever opened for that call) that step 3's rejection produces zero database round trips;
- **unchanged save still performs optimistic-concurrency validation**: `add()`, `get()`, `save()` immediately with the just-loaded `expected_persisted_version` and no aggregate mutation — assert `SaveResult(operation=UNCHANGED, persisted_version=<unchanged version>)`, that the guarded `UPDATE` of Section 8 step 6 still executed and its transaction actually committed (Section 8 step 10) before that `SaveResult` was returned (Section 8 step 11) — proving validation is never skipped merely because the values are equal — and that no owned-collection row was rewritten;
- **stale expected version cannot be reported as `UNCHANGED`**: two independent `LoadedAggregate`s at the same version; the first `save()`s a real mutation; the second then attempts an "unchanged" `save()` (no local mutation, but a now-stale `expected_persisted_version`, and still `record.version >= expected_persisted_version` so step 3 does not reject it) and must receive `OptimisticConcurrencyConflict`, not `UNCHANGED` — proving Section 8 step 7's classification never lets a stale caller slip through;
- **greater version persists the exact aggregate current version**: after one or more real mutations, `save()` and assert the persisted `version` column equals `record.version` exactly (not `expected_persisted_version + 1` or any repository-computed value);
- **repository never increments the version**: across every `save()` test above, assert the persisted version is always traceable to a value the aggregate itself produced via its own business methods, never a value invented by the repository;
- **caller aggregate remains unchanged after rejection**: after a step-3 lower-version rejection, assert the in-memory `aggregate` object passed to `save()` is byte-for-byte identical (identity, version, lifecycle state, owned collections) to its state immediately before the call;
- **`SaveResult` is returned only after commit succeeds**: for both the `UNCHANGED` and `UPDATED` branches, assert (e.g. by instrumenting or wrapping `PostgresUnitOfWork.commit()`) that `commit()` has already returned before `save()` produces a `SaveResult`, and that no `SaveResult` object exists anywhere in the call if `commit()` is made to raise;
- **commit failure returns no `SaveResult`**: force `commit()` (step 10) to raise (e.g. by closing the underlying connection immediately beforehand, or another real-PostgreSQL-compatible fault injection) and assert `save()` raises the resulting `FoundationError` and never returns any value, `SaveResult` or otherwise;
- **`UNCHANGED` commits before returning**: for the `UNCHANGED` branch specifically, assert the guarded root `UPDATE` (step 6) is durably visible in a separate connection immediately after `save()` returns (proving the transaction was actually committed, not merely attempted) before trusting the returned `SaveResult`;
- **`UPDATED` commits root and child changes together before returning**: for the `UPDATED` branch, assert both the root row's new version and every owned-collection row's new state (step 8) are durably visible in a separate connection immediately after `save()` returns, and that a forced failure during the child-collection replacement (step 8) leaves neither the root row's version advanced nor any child row changed (full rollback, no `SaveResult` returned);
- **rollback occurs on child-write failure**: a forced failure during step 8's `DELETE`/`INSERT` sequence must leave the database in the exact pre-`save()`-call state (including the root row's version, unchanged from before the call) and must not return a `SaveResult`;
- **no successful operation is reported after rollback or commit failure**: across every forced-failure scenario above, assert specifically that no code path returns a `SaveOperation`/`SaveResult` value — only a raised exception;
- optimistic-concurrency conflict on a real mutation (existing case, retained);
- `add()` duplicate rejection, both by duplicate `governance_id` and by duplicate `runtime_id` independently, each asserting the specific constraint-name branch in Section 9.2 fired;
- `get()`/`save()` not-found (identity never added);
- **identity mismatch**: a `get()`/`save()` against a `runtime_id` that exists but paired with a different `governance_id` than requested (constructed by direct SQL setup, since this cannot arise through the frozen mapper/aggregate contracts alone) must raise `InvalidPersistedAggregateState`, not `AggregateNotFound`;
- owned-collection ordering preserved end-to-end through the full mapper-and-schema round trip;
- atomicity of a simulated mid-write failure during `add()`/`save()`;
- every row of Section 9.3's error-translation table, proven against real PostgreSQL.

These are design-level implementation *obligations* for a future implementation milestone; this design does not write or execute any test.

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
| M023-DESIGN-ISSUE-0006 | MAJOR | 8 | Version 1.0 explicitly deferred `SaveOperation.UNCHANGED` as unsolved, despite M020 Design Section 18 already freezing its exact semantics. | M020 Design Section 18: "`aggregate current version == expected persisted version` is a valid unchanged save... Implementations may avoid physical writes for unchanged saves, but they must still validate." | Left unresolved, a future implementer would either invent an inconsistent algorithm or skip the required expected-version validation for the equal-version case, risking a false `UNCHANGED` under a concurrent conflict. | Added the full canonical algorithm (Section 8): the guarded `UPDATE` always runs (so validation always happens), classification is a post-hoc integer comparison, and owned-collection tables are skipped only in the `UNCHANGED` branch. Added the corresponding test case (Section 15). | Resolved |
| M023-DESIGN-ISSUE-0007 | MAJOR | 6, 8, 12 | Version 1.0's `get`/`save` predicates matched on `runtime_id` alone. | `runtime_id`-only matching cannot detect a persisted row whose `governance_id` disagrees with the requested identity — exactly the corruption M020's uniqueness rule is meant to make impossible, silently hidden instead of surfaced. | A caller with a stale/incorrect `DomainIdentity` pairing could silently operate on the wrong logical identity's data. | Added Design Principle 6; corrected every predicate to include both components; added the identity-mismatch diagnostic branch and its `InvalidPersistedAggregateState` classification (Sections 6, 8, 9.3); added the corresponding test case (Section 15). | Resolved |
| M023-DESIGN-ISSUE-0008 | MAJOR | 7, 9 | Version 1.0's `add()` duplicate detection referenced `.orig.diag.constraint_name` only in prose, without a stable, exhaustive dispatch table, and without stating the SQLSTATE precondition. | An implementer could parse error message text (unstable across PostgreSQL versions/locales) instead of the stable `sqlstate`/`constraint_name` diagnostic fields, or could incorrectly map an unrelated future unique-constraint violation to `AggregateAlreadyExists`. | Fragile, locale/version-dependent detection, or silent misclassification of an unrelated failure as identity duplication. | Added Section 9.2's exact SQLSTATE (`23505`) precondition and exhaustive constraint-name dispatch table, with an explicit "unknown uniqueness violation remains untranslated" fallback. | Resolved |
| M023-DESIGN-ISSUE-0009 | MAJOR | 5 | Version 1.0 stated, within the same section, both "no architecture-checker change of any kind is required" and that `ALLOWED["shared"]` needed a new entry. | Direct re-reading of Version 1.0 Section 5.2 confirms the contradiction verbatim. | A reviewer or implementer could reasonably act on either half of the contradiction and be wrong either way; independent review correctly flagged this. | Rewrote Section 5 to state the one required change (`ALLOWED["shared"]` gaining four names) exactly once, consistently, cross-referenced from every section that touches it (5.2, 16, 20), with an explicit comparison against Options A and C explaining why B is still correct despite requiring this one change. | Resolved |
| M023-DESIGN-ISSUE-0010 | MINOR | 9 | Version 1.0 did not explicitly analyze whether its zero-row handling was race-safe, despite already using an `UPDATE`-first ordering. | Independent review asked for an explicit race analysis; the ordering was already correct but undefended in the text. | A reader could not distinguish "correct by design" from "correct by accident" without the reasoning being stated. | Added Section 9.1, explicitly contrasting the chosen `UPDATE`-then-diagnostic-`SELECT` ordering against both a `SELECT`-then-`UPDATE` race and a same-statement CTE alternative, with the reasoning for rejecting the latter (cross-CTE snapshot visibility is not guaranteed to reflect the write). | Resolved |
| M023-DESIGN-ISSUE-0011 | MINOR | 10 | Version 1.0 deferred the field-by-field mapping entirely to M021/M022's own documents rather than restating it, and its prose example had `ORDER BY` before `WHERE` (invalid SQL clause order). | Independent review required a complete, self-contained mapping table and correct clause order. | An implementer would need to reconstruct the mapping by cross-referencing two other documents, and a naive prose reading could produce invalid SQL. | Added the complete per-table field mapping (Section 10) and corrected every query's clause order to `SELECT ... FROM ... WHERE ... ORDER BY`. | Resolved |
| M023-DESIGN-ISSUE-0012 | MINOR | 9 | Version 1.0 did not explicitly state that repository-domain error messages never leak SQL/driver/diagnostic detail, even though its own design did not actually leak any. | Independent review required this to be frozen explicitly, not left implicit. | An implementer without this stated explicitly might reasonably embed `sqlstate`/`constraint_name`/raw driver text into a `reason=` string for debugging convenience, leaking infrastructure detail through a domain-facing error. | Added Section 9.4, freezing that `reason=` values are always `mapper_error.safe_message`, `str(reconstruction_error)`, or a repository-authored literal — never SQL/driver text. | Resolved |
| M023-DESIGN-ISSUE-0013 | MAJOR | 8 | Version 1.1's closing paragraph for `save()` incorrectly asserted that `record.version < expected_persisted_version` "would simply fail to match" the guarded `UPDATE`'s `WHERE` clause and therefore needed no special handling. | False upon inspection: the `WHERE` clause compares the *durable* version to `expected_persisted_version` only; it never references `record.version` at all. When the durable version genuinely equals `expected_persisted_version` (the ordinary case), the guarded `UPDATE` matches regardless of `record.version`, and `SET version = :record_version` would then silently persist a version *lower* than what is already stored — moving a supposedly monotonic `AggregateVersion` backward. | An implementation following Version 1.1's reasoning verbatim would contain a real, silent version-corruption defect: no SQL predicate this design used could have caught it. | Added Section 8 step 3: an explicit, unconditional Python-level precondition (`record.version < expected_persisted_version` -> `InvalidAggregateForPersistence`, no transaction opened, no SQL executed) that runs before the guarded `UPDATE`; added Design Principle 8; removed the false closing paragraph; added the corresponding row to Section 9.3 and the corresponding tests to Section 15. | Resolved |
| M023-DESIGN-ISSUE-0014 | MAJOR | 8 | Version 1.2's canonical `save()` sequence described returning `SaveResult` in the same steps (7 and 8, as then numbered) that preceded the explicit "Commit" step (9) — a reader could reasonably conclude the result was constructed and returned *before* the transaction was durably committed. | Direct re-reading of Version 1.2 Section 8 confirms both success branches said "Return `SaveResult(...)`" ahead of the separately-listed final "Commit" step. | If an implementation followed this literally (or even just the ambiguity it left open), a caller could receive a `SaveResult` reporting success for a transaction that subsequently failed to commit — a false-success report for data that was never durably persisted, and specifically for `add()`/`save()`'s owned-collection writes (step 8, previously step 6/8), a false report even though the root row and child rows might not agree if commit partially applied in some future variant. | Rewrote Section 8 as an explicit 11-step sequence in which no step before step 10 (`commit()`) ever constructs or returns a `SaveResult`; step 9 explicitly prepares the values in memory only, and step 11 is the sole point that constructs and returns `SaveResult`, reachable only after step 10 has already succeeded. Added explicit restated bullets covering every failure/rollback path (steps 2, 3, 7, 8, 10) confirming none of them ever returns a `SaveResult`. Added the corresponding tests to Section 15 and the corresponding acceptance-gate line to Section 22. | Resolved |

No unresolved design finding remains.

## 22. Implementation Acceptance Gate (for a future Implementation milestone, not satisfied by this design)

A future implementation milestone must demonstrate, before it may be considered for freeze:

- every operation in Sections 6-8 implemented exactly as specified, for all four aggregates, including the corrected version semantics (never incrementing), the lower-version precondition (Section 8 step 3), the `UNCHANGED` algorithm, the commit-before-return ordering (Section 8 steps 9-11), and the full-identity predicates;
- every row of Section 9.3's error-translation table proven against real PostgreSQL, including the lower-version rejection, both duplicate-identity sub-cases (Section 9.2), and both identity-mismatch sub-cases (Sections 6/8);
- the concurrent-conflict-during-unchanged-save test (Section 15) passing, proving no stale caller can be misclassified as `UNCHANGED`;
- the lower-durable-version test (Section 15) passing, proving the rejection happens before any SQL and never corrupts the persisted version;
- the commit-before-return tests (Section 15) passing, proving `SaveResult` is never constructed or returned until after `commit()` has already succeeded, for both the `UNCHANGED` and `UPDATED` branches, and that a forced commit or child-write failure returns no `SaveResult` and leaves no partial durable state;
- the one narrow `ALLOWED["shared"]` architecture-checker change made, together with the one new negative fixture (Section 5.3), verified not to weaken any `FORBIDDEN_IMPORT_PREFIXES` rule;
- no frozen M019, M020, M021, or M022 file modified.

## 23. Final Decision

```text
DESIGN READY FOR INDEPENDENT FINAL RE-REVIEW
```

NOT APPROVED. NOT FROZEN. No repository, mapper, migration, or Unit of Work code was created by this design.
