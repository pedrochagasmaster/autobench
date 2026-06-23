#!/bin/bash
#
# update.sh - Sync this Edge Node deployment to the latest canonical code.
#
# Pulls from the corporate Bitbucket mirror and hard-resets the working tree so
# content AND line endings exactly match the repository (LF is enforced by
# .gitattributes). This is the supported way to update the node: never copy or
# scp individual files onto the node, as that reintroduces CRLF and drift.
#
# Untracked files (e.g. .venv/, offline_packages/, SHA256SUMS) are preserved,
# so the installed environment is left intact. If dependencies changed, refresh
# the offline bundle and re-run setup_remote_env.sh afterwards.
#
# Overridable via environment:
#   AUTOBENCH_GIT_REMOTE (default: bitbucket)
#   AUTOBENCH_GIT_BRANCH (default: main)

set -euo pipefail

REMOTE="${AUTOBENCH_GIT_REMOTE:-bitbucket}"
BRANCH="${AUTOBENCH_GIT_BRANCH:-main}"

cd "$(dirname "$0")"

echo "==> Fetching ${REMOTE}/${BRANCH} ..."
git fetch "${REMOTE}" "${BRANCH}"

echo "==> Resetting working tree to ${REMOTE}/${BRANCH} ..."
git reset --hard "${REMOTE}/${BRANCH}"

echo "==> Now at: $(git log -1 --format='%h %s')"
echo "==> Update complete (.venv/ and offline_packages/ preserved)."
