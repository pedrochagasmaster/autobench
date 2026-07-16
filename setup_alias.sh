#!/usr/bin/env sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
echo "setup_alias.sh is now a compatibility entrypoint for Autobench onboarding."
exec "$ROOT_DIR/onboard.sh"
