# MILESTONE-032 - Concrete Application Command Vertical Slice (Campaign Lifecycle Transition) Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW**

This document is implementation evidence. It has not been reviewed, approved, or frozen.

---

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| Authoritative governance HEAD at implementation start | `06f1284c20a34e06e01fa523426ca8e9df64819e` |
| Implementation commit | `2901a6e7f6c305a86a8ba7635a436c9299433519` |

---

## 3. Frozen Scope/Design Authority

| Document | Commit |
| --- | --- |
| M032 Scope | `5ea62d02d65945f0976e42b8c011217d895723e4` |
| M032 Scope Freeze | `b18878a514694d6663026e11d98859023c04a136` |
| M032 Design | `50f2cd829af2e10799ab3581b4c2e56e9e04d401` |
| M032 Design Correction | `2f48b1e4af1b039c3b2a7e3598f85e63e007b216` |
| M032 Design Freeze | `14204e4c24024fa7e1d56fbf49dccef0a1fa6a58` |

This implementation follows exactly the frozen decisions recorded in `MILESTONE_032_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_CAMPAIGN_LIFECYCLE_TRANSITION_DESIGN_FREEZE.md`. No architectural decision was made during implementation that was not already frozen.

---

## 4. Baseline Validation

Run before any production or test file was modified:

| Gate | Result |
| --- | --- |
| `git diff --check` | PASS — clean |
| Architecture checker (`tools/check_architecture.py .`) | PASS — 0 violations |
| Ruff format/check (`src tests tools`) | PASS — 200 files formatted, 0 lint issues |
| mypy strict | PASS — 88 source files |
| Full `pytest` suite, no PostgreSQL opt-in | PASS — **500 passed, 116 skipped**, coverage **83.07%** |
| Build (sdist/wheel) | PASS |

The pre-implementation test count (500 passed, 116 skipped, 83.07% coverage) is byte-for-byte identical to the M031 implementation-freeze evidence recorded in `PROJECT_CHECKPOINT.md`, confirming the baseline is exactly where M031 left it — no drift.

---

## 5. Implementation Map

| Category | Files |
| --- | --- |
| Production (new) | `src/empirical_platform/usecases/prepare_campaign_for_authorization.py` |
| Production (modified, exports only) | `src/empirical_platform/usecases/__init__.py` |
| Unit tests (new) | `tests/unit/test_prepare_campaign_for_authorization_usecase.py` |
| Contract tests (new) | `tests/contract/test_prepare_campaign_for_authorization_handler_contract.py` |
| Integration tests (new) | `tests/integration/test_m032_prepare_campaign_for_authorization_usecase.py` |
| Architecture evidence | none needed — existing M030 fixtures already prove the `usecases` boundary generically |
| Governance | this implementation document, `PROJECT_CHECKPOINT.md` |
| Explicit non-changes | `tools/check_architecture.py`, all schemas/migrations, `Campaign`, `CampaignRepository`, `PostgresCampaignRepository`, `CommandHandler`, `CommandEntryPoint`, M030/M031 source, M020-M031 governance |

---

## 6. Production Implementation

**New module:** `src/empirical_platform/usecases/prepare_campaign_for_authorization.py` (43 lines) — `PrepareCampaignForAuthorizationCommand`, `PrepareCampaignForAuthorizationHandler`.

**Modified file:** `src/empirical_platform/usecases/__init__.py` — export-only extension, mirroring the existing M030/M031 pattern exactly.

No other production file was created, modified, or deleted.

---

## 7. Command Contract

```python
@dataclass(frozen=True, slots=True)
class PrepareCampaignForAuthorizationCommand:
    identity: DomainIdentity[CampaignId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Exactly the six frozen fields, exact types, exact defaults. No reconstruction, no `Clock` injection, no transport/tracing/retry/idempotency metadata.

---

## 8. Handler Contract

```python
class PrepareCampaignForAuthorizationHandler:
    __slots__ = ("_campaign_repository",)

    def __init__(self, *, campaign_repository: CampaignRepository) -> None:
        self._campaign_repository = campaign_repository

    def handle(self, command: PrepareCampaignForAuthorizationCommand) -> SaveResult:
        loaded = self._campaign_repository.get(command.identity)
        campaign = loaded.aggregate
        campaign.prepare_for_authorization(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._campaign_repository.save(
            campaign, expected_persisted_version=command.expected_persisted_version
        )
```

Single dependency (`CampaignRepository`), constructor injection. No inheritance, no `try`/`except`, synchronous only.

---

## 9. Identity Semantics

`command.identity` — the full `DomainIdentity[CampaignId]` object — is passed to `CampaignRepository.get()` unchanged. Proven by object-identity assertion (`repository.get_calls[0] is command.identity`, not merely equality) in `test_get_is_called_exactly_once_with_exact_identity`.

---

## 10. Expected-Version Semantics

`command.expected_persisted_version` is passed unchanged to `save()`, never derived from or compared against `loaded.persisted_version`. Verified explicitly by `test_save_receives_command_version_not_loaded_persisted_version`, which constructs a `LoadedAggregate` with a *different* `persisted_version` than the command's `expected_persisted_version` and asserts the command's value (by object identity) reaches `save()` unchanged.

---

## 11. Load-Mutate-Save Sequence

Exactly one `get()`, one `prepare_for_authorization()` mutation, one `save()` — verified by direct grep (`.get(` count 1, `prepare_for_authorization(` count 1, `.save(` count 1 in the entire production module) and by unit tests asserting exact call counts. `save()` is never called if the domain mutation raises (`test_domain_invalid_transition_propagates_and_save_never_called`).

---

## 12. Return Contract

The exact `SaveResult` object produced by `save()` is returned unchanged — proven by object-identity assertion (`result is save_result`) in `test_returned_object_is_the_exact_save_result`.

---

## 13. Error and Conflict Behavior

No `try`/`except` anywhere in the module (verified: zero matches). `AggregateNotFound` from `get()`, arbitrary `get()`/`save()` exceptions, and the aggregate's own domain `ValueError` all propagate with exact instance identity preserved — verified by unit tests and independently reproduced against real PostgreSQL (`OptimisticConcurrencyConflict` with exact expected/actual version metadata).

---

## 14. Validation Ownership

Zero validation logic in the command or handler — verified: `test_command_construction_performs_no_business_validation` confirms an empty-string `actor` is accepted at construction (no duplicated check), relying entirely on `Campaign.prepare_for_authorization()`'s own frozen validation.

---

## 15. Transaction Non-Ownership

No `run_composed()`, no transaction manager, no session/connection/engine import anywhere in the production module (verified by the same prohibited-pattern grep sweep, Section 21). `get()` and `save()` retain their own independent, unmodified `unit_of_work()` behavior.

---

## 16. Architecture Impact

**Zero change to `tools/check_architecture.py`.** Verified two ways:

1. `python tools/check_architecture.py .` against the real source tree (now including the new module) passes with 0 violations.
2. `python tools/check_architecture.py tests/fixtures/illegal_imports` still triggers every pre-existing `usecases`-scoped violation (7 fixtures) with no modification — these fixtures are keyed to the `usecases` module name generically, so they already prove the boundary for the new module.

No new architecture fixture was added — none was needed.

---

## 17. Tests Added and Reused

**Added:**

- `tests/unit/test_prepare_campaign_for_authorization_usecase.py` — 19 tests: command field preservation/immutability/no-extra-fields, handler `get()`-exactly-once with exact identity, `prepare_for_authorization()` called with exact arguments, `save()` called with the mutated aggregate and the command's own (not the loaded) version, no `add()`, no second `get()`/`save()`, exact `SaveResult` returned, `CommandEntryPoint` invocation and multi-invocation reuse, domain-invalid-transition propagation with `save()` suppressed, `get()`/`save()` failure propagation with exact instance identity preserved.
- `tests/contract/test_prepare_campaign_for_authorization_handler_contract.py` — 3 tests: mypy-checked typed-assignment Protocol conformance, `handle()` single-parameter signature, no base-class inheritance.
- `tests/integration/test_m032_prepare_campaign_for_authorization_usecase.py` — 3 tests: golden path via `CommandEntryPoint` and real `PostgresCampaignRepository`, deterministic `OptimisticConcurrencyConflict` reproduction using `revise_scope_statement()` as the interfering write (frozen design Section 25), domain-invalid-transition with no further persistence.

**Reused, unmodified:**

- `tests/architecture/test_module_boundaries.py` — passes with the new module in place, no edit needed.
- All 7 M030 `usecases`-scoped illegal-import fixtures.
- `tests/integration/test_m030_create_campaign_usecase.py`'s `CreateCampaignHandler` — used directly as the precondition-Campaign-producing step for the new integration tests.
- The exact `engine`/`upgraded_schema`/`clean_tables`/`service`/`campaign_repo` fixture chain established by `test_m030_create_campaign_usecase.py`/`test_m031_get_campaign_usecase.py`, reproduced (pytest fixtures are file-scoped) in the new integration test file.

**Total new tests: 25** (19 unit + 3 contract + 3 integration).

---

## 18. PostgreSQL Successful-Transition Evidence

`test_golden_path_transitions_campaign_via_command_entry_point_and_real_repository`: persists a Campaign via M030's `CreateCampaignHandler` (`DRAFT`, version 0); invokes `PrepareCampaignForAuthorizationCommand` through `CommandEntryPoint` with `expected_persisted_version=AggregateVersion(0)`; verifies the returned `SaveResult.operation == SaveOperation.UPDATED` and `SaveResult.persisted_version == AggregateVersion(1)`; independently reloads via `campaign_repository.get()` and verifies `state == CampaignLifecycleState.READY_FOR_AUTHORIZATION`, the persisted version, and the transition record's `actor`/`correlation_id`/`reason`. **PASS.**

---

## 19. PostgreSQL Conflict Evidence

`test_stale_expected_version_raises_optimistic_concurrency_conflict`: persists a Campaign (`DRAFT`, version 0); independently loads the same identity a second time and calls `Campaign.revise_scope_statement(...)` on that separate in-memory object, then persists it with `expected_persisted_version=AggregateVersion(0)` — advancing the row to version 1 while leaving it `DRAFT` (verified by an explicit reload assertion before invoking the command under test); invokes `PrepareCampaignForAuthorizationCommand` through `CommandEntryPoint` with the now-stale `expected_persisted_version=AggregateVersion(0)`; verifies `OptimisticConcurrencyConflict` is raised with `expected_persisted_version == AggregateVersion(0)` and `actual_persisted_version == AggregateVersion(1)`; reloads and confirms the database still reflects only the interfering write (`DRAFT`, revised scope statement, version 1) — no partial or unintended write occurred. **PASS.** This is the exact frozen mechanism from Design Freeze Section 25, confirming the design correction (M032-DESIGN-REVIEW-0001) resolved a genuine, reproducible gap, not merely a documentation concern.

---

## 20. PostgreSQL Invalid-Transition Evidence

`test_invalid_transition_raises_domain_error_without_persisting`: invokes the command successfully once (`DRAFT → READY_FOR_AUTHORIZATION`, version 0→1); invokes it again against the same identity; verifies the aggregate's own `ValueError` ("cannot transition from...") propagates unchanged; reloads and confirms the database still reflects only the first, successful transition (`READY_FOR_AUTHORIZATION`, version 1) — no further write occurred. **PASS.**

No migration or schema change was required or introduced for any scenario.

---

## 21. Hostile Self-Audit

Executed, not merely asserted, against `src/empirical_platform/usecases/prepare_campaign_for_authorization.py` and the modified `__init__.py`:

- Zero matches for: `shared.persistence`, `PostgresRepositoryRuntime`, `FoundationRuntime`, `PostgresCampaignRepository`, `sqlalchemy`, `psycopg`, `boto3`, `try:`/`except`, `run_composed`, `registry`, `dispatcher`, `mediator`, `service locator`, `.add(`, `.delete(`, `revise_scope_statement`, `record_authorization`, `.activate(`, `.suspend(`, `.resume(`, `.complete(`, `.cancel(`.
- Exactly one `.get(`, one `.save(`, one `prepare_for_authorization(` call in the entire production module.
- `loaded.persisted_version` is never referenced anywhere in the module — confirmed via grep for `loaded` (only `loaded = ...get(...)` and `loaded.aggregate` appear).
- Exactly 5 first-party imports, all resolving to `campaign`/`identifiers`/`shared` top-level packages already `ALLOWED["usecases"]`.
- `PrepareCampaignForAuthorizationHandler.__bases__ == (object,)` — no inheritance (verified by test).
- No M033 identifier, module, or reference anywhere in the diff.

---

## 22. Validation Gates

| Gate | Command | Result |
| --- | --- | --- |
| `git diff --check` | `git diff --check` | PASS — clean |
| Architecture checker (real tree) | `python tools/check_architecture.py .` | PASS — 0 violations |
| Architecture checker (fixtures) | `python tools/check_architecture.py tests/fixtures/illegal_imports` | PASS — all pre-existing violations trigger exactly as before |
| Ruff format | `python -m ruff format --check src tests tools` | PASS — 204 files formatted |
| Ruff lint | `python -m ruff check src tests tools` | PASS — 0 issues |
| mypy strict | `python -m mypy` | PASS — **89 source files** (was 88; +1) |
| Focused M032 unit+contract tests | `pytest tests/unit/test_prepare_campaign_for_authorization_usecase.py tests/contract/test_prepare_campaign_for_authorization_handler_contract.py` | PASS — `22 passed` |
| Full suite, no PostgreSQL opt-in | `pytest -q` | PASS — `522 passed, 119 skipped`, coverage `83.18%` |
| Focused M032 PostgreSQL integration | `pytest tests/integration/test_m032_prepare_campaign_for_authorization_usecase.py` (opt-in) | PASS — `3 passed` |
| Full integration regression, PostgreSQL | `pytest tests/integration/` (opt-in) | PASS — `113 passed, 6 skipped` |
| Full suite, PostgreSQL opt-in | `pytest -q` (opt-in) | PASS — `635 passed, 6 skipped`, coverage `91.98%` |
| Build | `python -m build` | PASS — sdist and wheel built, new module present in wheel contents |
| Security — pip-audit | `python -m pip_audit` | PASS — no known vulnerabilities |
| Security — secret scan targets | `python tools/secret_scan_targets.py` | PASS — 355 targets discovered (was 345 at M031 freeze) |

---

## 23. Changed Files

```
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/prepare_campaign_for_authorization.py
A  tests/unit/test_prepare_campaign_for_authorization_usecase.py
A  tests/contract/test_prepare_campaign_for_authorization_handler_contract.py
A  tests/integration/test_m032_prepare_campaign_for_authorization_usecase.py
```

Plus this implementation document and the `PROJECT_CHECKPOINT.md` governance update, staged separately in the same commit per repository convention.

**No `tools/check_architecture.py` change. No architecture fixture added. No M020-M031 file touched.**

---

## 24. Explicit Non-Changes

- `Campaign`, `CampaignRepository`, `PostgresCampaignRepository` — unmodified.
- `CommandHandler`, `CommandEntryPoint` — unmodified, used exactly as frozen.
- `AggregateVersion`, `LoadedAggregate`, `SaveResult`, `OptimisticConcurrencyConflict` — unmodified.
- Database schema and Alembic migrations — unmodified.
- `src/empirical_platform/usecases/create_campaign.py` (M030), `src/empirical_platform/usecases/get_campaign.py` (M031) — unmodified.
- All M020-M031 governance documents — unmodified.
- No production composition root, registry, dispatcher, mediator, or DI container introduced anywhere.
- `revise_scope_statement()` is invoked only from test setup (integration test conflict scenario) — never from production code.
- No M033 work of any kind.

---

## 25. Known Limitations

- The typed-conformance test's "mypy-checked proof" docstring wording documents static evidence exercised by the canonical `mypy` gate only for source files; `pyproject.toml`'s `[tool.mypy] packages = ["empirical_platform"]` scope excludes `tests/`. This is the identical, already-acknowledged limitation inherited from M029/M030/M031's own frozen tests, not a new defect introduced here.
- `test_command_construction_performs_no_business_validation` uses an empty-string `actor` to prove the command performs no validation of its own; this does not by itself prove every possible malformed input is rejected only by the aggregate — that broader guarantee rests on `Campaign.prepare_for_authorization()`'s own already-frozen, unmodified validation, unchanged by this milestone.

---

## 26. Remaining Risks

- None beyond what the frozen design already identified and mitigated (Design Document Section 28, Design Freeze Section 27) — this implementation introduces no new architectural risk, since it deviates from the frozen decisions in no respect, and the deterministic conflict-evidence mechanism specified by the design correction was independently reproduced against real PostgreSQL and confirmed to work exactly as designed.

---

## 27. Review Status

`CANDIDATE_FOR_INDEPENDENT_IMPLEMENTATION_REVIEW`. Not approved. Not frozen.

---

## 28. Next Permitted Action

**MILESTONE-032 INDEPENDENT IMPLEMENTATION REVIEW.**
