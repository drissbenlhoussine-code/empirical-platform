# MILESTONE-050 - Application Composition Root: Real End-to-End Campaign Retrieval - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced in the same consolidated M050 mission as the scope document.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M050 frozen baseline | `f8a2e6c4b8c98150fc0cc99e481ade605ce88048` |

## 3. Public Application Contract

```python
def run_get_campaign(
    *,
    campaign_governance_id: str,
    campaign_runtime_id: str,
    config: PostgreSQLConfigSnapshot | None = None,
) -> CampaignSnapshot:
    """Resolve real PostgreSQL configuration (unless overridden), compose the
    real repository runtime, and retrieve one Campaign end-to-end."""
```

`config` defaults to `None`, meaning "resolve from the real environment via `resolve_foundation_config().postgresql`" — the production path `main()` always uses. A caller (specifically, this milestone's own integration test) may supply an explicit `PostgreSQLConfigSnapshot` pointing at a disposable test container, without needing to monkeypatch environment variables or module internals. This is the **only** configuration surface this function exposes — no dependency-injection framework, no service locator.

## 4. Invocation Ownership

`main()` is the sole production caller of `run_get_campaign()`, registered as the `empirical-platform-get-campaign` console script (mirroring `health.py`'s/`version.py`'s own `[project.scripts]` registration). `main()` performs exactly one piece of validation (argument count) and no exception handling of any kind — mirroring `health.py`'s own complete absence of `try`/`except`. An uncaught exception from `run_get_campaign()` (missing Campaign, malformed identifier, connectivity failure, misconfiguration) propagates with Python's default behavior: a full traceback printed to stderr, process exit code 1. This is deliberate — introducing a "clean CLI error" convention not otherwise present anywhere in this codebase would be new, unreviewed behavior; mirroring the zero-exception-handling precedent already frozen in `health.py` keeps this milestone's blast radius minimal.

```python
def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("usage: empirical-platform-get-campaign <governance_id> <runtime_id>")
    snapshot = run_get_campaign(
        campaign_governance_id=sys.argv[1],
        campaign_runtime_id=sys.argv[2],
    )
    print(json.dumps(_snapshot_payload(snapshot), sort_keys=True))
```

## 5. Allowed Dependencies

`run_get_campaign()` depends on exactly five already-frozen production symbols, no others:

1. `resolve_foundation_config` (foundation config resolution).
2. `PostgresPersistenceService` (M008/M023).
3. `PostgresRepositoryRuntime` (M025).
4. `GetCampaignHandler`/`GetCampaignQuery`/`CampaignSnapshot` (M031).
5. `QueryEntryPoint` (M029), plus `DomainIdentity`/`CampaignId`/`RuntimeIdentifier` for identity construction.

No new class is introduced beyond the module-level `run_get_campaign()`/`main()`/`_snapshot_payload()` functions — this is intentionally a composition function, not a new composition-root *class* or framework, matching the scope's explicit rejection of a generic dispatcher.

## 6. Composition Boundaries

```python
def run_get_campaign(
    *, campaign_governance_id: str, campaign_runtime_id: str,
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
```

Exactly one `PostgresPersistenceService` is constructed per invocation, and its entire lifetime — `.initialize()`, repository/handler/entry-point composition, and the query call — is owned by a single `try`/`finally` block whose `finally` clause unconditionally calls `.close()`. The `try` boundary starts immediately after construction, deliberately including `.initialize()` itself, so `.close()` is attempted whether initialization succeeds or fails, not only for failures that occur after a successful `.initialize()`. (Independent hostile review — finding M050-Y-1 — caught and this milestone corrected a candidate revision where `.initialize()` was called before the `try` opened, which left an initialization failure unable to reach `.close()`; see the Macro Implementation document's own correction record.) Exactly one `PostgresRepositoryRuntime`, one `GetCampaignHandler`, one `QueryEntryPoint`, one query, one result. No caching, no connection pooling beyond what `PostgresPersistenceService` itself already provides, no retry.

## 7. Transaction Ownership

Unchanged from M031: `GetCampaignHandler.handle()`'s own single `campaign_repository.get()` call is the entire unit of work. This milestone introduces no new transaction primitive and does not touch `PostgresPersistenceService.run_composed()` (the frozen M024 composed-transaction primitive) — a read-only single-repository query has no multi-repository transaction to compose.

## 8. Retry Ownership

None. No retry exists anywhere in this milestone, consistent with every prior milestone's explicit deferral of retry-on-conflict policy. A connectivity failure propagates once, uncaught, exactly as `main()` demands (Section 4).

## 9. Idempotency Boundary

Trivial: `GetCampaignQuery` is a read; repeated invocation has no side effect and always returns the current state. No idempotency key or deduplication mechanism is needed or introduced.

## 10. Exception Semantics

No exception is caught, translated, or suppressed anywhere in `run_get_campaign()`. `AggregateNotFound` (missing Campaign), `TypeError`/`ValueError` from malformed `CampaignId`/`RuntimeIdentifier` input, `FoundationError` from `resolve_foundation_config()`/`PostgreSQLConfigSnapshot.sqlalchemy_url()` misconfiguration, and any connectivity failure from `PostgresPersistenceService.initialize()` all propagate to the caller with exact instance identity, exactly mirroring the transparent-propagation discipline already frozen for every command/query handler since M030.

## 11. Persistence Boundary

`run_get_campaign()` never imports `sqlalchemy`, `psycopg`, or `boto3` directly — it only composes the already-frozen `PostgresPersistenceService`/`PostgresRepositoryRuntime`/`PostgresCampaignRepository`, all of which already own the actual persistence-driver dependency. This milestone's architecture-checker change (Section 12) makes this boundary machine-enforced, not merely a convention.

## 12. Architecture Impact

Two narrow, justified changes to `tools/check_architecture.py`:

1. `ALLOWED["entrypoints"]` extended from `{"shared", "application"}` to `{"shared", "application", "identifiers", "usecases"}` — required because `DomainIdentity`/`CampaignId` live under the top-level `identifiers` package (not `shared`), and `GetCampaignQuery`/`GetCampaignHandler`/`CampaignSnapshot` live under `usecases`.
2. A new `FORBIDDEN_IMPORT_PREFIXES["entrypoints"] = ("sqlalchemy", "psycopg", "boto3")` entry — `entrypoints` may compose already-built `shared.persistence` adapters (already permitted via `ALLOWED["entrypoints"]`'s existing `"shared"` entry, unchanged), but may never import a raw persistence-driver library directly, mirroring the identical discipline already enforced on `campaign`/`run`/`evidence`/`review`/`shared`/`application`/`usecases`.

`shared.persistence` itself is **not** added to `FORBIDDEN_IMPORT_PREFIXES["entrypoints"]` — unlike every domain/application package, `entrypoints` is precisely the layer where composing `shared.persistence` adapters is the entire point.

Corresponding fixture maintenance: three new negative-import fixture files under `tests/fixtures/illegal_imports/src/empirical_platform/entrypoints/` (`sqlalchemy`, `psycopg`, `boto3`), and three new assertions in `tests/architecture/test_module_boundaries.py`'s existing `test_negative_fixture_detects_illegal_import`.

## 13. PostgreSQL Success/Failure Strategy

- **Success**: a real Campaign is first persisted through the existing, frozen M030 `CreateCampaignHandler` (test setup, via the real `PostgresCampaignRepository`, not through `run_get_campaign()` itself — this milestone composes retrieval only). `run_get_campaign()` is then invoked with the real config pointing at the same disposable container, and its result is compared field-for-field against the aggregate persisted moments earlier.
- **Failure (missing Campaign)**: `run_get_campaign()` invoked with a syntactically valid but non-existent identity; `AggregateNotFound` must propagate uncaught.
- **Failure (malformed identifier)**: `run_get_campaign()` invoked with a governance ID that fails `CampaignId`'s own frozen `__post_init__` pattern check; the resulting `ValueError` must propagate uncaught, proving no premature or duplicated validation exists in the entrypoint itself.

## 14. Real Conflict / Stale-Caller Feasibility

Not applicable — this is a read-only query composition; `GetCampaignHandler` has never had, and does not gain, any `expected_persisted_version`/`OptimisticConcurrencyConflict` dimension.

## 15. Test Strategy

- **Unit**: `main()`'s own argument-count validation, tested via direct function calls with a monkeypatched `sys.argv` and a stubbed `run_get_campaign` (verifying `main()` calls it with exactly the parsed arguments and prints the expected JSON shape) — no real persistence touched.
- **Contract-equivalent**: a direct signature/behavior check that `run_get_campaign()` accepts an optional `config` override (proving the testability seam exists and works), using a `LoadedAggregate`-free real round-trip against a real container (folded into the integration tests below rather than a separate contract file, since there is no `CommandHandler`/`QueryHandler` Protocol being newly implemented here — this milestone adds a composition function, not a new Protocol conformant class).
- **PostgreSQL integration**: golden-path retrieval of a real, freshly-created Campaign; missing-Campaign `AggregateNotFound` propagation; malformed-identifier `ValueError` propagation — all executed live against a fresh disposable container.
- **Architecture**: `check_architecture.py` clean; both new fixture-negative cases (sqlalchemy/psycopg/boto3 under `entrypoints`) genuinely detected.

## 16. Rejected Alternatives

- A `CampaignCompositionRoot` class wrapping the four steps — rejected; a single function is simpler, matches `health.py`'s own function-based style, and avoids inventing unnecessary object lifecycle (construct-then-call-once has no benefit over a single function call here).
- Catching exceptions in `main()` to print a friendly one-line error — rejected (Section 4); would introduce a CLI convention with zero precedent elsewhere in this codebase.
- Returning a raw `dict` from `run_get_campaign()` instead of the real `CampaignSnapshot` — rejected; the composition function's return type should be the real, already-frozen domain read value, with JSON serialization handled only at the CLI boundary (`_snapshot_payload()`), keeping the composition function itself free of any output-format concern.

## 17. Risks

Carried forward from scope Section 12: this is the first production code path touching real persistence outside a test file, and must be reviewed with equal rigor to a domain transition's own `get()`/mutate/`save()` sequence.

## 18. M051 Boundary

This design resolves exactly one MILESTONE-050 capability. No MILESTONE-051 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 19. Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.**
