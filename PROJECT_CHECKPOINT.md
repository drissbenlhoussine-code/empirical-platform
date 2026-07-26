# PROJECT CHECKPOINT

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | PROJECT-CHECKPOINT |
| Purpose | Repository-authoritative record of the current frozen milestone and next authorized work |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at this checkpoint | `fdb180a2b21776cf37fe36826741a54ef7b43ad4` |
| origin/master at this checkpoint | `fdb180a2b21776cf37fe36826741a54ef7b43ad4` (identical — pushed) |

This document is updated at each milestone freeze or major checkpoint. It supersedes its own prior content; it does not rewrite any frozen milestone document.

## 2. Current State

```text
LATEST_FROZEN_MILESTONE=MILESTONE-021
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
M022_STATUS=NOT_STARTED
```

## 3. MILESTONE-020 Summary (frozen)

MILESTONE-020 froze the domain-facing repository and optimistic-concurrency **contract layer** for the four process-local aggregates (Campaign, Run, EvidencePackage, Review): `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` (`typing.Protocol`, exactly `get`/`add`/`save`); `LoadedAggregate`, `SaveOperation`, `SaveResult`, and a five-member `RepositoryContractError` hierarchy in `empirical_platform.shared.contracts`.

Full detail: `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_{SCOPE_SELECTION,DESIGN,IMPLEMENTATION,FREEZE}.md`.

## 4. MILESTONE-021 Summary (frozen)

MILESTONE-021 froze the persistence **mapper contract layer** for the same four aggregates: `CampaignMapper`, `RunMapper`, `EvidencePackageMapper`, `ReviewMapper` (`typing.Protocol`, exactly `to_durable_record`/`from_durable_record`); four aggregate-specific durable-record types (plus three nested ones); a mapper-local `MapperError`/`MapperErrorCategory`, verified distinct from the M020 repository error taxonomy; and a shared `IdentityDurableRecord`/`TransitionDurableRecord` pair reused across all four mappers.

**No database repository, persistence adapter, concrete mapper implementation, schema, or migration exists anywhere in the repository as of this checkpoint.** `migrations/versions` remains empty. Both the M020 repository Protocols and the M021 mapper Protocols are contracts only; nothing implements either against PostgreSQL or any other storage.

Full detail: `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_{SCOPE_SELECTION,DESIGN,FREEZE,IMPLEMENTATION_SCOPE_SELECTION,IMPLEMENTATION,IMPLEMENTATION_FREEZE}.md`.

## 5. Validation at This Checkpoint

| Gate | Result |
| --- | --- |
| `pytest` (full suite) | 328 passed, 9 skipped |
| Coverage | 92.31% (gate: 80%) |
| `scripts/security.ps1` | PASS |
| `scripts/verify.ps1` | PASS (exit 0, end-to-end) |
| `ruff format --check .` / `ruff check .` | PASS |
| `mypy` | PASS, 0 issues, 73 source files |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS |
| `git diff --check` | PASS |

## 6. Accepted Residual Observations (carried forward, not blocking)

1. mypy does not type-check `tests/` (project config scopes to `src/empirical_platform` only). `ACCEPTED FOR FUTURE TOOLING MILESTONE`.
2. Same-package aggregate-to-mapper (and aggregate-to-repository) import prohibition is convention-enforced, not mechanically blocked by `tools/check_architecture.py` (same-top-level-module imports are always permitted by its logic). Verified true in practice for both M020 and M021; not currently tool-enforceable.
3. A future concrete mapper implementation milestone should add exhaustive per-field transition assertions beyond the current aggregate-level round-trip tests.
4. `setuptools` emits a `project.license` TOML-table deprecation warning during `python -m build` (SPDX-string migration required before 2027-02-18). Unrelated to M020/M021; `pyproject.toml`-wide packaging metadata, not corrected in either milestone.

## 7. Deferred Capabilities (explicitly not built, not authorized by any freeze to date)

- concrete mapper implementation against any storage technology;
- repository implementations;
- PostgreSQL schema and migrations;
- SQL / ORM mapping;
- Unit of Work beyond the existing single-statement infrastructure primitive;
- application services, runtime composition, APIs, workers;
- Audit runtime, Decision Candidate, Decision Freeze;
- any MILESTONE-022 work.

## 8. Next Authorized Work

MILESTONE-022 scope selection and design only, per the current mission. Implementation is **not** authorized until that design is independently reviewed and separately approved and frozen by the Project Owner, following the same design → implementation → freeze discipline used for MILESTONE-019, MILESTONE-020, and MILESTONE-021.
