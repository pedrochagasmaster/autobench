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
REMOTE_REF="refs/remotes/$REMOTE/$BRANCH"
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
      requirements.txt|constraints.txt|setup_remote_env.sh|SHA256SUMS|scripts/offline_bundle_checksums.py|offline_packages/*|vendor/*)
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
FETCH_OUTPUT="$(git fetch --prune "$REMOTE" "$BRANCH" 2>&1)" || {
  FETCH_STATUS=$?
  case "$FETCH_OUTPUT" in
    *"cannot lock ref '$REMOTE_REF'"*"unable to resolve reference"*|*"fatal: bad object $REMOTE_REF"*)
      echo "Detected stale remote-tracking ref at $REMOTE_REF; repairing and retrying..." >&2
      git update-ref -d "$REMOTE_REF" 2>/dev/null || true
      rm -f ".git/$REMOTE_REF" ".git/logs/$REMOTE_REF"
      git fetch --prune "$REMOTE" "$BRANCH"
      ;;
    *)
      printf '%s\n' "$FETCH_OUTPUT" >&2
      exit "$FETCH_STATUS"
      ;;
  esac
}

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
echo "==> Re-applying permissions to updated tracked paths ..."
while IFS= read -r _path; do
  [ -n "$_path" ] || continue
  [ -e "$_path" ] && chmod a+r "$_path" 2>/dev/null || true
  _parent=$(dirname "$_path")
  while [ "$_parent" != "." ] && [ "$_parent" != "/" ]; do
    chmod a+rx "$_parent" 2>/dev/null || true
    _parent=$(dirname "$_parent")
  done
done <<EOF
$CHANGED_FILES
EOF
chmod a+rx . run_tool.sh install.sh setup_alias.sh update.sh 2>/dev/null || true
echo "==> Permission evidence: reported"
echo "==> Repo root permissions:"
ls -ld . 2>/dev/null || echo "    unavailable"
echo "==> Entrypoint permissions:"
ls -l run_tool.sh install.sh setup_alias.sh 2>/dev/null || echo "    unavailable"

# Trusted deployment owner provisions shared telemetry parents. Runtime/per-user
# install.sh must not create these directories. Idempotent normalize every sync;
# reject symlink / non-directory targets before any chmod.
#
# Telemetry is best-effort: a provisioning failure (missing mount, read-only
# storage, refused unsafe path) must not abort the node sync. The runtime
# capability gate keeps shared telemetry writes disabled until operators repair
# the layout, so warn loudly and continue.
echo "==> Provisioning shared telemetry directories ..."
TELEMETRY_DIR="${AUTOBENCH_TELEMETRY_DIR:-/ads_storage/autobench/telemetry}"
# shellcheck source=scripts/provision_telemetry_dirs.sh
. "$(cd "$(dirname "$0")" && pwd)/scripts/provision_telemetry_dirs.sh"
if ! provision_shared_telemetry_dirs "$TELEMETRY_DIR"; then
  echo "WARNING: shared telemetry provisioning failed for ${TELEMETRY_DIR};" >&2
  echo "WARNING: shared telemetry writes stay gated off until operators repair the layout." >&2
fi
echo "==> Telemetry permission evidence:"
ls -ld -- "$TELEMETRY_DIR" "$TELEMETRY_DIR/users" 2>/dev/null || echo "    unavailable"

echo "==> Now at: $(git log -1 --format='%h %s')"
echo "==> Install decision: ${INSTALL_DECISION}"
echo "==> Install signal: ${INSTALL_SIGNAL}"
echo "==> Update complete (.venv/ and offline_packages/ preserved)."
