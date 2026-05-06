#!/usr/bin/env python
"""Run the full CLI sweep and produce a structured results report."""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

TIMEOUT = 120


def parse_command_file(path: Path) -> List[str]:
    commands: List[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("REM"):
            continue
        commands.append(line)
    return commands


def run_command(command: str, cwd: Path) -> Dict:
    if command.startswith("py "):
        cmd_list = [sys.executable] + shlex.split(command[3:])
    else:
        cmd_list = shlex.split(command)

    start = time.time()
    try:
        result = subprocess.run(
            cmd_list,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=TIMEOUT,
        )
        elapsed = time.time() - start
        return {
            "returncode": result.returncode,
            "elapsed": round(elapsed, 2),
            "stdout_tail": result.stdout[-500:] if result.stdout else "",
            "stderr_tail": result.stderr[-500:] if result.stderr else "",
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "elapsed": TIMEOUT,
            "stdout_tail": "",
            "stderr_tail": "TIMEOUT",
        }
    except Exception as exc:
        return {
            "returncode": -2,
            "elapsed": time.time() - start,
            "stdout_tail": "",
            "stderr_tail": str(exc),
        }


def infer_output_path(command: str) -> str | None:
    parts = shlex.split(command)
    for i, p in enumerate(parts):
        if p == "--output" and i + 1 < len(parts):
            return parts[i + 1]
    return None


def check_output_files(command: str) -> Dict[str, bool]:
    output = infer_output_path(command)
    checks: Dict[str, bool] = {}
    if not output:
        return checks
    p = Path(output)
    checks["analysis_xlsx_exists"] = p.exists()
    pub = p.with_name(f"{p.stem}_publication{p.suffix}")
    checks["publication_xlsx_exists"] = pub.exists()
    bal = p.with_name(f"{p.stem}_balanced.csv")
    checks["balanced_csv_exists"] = bal.exists()
    audit = p.with_name(f"{p.stem}_audit.log")
    checks["audit_log_exists"] = audit.exists()
    return checks


def main() -> None:
    root = Path(__file__).parent.parent
    sweep_dir = root / "test_sweeps"
    if not sweep_dir.exists():
        print("ERROR: test_sweeps/ not found. Run generate_cli_sweep.py first.")
        sys.exit(1)

    categories = [
        ("config", sweep_dir / "config" / "commands.ps1"),
        ("share", sweep_dir / "share" / "commands.ps1"),
        ("rate", sweep_dir / "rate" / "commands.ps1"),
    ]

    all_results: List[Dict] = []
    summary: Dict[str, Dict[str, int]] = {}
    grand_total = 0
    grand_pass = 0
    grand_fail = 0
    grand_skip = 0

    for cat_name, cmd_file in categories:
        if not cmd_file.exists():
            print(f"[SKIP] {cat_name}: {cmd_file} not found")
            continue

        commands = parse_command_file(cmd_file)
        cat_pass = 0
        cat_fail = 0
        cat_skip = 0

        print(f"\n{'='*80}")
        print(f"  Running {cat_name} sweep: {len(commands)} commands")
        print(f"{'='*80}")

        for idx, cmd in enumerate(commands, 1):
            is_accuracy_first = "--preset low_distortion" in cmd or "--preset minimal_distortion" in cmd
            needs_ack = is_accuracy_first and "--acknowledge-accuracy-first" not in cmd

            result = run_command(cmd, root)
            output_checks = check_output_files(cmd)

            if needs_ack and result["returncode"] != 0:
                status = "EXPECTED_BLOCK"
                cat_skip += 1
            elif result["returncode"] == 0:
                status = "PASS"
                cat_pass += 1
            else:
                status = "FAIL"
                cat_fail += 1

            record = {
                "category": cat_name,
                "index": idx,
                "command": cmd,
                "status": status,
                **result,
                **output_checks,
            }
            all_results.append(record)

            marker = "✅" if status == "PASS" else ("⏭️" if status == "EXPECTED_BLOCK" else "❌")
            if idx % 25 == 0 or status == "FAIL":
                print(f"  {marker} [{idx}/{len(commands)}] rc={result['returncode']} ({result['elapsed']}s) {status}")
                if status == "FAIL":
                    tail = result["stderr_tail"] or result["stdout_tail"]
                    if tail:
                        print(f"       {tail[:200]}")

        summary[cat_name] = {"pass": cat_pass, "fail": cat_fail, "skip": cat_skip, "total": len(commands)}
        grand_total += len(commands)
        grand_pass += cat_pass
        grand_fail += cat_fail
        grand_skip += cat_skip

        print(f"\n  {cat_name}: {cat_pass} passed, {cat_fail} failed, {cat_skip} expected-block out of {len(commands)}")

    results_file = sweep_dir / "sweep_results.jsonl"
    with results_file.open("w", encoding="utf-8") as f:
        for r in all_results:
            f.write(json.dumps(r, default=str) + "\n")

    summary_file = sweep_dir / "sweep_summary.json"
    with summary_file.open("w", encoding="utf-8") as f:
        json.dump({
            "grand_total": grand_total,
            "grand_pass": grand_pass,
            "grand_fail": grand_fail,
            "grand_skip": grand_skip,
            "categories": summary,
        }, f, indent=2)

    print(f"\n{'='*80}")
    print(f"  SWEEP COMPLETE")
    print(f"{'='*80}")
    print(f"  Total: {grand_total}")
    print(f"  Passed: {grand_pass}")
    print(f"  Failed: {grand_fail}")
    print(f"  Expected Block: {grand_skip}")
    print(f"  Results: {results_file}")
    print(f"  Summary: {summary_file}")


if __name__ == "__main__":
    main()
