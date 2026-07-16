"""Diagnostics for obsolete personal-runtime launchers."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping


def stale_personal_runtime_warning(
    *,
    executable: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = os.environ if environ is None else environ
    user = env.get("USER") or env.get("USERNAME") or ""
    data_root = Path(env.get("AUTOBENCH_DATA_ROOT", f"/ads_storage/{user}"))
    personal_runtime = data_root / ".autobench" / "venv"
    try:
        running = (Path(sys.executable) if executable is None else executable).resolve()
        running.relative_to(personal_runtime.resolve())
    except (OSError, RuntimeError, ValueError):
        return ""
    return (
        "Autobench is running from an unsupported personal virtual environment. "
        "Run /ads_storage/autobench/onboard.sh to repair your launchers."
    )


def warn_if_personal_runtime() -> None:
    warning = stale_personal_runtime_warning()
    if warning:
        print(warning, file=sys.stderr)
