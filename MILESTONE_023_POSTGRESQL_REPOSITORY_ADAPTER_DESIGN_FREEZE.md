# MILESTONE-023 - PostgreSQL Repository Adapter Design Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-023-DESIGN-FREEZE |
| Title | PostgreSQL Repository Adapter Design Freeze |
| Version | 1.0 |
| Status | M023 DESIGN APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Freeze closure only |
| Implementation performed during this closure | No |
| Frozen design semantics altered | No |

## 2. Authority Chain

| Role | Commit | Summary |
| --- | --- | --- |
| Initial Design | `a6e1350b8c37467d3a33b73c6e254c34ce4aab1b` | Design MILESTONE-023 PostgreSQL repository adapter |
| First Correction | `7dcc7c10e247163d6e029fb6520fd76846e328d6` | Harden MILESTONE-023 PostgreSQL repository adapter design |
| Second Correction | `0f5c982a23f1b8c51ed5d56ff0a0cdab0c03c4bb` | Harden MILESTONE-023 save version precondition |
| Final Correction | `7933b567129e525ec4cf6235de3f22e3d737860f` | Harden MILESTONE-023 commit-before-return semantics |

Authoritative documents for this freeze:

- `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN_SCOPE_SELECTION.md`;
- `MILESTONE_023_POSTGRESQL_REPOSITORY_ADAPTER_DESIGN.md` (Version 1.3, final correction).

Frozen baseline this design built on: MILESTONE-022 (PostgreSQL schema/migration implementation freeze commit `10425e85b63a0b6f18b73b962355f22176cb279c`) and, transitively, MILESTONE-021, MILESTONE-020, and MILESTONE-019. None are reopened, rewritten, or reinterpreted by this freeze.

## 3. Independent Review Outcome

The design went through three independent correction rounds before approval:

1. First review: "M023 DESIGN REQUIRES NARROW CORRECTION" — save version semantics (repository-owned increment), unchanged-save detection, incomplete identity predicates, unstable add-duplicate translation, a self-contradictory module-placement statement, an under-specified field mapping, ambiguous transaction ownership, an undefended zero-row race, and unstated error-leakage rules. Resolved in the first correction commit.
2. Second review: "M023 DESIGN REQUIRES ANOTHER NARROW CORRECTION" — one remaining blocking defect: a false claim that the guarded `UPDATE`'s `WHERE` clause would reject a lower `record.version` on its own. Resolved in the second correction commit with an explicit pre-SQL precondition.
3. Third review: "M023 DESIGN REQUIRES ANOTHER NARROW CORRECTION" — one remaining documentation ambiguity: `save()`'s canonical sequence described returning `SaveResult` ahead of the explicit commit step. Resolved in the final correction commit with an explicit 11-step sequence in which no step before a successful `commit()` ever returns a result.
4. Final review:

```text
M023 DESIGN APPROVED FOR OWNER FREEZE
```

The Project Owner accepted that recommendation and authorized this design freeze closure.

## 4. What Was Frozen

The complete design for a concrete PostgreSQL repository adapter bridging the frozen M020 Repository Protocols, M021 Mapper Protocols, and M022 schema, for all four aggregates (Campaign, Run, EvidencePackage, Review):

- exact `get`/`add`/`save` call sequences, completing (not altering) the frozen `repository -> mapper -> ReconstructionState -> _reconstruct_* -> aggregate` chain;
- exact `DurableRecord`-to-SQL-column translation rules for every table;
- optimistic-concurrency enforcement via a single guarded `UPDATE ... WHERE runtime_id = ... AND governance_id = ... AND version = :expected_persisted_version RETURNING version`, with the repository never incrementing `AggregateVersion` itself;
- an explicit, unconditional pre-SQL precondition rejecting `record.version < expected_persisted_version` as `InvalidAggregateForPersistence`;
- a fully specified `SaveOperation.UNCHANGED` algorithm (equal version still validates via the guarded `UPDATE`, but never rewrites owned collections);
- full-`DomainIdentity` predicates (both `governance_id` and `runtime_id`) for every operation that identifies one persisted aggregate, with an explicit identity-mismatch classification (`InvalidPersistedAggregateState`);
- a stable, SQLSTATE/constraint-name-keyed error-translation table (never parsed message text) mapping real PostgreSQL/`FoundationError` conditions to the frozen `RepositoryContractError` vocabulary, with an explicit no-leakage rule;
- an explicit commit-before-return guarantee: `SaveResult` is constructed and returned only after a successful `commit()`, never before, on any path;
- module placement at `empirical_platform.shared.persistence.postgres_repositories.<x>_repository`, requiring exactly one narrow, disclosed architecture-checker change (`ALLOWED["shared"]` gaining `{"campaign", "run", "evidence", "review"}`, `FORBIDDEN_IMPORT_PREFIXES` unchanged) and one new negative fixture.

## 5. Accepted Observations

Carried forward explicitly into implementation scope, not silently:

1. **Implementation must prove commit-before-return against real PostgreSQL.** Design-level assertion is not sufficient; the implementation must demonstrate, for both the `UNCHANGED` and `UPDATED` branches, that durable state is visible from a separate connection only after `save()` returns, and that a forced commit failure returns no `SaveResult`.
2. **Implementation must prove lower-version rejection executes no SQL and opens no Unit of Work.** This is a precondition checked in Python before any transaction opens; the implementation's test suite must demonstrate zero database round trips for this path, not merely assert the raised exception type.
3. **Optimistic concurrency must use the complete `DomainIdentity`** (both `governance_id` and `runtime_id`) in every predicate that identifies a specific persisted aggregate — never `runtime_id` alone — with the identity-mismatch case empirically distinguished from ordinary absence.
4. **Same-package architecture restrictions remain partly convention-enforced, not mechanically enforced**, carried forward unchanged from M020/M021/M022 (the checker cannot detect a same-top-level-module aggregate-to-mapper-to-repository call chain misuse within `shared.persistence` itself; this remains disclosed, not resolved, by this design).
5. **`mypy` does not type-check `tests/`**, carried forward unchanged from M020/M021/M022.
6. **`setuptools` `project.license` TOML-table deprecation remains non-blocking**, carried forward unchanged; still unrelated to M023, still tracked for correction before 2027-02-18.

## 6. What This Freeze Does Not Authorize

Freezing the M023 design authorizes implementation of exactly the repository-adapter bridge this design specifies, for all four aggregates, plus the concrete mapper functionality strictly required to satisfy it. It does not authorize:

- multi-statement or multi-aggregate Unit of Work;
- repository runtime composition, dependency injection wiring, APIs, or workers;
- application services;
- any MILESTONE-024 work.

## 7. Final Status

```text
M023 DESIGN APPROVED AND FROZEN
```

No frozen historical MILESTONE-023 document is rewritten by this closure; this document only adds the closure decision on top of them. Implementation may now proceed under a separate mission phase, subject to its own validation, hostile review, and commit discipline before any future approval or freeze of the implementation itself.
