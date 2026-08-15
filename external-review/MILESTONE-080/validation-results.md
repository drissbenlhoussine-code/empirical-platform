# M080 — Validation Results

## Regression, baseline measured in the same environment

The baseline was measured by checking out `0e73e0b` in the **same working tree**
against the **same PostgreSQL instance**, not quoted from a previous milestone.

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `0e73e0b` | — | 24 failed, **2458** passed, 44 errors |
| M080 branch | 8 failed, **2144** passed, 12 errors | 24 failed, **2532** passed, 44 errors |

**Zero regressions**, and the claim does not rest on the counts: the sorted
failing-test-id lists were **diffed and are identical**. The PostgreSQL-off arm's
8 failures are exactly the non-integration subset of the baseline's 24.

No M076, M077, M078, M079 or M080 test appears in the failing set. The residual
failures and errors are the pre-existing M062/M064/M065 CRLF seal debt, untouched
here and invisible on the `windows-latest` CI runner.

## Tests

| Suite | Result |
|---|---|
| M080 unit | **58 passed** |
| M080 PostgreSQL integration | **12 passed** |
| M080 fresh second pass, separate database | **4 passed** |
| M076–M080 focused compatibility chain | **364 passed** |

## Gates

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed (one import-order fix applied) |
| `ruff format --check .` | 594 files already formatted |
| `mypy` | no issues in 302 source files |
| `check_architecture.py .` | exit 0 |
| negative architecture fixture (`tests/fixtures/illegal_imports`) | exit 1 (required) |
| secret scan | **0 findings**, 0 in M080 files |
| `pip-audit` | No known vulnerabilities found |
| `python -m build` | sdist + wheel |
| CLI usage paths | 5 malformed invocations, all rejected with a usage message |
| migrations | **none added or changed** |

**No `# type: ignore`, no concealing `# noqa`, and no gate suppression was
added.** Asserted by a purity attack over the module source, not merely intended.

## PostgreSQL evidence

### The mandated adversarial position, over genuinely persisted rows

```
OPENED  q=10  price=100     effective E1   recorded K1
REDUCED q=4   price=110     effective E2   recorded K2
CLOSED  q=6   price=90      effective E3   recorded K3
```

written through the **real M076 repository**, so the `CLOSED` quantity is
**derived by frozen M076** rather than supplied — raw SQL confirms the stored
value is `6`.

| Check | Result |
|---|---|
| entry cost for exited quantity | `1000` |
| exit consideration | `980` (`4×110 + 6×90`) |
| **asserted round-trip result** | **`−20`** |
| recomputed independently from raw SQL columns | agrees exactly |

### The arithmetic evolves only as evidence is recorded

| Knowledge cutoff | Status | Result |
|---|---|---|
| `K1` | `NO_EXIT_ASSERTED_YET` | none emitted |
| `K2` | `PARTIAL_EXIT_ASSERTED` | `40` on 4 of 10 units, 6 still open |
| `K3` | `FULLY_EXITED_ASSERTED` | `−20` |

Raw SQL `WHERE event_timestamp <= :e AND recorded_at <= :k` returns 1, 2 and 3
eligible rows at those cutoffs, matching the module's `visible_event_count`.

### Double-database temporal leak proof

Two **physical databases**; the probe is created empty and migrated from scratch
inside the test. Their rows with `recorded_at <= K` are **byte-identical**,
verified by raw SQL. Their futures differ radically:

| | DB-A after `K` | DB-B after `K` |
|---|---|---|
| | `REDUCED 4@110`, `CLOSED 6@90` | `CLOSED 10@9999.999999`, plus an entire extra `NVDA` position |

At `K`, **the full report objects are equal** — not merely the amount, but the
status, counts, limitations, ordering, **text** and **JSON**.

A companion test proves the two ledgers really were different: once `K` advances
they diverge to `−100` and `500`, and re-querying at the original `K` still
returns identical reports, so the earlier answer is not retroactively
strengthened.

### Second pass, separate database, boundary decimals

`m080_second_pass`, created empty with the full migration chain applied from
scratch. Different instruments (`PLTR`, `COIN`, `ARM`, `SMCI`), different ids,
different timestamps, **reversed insertion order**, and prices at both ends of
the frozen `NUMERIC(20, 6)` domain in one position:

- `0.000002` entry, exits at `0.000001` and `99999999999999.999999`
- result `299999999999999.999989`, exact
- a position whose opening is **recorded last** reports
  `UNRESOLVED_KNOWLEDGE_SEQUENCE` at the earlier cutoff and
  `PARTIAL_EXIT_ASSERTED` with `423.249995` once the opening is recorded
- appending post-cutoff rows between two reads leaves the report byte-identical

## One anomaly, recorded not buried

On the **first** chain run after a cold PostgreSQL start,
`test_m077_all_plans_acted_text_and_json_agree` failed once. It passed in
isolation and in five subsequent runs (`-k "m077 or m080"` 39 passed; the broad
chain 364 passed, three times). It is an M077 test in a module M080 does not
modify. **It is not claimed to be explained.** The authoritative check is the
failing-ID diff above, which is identical to the baseline.
