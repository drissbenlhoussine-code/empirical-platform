# MILESTONE-021 - Aggregate Persistence Mapper Contract Implementation Freeze

## 1. Document Control

| Field | Value |
| --- | --- |
| Document ID | MILESTONE-021-IMPL-FREEZE |
| Title | Aggregate Persistence Mapper Contract Implementation Freeze |
| Version | 1.0 |
| Status | APPROVED AND FROZEN |
| Repository | `C:\Users\LuxSy\Documents\trading` |
| Mission type | Freeze closure only |
| Implementation performed during this closure | No |
| Mapper contracts, durable records, tests, or frozen design semantics altered | No |

## 2. Authority Chain

This freeze closes the complete MILESTONE-021 lineage as one approved unit. No commit is amended, squashed, or rewritten.

| Role | Commit | Summary |
| --- | --- | --- |
| Design | `06d22defd6f06b96d0a46c5e91bc169e55e674e5` | Design MILESTONE-021 aggregate persistence mapper contract |
| Design Freeze | `abeba5a1407a8d31ce6d07fe3e071804d2385457` | chore: freeze MILESTONE-021 mapper contract design |
| Implementation | `73ffd3647bce749dff5c8f228f90f3be79413a9c` | feat: implement M021 aggregate persistence mapper contracts |

Authoritative documents for this freeze:

- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_SCOPE_SELECTION.md`;
- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_DESIGN.md` (Version 1.0);
- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_FREEZE.md` (design freeze);
- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_IMPLEMENTATION_SCOPE_SELECTION.md`;
- `MILESTONE_021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_IMPLEMENTATION.md` (Version 1.0);
- `external-review/M021_AGGREGATE_PERSISTENCE_MAPPER_CONTRACT_IMPLEMENTATION/` (independent review package, ZIP SHA-256 `cad8d800a434220d97d2b53acbea668902bac6d2c73fcdb39152025ecd6366c2`).

Frozen baseline this milestone built on: MILESTONE-020 (freeze commit `40dd6b6a0c02e710e3f7efe84e8959af51f839f9`) and MILESTONE-019. None are reopened, rewritten, or reinterpreted by this freeze.

## 3. Independent Review Outcome

Independent recommendation:

```text
M021 IMPLEMENTATION APPROVED FOR OWNER FREEZE
```

The Project Owner accepted that recommendation and authorized this implementation freeze closure.

## 4. Final Validation Evidence

| Gate | Result |
| --- | --- |
| `pytest` (full suite) | 328 passed, 9 skipped |
| Coverage | 92.31% (gate: 80%) |
| `scripts/security.ps1` | PASS |
| `scripts/verify.ps1` | PASS (exit 0, end-to-end) |
| `ruff format --check .` / `ruff check .` | PASS |
| `mypy` | PASS, 0 issues, 73 source files |
| `tools/check_architecture.py .` | PASS, 0 violations |
| `tools/check_architecture.py tests/fixtures/illegal_imports` | PASS, all violations (including the 4 new M021 fixtures) correctly detected |
| `python -m build` | PASS |
| `git diff --check` | PASS |

Re-executed fresh at freeze-closure time; see Section 6 for this session's own commands.

## 5. Accepted Non-Blocking Observations

Carried forward explicitly, not silently:

1. **mypy does not type-check `tests/`** (project config scopes to `src/empirical_platform` only) — unchanged since M020, still `ACCEPTED FOR FUTURE TOOLING MILESTONE`.
2. **Same-package aggregate-to-mapper import prohibition is convention-enforced, not mechanically blocked.** `tools/check_architecture.py` cannot detect `campaign/aggregate.py` importing `campaign/mapper.py` because both resolve to the same top-level module under its `module_for_path` logic, which always permits same-module imports. Identical, pre-existing limitation to M020's analogous repository-import rule; verified in practice that no aggregate module imports its mapper module.
3. **Future concrete mapper implementation should add exhaustive transition-field assertions.** The current fakes and tests prove round-trip fidelity for identity, version, sequence, lifecycle state, and collection order/optional-field preservation; a future concrete implementation milestone should extend this to assert every individual `TransitionDurableRecord` field (not just aggregate-level outcomes) once real serialization is at stake.
4. **`setuptools` `project.license` TOML-table deprecation** remains tracked, unrelated to M021, correction required before 2027-02-18 (carried forward unchanged from the M020 freeze record).

## 6. Freeze-Time Validation Commands (this session)

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

## 7. What This Freeze Does Not Authorize

Freezing MILESTONE-021 authorizes nothing beyond the mapper **contract** layer already committed (Protocols, durable-record types, mapper-local error type). It does not authorize:

- a concrete mapper implementation against any storage technology;
- repository implementations;
- PostgreSQL schema or migrations (`migrations/versions` remains empty);
- SQL, ORM mapping, or Unit of Work beyond the existing single-statement infrastructure primitive;
- application services, runtime composition, APIs, or workers;
- any MILESTONE-022 work.

## 8. Final Status

```text
M021 APPROVED AND FROZEN
```

No frozen historical MILESTONE-021 document is rewritten by this closure; this document only adds the closure decision on top of them.
