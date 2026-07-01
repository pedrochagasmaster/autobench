#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
USER_NAME=${USER:-$(id -un)}
DATA_ROOT=${AUTOBENCH_DATA_ROOT:-/ads_storage/$USER_NAME}
AUTOBENCH_HOME="$DATA_ROOT/.autobench"
# Determine the CPython minor version the bundled binary wheels were built for
# (e.g. "3.10" from a cp310 tag). Empty when no binary wheels are bundled, which
# means this is an online install and any supported interpreter is acceptable.
required_wheel_python() {
  for _whl in "$ROOT_DIR"/offline_packages/*.whl "$ROOT_DIR"/vendor/*.whl; do
    [ -e "$_whl" ] || continue
    _cp=$(printf '%s\n' "$_whl" | grep -oE 'cp3[0-9]+' | head -n1 || true)
    if [ -n "${_cp:-}" ]; then
      printf '3.%s\n' "${_cp#cp3}"
      return 0
    fi
  done
  return 0
}

# Resolve an interpreter for an exact "3.X" version across PATH and the known
# Edge Node locations.
find_python() {
  _ver=$1
  _nodots=$(printf '%s' "$_ver" | tr -d '.')
  for _cand in \
    "python${_ver}" \
    "/sys_apps_01/python/python${_nodots}/bin/python${_ver}" \
    "/sys_apps_01/python/python${_nodots}/bin/python3" \
    "/usr/bin/python${_ver}" \
    "/usr/local/bin/python${_ver}"; do
    if command -v "$_cand" >/dev/null 2>&1; then
      command -v "$_cand"
      return 0
    fi
  done
  return 1
}

interpreter_python_version() {
  "$1" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true
}

REQUIRED_PY=$(required_wheel_python)
PYTHON_BIN=${EDGE_DEPLOY_PYTHON_BIN:-${AUTOBENCH_PYTHON_BIN:-}}

if [ -z "$PYTHON_BIN" ]; then
  if [ -n "$REQUIRED_PY" ]; then
    # Bundled binary wheels (cp3XX) dictate the interpreter version: a mismatched
    # interpreter cannot install them (the classic cp310-wheels-vs-python3.11 break).
    PYTHON_BIN=$(find_python "$REQUIRED_PY" || true)
    if [ -z "$PYTHON_BIN" ]; then
      echo "Bundled offline packages require Python $REQUIRED_PY, but no python$REQUIRED_PY interpreter was found." >&2
      echo "Install Python $REQUIRED_PY or set AUTOBENCH_PYTHON_BIN to a matching interpreter." >&2
      exit 1
    fi
  else
    # Online install (no binary wheels bundled): accept any supported 3.10+.
    if command -v python3.11 >/dev/null 2>&1; then
      PYTHON_BIN=$(command -v python3.11)
    elif command -v python3.10 >/dev/null 2>&1; then
      PYTHON_BIN=$(command -v python3.10)
    else
      PYTHON_BIN=/sys_apps_01/python/python310/bin/python3.10
    fi
  fi
fi

if [ ! -x "$PYTHON_BIN" ] && ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python interpreter not found: $PYTHON_BIN" >&2
  echo "Set AUTOBENCH_PYTHON_BIN to a supported Python 3.10+ interpreter." >&2
  exit 1
fi

# Guard the classic failure mode where bundled cp3XX wheels cannot install into a
# mismatched interpreter (e.g. cp310 wheels + python3.11). Fail with a clear,
# actionable message instead of a cryptic "No matching distribution" from pip.
if [ -n "$REQUIRED_PY" ]; then
  ACTUAL_PY=$(interpreter_python_version "$PYTHON_BIN")
  if [ -n "$ACTUAL_PY" ] && [ "$ACTUAL_PY" != "$REQUIRED_PY" ]; then
    echo "Interpreter mismatch: $PYTHON_BIN is Python $ACTUAL_PY, but the bundled offline" >&2
    echo "wheels target Python $REQUIRED_PY (prebuilt cp$(printf '%s' "$REQUIRED_PY" | tr -d '.') wheels for numpy/pandas/scipy)." >&2
    echo "Use a Python $REQUIRED_PY interpreter (set AUTOBENCH_PYTHON_BIN) or rebuild" >&2
    echo "offline_packages for Python $ACTUAL_PY with deploy_and_install.ps1." >&2
    exit 1
  fi
fi

if [ ! -d "$DATA_ROOT" ] || [ ! -w "$DATA_ROOT" ]; then
  echo "$DATA_ROOT must exist and be writable" >&2
  exit 1
fi

mkdir -p "$AUTOBENCH_HOME/config" "$AUTOBENCH_HOME/logs" "$AUTOBENCH_HOME/cache"

if [ -f "$ROOT_DIR/SHA256SUMS" ] && [ -f "$ROOT_DIR/scripts/offline_bundle_checksums.py" ]; then
  echo "Verifying offline package checksums..."
  if ! "$PYTHON_BIN" "$ROOT_DIR/scripts/offline_bundle_checksums.py" verify \
    --manifest "$ROOT_DIR/SHA256SUMS" \
    --base-dir "$ROOT_DIR"; then
    echo "Offline package checksum verification failed." >&2
    echo "Ask the operator to rebuild and redeploy the offline bundle with deploy_and_install.ps1." >&2
    exit 1
  fi
fi

"$PYTHON_BIN" -m venv "$AUTOBENCH_HOME/venv"

if [ -n "$(find "$ROOT_DIR/offline_packages" "$ROOT_DIR/vendor" -maxdepth 1 -name '*.whl' -print -quit 2>/dev/null || true)" ]; then
  if ! "$AUTOBENCH_HOME/venv/bin/pip" install \
    --no-index \
    --find-links="$ROOT_DIR/offline_packages" \
    --find-links="$ROOT_DIR/vendor" \
    -r "$ROOT_DIR/requirements.txt"; then
    echo "Offline dependency install failed." >&2
    echo "The shared offline_packages bundle does not satisfy requirements.txt." >&2
    echo "Ask the operator to rebuild and redeploy the offline bundle with deploy_and_install.ps1." >&2
    exit 1
  fi
else
  "$AUTOBENCH_HOME/venv/bin/pip" install \
    --index-url "${AUTOBENCH_PIP_INDEX_URL:-https://pypi.org/simple}" \
    -r "$ROOT_DIR/requirements.txt"
fi

LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"
cat > "$LOCAL_BIN/autobench" <<EOF
#!/bin/bash
export PYTHONPATH="$ROOT_DIR"
exec "$AUTOBENCH_HOME/venv/bin/python" "$ROOT_DIR/tui_app.py" "\$@"
EOF
chmod +x "$LOCAL_BIN/autobench"

cat > "$LOCAL_BIN/autobench-cli" <<EOF
#!/bin/bash
export PYTHONPATH="$ROOT_DIR"
exec "$AUTOBENCH_HOME/venv/bin/python" "$ROOT_DIR/benchmark.py" "\$@"
EOF
chmod +x "$LOCAL_BIN/autobench-cli"

SHELL_RC="$HOME/.bashrc"
[ "${SHELL:-}" ] && [ "$(basename "$SHELL")" = "zsh" ] && [ -f "$HOME/.zshrc" ] && SHELL_RC="$HOME/.zshrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
case ":$PATH:" in
  *":$LOCAL_BIN:"*) ;;
  *)
    if [ -f "$SHELL_RC" ] && ! grep -F "$PATH_LINE" "$SHELL_RC" >/dev/null 2>&1; then
      printf '\n# Autobench command\n%s\n' "$PATH_LINE" >>"$SHELL_RC"
    fi
    ;;
esac

cp "$ROOT_DIR/VERSION" "$AUTOBENCH_HOME/installed_version"
echo
echo "Autobench installed."
case ":$PATH:" in
  *":$LOCAL_BIN:"*) echo "The autobench command is available in this shell." ;;
  *)
    echo "To use autobench in this shell now:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "New shells will pick this up automatically from $SHELL_RC."
    ;;
esac
echo "Then cd to your working directory and run: autobench"
