# MILESTONE-031 - Concrete Application Query Vertical Slice Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW**

This document is implementation evidence. It has not been reviewed, approved, or frozen.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative governance HEAD at implementation start | `9142a1b1880a077e40fe4c5dc440fcaafc9d4091` |
| Implementation commit | `840310c880f4645ab9a1c9e8219d09b4408f9845` |

---

## 3. Frozen Scope/Design Authority

| Document | Commit |
| --- | --- |
| M031 Scope | `68bd50d1d2e2d38abb3e3e389e4a8dde6d996848` |
| M031 Scope Freeze | `b31b664e9395aa0a988ccd1aecc21d6b06436d39` |
| M031 Design | `f73b924d3c36e4796087aa4bb889a8dcde7b548e` |
| M031 Design Freeze | `196150dcde88610c9bc78e6bd0ff40d4d5da9d9b` |

This implementation follows exactly the frozen decisions recorded in `MILESTONE_031_CONCRETE_APPLICATION_QUERY_VERTICAL_SLICE_DESIGN_FREEZE.md` Section 8. No architectural decision was made during implementation that was not already frozen.

---

## 4. Baseline Validation

Run before any production or test file was modified:

| Gate | Result |
| --- | --- |
| `git diff --check` | PASS — clean |
| Architecture checker (`tools/check_architecture.py .`) | PASS — 0 violations |
| Ruff format/check (`src tests tools`) | PASS — 196 files formatted, 0 lint issues |
| mypy strict | PASS — 87 source files |
| Full `pytest` suite, no PostgreSQL opt-in | PASS — **481 passed, 113 skipped**, coverage **82.96%** |
| Build (sdist/wheel) | PASS |

The pre-implementation test count (481 passed, 113 skipped, 82.96% coverage) is byte-for-byte identical to the M030 implementation-freeze evidence recorded in `PROJECT_CHECKPOINT.md` Section 15, confirming the baseline is exactly where M030 left it — no drift.

---

## 5. Exact Implementation

**New file:** `src/empirical_platform/usecases/get_campaign.py` (45 lines).

**Modified file:** `src/empirical_platform/usecases/__init__.py` — extended to export `GetCampaignQuery`, `GetCampaignHandler`, `CampaignSnapshot` alongside the existing M030 exports, mirroring the exact existing pattern.

No other production file was created, modified, or deleted.

---

## 6. Query Contract

```python
@dataclass(frozen=True, slots=True)
class GetCampaignQuery:
    identity: DomainIdentity[CampaignId]
```

Exactly one field, exactly the frozen type. No decomposition, no reconstruction, no runtime-ID generation, no new identifier wrapper — matching Design Freeze Section 8 row 1 exactly.

---

## 7. Snapshot Contract

```python
@dataclass(frozen=True, slots=True)
class CampaignSnapshot:
    identity: DomainIdentity[CampaignId]
    scope_statement: CampaignScopeStatement
    state: CampaignLifecycleState
```

Exactly the three frozen fields, no more, no fewer. `persisted_version` is read from `LoadedAggregate` inside the handler but never carried into this type — matching Design Freeze Section 8 row 4.

---

## 8. Handler Dependency Graph

```python
class GetCampaignHandler:
    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository
```

Single dependency: `CampaignRepository` Protocol, via constructor injection. No `RuntimeIdentifierGenerator`, no persistence adapter, no runtime, no registry, no DI container — matching Design Freeze Section 8 row 3 exactly.

---

## 9. Execution Sequence

```python
def handle(self, query: GetCampaignQuery) -> CampaignSnapshot:
    loaded = self._campaign_repository.get(query.identity)
    return CampaignSnapshot(
        identity=loaded.aggregate.identity,
        scope_statement=loaded.aggregate.scope_statement,
        state=loaded.aggregate.state,
    )
```

Exactly the frozen 7-step sequence (Frozen Implementation Shape Section F of the mission): receive query → read `query.identity` unchanged → call `CampaignRepository.get()` exactly once → receive `LoadedAggregate[Campaign]` → read the loaded Campaign's public `identity`/`scope_statement`/`state` → construct `CampaignSnapshot` → return it. Verified by direct source inspection: exactly one `.get(` call in the entire file (`grep -c` confirms `1`).

---

## 10. Identity Semantics

`query.identity` is passed to `CampaignRepository.get()` unchanged — no reconstruction, no splitting/rejoining, no runtime-ID generation, no governance-ID-only fallback. Proven by `test_exact_query_identity_object_is_passed_to_repository_unchanged`, which asserts `repository.get_calls[0] is query.identity` (object identity, not equality).

---

## 11. Repository Interaction

Exactly one `CampaignRepository.get()` call per invocation; no `add()`, `save()`, or a second `get()`. The unit-test fakes (`_RecordingCampaignRepository`, `_FailingCampaignRepository`) raise `AssertionError` from `add()`/`save()`, making a false-positive pass structurally impossible for the "no write call" claim, mirroring M030's own fake-design discipline.

---

## 12. Not-Found/Error Behavior

No `try`/`except` exists anywhere in `get_campaign.py` (verified: zero matches for `try:`/`except` in the file). `AggregateNotFound` and arbitrary repository exceptions propagate with exact instance identity preserved, proven by `test_aggregate_not_found_propagates_with_identity_preserved` and `test_arbitrary_repository_exception_propagates_with_identity_preserved` (both assert `excinfo.value is exc`), and independently reproduced against real PostgreSQL by `test_missing_full_identity_raises_aggregate_not_found`.

---

## 13. Architecture Impact

**Zero change to `tools/check_architecture.py`.** Verified two ways:

1. `python tools/check_architecture.py .` against the real source tree (now including `get_campaign.py`) passes with 0 violations — the existing `ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}` and `FORBIDDEN_IMPORT_PREFIXES["usecases"]` rules M030 established are sufficient without modification, exactly as the frozen design predicted (Design Freeze Section 8 row 9).
2. `python tools/check_architecture.py tests/fixtures/illegal_imports` still triggers every pre-existing `usecases`-scoped violation (`bad_boto3_import.py`, `bad_persistence_import.py`, `bad_postgres_runtime_import.py`, `bad_psycopg_import.py`, `bad_run_import.py`, `bad_sqlalchemy_import.py`, and `campaign/bad_usecases_import.py`) with no modification — these fixtures are keyed to the `usecases` module name generically, not to any specific file, so they already prove the boundary for the new module with zero duplication.

No new architecture fixture was added, per the mission's explicit "do not duplicate fixtures without added evidence value" instruction — the existing fixtures already provide full coverage.

---

## 14. Tests Added and Reused

**Added:**

- `tests/unit/test_get_campaign_usecase.py` — 17 tests: query immutability/field-preservation, handler `get()`-exactly-once and identity-preservation, no `add()`/`save()`, snapshot field mapping, snapshot immutability/field-exclusivity, aggregate non-mutation, `AggregateNotFound`/arbitrary-exception propagation, `QueryEntryPoint` invocation and rebinding.
- `tests/contract/test_get_campaign_handler_contract.py` — 3 tests: mypy-checked typed-assignment Protocol conformance, `handle()` single-parameter signature, no base-class inheritance.
- `tests/integration/test_m031_get_campaign_usecase.py` — 3 tests: golden path via `QueryEntryPoint` and real `PostgresCampaignRepository`, missing-identity `AggregateNotFound`, no production composition machinery required.

**Reused, unmodified:**

- `tests/architecture/test_module_boundaries.py` (`test_current_source_tree_respects_boundaries`, `test_negative_fixture_detects_illegal_import`) — both pass with the new module in place, no edit needed.
- All 7 M030 `usecases`-scoped illegal-import fixtures.
- `tests/integration/test_m030_create_campaign_usecase.py` — used directly as the identity-producing precondition for the new integration tests via the same `CreateCampaignHandler`/`CommandEntryPoint` path.
- The exact `engine`/`upgraded_schema`/`clean_tables`/`service`/`campaign_repo` fixture chain from `test_m030_create_campaign_usecase.py`, reproduced (not imported, since pytest fixtures are file-scoped) in the new integration test file per the frozen design's evidence strategy (Design Section 18).

**Total new tests: 23** (17 unit + 3 contract + 3 integration).

---

## 15. PostgreSQL Evidence

A disposable `postgres:17` Docker container was used (fresh, not reused from any prior session), following the frozen opt-in convention `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`.

| Gate | Result |
| --- | --- |
| Focused M031 integration tests | PASS — `3 passed` |
| Full integration regression (`tests/integration/`) | PASS — `110 passed, 6 skipped` (was 107 passed at M030 freeze; +3 for M031) |
| Full suite with PostgreSQL opt-in | PASS — `610 passed, 6 skipped`, coverage `91.92%` (was 588 passed at M030 freeze; +22 for M031's 19 non-PostgreSQL + 3 PostgreSQL tests) |
| Migration/schema change | None — verified no `migrations/` file touched |

---

## 16. Hostile Self-Audit

Executed, not merely asserted, against `src/empirical_platform/usecases/get_campaign.py` and the modified `__init__.py`:

- Zero matches for: `shared.persistence`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `PostgresCampaignRepository`, `sqlalchemy`, `psycopg`, `boto3`, `try:`/`except`, `run_composed`, `registry`, `dispatcher`, `mediator`, `service locator`, `.save(`, `.add(`, `.delete(`, `async`, `uuid`, `datetime`, `RuntimeIdentifierGenerator`, `@overload`, `yield`, `callback`, `list`/`filter`/`paginat`/`sort`/`cache`/`authoriz`/`http`/`cli`/`worker`/`queue`/`scheduler`/`bus`/`framework`/`envelope`.
- Exactly one `.get(` call in the entire production module.
- Exactly 5 imports, all resolving to `campaign`/`identifiers` top-level packages (already `ALLOWED["usecases"]`).
- `GetCampaignHandler.__bases__ == (object,)` — no inheritance (verified by test).
- No M032 identifier, module, or reference anywhere in the diff.

---

## 17. Validation Gates

| Gate | Command | Result |
| --- | --- | --- |
| `git diff --check` | `git diff --check` | PASS — clean |
| Architecture checker (real tree) | `python tools/check_architecture.py .` | PASS — 0 violations |
| Architecture checker (fixtures) | `python tools/check_architecture.py tests/fixtures/illegal_imports` | PASS — all pre-existing violations trigger exactly as before |
| Ruff format | `python -m ruff format --check src tests tools` | PASS — 200 files formatted |
| Ruff lint | `python -m ruff check src tests tools` | PASS — 0 issues |
| mypy strict | `python -m mypy` | PASS — **88 source files** (was 87; +1 for `get_campaign.py`) |
| Focused M031 unit+contract tests | `pytest tests/unit/test_get_campaign_usecase.py tests/contract/test_get_campaign_handler_contract.py` | PASS — `19 passed` |
| Architecture tests | `pytest tests/architecture/` | PASS — `2 passed` |
| Full suite, no PostgreSQL opt-in | `pytest -q` | PASS — `500 passed, 116 skipped`, coverage `83.07%` |
| Focused M031 PostgreSQL integration | `pytest tests/integration/test_m031_get_campaign_usecase.py` (opt-in) | PASS — `3 passed` |
| Full integration regression, PostgreSQL | `pytest tests/integration/` (opt-in) | PASS — `110 passed, 6 skipped` |
| Full suite, PostgreSQL opt-in | `pytest -q` (opt-in) | PASS — `610 passed, 6 skipped`, coverage `91.92%` |
| Build | `python -m build` | PASS — sdist and wheel built, `get_campaign.py` present in wheel contents |
| Security — pip-audit | `python -m pip_audit` | PASS — no known vulnerabilities |
| Security — secret scan targets | `python tools/secret_scan_targets.py` | PASS — 344 targets discovered (was 302 at M030 freeze) |

---

## 18. Changed Files

```
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/get_campaign.py
A  tests/unit/test_get_campaign_usecase.py
A  tests/contract/test_get_campaign_handler_contract.py
A  tests/integration/test_m031_get_campaign_usecase.py
```

Plus this implementation document and the `PROJECT_CHECKPOINT.md` governance update (Phase 9), staged separately in the same commit per repository convention.

**No `tools/check_architecture.py` change. No architecture fixture added. No M020-M030 file touched.**

---

## 19. Explicit Non-Changes

- `Campaign`, `CampaignRepository`, `PostgresCampaignRepository` — unmodified.
- `QueryHandler`, `QueryEntryPoint` — unmodified, used exactly as frozen.
- `DomainIdentity`, `CampaignId`, `LoadedAggregate`, `AggregateNotFound` — unmodified.
- Database schema and Alembic migrations — unmodified.
- `src/empirical_platform/usecases/create_campaign.py` (M030) — unmodified.
- All M020-M030 governance documents — unmodified.
- No production composition root, registry, dispatcher, mediator, or DI container introduced anywhere.
- No M032 work of any kind.

---

## 20. Known Limitations

- The typed-conformance tests' "mypy-checked proof" docstring wording documents static evidence that is exercised by the canonical `mypy` gate only for source files; `pyproject.toml`'s `[tool.mypy] packages = ["empirical_platform"]` scope excludes `tests/`, so the test-file type annotations are checked when `mypy` is run without a restricted target (as this implementation's validation gate does — `python -m mypy` with no path argument checks the configured `packages` only). This is the identical, already-acknowledged limitation inherited from M029/M030's own frozen tests, not a new defect introduced here.
- `CampaignSnapshot.state` is compared by value/enum-identity in tests, not independently re-derived from raw persisted SQL rows in the integration tests — this mirrors M030's own evidence style (asserting through the same repository/mapper stack under test) and is consistent with the frozen design's evidence strategy (Section 18).

---

## 21. Remaining Risks

- None beyond what the frozen design already identified and mitigated (Design Freeze Section 6, Design Document Section 24) — this implementation introduces no new architectural risk, since it deviates from the frozen decisions in no respect.

---

## 22. Review Status

`CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW`. Not approved. Not frozen.

---

## 23. Next Permitted Action

**MILESTONE-031 INDEPENDENT IMPLEMENTATION REVIEW.**
