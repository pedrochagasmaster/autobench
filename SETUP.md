# Offline Environment Setup

Since the remote server (`/ads_storage/autobench`) has **no internet access**, you must follow this workflow to prepare dependencies on your local machine and deploy them to the server.

## Prerequisites

1.  **Local Machine (Windows):** Internet access, PowerShell, and Python installed.
2.  **Remote Server (Linux):** Python 3.10 installed at `/sys_apps_01/python/python310/bin/python3.10`.
3.  **Repository:** Cloned on *both* your local machine and the remote server.

## Automated Deployment (Dependencies)

This workflow is for **installing dependencies** (Python packages). You only need to run this when `requirements.txt` changes.

1.  Open PowerShell in the project root.
2.  Run:
    ```powershell
    .\deploy_and_install.ps1
    ```
3.  Follow the prompts:
    *   **Remote User:** Defaults to `e176097` (press Enter to accept).
    *   **Host Suffix:** Enter the numeric suffix of your server (e.g., `04` for `hde2stl020004.mastercard.int`).

## Keeping the Code Up-to-Date

To update the **source code** (scripts, logic) on the server, use standard `git` commands.

### Initial Git Setup (Run Once)
If you see "not a git repository" or branch errors:

```bash
cd /ads_storage/autobench && git init && git remote add origin https://e176097@scm.mastercard.int/stash/scm/~e176097/autobench.git && git fetch origin && git checkout -f -b main origin/maingit checkout -f -b main origin/main
```

### Routine Updates
To pull the latest changes from the repository:

```bash
cd /ads_storage/autobench
git pull
```
*(You will be asked for your password).*

## Verification

Once installed, verify the tool works by running (on the server):

```bash
cd /ads_storage/autobench
./run_tool.sh share --help
```

## Manual Alternative (Dependencies)

If the automated `deploy_and_install.ps1` script fails, you can perform the steps manually:

1.  **Download & Bundle (Local):**
    *   Review `deploy_and_install.ps1` to see how dependencies are downloaded (some as binaries, some as source).
    *   Zip the resulting `offline_packages/` folder and `requirements.txt`.
2.  **Transfer:** Use `scp` (port 2222) to send the zip to `/ads_storage/autobench`.
3.  **Install (Remote):**
    *   SSH into the server.
    *   Unzip: 
        ```bash
        /sys_apps_01/python/python310/bin/python3.10 -m zipfile -e autobench_deploy.zip .
        ```
    *   Run Setup: 
        ```bash
        chmod +x setup_remote_env.sh
        ./setup_remote_env.sh
        ```