#!/bin/bash
# Stage the repo fonts into public/ and synthesize the soundtrack so the
# Remotion composition can resolve all static assets.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$DIR/../.." && pwd)"

mkdir -p "$DIR/public/fonts" "$DIR/public/audio"
cp "$REPO_ROOT/assets/fonts/InterDisplay-Light.ttf" \
   "$REPO_ROOT/assets/fonts/InterDisplay-Medium.ttf" \
   "$REPO_ROOT/assets/fonts/InterDisplay-SemiBold.ttf" \
   "$REPO_ROOT/assets/fonts/InterDisplay-Bold.ttf" \
   "$REPO_ROOT/assets/fonts/JetBrainsMono-Regular.ttf" \
   "$REPO_ROOT/assets/fonts/JetBrainsMono-Bold.ttf" \
   "$DIR/public/fonts/"

python3 "$DIR/scripts/make_soundtrack.py"
echo "Assets ready under $DIR/public/"
