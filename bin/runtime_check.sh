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
  case "$_digest" in
    *[!0-9a-f]*|"") echo "Autobench runtime directory has an invalid digest: $_digest." >&2; return 1 ;;
  esac
  if [ "${#_digest}" -ne 64 ]; then
    echo "Autobench runtime directory has an invalid digest: $_digest." >&2
    return 1
  fi
  if [ ! -x "$_runtime/bin/python" ]; then
    echo "Autobench shared runtime has no executable Python at $_runtime/bin/python." >&2
    return 1
  fi
  if ! "$_runtime/bin/python" - "$_runtime/.complete.json" "$_digest" "$_runtime/bin/python" <<'PY'
import json
import os
import sys

marker, digest, runtime_python = sys.argv[1:]
required_imports = ["pandas", "numpy", "openpyxl", "yaml", "scipy", "textual"]
try:
    with open(marker, encoding="utf-8") as marker_file:
        metadata = json.load(marker_file)
except (OSError, ValueError):
    raise SystemExit(1)
valid = (
    isinstance(metadata, dict)
    and metadata.get("bundle_digest") == digest
    and metadata.get("pip_check") == "passed"
    and metadata.get("required_imports") == required_imports
    and isinstance(metadata.get("approved_python"), str)
    and bool(metadata.get("approved_python"))
    and metadata.get("runtime_python") == os.path.abspath(runtime_python)
    and isinstance(metadata.get("python_version"), str)
    and bool(metadata.get("python_version"))
)
raise SystemExit(0 if valid else 1)
PY
  then
    echo "Autobench shared runtime completion metadata is corrupt: $_runtime/.complete.json." >&2
    return 1
  fi
  printf '%s\n' "$_runtime"
}
