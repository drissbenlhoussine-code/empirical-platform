# M100 — Cloud launch closure: acceptance report

Reviewed base: PR #47 head `ac5e649917c5089eafda698d451f32f32242dc80` (base `release/v1-personal-paper` `83ba3dba…`).
Follow-up commit on `claude/empirical-m100-launch-c492oz`: see `git log` (adds fixes below). Nothing merged by this work.

## PR #47 — the four corrections, verified from the diff and CI (not from the description)

| | Claim | Evidence |
|---|---|---|
| A | Real positions/open orders reach the risk engine | `paper_operator_console.py` builds `PositionSnapshot`/`OpenOrderSnapshot` from `fetch_position`/`fetch_open_orders`; 5 new HTTP-level tests + 2 candidate-preparation regressions |
| B | `approved_plan` in integrity checks | backup tool baselines `minimum_approved_plan_rows`; step 9 verifies; PG integration test proves the catch; old manifest → clear refusal (reviewer-confirmed) |
| C | PYTHONPATH pinned | `main()` passes `PYTHONPATH=<repo>/src`, overriding ambient (reviewer-confirmed) |
| D | Docs match code | Partly: the `_store_c_config` note was fixed, but step 9 text, resume/recovery text were still wrong — corrected in the follow-up commit |

PR #47 CI on its head: 8/8 check runs success (`verify` ×2 Windows, `temporal-postgres`, `console-postgres`, `exit-postgres`, `paper-exit-postgres`, `v1-deployment-shape-postgres`, `personal-paper-deploy-postgres`). No reviews or comments. PR #46's tree is identical to the release branch (empty diff) → redundant; **left open**, closure needs Owner authorization.

## Consolidated defect register (independent reviews; no P0 found)

| ID | Sev | Finding | Status |
|----|-----|---------|--------|
| D1 | P1 | Daily loss, daily order count, simultaneous-position limits never enforced (hardcoded 0 / single-symbol) — two reviewers | **OPEN** (needs broker daily-P&L/order-count plumbing; see mitigations) |
| D2 | P1 | Duplicate entry: two Prepares before either send both pass; working-order check only at Prepare | **FIXED** in follow-up (submit/recheck `_gather` folds working orders into exposure) + 2 unit tests + transport-test server route |
| D3 | P1 | STOP/MANDATORY exit is one DAY limit sell at trigger-time bid; never cancelled/repriced; EXPIRED/CANCELED attempt never re-armed → `NEEDS_ATTENTION` | **OPEN** (design change; manual exit procedure in handoff) |
| D4 | P1 | No Host-header check → DNS rebinding can read CSRF token and POST console actions | **FIXED** (421 for non-loopback Host) + tests |
| D5 | P1 | Deploy journal resume skipped gates 1–3,6 without re-checking | **FIXED** (re-evaluated until step 7 completes) + tests |
| D6 | P1 (conditional) | Autostart wrapper restarts console 10 s after step 5 stop | **MITIGATED** by runbook (disable task first); code unchanged |
| D7 | doc | Step 9/recovery text wrong ("re-run step N alone", baseline "console stopped") | **FIXED** |
| D8 | note | URLError after a step-13 failure gave a raw traceback | **FIXED** (journaled refusal) |

**Mitigations for open P1s in PAPER:** per-order Owner approval, one-symbol watchlist, per-order notional cap, whole-share only, kill switch for entries, PAPER money only. These make D1/D3 acceptable for a supervised PAPER first run **only with Owner acknowledgement**; they are LIVE blockers.

## Verification (exact commands, this session, Linux 4 cores, Python 3.13)

Base: `ac5e649`. After fixes: follow-up commit.
- `ruff format --check .` / `ruff check .` — clean. `python tools/check_architecture.py .` — clean.
- `mypy` (Linux): only 25 errors, all in `console_control.py` Windows-only attributes (`O_BINARY` etc.); CI type-checks on Windows and was green on the base.
- `pytest tests/unit tests/architecture tests/integration -n 3` after fixes: **5372 passed, 13 failed, 12 errors, 1395 skipped**. Failures/errors are Linux-environment only: 8+12 depend on dataset fixtures sealed with CRLF bytes (confirmed: the seal matches the CRLF form of `synthetic_multi_period_validation_dataset_bundle.json`), 2 `m098` tests assert Windows-specific error text, 1 deploy integration test needs Windows process semantics; the `m085_send_boundary_transport` pair was caused by my change and fixed. **Not independently proven green here; Windows CI is the authority.**
- Skipped (1395): Postgres/network opt-in tests. Postgres suites were run by CI on the base head (links above), not locally. Local coverage gate (79%) not reached because of skips — CI configuration governs.
- Windows CI on the follow-up commit: see final report.

## Stage 3 acceptance matrix — honest status

Reviewers drove the real simulation broker and handlers and reproduced: prepare/approve/submit/fill/position recording, stop/target exit submission, duplicate-exit prevention (claim), broker rejection/uncertain-status handling, kill switch, restart-deterministic ids, partial entry refusal. They did **not** produce a numbered test-ID for each of the 24 items, and a single end-to-end scripted run of all 24 was **not** built. Status: **not formally completed** → `PAPER_END_TO_END = NOT YET TESTED`.

Not performed: real Windows host run, real broker PAPER orders, any LIVE action, deployment-gate-by-gate rehearsal on Windows (the repo's `personal-paper-deploy-postgres` CI job covers the pipeline against disposable Postgres; the unit suite covers failure at every one of the 14 boundaries).
