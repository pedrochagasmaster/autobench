"""Windows-only regression tests for the PowerShell mock dev environment."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

import pytest


WORKSPACE = Path(__file__).resolve().parents[1]
MOCKS_DIR = WORKSPACE / "mocks"
POWERSHELL = shutil.which("powershell") or shutil.which("pwsh")
CSC = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe")


@pytest.mark.skipif(os.name != "nt", reason="Windows-only PowerShell mock test")
def test_dev_env_ps1_compiles_wrappers_with_detected_python_launcher(
    tmp_path: Path,
) -> None:
    """Mock wrappers should work when python is on PATH but py.exe is not."""
    if POWERSHELL is None:
        pytest.skip("PowerShell is not available")
    if not CSC.exists():
        pytest.skip("csc.exe is not available")

    python_exe = Path(sys.executable).resolve().with_name("python.exe")
    if not python_exe.exists():
        pytest.skip("python.exe is not available alongside the active interpreter")

    temp_mocks = tmp_path / "mocks"
    shutil.copytree(MOCKS_DIR, temp_mocks)

    smtp_guard = socket.socket()
    smtp_guard.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    smtp_guard.bind(("127.0.0.1", 2525))
    smtp_guard.listen(1)

    try:
        temp_dir = tmp_path / "temp"
        temp_dir.mkdir()

        env = os.environ.copy()
        env["PATH"] = str(python_exe.parent)
        env["TEMP"] = str(temp_dir)
        env["TMP"] = str(temp_dir)
        env["DISPATCH_DATA_ROOT"] = str(tmp_path / "data")
        env["DISPATCH_MOCK_STATE_DIR"] = str(tmp_path / "state")
        env["DISPATCH_MOCK_SCENARIO"] = "happy_path"

        dev_env = temp_mocks / "dev-env.ps1"
        wrapper = temp_mocks / "bin" / "impala-shell.exe"
        command = (
            f"& {{ . '{dev_env}'; "
            f"& '{wrapper}' '--output_delimiter=|' '-q' 'SHOW TABLES IN dw;' }}"
        )

        result = subprocess.run(
            [POWERSHELL, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0, result.stderr or result.stdout
        assert "dispatch_result" in result.stdout
    finally:
        smtp_guard.close()
