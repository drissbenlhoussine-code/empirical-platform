# PERSONAL PAPER operator handbook (Windows)

One page for running the platform day to day. **PAPER only**: orders can reach only
`https://paper-api.alpaca.markets`; there is no LIVE mode in this product. This is not a promise of
profitability. It does not replace `m100-windows-launch-handoff.md` (the one-time launch) or
`personal-paper-deployment.md` (the deploy tool); it supersedes `operator-console.md` for PAPER
(that file describes the SIMULATION console).

Verification tags used below: **[host 11-13]** = run on this host on 2026-11-13; **[tool]** = executed by
a tool that ran on this host (deploy, hourly backup); **[tests]** = covered by automated tests only;
**[unverified]** = not yet exercised on this host.

## 0. Facts

| Thing | Value |
|---|---|
| Deployed release | `240ad1f9a0726270551469e94f49718ee85d376e` on branch `release/v1-personal-paper` |
| Repo / Python | `C:\Users\LuxSy\Documents\trading` / `.venv\Scripts\python.exe` (3.13) |
| Console (local) | `http://127.0.0.1:8189/` (pages: `/today /active /history /safety /health`) |
| Console (iPhone, tailnet only) | `https://yanis.tail46bf93.ts.net/paper/today` (Tailscale Serve `/paper` -> 8189) |
| Local data | `%LOCALAPPDATA%\EmpiricalPlatform` = `C:\Users\LuxSy\AppData\Local\EmpiricalPlatform` |
| Safety manifest | `...\safety\personal-paper.json` (never edit by hand) |
| Hold / token | `...\safety\console-control\maintenance-hold.json` / `paper-exit-8189.json` |
| Deploy journal | `...\deploy-journal.json` (14 steps completed 2026-11-07; never delete) |
| Backups | `...\backups\personal-paper\<stamp>-<id>\{B.dump,C.dump,complete.json}`, hourly at :52, last 168 kept |
| Evidence | `...\evidence\<date>\` |
| PostgreSQL | dedicated cluster `%USERPROFILE%\empirical-platform-postgres`, `localhost:55433`, binaries `C:\Program Files\PostgreSQL\16\bin` |
| Store B / Store C | `empirical_platform_paper` (head `f3a7c9e2b164`) / `empirical_platform_paper_exit` (head `d4e9c2a7f183`) |
| Scheduled tasks | `EmpiricalPlatform Operator Console` (now **PostgreSQL only**, every 10 min + logon), `EmpiricalPlatform Personal Paper Backup` (hourly), `EmpiricalPlatform Post-Boot Verification` (logon) |
| Alpaca account | the PAPER account; credentials are persistent *User* environment variables `EMPIRICAL_ALPACA_PAPER_*` (never print or paste them) |

Trading rules in force (`CFG-089-PAPER` v1, read-only): AAPL only, long-only, whole shares, LIMIT at the
ask; 500 USD per trade; at most 1 share and 5 USD planned loss; daily loss limit 5.00; 1 order per day; 1
position; entries 09:35-15:30 ET; mandatory liquidation 15:45 ET; stop 1 %, target 2 %. **On early-close days
(2026-11-27, 2026-12-24) every entry is refused** unless the Owner first moves the liquidation time (an Owner
decision, not made).

## 1. Start the platform

The console is **not** autostarted (Owner decision pending, section 9). After a reboot or a logon:

```powershell
# 1. PostgreSQL 55433 (started by the scheduled task at logon / every 10 min)            [host 11-13]
& "C:\Program Files\PostgreSQL\16\bin\pg_isready.exe" -h localhost -p 55433
#    not ready? run the task now:
Start-ScheduledTask -TaskName "EmpiricalPlatform Operator Console"      # PostgreSQL only; starts no console

# 2. Nothing may already own the port, and no maintenance hold                           [host 11-13]
Get-NetTCPConnection -LocalPort 8189 -State Listen -ErrorAction SilentlyContinue     # must print nothing
Test-Path "$env:LOCALAPPDATA\EmpiricalPlatform\safety\console-control\maintenance-hold.json"   # must be False

# 3. Start the PAPER console, detached, with logs                                        [host 11-13]
$Repo = "C:\Users\LuxSy\Documents\trading"; Set-Location $Repo
foreach ($k in [Environment]::GetEnvironmentVariables("User").Keys) { if ($k -like "EMPIRICAL*") { Set-Item "Env:$k" ([Environment]::GetEnvironmentVariable($k,"User")) } }
$env:PYTHONPATH = "$Repo\src;$Repo"; $env:PYTHONUNBUFFERED = "1"; $env:PYTHONIOENCODING = "utf-8"
$Ev = Join-Path $env:LOCALAPPDATA "EmpiricalPlatform\evidence\$(Get-Date -Format yyyy-MM-dd)"; New-Item -ItemType Directory -Force $Ev | Out-Null
Start-Process -FilePath "$Repo\.venv\Scripts\python.exe" -WorkingDirectory $Repo -WindowStyle Hidden `
  -RedirectStandardOutput "$Ev\console.out.log" -RedirectStandardError "$Ev\console.err.log" `
  -ArgumentList @('-m','empirical_platform.entrypoints.operator_console','--capability','paper-exit','--no-browser','--host','127.0.0.1','--port','8189','--base-path','/paper')
```

Console exit codes (read `console.err.log`): `0` Ctrl+C, `64` authenticated shutdown (both = deliberate, do not
restart), `2` refused at startup (read the message), `73` another console already holds the lock, `74`
maintenance hold present (release only with `release_maintenance_hold --journal-path`, never by deleting files).

**Recovery mode** (read-only; no Plan Manager; no exit can be sent) is the same command plus
`'--recovery-mode'`. Use it to look at the state after a failure before resuming. **[tool: deploy step 12]**

## 2. Confirm PAPER health (do this after every start and before relying on it)

```powershell
$s = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8189/safety).Content -replace '<[^>]+>',' ' -replace '\s+',' '
[regex]::Match($s,'Automatic position manager.{0,140}').Value      # must say HEALTHY ... no error   [host 11-13]
[regex]::Match($s,'Kill switch.{0,50}').Value                       # "Execution stop is released" = entries allowed
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8189/health -OutFile "$env:TEMP\health.html"   # then open it
```

`/health` must show: trading endpoint `paper-api.alpaca.markets`, pinned PAPER host **Yes**, account ACTIVE, trading /
account blocked and trade suspended all **No**. `/safety` must show Environment PAPER, **Live: UNAVAILABLE**, manager
**HEALTHY**. Anything else (STALE, STOPPED, UNKNOWN, a red banner "AUTOMATIC EXIT STOPPED ...", a block flag): do not
enter; if a position is open, go to section 7.

## 3. iPhone dashboard

Open **`https://yanis.tail46bf93.ts.net/paper/today`** in Safari on the iPhone (Tailscale must be connected on the
phone). Path-test from the Windows PC works **[host 11-13]**: `/paper/safety`, `/paper/health`, `/paper/today` all
return 200. The page is tailnet-only (Funnel is off). The first time, **confirm on the phone itself [unverified]**:
Today, Active, History, Safety and Health open; the nav links stay under `/paper/...`; the text fits the screen.
If a page says HTTP 421, the host name is not in `EMPIRICAL_PLATFORM_CONSOLE_ALLOWED_HOSTS` (User variable, read at
console start; currently `yanis.tail46bf93.ts.net`). Never expose the console with Tailscale Funnel or any port forward.

## 4. Positions and orders

- **Today**: counts and the decision queue. **Active**: working entry orders, open positions with the plan (stop,
  target, mandatory exit, management status *Monitoring / Exit submitted / Needs attention / Closed*).
  **History**: round trips; "Position closed" is shown only after the broker was checked at zero.
- Independent truth from the broker (read-only):

```powershell
foreach ($k in [Environment]::GetEnvironmentVariables("User").Keys) { if ($k -like "EMPIRICAL_ALPACA*") { Set-Item "Env:$k" ([Environment]::GetEnvironmentVariable($k,"User")) } }
$h = @{ "APCA-API-KEY-ID"=$env:EMPIRICAL_ALPACA_PAPER_API_KEY; "APCA-API-SECRET-KEY"=$env:EMPIRICAL_ALPACA_PAPER_SECRET_KEY }; $b = "https://paper-api.alpaca.markets"
"positions=$((Invoke-RestMethod "$b/v2/positions" -Headers $h | ? {$_} | Measure).Count) open_orders=$((Invoke-RestMethod "$b/v2/orders?status=open&limit=500" -Headers $h | ? {$_} | Measure).Count)"   # [host 11-13]
Remove-Variable h
```
  (Use `| ? {$_} | Measure`; `@(Invoke-RestMethod ...).Count` prints a false 1 when the answer is empty.)

## 5. Stop trading safely

1. **Stop new entries (always safe)**: Safety page -> **ACTIVATE KILL SWITCH** (phone or PC). It blocks new entries
   only; it never blocks or delays an exit (`kill-switch.md`). **[tests]**
2. **A position is open**: do not stop the console. It is what protects the position. Close the position first
   (Active -> **Review exit** -> **CONFIRM EXIT**, once), wait for "Position closed", check section 4.
3. **Flat and idle**: stop the console with the authenticated shutdown (never `Stop-Process` unless section 8 says so):

```powershell
# After the closure PR is deployed:                                    [tests; same call path as host 11-13 21:22]
$env:PYTHONPATH = "C:\Users\LuxSy\Documents\trading\src;C:\Users\LuxSy\Documents\trading"
& "C:\Users\LuxSy\Documents\trading\.venv\Scripts\python.exe" "C:\Users\LuxSy\Documents\trading\tools\stop_paper_console.py" --check   # who owns 8189
& "C:\Users\LuxSy\Documents\trading\.venv\Scripts\python.exe" "C:\Users\LuxSy\Documents\trading\tools\stop_paper_console.py"           # stop it; exit 0 = stopped
```
   Until that PR is deployed, the same shutdown was executed on this host on 2026-11-13 by calling
   `RealProcessPort.graceful_stop` from the deployed `tools/personal_paper_deploy.py` (HTTP 202, PID echoed, process
   tree gone, no fallback needed). Ask for it rather than improvising.
4. Confirm: `Get-NetTCPConnection -LocalPort 8189 -State Listen -ErrorAction SilentlyContinue` prints nothing.

## 6. Entries and exits at a glance

- An entry happens only through the Owner flow: **Prepare** (once) -> review the exact terms -> **CONFIRM APPROVAL** (once).
  The engine computes the size; if the page shows a quantity or notional above what you authorized, press Reject.
- After a fill the Plan Manager (tick every 15 s) watches stop, target and the 15:45 ET mandatory exit. Exits are LIMIT
  sell-to-close at the bid, repriced 10 bps lower per attempt (never more than 50 bps below the bid), at most 5 attempts
  per session, never a market order, never re-sent while an outcome is unknown. **[tests]**
- An uncovered situation shows a red banner on Active and Safety: *AUTOMATIC EXIT STOPPED -- CLOSE THIS POSITION
  MANUALLY AT THE BROKER*. Act (section 7).

## 7. Restart after a failure

| Situation | Do |
|---|---|
| Console not running, broker flat, no hold | Section 1 (start), then section 2 |
| Console not running, **position open** | Start in **recovery mode** to look (read-only), then restart **without** it with the Owner present. The manager resumes from the database (restart with a position is covered by ACC-21 **[tests]**). Check the position at the broker meanwhile |
| Manager card STALE / STOPPED / UNKNOWN, or red banner, position open | Owner acts: **Review exit -> CONFIRM EXIT**; if refused, close at the Alpaca paper dashboard (section 8) |
| PostgreSQL down | `Start-ScheduledTask -TaskName "EmpiricalPlatform Operator Console"`, wait, `pg_isready`, then start the console |
| Hold file present | A deployment left it deliberately. Do not delete. Release only with `python -m empirical_platform.entrypoints.release_maintenance_hold --journal-path "%LOCALAPPDATA%\EmpiricalPlatform\deploy-journal.json"` after reading the journal **[host 11-13]** |
| `SUBMISSION_UNKNOWN` / "Needs attention" on an order | Never re-send. The console reconciles by client order id every tick. Compare with the broker (section 4) |

## 8. Emergency shutdown (position at risk, console misbehaving)

1. **Kill switch** on `/safety` (stops new entries; exits keep working).
2. Try **Review exit -> CONFIRM EXIT** on `/active`.
3. If that cannot work: stop the console (section 5.3) so it cannot send a second sell, then in the Alpaca **paper**
   dashboard cancel any working sell for the symbol and close the position. Verify with section 4 (positions 0, open orders 0).
4. Record the closure so a restart does not retry it: `python -m empirical_platform.entrypoints.record_external_position_closure <entry_intent_governance_id> <client_order_id> "<your name>"`
   (ids: console execution page and the Alpaca order detail). **[tests; handoff Phase 14]**
5. Last resort only if the authenticated stop fails *and* the account is flat: `Stop-Process -Id <PID from --check>`.
   State is in PostgreSQL, but an in-flight reconcile pass is cut short. Do not restart normal mode until the Owner decides.

## 9. Backup and restore

- Hourly backups run from `EmpiricalPlatform Personal Paper Backup` (script `scripts\backup-personal-paper.ps1`, keep 168
  complete sets, ~0.4 MB each). Status: `Get-Content "$env:LOCALAPPDATA\EmpiricalPlatform\safety\backup-status.json"`
  (`BACKUP_COMPLETE`, `exit_code 0`) **[tool]**. Take one now: `Start-ScheduledTask -TaskName "EmpiricalPlatform Personal Paper Backup"`.
  Avoid launching deploy/migration work between :50 and :55 (backup lock).
- **Verify a set before trusting it** (SHA-256 against `complete.json`, and `pg_restore --list` shows `alembic_version`):

```powershell
$set = Get-ChildItem "$env:LOCALAPPDATA\EmpiricalPlatform\backups\personal-paper" -Directory | ? { Test-Path "$($_.FullName)\complete.json" } | Sort Name | Select -Last 1
$c = Get-Content "$($set.FullName)\complete.json" -Raw | ConvertFrom-Json
foreach ($s in 'B','C') { (Get-FileHash "$($set.FullName)\$s.dump" -Algorithm SHA256).Hash.ToLower() -eq $c.files.$s.sha256 }   # both True   [host 11-13]
```
  A corrupted dump is **not** always rejected by `pg_restore` (a flipped byte restored with exit 0 in the rehearsal), so
  **the SHA-256 check is mandatory before any restore**. Truncated and empty dumps are rejected.
- **Restore rehearsal (verified 2026-11-13)**: restore only into **disposable** databases on a throwaway server, never over
  Store B/C. `initdb.exe` is blocked on this host by an Application Control policy; a throwaway container works:
  `docker run -d --name <name> -p 127.0.0.1:55499:5432 -e POSTGRES_USER=empirical -e POSTGRES_HOST_AUTH_METHOD=trust postgres:16`,
  then `createdb`, `pg_restore --no-owner --no-privileges --exit-on-error -d <disposable> <dump>`, check
  `SELECT version_num FROM alembic_version` (B `f3a7c9e2b164`, C `d4e9c2a7f183`) and the row counts in `complete.json`,
  then drop the databases and remove the container. Result 2026-11-13: both stores restored from real backups, heads and
  counts exact; the pinned migration SQL applied to the pre-migration backup reproduced the live schema.
- **Restoring over the live stores is a separate Owner-authorized operation** (console stopped, hold in place, a rehearsal
  first, cross-store reconciliation because B and C are separate snapshots). There is no downgrade command.

## 10. Known limitations (read these)

- **No autostart for the console** and **no external alerting**: nothing pages you. If the console is down, positions are unmanaged.
  Do not leave an open position unattended. The Windows restart path is **[unverified]** (the last reboot test, 2026-10-14, failed for the earlier simulation setup; the PostgreSQL-only task has not been through a reboot). After any reboot run `deploy\windows\verify-paper-after-boot.ps1` (read-only).
- The daily-loss figure is `equity - last_equity` (includes unrealized P&L): an open losing position can block a new entry.
- A STOP/TARGET/MANDATORY exit is **not sent** while the quote spread/age gate fails; the banner appears after 60 s (Owner decision pending).
- Alpaca specifics are untested against the real service until the first supervised order: `pending_cancel` latency, the status
  of an expired DAY order, the meaning of `last_equity`. Unknown statuses fail closed.
- Quotes are IEX and can differ from the Alpaca dashboard.
- The session cookie has no `Secure` attribute (the tailnet connection is HTTPS; low risk).
- Nothing here has real-money evidence. LIVE is not assessed and is disabled (`m100-live-readiness.md`).
