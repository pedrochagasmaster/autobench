#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
USER_NAME=${USER:-$(id -un)}
DATA_ROOT=${AUTOBENCH_DATA_ROOT:-/ads_storage/$USER_NAME}
AUTOBENCH_HOME="$DATA_ROOT/.autobench"

. "$ROOT_DIR/bin/runtime_check.sh"
autobench_active_runtime "$ROOT_DIR" >/dev/null

for _launcher in "$ROOT_DIR/bin/autobench" "$ROOT_DIR/bin/autobench-cli"; do
  if [ ! -x "$_launcher" ]; then
    echo "Shared Autobench launcher is missing or not executable: $_launcher" >&2
    exit 1
  fi
done
if [ ! -d "$DATA_ROOT" ] || [ ! -w "$DATA_ROOT" ]; then
  echo "$DATA_ROOT must exist and be writable" >&2
  exit 1
fi

mkdir -p \
  "$AUTOBENCH_HOME/config" \
  "$AUTOBENCH_HOME/logs" \
  "$AUTOBENCH_HOME/cache" \
  "$AUTOBENCH_HOME/telemetry"
chmod 700 \
  "$AUTOBENCH_HOME" \
  "$AUTOBENCH_HOME/config" \
  "$AUTOBENCH_HOME/logs" \
  "$AUTOBENCH_HOME/cache" \
  "$AUTOBENCH_HOME/telemetry"

LOCAL_BIN="$HOME/.local/bin"
mkdir -p "$LOCAL_BIN"
for _name in autobench autobench-cli; do
  _temporary="$LOCAL_BIN/.$_name.tmp.$$"
  trap 'rm -f "$LOCAL_BIN/.autobench.tmp.$$" "$LOCAL_BIN/.autobench-cli.tmp.$$"' 0
  cat >"$_temporary" <<EOF
#!/usr/bin/env sh
exec "$ROOT_DIR/bin/$_name" "\$@"
EOF
  chmod 755 "$_temporary"
  mv "$_temporary" "$LOCAL_BIN/$_name"
done
trap - 0

SHELL_RC="$HOME/.bashrc"
[ "${SHELL:-}" ] &&
  [ "$(basename "$SHELL")" = "zsh" ] &&
  [ -f "$HOME/.zshrc" ] &&
  SHELL_RC="$HOME/.zshrc"
PATH_LINE='export PATH="$HOME/.local/bin:$PATH"'
case ":$PATH:" in
  *":$LOCAL_BIN:"*) ;;
  *)
    if ! grep -F "$PATH_LINE" "$SHELL_RC" >/dev/null 2>&1; then
      printf '\n# Autobench commands\n%s\n' "$PATH_LINE" >>"$SHELL_RC"
    fi
    ;;
esac

echo
echo "Autobench onboarding complete."
case ":$PATH:" in
  *":$LOCAL_BIN:"*) echo "The autobench commands are available in this shell." ;;
  *)
    echo "To use Autobench in this shell now:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "New shells will pick this up automatically from $SHELL_RC."
    ;;
esac
echo "Then cd to your working directory and run: autobench"
