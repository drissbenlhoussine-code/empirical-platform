# Final candidate `2726f6f53f74a0f6d0c63198d0970d3bce822efe` — exact-SHA verification record

Status: PUBLISHED TO PR #15 FOR INDEPENDENT REVIEW. Not merged, not frozen. Paper acceptance
NOT_STARTED. No Proposal, Approval, Paper Intent, acceptance-database write, Alpaca API call or
M086 work occurred while producing this record.

Code under test: `2726f6f53f74a0f6d0c63198d0970d3bce822efe` = `754ceda` +
`b24c471` (corrective pass, D1/D2) + `5ae236c` (M084 Owner ratification of `1127134` and
mechanical freeze of M084) + `53f878c` (F1 identity-safety correction) + `2726f6f` (secret
scanner clears the M084 blob-id manifest by git's index). This document cites that code SHA; it
does not and cannot name the commit that contains it.

## 1. Local exact-SHA verification (all stages run one at a time in the foreground)

Environment: Windows 11 Pro, Python 3.13.14 (`.venv`), PostgreSQL 16.13 native service on
127.0.0.1:5432 with `trust` authentication for 127.0.0.1 (no password used, requested or
recorded), psycopg 3.3.4 with `PSYCOPG_IMPL=python` **pinned and printed in every stage log**
over the system `libpq.dll` 16.0.13 (`C:\Program Files\PostgreSQL\16\bin` prefixed to PATH).
Disposable databases only: `m085_pgon_c7a41f0` (role `empirical_m085`, M085 suites and the
campaign) and `m085_pgon_53f878c` (recreated fresh with `DROP/CREATE DATABASE`, owned by the
temporary verification role `empirical_m085_verify` which holds `LOGIN CREATEDB CREATEROLE` so
that the M079–M083 probe suites can create their own databases and roles). The acceptance
database `m085_acceptance_2e5c38c` was not touched. No shared-server authentication or
privilege was changed; the verification role and databases are disposable and disclosed here.

| Stage | Scope | Result | Log summary |
|---|---|---|---|
| R1a | temporal, time-basis, lifecycle, corrective-pass, identity-collision PostgreSQL suites | 180 passed, 0 failed, 0 skipped | `R1a-python.summary.txt` |
| R1b | concurrency, authority contract, hostile HTTP, M084 file audit | 266 passed, 0 failed, 0 skipped | `R1b-python.summary.txt` |
| R2 | full suite, PostgreSQL off, coverage gate | 3934 passed, 0 failed, 1232 skipped (1223 "PostgreSQL integration tests require explicit opt-in", 4 object-storage opt-in, 2 real-network opt-in, 2 unified-runtime opt-in, 1 "PostgreSQL is off, so no repetition ran"); **coverage 83.31 % ≥ 79 %** | `R2-full-non-pg.summary.txt` |
| R3a | every non-integration suite, PostgreSQL on, fresh coverage file | 3587 passed | `R3a-final.summary.txt` |
| R3b | `tests/integration/test_m085_*.py`, coverage appended | 423 passed | `R3b-final.summary.txt` |
| R3c | `tests/integration/test_m08[0-4]*.py`, coverage appended | **674 passed, 3 failed, 2 skipped, 43 errors** — see §2 | `R3c-final.summary.txt`, `R3c-baseline-failures.txt` |
| R3d | every remaining integration suite, coverage appended, gate evaluated | 420 passed, 14 skipped; **combined coverage 89.66 % ≥ 79 %** | `R3d-final.summary.txt` |
| R3 total | full suite, PostgreSQL on | **5104 passed, 3 failed, 43 errors, 16 skipped — NOT GREEN**; every failure and error is the documented non-M085 baseline of §2 | |
| R4 | full mutation campaign, 134 families, 7 sequential chunks, per-file SHA-256 restoration and whole-tree digest before/after each chunk | **134/134 detected, 0 blockers**; tree digest `cd7162ab…5108` identical before and after every chunk; `git status` clean after each | `mutation-matrix-final-chunk-00.md` … `-06.md` |
| R5 | compileall, ruff format (743 files), ruff check, mypy (368 files), architecture positive/negative, frozen-path guard (M083 27 + M084 69 = 96 paths), M083/M084/M085 authority renderers, M084 file audit (75 paths), secret scan `{}`, pip-audit (no known vulnerabilities), build | all green | `R5-final.summary.txt` |

The 16 R3 skips: 8 real-network opt-in (M069/M070/M073), 4 object-storage opt-in, 2 unified
runtime opt-in, 2 `test_m084_decision_to_approval_postgres_attacks` "a no-op update is not a
transition". No M085 test skipped.

## 2. Baseline limitations (not M085, not fixed here, frozen tests unmodified)

Exact ids and driver messages: `R3c-baseline-failures.txt`. Summary: 43 setup errors in the
frozen M083 suites (`psycopg.errors.FeatureNotSupported: cannot truncate a table referenced
in a foreign key constraint` — M084's foreign key makes M083's fixture `TRUNCATE` structurally
illegal at the M084+ head, recorded in the M084 freeze record as a measured limitation; M083
acceptance is obtained at M083's own revision); `test_28_migration_up_down_up_is_clean`
(M083, same root); `test_an_unexpected_checker_error_fails_closed` and
`test_a_non_superuser_cannot_shadow_the_event_table_through_pg_temp` (M082;
`permission denied to drop objects` — they need object-drop privileges beyond the
verification role's `CREATEROLE`; under the dedicated `empirical_m085` role they failed
earlier with `permission denied to create database` / `create role`). This set is identical
to the baseline table in `validation-results.md` first recorded at `754ceda`. CI never runs
these suites together (the `foundation` workflow runs no PostgreSQL; the PostgreSQL workflow
runs the M085 suites and the M084 file audit only), so this non-green result is visible only
in a local full run and is disclosed as such.

## 3. Environment findings from this verification

- **A1 — concurrency suite nondeterminism under the binary psycopg wheel (MEDIUM, unresolved).**
  `tests/integration/test_m085_concurrency.py` failed 3–7 tests in three of four runs when
  psycopg loaded its bundled binary implementation (libpq 18.0.3) with coverage on
  ("relation … does not exist" at the start of a repetition-2/3 test, right after the
  per-repetition `DROP SCHEMA … CASCADE` + `alembic upgrade head` rebuild; once
  `too many parameters specified for RAISE` while compiling a guard function during that
  upgrade), on a clean database and irrespective of the role. It passed 3/3 with
  `PSYCOPG_IMPL=python` under coverage and 6/6 without coverage under either implementation
  (including R1). Isolated runs of the failing tests passed. Root cause NOT established;
  disabling coverage is not an explanation. **Tested runtime profile for any future Paper
  acceptance and for CI comparison: psycopg pure-Python implementation, libpq 16, and the
  repository's `--no-cov` PostgreSQL mode.** Reproduction commands and logs: session scratch
  logs `iso-a/iso-b/e1/e2/probe*.log` (summarised in the round report).
- **A2 — orphaned catalog rows in a disposable database (LOW, cause not demonstrated).**
  `A2-orphaned-catalog-evidence.md` preserves the two orphaned `pg_proc` rows (oids 6515131
  and 6515126, namespace oid 6514009 with no `pg_namespace` row, xmin 2238170) that made the
  migration round-trip tests' unqualified `SELECT prosrc FROM pg_proc WHERE proname = …`
  return two rows. No system catalog was modified; the database was dropped and recreated;
  the tests then passed (R3b, R1a). Harness hardening (schema-qualified catalog queries) is a
  candidate follow-up, not done here.
- **A3 — implementation drift (INFO).** Earlier in the session psycopg's bundled DLL was
  blocked by Windows Application Control and the pure-Python implementation over libpq 16 was
  used and documented; the block proved transient and later imports silently loaded the binary
  implementation. `identity-collision-correction.md` §1 describes the earlier runs correctly;
  runs between that point and this record may have used either implementation. This record's
  stages pinned and logged the implementation.
- **A5 — local trust authentication (INFO).** `pg_hba` grants `trust` to 127.0.0.1, so the
  "isolated acceptance credential" provides no local isolation; not changed here.

## 4. Focused pre-Paper review of this head (evidence, not repair)

- **A6 — slow identity lookup (HIGH; blocks Paper acceptance; not fixed on this head).**
  `A6-test_slow_identity_lookup_review.py` + `A6-slow-lookup-proof.log`: with production
  handlers and the repository fakes, when the pre-send identity lookup added by `53f878c`
  is slow, the POST is still transmitted after the authorization expired during the lookup,
  with the kill switch engaged during the lookup, and with a quote that went stale during the
  lookup — 3/3 scenarios reached `PAPER_ACCEPTED` with one submission. Cause: in
  `usecases/paper_execution.py` the lookup (`fetch_order_by_client_order_id`, ~line 1428) is
  the last statement of `before_send`, after `final_send_refusal` (~line 1404), and the
  transport sends immediately after `before_send` returns (`alpaca_paper.py` ~lines 532–542).
  Time-based exposure is bounded by the lookup's connect+read timeouts (10 s + 20 s default);
  the kill-switch exposure is the lookup's duration. Required repair in the next authorized
  round: move the lookup before the final re-reads, or re-read the kill switch and re-run
  `final_send_refusal` on fresh time after it; add the three scenarios as regression tests and
  mutation families.
- **B — existing-order adoption (MEDIUM, review gap).** `order_identity_mismatches` compares
  `client_order_id`, symbol, side, quantity, order type and limit price. It does not compare
  `time_in_force` or `extended_hours` (the broker order view carries neither field), and the
  account context is implicit in the API key of the connection rather than re-verified against
  `authorization.account_reference`. After a database reconstruction the recovery cannot
  distinguish an earlier attempt of ours whose row was lost from a historical order that
  derived the same identity: a match on visible fields proves identity and terms, not the
  human-authorization provenance of THIS attempt. Adoption is visible
  (`IDENTITY_RECONCILED_EXACT_MATCH`); an unresolved identity stays `SUBMISSION_UNKNOWN`; no
  replacement id, resend, cancellation or liquidation exists. Whether adoption after a
  reconstruction should require an explicit operator confirmation is an open design question.

## 5. Exact-head CI for `2726f6f` — all four runs SUCCESS (2026-09-26, 06:59–07:05 UTC)

| Workflow / runner | Event | Tested SHA | Run | Job → conclusion | Result |
|---|---|---|---|---|---|
| `foundation` / windows-latest, CPython 3.13.15, no PostgreSQL, shallow checkout | push | `2726f6f` (branch head) | [36225400919](https://github.com/drissbenlhoussine-code/empirical-platform/actions/runs/36225400919) | `verify` → success; all 14 steps success (compile, format, lint, type check, tests, architecture + negative fixture, dependency audit, secret scan 1339 targets, build) | **3912 passed, 1254 skipped, 0 failed; coverage 80.29 % ≥ 79 %** |
| `foundation` | pull_request | synthetic merge of `2726f6f` into `master` | [36225403628](https://github.com/drissbenlhoussine-code/empirical-platform/actions/runs/36225403628) | `verify` → success; all steps success | 3912 passed, 1254 skipped; coverage 80.29 % |
| `M085 temporal PostgreSQL` / ubuntu-latest, CPython 3.13.15, `postgres:16` service = **PostgreSQL 16.15** (Debian), trust auth, `fetch-depth: 0` | push | `2726f6f` | [36225400940](https://github.com/drissbenlhoussine-code/empirical-platform/actions/runs/36225400940) | `temporal-postgres` → success; both test steps success | **252 passed** (temporal, time-basis, lifecycle, concurrency, corrective-pass, identity-collision, M084 file audit; `--no-cov`); **36/36 mutation families detected, 0 blockers**, tree digest identical before/after |
| `M085 temporal PostgreSQL` | pull_request | synthetic merge | [36225403553](https://github.com/drissbenlhoussine-code/empirical-platform/actions/runs/36225403553) | success | 252 passed; 36/36 detected |

CI versions actually installed (from the run logs), which differ from the local machine:
psycopg **3.3.6 with `psycopg-binary` 3.3.6** (manylinux wheel; the bundled libpq version is
not printed by the workflow — the pure-Python implementation is NOT what CI exercises),
SQLAlchemy 2.1.1 (local 2.0.51), alembic 1.20.0 (local 1.18.5), pytest 9.1.1, coverage 7.16.1,
Python 3.13.15 (local 3.13.14). The PostgreSQL workflow ran the M085 concurrency suite green
under the binary wheel with coverage OFF, consistent with A1's observations; it does not test
the binary wheel under coverage.

CI skips: `foundation` reports 1254 skipped against 1232 locally (PostgreSQL off). The 22
extra skips are the history-dependent checks that cannot run in a shallow checkout: the
frozen-path git comparison and base-object tests in `tests/architecture/test_frozen_paths.py`,
`test_the_m084_manifest_is_the_content_at_the_ratified_commit` and
`test_the_freeze_record_and_authority_of_m084_are_untouched_by_the_extension` in
`tests/architecture/test_frozen_milestones.py`, and the M084 base-pin tests. Their blob-id
counterparts (which need only HEAD) did run. The PostgreSQL workflow checks out full history,
so `tests/integration/test_m084_file_audit.py` ran there. The `foundation` workflow does not
print per-test skip reasons (`-rs` is not in its options); the count comparison is against the
local run with identical collection.

What CI does NOT cover: the full PostgreSQL run of every milestone's suite in one database
(§1 R3 / §2 baseline), the remaining 98 mutation families (local R4 covers 134/134), and any
external Paper activity.
