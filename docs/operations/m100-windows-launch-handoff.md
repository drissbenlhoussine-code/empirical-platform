# M100 — Windows PAPER launch handoff (single sitting)

**Scope:** PAPER only (Alpaca paper endpoint). LIVE stays disabled; nothing here enables it.
**Release SHA:** fill in the exact SHA after the Owner merges the reviewed branch
(`git rev-parse origin/release/v1-personal-paper`). Every command below uses `$SHA`.
**Status of this file:** prepared in the cloud. Nothing in it has been run on the Owner's host.
Cloud and Windows-CI results do not prove the host is healthy.

## 0. Owner approval boundaries (each is separate; none implies another)

| ID | Approves | Needed before |
|----|----------|---------------|
| A1 | Merge the reviewed PR(s) into `release/v1-personal-paper` | Phase 1 |
| A2 | Stop the running console and disable its autostart task | Phase 4 |
| A3 | Apply migration `f3a7c9e2b164` to the real Store B (and the Store B/C backup that precedes it) | Phase 5 |
| A4 | Start the console in **recovery mode** (read-only) | Phase 6 |
| A5 | Restart the console in **normal PAPER mode** (automatic Plan Manager on) | Phase 8 |
| A6 | Submit **one** PAPER entry order and its exit (broker order submission, even PAPER) | Phase 9 |

Read-only checks (Phases 1–3, 7, 10) need no approval. LIVE is not an approval option here.

## 1. Pin the release (read-only)

```powershell
cd C:\Users\LuxSy\Documents\trading
git fetch origin
git status --porcelain            # must print nothing
$SHA = (git rev-parse origin/release/v1-personal-paper)
git log -1 --format=%H $SHA       # record this SHA in the evidence folder
```
Stop if the worktree is dirty or the SHA is not the one the Owner approved.

## 2. Environment validation (read-only)

```powershell
.\.venv\Scripts\python.exe --version                    # 3.13.x
.\.venv\Scripts\python.exe -m pip install -e ".[persistence,object-storage]"
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe -c "import empirical_platform,sys;print(empirical_platform.__file__)"   # must be under this worktree\src
```
Required variables (never commit them; for the autostart task to work after logon they must ALSO be persistent *user* environment variables, because neither the wrapper nor the task XML sets any `EMPIRICAL_*` value): `EMPIRICAL_PLATFORM_POSTGRES_HOST/PORT/DATABASE/USER/PASSWORD`,
`EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE` (leave `_PAPER_EXIT_POSTGRES_HOST` **unset** — see the
deployment doc's follow-up note), `EMPIRICAL_ALPACA_PAPER_API_KEY`, `EMPIRICAL_ALPACA_PAPER_SECRET_KEY`,
`EMPIRICAL_ALPACA_PAPER_BASE_URL` (the paper host only; the client refuses anything else).
Never set `EMPIRICAL_PLATFORM_DATABASE_MODE=TEST` on this machine.

PostgreSQL preflight: `& "C:\Program Files\PostgreSQL\16\bin\pg_isready.exe" -h $env:EMPIRICAL_PLATFORM_POSTGRES_HOST -p $env:EMPIRICAL_PLATFORM_POSTGRES_PORT`.

## 3. Re-check time-sensitive conditions (read-only)

- Broker: account ACTIVE, not blocked, **zero positions, zero open orders** (step 1 of the deploy tool re-checks this; look yourself first in the Alpaca paper dashboard).
- Market hours: do the migration outside regular hours if possible; never with an open position.
- Console idle: no pending approval or submission in progress (the backup baseline is taken before shutdown).

## 4. Stop the console and the autostart task (needs A2)

The deploy tool now creates a **maintenance hold** (`%LOCALAPPDATA%\EmpiricalPlatform\safety\console-control\maintenance-hold.json`)
*before* it stops the console (step 5), and never removes it. The updated autostart wrapper
(`deploy/windows/run-v1-console.ps1`) checks that file before every launch and exits instead of relaunching; it also
treats the console's deliberate-shutdown exit code (64) as "do not restart", restarts only after real crashes (bounded
backoff, max 5 restarts per 600 s), and a full-mode console itself refuses to start (exit 74) while the hold exists.
A PAPER console also takes an exclusive OS file lock (`console-control\paper-exit-console.lock`), so a second
instance exits 73 without touching state.

**Belt and braces (still required):** a wrapper loop that is *already running* was started from the OLD script text
and has none of this protection, and the console you are about to stop was started by it. So first:

```powershell
Disable-ScheduledTask -TaskName "EmpiricalPlatformV1Console"   # only if it is registered; ignore "not found"
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like "*run-v1-console.ps1*" } | Select-Object ProcessId,CommandLine  # ignore your own PowerShell PID in this list; an OLD loop must be ended (Stop-Process on that powershell PID only, never the console)
```
An old loop (if any) must be ended before step 5, otherwise it relaunches a full-mode console ~10 s after the stop.
The new hold/lock make such a relaunch refuse itself, but do not rely on that for an old loop's first iteration.
Record the console PID: `Get-NetTCPConnection -LocalPort 8189 -State Listen | Select OwningProcess`.

## 5. Backup, shutdown, migrate, verify, recovery start — one tool run (needs A3 and A4)

```powershell
$env:PYTHONPATH = "$PWD\src"
.\.venv\Scripts\python.exe tools\personal_paper_deploy.py `
  --repo-path "$PWD" --expected-release-head $SHA `
  --manifest-path "$env:LOCALAPPDATA\EmpiricalPlatform\safety\personal-paper.json" `
  --backup-root "$env:LOCALAPPDATA\EmpiricalPlatform\backups" `
  --pg-bin "C:\Program Files\PostgreSQL\16\bin" `
  --console-host 127.0.0.1 --console-port 8189 --console-pid <PID from phase 4> `
  --journal-path "$env:LOCALAPPDATA\EmpiricalPlatform\deploy-journal.json" `
  --confirm-production
```
It runs 14 steps and **stops at step 14 with the console in recovery mode** (read-only, no Plan Manager).
Step 5 *is* the M098 authenticated-shutdown validation against the real console. Any failed gate halts with
recovery text and a journal; do **not** edit the manifest or restore a backup without separate Owner authorization.
- Re-run after a failure: the *same command* (same journal) resumes. Until step 7 completes, steps 1, 2, 3, 6 are re-checked.
- If the console was restarted by anyone after the backup, delete the journal and start from scratch.
- The maintenance hold stays in place after step 14 (and after any failure). That is deliberate: nothing can start a
  full-mode console until the Owner releases it in phase 8.

> If step 12 reports the console "did not begin listening" right after the step-5 shutdown, Windows may be holding port 8189 in TIME_WAIT under the exclusive-bind setting (untested on the host): wait a few minutes and re-run the same command (it resumes at step 12).

## 6. Verify recovery mode (read-only)

`http://127.0.0.1:8189/safety` (Plan Manager **not** running), `/health` (flat position). Save both pages.

## 7. Cloud-vs-host checks to run once (read-only)

`python tools\check_architecture.py .` and `python -m pytest tests/unit/test_v1_personal_paper_deploy.py -q`
(fast; the full suite already ran in CI on the same SHA — do not repeat it).

## 8. Normal PAPER start (needs A5)

First the Owner releases the maintenance hold. Stop the recovery-mode console first (only one console may run; a second one exits 73 at the lock, which is safe). The recovery console is read-only and was started detached, so Ctrl+C will not reach it:

```powershell
$pid8189 = (Get-NetTCPConnection -LocalPort 8189 -State Listen).OwningProcess
Stop-Process -Id $pid8189      # read-only recovery console: no orders or positions at risk; wait until the port is free
Get-NetTCPConnection -LocalPort 8189 -State Listen -ErrorAction SilentlyContinue   # must print nothing
```

Then release the hold. The
command refuses unless the deploy journal shows steps 12-14 completed, or the Owner passes the explicit
`--owner-override` flag instead of `--journal-path`:

```powershell
.\.venv\Scripts\python.exe -m empirical_platform.entrypoints.release_maintenance_hold `
  --journal-path "$env:LOCALAPPDATA\EmpiricalPlatform\deploy-journal.json"
```
Then start normal mode:

```powershell
.\.venv\Scripts\python.exe -m empirical_platform.entrypoints.operator_console --capability paper-exit --no-browser
```
(foreground, or via the wrapper only after Owner re-enables the task). Confirm `/safety` shows the manager running
and the kill switch **not** engaged-by-surprise. Keep the kill switch reachable.

## 9. One end-to-end PAPER round trip (needs A6)

Submit exactly one whole-share entry (the console enforces whole shares, a notional cap, and Owner approval of
each order). Do **not** click Prepare twice. Watch `/health` and the Alpaca paper dashboard. If an exit is
triggered and sits `ACCEPTED` but unfilled, or the console reports `NEEDS_ATTENTION`, **exit manually at the
broker** (known limitation D3 in the acceptance report). Finish flat.

## 10. Evidence to keep

`$SHA`, deploy journal JSON, backup dir listing + SHA-256s, `/safety` and `/health` captures before/after,
console log, Alpaca paper order/position screenshots, timestamps. Store under `%LOCALAPPDATA%\EmpiricalPlatform\evidence\<date>\`.

## 11. Stop conditions and rollback

Stop on any failed gate. Rollback of an applied migration is **never** automatic: the step-4 backup is preserved
and a restore needs separate Owner authorization. To stand down: stop the console gracefully, leave the broker flat,
leave the autostart task disabled.
