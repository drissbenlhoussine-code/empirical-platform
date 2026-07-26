# PROJECT CHECKPOINT

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | PROJECT-CHECKPOINT |
| Purpose | Repository-authoritative record of the current frozen milestone and next authorized work |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Checkpoint content baseline (HEAD this content was authored against) | `4ce800d3609ba7c621eadffc338bc5bc2503228d` (`chore: freeze MILESTONE-023 PostgreSQL repository adapters`, pushed) |
| Checkpoint content baseline origin/master | `4ce800d3609ba7c621eadffc338bc5bc2503228d` (identical — the M023 freeze lineage has been pushed) |

This document is updated at each milestone freeze or major checkpoint. It supersedes its own prior content; it does not rewrite any frozen milestone document.

**On self-reference:** the values in this table and in the `CHECKPOINT_CONTENT_BASELINE_*` fields below describe the repository state this checkpoint's content was *authored against* — they are not a live, self-updating record of Git HEAD. A document cannot cite the hash of the commit that first contains it without creating a recursive follow-up-commit cycle, so every edit to this file necessarily describes a baseline one commit behind the commit that carries the edit. **To find the live, current repository HEAD, run `git rev-parse HEAD` directly** — never infer it from this document. Within an external review package, `repository-truth.txt` (captured via live `git` commands at packaging time) is the authoritative source for live repository truth, not this file.

## 2. Current State

```text
LATEST_FROZEN_MILESTONE=MILESTONE-023
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
M023_DESIGN_COMMIT=a6e1350b8c37467d3a33b73c6e254c34ce4aab1b
M023_DESIGN_CORRECTION_COMMITS=7dcc7c10e247163d6e029fb6520fd76846e328d6,0f5c982a23f1b8c51ed5d56ff0a0cdab0c03c4bb,7933b567129e525ec4cf6235de3f22e3d737860f
M023_DESIGN_FREEZE_COMMIT=cb6ff16788b2ad8a26ed9f82a903d276daa6d3c4
M023_IMPLEMENTATION_COMMIT=4a93e44ea937885d45f5ce6587c2b963452ac8ff
M023_EVIDENCE_CORRECTION_COMMITS=f3f7fc097db37470dc731009176e065df1d5a70b,c6fb2c9d7f153d1b3fbee97a7b647d7ecca6d5af,5679034cf2f3887f7329cf56c5c73c1865208451
M023_IMPLEMENTATION_FREEZE_COMMIT=4ce800d3609ba7c621eadffc338bc5bc2503228d
M023_STATUS=APPROVED_AND_FROZEN
CHECKPOINT_CONTENT_BASELINE_BRANCH=master
CHECKPOINT_CONTENT_BASELINE_HEAD=4ce800d3609ba7c621eadffc338bc5bc2503228d
CHECKPOINT_CONTENT_BASELINE_ORIGIN=4ce800d3609ba7c621eadffc338bc5bc2503228d
CHECKPOINT_CONTENT_BASELINE_STATUS=PUSHED_UP_TO_DATE
M023_IMPLEMENTATION_APPROVAL=APPROVED
M023_IMPLEMENTATION_FREEZE=FROZEN
M024_SCOPE=Multi-Aggregate Persistence Unit of Work
M024_STATUS=SCOPE_SELECTED;DESIGN_READY_FOR_INDEPENDENT_REVIEW_NOT_APPROVED_NOT_FROZEN_NOT_IMPLEMENTED
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

`migrations/versions` contains exactly the one M022 revision. As of the M022 freeze, nothing yet implemented the M020 repository Protocols or M021 mapper Protocols against this schema — see Section 5.2 for the MILESTONE-023 implementation that now does.

## 5.1 MILESTONE-023 Design Summary (APPROVED AND FROZEN)

Following M022's freeze, MILESTONE-023 selected and designed the **PostgreSQL Repository Adapter**: the bridge between the frozen M020 Repository Protocols, M021 Mapper Protocols, and M022 schema that neither of those three milestones defines. The design specifies, for all four aggregates: the exact `get`/`add`/`save` call sequence (completing, not altering, the frozen `repository -> mapper -> ReconstructionState -> _reconstruct_*` chain); `DurableRecord`-to-SQL-column translation rules; optimistic-concurrency enforcement via a guarded `UPDATE ... WHERE version = :expected RETURNING version`; full-replace owned-collection write strategy (justified by the frozen `DurableRecord` shape carrying no per-item version/removal marker); a concrete error-translation table from real PostgreSQL/`FoundationError` conditions to the frozen `RepositoryContractError` vocabulary; and module placement under `shared.persistence.postgres_repositories.*`.

The design went through three correction rounds (commit-before-return semantics, save version precondition, general hardening) before an independent review returned "M023 DESIGN APPROVED FOR OWNER FREEZE"; the Project Owner then approved and froze the full four-commit lineage (`M023_DESIGN_COMMIT` through `M023_DESIGN_FREEZE_COMMIT` above), pushed fast-forward to `origin/master`.

Full detail: `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN_SCOPE_SELECTION.md`, `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN.md`, `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN_FREEZE.md`.

## 5.2 MILESTONE-023 Implementation Summary (APPROVED AND FROZEN)

The frozen M023 design has been implemented: four concrete mappers (`ConcreteCampaignMapper`, `ConcreteRunMapper`, `ConcreteEvidencePackageMapper`, `ConcreteReviewMapper`, added to each aggregate's existing `mapper.py`) satisfying the frozen M021 Protocols, and four concrete repository adapters (`PostgresCampaignRepository`, `PostgresRunRepository`, `PostgresEvidencePackageRepository`, `PostgresReviewRepository`, new `shared.persistence.postgres_repositories.*` modules) satisfying the frozen M020 Protocols against the frozen M022 schema — get/add/save exactly per the frozen 11-step save sequence, full-identity predicates, deterministic child ordering, atomic child-collection replacement, commit-before-return, and structured-fact-only error translation.

Implementing the frozen architecture change surfaced one necessary completion the design's own Phase 10 instruction did not anticipate: `ALLOWED["shared"]` also needed `identifiers` (not just the four aggregate packages), since every M020 Protocol signature the repositories implement verbatim takes `DomainIdentity[<X>Id]` parameters. This is documented in full in the implementation report, Section 10.

Both new test suites pass: 16 unit tests for the concrete mappers (no database), and 26 real-PostgreSQL integration tests (PostgreSQL 18.4, opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`) covering get/add/save across all four aggregates, optimistic concurrency (equal/greater/lower/stale version), duplicate detection, commit-before-return, and a genuine child-write-failure rollback proof. The full validation gate (`scripts/verify.ps1`) passes end-to-end: `344 passed, 84 skipped`.

Full detail: `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_IMPLEMENTATION.md`.

The implementation was hostile-self-reviewed (no defects found beyond the two already fixed above), packaged into `external-review/M023_POSTGRESQL_REPOSITORY_ADAPTER_IMPLEMENTATION/`, and committed locally as `4a93e44ea937885d45f5ce6587c2b963452ac8ff` (`feat: implement M023 PostgreSQL repository adapters`).

Three independent evidence/governance review rounds followed, each returning a single narrow, non-blocking correction and none finding any defect in the repository adapter source, concrete mapper source, tests, or PostgreSQL behavior itself: stale post-commit truth in `PROJECT_CHECKPOINT.md` left over from when the implementation was still staged (corrected in `f3f7fc097db37470dc731009176e065df1d5a70b`, which also fixed a file-count omission in the implementation report's own "Files Changed" list); a second round of the same staleness re-opened the moment the first correction landed (corrected in `c6fb2c9d7f153d1b3fbee97a7b647d7ecca6d5af`); and the root cause behind both — self-referentially named checkpoint fields — addressed by renaming them to the non-self-referential `CHECKPOINT_CONTENT_BASELINE_*` convention now used throughout this document (corrected in `5679034cf2f3887f7329cf56c5c73c1865208451`). None of these governance commits touched repository adapter source, concrete mapper source, or test content.

A final independent review of the complete four-commit lineage returned "M023 IMPLEMENTATION APPROVED FOR OWNER FREEZE". The Project Owner approved, and the implementation was frozen in `4ce800d3609ba7c621eadffc338bc5bc2503228d` (`chore: freeze MILESTONE-023 PostgreSQL repository adapters`), following a fresh, full validation re-run (Section 6). The complete five-commit lineage (`4a93e44`, `f3f7fc0`, `c6fb2c9`, `5679034`, `4ce800d`) has been pushed fast-forward to `origin/master`.

Full detail: `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_IMPLEMENTATION_FREEZE.md`.

**MILESTONE-023 is APPROVED AND FROZEN.**

## 5.3 MILESTONE-024 Scope and Design Summary (DESIGN READY FOR INDEPENDENT REVIEW — NOT approved, NOT frozen)

Following M023's freeze, MILESTONE-024 selected the **Multi-Aggregate Persistence Unit of Work**: a composition primitive letting a caller group two or more repository operations (potentially across different aggregate repositories) into one atomic transaction. This candidate had been evaluated and correctly deferred three times before — M020 Design Sections 18/26, M021 Design Section 15, and M023's own Scope Selection (Candidate D) and Design Section 11 — every time for the same reason: no concrete repository existed yet to design the composition against. M023's freeze resolved that blocker.

The design's public surface is exactly one new method, `PostgresPersistenceService.run_composed(operations)`, taking a sequence of zero-argument callables (each typically one repository call) and returning their results as a tuple **only after** the shared transaction they all ran inside has actually committed. Internally this is backed by a private `_ComposedTransaction`/`_JoinedUnitOfWork`/`_ActiveComposedScope`/`ContextVar` mechanism, entirely inside the existing `src/empirical_platform/shared/persistence/postgres.py` module. It changes **no** M020 Repository Protocol signature and **no** M023 concrete repository adapter source file — all four adapters participate correctly with zero changes. Single-operation behavior with no composed scope open is unchanged byte-for-byte from today's frozen M023 behavior.

An independent hostile review of the design's first version (v1.0) returned "M024 DESIGN REQUIRES NARROW CORRECTION" with two CRITICAL findings — (1) its original public `with service.composed_unit_of_work(): repo.save(...)` shape handed the caller a real, frozen-success-typed `SaveResult` inline, mid-transaction, before the outer commit, which could be mistaken for durable success; (2) its ambient `ContextVar` stored no owning-service reference, so a second, unrelated `PostgresPersistenceService` instance could silently join and operate against the wrong connection — plus four MAJOR findings (failure-unsafe `ContextVar` cleanup; a dishonest `PostgresUnitOfWork`-typed return annotation where a `_JoinedUnitOfWork` could also be returned; no defined behavior for repeated operations on the same aggregate identity within one composed scope; no defined mechanism for detecting and poisoning the scope when a joined operation's failure is caught and swallowed by the caller) and one MINOR finding (an unenforceable "handful of calls" phrasing). Version 1.1 replaced the public API with the callback/batch shape above, added an owner-checked `_ActiveComposedScope` record, froze token-based `try`/`finally` cleanup, corrected the return annotation to the existing `PersistenceUnitOfWork` Protocol, added full same-identity and nesting/service-identity behavior matrices, and froze exact poisoned-scope semantics — all without changing any M020 Protocol signature or any M023 adapter source file. Full account: Design document Section 23 (`M024-DESIGN-ISSUE-0006` through `0012`).

Full detail: `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_SCOPE_SELECTION.md`, `MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_DESIGN.md` (Version 1.1).

**This design is NOT approved, NOT frozen, and no repository/mapper/schema/application code has been created or modified by it.** It is ready for independent re-review, not yet approved. Repository runtime composition (Candidate E), application services (Candidate F), and retry policy (Candidate J) all remain independently deferred, not designed by this milestone.

## 6. Validation at This Checkpoint

Fresh re-run as part of M023's freeze closure:

| Gate | Result |
| --- | --- |
| `pytest` (full suite, `scripts/verify.ps1`) | 344 passed, 84 skipped |
| `scripts/security.ps1` | PASS (secret scan: 246 targets, 0 findings; `pip-audit`: no known vulnerabilities) |
| `scripts/verify.ps1` | PASS (exit 0, end-to-end) |
| `ruff format --check .` / `ruff check .` | PASS (150 files formatted) |
| `mypy` | PASS, 0 issues, 79 source files |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS |
| `git diff --check` | PASS |
| Real PostgreSQL integration tests (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, fresh disposable PostgreSQL 18.4 instance, torn down after) | 26 passed (M023 repository adapters: get/add/save across all four aggregates, concurrency, commit-before-return, rollback) |
| M023 concrete mapper unit tests (no database) | 16 passed |
| Pre-existing M020/M021 contract tests | 100 passed, no regression |

## 7. Accepted Residual Observations (carried forward, not blocking)

1. mypy does not type-check `tests/` (project config scopes to `src/empirical_platform` only). `ACCEPTED FOR FUTURE TOOLING MILESTONE`.
2. Same-package aggregate-to-mapper (and aggregate-to-repository) import prohibition is convention-enforced, not mechanically blocked by `tools/check_architecture.py` (same-top-level-module imports are always permitted by its logic). Verified true in practice for M020 through M023; not currently tool-enforceable.
3. `setuptools` emits a `project.license` TOML-table deprecation warning during `python -m build` (SPDX-string migration required before 2027-02-18). Unrelated to M020-M023; `pyproject.toml`-wide packaging metadata, not corrected in any of them.
4. Future additional indexes may require explicit names if naming collisions become possible; the frozen M022 `naming_convention` is deterministic and collision-free for the schema this design specifies, but a future milestone adding indexes beyond this design's scope must re-verify collision-freedom rather than assume it.
5. M022's and M023's real-PostgreSQL integration tests remain opt-in (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`); `scripts/verify.ps1` does not set this variable, so these tests show as skipped in the default gate. Any future work touching this schema/adapters must run the explicit suite to obtain real database evidence.
6. On Windows, `pg_ctl start -w` can return before the server is fully ready to accept connections in rare cases; disposable-instance setups for future milestones should verify readiness with an explicit connection probe rather than trusting the process return code alone.
7. Retry-on-`OptimisticConcurrencyConflict` remains application-owned per the frozen M020/M023 design; no repository or adapter retries internally.

## 8. Deferred Capabilities (explicitly not built, not authorized by any freeze to date)

- MILESTONE-024 implementation (design exists, pending independent review; not implemented);
- repository runtime composition, application services, APIs, workers;
- retry-on-`OptimisticConcurrencyConflict` policy;
- Audit runtime, Decision Candidate, Decision Freeze;
- any generic/shared concrete repository or mapper base class (deliberately not introduced by M023);
- any MILESTONE-025 work.

## 9. Next Authorized Work

Independent review of the MILESTONE-024 design described in Section 5.3 (`MILESTONE_024_MULTI_AGGREGATE_UNIT_OF_WORK_DESIGN.md`), followed by Project Owner approval and a separate design-freeze mission, following the same design → freeze → implementation → freeze discipline used for MILESTONE-019 through MILESTONE-023. MILESTONE-024 implementation may not begin until its own design is independently reviewed and separately approved and frozen by the Project Owner.
