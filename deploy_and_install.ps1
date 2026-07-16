# Bootstrap/recovery only. Normal releases use edge-deploy-core.
$ErrorActionPreference = "Stop"

Write-Host "=== Autobench shared-runtime recovery ===" -ForegroundColor Cyan
$RemoteUserInput = Read-Host "Enter Remote User [default: e176097]"
$RemoteUser = if ([string]::IsNullOrWhiteSpace($RemoteUserInput)) {
    "e176097"
} else {
    $RemoteUserInput
}
$HostSuffix = Read-Host "Enter Host Suffix (for example 04)"
if ([string]::IsNullOrWhiteSpace($HostSuffix)) {
    throw "Host Suffix is required."
}

$RemoteServer = "hde2stl0200${HostSuffix}.mastercard.int"
$RemotePort = 2222
$RemotePath = "/ads_storage/autobench"

Write-Host @"
This recovery path does not build or upload a legacy checksum-only package set.
The normal edge-deploy dependency delivery phase must already have created:
  /ads_storage/<operator>/.edge-deploy/bundles/autobench/current/manifest.json
"@ -ForegroundColor Yellow

$RemoteCommand = @"
set -eu
cd $RemotePath
BUNDLE_DIR="/ads_storage/`$USER/.edge-deploy/bundles/autobench/current"
test -f "`$BUNDLE_DIR/manifest.json" || {
  echo "Verified Autobench bundle is missing; run edge-deploy dependency delivery first." >&2
  exit 1
}
chmod +x install.sh setup_remote_env.sh bin/autobench bin/autobench-cli bin/runtime_check.sh
EDGE_DEPLOY_BUNDLE_DIR="`$BUNDLE_DIR" ./setup_remote_env.sh
"@

ssh -p $RemotePort "${RemoteUser}@${RemoteServer}" $RemoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Remote shared-runtime recovery failed."
}

Write-Host "Recovery completed. Review the emitted digest, metadata, smoke, drift, and permission evidence." -ForegroundColor Green
