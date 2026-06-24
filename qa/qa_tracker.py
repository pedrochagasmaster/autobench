#!/usr/bin/env python
"""Canonical QA feature-tracking store + spreadsheet builder.

Single source of truth:
  qa/features.jsonl        -> machine-readable record store (one JSON object per line)
  qa/feature_tracking.csv  -> canonical human spreadsheet (regenerated from the store)

Subagents drop per-area partials into qa/specs/<area>.jsonl. `merge` folds those
partials into features.jsonl (dedup by id; existing status fields are preserved so
test/fix/retest progress is never clobbered by a re-merge) and rebuilds the CSV.

Usage:
  py qa/qa_tracker.py merge          # merge qa/specs/*.jsonl -> features.jsonl -> csv
  py qa/qa_tracker.py build          # rebuild csv from features.jsonl
  py qa/qa_tracker.py stats          # print status counts
  py qa/qa_tracker.py set <id> field=value [field=value ...]
  py qa/qa_tracker.py get <id>
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

QA_DIR = Path(__file__).resolve().parent
STORE = QA_DIR / "features.jsonl"
CSV_OUT = QA_DIR / "feature_tracking.csv"
SPECS_DIR = QA_DIR / "specs"

# Canonical column order for the spreadsheet.
FIELDS = [
    "id",
    "area",
    "feature",
    "user_story",
    "expected_behavior",
    "test_steps",
    "spec_status",      # Specified
    "test_status",      # Not Tested | Pass | Fail | Blocked
    "test_result",      # short outcome note
    "error_details",    # full error / discrepancy
    "severity",         # Critical | High | Medium | Low | (blank)
    "fix_status",       # N/A | Pending | Fixed | Won't Fix
    "fix_details",      # what was changed
    "retest_status",    # Not Retested | Pass | Fail
    "notes",
]

DEFAULTS = {
    "spec_status": "Specified",
    "test_status": "Not Tested",
    "test_result": "",
    "error_details": "",
    "severity": "",
    "fix_status": "",
    "fix_details": "",
    "retest_status": "",
    "notes": "",
}


def _normalize(rec: dict) -> dict:
    out = {f: "" for f in FIELDS}
    out.update(DEFAULTS)
    for k, v in rec.items():
        if k in out:
            out[k] = "" if v is None else str(v)
    return out


def load_store() -> "dict[str, dict]":
    records: dict[str, dict] = {}
    if STORE.exists():
        for line in STORE.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            records[rec["id"]] = _normalize(rec)
    return records


def save_store(records: "dict[str, dict]") -> None:
    ordered = sorted(records.values(), key=lambda r: r["id"])
    with STORE.open("w", encoding="utf-8") as fh:
        for rec in ordered:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


def build_csv(records: "dict[str, dict]") -> None:
    ordered = sorted(records.values(), key=lambda r: r["id"])
    with CSV_OUT.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDS)
        writer.writeheader()
        for rec in ordered:
            writer.writerow({f: rec.get(f, "") for f in FIELDS})


# Status fields that must NOT be overwritten by a spec re-merge.
PROGRESS_FIELDS = {
    "test_status", "test_result", "error_details", "severity",
    "fix_status", "fix_details", "retest_status",
}


def merge() -> None:
    records = load_store()
    partials = sorted(SPECS_DIR.glob("*.jsonl"))
    added, updated = 0, 0
    for p in partials:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"  [skip] {p.name}: bad json line: {e}")
                continue
            rid = rec.get("id")
            if not rid:
                print(f"  [skip] {p.name}: record missing id")
                continue
            norm = _normalize(rec)
            if rid in records:
                existing = records[rid]
                for f in PROGRESS_FIELDS:
                    norm[f] = existing.get(f, norm[f])
                records[rid] = norm
                updated += 1
            else:
                records[rid] = norm
                added += 1
    save_store(records)
    build_csv(records)
    print(f"merged {len(partials)} partial file(s): {added} added, {updated} updated, {len(records)} total")


def stats() -> None:
    records = load_store()
    by_test: dict[str, int] = {}
    by_area: dict[str, int] = {}
    for rec in records.values():
        by_test[rec["test_status"]] = by_test.get(rec["test_status"], 0) + 1
        by_area[rec["area"]] = by_area.get(rec["area"], 0) + 1
    print(f"total features: {len(records)}")
    print("by area:")
    for k in sorted(by_area):
        print(f"  {k:18s} {by_area[k]}")
    print("by test_status:")
    for k in sorted(by_test):
        print(f"  {k:18s} {by_test[k]}")


def set_fields(args: "list[str]") -> None:
    if not args:
        print("usage: set <id> field=value [...]")
        sys.exit(2)
    rid, assignments = args[0], args[1:]
    records = load_store()
    if rid not in records:
        print(f"error: id not found: {rid}")
        sys.exit(1)
    for a in assignments:
        if "=" not in a:
            print(f"skip malformed assignment: {a}")
            continue
        key, val = a.split("=", 1)
        key = key.strip()
        if key not in FIELDS:
            print(f"skip unknown field: {key}")
            continue
        records[rid][key] = val
    save_store(records)
    build_csv(records)
    print(f"updated {rid}")


def get(rid: str) -> None:
    records = load_store()
    if rid not in records:
        print(f"error: id not found: {rid}")
        sys.exit(1)
    print(json.dumps(records[rid], indent=2, ensure_ascii=False))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 0
    cmd = sys.argv[1]
    if cmd == "merge":
        merge()
    elif cmd == "build":
        build_csv(load_store())
        print(f"rebuilt {CSV_OUT}")
    elif cmd == "stats":
        stats()
    elif cmd == "set":
        set_fields(sys.argv[2:])
    elif cmd == "get":
        get(sys.argv[2])
    else:
        print(f"unknown command: {cmd}")
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
