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
# Overridable via environment (EDGE_DEPLOY_* takes precedence; the AUTOBENCH_*
# names remain as fallback aliases for one release, per ADR-0004):
#   EDGE_DEPLOY_REMOTE / AUTOBENCH_GIT_REMOTE (default: bitbucket)
#   EDGE_DEPLOY_BRANCH / AUTOBENCH_GIT_BRANCH (default: main)
#
# Optionally pass a target ref (branch, tag, or exact SHA) as the first argument
# (defaults to <remote>/<branch>); the install-decision diff and the working-tree
# reset are computed against that resolved target.

set -euo pipefail

REMOTE="${EDGE_DEPLOY_REMOTE:-${AUTOBENCH_GIT_REMOTE:-bitbucket}}"
BRANCH="${EDGE_DEPLOY_BRANCH:-${AUTOBENCH_GIT_BRANCH:-main}}"
TARGET_REF="${1:-$REMOTE/$BRANCH}"

cd "$(dirname "$0")"

CURRENT_HEAD="$(git rev-parse HEAD 2>/dev/null || true)"

classify_install_decision() {
  _changed_files=$1
  _required_hits=""
  _recommended_hits=""

  while IFS= read -r _path; do
    [ -n "$_path" ] || continue
    case "$_path" in
      requirements.txt|requirements-dev.txt|constraints.txt|setup_remote_env.sh|SHA256SUMS|scripts/offline_bundle_checksums.py|offline_packages/*|vendor/*)
        _required_hits="${_required_hits}${_required_hits:+, }$_path"
        ;;
      VERSION|install.sh)
        _recommended_hits="${_recommended_hits}${_recommended_hits:+, }$_path"
        ;;
    esac
  done <<EOF
$_changed_files
EOF

  if [ -n "$_required_hits" ]; then
    INSTALL_DECISION="install required"
    INSTALL_SIGNAL="dependency inputs changed: $_required_hits"
  elif [ -n "$_recommended_hits" ]; then
    INSTALL_DECISION="install recommended"
    INSTALL_SIGNAL="runtime or launcher inputs changed: $_recommended_hits"
  else
    INSTALL_DECISION="install not required"
    INSTALL_SIGNAL="dependency inputs unchanged"
  fi
}

echo "==> Fetching ${REMOTE}/${BRANCH} ..."
git fetch "${REMOTE}" "${BRANCH}"

if [ -n "$CURRENT_HEAD" ] && git rev-parse --verify "${TARGET_REF}" >/dev/null 2>&1; then
  CHANGED_FILES="$(git diff --name-only "$CURRENT_HEAD" "${TARGET_REF}" 2>/dev/null || true)"
  classify_install_decision "$CHANGED_FILES"
else
  INSTALL_DECISION="install recommended"
  INSTALL_SIGNAL="could not compare the current deployment to ${TARGET_REF}"
fi

echo "==> Resetting working tree to ${TARGET_REF} ..."
git reset --hard "${TARGET_REF}"

# git reset rewrites files with umask-default permissions, which drops the
# shared read/execute access other analysts need. Re-apply it every sync so
# the shared deployment stays usable by all users (dirs +rx, files +r,
# executables stay runnable). Run from a writable directory for outputs.
echo "==> Re-applying shared read/execute permissions ..."
chmod -R a+rX . 2>/dev/null || echo "    Note: some paths could not be chmod'd (skipped)."
echo "==> Permission evidence: reported"
echo "==> Repo root permissions:"
ls -ld . 2>/dev/null || echo "    unavailable"
echo "==> Entrypoint permissions:"
ls -l run_tool.sh install.sh setup_alias.sh 2>/dev/null || echo "    unavailable"

echo "==> Now at: $(git log -1 --format='%h %s')"
echo "==> Install decision: ${INSTALL_DECISION}"
echo "==> Install signal: ${INSTALL_SIGNAL}"
echo "==> Update complete (.venv/ and offline_packages/ preserved)."
