# MILESTONE-023 - PostgreSQL Repository Adapter Design Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-023 |
| Title | PostgreSQL Repository Adapter Design Scope Selection |
| Version | 1.0 |
| Status | SCOPE SELECTED - PENDING INDEPENDENT REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen baseline | `10425e85b63a0b6f18b73b962355f22176cb279c` |
| Baseline status | MILESTONE-022 APPROVED AND FROZEN |
| Mission type | Scope selection only |
| Implementation performed | No |
| Source modified | No |
| Repositories, Unit of Work, application services created | No |

## 2. Frozen Baseline

MILESTONE-022 freezes a twelve-table PostgreSQL schema and its single Alembic migration revision (`5b58cdd7751b`), proven against real PostgreSQL. The repository now contains, verified live:

- frozen aggregate/reconstruction behavior (M013-M019);
- frozen `CampaignRepository`, `RunRepository`, `EvidencePackageRepository`, `ReviewRepository` Protocols — exactly `get`/`add`/`save` — and their `LoadedAggregate`/`SaveOperation`/`SaveResult`/`RepositoryContractError` support types (M020), verified live in `src/empirical_platform/shared/contracts/repository.py` and `src/empirical_platform/campaign/repository.py` (and the analogous `run`/`evidence`/`review` modules);
- frozen `CampaignMapper`, `RunMapper`, `EvidencePackageMapper`, `ReviewMapper` Protocols — exactly `to_durable_record`/`from_durable_record` — and their `<Aggregate>DurableRecord` types, field-complete for every aggregate (M021), verified live in `src/empirical_platform/campaign/mapper.py` (and the analogous three modules). `CampaignMapper.from_durable_record`'s own docstring states: "Does not call the internal `_reconstruct_campaign` factory; that call remains a **future repository implementation's responsibility**" — a direct, frozen textual pointer to this milestone's subject;
- a complete, frozen, twelve-table PostgreSQL schema (M022) with every constraint the durable records' invariants require structurally: root `governance_id`/`runtime_id` uniqueness, owned-collection composite primary keys (`position` or `sequence`), the `run_manifest` partial-unique index, and every numeric/enum-membership `CHECK`;
- `empirical_platform.shared.persistence.postgres.PostgresUnitOfWork` — verified live — provides exactly `execute(statement, parameters) -> Sequence[Mapping[str, object]]`, `commit()`, `rollback()`, single-connection, single-transaction, no nested units of work, no multi-statement orchestration beyond what one `with ... unit_of_work() as work:` block naturally provides;
- `migrations/versions/` contains exactly the one M022 revision; no concrete mapper, no concrete repository, no Unit of Work beyond the primitive above, and no application-layer code exists anywhere in the repository.

MILESTONE-022's own Scope Selection document (Section 7) already named the two next-available, non-blocking-of-each-other candidates once schema existed: concrete mapper implementation ("legitimate, ready... comparatively mechanical field-mapping work") and everything that depends on a concrete repository. MILESTONE-022's Design document (Section 14) states the frozen call chain this repository design must make concrete: `repository implementation -> mapper -> ReconstructionState -> _reconstruct_* -> aggregate`.

## 3. Current Persistence-Readiness Inventory

| Aggregate | Repository Protocol (M020, frozen) | Mapper Protocol (M021, frozen) | Schema (M022, frozen) | Concrete mapper | Concrete repository |
| --- | --- | --- | --- | --- | --- |
| Campaign | `CampaignRepository` | `CampaignMapper` | `campaign`, `campaign_transition` | No | No |
| Run | `RunRepository` | `RunMapper` | `run`, `run_manifest`, `run_transition` | No | No |
| EvidencePackage | `EvidencePackageRepository` | `EvidencePackageMapper` | `evidence_package`, `evidence_package_criterion_result`, `evidence_package_artifact_reference`, `evidence_package_transition` | No | No |
| Review | `ReviewRepository` | `ReviewMapper` | `review`, `review_finding`, `review_transition` | No | No |

Supporting inventory:

| Area | Repository evidence | Readiness |
| --- | --- | --- |
| Schema/constraint shape | Complete, frozen, empirically proven against real PostgreSQL (M022) | Ready to inform a concrete repository's SQL directly |
| Transaction primitive | `PostgresUnitOfWork` exists, single-statement-per-call, single-transaction-per-`with`-block | Sufficient for one repository operation (`get`/`add`/`save`) as a single transaction; insufficient for cross-aggregate or cross-call transactions (out of scope, unchanged from M020/M021's own deferral) |
| Error taxonomy | `RepositoryContractError` hierarchy frozen (M020): `AggregateNotFound`, `AggregateAlreadyExists`, `OptimisticConcurrencyConflict`, `InvalidAggregateForPersistence`, `InvalidPersistedAggregateState` | Ready to receive a concrete PostgreSQL-to-taxonomy translation design |
| Architecture permissions | `campaign`/`run`/`evidence`/`review` top-level packages are forbidden from importing `sqlalchemy`/`empirical_platform.shared.persistence` (`tools/check_architecture.py`, unchanged through M022) | A concrete repository inherently needs both; **where such a module may live without violating or silently weakening this rule is an open, unresolved question this design must answer** |

## 4. Remaining Uncertainty

MILESTONE-020 (Design Sections 18/26) and MILESTONE-021 (Design Section 15) both explicitly deferred multi-statement Unit of Work design as premature without a schema. MILESTONE-022's own Scope Selection (Candidate C) rejected a concrete repository adapter as "two milestones premature" while no schema existed. That blocker is now resolved — MILESTONE-022 froze the exact schema, table by table, constraint by constraint, empirically proven against real PostgreSQL.

Unresolved questions that block a correct, honest concrete repository implementation:

- exactly how a `<Aggregate>DurableRecord`'s fields (frozen, in-memory, persistence-neutral) become SQL parameters for the M022 schema's `INSERT`/`UPDATE`/`SELECT` statements, and the reverse for `get()` — this translation is not defined by either M021 (which stops at the durable record) or M022 (which stops at the schema);
- how `save(aggregate, expected_persisted_version=...)`'s optimistic-concurrency guarantee is enforced at the SQL level (a guarded `UPDATE ... WHERE version = :expected` and rowcount check, versus a `SELECT`-then-compare-then-`UPDATE` pattern) and how `OptimisticConcurrencyConflict`'s `actual_persisted_version` field gets populated when the guard fails;
- how an aggregate's owned collections (transition history, manifests, criterion results, artifact references, findings) get written to their child tables on `add()`/`save()` — full delete-and-reinsert of every owned row versus an incremental diff, and why;
- how `get()` reads the root row plus every owned child table's rows, in the correct deterministic order (using each child table's `position`/`sequence` column), assembles a `<Aggregate>DurableRecord`, and hands it to `Mapper.from_durable_record()` — completing, but not altering, the frozen `repository -> mapper -> ReconstructionState -> _reconstruct_*` call chain;
- which of `governance_id` or `runtime_id` is the primary access-path key for `get`/`save` operations, given M020 guarantees both are unique but the schema uses different columns as the FK target for different cross-aggregate references (Design Section 6: cross-aggregate context references use `governance_id`, but every table's own primary key is `runtime_id`);
- exact PostgreSQL/SQLAlchemy exception-to-`RepositoryContractError`-category translation rules (which real exception classes/conditions map to `AggregateNotFound` versus `AggregateAlreadyExists` versus `OptimisticConcurrencyConflict` versus `InvalidPersistedAggregateState`);
- where a concrete repository module may live given `tools/check_architecture.py`'s existing `campaign`/`run`/`evidence`/`review` forbidden-import rules, and whether that rule needs a narrow, explicit, disclosed adjustment or whether the concrete repository belongs in a different package entirely (e.g. under `shared.persistence`) that already permits `sqlalchemy`/persistence imports.

## 5. Candidate Milestones

| Candidate | Purpose | Disposition |
| --- | --- | --- |
| A. Concrete Mapper Implementation | Write real field-transformation code implementing the M021 Protocols, replacing the test-only fakes. | Rejected as *this* milestone: legitimate and ready, but comparatively mechanical (the Protocol and both endpoint shapes are already fully frozen field-by-field); does not raise the substantive, load-bearing design questions Section 4 lists. Remains available as an independent future milestone; does not block or get blocked by Candidate B. |
| B. Concrete PostgreSQL Repository Adapter Design | Define, without writing implementation code, exactly how a concrete repository satisfies the M020 Protocols against the M022 schema using the M021 mapper contracts: DurableRecord-to-SQL translation, transaction boundary, optimistic-concurrency enforcement, child-collection write/read strategy, error taxonomy translation, and module placement consistent with (or deliberately, narrowly adjusting) the architecture checker. | Selected. |
| C. Concrete PostgreSQL Repository Implementation | Write the actual repository code. | Rejected: implementing before the design questions in Section 4 are resolved and independently reviewed would repeat M020/M021/M022's own established discipline violation risk — coding ahead of a reviewed design. |
| D. Persistence Unit of Work (multi-statement/multi-aggregate) | Define transaction ownership beyond the existing single-statement/single-transaction primitive. | Rejected: M020 Design Sections 18/26 and M021 Design Section 15 both explicitly defer this; no new evidence changes that. A single repository operation (`get`/`add`/`save`) fits inside the existing primitive's one-transaction-per-`with`-block shape; this design will state that explicitly rather than inventing new orchestration. |
| E. Repository Runtime Composition | Wire concrete repositories into a runtime/DI container. | Rejected: no concrete repository exists yet to compose. |
| F. Application Services | Use-case-facing orchestration calling repositories. | Rejected: no concrete repository exists yet to call. |
| G. M022 Schema Hardening Follow-Up | Add more schema/constraint tests or documentation. | Rejected: M022's independent re-review found no outstanding blocker after correction; nothing new justifies revisiting it. |
| H. No Implementation-Ready Next Scope | Stop because no prerequisite is ready. | Rejected: the repository adapter design is ready and bounded now that M022 is frozen. |

## 6. Candidate Comparison

| Candidate | Architectural risk | Implementation risk | Unsupported-assumption risk | Reversibility risk | Scope-creep risk | Independent reviewability | Future milestones unlocked |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | LOW | LOW | LOW | LOW | LOW | HIGH | Concrete repositories, once a design exists to implement against |
| B | MEDIUM | LOW | MEDIUM | LOW (design-only; no code, no schema change) | MEDIUM | HIGH | Concrete mapper + repository implementation, repository runtime composition |
| C | HIGH | HIGH | HIGH | MEDIUM | HIGH | LOW | Fragile pilot only |
| D | MEDIUM | LOW | HIGH | LOW | HIGH | MEDIUM | Later orchestration, prematurely |
| E | MEDIUM | MEDIUM | HIGH | LOW | HIGH | MEDIUM | Nothing yet buildable |
| F | MEDIUM | MEDIUM | HIGH | LOW | HIGH | MEDIUM | Nothing yet buildable |
| G | LOW | LOW | LOW | LOW | LOW | HIGH | None material |
| H | LOW | LOW | LOW | LOW | LOW | HIGH | None |

Candidate B carries a real *architectural* risk (unlike M022's schema design, which was pure structural translation, this design must resolve genuine behavioral questions: concurrency enforcement, error translation, module placement against the architecture checker) but essentially no reversibility risk, because nothing is implemented or migrated yet — the design can be corrected freely before any code exists. This is exactly the profile that warrants a dedicated, independently-reviewed design milestone rather than folding these decisions into an implementation milestone's ad hoc choices.

## 7. Rejected Candidates

Candidate A (concrete mapper implementation) is legitimate, ready, and independent of Candidate B, but it is not selected as *this* milestone: it does not raise substantive design questions requiring independent architectural scrutiny (the Protocol and both endpoint shapes — aggregate and durable record — are already fully frozen field-by-field by M021; a concrete implementation is comparatively mechanical), and the mission explicitly directs a single narrow scope. It remains available as a future milestone and does not block or get blocked by Candidate B.

Candidate C is implementation before a reviewed design exists to implement against; repeats the coding-ahead-of-design risk this project's discipline exists to prevent.

Candidate D was already evaluated and re-rejected twice (M020, M021); nothing new justifies revisiting it, and Candidate B's design will explicitly confirm the existing single-statement primitive suffices for one repository operation rather than silently assuming so.

Candidates E and F require a concrete repository, which requires a reviewed design (Candidate B) and then an implementation (Candidate C); two and three milestones premature respectively.

Candidate G is unnecessary: M022's independent re-review returned "APPROVED FOR OWNER FREEZE" with no outstanding finding.

Candidate H is not supported: the repository adapter design is reviewable now using live, frozen M020/M021/M022 evidence.

## 8. Selected Milestone

Selected milestone:

```text
MILESTONE-023 - PostgreSQL Repository Adapter Design
```

The milestone is a design milestone. It must define, for Campaign, Run, EvidencePackage, and Review together, exactly how a concrete repository implementation would satisfy the frozen M020 Repository Protocols against the frozen M022 schema using the frozen M021 Mapper Protocols — without writing repository code, without writing mapper code, without creating a new migration, without inventing multi-statement Unit of Work.

## 9. Milestone Type

MILESTONE-023 is:

```text
REPOSITORY ADAPTER DESIGN ONLY
```

It is not implementation, mapper coding, migration authoring, or runtime composition.

## 10. Exact Scope Boundary

In scope:

- the exact call sequence a concrete `get()`/`add()`/`save()` implementation follows, expressed precisely enough that two independent implementers would produce interoperable code;
- DurableRecord-to-SQL-parameter translation for every field of every aggregate's durable record and every nested durable record, against the exact M022 column names and types;
- the reverse translation: SQL row set (root + every owned child table, correctly ordered) to a `<Aggregate>DurableRecord`;
- optimistic-concurrency enforcement strategy for `save()`, including exactly how `OptimisticConcurrencyConflict`'s `actual_persisted_version` is populated when the guard fails;
- `add()`'s atomicity and duplicate-detection strategy (root plus every owned child row, one transaction, `AggregateAlreadyExists` on collision);
- owned-collection write strategy (full replace versus incremental diff) with an explicit, justified choice;
- owned-collection read/ordering strategy, reusing each child table's `position`/`sequence` column;
- confirmation (not redesign) that the existing single-statement `PostgresUnitOfWork` primitive is sufficient for one repository operation as a single transaction;
- exact PostgreSQL/SQLAlchemy-exception-to-`RepositoryContractError`-category translation table;
- module placement for a future concrete repository relative to `tools/check_architecture.py`'s existing rules — either a placement that already satisfies them, or a narrow, explicit, disclosed rule adjustment;
- identity-handling strategy: which column anchors `get`/`save`'s primary lookup, consistent with M020's uniqueness guarantees and M022's FK-direction choices;
- test strategy for a future implementation milestone;
- architecture and security constraints;
- explicit non-goals preventing implementation/migration/Unit-of-Work lock-in.

Out of scope:

- writing repository implementation code;
- writing concrete mapper implementation code (Candidate A, independent, deferred);
- creating a new Alembic migration revision or altering the frozen M022 schema;
- multi-statement or multi-aggregate Unit of Work (Candidate D, still deferred);
- runtime composition, dependency injection wiring, APIs, workers;
- application services;
- Audit, Decision Candidate, Decision Freeze, trading, vendor, or empirical execution behavior.

## 11. Aggregate Coverage

All four aggregates: Campaign, Run, EvidencePackage, Review — for the same reason M020, M021, and M022 required it: a repository adapter design consistent for only some aggregates would invite an incompatible future implementation milestone, and three of the four aggregates share the same transition-history shape, so a partial design would waste the opportunity to specify one reusable pattern.

## 12. Required Deliverables (of the Design, not of this scope selection)

- exact `get`/`add`/`save` call-sequence specification, per aggregate;
- exact DurableRecord-field-to-SQL-column translation table, per aggregate and nested record;
- exact optimistic-concurrency and error-translation rules;
- exact owned-collection write/read strategy with rationale;
- exact module-placement decision relative to the architecture checker;
- explicit non-goals preventing implementation/migration/Unit-of-Work lock-in;
- hostile self-review before independent review.

## 13. Test Obligations (to be defined by the Design, executed only in a future Implementation milestone)

The Design must specify future test categories only: real-PostgreSQL round-trip fidelity per aggregate (add, get, save, re-get), optimistic-concurrency conflict reproduction, duplicate-`add()` rejection, not-found `get()`/`save()` behavior, owned-collection ordering preserved end-to-end through the full mapper-and-schema round trip, and atomicity of a multi-table write under a simulated mid-write failure.

## 14. Architecture Constraints

The Design must treat `tools/check_architecture.py`'s existing `ALLOWED`/`FORBIDDEN_IMPORT_PREFIXES` tables as authoritative and must explicitly resolve — not silently assume — where a concrete repository module can live without violating them, since `campaign`/`run`/`evidence`/`review` are currently forbidden from importing `sqlalchemy` or `empirical_platform.shared.persistence`. Any proposed adjustment to those tables must be narrow, explicit, and justified in the Design; the Design must not propose broadening those permissions beyond what a concrete repository module strictly requires.

## 15. Security Constraints

The Design must not introduce new credential handling or connection-string construction; those remain the existing `PersistenceService`/`resolve_foundation_config()` infrastructure's concern, unchanged since M008. The Design must consider whether any DurableRecord field requires parameterized-query handling different from structured fields (e.g. free-text `actor`, `reason`, `scope_statement` values) to avoid SQL injection, without introducing new secret-handling machinery.

## 16. Stop Conditions

Stop MILESTONE-023 design if:

- the design would require changing a frozen M019 reconstruction rule, M020 repository contract, M021 mapper/durable-record shape, or M022 schema/constraint;
- a DurableRecord field cannot be translated to an M022 column (or vice versa) without inventing a field or column neither frozen artifact has;
- answering a design question requires writing and running implementation code first.

## 17. Acceptance Gate

MILESTONE-023 scope is acceptable only if:

- all four aggregates are covered;
- the call-sequence, translation, concurrency, error-taxonomy, and module-placement questions in Section 4 are all enumerated for resolution by the Design;
- repository code, mapper code, migrations, Unit of Work, and runtime work remain deferred;
- validation passes;
- only this scope-selection document (and, in the same mission, the Design document) is changed.

## 18. Hostile Self-Review

| ID | Severity | Section | Finding | Evidence | Impact | Correction | Disposition |
| --- | --- | --- | --- | --- | --- | --- | --- |
| M023-SCOPE-ISSUE-0001 | MAJOR | 4, 14 | Initial framing treated architecture-checker module placement as an implementation detail rather than a design decision. | The checker's `FORBIDDEN_IMPORT_PREFIXES` table currently forbids exactly the imports a concrete repository needs; this is not resolvable by an implementer without a decision already reviewed at design time, unlike M022 (which touched no `src/` package at all). | Deferring this to implementation would repeat M020's disclosed "convention-enforced, not tool-enforced" gap in a new, avoidable way. | Elevated module placement to an explicit, in-scope Section 4/10/14 design question with its own required deliverable (Section 12), rather than an implementation afterthought. | Resolved |
| M023-SCOPE-ISSUE-0002 | MAJOR | 6 | Considered treating this milestone as low-risk across every dimension by analogy to M020/M021 (pure-contract designs). | Unlike M020/M021, this design must resolve genuine behavioral questions (concurrency, error translation) that a careless answer could get wrong even though nothing is "locked in" by a design document alone. | Understating architectural risk could lead to a thinner-than-warranted design document. | Added explicit MEDIUM architectural-risk framing in Section 6, distinguishing it from M022's schema-design risk profile (which was dominated by reversibility, not architectural difficulty). | Resolved |
| M023-SCOPE-ISSUE-0003 | MINOR | 5 | Considered bundling concrete mapper implementation (Candidate A) into this same milestone since both are "ready" once M022 froze. | Bundling multiple ready-but-independent concerns risks an uncontrolled milestone, which the mission explicitly warns against, and repeats M022-SCOPE-ISSUE-0003's exact resolved pattern. | Would blur repository-adapter-design review against unrelated mapper-implementation review. | Kept concrete mapper implementation as Candidate A, explicitly not selected, available as an independent future milestone. | Resolved |
| M023-SCOPE-ISSUE-0004 | MINOR | 2 | `PostgresUnitOfWork`'s exact method surface needed direct verification rather than assumed carry-forward from memory of earlier milestones. | Read live: confirmed `execute`/`commit`/`rollback`/single-transaction shape in `src/empirical_platform/shared/persistence/postgres.py`. | Low; would have been a citation-accuracy gap only. | Verified directly and cited with file evidence in Section 2. | Resolved |

No unresolved scope-selection finding remains.

## 19. Final Decision

Selected next milestone:

```text
MILESTONE-023 - PostgreSQL Repository Adapter Design
```

Final status:

```text
SCOPE SELECTED - PENDING INDEPENDENT REVIEW
```
