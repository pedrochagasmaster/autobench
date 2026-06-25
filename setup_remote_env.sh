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
BUNDLE_PATH="$(pwd)"
INSTALL_RESULT="not_started"
WRAPPER_CHECKS="not_run"
RUNTIME_PYTHON="unknown"
DRIFT_RESULT="not_run"
SMOKE_LEVEL="0"
PERMISSION_EVIDENCE="not_run"
DRIFT_OUTPUT="tools/prod_tui/reports/bundle_drift.json"

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
RUNTIME_PYTHON="$("$PYTHON_BIN" --version 2>&1 || true)"

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
        INSTALL_RESULT="success"

        echo "Running compileall and wrapper smoke checks..."
        "$PYTHON_BIN" -m compileall benchmark.py tui_app.py core utils scripts tools
        ./run_tool.sh config list
        ./run_tool.sh share --help
        WRAPPER_CHECKS="passed"
        SMOKE_LEVEL="1"

        mkdir -p "$(dirname "$DRIFT_OUTPUT")"
        "$PYTHON_BIN" -m tools.prod_tui drift --local . --remote /ads_storage/autobench --output "$DRIFT_OUTPUT"
        DRIFT_RESULT="reported"
        echo "Permission evidence (repo root):"
        ls -ld "$BUNDLE_PATH" 2>/dev/null || true
        echo "Permission evidence (entrypoints):"
        ls -l run_tool.sh setup_alias.sh 2>/dev/null || true
        PERMISSION_EVIDENCE="reported"

        echo "---------------------------------------------------"
        echo "Setup complete! Environment is ready."
        echo "Extraction path: $BUNDLE_PATH"
        echo "Runtime Python: $RUNTIME_PYTHON"
        echo "INSTALL_RESULT=$INSTALL_RESULT"
        echo "WRAPPER_CHECKS=$WRAPPER_CHECKS"
        echo "DRIFT_RESULT=$DRIFT_RESULT"
        echo "SMOKE_LEVEL=$SMOKE_LEVEL"
        echo "PERMISSION_EVIDENCE=$PERMISSION_EVIDENCE"
        echo "SUMMARY bundle_path=$BUNDLE_PATH runtime_python=$RUNTIME_PYTHON install_result=$INSTALL_RESULT wrapper_checks=$WRAPPER_CHECKS drift_result=$DRIFT_RESULT smoke_level=$SMOKE_LEVEL permission_evidence=$PERMISSION_EVIDENCE"
        echo "To activate it in the future, run: source .venv/bin/activate"
        echo "---------------------------------------------------"
    else
        echo "Installation failed."
        echo "Hint: this usually means the bundle needs a rebuild with deploy_and_install.ps1 or the runtime hit an interpreter mismatch."
        echo "Do not trust stale archived wheels after a dependency failure; treat this as a bundle rebuild candidate."
        INSTALL_RESULT="failed"
        exit 1
    fi
else
    echo "Error: Offline packages directory '$OFFLINE_DIR' not found."
    echo "Please ensure you have transferred the 'offline_packages' folder from your local machine."
    INSTALL_RESULT="failed"
    exit 1
fi
