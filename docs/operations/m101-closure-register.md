# M101 -- PERSONAL PAPER closure register

Date of record: 2026-11-13 (Friday). Deployed release: `240ad1f9a0726270551469e94f49718ee85d376e` (PR #49 merge)
on `release/v1-personal-paper`, running in normal PAPER mode on `127.0.0.1:8189` since 2026-11-13 21:22 EET.
Evidence on the host: `%LOCALAPPDATA%\EmpiricalPlatform\evidence\2026-11-13\m101\` (SHA-256 index included).
Nothing here is a promise of profitability; LIVE is disabled and not assessed.

## 1. Status

| Gate | Result | Evidence |
|---|---|---|
| PAPER_OPERATIONAL | **PASS** | Manager HEALTHY with no error, kill switch released, Live UNAVAILABLE, broker flat; `verify-paper-after-boot.ps1` ALL PASS (21 PASS checks, 2 INFO) |
| BROKER_END_TO_END (A6) | **NOT AUTHORIZED** | Plan in section 5; needs the Owner's sentence and a market window |
| SAFETY | **PASS** (one P2 fixed in the closure PR, deployment pending) | Acceptance matrix 29/29 on this Windows host, real PostgreSQL 16, deployed SHA; 5296 unit+architecture tests; section 3 maps every required safety item to tests |
| WINDOWS_RESTART | **BLOCKED -- not verified** | No reboot is authorized; the last reboot test (2026-10-14, earlier simulation setup) FAILED (task result `0x800710E0`, 8 checks FAIL) |
| BACKUP_RESTORE | **PASS** (disposable rehearsal) | Real dumps restored, migration rehearsed, corruption handled; live restore deliberately not done |
| IPHONE_ACCESS | **BLOCKED -- needs the phone** | Tailnet route verified from the PC (200 on `/paper/safety|health|today`); the phone itself not yet tested |
| CRITICAL_DEFECTS | **0** P0/P1 remaining | Register below |
| CLEANUP | **pending Owner approval** | Section 6 |
| LIVE_READY | NOT ASSESSED -- LIVE remains disabled | `m100-live-readiness.md` |
| FINAL_CLOSURE | **BLOCKED on Owner-gated items only** | Section 4 |

## 2. Deduplicated closure register

Classes: **C** critical blocker, **O** operational blocker, **N** nonblocking improvement, **L** future LIVE-only.
Previously resolved work (D1-D9, P2-1..P2-7 in `m100-acceptance-report.md`) is not reopened.

| ID | Class | Finding | Disposition |
|---|---|---|---|
| R-01 | N (was a narrow P2) | `_read_portfolio` read **positions before working orders**. A BUY that fills between the two reads is in neither snapshot and is under-counted by one entry. Mitigated by the 1-order/day and 1-position limits, but a real gap. Confirmed by a test that fails on the deployed code (entry wrongly admitted) | **Fixed in the closure PR** (orders first, then positions); test `test_an_entry_that_fills_between_the_two_broker_reads_is_never_missed`. Needs a deployment |
| R-02 | O | Windows restart path unverified; last reboot test failed; task `RunOnlyIfNetworkAvailable=true` is unnecessary for a PostgreSQL-only task and is a possible (unconfirmed) cause of the `0x800710E0` refusal | Owner-authorized reboot test; propose setting `RunOnlyIfNetworkAvailable` false on that one task |
| R-03 | O (Owner decision) | The PAPER console has **no autostart**: after a reboot or crash nothing manages an open position and nothing alerts | Keep manual + supervised until after A6, or import `deploy/windows/v1-console-task.xml` (the wrapper has a hold check, crash backoff, circuit breaker; it writes no log) |
| R-04 | O | iPhone access untested from the phone | Owner opens `https://yanis.tail46bf93.ts.net/paper/today` and confirms the five pages |
| R-05 | O | A6 not run, so Alpaca specifics (`pending_cancel` latency, expired-DAY status, `last_equity`) are untested against the real service (P2-8) | Section 5 |
| R-06 | O | Disk is ~98 % full (about 5 GB free of 237 GB). The platform needs little (backups 73 MB total) but a full disk would stop PostgreSQL and backups. Docker holds ~40 GB for other projects (22 GB images, 13.5 GB volumes, 3.8 GB cache, ~19 GB reclaimable by Docker's own estimate); worktrees are not the cause (two venvs of ~210 MB) | Owner decision on Docker and other large data; not touched |
| R-07 | O | `EmpiricalPlatform Post-Boot Verification` still checks the retired simulation console (will report ~8 FAIL) | New read-only `deploy/windows/verify-paper-after-boot.ps1` (ALL PASS on the live host); switching the task to it is an Owner action |
| R-08 | N | No sanctioned standalone stop command; only a deploy step and Ctrl+C in a window (the console is now windowless) | `tools/stop_paper_console.py` added (reuses the reviewed M098 call path; 8 unit tests; `--check` smoke-tested read-only against the live console). Live use only at the next authorized stop |
| R-09 | N | A flipped byte in a dump can restore with exit 0; only SHA-256 catches it | Handbook makes the SHA check mandatory before any restore |
| R-10 | N | 10 stale `*.partial` backup directories (10-10 .. 11-07, none in the last 6 days); `rotate()` prunes only complete sets; the deploy's step-4 set lives outside rotation | Cosmetic; delete only with approval |
| R-11 | N | Hourly backup task runs from `trading-worktrees\v1-release` (a worktree, currently on the closure branch) rather than the deployed checkout | Optional repoint (task change, Owner) |
| R-12 | N | Session cookie lacks the `Secure` attribute (transport is tailnet HTTPS) | P2, no change made |
| R-13 | N | Handoff inconsistencies: Phase 4/5 `@(Invoke-RestMethod ...).Count` prints a false `1` on empty answers; Phase 10.3 omits `--base-path /paper` and assumes a foreground window; `operator-console.md` is SIMULATION-era and contradicts v1 (kill switch, automatic exits) | Handbook supersedes; banner added to `operator-console.md`; evidence docs not edited |
| R-14 | N (outside the platform) | Docker Desktop has an inbound allow rule (any port, **Public** profile) and an unrelated Postgres 17 container is published on `0.0.0.0:55432`; the host is currently on a Public network ("iPhone 2"). The empirical stack is loopback-only and unaffected | Owner decision |
| R-15 | N | Tailscale Serve keeps a dead `/` -> 8086 mapping and other unrelated mappings (8091, 8190, 8092-8094) | Not changed (Owner) |
| R-16 | N | `initdb.exe` is blocked by an Application Control policy, so a disposable server needs Docker | Documented; policy not bypassed |
| R-17 | L | Quote spread/age gate can block a triggered STOP/TARGET/MANDATORY exit (banner after 60 s) | Owner policy decision, pre-existing |
| R-18 | L | Early-close days (2026-11-27, 2026-12-24) refuse every entry with the 15:45 ET liquidation | Owner policy decision, pre-existing |
| R-19 | L | No external alerting; daily-loss proxy includes unrealized P&L; P2-4/P2-6 residuals; all items in `m100-live-readiness.md` | LIVE-only / documented |

## 3. Trading-safety coverage (workstream 2)

Run on this host, deployed SHA, real PostgreSQL 16 (throwaway container, never the live stores), scripted PAPER wire
(real HTTP client, hosts pinned, virtual time). The matrix is **not** a substitute for broker validation: that is A6.

| Required item | Where it is proven |
|---|---|
| PAPER-only routing | `test_m100_single_order_submission_path.py`, ACC-09/10 (key id and host asserted on the wire), pinned host in `/health` and `verify_paper_environment` (live: `is_the_pinned_paper_host true`) |
| Kill switch / maintenance hold | ACC-22; `test_v1_kill_switch_semantics.py`; hold + exit codes 64/73/74 in `test_windows_lifecycle_proofs.py`, `test_console_lifecycle.py`; hold used for real in deploy step 5 and released in A5 |
| Daily loss, order count, position count, exposure | ACC-04b, `test_d1_portfolio_limits.py` (+ the new read-order test), `test_d1_entry_admission_postgres.py` (day advisory lock, fail closed) |
| Duplicate-order prevention | ACC-07, ACC-18; submit-time working-order guard |
| Entry and exit lifecycle | ACC-10..17c |
| Mandatory liquidation | ACC-17c |
| Early market close | `session_close_guard` tests (entry refused when the close precedes the liquidation) |
| Interrupted orders / reconciliation | ACC-12, ACC-12b, ACC-20 (no resend), ACC-24 |
| Pending cancellation | `test_v1_exit_retry_management.py` (bounded cancel/replace); real `pending_cancel` latency **only A6** |
| Restart with an existing position | ACC-21 |
| Failure escalation / Owner visibility | `test_v1_owner_escalation_board.py`, ACC-17b/17c banner assertions |

Results: deployed SHA, PostgreSQL stage 217/217 (216 + the backup rehearsal re-run with `pg_dump` on PATH) and matrix 29/29;
closure branch: 5296 unit+architecture, 9 real-subprocess Windows shutdown, 38 PostgreSQL (D1 admission + matrix) all passed.

## 4. Owner-gated actions (everything else is done)

| # | Action | Why it needs you |
|---|---|---|
| G-1 | Authorize **deployment of the closure PR**: stop the console (authenticated), `git merge --ff-only`, start, re-run `verify-paper-after-boot.ps1`. Do it flat | Changes the running release |
| G-2 | Open the iPhone URL and confirm (R-04) | Needs the phone |
| G-3 | **A6**: one PAPER order (section 5) | Broker order |
| G-4 | Authorize a **reboot test** (R-02) and decide autostart (R-03), `RunOnlyIfNetworkAvailable`, switching Post-Boot Verification to the PAPER script (R-07) | Service / Task Scheduler changes and a reboot |
| G-5 | Approve cleanup (section 6), the backup-task repoint (R-11), Docker/network exposure (R-14), Tailscale hygiene (R-15) | Destructive or host-wide |
| G-6 | Policy decisions R-17, R-18 (before 2026-11-27) | Owner policy |

## 5. A6 proposal (not authorized; nothing has been sent)

- **Order:** exactly one **BUY LIMIT, DAY, AAPL**, limit = the ask at confirmation. The engine computes the size: with the
  500 USD per-trade cap, max 1 share and the current ~358 USD AAPL quote it is **1 whole share**. Name in the sentence:
  *at most 1 whole share and at most 450 USD notional*. Maximum planned loss at the 1 % stop is about 3.6 USD (limit 5).
- **Limits that apply:** daily loss 5.00, 1 order/day (so no second entry is possible that day), 1 position, 500 USD per trade,
  kill switch released, entry window 09:35-15:30 ET, mandatory liquidation 15:45 ET, stop 1 %, target 2 %.
- **When:** Friday 11-13 is not suitable (about 40 minutes of entry window left, then liquidation at 15:45 ET). Use
  **Monday 2026-11-16 from 10:00 ET (17:00 EET)**, never on 2026-11-27 or 2026-12-24 (early close refuses entries).
  Preconditions: G-1 decided, G-2 done, broker flat, manager HEALTHY, Owner present throughout.
- **Flow:** Prepare once -> read the confirmation page (quantity <= 1, notional <= 450, PAPER, LIMIT) -> CONFIRM APPROVAL once ->
  Active shows the working entry, then the open position with the plan (stop, target, 15:45 mandatory exit) -> **Review exit ->
  CONFIRM EXIT once** (the controlled path) -> sell-to-close LIMIT at the bid, repriced if unfilled (max 5, never a market
  order) -> Position closed (broker verified at zero). Mandatory liquidation at 15:45 ET is the backstop.
- **Evidence to collect:** console pages, broker `GET /v2/orders` and `/v2/positions`, Store B `paper_execution_attempt` and
  `approved_plan` rows, Store C `position_exit_attempt` rows, the console log, and the final `verify-paper-after-boot.ps1`.
- **Cancel / failure:** an entry unfilled after a few minutes is cancelled from its execution page; any STOP condition in
  the handoff (Phase 12/13/14) means: click nothing else, engage the kill switch, follow handbook section 8. A position is never
  left unattended; no second order is submitted to complete the test.

## 6. Cleanup candidates (nothing deleted or closed without approval)

- **Open PRs fully contained in the release (patch-equivalent, 12):** #15-#26 (the stacked M085..M095 chain and the release
  PR #26). Also patch-equivalent: #19, #46. Superseded by merged work: **#48** (a parallel D1/D3 implementation replaced by
  #49), **#29** (replaced by merged #36; one patch not equivalent, verify before closing). Housekeeping: #2 and issue #1
  (mobile agent smoke test). Keep for a decision: #27 (IBKR/Helsinki draft), #38 (micro EUR design draft), #45 (CI cost draft).
  Closing a PR keeps its branch and history.
- **Branches:** 37 local and 42 remote branches are merged into the release (`git branch --merged origin/release/v1-personal-paper`).
- **Worktrees:** 24, all clean; two agent worktrees are locked. Keep `trading-worktrees\v1-release` until the backup task is repointed.
- **Host files:** 10 stale `*.partial` backup directories; `ops\_backup-20261107` (keep: rollback for the task change).
- **Docs:** `operator-console.md` (banner added), handoff errata (R-13), regenerate `m100-acceptance-evidence.md` when next touched.
- **Tailscale:** dead `/` -> 8086 mapping and unrelated mappings (R-15).
