# M079 — Validation Results

> ## ⚠ SUPERSEDED BY THE OWNER REVIEW CORRECTION
>
> The results below were measured on the **first** M079 candidate (`21ed5ad`),
> whose T07 discriminator Owner review found to be a temporal leak. They are
> kept for audit. **The current numbers are in the section that follows them.**
>
> One claim in the original section is not merely stale but **wrong**: it
> described the unfiltered re-fold as evidence that incompleteness could not
> mask corruption. That mechanism was the defect.


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


---

# M079 — Validation Results after the Owner review correction

Measured on the Owner review correction commit, the head of
`feature/m079-operator-evidence-availability-snapshot`. The commit SHA is in
the mission report and in `git log`; it is not repeated here because a file
cannot contain the hash of the commit that adds it.

## Regression, baseline measured in the same environment

| Head | PostgreSQL off | PostgreSQL on |
|---|---|---|
| `master` `5945e4e` | 8 failed, 1975 passed, 12 errors | 24 failed, **2383** passed, 44 errors |
| First candidate `21ed5ad` | 8 failed, 2070 passed, 12 errors | 24 failed, **2438** passed, 44 errors |
| **Corrected candidate** | 8 failed, **2086** passed, 12 errors | 24 failed, **2458** passed, 44 errors |

**Zero regressions**, and the claim does not rest on the counts: the sorted
failing-test-id lists were **diffed against the `5945e4e` baseline and are
identical**, with no M076, M077, M078 or M079 test in the failing set.

The residual failures and errors are the pre-existing M062/M064/M065 CRLF seal
debt, untouched here and invisible on the `windows-latest` CI runner.

## Tests

| Suite | Before | After |
|---|---|---|
| M079 unit | 41 | **57 passed** |
| M079 PostgreSQL integration | 11 | **14 passed** |
| M079 fresh second pass, database created empty | 3 | **4 passed** |
| M076–M079 focused compatibility chain | 69 | **290 passed** |

The 20 added tests are the Owner's required attacks, listed as O01–O20 in
`hostile-implementation-review.md`.

## Gates

| Gate | Result |
|---|---|
| `ruff check .` | All checks passed |
| `ruff format --check .` | 589 files already formatted |
| `mypy` | no issues in 298 source files |
| `check_architecture.py .` | exit 0 |
| negative architecture fixture (`tests/fixtures/illegal_imports`) | exit 1 (required) |
| secret scan, whole repository | **0 findings** |
| `pip-audit` | No known vulnerabilities found |
| `python -m build` | sdist + wheel |
| import smoke | 8 exports; statuses `KNOWN_OPEN`, `KNOWN_CLOSED`, `UNRESOLVED_KNOWLEDGE_SEQUENCE` |
| migrations | **none added or changed** |

**No `# type: ignore`, no concealing `# noqa`, and no gate suppression was
added.**

## PostgreSQL evidence for the correction

The Owner's attack 8, over **two genuinely separate databases**. The probe
database `m079_leak_probe` is created empty and migrated from scratch inside the
test; both ledgers are written through the **real M076 repository**.

| | DB-A | DB-B |
|---|---|---|
| Rows with `recorded_at <= K` | the `CLOSED`, identical in every column | the `CLOSED`, identical in every column |
| Rows after `K` | `OPENED` id `OPEV-7951`, price `100`, recorded `T3`; **plus an entire extra position** `POS-7960` | `OPENED` id `OPEV-7999`, price `555`, recorded `T0+90d` |
| Total rows | 3 | 2 |

Raw SQL confirms the shared prefix is byte-identical and the totals differ. At
`K = T2`:

- `snapshot_A == snapshot_B` — full object equality
- `render_evidence_snapshot_json(A) == render_evidence_snapshot_json(B)`
- `render_evidence_snapshot_text(A) == render_evidence_snapshot_text(B)`
- both report `UNRESOLVED_KNOWLEDGE_SEQUENCE`, `position is None`

A second test advances the cutoff to prove the two databases were genuinely
different all along: DB-A resolves to `KNOWN_CLOSED`, DB-B legitimately stays
unresolved, and re-querying at the original `K` still yields identical answers —
the earlier answer is not retroactively strengthened.

One frozen behaviour shaped this test and is worth recording: **M076 derives a
`CLOSED` event's quantity from the open position rather than taking it as
supplied**, so both ledgers' openings must carry the same quantity for the
visible prefix to match. The tails differ by id, price and `recorded_at`.

## Second pass

On the fresh `m079_second_pass` database, a further test takes a snapshot,
appends two assertions recorded **after** the cutoff — including an entire new
position — and takes the same snapshot again. Object and text output are
identical; advancing the cutoff then shows all three events, proving the ledger
really did grow between the two reads.
