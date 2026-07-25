# MILESTONE-020 - Domain Repository and Concurrency Contract Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-020-FREEZE |
| Title | Domain Repository and Concurrency Contract Freeze |
| Version | 1.0 |
| Status | APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Freeze closure only |
| Implementation performed | No |
| Contracts, tests, or source modified during this closure | No |

## 2. Authority Chain

This freeze closes exactly the following three commits, in order, as one approved lineage. No commit is amended, squashed, or rewritten.

| Role | Commit | Summary |
| --- | --- | --- |
| Design | `fd96b70366a7bbed2172a8f51d7d7cc52b60bc41` | Harden MILESTONE-020 repository and concurrency contract design (Version 1.6, OWNER APPROVED, DESIGN FROZEN) |
| Implementation | `e20bc76d2dc0be359cea2c385c210e081fb48a35` | feat: implement M020 repository contracts |
| Correction | `efed86be608471fdaa2956f7827fc9236209763a` | fix: harden M020 validation and review evidence |

Authoritative documents for this freeze:

- `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_SCOPE_SELECTION.md`;
- `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_DESIGN.md` (Version 1.6);
- `MILESTONE_020_DOMAIN_REPOSITORY_AND_CONCURRENCY_CONTRACT_IMPLEMENTATION.md` (Version 1.1);
- `external-review/M020_REPOSITORY_CONTRACT_IMPLEMENTATION/` (independent review package, correction pass, ZIP SHA-256 `377ac1672b4894e5b3580391d4db089bed9c7393383900c07edf9028e2061bfc`).

Frozen baseline this milestone built on: MILESTONE-019 (aggregate reconstruction contract, commit `22c0646`), itself resting on the MILESTONE-012 canonical runtime domain kernel. Neither is reopened, rewritten, or reinterpreted by this freeze.

## 3. Independent Review Outcome

Independent hostile review (Codex) first returned `M020 IMPLEMENTATION REQUIRES NARROW CORRECTION` against two MAJOR findings (external-review package contamination; `scripts/verify.ps1` not exiting 0 on this machine) and one MINOR finding (mypy does not type-check `tests/`). Both MAJOR findings were independently reproduced before correction, fixed narrowly (`efed86b`), and independently re-verified. Following the correction, the recommendation returned:

```text
M020 IMPLEMENTATION APPROVED FOR OWNER FREEZE
```

The Project Owner accepted that recommendation and authorized this freeze closure.

## 4. Final Validation Evidence

Re-executed fresh at freeze-closure time (see Section 7 for this session's own commands and Section 12 of the Implementation document / `external-review/M020_REPOSITORY_CONTRACT_IMPLEMENTATION/evidence/` for the correction-pass evidence bundle):

| Gate | Result |
| --- | --- |
| `pytest` (full suite) | 303 passed, 9 skipped |
| Coverage | 91.82% (gate: 80%) |
| `powershell -File .\scripts\security.ps1` | PASS |
| `powershell -File .\scripts\verify.ps1` | PASS (exit 0, end-to-end, no manual workaround) |
| `ruff format --check .` | PASS |
| `ruff check .` | PASS |
| `mypy` | PASS, 0 issues, 68 source files |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `tools/check_architecture.py tests/fixtures/illegal_imports` | PASS, all violations (including the 3 M020 fixtures) correctly detected |
| `python -m build` | PASS |
| `git diff --check` | PASS |

## 5. Accepted Residual Observations

These are disclosed, not blocking, and not corrected by this freeze:

1. **mypy does not type-check `tests/`.** The project's `[tool.mypy]` configuration (`packages = ["empirical_platform"]`) only checks `src/empirical_platform`. The Protocol-conformance assertions in `tests/contract/test_repository_contract_common.py` are structural documentation, not a currently-enforced gate. A genuinely narrow fix is not available without changing mypy's canonical resolution mode project-wide (confirmed by direct investigation during the correction pass — see the Implementation document, Section 14.3). Disposition: `ACCEPTED FOR FUTURE TOOLING MILESTONE`.
2. **`setuptools` `project.license` TOML-table deprecation.** `python -m build` emits `SetuptoolsDeprecationWarning: project.license as a TOML table is deprecated ... By 2027-Feb-18, you need to update your project and remove deprecated calls`. This originates from `pyproject.toml`'s existing `license = { text = "Proprietary" }` field, present since the project's initial M004 scaffolding, unrelated to M020, and does not fail the build (warning only). Disposition: `ACCEPTED, TRACK FOR PRE-2027-02-18 CORRECTION` — migrating to an SPDX string or `license-files` is a `pyproject.toml`-wide packaging-metadata change outside this milestone's mandate.

## 6. What This Freeze Does Not Authorize

Freezing MILESTONE-020 authorizes nothing beyond the domain-facing repository and optimistic-concurrency **contracts** (Protocols and their support types) already committed. It does not authorize, and no commit in this lineage contains:

- repository implementations or persistence mappers;
- PostgreSQL schema or migrations (`migrations/versions` remains empty);
- SQL or ORM mapping;
- Unit of Work implementation;
- application services, runtime composition, APIs, or workers;
- Audit runtime, Decision Candidate, Decision Freeze;
- any MILESTONE-021 work.

## 7. Freeze-Time Validation Commands (this session)

```text
python --version
powershell -ExecutionPolicy Bypass -File .\scripts\security.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\verify.ps1
python -m ruff format --check .
python -m ruff check .
python -m mypy
python tools\check_architecture.py .
python -m build
git diff --check
```

Raw output for this freeze-closure run is recorded alongside this document's companion evidence capture (see the project checkpoint for the exact evidence path at freeze time).

## 8. Final Status

```text
M020 APPROVED AND FROZEN
```

This freeze record is final for MILESTONE-020. No frozen historical MILESTONE-020 document (Scope Selection, Design, Implementation) is rewritten by this closure; this document only adds the closure decision on top of them.
