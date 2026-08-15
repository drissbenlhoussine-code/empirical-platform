# M077 — Validation Results

## Regression, measured against a baseline run in the same environment

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `e05cb2f` | 8 failed, **1922** passed, 12 errors | 24 failed, **2237** passed, 44 errors |
| M077 branch | 8 failed, **1966** passed, 12 errors | 24 failed, **2300** passed, 44 errors |

**+44 and +63 passing tests. Zero regressions.** The claim does not rest on the
counts matching: the sorted failing-test-id lists were diffed and are
**identical**, and no M075, M076 or M077 test appears in the failing set.

The 8/24 failures and 12/44 errors are the pre-existing M062/M064/M065 CRLF
seal debt, untouched here and invisible on the `windows-latest` CI runner.

## Gates

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 575 files already formatted |
| `mypy` | no issues in 290 source files |
| `check_architecture.py .` | exit 0 |
| negative architecture fixture | exit 1 (required) |
| secret scan, M077 files | **0 findings** |
| `pip-audit` | no known vulnerabilities |
| `python -m build` | sdist + wheel |

**No `# type: ignore`, no `# noqa` and no gate suppression was added to the new
module.** An early draft carried both; both were removed by restructuring the
code rather than by silencing the checker.

## Tests

| Suite | Result |
|---|---|
| M077 unit | **44 passed** |
| M077 PostgreSQL integration | **15 passed** |
| M077 fresh second pass, new database | **4 passed** |
| M070–M077 focused integration | 53 passed, 5 skipped, 6 pre-existing M074 seal-debt failures |

## PostgreSQL evidence

- Pass 1, `empirical_platform`: 15 passed, including a real writer/reader race
- **Pass 2, `m077_second_pass`** — database created empty, full migration chain
  applied from scratch, and deliberately different inputs throughout: different
  governance ids, symbols (`NVDA`/`AMD`/`SMCI` rather than `AAPL`/`MSFT`/`TSLA`),
  a shifted breakout fixture placing the event on day 13 rather than day 10, a
  different `as_of`, different quantities, prices carrying six decimal places,
  and a capital base of `43750.25` rather than `100000`: **4 passed**
- Held notional cross-checked against a raw-SQL `quantity * asserted_price`
  product with no repository helper in the path
- Exact `Decimal` round-trip proven for `123.456789` and `7.000001`

**Zero new migrations.** M077 adds no table and no schema change.
