# MILESTONE-022 - PostgreSQL Schema and Migration Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-022-IMPLEMENTATION |
| Title | PostgreSQL Schema and Migration Implementation |
| Version | 1.0 |
| Status | IMPLEMENTATION COMPLETE - PENDING INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen design authority | `MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_DESIGN.md` (Version 1.1) and `MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_DESIGN_FREEZE.md` (M022 DESIGN APPROVED AND FROZEN) |
| Mission type | Implementation only |
| Repository/mapper implementations, Unit of Work, application services, MILESTONE-023 work created | No |
| Frozen M019/M020/M021 source files modified | No |

## 2. Scope

This implementation creates the twelve-table PostgreSQL schema frozen by the MILESTONE-022 design as a single Alembic revision, and proves it against a real, disposable PostgreSQL 18.4 instance. It does not implement a concrete mapper, a repository, a Unit of Work, or any application-layer code.

## 3. Files Changed

Created:

- `migrations/script.py.mako` (standard, unmodified Alembic revision template; the environment had no template committed);
- `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py` (the single revision implementing all twelve tables);
- `tests/integration/test_m022_schema_migration.py` (20 real-PostgreSQL integration tests);
- `MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_IMPLEMENTATION.md` (this document).

Modified:

- `migrations/env.py` (`run_migrations_online()` now connects for real via `resolve_foundation_config().postgresql.sqlalchemy_url()` and `create_engine()`, replacing the placeholder `RuntimeError`; `target_metadata` stays `None` per the design);
- `alembic.ini` (added `path_separator = os` to silence a benign Alembic deprecation warning about `prepend_sys_path` splitting; no behavioral change).

`tools/check_architecture.py` was not modified, matching the design's Section 16 expectation ("This design touches no `src/empirical_platform` package"). No `src/empirical_platform` file was created or modified.

## 4. Revision Identity

| Field | Value |
| --- | --- |
| Revision ID | `5b58cdd7751b` |
| Down revision | `None` (first revision) |
| Message | `create m022 postgresql schema` |

## 5. Naming Convention Mechanism

The design (Section 12.5) freezes a standard SQLAlchemy `naming_convention` and specifically anticipates it being "attached to the `MetaData` object a future implementation constructs." The implementation does exactly that: a module-level `sa.MetaData(naming_convention=NAMING_CONVENTION)` backs every one of the twelve `sa.Table` definitions. Primary key, foreign key, and unique constraint names are left for the convention to derive automatically; every `CHECK` constraint is given the explicit short qualifier name (`version_non_negative`, `next_transition_sequence_positive`, `sequence_positive`, `position_non_negative`, `lifecycle_state_valid`, `from_state_valid`, `to_state_valid`, `disposition_valid`) the design mandates, which the convention then combines into `ck_<table>_<qualifier>`.

### 5.1 63-Byte Identifier Limit (discovered during implementation)

An initial implementation attempt hand-wrote literal constraint name strings reproducing the convention's pattern. Applying that revision against real PostgreSQL failed immediately:

```text
sqlalchemy.exc.IdentifierError: Identifier
'fk_evidence_package_criterion_result_evidence_package_runtime_id_evidence_package'
exceeds maximum length of 63 characters
```

Three foreign-key names, all on the `evidence_package_*` child tables (whose table and referenced-table names are long), exceed PostgreSQL's 63-byte identifier limit before truncation. This is not a design defect — the design's own naming convention, correctly *attached to a real `MetaData` object* rather than hand-transcribed as literal strings, truncates such names deterministically via SQLAlchemy's standard hashing behavior. Switching to the `MetaData`-driven mechanism (Section 5 above) resolved this without deviating from the frozen convention; it is the literal implementation of what Section 12.5 describes. The three resulting truncated names, empirically captured from a real applied migration:

| Table | Foreign key name |
| --- | --- |
| `evidence_package_artifact_reference` | `fk_evidence_package_artifact_reference_evidence_package_4209` |
| `evidence_package_criterion_result` | `fk_evidence_package_criterion_result_evidence_package_r_5363` |
| `evidence_package_transition` | `fk_evidence_package_transition_evidence_package_runtime_7780` |

All three are 62 characters, under the 63-byte limit; each carries a distinct 4-hex-digit suffix (no collision). Every other PK/FK/UQ/CK name across all twelve tables matches the convention's un-truncated form exactly (verified in `test_upgrade_campaign_table_structure` and `test_upgrade_foreign_key_names_including_truncated_ones`).

## 6. Tables, Creation Order, and Downgrade Order

The exact object creation order frozen by Design Section 12.5 is implemented literally as a list (`_TABLES_IN_CREATION_ORDER`) and iterated with individual `table.create(bind=...)` calls in `upgrade()`, and iterated in `reversed()` order with individual `table.drop(bind=...)` calls in `downgrade()`:

1. `campaign`
2. `campaign_transition`
3. `run`
4. `run_manifest` (+ its partial-unique index, emitted automatically as part of this table's own `CREATE TABLE`/`CREATE INDEX` sequence since the index is attached to the table definition)
5. `run_transition`
6. `evidence_package`
7. `evidence_package_criterion_result`
8. `evidence_package_artifact_reference`
9. `evidence_package_transition`
10. `review`
11. `review_finding`
12. `review_transition`

No ORM models were declared; every table is `sa.Table` Core metadata. No `op.create_table`/`op.drop_table` Alembic convenience wrappers were used (Section 5 explains why: only a `Table` object attached to a `naming_convention`-bearing `MetaData` gets correct automatic truncation) — `table.create(bind)`/`table.drop(bind)` are the equivalent SQLAlchemy Core primitives, executed through the same Alembic-managed connection (`op.get_bind()`) and the same transactional-DDL context Alembic establishes.

## 7. Constraints and Indexes (per design Sections 7-10, 12.2-12.4)

- Every table's primary key, matching its frozen identity/composite-key shape;
- Every frozen foreign key, with no `ondelete` specified (PostgreSQL default `NO ACTION`, as the design requires — no unauthorized `CASCADE` anywhere in the revision);
- Every frozen `UNIQUE` constraint, including the two-column uniqueness constraints on `evidence_package_criterion_result` (`criterion_id`, `evidence_package_runtime_id`) and `evidence_package_artifact_reference` (`value`, `evidence_package_runtime_id`);
- Every frozen numeric `CHECK` floor (`version >= 0`, `next_transition_sequence >= 1`, `sequence >= 1`, `position >= 0`) — twenty constraints across the twelve tables;
- Every frozen enum-membership `CHECK` (`lifecycle_state`, `from_state`, `to_state`, `disposition`) — thirteen constraints, each listing exactly the live enum's members read from `campaign/lifecycle.py`, `evidence/lifecycle.py`, `review/lifecycle.py` at design time;
- The partial unique index `ix_run_manifest_manifest_id_partial_unique` on `run_manifest(run_runtime_id, manifest_id) WHERE manifest_id IS NOT NULL`, matching the design's explicit-name requirement for this one index (the naming convention's `ix` key alone would not distinguish it).

No column, table, index, or constraint beyond what Sections 7-10 and 12.3-12.4 specify was created.

## 8. PostgreSQL-Specific Type Choices

| Domain concept | PostgreSQL/SQLAlchemy type |
| --- | --- |
| UUID identity/reference columns | `postgresql.UUID(as_uuid=False)` (string-typed, matching durable-record string identity fields) |
| Timestamps (`occurred_at`, `recorded_at`) | `sa.DateTime(timezone=True)` (`TIMESTAMPTZ`) |
| Free text / lifecycle-state / enum-membership columns | `sa.Text()` |
| Integer counters (`version`, `next_transition_sequence`, `sequence`, `position`) | `sa.Integer()` |
| String-list fields (`run_manifest.notes`, criterion `evidence_references`, review finding `evidence_references`) | `postgresql.ARRAY(sa.Text())`, `NOT NULL DEFAULT '{}'::text[]` |

## 9. Real PostgreSQL Test Environment

Per the mission's explicit instruction not to mock PostgreSQL, all tests in Section 10 ran against a real, disposable PostgreSQL instance under this session's exclusive control, isolated from any pre-existing system PostgreSQL service:

- Server: PostgreSQL 18.4 on x86_64-windows (self-managed `initdb`/`pg_ctl`, not a system service);
- Bind: `localhost` only, non-default port (matching the project's own `.env.example` local-dev convention, distinct from the two unrelated, credential-unknown PostgreSQL services already running on the machine's default ports, which were never touched);
- Database: `empirical_platform`, owned by a self-generated `empirical` role with a randomly generated password known only to a local, git-ignored temp file, never logged or committed;
- Connection parameters supplied to the application and to `migrations/env.py` exclusively via the existing `EMPIRICAL_PLATFORM_POSTGRES_*` environment variables and `resolve_foundation_config()` — no new credential-handling code was introduced.

## 10. Integration Test Evidence

`tests/integration/test_m022_schema_migration.py`, run with `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1` against the instance above (database URL and password redacted; full raw output captured in `external-review/M022_POSTGRESQL_SCHEMA_AND_MIGRATION_IMPLEMENTATION/evidence/`):

```text
PostgreSQL 18.4 on x86_64-windows, compiled by msvc-19.44.35227, 64-bit
EMPIRICAL_PLATFORM_POSTGRES_HOST=localhost
EMPIRICAL_PLATFORM_POSTGRES_PORT=55432
EMPIRICAL_PLATFORM_POSTGRES_DATABASE=empirical_platform
EMPIRICAL_PLATFORM_POSTGRES_USER=empirical
EMPIRICAL_PLATFORM_POSTGRES_PASSWORD=[REDACTED]

20 passed in 4.66s
```

Coverage by requirement (Phase 5 of the governing mission):

- **UPGRADE** — `test_upgrade_creates_all_twelve_tables`, `test_upgrade_campaign_table_structure`, `test_upgrade_foreign_key_names_including_truncated_ones`, `test_upgrade_run_manifest_partial_unique_index`: migration applied from an empty database; all twelve tables, columns, types, PK/FK/UNIQUE/CHECK names, and the partial index verified via live `sqlalchemy.inspect()` introspection against the real server (not stubbed metadata).
- **CONSTRAINT BEHAVIOR — rejections**, each proven by a real `INSERT`/`UPDATE` raising `sqlalchemy.exc.IntegrityError` against real PostgreSQL, then rolled back:
  - `test_campaign_version_below_zero_is_rejected` (`version < 0`);
  - `test_campaign_next_transition_sequence_below_one_is_rejected` (`next_transition_sequence < 1`);
  - `test_transition_sequence_below_one_is_rejected` (`campaign_transition.sequence < 1`);
  - `test_review_finding_sequence_below_one_is_rejected` (`review_finding.sequence < 1`);
  - `test_position_below_zero_is_rejected` (`run_manifest.position < 0`);
  - `test_invalid_lifecycle_state_is_rejected` (`campaign.lifecycle_state` not a member);
  - `test_invalid_review_disposition_is_rejected` (`review.disposition` not a member);
  - `test_duplicate_artifact_reference_position_is_rejected` (PK collision on `evidence_package_artifact_reference`);
  - `test_duplicate_artifact_reference_value_is_rejected` (UNIQUE collision on `(value, evidence_package_runtime_id)`);
  - `test_invalid_parent_reference_is_rejected` (FK violation: `campaign_transition` referencing a non-existent `campaign`);
  - `test_orphan_child_row_is_rejected` (FK violation: `review_finding` referencing a non-existent `review`);
  - `test_duplicate_owned_row_key_is_rejected` (PK collision on `run_manifest`).
- **CONSTRAINT BEHAVIOR — acceptance**: `test_full_valid_aggregate_chain_is_accepted` inserts one valid row into all twelve tables (a complete Campaign -> Run -> EvidencePackage -> Review chain) and confirms every insert succeeds.
- **ORDERING**: `test_artifact_reference_rows_reconstruct_deterministically_by_position` inserts `evidence_package_artifact_reference` rows out of position order and confirms `ORDER BY position` yields the position-encoded order, not insertion order.
- **DOWNGRADE**: `test_downgrade_removes_all_tables_and_reupgrade_succeeds` downgrades a fully upgraded database to `base`, confirms zero of the twelve tables and an empty `alembic_version` remain, then re-upgrades to `head` and confirms all twelve tables exist again.
- **ATOMICITY**: `test_migration_failure_leaves_no_partial_schema` pre-creates a conflicting `review` table so the revision fails at creation step 10, then confirms none of tables 1-9 survive (PostgreSQL DDL is transactional and Alembic wraps the revision in a transaction) and that `alembic_version` was never stamped.

## 11. CLI-Level Real Upgrade/Downgrade/Re-upgrade Evidence

In addition to the pytest-driven evidence above, the revision was also exercised directly via the `alembic` CLI against the same real instance, from an empty baseline:

```text
$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 5b58cdd7751b, create m022 postgresql schema
$ psql ... \dt   # 12 tables + alembic_version, 13 rows total
$ alembic downgrade base
INFO  [alembic.runtime.migration] Running downgrade 5b58cdd7751b -> , create m022 postgresql schema
$ psql ... \dt   # alembic_version only, 1 row; SELECT * FROM alembic_version -> 0 rows
$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade  -> 5b58cdd7751b, create m022 postgresql schema
```

Full constraint-name inventory (131 constraint rows across the twelve tables) was captured via `pg_constraint` and cross-checked against Design Sections 7-10 and 12.3-12.4 name-by-name; no missing, invented, or misnamed constraint was found.

## 12. Full Validation Loop

All commands run from `.venv`, never system Python. Raw output captured in `external-review/M022_POSTGRESQL_SCHEMA_AND_MIGRATION_IMPLEMENTATION/evidence/`.

- `python -m compileall -q src migrations tests tools`: PASS;
- `ruff format --check .`: PASS (141 files formatted; the two new files were reformatted once during development, then reverified clean);
- `ruff check .`: PASS, 0 issues (one `UP035`/`UP007` finding in the generated revision's boilerplate header was auto-fixed to match repository style: `Union[str, None]` -> `str | None`);
- `mypy`: PASS, 0 issues, 73 source files (unchanged — this milestone touches no `src/empirical_platform` file, consistent with the M020/M021 mypy-scope note);
- `tools/check_architecture.py .`: PASS, 0 violations;
- `tools/check_architecture.py tests/fixtures/illegal_imports`: PASS, negative fixtures still correctly detected;
- `scripts/security.ps1`: PASS (`pip-audit`: no known vulnerabilities; secret scan: 231 targets, no findings);
- `scripts/verify.ps1` (fresh GUID `--basetemp`, end-to-end): PASS — full suite `328 passed, 29 skipped in 13.26s`, coverage `92.31%` (>= 80% required); the 29 skips are the pre-existing MinIO/PostgreSQL/infrastructure integration tests that require explicit opt-in env vars `verify.ps1` does not set, including this milestone's own 20 new tests (correctly skipped in that unauthenticated context, separately run and proven in Section 10 above);
- `python -m build`: PASS (sdist + wheel built, including the two new `migrations/` files);
- `git diff --check`: PASS, exit 0 (two informational CRLF/LF line-ending notices from Git, no actual whitespace errors).

## 13. Hostile Self-Review

See the implementation's hostile-review pass, recorded in full in this session's final report rather than duplicated here. The one real defect found during implementation — three hand-written FK constraint names exceeding PostgreSQL's 63-byte limit — was found by actually applying the migration to real PostgreSQL (not by static review) and corrected by switching to the `MetaData`-driven naming mechanism Section 5 describes, which is a more faithful implementation of the frozen convention, not a deviation from it.

## 14. Explicit Non-Goals Confirmed

Not implemented:

- a concrete mapper implementation against PostgreSQL;
- concrete PostgreSQL repository implementations;
- Unit of Work beyond the existing single-statement infrastructure primitive;
- application services, runtime composition, APIs, or workers;
- Audit runtime, Decision Candidate, Decision Freeze;
- any MILESTONE-023 work.

No frozen M019, M020, or M021 source file was modified. No `src/empirical_platform` file was created or modified.

## 15. Final Status

```text
IMPLEMENTATION COMPLETE - PENDING INDEPENDENT REVIEW
```

MILESTONE-022 implementation is NOT marked APPROVED, and is NOT FROZEN. MILESTONE-023 has NOT started.
