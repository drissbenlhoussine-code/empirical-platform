# MILESTONE-085 — Mutation Matrix

**1 of 1 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `ace564c9d15e65686bd9b86dba736940c3e3d5235e868ff661275c38968466ce`, after `ace564c9d15e65686bd9b86dba736940c3e3d5235e868ff661275c38968466ce`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `definitive_refusal_statuses` | Only 400, 401, 403 and 422 can prove an order was refused | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_anything_else_is_uncertain` | **EXECUTED_PASS** | detected; restored to `053d28ff16a9e288` |

