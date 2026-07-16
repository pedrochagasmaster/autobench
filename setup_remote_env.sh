#!/usr/bin/env sh
# Bootstrap/recovery entrypoint. Dependency delivery must already have produced
# an edge-deploy-compatible verified bundle for Autobench.
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
cd "$ROOT_DIR"

chmod +x \
  install.sh onboard.sh run_tool.sh \
  bin/autobench bin/autobench-cli bin/runtime_check.sh

echo "Installing or reusing the verified shared runtime..."
./install.sh

. "$ROOT_DIR/bin/runtime_check.sh"
RUNTIME=$(autobench_active_runtime "$ROOT_DIR")
METADATA="$RUNTIME/.complete.json"

echo "Running shared-launcher smoke checks..."
"$ROOT_DIR/bin/autobench-cli" config list
"$ROOT_DIR/bin/autobench-cli" share --help

echo "Running compile and drift checks with the active runtime..."
"$RUNTIME/bin/python" -m compileall benchmark.py tui_app.py core utils scripts tools
mkdir -p tools/prod_tui/reports
"$RUNTIME/bin/python" -m tools.prod_tui drift \
  --local . \
  --remote "$ROOT_DIR" \
  --output tools/prod_tui/reports/bundle_drift.json

PUBLICLY_WRITABLE=$(
  find "$RUNTIME" -xdev ! -type l -perm /022 -print 2>/dev/null || true
)
if [ -n "$PUBLICLY_WRITABLE" ]; then
  echo "Shared runtime contains publicly writable entries:" >&2
  printf '%s\n' "$PUBLICLY_WRITABLE" >&2
  exit 1
fi

echo "Active runtime: $RUNTIME"
echo "Completion metadata:"
cat "$METADATA"
echo "Shared launcher permissions:"
ls -l bin/autobench bin/autobench-cli bin/runtime_check.sh
echo "Runtime permission evidence: no group/world-writable entries"
echo "SUMMARY runtime=$RUNTIME metadata=$METADATA wrappers=passed drift=reported permissions=passed"
