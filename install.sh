#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]:-$0}")" && pwd)
USER_NAME=${USER:-$(id -un)}
DATA_ROOT=${DISPATCH_DATA_ROOT:-/ads_storage/$USER_NAME}
DISPATCH_HOME="$DATA_ROOT/.dispatch"
PYTHON_BIN=${DISPATCH_PYTHON_BIN:-}
if [ -z "$PYTHON_BIN" ]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.11)
  elif command -v python3.10 >/dev/null 2>&1; then
    PYTHON_BIN=$(command -v python3.10)
  else
    PYTHON_BIN=/sys_apps_01/python/python310/bin/python3.10
  fi
fi

if [ ! -d "$DATA_ROOT" ] || [ ! -w "$DATA_ROOT" ]; then
  echo "$DATA_ROOT must exist and be writable" >&2
  exit 1
fi

mkdir -p "$DISPATCH_HOME/jobs"

LOCK_FILE="$DISPATCH_HOME/install.lock"
# exec 9>"$LOCK_FILE"
# flock 9

if [ ! -x "$PYTHON_BIN" ]; then
  echo "Python 3.10 not found at $PYTHON_BIN" >&2
  echo "Set DISPATCH_PYTHON_BIN for dev-mode validation if needed." >&2
  exit 1
fi

command -v klist >/dev/null 2>&1 || { echo "klist not found on PATH" >&2; exit 1; }
command -v impala-shell >/dev/null 2>&1 || { echo "impala-shell not found on PATH" >&2; exit 1; }

"$PYTHON_BIN" -m venv "$DISPATCH_HOME/venv"
if [ -n "$(find "$ROOT_DIR/vendor" -maxdepth 1 -name '*.whl' -print -quit 2>/dev/null)" ]; then
  "$DISPATCH_HOME/venv/bin/pip" install --no-index --find-links="$ROOT_DIR/vendor" -r "$ROOT_DIR/requirements.txt"
else
  "$DISPATCH_HOME/venv/bin/pip" install --index-url "${DISPATCH_PIP_INDEX_URL:-https://pypi.org/simple}" \
    -r "$ROOT_DIR/requirements.txt"
fi
# "$DISPATCH_HOME/venv/bin/pip" install --no-deps -e "$ROOT_DIR"

LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"
cat > "$LOCAL_BIN/dispatch" <<EOF
#!/bin/bash
export PYTHONPATH="$ROOT_DIR"
exec "$DISPATCH_HOME/venv/bin/python" -m dispatch "\$@"
EOF
chmod +x "$LOCAL_BIN/dispatch"

SHELL_RC="$HOME/.bashrc"
[ "${SHELL:-}" ] && [ "$(basename "$SHELL")" = "zsh" ] && [ -f "$HOME/.zshrc" ] && SHELL_RC="$HOME/.zshrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
case ":$PATH:" in
  *":$LOCAL_BIN:"*) ;;
  *)
    if ! grep -F "$PATH_LINE" "$SHELL_RC" >/dev/null 2>&1; then
      printf '\n# Dispatch command\n%s\n' "$PATH_LINE" >>"$SHELL_RC"
    fi
    ;;
esac

CONFIG="$DISPATCH_HOME/config.json"
if [ ! -f "$CONFIG" ]; then
  EMAIL=${DISPATCH_EMAIL:-}
  if [ -z "$EMAIL" ]; then
    printf "Email: "
    read -r EMAIL
  fi
  printf '{\n  "email": "%s"\n}\n' "$EMAIL" >"$CONFIG"
fi

cp "$ROOT_DIR/VERSION" "$DISPATCH_HOME/installed_version"
echo
echo "Dispatch installed."
case ":$PATH:" in
  *":$LOCAL_BIN:"*)
    echo "The dispatch command is available in this shell."
    ;;
  *)
    echo "To use dispatch in this shell now:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "New shells will pick this up automatically from $SHELL_RC."
    ;;
esac
echo "Then cd to your SQL files and run: dispatch"
