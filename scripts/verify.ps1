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

Invoke-Checked python @("--version")
Invoke-Checked python @("-m", "pip", "install", "-e", ".[dev,test,security,build,persistence,object-storage]")
Invoke-Checked python @("-m", "compileall", "-q", "src", "tests", "tools", "migrations")
Invoke-Checked python @("-m", "ruff", "format", "--check", ".")
Invoke-Checked python @("-m", "ruff", "check", ".")
Invoke-Checked python @("-m", "mypy")

# pytest's default temp root (%LOCALAPPDATA%\Temp\pytest-of-<user>\...) manages a
# "pytest-current" convenience symlink across runs. On this platform that symlink
# can be left locked by another process (e.g. antivirus real-time scanning),
# which makes pytest's own post-test cleanup hook crash with PermissionError even
# though every test already passed. Passing --basetemp with a fresh GUID-named
# directory under $env:TEMP bypasses that shared, stateful location entirely, so
# a stale or externally locked alias from a previous run can never collide with
# this run. This changes nothing about test selection, execution, or coverage.
$PytestBaseTemp = Join-Path $env:TEMP ("empirical-platform-pytest-" + [System.Guid]::NewGuid().ToString("N"))
try {
    Invoke-Checked python @("-m", "pytest", "--basetemp=$PytestBaseTemp")
}
finally {
    # Best-effort cleanup only: a failure here must never mask the real pytest
    # exit code captured by Invoke-Checked above.
    if (Test-Path $PytestBaseTemp) {
        Remove-Item -Path $PytestBaseTemp -Recurse -Force -ErrorAction SilentlyContinue
    }
}

Invoke-Checked python @("tools/check_architecture.py", ".")

python tools/check_architecture.py tests/fixtures/illegal_imports
if ($LASTEXITCODE -eq 0) {
    throw "Negative architecture fixture did not report a violation."
}

Invoke-Checked powershell @("-ExecutionPolicy", "Bypass", "-File", ".\scripts\security.ps1")
Invoke-Checked python @("-m", "build")
Invoke-Checked python @("-c", "import empirical_platform; print(empirical_platform.__version__)")
