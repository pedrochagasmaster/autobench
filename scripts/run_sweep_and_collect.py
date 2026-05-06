#!/usr/bin/env python
"""Run all sweep cases, collect results, and write a summary JSON."""

import json
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).parent.parent
SWEEP_DIR = ROOT / "test_sweeps"
RESULTS_FILE = SWEEP_DIR / "sweep_results.json"


def load_cases() -> List[Dict[str, Any]]:
    cases = []
    for section in ("share", "rate", "config"):
        jsonl = SWEEP_DIR / section / "cases.jsonl"
        if not jsonl.exists():
            continue
        with open(jsonl, "r") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    case = json.loads(line)
                    case["_section"] = section
                    cases.append(case)
    return cases


def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    command = case["command"]
    case_id = case["id"]

    if command.startswith("py "):
        cmd_list = [sys.executable] + shlex.split(command[3:])
    else:
        cmd_list = shlex.split(command)

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd_list,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=120,
        )
        duration = time.time() - t0

        has_traceback = "Traceback (most recent call last)" in proc.stderr
        status = "pass"
        error_detail = None
        if proc.returncode != 0:
            status = "error"
            error_detail = proc.stderr[-500:] if proc.stderr else "non-zero exit"
        elif has_traceback:
            status = "error"
            error_detail = proc.stderr[-500:]

        return {
            "id": case_id,
            "section": case.get("_section", ""),
            "status": status,
            "returncode": proc.returncode,
            "duration_s": round(duration, 2),
            "error": error_detail,
        }
    except subprocess.TimeoutExpired:
        return {
            "id": case_id,
            "section": case.get("_section", ""),
            "status": "timeout",
            "returncode": -1,
            "duration_s": 120.0,
            "error": "timed out after 120s",
        }
    except Exception as exc:
        return {
            "id": case_id,
            "section": case.get("_section", ""),
            "status": "exception",
            "returncode": -1,
            "duration_s": round(time.time() - t0, 2),
            "error": str(exc),
        }


def main() -> None:
    cases = load_cases()
    total = len(cases)
    print(f"Loaded {total} sweep cases")

    results: List[Dict[str, Any]] = []
    counts = {"pass": 0, "error": 0, "timeout": 0, "exception": 0}

    for i, case in enumerate(cases, 1):
        result = run_case(case)
        results.append(result)
        counts[result["status"]] = counts.get(result["status"], 0) + 1

        if i % 50 == 0 or result["status"] != "pass":
            tag = result["status"].upper()
            print(f"[{i}/{total}] {result['id']}: {tag} ({result['duration_s']}s)")

    summary = {
        "total": total,
        "passed": counts["pass"],
        "errors": counts["error"],
        "timeouts": counts.get("timeout", 0),
        "exceptions": counts.get("exception", 0),
        "pass_rate_pct": round(100 * counts["pass"] / total, 2) if total else 0,
    }

    output = {"summary": summary, "results": results}
    with open(RESULTS_FILE, "w") as fh:
        json.dump(output, fh, indent=2)

    print()
    print("=" * 60)
    print(f"SWEEP COMPLETE — {total} cases")
    print(f"  Passed:     {summary['passed']}")
    print(f"  Errors:     {summary['errors']}")
    print(f"  Timeouts:   {summary['timeouts']}")
    print(f"  Exceptions: {summary['exceptions']}")
    print(f"  Pass Rate:  {summary['pass_rate_pct']}%")
    print(f"Results: {RESULTS_FILE}")
    print("=" * 60)

    if summary["errors"] > 0 or summary["timeouts"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
