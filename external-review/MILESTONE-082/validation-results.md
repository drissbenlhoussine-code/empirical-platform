# M082 - Validation Results

All measured, none quoted from a previous run.

## Focused suites

| Suite | Result |
|---|---|
| M082 unit | **30 passed** |
| M082 PostgreSQL integration | **23 passed** |
| M082 fresh second pass | **4 passed**, dropped-and-recreated database |
| M076-M082 compatibility chain | **435 passed** |
| Executed attack battery | **263 / 263** |

## Full regression, candidate vs master baseline `28a1053`

Measured by checking out the baseline SHA in the **same working tree** against
the **same PostgreSQL instance**, then diffing sorted failing-test-id lists.

| Mode | Baseline `28a1053` | Candidate | Failing-ID diff |
|---|---|---|---|
| PostgreSQL **on** | 24 failed, 2704 passed, 14 skipped, 44 errors | 24 failed, **2761** passed, 14 skipped, 44 errors | **empty** - 68 ids each side |
| PostgreSQL **off** | 8 failed, 2285 passed, 481 skipped, 12 errors | 8 failed, **2316** passed, 507 skipped, 12 errors | **empty** - 20 ids each side |

**+57 passing tests with PostgreSQL on, zero new failures in either mode.**

The pre-existing M062/M064/M065 seal debt remains, unrepaired and identical on
both sides of both diffs.

> **One transient failure, found and fixed rather than accepted.** The first
> candidate run showed **25** failures — one more than baseline.
> `test_m076_migration_is_reversible` had begun failing because it downgraded by
> a relative step and assumed M076 was at head. See R02; the corrected run
> returns to 24 and the diff is empty.

## Static gates

| Gate | Result |
|---|---|
| `compileall src tests tools migrations` | clean |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 613 files already formatted |
| `python -m mypy` | Success, **312** source files |
| `tools/check_architecture.py .` | exit 0 |
| negative architecture fixture | exit 1 on seeded violations |

**No `# type: ignore`, no concealing `# noqa`, no gate suppression** in any M082
module - asserted by grep over the domain module, the Protocol, the repository,
the usecase, the IO module, the entry point and the migration.

## Security and build

| Gate | Result |
|---|---|
| `pip-audit` | no known vulnerabilities |
| secret scan | **0 findings** |
| `python -m build` | sdist + wheel |
| wheel import | M082 imports from the built wheel in a clean Python 3.13 venv |
| console entry point | `empirical-platform-attested-evidence-snapshot` present in wheel metadata |

> The secret scan initially reported **1** finding: my migration's alembic
> revision identifiers, flagged as high-entropy hex. **Not suppressed** - the
> repository already filters these in the annotated form every other migration
> uses, and my file had used the bare form. Conforming to the convention
> resolved it with no allowlist entry and no baseline file.

## Migration verification

| Check | Result |
|---|---|
| `upgrade head` | OK |
| `downgrade -1` | OK |
| `upgrade head` again | OK |
| receipt table present after up-down-up | yes |
| immutability trigger restored | yes |
| **table empty after upgrade (no backfill)** | **yes** |
| after downgrade: table gone | yes |
| after downgrade: trigger function gone | yes |
| existing tables altered | **zero** |
| rows written by the migration | **zero** |

## Frozen preservation

Byte-identical to `28a1053`: `operator_position_ledger.py`,
`operator_evidence_availability.py`, `operator_asserted_round_trip.py`,
`operator_asserted_round_trip_ratio.py`, `same_day_capital_feasibility.py`,
`portfolio_aware_capital_feasibility.py`,
`research_decision_follow_through.py`.

None of M079, M080 or M081 references `operator_event_receipt`,
`attested_known_by` or `system_received_at` — **no silent adoption**.

Non-M082 files changed: `pyproject.toml` (entry point), `runtime.py` (nine
added lines, no line removed), and the M076 reversibility test per R02.
