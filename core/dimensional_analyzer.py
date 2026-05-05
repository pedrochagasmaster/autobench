"""
DimensionalAnalyzer - Automatic dimensional breakdown analysis.

Analyzes metrics across all dimensional columns in the dataset,
following Mastercard privacy rules for balanced benchmarking.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging
import warnings
from time import perf_counter

from .privacy_validator import PrivacyValidator
from .category_builder import CategoryBuilder
from .diagnostics_engine import DiagnosticsEngine
from .analysis_calculator import AnalysisCalculator
from .global_weight_optimizer import GlobalWeightOptimizer
from .privacy_policy import PrivacyPolicy, PrivacyPolicySettings
from .contracts import SolverRequest
from .constants import (
    COMPARISON_EPSILON as SHARED_COMPARISON_EPSILON,
    BORDERLINE_CAP_EXCESS_TOLERANCE_PP,
    MIN_WEIGHT_DELTA_EPSILON,
)
from .solvers.lp_solver import LPSolver
from .solvers.heuristic_solver import HeuristicSolver

logger = logging.getLogger(__name__)


class DimensionalAnalyzer:
    """
    Performs automatic dimensional breakdown analysis.
    
    For each dimensional column:
    - Calculates BALANCED (weighted) peer group average (excluding target entity)
    - Calculates Best-in-Class using 85th percentile
    - Generates comparison metrics
    
    Following Mastercard Control 3.2 privacy rules.
    """
    
    def __init__(
        self,
        target_entity: Optional[str],
        entity_column: str = 'entity_identifier',
        bic_percentile: float = 0.85,
        debug_mode: bool = False,
        consistent_weights: bool = False,
        max_iterations: int = 1000,
        tolerance: float = 1.0,
        max_weight: float = 10.0,
        min_weight: float = 0.01,
        volume_preservation_strength: float = 0.5,
        # New controls
        prefer_slacks_first: bool = False,
        auto_subset_search: bool = False,
        subset_search_max_tests: int = 200,
        greedy_subset_search: bool = True,
        # Milestone 1 controls
        trigger_subset_on_slack: bool = True,
        max_cap_slack: float = 0.0,
        time_column: Optional[str] = None,
        # Volume-weighted penalties
        volume_weighted_penalties: bool = False,
        volume_weighting_exponent: float = 1.0,
        lambda_penalty: Optional[float] = None,
        enforce_additional_constraints: bool = True,
        # Dynamic constraint handling for sparse/low-representativeness buckets
        dynamic_constraints_enabled: bool = True,
        min_peer_count_for_constraints: int = 4,
        min_effective_peer_count: float = 3.0,
        min_category_volume_share: float = 0.001,
        min_overall_volume_share: float = 0.0005,
        min_representativeness: float = 0.1,
        dynamic_threshold_scale_floor: float = 0.6,
        dynamic_count_scale_floor: float = 0.5,
        representativeness_penalty_floor: float = 0.25,
        representativeness_penalty_power: float = 1.0,
        merchant_mode: bool = False,
        rank_constraint_mode: str = "all",
        rank_constraint_k: int = 1,
        bayesian_max_iterations: int = 500,
        bayesian_learning_rate: float = 0.01,
        violation_penalty_weight: float = 1000.0,
        enforce_single_weight_set: bool = False,
    ):
        """
        Initialize dimensional analyzer.
        
        Parameters:
        -----------
        target_entity : Optional[str]
            Name of the target entity to analyze (None for peer-only analysis)
        entity_column : str
            Name of the entity identifier column
        bic_percentile : float
            Percentile for Best-in-Class calculation (default: 0.85)
        debug_mode : bool
            If True, include unweighted averages in output (default: False)
        consistent_weights : bool
            If True, use the same privacy-constrained weights across all dimensions (global weighting)
        max_iterations : int
            Maximum iterations for privacy weight convergence (default: 1000)
        tolerance : float
            Tolerance for privacy violations in percentage points (default: 1.0)
        max_weight : float
            Maximum weight multiplier allowed (default: 10.0)
        min_weight : float
            Minimum weight multiplier allowed (default: 0.01)
        volume_preservation_strength : float
            DEPRECATED: Previously used to preserve volume profile. Now mapped to rank preservation strength.
        prefer_slacks_first : bool
            Try full-dimension LP with slacks-first before dropping dimensions (default: False)
        auto_subset_search : bool
            Automatically search for largest feasible global dimension subset (default: False)
        subset_search_max_tests : int
            Maximum attempts during subset search (default: 200)
        greedy_subset_search : bool
            Use greedy search (remove one dimension at a time). If False, use random search 
            testing n-1, n-2, ... combinations randomly (default: True)
        trigger_subset_on_slack : bool
            Trigger subset search if LP uses slack above threshold (default: True)
        max_cap_slack : float
            Slack sum threshold as percentage of total volume to trigger subset search (default: 0.0)
        time_column : Optional[str]
            Name of the time column for time-aware consistency. When provided with consistent_weights=True,
            ensures weights are consistent across all time periods and all time-category combinations.
        volume_weighted_penalties : bool
            If True, weight slack penalties by category volume (higher penalties for high-volume categories)
        volume_weighting_exponent : float
            Exponent for volume weighting: penalty proportional to volume^exponent (default: 1.0 = linear)
        enforce_additional_constraints : bool
            If True, enforce Control 3.2 additional constraints (6/30, 7/35, 10/40) in heuristic optimization
        dynamic_constraints_enabled : bool
            If True, adapt additional-constraint enforcement based on peer count and representativeness
        min_peer_count_for_constraints : int
            Minimum peers in a category/time bucket to enforce additional constraints
        min_effective_peer_count : float
            Minimum effective peer count (1/sum(s^2)) to enforce additional constraints
        min_category_volume_share : float
            Minimum share of volume within the dimension/time slice to enforce additional constraints
        min_overall_volume_share : float
            Minimum share of overall volume to enforce additional constraints
        min_representativeness : float
            Minimum representativeness score to enforce additional constraints
        dynamic_threshold_scale_floor : float
            Lower bound for scaling additional-constraint thresholds in sparse buckets
        dynamic_count_scale_floor : float
            Lower bound for scaling additional-constraint counts in sparse buckets
        representativeness_penalty_floor : float
            Minimum penalty weight applied to low-representativeness buckets
        representativeness_penalty_power : float
            Exponent for representativeness penalty weighting
        merchant_mode : bool
            If True, allow merchant-specific 4/35 privacy rule when peer count is 4
        rank_constraint_mode : str
            Rank constraint mode for LP solver ('all' or 'neighbor')
        rank_constraint_k : int
            Neighbor count used when rank_constraint_mode is 'neighbor'
        bayesian_learning_rate : float
            Numerical step size used for heuristic optimization (L-BFGS-B) when configured
        violation_penalty_weight : float
            Penalty multiplier for privacy/additional-constraint violations in heuristic solver
        enforce_single_weight_set : bool
            If True, force a single global weight set and disable per-dimension fallback/re-weighting.
        """
        self.target_entity = target_entity
        self.entity_column = entity_column
        self.bic_percentile = bic_percentile
        self.debug_mode = debug_mode
        self.consistent_weights = consistent_weights
        self.max_iterations = max_iterations
        self.tolerance = tolerance
        self.max_weight = max_weight
        self.min_weight = min_weight
        # Map legacy volume preservation to rank preservation
        self.rank_preservation_strength: float = float(volume_preservation_strength)
        self.volume_preservation_strength = volume_preservation_strength  # kept for backward compatibility (unused)
        self.global_weights = {}  # Store global weights for consistent mode
        self.weights_data = []  # Store weights for debug reporting
        # New: store per-dimension specific weights when global LP drops some dimensions
        self.per_dimension_weights: Dict[str, Dict[str, float]] = {}
        # Track the method used for each dimension's weights
        self.weight_methods: Dict[str, str] = {}  # dimension -> "Global-LP" | "Per-Dimension-LP" | "Per-Dimension-Bayesian"
        self.global_dimensions_used: List[str] = []
        self.removed_dimensions: List[str] = []
        # New: preferences and diagnostics
        self.prefer_slacks_first = prefer_slacks_first
        self.auto_subset_search = auto_subset_search
        self.subset_search_max_tests = subset_search_max_tests
        self.greedy_subset_search = greedy_subset_search
        self.last_lp_stats: Dict[str, Any] = {}
        self.subset_search_results: List[Dict[str, Any]] = []
        # Milestone 1 state
        self.trigger_subset_on_slack: bool = bool(trigger_subset_on_slack)
        self.max_cap_slack: float = float(max_cap_slack)
        self.time_column: Optional[str] = time_column
        # Volume-weighted penalties
        self.volume_weighted_penalties: bool = bool(volume_weighted_penalties)
        self.volume_weighting_exponent: float = float(volume_weighting_exponent)
        self.lambda_penalty: Optional[float] = float(lambda_penalty) if lambda_penalty is not None else None
        self.enforce_additional_constraints: bool = bool(enforce_additional_constraints)
        self.dynamic_constraints_enabled: bool = bool(dynamic_constraints_enabled)
        self.min_peer_count_for_constraints: int = int(min_peer_count_for_constraints)
        self.min_effective_peer_count: float = float(min_effective_peer_count)
        self.min_category_volume_share: float = float(min_category_volume_share)
        self.min_overall_volume_share: float = float(min_overall_volume_share)
        self.min_representativeness: float = float(min_representativeness)
        self.dynamic_threshold_scale_floor: float = float(dynamic_threshold_scale_floor)
        self.dynamic_count_scale_floor: float = float(dynamic_count_scale_floor)
        self.representativeness_penalty_floor: float = float(representativeness_penalty_floor)
        self.representativeness_penalty_power: float = float(representativeness_penalty_power)
        self.merchant_mode: bool = bool(merchant_mode)
        self.rank_constraint_mode = rank_constraint_mode
        self.rank_constraint_k = int(rank_constraint_k)
        self.bayesian_max_iterations = int(bayesian_max_iterations)
        self.bayesian_learning_rate = float(bayesian_learning_rate)
        self.violation_penalty_weight = float(violation_penalty_weight)
        self.enforce_single_weight_set: bool = bool(enforce_single_weight_set)
        self.category_builder = CategoryBuilder(
            entity_column=self.entity_column,
            target_entity=self.target_entity,
            time_column=self.time_column,
            consistent_weights=self.consistent_weights,
        )
        self.privacy_policy = PrivacyPolicy(
            merchant_mode=self.merchant_mode,
            time_column=self.time_column,
        )
        self.diagnostics_engine = DiagnosticsEngine(
            min_weight=self.min_weight,
            max_weight=self.max_weight,
            tolerance=self.tolerance,
            time_column=self.time_column,
        )
        self.slack_subset_triggered: bool = False
        self.lp_solver = LPSolver()
        self.heuristic_solver = HeuristicSolver()
        self.analysis_calculator = AnalysisCalculator(self)
        self.global_weight_optimizer = GlobalWeightOptimizer(self)
        # Structural diagnostics placeholders
        self.structural_detail_df: pd.DataFrame = pd.DataFrame()
        self.structural_summary_df: pd.DataFrame = pd.DataFrame()
        # Rank changes (Milestone 2)
        self.rank_changes_df: pd.DataFrame = pd.DataFrame()
        # Privacy compliance validation (enabled by output settings)
        self.privacy_validation_df: pd.DataFrame = pd.DataFrame()
        self.privacy_rule_name: Optional[str] = None
        self.additional_constraint_violations: List[Dict[str, Any]] = []
        self.dynamic_constraint_stats: Dict[str, int] = {
            'enforced': 0,
            'relaxed': 0,
            'skipped_low_peers': 0,
            'skipped_low_effective_peers': 0,
            'skipped_low_volume': 0,
            'skipped_low_representativeness': 0,
        }
        self._log_init_settings()

    def _log_init_settings(self) -> None:
        logger.info(f"Initialized DimensionalAnalyzer for entity: {self.target_entity}")
        if self.debug_mode:
            logger.info("Debug mode enabled - will include unweighted averages and weights tracking")
        if self.consistent_weights:
            logger.info("Consistent weights mode enabled - same privacy-constrained weights across all dimensions")
            if self.volume_weighted_penalties:
                logger.info(
                    "Volume-weighted penalties ENABLED - violations in high-volume categories penalized more heavily "
                    "(exponent=%s)",
                    self.volume_weighting_exponent
                )
            if self.dynamic_constraints_enabled:
                logger.info(
                    "Dynamic constraints ENABLED - min_peers=%s, min_effective_peers=%s, min_rep=%s",
                    self.min_peer_count_for_constraints,
                    self.min_effective_peer_count,
                    self.min_representativeness
                )
            logger.info(
                "Weight parameters: max_iterations=%s, tolerance=%s%%, "
                "max_weight=%sx, min_weight=%sx, rank_preservation=%s",
                self.max_iterations, self.tolerance, self.max_weight, self.min_weight, self.rank_preservation_strength
            )
            if self.enforce_single_weight_set:
                logger.info("Single weight-set mode ENABLED - per-dimension fallback is disabled")

    def get_structural_infeasibility_summary(self) -> Dict[str, Any]:
        """Return a compact summary of structural infeasibility diagnostics."""
        summary: Dict[str, Any] = {
            'has_structural_infeasibility': False,
            'infeasible_dimensions': 0,
            'infeasible_categories': 0,
            'infeasible_peers': 0,
            'worst_margin_pp': 0.0,
            'top_infeasible_dimension': None,
            'top_infeasible_category': None,
        }

        if self.structural_summary_df is not None and not self.structural_summary_df.empty:
            summary['has_structural_infeasibility'] = True
            summary['infeasible_dimensions'] = int(len(self.structural_summary_df))
            summary['infeasible_categories'] = int(
                self.structural_summary_df.get('infeasible_categories', pd.Series(dtype=float)).sum()
            )
            summary['infeasible_peers'] = int(
                self.structural_summary_df.get('infeasible_peers', pd.Series(dtype=float)).sum()
            )
            summary['worst_margin_pp'] = float(
                self.structural_summary_df.get('worst_margin_pp', pd.Series([0.0])).max()
            )
            try:
                top_row = self.structural_summary_df.sort_values('worst_margin_pp', ascending=False).iloc[0]
                summary['top_infeasible_dimension'] = top_row.get('dimension')
            except Exception:
                pass

        if self.structural_detail_df is not None and not self.structural_detail_df.empty:
            try:
                top_detail = self.structural_detail_df.sort_values('margin_over_cap_pp', ascending=False).iloc[0]
                summary['top_infeasible_category'] = top_detail.get('category')
            except Exception:
                pass

        return summary

    @classmethod
    def _warn_deprecated(cls, method_name: str, replacement: str) -> None:
        message = (
            f"{method_name} is deprecated and will be removed in v{cls.DEPRECATION_REMOVE_VERSION}. "
            f"Use {replacement} instead."
        )
        warnings.warn(message, DeprecationWarning, stacklevel=2)
        logger.warning(message)
    
    def calculate_global_weights(self, df: pd.DataFrame, metric_col: str) -> None:
        """
        DEPRECATED: Use calculate_global_privacy_weights instead.
        This method is kept for backward compatibility.
        """
        self._warn_deprecated("calculate_global_weights", "calculate_global_privacy_weights")
        # Aggregate total volume by entity
        entity_totals = df.groupby(self.entity_column)[metric_col].sum()
        peer_totals = entity_totals[entity_totals.index != self.target_entity]
        total_peer_volume = peer_totals.sum()
        
        for entity, volume in peer_totals.items():
            weight_pct = (volume / total_peer_volume * 100) if total_peer_volume > 0 else 0
            self.global_weights[entity] = {
                'volume': volume,
                'weight': weight_pct,
                'multiplier': 1.0
            }


    def _build_categories(self, df: pd.DataFrame, metric_col: str, dimensions: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, float], List[str]]:
        """Aggregate by entity and dimension categories for the given dimensions."""
        return self.category_builder.build_categories(df, metric_col, dimensions)

    def _build_time_aware_categories(self, df: pd.DataFrame, metric_col: str, dimensions: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, float], List[str]]:
        """
        Build categories that include time-aware constraints for consistent weights.
        
        When time_column is specified with consistent_weights=True, this method creates
        constraints for:
        1. Total monthly volumes (privacy rule for each month)
        2. Monthly category volumes (privacy rule for each month-category combination)
        
        The same weights must satisfy privacy rules across all these combinations.
        """
        return self.category_builder.build_time_aware_categories(df, metric_col, dimensions)

    def _get_privacy_rule(self, peer_count: int) -> Tuple[str, float]:
        """Select privacy rule and max concentration for a given peer count."""
        rule_name, rule_cfg = self.privacy_policy.select_rule(peer_count)
        max_concentration = float(rule_cfg.get('max_concentration', 50.0))
        return rule_name, max_concentration

    # Constants
    COMPARISON_EPSILON = SHARED_COMPARISON_EPSILON

    def _is_slack_excess(self, sum_slack: float) -> bool:
        return sum_slack > float(self.max_cap_slack) + self.COMPARISON_EPSILON

    def _is_share_violation(self, adjusted_share: float, max_concentration: float) -> bool:
        return adjusted_share > (max_concentration + self.tolerance + self.COMPARISON_EPSILON)

    def _nudge_borderline_cap_excess(
        self,
        weights: Dict[str, float],
        all_categories: List[Dict[str, Any]],
        max_concentration: float,
        dimension_filter: Optional[List[str]] = None,
    ) -> Dict[str, float]:
        """Reduce tiny cap excesses by nudging top violators within bounds.

        This only adjusts weights when the max excess is within a small threshold
        and preserves min/max bounds for all peers.
        """
        max_allowed = max_concentration + self.tolerance
        max_excess = 0.0
        worst_peer: Optional[str] = None
        worst_category: Optional[Dict[str, Any]] = None
        worst_total_weighted = 0.0

        grouped_cats: Dict[Tuple[Any, Any, Any], List[Dict[str, Any]]] = {}
        for cat in all_categories:
            key = (cat.get('dimension'), cat.get('category'), cat.get('time_period'))
            if key not in grouped_cats:
                grouped_cats[key] = []
            grouped_cats[key].append(cat)

        for cat in all_categories:
            if dimension_filter:
                if cat['dimension'] in dimension_filter:
                    pass
                elif self.time_column and any(
                    cat['dimension'].startswith(f"{dim}_{self.time_column}")
                    for dim in dimension_filter
                ):
                    pass
                else:
                    continue
            if cat['peer'] not in weights:
                continue

            key = (cat.get('dimension'), cat.get('category'), cat.get('time_period'))
            matching_cats = grouped_cats.get(key, [])

            total_weighted = sum(c['category_volume'] * weights[c['peer']] for c in matching_cats)
            if total_weighted <= 0:
                continue

            peer = cat['peer']
            peer_weighted = cat['category_volume'] * weights[peer]
            adjusted_share = (peer_weighted / total_weighted * 100.0)
            excess = adjusted_share - max_allowed
            if excess > max_excess:
                max_excess = excess
                worst_peer = peer
                worst_category = cat
                worst_total_weighted = total_weighted

        if not worst_peer:
            return weights

        if max_excess <= 0:
            return weights

        if max_excess > BORDERLINE_CAP_EXCESS_TOLERANCE_PP:
            return weights

        current = weights.get(worst_peer, 1.0)
        if not worst_category or worst_total_weighted <= 0:
            return weights

        peer_weighted = worst_category['category_volume'] * current
        others = max(worst_total_weighted - peer_weighted, 0.0)
        target_share = max_allowed
        if peer_weighted <= 0 or others <= 0:
            return weights

        scale = (target_share * others) / (peer_weighted * (100.0 - target_share))
        scale = max(0.0, min(scale, 1.0))
        new_weight = max(self.min_weight, min(current * scale, self.max_weight))
        if abs(new_weight - current) < MIN_WEIGHT_DELTA_EPSILON:
            return weights

        adjusted = dict(weights)
        adjusted[worst_peer] = new_weight
        return adjusted

    @staticmethod
    def _participant_count(peer_volumes: Dict[str, float]) -> int:
        return sum(1 for volume in peer_volumes.values() if volume > 0)

    def _reset_dynamic_constraint_stats(self) -> None:
        self.dynamic_constraint_stats = {
            'enforced': 0,
            'relaxed': 0,
            'skipped_low_peers': 0,
            'skipped_low_effective_peers': 0,
            'skipped_low_volume': 0,
            'skipped_low_representativeness': 0,
        }

    def _get_time_periods(self, df: pd.DataFrame) -> List[Any]:
        if not self.time_column or self.time_column not in df.columns:
            return []
        series = df[self.time_column].dropna()
        if series.empty:
            return []
        return sorted(series.unique())

    def _build_constraint_stats(
        self,
        dim_categories: List[Dict[str, Any]],
        peers: List[str],
        peer_volumes: Dict[str, float]
    ) -> Dict[Tuple[str, Any, Optional[Any]], Dict[str, float]]:
        return self.diagnostics_engine.build_constraint_stats(dim_categories, peers, peer_volumes)

    def _build_lp_request(
        self,
        *,
        peers: List[str],
        categories: List[Dict[str, Any]],
        max_concentration: float,
        peer_volumes: Dict[str, float],
        tolerance: Optional[float] = None,
    ) -> SolverRequest:
        return SolverRequest(
            peers=peers,
            categories=categories,
            max_concentration=max_concentration,
            peer_volumes=peer_volumes,
            rank_preservation_strength=self.rank_preservation_strength,
            rank_constraint_mode=self.rank_constraint_mode,
            rank_constraint_k=self.rank_constraint_k,
            tolerance=float(self.tolerance if tolerance is None else tolerance),
            volume_weighted_penalties=self.volume_weighted_penalties,
            volume_weighting_exponent=self.volume_weighting_exponent,
            lambda_penalty=self.lambda_penalty,
            max_iterations=self.max_iterations,
            min_weight=self.min_weight,
            max_weight=self.max_weight,
        )

    def _build_heuristic_request(
        self,
        *,
        peers: List[str],
        categories: List[Dict[str, Any]],
        max_concentration: float,
        peer_volumes: Dict[str, float],
        target_weights: Optional[Dict[str, float]],
        rule_name: Optional[str],
        tolerance: Optional[float] = None,
    ) -> SolverRequest:
        return SolverRequest(
            peers=peers,
            categories=categories,
            max_concentration=max_concentration,
            peer_volumes=peer_volumes,
            target_weights=target_weights,
            rule_name=rule_name,
            min_weight=self.min_weight,
            max_weight=self.max_weight,
            tolerance=float(self.tolerance if tolerance is None else tolerance),
            max_iterations=self.bayesian_max_iterations,
            learning_rate=self.bayesian_learning_rate,
            violation_penalty_weight=self.violation_penalty_weight,
            merchant_mode=self.merchant_mode,
            enforce_additional_constraints=self.enforce_additional_constraints,
            dynamic_constraints_enabled=self.dynamic_constraints_enabled,
            time_column=self.time_column,
            min_peer_count_for_constraints=self.min_peer_count_for_constraints,
            min_effective_peer_count=self.min_effective_peer_count,
            min_category_volume_share=self.min_category_volume_share,
            min_overall_volume_share=self.min_overall_volume_share,
            min_representativeness=self.min_representativeness,
            dynamic_threshold_scale_floor=self.dynamic_threshold_scale_floor,
            dynamic_count_scale_floor=self.dynamic_count_scale_floor,
            representativeness_penalty_floor=self.representativeness_penalty_floor,
            representativeness_penalty_power=self.representativeness_penalty_power,
        )

    def _get_dynamic_additional_thresholds(
        self,
        rule_name: str,
        participants: int,
        representativeness: float,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        thresholds = self.privacy_policy._dynamic_thresholds(
            rule_name=rule_name,
            participants=participants,
            representativeness=representativeness,
            settings=PrivacyPolicySettings(
                enforce_additional_constraints=self.enforce_additional_constraints,
                dynamic_constraints_enabled=self.dynamic_constraints_enabled,
                min_peer_count_for_constraints=self.min_peer_count_for_constraints,
                min_effective_peer_count=self.min_effective_peer_count,
                min_category_volume_share=self.min_category_volume_share,
                min_overall_volume_share=self.min_overall_volume_share,
                min_representativeness=self.min_representativeness,
                dynamic_threshold_scale_floor=self.dynamic_threshold_scale_floor,
                dynamic_count_scale_floor=self.dynamic_count_scale_floor,
            ),
        )
        return thresholds, bool(thresholds)

    def _assess_additional_constraints_applicability(
        self,
        rule_name: Optional[str],
        dimension: Optional[str],
        peer_volumes: Dict[str, float],
        stats: Optional[Dict[str, float]] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]], bool]:
        decision = self.privacy_policy.assess_additional_constraints(
            rule_name=rule_name,
            dimension=dimension,
            peers=list(peer_volumes.keys()),
            peer_volumes=peer_volumes,
            stats=stats,
            settings=PrivacyPolicySettings(
                enforce_additional_constraints=self.enforce_additional_constraints,
                dynamic_constraints_enabled=self.dynamic_constraints_enabled,
                min_peer_count_for_constraints=self.min_peer_count_for_constraints,
                min_effective_peer_count=self.min_effective_peer_count,
                min_category_volume_share=self.min_category_volume_share,
                min_overall_volume_share=self.min_overall_volume_share,
                min_representativeness=self.min_representativeness,
                dynamic_threshold_scale_floor=self.dynamic_threshold_scale_floor,
                dynamic_count_scale_floor=self.dynamic_count_scale_floor,
            ),
        )
        return decision.enforce, decision.reason, decision.thresholds, decision.relaxed

    def _evaluate_additional_constraints(
        self,
        shares: List[float],
        rule_name: str,
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        return PrivacyValidator.evaluate_additional_constraints_with_thresholds(
            shares, rule_name, thresholds
        )

    def _find_additional_constraint_violations(
        self,
        dim_categories: List[Dict[str, Any]],
        peers: List[str],
        weights: Dict[str, float],
        rule_name: str,
        peer_volumes: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Evaluate additional constraints per category and return violations."""
        violations: List[Dict[str, Any]] = []

        constraint_stats = self._build_constraint_stats(dim_categories, peers, peer_volumes)

        # Build unique constraint keys (dimension, category, time_period)
        unique_keys = set()
        for cat in dim_categories:
            key = (cat['dimension'], cat['category'], cat.get('time_period'))
            unique_keys.add(key)

        for key in unique_keys:
            dim, category, time_period = key
            matching_cats = [
                c for c in dim_categories
                if c['dimension'] == dim
                and c['category'] == category
                and c.get('time_period') == time_period
            ]
            peer_volumes = {p: 0.0 for p in peers}
            for cat in matching_cats:
                peer_volumes[cat['peer']] = float(cat.get('category_volume', 0.0))

            stats = constraint_stats.get(key)
            enforce, reason, thresholds, relaxed = self._assess_additional_constraints_applicability(
                rule_name, dim, peer_volumes, stats
            )
            if not enforce:
                if reason == 'low_peers':
                    self.dynamic_constraint_stats['skipped_low_peers'] += 1
                elif reason == 'low_effective_peers':
                    self.dynamic_constraint_stats['skipped_low_effective_peers'] += 1
                elif reason == 'low_volume':
                    self.dynamic_constraint_stats['skipped_low_volume'] += 1
                elif reason == 'low_representativeness':
                    self.dynamic_constraint_stats['skipped_low_representativeness'] += 1
                continue
            self.dynamic_constraint_stats['enforced'] += 1
            if relaxed:
                self.dynamic_constraint_stats['relaxed'] += 1

            total_weighted = sum(peer_volumes[p] * weights.get(p, 1.0) for p in peers)
            if total_weighted <= 0:
                shares = [0.0 for _ in peers]
            else:
                shares = [
                    (peer_volumes[p] * weights.get(p, 1.0) / total_weighted * 100.0)
                    for p in peers
                ]

            passed, details = self._evaluate_additional_constraints(shares, rule_name, thresholds)
            if not passed:
                participant_count = self._participant_count(peer_volumes)
                top_shares = sorted(shares, reverse=True)[:3]
                violations.append({
                    'Dimension': dim,
                    'Category': category,
                    'Time_Period': time_period,
                    'Participants': participant_count,
                    'Effective_Peers': round(float(stats.get('effective_peers', 0.0)) if stats else 0.0, 4),
                    'Representativeness': round(float(stats.get('representativeness', 0.0)) if stats else 0.0, 6),
                    'Volume_Share': round(float(stats.get('volume_share', 0.0)) if stats else 0.0, 6),
                    'Overall_Share': round(float(stats.get('overall_share', 0.0)) if stats else 0.0, 6),
                    'Top_Shares': ", ".join(f"{s:.2f}%" for s in top_shares),
                    'Details': "; ".join(details) if details else "Additional constraints not met",
                    'Dynamic_Thresholds': thresholds or {},
                })

        return violations

    def _dimension_unbalance_scores(self, all_categories: List[Dict[str, Any]]) -> Dict[str, float]:
        """Compute unbalance score per dimension: max raw concentration within any category (peer_cat_vol / sum_peers_cat_vol)."""
        return self.diagnostics_engine.dimension_unbalance_scores(all_categories)

    # New helpers: structural diagnostics and subset search
    def _compute_structural_caps_diagnostics(
        self,
        peers: List[str],
        all_categories: List[Dict[str, Any]],
        max_concentration: float,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        return self.diagnostics_engine.compute_structural_caps_diagnostics(
            peers, all_categories, max_concentration
        )

    def _search_largest_feasible_subset(
        self,
        df: pd.DataFrame,
        metric_col: str,
        dimensions: List[str],
        max_concentration: float,
        peer_volumes: Dict[str, float],
        peers: List[str],
        all_categories: List[Dict[str, Any]],
    ) -> Tuple[List[str], Optional[Dict[str, float]]]:
        self.subset_search_results.clear()
        best_dims: List[str] = []
        best_weights: Optional[Dict[str, float]] = None
        best_score: Tuple[int, float] = (0, float('inf'))
        max_tests = max(int(self.subset_search_max_tests), 1)
        
        if self.greedy_subset_search:
            # GREEDY MODE: Start with all dimensions, remove one at a time
            trial_dims = list(dimensions)
            tested = 0
            while tested < max_tests and len(trial_dims) > 0:
                tested += 1
                trial_cats, trial_peer_vols, _ = self._build_categories(df, metric_col, trial_dims)
                if not trial_cats:
                    if len(trial_dims) > 1:
                        scores = self._dimension_unbalance_scores(all_categories if all_categories else trial_cats)
                        drop_dim = max(trial_dims, key=lambda d: scores.get(d, 0.0))
                        self.subset_search_results.append({
                            'Attempt': tested,
                            'Dimensions': list(trial_dims),
                            'Count': len(trial_dims),
                            'Success': False,
                            'Max_Slack': None,
                            'Sum_Slack': None,
                            'Method': None,
                            'Note': f"No cats; dropping {drop_dim}",
                        })
                        trial_dims = [d for d in trial_dims if d != drop_dim]
                        continue
                    else:
                        break
                lp_result = self.lp_solver.solve(
                    self._build_lp_request(
                        peers=peers,
                        categories=trial_cats,
                        max_concentration=max_concentration,
                        peer_volumes=trial_peer_vols,
                    )
                )
                if lp_result and lp_result.success:
                    self.last_lp_stats = lp_result.stats
                    sol = lp_result.weights
                    stats = dict(lp_result.stats)
                else:
                    sol = None
                    stats = {}
                sum_slack = float(stats.get('sum_slack', 0.0) or 0.0) if stats else None
                max_slack = float(stats.get('max_slack', 0.0) or 0.0) if stats else None
                method = stats.get('method') if stats else None
                success = sol is not None
                note = ''
                if success and self.trigger_subset_on_slack and self._is_slack_excess(sum_slack):
                    success = False
                    note = f"Rejected due to slack {sum_slack:.6f} > {self.max_cap_slack:.6f}"
                self.subset_search_results.append({
                    'Attempt': tested,
                    'Dimensions': list(trial_dims),
                    'Count': len(trial_dims),
                    'Success': bool(success),
                    'Max_Slack': (max_slack if success else (None if note else max_slack)),
                    'Sum_Slack': (sum_slack if success else (None if note else sum_slack)),
                    'Method': method,
                    'Note': note,
                })
                if success and sol is not None:
                    score = (len(trial_dims), sum_slack)
                    if score[0] > best_score[0] or (score[0] == best_score[0] and score[1] < best_score[1]):
                        best_score = score
                        best_dims = list(trial_dims)
                        best_weights = sol
                    if len(trial_dims) == len(dimensions) and not self._is_slack_excess(sum_slack):
                        break
                    if not self._is_slack_excess(sum_slack):
                        break
                if len(trial_dims) <= 1:
                    break
                scores = self._dimension_unbalance_scores(trial_cats)
                drop_dim = max(trial_dims, key=lambda d: scores.get(d, 0.0))
                trial_dims = [d for d in trial_dims if d != drop_dim]
        else:
            # RANDOM MODE: Test random subsets starting with n-1, then n-2, etc.
            import random
            import itertools
            
            tested = 0
            n = len(dimensions)
            
            # Try subsets in decreasing size order: n-1, n-2, ..., 1
            for subset_size in range(n - 1, 0, -1):
                if tested >= max_tests:
                    break
                
                # Generate all combinations of this size
                all_combinations = list(itertools.combinations(dimensions, subset_size))
                
                # Shuffle to test randomly
                random.shuffle(all_combinations)
                
                # Test combinations until we find a feasible one or exhaust max_tests
                for combo in all_combinations:
                    if tested >= max_tests:
                        break
                    
                    tested += 1
                    trial_dims = list(combo)
                    trial_cats, trial_peer_vols, _ = self._build_categories(df, metric_col, trial_dims)
                    
                    if not trial_cats:
                        self.subset_search_results.append({
                            'Attempt': tested,
                            'Dimensions': list(trial_dims),
                            'Count': len(trial_dims),
                            'Success': False,
                            'Max_Slack': None,
                            'Sum_Slack': None,
                            'Method': None,
                            'Note': 'No categories found',
                        })
                        continue
                    
                    lp_result = self.lp_solver.solve(
                        self._build_lp_request(
                            peers=peers,
                            categories=trial_cats,
                            max_concentration=max_concentration,
                            peer_volumes=trial_peer_vols,
                        )
                    )
                    if lp_result and lp_result.success:
                        self.last_lp_stats = lp_result.stats
                        sol = lp_result.weights
                        stats = dict(lp_result.stats)
                    else:
                        sol = None
                        stats = {}
                    sum_slack = float(stats.get('sum_slack', 0.0) or 0.0) if stats else None
                    max_slack = float(stats.get('max_slack', 0.0) or 0.0) if stats else None
                    method = stats.get('method') if stats else None
                    success = sol is not None
                    note = ''
                    
                    if success and self.trigger_subset_on_slack and self._is_slack_excess(sum_slack):
                        success = False
                        note = f"Rejected due to slack {sum_slack:.6f} > {self.max_cap_slack:.6f}"
                    
                    self.subset_search_results.append({
                        'Attempt': tested,
                        'Dimensions': list(trial_dims),
                        'Count': len(trial_dims),
                        'Success': bool(success),
                        'Max_Slack': (max_slack if success else (None if note else max_slack)),
                        'Sum_Slack': (sum_slack if success else (None if note else sum_slack)),
                        'Method': method,
                        'Note': note,
                    })
                    
                    if success and sol is not None:
                        score = (len(trial_dims), sum_slack)
                        if score[0] > best_score[0] or (score[0] == best_score[0] and score[1] < best_score[1]):
                            best_score = score
                            best_dims = list(trial_dims)
                            best_weights = sol
                        
                        # If we found a feasible solution at this size, we're done
                        # (no need to test smaller subsets)
                        if not self._is_slack_excess(sum_slack):
                            logger.info(f"Random search found feasible subset of size {subset_size} after {tested} attempts")
                            return best_dims, best_weights
        
        return best_dims, best_weights

    def _solve_per_dimension_weights(
        self,
        df: pd.DataFrame,
        metric_col: str,
        dimensions: List[str],
        peers: List[str],
        max_concentration: float,
        weights: Optional[Dict[str, float]],
        rule_name: str
    ) -> None:
        for dimension in dimensions:
            dim_cats, dim_peer_vols, _ = self._build_categories(df, metric_col, [dimension])
            if not dim_cats:
                continue

            has_time = any('time_period' in cat for cat in dim_cats)
            time_info = f" (time-aware: {len([c for c in dim_cats if c.get('time_period')])} constraints)" if has_time else ""
            logger.info(f"Solving per-dimension weights for '{dimension}'{time_info}")

            lp_result = self.lp_solver.solve(
                self._build_lp_request(
                    peers=peers,
                    categories=dim_cats,
                    max_concentration=max_concentration,
                    peer_volumes=dim_peer_vols,
                )
            )
            if lp_result and lp_result.success:
                self.last_lp_stats = lp_result.stats
                dim_sol = lp_result.weights
            else:
                dim_sol = None
            if dim_sol is not None:
                self.per_dimension_weights[dimension] = dim_sol
                self.weight_methods[dimension] = "Per-Dimension-LP"
                logger.info(f"Per-dimension LP succeeded for '{dimension}'")
                continue

            strict_feasibility_mode = float(self.tolerance) <= float(self.COMPARISON_EPSILON)
            target_multipliers = None if strict_feasibility_mode else ({p: weights[p] for p in peers} if weights else None)
            if strict_feasibility_mode:
                logger.info(
                    "Strict tolerance mode detected for '%s'; using feasibility-first per-dimension heuristic.",
                    dimension,
                )
            heuristic_result = self.heuristic_solver.solve(
                self._build_heuristic_request(
                    peers=peers,
                    categories=dim_cats,
                    max_concentration=max_concentration,
                    peer_volumes=dim_peer_vols,
                    target_weights=target_multipliers,
                    rule_name=rule_name,
                )
            )
            if heuristic_result:
                if not heuristic_result.success:
                    logger.warning("Per-dimension heuristic solver did not converge; using best-effort weights.")
                self.per_dimension_weights[dimension] = heuristic_result.weights
                self.weight_methods[dimension] = "Per-Dimension-Bayesian"
                if target_multipliers is None:
                    logger.info(
                        "Per-dimension Bayesian optimization applied for '%s' (feasibility-first mode)",
                        dimension,
                    )
                else:
                    logger.info(
                        "Per-dimension Bayesian optimization applied for '%s' (targeting global weights)",
                        dimension,
                    )
            else:
                logger.warning(f"Per-dimension solving failed for '{dimension}'")

    def _build_weight_map_for_dimension(self, dimension: str) -> Dict[str, float]:
        weight_map: Dict[str, float] = {}
        if self.global_weights:
            for peer, info in self.global_weights.items():
                weight_map[peer] = float(info.get('multiplier', 1.0))
        if dimension in self.per_dimension_weights:
            for peer, mult in self.per_dimension_weights[dimension].items():
                weight_map[peer] = float(mult)
        return weight_map

    def _get_peer_multiplier(self, dimension_column: str, peer: str) -> float:
        if dimension_column in self.per_dimension_weights and peer in self.per_dimension_weights[dimension_column]:
            return float(self.per_dimension_weights[dimension_column][peer])
        if peer in self.global_weights:
            return float(self.global_weights[peer].get('multiplier', 1.0))
        return 1.0

    def _get_all_peers(self, entity_totals: pd.Series, time_period: Optional[Any]) -> List[str]:
        if self.consistent_weights and self.global_weights:
            return list(self.global_weights.keys())
        if time_period and time_period != "General":
            return list(set(k[0] if isinstance(k, tuple) else k for k in entity_totals.index))
        return list(entity_totals.index)

    def _store_final_weights(self, peers: List[str], peer_volumes: Dict[str, float], weights: Dict[str, float]) -> None:
        """Persist final weights into self.global_weights as dict with volume, weight, multiplier.
        Also compute Rank Changes (baseline vs adjusted shares) for reporting.
        """
        # Rescale to average 1.0 within bounds
        avg_weight = sum(weights.values()) / len(weights) if len(weights) > 0 else 1.0
        if avg_weight > 0 and len(weights) > 0:
            k_target = 1.0 / avg_weight
            k_min = max(self.min_weight / w for w in weights.values() if w > 0)
            k_max = min(self.max_weight / w for w in weights.values() if w > 0)
            k = min(max(k_target, k_min), k_max)
        else:
            k = 1.0
        for p in list(weights.keys()):
            weights[p] = max(self.min_weight, min(weights[p] * k, self.max_weight))
        
        # Calculate totals for both unbalanced and balanced volumes
        total_unbalanced_vol = sum(peer_volumes.get(p, 0.0) for p in peers) if peers else 0.0
        total_balanced_vol = sum(peer_volumes.get(p, 0.0) * weights[p] for p in peers) if peers else 0.0
        
        # Store
        self.global_weights.clear()
        for peer in peers:
            peer_vol = peer_volumes.get(peer, 0.0)
            balanced_vol = peer_vol * weights[peer]
            
            # Calculate shares
            unbalanced_share_pct = (peer_vol / total_unbalanced_vol * 100) if total_unbalanced_vol > 0 else 0
            balanced_share_pct = (balanced_vol / total_balanced_vol * 100) if total_balanced_vol > 0 else 0
            
            self.global_weights[peer] = {
                'unbalanced_volume': peer_vol,
                'unbalanced_share': unbalanced_share_pct,
                'balanced_volume': balanced_vol,
                'balanced_share': balanced_share_pct,
                'multiplier': weights[peer],
                # Keep legacy fields for backward compatibility
                'volume': peer_vol,
                'weight': balanced_share_pct
            }
        # Rank Changes (Milestone 2)
        try:
            total_base_vol = sum(peer_volumes.get(p, 0.0) for p in peers)
            base_share_pct = {p: ((peer_volumes.get(p, 0.0) / total_base_vol) * 100.0) if total_base_vol > 0 else 0.0 for p in peers}
            adj_share_pct = {p: float(self.global_weights.get(p, {}).get('weight', 0.0)) for p in peers}
            # Ranks: 1 is highest share
            base_rank_order = sorted(peers, key=lambda p: base_share_pct[p], reverse=True)
            adj_rank_order = sorted(peers, key=lambda p: adj_share_pct[p], reverse=True)
            base_rank = {p: i + 1 for i, p in enumerate(base_rank_order)}
            adj_rank = {p: i + 1 for i, p in enumerate(adj_rank_order)}
            rows = []
            for p in peers:
                rows.append({
                    'Peer': p,
                    'Base_Share_%': round(base_share_pct[p], 4),
                    'Adjusted_Share_%': round(adj_share_pct[p], 4),
                    'Base_Rank': base_rank[p],
                    'Adjusted_Rank': adj_rank[p],
                    'Delta': adj_rank[p] - base_rank[p],
                })
            df = pd.DataFrame(rows)
            self.rank_changes_df = df.sort_values(['Adjusted_Rank', 'Peer']).reset_index(drop=True)
        except Exception as e:  # pragma: no cover
            logger.warning(f"Failed to compute Rank Changes: {e}")


    def calculate_global_privacy_weights(
        self, 
        df: pd.DataFrame, 
        metric_col: str,
        dimensions: List[str]
    ) -> None:
        """Delegate global optimization workflow to the specialized optimizer."""
        start_time = perf_counter()
        self.global_weight_optimizer.calculate_global_privacy_weights(df, metric_col, dimensions)
        logger.info("Global privacy weight optimization completed in %.3fs", perf_counter() - start_time)
    
    def get_weights_dataframe(self) -> pd.DataFrame:
        """Return a dataframe of global weights and per-dimension weights for debugging."""
        rows: List[Dict[str, Any]] = []
        if self.global_weights:
            for p, rec in self.global_weights.items():
                rows.append({
                    'Scope': 'Global',
                    'Dimension': None,
                    'Method': 'Global-LP',
                    'Peer': p,
                    'Multiplier': rec.get('multiplier'),
                    'Unbalanced_Volume': rec.get('unbalanced_volume'),
                    'Unbalanced_Share_%': rec.get('unbalanced_share'),
                    'Balanced_Volume': rec.get('balanced_volume'),
                    'Balanced_Share_%': rec.get('balanced_share'),
                    # Legacy columns for backward compatibility
                    'Volume': rec.get('volume'),
                    'Weight_%': rec.get('weight')
                })
        for d, wmap in self.per_dimension_weights.items():
            method = self.weight_methods.get(d, "Unknown")
            for p, mult in wmap.items():
                global_rec = self.global_weights.get(p, {}) if self.global_weights else {}
                rows.append({
                    'Scope': 'Per-Dimension',
                    'Dimension': d,
                    'Method': method,
                    'Peer': p,
                    'Multiplier': mult,
                    'Unbalanced_Volume': global_rec.get('unbalanced_volume'),
                    'Unbalanced_Share_%': global_rec.get('unbalanced_share'),
                    'Balanced_Volume': global_rec.get('balanced_volume'),
                    'Balanced_Share_%': global_rec.get('balanced_share'),
                    # Legacy columns
                    'Volume': global_rec.get('volume'),
                    'Weight_%': global_rec.get('weight')
                })
        return pd.DataFrame(rows)

    def _weighted_percentile(self, data: List[float], weights: List[float], percentile: float) -> float:
        """
        Calculate weighted percentile.
        
        Args:
            data: List of values
            weights: List of weights corresponding to values
            percentile: Target percentile (0.0 to 1.0)
            
        Returns:
            Weighted percentile value
        """
        if not data:
            return 0.0
        
        if len(data) != len(weights):
            return float(np.percentile(data, percentile * 100.0))
            
        # Sort data and weights based on data
        sorted_indices = np.argsort(data)
        sorted_data = np.array(data)[sorted_indices]
        sorted_weights = np.array(weights)[sorted_indices]
        
        # Compute cumulative weights
        cum_weights = np.cumsum(sorted_weights)
        total_weight = cum_weights[-1]
        
        if total_weight <= 0:
             return float(np.percentile(data, percentile * 100.0))

        # Find the value
        target_weight = total_weight * percentile
        idx = np.searchsorted(cum_weights, target_weight)
        
        if idx >= len(sorted_data):
            return float(sorted_data[-1])
            
        return float(sorted_data[idx])

    def _calculate_share_metrics(
        self,
        category_df: pd.DataFrame,
        entity_totals: pd.Series,
        dimension_column: str,
        category: Any,
        metric_col: str,
        time_period: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Helper method to calculate share metrics for a category (optionally filtered by time)."""
        # Handle peer-only mode (no target entity)
        if self.target_entity is None:
            target_share = None  # No target in peer-only mode
            peer_df = category_df
        else:
            target_df = category_df[category_df[self.entity_column] == self.target_entity]
            peer_df = category_df[category_df[self.entity_column] != self.target_entity]
            # Target share
            target_category_vol = target_df[metric_col].sum()
            if time_period and time_period != "General":
                target_total_vol = float(entity_totals.get((self.target_entity, time_period), 0.0))
            else:
                target_total_vol = float(entity_totals.get(self.target_entity, 0.0))
            target_share = (target_category_vol / target_total_vol * 100.0) if target_total_vol > 0 else 0.0
        
        if len(peer_df) == 0:
            logger.warning(f"No peers found for category '{category}'" + (f" at time '{time_period}'" if time_period else ""))
            return None
        
        # Build per-peer category and totals
        # IMPORTANT: We must iterate over ALL peers (not just those in this category)
        # to ensure consistent denominators across all categories
        peer_category_volumes: Dict[str, float] = {}
        peer_totals_map: Dict[str, float] = {}
        
        all_peers = self._get_all_peers(entity_totals, time_period)
        
        for peer_entity in all_peers:
            peer_category_vol = float(peer_df[peer_df[self.entity_column] == peer_entity][metric_col].sum())
            if time_period and time_period != "General":
                peer_total_vol = float(entity_totals.get((peer_entity, time_period), 0.0))
            else:
                peer_total_vol = float(entity_totals.get(peer_entity, 0.0))
            peer_totals_map[peer_entity] = peer_total_vol
            peer_category_volumes[peer_entity] = peer_category_vol
        
        # Debug logging for denominator consistency
        if self.debug_mode and self.time_column and time_period and time_period != "General":
            logger.debug(f"Share analysis - Category={category}, Time={time_period}")
            logger.debug(f"  Peers with volume data: {set(peer_category_volumes.keys())}")
            logger.debug(f"  Peers in totals map: {set(peer_totals_map.keys())}")
            peers_with_zero_volume = [p for p in peer_totals_map.keys() if peer_category_volumes.get(p, 0.0) == 0]
            if peers_with_zero_volume:
                logger.debug(f"  Peers with zero volume in this category: {peers_with_zero_volume}")
        
        # Compute balanced average
        if self.consistent_weights:
            # Calculate weighted average share: sum(category_vol * weight) / sum(total_vol * weight)
            # Use the SAME set of peers (from peer_totals_map) for both numerator and denominator
            total_adjusted_category_volume = sum(
                peer_category_volumes.get(p, 0.0) * self._get_peer_multiplier(dimension_column, p)
                for p in peer_totals_map.keys()
            )
            total_adjusted_overall_volume = sum(
                peer_totals_map[p] * self._get_peer_multiplier(dimension_column, p)
                for p in peer_totals_map.keys()
            )
            peer_balanced_avg = (total_adjusted_category_volume / total_adjusted_overall_volume * 100.0) if total_adjusted_overall_volume > 0 else 0.0
        else:
            peer_category_total = sum(peer_category_volumes.values())
            peer_overall_total = sum(peer_totals_map.values())
            peer_balanced_avg = (peer_category_total / peer_overall_total * 100.0) if peer_overall_total > 0 else 0.0
        
        # BIC percentile from peers' category shares
        peer_shares = []
        peer_weights = []
        for p, cat_vol in peer_category_volumes.items():
            total_vol = peer_totals_map[p]
            if total_vol <= 0:
                continue
            share = (cat_vol / total_vol * 100.0)
            peer_shares.append(share)
            
            # Weight is the peer's total volume adjusted by privacy multiplier
            multiplier = self._get_peer_multiplier(dimension_column, p)
            peer_weights.append(total_vol * multiplier)

        if len(peer_shares) > 0:
            bic_value = self._weighted_percentile(peer_shares, peer_weights, self.bic_percentile)
        else:
            bic_value = 0.0
        
        # Calculate original (unweighted) peer average for debug mode
        peer_category_total = sum(peer_category_volumes.values())
        peer_overall_total = sum(peer_totals_map.values())
        original_peer_avg = (peer_category_total / peer_overall_total * 100.0) if peer_overall_total > 0 else 0.0
        
        # Build result dictionary
        result = {
            'Category': category,
        }
        
        # Add time column if applicable
        if time_period is not None:
            result[self.time_column if self.time_column else 'Time'] = time_period
        
        result['Balanced Peer Average (%)'] = round(peer_balanced_avg, 6)
        result['BIC (%)'] = round(bic_value, 6)
        
        # Add debug columns showing original metrics before privacy weighting
        if self.debug_mode:
            result['Original Peer Average (%)'] = round(original_peer_avg, 6)
            result['Original Total Volume'] = round(peer_category_total, 2)
            result['Impact (pp)'] = round(peer_balanced_avg - original_peer_avg, 6)
        
        # Add target-specific columns only if we have a target entity
        if self.target_entity is not None:
            result['Target Share (%)'] = round(target_share, 6)
            result['Distance to Peer (pp)'] = round(target_share - peer_balanced_avg, 6)
        
        return result

    def _calculate_rate_metrics(
        self,
        category_df: pd.DataFrame,
        entity_totals: pd.Series,
        dimension_column: str,
        category: Any,
        total_col: str,
        numerator_col: str,
        time_period: Optional[Any] = None
    ) -> Optional[Dict[str, Any]]:
        """Helper method to calculate rate metrics for a category (optionally filtered by time)."""
        # Handle peer-only mode (no target entity)
        if self.target_entity is None:
            target_rate = None  # No target in peer-only mode
            peer_df = category_df
        else:
            target_df = category_df[category_df[self.entity_column] == self.target_entity]
            peer_df = category_df[category_df[self.entity_column] != self.target_entity]
            # Target rate
            target_num = float(target_df[numerator_col].sum())
            target_den = float(target_df[total_col].sum())
            target_rate = (target_num / target_den * 100.0) if target_den > 0 else 0.0
        
        if len(peer_df) == 0:
            logger.warning(f"No peers found for category '{category}'" + (f" at time '{time_period}'" if time_period else ""))
            return None
        
        # Build per-peer category and totals
        # IMPORTANT: We must iterate over ALL peers (not just those in this category)
        # to ensure consistent denominators across all categories
        peer_category_nums: Dict[str, float] = {}
        peer_category_dens: Dict[str, float] = {}
        peer_totals_map: Dict[str, float] = {}
        
        all_peers = self._get_all_peers(entity_totals, time_period)
        
        for peer_entity in all_peers:
            # Use peer_df filtered to this peer (will be 0 if peer not in category)
            num = float(peer_df[peer_df[self.entity_column] == peer_entity][numerator_col].sum())
            den = float(peer_df[peer_df[self.entity_column] == peer_entity][total_col].sum())
            if time_period and time_period != "General":
                total_den = float(entity_totals.get((peer_entity, time_period), 0.0))
            else:
                total_den = float(entity_totals.get(peer_entity, 0.0))
            peer_totals_map[peer_entity] = total_den
            peer_category_nums[peer_entity] = num
            peer_category_dens[peer_entity] = den
        
        # Debug logging for denominator consistency
        if self.debug_mode and self.time_column and time_period and time_period != "General":
            logger.debug(f"Rate analysis - Category={category}, Time={time_period}")
            logger.debug(f"  Peers with denominator data: {set(peer_category_dens.keys())}")
            logger.debug(f"  Peers in totals map: {set(peer_totals_map.keys())}")
            peers_with_zero_den = [p for p in peer_totals_map.keys() if peer_category_dens.get(p, 0.0) == 0]
            if peers_with_zero_den:
                logger.debug(f"  Peers with zero denominator in this category: {peers_with_zero_den}")
        
        # Balanced peer rate
        if self.consistent_weights:
            # Calculate weighted average rate: sum(rate * weight * den) / sum(weight * den)
            # Use the SAME set of peers (from peer_totals_map) for consistency
            total_adjusted_den = sum(
                peer_category_dens.get(p, 0.0) * self._get_peer_multiplier(dimension_column, p)
                for p in peer_totals_map.keys()
            )
            peer_balanced_rate = 0.0
            for p in peer_totals_map.keys():
                # Only include peers with denominator > 0 in the weighted average
                if peer_category_dens.get(p, 0.0) > 0:
                    rate = (peer_category_nums.get(p, 0.0) / peer_category_dens[p] * 100.0)
                    adjusted_weight = (
                        peer_category_dens[p] * self._get_peer_multiplier(dimension_column, p)
                        / total_adjusted_den * 100.0
                    ) if total_adjusted_den > 0 else 0.0
                    peer_balanced_rate += (rate * adjusted_weight / 100.0)
        else:
            total_num = sum(peer_category_nums.values())
            total_den = sum(peer_category_dens.values())
            peer_balanced_rate = (total_num / total_den * 100.0) if total_den > 0 else 0.0
        
        # BIC percentile from peers' rates
        peer_rates = []
        peer_weights = []
        for p in peer_totals_map.keys():
            # Only include peers with denominator > 0
            if peer_category_dens.get(p, 0.0) > 0:
                rate = (peer_category_nums.get(p, 0.0) / peer_category_dens[p] * 100.0)
                peer_rates.append(rate)
                
                # Weight is the peer's denominator adjusted by privacy multiplier
                multiplier = self._get_peer_multiplier(dimension_column, p)
                peer_weights.append(peer_category_dens[p] * multiplier)
        
        if len(peer_rates) > 0:
            bic_value = self._weighted_percentile(peer_rates, peer_weights, self.bic_percentile)
        else:
            bic_value = 0.0
        
        # Calculate original (unweighted) peer rate for debug mode
        total_num = sum(peer_category_nums.values())
        total_den = sum(peer_category_dens.values())
        original_peer_rate = (total_num / total_den * 100.0) if total_den > 0 else 0.0
        
        # Build result dictionary
        result = {
            'Category': category,
        }
        
        # Add time column if applicable
        if time_period is not None:
            result[self.time_column if self.time_column else 'Time'] = time_period
        
        result['Balanced Peer Average (%)'] = round(peer_balanced_rate, 6)
        result['BIC (%)'] = round(bic_value, 6)
        
        # Add debug columns showing original metrics before privacy weighting
        if self.debug_mode:
            result['Original Peer Average (%)'] = round(original_peer_rate, 6)
            result['Original Total Numerator'] = round(total_num, 2)
            result['Original Total Denominator'] = round(total_den, 2)

            result['Impact (pp)'] = round(peer_balanced_rate - original_peer_rate, 6)
        
        # Add target-specific columns only if we have a target entity
        if self.target_entity is not None:
            result['Target Rate (%)'] = round(target_rate, 6)
            result['Distance to Peer (pp)'] = round(target_rate - peer_balanced_rate, 6)
        
        return result

    def analyze_dimension_share(
        self,
        df: pd.DataFrame,
        dimension_column: str,
        metric_col: str = 'transaction_count'
    ) -> pd.DataFrame:
        """Analyze a single dimension with SHARE distribution metrics."""
        logger.info("Running SHARE analysis for dimension: %s", dimension_column)
        start_time = perf_counter()
        result_df = self.analysis_calculator.analyze_dimension_share(df, dimension_column, metric_col)
        logger.info("Completed SHARE analysis for dimension %s in %.3fs", dimension_column, perf_counter() - start_time)
        return result_df

    def analyze_dimension_rate(
        self,
        df: pd.DataFrame,
        dimension_column: str,
        total_col: str,
        numerator_col: str
    ) -> pd.DataFrame:
        """Analyze a single dimension with RATE (approval/fraud)."""
        logger.info("Running RATE analysis for dimension: %s", dimension_column)
        start_time = perf_counter()
        result_df = self.analysis_calculator.analyze_dimension_rate(df, dimension_column, total_col, numerator_col)
        logger.info("Completed RATE analysis for dimension %s in %.3fs", dimension_column, perf_counter() - start_time)
        return result_df

    def build_privacy_validation_dataframe(self, df: pd.DataFrame, metric_col: str, dimensions: List[str]) -> pd.DataFrame:
        """Build detailed privacy validation dataframe showing original and balanced shares for each dimension-category-(time) combination."""
        validation_rows: List[Dict[str, Any]] = []
        all_categories, peer_volumes, _ = self._build_categories(df, metric_col, dimensions)
        peers = list(self.global_weights.keys())
        if not peers:
            per_dim_peers = set()
            for weights in self.per_dimension_weights.values():
                per_dim_peers.update(weights.keys())
            peers = sorted(per_dim_peers) if per_dim_peers else sorted(peer_volumes.keys())
        peer_count = len(peers)
        if peer_count == 0:
            return pd.DataFrame()
        constraint_stats = self._build_constraint_stats(all_categories, peers, peer_volumes) if all_categories else {}
        rule_name, max_concentration = self._get_privacy_rule(peer_count)
        weights = {p: float(self.global_weights.get(p, {}).get('multiplier', 1.0)) for p in peers}

        # Structural diagnostics are peer-level, keyed by (dimension, category, peer).
        # Expose both peer-level and category-level infeasibility markers in validation output.
        structural_peer_margin: Dict[Tuple[str, str, str], float] = {}
        structural_category_margin: Dict[Tuple[str, str], float] = {}
        if self.structural_detail_df is not None and not self.structural_detail_df.empty:
            for row in self.structural_detail_df.itertuples(index=False):
                dimension_key = str(getattr(row, 'dimension', ''))
                category_key = str(getattr(row, 'category', ''))
                peer_key = str(getattr(row, 'peer', ''))
                margin = float(getattr(row, 'margin_over_cap_pp', 0.0) or 0.0)
                if margin <= 0:
                    continue
                peer_lookup = (dimension_key, category_key, peer_key)
                cat_lookup = (dimension_key, category_key)
                structural_peer_margin[peer_lookup] = max(structural_peer_margin.get(peer_lookup, 0.0), margin)
                structural_category_margin[cat_lookup] = max(structural_category_margin.get(cat_lookup, 0.0), margin)

        for dimension in dimensions:
            dim_weights = dict(weights)
            if dimension in self.per_dimension_weights:
                dim_weights.update(self.per_dimension_weights[dimension])
            weight_source = "Per-Dimension" if dimension in self.per_dimension_weights else "Global"
            weight_method = self.weight_methods.get(dimension, "Global-LP")
            if self.time_column and self.time_column in df.columns:
                time_periods = self._get_time_periods(df)
                for time_period in time_periods:
                    time_df = df[df[self.time_column] == time_period]
                    entity_dim_agg = time_df.groupby([self.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()
                    for category in entity_dim_agg[dimension].unique():
                        cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                        structural_dim = f"{dimension}_{self.time_column}"
                        structural_cat = f"{category}_{time_period}"
                        peer_data = []
                        for peer_entity in peers:
                            peer_cat_vol = float(cat_df[cat_df[self.entity_column] == peer_entity][metric_col].sum())
                            peer_data.append({'peer': peer_entity, 'volume': peer_cat_vol})
                        total_original_vol = sum(p['volume'] for p in peer_data)
                        total_balanced_vol = sum(p['volume'] * dim_weights.get(p['peer'], 1.0) for p in peer_data)
                        balanced_shares: List[float] = []
                        for peer_info in peer_data:
                            peer_weight = dim_weights.get(peer_info['peer'], 1.0)
                            balanced_vol = peer_info['volume'] * peer_weight
                            balanced_share = (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                            balanced_shares.append(balanced_share)

                        peer_category_volumes = {p['peer']: p['volume'] for p in peer_data}
                        stats = constraint_stats.get((f"{dimension}_{self.time_column}", f"{category}_{time_period}", time_period))
                        enforce, reason, thresholds, relaxed = self._assess_additional_constraints_applicability(
                            rule_name, dimension, peer_category_volumes, stats
                        )
                        if enforce:
                            additional_passed, additional_details = self._evaluate_additional_constraints(
                                balanced_shares, rule_name, thresholds
                            )
                            threshold_detail = f" Thresholds={thresholds}" if thresholds else ""
                            additional_detail = "; ".join(additional_details) if additional_details else ""
                            additional_detail = f"{additional_detail}{threshold_detail}".strip()
                            additional_enforced = "Yes"
                        else:
                            additional_passed = True
                            additional_enforced = "No"
                            if reason == 'no_additional':
                                additional_detail = "Not applicable"
                            else:
                                additional_detail = f"Skipped ({reason})"
                        additional_relaxed = "Yes" if relaxed else "No"

                        for idx, peer_info in enumerate(peer_data):
                            peer, peer_vol = peer_info['peer'], peer_info['volume']
                            peer_weight = dim_weights.get(peer, 1.0)
                            original_share = (peer_vol / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                            balanced_vol = peer_vol * peer_weight
                            balanced_share = balanced_shares[idx]
                            is_violation = self._is_share_violation(balanced_share, max_concentration)
                            compliant = (not is_violation) and additional_passed
                            violation_margin = balanced_share - max_concentration if is_violation else 0.0
                            structural_peer_pp = structural_peer_margin.get((structural_dim, structural_cat, str(peer)), 0.0)
                            structural_category_pp = structural_category_margin.get((structural_dim, structural_cat), 0.0)
                            validation_rows.append({
                                'Dimension': dimension,
                                'Time_Period': time_period,
                                'Category': category,
                                'Peer': peer,
                                'Rule_Name': rule_name,
                                'Weight_Source': weight_source,
                                'Weight_Method': weight_method,
                                'Multiplier': peer_weight,
                                'Original_Volume': peer_vol,
                                'Original_Share_%': round(original_share, 4),
                                'Balanced_Volume': balanced_vol,
                                'Balanced_Share_%': round(balanced_share, 4),
                                'Privacy_Cap_%': max_concentration,
                                'Tolerance_%': self.tolerance,
                                'Additional_Constraints_Enforced': additional_enforced,
                                'Additional_Constraints_Relaxed': additional_relaxed,
                                'Additional_Constraints_Passed': 'Yes' if additional_passed else 'No',
                                'Additional_Constraint_Detail': additional_detail,
                                'Structural_Infeasible_Peer': 'Yes' if structural_peer_pp > 0 else 'No',
                                'Structural_Infeasible_Category': 'Yes' if structural_category_pp > 0 else 'No',
                                'Structural_Margin_Peer_pp': round(structural_peer_pp, 4) if structural_peer_pp > 0 else 0.0,
                                'Structural_Margin_Category_pp': round(structural_category_pp, 4) if structural_category_pp > 0 else 0.0,
                                'Compliant': 'Yes' if compliant else 'No',
                                'Violation_Margin_%': round(violation_margin, 4) if violation_margin > 0 else 0.0
                            })
            else:
                entity_dim_agg = df.groupby([self.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()
                for category in entity_dim_agg[dimension].unique():
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                    structural_dim = str(dimension)
                    structural_cat = str(category)
                    peer_data = []
                    for peer_entity in peers:
                        peer_cat_vol = float(cat_df[cat_df[self.entity_column] == peer_entity][metric_col].sum())
                        peer_data.append({'peer': peer_entity, 'volume': peer_cat_vol})
                    total_original_vol = sum(p['volume'] for p in peer_data)
                    total_balanced_vol = sum(p['volume'] * dim_weights.get(p['peer'], 1.0) for p in peer_data)
                    balanced_shares: List[float] = []
                    for peer_info in peer_data:
                        peer_weight = dim_weights.get(peer_info['peer'], 1.0)
                        balanced_vol = peer_info['volume'] * peer_weight
                        balanced_share = (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                        balanced_shares.append(balanced_share)

                    peer_category_volumes = {p['peer']: p['volume'] for p in peer_data}
                    stats = constraint_stats.get((dimension, category, None))
                    enforce, reason, thresholds, relaxed = self._assess_additional_constraints_applicability(
                        rule_name, dimension, peer_category_volumes, stats
                    )
                    if enforce:
                        additional_passed, additional_details = self._evaluate_additional_constraints(
                            balanced_shares, rule_name, thresholds
                        )
                        threshold_detail = f" Thresholds={thresholds}" if thresholds else ""
                        additional_detail = "; ".join(additional_details) if additional_details else ""
                        additional_detail = f"{additional_detail}{threshold_detail}".strip()
                        additional_enforced = "Yes"
                    else:
                        additional_passed = True
                        additional_enforced = "No"
                        if reason == 'no_additional':
                            additional_detail = "Not applicable"
                        else:
                            additional_detail = f"Skipped ({reason})"
                    additional_relaxed = "Yes" if relaxed else "No"

                    for idx, peer_info in enumerate(peer_data):
                        peer, peer_vol = peer_info['peer'], peer_info['volume']
                        peer_weight = dim_weights.get(peer, 1.0)
                        original_share = (peer_vol / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                        balanced_vol = peer_vol * peer_weight
                        balanced_share = balanced_shares[idx]
                        is_violation = self._is_share_violation(balanced_share, max_concentration)
                        compliant = (not is_violation) and additional_passed
                        violation_margin = balanced_share - max_concentration if is_violation else 0.0
                        structural_peer_pp = structural_peer_margin.get((structural_dim, structural_cat, str(peer)), 0.0)
                        structural_category_pp = structural_category_margin.get((structural_dim, structural_cat), 0.0)
                        validation_rows.append({
                            'Dimension': dimension,
                            'Time_Period': None,
                            'Category': category,
                            'Peer': peer,
                            'Rule_Name': rule_name,
                            'Weight_Source': weight_source,
                            'Weight_Method': weight_method,
                            'Multiplier': peer_weight,
                            'Original_Volume': peer_vol,
                            'Original_Share_%': round(original_share,  4),
                            'Balanced_Volume': balanced_vol,
                            'Balanced_Share_%': round(balanced_share, 4),
                            'Privacy_Cap_%': max_concentration,
                            'Tolerance_%': self.tolerance,
                            'Additional_Constraints_Enforced': additional_enforced,
                            'Additional_Constraints_Relaxed': additional_relaxed,
                            'Additional_Constraints_Passed': 'Yes' if additional_passed else 'No',
                            'Additional_Constraint_Detail': additional_detail,
                            'Structural_Infeasible_Peer': 'Yes' if structural_peer_pp > 0 else 'No',
                            'Structural_Infeasible_Category': 'Yes' if structural_category_pp > 0 else 'No',
                            'Structural_Margin_Peer_pp': round(structural_peer_pp, 4) if structural_peer_pp > 0 else 0.0,
                            'Structural_Margin_Category_pp': round(structural_category_pp, 4) if structural_category_pp > 0 else 0.0,
                            'Compliant': 'Yes' if compliant else 'No',
                            'Violation_Margin_%': round(violation_margin, 4) if violation_margin > 0 else 0.0
                        })
        return pd.DataFrame(validation_rows)
    
    def calculate_share_impact(
        self,
        df: pd.DataFrame,
        metric_col: str,
        dimensions: List[str],
        target_entity: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Calculate impact between raw and balanced market share.
        
        For each dimension-category(-time) combination, computes:
        - Raw share (unweighted peer group average)
        - Balanced share (privacy-constrained weighted average)
        - Impact in percentage points (balanced - raw)
        
        Parameters:
        -----------
        df : pd.DataFrame
            Input dataframe
        metric_col : str
            Column containing metric values
        dimensions : List[str]
            Dimensions to analyze
        target_entity : Optional[str]
            Target entity (uses self.target_entity if not provided)
            
        Returns:
        --------
        pd.DataFrame
            Impact details with columns: Dimension, Category, Time_Period,
            Entity, Raw_Share_%, Balanced_Share_%, Impact_PP
        """
        entity = target_entity or self.target_entity
        if not entity:
            logger.warning("No target entity specified for impact calculation")
            return pd.DataFrame()
        
        if metric_col not in df.columns:
            logger.error(f"Metric column '{metric_col}' not found in DataFrame")
            return pd.DataFrame()
        
        if df[metric_col].isna().any():
            nan_count = df[metric_col].isna().sum()
            logger.warning(f"Metric column '{metric_col}' contains {nan_count} NaN values - these rows will be excluded")
            df = df[df[metric_col].notna()].copy()
        
        if (df[metric_col] < 0).any():
            neg_count = (df[metric_col] < 0).sum()
            logger.warning(f"Metric column '{metric_col}' contains {neg_count} negative values - these rows will be excluded")
            df = df[df[metric_col] >= 0].copy()
        
        if df.empty:
            logger.warning("No valid data remaining after filtering NaN/negative values")
            return pd.DataFrame()

        impact_rows: List[Dict[str, Any]] = []
        
        for dimension in dimensions:
            # Get dimension-specific weights merged with global fallback
            dim_weights = self._build_weight_map_for_dimension(dimension)
            
            if self.time_column and self.time_column in df.columns:
                time_periods = self._get_time_periods(df)
                null_count = df[self.time_column].isna().sum()
                if null_count > 0:
                    logger.warning(f"Time column '{self.time_column}' contains {null_count} null values - excluded from time-based analysis")
                for time_period in time_periods:
                    time_df = df[df[self.time_column] == time_period]
                    entity_dim_agg = time_df.groupby([self.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()
                    
                    for category in entity_dim_agg[dimension].unique():
                        cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                        
                        # Calculate entity share
                        entity_vol = float(cat_df[cat_df[self.entity_column] == entity][metric_col].sum())
                        
                        # Raw: simple sum of all volumes
                        total_raw_vol = float(cat_df[metric_col].sum())
                        raw_share = (entity_vol / total_raw_vol * 100.0) if total_raw_vol > 0 else 0.0
                        
                        # Balanced: weighted sum of peer volumes only (excluding entity)
                        peer_cat_df = cat_df[cat_df[self.entity_column] != entity]
                        total_balanced_vol = entity_vol  # Entity counts as own weight
                        for _, row in peer_cat_df.iterrows():
                            peer = row[self.entity_column]
                            peer_vol = float(row[metric_col])
                            peer_weight = dim_weights.get(peer, 1.0)
                            total_balanced_vol += peer_vol * peer_weight
                        
                        balanced_share = (entity_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                        impact_pp = balanced_share - raw_share
                        
                        impact_rows.append({
                            'Dimension': dimension,
                            'Category': category,
                            'Time_Period': time_period,
                            'Entity': entity,
                            'Entity_Volume': entity_vol,
                            'Raw_Total_Volume': total_raw_vol,
                            'Balanced_Total_Volume': total_balanced_vol,
                            'Raw_Share_%': round(raw_share, 4),
                            'Balanced_Share_%': round(balanced_share, 4),
                            'Impact_PP': round(impact_pp, 4),
                        })
            else:
                entity_dim_agg = df.groupby([self.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()
                
                for category in entity_dim_agg[dimension].unique():
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                    
                    entity_vol = float(cat_df[cat_df[self.entity_column] == entity][metric_col].sum())
                    total_raw_vol = float(cat_df[metric_col].sum())
                    raw_share = (entity_vol / total_raw_vol * 100.0) if total_raw_vol > 0 else 0.0
                    
                    peer_cat_df = cat_df[cat_df[self.entity_column] != entity]
                    total_balanced_vol = entity_vol
                    for _, row in peer_cat_df.iterrows():
                        peer = row[self.entity_column]
                        peer_vol = float(row[metric_col])
                        peer_weight = dim_weights.get(peer, 1.0)
                        total_balanced_vol += peer_vol * peer_weight
                    
                    balanced_share = (entity_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                    impact_pp = balanced_share - raw_share
                    
                    impact_rows.append({
                        'Dimension': dimension,
                        'Category': category,
                        'Time_Period': None,
                        'Entity': entity,
                        'Entity_Volume': entity_vol,
                        'Raw_Total_Volume': total_raw_vol,
                        'Balanced_Total_Volume': total_balanced_vol,
                        'Raw_Share_%': round(raw_share, 4),
                        'Balanced_Share_%': round(balanced_share, 4),
                        'Impact_PP': round(impact_pp, 4),
                    })
        
        return pd.DataFrame(impact_rows)

    def calculate_share_distortion(
        self,
        df: pd.DataFrame,
        metric_col: str,
        dimensions: List[str],
        target_entity: Optional[str] = None
    ) -> pd.DataFrame:
        """Deprecated wrapper for calculate_share_impact."""
        self._warn_deprecated("calculate_share_distortion", "calculate_share_impact")
        df_impact = self.calculate_share_impact(df, metric_col, dimensions, target_entity)
        if 'Impact_PP' in df_impact.columns:
            df_impact['Distortion_PP'] = df_impact['Impact_PP']
        return df_impact
    
    def calculate_rate_impact(
        self,
        df: pd.DataFrame,
        total_col: str,
        numerator_cols: Dict[str, str],
        dimensions: List[str]
    ) -> pd.DataFrame:
        """
        Calculate impact on rate metrics (raw vs balanced rates).
        
        For each rate and dimension-category(-time) combination, computes:
        - Raw rate (simple weighted average by volume)
        - Balanced rate (privacy-constrained weighted average)
        - Impact in percentage points
        
        Parameters:
        -----------
        df : pd.DataFrame
            Input dataframe
        total_col : str
            Column containing totals/denominators
        numerator_cols : Dict[str, str]
            Mapping of rate name to numerator column
        dimensions : List[str]
            Dimensions to analyze
            
        Returns:
        --------
        pd.DataFrame
            Impact details with columns per rate
        """
        impact_rows: List[Dict[str, Any]] = []
        
        for dimension in dimensions:
            dim_weights = self._build_weight_map_for_dimension(dimension)
            
            if self.time_column and self.time_column in df.columns:
                time_periods = self._get_time_periods(df)
                null_count = df[self.time_column].isna().sum()
                if null_count > 0:
                    logger.warning(f"Time column '{self.time_column}' contains {null_count} null values - excluded from time-based analysis")
                for time_period in time_periods:
                    time_df = df[df[self.time_column] == time_period]
                    
                    all_num_cols = [total_col] + list(numerator_cols.values())
                    entity_dim_agg = time_df.groupby([self.entity_column, dimension]).agg(
                        {col: 'sum' for col in all_num_cols}
                    ).reset_index()
                    
                    for category in entity_dim_agg[dimension].unique():
                        cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                        if self.target_entity:
                            peer_cat_df = cat_df[cat_df[self.entity_column] != self.target_entity]
                        else:
                            peer_cat_df = cat_df
                        
                        row_data = {
                            'Dimension': dimension,
                            'Category': category,
                            'Time_Period': time_period,
                        }
                        
                        for rate_name, num_col in numerator_cols.items():
                            # Raw rate: sum of numerators / sum of denominators
                            total_num = float(peer_cat_df[num_col].sum())
                            total_denom = float(peer_cat_df[total_col].sum())
                            raw_rate = (total_num / total_denom * 100.0) if total_denom > 0 else 0.0
                            
                            # Balanced rate: weighted sums
                            balanced_num = 0.0
                            balanced_denom = 0.0
                            for _, prow in peer_cat_df.iterrows():
                                peer = prow[self.entity_column]
                                w = dim_weights.get(peer, 1.0)
                                balanced_num += float(prow[num_col]) * w
                                balanced_denom += float(prow[total_col]) * w
                            
                            balanced_rate = (balanced_num / balanced_denom * 100.0) if balanced_denom > 0 else 0.0
                            impact_pp = balanced_rate - raw_rate
                            
                            row_data[f'{rate_name}_Raw_%'] = round(raw_rate, 4)
                            row_data[f'{rate_name}_Balanced_%'] = round(balanced_rate, 4)
                            row_data[f'{rate_name}_Impact_PP'] = round(impact_pp, 4)
                        
                        impact_rows.append(row_data)
            else:
                all_num_cols = [total_col] + list(numerator_cols.values())
                entity_dim_agg = df.groupby([self.entity_column, dimension]).agg(
                    {col: 'sum' for col in all_num_cols}
                ).reset_index()
                
                for category in entity_dim_agg[dimension].unique():
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                    if self.target_entity:
                        peer_cat_df = cat_df[cat_df[self.entity_column] != self.target_entity]
                    else:
                        peer_cat_df = cat_df
                    
                    row_data = {
                        'Dimension': dimension,
                        'Category': category,
                        'Time_Period': None,
                    }
                    
                    for rate_name, num_col in numerator_cols.items():
                        total_num = float(peer_cat_df[num_col].sum())
                        total_denom = float(peer_cat_df[total_col].sum())
                        raw_rate = (total_num / total_denom * 100.0) if total_denom > 0 else 0.0
                        
                        balanced_num = 0.0
                        balanced_denom = 0.0
                        for _, prow in peer_cat_df.iterrows():
                            peer = prow[self.entity_column]
                            w = dim_weights.get(peer, 1.0)
                            balanced_num += float(prow[num_col]) * w
                            balanced_denom += float(prow[total_col]) * w
                        
                        balanced_rate = (balanced_num / balanced_denom * 100.0) if balanced_denom > 0 else 0.0
                        impact_pp = balanced_rate - raw_rate
                        
                        row_data[f'{rate_name}_Raw_%'] = round(raw_rate, 4)
                        row_data[f'{rate_name}_Balanced_%'] = round(balanced_rate, 4)
                        row_data[f'{rate_name}_Impact_PP'] = round(impact_pp, 4)
                    
                    impact_rows.append(row_data)
        
        return pd.DataFrame(impact_rows)

    def calculate_rate_weight_effect(
        self,
        df: pd.DataFrame,
        total_col: str,
        numerator_cols: Dict[str, str],
        dimensions: List[str]
    ) -> pd.DataFrame:
        """Deprecated wrapper for calculate_rate_impact."""
        self._warn_deprecated("calculate_rate_weight_effect", "calculate_rate_impact")
        df_impact = self.calculate_rate_impact(df, total_col, numerator_cols, dimensions)
        # Add legacy columns for backward compatibility
        for col in list(df_impact.columns):
            if col.endswith('_Impact_PP'):
                legacy_col = col.replace('_Impact_PP', '_Weight_Effect_PP')
                df_impact[legacy_col] = df_impact[col]
        return df_impact
    
    def calculate_impact_summary(
        self,
        impact_df: pd.DataFrame,
        analysis_type: str = 'share'
    ) -> pd.DataFrame:
        """
        Calculate summary statistics for impact.
        
        Computes mean, min, max, std for each:
        - Dimension
        - Category
        - Time period (if present)
        - Overall
        
        Parameters:
        -----------
        impact_df : pd.DataFrame
            Output from calculate_share_impact() or calculate_rate_impact()
        analysis_type : str
            'share' or 'rate' - determines which columns to summarize
            
        Returns:
        --------
        pd.DataFrame
            Summary statistics with aggregation level column
        """
        if impact_df.empty:
            return pd.DataFrame()
        
        summary_rows: List[Dict[str, Any]] = []
        
        if analysis_type == 'share':
            metric_col = 'Impact_PP'
            if metric_col not in impact_df.columns and 'Distortion_PP' in impact_df.columns:
                metric_col = 'Distortion_PP'  # Backward compatibility
            if metric_col not in impact_df.columns:
                logger.warning(f"Column {metric_col} not found in impact dataframe")
                return pd.DataFrame()
            
            # Overall summary
            summary_rows.append({
                'Aggregation': 'Overall',
                'Level': 'All Data',
                'Mean_Impact_PP': round(impact_df[metric_col].mean(), 4),
                'Min_Impact_PP': round(impact_df[metric_col].min(), 4),
                'Max_Impact_PP': round(impact_df[metric_col].max(), 4),
                'Std_Impact_PP': round(impact_df[metric_col].std(), 4) if len(impact_df) > 1 else 0.0,
                'Count': len(impact_df),
            })
            
            # By dimension
            for dim in impact_df['Dimension'].unique():
                dim_df = impact_df[impact_df['Dimension'] == dim]
                summary_rows.append({
                    'Aggregation': 'By Dimension',
                    'Level': dim,
                    'Mean_Impact_PP': round(dim_df[metric_col].mean(), 4),
                    'Min_Impact_PP': round(dim_df[metric_col].min(), 4),
                    'Max_Impact_PP': round(dim_df[metric_col].max(), 4),
                    'Std_Impact_PP': round(dim_df[metric_col].std(), 4) if len(dim_df) > 1 else 0.0,
                    'Count': len(dim_df),
                })
            
            # By time (if present)
            if 'Time_Period' in impact_df.columns and impact_df['Time_Period'].notna().any():
                for time_period in impact_df['Time_Period'].dropna().unique():
                    time_df = impact_df[impact_df['Time_Period'] == time_period]
                    summary_rows.append({
                        'Aggregation': 'By Time Period',
                        'Level': str(time_period),
                        'Mean_Impact_PP': round(time_df[metric_col].mean(), 4),
                        'Min_Impact_PP': round(time_df[metric_col].min(), 4),
                        'Max_Impact_PP': round(time_df[metric_col].max(), 4),
                        'Std_Impact_PP': round(time_df[metric_col].std(), 4) if len(time_df) > 1 else 0.0,
                        'Count': len(time_df),
                    })
        else:
            # Rate analysis - summarize impact columns
            effect_cols = [col for col in impact_df.columns if col.endswith('_Impact_PP')]
            if not effect_cols:
                # Backward compatibility
                effect_cols = [col for col in impact_df.columns if col.endswith('_Weight_Effect_PP')]
            if not effect_cols:
                logger.warning("No impact columns found in impact dataframe")
                return pd.DataFrame()
            
            for rate_col in effect_cols:
                rate_name = rate_col.replace('_Impact_PP', '').replace('_Weight_Effect_PP', '')
                
                # Overall summary
                summary_rows.append({
                    'Aggregation': 'Overall',
                    'Level': 'All Data',
                    'Rate': rate_name,
                    'Mean_Impact_PP': round(impact_df[rate_col].mean(), 4),
                    'Min_Impact_PP': round(impact_df[rate_col].min(), 4),
                    'Max_Impact_PP': round(impact_df[rate_col].max(), 4),
                    'Std_Impact_PP': round(impact_df[rate_col].std(), 4) if len(impact_df) > 1 else 0.0,
                    'Count': len(impact_df),
                })
                
                # By dimension
                for dim in impact_df['Dimension'].unique():
                    dim_df = impact_df[impact_df['Dimension'] == dim]
                    summary_rows.append({
                        'Aggregation': 'By Dimension',
                        'Level': dim,
                        'Rate': rate_name,
                        'Mean_Impact_PP': round(dim_df[rate_col].mean(), 4),
                        'Min_Impact_PP': round(dim_df[rate_col].min(), 4),
                        'Max_Impact_PP': round(dim_df[rate_col].max(), 4),
                        'Std_Impact_PP': round(dim_df[rate_col].std(), 4) if len(dim_df) > 1 else 0.0,
                        'Count': len(dim_df),
                    })
        
        return pd.DataFrame(summary_rows)

    def calculate_distortion_summary(
        self,
        distortion_df: pd.DataFrame,
        analysis_type: str = 'share'
    ) -> pd.DataFrame:
        """Backward-compatible wrapper for impact summary."""
        self._warn_deprecated("calculate_distortion_summary", "calculate_impact_summary")
        return self.calculate_impact_summary(distortion_df, analysis_type)

    DEPRECATION_REMOVE_VERSION = "4.0"
