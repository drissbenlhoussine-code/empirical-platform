# MILESTONE-017 - Process-Local Run Aggregate Behavior

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-017 |
| Title | Process-Local Run Aggregate Behavior |
| Version | 1.0 |
| Status | APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Frozen architecture baseline | `17e4a43fe97ca3fa23b5c9aedc54f65a7b7d0d52` |
| Implementation baseline | `44141a2034bf5cffd97273e5b519caf4ac28fbb0` |
| Scope authority | `MILESTONE_017_PROCESS_LOCAL_RUN_AGGREGATE_BEHAVIOR_SCOPE_SELECTION.md` |
| Implementation type | Process-local aggregate behavior only |
| Persistence introduced | No |
| Schemas or migrations introduced | No |
| APIs or workers introduced | No |

## 2. Scope Summary

This milestone implements exactly one process-local aggregate:

```text
Run
```

The Run aggregate manages one execution attempt lifecycle, immutable Campaign context, and append-only Dataset Manifest records. It does not load, inspect, validate, or mutate Campaign, Evidence Package, Review, Audit, Decision Candidate, persistence, object storage, vendor data, or market-data execution behavior.

## 3. Package Placement

| Package | Responsibility |
| --- | --- |
| `empirical_platform.run.aggregate` | Process-local Run aggregate root |
| `empirical_platform.run.__init__` | Public Run package export |
| `tests.unit.test_run_aggregate` | Focused Run behavior, invariant, lifecycle, manifest, and boundary tests |
| `tools.check_architecture` | Narrow `run` dependency rule with exact `campaign.lifecycle` allowance |
| `tests.fixtures.illegal_imports` | Negative architecture fixtures for forbidden reverse and premature dependencies |

## 4. Requirement-to-Code Traceability

| Requirement | Implementation | Test evidence |
| --- | --- | --- |
| `DomainIdentity[RunId]` identity | `Run.identity` | construction tests |
| Immutable Campaign context | `Run.campaign_id` | construction and boundary tests |
| Initial state `CREATED` | `Run.__init__` | construction tests |
| Allowed lifecycle transitions | named transition methods | lifecycle matrix tests |
| Terminal states | transition and manifest guards | terminal immutability tests |
| Dataset Manifest ownership | `Run.append_manifest` | manifest ownership tests |
| Manifest supersession by append order | `Run.manifests`, `Run.current_manifest` | supersession tests |
| Version increments | `AggregateVersion.next()` usage | lifecycle, manifest, and mixed-sequence tests |
| Transition sequence | `TransitionSequence.next()` usage | lifecycle and mixed-sequence tests |
| Transition history | `StateTransitionRecord` append | lifecycle and mixed-sequence tests |
| Rejection atomicity | validate-before-mutate implementation | snapshot rejection tests |
| Boundary compliance | no deferred dependency surface | boundary and architecture tests |

## 5. Aggregate Design

`Run` is a concrete process-local aggregate root. It is not a repository, command handler, workflow engine, event source, persistence model, API handler, or orchestration service.

The aggregate stores:

- `DomainIdentity[RunId]`;
- immutable parent `CampaignId`;
- `RunLifecycleState`;
- `AggregateVersion`;
- next `TransitionSequence`;
- tuple of `StateTransitionRecord`;
- tuple of immutable `DatasetManifest`.

All collection views are tuples. No mutable collection is exposed.

## 6. Lifecycle Matrix

Allowed lifecycle transitions:

| From | Operation | To | Reason required |
| --- | --- | --- | --- |
| `CREATED` | `authorize` | `AUTHORIZED` | No |
| `AUTHORIZED` | `start_acquisition` | `ACQUIRING` | No |
| `ACQUIRING` | `start_normalization` | `NORMALIZING` | No |
| `NORMALIZING` | `start_validation` | `VALIDATING` | No |
| `VALIDATING` | `complete_execution` | `EXECUTION_COMPLETED` | No |
| `AUTHORIZED` | `cancel` | `CANCELLED` | Yes |
| `ACQUIRING` | `fail` | `FAILED` | Yes |
| `NORMALIZING` | `fail` | `FAILED` | Yes |
| `VALIDATING` | `fail` | `FAILED` | Yes |

Each accepted lifecycle transition:

- increments `AggregateVersion` exactly once;
- appends exactly one `StateTransitionRecord`;
- records the current `TransitionSequence`;
- advances the next `TransitionSequence` exactly once.

Construction does not append lifecycle history.

## 7. Manifest Mutation Matrix

| Current state | Append Dataset Manifest | Version | Sequence | History |
| --- | --- | --- | --- | --- |
| `CREATED` | Allowed | +1 | unchanged | unchanged |
| `AUTHORIZED` | Allowed | +1 | unchanged | unchanged |
| `ACQUIRING` | Allowed | +1 | unchanged | unchanged |
| `NORMALIZING` | Allowed | +1 | unchanged | unchanged |
| `VALIDATING` | Allowed | +1 | unchanged | unchanged |
| `EXECUTION_COMPLETED` | Rejected | unchanged | unchanged | unchanged |
| `FAILED` | Rejected | unchanged | unchanged | unchanged |
| `CANCELLED` | Rejected | unchanged | unchanged | unchanged |

Dataset Manifest append validates only local process-boundary invariants:

- input is a canonical `DatasetManifest`;
- `manifest.run_id` matches the Run identity;
- duplicate non-null `manifest_id` values are rejected inside one Run;
- unidentified manifests may be appended multiple times;
- prior manifests are never edited, removed, or reordered.

The latest appended manifest is exposed as `current_manifest`. Before any append, `current_manifest` is `None`.

## 8. Local Invariant Table

| Invariant | Enforcement point | Rejected behavior | Atomicity evidence |
| --- | --- | --- | --- |
| Run identity is `DomainIdentity[RunId]` | constructor | wrong identity type or governance ID | construction tests |
| Campaign context is `CampaignId` | constructor | wrong Campaign context type | construction tests |
| Campaign context is immutable data only | no Campaign object reference | Campaign load/mutation/orchestration surface | boundary tests |
| Lifecycle transitions use named methods only | transition methods | skipped, repeated, unsupported, terminal transitions | lifecycle rejection tests |
| Terminal states are immutable | lifecycle and append guards | manifest or lifecycle mutation after terminal | terminal tests |
| Dataset Manifest belongs to this Run | `append_manifest` | wrong `run_id` | manifest rejection tests |
| Manifest supersession is append-only | tuple append | replacement, deletion, reordering, supersession field | supersession tests |
| Transition metadata is valid | `_transition` | invalid actor, timestamp, correlation, reason | metadata rejection tests |

## 9. Version, Sequence, and History Analysis

Lifecycle transitions and manifest appends both advance aggregate version exactly once after all validation succeeds.

Only lifecycle transitions consume and advance `TransitionSequence`. Manifest appends do not append transition history and do not advance transition sequence.

Representative mixed path evidence:

```text
append manifest
authorize
start acquisition
append manifest
start normalization
start validation
complete execution
```

Final expected state:

```text
state = EXECUTION_COMPLETED
version = 7
next_transition_sequence = 6
history length = 5
manifest count = 2
```

## 10. Architecture Rule Changes

`tools/check_architecture.py` now registers one new top-level domain package:

```text
run -> shared, identifiers, datasets
```

It also registers one exact import allowance:

```text
run -> empirical_platform.campaign.lifecycle
```

This is the narrow dependency set authorized by the hardened M017 scope. The `campaign.lifecycle` dependency is only for the existing canonical `RunLifecycleState` source. Broad `run -> campaign` imports remain forbidden.

Negative architecture fixtures now verify:

- `datasets -> run` remains forbidden;
- `campaign -> datasets` remains forbidden;
- `campaign -> run` remains forbidden;
- broad `run -> campaign` remains forbidden;
- `evidence -> run` remains forbidden;
- `review -> run` remains forbidden;
- existing `review -> acquisition` remains forbidden.

No generic domain-to-domain import allowance was introduced.

## 11. Tests Added

Focused M017 tests cover:

- valid construction;
- wrong Run identity type;
- wrong Campaign context type;
- initial lifecycle, version, sequence, history, manifest collection, and current-manifest behavior;
- every accepted lifecycle transition;
- every invalid state-operation pair;
- terminal-state lifecycle rejection;
- invalid transition metadata;
- cancellation and failure reason validation;
- valid manifest append in every permitted lifecycle state;
- manifest rejection in every terminal state;
- wrong manifest type;
- wrong Run ownership identity;
- duplicate non-null manifest identity;
- multiple unidentified manifests;
- insertion order;
- latest manifest as current manifest;
- append-only supersession;
- immutable tuple exposure;
- cumulative version, sequence, and history behavior;
- absence of deferred infrastructure and cross-aggregate surfaces.

## 12. Validation Evidence

Focused MILESTONE-017 command:

```powershell
python -m pytest tests\unit\test_run_aggregate.py tests\architecture\test_module_boundaries.py --no-cov
```

Focused result:

```text
36 passed
```

Static validation:

```text
Python 3.13.14
ruff format --check: 100 files already formatted
ruff check: passed
mypy: passed in strict mode across 57 source files
architecture checker: passed
negative architecture fixture: produced expected violations
git diff --check: passed with Git LF-to-CRLF working-copy warnings only
```

Security validation:

```text
Python 3.13.14
security.ps1 passed
Secret scan target count: 169
No known vulnerabilities found
```

Full verification:

```text
Python 3.13.14
verify.ps1 passed
175 passed, 9 skipped
Coverage: 92.81%
Architecture checker passed
Negative architecture fixtures passed
Build passed
Import/version check passed: 0.0.0
```

Build warnings:

```text
Setuptools emitted an existing deprecation warning for project.license TOML table format. No M017 behavior depends on this warning.
```

## 13. Hostile Review

| Check | Result |
| --- | --- |
| Scope creep | PASS |
| Frozen architecture violation | PASS |
| Persistence leakage | PASS |
| Infrastructure leakage | PASS |
| Cross-aggregate lookup or mutation | PASS |
| Unsupported lifecycle behavior | PASS |
| Missing accepted lifecycle transition | PASS |
| Incorrect version increments | PASS |
| Incorrect transition-sequence increments | PASS |
| False transition-history entries for manifest append | PASS |
| Mutable collection exposure | PASS |
| Duplicate-rule enforcement | PASS |
| Manifest ownership check | PASS |
| Terminal mutation rejection | PASS |
| Rejection atomicity | PASS |
| Deferred functionality introduced | PASS |
| Migration/schema creation | PASS |

## 14. Scope-Integrity Audit

| Check | Result |
| --- | --- |
| No persistence introduced | PASS |
| No repositories introduced | PASS |
| No schemas introduced | PASS |
| No migrations introduced | PASS |
| No APIs introduced | PASS |
| No workers introduced | PASS |
| No outbox or event dispatch introduced | PASS |
| No Campaign aggregate behavior introduced | PASS |
| No Evidence Package behavior changed | PASS |
| No Review behavior changed | PASS |
| No Audit introduced | PASS |
| No Decision Candidate introduced | PASS |
| No Decision Freeze introduced | PASS |
| No cross-aggregate validation introduced | PASS |
| No DatasetManifest redesign introduced | PASS |
| No vendor, market-data, trading, or campaign execution behavior introduced | PASS |
| `migrations/versions` remains empty | PASS |

## 15. Issue Register

| Issue ID | Severity | Finding | Resolution |
| --- | --- | --- | --- |
| M017-IMPLEMENTATION-ISSUE-0001 | MINOR | Initial full validation commands were invoked from a subprocess that used global Python 3.14 instead of the canonical `.venv` Python 3.13.14. | Reran `security.ps1` and `verify.ps1` with `.venv` activated in the same PowerShell process; both passed. |
| M017-IMPLEMENTATION-ISSUE-0002 | MINOR | Initial lint found test helper function calls in default arguments. | Replaced defaults with a sentinel-backed helper while preserving unidentified-manifest test behavior; focused and full validation passed. |
| M017-IMPLEMENTATION-ISSUE-0003 | MAJOR | Independent hostile review found `run -> campaign` was implemented as a broad top-level architecture permission even though only `campaign.lifecycle` was authorized. | Replaced the broad permission with an exact import allowance for `empirical_platform.campaign.lifecycle` and added a negative fixture proving broad `run -> campaign` remains forbidden. |
| M017-IMPLEMENTATION-ISSUE-0004 | MINOR | Independent hostile review requested stronger mixed-path tests for cancellation and failure after manifest appends. | Added cancellation-after-manifest and execution-stage failure-after-manifest tests covering cumulative version, sequence, history, manifest order, and reason behavior. |

No CRITICAL or MAJOR implementation issue remains open.

## 16. Deferred Items

- Campaign aggregate behavior;
- Campaign authorization validation;
- parent Campaign existence checks;
- authorized scope snapshot value object;
- richer Dataset Manifest supersession reference;
- rerun link record behavior;
- Evidence Package changes;
- Review changes;
- Run-target Review behavior;
- Audit runtime;
- Decision Candidate runtime;
- Decision Freeze;
- persistence schemas and repositories;
- APIs and workers;
- job ledger and outbox;
- object-storage layout and retention policy;
- acquisition, normalization, validation engine behavior;
- market-data, vendor, trading, and empirical campaign execution behavior.

## 17. Files Created and Modified

Created:

- `MILESTONE_017_PROCESS_LOCAL_RUN_AGGREGATE_BEHAVIOR.md`;
- `src/empirical_platform/run/__init__.py`;
- `src/empirical_platform/run/aggregate.py`;
- `tests/unit/test_run_aggregate.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/campaign/bad_dataset_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/campaign/bad_run_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/datasets/bad_run_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/evidence/bad_run_import.py`;
- `tests/fixtures/illegal_imports/src/empirical_platform/review/bad_run_import.py`.

Modified:

- `tools/check_architecture.py`;
- `tests/architecture/test_module_boundaries.py`.

## 18. Final Decision

MILESTONE-017 implementation is approved and frozen after independent hostile review and M017-scoped hardening.

Final status:

```text
APPROVED AND FROZEN
```
