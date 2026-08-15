# M074 — recovery-run verification

The closure run was interrupted mid-flight and its container was lost. Nothing
below is carried over from that run. Every figure here was re-measured
afterwards on Linux, from fresh clones of this branch, against a PostgreSQL 16
instance created from scratch for the purpose.

The pre-interruption artifacts in the parent directory are Windows captures by
the owner and are left exactly as they were.

## Repository truth

| Item | Value |
|---|---|
| Branch | `feature/m074-historical-portfolio-evidence` (PR #4 head) |
| Base | `master` @ `328e8b014541107165932ddcf19c14f7b0f56cdc` |
| Head at interruption | `47af58087264a03c977682feac738fcf0dbb2d13` |
| Code head verified here | `36ef71977a219710cd93cb1d43b58e41d1c96dca` |

## Clean-clone seal reproduction

`clean-clone-seal-reproduction.txt`. Two clones of the same commit differing
only in `core.autocrlf`. The M063 fixture materializes to the repaired seal in
both, which is what the `-text` pin exists to guarantee. M064 still materializes
to its own recorded seal under `autocrlf=true`, untouched.

## Test results

| Environment | Result |
|---|---|
| CRLF clean clone, PostgreSQL off | 1863 passed, 357 skipped, coverage 80.01% |
| CRLF clean clone, PostgreSQL on | 2206 passed, 14 skipped, coverage 91.93% |
| M070–M074 integration, pass 1 | 24 passed, 5 skipped |
| M070–M074 integration, pass 2 (new database) | 24 passed, 5 skipped |
| LF clean clone, PostgreSQL off | 8 failed, 1843 passed, 357 skipped, 12 errors |

Pass 2 runs against a database created fresh for it, not a truncated reuse of
pass 1's.

The LF-clone failures are the pre-existing M062/M064/M065 CRLF-seal exposure.
`master-baseline-lf-clone.txt` shows the same clone on `origin/master` failing
22 tests; this branch fails 8. The 14-test difference is the M063 repair, and
nothing regressed. Section 8 of
`MILESTONE_063_EXCEPTIONAL_BYTE_SEAL_RECONCILIATION.md` documents the exposure
and why it is out of scope to repair here.

## Toolchain

| Gate | Result |
|---|---|
| `ruff format --check .` | 557 files already formatted |
| `ruff check .` | All checks passed |
| `mypy` | no issues in 280 source files |
| `check_architecture.py .` | exit 0 |
| `check_architecture.py tests/fixtures/illegal_imports` | exit 1, 32 violations — the required outcome |
| `pip-audit` | no known vulnerabilities |
| Secret scan | 957 targets, 0 findings |
| `python -m build` | sdist + wheel |

## Adversarial review

`HOSTILE_REVIEW_RECOVERY.md` — a fresh 89-check pass, independent of the two
pre-interruption reviews. One real defect found and fixed in this branch (the
naive/aware `coverage_end` sentinel); two observations recorded for the owner
rather than changed.
