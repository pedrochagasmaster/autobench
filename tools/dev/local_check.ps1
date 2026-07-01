[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Name,
        [string]$Display,
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "== $Name ==" -ForegroundColor Cyan
    Write-Host $Display
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$repoRoot = (& git rev-parse --show-toplevel 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Run this script from inside the Autobench git repository."
}

Set-Location (($repoRoot -join "`n").Trim())

# Wrapped commands:
# py -m compileall benchmark.py tui_app.py core utils scripts tools
# py -m ruff check .
# py -m mypy --no-site-packages core/ utils/
# py scripts/perform_gate_test.py
# py -m pytest
Invoke-Step "Compile Python sources" "py -m compileall benchmark.py tui_app.py core utils scripts tools" {
    py -m compileall benchmark.py tui_app.py core utils scripts tools
}
Invoke-Step "Lint" "py -m ruff check ." {
    py -m ruff check .
}
Invoke-Step "Typecheck" "py -m mypy --no-site-packages core/ utils/" {
    py -m mypy --no-site-packages core/ utils/
}
Invoke-Step "Gate test" "py scripts/perform_gate_test.py" {
    py scripts/perform_gate_test.py
}
Invoke-Step "Unit tests" "py -m pytest" {
    py -m pytest
}

Write-Host ""
Write-Host "Local check passed." -ForegroundColor Green
