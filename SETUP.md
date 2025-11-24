Yes, but because your server has **no internet access** (as confirmed by the failed ping), you cannot use a single script on the server to do everything.

You need a **two-stage workflow**:

1.  **Stage 1 (Local Machine):** A script to download all dependencies from the Artifactory.
2.  **Stage 2 (Remote Server):** A script to install them into your virtual environment without using the internet.

Here is the full setup for both sides.

-----

### Stage 1: The Download Script (Run on your Laptop)

Save this as `download_bundle.sh` (Mac/Linux) or `download_bundle.bat` (Windows) on your local machine where you have internet access and the `requirements.txt` file.

**Bash (Mac/Linux):**

```bash
#!/bin/bash

# 1. Create a directory for the offline packages
mkdir -p offline_packages

# 2. Download packages specified in requirements.txt
# We use the specific Artifactory URL found in your document
echo "Downloading packages..."
pip download \
    -r requirements.txt \
    --dest offline_packages \
    --index-url https://artifactdv.us.platforms.dev/artifactory/api/pypi/pypi-all/simple

echo "Download complete. Please transfer the 'offline_packages' folder and 'requirements.txt' to the server."
```

**CMD (Windows):**

```cmd
@echo off
mkdir offline_packages
echo Downloading packages...
pip download -r requirements.txt --dest offline_packages --index-url https://artifactdv.us.platforms.dev/artifactory/api/pypi/pypi-all/simple
echo Download complete.
pause
```

-----

### Stage 2: Transfer Files

You will now have a folder named `offline_packages` full of `.whl` and `.tar.gz` files.
Use `scp` or WinSCP to copy both **requirements.txt** and the **offline\_packages** folder to your server path:
`/ads_storage/Peer Benchmark Tool/`

-----

### Stage 3: The Install Script (Run on the Server)

Save this as `setup_env.sh` on your server inside `/ads_storage/Peer Benchmark Tool/`.

```bash
#!/bin/bash

# 1. Initialize/Create the Virtual Environment if it doesn't exist
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# 2. Activate the environment
source .venv/bin/activate

# 3. Upgrade pip (using the offline file if present in the folder, otherwise skips)
# Note: This looks for pip inside the offline folder to update itself
pip install --no-index --find-links=./offline_packages pip

# 4. Install requirements from the offline folder
echo "Installing packages from offline source..."
pip install \
    --no-index \
    --find-links=./offline_packages \
    -r requirements.txt

echo "Setup complete! Environment is ready."
```

### How to run it on the server:

1.  Navigate to your folder:
    ```bash
    cd "/ads_storage/Peer Benchmark Tool"
    ```
2.  Make the script executable:
    ```bash
    chmod +x setup_env.sh
    ```
3.  Run it:
    ```bash
    ./setup_env.sh
    ```

### Why this works 

Your uploaded document ("Python Distribution Management") specifically highlights that direct installation on Edge Nodes has "pending issues". It recommends downloading and zipping libraries as a workaround. By using `--find-links=./offline_packages` and `--no-index`, you force `pip` to ignore the broken internet connection and look strictly at the files you uploaded.