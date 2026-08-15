# M076 — Validation Results

## Regression, measured against a baseline run in the same environment

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `92ff472` | 8 failed, **1869** passed, 12 errors | 24 failed, **2168** passed, 44 errors |
| this branch | 8 failed, **1922** passed, 12 errors | 24 failed, **2237** passed, 44 errors |

Identical failure and error counts. **+53 and +69 passing tests** — exactly the tests M076
adds, including the owner correction passes. **Zero regressions**, and the claim does not
rest on the counts: the sorted failing-test-id lists were diffed and are identical, with no
M075 or M076 test in the failing set. The 8/24 failures and 12/44 errors are the pre-existing
M062/M064/M065 CRLF seal debt, untouched here and invisible on the `windows-latest` CI
runner.

Re-measured at freeze time against the merge commit `635a2f6`, with the baseline re-run from
`92ff472` in the same working tree and the same PostgreSQL instance.

## Gates

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 571 files already formatted |
| `mypy` | no issues in 289 source files |
| `check_architecture.py .` | exit 0 |
| negative architecture fixture | exit 1 (required) |
| `pip-audit` | no known vulnerabilities |
| secret scan | 0 findings |
| `python -m build` | sdist + wheel |
| installed-wheel smoke import | OK |
| M070–M076 focused integration | 38 passed, 5 skipped, 6 pre-existing M074 seal-debt failures |

## PostgreSQL

- Pass 1, `empirical_platform`: **16 passed**
- **Pass 2, `m076_freeze_pass`** — database created empty, full migration chain applied
  from scratch: **16 passed**
- Raw SQL inspection inside the tests, independent of the repository helpers
- Migration up → down → up verified with `to_regclass`

## Real installed CLI, end to end

```
empirical-platform-record-position-event --event-id OPEV-7601 --position-id POS-CLI \
  --symbol AAPL --kind OPENED --quantity 25 --price 187.50 --at 2026-04-01T14:30:00+00:00
empirical-platform-record-position-event --event-id OPEV-7602 ... --kind REDUCED --quantity 10 ...
empirical-platform-get-position-state --as-of 2026-04-04T00:00:00+00:00   -> qty 15
empirical-platform-get-position-state --as-of 2026-04-02T00:00:00+00:00   -> qty 25,
        "1 event(s) stamped after the requested as_of were excluded"
duplicate --event-id OPEV-7601 -> "rejected: DUPLICATE_EVENT_GOVERNANCE_ID"
```
