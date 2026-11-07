# RELEASE v1 -- autostart wrapper for the Paper console.
#
# HONEST STATUS (see external-review/RELEASE-V1/engineering-status.md for the full
# picture): this wrapper currently starts the EXISTING, already-proven M088/M089 console
# (`operator_console.py --capability paper-exit`), which already combines candidate
# display, approval, active-position view and the kill switch in one loopback-only
# process. The release mission's full TODAY/ACTIVE/HISTORY/SAFETY navigation, the
# "RESEARCH CANDIDATE" banner/labeling, and the one-click full-plan-approval UI that wires
# the new `ApprovedPlan`/`PositionPlanManager` pieces into this console are NOT yet built
# -- this script will be updated to point at that consolidated entrypoint once it exists.
#
# What this DOES do: activates the repo's existing venv and runs the current paper console,
# restarting it ONLY after a crash (see the contract below). It does NOT touch Tailscale,
# does NOT register itself as a scheduled task, and does NOT run anything else.
#
# The task XML's RestartOnFailure (3 tries, 5 min apart) only covers THIS script itself failing
# unexpectedly (e.g. a missing venv); it is bounded and never relaunches an intentional stop.
#
# RESTART CONTRACT (mirrors src/empirical_platform/shared/console_lifecycle.py):
#   1. MAINTENANCE HOLD. Before EVERY launch this script checks for
#      %LOCALAPPDATA%\EmpiricalPlatform\safety\console-control\maintenance-hold.json. If it
#      exists the script exits with a message; it never sleeps and retries. The
#      deployment tool creates that file before it stops the console and never removes it;
#      the Owner removes it with
#      `python -m empirical_platform.entrypoints.release_maintenance_hold`.
#   2. EXIT CODES. 0 (Ctrl+C), 64 (authenticated deliberate shutdown), 2 (refused at startup),
#      73 (another console already running) and 74 (maintenance hold) mean "do NOT restart":
#      this script exits too (its own exit code is 0 so Task Scheduler's RestartOnFailure does not
#      relaunch an intentional stop). Any other exit code is a crash and is restarted
#      with exponential backoff (10s, 20s, 40s ... capped at 300s).
#   3. CIRCUIT BREAKER. More than 5 crash restarts inside any 600-second window stops the
#      wrapper (exit 0, loud warning) so a crash loop never hammers the database or broker. The Owner
#      investigates and starts the task again.
#
# This script is a committed artifact only. Actually registering it as a Windows autostart
# task (via Task Scheduler, importing `v1-console-task.xml` in this same directory) is an
# Owner action outside engineering -- see that file's own header comment for exact steps.

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ExitIntentionalStop = 0  # RestartOnFailure in the task XML must NOT relaunch these
$NoRestartExitCodes = @(0, 2, 64, 73, 74)
$MaxRestartsPerWindow = 5
$RestartWindowSeconds = 600
$InitialBackoffSeconds = 10
$MaxBackoffSeconds = 300

# TEST SEAM (tests/unit/test_windows_lifecycle_proofs.py ONLY). When the environment variable
# EMPIRICAL_WRAPPER_TEST_SLEEP_SCALE holds a number in (0, 1], every backoff sleep is multiplied
# by it so the CI proof does not wait minutes. It can only SHORTEN sleeps (anything unset,
# unparsable, <= 0 or > 1 is ignored), it changes no limit, window or exit-code rule, and the
# production task never sets it. Production behaviour is the scale 1.0 below.
$SleepScale = 1.0
$scaleRaw = $Env:EMPIRICAL_WRAPPER_TEST_SLEEP_SCALE
if (-not [string]::IsNullOrWhiteSpace($scaleRaw)) {
    $parsedScale = 0.0
    if ([double]::TryParse($scaleRaw, [System.Globalization.NumberStyles]::Float, [System.Globalization.CultureInfo]::InvariantCulture, [ref]$parsedScale) -and $parsedScale -gt 0 -and $parsedScale -le 1) {
        $SleepScale = $parsedScale
    }
}

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
$Env:PYTHONPATH = Join-Path $RepoRoot "src"
$LocalAppData = $Env:LOCALAPPDATA
if ([string]::IsNullOrWhiteSpace($LocalAppData)) {
    throw "LOCALAPPDATA is not set; cannot locate the maintenance hold"
}
$HoldFile = Join-Path $LocalAppData "EmpiricalPlatform\safety\console-control\maintenance-hold.json"

if (-not (Test-Path -LiteralPath $VenvActivate)) {
    throw "venv not found at $VenvActivate -- run this from a machine with the repo's venv already set up"
}

$restartTimes = New-Object System.Collections.Generic.List[datetime]
$backoff = $InitialBackoffSeconds

while ($true) {
    # Checked before EVERY launch, including the first and every restart.
    if (Test-Path -LiteralPath $HoldFile) {
        Write-Warning "maintenance hold present at $HoldFile -- NOT launching the console. Release it with: python -m empirical_platform.entrypoints.release_maintenance_hold"
        exit $ExitIntentionalStop
    }

    & $VenvActivate
    $exitCode = 1
    try {
        & python -m empirical_platform.entrypoints.operator_console --capability paper-exit --no-browser
        $exitCode = $LASTEXITCODE
    } catch {
        Write-Warning "console launch failed: $_"
        $exitCode = 1
    }

    if ($NoRestartExitCodes -contains $exitCode) {
        Write-Host "console exited with code $exitCode (deliberate stop or refusal) -- not restarting."
        exit $ExitIntentionalStop
    }

    $now = Get-Date
    $restartTimes.Add($now)
    $cutoff = $now.AddSeconds(-$RestartWindowSeconds)
    $recent = @($restartTimes | Where-Object { $_ -gt $cutoff })
    $restartTimes = New-Object System.Collections.Generic.List[datetime]
    foreach ($t in $recent) { $restartTimes.Add($t) }
    if ($restartTimes.Count -gt $MaxRestartsPerWindow) {
        Write-Warning "circuit breaker: $($restartTimes.Count) crash restarts within $RestartWindowSeconds seconds -- giving up. Investigate before starting the task again."
        exit $ExitIntentionalStop
    }

    Write-Warning "console crashed (exit code $exitCode). Restarting in $backoff s."
    Start-Sleep -Milliseconds ([int][Math]::Round($backoff * 1000 * $SleepScale))
    $backoff = [Math]::Min($backoff * 2, $MaxBackoffSeconds)
}
