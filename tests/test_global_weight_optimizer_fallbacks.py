import unittest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.global_weight_optimizer import GlobalWeightOptimizer


@dataclass
class _SolverResult:
    success: bool
    weights: Dict[str, float]
    stats: Dict[str, Any]


class _FakeLpSolver:
    def __init__(self, weights: Dict[str, float]) -> None:
        self._weights = weights

    def solve(self, *_args: Any, **_kwargs: Any) -> _SolverResult:
        return _SolverResult(success=True, weights=dict(self._weights), stats={'sum_slack': 0.0})


class _FakeHeuristicSolver:
    def solve(self, *_args: Any, **_kwargs: Any) -> Optional[_SolverResult]:
        return None


class _FakeAnalyzer:
    def __init__(
        self,
        all_categories: List[Dict[str, Any]],
        peer_volumes: Dict[str, float],
        peers: List[str],
        *,
        enforce_single_weight_set: bool,
    ) -> None:
        self.consistent_weights = True
        self.time_column = 'year_month'
        self.enforce_single_weight_set = enforce_single_weight_set
        self.tolerance = 0.0
        self.max_cap_slack = 0.0
        self.trigger_subset_on_slack = False
        self.auto_subset_search = False
        self.prefer_slacks_first = False
        self.rank_preservation_strength = 0.5
        self.rank_constraint_mode = 'all'
        self.rank_constraint_k = 1
        self.volume_weighted_penalties = False
        self.volume_weighting_exponent = 1.0
        self.lambda_penalty = None
        self.max_iterations = 1000
        self.min_weight = 0.01
        self.max_weight = 10.0
        self.bayesian_max_iterations = 50
        self.bayesian_learning_rate = 0.01
        self.violation_penalty_weight = 1000.0
        self.merchant_mode = False
        self.enforce_additional_constraints = False
        self.dynamic_constraints_enabled = False
        self.min_peer_count_for_constraints = 4
        self.min_effective_peer_count = 3.0
        self.min_category_volume_share = 0.001
        self.min_overall_volume_share = 0.0005
        self.min_representativeness = 0.1
        self.dynamic_threshold_scale_floor = 0.6
        self.dynamic_count_scale_floor = 0.5
        self.representativeness_penalty_floor = 0.25
        self.representativeness_penalty_power = 1.0
        self.last_lp_stats: Dict[str, Any] = {}
        self.weight_methods: Dict[str, str] = {}
        self.per_dimension_weights: Dict[str, Dict[str, float]] = {}
        self.global_weights: Dict[str, Dict[str, float]] = {}
        self.additional_constraint_violations: List[Dict[str, Any]] = []
        self.global_dimensions_used: List[str] = []
        self.removed_dimensions: List[str] = []
        self.lp_solver = _FakeLpSolver({p: 1.0 for p in peers})
        self.heuristic_solver = _FakeHeuristicSolver()
        self._all_categories = all_categories
        self._peer_volumes = peer_volumes
        self._peers = peers
        self._build_categories_calls: List[List[str]] = []
        self.structural_detail_df = pd.DataFrame()
        self.structural_summary_df = pd.DataFrame()
        self.slack_subset_triggered = False

    def _build_time_aware_categories(
        self,
        _df: pd.DataFrame,
        _metric_col: str,
        _dimensions: List[str],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], List[str]]:
        return self._all_categories, self._peer_volumes, self._peers

    def _build_categories(
        self,
        _df: pd.DataFrame,
        _metric_col: str,
        dimensions: List[str],
    ) -> Tuple[List[Dict[str, Any]], Dict[str, float], List[str]]:
        self._build_categories_calls.append(list(dimensions))
        return [], {}, []

    def _get_privacy_rule(self, _peer_count: int) -> Tuple[str, float]:
        return '6/30', 30.0

    def _reset_dynamic_constraint_stats(self) -> None:
        return

    def _compute_structural_caps_diagnostics(
        self,
        _peers: List[str],
        _all_categories: List[Dict[str, Any]],
        _max_concentration: float,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        return pd.DataFrame(), pd.DataFrame()

    def get_structural_infeasibility_summary(self) -> Dict[str, Any]:
        return {'has_structural_infeasibility': False}

    def _is_slack_excess(self, _sum_slack: float) -> bool:
        return False

    def _search_largest_feasible_subset(self, *_args: Any, **_kwargs: Any) -> Tuple[List[str], Optional[Dict[str, float]]]:
        return [], None

    def _dimension_unbalance_scores(self, _all_categories: List[Dict[str, Any]]) -> Dict[str, float]:
        return {}

    def _solve_per_dimension_weights(self, *_args: Any, **_kwargs: Any) -> None:
        return

    def _find_additional_constraint_violations(self, *_args: Any, **_kwargs: Any) -> List[Dict[str, Any]]:
        return []

    def _nudge_borderline_cap_excess(
        self,
        weights: Dict[str, float],
        _all_categories: List[Dict[str, Any]],
        _max_concentration: float,
        _used_dimensions: List[str],
    ) -> Dict[str, float]:
        return weights

    def _store_final_weights(self, peers: List[str], _peer_volumes: Dict[str, float], weights: Dict[str, float]) -> None:
        self.global_weights = {peer: {'multiplier': weights[peer]} for peer in peers}

    def _is_share_violation(self, adjusted_share: float, max_concentration: float) -> bool:
        return adjusted_share > (max_concentration + self.tolerance)


class TestGlobalWeightOptimizerFallbacks(unittest.TestCase):
    def test_internal_time_total_dimension_is_not_sent_to_per_dimension_solver(self) -> None:
        # Only internal TIME_TOTAL constraints violate; optimizer must not attempt per-dimension solve for them.
        all_categories = [
            {
                'peer': 'P1',
                'dimension': '_TIME_TOTAL_year_month',
                'category': 202501,
                'time_period': 202501,
                'category_volume': 100.0,
            },
            {
                'peer': 'P2',
                'dimension': '_TIME_TOTAL_year_month',
                'category': 202501,
                'time_period': 202501,
                'category_volume': 0.0,
            },
        ]
        analyzer = _FakeAnalyzer(
            all_categories=all_categories,
            peer_volumes={'P1': 100.0, 'P2': 50.0},
            peers=['P1', 'P2'],
            enforce_single_weight_set=False,
        )
        optimizer = GlobalWeightOptimizer(analyzer)
        optimizer.calculate_global_privacy_weights(
            df=pd.DataFrame({'year_month': [202501]}),
            metric_col='metric',
            dimensions=['flag_domestic'],
        )
        self.assertEqual(analyzer._build_categories_calls, [])

    def test_single_weight_set_mode_skips_per_dimension_reweighting(self) -> None:
        # Real dimension violates, but strict single-weight-set mode should keep global weights.
        all_categories = [
            {
                'peer': 'P1',
                'dimension': 'flag_domestic_year_month',
                'category': 'Domestic_202501',
                'time_period': 202501,
                'category_volume': 100.0,
            },
            {
                'peer': 'P2',
                'dimension': 'flag_domestic_year_month',
                'category': 'Domestic_202501',
                'time_period': 202501,
                'category_volume': 0.0,
            },
        ]
        analyzer = _FakeAnalyzer(
            all_categories=all_categories,
            peer_volumes={'P1': 100.0, 'P2': 50.0},
            peers=['P1', 'P2'],
            enforce_single_weight_set=True,
        )
        optimizer = GlobalWeightOptimizer(analyzer)
        optimizer.calculate_global_privacy_weights(
            df=pd.DataFrame({'year_month': [202501]}),
            metric_col='metric',
            dimensions=['flag_domestic'],
        )
        self.assertEqual(analyzer._build_categories_calls, [])
        self.assertIn('flag_domestic', analyzer.weight_methods)
        self.assertEqual(analyzer.weight_methods['flag_domestic'], 'Global-LP')


if __name__ == '__main__':
    unittest.main()

