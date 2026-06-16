"""Single subprocess gateway for the Dispatch TUI."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
from pathlib import Path


async def run_exec(*argv: str, timeout: float | None = None) -> tuple[int, str, str]:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.terminate()
        await proc.wait()
        raise
    return proc.returncode or 0, stdout.decode(errors="replace"), stderr.decode(errors="replace")


async def launch_runner(job_dir: Path) -> int:
    proc = await asyncio.create_subprocess_exec(
        "nohup",
        "setsid",
        sys.executable,
        "-m",
        "dispatch.runner",
        "--job-dir",
        str(job_dir),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    return proc.pid


def cancel_process_group(pid: int) -> None:
    os.killpg(pid, signal.SIGTERM)


def run_interactive(*argv: str) -> int:
    with subprocess.Popen(argv) as proc:
        return proc.wait()
