#!/usr/bin/env bash
# Cursor Cloud / environment.json install hook.
# Idempotent: safe to run on every agent startup.
set -euo pipefail

printf '>>> [cloud_install] start\n'

# Do not symlink into /usr/local/bin — cloud agents run unprivileged and that
# path is root-owned. Most images already ship `py`; otherwise use ~/.local/bin.
if command -v py >/dev/null 2>&1; then
  printf '>>> py launcher: %s\n' "$(command -v py)"
else
  python3_bin="$(command -v python3)"
  mkdir -p "${HOME}/.local/bin"
  ln -sf "${python3_bin}" "${HOME}/.local/bin/py"
  export PATH="${HOME}/.local/bin:${PATH}"
  printf '>>> py launcher: %s (ensure ~/.local/bin is on PATH)\n' "${HOME}/.local/bin/py"
fi

pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt

printf '<<< [cloud_install] complete\n'
