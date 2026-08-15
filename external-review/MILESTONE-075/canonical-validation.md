# M075 — Canonical Validation

All executed on this branch, Linux, Python 3.13.12, against a live PostgreSQL 16.

| Gate | Result |
|---|---|
| `ruff format --check .` | 560 files already formatted |
| `ruff check .` | All checks passed |
| `mypy` | no issues in 281 source files |
| `tools/check_architecture.py .` | exit 0 |
| `tools/check_architecture.py tests/fixtures/illegal_imports` | exit 1 (the required outcome) |
| M075 unit tests | 24 passed |
| M075 brief-rendering tests | 2 passed |
| M075 PostgreSQL integration tests | 4 passed |

## Regression, measured against the identical baseline

Both runs: same LF clone semantics, same PostgreSQL instance, PG integration enabled.

| Head | Result |
|---|---|
| `origin/master` (`9b42759`) | **24 failed, 2138 passed, 14 skipped, 44 errors** |
| this branch | **24 failed, 2168 passed, 14 skipped, 44 errors** |

Identical failure and error counts; **+30 passing tests**, which is exactly the 30 tests
M075 adds. **Zero regressions and zero new failures.**

The 24 failures and 44 errors are the pre-existing M062/M064/M065 CRLF seal debt,
inherited from before this milestone and documented in
`MILESTONE_063_EXCEPTIONAL_BYTE_SEAL_RECONCILIATION.md` section 8. Not one of them is in
an M075 file. CI runs `windows-latest`, where they do not occur.
