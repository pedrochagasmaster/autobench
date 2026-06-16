# deploy_and_install.ps1

# --- Configuration ---
Write-Host "=== Configuration ===" -ForegroundColor Cyan
$RemoteUserInput = Read-Host "Enter Remote User [default: e176097]"
$RemoteUser = if ([string]::IsNullOrWhiteSpace($RemoteUserInput)) { "e176097" } else { $RemoteUserInput }

$HostSuffix = Read-Host "Enter Host Suffix (e.g., '03' for hde2stl020003)"
if ([string]::IsNullOrWhiteSpace($HostSuffix)) {
    Write-Error "Host Suffix is required."
    exit 1
}

$RemoteServer = "hde2stl0200${HostSuffix}.mastercard.int"
$RemotePort = 2222
$RemotePath = "/ads_storage/dispatch"
$ZipName = "dispatch_deploy.zip"
$SetupScript = "install.sh"
$VendorDir = "vendor"
$PythonRemote = "python3" # Uses whatever python3 is on the PATH (3.10 or 3.11)

# --- Step 1: Create Vendor Bundle ---
Write-Host "`n=== Step 1: Creating Vendor Bundle ===" -ForegroundColor Cyan

if (!(Test-Path -Path $VendorDir)) {
    New-Item -ItemType Directory -Path $VendorDir | Out-Null
    Write-Host "Created directory: $VendorDir"
}

# Clean previous packages to ensure fresh download
Remove-Item -Path "$VendorDir\*" -Force -Recurse -ErrorAction SilentlyContinue

if (!(Test-Path requirements.txt)) {
    Write-Error "requirements.txt not found!"
    exit 1
}

Write-Host "Downloading binary packages for Linux (Python 3.10)..."
py -m pip download -r requirements.txt --dest $VendorDir --platform manylinux2014_x86_64 --python-version 3.10 --implementation cp --abi cp310 --only-binary=:all:

if ($LASTEXITCODE -ne 0) {
    Write-Error "Download failed."
    exit 1
}

# Verify files exist
if ((Get-ChildItem $VendorDir).Count -eq 0) {
    Write-Error "Vendor directory is empty! Something went wrong with the download."
    exit 1
}

# --- Step 2: Compress Artifacts ---
Write-Host "`n=== Step 2: Compressing Artifacts (Python) ===" -ForegroundColor Cyan
if (Test-Path $ZipName) { Remove-Item $ZipName -Force }

# We use Python to zip because Compress-Archive uses Windows backslashes,
# which breaks directory structure when unzipped on Linux.
$PyScript = @"
import zipfile, os

zip_name = '$ZipName'
items = ['dispatch', 'scr', 'vendor', 'install.sh', 'pyproject.toml', 'requirements.txt', 'VERSION', 'README.md', 'docs']

print(f'Creating {zip_name}...')
with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zf:
    for item in items:
        if not os.path.exists(item):
            print(f'  Warning: {item} not found, skipping.')
            continue
        if os.path.isfile(item):
            print(f'  Adding {item}')
            zf.write(item, os.path.basename(item))
        elif os.path.isdir(item):
            print(f'  Adding {item} (recursive)')
            for root, dirs, files in os.walk(item):
                # Skip .pyc files or __pycache__
                if '__pycache__' in root:
                    continue
                for file in files:
                    if file.endswith('.pyc'):
                        continue
                    file_path = os.path.join(root, file)
                    # Create relative path for archive
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
                 "DISPATCH_PYTHON_BIN=`$(command -v python3.11 || command -v python3.10) ./$SetupScript"

Write-Host "Executing setup on remote server..."
ssh -p $RemotePort "${RemoteUser}@${RemoteServer}" "$RemoteCommand"

if ($LASTEXITCODE -eq 0) {
    Write-Host "`n=== SUCCESS! ===" -ForegroundColor Green
    Write-Host "Dispatch is deployed and installed."
    Write-Host "You can verify by running: ssh -p $RemotePort ${RemoteUser}@${RemoteServer} 'source ~/.bashrc && dispatch --help'"
} else {
    Write-Error "Remote installation failed."
}
