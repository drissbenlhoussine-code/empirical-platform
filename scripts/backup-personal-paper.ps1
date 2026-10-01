param(
    [Parameter(Mandatory=$true)][string]$Repository,
    [string]$PgBin = 'C:\Program Files\PostgreSQL\16\bin',
    [string]$BackupRoot = "$env:LOCALAPPDATA\EmpiricalPlatform\backups\personal-paper"
)
$ErrorActionPreference = 'Stop'
# Load only database configuration. Never echo credentials or place them in arguments.
foreach ($name in @('HOST','PORT','DATABASE','USER','PASSWORD')) {
    $key = "EMPIRICAL_PLATFORM_POSTGRES_$name"
    $value = [Environment]::GetEnvironmentVariable($key, 'User')
    if ($null -ne $value) { [Environment]::SetEnvironmentVariable($key, $value, 'Process') }
}
[Environment]::SetEnvironmentVariable('EMPIRICAL_PLATFORM_DATABASE_MODE', 'PERSONAL_PAPER', 'Process')
$python = Join-Path $Repository '.venv\Scripts\python.exe'
$program = Join-Path $Repository 'tools\personal_paper_backup.py'
$statusDirectory = Join-Path $env:LOCALAPPDATA 'EmpiricalPlatform\safety'
New-Item -ItemType Directory -Path $statusDirectory -Force | Out-Null
$resultCode = 2
try {
    # The Python command sanitizes all diagnostics, including database failures.
    & $python $program --root $BackupRoot --pg-bin $PgBin --keep 168
    $resultCode = $LASTEXITCODE
} finally {
    @{
        checked_utc = [DateTime]::UtcNow.ToString('o')
        exit_code = $resultCode
        status = $(if ($resultCode -eq 0) { 'BACKUP_COMPLETE' } else { 'BACKUP_BLOCKED' })
    } | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $statusDirectory 'backup-status.json')
}
exit $resultCode
