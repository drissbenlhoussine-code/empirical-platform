# MILESTONE-085 — Mutation Matrix

**1 of 1 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `b484179c2fb15454b7115b07dd79d3a3f522bef110634fcbe3b723ec86da973e`, after `b484179c2fb15454b7115b07dd79d3a3f522bef110634fcbe3b723ec86da973e`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `legacy_dry_run_refused` | --dry-run refuses before any runtime, writer, socket or file is touched | `tools/m085_paper_acceptance.py` | `test_dry_run_is_refused_before_any_record_connection_or_file` | **EXECUTED_PASS** | detected; restored to `7dce15d38fafbc75` |

