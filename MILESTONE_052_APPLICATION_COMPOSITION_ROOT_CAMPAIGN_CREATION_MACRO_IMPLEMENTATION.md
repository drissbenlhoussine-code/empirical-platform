# MILESTONE-052 - Application Composition Root: Real End-to-End Campaign Creation - Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced in the same consolidated M052 mission as the scope and design documents.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M052 frozen baseline | `1bff7903c5c6c34eba3596b564a209bfceb485e6` (sits on top of the M051 Owner Freeze hash-recording HEAD `7620b0bc2d50adf858cd4afe72ed8c8fe6995f12` plus one narrow, independently-tested M026 post-freeze correction — see scope document Section 7 for the full baseline-shift explanation) |

## 3. Delivered Capability

The third platform-integration entrypoint, and the first to exercise the repository's `.add()` code path: `src/empirical_platform/entrypoints/create_campaign.py`, composing — for the first time in production code — `resolve_foundation_config()` → `PostgresPersistenceService` → the frozen M025 `PostgresRepositoryRuntime` → the frozen M030 `CreateCampaignHandler`/`CreateCampaignCommand` → the frozen `CommandEntryPoint` (M029) → the frozen `UuidRuntimeIdentifierGenerator` (first-ever production construction), invocable as a real CLI command (`empirical-platform-create-campaign`). Completes a full create→retrieve→cancel real-world-usable trio for Campaign, alongside M050's `get_campaign` and M051's `cancel_campaign`. Zero new business/domain capability; every composed piece is already frozen and unmodified.

## 4. Production Source

```python
def run_create_campaign(
    *,
    campaign_governance_id: str,
    scope_statement: str,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> DomainIdentity[CampaignId]:
    resolved_config = config if config is not None else resolve_foundation_config().postgresql
    resolved_generator = identifier_generator or UuidRuntimeIdentifierGenerator()
    service = PostgresPersistenceService(resolved_config)
    try:
        service.initialize()
        runtime = PostgresRepositoryRuntime(service)
        handler = CreateCampaignHandler(
            campaign_repository=runtime.campaigns,
            runtime_identifier_generator=resolved_generator,
        )
        entry_point = CommandEntryPoint(handler)
        command = CreateCampaignCommand(
            campaign_governance_id=campaign_governance_id,
            scope_statement=scope_statement,
        )
        return entry_point(command)
    finally:
        service.close()


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: empirical-platform-create-campaign <governance_id> <scope_statement>")
    identity = run_create_campaign(
        campaign_governance_id=sys.argv[1],
        scope_statement=sys.argv[2],
    )
    print(json.dumps(_identity_payload(identity), sort_keys=True))
```

**Applies the M050-Y-1 corrected shape from the first line written**, independently sanity-checked during implementation: `service.initialize()` was deliberately, temporarily moved back before `try:`, confirmed to make `test_run_create_campaign_closes_service_when_initialize_raises` **fail**, then restored and confirmed to make it **pass** again.

## 5. Files Changed

```
A  MILESTONE_052_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CREATION_MACRO_DESIGN.md
A  MILESTONE_052_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CREATION_MACRO_IMPLEMENTATION.md
A  MILESTONE_052_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CREATION_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  pyproject.toml
A  src/empirical_platform/entrypoints/create_campaign.py
A  tests/integration/test_m052_create_campaign_entrypoint.py
A  tests/unit/test_create_campaign_entrypoint.py
```

Eight files: two modified, six added — identical footprint shape to M051. No architecture-checker change required.

## 6. Architecture Impact

None. `ALLOWED["entrypoints"]`/`FORBIDDEN_IMPORT_PREFIXES["entrypoints"]` (both established by M050, unchanged since) already permit everything M052 needs — `CreateCampaignCommand`/`CreateCampaignHandler` and `UuidRuntimeIdentifierGenerator` both live in already-permitted packages (`usecases`, `shared`). `python tools/check_architecture.py .` exit 0, independently re-verified after this implementation, with zero diff to `tools/check_architecture.py`.

## 7. Composition Feasibility — Result (Empirically Confirmed, Not Assumed)

Scope Section 3.E / design Section 13 raised this milestone's central empirical claims: whether the repository's `.add()` code path and the first-ever production construction of `UuidRuntimeIdentifierGenerator` both work correctly through a real entrypoint. **Result: genuinely achievable, exactly as designed.** Against a fresh, disposable `postgres:17` container, `run_create_campaign()` independently confirmed all five required behaviors: (1) golden-path creation using the **real, non-deterministic** `UuidRuntimeIdentifierGenerator` (not a test override), independently verified via direct-SQL read-back that a genuinely valid `DRAFT`-state Campaign row exists with the exact scope statement and version 0; (2) a deterministic-generator override producing an exact, predictable identity; (3) a genuine, unqualified `AggregateAlreadyExists` on a duplicate governance id; (4) a genuine `ValueError` on a malformed governance id; (5) genuine environment-based resolution of the production default `config` path.

## 8. Test Evidence

- Focused unit (CLI wrapper + `run_create_campaign()` resource-lifecycle coverage): **11 passed**.
- M052 focused PostgreSQL integration (fresh disposable `postgres:17` container, host-mapped port 32774): **5 passed** — real-UUID golden path, deterministic-override identity, `AggregateAlreadyExists`, `ValueError`, default-config environment resolution.
- Predecessor regression: M030 create-campaign 3/3 passed, M050 get-campaign 4/4 passed, M051 cancel-campaign 5/5 passed.
- Non-integration suite: **951 passed** (up from 938 pre-M052 unit-test-only delta; true pre-M052 baseline after the concurrent M026 correction was 940 — see Section 9), 223 deselected, coverage 85.15%.
- Full integration suite: **217 passed** (up from 212), 6 skipped.
- Full suite with PostgreSQL: **1168 passed** (up from 1152 true pre-M052 baseline — see Section 9), 6 skipped, coverage 93.73%, zero regression.
- `ruff format --check` / `ruff check`: clean, 288 files formatted.
- Canonical bare `mypy`: clean, 109 source files (up from 108).
- `python -m build --wheel`: succeeds; wheel inspection confirms `empirical_platform/entrypoints/create_campaign.py` packaged, `get_campaign.py`/`cancel_campaign.py` compositions intact, and `empirical-platform-create-campaign = empirical_platform.entrypoints.create_campaign:main` correctly registered under `[console_scripts]`.
- Smoke import: succeeds.
- `pip-audit`: no known vulnerabilities.
- Secret-scan: 0 findings across all tracked files at the M052 baseline (517); target count after this milestone's own commit: 523 (517 + 6 new tracked files).

## 9. Baseline Note — Concurrent Out-of-Band Correction

While this M052 mission was in progress, a separately-run, narrowly-scoped correction (commit `1bff7903c5c6c34eba3596b564a209bfceb485e6`) landed locally, fixing the M026 `bootstrap.py` resource-lifecycle defect this mission's own scope document (Section 7) discovered and flagged. That commit added 2 tests to the pre-existing unit suite (805 passed, up from 803, per its own commit message) — meaning the **true** pre-M052 baseline was 940 non-integration / 1152 full-suite passed, not the 938/1150 this mission's scope/design documents were originally drafted against. All numbers in Section 8 above are independently re-verified against the actual, current `1bff790` baseline, not the stale pre-correction figures. M052's own diff (Section 5) does not touch `bootstrap.py` or its tests in any way — `git diff` confirms zero overlap.

## 10. Hostile Self-Audit

Targeted prohibited-pattern grep on `create_campaign.py` (`try:|except|retry|while |sleep(|dispatcher|registry|locator|mediator|TODO|FIXME|M053`): exactly one match, the single `try:` that opens the `try/finally` guaranteeing `service.close()` — no `except` clause anywhere. Construction/lifecycle counts confirmed exactly 1 each: `PostgresPersistenceService(`, `.initialize()`, `.close()`, `PostgresRepositoryRuntime(`. Zero direct `.get(`/`.add(` calls on the repository anywhere in the entrypoint (the sole textual `.add(` match is inside the module docstring, not code). Zero domain/usecase/repository files touched. A full scope-creep sweep across the diff for `M053`/"second capability"/`http`/`api`/`flask`/`fastapi`/`dispatcher`/`registry`/`locator`/`mediator` inside `create_campaign.py`: zero matches.

## 11. No-Scope-Creep Declaration

No composition of any command/query beyond `CreateCampaignCommand`; no generic dispatcher, registry, or handler-discovery mechanism; no retry policy; no transport/HTTP/API layer; no schema/migration change; no adoption of `FoundationRuntime`/`bootstrap.py` (scope Section 7); no change to `Campaign`, `CampaignRepository`, `PostgresCampaignRepository`, `CreateCampaignCommand`, `CreateCampaignHandler`, `UuidRuntimeIdentifierGenerator`, `PostgresRepositoryRuntime`, `resolve_foundation_config`, `CommandEntryPoint`, `get_campaign.py`, `cancel_campaign.py`, or any other already-frozen contract; no MILESTONE-053 work.

## 12. Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.**
