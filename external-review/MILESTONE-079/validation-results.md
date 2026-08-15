# M079 — Validation Results

## Regression, measured against a baseline run in the same environment

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `5945e4e` | 8 failed, **1975*** passed, 12 errors | 24 failed, **2383** passed, 44 errors |
| M079 branch | 8 failed, **2070** passed, 12 errors | 24 failed, **2438** passed, 44 errors |

\* the PostgreSQL-off baseline was measured at `183401e` during M078 and is
unchanged by M078's docs-only commits; the PostgreSQL-on baseline was
re-measured at `5945e4e` at this mission's start.

**Zero regressions**, and the claim does not rest on the counts: the sorted
failing-test-id lists were **diffed and are identical**, with no M076, M077,
M078 or M079 test in the failing set.

The 8/24 failures and 12/44 errors are the pre-existing M062/M064/M065 CRLF
seal debt, untouched here and invisible on the `windows-latest` CI runner.

## Tests

| Suite | Result |
|---|---|
| M079 unit | **41 passed** |
| M079 PostgreSQL integration | **11 passed** |
| M079 fresh second pass, database created empty | **3 passed** |
| M076–M079 focused compatibility chain | **69 passed** |

## Gates

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 589 files already formatted |
| `mypy` | no issues in 298 source files |
| `check_architecture.py .` | exit 0 |
| negative architecture fixture | exit 1 (required) |
| secret scan, M079 files | **0 findings** |
| `pip-audit` | No known vulnerabilities found |
| `python -m build` | sdist + wheel |
| import smoke | module imports, 8 exports |
| migrations | **none added or changed** |

**No `# type: ignore`, no concealing `# noqa`, and no gate suppression was
added.**

## PostgreSQL evidence

The mandated adversarial timeline, `T1 < T2 < T3` with the `OPENED` **recorded
last**:

```
OPEV-7902  OPENED  effective T1  recorded T3      <- the backfill
OPEV-7903  CLOSED  effective T2  recorded T2
```

Proven at three knowledge cutoffs over genuinely persisted rows:

| Knowledge cutoff | Result |
|---|---|
| `T1` | `NO_EVIDENCE_RECORDED_BY_KNOWLEDGE_CUTOFF` — the firewall holds |
| `T2` | the `CLOSED` is visible, its `OPENED` is not → `INCOMPLETE_KNOWLEDGE_SEQUENCE`, `position is None`, `incoherent_position_count == 0` |
| `T3` | `KNOWN_CLOSED` — the same key folds normally once knowledge advances |

**Raw SQL cross-check**, independent of every repository helper: both
timestamps read back exactly, and
`SELECT count(*) … WHERE event_timestamp <= :e AND recorded_at <= :k` agrees
with the module's `visible_event_count` at each cutoff.

- **Second pass** on `m079_second_pass`, created empty with the full migration
  chain applied from scratch: different symbols (`SMCI`, `PLTR`, `COIN`,
  `ARM`), different ids, different timestamps, prices at both ends of the
  `NUMERIC(20,6)` range (`0.000001` and `99999999999999.999999`), and
  **reversed insertion order** so ordering cannot be what makes it work: 3
  passed.
- A barrier-synchronised writer/reader race proves snapshot consistency.
- A named test asserts **M076 still sees the backfill that M079 hides**, and
  that M076 is unchanged by having been called through M079.
