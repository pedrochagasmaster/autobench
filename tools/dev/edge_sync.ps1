[CmdletBinding()]
param(
    [ValidateSet("03", "04", "all")]
    [string]$Node = "03",

    [ValidateSet("verify", "sync")]
    [string]$Mode = "verify",

    [switch]$IncludeScr
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ($IncludeScr -and $Mode -ne "sync") {
    throw "-IncludeScr is only valid with -Mode sync."
}

$repoRoot = (& git rev-parse --show-toplevel 2>&1)
if ($LASTEXITCODE -ne 0) {
    throw "Run this script from inside the Dispatch git repository."
}

Set-Location (($repoRoot -join "`n").Trim())

$configs = @{
    "03" = "tools/prod_tui/config.yaml"
    "04" = "tools/prod_tui/config-node04.yaml"
}

$targets = if ($Node -eq "all") { @("03", "04") } else { @($Node) }
$deployMode = if ($IncludeScr) { "deploy-all" } else { $Mode }

Write-Host "This wrapper uses the existing authenticated tmux/psmux session for each node." -ForegroundColor Yellow
Write-Host "Start the session and confirm Kerberos before running sync or production checks."
Write-Host ""

foreach ($target in $targets) {
    $config = $configs[$target]
    if (!(Test-Path -Path $config)) {
        throw "Missing config for node ${target}: $config"
    }

    Write-Host "== Node ${target}: $deployMode ==" -ForegroundColor Cyan
    Write-Host "py -m tools.prod_tui._seam_deploy --config $config $deployMode"

    & py -m tools.prod_tui._seam_deploy --config $config $deployMode
    if ($LASTEXITCODE -ne 0) {
        throw "Node $target $deployMode failed with exit code $LASTEXITCODE"
    }

    Write-Host ""
}

Write-Host "Edge sync command completed." -ForegroundColor Green
