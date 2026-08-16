# M081 - Validation Results

All measured, none quoted from a previous run.

## Focused suites

| Suite | Result |
|---|---|
| M081 unit | **77 passed** |
| M081 PostgreSQL integration | **21 passed** |
| M081 fresh second pass | **4 passed**, from a dropped-and-recreated database |
| M076-M081 compatibility chain | **509 passed** |

## Full regression, candidate vs master baseline `43eb2c3`

Measured by checking out the baseline SHA in the **same working tree** against
the **same PostgreSQL instance**, then diffing sorted failing-test-id lists -
never by comparing counts.

| Mode | Baseline `43eb2c3` | Candidate | Failing-ID diff |
|---|---|---|---|
| PostgreSQL **on** | 24 failed, 2575 passed, 14 skipped, 44 errors | 24 failed, **2677** passed, 14 skipped, 44 errors | **empty** - 68 ids each side |
| PostgreSQL **off** | 8 failed, 2184 passed, 453 skipped, 12 errors | 8 failed, **2261** passed, 478 skipped, 12 errors | **empty** - 20 ids each side |

**+102 passing tests with PostgreSQL on, zero new failures in either mode.**

The pre-existing M062/M064/M065 seal debt remains, unrepaired and unchanged - it
appears identically on both sides of both diffs.

## Static gates

| Gate | Result |
|---|---|
| `compileall src tests tools migrations` | clean |
| `ruff check .` | All checks passed |
| `ruff format --check .` | 603 files already formatted |
| `python -m mypy` | Success, **306** source files |
| `tools/check_architecture.py .` | exit 0 |
| negative architecture fixture | exit 1 on 32 seeded violations |

**No `# type: ignore`, no concealing `# noqa`, no gate suppression** anywhere in
M081 source - asserted by grep over all four M081 modules.

## Security and build

| Gate | Result |
|---|---|
| `pip-audit` | no known vulnerabilities |
| secret scan | **0 findings** |
| `python -m build` | sdist + wheel |
| wheel import | `empirical_platform...operator_asserted_round_trip_ratio` imports from the built wheel in a clean Python 3.13 venv |
| console entry point in wheel metadata | `empirical-platform-asserted-round-trip-ratio` |

A note on method: my first wheel check created its venv with the system
interpreter, which is Python 3.11, and the install correctly refused because the
project requires 3.13. That was my harness being wrong, not a packaging defect;
re-run with the project interpreter it installs and imports cleanly.

## Adversarial review

| Pass | Attacks | Outcome |
|---|---|---|
| Hostile design review | **156** | 9 findings, all corrected before implementation |
| Hostile implementation review | **232** | 1 defect (R01), fixed; 10 wrong probe assertions of mine, recorded |

## The PostgreSQL evidence

All seven mandated scenarios were built against real rows:

| # | Scenario | Ratio |
|---|---|---|
| A | fully exited, positive result | `1/2` |
| B | fully exited, negative result | `-3/4` |
| C | break-even | `0` |
| D | partial exit (1 of 10) | `1` - **not** `1/10` |
| E | no exit | none, explicit absence |
| F | post-`K` exit | invisible at the early cutoff, `2` once `K` advances |
| G | unresolved knowledge sequence | none, own reason |

Every ratio was cross-checked against a numerator and denominator recomputed
**independently from raw SQL** using pure integer arithmetic, without touching
M080's or M081's helpers.

The persistence boundary - max `INTEGER` quantity against the max
`NUMERIC(20,6)` price - was verified exact against raw rows, strictly greater
than `-1`, and rendered `~-0.999999` rather than the unreachable `-1`.
