# MILESTONE-022 - PostgreSQL Schema and Migration Design

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-022 |
| Title | PostgreSQL Schema and Migration Design |
| Version | 1.0 |
| Status | DESIGN READY FOR INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Design baseline | `fdb180a2b21776cf37fe36826741a54ef7b43ad4` |
| Scope authority | `MILESTONE_022_POSTGRESQL_SCHEMA_AND_MIGRATION_DESIGN_SCOPE_SELECTION.md` |
| Mission type | Schema design only |
| Migration files created | No |
| SQL/DDL written or executed | No |
| Repositories, mappers, Unit of Work implemented | No |

## 2. Baseline

Repository facts at design time (verified live):

- MILESTONE-021 mapper contract is frozen and implemented: `CampaignDurableRecord`, `RunDurableRecord` (+ `DatasetManifestDurableRecord`), `EvidencePackageDurableRecord` (+ `CriterionResultDurableRecord`), `ReviewDurableRecord` (+ `ReviewFindingDurableRecord`), and shared `IdentityDurableRecord`/`TransitionDurableRecord` are field-complete.
- `empirical_platform.shared.persistence.postgres` uses SQLAlchemy Engine/Core only (verified: no `declarative`, `DeclarativeBase`, `Table(`, or `MetaData` usage anywhere in that module).
- `migrations/versions/` is empty; `migrations/env.py` has `target_metadata = None`; `alembic.ini` carries no schema or naming-convention configuration.
- No repository, mapper implementation, schema, or migration revision exists anywhere in the repository.

## 3. Problem Statement

MILESTONE-021 froze exactly what fields a mapper produces and consumes for each aggregate. MILESTONE-022 defines the relational structure those fields map onto — table shape, keys, constraints, column types, and migration revision strategy — without writing the SQL or migration file that would make it real. This closes the gap both MILESTONE-020 and MILESTONE-021 explicitly left open: neither could responsibly design a schema before the durable/mapping shape was known; it is now known and frozen.

## 4. Design Principles

1. Every table and column traces directly to a frozen M021 durable-record field. No column is invented that does not correspond to a field already frozen by M021.
2. Schema constraints enforce **structural** integrity only (primary keys, foreign keys, NOT NULL where a field is never absent, uniqueness where M020 already freezes a uniqueness rule). Schema constraints do not re-implement **business-rule** validation already frozen at the reconstruction layer (M019) — for example, no CHECK constraint attempts to enforce "a completed Review requires a disposition and rationale"; that rule remains reconstruction's sole authority, avoiding two divergent sources of truth for the same rule.
3. Ordered collections without their own natural sequence field (`DatasetManifest`, `CriterionResult`, `ArtifactReference` — none of which the frozen aggregate/durable-record types number) receive an explicit `position` column. Ordered collections that already carry their own frozen sequence field (`StateTransitionRecord.sequence`, `ReviewFinding.sequence`) use that field directly as part of their primary key, which gives uniqueness and ordering together for free.
4. One child table per owned collection, one row per element, keyed by `(parent_runtime_id, position_or_sequence)`. No collection is flattened into a JSON column: every durable-record field this design covers already has an explicit, named, typed field (per Design Principle 1), so a structured child table row is a more faithful, query-able mapping than an opaque JSON blob, and keeps this design's constraints (Design Principle 2) actually enforceable by the database.
5. Simple flat string lists with no further structure (`DatasetManifest.notes`, `CriterionResult.evidence_references`, `ReviewFinding.evidence_references`) are represented as native PostgreSQL `TEXT[]` array columns rather than yet another child table, as a deliberate, disclosed simplification (Section 12) rather than full normalization of every scalar list.
6. `TransitionDurableRecord.identity_reference` is preserved as its own nullable column pair on every transition child table, even though it is observed (Section 11) to always equal the parent aggregate's own identity in the current frozen aggregate implementations. This design maps the frozen durable record faithfully rather than optimizing away a field based on an implementation detail that M019/M020/M021 do not freeze as a guaranteed invariant.
7. No table, column, or migration is created by this design. It is a specification for a future implementation milestone to build from.

## 5. Schema Design Options

| Option | Description | Query-ability | Constraint enforceability | Normalization risk | Decision |
| --- | --- | --- | --- | --- | --- |
| A | One table per aggregate root plus one child table per owned collection, keyed by identity + position/sequence | High | High | Low | Selected |
| B | One denormalized table per aggregate with owned collections serialized into JSON columns | Medium | Low (constraints can't reach into JSON) | Low | Rejected |
| C | Fully normalized, including array-typed simple string lists split into their own child tables | High | High | High (table proliferation for trivial data) | Rejected |
| D | Single shared polymorphic table for all four aggregates with a discriminator column | Low | Low | High (loses per-aggregate column typing) | Rejected |

Option A is selected because it keeps every frozen durable-record field individually typed, queryable, and constrainable, without the discriminator-driven type erasure of Option D or the JSON-opacity of Option B. Option C's full normalization of trivial flat string lists was rejected as disproportionate; Design Principle 5 documents the deliberate, narrower simplification actually selected.

## 6. Naming and Key Conventions

- Table names are lower-case, singular, aggregate-named (`campaign`, `run`, `evidence_package`, `review`) plus a collection suffix for child tables (`campaign_transition`, `run_manifest`, `evidence_package_criterion_result`, `evidence_package_artifact_reference`, `review_finding`, `review_transition`, `run_transition`, `evidence_package_transition`).
- Every aggregate root table's primary key is its `runtime_id` (UUID), matching `IdentityDurableRecord.runtime_id` exactly — the opaque, immutable, collision-resistant identity M012 already established as the canonical runtime identity.
- Every aggregate root table also carries `governance_id` (TEXT) with its own `UNIQUE NOT NULL` constraint, matching `IdentityDurableRecord.governance_id` and mirroring the frozen M020 uniqueness rule ("per aggregate type, `governance_id` is unique, `runtime_id` is unique, and both form one canonical `DomainIdentity`").
- Every child table's primary key is a composite of its parent's `runtime_id` foreign key plus either `position` (collections without a frozen sequence field) or `sequence` (collections that already have one), giving uniqueness and stable ordering from the same columns.
- Cross-aggregate context references (`run.campaign_id`, `evidence_package.run_id`, `review.target_evidence_package_id`) are foreign keys against the referenced aggregate's `governance_id` column (not `runtime_id`), because the frozen durable records themselves carry the governance-shaped context identifier (e.g. `RunDurableRecord.campaign_id: str`, not a runtime UUID) — the schema follows what the durable record actually contains rather than introducing a lookup the mapper contract does not provide.

## 7. Campaign Schema

| Table | Column | Type | Constraint | Durable-record source |
| --- | --- | --- | --- | --- |
| `campaign` | `runtime_id` | UUID | PRIMARY KEY | `identity.runtime_id` |
| `campaign` | `governance_id` | TEXT | UNIQUE, NOT NULL | `identity.governance_id` |
| `campaign` | `scope_statement` | TEXT | NOT NULL | `scope_statement` |
| `campaign` | `lifecycle_state` | TEXT | NOT NULL | `lifecycle_state` |
| `campaign` | `version` | INTEGER | NOT NULL | `version` |
| `campaign` | `next_transition_sequence` | INTEGER | NOT NULL | `next_transition_sequence` |
| `campaign_transition` | `campaign_runtime_id` | UUID | PK part, FK -> `campaign.runtime_id` | (parent) |
| `campaign_transition` | `sequence` | INTEGER | PK part | `transition_history[].sequence` |
| `campaign_transition` | `from_state` | TEXT | NULL | `transition_history[].from_state` |
| `campaign_transition` | `to_state` | TEXT | NOT NULL | `transition_history[].to_state` |
| `campaign_transition` | `version` | INTEGER | NOT NULL | `transition_history[].version` |
| `campaign_transition` | `actor` | TEXT | NOT NULL | `transition_history[].actor` |
| `campaign_transition` | `occurred_at` | TIMESTAMPTZ | NOT NULL | `transition_history[].occurred_at` |
| `campaign_transition` | `identity_governance_id` | TEXT | NULL | `transition_history[].identity_reference.governance_id` |
| `campaign_transition` | `identity_runtime_id` | UUID | NULL | `transition_history[].identity_reference.runtime_id` |
| `campaign_transition` | `correlation_id` | TEXT | NULL | `transition_history[].correlation_id` |
| `campaign_transition` | `reason` | TEXT | NULL | `transition_history[].reason` |

`campaign_transition` primary key: `(campaign_runtime_id, sequence)`.

## 8. Run Schema

| Table | Column | Type | Constraint | Durable-record source |
| --- | --- | --- | --- | --- |
| `run` | `runtime_id` | UUID | PRIMARY KEY | `identity.runtime_id` |
| `run` | `governance_id` | TEXT | UNIQUE, NOT NULL | `identity.governance_id` |
| `run` | `campaign_id` | TEXT | NOT NULL, FK -> `campaign.governance_id` | `campaign_id` |
| `run` | `lifecycle_state` | TEXT | NOT NULL | `lifecycle_state` |
| `run` | `version` | INTEGER | NOT NULL | `version` |
| `run` | `next_transition_sequence` | INTEGER | NOT NULL | `next_transition_sequence` |
| `run_manifest` | `run_runtime_id` | UUID | PK part, FK -> `run.runtime_id` | (parent) |
| `run_manifest` | `position` | INTEGER | PK part | (ordinal index; `manifests` has no frozen sequence field) |
| `run_manifest` | `manifest_id` | TEXT | NULL, partial-unique (Section 12) | `manifests[].manifest_id` |
| `run_manifest` | `recorded_at` | TIMESTAMPTZ | NOT NULL | `manifests[].recorded_at` |
| `run_manifest` | `source` | TEXT | NOT NULL | `manifests[].source` |
| `run_manifest` | `acquisition_method` | TEXT | NULL | `manifests[].acquisition_method` |
| `run_manifest` | `normalization_method` | TEXT | NULL | `manifests[].normalization_method` |
| `run_manifest` | `notes` | TEXT[] | NOT NULL, default `{}` | `manifests[].notes` |
| `run_transition` | (same shape as `campaign_transition`, keyed by `run_runtime_id`) | | | `transition_history[]` |

`run_manifest` primary key: `(run_runtime_id, position)`. Partial unique index: `UNIQUE (run_runtime_id, manifest_id) WHERE manifest_id IS NOT NULL`, mirroring the frozen M019 rule ("duplicate non-null `manifest_id` rejected; repeated unidentified manifest allowed") structurally.

## 9. EvidencePackage Schema

| Table | Column | Type | Constraint | Durable-record source |
| --- | --- | --- | --- | --- |
| `evidence_package` | `runtime_id` | UUID | PRIMARY KEY | `identity.runtime_id` |
| `evidence_package` | `governance_id` | TEXT | UNIQUE, NOT NULL | `identity.governance_id` |
| `evidence_package` | `run_id` | TEXT | NOT NULL, FK -> `run.governance_id` | `run_id` |
| `evidence_package` | `lifecycle_state` | TEXT | NOT NULL | `lifecycle_state` |
| `evidence_package` | `version` | INTEGER | NOT NULL | `version` |
| `evidence_package` | `next_transition_sequence` | INTEGER | NOT NULL | `next_transition_sequence` |
| `evidence_package_criterion_result` | `evidence_package_runtime_id` | UUID | PK part, FK -> `evidence_package.runtime_id` | (parent) |
| `evidence_package_criterion_result` | `position` | INTEGER | PK part | (ordinal index) |
| `evidence_package_criterion_result` | `criterion_id` | TEXT | NOT NULL, UNIQUE per parent | `criterion_results[].criterion_id` |
| `evidence_package_criterion_result` | `recorded_at` | TIMESTAMPTZ | NOT NULL | `criterion_results[].recorded_at` |
| `evidence_package_criterion_result` | `result_label` | TEXT | NOT NULL | `criterion_results[].result_label` |
| `evidence_package_criterion_result` | `summary` | TEXT | NULL | `criterion_results[].summary` |
| `evidence_package_criterion_result` | `evidence_references` | TEXT[] | NOT NULL, default `{}` | `criterion_results[].evidence_references` |
| `evidence_package_artifact_reference` | `evidence_package_runtime_id` | UUID | PK part, FK -> `evidence_package.runtime_id` | (parent) |
| `evidence_package_artifact_reference` | `value` | TEXT | PK part | `artifact_references[]` |
| `evidence_package_artifact_reference` | `position` | INTEGER | NOT NULL | (ordinal index, not part of the key — see Section 12) |
| `evidence_package_transition` | (same shape as `campaign_transition`, keyed by `evidence_package_runtime_id`) | | | `transition_history[]` |

`evidence_package_criterion_result` primary key: `(evidence_package_runtime_id, position)`, plus `UNIQUE (evidence_package_runtime_id, criterion_id)`, mirroring the frozen M019 rule that `criterion_id` is always present (unlike `manifest_id`) and always unique per package — no partial index needed. `evidence_package_artifact_reference` primary key: `(evidence_package_runtime_id, value)`, directly mirroring the frozen M019 "duplicate exact artifact value rejected" rule as a structural key rather than a separate constraint.

## 10. Review Schema

| Table | Column | Type | Constraint | Durable-record source |
| --- | --- | --- | --- | --- |
| `review` | `runtime_id` | UUID | PRIMARY KEY | `identity.runtime_id` |
| `review` | `governance_id` | TEXT | UNIQUE, NOT NULL | `identity.governance_id` |
| `review` | `target_evidence_package_id` | TEXT | NOT NULL, FK -> `evidence_package.governance_id` | `target_evidence_package_id` |
| `review` | `reviewer_reference` | TEXT | NOT NULL | `reviewer_reference` |
| `review` | `lifecycle_state` | TEXT | NOT NULL | `lifecycle_state` |
| `review` | `disposition` | TEXT | NULL | `disposition` |
| `review` | `final_disposition_rationale` | TEXT | NULL | `final_disposition_rationale` |
| `review` | `cancellation_reason` | TEXT | NULL | `cancellation_reason` |
| `review` | `version` | INTEGER | NOT NULL | `version` |
| `review` | `next_transition_sequence` | INTEGER | NOT NULL | `next_transition_sequence` |
| `review_finding` | `review_runtime_id` | UUID | PK part, FK -> `review.runtime_id` | (parent) |
| `review_finding` | `sequence` | INTEGER | PK part | `findings[].sequence` |
| `review_finding` | `text` | TEXT | NOT NULL | `findings[].text` |
| `review_finding` | `rationale` | TEXT | NULL | `findings[].rationale` |
| `review_finding` | `evidence_references` | TEXT[] | NOT NULL, default `{}` | `findings[].evidence_references` |
| `review_transition` | (same shape as `campaign_transition`, keyed by `review_runtime_id`) | | | `transition_history[]` |

`review_finding` primary key: `(review_runtime_id, sequence)`, using `ReviewFinding`'s own frozen, contiguous-from-1 sequence field directly, exactly as Design Principle 3 anticipates.

## 11. Identity-Reference Redundancy (Observed, Not Eliminated)

Live inspection of every frozen aggregate's `_transition` method (Campaign, Run, EvidencePackage, Review, all identical in shape) confirms `identity_reference` is always set to the aggregate's own current identity at the moment of transition — no frozen aggregate ever records a transition with a *different* identity than its own. This makes `campaign_transition.identity_governance_id`/`identity_runtime_id` (and the equivalent columns on the other three transition tables) fully redundant with `campaign_transition.campaign_runtime_id` in every case observed today.

This design does not eliminate the redundant columns (Design Principle 6): "always true today" is not the same as "frozen as an invariant" by M019/M020/M021, and a schema that silently drops a frozen durable-record field on the assumption it is always derivable would be inventing a schema-level assumption the mapper contract does not make. The columns are kept, nullable, faithfully mirroring the durable record. A future implementation milestone may revisit this as a storage optimization only if a future design explicitly re-examines and freezes that assumption; this design does not pre-authorize that.

## 12. Deliberate Simplifications (Disclosed)

- `TEXT[]` array columns for `notes`, `evidence_references` (both occurrences): a full normalization into per-element child tables was considered (Option C, Section 5) and rejected as disproportionate for flat, orderless-enough, no-further-structure string lists. This is a narrower, explicitly bounded simplification, not a general license to collapse structured data into arrays elsewhere in this design.
- `evidence_package_artifact_reference.position`: kept as a plain column, not part of the primary key, because the primary key is already the natural, domain-meaningful `(evidence_package_runtime_id, value)` pair (mirroring the uniqueness rule directly); `position` exists solely to let a future query `ORDER BY position` recover original insertion order without relying on physical storage order, which PostgreSQL does not guarantee.

## 12.1 SQLAlchemy Core Versus Raw DDL (Deferred, Bounded)

The scope selection named this a required comparison. Evaluated:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| SQLAlchemy Core `Table`/`MetaData` objects (Alembic's `op.create_table`) | Consistent with the existing Engine/Core-only adapter; Alembic-idiomatic; autogeneration-friendly for future revisions | None material | Preferred |
| Raw DDL strings executed via `op.execute` | Full control over exact SQL | Bypasses Alembic's own schema-diffing tooling for no evident benefit here; inconsistent with the Core-only adapter style already established | Rejected |

This design prefers SQLAlchemy Core `Table`/`MetaData` for the eventual migration, consistent with Design Principle 1's "no ORM" boundary (Core is not the ORM layer) and the existing adapter's established style. The exact Python code is not written by this design (Section 20); a future implementation milestone must use Core, not raw DDL strings, unless it discovers a concrete blocker this design did not anticipate, in which case that becomes a documented deviation, not a silent one.

## 13. Migration Revision Strategy

Options evaluated:

| Option | Strength | Risk | Decision |
| --- | --- | --- | --- |
| One revision creating all four aggregates' tables together | Matches "all four aggregates together" discipline already used for scope/design in M020/M021; one atomic bootstrap | Larger single revision to review | Selected |
| One revision per aggregate (four revisions) | Smaller individual diffs | Introduces an artificial partial-schema state between revisions (e.g. `run` referencing `campaign` before `campaign` exists in a piecemeal apply) that never corresponds to any real, reviewed milestone state | Rejected |
| One revision per table (many revisions) | Maximally granular | Excessive churn for a bootstrap; no evidence any table needs independent rollback from its siblings | Rejected |

Selected: a single Alembic revision creating all eleven tables (`campaign`, `campaign_transition`, `run`, `run_manifest`, `run_transition`, `evidence_package`, `evidence_package_criterion_result`, `evidence_package_artifact_reference`, `evidence_package_transition`, `review`, `review_finding`, `review_transition`) together, in dependency order (parents before children, `campaign` before `run` before `evidence_package` before `review`, matching the frozen context-reference direction). This design does not write that revision; a future implementation milestone does.

## 14. Reconstruction and Mapper Integration

This design does not alter the frozen M021 mapper contract or M019 reconstruction contract in any way. It defines only the relational target a future concrete mapper implementation (deferred; MILESTONE-022 Scope Selection Candidate B) would read from and write to. The frozen call direction (`repository implementation -> mapper -> ReconstructionState -> _reconstruct_* -> aggregate`) is unaffected; this design only makes the leftmost arrow ("repository implementation" reading/writing storage) concrete enough to eventually implement.

## 15. Test Strategy (for a future Implementation milestone)

Defined here, not implemented: migration apply/rollback correctness (`alembic upgrade head` / `alembic downgrade base` both succeed against a disposable database); every structural constraint in Sections 7-10 is exercised (primary key violations, foreign key violations, the partial-unique `manifest_id` rule, the `criterion_id`/`artifact_reference` uniqueness rules); column-type round-trip fidelity against real M021 durable-record values, including `TEXT[]` arrays and `TIMESTAMPTZ` timezone handling.

## 16. Architecture Enforcement

No `tools/check_architecture.py` change is anticipated. This design touches no `src/empirical_platform` package; it is entirely `migrations/`-facing. A future implementation milestone creating actual migration files should confirm this remains true rather than assume it.

## 17. Security Considerations

No credential material or connection string is introduced by this design; unchanged from the existing `PersistenceService` infrastructure boundary. `actor`, `reason`, `correlation_id`, and free-text fields (`scope_statement`, `summary`, `rationale`, findings `text`) are plain `TEXT` columns with no special handling proposed; this design does not identify a secret-shaped field among any frozen durable record.

## 18. Migration Implications

This design, by itself, creates no migration. It specifies exactly what a future single Alembic revision (Section 13) must contain. `migrations/versions/` remains empty after this design.

## 19. Compatibility with M019, M020, and M021

- No frozen M019 aggregate, lifecycle, or reconstruction source file is referenced for modification.
- No frozen M020 repository contract or M021 mapper contract, Protocol, or durable-record type is modified.
- Every column in this design traces to an already-frozen durable-record field (Design Principle 1); no new field is introduced anywhere in this document.

## 20. Explicit Non-Goals

MILESTONE-022 must not:

- write SQL or DDL;
- create Alembic migration revision files;
- implement mappers, repositories, or Unit of Work;
- implement runtime composition, APIs, or workers;
- introduce Audit, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior;
- re-implement M019 domain/reconstruction business-rule validation as database constraints (Design Principle 2).

## 21. Deferred Work

Deferred after MILESTONE-022:

- migration revision file authoring and execution;
- concrete mapper implementation;
- concrete PostgreSQL repository implementations;
- Unit of Work integration beyond the existing single-statement primitive;
- application services, runtime composition, API and worker integration;
- read models and projections;
- Audit runtime, Decision Candidate, Decision Freeze.

## 22. Hostile Self-Review

| ID | Severity | Section | Issue considered | Impact | Decision | Disposition |
| --- | --- | --- | --- | --- | --- | --- |
| M022-DESIGN-ISSUE-0001 | MAJOR | 4, 20 | Initial draft risked adding CHECK constraints mirroring M019's terminal-metadata rules (e.g. "completed Review requires disposition"). | Would create a second, potentially divergent source of truth for a frozen business rule. | Restricted schema constraints to structural integrity only (Design Principle 2); business-rule validation stays exclusively at the reconstruction layer. | Resolved |
| M022-DESIGN-ISSUE-0002 | MAJOR | 6 | Considered keying aggregate root tables by `governance_id` (human-readable) rather than `runtime_id` (opaque UUID). | Would contradict M012's frozen governance/runtime identity separation, which exists precisely so governance IDs remain re-assignable/human-facing while runtime IDs stay the stable, collision-resistant key. | Selected `runtime_id` as primary key everywhere; `governance_id` remains a separately unique, not-null column, not the key. | Resolved |
| M022-DESIGN-ISSUE-0003 | MAJOR | 11 | Considered silently dropping `identity_reference` columns on transition tables since they are always redundant with the parent in every live aggregate today. | Would encode an assumption (identity_reference always equals parent identity) that no frozen document actually guarantees as an invariant. | Kept the columns, documented the redundancy explicitly rather than silently optimizing it away. | Resolved |
| M022-DESIGN-ISSUE-0004 | MINOR | 8, 9 | Needed to distinguish which owned collections have their own frozen sequence field (transitions, findings) versus which do not (manifests, criterion results, artifact references) before assigning primary keys. | Getting this wrong would either lose ordering information or introduce an unnecessary surrogate key where a natural one already exists. | Verified directly against each frozen dataclass definition (Section 8-10); used the natural field where one exists, an explicit `position` column where none does. | Resolved |
| M022-DESIGN-ISSUE-0005 | MINOR | 5, 12 | Considered fully normalizing `notes`/`evidence_references` into child tables for consistency with every other collection. | Would add three more child tables for data with no further structure than a flat string list, disproportionate to the benefit. | Selected `TEXT[]` for these specific fields only, explicitly bounded and disclosed rather than applied as a general pattern. | Resolved |
| M022-DESIGN-ISSUE-0006 | MINOR | 13 | Considered one migration revision per aggregate for smaller review diffs. | Would create real intermediate database states (e.g. `run` FK-referencing a not-yet-existing `campaign`) that never correspond to a reviewed milestone state. | Selected one revision for all four aggregates together, matching the "all four aggregates together" discipline already used for every prior contract milestone. | Resolved |

All CRITICAL and MAJOR issues recorded in this self-review have proposed resolutions. Independent verification remains pending.

## 23. Implementation Acceptance Gate (for a future Implementation milestone, not satisfied by this design)

A future MILESTONE-022 implementation must demonstrate, before it may be considered for freeze:

- the single Alembic revision (Section 13) applies and rolls back cleanly against a disposable PostgreSQL database;
- every table/column/constraint in Sections 7-10 exists exactly as specified, with no invented column;
- the partial-unique `manifest_id` index and the `criterion_id`/`artifact_reference` uniqueness constraints are exercised by tests and behave as specified;
- no business-rule (non-structural) constraint was added beyond what this design specifies;
- no frozen M019, M020, or M021 file is modified.

## 24. Final Decision

MILESTONE-022 selects a one-table-per-aggregate-root-plus-child-tables-per-owned-collection relational design for Campaign, Run, EvidencePackage, and Review, keyed by `runtime_id` with a separately unique `governance_id`, with structural-only constraints and a single, all-four-aggregates-together migration revision strategy.

This document does not mark MILESTONE-022 approved, frozen, or implemented. It requires independent review, then (if approved) a separate implementation milestone following the same design-then-implementation-then-freeze discipline used for MILESTONE-019, MILESTONE-020, and MILESTONE-021.

Final status:

```text
DESIGN READY FOR INDEPENDENT REVIEW

NOT APPROVED
NOT FROZEN
```
