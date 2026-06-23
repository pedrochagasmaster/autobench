#!/bin/bash

# setup_remote_env.sh

# Define the specific Python interpreter path.
# This MUST be Python 3.10: the offline bundle built by deploy_and_install.ps1
# contains CPython 3.10 (cp310) wheels for numpy/pandas/scipy, which cannot be
# installed by a 3.11+ interpreter. Keep this in sync with install.sh and
# deploy_and_install.ps1 (--abi cp310 / --python-version 3.10).
PYTHON_BIN="/sys_apps_01/python/python310/bin/python3.10"
VENV_DIR=".venv"
OFFLINE_DIR="./offline_packages"
CHECKSUM_MANIFEST="SHA256SUMS"

# 1. Create Virtual Environment
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment '$VENV_DIR' already exists."
else
    echo "Creating virtual environment using $PYTHON_BIN..."
    if [ -f "$PYTHON_BIN" ]; then
        $PYTHON_BIN -m venv $VENV_DIR
    else
        echo "Error: Python executable not found at $PYTHON_BIN"
        echo "Please verify the path or check if Python 3.10 is installed."
        exit 1
    fi
fi

# 2. Activate Environment
echo "Activating virtual environment..."
source $VENV_DIR/bin/activate

# 3. Upgrade pip (optional but recommended, tries to find it in offline packages)
echo "Attempting to upgrade pip..."
pip install --no-index --find-links=$OFFLINE_DIR pip || echo "Pip upgrade skipped (not found in offline bundle)."

# 3b. Verify offline bundle checksums before installing dependencies.
if [ -f "$CHECKSUM_MANIFEST" ] && [ -f "scripts/offline_bundle_checksums.py" ]; then
    echo "Verifying offline package checksums..."
    "$PYTHON_BIN" scripts/offline_bundle_checksums.py verify --manifest "$CHECKSUM_MANIFEST"
    if [ $? -ne 0 ]; then
        echo "Checksum verification failed."
        exit 1
    fi
else
    echo "Checksum manifest not found; skipping checksum verification."
fi

# 4. Install Packages
if [ -d "$OFFLINE_DIR" ]; then
    echo "Installing packages from $OFFLINE_DIR..."
    pip install --no-index --find-links=$OFFLINE_DIR -r requirements.txt
    
    if [ $? -eq 0 ]; then
        # Make scripts executable
        chmod +x run_tool.sh setup_alias.sh
        
        echo "---------------------------------------------------"
        echo "Setup complete! Environment is ready."
        echo "To activate it in the future, run: source .venv/bin/activate"
        echo "---------------------------------------------------"
    else
        echo "Installation failed."
        exit 1
    fi
else
    echo "Error: Offline packages directory '$OFFLINE_DIR' not found."
    echo "Please ensure you have transferred the 'offline_packages' folder from your local machine."
    exit 1
fi
