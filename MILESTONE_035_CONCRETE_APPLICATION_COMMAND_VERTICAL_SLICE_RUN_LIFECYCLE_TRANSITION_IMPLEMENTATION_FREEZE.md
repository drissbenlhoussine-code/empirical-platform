# MILESTONE-035 - Concrete Application Command Vertical Slice (Run Lifecycle Transition) Implementation Freeze

## 1. Document Status

**Status: FINAL — OWNER FROZEN**

This document is the Owner Implementation Freeze record for MILESTONE-035. It is authoritative.

## 2. Milestone Identity

MILESTONE-035 — Concrete Application Command Vertical Slice: Run Lifecycle Transition (Run Authorization), Implementation stage.

## 3. Repository Authority

| Field | Value |
| --- | --- |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Branch | `master` |
| HEAD at freeze | `1b42d8ac943175eb4e4c2fc064062054854dedd7` |

## 4. Frozen Predecessor Chain

| Milestone | Status |
| --- | --- |
| M020-M029 | APPROVED_AND_FROZEN |
| M030 (Campaign Creation) | APPROVED_AND_FROZEN |
| M031 (Campaign Retrieval) | APPROVED_AND_FROZEN |
| M032 (Campaign Lifecycle Transition) | APPROVED_AND_FROZEN |
| M033 (Run Creation) | APPROVED_AND_FROZEN |
| M034 (Run Retrieval) | APPROVED_AND_FROZEN (implementation freeze `3056e3010b4f20f3cf7bf2ab2e3fbbc43fcff825`) |

## 5. M035 Scope Authority

`MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE.md`, candidate `26aab1acb1d08150144b8ce52d63f17796f121ef`.

## 6. M035 Scope-Freeze Authority

`MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_SCOPE_FREEZE.md`, commit `cebbd945107f4242cada86eea29e210e7b7c701c`. **M035 SCOPE APPROVED_AND_FROZEN.**

## 7. M035 Design Authority

`MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_DESIGN.md`, candidate `bac7f202c4f6dca591702d4d1404a8390c4bb755`.

## 8. M035 Design-Freeze Authority

`MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_DESIGN_FREEZE.md`, commit `3227bba3d22756bc138cd45bbb0ac98824bc537c`. **M035 DESIGN APPROVED_AND_FROZEN.**

## 9. Implementation Commit

`1037876fac376238298c22cfae0b4d5b949ffaac` (`feat: implement M035 Run authorization usecase`).

## 10. Finalization Commit

`1b42d8ac943175eb4e4c2fc064062054854dedd7` (`docs: finalize M035 implementation review package`) — narrow, docs-only, recorded the implementation commit's own hash. No production behavior changed.

## 11. Independent Implementation-Review Authority

The final independent hostile implementation review reproduced: 24 passed focused unit/contract tests; 5 passed focused M035 PostgreSQL tests; 43 passed targeted PostgreSQL regression; 127 passed full integration suite (6 skipped); 712 passed full PostgreSQL opt-in suite (6 skipped, 92.38% coverage); 585 passed non-integration suite (133 deselected, 83.49% coverage); a passing architecture checker; a passing Ruff run (219 files formatted); a passing canonical mypy run (92 source files); a passing build and wheel inspection; passing security/pip-audit; 51/51 manifest verification; a `complete.diff` matching live repository bytes; and synchronized, clean repository truth.

## 12. Final Review Decision

**M035 IMPLEMENTATION APPROVED WITH NON-BLOCKING OBSERVATIONS.** No CRITICAL, MAJOR, or blocking MINOR finding remains. The implementation exactly realizes the frozen Run authorization command, preserves caller-supplied optimistic-concurrency semantics, independently proves the real `append_manifest()`-based PostgreSQL conflict path, introduces no secondary capability, and preserves every predecessor contract.

## 13. Owner Approval

The owner formally freezes the M035 implementation via this document.

**M035 IMPLEMENTATION APPROVED_AND_FROZEN.**

**M035 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

## 14. Frozen Production Surface

Exactly: `src/empirical_platform/usecases/authorize_run.py` (new); `src/empirical_platform/usecases/__init__.py` (export-only addition); `tests/unit/test_authorize_run_usecase.py`, `tests/contract/test_authorize_run_handler_contract.py`, `tests/integration/test_m035_authorize_run_usecase.py` (new); `MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_IMPLEMENTATION.md` (new); `PROJECT_CHECKPOINT.md` (updated). Seven files total across the implementation and finalization commits.

## 15. Frozen Command Contract

```python
@dataclass(frozen=True, slots=True)
class AuthorizeRunCommand:
    identity: DomainIdentity[RunId]
    expected_persisted_version: AggregateVersion
    actor: str
    occurred_at: datetime
    correlation_id: str | None = None
    reason: str | None = None
```

Exactly six fields, no `__post_init__`, passive typed carrier.

## 16. Frozen Handler Contract

```python
class AuthorizeRunHandler:
    __slots__ = ("_run_repository",)

    def __init__(self, *, run_repository: RunRepository) -> None:
        self._run_repository = run_repository

    def handle(self, command: AuthorizeRunCommand) -> SaveResult:
        loaded = self._run_repository.get(command.identity)
        run = loaded.aggregate
        run.authorize(
            actor=command.actor,
            occurred_at=command.occurred_at,
            correlation_id=command.correlation_id,
            reason=command.reason,
        )
        return self._run_repository.save(
            run, expected_persisted_version=command.expected_persisted_version
        )
```

Sole dependency: `RunRepository`. No `CampaignRepository`, `EvidencePackageRepository`, `ReviewRepository`, `Clock`, or persistence adapter.

## 17. Frozen Run Transition

`Run.authorize()`: `CREATED` → `AUTHORIZED`. No other Run lifecycle method appears in `authorize_run.py` — independently re-verified in this freeze via direct grep (Section 14 confirms no matches for `start_acquisition`/`start_normalization`/`start_validation`/`complete_execution`/`.cancel(`/`.fail(`).

## 18. Frozen Identity Semantics

`command.identity` passed unchanged to `RunRepository.get()` — proven by `test_get_is_called_exactly_once_with_exact_identity`.

## 19. Frozen Expected-Version Semantics

`command.expected_persisted_version` — never `loaded.persisted_version` — reaches `save()`. Proven with deliberately distinguishable values (`AggregateVersion(5)` vs. `AggregateVersion(0)`) by `test_save_receives_command_version_not_loaded_persisted_version`.

## 20. Frozen Load–Mutate–Save Sequence

1. Receive one `AuthorizeRunCommand`.
2. `RunRepository.get(command.identity)` exactly once.
3. `run.authorize(...)` exactly once using the command's own `actor`/`occurred_at`/`correlation_id`/`reason`.
4. `RunRepository.save(run, expected_persisted_version=command.expected_persisted_version)` exactly once.
5. Return the resulting `SaveResult` unchanged.

No second `get()`/`save()`. No `add()`/`delete()`. No retry. No Campaign/EvidencePackage/Review access. No application-level transaction orchestration.

## 21. Frozen Result Contract

Exactly the `SaveResult` produced by `save()`, returned unchanged — proven by `test_returned_object_is_the_exact_save_result`.

## 22. Aggregate-Version Semantics

`Run.version` advances by exactly one on `authorize()` — proven against a genuine `Run` aggregate by `test_successful_authorize_produces_exactly_one_transition_record`. Never conflated with `loaded.persisted_version` or `command.expected_persisted_version` anywhere in the implementation.

## 23. Persisted-Version Semantics

`loaded.persisted_version` is never passed to `save()` (Section 19). `SaveResult.persisted_version` is returned unchanged.

## 24. Transition-History Semantics

Exactly one `StateTransitionRecord` is appended on success (`from_state="CREATED"`, `to_state="AUTHORIZED"`, command's own `actor`/`correlation_id`/`reason`) — proven at unit level and independently against real PostgreSQL (Section 35).

## 25. Invalid-Transition Behavior

Domain `ValueError` propagates before `save()` is reached when the persisted state is not `CREATED` — proven at unit level (`test_domain_invalid_transition_propagates_and_save_never_called`) and against real PostgreSQL (Section 36).

## 26. Not-Found Behavior

Transparent, unchanged `AggregateNotFound` propagation — proven at unit level and against real PostgreSQL (Section 37).

## 27. Optimistic-Concurrency Behavior

Transparent, unchanged `OptimisticConcurrencyConflict` propagation — proven at unit level with the real exception type (`test_optimistic_concurrency_conflict_from_save_propagates_unchanged`) and genuinely reproduced against real PostgreSQL using the frozen deterministic mechanism (Section 28/38).

## 28. Deterministic Conflict Evidence

Independently re-verified in this freeze mission's own scope: `Run.append_manifest()` (the only Run mutator that advances `AggregateVersion` while preserving `RunLifecycleState`) serves as the interfering write on an independently-loaded second Run instance. This deliberately avoids the exact failure mode M032's own initial design mistakenly risked (an interfering transition invalidating the command-under-test's own domain precondition before the concurrency check could be reached). Genuinely reproduced against real PostgreSQL (`test_stale_expected_version_raises_optimistic_concurrency_conflict`), both during implementation and independently during the external-review package build. `append_manifest()`'s use is confined entirely to the test file — confirmed absent from `authorize_run.py` (Section 14).

## 29. Arbitrary Error Semantics

Transparent, unchanged propagation of arbitrary `get()`/`save()` exceptions — proven by dedicated fake-repository tests.

## 30. Validation Ownership

No `__post_init__` on `AuthorizeRunCommand`; no duplicated identifier, version, or domain-argument validation in the handler. `DomainIdentity` validates only the base identity-pair structure at runtime; `RunId` specialization is expressed statically only (M035 design-freeze correction, Section 9, preserved unmodified by this implementation).

## 31. Transaction Non-Ownership

No `run_composed()`, no unit-of-work, session, engine, or connection reference anywhere in `authorize_run.py`.

## 32. CommandEntryPoint Binding

Test-only direct construction; no production composition root exists anywhere in this change.

## 33. Architecture Preservation

Zero change to `tools/check_architecture.py`. `python tools/check_architecture.py .` passes at exit 0, independently reconfirmed in this freeze session.

## 34. Unit and Contract Evidence

29 new tests (21 unit, 3 contract, plus 5 PostgreSQL integration — Section 35-38) — all passing, reconfirmed at freeze time: `pytest tests/unit/test_authorize_run_usecase.py tests/contract/test_authorize_run_handler_contract.py tests/architecture/test_module_boundaries.py` → 26 passed (21 unit + 3 contract + 2 architecture; the independent review's own "24 passed" figure covers unit+contract only, excluding the 2 architecture tests — both figures are consistent, not contradictory, differing only in which fixed subset was run).

## 35. PostgreSQL Success Evidence

Independently reproduced (both in the implementation session and the external-review package build): `test_golden_path_authorizes_run_via_command_entry_point_and_real_repository` — golden-path `SaveResult`, persisted state/version, and transition-history record all verified against a real, freshly migrated database.

## 36. PostgreSQL Invalid-Transition Evidence

Independently reproduced: `test_invalid_transition_raises_domain_error_without_persisting` — the same command reused twice; the second attempt fails domain-validly with no persisted change.

## 37. PostgreSQL Missing-Run Evidence

Independently reproduced: `test_missing_run_raises_aggregate_not_found` — `AggregateNotFound` propagates unchanged for a never-persisted identity.

## 38. PostgreSQL Conflict Evidence

Independently reproduced: `test_stale_expected_version_raises_optimistic_concurrency_conflict` — the frozen thirteen-step `append_manifest()`-based sequence genuinely reaches `OptimisticConcurrencyConflict`; the persisted row is confirmed unchanged by the failed attempt.

## 39. PostgreSQL Regression Evidence

Full `tests/integration/` suite: 127 passed, 6 skipped (pre-existing MinIO/unified-runtime opt-in gating, unrelated to M035) — reconfirmed by the independent review.

## 40. Ruff, Typing, Build, and Security Evidence

`ruff check`/`format --check` clean (219 files formatted); canonical `mypy` clean (92 source files); `python -m build` succeeds with `authorize_run.py` present in the built wheel; `pip_audit` reports no known vulnerabilities; `secret_scan_targets.py` — see Section 43 for the precise count disposition.

## 41. External-Review Package Verification

`external-review/MILESTONE-035/MILESTONE-035-1b42d8a-external-review.zip`, SHA-256 `c42b0eb7d502fd20bd56893db2c6cf1de8d82d7a536fbe529ffe04a30509f12f` — independently re-verified against the live file in this freeze session (`python -c "hashlib.sha256(...)"` reproduced the identical hash). `manifest.sha256`: 51 entries, all verified OK. `complete.diff` byte-identical to a live regeneration against the same commit range. Package unchanged by this freeze mission, per its own authorization boundary.

## 42. Changed-File Summary

```
A  MILESTONE_035_CONCRETE_APPLICATION_COMMAND_VERTICAL_SLICE_RUN_LIFECYCLE_TRANSITION_IMPLEMENTATION.md
M  PROJECT_CHECKPOINT.md
M  src/empirical_platform/usecases/__init__.py
A  src/empirical_platform/usecases/authorize_run.py
A  tests/contract/test_authorize_run_handler_contract.py
A  tests/integration/test_m035_authorize_run_usecase.py
A  tests/unit/test_authorize_run_usecase.py
```

Plus this freeze document and a further `PROJECT_CHECKPOINT.md` update, added in this freeze mission per its own authorization.

## 43. Non-Blocking Findings

**M035-IMPL-REVIEW-0001 (MINOR, non-blocking) — secret-scan target count drift.** The implementation document (Section 31 table) reported **385** targets, written at implementation time. The independent review reproduced **386** targets. Independently re-verified genuine before recording (not taken on faith): the external-review package's own `evidence/security-secret-scan-targets.txt` (captured after the implementation session, during package assembly) already recorded 386 targets, and a fresh `python tools/secret_scan_targets.py --root .` rerun in this freeze session also produced 386 — confirming 386 is the reproducible, current-truth count, and 385 was a stale or momentarily-miscounted value in the implementation document's own table. **Disposition: `RESOLVED_BY_FREEZE_RECORD_CLARIFICATION`.** No source, test, or package correction is required or authorized; the security gate itself passed under both counts (no threshold was ever at risk), and the discrepancy is documentation/evidence-count drift only. Per this mission's own explicit instruction, the original implementation document is **not** rewritten to erase this historical statement — 385 remains as the historical implementation-time claim, and this freeze record is the authoritative source for the corrected, reproducible figure (386).

**M035-IMPL-REVIEW-0002 (OBSERVATION, non-blocking) — non-canonical mypy test-file artifact.** A non-canonical `mypy --explicit-package-bases` per-test-file invocation reports two "unused type: ignore" findings in `tests/unit/test_authorize_run_usecase.py`. This is the identical, already-documented pattern shared with every prior milestone's test files (M031, M034) under the same non-canonical invocation — canonical `mypy` (`packages = ["empirical_platform"]`, `src/` only) does not cover test files and passed cleanly. **Disposition: `ACCEPTED_NON_BLOCKING_TEST_HYGIENE_OBSERVATION`.** The reviewed type-ignore comments are **not** removed during this freeze, per explicit instruction; this is recorded as optional future test-hygiene work, not a defect requiring correction now.

**M035-IMPL-REVIEW-0003 (OBSERVATION, non-blocking) — transient tooling friction during review.** The independent review's initial security/verification attempts encountered an unintended interpreter selection or a transient PyPI DNS failure; final canonical reruns under the repository's own Python 3.13.14 `.venv` environment passed cleanly (Section 40). **Disposition: `RESOLVED_BY_SUCCESSFUL_CANONICAL_RERUN`.** No configuration or source change is required or authorized.

## 44. Finding Disposition

None of the three findings above affects behavior, architecture, PostgreSQL correctness, or package integrity, and none blocks Owner Freeze. All three are non-blocking and require no code, test, checker, package, or governance-authority change beyond the clarifications recorded in Section 43 itself.

## 45. No-Scope-Creep Declaration

No second Run transition, Run mutation beyond `authorize()`, `EvidencePackage`/`Review` work, generic save/concurrency framework, composition root, registry, dispatcher, mediator, service locator, DI framework, transport/API layer, caching, retry policy, audit integration, schema/migration change, or MILESTONE-036 work exists anywhere in this implementation.

## 46. Preserved M020-M034 Authority

No change to any M020-M034 frozen contract, source file, test, or governance document. No change to M035 scope/design authority. All prior authority remains exactly as previously frozen.

## 47. Owner Freeze Declaration

**M035 IMPLEMENTATION APPROVED_AND_FROZEN.** The implementation delivered in commits `1037876`/`1b42d8a`, exactly as verified in Sections 34-41 above, is the final, frozen implementation of MILESTONE-035.

**M035 is now APPROVED_AND_FROZEN at every stage — scope, design, and implementation.**

## 48. Deferred Work

- A second Run lifecycle-transition command — future milestone, once evidenced.
- `EvidencePackage`/`Review` creation and retrieval.
- Retry-on-`OptimisticConcurrencyConflict` policy — now evidenced by two independently-proven save()-based commands (M032, M035), but still not authorized by any frozen scope.
- Read-to-update `expected_persisted_version` acquisition for a real caller workflow (M034's own known limitation, unchanged).
- Any composition-root abstraction beyond direct binding.
- Optional future test-hygiene cleanup of the two non-canonical-scope type-ignore comments (M035-IMPL-REVIEW-0002).
- MILESTONE-036 and beyond.

## 49. Macro Milestone Protocol Activation

Effective from MILESTONE-036 onward, the owner activates the following standing workflow policy:

```
MACRO_MILESTONE_PROTOCOL_ACTIVE_FROM=MILESTONE-036
```

**Normal future workflow, one milestone at a time:**

1. **One Complete Macro Milestone Mission** (Claude Code): predecessor freeze if required; repository truth; architecture inventory; scope selection; hostile scope self-audit; design; hostile design self-audit; implementation; unit/contract/PostgreSQL tests; validation; governance; external-review package; manifest/ZIP; commits and push.
2. **One Complete Independent Hostile Milestone Review** (Codex or equivalent): scope; design; implementation; tests; PostgreSQL; architecture; typing/build/security; governance; package integrity.
3. **If correction is required:** one narrow correction mission, followed by one final independent re-review.
4. **Owner Freeze:** normally recorded at the start of the next Macro Milestone mission, or through a final narrow freeze mission when no next milestone begins.

This policy is a **workflow consolidation**, not a governance weakening. It does **not** reduce, skip, or soften: repository-truth verification gates; independent review; live PostgreSQL evidence requirements; architecture-checker validation; external-review package requirements; manifest/ZIP integrity verification; or owner freeze authority. Every gate this milestone (and M030-M034 before it) already required remains required — only the granularity of how many separate owner messages are used to invoke each stage may consolidate going forward.

This freeze mission does **not** create any M036 scope, design, or implementation artifact — that begins with MILESTONE-036's own first mission under this newly activated protocol.

## 50. Final Status

**M035 APPROVED_AND_FROZEN** — scope, design, and implementation, at every stage.

M036: NOT_STARTED. `MACRO_MILESTONE_PROTOCOL_ACTIVE_FROM=MILESTONE-036`.

## 51. Next Permitted Action

**MILESTONE-036 COMPLETE MACRO MILESTONE MISSION.**
