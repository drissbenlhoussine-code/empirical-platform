# MILESTONE-023 - PostgreSQL Repository Adapter Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-023 |
| Title | PostgreSQL Repository Adapter Design |
| Version | 1.0 |
| Status | DESIGN READY FOR INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `10425e85b63a0b6f18b73b962355f22176cb279c` |
| Baseline status | MILESTONE-022 APPROVED AND FROZEN |
| Mission type | Design only |
| Repository code, mapper code, migrations, Unit of Work created | No |

## 2. Baseline

This design builds on, without altering:

- M019's frozen `_reconstruct_<aggregate>(state) -> <Aggregate>` factories and `<Aggregate>ReconstructionState` types;
- M020's frozen `<Aggregate>Repository` Protocols (`get`/`add`/`save`) and `LoadedAggregate`/`SaveOperation`/`SaveResult`/`RepositoryContractError` hierarchy (`AggregateNotFound`, `AggregateAlreadyExists`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, `InvalidPersistedAggregateState`);
- M021's frozen `<Aggregate>Mapper` Protocols (`to_durable_record`/`from_durable_record`), `<Aggregate>DurableRecord` types (and nested `DatasetManifestDurableRecord`, `CriterionResultDurableRecord`, `ReviewFindingDurableRecord`, shared `IdentityDurableRecord`/`TransitionDurableRecord`), and `MapperError`/`MapperErrorCategory`;
- M022's frozen twelve-table PostgreSQL schema and single migration revision (`5b58cdd7751b`);
- `empirical_platform.shared.persistence.postgres.PostgresPersistenceService`/`PostgresUnitOfWork`, verified live: `unit_of_work()` returns a context-managed `PostgresUnitOfWork` with `execute(statement, parameters) -> Sequence[Mapping[str, object]]`, `commit()`, `rollback()`; every exception raised inside `execute()` is translated via `translate_persistence_error()` into a `FoundationError` (category `PERSISTENCE`), which preserves the original exception only via Python's standard `__cause__` chaining, not as a structured field.

## 3. Problem Statement

M020 specifies *what* a repository must do (`get`/`add`/`save`, exact error vocabulary). M021 specifies *how an aggregate becomes persistence-neutral data* (`DurableRecord`) and back. M022 specifies *where that data physically lives* (twelve tables, exact columns and constraints). Nothing yet specifies how a concrete repository implementation bridges these three frozen artifacts: how a `DurableRecord`'s fields become SQL parameters against the M022 schema (and the reverse), how the M020 error vocabulary is produced from real PostgreSQL failures (which, per Section 2, do not arrive as raw driver exceptions), how optimistic concurrency is actually enforced, and where such an implementation module may live given the architecture checker's existing import-boundary rules. This design answers those questions without writing the implementation itself.

## 4. Design Principles

1. **No frozen artifact is altered.** This design adds a bridging layer between M020, M021, and M022; it does not reinterpret any of the three.
2. **The frozen call chain is completed, not changed.** `repository implementation -> mapper -> ReconstructionState -> _reconstruct_* -> aggregate` (M019 Design, M021 Design Section 14) is the exact shape a concrete `get()` follows; this design specifies the repository-side steps before and after the mapper call, not a different chain.
3. **One repository operation is one transaction.** `get()`, `add()`, and `save()` each open exactly one `PostgresUnitOfWork` and commit or roll back once; no operation spans multiple `with ... unit_of_work()` blocks, and no new multi-statement/multi-aggregate Unit of Work is introduced (Candidate D, M023 Scope Selection Section 7, remains deferred).
4. **Full-replace for owned collections.** A `DurableRecord`'s owned collections (transition history, manifests, criterion results, artifact references, findings) carry no per-item version or removal marker; the frozen contracts do not distinguish "this manifest changed" from "this manifest is new." Consequently `save()` deletes and re-inserts every owned-collection row for a parent rather than attempting an incremental diff — the only strategy consistent with the frozen `DurableRecord` shape without extending it.
5. **`runtime_id` is the primary access-path key.** Every table's own primary key is `runtime_id` (M022 Design Section 6); `governance_id` carries its own `UNIQUE` constraint and is used for cross-aggregate FK references and duplicate detection, but `get()`/`save()` address a row by `runtime_id`, since `DomainIdentity` always carries both and `runtime_id` is the schema's actual primary key.

## 5. Repository Placement and Architecture Boundary

### 5.1 The Problem

`tools/check_architecture.py`'s `FORBIDDEN_IMPORT_PREFIXES` table forbids `campaign`, `run`, `evidence`, and `review` (and `shared`, outside `shared.domain`) from importing `sqlalchemy`, `psycopg`, `boto3`, or `empirical_platform.shared.persistence`. A concrete repository implementation inherently needs `sqlalchemy` (to build parameterized statements) and `empirical_platform.shared.persistence` (to use `PostgresUnitOfWork`). Placing it inside `campaign/repository.py` itself (next to the frozen Protocol) would either violate the existing rule or require weakening it for the whole `campaign` package — reopening the exact same door to domain-layer persistence leakage M019-M022 have consistently kept closed.

### 5.2 Resolution

A concrete repository implementation for aggregate `X` lives at `empirical_platform.shared.persistence.postgres_repositories.<x>_repository` (one module per aggregate, e.g. `postgres_repositories/campaign_repository.py`), inside the existing `shared.persistence` sub-package that already legitimately imports `sqlalchemy`/`psycopg`/`empirical_platform.shared.persistence` internals — no new top-level package, no change to `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` is required, because `shared.persistence` is already the one place in the tree where these imports are expected. `check_architecture.py`'s `module_for_path` classifies every file under `src/empirical_platform/<top-level>/...` by `<top-level>` alone, so a new subdirectory under `shared/persistence/` remains classified as `shared`; since `shared`'s forbidden-import check only applies "if `'domain' not in path.parts`" (`check_architecture.py` line 121-122), a file under `shared/persistence/...` is already exempted by the checker's own existing logic. **No architecture-checker change of any kind is required or proposed by this design.**

The concrete repository class imports its aggregate's Protocol module (e.g. `from empirical_platform.campaign.repository import CampaignRepository`) only to declare Protocol conformance in tests, and imports its aggregate's mapper module (e.g. `from empirical_platform.campaign.mapper import CampaignMapper, CampaignDurableRecord`) — both already-permitted `shared -> campaign` style imports are not needed, since `shared.persistence` importing `campaign` is the reverse direction from the forbidden one (`campaign` importing `shared.persistence`); `ALLOWED["shared"]` is the empty set today, so this direction needs the same one-line, narrow, disclosed acknowledgment M020/M021 already carry ("same-top-level-module imports are always permitted; cross-module imports follow the `ALLOWED` table") — concretely, `shared.persistence` importing `campaign.mapper`/`campaign.repository` requires `"shared": {"campaign", "run", "evidence", "review"}` (currently `set()`) in `ALLOWED`. **This is the one narrow, explicit, disclosed architecture-checker adjustment this design requires**, and it only widens what `shared` may import, not what `campaign`/`run`/`evidence`/`review` may import — the existing, correct direction of restriction (domain packages may not reach into persistence) is unaffected.

### 5.3 What This Design Does Not Decide

Whether the four concrete repository classes share a common base class or duplicate a small amount of structurally-identical code (root CRUD plus per-aggregate child-table handling) is an implementation-time decision, not a design-time one; Section 6 specifies the exact steps each operation takes per aggregate, which a future implementation may factor however it chooses as long as the steps and their order are unchanged.

## 6. Operation Design: `get`

For aggregate `X` with root table `x`, owned child tables `x_c1, x_c2, ...` (each with a `position` or `sequence` ordering column per M022):

1. Open one `PostgresUnitOfWork`.
2. `SELECT * FROM x WHERE runtime_id = :runtime_id`. If zero rows: raise `AggregateNotFound(aggregate_kind=..., identity=identity)`, roll back, return.
3. For each owned child table, `SELECT * FROM x_c ORDER BY position` (or `sequence`) `WHERE <parent_fk_column> = :runtime_id`.
4. Assemble an `<X>DurableRecord` from the root row's columns and each child table's ordered rows, constructing `IdentityDurableRecord(governance_id=root.governance_id, runtime_id=str(root.runtime_id))` and one `TransitionDurableRecord` per `x_transition` row (ordered by `sequence`).
5. Call `mapper.from_durable_record(record)`. If it raises `MapperError`: raise `InvalidPersistedAggregateState(aggregate_kind=..., reason=str(mapper_error), identity=identity)` from it, roll back, return.
6. Call `_reconstruct_x(state)` (the aggregate's own frozen, package-internal factory). If it raises `ReconstructionError`: raise `InvalidPersistedAggregateState(aggregate_kind=..., reason=str(reconstruction_error), identity=identity)` from it, roll back, return.
7. Commit (a `get()` performs no writes; committing only releases the transaction cleanly rather than leaving it open).
8. Return `LoadedAggregate(aggregate=aggregate, persisted_version=AggregateVersion(root.version))`.

Both `MapperError` (Section 2; M021 `mapping.py`'s own docstring: "A future repository implementation... is responsible for wrapping `MapperError` into `InvalidPersistedAggregateState` or `InvalidAggregateForPersistence`") and `ReconstructionError` are wrapped identically on the read path, because both represent "durable data could not be safely turned back into a valid aggregate" from the repository's vantage point — the M020 error vocabulary does not distinguish which internal stage of reconstruction failed, only that persisted state was invalid.

## 7. Operation Design: `add`

1. Call `mapper.to_durable_record(aggregate)`. If it raises `MapperError`: raise `InvalidAggregateForPersistence(aggregate_kind=..., reason=str(mapper_error))`, no transaction opened yet.
2. Open one `PostgresUnitOfWork`.
3. `INSERT INTO x (...) VALUES (...)` using the durable record's root-level fields.
4. For each owned collection, one `INSERT` per element, in the collection's existing tuple order, writing `position`/`sequence` as the element's index (or its own frozen `sequence` field, where the durable record already carries one — e.g. `ReviewFindingDurableRecord.sequence`, `TransitionDurableRecord.sequence`).
5. If any `INSERT` raises (via `PostgresUnitOfWork.execute()`, surfaced as `FoundationError`): inspect `error.__cause__` (see Section 9). If it indicates a unique-constraint violation on the root table's `governance_id` or `runtime_id`: raise `AggregateAlreadyExists(aggregate_kind=..., identity=identity)`; the transaction is already rolled back by `PostgresUnitOfWork.__exit__`'s exception path. Any other translated error propagates as the `FoundationError` it already is — this design does not invent new handling for infrastructure-level failures (connection loss, etc.), consistent with `PostgresUnitOfWork`'s existing contract.
6. Commit.
7. Return `SaveResult(operation=SaveOperation.CREATED, persisted_version=AggregateVersion(<the version value just written>))`.

`add()` performs no pre-check `SELECT` for existence: the root table's `UNIQUE` constraints on `governance_id` and its `PRIMARY KEY` on `runtime_id` are the actual source of truth, and relying on them (rather than a check-then-insert race) is both simpler and free of a TOCTOU race under concurrent `add()` calls for the same identity.

## 8. Operation Design: `save`

1. Call `mapper.to_durable_record(aggregate)`. If it raises `MapperError`: raise `InvalidAggregateForPersistence(...)`, no transaction opened yet.
2. Open one `PostgresUnitOfWork`.
3. `UPDATE x SET <every non-key column> = <value>, version = version + 1 WHERE runtime_id = :runtime_id AND version = :expected_persisted_version`, and read the row count `execute()` reports (`PostgresUnitOfWork.execute()` returns `Sequence[Mapping[str, object]]` for `RETURNING`-bearing statements; this design specifies the guarded `UPDATE` includes `RETURNING version` so the new version and whether any row matched are both known from one round trip).
4. If the `UPDATE ... RETURNING` returned zero rows: run `SELECT version FROM x WHERE runtime_id = :runtime_id`.
   - Zero rows: raise `AggregateNotFound(aggregate_kind=..., identity=identity)`.
   - One row, with `version != expected_persisted_version`: raise `OptimisticConcurrencyConflict(aggregate_kind=..., identity=identity, expected_persisted_version=expected_persisted_version, aggregate_current_version=AggregateVersion(durable_record.version), actual_persisted_version=AggregateVersion(that row's version))`.
   Both paths roll back before raising.
5. If the guarded `UPDATE` returned exactly one row: delete every owned-collection row for this parent (`DELETE FROM x_c WHERE <parent_fk_column> = :runtime_id`, one statement per child table) and re-insert the durable record's current collection state, identically to `add()` step 4.
6. Commit.
7. Return `SaveResult(operation=SaveOperation.UPDATED, persisted_version=AggregateVersion(<the version RETURNING reported>))`.

`save()` never returns `SaveOperation.UNCHANGED` under this design: the frozen `SaveOperation` vocabulary includes it, but nothing in the frozen aggregate/mapper contracts exposes "no field actually changed since load" as information the repository can obtain without an aggregate-shaped diff the frozen types do not provide (mirroring Section 4's owned-collection reasoning). A future implementation milestone that wants to detect true no-op saves would need its own narrow design extension; this design does not claim to solve that and explicitly defers it (Section 21).

## 9. Error Translation

| Failure | Detected how | Raised as |
| --- | --- | --- |
| `mapper.to_durable_record()` raises `MapperError` | Direct catch, no transaction involved | `InvalidAggregateForPersistence(aggregate_kind, reason=str(err))` |
| `mapper.from_durable_record()` raises `MapperError` | Direct catch, inside the `get()` transaction | `InvalidPersistedAggregateState(aggregate_kind, reason=str(err), identity)` |
| `_reconstruct_x()` raises `ReconstructionError` | Direct catch, inside the `get()` transaction | `InvalidPersistedAggregateState(aggregate_kind, reason=str(err), identity)` |
| Root row not found on `get()` | Zero rows from the root `SELECT` | `AggregateNotFound(aggregate_kind, identity)` |
| Root row not found on `save()` | Zero rows from the post-guard `SELECT` (Section 8 step 4) | `AggregateNotFound(aggregate_kind, identity)` |
| Version mismatch on `save()` | Guarded `UPDATE` affects zero rows, but the post-guard `SELECT` finds a row with a different version | `OptimisticConcurrencyConflict(...)` with `actual_persisted_version` populated from that `SELECT` |
| Duplicate `governance_id`/`runtime_id` on `add()` | `PostgresUnitOfWork.execute()` raises; translated to `FoundationError` (category `PERSISTENCE`) whose `__cause__` is the original `sqlalchemy.exc.IntegrityError`, whose own `.orig` is the `psycopg.errors.UniqueViolation`, whose `.diag.constraint_name` identifies `uq_<table>_governance_id` or `pk_<table>` | `AggregateAlreadyExists(aggregate_kind, identity)` |
| Any other persistence failure (connection loss, timeout, unrelated constraint violation, etc.) | `FoundationError` whose `__cause__`/`.orig`/`.diag.constraint_name` do not match a known, expected case above | Not translated to a `RepositoryContractError`; the `FoundationError` propagates unchanged. A repository is not required to have an opinion about failures it was not designed to expect. |

This table is the concrete resolution of Section 2's finding: `PostgresUnitOfWork.execute()` already wraps every exception into a generic `FoundationError`, discarding the original type as anything other than `__cause__`. A concrete repository implementation must therefore inspect `__cause__` (and, through it, `.orig.diag.constraint_name` for PostgreSQL-specific detail) rather than expect to catch `sqlalchemy.exc.IntegrityError` directly from a call through `PostgresUnitOfWork.execute()`.

## 10. DurableRecord-to-Schema Field Mapping

Every field of every `<Aggregate>DurableRecord` (M021, frozen) maps to exactly one column already named in the M022 schema (frozen); no field lacks a column and no column lacks a source field. This design does not restate the full field-by-field table (it is already fully specified, twice over, by M021 Design Sections 9-10 and M022 Design Sections 7-10 and this milestone's own baseline evidence, Section 3 of the Scope Selection); it specifies only the translation *rules* a concrete implementation must follow, since the frozen types on both sides already fully determine the mapping:

- `IdentityDurableRecord.governance_id` / `.runtime_id` — the root table's `governance_id`/`runtime_id` columns directly; `runtime_id` (a `str`, per `IdentityDurableRecord`'s frozen shape) binds to the schema's `UUID` column as a string, consistent with the migration's `postgresql.UUID(as_uuid=False)` choice (M022 Design/Implementation) — no UUID-object marshaling is needed on either side of the boundary;
- every `tuple[str, ...]` field (`notes`, `evidence_references`, `artifact_references`) binds directly to the corresponding `TEXT[]` column; an empty tuple binds to `{}`, matching the column's `NOT NULL DEFAULT '{}'::text[]`;
- every `datetime` field binds directly to the corresponding `TIMESTAMPTZ` column (the frozen durable records already use timezone-aware `datetime` values, per M021's own field types);
- every `str | None` / optional field binds to `NULL` when the durable record's value is `None`, and to the value otherwise — no sentinel value is introduced;
- `TransitionDurableRecord.identity_reference: IdentityDurableRecord | None` splits into the transition table's two nullable columns, `identity_governance_id` and `identity_runtime_id`, both `NULL` when `identity_reference is None`;
- ordinal position for `run_manifest`/`evidence_package_criterion_result`/`evidence_package_artifact_reference` (which have no frozen sequence field of their own) is the durable record tuple's own index (`0`-based, matching the schema's `position >= 0` floor); ordinal position for `campaign_transition`/`run_transition`/`evidence_package_transition`/`review_transition`/`review_finding` (which do carry a frozen `sequence` field) is that field's own value, not the tuple index — the two are expected to agree for a validly-reconstructed aggregate, but the schema column is populated from the frozen field, not re-derived, per Section 4's "no reinterpretation" principle.

## 11. Transaction Boundary Confirmation

Per Design Principle 3, this design confirms — rather than invents — that the existing `PostgresUnitOfWork` primitive suffices: every one of `get`/`add`/`save`'s SQL statements above executes inside exactly one `with service.unit_of_work() as work:` block, `commit()`-ed once on success or implicitly rolled back once on any raised exception (`PostgresUnitOfWork.__exit__`'s existing behavior, unchanged). No cross-aggregate transaction, no multi-call transaction, and no savepoint/nested-transaction usage is introduced. Candidate D (multi-statement/multi-aggregate Unit of Work) from the Scope Selection remains correctly deferred; nothing in this design requires it.

## 12. Identity Handling

`get(identity: DomainIdentity[XId])` and `save(aggregate, expected_persisted_version=...)` (whose aggregate carries its own `DomainIdentity` internally) both address the root row by `runtime_id` (Design Principle 5). `add(aggregate)` writes both `governance_id` and `runtime_id` from the aggregate's identity and relies on the schema's own `UNIQUE`/`PRIMARY KEY` constraints for duplicate detection (Section 7) rather than a separate lookup. Cross-aggregate context fields already stored as `governance_id` strings in the durable record (`RunDurableRecord.campaign_id`, `EvidencePackageDurableRecord.run_id`, `ReviewDurableRecord.target_evidence_package_id`) are written and read as opaque strings — this design does not resolve them to the parent aggregate's `runtime_id` or fetch the parent, matching M022 Design Section 6's own choice to FK against the referenced aggregate's `governance_id` column specifically because the durable record already carries that shape.

## 13. Migration Revision Strategy

None. This design creates no migration; `migrations/versions/` remains exactly the one M022 revision.

## 14. Reconstruction and Mapper Integration

This design is precisely the "future repository implementation" M019, M020, and M021's own frozen documents and docstrings anticipate and explicitly defer to (Section 2, Section 6). It does not alter `_reconstruct_*`, `<Aggregate>ReconstructionState`, any `Mapper` Protocol, or any `DurableRecord` type; it specifies exactly how a concrete implementation calls them, in what order, and how their exceptions are translated.

## 15. Test Strategy (for a future Implementation milestone)

- real-PostgreSQL round-trip fidelity per aggregate: `add()` a freshly-constructed aggregate, `get()` it back, assert structural equality (identity, lifecycle state, version, every owned-collection element in order) with the original;
- `save()` round-trip: `add()`, mutate the in-memory aggregate via its own frozen business methods, `save()` with the correct `expected_persisted_version`, `get()` again, assert the mutation persisted and `version` advanced;
- optimistic-concurrency conflict: `add()`, `get()` twice (two independent `LoadedAggregate`s), `save()` the first successfully, then attempt `save()` with the second's now-stale `persisted_version` and assert `OptimisticConcurrencyConflict` with the correct `actual_persisted_version`;
- `add()` duplicate rejection: `add()` twice with the same identity, assert `AggregateAlreadyExists` on the second call and that the first `add()`'s row is unaffected;
- `get()`/`save()` not-found: call each against an identity never added, assert `AggregateNotFound`;
- owned-collection ordering: an aggregate with a multi-element owned collection round-trips through `add()`/`get()` with element order preserved, exercising the full mapper-and-schema path (not just the schema-level ordering M022's own tests already prove);
- atomicity: a simulated mid-write failure (e.g. a child-table `INSERT` violating a frozen `CHECK`) during `add()`/`save()` leaves no partial row for that aggregate — the existing transaction boundary (Section 11) should guarantee this, and a test should prove it rather than assume it;
- error-translation table (Section 9) coverage: one test per row proving the specific `RepositoryContractError` subtype (or unmodified `FoundationError` passthrough, for the final row) that results from the described real-PostgreSQL condition.

All tests in a future implementation milestone must run against real PostgreSQL, not a mock, consistent with M022's own established discipline for this schema.

## 16. Architecture Enforcement

One narrow, explicit, disclosed change is anticipated for a future implementation milestone (not made by this design, which touches no `src/empirical_platform` file): adding `"campaign", "run", "evidence", "review"` to `ALLOWED["shared"]` in `tools/check_architecture.py` (currently `set()`), so that `shared.persistence.postgres_repositories.*` modules may import their aggregate's `mapper`/`repository`/`aggregate` modules. This widens only what `shared` may import; `FORBIDDEN_IMPORT_PREFIXES` for `campaign`/`run`/`evidence`/`review` (forbidding `sqlalchemy`/`psycopg`/`boto3`/`empirical_platform.shared.persistence`) is unchanged, so no domain package gains any new ability to import persistence machinery. See Section 5 for the full reasoning.

## 17. Security Considerations

No new credential handling or connection-string construction is introduced; every SQL statement in Sections 6-8 is parameterized (bound parameters via `PostgresUnitOfWork.execute(statement, parameters)`, never string-interpolated values), including every free-text `DurableRecord` field (`actor`, `reason`, `scope_statement`, findings `text`, etc.), preventing SQL injection through those fields. No new secret-shaped field is introduced by this design.

## 18. Compatibility with M019, M020, M021, and M022

No frozen file in any of the four milestones is modified. Every operation in Sections 6-8 uses only already-frozen types (`DomainIdentity`, `AggregateVersion`, `<Aggregate>ReconstructionState`, `<Aggregate>DurableRecord`, the M020 error hierarchy) and already-frozen schema objects (M022's twelve tables and their constraints) exactly as specified.

## 19. Explicit Non-Goals

This design does not:

- write repository implementation code;
- write concrete mapper implementation code (an independent, deferred, future milestone);
- create a migration or alter the M022 schema;
- introduce multi-statement or multi-aggregate Unit of Work;
- introduce runtime composition, dependency injection wiring, APIs, or workers;
- introduce application services;
- touch Audit runtime, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior;
- solve true no-op-save detection (`SaveOperation.UNCHANGED`) — explicitly deferred, Section 8.

## 20. Deferred Work

- concrete mapper implementation (independent, ready, non-blocking — M023 Scope Selection Candidate A);
- concrete repository implementation following this design (a future implementation milestone, subject to its own freeze discipline);
- the one narrow `ALLOWED["shared"]` architecture-checker change (Section 16), to be made by that future implementation milestone alongside the code that needs it, not by this design;
- `SaveOperation.UNCHANGED` detection (Section 8);
- multi-statement/multi-aggregate Unit of Work, repository runtime composition, application services (all still correctly deferred per prior milestones' own findings).

## 21. Hostile Self-Review

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M023-DESIGN-ISSUE-0001 | MAJOR | 9 | Initial framing assumed a repository implementation could catch `sqlalchemy.exc.IntegrityError` directly from a call through `PostgresUnitOfWork.execute()`. | Live inspection of `postgres.py` shows `execute()` translates every exception into a generic `FoundationError` via `translate_persistence_error()`, preserving the original only as `__cause__`. | An implementer following an untested assumption here would either fail to distinguish `AggregateAlreadyExists` from other failures, or would need to rediscover this translation behavior mid-implementation without a reviewed design to guide it. | Added Section 9's error-translation table, keyed explicitly on `FoundationError.__cause__` / `.orig.diag.constraint_name`, verified against the real `translate_persistence_error`/`FoundationError.wrap` source. | Resolved |
| M023-DESIGN-ISSUE-0002 | MAJOR | 5 | Initial framing treated repository module placement as obviously fine anywhere convenient, without checking the architecture checker's actual rules. | `campaign`/`run`/`evidence`/`review` are forbidden from importing `sqlalchemy`/persistence; a naive placement inside those packages would either violate the checker or require weakening a domain-purity rule this project has consistently protected since M019. | Could have produced a design that implicitly required an unreviewed, broad architecture-checker weakening at implementation time. | Traced `check_architecture.py`'s actual `module_for_path`/`ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` logic and confirmed `shared/persistence/...` placement requires exactly one narrow, disclosed addition (`ALLOWED["shared"]` gaining the four aggregate names) and no change to any forbidden-import rule. | Resolved |
| M023-DESIGN-ISSUE-0003 | MINOR | 8 | Considered specifying an incremental-diff strategy for owned collections to avoid delete-and-reinsert's apparent inefficiency. | The frozen `DurableRecord` types (M021) carry no per-item identity, version, or removal marker distinguishing "unchanged" from "new" elements; an incremental diff would require inventing such metadata, which is out of this design's scope (would touch M021's frozen shape). | Attempting this would either silently invent new mapper-contract surface or produce an under-specified, ambiguous design. | Adopted and justified full-replace explicitly (Design Principle 4), with the reasoning recorded rather than left implicit. | Resolved |
| M023-DESIGN-ISSUE-0004 | MINOR | 12 | Considered having `get`/`save` accept and resolve `governance_id` as an alternative lookup key for flexibility. | M022 Design Section 6 already establishes `runtime_id` as every table's own primary key; supporting a second lookup path adds surface area no frozen caller (the M020 Protocol signatures) actually requires. | Would add an unrequested, unreviewed degree of freedom beyond what M020's frozen Protocol signatures need. | Fixed `runtime_id` as the sole primary access-path key (Design Principle 5), matching exactly what the frozen `DomainIdentity`-typed Protocol parameters already provide. | Resolved |

No unresolved design finding remains.

## 22. Implementation Acceptance Gate (for a future Implementation milestone, not satisfied by this design)

A future MILESTONE-023-implementation (or MILESTONE-024, depending on how the Project Owner sequences it) must demonstrate, before it may be considered for freeze:

- every operation in Sections 6-8 implemented exactly as specified, for all four aggregates;
- every row of Section 9's error-translation table proven against real PostgreSQL, not asserted from source reading alone;
- the one narrow `ALLOWED["shared"]` architecture-checker change made and verified not to weaken any `FORBIDDEN_IMPORT_PREFIXES` rule;
- the Section 15 test strategy executed in full against real, disposable PostgreSQL;
- no frozen M019, M020, M021, or M022 file modified.

## 23. Final Decision

```text
DESIGN READY FOR INDEPENDENT REVIEW
```

NOT APPROVED. NOT FROZEN. No repository, mapper, migration, or Unit of Work code was created by this design.
