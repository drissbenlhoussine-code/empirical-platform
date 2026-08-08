# MILESTONE-052 - Application Composition Root: Real End-to-End Campaign Creation - Macro Design

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_DESIGN**

Produced in the same consolidated M052 mission as the scope document.

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M052 frozen baseline | `1bff7903c5c6c34eba3596b564a209bfceb485e6` (sits on top of the M051 Owner Freeze hash-recording HEAD `7620b0bc2d50adf858cd4afe72ed8c8fe6995f12` plus one narrow, independently-tested M026 post-freeze correction — see scope document Section 7) |

## 3. Public Application Contract

```python
def run_create_campaign(
    *,
    campaign_governance_id: str,
    scope_statement: str,
    identifier_generator: RuntimeIdentifierGenerator | None = None,
    config: PostgreSQLConfigSnapshot | None = None,
) -> DomainIdentity[CampaignId]:
    """Resolve real PostgreSQL configuration (unless overridden), compose the
    real repository runtime, and create one Campaign end-to-end."""
```

`config` defaults to `None`, resolving via `resolve_foundation_config().postgresql` — the production path `main()` always uses, identical to `get_campaign.py`/`cancel_campaign.py`. `identifier_generator` defaults to `None`, resolving to a real `UuidRuntimeIdentifierGenerator()` — this milestone's own testability seam, mirroring `config`'s own pattern, so the integration test can supply a `DeterministicRuntimeIdentifierGenerator` without monkeypatching module internals.

## 4. Invocation Ownership

`main()` is the sole production caller, registered as the `empirical-platform-create-campaign` console script. `main()` performs argument-count validation only (exactly two required positional CLI arguments: governance id, scope statement) and no exception handling of any kind — mirroring `get_campaign.py`/`cancel_campaign.py`'s own complete absence of `try`/`except`.

```python
def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(
            "usage: empirical-platform-create-campaign <governance_id> <scope_statement>"
        )
    identity = run_create_campaign(
        campaign_governance_id=sys.argv[1],
        scope_statement=sys.argv[2],
    )
    print(json.dumps(_identity_payload(identity), sort_keys=True))
```

## 5. Allowed Dependencies

`run_create_campaign()` depends on exactly six already-frozen production symbols, no others: `resolve_foundation_config`/`PostgreSQLConfigSnapshot` (config), `PostgresPersistenceService` (M008/M023), `PostgresRepositoryRuntime` (M025), `CreateCampaignCommand`/`CreateCampaignHandler` (M030), `CommandEntryPoint` (M029), `UuidRuntimeIdentifierGenerator`/`RuntimeIdentifierGenerator` (foundation). **Deliberately not `FoundationRuntime`/`bootstrap.py`** — see scope document Section 7 for the investigated-and-rejected reasoning: `bootstrap.py`'s own composition functions are never invoked by any production entrypoint and independently were found to carry an uncorrected, out-of-scope resource-lifecycle defect of their own.

## 6. Composition Boundaries

```python
def run_create_campaign(
    *, campaign_governance_id: str, scope_statement: str,
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
```

**Applies the M050-Y-1 corrected shape from the first line written**: `service.initialize()` is the first statement inside `try:`, not before it — identical discipline to `cancel_campaign.py`, and a deliberate contrast to the uncorrected defect independently found in `bootstrap.py` during this same mission (scope Section 7). Exactly one `PostgresPersistenceService`, one `PostgresRepositoryRuntime`, one `CreateCampaignHandler`, one `CommandEntryPoint`, one command, one `.add()` call (inside the frozen handler, never called directly by this entrypoint).

## 7. Identity Model

Unlike `get_campaign.py`/`cancel_campaign.py`, this entrypoint does **not** construct a `DomainIdentity` itself — identity construction is the frozen `CreateCampaignHandler`'s own responsibility (it pairs the caller-supplied `governance_id` with a freshly generated `runtime_id`). `run_create_campaign()` returns whatever `DomainIdentity[CampaignId]` the handler produces, unchanged.

## 8. Persistence Contract

`PostgresCampaignRepository` (M023, via `PostgresRepositoryRuntime.campaigns`), obtained exactly as the two existing entrypoints obtain it — unmodified, unwrapped, passed directly to `CreateCampaignHandler`'s constructor. `run_create_campaign()` never touches SQL or the `unit_of_work()` boundary directly, and never calls `.add()` itself.

## 9. Runtime-Identifier Generation Boundary

`identifier_generator` defaults to a freshly-constructed `UuidRuntimeIdentifierGenerator()` per invocation — genuinely random, collision-resistant UUIDv4 values in production, exactly matching `RuntimeIdentifierGenerator`'s own frozen contract. The override seam exists solely for this milestone's own integration test (to assert a specific, predictable identity), mirroring the established `config` override precedent — it is never used to substitute production randomness with anything deterministic outside a test file.

## 10. PostgreSQL Success/Failure Strategy

Golden path: call `run_create_campaign()` with a fresh governance id, independently read back the persisted row via direct SQL (bypassing the repository), confirm `lifecycle_state = 'DRAFT'`, `version = 0`, exact `scope_statement`. Duplicate identity: call twice with the same governance id and a deterministic generator forcing the same runtime id — expect the frozen `AggregateAlreadyExists`, unqualified. Malformed governance id: expect the frozen `CampaignId.__post_init__`'s own `ValueError`, `add()` never reached.

## 11. Exception Semantics

No exception is caught, translated, or suppressed anywhere in `run_create_campaign()`. `AggregateAlreadyExists` (the creation-specific failure mode neither `get_campaign.py` nor `cancel_campaign.py` could ever exercise), `ValueError`/`TypeError` from malformed `CampaignId`/`CampaignScopeStatement`, `FoundationError` from configuration/connectivity failure — all propagate to the caller with exact instance identity.

## 12. Result Contract

`DomainIdentity[CampaignId]`, returned exactly as produced by `CreateCampaignHandler.handle()` — no wrapping. `main()`'s own `_identity_payload()` helper renders `governance_id`/`runtime_id` as JSON for CLI output only.

## 13. Test Strategy

Focused unit tests (CLI wrapper argument parsing/delegation, and the composition function's own resource-lifecycle shape via monkeypatched classes) — mirroring M051's corrected pattern, including an explicit `initialize()`-raises-closes-service regression test from the start, independently sanity-checked via a fail-before/pass-after defect reintroduction during implementation, exactly as done for M051. PostgreSQL integration tests: golden-path creation with direct-SQL read-back, `AggregateAlreadyExists`, malformed-identifier `ValueError` — all executed live against a fresh, disposable, uniquely-named/ported container.

## 14. Rejected Alternatives

- **Adopting `bootstrap.py`'s `FoundationRuntime`** — rejected; see scope document Section 7. Its own composition functions are never used in production and independently carry an uncorrected resource-lifecycle defect of their own.
- **A shared composition helper with `get_campaign.py`/`cancel_campaign.py`** — rejected per scope Section 6's anti-abstraction gate; no material duplication demonstrated.
- **Auto-generating `campaign_governance_id`** — rejected; the caller (a real external system, e.g. a workflow orchestrator) is the correct owner of the governance identifier's own meaning; `CreateCampaignCommand`'s own frozen contract already requires it as caller-supplied.

## 15. Risks

- This is the first production code path to exercise the `.add()` repository code path and `UuidRuntimeIdentifierGenerator`'s first-ever production construction — both must be independently verified during implementation, not assumed by citation from their own frozen unit tests.
- The M050-Y-1 resource-lifecycle discipline must again be structurally present from the first draft, independently re-verified via the same fail-before/pass-after sanity check used in M051.

## 16. M053 Boundary

This design selects exactly one MILESTONE-052 capability. No MILESTONE-053 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document.

## 17. Status

**CANDIDATE_INTERNAL_MACRO_DESIGN.**
