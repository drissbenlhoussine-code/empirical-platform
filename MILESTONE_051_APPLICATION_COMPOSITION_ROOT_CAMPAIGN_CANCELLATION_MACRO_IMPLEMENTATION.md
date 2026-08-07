# MILESTONE-051 - Application Composition Root: Real End-to-End Campaign Cancellation - Macro Implementation

## 1. Document Status

**Status: CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW**

Produced in the same consolidated M051 mission as the scope and design documents.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M051 frozen baseline | `6151fee11479a02207c271e84e79e430209705d0` (the final M050 Owner Freeze hash-recording HEAD) |

## 3. Delivered Capability

The first write command ever composed through a production entrypoint: `src/empirical_platform/entrypoints/cancel_campaign.py`, composing — for the first time in production code — `resolve_foundation_config()` → `PostgresPersistenceService` → the frozen M025 `PostgresRepositoryRuntime` → the frozen M047 `CancelCampaignHandler`/`CancelCampaignCommand` → the frozen `CommandEntryPoint` (M029), invocable as a real CLI command (`empirical-platform-cancel-campaign`). Pairs with M050's own `get_campaign` composition on the same aggregate, and proves — for the first time outside a test fixture — that `expected_persisted_version`/`OptimisticConcurrencyConflict` semantics propagate correctly through a real production entrypoint. Zero new business/domain capability; every composed piece is already frozen and unmodified.

## 4. Production Source

```python
def run_cancel_campaign(
    *,
    campaign_governance_id: str,
    campaign_runtime_id: str,
    expected_persisted_version: int,
    actor: str,
    occurred_at: datetime,
    reason: str | None = None,
    correlation_id: str | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> SaveResult:
    resolved_config = config if config is not None else resolve_foundation_config().postgresql
    service = PostgresPersistenceService(resolved_config)
    try:
        service.initialize()
        runtime = PostgresRepositoryRuntime(service)
        handler = CancelCampaignHandler(campaign_repository=runtime.campaigns)
        entry_point = CommandEntryPoint(handler)
        identity = DomainIdentity(
            governance_id=CampaignId(campaign_governance_id),
            runtime_id=RuntimeIdentifier(campaign_runtime_id),
        )
        command = CancelCampaignCommand(
            identity=identity,
            expected_persisted_version=AggregateVersion(expected_persisted_version),
            actor=actor,
            occurred_at=occurred_at,
            reason=reason,
            correlation_id=correlation_id,
        )
        return entry_point(command)
    finally:
        service.close()


def main() -> None:
    if len(sys.argv) not in (6, 7, 8):
        raise SystemExit(
            "usage: empirical-platform-cancel-campaign "
            "<governance_id> <runtime_id> <expected_version> <actor> <occurred_at_iso> "
            "[reason] [correlation_id]"
        )
    result = run_cancel_campaign(
        campaign_governance_id=sys.argv[1],
        campaign_runtime_id=sys.argv[2],
        expected_persisted_version=int(sys.argv[3]),
        actor=sys.argv[4],
        occurred_at=datetime.fromisoformat(sys.argv[5]),
        reason=sys.argv[6] if len(sys.argv) > 6 else None,
        correlation_id=sys.argv[7] if len(sys.argv) > 7 else None,
    )
    print(json.dumps(_result_payload(result), sort_keys=True))
```

**Applies the M050-Y-1 lesson from the first line written:** `service.initialize()` is deliberately the first statement inside `try:`, not before it — the entire service lifetime is owned by one `try`/`finally` boundary from the start, independently re-verified via a fail-before/pass-after sanity check during implementation (Section 9).

## 5. Files Changed

```
A  MILESTONE_051_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CANCELLATION_MACRO_DESIGN.md
A  MILESTONE_051_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CANCELLATION_MACRO_IMPLEMENTATION.md
A  MILESTONE_051_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_CANCELLATION_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  pyproject.toml
A  src/empirical_platform/entrypoints/cancel_campaign.py
A  tests/integration/test_m051_cancel_campaign_entrypoint.py
A  tests/unit/test_cancel_campaign_entrypoint.py
```

Eight files: two modified, six added. No architecture-checker change required — `entrypoints` already permits `usecases`/`identifiers` since M050.

## 6. Architecture Impact

None. `ALLOWED["entrypoints"]` and `FORBIDDEN_IMPORT_PREFIXES["entrypoints"]` (both established by M050) already permit exactly what this milestone needs — `CancelCampaignCommand`/`CancelCampaignHandler` live in the already-permitted `usecases` package. `python tools/check_architecture.py .` exit 0, independently re-verified after this implementation, with zero diff to `tools/check_architecture.py`.

## 7. Composition Feasibility — Result (Empirically Confirmed, Not Assumed)

Scope Section 12 / design Section 17 raised this milestone's central empirical claim: whether a genuine `OptimisticConcurrencyConflict` — not merely a domain `ValueError` — propagates correctly through a real production entrypoint, reusing M047's own frozen conflict mechanism (`revise_scope_statement()` from `DRAFT`). **Result: genuinely achievable, exactly as designed.** Against a fresh, disposable `postgres:17` container, `run_cancel_campaign()` independently confirmed all four required behaviors: (1) golden-path cancellation of a real, freshly-created Campaign, advancing `SaveResult.persisted_version` by exactly one; (2) a missing Campaign genuinely propagates the frozen `AggregateNotFound`, unqualified; (3) an invalid source state (`COMPLETED`) genuinely propagates the frozen domain `ValueError` from `Campaign.cancel()`'s own `_transition()`, unqualified, with `save()` never reached; (4) a genuine, independently-loaded interfering write (`revise_scope_statement()`) advancing the real persisted version causes the stale caller's own cancel to raise an exact, unqualified `OptimisticConcurrencyConflict` — confirmed via a fresh hostile probe checking `type(exc) is OptimisticConcurrencyConflict` precisely, with the interferer's write remaining authoritative and the stale cancellation never persisted. A fifth test independently confirmed the production default `config` path resolves through `resolve_foundation_config()` against the same disposable database via real environment variables.

A bonus hostile-audit finding (Section 9): an adversarially-chosen, impossibly-high `expected_persisted_version` (999, versus an actual version of 0) was independently confirmed to raise the distinct, pre-existing, frozen `InvalidAggregateForPersistence` exception (from `PostgresCampaignRepository`, unmodified since M023) rather than `OptimisticConcurrencyConflict` — confirming `run_cancel_campaign()` transparently propagates whichever exception the repository decides to raise, with zero interference or reclassification of any kind.

## 8. Test Evidence

- Focused unit (CLI wrapper + `run_cancel_campaign()` resource-lifecycle coverage): **11 passed**.
- M051 focused PostgreSQL integration (fresh disposable `postgres:17` container, host-mapped port 32772): **5 passed** — golden path, `AggregateNotFound`, invalid-state `ValueError`, genuine `OptimisticConcurrencyConflict`, default-config environment resolution.
- Non-integration suite: **938 passed** (up from 927), 218 deselected, coverage 85.05%.
- Full integration suite: **212 passed** (up from 207), 6 skipped.
- Full suite with PostgreSQL: **1150 passed** (up from 1134), 6 skipped, coverage 93.71%, zero regression.
- `ruff format --check` / `ruff check`: clean, 285 files formatted.
- Canonical bare `mypy`: clean, 108 source files (up from 107).
- `python -m build --wheel`: succeeds; wheel inspection confirms `empirical_platform/entrypoints/cancel_campaign.py` packaged and `empirical-platform-cancel-campaign = empirical_platform.entrypoints.cancel_campaign:main` correctly registered under `[console_scripts]`.
- Smoke import (`from empirical_platform.entrypoints.cancel_campaign import run_cancel_campaign, main`): succeeds.
- `pip-audit`: no known vulnerabilities.
- Secret-scan: 0 findings across all 510 tracked files (pre-commit baseline, the M050 Owner Freeze HEAD's own tracked-file count); target count after this milestone's own commit: 516 (510 + 6 new tracked files).

## 9. Hostile Self-Audit

Targeted prohibited-pattern grep on `cancel_campaign.py` (`try:|except|retry|while |sleep(|dispatcher|registry|locator|mediator|TODO|FIXME|M052`): exactly one match, the single `try:` that opens the `try/finally` guaranteeing `service.close()` — no `except` clause anywhere, confirming zero exception handling, translation, or suppression exists at the composition-function level. Resource-lifecycle sanity check: the M050-Y-1 defect (`initialize()` before `try:`) was deliberately, temporarily reintroduced during implementation and independently confirmed to make `test_run_cancel_campaign_closes_service_when_initialize_raises` **fail**; the correct shape was then restored and independently confirmed to make the same test **pass** — proving the regression guard is genuinely meaningful, not tautological, from the very first version of this file. Construction/lifecycle counts confirmed exactly 1 each: `PostgresPersistenceService(`, `.initialize()`, `.close()`, `PostgresRepositoryRuntime(`. No `.get()` call exists anywhere in `run_cancel_campaign()` — independently confirmed the entrypoint never peeks at or re-derives the current persisted version; `expected_persisted_version` flows unchanged from the caller's own argument into `AggregateVersion(...)` into `CancelCampaignCommand`. Zero domain/usecase/repository files touched (`git status --porcelain` against `src/empirical_platform/campaign/`, `src/empirical_platform/usecases/cancel_campaign.py`, `src/empirical_platform/shared/persistence/` — empty). A full scope-creep sweep across the diff for `M052`/"second capability"/`http`/`api`/`flask`/`fastapi`/`dispatcher`/`registry`/`locator`/`mediator` inside `cancel_campaign.py`: zero matches.

## 10. No-Scope-Creep Declaration

No composition of any command/query beyond `CancelCampaignCommand`; no generic dispatcher, registry, or handler-discovery mechanism; no retry policy; no transport/HTTP/API layer; no schema/migration change; no change to `Campaign`, `CampaignRepository`, `PostgresCampaignRepository`, `CancelCampaignCommand`, `CancelCampaignHandler`, `PostgresRepositoryRuntime`, `resolve_foundation_config`, `CommandEntryPoint`, `get_campaign.py`, or any other already-frozen contract; no MILESTONE-052 work.

## 11. Status

**CANDIDATE_FOR_COMPLETE_INDEPENDENT_MACRO_REVIEW.**
