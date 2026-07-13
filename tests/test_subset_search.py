from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Optional

import pandas as pd

import core.subset_search as subset_search
from core.subset_search import _solve_trial


@dataclass
class _SolverResult:
    success: bool
    weights: Optional[Dict[str, float]]
    stats: Dict[str, Any]


class _Solver:
    def __init__(self, result: _SolverResult) -> None:
        self.result = result
        self.calls = 0

    def solve(self, _request: object) -> _SolverResult:
        self.calls += 1
        return self.result


def _analyzer(categories: list[dict[str, Any]], solver: _Solver) -> SimpleNamespace:
    analyzer = SimpleNamespace(
        lp_solver=solver,
        last_lp_stats={},
        trigger_subset_on_slack=False,
        max_cap_slack=0.1,
        subset_search_results=[],
    )
    analyzer._build_categories = lambda _df, _metric, _dims: (
        categories,
        {"P1": 1.0},
        ["P1"],
    )
    analyzer._is_slack_excess = lambda slack: bool(slack and slack > 0.1)
    return analyzer


def test_solve_trial_returns_successful_weights_and_stats(monkeypatch) -> None:
    monkeypatch.setattr(subset_search, "build_lp_request", lambda *_a, **_kw: object())
    solver = _Solver(
        _SolverResult(
            success=True,
            weights={"P1": 1.0},
            stats={"sum_slack": 0.0, "max_slack": 0.0, "method": "LP"},
        )
    )
    analyzer = _analyzer([{"dimension": "d1"}], solver)

    trial = _solve_trial(
        analyzer, pd.DataFrame({"metric": [1]}), "metric", ["d1"], 25.0, ["P1"], 1
    )

    assert trial.categories == [{"dimension": "d1"}]
    assert trial.weights == {"P1": 1.0}
    assert trial.sum_slack == 0.0
    assert analyzer.last_lp_stats == {
        "sum_slack": 0.0,
        "max_slack": 0.0,
        "method": "LP",
    }
    row = analyzer.subset_search_results[0]
    assert row["Success"] is True
    assert row["Max_Slack"] == 0.0
    assert row["Sum_Slack"] == 0.0
    assert row["Note"] == ""


def test_solve_trial_rejects_excess_slack(monkeypatch) -> None:
    monkeypatch.setattr(subset_search, "build_lp_request", lambda *_a, **_kw: object())
    solver = _Solver(
        _SolverResult(
            success=True,
            weights={"P1": 1.0},
            stats={"sum_slack": 0.2, "max_slack": 0.2, "method": "LP"},
        )
    )
    analyzer = _analyzer([{"dimension": "d1"}], solver)
    analyzer.trigger_subset_on_slack = True

    trial = _solve_trial(
        analyzer, pd.DataFrame({"metric": [1]}), "metric", ["d1"], 25.0, ["P1"], 1
    )

    assert trial.weights is None
    assert trial.sum_slack is None
    row = analyzer.subset_search_results[0]
    assert row["Success"] is False
    assert row["Max_Slack"] is None
    assert row["Sum_Slack"] is None
    assert row["Method"] == "LP"
    assert row["Note"] == "Rejected due to slack 0.200000 > 0.100000"


def test_solve_trial_excess_slack_without_weights_keeps_stats(monkeypatch) -> None:
    monkeypatch.setattr(subset_search, "build_lp_request", lambda *_a, **_kw: object())
    stats = {"sum_slack": 0.2, "max_slack": 0.2, "method": "LP"}
    solver = _Solver(_SolverResult(success=True, weights=None, stats=stats))
    analyzer = _analyzer([{"dimension": "d1"}], solver)
    analyzer.trigger_subset_on_slack = True

    trial = _solve_trial(
        analyzer, pd.DataFrame({"metric": [1]}), "metric", ["d1"], 25.0, ["P1"], 1
    )

    assert trial.weights is None
    assert trial.sum_slack is None
    assert analyzer.last_lp_stats == stats
    row = analyzer.subset_search_results[0]
    assert row["Success"] is False
    assert row["Note"] == ""
    assert row["Max_Slack"] == 0.2
    assert row["Sum_Slack"] == 0.2
    assert row["Method"] == "LP"


def test_solve_trial_records_solver_failure(monkeypatch) -> None:
    monkeypatch.setattr(subset_search, "build_lp_request", lambda *_a, **_kw: object())
    solver = _Solver(_SolverResult(success=False, weights=None, stats={}))
    analyzer = _analyzer([{"dimension": "d1"}], solver)

    trial = _solve_trial(
        analyzer, pd.DataFrame({"metric": [1]}), "metric", ["d1"], 25.0, ["P1"], 1
    )

    assert trial.categories == [{"dimension": "d1"}]
    assert trial.weights is None
    assert trial.sum_slack is None
    assert analyzer.last_lp_stats == {}
    row = analyzer.subset_search_results[0]
    assert row == {
        "Attempt": 1,
        "Dimensions": ["d1"],
        "Count": 1,
        "Success": False,
        "Max_Slack": None,
        "Sum_Slack": None,
        "Method": None,
        "Note": "",
    }


def test_solve_trial_skips_solver_without_categories(monkeypatch) -> None:
    monkeypatch.setattr(subset_search, "build_lp_request", lambda *_a, **_kw: object())
    solver = _Solver(_SolverResult(True, {"P1": 1.0}, {}))
    analyzer = _analyzer([], solver)

    trial = _solve_trial(
        analyzer, pd.DataFrame({"metric": [1]}), "metric", ["d1"], 25.0, ["P1"], 1
    )

    assert trial.categories == []
    assert trial.weights is None
    assert trial.sum_slack is None
    assert solver.calls == 0
    assert analyzer.subset_search_results == []
