# MILESTONE-018 - Process-Local Campaign Aggregate Behavior

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-018 |
| Title | Process-Local Campaign Aggregate Behavior |
| Version | 1.0 |
| Status | APPROVED FOR HOSTILE REVIEW |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Implementation baseline | `912e5ed1e8904ccef60f2ac40a43b7ff84236921` |
| Baseline meaning | Hardened M018 scope approved for implementation |
| Mission type | Process-local domain aggregate implementation |
| Source modified | Yes, Campaign package only |
| Schemas or migrations created | No |
| Repository contracts created | No |
| APIs or workers created | No |

## 2. Scope

This milestone implements only the process-local Campaign aggregate behavior approved by
`MILESTONE_018_PROCESS_LOCAL_CAMPAIGN_AGGREGATE_BEHAVIOR_SCOPE_SELECTION.md`.

Included:

- `Campaign` aggregate root;
- immutable `CampaignScopeStatement`;
- canonical Campaign lifecycle transitions;
- DRAFT-only scope replacement;
- aggregate versioning;
- transition sequence advancement;
- immutable lifecycle transition history;
- focused unit tests;
- minimal public exports.

Excluded:

- Run imports, Run IDs, Run coordination, or Run state inspection;
- Dataset, Evidence Package, Review, Audit, Decision Candidate, or Decision Freeze behavior;
- authorization execution or governance authority lookup;
- readiness checklist, score, calculator, or external gate;
- persistence, repositories, schemas, migrations, APIs, workers, job ledger, outbox, event dispatch, or orchestration;
- market-data, vendor, trading, strategy, signal, order, or execution behavior.

## 3. Repository Evidence Reviewed

| Evidence | Relevance |
| --- | --- |
| `MILESTONE_012_CANONICAL_RUNTIME_DOMAIN_KERNEL_DESIGN.md` | Campaign lifecycle and aggregate boundary |
| `MILESTONE_013_PROCESS_LOCAL_DOMAIN_PRIMITIVE_FOUNDATION.md` | Canonical identity, version, sequence, transition primitives |
| `MILESTONE_014_PROCESS_LOCAL_EVIDENCE_PACKAGE_AGGREGATE_BEHAVIOR.md` | Aggregate implementation pattern |
| `MILESTONE_015_PROCESS_LOCAL_REVIEW_AGGREGATE_BEHAVIOR.md` | Aggregate-local mutation and transition pattern |
| `MILESTONE_016_RUN_AGGREGATE_BOUNDARY_RECONCILIATION_DECISION.md` | Run/Campaign import direction and boundary decision |
| `MILESTONE_017_PROCESS_LOCAL_RUN_AGGREGATE_BEHAVIOR.md` | Run aggregate behavior and Campaign deferral |
| `src/empirical_platform/campaign/lifecycle.py` | Canonical `CampaignLifecycleState` |
| `src/empirical_platform/shared/domain/` | `AggregateVersion`, `TransitionSequence`, `StateTransitionRecord` |
| `tools/check_architecture.py` | Static package-boundary constraints |

## 4. Package Placement

Created:

- `src/empirical_platform/campaign/aggregate.py`
- `tests/unit/test_campaign_aggregate.py`

Modified:

- `src/empirical_platform/campaign/__init__.py`

No architecture checker change was required.

## 5. Campaign Aggregate Design

`Campaign` is a process-local aggregate root with these fields:

| Field | Type | Mutation rule |
| --- | --- | --- |
| `_identity` | `DomainIdentity[CampaignId]` | Immutable after construction |
| `_scope_statement` | `CampaignScopeStatement` | Replaceable only in `DRAFT` |
| `_state` | `CampaignLifecycleState` | Lifecycle transitions only |
| `_version` | `AggregateVersion` | Incremented after accepted mutations |
| `_next_transition_sequence` | `TransitionSequence` | Advanced only by lifecycle transitions |
| `_transition_history` | tuple of `StateTransitionRecord[DomainIdentity[CampaignId]]` | Append-only for lifecycle transitions |

Construction enforces:

- identity is a `DomainIdentity`;
- identity governance ID is a `CampaignId`;
- scope statement is a `CampaignScopeStatement`;
- initial state is `DRAFT`;
- initial version is `AggregateVersion.initial()`;
- initial sequence is `TransitionSequence.initial()`;
- transition history is empty.

## 6. CampaignScopeStatement Design

`CampaignScopeStatement` is a frozen slots dataclass with one field:

```text
value: str
```

Validation:

- `value` must be a string;
- `value.strip()` must be non-empty;
- the object is immutable, hashable, and deterministic.

It contains no Run, Dataset, Evidence Package, Review, vendor, market-data, trading, repository, storage, credential,
or schedule structure.

## 7. Lifecycle Matrix

| Current state | Method | Next state | Reason required | Scope |
| --- | --- | --- | --- | --- |
| `DRAFT` | `prepare_for_authorization` | `READY_FOR_AUTHORIZATION` | No | Local readiness lifecycle record only |
| `READY_FOR_AUTHORIZATION` | `record_authorization` | `AUTHORIZED` | Yes | Opaque local authorization rationale only |
| `AUTHORIZED` | `activate` | `ACTIVE` | Yes | Local activation record only |
| `ACTIVE` | `suspend` | `SUSPENDED` | Yes | Local suspension record only |
| `SUSPENDED` | `resume` | `ACTIVE` | Yes | Local resume record only |
| `ACTIVE` | `complete` | `COMPLETED` | Yes | Local completion record only |
| `DRAFT` | `cancel` | `CANCELLED` | No | Optional abandonment note |
| `READY_FOR_AUTHORIZATION` | `cancel` | `CANCELLED` | No | Optional abandonment note |
| `AUTHORIZED` | `cancel` | `CANCELLED` | Yes | Required cancellation reason |
| `ACTIVE` | `cancel` | `CANCELLED` | Yes | Required cancellation reason |
| `SUSPENDED` | `cancel` | `CANCELLED` | Yes | Required cancellation reason |

All other state-operation pairs are rejected atomically.

Terminal states:

- `COMPLETED`
- `CANCELLED`

No reopen, restart, retry, archival, supersession, Decision Candidate, or Decision Freeze behavior exists.

## 8. Scope Mutation Matrix

| Operation | Required state | Version | Sequence | History |
| --- | --- | --- | --- | --- |
| `revise_scope_statement` | `DRAFT` | +1 | unchanged | unchanged |
| Rejected scope replacement | any invalid condition | unchanged | unchanged | unchanged |

Scope replacement validates the replacement object before state mutation.

## 9. Local Invariant Table

| Invariant | Enforcement |
| --- | --- |
| Campaign identity is `DomainIdentity[CampaignId]` | Constructor type checks |
| Scope statement is Campaign-local and immutable | `CampaignScopeStatement` frozen dataclass |
| Readiness is lifecycle only | No readiness field/object/calculator exists |
| Authorization is local recording only | `record_authorization` only records transition reason |
| Activation is local recording only | `activate` mutates only Campaign lifecycle state |
| Completion does not inspect Runs or Reviews | `complete` requires only local state and reason |
| Cancellation does not mutate downstream state | `cancel` records one local lifecycle transition |
| Terminal states reject all mutation | State matrix and scope replacement checks |

## 10. Version, Sequence, and History Analysis

Accepted lifecycle transition:

- validates current state, timestamp, actor, correlation ID, and reason before mutation;
- computes `next_version = current_version.next()`;
- records the current transition sequence in one `StateTransitionRecord`;
- advances next transition sequence exactly once;
- appends exactly one immutable transition record;
- mutates state, version, sequence, and history only after validation succeeds.

Accepted scope replacement:

- validates replacement type and DRAFT state before mutation;
- increments version exactly once;
- does not advance transition sequence;
- does not append transition history.

Rejected operations leave identity, scope statement, state, version, next sequence, and history unchanged.

## 11. Tests Added

`tests/unit/test_campaign_aggregate.py` adds 38 focused tests covering:

- construction and wrong identity rejection;
- immutable identity and absence of authority/Run surfaces;
- `CampaignScopeStatement` validation, immutability, equality, and hashing;
- DRAFT-only scope replacement;
- every allowed lifecycle transition;
- invalid state-operation pairs from every lifecycle state;
- metadata validation;
- required reason validation;
- cancellation reason rules before and after authorization;
- readiness as lifecycle only;
- authorization recording without implicit activation;
- suspension/resume repetition and terminal rejection;
- terminal immutability;
- cumulative mixed path version, sequence, history, and scope behavior;
- valid cancellation paths;
- absence of infrastructure, repository, outbox, Audit, Decision Candidate, vendor, market-data, trading, and orchestration surfaces.

## 12. Validation Evidence

| Check | Result |
| --- | --- |
| Python | `3.13.14` |
| Focused tests | `38 passed` |
| Full test suite | `213 passed, 9 skipped` |
| Coverage | `93.24%` |
| `security.ps1` | Passed |
| Secret scan target count | `172` |
| Dependency audit | No known vulnerabilities; local package skipped because it is not on PyPI |
| `ruff format --check .` | `102 files already formatted` |
| `ruff check .` | Passed |
| `mypy` | Passed; `58 source files` |
| Architecture checker | Passed |
| Negative fixtures | Passed; forbidden imports include `campaign -> datasets` and `campaign -> run` |
| Build/import/version checks | Passed |

Known warning:

- Setuptools warns that `project.license` as a TOML table is deprecated before 2027-02-18. This is pre-existing packaging metadata behavior and not introduced by M018.

## 13. Scope-Integrity Audit

| Check | Result |
| --- | --- |
| No Run import or behavior | PASS |
| No Run ID storage | PASS |
| No Dataset import | PASS |
| No Evidence Package behavior | PASS |
| No Review behavior | PASS |
| No authorization execution | PASS |
| No readiness checklist/score/calculator | PASS |
| No persistence | PASS |
| No repositories | PASS |
| No schemas | PASS |
| No migrations | PASS |
| No APIs | PASS |
| No workers | PASS |
| No job ledger/outbox | PASS |
| No Audit runtime | PASS |
| No Decision Candidate or Decision Freeze | PASS |
| No market-data, vendor, or trading behavior | PASS |
| No orchestration | PASS |
| No frozen primitive redesign | PASS |

`migrations/versions` remains empty.

## 14. Issue Register

| Issue ID | Severity | Finding | Resolution | Status |
| --- | --- | --- | --- | --- |
| M018-IMPLEMENTATION-ISSUE-0001 | MINOR | Initial implementation had one overlong error string. | Wrapped message without behavior change. | Resolved |
| M018-IMPLEMENTATION-ISSUE-0002 | MINOR | `cancel` required an explicit type narrowing for post-authorization required reason semantics. | Added explicit `None` rejection before non-empty validation. | Resolved |

No CRITICAL or MAJOR M018 implementation issues remain open.

## 15. Files Created And Modified

Created:

- `src/empirical_platform/campaign/aggregate.py`
- `tests/unit/test_campaign_aggregate.py`
- `MILESTONE_018_PROCESS_LOCAL_CAMPAIGN_AGGREGATE_BEHAVIOR.md`

Modified:

- `src/empirical_platform/campaign/__init__.py`

## 16. Deferred Items

| Deferred item | Reason |
| --- | --- |
| Campaign-to-Run relationship model | Cross-aggregate relationship intentionally excluded |
| Campaign completion enforcement using active Run/Review state | Application service or later command-time scope |
| Authorization policy execution | Governance/application-service responsibility |
| Campaign owner, sponsor, reviewer assignment | Workflow/authority scope |
| Repository contracts | Requires aggregate persistence boundary milestone |
| Schemas/migrations | Requires repository and persistence model |
| Audit runtime | Deferred by M012 |
| Decision Candidate runtime | Deferred by M012 |
| Decision Freeze | Governance decision layer, not aggregate behavior |

## 17. Blockers

None for M018 implementation review.

## 18. Independent Score

Score: 97 / 100

Rationale:

- Full lifecycle matrix implemented with focused tests.
- Version, sequence, history, and rejection atomicity are covered.
- Campaign remains process-local and does not import Run, Dataset, Evidence, Review, persistence, repositories, or orchestration.
- Minor residual risk remains around future application-service semantics for authorization and completion, but those are explicitly deferred and outside M018.

## 19. Final Status

```text
APPROVED FOR HOSTILE REVIEW
```

M018 is implemented and ready for a separate independent hostile-review/freeze mission. This document does not claim M018 is frozen.
