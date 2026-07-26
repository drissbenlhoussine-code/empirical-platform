# MILESTONE-022 - PostgreSQL Schema and Migration Design Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-022 |
| Title | PostgreSQL Schema and Migration Design Scope Selection |
| Version | 1.0 |
| Status | SCOPE SELECTED - PENDING INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `fdb180a2b21776cf37fe36826741a54ef7b43ad4` |
| Baseline status | MILESTONE-021 APPROVED AND FROZEN |
| Mission type | Scope selection only |
| Implementation performed | No |
| Source modified | No |
| Schemas, migrations, repositories, Unit of Work, application services created | No |

## 2. Frozen Baseline

MILESTONE-021 freezes the persistence mapper contract for Campaign, Run, EvidencePackage, and Review. The repository now contains, verified live:

- frozen aggregate/reconstruction behavior (M013-M019);
- frozen `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` Protocols and their `LoadedAggregate`/`SaveOperation`/`SaveResult`/`RepositoryContractError` support types (M020);
- frozen `CampaignMapper`, `RunMapper`, `EvidencePackageMapper`, `ReviewMapper` Protocols and their `<Aggregate>DurableRecord` types, field-complete for every aggregate, including nested `DatasetManifestDurableRecord`, `CriterionResultDurableRecord`, `ReviewFindingDurableRecord`, and shared `IdentityDurableRecord`/`TransitionDurableRecord` (M021);
- `empirical_platform.shared.persistence.postgres` verified to use SQLAlchemy **Engine/Core** connectivity only — no ORM declarative models, no `Table`/`MetaData` objects, no domain schema;
- `migrations/versions/` verified empty (0 files); `migrations/env.py` verified to declare `target_metadata = None`, with `migrations/README.md` explicitly stating no business tables are defined;
- `alembic.ini` verified to contain only tool bootstrap configuration — no schema, naming convention, or table-related settings.

The next milestone may therefore select a schema/migration design boundary, but must not implement repositories, mappers, migrations, or runtime composition.

## 3. Current Persistence-Readiness Inventory

| Aggregate | Durable record (M021, frozen) | Nested durable records | Schema exists | Migration exists |
| --- | --- | --- | --- | --- |
| Campaign | `CampaignDurableRecord` | `TransitionDurableRecord` (shared) | No | No |
| Run | `RunDurableRecord` | `DatasetManifestDurableRecord`, `TransitionDurableRecord` | No | No |
| EvidencePackage | `EvidencePackageDurableRecord` | `CriterionResultDurableRecord`, `TransitionDurableRecord` | No | No |
| Review | `ReviewDurableRecord` | `ReviewFindingDurableRecord`, `TransitionDurableRecord` | No | No |

Supporting inventory:

| Area | Repository evidence | Readiness |
| --- | --- | --- |
| Durable-record field inventory | Complete, frozen, field-level (M021 Design Sections 9-10) | Ready to inform table/column design directly |
| PostgreSQL connectivity | Engine/Core only; `PersistenceService`/`PersistenceUnitOfWork` bounded raw-SQL execution exists | Connectivity-ready, no schema |
| Migration tooling | Alembic bootstrapped (M004/M008); zero revisions | Tooling-ready, no schema to migrate toward |
| Architecture permissions | Domain/mapper packages may not import SQLAlchemy/persistence; unchanged through M021 | Correct for domain purity; schema work does not touch domain packages at all |

## 4. Remaining Uncertainty

Both MILESTONE-020 (Candidate F, "premature schema lock-in") and MILESTONE-021 (Candidate B, "schema shape depends on mapping decisions not yet made") explicitly rejected schema design as premature, each citing the same blocker: the durable/mapping shape was not yet known. That blocker is now resolved — MILESTONE-021 froze exactly that shape, field by field, for all four aggregates.

Unresolved questions that block implementation:

- one table per aggregate root versus splitting owned collections (transition history, manifests, criterion results, artifact references, findings) into separate child tables versus a single denormalized table with JSON columns;
- primary key strategy: governance ID, runtime ID (UUID), a surrogate key, or a composite key;
- how `AggregateVersion`/`TransitionSequence` (plain integers in the durable record) become column types and whether they participate in uniqueness/optimistic-concurrency constraints at the schema level;
- how ordered collections (manifests, criterion results, findings) preserve order in a relational table without relying on physical insertion order;
- whether SQLAlchemy Core `Table`/`MetaData` objects or raw DDL strings are used to express the schema, consistent with the existing Engine/Core-only adapter;
- migration revision strategy: one revision establishing all tables, or one revision per aggregate;
- how NULL-able durable-record fields (e.g. `manifest_id`, `summary`, `rationale`, `disposition`) map to nullable columns without weakening the frozen domain invariants that already forbid certain combinations (e.g. M019's terminal-metadata rules) — the schema must not attempt to re-enforce domain validation at the database level in a way that could diverge from the frozen reconstruction rules.

## 5. Candidate Milestones

| Candidate | Purpose | Disposition |
| --- | --- | --- |
| A. PostgreSQL Schema and Migration Design | Define table/column/key/index shape and migration revision strategy for all four aggregates' durable records, without writing SQL or migration files. | Selected. |
| B. Concrete Mapper Implementation | Write real field-transformation code implementing the M021 Protocols, replacing the test-only fakes. | Rejected as a second-priority, non-schema-dependent track — see Section 7; not selected as *this* milestone because schema design is the more architecturally load-bearing, harder-to-reverse decision and both M020 and M021 named it as the next blocked item once mapping was known. |
| C. Concrete PostgreSQL Repository Adapters | Implement `CampaignRepository` etc. against PostgreSQL. | Rejected: cannot implement honestly without a schema to query against; two milestones premature. |
| D. Persistence Unit of Work (multi-statement/multi-aggregate) | Define transaction ownership beyond the existing single-statement primitive. | Rejected: M020 Design Sections 18/26 and M021 Design Section 15 both explicitly defer this; no new evidence changes that. |
| E. Repository Runtime Composition | Wire concrete repositories into a runtime/DI container. | Rejected: no concrete repository exists yet to compose. |
| F. Application Services | Use-case-facing orchestration calling repositories. | Rejected: no concrete repository exists yet to call. |
| G. Repository Implementation Hardening Follow-Up | Add more M021 contract tests/hardening. | Rejected: M021 hostile review and independent Codex approval found no outstanding blocker. |
| H. No Implementation-Ready Next Scope | Stop because no prerequisite is ready. | Rejected: schema design is ready and bounded now that M021 is frozen. |

## 6. Candidate Comparison

| Candidate | Architectural risk | Implementation risk | Unsupported-assumption risk | Reversibility risk | Scope-creep risk | Independent reviewability | Future milestones unlocked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | LOW | LOW | MEDIUM | HIGH if done carelessly, LOW if scoped as design-only | MEDIUM | HIGH | Migration authoring, concrete mapper/repository implementation |
| B | LOW | LOW | LOW | LOW | LOW | HIGH | Concrete repositories, but only after schema exists to persist against |
| C | HIGH | HIGH | HIGH | HIGH | HIGH | LOW | Fragile pilot only |
| D | MEDIUM | LOW | HIGH | LOW | HIGH | MEDIUM | Later orchestration, prematurely |
| E | MEDIUM | MEDIUM | HIGH | LOW | HIGH | MEDIUM | Nothing yet buildable |
| F | MEDIUM | MEDIUM | HIGH | LOW | HIGH | MEDIUM | Nothing yet buildable |
| G | LOW | LOW | LOW | LOW | LOW | HIGH | None material |
| H | LOW | LOW | LOW | LOW | LOW | HIGH | None |

Candidate A carries the highest *reversibility* risk of any candidate on this table precisely because schema decisions are unusually hard to reverse once migrations exist in a shared environment — which is exactly why this milestone is scoped as **design only**: no migration file, no DDL execution, nothing to reverse yet. The design's job is to make that eventual, harder-to-reverse step as well-evidenced as possible before it happens.

## 7. Rejected Candidates

Candidate B (concrete mapper implementation) is a legitimate, ready, non-schema-dependent next step, but it is not selected as *this* milestone: it does not need architectural review at the same level of scrutiny (the contract is already frozen; implementing it is comparatively mechanical field-mapping work), and the mission explicitly directs a single narrow scope. It remains available as a future milestone and does not block or get blocked by Candidate A.

Candidate C is implementation before schema exists; nothing to query against.

Candidate D was already evaluated and re-rejected twice (M020, M021); nothing new justifies revisiting it.

Candidates E and F require a concrete repository, which requires a schema, which does not yet exist; three and four milestones premature respectively.

Candidate G is unnecessary: M021 froze cleanly with independent-review approval and no outstanding finding.

Candidate H is not supported: schema design is reviewable now using live, frozen M021 evidence.

## 8. Selected Milestone

Selected milestone:

```text
MILESTONE-022 - PostgreSQL Schema and Migration Design
```

The milestone is a design milestone. It must define, for Campaign, Run, EvidencePackage, and Review together, the exact relational table/column/key/index shape their frozen durable records map onto, and the migration revision strategy — without writing SQL, without creating migration files, without implementing repositories, mappers, or Unit of Work.

## 9. Milestone Type

MILESTONE-022 is:

```text
SCHEMA DESIGN ONLY
```

It is not implementation, migration authoring, repository coding, or persistence testing.

## 10. Exact Scope Boundary

In scope:

- table-per-aggregate versus normalized child-table versus denormalized/JSON-column comparison, for the root and every owned collection;
- primary key, foreign key, and uniqueness constraint strategy, grounded in the frozen M020 identity-uniqueness rules (per-aggregate-kind uniqueness of `governance_id`, `runtime_id`, and their pairing);
- column type mapping for every durable-record field (string, integer, datetime, optional, tuple/ordered-collection);
- ordering strategy for ordered collections (manifests, criterion results, findings, transition history) at the relational level;
- SQLAlchemy Core `Table`/`MetaData` versus raw DDL comparison, consistent with the existing Engine/Core-only adapter;
- migration revision strategy (single versus per-aggregate) and Alembic conventions;
- explicit boundary against re-implementing domain/reconstruction validation at the schema level;
- architecture-checker implications, if any;
- test expectations for a schema-design-only milestone.

Out of scope:

- writing SQL or DDL;
- creating Alembic migration revision files;
- implementing mappers, repositories, or Unit of Work;
- runtime composition, APIs, workers;
- Audit, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior.

## 11. Aggregate Coverage

All four aggregates: Campaign, Run, EvidencePackage, Review — for the same reason M020 and M021 required it: a schema design consistent for only some aggregates would invite incompatible future migrations.

## 12. Required Deliverables (of the Design, not of this scope selection)

- exact table shape (or documented equivalent) for all four aggregates and their owned collections;
- exact key and constraint strategy;
- exact column-type mapping for every durable-record field;
- exact migration revision strategy;
- explicit non-goals preventing SQL/migration/implementation lock-in;
- hostile self-review before independent review.

## 13. Test Obligations (to be defined by the Design, executed only in a future Implementation milestone)

The Design must specify future test categories only: migration apply/rollback correctness, constraint enforcement matching frozen domain uniqueness rules, and column-type round-trip fidelity against the M021 durable records.

## 14. Architecture Constraints

The Design must preserve `tools/check_architecture.py`'s existing tables as authoritative; schema design touches no `src/empirical_platform` package boundary at all (it is pure `migrations/`-facing design), so no architecture-checker change is anticipated.

## 15. Security Constraints

The Design must not introduce credential handling or connection-string construction; those remain the existing `PersistenceService` infrastructure's concern. The Design must consider whether any durable-record field (e.g. `actor`, `reason`, free-text notes) requires column-level handling different from structured fields, without introducing new secret-handling machinery.

## 16. Stop Conditions

Stop MILESTONE-022 design if:

- schema design would require changing a frozen M019 reconstruction rule, M020 repository contract, or M021 mapper/durable-record shape;
- a durable-record field cannot be mapped to a relational column without inventing a field the frozen durable record does not have;
- migration authoring becomes necessary to answer a design question.

## 17. Acceptance Gate

MILESTONE-022 scope is acceptable only if:

- all four aggregates are covered;
- table/column/key/index questions are enumerated for the root and every owned collection;
- migration revision strategy is included;
- SQL, migration files, implementation, and runtime work remain deferred;
- validation passes;
- only this scope-selection document is changed.

## 18. Hostile Self-Review

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M022-SCOPE-ISSUE-0001 | MAJOR | 4, 10 | Initial framing risked scope creep into re-validating domain invariants (e.g. terminal-metadata rules) at the schema/constraint level. | M019 already froze these rules at the reconstruction layer; duplicating them as CHECK constraints risks divergence if one layer is updated without the other. | Could create two sources of truth for the same business rule. | Added an explicit non-goal (Section 10) against re-implementing domain/reconstruction validation at the schema level; schema constraints are limited to structural integrity (keys, types, NOT NULL where a field is always present), not business-rule enforcement. | Resolved |
| M022-SCOPE-ISSUE-0002 | MAJOR | 6 | Schema design is unusually hard to reverse once applied in a shared environment; initial framing did not make this explicit. | Unlike M020/M021's pure-Python contract designs, a migration once run against a shared database is costly to reverse. | Could understate the stakes of getting this design wrong before implementation. | Added explicit reversibility-risk framing in Section 6 and confirmed the scope stays design-only (no DDL, no migration file) specifically because of this. | Resolved |
| M022-SCOPE-ISSUE-0003 | MINOR | 5 | Considered bundling concrete mapper implementation into this same milestone since it is also "ready." | Bundling multiple ready-but-independent concerns risks an uncontrolled milestone, which the mission explicitly warns against. | Would blur schema-design review against unrelated mapper-implementation review. | Kept concrete mapper implementation as Candidate B, explicitly not selected, available as an independent future milestone. | Resolved |
| M022-SCOPE-ISSUE-0004 | MINOR | 2 | `alembic.ini` and `migrations/README.md` needed direct verification rather than assumed-empty carry-forward. | Read live: confirmed no schema/naming-convention settings, confirmed explicit "no business tables" statement. | Low; would have been a citation-accuracy gap only. | Verified directly and cited with file evidence in Section 2. | Resolved |

No unresolved scope-selection finding remains.

## 19. Final Decision

Selected next milestone:

```text
MILESTONE-022 - PostgreSQL Schema and Migration Design
```

Final status:

```text
SCOPE SELECTED - PENDING INDEPENDENT REVIEW
```
