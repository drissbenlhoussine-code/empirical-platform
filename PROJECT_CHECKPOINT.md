# PROJECT CHECKPOINT

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | PROJECT-CHECKPOINT |
| Purpose | Repository-authoritative record of the current frozen milestone and next authorized work |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at this checkpoint | `40dd6b6a0c02e710e3f7efe84e8959af51f839f9` |
| origin/master at this checkpoint | `40dd6b6a0c02e710e3f7efe84e8959af51f839f9` (identical — pushed) |

This document is updated at each milestone freeze or major checkpoint. It supersedes its own prior content; it does not rewrite any frozen milestone document.

## 2. Current State

```text
LATEST_FROZEN_MILESTONE=MILESTONE-020
M020_STATUS=APPROVED_AND_FROZEN
M020_DESIGN_COMMIT=fd96b70366a7bbed2172a8f51d7d7cc52b60bc41
M020_IMPLEMENTATION_COMMIT=e20bc76d2dc0be359cea2c385c210e081fb48a35
M020_CORRECTION_COMMIT=efed86be608471fdaa2956f7827fc9236209763a
M020_FREEZE_COMMIT=40dd6b6a0c02e710e3f7efe84e8959af51f839f9
M021_STATUS=NOT_IMPLEMENTED
```

## 3. MILESTONE-020 Summary

MILESTONE-020 froze the domain-facing repository and optimistic-concurrency **contract layer** for the four process-local aggregates (Campaign, Run, EvidencePackage, Review):

- `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` — `typing.Protocol` classes with exactly `get`/`add`/`save`;
- `LoadedAggregate`, `SaveOperation`, `SaveResult`, and a five-member `RepositoryContractError` hierarchy (`AggregateNotFound`, `AggregateAlreadyExists`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, `InvalidPersistedAggregateState`) in `empirical_platform.shared.contracts`.

**No database repository, persistence adapter, mapper, schema, or migration exists anywhere in the repository as of this checkpoint.** `migrations/versions` remains empty. The Protocols are contracts only; nothing implements them against PostgreSQL or any other storage.

Full detail: `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_{SCOPE_SELECTION,DESIGN,IMPLEMENTATION,FREEZE}.md`.

## 4. Validation at This Checkpoint

| Gate | Result |
| --- | --- |
| `pytest` (full suite) | 303 passed, 9 skipped |
| Coverage | 91.82% (gate: 80%) |
| `scripts/security.ps1` | PASS |
| `scripts/verify.ps1` | PASS (exit 0, end-to-end) |
| `ruff format --check .` / `ruff check .` | PASS |
| `mypy` | PASS, 0 issues, 68 source files |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `python -m build` | PASS |
| `git diff --check` | PASS |

## 5. Accepted Residual Observations (carried forward, not blocking)

1. mypy does not type-check `tests/` (project config scopes to `src/empirical_platform` only). `ACCEPTED FOR FUTURE TOOLING MILESTONE`.
2. `setuptools` emits a `project.license` TOML-table deprecation warning during `python -m build` (SPDX-string migration required before 2027-02-18). Unrelated to M020; `pyproject.toml`-wide packaging metadata, not corrected here.

## 6. MILESTONE-020 Deferred Capabilities (explicitly not built, not authorized by this freeze)

- repository implementations / persistence mappers;
- PostgreSQL schema and migrations;
- SQL / ORM mapping;
- Unit of Work implementation;
- application services, runtime composition, APIs, workers;
- Audit runtime, Decision Candidate, Decision Freeze;
- any MILESTONE-021 work.

## 7. MILESTONE-021 Status

Scope selected and design drafted this checkpoint cycle:

- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_SCOPE_SELECTION.md` — `SCOPE SELECTED - PENDING INDEPENDENT REVIEW`;
- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_DESIGN.md` — `DESIGN READY FOR INDEPENDENT REVIEW`.

Selected scope: an aggregate-specific, persistence-neutral **mapper contract** (`CampaignMapper`, `RunMapper`, `EvidencePackageMapper`, `ReviewMapper`) translating between frozen aggregates/reconstruction states and a field-level "durable record" concept — no schema, no SQL, no concrete repository implementation, no Unit of Work.

## 8. Next Authorized Work

Independent review of the MILESTONE-021 scope and design documents above. Implementation is **not** authorized until that review is complete and the Project Owner separately approves and (later) freezes the design, following the same design → implementation → freeze discipline used for MILESTONE-019 and MILESTONE-020. No MILESTONE-021 source code, mapper, schema, or migration exists as of this checkpoint.
