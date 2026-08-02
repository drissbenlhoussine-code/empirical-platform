# MILESTONE-033 - Concrete Application Command Vertical Slice (Run Creation) Implementation Freeze

## 1. Milestone Identity

| Field | Value |
| --- | --- |
| Milestone | MILESTONE-033 |
| Working title | Concrete Application Command Vertical Slice (Run Creation) |
| Freeze type | Owner Implementation Freeze |

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `18dabb8966a0b54572aea684e4a5075448052bc0` |

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Concrete Application Command Vertical Slice — Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |

## 4. M033 Scope Authority

`MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_SCOPE.md`, candidate commit `04e274240f7958d80bc0cb87f92f825b563fbd5a`.

## 5. M033 Scope-Freeze Authority

`MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_SCOPE_FREEZE.md`, freeze commit `44dd29e34f6150bd37bc466eed14098d75ac57ab`. **M033 SCOPE APPROVED_AND_FROZEN.**

## 6. M033 Design Authority

`MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN.md`, candidate commit `8edead3bc25d786cef8563f4fc4815a889a3a447`.

## 7. M033 Design-Freeze Authority

`MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN_FREEZE.md`, freeze commit `ec802143626e850dafe70ce9f0f561fa8516df94`. **M033 DESIGN APPROVED_AND_FROZEN.**

## 8. Implementation Commit

`59fb2ffaa244886990bf68da018c138777a209f0` (`feat: implement M033 Run creation usecase`) — the single commit containing all production, test, and initial governance changes. Verified in this freeze mission to remain byte-for-byte unchanged since that commit.

## 9. Original Finalization Commit

`244864dc7339862ae7f4593a48c8280c4d9d27a0` (`docs: finalize M033 implementation review package`) — narrow, docs-only, recorded the implementation commit's own hash in `PROJECT_CHECKPOINT.md`.

## 10. Initial Independent Implementation-Review Decision

The initial independent hostile implementation review found the production implementation, tests, architecture, and PostgreSQL behavior technically sound, but found the external-review package untrustworthy: **M033 IMPLEMENTATION REQUIRES CORRECTION**, with four findings —

- **M033-IMPLEMENTATION-REVIEW-0001 (MAJOR):** packaged `complete.diff` stale, still showing `M033_IMPLEMENTATION_COMMIT=PENDING`.
- **M033-IMPLEMENTATION-REVIEW-0002 (MAJOR):** packaged `repository-truth.txt` stale, recording pre-push `origin/master`/ahead-by-2 state.
- **M033-IMPLEMENTATION-REVIEW-0003 (MINOR):** narrative test count wrong (reported 16 unit / 24 total; actual 15 unit / 3 contract / 5 integration / 23 total).
- **M033-IMPLEMENTATION-REVIEW-0004 (MINOR):** narrative secret-scan target count wrong (reported 365; actual 366).

## 11. Evidence-Package Correction Commit

`18dabb8966a0b54572aea684e4a5075448052bc0` (`docs: correct M033 implementation evidence counts`) — narrow, docs-only, corrected `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_IMPLEMENTATION.md` and `PROJECT_CHECKPOINT.md` test-count and secret-scan-count narrative; fully regenerated the external-review package (`repository-truth.txt`, `complete.diff`, all evidence files, manifest, ZIP) against the synchronized post-push HEAD. No production source, test, checker, fixture, schema, or migration file touched. No frozen M033 scope/design/freeze document touched.

## 12. Final Independent Implementation Re-Review Decision

The final independent hostile implementation re-review verified all four prior findings fully resolved: `complete.diff` byte-identical to `git diff` against the corrected final HEAD; `repository-truth.txt` synchronized (`HEAD == origin/master`, `0/0`); corrected counts (15 unit / 3 contract / 5 integration / 23 total; 366 secret-scan targets) verified by independent reproduction; 51/51 manifest hashes verified; ZIP integrity validated; all technical regression gates re-confirmed; no new finding raised; no MILESTONE-034 material found. Decision: **M033 IMPLEMENTATION APPROVED FOR OWNER FREEZE.**

## 13. Corrected Evidence-Package Authority

`external-review/MILESTONE-033/MILESTONE-033-18dabb8-external-review.zip`, SHA-256 `04529486cd65b4449faba23ca40cb3ab8d121c46cbea8f3d1953bb7fa20ef922`, 51 manifested files (52 including `manifest.sha256` itself), 51/51 manifest verification PASS.

## 14. Owner Approval

The Owner reviewed the final independent implementation re-review's conclusion and formally authorizes this Implementation Freeze. **M033 IMPLEMENTATION APPROVED_AND_FROZEN.**

## 15. Frozen Implementation Surface

Exactly one production module, `src/empirical_platform/usecases/create_run.py`, exporting `CreateRunCommand` and `CreateRunHandler`; the necessary `usecases/__init__.py` export update; the one narrow `tools/check_architecture.py` line (`ALLOWED["usecases"]` gains `"run"`); two replacement architecture fixtures (`bad_evidence_import.py`, `run/bad_usecases_import.py`) and one removed obsolete fixture (`bad_run_import.py`); 23 focused tests (15 unit, 3 contract, 5 integration).

## 16. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class CreateRunCommand:
    run_governance_id: str
    campaign_governance_id: str
```

Immutable, slots-based, exactly two fields, no defaults, no extra metadata, no command-level business validation.

## 17. Frozen Handler Contract

`CreateRunHandler`, dependencies `RunRepository` and `RuntimeIdentifierGenerator` only — no `CampaignRepository`, no persistence/runtime adapter. Synchronous, structurally conforms to `CommandHandler[CreateRunCommand, DomainIdentity[RunId]]`.

## 18. Campaign-Existence Semantics

No application-level Campaign lookup. No `CampaignRepository` pre-check. The database foreign key (`run.campaign_id → campaign.governance_id`, frozen since M022) remains authoritative. A missing Campaign propagates as the existing `FoundationError` (category `PERSISTENCE`) — no translation, fallback, nullable result, or retry.

## 19. Identity Semantics

Caller supplies the Run governance ID and Campaign governance ID. The handler: constructs `RunId`; generates the runtime ID exactly once; constructs `DomainIdentity[RunId]`; constructs `CampaignId`. The governance ID is never generated by the handler. The runtime ID is never supplied by the command.

## 20. Runtime-Identifier Generation Semantics

Exactly one `RuntimeIdentifierGenerator.generate()` call per `handle()` invocation, verified by dedicated unit tests on both the success and failure paths.

## 21. Exact Creation Sequence

1. Receive command. 2. Construct `RunId`. 3. Generate runtime ID once. 4. Construct `DomainIdentity[RunId]`. 5. Construct `CampaignId`. 6. Construct exactly one `Run`. 7. Call `RunRepository.add()` exactly once. 8. Return `run.identity`. No second `add()`. No retry. No runtime-ID regeneration. No Campaign lookup. No transaction orchestration.

## 22. Return Contract

Returns the exact `DomainIdentity[RunId]` belonging to the constructed `Run` (read off the aggregate itself).

## 23. Duplicate-Identity Behavior

Duplicate governance-ID or runtime-ID persistence collisions propagate as the existing `AggregateAlreadyExists`. No pre-check. No retry. No regenerated runtime ID. Proven against real PostgreSQL for both governance-ID and runtime-ID collisions.

## 24. Missing-Campaign Behavior

See Section 18. Proven against real PostgreSQL: a nonexistent `campaign_governance_id` produces an unmodified `FoundationError` (category `PERSISTENCE`), explicitly not `AggregateAlreadyExists`/`AggregateNotFound`, with confirmation that no Run row was persisted.

## 25. Error Semantics

Transparent propagation of: `RunId` construction `ValueError`; `CampaignId` construction `ValueError`; `RuntimeIdentifierGenerator` failures; `AggregateAlreadyExists`; the missing-Campaign `FoundationError`; arbitrary repository failures. No handler `try`/`except`, translation, wrapper, suppression, status result, nullable result, or generic application error hierarchy.

## 26. Validation Ownership

Command: passive immutable carrier. `RunId`/`CampaignId`: format validation. `Run` aggregate: constructor/structural invariants. `RunRepository`/database: uniqueness and referential integrity. Handler: orchestration only.

## 27. Transaction Non-Ownership

No application transaction orchestration. No `run_composed()`. Exactly one `RunRepository.add()` operation owns persistence atomicity.

## 28. CommandEntryPoint Binding

Direct construction in tests only. No production composition root, registry, command bus, dispatcher, mediator, service locator, or DI framework. Unmodified `CommandEntryPoint`.

## 29. Architecture-Checker Preservation

The authorized change remains exactly: `"run"` added to `ALLOWED["usecases"]`. `FORBIDDEN_IMPORT_PREFIXES["usecases"]` unchanged — no forbidden-prefix weakening. Architecture fixtures continue proving: `usecases` cannot import persistence/runtime, `usecases` cannot import `evidence` or `review`, `run`/domain packages cannot import `usecases`.

## 30. PostgreSQL Success Evidence

Golden-path Run creation proven against real PostgreSQL: correct persisted identity, correct Campaign association, initial state `CREATED`, initial `AggregateVersion.initial()`, empty manifests, empty transition history — reproduced across three independently fresh, disposable `postgres:17` containers with identical results each time.

## 31. PostgreSQL Duplicate-Governance Evidence

Two `CreateRunCommand` invocations with the same `run_governance_id` against the same seeded Campaign: the second raises `AggregateAlreadyExists`. Proven against real PostgreSQL.

## 32. PostgreSQL Duplicate-Runtime Evidence

Two different `run_governance_id` values sharing one `DeterministicRuntimeIdentifierGenerator`-supplied runtime ID: the second collides on the real `pk_run` primary-key constraint, raising `AggregateAlreadyExists`. Proven deterministically feasible and genuinely reproduced against real PostgreSQL.

## 33. PostgreSQL Missing-Campaign Evidence

No Campaign seeded; `campaign_governance_id="CAMP-9999"` triggers the real foreign-key violation, producing an unmodified `FoundationError` (category `PERSISTENCE`) — explicitly not `AggregateAlreadyExists`; confirmed no Run row persisted. Proven against real PostgreSQL.

## 34. Corrected Validation Counts

| Metric | Value |
| --- | --- |
| Unit tests | 15 |
| Contract tests | 3 |
| Integration tests | 5 |
| Total M033 tests | 23 |

## 35. Corrected Secret-Scan Count

366 targets discovered (fresh reproduction; corrects the originally reported 365).

## 36. External-Review Package Verification

Package: `external-review/MILESTONE-033/MILESTONE-033-18dabb8-external-review.zip`. SHA-256: `04529486cd65b4449faba23ca40cb3ab8d121c46cbea8f3d1953bb7fa20ef922`. Manifest: 51 entries, 51/51 verified against a fresh short-path extraction. `complete.diff` verified byte-identical to `git diff 4fc6c041832362af87a6b0e77e661394b7a11eb5..18dabb8966a0b54572aea684e4a5075448052bc0`. `repository-truth.txt` verified synchronized (`HEAD == origin/master`, `0/0`). Packaged source, tests, and governance spot-checked byte-identical to the live repository.

## 37. Changed-File Summary

Cumulative baseline-to-final-HEAD change set (frozen baseline `4fc6c041832362af87a6b0e77e661394b7a11eb5` to `18dabb8966a0b54572aea684e4a5075448052bc0`) is exactly twelve files:

```
A  MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/create_run.py
M  tests/architecture/test_module_boundaries.py
A  tests/contract/test_create_run_handler_contract.py
A  tests/fixtures/illegal_imports/src/empirical_platform/run/bad_usecases_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_evidence_import.py
D  tests/fixtures/illegal_imports/src/empirical_platform/usecases/bad_run_import.py
A  tests/integration/test_m033_create_run_usecase.py
A  tests/unit/test_create_run_usecase.py
M  tools/check_architecture.py
```

No M020-M032 source, test, governance, schema, or migration file touched. No M033 scope/design/freeze document touched.

## 38. No-Scope-Creep Declaration

No Run retrieval, no Run lifecycle transition, no Run save/update, no second Run command, no Campaign mutation/query beyond M030-M032, no `EvidencePackage`/`Review` usecase, no retry/backoff, no composition root, no registry/dispatcher/mediator/service locator/DI framework, no transport/API, no audit integration, no schema/migration change, no MILESTONE-034 work of any kind.

## 39. Owner Freeze Declaration

**M033 IMPLEMENTATION APPROVED_AND_FROZEN.** No further M033 implementation change is permitted without explicit owner re-authorization, documented reason, independent review where material, and a new governance commit.

## 40. Preserved M020-M032 Authority

M020 through M032 remain `APPROVED_AND_FROZEN` at every stage, entirely untouched by this freeze mission.

## 41. Deferred Work

Run retrieval (a future query-side milestone, mirroring M031's role); Run lifecycle transitions (a future command-side milestone, mirroring M032's role); `EvidencePackage`/`Review` creation; retry-on-`OptimisticConcurrencyConflict` policy; composition-root abstraction; transport; audit integration; MILESTONE-034 and beyond.

## 42. Final Status

**M033 IMPLEMENTATION APPROVED_AND_FROZEN.** MILESTONE-033 is now fully frozen at every stage: scope, design, and implementation.

## 43. Next Permitted Action

**MILESTONE-034 SCOPE SELECTION.**
