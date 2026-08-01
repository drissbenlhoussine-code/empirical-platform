# MILESTONE-033 - Concrete Application Command Vertical Slice (Run Creation) Design Freeze

## 1. Milestone Identity

| Field | Value |
| --- | --- |
| Milestone | MILESTONE-033 |
| Working title | Concrete Application Command Vertical Slice (Run Creation) |
| Freeze type | Owner Design Freeze |

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `d16f429dc69110a9ec9e8a46f40af32164ad5d22` |

## 3. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Concrete Application Command Vertical Slice — Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Concrete Application Query Vertical Slice — Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Concrete Application Command Vertical Slice — Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |

## 4. M033 Scope Authority

`MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_SCOPE.md`, scope candidate commit `04e274240f7958d80bc0cb87f92f825b563fbd5a`. Selected capability: one concrete Run-creation command vertical slice via `RunRepository.add()`.

## 5. M033 Scope-Freeze Authority

`MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_SCOPE_FREEZE.md`, freeze commit `44dd29e34f6150bd37bc466eed14098d75ac57ab`. **M033 SCOPE APPROVED_AND_FROZEN.** Verified in this freeze mission to remain byte-identical to its own commit content.

## 6. M033 Design Candidate Commit

`8edead3bc25d786cef8563f4fc4815a889a3a447` (`docs: define M033 Run creation design candidate`), hash recorded via narrow follow-up `d16f429dc69110a9ec9e8a46f40af32164ad5d22` (`docs: record M033 design candidate commit hash`). Verified directly in this freeze mission: `MILESTONE_033_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_CREATION_DESIGN.md` remains byte-identical to its content at the candidate commit (`git diff` against that commit for this file is empty).

## 7. Independent Hostile Design-Review Decision

**M033 DESIGN APPROVED FOR OWNER FREEZE.** No CRITICAL, MAJOR, or blocking MINOR finding remains. No correction was required.

**Non-blocking observation (preserved, not corrected):** the missing-Campaign behavior intentionally exposes the existing `FoundationError` (category `PERSISTENCE`) produced by the frozen persistence layer. This is explicit by design (Design Section 6), consistent with M029's transparent-error-propagation principle, and is preserved unchanged by this freeze — it is not translated, wrapped, or replaced.

## 8. Review Validation Summary

The independent review verified directly: repository truth and clean lineage; the design-only two-file delta; `Run` aggregate creation semantics; `RunRepository.add()`; `PostgresRunRepository.add()`; the real database foreign-key behavior (`run.campaign_id → campaign.governance_id`, M022); duplicate-identity translation (`AggregateAlreadyExists`); raw `FoundationError` propagation for a missing Campaign; the Run identity-generation model; the exact command and handler contracts; the exact creation sequence; the `DomainIdentity[RunId]` return contract; transparent error behavior; the absence of transaction orchestration; the narrow architecture-checker extension; the PostgreSQL evidence strategy; testability; the absence of scope creep; and governance consistency.

## 9. Owner Approval

The Owner reviewed the independent design review's conclusion and formally authorizes this Design Freeze. **M033 DESIGN APPROVED_AND_FROZEN.**

## 10. Frozen Run Creation Semantics

`Run.__init__(self, *, identity: DomainIdentity[RunId], campaign_id: CampaignId) -> None`. Pure value construction: no `actor`/`occurred_at`/`correlation_id`/`reason`; initial state `RunLifecycleState.CREATED` set unconditionally (not via `_transition()`); initial version `AggregateVersion.initial()`; empty `_manifests` and `_transition_history`. Unmodified aggregate — verified directly against `src/empirical_platform/run/aggregate.py` in this freeze mission.

## 11. Frozen Campaign-Existence Decision

**No application-level Campaign lookup. No `CampaignRepository` dependency.** Campaign existence is enforced exclusively by the existing database foreign-key constraint `run.campaign_id → campaign.governance_id` (frozen since M022, verified directly in `migrations/versions/5b58cdd7751b_create_m022_postgresql_schema.py`). A missing Campaign propagates through the frozen persistence behavior as an unmodified `FoundationError` with `category=FoundationErrorCategory.PERSISTENCE` — raised inside `PostgresRunRepository.add()`, re-raised unchanged because its `except FoundationError` block only special-cases unique-violation constraints (`_ROOT_UNIQUE_CONSTRAINTS = {"pk_run", "uq_run_governance_id"}`), which a foreign-key violation (SQLSTATE `23503`) is not. This decision is frozen without modification: **no pre-check, no fallback behavior, no translation is authorized.**

## 12. Frozen Identity Model

The caller supplies `run_governance_id: str`. The handler: (1) constructs `RunId(command.run_governance_id)`; (2) calls `RuntimeIdentifierGenerator.generate()` exactly once; (3) constructs `DomainIdentity[RunId]` from the `RunId` and the generated runtime identifier. The handler never generates the governance ID. The caller never supplies a full `DomainIdentity`. This mirrors `CreateCampaignCommand`/`CreateCampaignHandler` (M030) exactly.

## 13. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class CreateRunCommand:
    run_governance_id: str
    campaign_governance_id: str
```

Immutable, slots-based, exactly two fields, no defaults, no metadata, no command-level validation beyond ordinary dataclass construction — all format validation deferred to `RunId`/`CampaignId` construction inside the handler.

## 14. Frozen Handler Contract

`CreateRunHandler`, constructor dependencies `RunRepository` and `RuntimeIdentifierGenerator` only — no `CampaignRepository`, no concrete persistence/runtime adapter. Structurally conforms to `CommandHandler[CreateRunCommand, DomainIdentity[RunId]]`. Synchronous. Location: `src/empirical_platform/usecases/create_run.py`.

## 15. Frozen Campaign-Reference Semantics

The handler constructs `CampaignId(command.campaign_governance_id)` and passes it directly to `Run.__init__(campaign_id=...)`. No Campaign aggregate load occurs. No full Campaign `DomainIdentity` is required — `Run.campaign_id` is typed as a bare `CampaignId`, not a `DomainIdentity[CampaignId]`.

## 16. Frozen Runtime-Identity Generation Semantics

`runtime_id` is generated exactly once per `handle()` invocation via the injected `RuntimeIdentifierGenerator.generate()`. Failure propagates as the frozen `UuidRuntimeIdentifierGenerator`'s own `FoundationError` (category `TIME_IDENTIFIER`), unmodified.

## 17. Exact Creation Sequence

1. Receive `CreateRunCommand`.
2. Construct `RunId` from `command.run_governance_id`.
3. Generate the runtime identifier exactly once.
4. Construct `DomainIdentity[RunId]`.
5. Construct `CampaignId` from `command.campaign_governance_id`.
6. Construct exactly one `Run` aggregate using the created identity and the `CampaignId`.
7. Call `RunRepository.add(run)` exactly once.
8. Return `run.identity`.

No second repository call. No Campaign lookup. No retry. No transaction orchestration.

## 18. Return Contract

Return `DomainIdentity[RunId]` — the identity belonging to the constructed `Run` aggregate (read off the aggregate itself, not the local `identity` variable). Do not return `Run`, `LoadedAggregate`, `SaveResult`, any repository implementation result, any generic result envelope, or `None`.

## 19. Duplicate-Identity Behavior

Existing database uniqueness constraints remain authoritative. Duplicate governance-ID or runtime-ID persistence collisions propagate through the existing `RunRepository.add()` translation as `AggregateAlreadyExists`. No handler pre-check. No retry or regenerated runtime ID.

## 20. Missing-Campaign Behavior

Existing database foreign-key enforcement remains authoritative. Missing-Campaign failure propagates as the existing `FoundationError` (category `PERSISTENCE`). No translation to `AggregateNotFound` or any new application error. No nullable result. (See Section 11 and the preserved non-blocking observation in Section 7.)

## 21. Error Semantics

Transparent propagation of: `RunId` construction `ValueError`; `CampaignId` construction `ValueError`; `RuntimeIdentifierGenerator` failures; `AggregateAlreadyExists`; `FoundationError` for a missing Campaign; arbitrary repository failures. No handler `try`/`except`. No wrapping, translation, suppression, retry, nullable result, or status envelope.

## 22. Validation Ownership

Command: passive immutable carrier. `RunId`/`CampaignId`: identifier format validation. `Run` aggregate: constructor and structural invariants. `RunRepository`/database: uniqueness and referential integrity. Handler: orchestration only — no duplicated validation anywhere.

## 23. Transaction Non-Ownership

No application transaction orchestration. No `run_composed()`. Exactly one `RunRepository.add()` operation owns persistence atomicity.

## 24. CommandEntryPoint Binding

Direct construction in tests only. No production composition root. No registry, command bus, dispatcher, mediator, service locator, or DI framework.

## 25. Package and Dependency Boundaries

Approved production module: `src/empirical_platform/usecases/create_run.py`. Package (`usecases/__init__.py`) exports may be updated only as necessary to expose `CreateRunCommand`/`CreateRunHandler`, mirroring the existing export pattern for `create_campaign`/`get_campaign`/`prepare_campaign_for_authorization`. No import from `empirical_platform.campaign` in the new module — only `CampaignId` from `empirical_platform.identifiers` (already allowed).

## 26. Architecture-Checker Impact

The future implementation is authorized to make exactly the narrow change: add `"run"` to `ALLOWED["usecases"]`. Existing forbidden-prefix protections (`FORBIDDEN_IMPORT_PREFIXES["usecases"]`) remain unchanged — no broader permission grant, no package restructuring. Focused fixtures/tests must prove: `usecases` may import `run`; `usecases` still cannot import `shared.persistence`; `usecases` still cannot import concrete adapters/runtime; `usecases` still cannot import unrelated aggregates such as `evidence` or `review`; `run`/domain packages still cannot import `usecases`.

## 27. PostgreSQL Evidence Strategy

Future implementation must prove: (1) successful Run creation; (2) correct persisted Run identity; (3) correct Campaign association; (4) initial Run state `CREATED`; (5) initial aggregate/persisted version behavior; (6) duplicate governance-identity failure; (7) duplicate runtime-identity failure where deterministically feasible; (8) missing-Campaign foreign-key failure; (9) exact error behavior; (10) no schema/migration change; (11) existing Run repository regression remains green; (12) M030-M032 regressions remain green.

## 28. Test Obligations

Unit tests for the command (exact fields, immutability, no extra validation); handler success (exact dependencies, exact sequence, exact return value, zero unrelated repository calls, structural absence of any `CampaignRepository` dependency); failure behavior (duplicate identity, malformed identifiers, generator failure, arbitrary repository failure — all transparent, no retry); `CommandEntryPoint` structural conformance; architecture fixtures per Section 26; the twelve PostgreSQL evidence items per Section 27.

## 29. Implementation Authorization Boundary

After this design freeze, a future M033 implementation mission may touch only what is narrowly required for: `src/empirical_platform/usecases/create_run.py`; necessary `usecases` package exports; the exact `ALLOWED["usecases"]` addition for `"run"`; focused architecture fixtures/tests; focused Run-creation unit tests; contract tests; PostgreSQL integration tests; M033 implementation evidence; `PROJECT_CHECKPOINT.md`; the mandatory external-review package.

It must **not** modify: `Run` aggregate; `RunRepository`; `PostgresRunRepository`; `Campaign` aggregate; `CampaignRepository`; database schema or migrations; `CommandHandler`; `CommandEntryPoint`; M030-M032 source; frozen governance authority.

## 30. Prohibited Expansion

No Run retrieval; no Run lifecycle transition; no Run save/update; no second Run command; no Campaign lookup usecase; no Campaign mutation/query; no `EvidencePackage` or `Review` usecase; no retry/backoff; no identifier regeneration after duplicate; no generic creation framework; no generic cross-aggregate validation framework; no composition root; no registry; no command bus; no dispatcher; no mediator; no service locator; no DI framework; no transport/API; no audit integration; no market data; no trading behavior; no schema/migration change; no MILESTONE-034 work.

## 31. Preserved M020-M032 Authority

M020 through M032 remain `APPROVED_AND_FROZEN` at every stage, entirely untouched by this freeze mission. No frozen contract, source file, test file, governance document, schema, or migration belonging to any of those milestones was read for modification purposes or changed.

## 32. Deferred Work

Run retrieval (a future query-side milestone, mirroring M031's role); Run lifecycle transitions (a future command-side milestone, mirroring M032's role); `EvidencePackage`/`Review` creation; retry-on-`OptimisticConcurrencyConflict` policy; composition-root abstraction; transport; audit integration; MILESTONE-034 and beyond.

## 33. Final Status

**M033 DESIGN APPROVED_AND_FROZEN.**

## 34. Next Permitted Action

**MILESTONE-033 IMPLEMENTATION MISSION.**
