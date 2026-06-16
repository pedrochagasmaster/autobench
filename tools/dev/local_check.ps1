[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [string[]]$Command
    )

    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    Write-Host ($Command -join " ")
    $exe = $Command[0]
    $args = if ($Command.Count -gt 1) { $Command[1..($Command.Count - 1)] } else { @() }
    & $exe @args
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$repoRoot = (& git rev-parse --show-toplevel 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Run this script from inside the Dispatch git repository."
}

Set-Location (($repoRoot -join "`n").Trim())

Invoke-Step "Compile Python sources" @("py", "-m", "compileall", "dispatch", "scr")
Invoke-Step "Run unit tests" @("py", "-m", "pytest", "tests", "tools/prod_tui/tests", "-q")
Invoke-Step "Dispatch help smoke" @("py", "-m", "dispatch", "--help")

Write-Host ""
Write-Host "Local check passed." -ForegroundColor Green
