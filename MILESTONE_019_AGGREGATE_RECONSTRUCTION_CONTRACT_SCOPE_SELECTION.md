# MILESTONE-019 - Aggregate Reconstruction Contract Scope Selection

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-019 |
| Title | Aggregate Reconstruction Contract Scope Selection |
| Version | 1.0 |
| Status | SCOPE CANDIDATE SELECTED |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Baseline | `da3153fc3a0d5a277958d62a53711cfd76495d4b` |
| Baseline meaning | MILESTONE-018 hostile-review hardening commit |
| Mission type | Scope selection only |
| Implementation performed | No |
| Source modified | No |
| Schemas or migrations created | No |
| Repository contracts created | No |

## 2. Frozen Baseline

The repository baseline for this scope-selection mission is:

```text
da3153fc3a0d5a277958d62a53711cfd76495d4b
```

This baseline contains frozen process-local behavior for the first four runtime aggregates:

- Campaign;
- Run;
- Evidence Package;
- Review.

The baseline also contains foundation persistence and object-storage connectivity, but no domain repositories, domain schemas, migrations, aggregate mappers, reconstruction APIs, application services, orchestration, job ledger, outbox, Audit runtime, Decision Candidate runtime, Decision Freeze, vendor behavior, market-data behavior, trading behavior, or empirical campaign execution behavior.

## 3. Completed Domain Inventory

| Concept | Implemented | Frozen | Process-local | Cross-aggregate behavior | Persistence-ready | Remaining work |
| --- | --- | --- | --- | --- | --- | --- |
| `Campaign` | Yes | Yes, M018 | Yes | No Run import, no Run status, no authorization execution | No | reconstruction, repository contract, schema, application-service coordination |
| `Run` | Yes | Yes, M017 | Yes | Stores immutable `CampaignId` context only | No | reconstruction, repository contract, schema, rerun links, authorized scope snapshot |
| `EvidencePackage` | Yes | Yes, M014 | Yes | Stores immutable `RunId` context only | No | reconstruction, repository contract, schema, artifact metadata mapping |
| `Review` | Yes | Yes, M015 | Yes | Targets Evidence Package by immutable ID only | No | reconstruction, repository contract, schema, reviewer-independence integration |
| `DatasetManifest` | Yes | Yes, M013/M017 | Owned immutable record under Run | No | No | reconstruction within Run boundary and later schema mapping |
| `CriterionResult` | Yes | Yes, M013/M014 | Owned immutable record under Evidence Package | No | No | reconstruction within Evidence Package boundary and later schema mapping |
| `ArtifactReference` | Yes | Yes, M014 | Owned value under Evidence Package | No | No | reconstruction within Evidence Package boundary and later object-reference mapping |
| `ReviewFinding` | Yes | Yes, M015 | Owned record under Review | No | No | reconstruction within Review boundary and later schema mapping |
| `CampaignScopeStatement` | Yes | Yes, M018 | Owned value under Campaign | No | No | reconstruction within Campaign boundary |
| `AggregateVersion` | Yes | Yes, M013 | Shared primitive | No | Partially | mapping and optimistic-concurrency use remain undefined |
| `TransitionSequence` | Yes | Yes, M013 | Shared primitive | No | Partially | restoration and continuity rules remain undefined |
| `StateTransitionRecord` | Yes | Yes, M013 | Historical data only | No | Partially | transition-history loading/restoration rules remain undefined |

## 4. Persistence-Readiness Gaps

The domain model is behavior-complete for process-local mutation, but it is not yet safe to design repositories or schemas because the following bridge questions remain unresolved:

| Gap | Affected aggregate | Why it blocks repository/schema work |
| --- | --- | --- |
| Trusted reconstruction authority is undefined | Campaign, Run, Evidence Package, Review | Repositories would need to bypass public constructors without inventing ad hoc private mutation patterns |
| Persistence-neutral state shape is undefined | Campaign, Run, Evidence Package, Review | Schemas could accidentally become the domain state contract |
| Version restoration rules are undefined | All aggregates | Optimistic concurrency cannot be mapped safely without knowing how `AggregateVersion` is restored |
| Transition-sequence restoration rules are undefined | All aggregates | Repositories could corrupt append-only lifecycle history ordering |
| Transition-history completeness rules are undefined | All aggregates | The system has no rule for full, partial, or absent history loads |
| Owned collection ordering rules are not formalized for persistence | Run, Evidence Package, Review | Manifest, result, artifact-reference, and finding order could drift between memory and storage |
| Terminal aggregate restoration is undefined | All aggregates | Loaded terminal states must remain immutable without replaying public transitions |
| Rejection atomicity after reconstruction is not specified | All aggregates | Reconstructed aggregates must preserve the same invariant behavior as newly constructed aggregates |
| Cross-aggregate reference loading is not bounded | Campaign, Run, Evidence Package, Review | Repository design could accidentally load other aggregates or implement orchestration |
| Schema neutrality is not protected by a contract | All aggregates | Early schemas could leak physical table, ORM, or SQLAlchemy assumptions into domain code |

## 5. Candidate Milestones

| Candidate | Title | Architectural layer | Dependencies | Scope size | Risk | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| A | Aggregate Reconstruction Contract Design | Domain-persistence bridge design | M012-M018 frozen aggregates | Small/medium | Low | All aggregates are process-local and lack trusted reconstruction semantics |
| B | Persistence-Neutral Aggregate State Record Design | Domain state representation design | M013-M018 | Medium | Medium | State fields exist but no persistence-neutral record contract exists |
| C | Domain Repository Contracts | Persistence boundary API | A and B unresolved | Medium/high | High | Repository contracts would need reconstruction and state shape decisions first |
| D | Domain Schema and Migration Design | Physical persistence | Repository contracts unresolved | High | High | M012 explicitly defers schemas and migrations |
| E | Aggregate Persistence Mapper Implementation | Implementation | A-D unresolved | High | Critical | Would implement a bridge before the contract exists |
| F | Application Service Command Layer | Cross-aggregate orchestration | Repository contracts unresolved | High | High | Campaign completion and review staleness require loaded aggregate coordination |
| G | Audit Runtime Scope | Deferred domain concept | Audit authority unresolved | Medium/high | High | M012 defers Audit as separate process-compliance design |
| H | Decision Candidate Scope | Deferred governance-preparation concept | Evidence/review/audit sufficiency unresolved | High | High | M012 defers Decision Candidate |
| I | Outbox or Job Ledger Design | Integration infrastructure | Domain persistence unresolved | High | High | M012 treats domain events and outbox as future concerns |
| J | Additional Aggregate Hardening | Existing aggregate behavior | M014-M018 frozen | Small | Low | Current validation and hostile reviews found no open MAJOR/CRITICAL issue |

## 6. Candidate Comparison Matrix

| Criterion | A Reconstruction Contract | B State Records | C Repository Contracts | D Schema Design | F Application Services | G Audit | H Decision Candidate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Architectural ordering | Highest | High | Medium | Low | Low | Low | Low |
| Dependency readiness | High | Medium | Low | Low | Low | Low | Low |
| Isolation | High | Medium | Medium | Low | Low | Medium | Medium |
| Independent testability | High | Medium | Medium | Medium | Medium | Medium | Medium |
| Reversibility | High | Medium | Medium | Low | Medium | Medium | Medium |
| Auditability benefit | High | High | High | Medium | Medium | Medium | Medium |
| Implementation confidence | High | Medium | Low | Low | Low | Low | Low |
| Scope-creep risk | Low | Medium | High | High | High | High | High |
| Protects domain/persistence boundary | High | Medium | Medium | Low | Low | Medium | Medium |
| Unlocks future milestones | High | Medium | High after A | Medium after C | Medium after C | Low now | Low now |

Candidate A is selected because it resolves the first missing contract between the frozen process-local domain layer and future persistence without implementing repositories, schemas, mappers, or runtime behavior.

## 7. Rejected Candidates

| Candidate | Rejection reason |
| --- | --- |
| Persistence-neutral state records as a standalone milestone | Necessary input, but too narrow alone; state shape must be tied to trusted reconstruction authority, invariant preservation, and aggregate behavior compatibility |
| Domain repository contracts | Premature until reconstruction authority, restored state shape, history restoration, and version semantics are defined |
| Domain schema and migration design | Premature and too physical; could freeze table shapes before the domain-persistence contract exists |
| Aggregate persistence mapper implementation | Implementation would violate the current bridge gap and create hidden repository/schema assumptions |
| Application service command layer | Requires repositories or aggregate loading contracts and would introduce cross-aggregate behavior too early |
| Audit runtime | Still deferred by M012 and does not unlock persistence for the existing aggregate set |
| Decision Candidate runtime | Still deferred by M012 and depends on evidence/review/audit sufficiency not yet implemented |
| Outbox or job ledger | Depends on persistence boundaries and event semantics that remain deferred |
| Additional aggregate hardening | No current repository evidence shows an open MAJOR or CRITICAL aggregate behavior defect |

## 8. Selected Milestone

Selected milestone:

```text
MILESTONE-019 - Aggregate Reconstruction Contract Design
```

One-sentence purpose:

```text
Define the persistence-neutral contract by which trusted infrastructure may reconstruct frozen process-local aggregates from stored state without replaying public behavior or leaking persistence details into the domain model.
```

Milestone type:

```text
Design and contract scope only; no implementation.
```

## 9. Exact Boundary

MILESTONE-019 shall define:

- trusted reconstruction authority;
- reconstruction entry-point expectations for each aggregate;
- persistence-neutral aggregate state requirements;
- required state fields for Campaign, Run, Evidence Package, and Review;
- owned-record restoration requirements;
- `AggregateVersion` restoration rules;
- `TransitionSequence` restoration rules;
- `StateTransitionRecord` restoration and ordering rules;
- terminal-state restoration rules;
- invariant preservation after reconstruction;
- rejection atomicity after reconstruction;
- separation between reconstruction contracts and public behavior methods;
- repository/schema neutrality rules;
- test expectations for any later implementation milestone.

MILESTONE-019 shall not implement any code or select a physical persistence model.

## 10. Allowed Deliverables

The future M019 deliverable may include:

- a contract design document;
- aggregate-by-aggregate reconstruction field inventory;
- persistence-neutral state-shape requirements;
- reconstruction trust boundary;
- rejected reconstruction options;
- version and transition-sequence consistency rules;
- transition-history loading policy;
- owned collection ordering policy;
- compatibility matrix against M014-M018 aggregate behavior;
- future implementation acceptance criteria;
- hostile-review checklist.

## 11. Explicit Non-Goals

MILESTONE-019 must not include:

- source code;
- aggregate implementation changes;
- schemas, tables, columns, migrations, or ORM mappings;
- repository interfaces or concrete repositories;
- SQLAlchemy domain mappings;
- object-storage layout;
- APIs;
- workers;
- application services;
- runtime composition changes;
- event dispatch;
- job ledger;
- outbox;
- Audit runtime;
- Decision Candidate runtime;
- Decision Freeze;
- vendor behavior;
- market-data behavior;
- trading behavior;
- empirical campaign execution.

## 12. Aggregate Coverage

MILESTONE-019 must cover every frozen process-local aggregate:

| Aggregate | Required reconstruction questions |
| --- | --- |
| Campaign | identity, scope statement, lifecycle state, version, next transition sequence, transition history, terminal state |
| Run | identity, Campaign context, lifecycle state, version, next transition sequence, transition history, ordered Dataset Manifest collection, current manifest derivation |
| Evidence Package | identity, Run context, lifecycle state, version, next transition sequence, transition history, Criterion Result collection, ArtifactReference collection, sealed/invalidated state |
| Review | identity, target reference, reviewer reference, lifecycle state, version, next transition sequence, transition history, findings, next finding sequence, disposition, rationale, cancellation reason |

The milestone must preserve the current aggregate public behavior and must not redesign aggregate state unless a documented contradiction is proven.

## 13. Reconstruction Considerations

The future design must decide whether reconstruction is expressed as:

- aggregate classmethod;
- package-local factory;
- dedicated trusted reconstructor;
- separate domain-state loader contract;
- other persistence-neutral approach.

The selected approach must:

- avoid calling public lifecycle methods to rebuild historical state;
- avoid appending duplicate transition records during load;
- avoid incrementing versions during load;
- avoid exposing setters or mutable collections to ordinary callers;
- avoid SQLAlchemy, database row, object-storage, or repository types in aggregate constructors;
- keep reconstruction trusted and visibly separated from public behavior.

## 14. Version and Concurrency Considerations

MILESTONE-019 must define:

- whether `AggregateVersion.initial()` remains construction-only;
- how persisted aggregate versions are restored;
- how stale-version checks are expected to interact with future repositories;
- whether restored versions may be zero;
- whether version gaps are permitted;
- how content mutations and lifecycle transitions remain distinguishable after reconstruction;
- how version validation remains local and persistence-neutral.

No database locking, isolation level, transaction boundary, or repository method may be designed by this milestone.

## 15. Transition-History Considerations

MILESTONE-019 must define:

- whether transition history is mandatory for reconstruction;
- whether partial history is allowed for command handling;
- how `next_transition_sequence` is derived or restored;
- how transition record identity references are restored;
- how lifecycle state and final transition history are checked for consistency;
- how missing or inconsistent transition history is reported in a future implementation;
- whether transition history remains historical data only and not an outbox/event stream.

The milestone must preserve the M013 rule that `StateTransitionRecord` is not a domain event, event-store record, queue message, or outbox payload by default.

## 16. Collection Considerations

MILESTONE-019 must define ordered restoration semantics for:

- Run-owned `DatasetManifest` records;
- Evidence-Package-owned `CriterionResult` records;
- Evidence-Package-owned `ArtifactReference` values;
- Review-owned `ReviewFinding` records.

The design must specify whether order is persisted explicitly, derived from insertion order, or supplied by a future repository contract, without defining schema columns.

## 17. Domain/Persistence Separation

The selected M019 scope must preserve these boundary rules:

- domain packages do not import persistence adapters;
- domain packages do not import SQLAlchemy, psycopg, boto, MinIO, or filesystem APIs;
- repositories are not introduced;
- schemas are not introduced;
- object-storage keys and buckets are not introduced;
- aggregate reconstruction does not imply campaign execution, validation execution, or authorization execution;
- PostgreSQL remains future metadata source of truth only at the architecture level, not a domain import or schema design.

## 18. Required Design Questions

MILESTONE-019 must answer:

1. Who is allowed to reconstruct an aggregate?
2. Is reconstruction public API, package-internal API, or contract documentation only?
3. What is the minimum complete state for each aggregate?
4. Which restored fields are derived versus authoritative?
5. How are invalid persisted states rejected?
6. How are owned collections restored without exposing mutation?
7. How are terminal states restored without making them mutable?
8. How are versions and transition sequences restored without incrementing?
9. How does reconstruction preserve rejection atomicity for later commands?
10. What remains deferred to repository, schema, and mapper milestones?

## 19. Risks

| Risk | Severity | Mitigation required in M019 |
| --- | --- | --- |
| Reconstruction contract becomes hidden repository design | MAJOR | Explicitly prohibit repository methods, database rows, ORM mappings, and schema fields |
| State representation becomes physical schema | MAJOR | Require persistence-neutral state language and no table/column names |
| Public behavior methods are used to replay state | MAJOR | Require trusted reconstruction that does not emit transitions or increment versions |
| Transition history is treated as an event stream | MAJOR | Preserve StateTransitionRecord as historical data only |
| Aggregate invariants are weakened for persistence | MAJOR | Require post-reconstruction behavior-equivalence tests in future implementation |
| Scope expands to all persistence | CRITICAL | Stop if repository contracts, schemas, migrations, mappers, or runtime composition are introduced |
| Owned collection ordering remains ambiguous | MINOR | Require collection-ordering policy for each owned collection |
| Future optimistic concurrency remains underdefined | MINOR | Define version restoration and stale-version expectations without database design |

## 20. Validation Expectations

The M019 design mission must run the repository's current verification gates and keep the working tree limited to documentation:

```powershell
.\scripts\security.ps1
.\scripts\verify.ps1
python -m ruff format --check .
python -m ruff check .
python -m mypy
python tools/check_architecture.py .
git diff --check
git status --short
```

No source file, test file, migration file, infrastructure file, or runtime configuration file may change during M019 design.

## 21. Hostile-Review Criteria

The independent review for M019 must verify:

- reconstruction is necessary before repository contracts;
- all four frozen aggregates are covered;
- the design is persistence-neutral;
- no schema or repository API is introduced;
- no aggregate behavior is modified;
- no cross-aggregate behavior is introduced;
- public constructors remain creation-oriented unless explicitly and safely differentiated from reconstruction;
- terminal, version, sequence, and history semantics are preserved;
- transition history is not reclassified as an event stream or outbox;
- object-storage layout remains deferred;
- the milestone does not begin Audit, Decision Candidate, Decision Freeze, or campaign execution behavior.

## 22. Acceptance Gate

MILESTONE-019 may be accepted only if:

- it selects exactly one reconstruction-contract approach or records a bounded unresolved decision with a blocking status;
- it defines aggregate-by-aggregate reconstruction state requirements;
- it keeps persistence and storage concerns outside the domain model;
- it clearly rejects premature repository, schema, migration, mapper, API, worker, outbox, and orchestration work;
- it preserves M012-M018 frozen behavior;
- it leaves source code unchanged;
- all validation gates pass.

## 23. Stop Conditions

Stop M019 immediately if:

- a source file change is required;
- a schema, migration, table, ORM mapping, or repository method is introduced;
- the design requires SQLAlchemy or PostgreSQL types in domain contracts;
- object-storage layout appears in the reconstruction contract;
- campaign execution or validation execution is introduced;
- Audit or Decision Candidate behavior becomes part of the scope;
- a contradiction with M012-M018 frozen behavior cannot be resolved by documentation alone.

## 24. Deferred Work

Deferred beyond M019:

- repository contract design;
- aggregate persistence mapper design;
- physical schema and migration design;
- repository implementation;
- aggregate reconstruction implementation;
- application services and command handlers;
- cross-aggregate invariant enforcement;
- idempotency keys;
- outbox and job ledger;
- Audit runtime;
- Decision Candidate runtime;
- Decision Freeze;
- campaign execution and empirical validation behavior.

## 25. Hostile Self-Review

| Issue ID | Severity | Finding | Correction | Status |
| --- | --- | --- | --- | --- |
| M019-SCOPE-SELF-REVIEW-0001 | MAJOR | Initial selection risked combining state records and repository contracts. | Scope narrowed to reconstruction contract design and explicitly excludes repository APIs and schemas. | Resolved |
| M019-SCOPE-SELF-REVIEW-0002 | MAJOR | Repository contracts were tempting because persistence connectivity already exists. | Candidate C is rejected until reconstruction authority and state shape are defined. | Resolved |
| M019-SCOPE-SELF-REVIEW-0003 | MINOR | Transition-history restoration could be underspecified. | Added a dedicated transition-history section and acceptance criteria. | Resolved |
| M019-SCOPE-SELF-REVIEW-0004 | MINOR | A Campaign-only or Run-only bridge would leave the aggregate set inconsistent. | Required coverage of Campaign, Run, Evidence Package, and Review. | Resolved |
| M019-SCOPE-SELF-REVIEW-0005 | MAJOR | State shape could be mistaken for physical schema. | Added persistence-neutrality rules and a stop condition against table/column/ORM design. | Resolved |

No MAJOR or CRITICAL self-review issue remains open.

## 26. Final Decision

The next bounded post-domain milestone is:

```text
MILESTONE-019 - Aggregate Reconstruction Contract Design
```

This is the smallest safe persistence bridge because it answers how frozen process-local aggregates can later be loaded from durable state without prematurely designing repositories, schemas, migrations, SQL mappings, application services, or runtime execution.

Final scope-selection status:

```text
SCOPE CANDIDATE SELECTED
```
