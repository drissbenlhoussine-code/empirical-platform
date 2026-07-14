$ErrorActionPreference = "Stop"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,

        [Parameter(Mandatory = $true)]
        [string[]] $Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Get-SecretScanTargets {
    $Targets = & python tools/secret_scan_targets.py
    if ($LASTEXITCODE -ne 0) {
        throw "Secret scan target discovery failed."
    }
    $Targets = @($Targets | Where-Object { $_ -ne "" })
    if ($Targets.Count -eq 0) {
        throw "Secret scan target discovery returned no files."
    }
    return $Targets
}

Invoke-Checked python @("-m", "pip_audit")
$SecretScanTargets = Get-SecretScanTargets
Write-Host "Secret scan target count: $($SecretScanTargets.Count)"
$SecretScanOutput = & python -m detect_secrets scan @SecretScanTargets
if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: python -m detect_secrets scan <source targets>"
}
$SecretScanJson = $SecretScanOutput | ConvertFrom-Json
$SecretFindings = @($SecretScanJson.results.PSObject.Properties | Where-Object { $_.MemberType -eq "NoteProperty" })
if ($SecretFindings.Count -ne 0) {
    $SecretScanOutput
    throw "Potential secrets detected in source targets."
}
