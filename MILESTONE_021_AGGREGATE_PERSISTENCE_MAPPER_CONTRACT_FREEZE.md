# MILESTONE-021 - Aggregate Persistence Mapper Contract Design Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-021-FREEZE |
| Title | Aggregate Persistence Mapper Contract Design Freeze |
| Version | 1.0 |
| Status | DESIGN APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Design freeze closure only |
| Implementation performed | No |
| Design semantics altered during this closure | No |

## 2. Authority Chain

This freeze closes the M021 design lineage as one approved unit. Neither commit is amended, squashed, or rewritten.

| Role | Commit | Summary |
| --- | --- | --- |
| Design | `06d22defd6f06b96d0a46c5e91bc169e55e674e5` | Design MILESTONE-021 aggregate persistence mapper contract |

Authoritative documents for this freeze:

- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_SCOPE_SELECTION.md`;
- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_DESIGN.md` (Version 1.0);
- `PROJECT_CHECKPOINT.md` (M021 status section);
- `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_FREEZE.md` (frozen prerequisite this design rests on).

Frozen baseline this design built on: MILESTONE-020 (domain repository and concurrency contract, freeze commit `40dd6b6a0c02e710e3f7efe84e8959af51f839f9`), itself resting on MILESTONE-019 (aggregate reconstruction contract). None of these are reopened, rewritten, or reinterpreted by this freeze.

## 3. Independent Review Outcome

Independent recommendation:

```text
M021 DESIGN APPROVED FOR OWNER FREEZE
```

The Project Owner accepted that recommendation and authorized this design freeze closure.

## 4. Accepted Design Observations

These are carried forward into implementation scope explicitly, not silently:

1. **Mapper-local error shape must be frozen explicitly during implementation.** The design (Section 13) deliberately deferred the exact error type/shape to implementation. This freeze does not resolve it; MILESTONE-021's implementation phase must, narrowly, before any mapper code is written.
2. **Durable records must remain field-level and schema-neutral.** No table, column, index, or SQL type may appear in any durable-record type at implementation time.
3. **Reconstruction factories remain internal.** Only mapper implementation modules gain the narrow, explicit authorization the design grants (Section 8); no other authorization is implied.
4. **Mapper architecture fixtures must cover SQLAlchemy, psycopg, boto3, and persistence imports.** Implementation must extend the negative-fixture pattern established in MILESTONE-020 to the four new mapper modules specifically.
5. **The `setuptools` `project.license` TOML-table deprecation warning remains non-blocking**, carried forward unchanged from the MILESTONE-020 freeze record; still unrelated to M021, still tracked for correction before 2027-02-18.

## 5. What This Freeze Does Not Authorize

Freezing the M021 *design* authorizes implementation of exactly what the design specifies (Sections 7-16 of the design document): four aggregate-specific mapper Protocols and their durable-record types. It does not authorize:

- PostgreSQL schema or migrations (`migrations/versions` remains empty);
- concrete repository implementations;
- Unit of Work beyond the existing single-statement infrastructure primitive;
- application services, runtime composition, APIs, or workers;
- any MILESTONE-022 work.

## 6. Final Status

```text
M021 DESIGN APPROVED AND FROZEN
```

No frozen historical MILESTONE-021 document (Scope Selection, Design) is rewritten by this closure; this document only adds the closure decision on top of them. Implementation may now proceed under a separate mission, subject to its own validation, hostile review, and commit discipline before any future approval or freeze of the implementation itself.
