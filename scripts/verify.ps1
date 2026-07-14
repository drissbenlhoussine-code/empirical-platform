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

$SecretScanTargets = @(
    ".dockerignore",
    ".editorconfig",
    ".env.example",
    ".github",
    ".gitignore",
    "LICENSE",
    "README.md",
    "alembic.ini",
    "docs",
    "infra",
    "migrations",
    "pyproject.toml",
    "scripts",
    "src",
    "tests",
    "tools",
    "MILESTONE_004_REPOSITORY_SCAFFOLDING_AND_TOOLCHAIN_BOOTSTRAP.md"
)

Invoke-Checked python @("--version")
Invoke-Checked python @("-m", "pip", "install", "-e", ".[dev,test,security,build]")
Invoke-Checked python @("-m", "compileall", "-q", "src", "tests", "tools", "migrations")
Invoke-Checked python @("-m", "ruff", "format", "--check", ".")
Invoke-Checked python @("-m", "ruff", "check", ".")
Invoke-Checked python @("-m", "mypy")
Invoke-Checked python @("-m", "pytest")
Invoke-Checked python @("tools/check_architecture.py", ".")

python tools/check_architecture.py tests/fixtures/illegal_imports
if ($LASTEXITCODE -eq 0) {
    throw "Negative architecture fixture did not report a violation."
}

Invoke-Checked python @("-m", "pip_audit")
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
Invoke-Checked python @("-m", "build")
Invoke-Checked python @("-c", "import empirical_platform; print(empirical_platform.__version__)")
