# PROJECT CHECKPOINT

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | PROJECT-CHECKPOINT |
| Purpose | Repository-authoritative record of the current frozen milestone and next authorized work |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at this checkpoint | `10425e85b63a0b6f18b73b962355f22176cb279c` (M022 freeze, pushed); one local, unpushed MILESTONE-023 design commit follows on top |
| origin/master at this checkpoint | `10425e85b63a0b6f18b73b962355f22176cb279c` (identical to pushed HEAD; the M023 design commit is local-only) |

This document is updated at each milestone freeze or major checkpoint. It supersedes its own prior content; it does not rewrite any frozen milestone document.

## 2. Current State

```text
LATEST_FROZEN_MILESTONE=MILESTONE-022
M020_STATUS=APPROVED_AND_FROZEN
M020_DESIGN_COMMIT=fd96b70366a7bbed2172a8f51d7d7cc52b60bc41
M020_IMPLEMENTATION_COMMIT=e20bc76d2dc0be359cea2c385c210e081fb48a35
M020_CORRECTION_COMMIT=efed86be608471fdaa2956f7827fc9236209763a
M020_FREEZE_COMMIT=40dd6b6a0c02e710e3f7efe84e8959af51f839f9
M021_STATUS=APPROVED_AND_FROZEN
M021_DESIGN_COMMIT=06d22defd6f06b96d0a46c5e91bc169e55e674e5
M021_DESIGN_FREEZE_COMMIT=abeba5a1407a8d31ce6d07fe3e071804d2385457
M021_IMPLEMENTATION_COMMIT=73ffd3647bce749dff5c8f228f90f3be79413a9c
M021_IMPLEMENTATION_FREEZE_COMMIT=fdb180a2b21776cf37fe36826741a54ef7b43ad4
M022_STATUS=APPROVED_AND_FROZEN
M022_DESIGN_COMMIT=ccd1077a733915e4a345001e505e25bee33696a9
M022_DESIGN_CORRECTION_COMMIT=1179e307782549401157cf2b251276614fe10fa2
M022_DESIGN_FREEZE_COMMIT=4ce351d6d933c9199310337add4490cafcca4d20
M022_IMPLEMENTATION_COMMIT=69920125214b577485096406b9a2b2b573bead81
M022_IMPLEMENTATION_CORRECTION_COMMIT=c7d75334ae9f7fd760e67135eb90248f1747f1b5
M022_IMPLEMENTATION_FREEZE_COMMIT=10425e85b63a0b6f18b73b962355f22176cb279c
M023_STATUS=DESIGN_READY_PENDING_INDEPENDENT_REVIEW_NOT_APPROVED_NOT_FROZEN
```

## 3. MILESTONE-020 Summary (frozen)

MILESTONE-020 froze the domain-facing repository and optimistic-concurrency **contract layer** for the four process-local aggregates (Campaign, Run, EvidencePackage, Review): `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` (`typing.Protocol`, exactly `get`/`add`/`save`); `LoadedAggregate`, `SaveOperation`, `SaveResult`, and a five-member `RepositoryContractError` hierarchy in `empirical_platform.shared.contracts`.

Full detail: `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_{SCOPE_SELECTION,DESIGN,IMPLEMENTATION,FREEZE}.md`.

## 4. MILESTONE-021 Summary (frozen)

MILESTONE-021 froze the persistence **mapper contract layer** for the same four aggregates: `CampaignMapper`, `RunMapper`, `EvidencePackageMapper`, `ReviewMapper` (`typing.Protocol`, exactly `to_durable_record`/`from_durable_record`); four aggregate-specific durable-record types (plus three nested ones); a mapper-local `MapperError`/`MapperErrorCategory`, verified distinct from the M020 repository error taxonomy; and a shared `IdentityDurableRecord`/`TransitionDurableRecord` pair reused across all four mappers.

Full detail: `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_{SCOPE_SELECTION,DESIGN,FREEZE,IMPLEMENTATION_SCOPE_SELECTION,IMPLEMENTATION,IMPLEMENTATION_FREEZE}.md`.

## 5. MILESTONE-022 Summary (APPROVED AND FROZEN)

MILESTONE-022 froze a twelve-table PostgreSQL schema (four aggregate roots plus eight owned child/collection tables) directly derived from the M021 durable records, with structural-only `CHECK` constraints, a deterministic SQLAlchemy `naming_convention`, and a single Alembic revision (`5b58cdd7751b`) with an exact creation and downgrade order, implemented and proven against a real, disposable PostgreSQL 18.4 instance (not mocked).

The implementation went through one independent-review correction round: the first review returned "M022 IMPLEMENTATION REQUIRES NARROW CORRECTION" (UNIQUE column order on `evidence_package_criterion_result`/`evidence_package_artifact_reference` reversed relative to the frozen design; incomplete integration-test coverage; no independently reproducible PostgreSQL evidence). All three findings were resolved in the correction commit; a second independent review then returned "M022 IMPLEMENTATION APPROVED FOR OWNER FREEZE", and the Project Owner approved and froze it.

Full detail: `MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_{SCOPE_SELECTION,DESIGN,DESIGN_FREEZE,IMPLEMENTATION,IMPLEMENTATION_FREEZE}.md`.

**No repository implementation, concrete mapper implementation, Unit of Work, or application-layer code exists anywhere in the repository as of this checkpoint.** `migrations/versions` now contains exactly the one M022 revision; nothing implements the M020 repository Protocols or M021 mapper Protocols against this schema yet.

## 5.1 MILESTONE-023 Summary (design ready, pending independent review — NOT approved, NOT frozen)

Following M022's freeze, MILESTONE-023 selected and designed the **PostgreSQL Repository Adapter**: the bridge between the frozen M020 Repository Protocols, M021 Mapper Protocols, and M022 schema that neither of those three milestones defines. The design specifies, for all four aggregates: the exact `get`/`add`/`save` call sequence (completing, not altering, the frozen `repository -> mapper -> ReconstructionState -> _reconstruct_*` chain); `DurableRecord`-to-SQL-column translation rules; optimistic-concurrency enforcement via a guarded `UPDATE ... WHERE version = :expected RETURNING version`; full-replace owned-collection write strategy (justified by the frozen `DurableRecord` shape carrying no per-item version/removal marker); a concrete error-translation table from real PostgreSQL/`FoundationError` conditions to the frozen `RepositoryContractError` vocabulary (a genuine finding: `PostgresUnitOfWork.execute()` already wraps every exception into a generic `FoundationError`, preserving the original only via `__cause__`); and module placement under `shared.persistence.postgres_repositories.*`, requiring exactly one narrow, disclosed `ALLOWED["shared"]` architecture-checker addition (verified against live `tools/check_architecture.py` logic) and no `FORBIDDEN_IMPORT_PREFIXES` change.

Full detail: `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN_SCOPE_SELECTION.md`, `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN.md`.

**This design is NOT approved, NOT frozen. No repository code, mapper code, migration, or Unit of Work was created.** The design commit reflecting this work is local-only, not pushed, pending independent review.

## 6. Validation at This Checkpoint

| Gate | Result |
| --- | --- |
| `pytest` (full suite) | 328 passed, 58 skipped |
| Coverage | 92.31% (gate: 80%) |
| `scripts/security.ps1` | PASS (secret scan: 233 targets, 0 findings) |
| `scripts/verify.ps1` | PASS (exit 0, end-to-end) |
| `ruff format --check .` / `ruff check .` | PASS |
| `mypy` | PASS, 0 issues, 73 source files |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS |
| `git diff --check` | PASS |
| Real PostgreSQL integration tests (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`) | 49 passed (M022 schema migration: exact structure, upgrade, downgrade, re-upgrade, atomicity, exhaustive constraint behavior, ordering) + 3 passed (pre-existing connectivity suite), re-verified against a freshly provisioned disposable instance as part of this freeze closure |

## 7. Accepted Residual Observations (carried forward, not blocking)

1. mypy does not type-check `tests/` (project config scopes to `src/empirical_platform` only). `ACCEPTED FOR FUTURE TOOLING MILESTONE`.
2. Same-package aggregate-to-mapper (and aggregate-to-repository) import prohibition is convention-enforced, not mechanically blocked by `tools/check_architecture.py` (same-top-level-module imports are always permitted by its logic). Verified true in practice for M020, M021, and M022; not currently tool-enforceable.
3. A future concrete mapper implementation milestone should add exhaustive per-field transition assertions beyond the current aggregate-level round-trip tests.
4. `setuptools` emits a `project.license` TOML-table deprecation warning during `python -m build` (SPDX-string migration required before 2027-02-18). Unrelated to M020/M021/M022; `pyproject.toml`-wide packaging metadata, not corrected in any of the three.
5. Future additional indexes may require explicit names if naming collisions become possible; the frozen M022 `naming_convention` is deterministic and collision-free for the schema this design specifies (including its automatic truncation of the foreign-key and, after correction, unique-constraint names on the `evidence_package_*` tables — see `MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_IMPLEMENTATION.md` Sections 5.1 and 14.1), but a future milestone adding indexes beyond this design's scope must re-verify collision-freedom rather than assume it.
6. M022's real-PostgreSQL integration tests remain opt-in (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`); `scripts/verify.ps1` does not set this variable, so these 49 tests show as skipped in the default gate. Any future work touching this schema must run the explicit suite to obtain real database evidence.
7. On Windows, `pg_ctl start -w` can return before the server is fully ready to accept connections in rare cases; disposable-instance setups for this and future milestones should verify readiness with an explicit connection probe rather than trusting the process return code alone.

## 8. Deferred Capabilities (explicitly not built, not authorized by any freeze to date)

- concrete mapper implementation against any storage technology (independent of M023, not selected as its scope);
- concrete repository implementation following the M023 design (design exists; implementation does not);
- SQL / ORM mapping beyond the M022 schema DDL itself;
- Unit of Work beyond the existing single-statement infrastructure primitive;
- application services, runtime composition, APIs, workers;
- Audit runtime, Decision Candidate, Decision Freeze;
- the one narrow `ALLOWED["shared"]` architecture-checker addition the M023 design identifies (to be made alongside its implementation, not before);
- any MILESTONE-024 work.

## 9. Next Authorized Work

Independent review of the MILESTONE-023 design described in Section 5.1, followed by Project Owner approval and a separate design-freeze mission, following the same design → freeze → implementation → freeze discipline used for MILESTONE-019 through MILESTONE-022. MILESTONE-023 implementation may not begin until its own design is independently reviewed and separately approved and frozen by the Project Owner.
