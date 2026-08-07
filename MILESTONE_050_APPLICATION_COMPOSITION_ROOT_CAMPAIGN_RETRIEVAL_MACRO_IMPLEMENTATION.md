# MILESTONE-050 - Application Composition Root: Real End-to-End Campaign Retrieval - Macro Implementation

## 1. Document Status

**Status: CORRECTED_CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced in the same consolidated M050 mission as the scope and design documents. This document has been updated once, in place, to correct finding M050-Y-1 identified by the first independent hostile macro review; see Section 12 for the complete correction record. No other decision from the original mission was reopened.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M050 frozen baseline | `f8a2e6c4b8c98150fc0cc99e481ade605ce88048` (the final M049 Owner Freeze hash-recording HEAD) |

## 3. Delivered Capability

The first real, production, end-to-end application composition in the project's history: `src/empirical_platform/entrypoints/get_campaign.py`, composing — for the first time in production code — `resolve_foundation_config()` → `PostgresPersistenceService` → the frozen M025 `PostgresRepositoryRuntime` → the frozen M031 `GetCampaignHandler`/`GetCampaignQuery` → the frozen `QueryEntryPoint`, invocable as a real CLI command (`empirical-platform-get-campaign <governance_id> <runtime_id>`). Zero new business/domain capability; every composed piece is already frozen and unmodified.

## 4. Production Source

```python
def run_get_campaign(
    *,
    campaign_governance_id: str,
    campaign_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> CampaignSnapshot:
    resolved_config = config if config is not None else resolve_foundation_config().postgresql
    service = PostgresPersistenceService(resolved_config)
    try:
        service.initialize()
        runtime = PostgresRepositoryRuntime(service)
        handler = GetCampaignHandler(campaign_repository=runtime.campaigns)
        entry_point = QueryEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=CampaignId(campaign_governance_id),
            runtime_id=RuntimeIdentifier(campaign_runtime_id),
        )
        return entry_point(GetCampaignQuery(identity=identity))
    finally:
        service.close()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: empirical-platform-get-campaign <governance_id> <runtime_id>")
    snapshot = run_get_campaign(
        campaign_governance_id=sys.argv[1],
        campaign_runtime_id=sys.argv[2],
    )
    print(json.dumps(_snapshot_payload(snapshot), sort_keys=True))
```

Exactly as specified in design Sections 3-4: `run_get_campaign()` owns the entire composition and the sole unit of work (`GetCampaignHandler`'s single `get()` call); `main()` performs only CLI-argument-count validation and delegates, catching nothing.

## 5. Files Changed

```
M  PROJECT_CHECKPOINT.md
M  pyproject.toml
M  tests/architecture/test_module_boundaries.py
M  tools/check_architecture.py
A  MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_SCOPE.md
A  MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_DESIGN.md
A  MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_IMPLEMENTATION.md
A  src/empirical_platform/entrypoints/get_campaign.py
A  tests/fixtures/illegal_imports/src/empirical_platform/entrypoints/bad_boto3_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/entrypoints/bad_psycopg_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/entrypoints/bad_sqlalchemy_import.py
A  tests/integration/test_m050_get_campaign_entrypoint.py
A  tests/unit/test_get_campaign_entrypoint.py
```

Thirteen files: four modified, nine added.

## 6. Architecture Impact

Non-trivial, and fully justified per scope Section 7 / design Section 12: `ALLOWED["entrypoints"]` extended from `{"shared", "application"}` to `{"shared", "application", "identifiers", "usecases"}` (required to import `DomainIdentity`/`CampaignId`/`RuntimeIdentifier` and `GetCampaignQuery`/`GetCampaignHandler`/`CampaignSnapshot`). A new `FORBIDDEN_IMPORT_PREFIXES["entrypoints"]` entry forbids direct `sqlalchemy`/`psycopg`/`boto3` imports, deliberately excluding `empirical_platform.shared.persistence` — the composition this milestone exists to prove. `python tools/check_architecture.py .` exit 0, independently re-verified after this implementation. Three new negative-import fixtures under `tests/fixtures/illegal_imports/src/empirical_platform/entrypoints/`; `tests/architecture/test_module_boundaries.py` extended with three new assertions; both architecture tests pass (2/2).

## 7. Composition Feasibility — Result (Empirically Confirmed, Not Assumed)

Scope Section 12 / design Section 17 raised this milestone's central risk: this is the first production code path ever to touch real persistence outside a test file, and the composition itself — not a domain mutation — is what required independent proof. **Result: genuinely achievable, exactly as designed.** Against a fresh, disposable `postgres:17` container (never reused from any prior milestone), `run_get_campaign()` independently confirmed all three required behaviors: (1) golden-path retrieval of a real Campaign persisted moments earlier through the existing, frozen M030 `CreateCampaignHandler`, via a fully independent `PostgresPersistenceService`/`PostgresRepositoryRuntime` instance constructed inside `run_get_campaign()` itself — not shared with the test's own seeding connection; (2) a missing Campaign genuinely propagates the frozen `AggregateNotFound`, unqualified and untranslated; (3) a malformed empty `governance_id` genuinely propagates a `ValueError` from `CampaignId`'s own frozen `__post_init__` validation, confirming `run_get_campaign()` performs no exception translation of any kind, exactly as design Section 10 requires. A fourth test independently confirmed the production default path — omitting `config` entirely — genuinely resolves through `resolve_foundation_config()` against the same disposable database via real environment variables, not merely the explicit-override path the other three tests exercise.

## 8. Test Evidence

Original mission (pre-correction): focused unit 7 passed; M050 focused PostgreSQL integration 4 passed; non-integration suite 924 passed (213 deselected, coverage 84.72%); full integration regression 207 passed (6 skipped); full suite with PostgreSQL 1131 passed (6 skipped, coverage 93.70%).

Post-correction (this document's current numbers, re-run in full against a fresh, uniquely-named/ported `postgres:17` container never reused from the original mission's own evidence):

- Focused unit (CLI wrapper + `run_get_campaign()` resource-lifecycle coverage): **10 passed** (up from 7 — three new tests added by the M050-Y-1 correction; see Section 12).
- M050 focused PostgreSQL integration: **4 passed**, unchanged — golden path, `AggregateNotFound` propagation, `ValueError` propagation, default-config environment resolution.
- M031 Campaign-retrieval regression: **3 passed**, unchanged.
- Non-integration suite: **927 passed** (up from 924 by exactly the 3 new unit tests), 213 deselected, coverage 84.96%.
- Full integration suite: **207 passed**, unchanged, 6 skipped.
- Full suite with PostgreSQL: **1134 passed** (up from 1131 by exactly the 3 new unit tests), 6 skipped, coverage 93.70%, zero regression.
- `ruff format --check` / `ruff check`: clean, 282 files formatted.
- Canonical bare `mypy`: clean, 107 source files, unchanged.
- `python -m build --wheel`: succeeds; wheel inspection confirms `empirical_platform/entrypoints/get_campaign.py` packaged and `empirical-platform-get-campaign = empirical_platform.entrypoints.get_campaign:main` correctly registered under `[console_scripts]`.
- Smoke import (`from empirical_platform.entrypoints.get_campaign import run_get_campaign, main`): succeeds.
- `pip-audit`: no known vulnerabilities.
- Secret-scan: 0 findings across all 509 currently-tracked files (no new tracked file is introduced by this correction — only existing tracked files were edited).

## 9. Hostile Self-Audit

Targeted prohibited-pattern grep on `get_campaign.py` (`try:|except|retry|while |sleep(|dispatcher|registry|locator|mediator|TODO|FIXME|M051`): exactly one match, the single `try:` that opens the `try/finally` guaranteeing `service.close()` — no `except` clause anywhere in the file, confirming zero exception handling, translation, or suppression exists at the composition-function level, exactly as design Section 10 requires; `main()` itself contains no `try`/`except` at all, mirroring `health.py`'s own complete absence of exception handling. A scope-creep sweep across the full diff for `M051`/"second capability"/`http`/`api`/`flask`/`fastapi`/`dispatcher`/`registry`/`locator`/`mediator` inside `get_campaign.py`: zero matches. No generic dispatcher, no service locator, no handler-discovery mechanism, no second query or command composed anywhere in the diff.

## 10. No-Scope-Creep Declaration

No composition of any command/query beyond `GetCampaignQuery`; no generic dispatcher, registry, or handler-discovery mechanism; no retry policy; no transport/HTTP/API layer; no schema/migration change; no change to `Campaign`, `CampaignRepository`, `PostgresCampaignRepository`, `GetCampaignQuery`, `GetCampaignHandler`, `CampaignSnapshot`, `PostgresRepositoryRuntime`, `resolve_foundation_config`, or any other already-frozen contract; no MILESTONE-051 work.

## 12. Correction Record — M050-Y-1

The first independent hostile macro review (conducted against implementation commit `e5d6538`/finalization commit `f452c5c`) found one MAJOR, Owner-Freeze-blocking defect:

- **Finding M050-Y-1.** In the reviewed candidate, `service.initialize()` was called *before* the `try:` block opened in `run_get_campaign()`. The `finally: service.close()` clause therefore only covered failures occurring *after* a successful `initialize()`. When `initialize()` itself raised (e.g. an unreachable or misconfigured database), `close()` was never invoked, leaking the constructed-but-undisposed `PostgresPersistenceService`/SQLAlchemy engine. The reviewer reproduced this with an instrumented probe: `close()` call count of zero against a controlled `initialize()` failure. This directly contradicted the scope document's own claim (Section 11, pre-correction) that cleanup was guaranteed "regardless of success or failure."

**Correction applied.** `service.initialize()` was moved one line, from immediately before the `try:` to the first statement inside it, so the entire service lifetime — initialization, repository/handler/entry-point composition, and the query call — is now owned by one `try`/`finally` boundary. This is the complete correction; no other line of `get_campaign.py` changed, no new abstraction, context manager, resource-manager framework, or exception policy was introduced.

**Verification of the correction.**

1. *Pre-fix reproduction*, independent of the original review's own probe: a fresh instrumented script confirmed `close()` call count of `0` against the pre-correction source when `initialize()` was made to raise.
2. *Post-fix confirmation*: the identical script, run again after the one-line correction, confirmed `close()` call count of `1`, with the original exception (`FoundationError`, unaltered) still propagating to the caller.
3. *Regression test added*: `tests/unit/test_get_campaign_entrypoint.py::test_run_get_campaign_closes_service_when_initialize_raises` — monkeypatches `PostgresPersistenceService` with a fake whose `initialize()` raises and whose `close()` is tracked, and monkeypatches `PostgresRepositoryRuntime` to assert it is never constructed. Independently confirmed to **fail** against the pre-correction source (`close_calls == []`) and **pass** against the corrected source (`close_calls == [None]`), satisfying the "must fail before, pass after" requirement.
4. Two companion regression tests added for coverage completeness: `test_run_get_campaign_closes_service_exactly_once_on_success` (the already-correct success path, now explicitly guarded) and `test_run_get_campaign_closes_service_when_query_handler_raises` (the already-correct post-initialize-failure path, now explicitly guarded) — both pass, preserving the two scenarios the original implementation already handled correctly.

**Close-failure semantics — clarified, not changed.** `PostgresPersistenceService.close()` (frozen since M008/M023) contains no `try`/`except` of its own; if it were to raise while an exception from the `try` body is already propagating, ordinary Python `finally` semantics apply unchanged: the exception raised by `close()` becomes the actively propagating exception, with the original exception attached as its `__context__`. This is pre-existing, frozen behavior identical to every other `try`/`finally` resource-cleanup site in this codebase (including every integration test's own `service`/`seeding_service` fixtures) — M050 introduces no new exception-translation or suppression policy of any kind, in the correction or otherwise.

**Scope discipline preserved.** No second entrypoint, no dispatcher/registry/service-locator/mediator, no generic resource-manager abstraction, no retry policy, no MILESTONE-051 material — the correction is exactly the one-line change described above, plus the tests and governance wording needed to prove and document it.

## 13. Status

**CORRECTED_CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.** Ready for a fresh independent hostile macro re-review covering both the original mission and this correction.
