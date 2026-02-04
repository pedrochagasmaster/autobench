# deploy_and_install.ps1

# --- Configuration ---
Write-Host "=== Configuration ===" -ForegroundColor Cyan
$RemoteUserInput = Read-Host "Enter Remote User [default: e176097]"
$RemoteUser = if ([string]::IsNullOrWhiteSpace($RemoteUserInput)) { "e176097" } else { $RemoteUserInput }

$HostSuffix = Read-Host "Enter Host Suffix (e.g., '04' for hde2stl020004)"
if ([string]::IsNullOrWhiteSpace($HostSuffix)) {
    Write-Error "Host Suffix is required."
    exit 1
}

$RemoteServer = "hde2stl0200${HostSuffix}.mastercard.int"
$RemotePort = 2222
$RemotePath = "/ads_storage/autobench"
$ZipName = "autobench_deploy.zip"
$SetupScript = "setup_remote_env.sh"
$OfflineDir = "offline_packages"
$PythonRemote = "/sys_apps_01/python/python310/bin/python3.10"

# --- Step 1: Create Offline Bundle ---
Write-Host "`n=== Step 1: Creating Offline Bundle ===" -ForegroundColor Cyan

if (!(Test-Path -Path $OfflineDir)) {
    New-Item -ItemType Directory -Path $OfflineDir | Out-Null
    Write-Host "Created directory: $OfflineDir"
}

# Clean previous packages to ensure fresh download
Remove-Item -Path "$OfflineDir\*" -Force -Recurse -ErrorAction SilentlyContinue

Write-Host "Preparing requirements for Linux..."
# Filter out pypyodbc which doesn't have a wheel and fails with --only-binary
if (Test-Path requirements.txt) {
    $AllReqs = Get-Content requirements.txt
    # We look for lines starting with pypyodbc (case insensitive)
    $PypyodbcReqs = $AllReqs | Where-Object { $_ -match "^pypyodbc" }
    $BinaryReqs = $AllReqs | Where-Object { $_ -notmatch "^pypyodbc" }
    
    $BinaryReqs | Set-Content requirements_linux.txt
} else {
    Write-Error "requirements.txt not found!"
    exit 1
}

Write-Host "Downloading binary packages for Linux (Python 3.10)..."
py -m pip download -r requirements_linux.txt --dest $OfflineDir --platform manylinux2014_x86_64 --python-version 3.10 --implementation cp --abi cp310 --only-binary=:all:

if ($LASTEXITCODE -ne 0) {
    Write-Error "Download failed."
    Write-Host "Hint: If this failed, another package in requirements.txt might not have a Linux binary wheel." -ForegroundColor Yellow
    Write-Host "You may need to treat it like pypyodbc and download it separately." -ForegroundColor Yellow
    exit 1
}

if ($PypyodbcReqs) {
    Write-Host "Downloading source packages for: $PypyodbcReqs"
    # Download the specific version requested in requirements.txt
    foreach ($req in $PypyodbcReqs) {
        py -m pip download $req --dest $OfflineDir --platform manylinux2014_x86_64 --python-version 3.10 --implementation cp --abi cp310 --no-deps
    }
} else {
    Write-Host "No pypyodbc requirement found, skipping source download."
}

# Cleanup temp requirement file
if (Test-Path requirements_linux.txt) { Remove-Item requirements_linux.txt }

# Verify files exist
if ((Get-ChildItem $OfflineDir).Count -eq 0) {
    Write-Error "Offline packages directory is empty! Something went wrong with the download."
    exit 1
}

# --- Step 2: Compress Artifacts ---
Write-Host "`n=== Step 2: Compressing Artifacts (Python) ===" -ForegroundColor Cyan
if (Test-Path $ZipName) { Remove-Item $ZipName -Force }

# We use Python to zip because Compress-Archive uses Windows backslashes,
# which breaks directory structure when unzipped on Linux.
$PyScript = @"
import zipfile, os, sys

zip_name = '$ZipName'
items = ['offline_packages', 'requirements.txt']

print(f'Creating {zip_name}...')
with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
    for item in items:
        if not os.path.exists(item):
            continue
        if os.path.isfile(item):
            print(f'  Adding {item}')
            zf.write(item, os.path.basename(item))
        elif os.path.isdir(item):
            print(f'  Adding {item} (recursive)')
            for root, dirs, files in os.walk(item):
                for file in files:
                    file_path = os.path.join(root, file)
                    # Create relative path for archive (e.g., offline_packages/file.whl)
                    # We assume we are running from project root
                    arcname = os.path.relpath(file_path, os.getcwd())
                    # FORCE forward slashes for Linux compatibility
                    arcname = arcname.replace(os.sep, '/')
                    zf.write(file_path, arcname)
print('Compression complete.')
"@

# Run the python script
py -c $PyScript

if ($LASTEXITCODE -ne 0) {
    Write-Error "Compression failed."
    exit 1
}

# --- Step 3: Transfer to Server ---
Write-Host "`n=== Step 3: Transferring to Server ===" -ForegroundColor Cyan
$Destination = "${RemoteUser}@${RemoteServer}:${RemotePath}"
Write-Host "Uploading $ZipName to $Destination on port $RemotePort..."

# Ensure remote directory exists
ssh -p $RemotePort "${RemoteUser}@${RemoteServer}" "mkdir -p $RemotePath"

# SCP the file
scp -P $RemotePort $ZipName "$Destination/$ZipName"

if ($LASTEXITCODE -ne 0) {
    Write-Error "Transfer failed."
    exit 1
}

# --- Step 4: Remote Installation ---
Write-Host "`n=== Step 4: Remote Installation ===" -ForegroundColor Cyan

# We add 'ls -F' to debug if the folder was created correctly
$RemoteCommand = "cd $RemotePath && " +
                 "echo '--- Unzipping artifacts ---' && " +
                 "$PythonRemote -m zipfile -e $ZipName . && " +
                 "echo '--- Verifying extraction ---' && " +
                 "ls -F && " +
                 "echo '--- Running Setup ---' && " +
                 "chmod +x $SetupScript && " +
                 "./$SetupScript"

Write-Host "Executing setup on remote server..."
ssh -p $RemotePort "${RemoteUser}@${RemoteServer}" "$RemoteCommand"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== SUCCESS! ===" -ForegroundColor Green
    Write-Host "The tool is deployed and installed."
    Write-Host "You can verify by running: ssh -p $RemotePort ${RemoteUser}@${RemoteServer} 'cd $RemotePath && ./run_tool.sh share --help'"
} else {
    Write-Error "Remote installation failed."
}
