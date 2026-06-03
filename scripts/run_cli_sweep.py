"""Run a previously-generated CLI sweep against benchmark.py and verify outputs.

Usage:
    py scripts/run_cli_sweep.py --sweep-dir test_sweeps --results-json test_sweeps/results.json --workers 6

The runner reuses ``GateTestRunner.verify_case`` so per-case expectations match the
gate test exactly. Results are written to a JSON file so they can be analysed
without re-running the sweep.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import logging
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Local import of the gate runner so verification logic stays in one place.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from perform_gate_test import GateTestRunner  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("sweep")


def _load_cases(sweep_dir: Path) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for section in ["share", "rate", "config"]:
        path = sweep_dir / section / "cases.jsonl"
        if not path.exists():
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    cases.append(json.loads(line))
    return cases


def _execute_command(command: str, root_dir: Path) -> Dict[str, Any]:
    if command.startswith("py "):
        cmd_list = [sys.executable] + shlex.split(command[3:])
    else:
        cmd_list = shlex.split(command)
    start = time.time()
    proc = subprocess.run(
        cmd_list,
        cwd=root_dir,
        capture_output=True,
        text=True,
        timeout=600,
    )
    duration = time.time() - start
    return {
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "duration_s": round(duration, 3),
    }


def _classify(result: Dict[str, Any]) -> str:
    if result["status"] == "pass":
        return "pass"
    if result["status"] == "error":
        return "error"
    return "fail"


def _process_case(case: Dict[str, Any], runner: GateTestRunner) -> Dict[str, Any]:
    case_id = case["id"]
    command = case["command"]
    expectations = case.get("expectations", [])
    record: Dict[str, Any] = {
        "id": case_id,
        "command": command,
        "expectations": expectations,
        "status": "error",
        "execution": None,
        "verification_failures": [],
        "stderr_excerpt": "",
        "traceback": False,
    }

    try:
        execution = _execute_command(command, runner.root_dir)
    except subprocess.TimeoutExpired as exc:
        record["execution"] = {
            "returncode": None,
            "duration_s": exc.timeout,
            "stdout": "",
            "stderr": str(exc),
        }
        record["status"] = "error"
        record["stderr_excerpt"] = "TIMEOUT"
        return record

    record["execution"] = {
        "returncode": execution["returncode"],
        "duration_s": execution["duration_s"],
    }

    has_traceback = "Traceback (most recent call last)" in execution["stderr"]
    record["traceback"] = has_traceback

    if has_traceback or execution["returncode"] != 0:
        record["status"] = "error"
        # Capture trailing stderr lines so the analysis script can group failures.
        stderr_tail = "\n".join(execution["stderr"].splitlines()[-20:])
        record["stderr_excerpt"] = stderr_tail
        return record

    failures = runner.verify_case(case)
    if failures:
        record["status"] = "fail"
        record["verification_failures"] = list(failures)
        return record

    record["status"] = "pass"
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a CLI sweep and verify outputs")
    parser.add_argument("--sweep-dir", default="test_sweeps", help="Directory with generated cases")
    parser.add_argument("--results-json", default="test_sweeps/results.json", help="Where to write per-case results")
    parser.add_argument("--workers", type=int, default=6, help="Parallel worker count")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit on number of cases (0 = no limit)")
    args = parser.parse_args()

    sweep_dir = Path(args.sweep_dir).resolve()
    if not sweep_dir.exists():
        logger.error("Sweep directory does not exist: %s", sweep_dir)
        return 1

    runner = GateTestRunner(output_dir=str(sweep_dir))
    # Ensure output sub-directories exist so case commands can write workbooks.
    for section in ("share", "rate", "config"):
        (sweep_dir / "outputs" / section).mkdir(parents=True, exist_ok=True)
    # ``benchmark config generate`` refuses to overwrite an existing target file.
    # Remove any previously-generated artefact so the sweep is idempotent.
    generated_template = sweep_dir / "config" / "generated_template.yaml"
    if generated_template.exists():
        generated_template.unlink()
    cases = _load_cases(sweep_dir)
    if args.limit and args.limit > 0:
        cases = cases[: args.limit]
    logger.info("Loaded %d cases from %s", len(cases), sweep_dir)

    results: List[Dict[str, Any]] = []
    counts = {"pass": 0, "fail": 0, "error": 0}

    started_at = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        future_to_case = {pool.submit(_process_case, case, runner): case for case in cases}
        completed = 0
        for future in concurrent.futures.as_completed(future_to_case):
            record = future.result()
            classification = _classify(record)
            counts[classification] += 1
            results.append(record)
            completed += 1
            if completed % 25 == 0 or completed == len(cases):
                logger.info(
                    "Progress: %d/%d (pass=%d fail=%d error=%d)",
                    completed,
                    len(cases),
                    counts["pass"],
                    counts["fail"],
                    counts["error"],
                )
    duration = time.time() - started_at

    results.sort(key=lambda r: r["id"])
    summary = {
        "sweep_dir": str(sweep_dir),
        "case_count": len(cases),
        "duration_s": round(duration, 2),
        "counts": counts,
        "results": results,
    }

    Path(args.results_json).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    logger.info(
        "Sweep complete in %.1fs: pass=%d fail=%d error=%d",
        duration,
        counts["pass"],
        counts["fail"],
        counts["error"],
    )
    if counts["fail"] or counts["error"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
