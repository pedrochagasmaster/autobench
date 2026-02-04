# Offline Environment Setup

Since the remote server (`/ads_storage/autobench`) has **no internet access**, you must follow this workflow to prepare dependencies on your local machine and deploy them to the server.

## Prerequisites

1.  **Local Machine (Windows):** Internet access, PowerShell, and Python installed.
2.  **Remote Server (Linux):** Python 3.10 installed at `/sys_apps_01/python/python310/bin/python3.10`.
3.  **Repository:** Cloned on *both* your local machine and the remote server.

## Automated Deployment

We have consolidated the setup into a single PowerShell script that handles downloading dependencies, transferring them, and installing them on the remote server.

1.  Open PowerShell in the project root.
2.  Run:
    ```powershell
    .\deploy_and_install.ps1
    ```
3.  Follow the prompts:
    *   **Remote User:** Defaults to `e176097` (press Enter to accept).
    *   **Host Suffix:** Enter the numeric suffix of your server (e.g., `04` for `hde2stl020004.mastercard.int`).

The script will automatically:
*   Download Linux-compatible binaries (wheels) for Python 3.10.
*   Download source packages for libraries without wheels (e.g., `pypyodbc`).
*   Bundle everything into a zip file.
*   Transfer the bundle to the server via SCP (Port 2222).
*   Connect via SSH to unzip the files and run the installation script (`setup_remote_env.sh`).

## Verification

Once the script completes successfully, you can verify the tool works by logging into the server and running:

```bash
cd /ads_storage/autobench
./run_tool.sh share --help
```

## Manual Alternative (If script fails)

If the automation fails, you can perform the steps manually:

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
