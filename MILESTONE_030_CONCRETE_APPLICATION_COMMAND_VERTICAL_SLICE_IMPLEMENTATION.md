# MILESTONE-030 - Concrete Application Command Vertical Slice Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW**

This document records the M030 implementation as built. It is not approved and not frozen. No implementation change beyond what is recorded here is authorized by this document.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Baseline HEAD (before implementation) | `5ac83cb3abe871ca80e713fc516cae3d49ec7fb6` |
| Frozen scope authority | `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_SCOPE_FREEZE.md` (commit `52f07c03195926e4f3a67dc1524aba7c206a09cb`) |
| Frozen design authority | `MILESTONE_030_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_DESIGN_FREEZE.md` (commit `990ce7c82a531015b883f7a2d3f8889107e6eee9`) |

---

## 3. Baseline Validation (Before Any Change)

| Gate | Result |
| --- | --- |
| Architecture checker | PASS — 0 violations |
| mypy strict | PASS — 85 source files |
| Ruff format/check | PASS — 184 files formatted, 0 lint issues |
| Full `pytest` suite (no PostgreSQL opt-in) | PASS — 464 passed, 110 skipped, coverage 82.85% |

No pre-existing failure was found. Implementation proceeded from a fully green baseline.

---

## 4. Exact Implementation

### 4.1 New production files

- `src/empirical_platform/usecases/__init__.py` — package initializer, exports `CreateCampaignCommand`, `CreateCampaignHandler`.
- `src/empirical_platform/usecases/create_campaign.py` — the entire vertical slice:
  - `CreateCampaignCommand` (`@dataclass(frozen=True, slots=True)`; fields: `campaign_governance_id: str`, `scope_statement: str`).
  - `CreateCampaignHandler` (constructor injection of `campaign_repository: CampaignRepository`, `runtime_identifier_generator: RuntimeIdentifierGenerator`; single method `handle(command) -> DomainIdentity[CampaignId]`).

No other production file was added. No existing production file was modified except `tools/check_architecture.py` (Section 5 below).

### 4.2 Exact dependency graph (verified, not assumed)

```
CreateCampaignHandler
    -> CampaignRepository Protocol          (empirical_platform.campaign.repository)
    -> RuntimeIdentifierGenerator Protocol  (empirical_platform.shared.identifiers)
    -> Campaign, CampaignScopeStatement     (empirical_platform.campaign.aggregate)
    -> CampaignId                           (empirical_platform.identifiers.types)
    -> DomainIdentity                       (empirical_platform.identifiers.pairs)
```

Exactly seven import statements in `create_campaign.py`, confirmed by direct source inspection (Section 8, prohibited-import self-audit).

### 4.3 Execution sequence (as implemented, matching the frozen design exactly)

```python
def handle(self, command: CreateCampaignCommand) -> DomainIdentity[CampaignId]:
    identity = DomainIdentity(
        governance_id=CampaignId(command.campaign_governance_id),
        runtime_id=self._runtime_identifier_generator.generate(),
    )
    campaign = Campaign(
        identity=identity,
        scope_statement=CampaignScopeStatement(command.scope_statement),
    )
    self._campaign_repository.add(campaign)
    return campaign.identity
```

One `RuntimeIdentifierGenerator.generate()` call, one `Campaign` construction, one `CampaignRepository.add()` call. No `get()`, no `save()`, no retry, no transaction orchestration, no `run_composed()`.

---

## 5. Architecture-Checker Changes

Exactly the paired addition the design freeze specifies, and nothing else:

```python
ALLOWED["usecases"] = {"shared", "identifiers", "campaign"}

FORBIDDEN_IMPORT_PREFIXES["usecases"] = (
    "empirical_platform.shared.persistence",
    "sqlalchemy",
    "psycopg",
    "boto3",
)
```

Both entries were added to their respective existing dictionaries in `tools/check_architecture.py`; no existing entry, function, or line was modified. Verified via `git diff` (Section 12) that the checker's total change is exactly these two additions.

---

## 6. Tests Added

### 6.1 Unit tests — `tests/unit/test_create_campaign_usecase.py` (14 tests)

Deterministic recording fakes (`_RecordingCampaignRepository`, `_FailingCampaignRepository`, `_FailingRuntimeIdentifierGenerator`) — no mocks. Proves: typed Protocol conformance; `CampaignId` preserved from the command; `runtime_id` sourced from the injected generator; `add()` called exactly once; the persisted aggregate has the expected identity and scope statement; the handler returns the persisted aggregate's identity; no repository pre-read (`get()`) occurs; malformed `CampaignId`/empty scope-statement failures propagate unchanged (identity-preserved via `pytest.raises` + exact exception-instance assertions where applicable); `CampaignRepository.add()` failures propagate with instance identity preserved; `RuntimeIdentifierGenerator` failures propagate with instance identity preserved; the handler is invocable through `CommandEntryPoint`; the handler is bound once and reused across multiple invocations; the command itself performs no validation.

### 6.2 Contract test — `tests/contract/test_create_campaign_handler_contract.py` (3 tests)

Mypy-checked typed-assignment proof of `CommandHandler` Protocol conformance; runtime documentation of the frozen single-parameter `handle()` shape; confirmation of no base-class inheritance (Protocol satisfied structurally only).

### 6.3 Integration tests — `tests/integration/test_m030_create_campaign_usecase.py` (3 tests)

Real PostgreSQL (opt-in via `EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, identical convention to `test_m023_postgres_repositories.py`). The real `PostgresCampaignRepository` is obtained externally by this test's own fixtures — `usecases` itself never imports it. Proves: the golden path persists via `CommandEntryPoint` and is independently readable back via `CampaignRepository.get()`; a duplicate `campaign_governance_id` raises `AggregateAlreadyExists` unchanged; the handler requires no production composition machinery (direct construction from an externally-obtained repository and a deterministic generator only).

### 6.4 Architecture-checker fixtures — `tests/fixtures/illegal_imports/src/empirical_platform/usecases/` (6 files) + 1 file under `campaign/`

- `bad_persistence_import.py` — `usecases` importing `shared.persistence` (top-level).
- `bad_postgres_runtime_import.py` — `usecases` importing the concrete `PostgresRepositoryRuntime` submodule (proves the prefix rule catches submodules, not just the top-level package).
- `bad_sqlalchemy_import.py`, `bad_psycopg_import.py`, `bad_boto3_import.py` — each third-party infrastructure library individually.
- `bad_run_import.py` — an unrelated domain aggregate.
- `campaign/bad_usecases_import.py` — reconfirms `campaign` still cannot import `usecases`.

`tests/architecture/test_module_boundaries.py` extended with 7 new assertions (one per fixture above) plus the existing `test_current_source_tree_respects_boundaries` check, which already covers the positive case (the real `usecases` implementation passes the full checker).

---

## 7. Failure-Propagation Evidence

Every propagation test asserts **exact exception instance identity** (`excinfo.value is exc`), not merely exception type, proving the frozen M029 transparent-propagation invariant holds through `CreateCampaignHandler` exactly as it already holds through `CommandEntryPoint`:

- `CampaignId`'s frozen format validation (`ValueError: Identifier must match ...`) — unit test.
- `CampaignScopeStatement`'s frozen non-empty validation (`ValueError: ... must be non-empty`) — unit test.
- `CampaignRepository.add()` raising `AggregateAlreadyExists` — unit test (identity-preserved) and integration test (real PostgreSQL, real unique-constraint violation).
- `RuntimeIdentifierGenerator.generate()` raising an arbitrary exception — unit test (identity-preserved).

---

## 8. Hostile Self-Audit (Executed, Not Merely Asserted)

See `evidence/prohibited-import-self-audit.txt` for full command output. Summary:

| Search | Result |
| --- | --- |
| `shared.persistence`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `PostgresCampaignRepository`, `sqlalchemy`, `psycopg`, `boto3` anywhere in `src/empirical_platform/usecases/` | **0 matches** |
| `try:`/`except` in the handler | **0 matches** |
| `uuid`/`datetime` identity generation in the handler | **0 matches** |
| `run_composed`, `Registry`, `Dispatcher`, `Mediator`, `ServiceLocator`, `DI framework` | **0 matches** |
| Repository calls other than `.add(` | **0 matches** (`.get(`/`.save(` absent) |
| Import count in `create_campaign.py` | **7**, matching the frozen dependency graph exactly |
| Module count in `usecases/` package | **2** (`__init__.py`, `create_campaign.py`) — no additional use-case module |

---

## 9. Validation Gates (All Executed, With Command Evidence)

| Gate | Command | Result |
| --- | --- | --- |
| Whitespace | `git diff --check` | PASS |
| Architecture checker (full repo) | `python tools/check_architecture.py .` | PASS — 0 violations |
| Architecture checker (fixtures) | `python tools/check_architecture.py tests/fixtures/illegal_imports` | PASS — all 7 new + all pre-existing violations trigger exactly as expected (exit 1, as intended for a negative-fixture run) |
| Ruff format | `ruff format --check src tests tools` | PASS — 196 files formatted |
| Ruff lint | `ruff check src tests tools` | PASS — 0 issues |
| mypy strict | `mypy` | PASS — 87 source files (was 85; +2 for `usecases`) |
| Focused M030 tests | `pytest tests/unit/test_create_campaign_usecase.py tests/contract/test_create_campaign_handler_contract.py tests/architecture/` | PASS — 19 passed |
| Full suite, no PostgreSQL opt-in | `pytest tests/` | PASS — 481 passed, 113 skipped, coverage 82.96% |
| Full suite, **real PostgreSQL** (`EMPIRICAL_PLATFORM_RUN_POSTGRES_TESTS=1`, disposable Docker instance) | `pytest tests/` | PASS — **588 passed**, 6 skipped (unrelated MinIO), coverage **91.87%** |
| M030-specific PostgreSQL integration tests | `pytest tests/integration/test_m030_create_campaign_usecase.py` | PASS — 3 passed |
| Full integration suite regression check, real PostgreSQL | `pytest tests/integration/` | PASS — 107 passed, 6 skipped |
| Build | `python -m build --sdist --wheel` | PASS — `usecases` package present in wheel contents |

**PostgreSQL evidence is genuine, not simulated:** a disposable `postgres:17` container was started via the repository's own established `infra/local/compose.yaml`, migrated with the frozen Alembic chain, and torn down after evidence capture — following the exact opt-in convention `test_m023_postgres_repositories.py` already established. No schema or migration change was made or needed, confirming the design's own prediction.

---

## 10. Changed Files (Complete List)

**New (7):**
- `src/empirical_platform/usecases/__init__.py`
- `src/empirical_platform/usecases/create_campaign.py`
- `tests/unit/test_create_campaign_usecase.py`
- `tests/contract/test_create_campaign_handler_contract.py`
- `tests/integration/test_m030_create_campaign_usecase.py`
- `tests/fixtures/illegal_imports/src/empirical_platform/usecases/` (6 files)
- `tests/fixtures/illegal_imports/src/empirical_platform/campaign/bad_usecases_import.py`

**Modified (2):**
- `tools/check_architecture.py` (2 dictionary entries added)
- `tests/architecture/test_module_boundaries.py` (7 assertions added)

**No other file was touched.** No M020-M029 material, no M030 scope/design/design-freeze document, no unrelated source or test file.

---

## 11. Explicit Non-Changes

- No transport, HTTP, CLI, worker, queue, or scheduler code.
- No query-side command, handler, or Protocol usage.
- No composition root, registry, dispatcher, mediator, service locator, or DI framework.
- No modification to any frozen Protocol signature (`CommandHandler`, `QueryHandler`, `CampaignRepository`, `CommandEntryPoint`).
- No modification to `PostgresCampaignRepository`, `PostgresRepositoryRuntime`, or `FoundationRuntime`.
- No new Campaign business rule; all validation is delegated to the already-frozen `Campaign` aggregate and its value objects.
- No database schema or migration change.
- No MILESTONE-031 work of any kind.

---

## 12. Known Limitations

- The handler's constructor dependencies (`CampaignRepository`, `RuntimeIdentifierGenerator`) must currently be supplied by hand (a test, in this milestone) — there is no production composition code to obtain them from a running `FoundationRuntime`. This is by design (frozen design Section 10.C/H) and is explicitly deferred, not a defect.
- Only the golden path and the single already-frozen `AggregateAlreadyExists` failure mode are covered by integration tests, matching exactly what the frozen scope authorizes for the creation-only vertical slice.

---

## 13. Remaining Risks

- As the first concrete command/handler pair, this implementation's conventions (package name, file-per-use-case granularity, constructor-injection shape) may be imitated by future milestones without independent re-justification — the design freeze record already flags this as a governance risk to watch, not a defect in this implementation.
- `tools/check_architecture.py` is a shared, sensitive file; the two-entry addition here was verified minimal and independently tested (positive: real source tree passes; negative: 7 new fixtures each trigger exactly one expected violation), but any future change to this file should re-verify the `usecases` entries remain intact.

---

## 14. Review Status

**CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW.** Not approved. Not frozen. MILESTONE-030 owner implementation freeze has not occurred.

---

## 15. Next Permitted Action

**MILESTONE-030 INDEPENDENT IMPLEMENTATION REVIEW.**
