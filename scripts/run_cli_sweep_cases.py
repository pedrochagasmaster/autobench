#!/usr/bin/env python
"""Execute generated CLI sweep cases and save per-case logs plus summaries."""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from scripts.perform_gate_test import GateTestRunner


def detect_output_path(stdout_text: str) -> str | None:
    for line in stdout_text.splitlines():
        if line.startswith("Report:"):
            report_value = line.split(":", 1)[1].strip()
            if not report_value:
                continue
            first_path = report_value.split(",", 1)[0].strip()
            if first_path:
                return first_path
    return None


def load_cases(case_dir: Path) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    for jsonl_path in sorted(case_dir.glob("*/cases.jsonl")):
        with open(jsonl_path, "r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                case = json.loads(line)
                case["suite"] = jsonl_path.parent.name
                cases.append(case)
    return cases


def run_case(
    case: Dict[str, Any],
    *,
    workspace_root: Path,
    gate_runner: GateTestRunner,
    logs_dir: Path,
    timeout_sec: int,
) -> Dict[str, Any]:
    command = case["command"]
    argv = [sys.executable] + shlex.split(command[3:]) if command.startswith("py ") else shlex.split(command)

    started = time.time()
    stdout_path = logs_dir / f"{case['id']}.stdout.log"
    stderr_path = logs_dir / f"{case['id']}.stderr.log"
    record: Dict[str, Any] = {
        "id": case["id"],
        "suite": case.get("suite"),
        "command": command,
        "status": "unknown",
        "duration_seconds": 0.0,
        "returncode": None,
        "verification_failures": [],
    }

    try:
        proc = subprocess.run(
            argv,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
        )
        stdout_path.write_text(proc.stdout, encoding="utf-8")
        stderr_path.write_text(proc.stderr, encoding="utf-8")
        record["returncode"] = proc.returncode
        record["duration_seconds"] = round(time.time() - started, 3)
        if proc.returncode == 0:
            verify_case_payload = {
                "id": case["id"],
                "params": dict(case.get("params", {})),
                "expectations": list(case.get("expectations", [])),
            }
            if "output" not in verify_case_payload["params"]:
                detected_output = detect_output_path(proc.stdout)
                if detected_output:
                    verify_case_payload["params"]["output"] = detected_output
            verification_failures = gate_runner.verify_case(verify_case_payload)
            record["verification_failures"] = verification_failures
            record["status"] = "passed" if not verification_failures else "verification_failed"
        else:
            record["status"] = "failed"
    except subprocess.TimeoutExpired as exc:
        stdout_path.write_text(exc.stdout or "", encoding="utf-8")
        stderr_path.write_text(exc.stderr or "", encoding="utf-8")
        record["duration_seconds"] = round(time.time() - started, 3)
        record["status"] = "timed_out"
    except Exception as exc:  # pragma: no cover - defensive CLI runner
        stderr_path.write_text(f"{type(exc).__name__}: {exc}\n", encoding="utf-8")
        record["duration_seconds"] = round(time.time() - started, 3)
        record["status"] = "runner_error"
    return record


def build_summary(records: List[Dict[str, Any]], *, elapsed_seconds: float) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "total_cases": len(records),
        "passed": sum(1 for record in records if record["status"] == "passed"),
        "failed": sum(1 for record in records if record["status"] == "failed"),
        "verification_failed": sum(1 for record in records if record["status"] == "verification_failed"),
        "timed_out": sum(1 for record in records if record["status"] == "timed_out"),
        "runner_error": sum(1 for record in records if record["status"] == "runner_error"),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "suites": {},
    }
    for suite_name in sorted({record["suite"] for record in records}):
        suite_records = [record for record in records if record["suite"] == suite_name]
        summary["suites"][suite_name] = {
            "total": len(suite_records),
            "passed": sum(1 for record in suite_records if record["status"] == "passed"),
            "failed": sum(1 for record in suite_records if record["status"] == "failed"),
            "verification_failed": sum(1 for record in suite_records if record["status"] == "verification_failed"),
            "timed_out": sum(1 for record in suite_records if record["status"] == "timed_out"),
            "runner_error": sum(1 for record in suite_records if record["status"] == "runner_error"),
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run generated CLI sweep cases and save logs/results.")
    parser.add_argument("--case-dir", required=True, help="Directory containing share/rate/config cases.jsonl files")
    parser.add_argument("--results-dir", required=True, help="Directory to write JSON summaries and per-case logs")
    parser.add_argument("--timeout-sec", type=int, default=300, help="Per-case timeout in seconds")
    parser.add_argument("--progress-every", type=int, default=25, help="Print progress every N cases")
    args = parser.parse_args()

    workspace_root = Path.cwd()
    case_dir = Path(args.case_dir)
    results_dir = Path(args.results_dir)
    logs_dir = results_dir / "case_logs"
    results_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    cases = load_cases(case_dir)
    gate_runner = GateTestRunner(output_dir=str(case_dir))
    started = time.time()
    records: List[Dict[str, Any]] = []

    for idx, case in enumerate(cases, start=1):
        record = run_case(
            case,
            workspace_root=workspace_root,
            gate_runner=gate_runner,
            logs_dir=logs_dir,
            timeout_sec=args.timeout_sec,
        )
        records.append(record)
        if idx % args.progress_every == 0 or idx == len(cases):
            print(f"[{idx}/{len(cases)}] {case['id']} -> {record['status']}")

    summary = build_summary(records, elapsed_seconds=time.time() - started)
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    with open(results_dir / "results.jsonl", "w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")

    return 0 if summary["passed"] == summary["total_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
