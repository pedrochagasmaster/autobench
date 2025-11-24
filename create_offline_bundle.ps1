# create_offline_bundle.ps1
Write-Host "Starting offline package download..."

# Create directory
$OfflineDir = "offline_packages"
if (!(Test-Path -Path $OfflineDir)) {
    New-Item -ItemType Directory -Path $OfflineDir | Out-Null
    Write-Host "Created directory: $OfflineDir"
}

# Download packages
# Using standard PyPI since the internal Artifactory seems inaccessible
# $IndexUrl = "https://artifactdv.us.platforms.dev/artifactory/api/pypi/pypi-all/simple"

Write-Host "Cleaning previous packages..."
Remove-Item -Path "$OfflineDir\*" -Force -Recurse -ErrorAction SilentlyContinue

Write-Host "Preparing requirements for Linux..."
# Filter out pypyodbc which doesn't have a wheel and fails with --only-binary
Get-Content requirements.txt | Where-Object { $_ -notmatch "pypyodbc" } | Set-Content requirements_linux.txt

Write-Host "Downloading binary packages for Linux (Python 3.10)..."
# We use --platform manylinux2014_x86_64 to ensure compatibility with the remote Linux server
# We use --only-binary=:all: to force downloading wheels instead of source
py -m pip download -r requirements_linux.txt --dest $OfflineDir --platform manylinux2014_x86_64 --python-version 3.10 --implementation cp --abi cp310 --only-binary=:all:

if ($LASTEXITCODE -eq 0) {
    Write-Host "Downloading source packages (pypyodbc)..."
    # Download pypyodbc separately allowing source distribution
    py -m pip download pypyodbc>=1.3.6 --dest $OfflineDir --platform manylinux2014_x86_64 --python-version 3.10 --implementation cp --abi cp310 --no-deps

    Write-Host "Download complete." -ForegroundColor Green
    Write-Host "Please transfer the '$OfflineDir' folder and 'requirements.txt' to the remote server." -ForegroundColor Cyan
} else {
    Write-Host "Download failed. Please check your internet connection or VPN." -ForegroundColor Red
    Write-Host "Note: If specific packages fail, they might not have pre-built Linux wheels." -ForegroundColor Yellow
}

# Cleanup
if (Test-Path requirements_linux.txt) {
    Remove-Item requirements_linux.txt
}
