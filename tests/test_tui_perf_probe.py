"""Unit tests for the probe's budgets and paired base-vs-head check (03 §8)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def probe():
    spec = importlib.util.spec_from_file_location(
        "tui_perf_probe", REPO_ROOT / "scripts" / "tui_perf_probe.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["tui_perf_probe"] = module
    spec.loader.exec_module(module)
    return module


def test_default_budgets_match_the_phase1_table(probe) -> None:
    assert probe.DEFAULT_BUDGETS == {
        "import_s": 0.8,
        "import_core_s": 0.3,
        "startup_idle_s": 0.75,
        "startup_stall_max_ms": 300.0,
        "csv_headers_ready_s": 0.1,
        "csv_stall_max_ms": 100.0,
        "entity_change_s": 1.5,
        "entity_change_stall_max_ms": 100.0,
        "key_latency_p95_ms": 100.0,
        "key_latency_max_ms": 150.0,
        "key_stall_max_ms": 100.0,
        "expert_open_s": 0.3,
        "picker_open_s": 0.2,
        "picker_ready_s": 0.5,
        "picker_stall_max_ms": 200.0,
        "log_flood_s": 0.5,
        "log_flood_stall_max_ms": 100.0,
        "entity_filter_key_max_ms": 50.0,
    }
    assert set(probe.DEFAULT_BUDGETS) <= set(probe.SUMMARY_METRICS)


def _report(path: Path, runs: list[dict], dataset: str = "10,000 rows x 50 ent") -> Path:
    path.write_text(json.dumps({"results": [{"dataset": dataset, "runs": runs}]}), encoding="utf-8")
    return path


def test_compare_needs_both_the_factor_and_the_floor(probe, tmp_path: Path) -> None:
    base = probe.merge_reports(
        [
            _report(tmp_path / "b1.json", [{"key_latency_p50_ms": 6.0, "startup_idle_s": 0.40}]),
            _report(tmp_path / "b2.json", [{"key_latency_p50_ms": 6.0, "startup_idle_s": 0.40}]),
        ]
    )
    # 6 -> 9 ms is +50 % but under the 50 ms floor; 0.40 -> 0.60 s is over both.
    head = probe.merge_reports(
        [_report(tmp_path / "h1.json", [{"key_latency_p50_ms": 9.0, "startup_idle_s": 0.60}])]
    )
    result = probe.compare_reports(base, head, budgets={})
    status = {row["metric"]: row["status"] for row in result["rows"]}
    assert status == {"startup_idle_s": "regression", "key_latency_p50_ms": "ok"}
    assert len(result["failures"]) == 1 and "startup_idle_s" in result["failures"][0]


def test_compare_ceiling_catches_an_already_bad_base(probe) -> None:
    runs = [{"log_flood_s": 4.0}]
    result = probe.compare_reports({"d": runs}, {"d": runs}, budgets={"log_flood_s": 0.5})
    assert [row["status"] for row in result["rows"]] == ["over-ceiling"]
    assert result["failures"]


def test_compare_skips_metrics_the_head_does_not_produce(probe) -> None:
    result = probe.compare_reports(
        {"d": [{"picker_tree_ready_s": 3.0}]}, {"d": [{"picker_ready_s": 0.2}]}, budgets={}
    )
    assert [(row["metric"], row.get("base")) for row in result["rows"]] == [("picker_ready_s", None)]
    assert result["failures"] == []


def test_compare_cli_writes_markdown_and_exit_code(probe, tmp_path: Path) -> None:
    base = _report(tmp_path / "base.json", [{"startup_idle_s": 0.4}])
    head = _report(tmp_path / "head.json", [{"startup_idle_s": 0.9}])
    summary = tmp_path / "summary.md"
    out = tmp_path / "compare.json"
    code = probe.main(
        [
            "--compare-base", str(base),
            "--compare-head", str(head),
            "--summary-md", str(summary),
            "--json-out", str(out),
            "--quiet",
        ]
    )
    assert code == 1
    assert "| `startup_idle_s` | 0.4 | 0.9 |" in summary.read_text(encoding="utf-8")
    assert json.loads(out.read_text(encoding="utf-8"))["failures"]


def test_entity_values_prefers_the_app_api(probe) -> None:
    class App:
        entity_choices = ["A", "B"]

    assert probe.entity_values(App()) == ["A", "B"]
