#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)

case "${1:-tui}" in
  tui)
    if [ "${1:-}" = "tui" ]; then
      shift
    fi
    exec "$ROOT_DIR/bin/autobench" "$@"
    ;;
  share|rate|config|telemetry)
    exec "$ROOT_DIR/bin/autobench-cli" "$@"
    ;;
  *)
    echo "Usage: ./run_tool.sh [tui|share|rate|config|telemetry] [options...]"
    exit 2
    ;;
esac
