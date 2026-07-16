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
for _target in "$LOCAL_BIN/autobench" "$LOCAL_BIN/autobench-cli"; do
  if [ -e "$_target" ] && [ ! -f "$_target" ] && [ ! -L "$_target" ]; then
    echo "Cannot replace non-file launcher target: $_target" >&2
    exit 1
  fi
done

AUTOBENCH_TMP="$LOCAL_BIN/.autobench.tmp.$$"
CLI_TMP="$LOCAL_BIN/.autobench-cli.tmp.$$"
AUTOBENCH_BACKUP="$LOCAL_BIN/.autobench.backup.$$"
CLI_BACKUP="$LOCAL_BIN/.autobench-cli.backup.$$"
trap 'rm -f "$AUTOBENCH_TMP" "$CLI_TMP" "$AUTOBENCH_BACKUP" "$CLI_BACKUP"' 0

cat >"$AUTOBENCH_TMP" <<EOF
#!/usr/bin/env sh
exec "$ROOT_DIR/bin/autobench" "\$@"
EOF
cat >"$CLI_TMP" <<EOF
#!/usr/bin/env sh
exec "$ROOT_DIR/bin/autobench-cli" "\$@"
EOF
chmod 755 "$AUTOBENCH_TMP" "$CLI_TMP"

[ ! -e "$LOCAL_BIN/autobench" ] && [ ! -L "$LOCAL_BIN/autobench" ] ||
  mv "$LOCAL_BIN/autobench" "$AUTOBENCH_BACKUP"
if ! {
  [ ! -e "$LOCAL_BIN/autobench-cli" ] && [ ! -L "$LOCAL_BIN/autobench-cli" ]
} then
  if ! mv "$LOCAL_BIN/autobench-cli" "$CLI_BACKUP"; then
    [ ! -e "$AUTOBENCH_BACKUP" ] || mv "$AUTOBENCH_BACKUP" "$LOCAL_BIN/autobench"
    exit 1
  fi
fi

if ! mv "$AUTOBENCH_TMP" "$LOCAL_BIN/autobench"; then
  [ ! -e "$AUTOBENCH_BACKUP" ] || mv "$AUTOBENCH_BACKUP" "$LOCAL_BIN/autobench"
  [ ! -e "$CLI_BACKUP" ] || mv "$CLI_BACKUP" "$LOCAL_BIN/autobench-cli"
  exit 1
fi
if ! mv "$CLI_TMP" "$LOCAL_BIN/autobench-cli"; then
  rm -f "$LOCAL_BIN/autobench"
  [ ! -e "$AUTOBENCH_BACKUP" ] || mv "$AUTOBENCH_BACKUP" "$LOCAL_BIN/autobench"
  [ ! -e "$CLI_BACKUP" ] || mv "$CLI_BACKUP" "$LOCAL_BIN/autobench-cli"
  exit 1
fi
rm -f "$AUTOBENCH_BACKUP" "$CLI_BACKUP"
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
