#!/bin/bash
# Convert the SVG footage captured by capture_footage.py into transparent
# PNGs under public/footage/, using headless Chrome.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SVG_DIR="$DIR/footage_svg"
OUT_DIR="$DIR/public/footage"
CHROME="${CHROME:-google-chrome}"
mkdir -p "$OUT_DIR"

for f in "$SVG_DIR"/*.svg; do
  base="$(basename "${f%.svg}")"
  dims=$(python3 - "$f" <<'EOF'
import re, sys
s = open(sys.argv[1]).read()
m = re.search(r'viewBox="0 0 ([0-9.]+) ([0-9.]+)"', s)
print(f"{int(float(m.group(1)))},{int(float(m.group(2)))}")
EOF
)
  profile="$(mktemp -d)"
  rm -f "$OUT_DIR/$base.png"
  # Chrome can hang around after writing the screenshot in headless
  # environments; the timeout is a cleanup mechanism, not a failure.
  timeout 60 "$CHROME" --headless=new --disable-gpu --no-sandbox \
    --disable-dev-shm-usage --user-data-dir="$profile" \
    --hide-scrollbars --force-device-scale-factor=2 \
    --default-background-color=00000000 \
    --screenshot="$OUT_DIR/$base.png" \
    --window-size="$dims" "file://$f" 2>/dev/null || true
  rm -rf "$profile"
  if [[ ! -s "$OUT_DIR/$base.png" ]]; then
    echo "ERROR: failed to render $base.png" >&2
    exit 1
  fi
  echo "$base.png"
done
