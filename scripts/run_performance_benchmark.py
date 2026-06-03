#!/usr/bin/env python
"""Run a lightweight synthetic performance benchmark for the CLI pipeline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent


def build_synthetic_dataset(
    *,
    entities: int,
    months: int,
    categories_per_dimension: int,
) -> pd.DataFrame:
    """Create deterministic long-format benchmark data."""
    if entities < 7:
        raise ValueError("entities must be at least 7 to satisfy privacy gate scenarios")
    rows: List[Dict[str, Any]] = []
    entity_names = ["Target"] + [f"Peer{i}" for i in range(1, entities)]
    card_types = [f"CARD_{idx}" for idx in range(categories_per_dimension)]
    channels = [f"CHANNEL_{idx}" for idx in range(categories_per_dimension)]

    for entity_idx, entity_name in enumerate(entity_names):
        base = 1000 + entity_idx * 25
        for month_idx in range(months):
            month = f"2024-{month_idx + 1:02d}"
            for card_idx, card_type in enumerate(card_types):
                for channel_idx, channel in enumerate(channels):
                    multiplier = 1 + card_idx + channel_idx
                    total = float(base * multiplier)
                    rows.append(
                        {
                            "issuer_name": entity_name,
                            "year_month": month,
                            "card_type": card_type,
                            "channel": channel,
                            "txn_cnt": total,
                            "total": total,
                            "approved": total * 0.91,
                            "fraud": total * 0.002,
                            "clearing_spend": total * 10.0,
                        }
                    )
    return pd.DataFrame(rows)


def run_benchmark(data_path: Path, output_path: Path) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable,
        str(ROOT / "benchmark.py"),
        "share",
        "--csv",
        str(data_path),
        "--entity",
        "Target",
        "--metric",
        "txn_cnt",
        "--dimensions",
        "card_type",
        "channel",
        "--time-col",
        "year_month",
        "--preset",
        "balanced_default",
        "--no-validate-input",
        "--output",
        str(output_path),
    ]
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a synthetic CLI performance benchmark.")
    parser.add_argument("--entities", type=int, default=12)
    parser.add_argument("--months", type=int, default=6)
    parser.add_argument("--categories-per-dimension", type=int, default=4)
    parser.add_argument("--output-json", type=Path, default=Path("performance_summary.json"))
    parser.add_argument("--work-dir", type=Path, default=None)
    args = parser.parse_args()

    work_dir = args.work_dir or args.output_json.parent
    work_dir.mkdir(parents=True, exist_ok=True)
    data_path = work_dir / "synthetic_performance_input.csv"
    report_path = work_dir / "synthetic_performance_report.xlsx"

    df = build_synthetic_dataset(
        entities=args.entities,
        months=args.months,
        categories_per_dimension=args.categories_per_dimension,
    )
    df.to_csv(data_path, index=False)

    started = time.perf_counter()
    result = run_benchmark(data_path, report_path)
    elapsed = time.perf_counter() - started
    status = "passed" if result.returncode == 0 and report_path.exists() else "failed"

    summary = {
        "status": status,
        "entities": args.entities,
        "months": args.months,
        "categories_per_dimension": args.categories_per_dimension,
        "records": int(len(df)),
        "elapsed_seconds": round(elapsed, 6),
        "returncode": result.returncode,
        "report_path": str(report_path),
        "solver_stats": {},
        "stdout_tail": result.stdout[-2000:],
        "stderr_tail": result.stderr[-2000:],
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 0 if status == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
