# MILESTONE-085 — Mutation Matrix

**2 of 2 families detected.** A surviving mutation is a defect,
never a pass.

Each row names its detecting test BEFORE the mutation was applied. For every family the
campaign required a green baseline, applied the mutation to the real governing rule,
required the named test to fail FOR THE INTENDED REASON, restored the file, verified the
restoration by SHA-256 against the digest taken beforehand, and re-ran the test to
require it green again.

**Tree-wide restoration: VERIFIED.** SHA-256 over every file under src, tests, tools, migrations, scripts (byte-compiled caches excluded): before `cbb5318236d04147c30eb9c031d9abbebcb833bac2f38578d63a406dc0689389`, after `cbb5318236d04147c30eb9c031d9abbebcb833bac2f38578d63a406dc0689389`.

| Family | Rule removed | File | Detecting test | Status | Detail |
|---|---|---|---|---|---|
| `binding_parser_rejects_padding_and_duplicates` | A boundary record with more or fewer than the canonical tokens is rejected whole | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole[identical-duplicate-appended]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |
| `binding_parser_requires_canonical_keys` | Each token must carry the canonical key for its position | `src/empirical_platform/decision_candidate/paper_execution.py` | `test_ambiguous_or_damaged_evidence_is_rejected_as_a_whole[fields-out-of-canonical-order]` | **EXECUTED_PASS** | detected; restored to `18dbd42f3b2897a3` |

