# MILESTONE-051 - Application Composition Root: Real End-to-End Campaign Cancellation - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced in the same consolidated M051 mission as the scope document.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M051 frozen baseline | `6151fee11479a02207c271e84e79e430209705d0` |

## 3. Public Application Contract

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
    """Resolve real PostgreSQL configuration (unless overridden), compose the
    real repository runtime, and cancel one Campaign end-to-end."""
```

`config` defaults to `None`, meaning "resolve from the real environment via `resolve_foundation_config().postgresql`" — the production path `main()` always uses, identical to `get_campaign.py`. `expected_persisted_version` is accepted as a plain `int` at this boundary (the CLI has no richer type to parse from `sys.argv`) and wrapped into an `AggregateVersion` inside the function body — the identical boundary-typing pattern the command layer itself already uses at every other command's own construction site. This is the only configuration/version surface this function exposes — no dependency-injection framework, no service locator.

## 4. Invocation Ownership

`main()` is the sole production caller of `run_cancel_campaign()`, registered as the `empirical-platform-cancel-campaign` console script (mirroring `get_campaign.py`'s own `[project.scripts]` registration). `main()` performs argument-count/parsing validation only (five required positional CLI arguments: governance id, runtime id, expected version, actor, occurred-at ISO timestamp; `reason` and `correlation_id` accepted as optional trailing arguments) and no exception handling of any kind — mirroring `get_campaign.py`'s own complete absence of `try`/`except`. An uncaught exception from `run_cancel_campaign()` propagates with Python's default behavior: a full traceback printed to stderr, process exit code 1.

```python
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

`int(sys.argv[3])`/`datetime.fromisoformat(sys.argv[5])` may themselves raise `ValueError` before `run_cancel_campaign()` is ever called — this is standard, unavoidable CLI-argument-parsing behavior (identical in kind to Python's own `argparse` type coercion), not exception handling of `run_cancel_campaign()`'s own behavior, and not a second capability.

## 5. Allowed Dependencies

`run_cancel_campaign()` depends on exactly six already-frozen production symbols, no others: `resolve_foundation_config`/`PostgreSQLConfigSnapshot` (config), `PostgresPersistenceService` (M008/M023), `PostgresRepositoryRuntime` (M025), `CancelCampaignCommand`/`CancelCampaignHandler` (M047), `CommandEntryPoint` (M029), `DomainIdentity`/`CampaignId`/`RuntimeIdentifier`/`AggregateVersion` (foundation value objects). One more than M050's five, because a write command's `expected_persisted_version` requires `AggregateVersion` construction at the boundary — `get_campaign.py`'s read-only `GetCampaignQuery` had no such field.

## 6. Composition Boundaries

```python
def run_cancel_campaign(
    *, campaign_governance_id: str, campaign_runtime_id: str,
    expected_persisted_version: int, actor: str, occurred_at: datetime,
    reason: str | None = None, correlation_id: str | None = None,
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
```

Exactly one `PostgresPersistenceService` is constructed per invocation, and its entire lifetime — `.initialize()`, repository/handler/entry-point composition, command construction, and the command call — is owned by a single `try`/`finally` block whose `finally` clause unconditionally calls `.close()`. **This is the corrected M050-Y-1 shape from the first line written** — `.initialize()` is deliberately the first statement inside `try:`, not before it; this milestone does not repeat M050's original defect. Exactly one `PostgresRepositoryRuntime`, one `CancelCampaignHandler`, one `CommandEntryPoint`, one command, one result. No caching, no connection pooling beyond what `PostgresPersistenceService` itself already provides, no retry.

## 7. Identity Model

Identical to `get_campaign.py`: `DomainIdentity[CampaignId]` constructed from the two CLI-supplied strings (`campaign_governance_id`, `campaign_runtime_id`), relying entirely on `CampaignId`/`RuntimeIdentifier`'s own frozen `__post_init__` validation. No new identity type, no identity translation layer.

## 8. Persistence Contract

`PostgresCampaignRepository` (M023, via `PostgresRepositoryRuntime.campaigns`), obtained exactly as `get_campaign.py` obtains it — unmodified, unwrapped, passed directly to `CancelCampaignHandler`'s constructor. `run_cancel_campaign()` never touches SQL, the `unit_of_work()` boundary, or any persistence internal directly.

## 9. Expected-Version Semantics

`expected_persisted_version` is accepted as a CLI-parseable `int`, wrapped into `AggregateVersion(expected_persisted_version)` at the composition boundary, and passed through to `CancelCampaignCommand.expected_persisted_version` unchanged — never re-derived from a `.get()` call the entrypoint itself might otherwise be tempted to make. The entrypoint does not "look up the current version and cancel" — it is a thin, honest translation of "the caller asserts version N; cancel if and only if version N is still current," exactly matching every other frozen command's own semantics since M030.

## 10. PostgreSQL Success/Failure Strategy

Golden path: seed a Campaign via the frozen M030 `CreateCampaignHandler` (as `get_campaign.py`'s own integration test already does), read its `identity`/initial `persisted_version` via a real, independent seeding connection, then call `run_cancel_campaign()` with that exact version — expect a genuine `SaveResult` with `version` advanced by one and `state == CANCELLED`. Missing Campaign: expect `AggregateNotFound`, unqualified. Invalid source state: seed a Campaign already in `CANCELLED` (via a prior real `cancel()` through the same entrypoint or the frozen handler directly), call again — expect the domain `ValueError` from `Campaign.cancel()`'s own `_transition()`, unqualified, `save()` never reached.

## 11. Real Conflict / Stale-Caller Feasibility

Reusing M047's own frozen conflict evidence: seed a Campaign in `DRAFT` via `CreateCampaignHandler`; an independently-loaded interferer calls `revise_scope_statement()` (state-preserving — `DRAFT` remains `DRAFT`, still within `cancel()`'s own `allowed_states`) and persists, genuinely advancing the persisted version; a stale caller then invokes `run_cancel_campaign()` with the caller's own now-stale `expected_persisted_version`, captured before the interferer's write. Expected: a genuine, unqualified `OptimisticConcurrencyConflict` propagating through `CommandEntryPoint`/`run_cancel_campaign()` unchanged — not a domain `ValueError`, not a swallowed/wrapped exception. This is the one behavior M050's read-only composition structurally could not exercise; independently reproducing it here is this milestone's central empirical claim, to be genuinely verified during implementation, not assumed by citation from M047.

## 12. Architecture Impact

None required. `ALLOWED["entrypoints"]` already includes `usecases`/`identifiers` (extended by M050) — `CancelCampaignCommand`/`CancelCampaignHandler` live in `usecases`, already permitted. `FORBIDDEN_IMPORT_PREFIXES["entrypoints"]` already forbids `sqlalchemy`/`psycopg`/`boto3` while permitting `shared.persistence` composition (M050) — no new raw-driver risk is introduced by a write command that this boundary doesn't already guard against. `python tools/check_architecture.py .` exit 0, to be independently re-verified after implementation with zero diff to `tools/check_architecture.py`.

## 13. Exception Semantics

No exception is caught, translated, or suppressed anywhere in `run_cancel_campaign()`. `AggregateNotFound`, the domain `ValueError` (invalid state), `OptimisticConcurrencyConflict` (stale version), `FoundationError` from configuration/connectivity failure — all propagate to the caller with exact instance identity, exactly mirroring `get_campaign.py`'s own transparent-propagation discipline and every command handler's own discipline since M030.

## 14. Result Contract

`SaveResult`, returned exactly as received from `CommandEntryPoint`/`CancelCampaignHandler.handle()` (`is` identity) — no wrapping, no reconstruction. The CLI's own `_result_payload()` helper (mirroring `get_campaign.py`'s `_snapshot_payload()`) renders it as JSON for `main()`'s own output only; `run_cancel_campaign()` itself returns the real `SaveResult` object, not a serialized form.

## 15. Test Strategy

Focused unit tests (CLI wrapper argument parsing/delegation, and the composition function's own resource-lifecycle shape via monkeypatched `PostgresPersistenceService`/`PostgresRepositoryRuntime`/handler/entry-point classes) — mirroring M050's corrected pattern (including an explicit `initialize()`-raises-closes-service regression test from the start, per Section 12 of the scope document's stated risk). PostgreSQL integration tests: golden-path cancellation, `AggregateNotFound`, invalid-state `ValueError`, and genuine `OptimisticConcurrencyConflict` — all executed live against a fresh, disposable, uniquely-named/ported container, never reused from any prior milestone.

## 16. Rejected Alternatives

- **Deriving `expected_persisted_version` from an internal `.get()` call inside the entrypoint** — rejected; would silently change this command's semantics from "cancel if version N is current" to "cancel whatever version is current," defeating the entire purpose of optimistic concurrency and diverging from every other frozen command's own contract.
- **A generic result-formatting abstraction shared with `get_campaign.py`** — rejected; two independent five-line helper functions (`_snapshot_payload`, `_result_payload`) are simpler and safer than introducing a shared module purely to save a few lines, per this project's own "no premature abstraction" discipline.
- **Composing `CancelCampaignCommand` and `GetCampaignQuery` through one shared composition helper** — rejected; would introduce exactly the kind of generic composition machinery M050 and this milestone both explicitly reject, for a savings of a few duplicated lines.

## 17. Risks

- The genuine `OptimisticConcurrencyConflict` reproduction (Section 11) is the milestone's central empirical claim and must be independently proven during implementation against real PostgreSQL, not assumed by citation from M047's own frozen evidence.
- CLI argument parsing now has more surface than `get_campaign.py`'s (five to seven positional arguments, two of which require type coercion before `run_cancel_campaign()` is ever called) — must fail cleanly and predictably, without inventing a new "clean CLI error" convention absent elsewhere in this codebase.
- The M050-Y-1 resource-lifecycle correction must be structurally present from the first draft of `cancel_campaign.py`, independently re-verified during implementation exactly as `get_campaign.py`'s own corrected shape was re-verified at M050's re-review.

## 18. M052 Boundary

This design selects exactly one MILESTONE-051 capability. No MILESTONE-052 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 19. Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.**
