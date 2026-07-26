# MILESTONE-022 - PostgreSQL Schema and Migration Implementation

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-022-IMPLEMENTATION |
| Title | PostgreSQL Schema and Migration Implementation |
| Version | 1.1 (narrow correction) |
| Status | IMPLEMENTATION COMPLETE - PENDING INDEPENDENT RE-REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen design authority | `MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_DESIGN.md` (Version 1.1) and `MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_DESIGN_FREEZE.md` (M022 DESIGN APPROVED AND FROZEN) |
| Mission type | Implementation only |
| Repository/mapper implementations, Unit of Work, application services, MILESTONE-023 work created | No |
| Frozen M019/M020/M021 source files modified | No |

## 2. Scope

This implementation creates the twelve-table PostgreSQL schema frozen by the MILESTONE-022 design as a single Alembic revision, and proves it against a real, disposable PostgreSQL 18.4 instance. It does not implement a concrete mapper, a repository, a Unit of Work, or any application-layer code.

**Version 1.1 note:** an independent hostile review of implementation commit `69920125214b577485096406b9a2b2b573bead81` returned "M022 IMPLEMENTATION REQUIRES NARROW CORRECTION" (two MAJOR findings against this implementation, one MAJOR finding about missing independent PostgreSQL evidence due to a Docker-unavailable review environment). See Section 16 for the full correction record. This document's body has been updated in place to describe the corrected state; Section 16 preserves the independent findings and how each was resolved.

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

**Version 1.1 correction round** modified exactly two files beyond the above (no new files): `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py` (UNIQUE column order fix) and `tests/integration/test_m022_schema_migration.py` (expanded from 20 to 49 tests). See Section 14.

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
- Every frozen `UNIQUE` constraint, including the two-column uniqueness constraints on `evidence_package_criterion_result` (`evidence_package_runtime_id`, `criterion_id`) and `evidence_package_artifact_reference` (`evidence_package_runtime_id`, `value`) — this exact column order (owning parent's FK column first) was corrected in Version 1.1; see Section 16.1;
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

`tests/integration/test_m022_schema_migration.py` (49 tests, expanded from 20 in the narrow correction — see Section 16.2), run with `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1` against a fresh, independently re-provisioned disposable PostgreSQL 18.4 instance (database URL and password redacted; full raw output captured in `external-review/M022_POSTGRESQL_SCHEMA_AND_MIGRATION_IMPLEMENTATION/evidence/`):

```text
PostgreSQL 18.4 on x86_64-windows, compiled by msvc-19.44.35227, 64-bit
EMPIRICAL_PLATFORM_POSTGRES_HOST=localhost
EMPIRICAL_PLATFORM_POSTGRES_PORT=55433
EMPIRICAL_PLATFORM_POSTGRES_DATABASE=empirical_platform
EMPIRICAL_PLATFORM_POSTGRES_USER=empirical
EMPIRICAL_PLATFORM_POSTGRES_PASSWORD=[REDACTED]

49 passed in 6.03s
```

Coverage by requirement (Phase 5 of the original mission, plus the independent review's Phase 3 additions):

- **UPGRADE / EXACT STRUCTURE** — `test_upgrade_creates_all_twelve_tables` plus `test_table_matches_frozen_structure` (parametrized over all twelve tables): for every table, exact column set, exact PostgreSQL reflected type per column, exact nullability, exact PK name and columns, exact FK name/columns/target/referenced-columns and confirmed-implicit `ON DELETE` (no explicit action — PostgreSQL default `NO ACTION`), exact UNIQUE name and column order, exact CHECK name set, exact index name/columns/uniqueness/predicate — all read back via live `sqlalchemy.inspect()` against the real server, independent of the migration file's own construction-time type objects. `test_upgrade_evidence_package_unique_constraints_preserve_frozen_column_order` is a narrow, explicit regression test for the Section 16.1 correction specifically.
- **CONSTRAINT BEHAVIOR — rejections**, each proven by a real `INSERT`/`UPDATE` raising `sqlalchemy.exc.IntegrityError` against real PostgreSQL, then rolled back:
  - numeric floors: `test_campaign_version_below_zero_is_rejected`, `test_campaign_next_transition_sequence_below_one_is_rejected`, `test_transition_sequence_below_one_is_rejected`, `test_review_finding_sequence_below_one_is_rejected`, `test_position_below_zero_is_rejected`;
  - enum membership: `test_invalid_campaign_lifecycle_state_is_rejected`, `test_invalid_run_lifecycle_state_is_rejected`, `test_invalid_evidence_package_lifecycle_state_is_rejected`, `test_invalid_review_lifecycle_state_is_rejected`, `test_invalid_review_disposition_is_rejected`, `test_invalid_transition_from_state_is_rejected` and `test_invalid_transition_to_state_is_rejected` (each parametrized over all four transition tables — 8 tests total);
  - root identity uniqueness: `test_duplicate_campaign_governance_id_is_rejected`, `test_duplicate_run_governance_id_is_rejected`, `test_duplicate_evidence_package_governance_id_is_rejected`, `test_duplicate_review_governance_id_is_rejected`;
  - owned-collection uniqueness: `test_duplicate_criterion_id_within_same_package_is_rejected`, `test_duplicate_artifact_reference_position_is_rejected`, `test_duplicate_artifact_reference_value_is_rejected`, `test_duplicate_manifest_id_within_same_run_is_rejected`, `test_duplicate_owned_row_key_is_rejected`;
  - referential integrity: `test_invalid_parent_reference_is_rejected` (FK violation: `campaign_transition` referencing a non-existent `campaign`), `test_orphan_child_row_is_rejected` (FK violation: `review_finding` referencing a non-existent `review`).
- **CONSTRAINT BEHAVIOR — acceptance**: `test_full_valid_aggregate_chain_is_accepted` inserts one valid row into all twelve tables; `test_same_criterion_id_across_different_packages_is_accepted` proves the same `criterion_id` is accepted in two different `EvidencePackage`s (the UNIQUE constraint is scoped per package, matching Design Section 9); `test_multiple_null_manifest_id_within_same_run_is_accepted` proves the partial unique index correctly allows repeated `NULL` `manifest_id` values within the same run.
- **ORDERING**: `test_artifact_reference_rows_reconstruct_deterministically_by_position` inserts `evidence_package_artifact_reference` rows out of position order and confirms `ORDER BY position` yields the position-encoded order, not insertion order.
- **DOWNGRADE**: `test_downgrade_removes_all_tables_and_reupgrade_succeeds` downgrades a fully upgraded database to `base`, confirms zero of the twelve tables and an empty `alembic_version` remain, then re-upgrades to `head` and confirms all twelve tables exist again.
- **ATOMICITY**: `test_migration_failure_leaves_no_partial_schema` pre-creates a conflicting `review` table so the revision fails at creation step 10, then confirms none of tables 1-9 survive (PostgreSQL DDL is transactional and Alembic wraps the revision in a transaction) and that `alembic_version` was never stamped; narrowed to assert the specific `sqlalchemy.exc.ProgrammingError` this failure mode produces, not a broad `Exception`.

## 11. CLI-Level Real Upgrade/Downgrade/Re-upgrade Evidence

In addition to the pytest-driven evidence above, the corrected revision was also exercised directly via the `alembic` CLI against the same fresh real instance, from an empty baseline:

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

Full constraint-name inventory (131 constraint rows across the twelve tables, including the two corrected UNIQUE constraints' new truncated names — see Section 16.1) was captured fresh via `pg_constraint` and cross-checked against Design Sections 7-10 and 12.3-12.4 name-by-name; no missing, invented, or misnamed constraint was found.

## 12. Full Validation Loop

All commands run from `.venv`, never system Python. Raw output captured in `external-review/M022_POSTGRESQL_SCHEMA_AND_MIGRATION_IMPLEMENTATION/evidence/`.

- `python -m compileall -q src migrations tests tools`: PASS;
- `ruff format --check .`: PASS (141 files formatted);
- `ruff check .`: PASS, 0 issues;
- `mypy`: PASS, 0 issues, 73 source files (unchanged — this milestone touches no `src/empirical_platform` file, consistent with the M020/M021 mypy-scope note);
- `tools/check_architecture.py .`: PASS, 0 violations;
- `tools/check_architecture.py tests/fixtures/illegal_imports`: PASS, negative fixtures still correctly detected;
- `scripts/security.ps1`: PASS (`pip-audit`: no known vulnerabilities; secret scan: **232 targets**, no findings — the exact current count, re-verified fresh for this correction, one higher than the original implementation's 231 because this document itself is a scan target);
- `scripts/verify.ps1` (fresh GUID `--basetemp`, end-to-end): PASS — full suite `328 passed, 58 skipped in 12.46s`, coverage `92.31%` (>= 80% required); the 58 skips are the pre-existing MinIO/PostgreSQL/infrastructure integration tests that require explicit opt-in env vars `verify.ps1` does not set, including this milestone's own 49 tests (correctly skipped in that unauthenticated context, separately run and proven in Section 10 above);
- `python -m build`: PASS (sdist + wheel built);
- `git diff --check`: PASS, exit 0 (informational CRLF/LF line-ending notices from Git only, no actual whitespace errors).

## 13. Hostile Self-Review

Recorded in full in the correction mission's final report rather than duplicated here. See Section 16 for the independent-review findings this correction responds to, and Section 16.4 for this correction's own hostile self-review pass.

## 14. MILESTONE-022 Implementation Narrow Correction (Independent Review Response)

An independent hostile review of implementation commit `69920125214b577485096406b9a2b2b573bead81` returned "M022 IMPLEMENTATION REQUIRES NARROW CORRECTION" with three authoritative findings. This section is the permanent record of those findings and how each was resolved; Sections 1-13 above were updated in place to describe the corrected state.

### 14.1 MAJOR 1 — Frozen UNIQUE Column Order Mismatch

The migration defined `UniqueConstraint("criterion_id", "evidence_package_runtime_id")` and `UniqueConstraint("value", "evidence_package_runtime_id")`, reversed from the frozen design's `UNIQUE (evidence_package_runtime_id, criterion_id)` and `UNIQUE (evidence_package_runtime_id, value)` (Design Section 9: "the owning parent's foreign-key column first"). The constraints were semantically equivalent (a UNIQUE constraint enforces the same rule regardless of column order) but did not match the frozen column order the design specifies, and — because the naming convention's `uq` key derives its name from `column_0_name` — produced different (though still deterministic and collision-free) constraint names than the frozen order would.

**Resolution:** both `UniqueConstraint` calls in `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py` were corrected to list `evidence_package_runtime_id` first. Because both tables' fully-qualified names already exceed 63 bytes when combined with either column order, both corrected constraint names are truncated deterministically by SQLAlchemy's naming convention (the same mechanism documented in Section 5.1), empirically re-captured from a real applied migration:

| Table | Corrected UNIQUE constraint name | Columns (frozen order) |
| --- | --- | --- |
| `evidence_package_criterion_result` | `uq_evidence_package_criterion_result_evidence_package_r_3ff8` | `(evidence_package_runtime_id, criterion_id)` |
| `evidence_package_artifact_reference` | `uq_evidence_package_artifact_reference_evidence_package_35f6` | `(evidence_package_runtime_id, value)` |

No other constraint, column, table, or index changed as a result of this correction; the full 131-row constraint inventory was re-verified against Design Sections 7-10 and 12.3-12.4 name-by-name after the fix (Section 11).

### 14.2 MAJOR 2 — Integration-Test Coverage Was Incomplete

`tests/integration/test_m022_schema_migration.py` grew from 20 to 49 tests. Added, all against real PostgreSQL, none replacing behavioral assertions with source-string checks:

- root `governance_id` uniqueness for all four aggregate roots (4 tests);
- duplicate `CriterionResult.criterion_id` within one `EvidencePackage` rejected, and the same `criterion_id` across two different `EvidencePackage`s accepted (2 tests);
- duplicate non-null `run_manifest.manifest_id` within the same run rejected, and multiple null `manifest_id` values within the same run accepted (2 tests);
- invalid lifecycle rejected for `Run`, `EvidencePackage`, `Review` (`Campaign`'s was already covered) (3 tests);
- invalid `from_state` and invalid `to_state` rejected for all four transition tables, parametrized (8 tests);
- one comprehensive, data-driven structural test (`test_table_matches_frozen_structure`, parametrized over all twelve tables) asserting exact columns, PostgreSQL-reflected types, nullability, PK name/columns, FK name/columns/target/`ON DELETE` action, UNIQUE name/column order, CHECK name set, and index name/columns/uniqueness/predicate for every table — replacing the three narrower ad hoc structural tests the original implementation had;
- one narrow regression test pinning the corrected UNIQUE column order specifically (Section 14.1).

The pre-existing atomicity test's `pytest.raises(Exception)` (a broad catch flagged during this correction's own hostile self-review, Section 14.4) was narrowed to `pytest.raises(sa.exc.ProgrammingError, match="already exists")`, the exact error a pre-created conflicting table produces.

### 14.3 MAJOR 3 — Fresh Independent PostgreSQL Evidence

The independent reviewer could not run PostgreSQL (Docker Engine unavailable in that review environment) and could not itself produce real-database evidence. A new, independently reproducible evidence package was generated using a freshly provisioned, fully isolated PostgreSQL instance — distinct from the one used during the original implementation, and from the two unrelated, credential-unknown system PostgreSQL services on this machine, neither of which was touched:

- PostgreSQL 18.4 on x86_64-windows, self-managed `initdb`/`pg_ctl`, new data directory, new self-generated `empirical` role with a freshly randomly generated password (SCRAM-SHA-256), bound to `localhost` only on port `55433` (distinct from the original implementation's `55432`, itself distinct from the two system services' default `5432`/`5433`);
- password stored only in a local, git-ignored temp file, never logged, never committed, confirmed absent from every evidence file via a direct grep before packaging;
- torn down after evidence capture (see Section 16.3 of the correction mission's final report for the exact teardown confirmation).

All Section 10 and Section 11 evidence in this document was produced against this fresh instance.

### 14.4 Hostile Self-Review of This Correction

- Re-verified all 12 tables' full field/constraint inventory against Design Sections 7-10 a second time (unchanged from the original implementation except the two corrected UNIQUE column orders).
- Confirmed the corrected UNIQUE constraint names are stable, deterministic, and collision-free (distinct 4-hex-digit truncation suffixes, verified via two independent applications of the migration to two different fresh databases producing identical names both times).
- Confirmed no CASCADE, no unauthorized schema object, and no credential handling was introduced by the correction.
- Confirmed the broad `except Exception`/`pytest.raises(Exception)` pattern flagged in the independent review does not appear anywhere else in the test file (grepped for `raises(Exception)` and bare `except Exception` — none found outside the one instance already narrowed).
- Confirmed every new test either exercises real PostgreSQL behavior (an actual `INSERT`/`UPDATE`/`SELECT`) or real schema introspection (`sqlalchemy.inspect()` against the live server) — none rely on the migration file's own source text or construction-time type objects.
- Confirmed every test that seeds data explicitly rolls back its own transaction (or operates within a fixture that resets the schema), so no test leaks state to another.

## 15. Explicit Non-Goals Confirmed

Not implemented:

- a concrete mapper implementation against PostgreSQL;
- concrete PostgreSQL repository implementations;
- Unit of Work beyond the existing single-statement infrastructure primitive;
- application services, runtime composition, APIs, or workers;
- Audit runtime, Decision Candidate, Decision Freeze;
- any MILESTONE-023 work.

No frozen M019, M020, or M021 source file was modified. No `src/empirical_platform` file was created or modified. This correction did not redesign M022, reopen the approved scope, or add repositories, concrete mappers, Unit of Work, application services, APIs, workers, or runtime composition.

## 16. Final Status

```text
IMPLEMENTATION COMPLETE - PENDING INDEPENDENT RE-REVIEW
```

MILESTONE-022 implementation is NOT marked APPROVED, and is NOT FROZEN. MILESTONE-023 has NOT started.
