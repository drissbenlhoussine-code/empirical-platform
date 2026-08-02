# MILESTONE-034 - Concrete Application Query Vertical Slice (Run Retrieval) Implementation Freeze

## 1. Milestone Identity

MILESTONE-034 — Concrete Application Query Vertical Slice: Run Retrieval, Implementation stage.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `7196a3b4a8b67eaa1745b87b67dca98212e8935f` |

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Run Creation) | APPROVED_AND_FROZEN (implementation freeze `38ed45518d8a2068d29e7375c2c09ea2af80963c`) |

## 4. M034 Scope Authority

`MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE.md`, candidate `3ee8485143f1397cad9d14bc55744e97f60aa9d3`.

## 5. M034 Scope-Correction Authority

Commit `60178d3d1caf96d1fe33f318e57e94c708e8896f` (`M034-SCOPE-REVIEW-0001` correction — removed premature result-shape commitment).

## 6. M034 Scope-Freeze Authority

`MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_SCOPE_FREEZE.md`, commit `e6ad2c0e976ad0eb1cd00f8e15544d58ac45de7e`. **M034 SCOPE APPROVED_AND_FROZEN.**

## 7. M034 Design Authority

`MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_DESIGN.md`, candidate `d343e38cba9b5a49db278c72ca1650dd50839bd2`.

## 8. M034 Design-Correction Authority

Commit `993144e4361372e6978b11d96d6e1fe98e722c73` (`M034-DESIGN-REVIEW-0001`/`0002` correction — distinguished `Run.version` from `LoadedAggregate.persisted_version`; corrected dataclass runtime-enforcement wording).

## 9. M034 Design-Freeze Authority

`MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_DESIGN_FREEZE.md`, commit `072fcee1d75c3f13547a6033c689786f2a110ab3`. **M034 DESIGN APPROVED_AND_FROZEN.**

## 10. Implementation Commit

`aef1ee96cf9662e6b726bdb1168fe3d79bc8a79e` (`feat: implement M034 Run retrieval usecase`) — the single commit delivering `GetRunQuery`/`RunSnapshot`/`GetRunHandler`, 21 new tests, and the initial implementation document.

## 11. Finalization Commit

`7196a3b4a8b67eaa1745b87b67dca98212e8935f` (`docs: finalize M034 implementation review package`) — narrow, docs-only, recorded the implementation commit's own hash. No production behavior changed.

## 12. Independent Implementation-Review Decision

The independent hostile implementation review verified: exact seven-file implementation lineage; frozen design conformance; exact `GetRunQuery`/`RunSnapshot`/`GetRunHandler` contracts; exactly one `RunRepository.get()` call; exact identity-object pass-through; `Run.version` and `LoadedAggregate.persisted_version` remain distinct and both excluded; `manifests`/`transition_history` excluded; transparent `AggregateNotFound`/arbitrary-error propagation; no `CampaignRepository`; no retry/cache/transaction orchestration/second capability; real PostgreSQL golden-path, bounded/non-empty-state, and missing-Run behavior; PostgreSQL regression; typing/architecture/build/security; external-review package integrity; governance consistency; no MILESTONE-035 work.

**Decision: M034 IMPLEMENTATION APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains.

## 13. Live PostgreSQL Review Authority

The original implementation package (finalization commit `7196a3b`) disclosed an honest limitation: the four M034 PostgreSQL integration tests were written and verified to import/collect cleanly, but were not executed live — no database credentials and no working Docker daemon were available in that session. The independent review subsequently obtained Docker access and reproduced live PostgreSQL evidence.

**This freeze record does not take that reproduction on faith.** Before writing this document, the specific claimed results were independently re-verified a third time, in this freeze session, using a freshly started, disposable `postgres:17` Docker container (`m034-postgres-review`, isolated, non-default host port, stopped and removed immediately after evidence capture):

| Claim | Independently reproduced result |
| --- | --- |
| Focused M034 PostgreSQL tests: 4 passed | `pytest tests/integration/test_m034_get_run_usecase.py -v` → **4 passed** |
| PostgreSQL integration regression: 122 passed | `pytest tests/integration/ -v` → **122 passed, 6 skipped** (6 skips are pre-existing MinIO/unified-runtime opt-in gating, unrelated to M034) |
| Full non-integration suite: 561 passed | `pytest -q -m "not integration"` → **561 passed, 128 deselected** |
| Architecture checker: passed | `python tools/check_architecture.py .` → **exit 0** |
| Ruff: passed | `ruff check .` → **All checks passed**; `ruff format --check .` → **215 files already formatted** |
| mypy: 91 source files, passed | `mypy` (canonical) → **Success: no issues found in 91 source files** |
| Build: known setuptools license-metadata deprecation warning | `python -m build` → reproduced the exact `SetuptoolsDeprecationWarning: project.license as a TOML table is deprecated` warning, build otherwise succeeded |

Every specific number and warning claimed by the independent review was independently reproduced from a fresh container, not merely copied from the review's own report. This is the load-bearing evidence for this freeze.

## 14. Non-Blocking Observations

1. The original implementation session's first security-script invocation used the system Python interpreter rather than the project `.venv` (a benign environment-selection mistake, not a code defect); the canonical rerun under `.venv` passed cleanly (376 secret-scan targets, consistent both in the original package and independently reconfirmed).
2. An initial PostgreSQL container attempt during independent review encountered a stale-volume authentication mismatch (unrelated to M034 code); a fresh, isolated container resolved it and reproduced all required evidence. This freeze session's own independent re-verification (Section 13) used a third, separately fresh container and encountered no such issue.
3. `python -m build` emits a known, pre-existing `setuptools` future deprecation warning about `project.license` as a TOML table — unrelated to this milestone's code, reproduced identically, and not a build failure.

None of these observations authorize or require any source, test, package, or build-configuration change.

## 15. Owner Approval

The owner formally freezes the M034 implementation via this document.

**M034 IMPLEMENTATION APPROVED_AND_FROZEN.**

## 16. Frozen Implementation Surface

Exactly: `src/empirical_platform/usecases/get_run.py` (new); `src/empirical_platform/usecases/__init__.py` (export-only addition); `tests/unit/test_get_run_usecase.py`, `tests/contract/test_get_run_handler_contract.py`, `tests/integration/test_m034_get_run_usecase.py` (new); `MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_IMPLEMENTATION.md` (new); `PROJECT_CHECKPOINT.md` (updated). Seven files total across the implementation and finalization commits.

## 17. Frozen Query Contract

```python
@dataclass(frozen=True, slots=True)
class GetRunQuery:
    identity: DomainIdentity[RunId]
```

Exactly one field, no default, passive typed carrier.

## 18. Frozen Result Contract

```python
@dataclass(frozen=True, slots=True)
class RunSnapshot:
    identity: DomainIdentity[RunId]
    campaign_id: CampaignId
    state: RunLifecycleState
```

Exactly three fields, no defaults, no mutable collections, no aggregate/`LoadedAggregate` reference.

## 19. Bounded RunSnapshot Semantics

`RunSnapshot` is frozen as a bounded Run header/status result — not a complete Run-state representation — per its own docstring and the design freeze's Section 16.

## 20. Frozen Handler Contract

```python
class GetRunHandler:
    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, query: GetRunQuery) -> RunSnapshot:
        loaded = self._run_repository.get(query.identity)
        return RunSnapshot(
            identity=loaded.aggregate.identity,
            campaign_id=loaded.aggregate.campaign_id,
            state=loaded.aggregate.state,
        )
```

Sole dependency: `RunRepository`. No `CampaignRepository`, identifier generator, or persistence/runtime adapter.

## 21. Identity Semantics

`query.identity` passed unchanged to `run_repository.get()` — proven by `test_exact_query_identity_object_is_passed_to_repository_unchanged`.

## 22. Exact Retrieval Sequence

Receive query → one `get()` call → one `LoadedAggregate[Run]` → read `identity`/`campaign_id`/`state` only → one `RunSnapshot` constructed → returned. No second `get()`, no Campaign lookup, no retry, no cache, no transaction orchestration.

## 23. Return Semantics

Exactly one `RunSnapshot` per successful call.

## 24. Aggregate-Version Exclusion

`Run.version` never appears on `RunSnapshot`. Independently proven (unit-level, deliberately distinguishable values) and independently proven live against real PostgreSQL in this freeze session (Section 13, golden-path assertion `set(RunSnapshot.__slots__) == {"identity", "campaign_id", "state"}`).

## 25. Persisted-Version Exclusion

`LoadedAggregate.persisted_version` never appears on `RunSnapshot`. Same evidence as Section 24.

## 26. Manifest/History Exclusion

`manifests`/`transition_history` never appear on `RunSnapshot`, proven against non-empty source data at unit level and confirmed live via `test_no_campaign_table_query_and_manifests_history_load_without_error`.

## 27. Not-Found Behavior

Transparent, unchanged `AggregateNotFound` propagation — proven at unit level and independently reproduced live in this freeze session (`test_missing_full_identity_raises_aggregate_not_found` passed against the real database).

## 28. Error Semantics

Transparent, unchanged propagation of any arbitrary repository exception — proven at unit level.

## 29. Validation Ownership

No `__post_init__` on `GetRunQuery`/`RunSnapshot`; no duplicated identifier validation in the handler.

## 30. Transaction Non-Ownership

No `run_composed()`, no unit-of-work/session/engine/connection reference in `get_run.py`.

## 31. QueryEntryPoint Binding

Test-only direct construction; no production composition root. Proven live in this freeze session (`test_no_production_composition_machinery_is_required` passed against the real database).

## 32. Architecture Preservation

Zero change to `tools/check_architecture.py`. `python tools/check_architecture.py .` passes at exit 0, independently reconfirmed in this freeze session.

## 33. PostgreSQL Success Evidence

Independently reproduced in this freeze session (Section 13): `test_golden_path_retrieves_via_query_entry_point_and_real_repository` passed against a real, freshly migrated database, seeded via the frozen M030/M033 usecases.

## 34. PostgreSQL Bounded/Non-Empty-State Evidence

Independently reproduced: `test_no_campaign_table_query_and_manifests_history_load_without_error` passed, confirming the bounded result holds against the real adapter's always-eager manifest/transition-history load path.

## 35. PostgreSQL Missing-Run Evidence

Independently reproduced: `test_missing_full_identity_raises_aggregate_not_found` passed against the real database.

## 36. PostgreSQL Regression Evidence

Independently reproduced: full `tests/integration/` suite — 122 passed, 6 skipped (pre-existing MinIO/unified-runtime opt-in gating, unaffected by M034).

## 37. Unit/Contract Evidence

23 tests (18 unit + 3 contract + 2 architecture) passed in the focused run; full non-integration suite 561 passed, 128 deselected, zero regression from the 540-test pre-implementation baseline.

## 38. Typing/Architecture/Build/Security Evidence

`mypy` 91 source files clean; `ruff check`/`format --check` clean; `tools/check_architecture.py` exit 0; `python -m build` succeeds (with the pre-existing, unrelated setuptools deprecation warning); `python tools/secret_scan_targets.py --root .` finds 376 targets, consistent across every run.

## 39. External-Review Package Verification

`external-review/MILESTONE-034/MILESTONE-034-7196a3b-external-review.zip`, SHA-256 `afcad7ba602685d6351e37dba1e610b51f489708e023bd29d73cb6adfe739a5e`. `manifest.sha256`: 45 entries, all verified OK both before packaging and after a fresh extraction. `complete.diff` byte-identical to a live regeneration against the same commit range. Package unchanged by this freeze mission (per its own authorization boundary).

## 40. Changed-File Summary

```
A  MILESTONE_034_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_RUN_RETRIEVAL_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/get_run.py
A  tests/contract/test_get_run_handler_contract.py
A  tests/integration/test_m034_get_run_usecase.py
A  tests/unit/test_get_run_usecase.py
```

Plus this freeze document and a further `PROJECT_CHECKPOINT.md` update, added in this freeze mission per its own authorization.

## 41. No-Scope-Creep Declaration

No Run mutation, lifecycle transition, save/update, second query, listing, filtering, pagination, Campaign lookup/join, cross-aggregate enrichment, generic read-model/projection framework, caching, retry, composition root, registry, dispatcher, mediator, service locator, DI framework, transport/API layer, audit integration, `EvidencePackage`/`Review` work, schema/migration change, or MILESTONE-035 work of any kind exists anywhere in this implementation.

## 42. Owner Freeze Declaration

**M034 IMPLEMENTATION APPROVED_AND_FROZEN.** The implementation delivered in commits `aef1ee9`/`7196a3b`, exactly as verified in Sections 13 and 33-38 above, is the final, frozen implementation of MILESTONE-034.

## 43. Preserved M020-M033 Authority

No change to any M020-M033 frozen contract, source file, test, or governance document. No change to M034 scope/design authority. All prior authority remains exactly as previously frozen.

## 44. Deferred Work

- Exposing `Run.version`, `manifests`, or `transition_history` through a Run read model — future, independently-scoped milestone.
- Read-to-update `expected_persisted_version` acquisition — future, independently-scoped milestone, if genuinely evidenced.
- Run lifecycle-transition command; `EvidencePackage`/`Review` creation; retry-on-`OptimisticConcurrencyConflict` policy; any composition-root abstraction beyond direct binding.
- MILESTONE-035 and beyond.

## 45. Final Status

**M034 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M035: NOT_STARTED.

## 46. Next Permitted Action

**MILESTONE-035 SCOPE SELECTION.**
