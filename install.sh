#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
USER_NAME=${USER:-$(id -un)}
BUNDLE_DIR=${EDGE_DEPLOY_BUNDLE_DIR:-/ads_storage/$USER_NAME/.edge-deploy/bundles/autobench/current}
PYTHON_BIN=${EDGE_DEPLOY_PYTHON_BIN:-${AUTOBENCH_PYTHON_BIN:-}}

if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.10 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.10)
  else
    PYTHON_BIN=/sys_apps_01/python/python310/bin/python3.10
  fi
fi

if [ ! -d "$ROOT_DIR" ] || [ ! -w "$ROOT_DIR" ]; then
  echo "$ROOT_DIR must exist and be writable by the Release Operator" >&2
  exit 1
fi
if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python 3.10 not found at $PYTHON_BIN" >&2
  echo "Set AUTOBENCH_PYTHON_BIN to the approved Python 3.10 interpreter." >&2
  exit 1
fi
if [ ! -f "$BUNDLE_DIR/manifest.json" ] ||
   [ ! -f "$BUNDLE_DIR/requirements/requirements.txt" ]; then
  echo "Verified dependency bundle not found: $BUNDLE_DIR" >&2
  echo "Run the edge-deploy dependency delivery phase before installing." >&2
  exit 1
fi

"$PYTHON_BIN" "$ROOT_DIR/shared_runtime.py" \
  --bundle "$BUNDLE_DIR" \
  --python "$PYTHON_BIN" \
  --root "$ROOT_DIR"

echo "Shared Autobench runtime is active."
echo "Analysts can now run: $ROOT_DIR/onboard.sh"
