# M100 -- Windows PAPER launch: Owner's sequential procedure

**This is the Owner's copy-ready script for the day the Windows host is powered on.** It was written in the
cloud and checked against the code. Nothing in it has been run on the host or against the broker, and nothing in
it authorizes any real-host action by itself: every risk-bearing phase waits for a written Owner approval (A1-A6
below). Read a phase completely before pasting anything from it.

## 0. Scope and safety boundaries

- **PAPER only.** Orders can reach only `https://paper-api.alpaca.markets` (market data from
  `data.alpaca.markets`, IEX feed). The broker client pins that host and refuses anything else, including
  redirects. The console has no `--capability live`; no LIVE configuration variable exists. LIVE is not an
  option in this document and cannot be enabled by following it. LIVE readiness is a separate, failing
  assessment: `docs/operations/m100-live-readiness.md`.
- **The Owner never changes a threshold in this procedure.** Where the document says CHECK a limit, it means read
  it and stop if it is not what you intended. Changing a limit is a separate Owner decision made outside this
  document (a new configuration version); do not do it mid-run.
- **No secret is ever typed, pasted or printed.** The Alpaca keys and the PostgreSQL password are already
  in the environment. Commands here print only presence (True/False) or non-secret values. Never paste a key into
  a transcript, screenshot or chat.
- **Nothing is retried blindly.** If a command fails, read the STOP IF list and the troubleshooting table
  ("Troubleshooting by journal step", below). Do not improvise a different command.

### Approvals (each is separate; none implies another)

| ID | Authorizes | Does NOT authorize | Needed before |
|----|------------|--------------------|---------------|
| A1 | Merge of PR #49 into `release/v1-personal-paper`; names the approved merge SHA | Any action on the host | Phase 3 |
| A2 | Disable the autostart task; end an old wrapper loop; stop an already-running old console (Phase 2 only) | Migration, restart, orders | Phase 2 actions |
| A3 | Take the Store B/C backup and apply migration `f3a7c9e2b164` to the real Store B | Starting any console mode, orders | Phase 6 and Phase 7 |
| A4 | Start the console in **recovery mode** (read-only, no Plan Manager, no exits) | Normal mode, orders | Phase 7 launch (the same command performs it) |
| A5 | Release the maintenance hold; start the console in **normal PAPER mode** (Plan Manager on) | Any order | Phase 10 |
| A6 | **One** PAPER entry order for the symbol and size the Owner names, and its exit | A second order, any limit change, anything LIVE | Phase 12 |

Approvals are not combined. They lapse at the end of the sitting in which they were given. Record each one (ID,
exact sentence, date/time) in the evidence checklist (Phase 16). The tool for Phases 7-8 is one command, so A3 and
A4 must both be on record **before** it is launched (it cannot be stopped at step 11; it always runs on to
step 14).

### Phase summary

| # | Phase | Gate | Changes anything? |
|---|-------|------|-------------------|
| 1 | Power on the host | none | no |
| 2 | Existing processes and autostart | A2 for any stop/disable | only after A2 |
| 3 | Verify the release SHA | A1 on record | local git only if behind |
| 4 | Verify broker PAPER environment | none | no (GET only) |
| 5 | Verify PostgreSQL | none | no (SELECT only) |
| 6 | Fresh backup | A3 | backup dir + manifest row-count floors |
| 7 | Authorized migration (deploy tool, steps 1-14) | A3 + A4 | **Store B schema**, manifest, console |
| 8 | Recovery-mode checks | A4 (given in Phase 7) | no |
| 9 | Confirm the shutdown control worked | none | no |
| 10 | Start normal PAPER operation | A5 | releases hold, starts console |
| 11 | Validate live PAPER broker connectivity | none | no (no orders) |
| 12 | ONE PAPER order test | A6 | **places one PAPER order** |
| 13 | Verify order and position reconciliation | none | no |
| 14 | Verify exits and risk limits | A6 covers the exit | the exit order |
| 15 | Confirm monitoring | none | no |
| 16 | Final evidence, stand-down, rollback | Owner decision for any autostart | no |

### Known limits of cloud verification

- **Windows-only mechanisms are proven only by Windows CI tests plus this first host run:** the `msvcrt` console
  lock, `SO_EXCLUSIVEADDRUSE` port exclusivity, the PowerShell autostart wrapper, Task Scheduler import of
  `deploy/windows/v1-console-task.xml`, the Win32 token ACL/junction checks, and the listener-table PID lookup.
  The cloud cannot run any of them. Treat each as unproven until its phase passes here.
- **Alpaca specifics are untested against the real service:** `pending_cancel` latency, the status name of a
  DAY order that expires, and the real meaning of `last_equity`. The 29-test acceptance matrix ran against a
  scripted local exchange with virtual time (real HTTP client, hosts pinned, WSGI called in-process).
- **The daily-loss figure is a proxy:** `equity - last_equity`. It includes unrealized profit and loss, so an
  open position that is under water can block further entries. That is deliberate (conservative), not a bug.
- **Port 8189 `TIME_WAIT`:** with exclusive bind on Windows, a console restarted within a few minutes of a stop
  may fail to bind (untested on the host). If step 12 reports the console "did not begin listening", wait a few
  minutes and re-run the same deploy command; it resumes at step 12.
- **No external alerting exists.** `manager_liveness_alert` is defined in code but not wired into the console.
  Monitoring is you looking at the pages (Phase 15). Do not leave an open position unattended.
- **Quotes come from the IEX feed**, which can differ from what the Alpaca dashboard shows.
- Known P2 items (acceptance report): a blocked `/confirm-approval` shows no outcome flash; a refused Prepare
  followed by another within the same second raises a raw persistence error (fails closed); a working BUY is
  worded "a position of N already exists".

---

## Session variables (run at the start of EVERY new PowerShell window)

PowerShell variables do not survive a closed window. Every phase below assumes this block ran in the same
window. It creates the evidence folder and starts a transcript. Use a normal (not Administrator) PowerShell
prompt, as the same user that owns the repository and `%LOCALAPPDATA%\EmpiricalPlatform`.

```powershell
$Repo      = "C:\Users\LuxSy\Documents\trading"
$Local     = Join-Path $env:LOCALAPPDATA "EmpiricalPlatform"
$Safety    = Join-Path $Local "safety"
$Control   = Join-Path $Safety "console-control"
$Manifest  = Join-Path $Safety "personal-paper.json"
$HoldFile  = Join-Path $Control "maintenance-hold.json"
$Journal   = Join-Path $Local "deploy-journal.json"
$Backups   = Join-Path $Local "backups"
$PgBin     = "C:\Program Files\PostgreSQL\16\bin"
$Py        = Join-Path $Repo ".venv\Scripts\python.exe"
$Stamp     = Get-Date -Format "yyyy-MM-dd"
$Evidence  = Join-Path $Local "evidence\$Stamp"
New-Item -ItemType Directory -Force -Path $Evidence | Out-Null
try { Start-Transcript -Path (Join-Path $Evidence "transcript.txt") -Append | Out-Null } catch { "transcript already running" }
Set-Location $Repo
# src for empirical_platform; the repo root so that 'tools.personal_paper_backup' imports (deploy step 4).
$env:PYTHONPATH = "$Repo\src;$Repo"
```

---

## Phase 1 -- Power on the host

**Purpose.** Establish that the machine, clock, network and database service are in a state worth working on.

**Preconditions.** Host powered on, Owner logged in as the normal user that owns `C:\Users\LuxSy\Documents\trading`.

**Commands** (read-only):

```powershell
Get-Date -Format o
(Get-TimeZone).Id
w32tm /query /status
$PSVersionTable.PSVersion
Get-Service -Name "postgresql*" | Select-Object Name,Status,StartType
Get-PSDrive -Name C | Select-Object Used,Free
Test-NetConnection paper-api.alpaca.markets -Port 443 | Select-Object ComputerName,TcpTestSucceeded
Test-NetConnection data.alpaca.markets -Port 443 | Select-Object ComputerName,TcpTestSucceeded
"repo: $(Test-Path $Repo)  venv python: $(Test-Path $Py)  manifest: $(Test-Path $Manifest)"
```

**Expected result.** Clock within a second or two of real time (`w32tm` shows a recent sync, small offset);
PostgreSQL service `Running`; several GB free; both Alpaca hosts `TcpTestSucceeded : True`; the three paths `True`.

**STOP IF**
- the clock is visibly wrong or the last sync is days old (the mandatory-liquidation deadline and the daily
  limits depend on correct time; resynchronising the clock is a system change -- the Owner decides, then re-run
  this phase);
- the PostgreSQL service is not `Running` (start it yourself; do not continue until Phase 5 passes);
- either Alpaca host is unreachable;
- any of the three paths is `False`.

---

## Phase 2 -- Existing processes and autostart

**Purpose.** Make sure nothing is already running, will relaunch itself, or holds the ports before anything is
stopped, migrated or started. This is the most likely place for a surprise.

**Preconditions.** Phase 1 passed. Run the discovery commands only -- they change nothing.

**Commands -- discovery (read-only):**

```powershell
"--- listeners on 8189 / 8086 ---"
Get-NetTCPConnection -LocalPort 8189,8086 -State Listen -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,OwningProcess
"--- TIME_WAIT / other states on those ports ---"
Get-NetTCPConnection -LocalPort 8189,8086 -ErrorAction SilentlyContinue |
  Group-Object State | Select-Object Name,Count
"--- scheduled tasks that look like ours ---"
Get-ScheduledTask | Where-Object {
  $_.TaskName -like "*Empirical*" -or
  ($_.Actions | Where-Object { $_.Arguments -like "*run-v1-console.ps1*" })
} | Select-Object TaskName,State,TaskPath
"--- processes (this window's own PID, $PID, is excluded) ---"
Get-CimInstance Win32_Process | Where-Object {
  $_.ProcessId -ne $PID -and (
    $_.CommandLine -like "*run-v1-console*" -or
    $_.CommandLine -like "*operator_console*" -or
    $_.CommandLine -like "*empirical-platform-operator-console*" -or
    $_.CommandLine -like "*personal_paper_deploy*")
} | Select-Object ProcessId,ParentProcessId,Name,CommandLine
"--- other autostart places ---"
Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup" -ErrorAction SilentlyContinue
Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -ErrorAction SilentlyContinue
"--- hold / token / lock files (names only; never open the token file) ---"
"hold present: $(Test-Path $HoldFile)"
Get-ChildItem $Control -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime
```

Note: the Task Scheduler task name is whatever the Owner typed when importing `v1-console-task.xml` (the XML itself
carries no name; the repository documents it as `EmpiricalPlatformV1Console`). Use the `TaskName` the listing
printed, not a remembered one.

**Interpretation.**

| What you see | Meaning | Action |
|---|---|---|
| Nothing on 8189/8086, no task, no matching process, no hold | Clean host | Go to Phase 3 |
| A task exists and is `Ready`/`Running` | It will relaunch a console (a wrapper loop started from the OLD script uses port **8086**; the current script uses 8189) | Needs A2: disable it |
| A matching `run-v1-console` PowerShell process | A wrapper loop, possibly OLD code with no hold/lock protection | Needs A2: end that PowerShell PID only |
| A listener on 8189 | A console the deploy tool can stop | Check for its token file (below) |
| A listener on 8086 only | A console from an OLD autostart wrapper loop (the pre-M100 script passed no `--port`, so it used the default 8086; the current script passes `--port 8189 --base-path /paper`). `personal_paper_deploy.py` looks at 8189 and will **not** see it | Needs A2: stop it by hand (below) before Phase 7 |
| A hold file present | A previous deployment attempt left it, deliberately | Do not delete it. Note it; Phase 7 resumes/uses it |

**Is the running console one the deploy tool can stop gracefully?** Only a console started with M098-or-later
code has an authenticated shutdown route. Check without opening the file:

```powershell
Test-Path (Join-Path $Control "paper-exit-8189.json")
```

- `True` and a listener on 8189: leave that console running. Deploy step 5 creates the hold first, then stops it
  with the authenticated request (this also exercises the shutdown control for real -- Phase 9).
- No token file, or the console is on 8086, or it predates M098: the tool will refuse to guess. It must be stopped
  by hand, which needs A2. Prefer **Ctrl+C in the window that started it** (runs the documented shutdown order:
  reconciler joined, Plan Manager stopped, server and database closed). Only if no window exists, and only with
  the account confirmed flat (Phase 4) and the Owner's approval, use `Stop-Process -Id <console listener PID>`.
  Do not use `Stop-ScheduledTask` for this: it ends the whole task tree, including the console, abruptly.

**Commands -- actions, ONLY after the A2 sentence below is on record:**

```powershell
# 1. Prevent any relaunch (use the TaskName printed above; a task that does not exist -> ignore "not found").
Disable-ScheduledTask -TaskName "<TaskName from the listing>"

# 2. End an OLD wrapper loop: the PowerShell process, NEVER the console and never this window.
Stop-Process -Id <wrapper PowerShell ProcessId from the listing>

# 3. Re-check: no wrapper left, task Disabled.
Get-ScheduledTask -TaskName "<TaskName from the listing>" | Select-Object TaskName,State
Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -like "*run-v1-console*" } |
  Select-Object ProcessId,CommandLine
```

An old loop must be ended **before** Phase 7: otherwise it relaunches a full-mode console about 10 s after the
deploy tool stops the old one.

**Expected result.** Task `Disabled` (or absent); no wrapper process; the only listener, if any, is a console on
8189 that has a token file (to be stopped by the deploy tool), or no listener at all.

**STOP IF**
- a listener appears on 8189 or 8086 whose command line you do not recognise;
- you cannot tell whether a console is running;
- any process matches the patterns that you cannot explain (this window's own PID is already excluded by the
  filter);
- the old console is mid-way through an approval or submission (look at its `/active` page): wait until nothing
  is in flight;
- you are about to end a console process other than by Ctrl+C without the Owner's explicit approval.

**Owner approval gate A2 -- required before any command in the "actions" block.**
Exact sentence: `A2 approved on <date time>: disable the autostart task "<TaskName>", end the old wrapper loop PID <n>, and stop the running console PID <n> by <Ctrl+C | Stop-Process>. The Alpaca paper account is flat with no open orders; nothing is in flight.`
(Delete the clauses that do not apply.)

---

## Phase 3 -- Verify the release SHA

**Purpose.** Prove the worktree is clean, on `release/v1-personal-paper`, and at exactly the commit the Owner
approved when merging PR #49. The deploy tool re-checks this in step 3 and refuses on any difference; checking it
first costs nothing.

**Preconditions.** A1 on record: the Owner has merged PR #49 into `release/v1-personal-paper` and has the merge
commit SHA from GitHub (the PR page, or `gh pr view 49 --json state,mergeCommit`). Phase 2 shows no console is
running from this worktree (updating source files under a running Python process is not safe).

**Commands:**

```powershell
Set-Location $Repo
git status --porcelain                    # must print nothing
git rev-parse --abbrev-ref HEAD           # must print: release/v1-personal-paper
git fetch origin
$ApprovedSha = "<PASTE the Owner-approved merge SHA of PR #49>"
$OriginSha   = (git rev-parse origin/release/v1-personal-paper).Trim()
$HeadSha     = (git rev-parse HEAD).Trim()
"approved=$ApprovedSha"; "origin  =$OriginSha"; "HEAD    =$HeadSha"
if ($OriginSha -ne $ApprovedSha) { throw "origin/release/v1-personal-paper is NOT the approved SHA -- stop and ask the Owner" }
```

If `HEAD` differs from `$ApprovedSha` and the branch is only *behind* (no local commits, clean), bring it forward
to the approved SHA -- and nothing else:

```powershell
git merge --ff-only $ApprovedSha
(git rev-parse HEAD).Trim() -eq $ApprovedSha        # must print True
```

Environment and code checks (read-only; the pip line changes only `.venv`, run it only if the import check fails):

```powershell
& $Py --version                                     # 3.13.x
& $Py -c "import empirical_platform,sys;print(empirical_platform.__file__)"   # must be under $Repo\src
Test-Path (Join-Path $Repo ".venv\Scripts\empirical-platform-operator-console.exe")   # True; deploy step 12 launches this exact file
Test-Path (Join-Path $Repo "tools\personal_paper_deploy_migration_f3a7c9e2b164.sql")  # True
$pinned = (Select-String -Path "$Repo\tools\personal_paper_deploy.py" -Pattern '^MIGRATION_SQL_SHA256: Final = "([0-9a-f]{64})"').Matches[0].Groups[1].Value
$actual = (Get-FileHash "$Repo\tools\personal_paper_deploy_migration_f3a7c9e2b164.sql" -Algorithm SHA256).Hash.ToLower()
"migration SQL matches the pinned hash: $($pinned -eq $actual)"
& $Py tools\check_architecture.py .
& $Py -m pytest tests/unit/test_v1_personal_paper_deploy.py tests/unit/test_console_lifecycle.py -q
# Only if the import check above failed:
# & $Py -m pip install -e ".[persistence,object-storage]"
```

The full test suite already ran in CI on the same SHA; do not repeat it.

**Expected result.** Clean tree; branch `release/v1-personal-paper`; `HEAD == origin == $ApprovedSha`; import path
under `$Repo\src`; both files exist; hash comparison `True`; architecture check and the two test files pass.

**STOP IF**
- `git status --porcelain` prints anything (do not commit, reset or stash on the Owner's behalf);
- the branch is not `release/v1-personal-paper`, or is detached;
- `origin` is not the approved SHA (someone pushed after approval; the Owner re-approves);
- `HEAD` is **ahead** of the approved SHA or diverged;
- the migration hash comparison is `False`, or `check_architecture` / the tests fail.

---

## Phase 4 -- Verify the broker PAPER environment (read-only)

**Purpose.** Confirm the keys exist, the base URL is the paper host, and the account is active and flat -- before
the deploy tool asks the same question in step 1.

**Preconditions.** Phase 1 passed. Deploy step 1 and the console both read the same three variables.
(For the autostart task to work after logon they must also be persistent *user* environment variables: neither
the wrapper nor the task XML sets any `EMPIRICAL_*` value.)

**Commands (GET only; secrets are used in memory and never printed):**

```powershell
foreach ($n in "EMPIRICAL_ALPACA_PAPER_API_KEY","EMPIRICAL_ALPACA_PAPER_SECRET_KEY","EMPIRICAL_ALPACA_PAPER_BASE_URL") {
  "{0,-38} process-env present={1}  user-env present={2}" -f $n,
    [bool][Environment]::GetEnvironmentVariable($n,"Process"), [bool][Environment]::GetEnvironmentVariable($n,"User")
}
"base url: $($env:EMPIRICAL_ALPACA_PAPER_BASE_URL)"     # must be exactly https://paper-api.alpaca.markets

$h    = @{ "APCA-API-KEY-ID" = $env:EMPIRICAL_ALPACA_PAPER_API_KEY; "APCA-API-SECRET-KEY" = $env:EMPIRICAL_ALPACA_PAPER_SECRET_KEY }
$base = "https://paper-api.alpaca.markets"
$acct = Invoke-RestMethod -Method Get -Uri "$base/v2/account" -Headers $h
$acct | Select-Object status,trading_blocked,account_blocked,trade_suspended_by_user,currency,cash,equity,last_equity | Format-List
"positions: $(@(Invoke-RestMethod -Method Get -Uri "$base/v2/positions" -Headers $h).Count)"
$open = @(Invoke-RestMethod -Method Get -Uri "$base/v2/orders?status=open&limit=500" -Headers $h)
"open orders: $($open.Count)"
$open | Group-Object status | Select-Object Name,Count
Invoke-RestMethod -Method Get -Uri "$base/v2/clock" -Headers $h | Format-List
Remove-Variable h,acct,open
```

Also look at the Alpaca **paper** dashboard in a browser: account flat, no open orders, and the account is the
paper account (not live).

**Expected result.** Both key variables and the URL present; URL exactly the paper host; `status : ACTIVE`;
`trading_blocked`, `account_blocked`, `trade_suspended_by_user` all `False`; `positions: 0`; `open orders: 0`;
`last_equity` present (a missing one makes the daily-loss check refuse).

**STOP IF**
- any variable is missing, or the base URL is anything but the paper host;
- the account is not `ACTIVE` or any block flag is `True`;
- positions or open orders are not zero, or any open order has a status other than `new`, `accepted`,
  `pending_new`, `partially_filled` (deploy step 1 refuses these too);
- the dashboard shows a LIVE account, or a balance that is not the expected paper balance.

---

## Phase 5 -- Verify PostgreSQL

**Purpose.** Confirm both stores answer, are the real protected databases, match the safety manifest, and that
the process is not in TEST mode.

**Preconditions.** Phases 1-4 passed. Required variables (never commit them):
`EMPIRICAL_PLATFORM_POSTGRES_HOST/PORT/DATABASE/USER/PASSWORD`, and
`EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE`. Leave `EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST` **unset**
(the console reuses Store B's host and credentials for Store C; setting it would make the deploy tool and the
console disagree -- see the deployment doc's follow-up note).

**Commands (SELECT only):**

```powershell
foreach ($n in "EMPIRICAL_PLATFORM_POSTGRES_HOST","EMPIRICAL_PLATFORM_POSTGRES_PORT","EMPIRICAL_PLATFORM_POSTGRES_DATABASE",
               "EMPIRICAL_PLATFORM_POSTGRES_USER","EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE") {
  "{0,-52} = {1}" -f $n, [Environment]::GetEnvironmentVariable($n,"Process")
}
"password present: $([bool]$env:EMPIRICAL_PLATFORM_POSTGRES_PASSWORD)"
"PAPER_EXIT_POSTGRES_HOST set (must be False): $([bool]$env:EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_HOST)"
foreach ($scope in "Process","User","Machine") {
  "DATABASE_MODE ($scope) = '$([Environment]::GetEnvironmentVariable('EMPIRICAL_PLATFORM_DATABASE_MODE',$scope))'   (must be empty, never TEST)"
}

& "$PgBin\pg_isready.exe" -h $env:EMPIRICAL_PLATFORM_POSTGRES_HOST -p $env:EMPIRICAL_PLATFORM_POSTGRES_PORT

$env:PGPASSWORD = $env:EMPIRICAL_PLATFORM_POSTGRES_PASSWORD
$StoreC = if ($env:EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE) { $env:EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE } else { "empirical_platform_paper_exit" }
function Invoke-Psql($db, $sql) {
  & "$PgBin\psql.exe" --no-password -h $env:EMPIRICAL_PLATFORM_POSTGRES_HOST -p $env:EMPIRICAL_PLATFORM_POSTGRES_PORT `
    -U $env:EMPIRICAL_PLATFORM_POSTGRES_USER -d $db -At -F " | " -c $sql
}
"--- Store B ---"
Invoke-Psql $env:EMPIRICAL_PLATFORM_POSTGRES_DATABASE "SELECT current_database(), inet_server_port(), shobj_description(oid,'pg_database') FROM pg_database WHERE datname = current_database()"
Invoke-Psql $env:EMPIRICAL_PLATFORM_POSTGRES_DATABASE "SELECT version_num FROM public.alembic_version"
Invoke-Psql $env:EMPIRICAL_PLATFORM_POSTGRES_DATABASE "SELECT (SELECT count(*) FROM public.paper_execution_attempt) AS attempts, (SELECT count(*) FROM public.approved_plan) AS approved_plans"
"--- Store C ---"
Invoke-Psql $StoreC "SELECT current_database(), inet_server_port(), shobj_description(oid,'pg_database') FROM pg_database WHERE datname = current_database()"
Invoke-Psql $StoreC "SELECT version_num FROM public.alembic_version"
Invoke-Psql $StoreC "SELECT count(*) FROM public.position_exit_attempt"
Remove-Item Env:PGPASSWORD

"--- manifest ---"
$m = Get-Content $Manifest -Raw | ConvertFrom-Json
"state=$($m.state) host=$($m.host) port=$($m.port)"
"B: database=$($m.stores.B.database) head=$($m.stores.B.head) minimum_attempts=$($m.stores.B.minimum_attempts)"
"C: database=$($m.stores.C.database) head=$($m.stores.C.head) minimum_attempts=$($m.stores.C.minimum_attempts)"
```

**Expected result.**
- `pg_isready` says "accepting connections".
- Store B database `empirical_platform_paper`, Store C `empirical_platform_paper_exit` (the two protected names the
  code recognises). The identity comment printed for each starts with `PERSONAL_PAPER:`.
- Heads before the migration: Store B `83e15e6bfae4`, Store C `d4e9c2a7f183`.
- Manifest: `state=INITIALIZED`; `host`/`port` equal the environment's; each store's `database` and `head` equal what
  the databases report; each live row count is **at least** the manifest's `minimum_attempts`.
- `DATABASE_MODE` empty in all three scopes; `PAPER_EXIT_POSTGRES_HOST set: False`.

**STOP IF**
- `pg_isready` fails, or either query fails;
- the database name is not one of the two protected names, or the identity comment is not `PERSONAL_PAPER:...`
  (you may be pointed at a test or wrong database);
- `EMPIRICAL_PLATFORM_DATABASE_MODE` is `TEST` in **any** scope (remove it; never run this machine in TEST mode);
- a head differs from the values above, or the manifest says `LOSS_DETECTED`, or a row count is *below*
  `minimum_attempts` (history shrank -- do not continue; this is a data-loss alarm);
- Store C reports Store B's database name or vice versa.

---

## Phase 6 -- Fresh backup

**Purpose.** Have a verified, restorable copy of both stores before anything is changed.

**What the deploy tool does vs. a manual backup.** Deploy **step 4** takes its own fresh backup with
`personal_paper_backup.backup()` and independently re-verifies each dump (SHA-256 against `complete.json`, and
`pg_restore --list` shows `alembic_version`) -- so a manual backup is **not required**. Run one anyway if the
Owner wants a rehearsal and a known-good set on disk before the real run. Both write the same way: dumps into
`$Backups\<UTC stamp>\`, and they raise the manifest's `minimum_attempts` / `minimum_approved_plan_rows` floors.
Dumps are sensitive data: keep them on this host.

**Preconditions.** Phases 1-5 passed. **No console may be doing work** (no approval or submission in progress; the
console is idle -- if a console is running, do not click anything in it until Phase 7 stops it). A3 on record.

**Commands:**

```powershell
& $Py tools\personal_paper_backup.py --manifest $Manifest --root $Backups --pg-bin $PgBin
"backup exit code: $LASTEXITCODE"      # 0 = "BACKUP_COMPLETE <dir>", 2 = "BACKUP_BLOCKED: ..."

# Verify checksums yourself, from the newest complete set:
$bk = Get-ChildItem $Backups -Directory | Where-Object { Test-Path (Join-Path $_.FullName "complete.json") } |
      Sort-Object Name | Select-Object -Last 1
$c  = Get-Content (Join-Path $bk.FullName "complete.json") -Raw | ConvertFrom-Json
"backup set: $($bk.Name)   kind: $($c.kind)"
foreach ($s in "B","C") {
  $dump   = Join-Path $bk.FullName "$s.dump"
  $actual = (Get-FileHash $dump -Algorithm SHA256).Hash.ToLower()
  "{0}.dump  sha256 matches complete.json: {1}   size: {2}   attempts: {3}" -f $s, ($actual -eq $c.files.$s.sha256), (Get-Item $dump).Length, $c.files.$s.attempts
  "{0}.dump  structure lists alembic_version: {1}" -f $s, [bool](& "$PgBin\pg_restore.exe" --list $dump | Select-String "alembic_version")
}
Get-ChildItem $bk.FullName | Select-Object Name,Length | Tee-Object -FilePath (Join-Path $Evidence "backup-listing.txt")
```

**Expected result.** `BACKUP_COMPLETE <path>`; the set contains exactly `B.dump`, `C.dump`, `complete.json`;
both checksum lines `True`; both structure lines `True`; sizes non-zero; `attempts` equal to the Phase 5 counts.

**STOP IF**
- `BACKUP_BLOCKED` (the tool deliberately prints no detail -- verify identity, loss state, credentials, binaries
  and free space; a leftover `$Backups\.backup.lock` means a prior backup died: investigate, do not delete blindly);
- any checksum or structure line is `False`, or a dump is zero bytes;
- the set has extra or missing files;
- `PERSONAL_PAPER_LOSS_DETECTED` appears anywhere (history shrank / identity mismatch).

**Owner approval gate A3 (covers Phases 6 and 7).**
Exact sentence: `A3 approved on <date time>: take the Store B and Store C backup and apply migration f3a7c9e2b164 to the real Store B using tools/personal_paper_deploy.py at release SHA <ApprovedSha>. The broker is flat. I understand a rollback is never automatic.`

---

## Phase 7 -- Authorized migration (the deploy tool, all 14 steps)

**Purpose.** Run the single reviewed tool that checks, backs up, stops the console, migrates Store B, updates the
manifest, fast-forwards the worktree and starts the console in recovery mode. `alembic upgrade` against these
databases is refused by design; this tool is the only sanctioned path.

The 14 steps: 1 broker flat; 2 nothing in flight; 3 exact clean release head; 4 backup + independent
verification; 5 **create the maintenance hold, then** authenticated shutdown of the console on the port;
6 verify stopped; 7 apply the hash-pinned SQL; 8 verify the schema; 9 verify no historical row changed;
10 manifest update (with a verbatim `personal-paper.pre-migration-<stamp>.bak.json` copy beside it);
11 fast-forward and check the code's migration chain matches the live schema; 12 recovery-mode start;
13 verify startup; 14 stop. There is **no step selector**; the tool always proceeds in order and always stops at 14.

**Preconditions.** Phases 1-6 passed; A1, A2 (if used), A3 **and A4** on record; the Phase 3 variables
`$ApprovedSha` is set in this window; the console (if any) is on 8189 with a token file, or nothing listens;
any old wrapper loop is gone and the task is disabled.

**Commands:**

```powershell
# If a console listens on 8189, put its listener PID here (from Phase 2); otherwise leave $null.
$ConsolePid = $null     # e.g. $ConsolePid = 12345

$deployArgs = @(
  "tools\personal_paper_deploy.py",
  "--repo-path", $Repo,
  "--expected-release-head", $ApprovedSha,
  "--manifest-path", $Manifest,
  "--backup-root", $Backups,
  "--pg-bin", $PgBin,
  "--console-host", "127.0.0.1",
  "--console-port", "8189",
  "--journal-path", $Journal,
  "--confirm-production"
)
if ($ConsolePid) { $deployArgs += @("--console-pid", "$ConsolePid") }
& $Py @deployArgs
"deploy exit code: $LASTEXITCODE"      # 0 = reached step 14; 1 = BLOCKED at a step; 2 = refused before touching anything
```

Then read the journal (the last record always says where a run stopped):

```powershell
Copy-Item $Journal (Join-Path $Evidence "deploy-journal.json") -Force
(Get-Content $Journal -Raw | ConvertFrom-Json).records |
  Where-Object { $_.status -ne "started" } | Select-Object step,status,at,detail | Format-List
Get-ChildItem $Safety -Filter "personal-paper.pre-migration-*.bak.json" | Select-Object Name,Length
```

**Expected result.** Exit code `0` and the line `Deployment procedure complete through STEP_14 (recovery mode).
Awaiting separate Owner authorization for Active Mode.` The journal shows `completed` for all 14 steps. Step 5's
detail says either `PID <n> exited gracefully via authenticated control request` or `port 8189 is already free;
nothing to stop` (Phase 9 explains what each means). Step 7 says `migration SQL (...) applied via psql`. The
maintenance hold file exists. The pre-migration manifest copy exists.

**Resume and restart rule.** After a failure, **resume = re-run the same command with the same `--journal-path`**:
completed steps are skipped (until step 7 completes, steps 1, 2, 3 and 6 are always re-checked). **Delete the
journal and start over only if, before step 7 completed, the console was restarted by anyone after the backup**
(copy the old journal into the evidence folder first, then `Remove-Item $Journal`). After step 7 completed, never
delete the journal: Store B is already migrated and a fresh backup would be refused (manifest head would not
match). Do **not** edit the manifest, run `alembic`, or restore a backup without separate Owner authorization.

**STOP IF**
- exit code is not `0` (read the `BLOCKED at STEP_n` text and use the troubleshooting table, section 3);
- step 5 or 6 fails with a PID/port mismatch: do not start or kill anything by hand to "help" -- find out what
  owns the port (Phase 2 commands) and re-run;
- step 8 or 9 fails: Store B may be in an unknown state. Treat as an incident. Do not downgrade, do not restore,
  do not update the manifest;
- anything starts a console other than the tool's own step 12.

**Owner approval gates A3 and A4 -- both required before launch.**
A3: sentence in Phase 6.
A4 exact sentence: `A4 approved on <date time>: the tool may start the console in RECOVERY MODE (read-only; no Plan Manager; no exit can be sent) on 127.0.0.1:8189. This does not authorize normal mode or any order.`

---

## Phase 8 -- Recovery-mode checks

**Purpose.** Confirm the console that the tool left running really is read-only and healthy, with the hold in
place. A4 is already on record (it was needed to launch Phase 7); this phase is the checkpoint that proves the
console stayed within it.

**Preconditions.** Phase 7 exit code 0.

**Commands:**

```powershell
Get-NetTCPConnection -LocalPort 8189 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
"hold present (must be True): $(Test-Path $HoldFile)"
"token file present (shutdown route active): $(Test-Path (Join-Path $Control 'paper-exit-8189.json'))"
$listenPid = (Get-NetTCPConnection -LocalPort 8189 -State Listen).OwningProcess | Select-Object -Unique
(Get-CimInstance Win32_Process -Filter "ProcessId = $listenPid").CommandLine      # must contain --recovery-mode

Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8189/safety" -OutFile (Join-Path $Evidence "safety-recovery.html")
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8189/health" -OutFile (Join-Path $Evidence "health-recovery.html")
Select-String -Path (Join-Path $Evidence "safety-recovery.html") -Pattern "RECOVERY_MODE" | Select-Object -First 1
Select-String -Path (Join-Path $Evidence "health-recovery.html") -Pattern "Current position" | Select-Object -First 1
Get-Content (Join-Path $Local "recovery-console.log") -Tail 40
Select-String -Path (Join-Path $Local "recovery-console.log") -Pattern "SECURITY" ; "(no SECURITY lines above = shutdown route registered)"
```

Also open `http://127.0.0.1:8189/safety` and `/health` in a browser and take screenshots. **Type the URLs.** This
console was started with `--base-path /paper`, so links *inside* its pages point at `/paper/...` and 404 on the
direct local address; the pages themselves are served at the unprefixed paths. Always use `127.0.0.1` (or
`localhost`): any other Host name is refused with HTTP 421. To reach the console through a private tunnel (e.g. Tailscale `serve` from the iPhone) the Owner may list the EXACT tunnel host name(s) in the user environment variable `EMPIRICAL_PLATFORM_CONSOLE_ALLOWED_HOSTS` (comma-separated plain DNS names; no wildcards, no ranges, no ports; default empty = loopback only) **before** starting the console. This is optional and never needed for the procedure itself.

**Expected result.** One listener on `127.0.0.1:8189`; hold present; token file present; command line contains
`--recovery-mode`; `/safety` shows PAPER, "Live: UNAVAILABLE", **Automatic position manager: RECOVERY_MODE**
(not HEALTHY, no "tick(s) completed"), Kill switch released; `/health` shows account `ACTIVE`, pinned PAPER host
`Yes`, no block flags, `Current position (shares)` `0`; the log has the banner "PAPER, RECOVERY MODE" and **no**
`SECURITY` line.

**STOP IF**
- the command line lacks `--recovery-mode`, or `/safety` shows HEALTHY / "tick(s) completed" (a full console is
  running -- stop it with Ctrl+C or, if it is detached, `Stop-Process -Id $listenPid`, then investigate);
- the hold is missing;
- `SECURITY` appears in the log (the shutdown route was not activated -- the next stop would need a hand stop);
- `/health` shows a non-zero position, a blocked account, or a non-pinned host;
- any HTTP error other than the 421-by-hostname case.

**Gate.** A4 (recorded in Phase 7). Nothing in this phase asks for a new approval; it does not authorize leaving
recovery mode.

---

## Phase 9 -- Confirm the shutdown control worked

**Purpose.** Deploy step 5 is the authenticated-shutdown (M098) validation against the real console: the tool
read the per-instance token under `console-control\`, sent `POST /control/shutdown` over loopback, and waited for
that exact process to exit. There is **no separate shutdown command** and none should be invented. This phase
reads the evidence that it happened.

**Preconditions.** Phase 7 completed.

**Commands:**

```powershell
$recs = (Get-Content $Journal -Raw | ConvertFrom-Json).records
$recs | Where-Object { $_.step -in "STEP_5_SHUTDOWN","STEP_6_VERIFY_STOPPED" -and $_.status -eq "completed" } |
  Select-Object step,at,detail | Format-List
```

**How to read it.**

| Step 5 detail | What it proves |
|---|---|
| `PID <n> exited gracefully via authenticated control request` | The old console had the shutdown route; the request was accepted (HTTP 202 with its own PID echoed back), and the process exited. The console ran its normal shutdown order and returned **exit code 64** (the deliberate-shutdown code, "do not restart"). If its window was visible it printed `operator-console: authenticated shutdown request accepted`; a wrapper would have printed `console exited with code 64 ... not restarting`. |
| `port 8189 is already free; nothing to stop` | There was no console. **The shutdown control was NOT exercised against a real console.** Record it as untested. |

Hold semantics: the hold was created in step 5 *before* the stop and is still present (Phase 8). While it exists,
the wrapper exits instead of relaunching and a full-mode console exits 74; `--recovery-mode` is allowed. Exit
codes the console uses: 0 Ctrl+C; 64 authenticated shutdown; 2 refused at startup; 73 another console holds the
lock; 74 hold present -- all mean "do not restart"; any other code is a crash.

Phase 8 already showed the token file exists again for the new recovery console and no `SECURITY` line in its
log -- i.e. the *new* console's shutdown route is live.

**Optional 9.2 -- exercise the control against the recovery console.** Only if step 5 said "already free" and the
Owner wants the control proven on the host. It repeats the whole tool with a new journal: step 4 takes another
backup, step 5 stops the recovery console with the authenticated request, step 7 is a no-op (it sees Store B
already at `f3a7c9e2b164`), and step 12 starts recovery mode again. It needs **fresh A3 and A4 sentences**.
Use `--journal-path (Join-Path $Local "deploy-journal-2.json")` and `--console-pid <recovery listener PID>`
in the Phase 7 command. If the Owner declines, Phase 10 stops the read-only recovery console by hand
(`Stop-Process`), and the control stays recorded as untested.

**Expected result.** Journal steps 5 and 6 `completed`; you can state which row of the table applies.

**STOP IF**
- step 5 or 6 is not `completed`;
- step 5's detail names a PID you cannot match to the console from Phase 2 (a PID/port race was detected);
- the maintenance hold is gone (nothing is supposed to remove it before Phase 10).

---

## Phase 10 -- Start normal PAPER operation

**Purpose.** Replace the read-only recovery console with the real one: hold released, Plan Manager running.
Nothing here places an order.

**Preconditions.** Phases 8 and 9 passed; flat broker (Phase 4 numbers still true -- re-run the Phase 4 GETs if
time has passed); **A5 on record**. Only one console may run: a second one exits 73 at the lock (safe), or 74 if
the hold is still present.

**Commands:**

```powershell
# 10.1 Identify and stop the READ-ONLY recovery console (no orders or positions at risk).
$recoveryPid = (Get-NetTCPConnection -LocalPort 8189 -State Listen).OwningProcess | Select-Object -Unique
(Get-CimInstance Win32_Process -Filter "ProcessId = $recoveryPid").CommandLine       # MUST contain --recovery-mode
```
Only if that command line contains `--recovery-mode`:
```powershell
Stop-Process -Id $recoveryPid
# wait until the port is free (up to ~30 s); the venv launcher .exe may show as a parent -- it ends with the child
$n = 0
while ((Get-NetTCPConnection -LocalPort 8189 -State Listen -ErrorAction SilentlyContinue) -and $n -lt 30) { Start-Sleep 1; $n++ }
Get-NetTCPConnection -LocalPort 8189 -State Listen -ErrorAction SilentlyContinue      # must print nothing
```
The recovery console was started detached in its own process group, so Ctrl+C in this window will not reach it.

```powershell
# 10.2 Release the maintenance hold. Refuses unless the journal shows steps 12, 13, 14 completed
#      (the only override is --owner-override; do not use it here).
# If you ran the optional 9.2 repeat, pass the LATEST journal (deploy-journal-2.json) instead of $Journal;
# if that repeat did not reach step 14, do NOT release: stop and follow the failure table.
& $Py -m empirical_platform.entrypoints.release_maintenance_hold --journal-path $Journal
"release exit code: $LASTEXITCODE"          # 0 = "maintenance hold removed ..."
"hold present (must be False): $(Test-Path $HoldFile)"

# 10.3 Start the console in normal PAPER mode, in THIS window, in the foreground, logging to the evidence folder.
#      Keep this window open and visible for the whole test. Open a SECOND window (run Phase 1's variables block there) for everything else.
& $Py -m empirical_platform.entrypoints.operator_console --capability paper-exit --no-browser --port 8189 *>&1 |
  Tee-Object -FilePath (Join-Path $Evidence "console-normal.log")
```
Why `--port 8189` is explicit: the console's own default is 8086, and the deploy tool, this procedure and the
recovery console all use 8189. Why no `--base-path`: without it the pages' links work at
`http://127.0.0.1:8189/`. (A reverse-proxy prefix such as `/paper` is a separate Owner choice.)

Then, **in the second window**:

```powershell
Get-NetTCPConnection -LocalPort 8189 -State Listen | Select-Object LocalAddress,LocalPort,OwningProcess
"token file present: $(Test-Path (Join-Path $Control 'paper-exit-8189.json'))   hold present: $(Test-Path $HoldFile)"
Start-Sleep 30
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8189/safety" -OutFile (Join-Path $Evidence "safety-normal.html")
Select-String -Path (Join-Path $Evidence "safety-normal.html") -Pattern "Automatic position manager" -Context 0,2
```
Open `http://127.0.0.1:8189/safety` in a browser and screenshot it.

**Do not enable the scheduled task in this phase.** Re-enabling autostart is an Owner decision at the very end
(Phase 16), and it has a known problem (below).

**Expected result.** Banner `OPERATOR CONSOLE -- PAPER. Orders reach the real Alpaca PAPER endpoint only.` and
`RELEASE v1: an Owner-approved full plan is managed automatically`; one listener on 127.0.0.1:8189; hold gone; token
file present; `/safety`: Automatic position manager **HEALTHY** ("The automatic position manager is running: N
tick(s) completed, most recently Ns ago, with no error"; it ticks every 15 s, so allow up to a minute for the
first tick), Kill switch **released**, "Live: UNAVAILABLE".

**STOP IF**
- the command line from 10.1 does not contain `--recovery-mode` (do **not** stop it; it is a normal console);
- the release command refuses (the journal does not show steps 12-14; do not use `--owner-override`);
- the console exits at startup: 73 (another console/lock), 74 (hold still present), 2 (refused: read the message);
- the manager card reads STOPPED, STALE or UNKNOWN for more than about a minute after start;
- the kill switch shows Engaged and you did not engage it;
- the account is no longer flat.

**Owner approval gate A5.**
Exact sentence: `A5 approved on <date time>: stop the read-only recovery console, release the maintenance hold and start the PAPER console in NORMAL mode on 127.0.0.1:8189 with the automatic Plan Manager on, for this supervised session. This does not authorize any order, and does not authorize re-enabling the autostart task.`

---

## Phase 11 -- Validate live PAPER broker connectivity (read-only)

**Purpose.** From the running normal console and from outside it: the account is ACTIVE, the clock is right, a
fresh quote arrives, and the entry limits are what the Owner intends. **No order is placed.**

**Preconditions.** Phase 10 passed. Market hours are needed for a fresh quote and for Phase 12.

**Commands (second window):**

```powershell
# 11.1 The console's own read-only broker health page (GET requests only; cannot place or cancel anything).
Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8189/health" -OutFile (Join-Path $Evidence "health-normal.html")

# 11.2 The platform's own environment verifier (read-only; sends no order).
& $Py -m empirical_platform.entrypoints.verify_paper_environment --json | Tee-Object -FilePath (Join-Path $Evidence "verify-paper-environment.json")

# 11.3 The configuration the Prepare button will use -- READ IT, do not edit it.
& $Py -m empirical_platform.entrypoints.show_trading_configuration CFG-089-PAPER | Tee-Object -FilePath (Join-Path $Evidence "config-CFG-089-PAPER.txt")

# 11.4 Independent read-only quote + clock for the configured symbol (replace <SYMBOL> with the watchlist symbol printed in 11.3).
$Sym  = "<SYMBOL>"
$h    = @{ "APCA-API-KEY-ID" = $env:EMPIRICAL_ALPACA_PAPER_API_KEY; "APCA-API-SECRET-KEY" = $env:EMPIRICAL_ALPACA_PAPER_SECRET_KEY }
Invoke-RestMethod -Method Get -Uri "https://paper-api.alpaca.markets/v2/clock" -Headers $h | Format-List
(Invoke-RestMethod -Method Get -Uri "https://data.alpaca.markets/v2/stocks/$Sym/quotes/latest?feed=iex" -Headers $h).quote |
  Select-Object t,bp,ap,bs,as | Format-List
Remove-Variable h
```
Also open `http://127.0.0.1:8189/health` in the browser.

**CHECK the configuration (11.3) -- values only, never change them here.** Confirm each line is what the Owner
intends for a first supervised PAPER order: `account mode`, `kill switch`, `watchlist` (**exactly one symbol** --
the Prepare button refuses otherwise), `capital` / `per-trade` / `reserve`, `risk contract v2: maximum shares ...
maximum planned loss ...`, `daily loss limit`, `daily order limit`, `max positions`, session window and
`liquidate` time with its timezone, `order LIMIT`, `stop %`, `target %`. Note that `/safety` ("Trading rules") shows
the capital, session, order-type and expiry values but **not** the daily-loss, daily-order-count or
simultaneous-position limits or the stop/target percentages; only this command prints them.

**Expected result.** `/health`: Trading endpoint `paper-api.alpaca.markets`, Pinned PAPER host `Yes`, Account
reachable `Yes`, Account status `ACTIVE`, Trading blocked / Account blocked / Trade suspended all `No`, Market is
open `Yes` (during hours), Asset tradable `Yes`, quote bid/ask present, **Quote age (s)** a few seconds (the
Prepare action refuses a quote older than the configured freshness limit). The
verifier prints "pinned paper host : yes" and "account status : ACTIVE". `/health` and the REST quote agree to
within a normal tick. The config exists and is what the Owner intended.

**STOP IF**
- `show_trading_configuration` says `CFG-089-PAPER` does not exist, or it is not on risk contract v2, or its
  watchlist is not exactly one symbol, or any limit is not what the Owner intended (do not edit it here: stop,
  decide, and come back);
- the verifier or `/health` shows an unpinned host, an unreachable or non-ACTIVE account, or a block flag;
- the market is closed (Phase 12 cannot happen; stop the session at Phase 11 and stand down per Phase 16);
- the quote is missing or older than the freshness limit;
- `/health` shows `Current position (shares)` other than `0`. Note this page's symbol is fixed in code (it says
  `AAPL`), regardless of the configured watchlist symbol: use the broker dashboard for the configured symbol.

---

## Phase 12 -- ONE separately authorized PAPER order test

**Purpose.** Place exactly one small whole-share PAPER entry order through the real Owner flow (Prepare, review,
approve once) and let the Plan Manager protect it. This is the first phase that can change the broker.

**Preconditions.** Phases 10-11 passed. Market open with enough time left: at least about an hour before the
configured `liquidate` time, so the exit path can run in daylight. Account flat. Kill switch **released**. Manager
**HEALTHY**. **A6 on record, naming the symbol, a maximum share count and a maximum notional.** Nothing else
happening on the console in any browser tab.

**Sizing.** The Owner does not type a quantity. The engine computes it from the configuration (per-trade cap,
`maximum shares`, `maximum planned loss`, percent cap, cash reserve, deployable capital). Before pressing Prepare,
work out from Phase 11.3 what size to expect. After Prepare, the confirmation page shows the exact quantity and
notional; **if either exceeds the limit written in A6, press Cancel / Reject, not CONFIRM.** Do not "fix" the
size by editing the configuration during the test.

**Screens and clicks** (browser at `http://127.0.0.1:8189/`):

1. **Safety** (`/safety`): Kill switch released; manager HEALTHY. Screenshot.
2. **Today** (`/today`): top stats show Kill switch Released. Press **Prepare a fresh Paper candidate** **exactly
   once**. Do not double-click, do not refresh the POST, do not open a second tab.
   - A page "Candidate prepared" gives the symbol, live bid/ask, capture time and a proposal id
     (`PRP-089-PAPER-<stamp>`) -> use its link to the opportunity page.
   - A page "Candidate not prepared" gives a reason (market closed, stale quote, NO_TRADE check...). Nothing was
     written. Record the reason. A second Prepare is allowed only after the reason is understood and fixed, and
     never within the same second as the first.
3. **Opportunity card** -> **REVIEW PLAN** -> the **Confirm approval** page. Read every row:
   Symbol, Side `BUY`, **Quantity**, Order type LIMIT, **Limit price**, **Approved stop**, **Target**, Evaluated
   planned loss vs Configured maximum planned loss, Configured maximum shares, **Mandatory exit** time,
   Time in force, **Environment PAPER**, **Notional**, Proposal / Approval expiry, Configuration `CFG-089-PAPER`.
   Screenshot it.
4. Press **CONFIRM APPROVAL** **once**. This single click authorizes **and sends** the entry order to the Alpaca
   PAPER endpoint and creates the managed plan. Do not click again or reload the result page; if the page seems to
   hang or shows no outcome (a known gap), go to **Active trades** (`/active`) and look.
5. Watch **Active trades** (`/active`): the entry appears as *Working entry order*, then *Open position* once
   filled, with an *Approved plan* block (quantity, entry average fill, stop, target, mandatory exit, maximum loss,
   management status **Monitoring**). Use **Check with broker now** if you want an immediate reconcile. If a
   partial fill leaves a remainder, the entry-remainder protector cancels it (about 120 s, or at a trigger or the
   deadline); the filled shares are managed.
6. In the **Alpaca paper dashboard**: one BUY limit order for the same symbol, quantity and price as the console;
   then one position.
7. If the entry order is still unfilled after a few minutes, you may cancel it from its execution page
   (`/execution?intent=...` -> cancel -> confirm). Cancelling is risk-reducing and is covered by A6.

Evidence while you go: screenshots of steps 1-5 and 6, plus the console log in the first window.

```powershell
# Before and after the click, in the second window (read-only):
$env:PGPASSWORD = $env:EMPIRICAL_PLATFORM_POSTGRES_PASSWORD
Invoke-Psql $env:EMPIRICAL_PLATFORM_POSTGRES_DATABASE "SELECT state, count(*) FROM public.paper_execution_attempt GROUP BY state ORDER BY state"
Remove-Item Env:PGPASSWORD
```
(`Invoke-Psql` was defined in Phase 5's block; re-define it if this is a new window.)

**Expected result.** Exactly one entry order exists, with the quantity/price you approved. Log lines include
`paper-console: plan <id> for <proposal> created`. `/active` shows the position with management status
Monitoring and the exact stop, target and mandatory exit you saw on the confirmation page. No `Needs attention`.

**STOP IF**
- the confirmation page shows a quantity or notional above the A6 limits, a symbol you did not authorize,
  `Environment` not PAPER, a kill switch warning banner, or "terms changed";
- you pressed Prepare or CONFIRM more than once, or the Alpaca dashboard shows **two** orders for the entry;
- the entry shows `Needs attention`, `Submission unknown`, or the console prints an unexpected error;
- the Alpaca dashboard and the console disagree about symbol, side, quantity or price;
- the manager card leaves HEALTHY while a position is open;
- the market closes or the configured liquidate time is close and the entry has only just filled.

If any of these happen: **do not click anything else.** Engage the kill switch on `/safety` (it blocks new entries;
it never blocks exits), go to Phase 14's manual path, and tell the Owner.

**Owner approval gate A6.**
Exact sentence: `A6 approved on <date time>: exactly ONE PAPER entry order for <SYMBOL>, at most <N> whole shares and at most <USD> notional, followed by its exit (automatic or via Review exit), supervised by me throughout. No second order. No limit or configuration change. Nothing LIVE.`

---

## Phase 13 -- Verify order and position reconciliation

**Purpose.** The console, the database and the broker all describe the same order and the same position, and no
attempt is left unknown or in flight.

**Preconditions.** Phase 12 entry filled (or cancelled). Run again after the exit (Phase 14).

**Commands (read-only):**

```powershell
foreach ($p in "active","history","today") {
  Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8189/$p" -OutFile (Join-Path $Evidence "$p-$(Get-Date -Format HHmmss).html")
}
$env:PGPASSWORD = $env:EMPIRICAL_PLATFORM_POSTGRES_PASSWORD
$StoreC = if ($env:EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE) { $env:EMPIRICAL_PLATFORM_PAPER_EXIT_POSTGRES_DATABASE } else { "empirical_platform_paper_exit" }
"--- entry attempts by state (Store B) ---"
Invoke-Psql $env:EMPIRICAL_PLATFORM_POSTGRES_DATABASE "SELECT state, count(*) FROM public.paper_execution_attempt GROUP BY state ORDER BY state"
"--- exit attempts by state (Store C) ---"
Invoke-Psql $StoreC "SELECT state, count(*) FROM public.position_exit_attempt GROUP BY state ORDER BY state"
Remove-Item Env:PGPASSWORD

$h    = @{ "APCA-API-KEY-ID" = $env:EMPIRICAL_ALPACA_PAPER_API_KEY; "APCA-API-SECRET-KEY" = $env:EMPIRICAL_ALPACA_PAPER_SECRET_KEY }
$base = "https://paper-api.alpaca.markets"
"--- broker positions ---"
Invoke-RestMethod -Method Get -Uri "$base/v2/positions" -Headers $h | Select-Object symbol,side,qty,avg_entry_price,market_value
"--- broker open orders ---"
Invoke-RestMethod -Method Get -Uri "$base/v2/orders?status=open&limit=500" -Headers $h | Select-Object symbol,side,qty,type,limit_price,status
"--- broker orders, recent (a standard Alpaca endpoint; the platform itself does not call it) ---"
Invoke-RestMethod -Method Get -Uri "$base/v2/orders?status=all&limit=10&direction=desc" -Headers $h |
  Select-Object submitted_at,symbol,side,qty,filled_qty,filled_avg_price,type,limit_price,status
Remove-Variable h
```

Compare, line for line: console **Active** and **History** (and the execution page `/execution?intent=...`) vs the
broker lines vs the Alpaca paper dashboard: symbol, side, quantity, order type, limit price, status, filled
quantity and average fill price. Table of what is non-terminal in Store B: `NOT_SUBMITTED`, `PAPER_SUBMITTED`,
`PARTIALLY_FILLED`, `SUBMISSION_UNKNOWN`.

**Expected result.** After the entry fill: one Store B attempt in a filled state; none in `SUBMISSION_UNKNOWN`; the
broker shows one position of the same quantity; the console shows the same quantity and average price. After the
exit and a reconcile: broker flat, console "Position closed" (shown only after a broker check verified the
position at zero), Store C exit attempt terminal.

**STOP IF**
- any attempt is `SUBMISSION_UNKNOWN`, or any state that stays non-terminal while the broker shows nothing for it;
- quantity, price or status differ between console and broker;
- an order exists at the broker that the console does not show (or the reverse);
- there are two entry orders. Do nothing further automatic: engage the kill switch and follow Phase 14's manual path.

---

## Phase 14 -- Verify exits and risk limits

**Purpose.** See the position leave through the protected path, and see the entry limits for what they are.

**Preconditions.** Phase 12 position open, manager HEALTHY, A6 on record (it names the exit).

**How exits work.**
- The Plan Manager (one tick every 15 s) watches the stop price, target price and the mandatory liquidation
  time from the approved plan. Triggers use a quote check that rejects thin or stale evidence; an uncertain
  trigger is logged as `TRIGGER_EVIDENCE_UNCERTAIN` at WARNING and not acted on.
- Status words on `/active`: *Monitoring*, *Stop triggered*, *Target triggered*, *Mandatory exit triggered*,
  *Exit submitted*, *Needs attention*, *Closed*.
- An exit is a SELL TO CLOSE **limit** order for the whole holding, first at the bid. If it does not fill, the
  manager cancels it, waits until the broker reports it terminal, and only then sends the next one, each priced
  10 bps lower than the last (`bid - generation x 10 bps`), never more than 50 bps below the current bid. There is
  no market-order path. Minimum 30 s between attempts (15 s for a mandatory liquidation). **At most 5 attempts per
  session**, and a DAY exit that expires is re-armed next session at most 5 times. After that the plan reads
  **Needs attention** with `EXIT_RETRIES_EXHAUSTED` and nothing more is sent automatically.
- An exit attempt whose outcome is unknown (or in progress) for 120 s reads **Needs attention** with "NEVER
  re-sent automatically": it is reconciled by client order id every tick.
- Exits are not blocked by the kill switch or by any entry limit.

**Choose how the test position leaves (the Owner decides, inside A6):**
- *Automatic:* wait for stop/target/mandatory exit. Slow and market-dependent.
- *Owner-confirmed exit:* on `/active` press **Review exit** on the open position, read the frozen terms
  (SELL TO CLOSE, the whole holding, limit price = current bid, mandatory deadline), press **CONFIRM EXIT**
  **once**. Follow the timeline to **Position closed**. This is the preferred controlled test.

**Entry limits -- where they are visible, and how to read a refusal.**
`show_trading_configuration CFG-089-PAPER` (Phase 11.3) prints the daily-loss limit, daily order limit, maximum
simultaneous positions, maximum shares and planned loss; `/safety` shows capital, deployable capital and window
rules. The daily limits are judged at the last point before an entry leaves, from fresh broker reads and the
durable local order count (counted per US/Eastern trading day, including the order being sent), and **fail
closed**: missing or odd evidence refuses, it never counts as zero. If Prepare or CONFIRM is refused for a
daily-loss, order-count, position-count or exposure reason, that is the control working. Read the reason, record
it, and stop. Do not change a limit to get past it. Remember the daily-loss figure is `equity - last_equity` and
includes unrealized results.

**What to do when an exit does not complete.**
1. Look at `/active`: management status, the exit timeline, the *Liquidation deadline* note, any red banner
   ("the automatic exit cannot act on this position right now: <reason>").
2. *Exit submitted* and the price is moving: wait; it reprices on its own as above.
3. **Needs attention**, or the manager card leaves HEALTHY, or the deadline has passed with the position still
   open: **the Owner acts**. First try **Review exit -> CONFIRM EXIT** (it uses the same chain and is not blocked
   by the kill switch). If the page says the position "requires operator attention before it can be closed
   safely", it lists the reasons; nothing is guessed or sent. A deadline-overdue position has the extra
   two-step recovery on `/exit/recovery?intent=...`.
4. **Manual exit at the broker (last resort), without double-selling:**
   1. Engage the kill switch on `/safety` (blocks new entries only).
   2. Stop the platform's console so it cannot send a second sell: press Ctrl+C in the console window and wait
      for it to exit. (Your position is now protected only by you.)
   3. In the Alpaca paper dashboard: cancel any working sell order for the symbol, then close the position.
      Verify position quantity 0 and no open orders (Phase 4 GETs).
   4. Record the closure in the platform so a restart does not keep retrying a trigger that can never succeed
      (it reads the broker fresh and refuses unless the position is zero). Find the closing order's client order
      id on the Alpaca order detail page, and the entry intent id on the console's execution page:
      ```powershell
      & $Py -m empirical_platform.entrypoints.record_external_position_closure <entry_intent_governance_id> <client_order_id> "<your name>"
      ```
   5. Do not restart in normal mode without a new Owner decision (A5 again).

**Expected result.** Position closed through the chosen path; broker flat; `/active` shows *Closed* then moves to
History with entry and exit fills; History's Plan column shows Trigger, Exit order, Exit fill, Zero-verified Yes,
Gross P&L. Repeat the Phase 13 reconciliation: Store C exit attempt terminal, no unknown attempts.

**STOP IF**
- more than one exit order is working for the same position;
- an exit limit price is more than 50 bps below the current bid (it should never be);
- the manager is not HEALTHY while the position is open;
- status is *Needs attention* and you cannot resolve it within a few minutes -- go to the manual broker path;
- the market is about to close with the position still open: manual path now, not later.

---

## Phase 15 -- Confirm monitoring

**Purpose.** Know what "healthy" looks like and who acts when it does not. There is no external alerting; the
console pages and its log are the monitoring.

**What to watch, and where (all on `http://127.0.0.1:8189/`):**

| Where | Healthy | Not healthy -> who acts |
|---|---|---|
| `/health` | account ACTIVE, pinned host Yes, no block flags, quote age in seconds | Any No/blocked/stale -> **Owner**: stop trading for the day |
| `/safety` -> Automatic position manager | **HEALTHY** (a tick in the last 60 s, no error) | **STALE** (no tick for >60 s, or last tick failed), **STOPPED** (never ticked), **UNKNOWN** (cannot be proven) -> **Owner**: do not rely on automatic exits; manual exit; restart the console only with the Owner present |
| `/safety` -> Kill switch | Released (Engaged only when you engaged it) | |
| `/active` -> management status | Monitoring / Exit submitted / Closed | **Needs attention** -> **Owner** (Phase 14 steps 3-4). It means the automatic manager has stopped acting on that position (retries exhausted, outcome unknown for 120 s, blocked by a refusal, or ambiguous state), not that something is merely slow |
| `/today` stats | "Need your decision" 0 when idle | |
| Console window / `console-normal.log` | Routine lines | `plan ... NEEDS_ATTENTION: ...` and `TRIGGER_EVIDENCE_UNCERTAIN` are logged at WARNING; `position plan manager tick failed` with a traceback means a tick raised (the loop keeps going) |
| `$Local\recovery-console.log` | The recovery run's output | Look here if Phase 8 went wrong |

Log caveat: the console prints to its terminal; nothing writes a log file unless you do (the `Tee-Object` in
Phase 10.3). INFO-level lines may not appear at all; WARNING and above do.

Optional convenience while a position is open (second window; stops with Ctrl+C):

```powershell
while ($true) {
  $t = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:8189/safety").Content
  $s = [regex]::Match($t, "Automatic position manager.*?<strong>([A-Z_]+)</strong>", "Singleline").Groups[1].Value
  "{0}  manager={1}" -f (Get-Date -Format HH:mm:ss), $s
  Start-Sleep 30
}
```

**Expected result.** You can point to each of the six rows and say what it showed during the run.

**STOP IF**
- the manager state is anything but HEALTHY while a position is open, for more than one polling interval;
- a `NEEDS_ATTENTION` appears and no one is watching: do not leave the host.

---

## Phase 16 -- Final operational evidence, stand-down and rollback

**Purpose.** Leave a complete, checkable record, then leave the system safe.

**Preconditions.** Broker flat. No open orders.

### 16.1 Evidence to save under `%LOCALAPPDATA%\EmpiricalPlatform\evidence\<date>\`

```powershell
Get-Date -Format o | Out-File (Join-Path $Evidence "finished-at.txt")
git -C $Repo rev-parse HEAD            | Out-File (Join-Path $Evidence "release-sha.txt")
git -C $Repo status --porcelain        | Out-File (Join-Path $Evidence "git-status.txt")
Copy-Item $Journal                      (Join-Path $Evidence "deploy-journal.json") -Force
Copy-Item $Manifest                     (Join-Path $Evidence "personal-paper.manifest.json") -Force
Copy-Item (Join-Path $Local "recovery-console.log") $Evidence -Force
Get-ChildItem $Safety -Filter "personal-paper.pre-migration-*.bak.json" | Copy-Item -Destination $Evidence -Force
if ($bk) { Copy-Item (Join-Path $bk.FullName "complete.json") (Join-Path $Evidence "backup-complete.json") -Force }   # not the dumps
& $Py -m pip freeze | Out-File (Join-Path $Evidence "pip-freeze.txt")
Get-ChildItem $Evidence -File | Get-FileHash -Algorithm SHA256 | Select-Object Hash,Path |
  Export-Csv (Join-Path $Evidence "evidence-sha256.csv") -NoTypeInformation
Stop-Transcript
```
(The transcript is stopped last so the hash list does not miss it; run the `Get-FileHash` line once more after
`Stop-Transcript` if you want it included.) Do not copy `.dump` files or the token file. Do not paste the
evidence into any chat.

### 16.2 Evidence checklist (copy into the evidence folder and fill in)

```text
M100 Windows PAPER launch -- evidence checklist                Date: ____________   Owner: ____________
Release SHA (Owner-approved merge of PR #49): ______________________   HEAD matched: [ ]

Approvals (ID | exact sentence given | date/time)
 A1 [ ] ________________________________________________
 A2 [ ] ________________________________________________   (or N/A)
 A3 [ ] ________________________________________________
 A4 [ ] ________________________________________________
 A5 [ ] ________________________________________________
 A6 [ ] ________________________________________________

Phase  1 clock/service/network output saved                         [ ]
Phase  2 listeners / task / processes output saved; task disabled   [ ]   TaskName: ________
Phase  3 SHA lines, hash check True, architecture + tests pass       [ ]
Phase  4 broker env: ACTIVE, flat, paper host (no secrets in file)   [ ]
Phase  5 DB names, heads, manifest, DATABASE_MODE empty              [ ]
Phase  6 backup set name: ____________  checksums True  structure True [ ]
Phase  7 deploy-journal.json (14 completed), pre-migration .bak.json [ ]
Phase  8 safety-recovery.html, health-recovery.html, screenshots     [ ]
Phase  9 step 5 detail: [ ] graceful via control request  [ ] port was free (control NOT exercised)
Phase 10 safety-normal.html (HEALTHY), console-normal.log started    [ ]
Phase 11 health-normal.html, verify-paper-environment.json, config-CFG-089-PAPER.txt [ ]
Phase 12 screenshots: prepare, confirm page, active, Alpaca order    [ ]
Phase 13 active/history html, psql state counts, broker GET output   [ ]
Phase 14 exit path used: [ ] Review exit [ ] automatic [ ] manual broker   closed verified [ ]
Phase 15 any WARNING / NEEDS_ATTENTION seen: ______________________
Phase 16 evidence-sha256.csv written; broker flat at end [ ]; console stopped [ ]; task state: ________

Deviations / anything unexpected: _______________________________________________
Owner sign-off: ____________________   time: ____________
```

### 16.3 Stand-down

1. Stop the console gracefully: Ctrl+C in its window. It stops taking requests, waits for the in-flight
   reconciliation pass (however long that takes -- a second Ctrl+C does not shorten it), stops the Plan Manager,
   removes its token, then closes the database. Exit code 0.
2. Confirm: `Get-NetTCPConnection -LocalPort 8189 -State Listen -ErrorAction SilentlyContinue` prints nothing.
3. Leave the broker **flat**. Check the Alpaca dashboard.
4. Leave the **autostart task disabled** and no wrapper loop running. The maintenance hold: if you stand down
   *before* Phase 10, it is still in place -- **leave it**. After Phase 10 it was released by A5; there is no
   command in this repository to re-create it (only the deploy tool creates it), so the protection against an
   unattended relaunch is the disabled task.
5. **Re-enabling autostart is a separate Owner decision, only at the very end, never as part of this procedure.**
   Known problems to settle first: the wrapper (`deploy/windows/run-v1-console.ps1`) now starts the console on
   `127.0.0.1:8189 --base-path /paper` (same as the deploy tool); it writes no log file; and it
   needs the `EMPIRICAL_*` variables to be persistent *user* variables. Only if the Owner decides after weighing
   these: `Enable-ScheduledTask -TaskName "<TaskName>"`.

### 16.4 Rollback

- **A migration is never rolled back automatically**, and this document gives no downgrade command. The step-4
  backup is kept untouched. **Restoring a backup requires separate, explicit Owner authorization** in writing
  outside this document, a disposable-database rehearsal first, and cross-store reconciliation (the two dumps are
  per-store snapshots).
- If Store B is migrated and the manifest is not (failure at step 10): leave the console stopped, restore the
  manifest from `personal-paper.pre-migration-<stamp>.bak.json` only if it looks corrupted, then re-run the
  same deploy command.
- If you must abandon the day mid-way: console stopped (graceful), broker flat, hold left where it is, task
  disabled, evidence saved.

---

## Troubleshooting by journal step

Source: `_RECOVERY_TEXT` in `tools/personal_paper_deploy.py`. **Resume = re-run the same command with the same
journal. Delete the journal and start over if the console was restarted after the backup (only possible before
step 7 completed).** No step is ever "forced" by this tool.

| Step | What a failure means | Safe action |
|---|---|---|
| 1 `STEP_1_BROKER_VERIFY` | Account not ACTIVE/blocked, or not flat (positions, open orders, or an order in an unrecognised state). Nothing changed. | Make the account flat in the Alpaca dashboard (Owner), re-run. |
| 2 `STEP_2_NO_INFLIGHT` | An entry/exit attempt is non-terminal in Store B/C. Nothing changed. | Let it resolve (or the Owner resolves it); re-run. Never force it closed from the tool. |
| 3 `STEP_3_RELEASE_HEAD` | Worktree dirty, or HEAD is not the expected SHA. Nothing changed. | Inspect `git status` / `git log` by hand; the tool never commits, resets or checks out for you. Phase 3. |
| 4 `STEP_4_BACKUP` | The backup failed or a dump failed independent checksum/structure verification. Store B/C untouched. | Read `BACKUP_BLOCKED` causes (identity, loss state, credentials, binaries, free space, a stale `.backup.lock`). Re-run from the top. |
| 5 `STEP_5_SHUTDOWN` | Console still running or mid-shutdown; or the hold could not be created (then the console was *not* stopped); or a token/PID/port mismatch; or an old console with no control route. | Do not start a second console. Check process/port by hand (Phase 2), find out why the shutdown is hung. The hold stays; it is correct. Re-run. |
| 6 `STEP_6_VERIFY_STOPPED` | The old process or port 8189 did not clear in time, or a backup lock remains. Migration has NOT started. | Confirm no listener and no stale lock; re-run. Do not migrate while this is ambiguous. |
| 7 `STEP_7_MIGRATE` | The SQL transaction did not commit (psql non-zero) or the identity/head pre-check refused. Store B should be at the pre-migration head. | Verify directly (`SELECT version_num FROM public.alembic_version`). Do **not** downgrade or restore without separate Owner authorization. |
| 8 `STEP_8_VERIFY_SCHEMA` | SQL "succeeded" but head/columns/constraints/guard function do not match. Store B may be half-migrated. | Treat as an incident. No manifest update, no downgrade. Manual DBA inspection and separate Owner authorization before anything, including a restore. |
| 9 `STEP_9_VERIFY_UNCHANGED` | The schema looks right but a historical row count changed (a write during the window). | Do not update the manifest. Investigate; preserve the step-4 backup; no restore without separate authorization. |
| 10 `STEP_10_MANIFEST_UPDATE` | Store B is migrated but the manifest update did not complete or verify. A verbatim pre-change copy exists. | Restore the manifest from that copy only if corrupted; re-run (idempotent; it only confirms). Console stays stopped until the manifest shows the new head (a stale manifest fails closed as `PERSONAL_PAPER_LOSS_DETECTED`). |
| 11 `STEP_11_FAST_FORWARD` | Could not fast-forward, or the worktree's migration chains do not match the live schema. | Do **not** start a console from this worktree. Resolve the worktree by hand; the migration and manifest are already correct. |
| 12 `STEP_12_RECOVERY_START` | The recovery console did not start or did not listen in time. | Read `%LOCALAPPDATA%\EmpiricalPlatform\recovery-console.log` (likely a startup refusal such as an identity/head mismatch). Check for a stale holder of 8189. If it is `TIME_WAIT`, wait a few minutes. Re-run (resumes at step 12). |
| 13 `STEP_13_VERIFY_STARTUP` | Console runs but did not verify (HTTP check failed, non-flat position, identity mismatch, or it is not in recovery mode). | Do not hand this console on for Active Mode. Stop it, diagnose from the log, re-run from step 12. |
| 14 `STEP_14_STOP_BEFORE_ACTIVE` | Not a failure: the tool stops here by construction. The hold is still in place. | Continue with Phase 8; the Owner releases the hold only in Phase 10. |

Other messages you may meet:

| Message / exit | Meaning | Safe action |
|---|---|---|
| Deploy exit `2`: `REFUSED: Store B/C configuration is incomplete or invalid` | An environment variable is missing, or `..._PAPER_EXIT_POSTGRES_PORT/USER/PASSWORD` is set without `_HOST` | Phase 5; nothing was touched |
| Deploy exit `2`: `REFUSED: --manifest-path is the real ... but --confirm-production was not given` (or the reverse) | The production guard | Use the exact Phase 7 command |
| Deploy exit `2`: `Alpaca PAPER credentials are not set` | Missing key variables in this window | Phase 4 |
| `ModuleNotFoundError: No module named 'tools'` at step 4 | `PYTHONPATH` lacks the repository root | Run the Phase 1 block (it sets `src` and the repo root) |
| Console exit `73` | Another PAPER console holds the lock | Find and stop that console by Ctrl+C; nothing was changed |
| Console exit `74` | Maintenance hold present (full mode) | Correct while Phases 7-9 are in progress; release only in Phase 10 under A5 |
| Console exit `2` | Refused at startup (flags, schema, identity) | Read the message; nothing was opened |
| HTTP 421 | Host header is not `127.0.0.1` / `localhost` / `[::1]` | Use the loopback address (DNS-rebinding guard) |

---

## Evidence the cloud already produced

None of this proves the host works (see "Known limits"). It is the review trail behind the code being run:

- **PR #49** (`claude/empirical-m100-launch-c492oz` into `release/v1-personal-paper`): the consolidated M100
  launch-closure work. The commit to run is **the Owner-approved merge SHA** of that PR, as recorded under A1 and
  checked in Phase 3.
- `docs/operations/m100-acceptance-report.md` -- defect register D1-D9 (all fixed in code), the known residual
  items, and what the acceptance run was not (scripted exchange, virtual time).
- `docs/operations/m100-acceptance-evidence.md` and `docs/operations/m100-acceptance-evidence.json` -- the 24-step
  owner matrix (29 tests) produced by `tests/integration/test_m100_e2e_acceptance_matrix.py` against throwaway
  PostgreSQL 16; rendered by `tools/m100_render_acceptance_report.py`. Do not edit by hand.
- `docs/operations/personal-paper-deployment.md` -- the 14 deploy steps, the hold and lock, the Windows
  shutdown design, the journal, and the failure/recovery table.
- `docs/operations/kill-switch.md` -- the kill switch blocks new entries only, never exits.
- `docs/operations/operator-console.md` -- how the console screens read.
- `docs/operations/m100-live-readiness.md` -- why LIVE is a separate, currently failing assessment.
- `deploy/windows/run-v1-console.ps1` and `deploy/windows/v1-console-task.xml` -- the autostart wrapper and task
  definition (committed artifacts; registering them is an Owner action).
