"""Unit tests for the canonical ordering contract of the analytical pipeline.

Every optimization path must see peers, dimensions, and constraints in one
canonical order so identical input bytes and resolved configuration produce
identical analytical results, regardless of how a caller happened to order its
inputs or how a fresh interpreter hashed its strings.
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

import pandas as pd
import pytest

import core.subset_search as subset_search
from core.canonical_order import canonical_key, canonical_order
from core.category_builder import CategoryBuilder
from core.contracts import SolverRequest
from core.dimensional_analyzer import DimensionalAnalyzer
from core.solver_request_builder import build_heuristic_request, build_lp_request
from core.solvers.lp_solver import LPSolver
from core.subset_search import _most_unbalanced_dimension, search_largest_feasible_subset

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRAMBLED_PEERS = ["P4", "P1", "P6", "P2", "P5", "P3"]
CANONICAL_PEERS = ["P1", "P2", "P3", "P4", "P5", "P6"]


def _peer_frame(peer_order: List[str]) -> pd.DataFrame:
    """Build a two-dimension frame whose rows follow ``peer_order``."""
    volumes = {"P1": 300, "P2": 260, "P3": 200, "P4": 200, "P5": 160, "P6": 120}
    rows = []
    for month in ("2024-01", "2024-02"):
        for card in ("CREDIT", "DEBIT"):
            for channel in ("Online", "POS"):
                for peer in peer_order:
                    rows.append(
                        {
                            "issuer_name": peer,
                            "year_month": month,
                            "card_type": card,
                            "channel": channel,
                            "txn_cnt": volumes[peer],
                        }
                    )
    return pd.DataFrame(rows)


def _builder(*, consistent_weights: bool) -> CategoryBuilder:
    return CategoryBuilder(
        entity_column="issuer_name",
        target_entity=None,
        time_column="year_month",
        consistent_weights=consistent_weights,
    )


def _flat_categories(peers: List[str], volumes: Dict[str, float]) -> List[Dict[str, Any]]:
    return [
        {
            "peer": peer,
            "dimension": "channel",
            "category": "Online",
            "volume": volumes[peer],
            "category_volume": volumes[peer],
            "share_pct": 0.0,
        }
        for peer in peers
    ]


def _lp_settings() -> SimpleNamespace:
    return SimpleNamespace(
        rank_preservation_strength=0.5,
        rank_constraint_mode="all",
        rank_constraint_k=1,
        tolerance=1.0,
        volume_weighted_penalties=False,
        volume_weighting_exponent=1.0,
        lambda_penalty=None,
        max_iterations=1000,
        min_weight=0.01,
        max_weight=10.0,
        protected_entity_caps={},
    )


def test_canonical_key_orders_mixed_types_without_error() -> None:
    assert canonical_order(["b", "a", 10, 2, "10"]) == [10, "10", 2, "a", "b"]
    assert canonical_key("10") == ("10", "str")
    assert canonical_key(10) == ("10", "int")


def test_canonical_order_removes_duplicates() -> None:
    assert canonical_order(["P2", "P1", "P2"]) == ["P1", "P2"]


def test_standard_category_building_returns_canonical_peer_order() -> None:
    builder = _builder(consistent_weights=False)
    _, _, peers = builder.build_categories(
        _peer_frame(SCRAMBLED_PEERS), "txn_cnt", ["card_type", "channel"]
    )
    assert peers == CANONICAL_PEERS


def test_time_aware_category_building_returns_canonical_peer_order() -> None:
    builder = _builder(consistent_weights=True)
    categories, _, peers = builder.build_categories(
        _peer_frame(SCRAMBLED_PEERS), "txn_cnt", ["card_type", "channel"]
    )
    assert peers == CANONICAL_PEERS
    assert any(cat["dimension"].startswith("_TIME_") for cat in categories)


def test_both_category_paths_agree_on_peer_order() -> None:
    frame = _peer_frame(SCRAMBLED_PEERS)
    _, _, standard_peers = _builder(consistent_weights=False).build_categories(
        frame, "txn_cnt", ["card_type", "channel"]
    )
    _, _, time_aware_peers = _builder(consistent_weights=True).build_categories(
        frame, "txn_cnt", ["card_type", "channel"]
    )
    assert standard_peers == time_aware_peers


def test_reversed_row_order_produces_identical_categories() -> None:
    builder = _builder(consistent_weights=True)
    forward = builder.build_categories(
        _peer_frame(CANONICAL_PEERS), "txn_cnt", ["card_type", "channel"]
    )
    reversed_rows = builder.build_categories(
        _peer_frame(list(reversed(CANONICAL_PEERS))), "txn_cnt", ["card_type", "channel"]
    )
    assert forward[0] == reversed_rows[0]
    assert forward[1] == reversed_rows[1]
    assert forward[2] == reversed_rows[2]


def test_equal_volume_peers_receive_stable_rank_order() -> None:
    """Peers holding an identical base share rank by canonical key."""
    volumes = {peer: 100.0 for peer in CANONICAL_PEERS}
    request = build_lp_request(
        _lp_settings(),
        peers=list(reversed(CANONICAL_PEERS)),
        categories=_flat_categories(CANONICAL_PEERS, volumes),
        max_concentration=30.0,
        peer_volumes=volumes,
    )
    assert request.peers == CANONICAL_PEERS

    analyzer = DimensionalAnalyzer(
        entity_column="issuer_name",
        target_entity=None,
        time_column=None,
        consistent_weights=False,
    )
    analyzer._store_final_weights(
        list(reversed(CANONICAL_PEERS)), volumes, {peer: 1.0 for peer in CANONICAL_PEERS}
    )
    ranks = analyzer.rank_changes_df.set_index("Peer")["Base_Rank"].to_dict()
    assert [peer for peer, _ in sorted(ranks.items(), key=lambda item: item[1])] == (
        CANONICAL_PEERS
    )


def test_reversed_peer_input_order_produces_same_weight_mapping() -> None:
    volumes = {"P1": 900.0, "P2": 200.0, "P3": 150.0, "P4": 150.0, "P5": 120.0, "P6": 90.0}
    categories = _flat_categories(CANONICAL_PEERS, volumes)
    solver = LPSolver()

    forward = solver.solve(
        build_lp_request(
            _lp_settings(),
            peers=list(CANONICAL_PEERS),
            categories=categories,
            max_concentration=30.0,
            peer_volumes=volumes,
        )
    )
    reverse = solver.solve(
        build_lp_request(
            _lp_settings(),
            peers=list(reversed(CANONICAL_PEERS)),
            categories=categories,
            max_concentration=30.0,
            peer_volumes=volumes,
        )
    )

    assert forward is not None and reverse is not None
    assert forward.weights == reverse.weights


def test_reordered_dictionaries_produce_same_analytical_result() -> None:
    """Reordering the volume dict and the category records changes nothing."""
    volumes = {"P1": 900.0, "P2": 200.0, "P3": 150.0, "P4": 150.0, "P5": 120.0, "P6": 90.0}
    reordered_volumes = {peer: volumes[peer] for peer in reversed(CANONICAL_PEERS)}
    categories = _flat_categories(CANONICAL_PEERS, volumes)
    solver = LPSolver()

    forward = solver.solve(
        build_lp_request(
            _lp_settings(),
            peers=list(CANONICAL_PEERS),
            categories=categories,
            max_concentration=30.0,
            peer_volumes=volumes,
        )
    )
    shuffled = solver.solve(
        build_lp_request(
            _lp_settings(),
            peers=list(CANONICAL_PEERS),
            categories=list(reversed(categories)),
            max_concentration=30.0,
            peer_volumes=reordered_volumes,
        )
    )

    assert forward is not None and shuffled is not None
    assert forward.weights == shuffled.weights


@pytest.mark.parametrize(
    "trial_dims",
    [
        ["card_type", "channel", "region"],
        ["region", "channel", "card_type"],
        ["channel", "card_type", "region"],
    ],
)
def test_greedy_ties_select_same_dimension(trial_dims: List[str]) -> None:
    tied_scores = {dim: 40.0 for dim in trial_dims}
    assert _most_unbalanced_dimension(trial_dims, tied_scores) == "card_type"


def test_greedy_still_prefers_the_most_unbalanced_dimension() -> None:
    scores = {"card_type": 40.0, "channel": 90.0, "region": 40.0}
    assert _most_unbalanced_dimension(["card_type", "channel", "region"], scores) == (
        "channel"
    )


def _record_trial_order(dimensions: List[str], monkeypatch: pytest.MonkeyPatch) -> List[List[str]]:
    """Run the seeded random subset search and return the trial dimension order."""
    monkeypatch.setattr(subset_search, "build_lp_request", lambda *_a, **_kw: object())

    class _NeverFeasibleSolver:
        def solve(self, _request: object) -> SimpleNamespace:
            return SimpleNamespace(
                success=True,
                weights=None,
                stats={"sum_slack": 9.0, "max_slack": 9.0, "method": "highs"},
            )

    analyzer = SimpleNamespace(
        lp_solver=_NeverFeasibleSolver(),
        last_lp_stats={},
        trigger_subset_on_slack=True,
        max_cap_slack=0.0,
        greedy_subset_search=False,
        subset_search_max_tests=50,
        subset_search_results=[],
    )
    analyzer.build_categories = lambda _df, _metric, _dims: (
        [{"dimension": "d", "category": "c", "peer": "P1", "category_volume": 1.0}],
        {"P1": 1.0},
        ["P1"],
    )
    analyzer._is_slack_excess = lambda slack: bool(slack and slack > 0.0)

    search_largest_feasible_subset(
        analyzer,
        pd.DataFrame({"txn_cnt": [1]}),
        "txn_cnt",
        dimensions,
        30.0,
        {"P1": 1.0},
        ["P1"],
        [],
    )
    return [row["Dimensions"] for row in analyzer.subset_search_results]


def test_random_subset_search_repeats_the_same_trial_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dimensions = ["card_type", "channel", "region", "segment"]
    first = _record_trial_order(dimensions, monkeypatch)
    second = _record_trial_order(dimensions, monkeypatch)

    assert first, "seeded random subset search recorded no trials"
    assert first == second


def _capturing_analyzer(peers: List[str]) -> DimensionalAnalyzer:
    """An analyzer whose solvers record the peer order they were handed."""
    analyzer = DimensionalAnalyzer(
        entity_column="issuer_name",
        target_entity=None,
        time_column=None,
        consistent_weights=False,
    )
    analyzer.seen_lp_peers: List[List[str]] = []
    analyzer.seen_heuristic_peers: List[List[str]] = []

    class _RecordingLpSolver:
        def solve(self, request: SolverRequest) -> None:
            analyzer.seen_lp_peers.append(list(request.peers))
            return None

    class _RecordingHeuristicSolver:
        def solve(self, request: SolverRequest) -> SimpleNamespace:
            analyzer.seen_heuristic_peers.append(list(request.peers))
            return SimpleNamespace(
                success=True,
                weights={peer: 1.0 for peer in request.peers},
                stats={"converged": True},
            )

    analyzer.lp_solver = _RecordingLpSolver()
    analyzer.heuristic_solver = _RecordingHeuristicSolver()
    return analyzer


def test_per_dimension_fallback_uses_canonical_peer_order() -> None:
    analyzer = _capturing_analyzer(SCRAMBLED_PEERS)
    analyzer._solve_per_dimension_weights(
        _peer_frame(SCRAMBLED_PEERS),
        "txn_cnt",
        ["card_type", "channel"],
        list(SCRAMBLED_PEERS),
        30.0,
        None,
        "6/30",
    )

    assert analyzer.seen_lp_peers, "per-dimension LP was never called"
    assert all(seen == CANONICAL_PEERS for seen in analyzer.seen_lp_peers)


def test_heuristic_fallback_uses_canonical_peer_order() -> None:
    analyzer = _capturing_analyzer(SCRAMBLED_PEERS)
    analyzer._solve_per_dimension_weights(
        _peer_frame(SCRAMBLED_PEERS),
        "txn_cnt",
        ["card_type", "channel"],
        list(SCRAMBLED_PEERS),
        30.0,
        None,
        "6/30",
    )

    assert analyzer.seen_heuristic_peers, "heuristic fallback was never called"
    assert all(seen == CANONICAL_PEERS for seen in analyzer.seen_heuristic_peers)
    for dimension in ("card_type", "channel"):
        assert list(analyzer.per_dimension_weights[dimension]) == CANONICAL_PEERS


def test_global_heuristic_fallback_uses_canonical_peer_order() -> None:
    """When the global LP fails outright, the heuristic sees canonical peers."""
    analyzer = _capturing_analyzer(SCRAMBLED_PEERS)
    analyzer.consistent_weights = True
    analyzer.enforce_single_weight_set = True
    analyzer.auto_subset_search = False
    analyzer.trigger_subset_on_slack = False

    analyzer.fit_privacy_weights(
        _peer_frame(SCRAMBLED_PEERS), "txn_cnt", ["card_type", "channel"]
    )

    assert analyzer.seen_heuristic_peers, "global heuristic fallback was never called"
    assert all(seen == CANONICAL_PEERS for seen in analyzer.seen_heuristic_peers)
    assert list(analyzer.global_weights) == CANONICAL_PEERS
    assert set(analyzer.weight_methods.values()) == {"Global-Bayesian"}


def test_heuristic_request_builder_canonicalizes_peers() -> None:
    request = build_heuristic_request(
        SimpleNamespace(
            min_weight=0.01,
            max_weight=10.0,
            tolerance=1.0,
            bayesian_max_iterations=50,
            bayesian_learning_rate=0.01,
            violation_penalty_weight=1000.0,
            merchant_mode=False,
            protected_entity_caps={},
            enforce_additional_constraints=False,
            dynamic_constraints_enabled=False,
            time_column=None,
            min_peer_count_for_constraints=4,
            min_effective_peer_count=3.0,
            min_category_volume_share=0.01,
            min_overall_volume_share=0.01,
            min_representativeness=0.5,
            dynamic_threshold_scale_floor=0.5,
            dynamic_count_scale_floor=0.5,
            representativeness_penalty_floor=0.1,
            representativeness_penalty_power=2.0,
        ),
        peers=list(SCRAMBLED_PEERS),
        categories=[],
        max_concentration=30.0,
        peer_volumes={},
        target_weights=None,
        rule_name="6/30",
    )
    assert request.peers == CANONICAL_PEERS


def test_lp_solver_method_fallback_preserves_canonical_weight_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed first LP method must not change the peer/weight mapping."""
    volumes = {"P1": 900.0, "P2": 200.0, "P3": 150.0, "P4": 150.0, "P5": 120.0, "P6": 90.0}
    request = build_lp_request(
        _lp_settings(),
        peers=list(reversed(CANONICAL_PEERS)),
        categories=_flat_categories(CANONICAL_PEERS, volumes),
        max_concentration=30.0,
        peer_volumes=volumes,
    )
    baseline = LPSolver().solve(request)
    assert baseline is not None

    import core.solvers.lp_solver as lp_module

    original = lp_module.linprog
    attempted: List[str] = []

    def _failing_first_method(*args: Any, **kwargs: Any) -> Any:
        method = kwargs.get("method")
        attempted.append(method)
        if method == "highs":
            raise RuntimeError("simulated solver failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(lp_module, "linprog", _failing_first_method)
    fallback = LPSolver().solve(request)

    assert attempted[0] == "highs"
    assert fallback is not None
    assert fallback.stats["method"] == "highs-ds"
    assert list(fallback.weights) == CANONICAL_PEERS
    assert fallback.weights == baseline.weights


def _analytical_modules() -> List[Path]:
    core_dir = REPO_ROOT / "core"
    return sorted(core_dir.rglob("*.py"))


def test_no_analytical_path_orders_data_from_an_unsorted_set() -> None:
    """`list(set(...))` and friends must never define analytical order."""
    offenders: List[str] = []
    ordering_calls = {"list", "tuple", "sorted"}

    for module in _analytical_modules():
        tree = ast.parse(module.read_text(encoding="utf-8-sig"), filename=str(module))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not node.args:
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else None
            if name not in ordering_calls or name == "sorted":
                continue
            argument = node.args[0]
            builds_a_set = isinstance(argument, ast.SetComp) or (
                isinstance(argument, ast.Call)
                and isinstance(argument.func, ast.Name)
                and argument.func.id == "set"
            )
            if builds_a_set:
                offenders.append(
                    f"{module.relative_to(REPO_ROOT)}:{node.lineno} {name}(set(...))"
                )

    assert offenders == []
