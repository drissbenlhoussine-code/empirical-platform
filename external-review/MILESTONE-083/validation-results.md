# MILESTONE-083 — Validation Results

Baseline and candidate were run **serially against isolated database state**
(one shared local PostgreSQL 16.13 instance, schema fully torn down and
rebuilt by each integration test module's own fixtures) — never concurrently,
so no run is contaminated by another.

## Focused M083 suites

| Suite | Collected | Result |
|---|---|---|
| Domain unit (`test_decision_candidate_evaluation_evidence_watermark.py`) | 13 | 13 passed |
| CLI argument handling (`test_m083_evaluation_evidence_watermark_cli.py`) | 6 | 6 passed |
| PostgreSQL hostile lifecycle (`test_m083_evaluation_evidence_watermark_lifecycle.py`) | 33 | 33 passed |
| Fresh second pass (`test_m083_evaluation_evidence_watermark_second_pass.py`) | 5 | 5 passed |
| **M083 together** | **57** | **57 passed** |

Repeated 3x consecutively for the PostgreSQL suite to check determinism
(concurrency/barrier tests in particular): 32/32 passed on run 1 (before a
test-fixture-only correction to the pg_temp-shadowing test's connection
handling), 32/32 on runs 2-3, 33/33 after the blank-set database-agreement
test was added. No flake observed.

## Full regression, exact failing-ID diff

Baseline measured at exact master `45016d7cb79381d9ff8f90a410f57d5a22473269`.

| Mode | Baseline | Candidate | Diff |
|---|---|---|---|
| PostgreSQL off | 8 failed / 2376 passed / 667 skipped / 12 errors | 8 failed / 2395 passed / 705 skipped / 12 errors | **sorted failing+error IDs: EMPTY** |
| PostgreSQL on | 26 failed / 2979 passed / 14 skipped / 44 errors | 26 failed / 3036 passed / 14 skipped / 44 errors | **sorted failing+error IDs: EMPTY** |

Passed-count deltas are exactly the 57 new M083 tests, present as `passed` in
PG-on and as `skipped` (self-skipping on `_postgres_enabled()`) in PG-off
(19 unit + 38 integration = 57 total; 19 run either way, 38 skip without PG).
Every pre-existing failing and erroring test id is byte-identical between
baseline and candidate in both modes; none is newly introduced and none is
newly fixed. The pre-existing failures (survivorship-study fixture errors,
validation-study checksum mismatches, historical-import tamper-detection
mismatch) are unrelated to M083 and match the CRLF/byte-seal debt on
M062/M064/M065 that M082's own freeze record explicitly declined to repair.

## M082 unaffected

M082's own focused suites (277 tests: 40 domain, 9 CLI, 4 handler wiring, 184
PostgreSQL lifecycle, 4 fresh second pass, 36 authority contract) are included
in the full regression run above and are part of the 3036-passed PG-on total
with no new failure. `src/` and `migrations/` paths under M082's ownership are
untouched — confirmed both by `git diff` scope (M083's changed-files.txt
below) and by the migration-survival test
(`test_29_m082_survives_m083_downgrade_unchanged`), which downgrades past the
M083 migration on a live database and re-asserts M082's row counts and its
own immutability trigger.

## Migration

`alembic upgrade head` / `downgrade d9a2f5c81b73` / `upgrade head` cycle
executed against a live database inside
`test_28_migration_up_down_up_is_clean`, asserting `to_regclass` for
`evaluation_evidence_watermark` at each step. Also executed manually against
the shared local database as part of interactive verification.

## Static and build gates

| Gate | Result |
|---|---|
| `python -m compileall -q src tests tools migrations` | clean |
| `ruff format --check .` | 629 files already formatted |
| `ruff check .` | all checks passed |
| `python -m mypy` (scoped to `packages = ["empirical_platform"]` per `pyproject.toml`, matching CI) | Success: no issues found in 319 source files |
| `python tools/check_architecture.py .` | exit 0 |
| `python tools/check_architecture.py tests/fixtures/illegal_imports` | exit 1 (expected negative-fixture failure; 33 violations listed) |
| `python -m pip_audit` | no known vulnerabilities |
| Secret scan (`tools/secret_scan_targets.py --scan-json`) | 0 findings (1 false positive found and corrected — see hostile-review.md I04) |
| `python -m build` | sdist + wheel built successfully |
| Clean-environment wheel import | `EvaluationEvidenceWatermark` / `EvaluationEvidenceWatermarkRepository` import cleanly from the built wheel in a fresh venv |
| Installed console entry points | `empirical-platform-capture-evaluation-evidence-watermark` and `empirical-platform-get-evaluation-evidence-watermark` execute, print correct usage on bad args, and run a full capture/get round trip against a live database with correct output |
| `git diff --check` | clean, no whitespace errors |
| `changed-files.txt` vs `git diff --name-only 45016d7...HEAD` | exact match |

## Suppressions introduced by M083

Measured directly with `git diff 45016d7...HEAD | grep '^+' | grep -c ...`,
not asserted generically:

- `# noqa: E501` — 4 occurrences: two long dotted import lines (matching the
  identical pre-existing convention in `runtime.py` and M082's own test
  file), one CLI usage string, and one long test function name.
- `# noqa: S608` — 2 occurrences, both on an f-string-built `SELECT count(*)
  FROM {table}`/`SELECT {literal}` where the interpolated value is always a
  hardcoded literal from this test module itself, never external input
  (matching the precedented pattern already used in five other integration
  test files' `TRUNCATE {', '.join(_ALL_TABLES)}`).
- `# noqa: BLE001` — 3 occurrences, each on a `except Exception as exc:`
  inside a concurrency-test worker thread whose job is to capture *any*
  failure from a background thread and report it via `errors.append(exc)`
  rather than let pytest silently swallow a thread crash — the identical
  pattern M082's own `test_scenario_i_concurrent_attesters_yield_exactly_
  one_receipt` uses for the same reason.
- `# type: ignore[attr-defined]` — 4 occurrences: three in
  `test_m083_evaluation_evidence_watermark_cli.py` narrowing a
  `module: object` parametrize value back to a callable `main()` (the
  parametrize list mixes two different entrypoint modules, so the static
  type is intentionally widened), one in the lifecycle test narrowing a
  `dict[str, object]` handoff value from a worker thread back to
  `EvaluationEvidenceWatermark`.
- `# type: ignore[misc]` — 1 occurrence, on a unit test deliberately
  assigning to a frozen dataclass field to prove `FrozenInstanceError` is
  raised — the assignment is intentionally type-invalid.
- `# pragma: no cover` — 1 occurrence, on the same defensive
  "conflicted-but-cannot-be-read-back" branch M082's own repository carries
  for the identical reason (a race outcome that cannot be constructed in a
  test without a fault injection the codebase does not have).

No skip or xfail marker was added by M083 to any pre-existing test.
