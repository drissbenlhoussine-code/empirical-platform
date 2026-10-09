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
# What this DOES do today: activates the repo's existing venv and runs the current paper
# console, restarting it automatically if it exits (a crash restarts cleanly from durable
# Postgres state). It does NOT touch Tailscale, does NOT register itself as a scheduled
# task, and does NOT run anything else.
#
# This script is a committed artifact only. Actually registering it as a Windows autostart
# task (via Task Scheduler, importing `v1-console-task.xml` in this same directory) is an
# Owner action outside engineering -- see that file's own header comment for exact steps.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$VenvActivate = Join-Path $RepoRoot ".venv\Scripts\Activate.ps1"
$Env:PYTHONPATH = Join-Path $RepoRoot "src"

if (-not (Test-Path $VenvActivate)) {
    throw "venv not found at $VenvActivate -- run this from a machine with the repo's venv already set up"
}

while ($true) {
    & $VenvActivate
    try {
        python -m empirical_platform.entrypoints.operator_console --capability paper-exit --no-browser
    } catch {
        Write-Warning "console exited: $_. Restarting in 10s."
    }
    Start-Sleep -Seconds 10
}
