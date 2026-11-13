param([Parameter(Mandatory=$true)][string]$Repository)
$ErrorActionPreference = 'Stop'
$resolved = (Resolve-Path -LiteralPath $Repository).Path
$script = Join-Path $resolved 'scripts\backup-personal-paper.ps1'
if (-not (Test-Path -LiteralPath $script -PathType Leaf)) { throw 'Backup script missing' }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument (
    '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' +
    $script + '" -Repository "' + $resolved + '"'
)
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(5) `
    -RepetitionInterval (New-TimeSpan -Hours 1)
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) `
    -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'EmpiricalPlatform Personal Paper Backup' `
    -Action $action -Trigger $trigger -Principal $principal -Settings $settings `
    -Description 'Hourly paired read-only pg_dump; fail closed on database loss; retain 168 complete sets.' `
    -Force | Select-Object TaskName, State
