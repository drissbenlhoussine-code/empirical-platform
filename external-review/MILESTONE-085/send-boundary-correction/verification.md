# Exact-SHA verification — send-boundary and identity-recovery correction

CODE_CANDIDATE_SHA: **`00716e460ffdb7de99f554d443e05c3ddf9003a9`** (`00716e4`), on
`feature/m085-alpaca-paper-human-approved-execution`, two commits above the published `38dc069`:

| Commit | Content |
|---|---|
| `80d1faa` | the correction proper: send boundary, canonical terms, lineage, inconclusive lookup, documented refusal codes, four new suites, 14 new families, CI workflow, evidence README + defect log |
| `00716e4` | found by this verification (§2.4): the refusal-status rule stated once, in the code table; two equivalent mutants retargeted |

Every command below ran in the foreground, one at a time, on a clean working tree at the named
SHA (`dirty=0` is printed at the head of every log in `runs-00716e4/`). Mutation runs never
overlapped any other test run. Nothing was pushed. No Alpaca endpoint was called; every HTTP test
targets a local hostile server on 127.0.0.1; every PostgreSQL test targets the disposable database
`m085_pgon_b24c471`; `m085_acceptance_2e5c38c` was not touched.

## 1. Environment (pinned and printed, not assumed)

| Component | Value |
|---|---|
| Host | Windows 11 Pro 10.0.26200, Git Bash (MINGW64) |
| Python | 3.13.14 (`.venv`) |
| pytest 9.1.1, pytest-cov 6.3.0, coverage 7.15.1, freezegun 1.5.5, hypothesis 6.156.6 | |
| ruff 0.16.3, mypy 1.20.2, build 1.5.1 | |
| psycopg 3.3.4 (psycopg-binary 3.3.4 also installed) | **pinned `PSYCOPG_IMPL=python`, libpq 16.0.13 from `PostgreSQL/16/bin` on PATH**; the loaded implementation is printed at the head of R2 and R3 (`impl python libpq 160013`). Unpinned, the bundled binary (libpq 18.0.3) loads on this host today — the earlier Application-Control block is not in effect. |
| SQLAlchemy 2.0.51, alembic 1.18.5 | |
| PostgreSQL | 16.13 on 127.0.0.1:5432, `pg_hba` trust for the disposable role; no password is used or recorded (the `EMPIRICAL_PLATFORM_POSTGRES_PASSWORD` variable carries the literal placeholder `trust-auth-placeholder-not-a-credential`) |

CI (`.github/workflows/`) resolves newer pins (Python 3.13.x latest, psycopg-binary, PostgreSQL 16
service container). **Exact-head CI has not run on `00716e4`: it is not pushed.**

## 2. Results on `00716e4`

| Stage | Command (summary) | Result | Log |
|---|---|---|---|
| R1 focused regressions | 10 M085 files: send boundary, identity lineage, identity collision, handlers, corrective pass (domain + handlers), domain, hostile HTTP, acknowledgement terms HTTP, send-boundary transport | **661 passed**, 72 s | `runs-00716e4/R1-focused.txt` |
| R2 PostgreSQL | temporal, time-basis, lifecycle, concurrency, corrective pass, identity collision, M084 file audit — disposable DB, pinned `python` impl | **253 passed**, 3 m 27 s | `runs-00716e4/R2-postgres.txt` |
| R3 non-PostgreSQL full suite + coverage | `pytest tests` with the project's `--cov`, PostgreSQL opt-in unset | **4034 passed, 0 failed, 1233 skipped**; **coverage 80.37 % ≥ 79 %** (20 380 statements, 3 480 missed; 4 708 branches, 786 partial); every skip is an explicit opt-in gate (PostgreSQL 831 tests, object storage 4, real network 2, unified runtime 2) | `runs-00716e4/R3-full-non-pg.txt` |
| R4 mutation campaign | all **108** families whose target file changed (66 domain, 31 usecase, 11 adapter — includes the 14 new ones), five sequential chunks, whole-tree SHA-256 before/after each chunk | **108 / 108 detected, 0 survivors**; tree digest `b484179c…8da973e` identical before and after every chunk; working tree clean after each | `runs-00716e4/mutation-chunk-0{0..4}.md`, `R4-chunk-0{0..4}.txt`, `affected-families.txt` |
| R5 static gates | compileall; ruff format `--check` (747 files); ruff check; mypy (368 files); architecture positive + negative fixture; frozen-path guard (M083 27 since `707161a1`, M084 69 since `1127134`, 96 by blob id and by diff); architecture/frozen tests (41); authority renderers M082–M085 `--check`; M084 file audit (75 paths); `scripts/security.ps1` (pip-audit: no known vulnerabilities; secret scan: 1365 targets, none); `python -m build` (sdist + wheel) | **all green** | `runs-00716e4/R5-static.txt` |

### 2.1 Coverage: the 83.31 % recorded for `2726f6f` is not reproducible today

R3 reports 80.37 %; `final-candidate-2726f6f/R2-full-non-pg.summary.txt` recorded 83.31 % for the
base. To find out whether this correction lowered coverage, `2726f6f` was exported with
`git archive` and measured in the *same* environment (`PYTHONPATH` on the export's `src`, verified
by printing the imported module path): **80.29 %** (20 326 statements, 3 484 missed). The
correction therefore *raises* coverage by 0.08 points; the 3-point gap is between two measuring
environments of `2726f6f`, not between the two candidates. Per changed module (statements /
missed): domain 879 / 66 (was 848 / 65), usecases 678 / 27 (652 / 24), adapter 395 / 42 (398 / 50).
The export run also shows 21 failures — all in `tests/architecture/test_frozen_*` and
`tests/unit/test_m085_base_pin.py`, which need a `.git` directory the export does not have; they
are not test results about the code. Log: `runs-00716e4/coverage-2726f6f-export.txt`.

### 2.2 One environment slip, recorded rather than hidden

The first R3 attempt on `00716e4` pinned `PSYCOPG_IMPL=python` **without** libpq on PATH in that
shell: two M084 modules that import psycopg at module level failed to collect
(`ImportError: libpq library not found`), pytest exit 2. That is an operator error, not a product
finding; the attempt is kept as `runs-00716e4/R3-attempt1-env-error-libpq-not-on-path.txt` and R3
was rerun with the same PATH the PostgreSQL stage used. Lesson for the environment record: the
pure-Python pin requires libpq 16 on PATH.

### 2.3 Historical baseline (unchanged, not re-run, not green)

The combined full PostgreSQL run of the base (5104 passed / 3 failed / 43 errors / 16 skipped —
43 M083 `TRUNCATE`-under-FK setup errors, `test_28_migration_up_down_up_is_clean`, two M082
privilege tests; all documented as non-M085 and left unmodified) was **not** re-run in this round.
The Owner's list for this round was the relevant M085 PostgreSQL suites (R2) and the
non-PostgreSQL full suite (R3); nothing here changes those historical results and nothing here
should be read as making them green.

### 2.4 What the first candidate `80d1faa` showed (kept in `runs-80d1faa/`)

The identical sequence ran first on `80d1faa`: R1 661 passed; R2 253 passed; R3 4034 passed /
1233 skipped, 80.37 % (that run left `PSYCOPG_IMPL` unpinned — the binary implementation loaded;
recorded as such); R5 all green. **R4: 106 / 108** — chunk 03 left two survivors,
`definitive_refusal_statuses` and `definitive_refusal_requires_the_brokers_document`, both in
`classify_broker_refusal`. Analysis (README §3.1): equivalent mutants — the new per-status code
table already refused what each removed rule refused, so each had become a masking duplicate.
`00716e4` derives `DEFINITIVE_BROKER_REFUSAL_STATUSES` from the table, removes the early exit, and
retargets both families at the table (a `500` entry; a fabricated *documented* code); both are
detected in `runs-00716e4/mutation-chunk-03.md`. Also in that folder: the very first pass of the 20
directly affected/new families before the first commit, in which
`pre_send_lookup_uses_the_derived_identity` and `lineage_unsent_never_attributed` survived and were
fixed by strengthening the tests (README §3).

## 3. Invariant → family mapping

Recorded in [README.md](README.md) §3. Every family named there is in the 108 of R4.

## 4. Findings outside the code (Owner-visible, not fixed here)

| Id | Finding | Why not fixed in this round |
|---|---|---|
| V1 | `tools/render_m085_exhaustion_table.py --check` reports that `external-review/MILESTONE-085/exhaustion-table.md` "is not the current rendering". The committed table was last rendered at `754ceda` (67 families, no M084 manifest). Rendering it today derives three `EXECUTED_FAIL_BLOCKER` rows: row 21 flags `external-review/MILESTONE-085/m084-frozen-path-digests.json` because the renderer's M084 pattern (`m084|MILESTONE-084`) matches the M085-owned manifest the Owner-ratified freeze introduced; row 28 says `changed-files.txt` is 49 paths behind the diff; row 29 flags `PROJECT_CHECKPOINT.md`, modified by the Owner-ratified §119 record. The staleness predates this round (it is present at `38dc069`). | Rows 21 and 29 need the renderer's expectations amended to recognise the Owner's ratification — a governance/documentation change outside this mission's boundary; row 28 is a docs-only update the Owner may authorise together with it. The renderer is not part of CI; the regenerated file was **not** committed (the working tree was restored). |
| V2 | The 83.31 % coverage figure recorded for `2726f6f` is an artefact of the environment it was measured in (§2.1). | The record is historical; this file states the reproducible figure (80.29 %). |
| V3 | `scripts/security.ps1` invokes `python` from PATH. On this host that resolved to a system Python 3.14 without `pip-audit`, so the script aborted at its own audit step until the `.venv` was put first on PATH; CI is unaffected (setup-python owns PATH). | Tooling ergonomics, not a gate weakness; noted for the Owner. |

## 5. Adversarial self-review (item 9)

**What is proven.** The in-connection guard's order — lookup first, configuration/clock/quote
next, kill switch after them, host and broker-bounded time sampled after them, `final_send_refusal`
on that evidence, nothing after — is pinned by a trace test (`boundary[0]=="lookup"`,
`boundary[-2]=="kill_switch"`, `boundary[-1]=="POST"`), by scenario tests that flip each hazard
*during* each slow read and count POSTs (positive control: exactly one POST while permitted), by a
transport-level test through the real `AlpacaPaperClient` and real HTTP framing, and by three
mutation families that respectively insert a read after the decision, reuse the pre-claim
kill-switch snapshot, and judge deadlines on the pre-read time. In the adapter, the statement after
`before_send()` returns is `connection.request(...)`; headers and body are built before the guard.

**What is not claimed.** Control over the broker's receipt time, over the TCP write once
`connection.request` is invoked, or over anything after the request leaves. Those are the cases
`SUBMISSION_UNKNOWN` + reconciliation exist for, and they are unchanged.

**Residual observations.**
- R-1 The POST's TLS connection is opened *before* the guard runs (phase 1), so a very slow lookup
  leaves that socket idle; if the peer closes it, `connection.request` raises and the attempt is
  `SUBMISSION_UNKNOWN` (`BrokerAmbiguousDispatchError`), later resolved by reconciliation
  (404 twice over ≥ 60 s → `NOT_SENT`). Safe — never a second send — but an UNKNOWN rather than a
  clean refusal. Opening the connection after the guard would move the connect phase between the
  decision and the send, which is the wrong trade; left as is and recorded.
- R-2 Lineage admits a `SUBMISSION_IN_PROGRESS` attempt with no unsent event as "may have
  transmitted" (a dispatcher that died after claiming). Reconciliation then adopts a found order
  only if every term matches *and* the broker account is the authorized one. A foreign order under
  the same deterministic id, same terms, same account would be adopted; by construction such an
  order is one this product's own derivation produced. Accepted as the intended crash-recovery path.
- R-3 An order observed without lineage rests in `SUBMISSION_UNKNOWN` with `IDENTITY_EXISTS_*`
  indefinitely; there is deliberately no automatic path from "observed" to "attributed". The
  operator-visible note and events are the resolution surface; a human decision is required, and
  no command exists that would resend, replace, cancel or liquidate on its behalf.
- R-4 `_observe_identity` performs one further lookup *after* the decision not to send, to record
  the broker's order. That is a network operation after the decision, but there is no POST after
  it; it does not sit between a decision and a send.

## 6. Outcome

Outcome of this round: **READY_FOR_OWNER_PUBLICATION_APPROVAL** — local candidate `00716e4`
verified as above; not pushed; not merged; not frozen; not OWNER_ACCEPTED; not READY_FOR_PAPER;
Paper acceptance NOT_STARTED; M086 NOT_STARTED. Publishing (push, PR update, exact-head CI) needs
the Owner's explicit authorization. The commit that contains this document is a docs-only commit
on top of `00716e4`; it changes nothing under `src/`, `tests/`, `tools/`, `migrations/` or
`.github/`.
