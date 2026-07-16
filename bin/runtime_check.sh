# Shared validation of the active Autobench runtime. POSIX sh; sourced by the
# shared launchers and onboard.sh.
#
# autobench_active_runtime <root-dir>
#   Prints the physical path of the validated active runtime on stdout.
autobench_active_runtime() {
  _root=$1
  _current="$_root/.venv/current"
  if [ ! -L "$_current" ]; then
    echo "Autobench shared runtime is not active at $_current." >&2
    echo "Ask the Release Operator to run $_root/install.sh." >&2
    return 1
  fi
  _runtime=$(readlink -f "$_current" 2>/dev/null || true)
  if [ -z "$_runtime" ] || [ ! -d "$_runtime" ] || [ ! -f "$_runtime/.complete.json" ]; then
    echo "Autobench shared runtime is invalid at $_current." >&2
    echo "Ask the Release Operator to reactivate a completed runtime." >&2
    return 1
  fi
  case "$_runtime" in
    "$_root/.venv/releases/"*) ;;
    *)
      echo "Autobench shared runtime resolves outside the release root: $_runtime." >&2
      return 1
      ;;
  esac
  _digest=$(basename "$_runtime")
  if ! grep -Eq '"bundle_digest"[[:space:]]*:[[:space:]]*"'"$_digest"'"' "$_runtime/.complete.json" ||
     ! grep -Eq '"pip_check"[[:space:]]*:[[:space:]]*"passed"' "$_runtime/.complete.json"; then
    echo "Autobench shared runtime completion metadata is corrupt: $_runtime/.complete.json." >&2
    return 1
  fi
  if [ ! -x "$_runtime/bin/python" ]; then
    echo "Autobench shared runtime has no executable Python at $_runtime/bin/python." >&2
    return 1
  fi
  printf '%s\n' "$_runtime"
}
