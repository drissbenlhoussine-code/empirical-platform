# READ-ONLY PERSONAL PAPER acceptance check (M101). Starts nothing, stops nothing, changes nothing.
#
# Run after a logon/reboot (or any time) to see whether the PAPER platform is in a state worth
# trusting. It does NOT require the console to be running (the console is started by the Owner, not
# autostarted); it reports that as INFO. Prints no secret. Replaces the SIMULATION-era
# verify-after-boot.ps1 checks (console on 8086) for the PAPER setup.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File deploy\windows\verify-paper-after-boot.ps1
#   ... -ExpectedSha 240ad1f9a0726270551469e94f49718ee85d376e   (also check the checkout)
#
# Exit code: 0 when no FAIL line, 1 otherwise.

param(
    [string]$Repository = "C:\Users\LuxSy\Documents\trading",
    [string]$ExpectedSha = "",
    [string]$PgBin = "C:\Program Files\PostgreSQL\16\bin",
    [int]$PgPort = 55433,
    [int]$ConsolePort = 8189,
    [string]$Output = ""
)
$ErrorActionPreference = "Continue"
$Local = Join-Path $env:LOCALAPPDATA "EmpiricalPlatform"
$Safety = Join-Path $Local "safety"
if (-not $Output) { $Output = Join-Path $Local ("logs\paper-verification-{0}.log" -f (Get-Date -Format "yyyyMMdd-HHmmss")) }
$lines = New-Object System.Collections.Generic.List[string]
function Check([string]$Name, [bool]$Ok, [string]$Detail = "") { $lines.Add(("{0,-52} {1,-4} {2}" -f $Name, $(if ($Ok) { "PASS" } else { "FAIL" }), $Detail)) }
function Info([string]$Name, [string]$Detail = "") { $lines.Add(("{0,-52} {1,-4} {2}" -f $Name, "INFO", $Detail)) }

$boot = (Get-CimInstance Win32_OperatingSystem).LastBootUpTime
$lines.Add("PAPER verification at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss'); last boot $($boot.ToString('yyyy-MM-dd HH:mm:ss'))")

# -- tasks -------------------------------------------------------------------------------------
foreach ($name in "EmpiricalPlatform Operator Console", "EmpiricalPlatform Personal Paper Backup") {
    $task = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if (-not $task) { Check "task '$name' exists" $false; continue }
    $info = $task | Get-ScheduledTaskInfo
    Check "task '$name' enabled" ($task.State -ne "Disabled") "$($task.State); last run $($info.LastRunTime); result $($info.LastTaskResult)"
}
$pgTask = Get-ScheduledTask -TaskName "EmpiricalPlatform Operator Console" -ErrorAction SilentlyContinue
if ($pgTask) {
    $arg = ($pgTask.Actions | ForEach-Object { $_.Arguments }) -join " "
    Check "startup task runs the PostgreSQL-only script" ($arg -like "*start-postgres-hidden.vbs*") $arg
    Check "startup task ran after this boot" (($pgTask | Get-ScheduledTaskInfo).LastRunTime -gt $boot)
}

# -- PostgreSQL + stores -----------------------------------------------------------------------
& (Join-Path $PgBin "pg_isready.exe") -h localhost -p $PgPort -q
$pgReady = ($LASTEXITCODE -eq 0)
Check "PostgreSQL localhost:$PgPort accepting connections" $pgReady
if ($pgReady) {
    $manifestFile = Join-Path $Safety "personal-paper.json"
    $manifest = if (Test-Path $manifestFile) { Get-Content $manifestFile -Raw | ConvertFrom-Json } else { $null }
    Check "safety manifest present, state INITIALIZED" ($manifest -and $manifest.state -eq "INITIALIZED") "state=$($manifest.state)"
    $pw = [Environment]::GetEnvironmentVariable("EMPIRICAL_PLATFORM_POSTGRES_PASSWORD", "User")
    $usr = [Environment]::GetEnvironmentVariable("EMPIRICAL_PLATFORM_POSTGRES_USER", "User")
    if ($manifest -and $pw -and $usr) {
        $env:PGPASSWORD = $pw
        foreach ($store in "B", "C") {
            $db = $manifest.stores.$store.database
            $head = (& (Join-Path $PgBin "psql.exe") --no-password -h localhost -p $PgPort -U $usr -d $db -At -c "SELECT version_num FROM public.alembic_version" 2>$null | Out-String).Trim()
            Check "Store $store ($db) head equals manifest" ($head -eq $manifest.stores.$store.head) "db=$head manifest=$($manifest.stores.$store.head)"
        }
        Remove-Item Env:PGPASSWORD -ErrorAction SilentlyContinue
    } else { Check "database credentials present (User env)" $false }
}

# -- release checkout --------------------------------------------------------------------------
$head = (git -C $Repository rev-parse HEAD 2>$null | Out-String).Trim()
$dirty = (git -C $Repository status --porcelain 2>$null | Out-String).Trim()
Check "checkout clean" ($head -and -not $dirty) "HEAD $head"
if ($ExpectedSha) { Check "checkout at expected release SHA" ($head -eq $ExpectedSha) "expected $ExpectedSha" }

# -- console (informational: started by the Owner, not autostarted) ----------------------------
$hold = Join-Path $Safety "console-control\maintenance-hold.json"
Info "maintenance hold present" "$(Test-Path $hold)  (True is normal only during a deployment)"
$listeners = @(Get-NetTCPConnection -LocalPort $ConsolePort -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -eq 0) {
    Info "PAPER console on 127.0.0.1:$ConsolePort" "NOT RUNNING (expected after a reboot; start it per the handbook)"
} else {
    Check "console bound to loopback only" (-not ($listeners | Where-Object { $_.LocalAddress -notin "127.0.0.1", "::1" })) (($listeners | ForEach-Object { $_.LocalAddress }) -join ",")
    try {
        $t = (Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$ConsolePort/safety" -TimeoutSec 10).Content -replace "<[^>]+>", " " -replace "\s+", " "
        Check "manager HEALTHY" ($t -match "Automatic position manager HEALTHY") ""
        Check "Live UNAVAILABLE / PAPER environment" (($t -match "Live: UNAVAILABLE") -and ($t -match "Environment: PAPER"))
    } catch { Check "console /safety answers" $false $_.Exception.Message }
}
Check "nothing listening on retired simulation port 8086" (-not (Get-NetTCPConnection -LocalPort 8086 -State Listen -ErrorAction SilentlyContinue))

# -- Tailscale (transport only) ----------------------------------------------------------------
$tailscale = "C:\Program Files\Tailscale\tailscale.exe"
if (Test-Path $tailscale) {
    $state = ((& $tailscale status --json 2>$null | Out-String) | ConvertFrom-Json).BackendState
    Check "Tailscale connected" ($state -eq "Running") $state
    $serve = (& $tailscale serve status 2>&1 | Out-String)
    Check "serve maps /paper to 127.0.0.1:$ConsolePort" ($serve -match "/paper\s+proxy http://127\.0\.0\.1:$ConsolePort")
    Check "serve is tailnet-only (Funnel off)" (($serve -match "tailnet only") -and ($serve -notmatch "Funnel on"))
} else { Check "Tailscale installed" $false }

# -- backups -----------------------------------------------------------------------------------
$statusFile = Join-Path $Safety "backup-status.json"
if (Test-Path $statusFile) {
    $s = Get-Content $statusFile -Raw | ConvertFrom-Json
    $age = ((Get-Date).ToUniversalTime() - [datetime]::Parse($s.checked_utc).ToUniversalTime()).TotalMinutes
    Check "latest backup BACKUP_COMPLETE" ($s.status -eq "BACKUP_COMPLETE") "status=$($s.status)"
    Check "latest backup check within 130 minutes" ($age -lt 130) ("{0:N0} min ago" -f $age)
} else { Check "backup status file present" $false }

# -- broker (read-only GET; keys used in memory, never printed) --------------------------------
$k = [Environment]::GetEnvironmentVariable("EMPIRICAL_ALPACA_PAPER_API_KEY", "User")
$sec = [Environment]::GetEnvironmentVariable("EMPIRICAL_ALPACA_PAPER_SECRET_KEY", "User")
$base = [Environment]::GetEnvironmentVariable("EMPIRICAL_ALPACA_PAPER_BASE_URL", "User")
Check "broker base URL is the PAPER host" ($base -eq "https://paper-api.alpaca.markets") $base
if ($k -and $sec -and $base -eq "https://paper-api.alpaca.markets") {
    try {
        $h = @{ "APCA-API-KEY-ID" = $k; "APCA-API-SECRET-KEY" = $sec }
        $a = Invoke-RestMethod -Uri "$base/v2/account" -Headers $h -TimeoutSec 20
        Check "account ACTIVE, not blocked" ($a.status -eq "ACTIVE" -and -not $a.trading_blocked -and -not $a.account_blocked) "status=$($a.status)"
        $pos = (Invoke-RestMethod -Uri "$base/v2/positions" -Headers $h -TimeoutSec 20 | Where-Object { $_ } | Measure-Object).Count
        $ord = (Invoke-RestMethod -Uri "$base/v2/orders?status=open&limit=500" -Headers $h -TimeoutSec 20 | Where-Object { $_ } | Measure-Object).Count
        Info "broker positions / open orders" "$pos / $ord"
    } catch { Check "broker read-only GETs" $false $_.Exception.Message }
    Remove-Variable h -ErrorAction SilentlyContinue
} else { Check "broker credentials present (User env)" $false }
Remove-Variable k, sec -ErrorAction SilentlyContinue

$fails = @($lines | Where-Object { $_ -match " FAIL " }).Count
$lines.Add("RESULT: $(if ($fails -eq 0) { 'ALL PASS' } else { "$fails FAIL" })")
New-Item -ItemType Directory -Force -Path (Split-Path $Output) | Out-Null
$lines | Set-Content -Path $Output -Encoding UTF8
$lines
exit $(if ($fails -eq 0) { 0 } else { 1 })
