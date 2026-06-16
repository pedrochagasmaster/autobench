#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
USER_NAME=${USER:-$(id -un)}
DATA_ROOT=${AUTOBENCH_DATA_ROOT:-/ads_storage/$USER_NAME}
AUTOBENCH_HOME="$DATA_ROOT/.autobench"
PYTHON_BIN=${AUTOBENCH_PYTHON_BIN:-}

if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.11)
  elif command -v python3.10 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.10)
  else
    PYTHON_BIN=/sys_apps_01/python/python310/bin/python3.10
  fi
fi

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python 3.10+ not found at $PYTHON_BIN" >&2
  echo "Set AUTOBENCH_PYTHON_BIN to a supported interpreter." >&2
  exit 1
fi

if [ ! -d "$DATA_ROOT" ] || [ ! -w "$DATA_ROOT" ]; then
  echo "$DATA_ROOT must exist and be writable" >&2
  exit 1
fi

mkdir -p "$AUTOBENCH_HOME/config" "$AUTOBENCH_HOME/logs" "$AUTOBENCH_HOME/cache"
"$PYTHON_BIN" -m venv "$AUTOBENCH_HOME/venv"

if [ -n "$(find "$ROOT_DIR/offline_packages" "$ROOT_DIR/vendor" -maxdepth 1 -name '*.whl' -print -quit 2>/dev/null || true)" ]; then
  "$AUTOBENCH_HOME/venv/bin/pip" install \
    --no-index \
    --find-links="$ROOT_DIR/offline_packages" \
    --find-links="$ROOT_DIR/vendor" \
    -r "$ROOT_DIR/requirements.txt"
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
