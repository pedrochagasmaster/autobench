from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_performance_benchmark_generates_summary(tmp_path: Path) -> None:
    output = tmp_path / "perf_summary.json"
    script = ROOT / "scripts" / "run_performance_benchmark.py"

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--entities",
            "7",
            "--months",
            "2",
            "--categories-per-dimension",
            "2",
            "--output-json",
            str(output),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["status"] == "passed"
    assert summary["records"] == 7 * 2 * 2 * 2
    assert summary["elapsed_seconds"] >= 0
    assert "solver_stats" in summary
