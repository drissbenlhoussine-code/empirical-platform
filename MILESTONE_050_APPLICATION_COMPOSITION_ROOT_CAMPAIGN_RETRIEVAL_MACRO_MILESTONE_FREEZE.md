# MILESTONE-050 - Application Composition Root: Real End-to-End Campaign Retrieval - Macro Milestone Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Freeze record for MILESTONE-050, the project's first cross-cutting application/platform-integration milestone, produced under the Macro Milestone Protocol (M035 implementation freeze, Section 49; PROJECT_CHECKPOINT.md Section 31). It is authoritative.

## 2. Milestone Identity

MILESTONE-050 — Application Composition Root: Real End-to-End Campaign Retrieval.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze (pre-freeze-commit) | `9a1331c9c1d7e3c362fa835f9856e8a5ea1150d1` |
| origin/master at freeze (pre-freeze-commit) | `9a1331c9c1d7e3c362fa835f9856e8a5ea1150d1` (0/0, clean tree) |

## 4. Frozen Predecessor Chain

M020-M049 all `APPROVED_AND_FROZEN` at every stage. M049 Owner Freeze: `MILESTONE_049_REVIEW_CANCELLATION_MACRO_MILESTONE_FREEZE.md`, freeze commit `3ae497c32dd93579409f6a156391196ce910ec82`, hash-recording commit `f8a2e6c4b8c98150fc0cc99e481ade605ce88048` — this is M050's own starting baseline.

## 5. Scope Authority

`MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_SCOPE.md` — the project's first deliberate strategic pivot away from isolated domain vertical slices. A fresh, complete architecture inventory (Section 3) independently confirmed: every remaining domain-completion candidate (`EvidencePackage.invalidate()`, `Run.cancel()`, any Campaign/Run forward transition) repeats an already-proven single-state mechanism shape; zero production code anywhere had ever composed a real settings→service→repository→handler→result chain — all 21 frozen handlers (M030-M049) had only ever been invoked from hand-wired test fixtures; "composition root" had been named in the Deferred Work/Out-of-Scope section of 18 consecutive milestones (M032-M049). Mandatory leverage reassessment (Section 4) answered **yes** — platform integration now has higher leverage than another domain transition.

## 6. Design Authority

`MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_DESIGN.md` — `run_get_campaign()` owns the entire composition and the sole unit of work; `main()` performs only CLI-argument-count validation and delegates, catching nothing, mirroring `health.py`'s own complete absence of exception handling. Composition Boundaries (Section 6) defines the exact resource-lifecycle shape, corrected in place after the first independent review (see Section 9 below).

## 7. Implementation Commit

`e5d65385f01b6617657bc86d24426f6dec8babf2` (`feat: implement M050 application composition root (Campaign retrieval)`).

## 8. Original Finalization Commit

`f452c5c1db50570bb7abca02a6412ee075199a9b` (`docs: finalize M050 macro milestone review package`) — narrow, checkpoint-only, recorded the implementation commit's own hash. Reviewed by the first independent hostile macro review (Section 9).

## 9. First Independent Review — Finding M050-Y-1 and Correction Lineage

The first independent hostile macro review (27-phase mission, against implementation commit `e5d6538`/finalization commit `f452c5c`) found one MAJOR, Owner-Freeze-blocking defect and returned **M050 MACRO MILESTONE REQUIRES CORRECTION**:

- **M050-Y-1.** `service.initialize()` was called *before* the `try:` block opened in `run_get_campaign()`, so `finally: service.close()` never ran when `initialize()` itself raised (unreachable/misconfigured database). The reviewer independently reproduced this: `close()` call count of zero against a controlled `initialize()` failure. This directly contradicted the scope document's own claim (Section 11, pre-correction) that cleanup was guaranteed "regardless of success or failure."

**Correction applied** (commit `83043d4a4b83222bc5a75fefaa22a0b466b6be54`, `fix: close M050 persistence service on initialization failure`): `service.initialize()` moved one line, from immediately before the `try:` to the first statement inside it. No other production line changed; no new abstraction, context manager, resource-manager framework, or exception policy was introduced. Three new focused unit tests added, one of which (`test_run_get_campaign_closes_service_when_initialize_raises`) was independently confirmed — by both the author and, separately, by the corrected-candidate re-review — to genuinely **fail** against the pre-correction source and **pass** against the corrected source.

**Corrected finalization commit** `9a1331c9c1d7e3c362fa835f9856e8a5ea1150d1` (`docs: finalize corrected M050 macro review package`) — recorded the correction commit's own hash. This is the HEAD this freeze is authorized against.

## 10. Second Independent Review — Re-Review Authority

A fresh, independent hostile macro re-review (covering both the original mission and the M050-Y-1 correction, not merely the correction in isolation) independently re-derived: repository truth and full commit lineage; the correction delta (`git diff f452c5c..9a1331c`, exactly 6 files, a minimal 2-line production change); a fresh, non-reused reproduction of the pre-fix defect (temporarily restoring `f452c5c`'s source into the working tree, confirming `close() call count: 0` via an independently-authored probe); a more thorough post-fix probe than the author's own evidence, additionally instrumenting `PostgresRepositoryRuntime.__init__` to independently prove zero downstream composition work occurs after a failed `initialize()`; independent re-execution of the actual pytest defect test against both pre-fix and post-fix checked-out source (FAILED, then PASSED); close-failure semantics classified **SOUND** (no overclaiming — governance correctly states `close()`'s own exception would become the active one under Python's ordinary `finally` semantics, not that the original is preserved); an unbiased re-run of the strategic-pivot assessment (unchanged conclusion); a **second, independently-chosen failure mode** — real credential rejection against a live listening PostgreSQL server, not merely connection-refused — confirming `close()` still called exactly once; five fresh architecture negative probes (all correctly rejected); full regression and toolchain re-verification on a third, independently-provisioned disposable container, zero drift from every reported number; and independent package-integrity verification (ZIP hash recomputed from disk, fresh extraction, manifest, `complete.diff`, and every packaged file confirmed byte-identical to live git blobs).

## 11. Review Decision

**M050 CORRECTED MACRO MILESTONE APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL or MAJOR finding survived independent verification. Exactly one MINOR, explicitly non-blocking observation was recorded (Section 25 below).

## 12. Owner Approval

The owner formally freezes the M050 macro milestone via this document.

**M050 MACRO MILESTONE APPROVED_AND_FROZEN.**

**M050 APPROVED_AND_FROZEN** — scope, design, and implementation (as corrected), at every stage, frozen as one consolidated unit per the Macro Milestone Protocol.

## 13. Frozen Production Capability

Exactly one: a real, production `entrypoints.get_campaign` composition root — `run_get_campaign()` and its thin `main()` CLI wrapper (`src/empirical_platform/entrypoints/get_campaign.py`) — composing, for the first time in production code, real configuration resolution, a real PostgreSQL persistence service, the frozen M025 `PostgresRepositoryRuntime`, and the frozen M031 `GetCampaignHandler`/`GetCampaignQuery`/`QueryEntryPoint` into one real, invocable flow, registered as the `empirical-platform-get-campaign` console script. No second entrypoint, no composition of any command/query beyond `GetCampaignQuery`.

## 14. Frozen Production Source

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

## 15. Resource Lifetime (Frozen, Corrected Shape)

```
construct service

try
    initialize
    runtime / handler / entry point / query
finally
    close
```

Exactly one `PostgresPersistenceService` construction, exactly one `.initialize()` call, exactly one `.close()` call, exactly one `PostgresRepositoryRuntime` construction, per invocation — independently re-confirmed by count at both freeze time and the corrected-candidate re-review. `.close()` is attempted regardless of whether initialization, repository/handler/entry-point composition, or the query call succeeds or fails. No retry, no duplicate initialize/close, no exception translation, no hidden framework dependency.

## 16. Allowed Dependencies

Exactly five already-frozen production symbols: `resolve_foundation_config`/`PostgreSQLConfigSnapshot` (foundation), `PostgresPersistenceService` (M008/M023), `PostgresRepositoryRuntime` (M025), `GetCampaignHandler`/`GetCampaignQuery`/`CampaignSnapshot` (M031), `QueryEntryPoint` (M029) — plus `DomainIdentity`/`CampaignId`/`RuntimeIdentifier` value objects (foundation). None modified.

## 17. Architecture Impact (Frozen)

`ALLOWED["entrypoints"]` extended from `{"shared", "application"}` to `{"shared", "application", "identifiers", "usecases"}`. New `FORBIDDEN_IMPORT_PREFIXES["entrypoints"]` entry forbids exactly `sqlalchemy`, `psycopg`, `boto3`, deliberately excluding `empirical_platform.shared.persistence`. `entrypoints` does not appear in any other module's `ALLOWED` set — nothing may import it; the inward-dependency direction is fully preserved, independently re-confirmed via five fresh negative probes at re-review (entrypoints→psycopg, entrypoints→sqlalchemy, entrypoints→campaign, usecases→entrypoints, campaign→entrypoints — all five correctly rejected). `python tools/check_architecture.py .` exit 0. This architecture-checker delta is unchanged by the M050-Y-1 correction (`git diff f452c5c..9a1331c -- tools/check_architecture.py` is empty).

## 18. Exception Semantics (Frozen)

Zero exception translation anywhere in `run_get_campaign()`. `AggregateNotFound`, `ValueError`/`TypeError` from malformed identifiers, `FoundationError` from configuration or connectivity failure — all propagate to the caller with exact instance identity. `main()` contains no `try`/`except` of any kind. `PostgresPersistenceService.close()` (frozen since M008/M023, unmodified) has no `try`/`except` of its own; if it were to raise mid-unwind, ordinary Python `finally` semantics apply — `close()`'s exception becomes the actively propagating one, with the original attached via `__context__`. This is pre-existing behavior, not a new policy introduced by M050 or its correction.

## 19. Configuration Boundary (Frozen)

`config` defaults to `None`, resolving via `resolve_foundation_config().postgresql` against real `EMPIRICAL_PLATFORM_POSTGRES_*` environment variables — independently re-confirmed via a real, unmocked environment-driven test. No hard-coded credentials anywhere in `get_campaign.py`.

## 20. PostgreSQL Evidence

Independently reproduced across implementation, original review, correction, and re-review, each on a freshly provisioned, uniquely-named/ported, never-reused `postgres:17` container: M050 focused integration — golden path, `AggregateNotFound`, `ValueError`, environment-default resolution — **4 passed**, every time. Initialization-failure resource-lifecycle evidence independently reproduced against two distinct real failure modes (connection-refused on an unreachable port, and credential rejection against a live listening server) — `close()` called exactly once in both, zero times pre-fix.

## 21. Full Regression Evidence

Independently reproduced at implementation time, correction time, and re-review time, zero drift each time: focused unit **10 passed** (up from 7 pre-correction); M050 focused PostgreSQL 4 passed; M031 Campaign-retrieval regression 3 passed; non-integration suite **927 passed**, 213 deselected, coverage 84.96%; full integration suite **207 passed**, 6 skipped; full suite with PostgreSQL **1134 passed, 6 skipped, coverage 93.70%** (up from 1131 pre-correction, up from 1120 pre-M050).

## 22. Ruff/Mypy/Build/Security Evidence

`ruff format --check` / `ruff check`: clean, 282 files. Canonical bare `mypy`: 107 source files, 0 issues. `python -m build --wheel`: succeeds; wheel contains `entrypoints/get_campaign.py`; `empirical-platform-get-campaign` correctly registered under `[console_scripts]`; smoke import succeeds. `pip-audit`: no known vulnerabilities. Secret-scan: 509 tracked files, 0 findings — independently reconciled (500 M049 baseline + 9 new M050 files; the correction introduced zero new tracked files).

## 23. Package Integrity

`external-review/MILESTONE-050/MILESTONE-050-9a1331c-external-review.zip` — SHA-256 `a66484132c921fef14c02de5bfdbaeae25a4a63efab78859668344cbf75e89c8`, independently recomputed and matched at package-build time and re-review time (including a fresh extraction). 33 entries, no duplicates, no unsafe paths, no self-inclusion. `manifest.sha256`: 32/32 verified, including from a fresh extraction. `complete.diff` (spanning `f8a2e6c..9a1331c`, the full M049 baseline to the corrected finalization HEAD): byte-identical to a fresh `git diff` regeneration of the exact same commit range, independently confirmed twice (package build and re-review). All packaged `source/`/`tests/`/`governance/` files, including `PROJECT_CHECKPOINT.md` and the Macro Implementation document, independently confirmed byte-identical to live git HEAD blobs.

## 24. Changed-File Surface

```
A  MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_DESIGN.md
A  MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_IMPLEMENTATION.md
A  MILESTONE_050_APPLICATION_COMPOSITION_ROOT_CAMPAIGN_RETRIEVAL_MACRO_SCOPE.md
M  PROJECT_CHECKPOINT.md
M  pyproject.toml
A  src/empirical_platform/entrypoints/get_campaign.py
M  tests/architecture/test_module_boundaries.py
A  tests/fixtures/illegal_imports/src/empirical_platform/entrypoints/bad_boto3_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/entrypoints/bad_psycopg_import.py
A  tests/fixtures/illegal_imports/src/empirical_platform/entrypoints/bad_sqlalchemy_import.py
A  tests/integration/test_m050_get_campaign_entrypoint.py
A  tests/unit/test_get_campaign_entrypoint.py
M  tools/check_architecture.py
```

Exactly thirteen files, spanning the full M049 baseline to the corrected finalization HEAD — identical footprint to the original mission; the M050-Y-1 correction introduced zero new files, editing only already-new-in-M050 files. Independently re-confirmed via `git diff --name-status` at both the original review and the re-review, byte-for-byte identical to the external-review package manifest.

## 25. Known Non-Blocking Observation

The Macro Implementation document (`MILESTONE_050_..._MACRO_IMPLEMENTATION.md`) contains one cosmetic section-numbering gap: headers run `## 9.`, `## 10.`, `## 12.`, `## 13.` — `## 11.` does not exist (an authoring slip when the correction record was inserted). No cross-reference in any other document points at the missing number; every reference to the correction record correctly cites "Section 12," which exists and contains the intended content. **Non-blocking. No production impact.** Left uncorrected in this freeze as immaterial; may be tidied at a future governance touch.

## 26. No Scope Creep

No generic command/query dispatcher, registry, or handler-discovery mechanism; no retry-on-conflict policy; no transport/HTTP/API layer; no schema/migration change; no composition of any command/query beyond `GetCampaignQuery`; no context-manager/resource-manager framework, service locator, or DI container introduced by the correction; no MILESTONE-051 work anywhere in this milestone — independently re-confirmed via full-delta grep sweeps at implementation, original review, correction, and re-review.

## 27. Preserved M020-M049 Authority

No change to any M020-M049 frozen contract, source file, test, or governance document, and no change to `GetCampaignHandler`/`GetCampaignQuery`, `QueryEntryPoint`, `PostgresRepositoryRuntime`, or `PostgresCampaignRepository` — independently re-confirmed via `git diff f8a2e6c..9a1331c` restricted to `src/empirical_platform/{campaign,run,evidence,review}/`, `usecases/`, `shared/persistence/postgres_repositories/`, `application/`, and `migrations/`, returning zero matches outside the explicitly authorized architecture-checker files.

## 28. Owner Freeze Declaration

**M050 MACRO MILESTONE APPROVED_AND_FROZEN.** The implementation delivered in commit `e5d6538`, originally finalized in commit `f452c5c`, corrected for finding M050-Y-1 in commit `83043d4`, and finalized in corrected form in commit `9a1331c`, exactly as independently re-verified across two independent hostile reviews (Sections 9-10 above), is the final, frozen implementation of MILESTONE-050.

## 29. Deferred Work

`EvidencePackage.invalidate()`; `Run.cancel()`; remaining Run forward-pipeline transitions; other Campaign lifecycle transitions; composition of any of the remaining 20 already-frozen command/query handlers; retry-on-conflict policy; transport/HTTP/API layer; a generic dispatcher/registry mechanism; MILESTONE-051 and beyond.

## 30. M051 Boundary

This freeze authorizes work through MILESTONE-050 only. No MILESTONE-051 capability, terminology, sequencing decision, or forward commitment is made anywhere in this document. Section 29's "Deferred Work" is descriptive of currently-visible future candidates, not a binding selection of MILESTONE-051's scope.

## 31. Final Status

**M050 APPROVED_AND_FROZEN** — scope, design, and implementation (as corrected), at every stage.

With M050's completion, the project has, for the first time, a real production code path proving that its already-frozen application-layer handlers can be composed and invoked as a genuine, running program.

M051: NOT_STARTED (pending this freeze's completion).

## 32. Next Permitted Action

**MILESTONE-051 COMPLETE MACRO MILESTONE MISSION.**
