# MILESTONE-050 - Application Composition Root: Real End-to-End Campaign Retrieval - Macro Scope

## 1. Document Status

**Status: CANDIDATE_INTERNAL_MACRO_SCOPE**

Produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31) as part of one consolidated M050 mission: scope, design, and implementation together, followed by one independent review checkpoint.

**This document represents the first deliberate strategic pivot in the project's history — away from adding another isolated domain vertical slice, and toward the first cross-cutting application/platform-integration capability. Section 4 below performs the mandated leverage reassessment from repository truth, not from precedent.**

## 2. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| M050 frozen baseline | `f8a2e6c4b8c98150fc0cc99e481ade605ce88048` (the final M049 Owner Freeze hash-recording HEAD; M049 fully `APPROVED_AND_FROZEN` at scope, design, and implementation) |

## 3. Fresh, Complete Architecture Inventory

### 3.A Domain-Completion Remaining Gaps

| Aggregate | Domain methods | Proven | Unproven |
| --- | --- | --- | --- |
| Campaign | 8 | 2 (`prepare_for_authorization`, `cancel`) | 6 |
| Run | 8 | 2 (`authorize`, `fail`) | 6 |
| EvidencePackage | 5 | 4 | 1 (`invalidate`) |
| Review | 4 | 4 | 0 — **complete** |

Review reached 100% application-layer coverage at M049. All remaining domain-completion candidates (`EvidencePackage.invalidate()`, `Run.cancel()`, any Campaign/Run forward transition) are architecturally repetitive: every remaining Campaign/Run transition is a single-state, unconditionally-validated `_transition()` call — a shape independently proven correct at least 9 times already (M030, M031, M032, M033, M034, M035, M036-M041, M042-M046, M047, M048, M049). `EvidencePackage.invalidate()` would be the third proof of its aggregate's already-established single-state mechanism, with no genuine interfering write reachable from `SEALED` (independently re-confirmed during the M049 review). No remaining domain-completion candidate exercises any mechanism not already proven multiple times over.

### 3.B Platform/Application-Integration Gaps — Independently Verified from Live Source

A direct inspection of `src/empirical_platform/entrypoints/`, `src/empirical_platform/application/`, and every production (non-test) file in the repository found:

- **Zero production code anywhere constructs a real, working chain from configuration to a command/query result.** Every one of the 21 command/query handlers built across M030-M049 has only ever been invoked from test fixtures that manually construct `PostgresPersistenceService`, the repository adapters, the handler, and the entry point, inline, by hand. No such wiring exists in `src/`.
- `src/empirical_platform/entrypoints/` contains exactly two production entrypoints: `health.py` and `version.py` (both frozen, both registered as `[project.scripts]` in `pyproject.toml`). Neither touches persistence, a repository, a handler, or an entry point.
- `src/empirical_platform/shared/persistence/postgres_repositories/runtime.py` (`PostgresRepositoryRuntime`, frozen since M025) already composes the four concrete PostgreSQL repository adapters over one shared `PostgresPersistenceService` — but nothing in production code ever constructs a `PostgresRepositoryRuntime` and hands one of its repositories to a real handler.
- `src/empirical_platform/shared/config/settings.py` already has a fully-frozen, working `resolve_foundation_config()` function that resolves a `FoundationConfigSnapshot` — including a `.postgresql: PostgreSQLConfigSnapshot` field — directly from the same `EMPIRICAL_PLATFORM_POSTGRES_*` environment variables every integration test's own fixtures already read by hand. This is directly usable to construct a `PostgresPersistenceService` without any adapter work. (A second, older, unrelated settings system — `load_settings()`/`Settings`, used only by `health.py` — carries a single opaque `database_url: str` field and cannot construct a `PostgreSQLConfigSnapshot` without new adapter code; `resolve_foundation_config()` is the correct mechanism, independently confirmed by direct inspection of both.)
- `registry/`, `audit/`, `governance/` remain literal empty stub packages (`"No business behavior is implemented."`) — confirmed unchanged since their respective placeholder milestones.
- `retry`, `composition root`, `transport-neutral invocation`, and `registry/dispatcher` have been named in the "Deferred Work" or "Out-of-Scope" section of **every single milestone from M032 through M049** — eighteen consecutive milestones — always deferred, never built, never even attempted as a narrow slice.

## 4. Mandatory Leverage Reassessment

**Question posed by this mission: "Has the project reached the point where another isolated domain transition has lower leverage than the first cross-cutting application/platform integration capability?"**

**Answer, derived from Section 3 above, not from precedent: yes.**

Reasoning:

1. **Diminishing domain-transition returns.** Every remaining domain-completion candidate repeats an already-proven mechanism shape. None would prove anything new about the domain layer.
2. **A completely unproven, load-bearing axis.** In eighteen milestones, zero production code has ever demonstrated that this system's 21 already-frozen, already-fully-tested command/query handlers can be invoked as a real, running program rather than as test-fixture-internal Python objects. This is not a stylistic gap — it means the system, as it stands, **cannot currently be operated by anyone who is not directly editing test files**, regardless of how many additional domain transitions are proven.
3. **Every future milestone — domain or platform — will eventually need this exact capability.** Building it now, narrowly, removes a blocking dependency for all subsequent work, rather than deferring it indefinitely while the domain-transition backlog grows.
4. **A safe, already-de-risked foundation exists.** `PostgresRepositoryRuntime` (M025) and `resolve_foundation_config()` (foundation milestone) are already frozen, already correct, and already used correctly in every integration test's own fixtures — this milestone does not need to invent new infrastructure, only wire two already-frozen pieces together for the first time in production code.
5. **The risk of over-building is real and must be actively resisted** (Section 6, Rejected Alternatives) — this scope deliberately selects the single narrowest possible slice, not a general framework.

**This milestone is the first platform-integration milestone in the project's history.**

## 5. Selected Scope

One concrete, narrow composition: a real, production `entrypoints.get_campaign` module that composes — for the first time in production code — `resolve_foundation_config()` → `PostgresPersistenceService` → `PostgresRepositoryRuntime` (M025) → the already-frozen `GetCampaignHandler`/`GetCampaignQuery`/`CampaignSnapshot` (M031) → the already-frozen `QueryEntryPoint` (M029), invocable as a real CLI command (mirroring `health.py`/`version.py`'s own established minimal style, registered as a new `[project.scripts]` entry) and proven end-to-end against real PostgreSQL.

**Zero new business capability.** Every domain type, command/query, handler, repository, and entry point this milestone touches is already frozen and unmodified. This milestone adds only the missing composition glue between already-proven pieces — the narrowest possible slice that proves the architectural direction (real settings resolution → real service construction → real repository composition → real handler invocation → real result), reusable as a template for composing the remaining 20 handlers in later milestones, none of which are built here.

## 6. Rejected Alternatives

- **A generic command/query dispatcher or registry** (map any command type to its handler dynamically) — rejected as premature framework-building; this milestone proves the wiring pattern for exactly one already-existing query, explicitly, by hand, with no reflection, no dynamic handler discovery, and no registry lookup.
- **Composing all 21 existing handlers in one milestone** — rejected; would violate the one-capability-per-milestone discipline this project has maintained since M030, and would make the independent review's job of exhaustively verifying every wire disproportionate to the value of proving the pattern once.
- **A full HTTP/transport-layer API** — rejected as premature; a CLI entrypoint mirroring the already-frozen `health.py`/`version.py` pattern is the narrowest possible real invocation surface, introduces no new dependency (no web framework), and is sufficient to prove genuine end-to-end operability.
- **Retry-on-conflict policy** — rejected; orthogonal to this milestone's goal (proving composition, not resilience), and every prior milestone has correctly deferred it as a separate, later concern.
- **`EvidencePackage.invalidate()` / `Run.cancel()` / any remaining domain transition** — rejected per Section 4's leverage reassessment; would repeat an already-proven mechanism shape rather than close the single largest, completely unproven gap in the project.
- **A write command as the first composition slice (e.g., composing `CancelReviewCommand`)** — rejected in favor of a read-only query: `GetCampaignQuery` has no `expected_persisted_version`/optimistic-concurrency dimension, no side effects, and the lowest possible blast radius for a genuinely first-of-its-kind composition proof; a write-side composition slice is a natural, well-motivated candidate for a **future** milestone, once the read-side pattern is independently reviewed and frozen.

## 7. In-Scope

- `src/empirical_platform/entrypoints/get_campaign.py`: a `run_get_campaign()` composition function (settings → service → repository runtime → handler → entry point → result, with deterministic cleanup) and a thin `main()` CLI wrapper (argument parsing, JSON output), mirroring `health.py`'s own `<payload-function>`/`main()` split.
- One new `[project.scripts]` entry: `empirical-platform-get-campaign`.
- A narrow, justified architecture-checker change: add `identifiers` and `usecases` to `ALLOWED["entrypoints"]` (required to import `DomainIdentity`/`CampaignId` and `GetCampaignQuery`/`GetCampaignHandler`/`CampaignSnapshot`); add a new `FORBIDDEN_IMPORT_PREFIXES["entrypoints"]` entry forbidding direct `sqlalchemy`/`psycopg`/`boto3` imports (entrypoints may compose already-built `shared.persistence` adapters, but may never import a raw persistence driver library directly — the identical discipline already enforced on every other package).
- Corresponding architecture-fixture maintenance (new negative-import fixtures for `entrypoints`, extending the existing test assertions).
- Focused unit tests for the CLI argument-parsing/error-handling layer (using a fake/stub composition function, never touching real persistence).
- A real PostgreSQL integration test exercising `run_get_campaign()` itself end-to-end (found and not-found cases) against a fresh disposable container.

## 8. Out-of-Scope

- Any new business/domain capability of any kind (no new command, no new query, no domain-method change).
- Composition for any command/query beyond `GetCampaignQuery`.
- A generic dispatcher, registry, or handler-discovery mechanism.
- Retry-on-conflict policy, transaction orchestration beyond what `PostgresPersistenceService`/`PostgresRepositoryRuntime` already provide.
- Any transport/HTTP/API layer.
- Any change to `Campaign`, `CampaignRepository`, `PostgresCampaignRepository`, `GetCampaignQuery`, `GetCampaignHandler`, `CampaignSnapshot`, `PostgresRepositoryRuntime`, `resolve_foundation_config`, or any other already-frozen contract.
- Any schema/migration change.
- MILESTONE-051 work of any kind.

## 9. Frozen Dependencies

`GetCampaignQuery`/`GetCampaignHandler`/`CampaignSnapshot` (M031), `PostgresCampaignRepository` (M023), `PostgresRepositoryRuntime` (M025), `PostgresPersistenceService` (M008/M023), `resolve_foundation_config`/`FoundationConfigSnapshot`/`PostgreSQLConfigSnapshot` (foundation milestones), `QueryEntryPoint` (M029), `DomainIdentity`/`CampaignId`/`RuntimeIdentifier` (M020/foundation) — all unmodified.

## 10. Failure Model

`run_get_campaign()` performs no exception translation. `AggregateNotFound` (missing Campaign), configuration errors (`FoundationError` from `resolve_foundation_config()`/`sqlalchemy_url()` if misconfigured), and any repository/connectivity failure propagate to the caller unchanged — the CLI wrapper (`main()`) is the only layer that ever catches an exception, and only to print a clean, single-line error message and exit non-zero, mirroring ordinary CLI tool behavior; it never suppresses, retries, or translates the underlying exception's meaning.

## 11. Persistence/Transaction Implications

`PostgresPersistenceService` is constructed once per invocation, and the entire lifetime of that service — including its own `.initialize()` call — is owned by one `try`/`finally` block whose `finally` clause unconditionally calls `.close()`, guaranteeing `.close()` is attempted regardless of whether initialization, repository composition, or query handling succeeds or fails. (An earlier candidate revision of this milestone called `.initialize()` before the `try` opened, so a failure during initialization itself bypassed `.close()` entirely; this was caught by independent hostile review as finding M050-Y-1, empirically reproduced — `close()` call count of zero on a failed `initialize()` — and corrected by moving `.initialize()` inside the `try`. No new resource-management abstraction was introduced; this is the same `try`/`finally` shape every integration test's own fixtures already use, now drawn around the correct boundary.) No new transaction primitive is introduced; `GetCampaignHandler`'s own single `get()` call is the entire unit of work, exactly as already frozen since M031.

## 12. Risks

- This is the first milestone to introduce a production code path that touches real persistence outside a test file — the independent review must scrutinize this composition with at least the same rigor as any domain transition's own `get()`/mutate/`save()` sequence, even though no domain mutation occurs.
- The two parallel settings systems (`load_settings()`/`Settings` vs. `resolve_foundation_config()`/`FoundationConfigSnapshot`) are a pre-existing architectural inconsistency, not introduced by this milestone; this scope deliberately does not attempt to unify or refactor them, only correctly selects the mechanism that actually produces a usable `PostgreSQLConfigSnapshot` — disclosed here, not silently worked around.
- CLI argument parsing for two required string identifiers (`campaign_governance_id`, `campaign_runtime_id`) must fail cleanly on missing/malformed input, relying on the already-frozen `CampaignId`/`RuntimeIdentifier` value objects' own `__post_init__` validation rather than duplicating validation logic in the entrypoint.

## 13. M051 Boundary

This scope selects exactly one MILESTONE-050 capability. No MILESTONE-051 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. In particular, this scope does **not** commit to composing any further command/query in M051 — the next milestone's own scope mission must independently re-derive the next highest-leverage capability, exactly as this document did.

## 14. Hostile Self-Review

Every claim in Section 3.B was independently verified by direct source inspection during this scope mission, not assumed from memory: `find`/`grep` confirmed `entrypoints/` contains only `health.py`/`version.py`; `grep` across all of `src/` for `PostgresCampaignRepository(`/`PostgresRunRepository(`/`PostgresReviewRepository(`/`PostgresEvidencePackageRepository(` found only `shared/persistence/postgres_repositories/runtime.py` as a production constructor (all other matches are test files); `pyproject.toml`'s `[project.scripts]` section was read directly, confirming exactly two registered console scripts; the `registry`/`audit`/`governance` stub docstrings were read directly, confirming their unchanged placeholder text; and a full-history `git log` grep across every M032-M049 governance document's "Deferred Work"/"Out-of-Scope" section confirmed "composition root" and equivalent phrasing recurs in each. No hidden design, implementation, sequencing, or governance decision is present in this document; all detailed load-bearing decisions (exact composition function signature, exact architecture-checker changes, exact test strategy) are deferred to the Design section of this same consolidated mission.

## 15. Status

**CANDIDATE_INTERNAL_MACRO_SCOPE.**
