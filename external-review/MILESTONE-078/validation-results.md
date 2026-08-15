# M078 — Validation Results

## Regression, measured against a baseline run in the same environment

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `183401e` | 8 failed, **1975** passed, 12 errors | 24 failed, **2311** passed, 44 errors |
| M078 branch | 8 failed, **2017** passed, 12 errors | 24 failed, **2368** passed, 44 errors |

**+42 and +57 passing tests. Zero regressions**, and the claim does not rest on
the counts: the sorted failing-test-id lists were **diffed and are identical**,
with no M075, M076, M077 or M078 test in the failing set.

The 8/24 failures and 12/44 errors are the pre-existing M062/M064/M065 CRLF
seal debt, untouched here and invisible on the `windows-latest` CI runner.

## Tests

| Suite | Result |
|---|---|
| M078 unit | **42 passed** |
| M078 PostgreSQL integration | **12 passed** |
| M078 fresh second pass, database created empty | **3 passed** |
| M070–M078 focused integration | 74 passed, 5 skipped, 6 pre-existing M074 seal-debt failures |

## Gates

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 582 files already formatted |
| `mypy` | no issues in 294 source files |
| `check_architecture.py .` | exit 0 |
| negative architecture fixture | exit 1 (required) |
| secret scan, M078 files | **0 findings** |
| `pip-audit` | No known vulnerabilities found |
| `python -m build` | sdist + wheel |
| import smoke | module imports, 11 exports |
| migrations | **none added or changed** |

**No `# type: ignore`, no `# noqa` concealing a defect, and no gate suppression
was added.** Two drafts required suppressions — a `**dict` splat in the usecase
and a complexity `noqa` — and both were removed by restructuring the code
rather than by silencing the checker.

## PostgreSQL evidence

- Pass 1, `empirical_platform`: 12 passed, including a barrier-synchronised
  writer/reader race and an M077-compatibility cross-check
- **Pass 2, `m078_second_pass`** — database created empty, full migration chain
  applied from scratch, deliberately different inputs throughout: different
  session ids, symbols (`NVDA`/`AMD`/`SMCI`), a shifted breakout fixture
  placing the event on day 13, a different `as_of`, different quantities, six
  decimal-place prices and a capital base of `43750.25`: **3 passed**
- Plan lineage and instrument symbol cross-checked against raw SQL with no
  repository helper in the path
- Asserted prices of `110`, `123.456789`, `291.6375`, `415.999999`, `150.125`
  and `99.999999` were persisted during these tests and **none of them appears
  in any M078 output**, which is the no-money guarantee proven rather than
  asserted

**Zero new migrations.** M078 adds no table and no schema change.
