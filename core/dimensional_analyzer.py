"""
DimensionalAnalyzer - Automatic dimensional breakdown analysis.

Analyzes metrics across all dimensional columns in the dataset,
following Mastercard privacy rules for balanced benchmarking.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging

from .privacy_validator import PrivacyValidator

# Optional SciPy LP solver
try:
    from scipy.optimize import linprog  # type: ignore
    _SCIPY_AVAILABLE = True
except Exception:  # pragma: no cover - SciPy not installed
    linprog = None  # type: ignore
    _SCIPY_AVAILABLE = False

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
        self.slack_subset_triggered: bool = False
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
    
    def calculate_global_weights(self, df: pd.DataFrame, metric_col: str) -> None:
        """
        DEPRECATED: Use calculate_global_privacy_weights instead.
        This method is kept for backward compatibility.
        """
        logger.warning("calculate_global_weights is deprecated. Use calculate_global_privacy_weights instead.")
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

    def _solve_global_weights_lp(
        self,
        peers: List[str],
        all_categories: List[Dict[str, Any]],
        max_concentration: float,
        peer_volumes: Dict[str, float]
    ) -> Optional[Dict[str, float]]:
        """
        Solve for global weight multipliers using Linear Programming to strictly enforce
        per-category share caps: m_p * v_{p,c} <= cap * sum_j m_j * v_{j,c}.
        Objective penalizes deviation from 1.0 (via L1 with t vars) and rank inversions
        relative to baseline peer order (by total share), with strength rank_preservation_strength.
        Now includes nonnegative slack variables on each share-cap constraint, penalized in the
        objective, to incorporate tolerance directly within the LP.
        Returns a dict of peer -> multiplier if solved, else None.
        """
        if not _SCIPY_AVAILABLE:
            logger.info("SciPy not available, skipping LP solver and using heuristic fallback.")
            return None

        P = len(peers)
        if P == 0:
            return {}
        peer_index = {p: i for i, p in enumerate(peers)}

        # Build category vectors v_c in R^P
        # Key by (dimension, category)
        cat_keys: List[Tuple[str, Any]] = []
        cat_vectors: List[np.ndarray] = []
        cat_seen = set()
        for cat in all_categories:
            key = (cat['dimension'], cat['category'])
            if key in cat_seen:
                continue
            cat_seen.add(key)
            # Assemble vector for this category
            v = np.zeros(P, dtype=float)
            for c in all_categories:
                if c['dimension'] == key[0] and c['category'] == key[1]:
                    idx = peer_index[c['peer']]
                    v[idx] = float(c['category_volume'])
            if v.sum() > 0:
                cat_keys.append(key)
                cat_vectors.append(v)

        if not cat_vectors:
            logger.warning("No category volumes found for LP solver.")
            return None

        cap = max_concentration / 100.0
        # Baseline shares (overall) for rank order
        peer_vol_arr = np.array([peer_volumes.get(p, 0.0) for p in peers], dtype=float)
        total_vol = float(peer_vol_arr.sum())
        base_shares = peer_vol_arr / total_vol if total_vol > 0 else np.ones(P, dtype=float) / max(P, 1)
        # Create ordered pairs (i,j) where base_shares[i] >= base_shares[j] and i<j
        pair_indices: List[Tuple[int, int]] = []
        order = np.argsort(-base_shares)  # descending
        # To avoid O(P^2) duplicates, build pairs by rank order sequence
        for a in range(P):
            i = int(order[a])
            for b in range(a + 1, P):
                j = int(order[b])
                pair_indices.append((i, j))
        K = len(pair_indices)

        # Number of share-cap constraints (one per category per peer)
        num_cap_constraints = len(cat_vectors) * P

        # Variables: [m (P), t_plus (P), t_minus (P), s_cap (num_cap_constraints), s_rank (K)]
        n_vars = 3 * P + num_cap_constraints + K
        
        # Objective: minimize sum_p (t_plus_p + t_minus_p) + lambda_cap * sum s_cap + lambda_rank * sum s_rank
        lambda_rank = float(self.rank_preservation_strength)
        # Penalty for cap slacks: scale by inverse of tolerance so higher tolerance allows more slack
        base_lambda_cap = float(100.0 / max(self.tolerance, 1e-6))
        
        # Calculate volume-weighted slack penalties if enabled
        if self.volume_weighted_penalties:
            # Calculate category volumes
            category_volumes = []
            for v in cat_vectors:
                cat_vol = float(np.dot(v, peer_vol_arr))
                category_volumes.append(cat_vol)
            
            total_category_vol = sum(category_volumes)
            
            # Build volume-weighted penalties for each constraint
            slack_penalties = []
            for cat_idx, cat_vol in enumerate(category_volumes):
                # Volume weight: (volume / total_volume) ^ exponent
                vol_weight = (cat_vol / total_category_vol) ** self.volume_weighting_exponent if total_category_vol > 0 else 1.0
                # Apply volume weight to base penalty for all peers in this category
                for p_idx in range(P):
                    penalty = base_lambda_cap * vol_weight
                    slack_penalties.append(penalty)
            
            slack_penalty_array = np.array(slack_penalties, dtype=float)
        else:
            # Uniform penalties (original behavior)
            slack_penalty_array = np.full(num_cap_constraints, base_lambda_cap, dtype=float)
        
        c = np.concatenate([
            np.zeros(P, dtype=float),                              # m
            np.ones(P, dtype=float),                               # t_plus
            np.ones(P, dtype=float),                               # t_minus
            slack_penalty_array,                                   # s_cap (volume-weighted if enabled)
            np.full(K, lambda_rank, dtype=float)                   # s_rank
        ])

        A_ub_rows: List[np.ndarray] = []
        b_ub: List[float] = []

        # Share cap constraints for each category and each peer, with slack s_cap >= 0
        cap_idx = 0
        for v in cat_vectors:
            for p_idx in range(P):
                coeff_m = (-cap) * v.copy()
                coeff_m[p_idx] += v[p_idx]  # (1-cap) * v_p
                row = np.zeros(n_vars, dtype=float)
                row[0:P] = coeff_m
                # assign slack variable for this constraint (subtract to relax): a^T m - s_cap <= 0
                row[3 * P + cap_idx] = -1.0
                A_ub_rows.append(row)
                b_ub.append(0.0)
                cap_idx += 1

        # Absolute deviation constraints: t_plus >= m - 1 and t_minus >= 1 - m
        # 1) m_p - t_plus_p <= 1
        for p_idx in range(P):
            row = np.zeros(n_vars, dtype=float)
            row[p_idx] = 1.0
            row[P + p_idx] = -1.0
            A_ub_rows.append(row)
            b_ub.append(1.0)
        # 2) -m_p - t_minus_p <= -1  (equivalently m_p + t_minus_p >= 1)
        for p_idx in range(P):
            row = np.zeros(n_vars, dtype=float)
            row[p_idx] = -1.0
            row[2 * P + p_idx] = -1.0
            A_ub_rows.append(row)
            b_ub.append(-1.0)

        # Rank preservation soft constraints: A_j - A_i <= s_ij, where A = diag(V) m
        # For each pair (i,j) in rank order
        for k, (i, j) in enumerate(pair_indices):
            row = np.zeros(n_vars, dtype=float)
            # coefficients on m: V_j for m_j, -V_i for m_i
            row[i] = -peer_vol_arr[i]
            row[j] = peer_vol_arr[j]
            # s_rank variable position (after s_cap block)
            row[3 * P + num_cap_constraints + k] = 1.0
            A_ub_rows.append(row)
            b_ub.append(0.0)

        A_ub = np.vstack(A_ub_rows) if A_ub_rows else None
        b_ub_arr = np.array(b_ub, dtype=float) if b_ub else None

        # Bounds
        bounds: List[Tuple[float, Optional[float]]] = []
        # m bounds
        for _ in range(P):
            bounds.append((self.min_weight, self.max_weight))
        # t_plus and t_minus bounds (>=0)
        for _ in range(2 * P):
            bounds.append((0.0, None))
        # s_cap bounds (>=0)
        for _ in range(num_cap_constraints):
            bounds.append((0.0, None))
        # s_rank bounds (>=0)
        for _ in range(K):
            bounds.append((0.0, None))

        # Solve LP with method fallback and capture stats
        res = None
        solved_method = None
        for method in ['highs', 'highs-ds', 'highs-ipm']:
            try:
                res = linprog(c=c, A_ub=A_ub, b_ub=b_ub_arr, A_eq=None, b_eq=None, bounds=bounds, method=method)  # type: ignore
                if res is not None and res.success:
                    solved_method = method
                    break
            except Exception as e:  # pragma: no cover
                logger.warning(f"LP solver error with method {method}: {e}")

        if res is None or not res.success:
            logger.warning("LP solver failed or found no feasible solution; falling back to heuristic.")
            return None

        x = res.x
        m = x[0:P].copy()
        # Extract slack summaries for diagnostics
        s_cap_used = x[3 * P: 3 * P + num_cap_constraints] if num_cap_constraints > 0 else np.array([])
        
        # Convert slack to percentage: normalize by total category volumes
        # Each slack corresponds to a (category, peer) constraint
        total_category_volume = sum(v.sum() for v in cat_vectors)
        max_slack_abs = float(s_cap_used.max()) if s_cap_used.size > 0 else 0.0
        sum_slack_abs = float(s_cap_used.sum()) if s_cap_used.size > 0 else 0.0
        
        # Convert to percentage of total volume
        max_slack_pct = (max_slack_abs / total_category_volume * 100.0) if total_category_volume > 0 else 0.0
        sum_slack_pct = (sum_slack_abs / total_category_volume * 100.0) if total_category_volume > 0 else 0.0
        
        if s_cap_used.size > 0:
            # Report the base lambda (or average if volume-weighted)
            avg_lambda = base_lambda_cap if not self.volume_weighted_penalties else float(slack_penalty_array.mean())
            logger.info(f"LP used cap slacks: max={max_slack_pct:.4f}%, sum={sum_slack_pct:.4f}% (penalized with lambda={avg_lambda:.2f})")
        
        # Save stats for reporting (store both absolute and percentage)
        self.last_lp_stats = {
            'method': solved_method or 'highs',
            'max_slack': max_slack_pct,  # Now in percentage
            'sum_slack': sum_slack_pct,  # Now in percentage
            'max_slack_abs': max_slack_abs,  # Keep absolute for debugging
            'sum_slack_abs': sum_slack_abs,  # Keep absolute for debugging
            'lambda_cap': base_lambda_cap,  # Base penalty (before volume weighting)
            'volume_weighted': self.volume_weighted_penalties,
            'num_vars': n_vars,
            'num_constraints': len(b_ub),
            'num_categories': len(cat_vectors),
            'peers': P,
        }

        # Optional rescale to bring average near 1.0 without violating bounds
        avg = float(m.mean()) if P > 0 else 1.0
        if avg > 0:
            k_target = 1.0 / avg
            # Feasible k within bounds
            k_min = max(self.min_weight / mi for mi in m if mi > 0)
            k_max = min(self.max_weight / mi for mi in m if mi > 0)
            k = min(max(k_target, k_min), k_max)
            m = m * k
            m = np.clip(m, self.min_weight, self.max_weight)

        return {peer: float(m[peer_index[peer]]) for peer in peers}

    def _build_categories(self, df: pd.DataFrame, metric_col: str, dimensions: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, float], List[str]]:
        """Aggregate by entity and dimension categories for the given dimensions."""
        if self.time_column and self.consistent_weights:
            return self._build_time_aware_categories(df, metric_col, dimensions)
        
        all_categories: List[Dict[str, Any]] = []
        for dim in dimensions:
            entity_dim_agg = df.groupby([self.entity_column, dim]).agg({metric_col: 'sum'}).reset_index()
            entity_totals = entity_dim_agg.groupby(self.entity_column)[metric_col].sum()
            categories = entity_dim_agg[dim].unique()
            for category in categories:
                category_df = entity_dim_agg[entity_dim_agg[dim] == category].copy()
                # In peer-only mode, include all entities; otherwise exclude target
                if self.target_entity is not None:
                    peer_df = category_df[category_df[self.entity_column] != self.target_entity]
                else:
                    peer_df = category_df
                for peer_entity in peer_df[self.entity_column].unique():
                    peer_category_vol = peer_df[peer_df[self.entity_column] == peer_entity][metric_col].sum()
                    peer_total_vol = entity_totals[peer_entity]
                    peer_share_pct = (peer_category_vol / peer_total_vol * 100) if peer_total_vol > 0 else 0
                    all_categories.append({
                        'peer': peer_entity,
                        'dimension': dim,
                        'category': category,
                        'volume': peer_total_vol,
                        'category_volume': peer_category_vol,
                        'share_pct': peer_share_pct
                    })
        peers = list(set([c['peer'] for c in all_categories]))
        peer_volumes: Dict[str, float] = {}
        for cat in all_categories:
            if cat['peer'] not in peer_volumes:
                peer_volumes[cat['peer']] = cat['volume']
        return all_categories, peer_volumes, peers

    def _build_time_aware_categories(self, df: pd.DataFrame, metric_col: str, dimensions: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, float], List[str]]:
        """
        Build categories that include time-aware constraints for consistent weights.
        
        When time_column is specified with consistent_weights=True, this method creates
        constraints for:
        1. Total monthly volumes (privacy rule for each month)
        2. Monthly category volumes (privacy rule for each month-category combination)
        
        The same weights must satisfy privacy rules across all these combinations.
        """
        if not self.time_column:
            return self._build_categories(df, metric_col, dimensions)
            
        if self.time_column not in df.columns:
            logger.warning(f"Time column '{self.time_column}' not found in data. Falling back to standard aggregation.")
            return self._build_categories(df, metric_col, dimensions)
            
        logger.info(f"Building time-aware categories using time column: {self.time_column}")
        
        all_categories: List[Dict[str, Any]] = []
        
        # Get all unique time periods
        time_periods = sorted(df[self.time_column].unique())
        logger.info(f"Found {len(time_periods)} time periods: {time_periods}")
        
        # 1. Monthly volume constraints: privacy rules for total volume per month
        for time_period in time_periods:
            time_df = df[df[self.time_column] == time_period]
            entity_totals = time_df.groupby(self.entity_column)[metric_col].sum()
            # In peer-only mode, include all entities; otherwise exclude target
            if self.target_entity is not None:
                peer_totals = entity_totals[entity_totals.index != self.target_entity]
            else:
                peer_totals = entity_totals
            
            for peer_entity in peer_totals.index:
                peer_monthly_vol = peer_totals[peer_entity]
                # Add as a "virtual category" for monthly volume constraints
                all_categories.append({
                    'peer': peer_entity,
                    'dimension': f'_TIME_TOTAL_{self.time_column}',
                    'category': time_period,
                    'volume': float(peer_totals.sum()),  # Total peer volume for this month
                    'category_volume': peer_monthly_vol,
                    'share_pct': (peer_monthly_vol / peer_totals.sum() * 100) if peer_totals.sum() > 0 else 0,
                    'time_period': time_period,  # Add explicit time_period field
                    'original_dimension': '_TIME_TOTAL',  # Special marker for time totals
                    'original_category': time_period  # Category is the time period itself
                })
        
        # 2. Monthly category constraints: privacy rules for each month-dimension-category combination  
        for time_period in time_periods:
            time_df = df[df[self.time_column] == time_period]
            for dim in dimensions:
                if dim == self.time_column:
                    continue  # Skip the time column itself as a regular dimension
                
                # Aggregate by entity and dimension for this time period
                entity_dim_agg = time_df.groupby([self.entity_column, dim]).agg({metric_col: 'sum'}).reset_index()
                categories = entity_dim_agg[dim].unique()
                
                for category in categories:
                    category_df = entity_dim_agg[entity_dim_agg[dim] == category].copy()
                    # In peer-only mode, include all entities; otherwise exclude target
                    if self.target_entity is not None:
                        peer_df = category_df[category_df[self.entity_column] != self.target_entity]
                    else:
                        peer_df = category_df
                    
                    # Calculate total volume for this time-category combination (for share calculation)
                    total_time_cat_vol = peer_df[metric_col].sum()
                    
                    for peer_entity in peer_df[self.entity_column].unique():
                        peer_category_vol = peer_df[peer_df[self.entity_column] == peer_entity][metric_col].sum()
                        
                        # Add as a time-aware category constraint
                        all_categories.append({
                            'peer': peer_entity,
                            'dimension': f'{dim}_{self.time_column}',  # Combined dimension name
                            'category': f'{category}_{time_period}',  # Combined category name
                            'volume': total_time_cat_vol,  # Total volume for this time-category
                            'category_volume': peer_category_vol,
                            'share_pct': (peer_category_vol / total_time_cat_vol * 100) if total_time_cat_vol > 0 else 0,
                            'time_period': time_period,  # Add explicit time_period field for validation
                            'original_dimension': dim,  # Add original dimension name
                            'original_category': category  # Add original category name
                        })
        
        # Calculate peer volumes (aggregate across all time periods)
        peer_volumes: Dict[str, float] = {}
        entity_totals = df.groupby(self.entity_column)[metric_col].sum()
        # In peer-only mode, include all entities; otherwise exclude target
        if self.target_entity is not None:
            peer_totals = entity_totals[entity_totals.index != self.target_entity]
        else:
            peer_totals = entity_totals
        for peer_entity in peer_totals.index:
            peer_volumes[peer_entity] = float(peer_totals[peer_entity])
            
        peers = list(peer_volumes.keys())
        
        logger.info(f"Built {len(all_categories)} time-aware category constraints for {len(peers)} peers across {len(time_periods)} time periods")
        
        return all_categories, peer_volumes, peers

    def _get_privacy_rule(self, peer_count: int) -> Tuple[str, float]:
        """Select privacy rule and max concentration for a given peer count."""
        rule_name = PrivacyValidator.select_rule(peer_count)
        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
        max_concentration = float(rule_cfg.get('max_concentration', 50.0))
        return rule_name, max_concentration

    # Constants
    VIOLATION_PENALTY_WEIGHT = 100.0
    COMPARISON_EPSILON = 1e-6

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

        if max_excess > 1e-3:
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
        if abs(new_weight - current) < 1e-9:
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

    def _build_constraint_stats(
        self,
        dim_categories: List[Dict[str, Any]],
        peers: List[str],
        peer_volumes: Dict[str, float]
    ) -> Dict[Tuple[str, Any, Optional[Any]], Dict[str, float]]:
        overall_total = float(sum(peer_volumes.values()))
        dim_time_totals: Dict[Tuple[str, Optional[Any]], float] = {}
        category_totals: Dict[Tuple[str, Any, Optional[Any]], float] = {}
        peer_sets: Dict[Tuple[str, Any, Optional[Any]], set] = {}
        volumes_by_key: Dict[Tuple[str, Any, Optional[Any]], List[float]] = {}

        for cat in dim_categories:
            key = (cat['dimension'], cat['category'], cat.get('time_period'))
            dim_time_key = (cat['dimension'], cat.get('time_period'))
            vol = float(cat.get('category_volume', 0.0))
            category_totals[key] = category_totals.get(key, 0.0) + vol
            dim_time_totals[dim_time_key] = dim_time_totals.get(dim_time_key, 0.0) + vol
            if key not in peer_sets:
                peer_sets[key] = set()
                volumes_by_key[key] = []
            if vol > 0:
                peer_sets[key].add(cat['peer'])
            volumes_by_key[key].append(vol)

        stats: Dict[Tuple[str, Any, Optional[Any]], Dict[str, float]] = {}
        peer_total = max(len(peers), 1)
        for key, total in category_totals.items():
            dim_time_key = (key[0], key[2])
            dim_total = float(dim_time_totals.get(dim_time_key, 0.0))
            participants = float(len(peer_sets.get(key, set())))
            eff_peers = 0.0
            if total > 0:
                shares_sq = 0.0
                for v in volumes_by_key.get(key, []):
                    share = v / total
                    shares_sq += share * share
                eff_peers = (1.0 / shares_sq) if shares_sq > 0 else 0.0
            volume_share = (total / dim_total) if dim_total > 0 else 0.0
            overall_share = (total / overall_total) if overall_total > 0 else 0.0
            peer_fraction = participants / float(peer_total)
            coverage = max(volume_share, overall_share)
            representativeness = (peer_fraction * coverage) ** 0.5 if peer_fraction > 0 and coverage > 0 else 0.0
            representativeness = max(0.0, min(1.0, representativeness))
            stats[key] = {
                'participants': participants,
                'effective_peers': eff_peers,
                'category_total': total,
                'dimension_total': dim_total,
                'volume_share': volume_share,
                'overall_share': overall_share,
                'representativeness': representativeness,
            }
        return stats

    def _representativeness_weight(self, stats: Optional[Dict[str, float]]) -> float:
        if not stats:
            return 1.0
        rep = float(stats.get('representativeness', 0.0))
        scaled = rep ** self.representativeness_penalty_power if rep > 0 else 0.0
        return max(self.representativeness_penalty_floor, scaled)

    def _get_dynamic_additional_thresholds(
        self,
        rule_name: str,
        participants: int,
        representativeness: float,
    ) -> Tuple[Optional[Dict[str, Any]], bool]:
        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
        additional = rule_cfg.get('additional') if rule_cfg else None
        if not additional:
            return None, False

        min_entities = int(rule_cfg.get('min_entities', 0))
        if min_entities <= 0:
            return None, False

        peer_scale = min(1.0, participants / float(min_entities)) if min_entities > 0 else 1.0
        rep_scale = max(self.dynamic_threshold_scale_floor, min(1.0, representativeness))
        count_scale = max(self.dynamic_count_scale_floor, min(1.0, peer_scale, representativeness))

        relaxed = rep_scale < 1.0 or count_scale < 1.0
        if rule_name == '6/30':
            min_count, threshold = additional.get('min_count_above_threshold', (3, 7.0))
            dyn_count = max(1, int(round(min_count * count_scale)))
            dyn_threshold = float(threshold) * rep_scale
            return {
                'min_count_above_threshold': (dyn_count, dyn_threshold)
            }, relaxed
        if rule_name == '7/35':
            min_count_15 = int(additional.get('min_count_15', 2))
            min_count_8 = int(additional.get('min_count_8', 1))
            dyn_count_15 = max(1, int(round(min_count_15 * count_scale)))
            dyn_count_8 = max(0, int(round(min_count_8 * count_scale)))
            return {
                'min_count_15': dyn_count_15,
                'min_count_8': dyn_count_8,
                'threshold_15': 15.0 * rep_scale,
                'threshold_8': 8.0 * rep_scale,
            }, relaxed
        if rule_name == '10/40':
            min_count_20 = int(additional.get('min_count_20', 2))
            min_count_10 = int(additional.get('min_count_10', 1))
            dyn_count_20 = max(1, int(round(min_count_20 * count_scale)))
            dyn_count_10 = max(0, int(round(min_count_10 * count_scale)))
            return {
                'min_count_20': dyn_count_20,
                'min_count_10': dyn_count_10,
                'threshold_20': 20.0 * rep_scale,
                'threshold_10': 10.0 * rep_scale,
            }, relaxed
        return None, False

    def _assess_additional_constraints_applicability(
        self,
        rule_name: Optional[str],
        dimension: Optional[str],
        peer_volumes: Dict[str, float],
        stats: Optional[Dict[str, float]] = None,
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]], bool]:
        if not self.enforce_additional_constraints or not rule_name:
            return False, 'disabled', None, False

        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
        if not rule_cfg or not rule_cfg.get('additional'):
            return False, 'no_additional', None, False

        if dimension:
            if dimension == '_TIME_TOTAL':
                return False, 'time_total', None, False
            if self.time_column and dimension.startswith(f'_TIME_TOTAL_{self.time_column}'):
                return False, 'time_total', None, False

        min_entities = int(rule_cfg.get('min_entities', 0))
        participants = self._participant_count(peer_volumes)
        if min_entities and participants < min_entities:
            return False, 'low_peers', None, False

        if not self.dynamic_constraints_enabled or not stats:
            return True, None, None, False

        if participants < self.min_peer_count_for_constraints:
            return False, 'low_peers', None, False
        if float(stats.get('effective_peers', 0.0)) < self.min_effective_peer_count:
            return False, 'low_effective_peers', None, False
        if (
            float(stats.get('volume_share', 0.0)) < self.min_category_volume_share
            or float(stats.get('overall_share', 0.0)) < self.min_overall_volume_share
        ):
            return False, 'low_volume', None, False
        if float(stats.get('representativeness', 0.0)) < self.min_representativeness:
            return False, 'low_representativeness', None, False

        thresholds, relaxed = self._get_dynamic_additional_thresholds(
            rule_name,
            participants,
            float(stats.get('representativeness', 0.0))
        )
        return True, None, thresholds, relaxed

    def _evaluate_additional_constraints(
        self,
        shares: List[float],
        rule_name: str,
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, List[str]]:
        if thresholds is None:
            return PrivacyValidator.evaluate_additional_constraints(shares, rule_name)

        shares_sorted = sorted([float(s) for s in shares], reverse=True)
        details: List[str] = []
        passed = True

        if rule_name == '6/30':
            min_count, threshold = thresholds.get('min_count_above_threshold', (3, 7.0))
            idx = int(min_count) - 1
            observed = shares_sorted[idx] if idx < len(shares_sorted) else 0.0
            if observed + PrivacyValidator.COMPARISON_EPSILON < threshold:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count} participants >= {threshold:.2f}%, found {PrivacyValidator._count_at_or_above(shares_sorted, threshold)}"
                )
        elif rule_name == '7/35':
            min_count_15 = int(thresholds.get('min_count_15', 2))
            min_count_8 = int(thresholds.get('min_count_8', 1))
            threshold_15 = float(thresholds.get('threshold_15', 15.0))
            threshold_8 = float(thresholds.get('threshold_8', 8.0))
            idx_15 = min_count_15 - 1
            idx_8 = min_count_15 + min_count_8 - 1
            observed_15 = shares_sorted[idx_15] if idx_15 < len(shares_sorted) else 0.0
            observed_8 = shares_sorted[idx_8] if idx_8 < len(shares_sorted) else 0.0
            if observed_15 + PrivacyValidator.COMPARISON_EPSILON < threshold_15:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_15} participants >= {threshold_15:.2f}%, found {PrivacyValidator._count_at_or_above(shares_sorted, threshold_15)}"
                )
            if observed_8 + PrivacyValidator.COMPARISON_EPSILON < threshold_8:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_8} additional participants >= {threshold_8:.2f}%, found {max(PrivacyValidator._count_at_or_above(shares_sorted, threshold_8) - min_count_15, 0)}"
                )
        elif rule_name == '10/40':
            min_count_20 = int(thresholds.get('min_count_20', 2))
            min_count_10 = int(thresholds.get('min_count_10', 1))
            threshold_20 = float(thresholds.get('threshold_20', 20.0))
            threshold_10 = float(thresholds.get('threshold_10', 10.0))
            idx_20 = min_count_20 - 1
            idx_10 = min_count_20 + min_count_10 - 1
            observed_20 = shares_sorted[idx_20] if idx_20 < len(shares_sorted) else 0.0
            observed_10 = shares_sorted[idx_10] if idx_10 < len(shares_sorted) else 0.0
            if observed_20 + PrivacyValidator.COMPARISON_EPSILON < threshold_20:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_20} participants >= {threshold_20:.2f}%, found {PrivacyValidator._count_at_or_above(shares_sorted, threshold_20)}"
                )
            if observed_10 + PrivacyValidator.COMPARISON_EPSILON < threshold_10:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_10} additional participants >= {threshold_10:.2f}%, found {max(PrivacyValidator._count_at_or_above(shares_sorted, threshold_10) - min_count_20, 0)}"
                )

        return passed, details

    def _should_check_additional_constraints(
        self,
        rule_name: Optional[str],
        dimension: Optional[str],
        peer_volumes: Dict[str, float],
    ) -> bool:
        if not self.enforce_additional_constraints or not rule_name:
            return False

        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
        if not rule_cfg or not rule_cfg.get('additional'):
            return False

        if dimension:
            if dimension == '_TIME_TOTAL':
                return False
            if self.time_column and dimension.startswith(f'_TIME_TOTAL_{self.time_column}'):
                return False

        min_entities = int(rule_cfg.get('min_entities', 0))
        if min_entities and self._participant_count(peer_volumes) < min_entities:
            return False

        return True

    def _additional_constraints_penalty(
        self,
        shares: List[float],
        rule_name: str,
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> float:
        """Compute penalty for additional Control 3.2 constraints.
        
        Note: The min_entities check is static and should be performed before calling this
        in a hot loop, but we keep a fallback check here just in case.
        """
        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
        if not rule_cfg or not rule_cfg.get('additional'):
            return 0.0

        # Optimization: shares are already floats, sort directly
        # We need the sorted values to check top N shares
        shares_sorted = sorted(shares, reverse=True)
        penalty = 0.0

        if thresholds is None:
            if rule_name == '6/30':
                third = shares_sorted[2] if len(shares_sorted) > 2 else 0.0
                penalty += max(0.0, 7.0 - third) ** 2
            elif rule_name == '7/35':
                second = shares_sorted[1] if len(shares_sorted) > 1 else 0.0
                third = shares_sorted[2] if len(shares_sorted) > 2 else 0.0
                penalty += max(0.0, 15.0 - second) ** 2
                penalty += max(0.0, 8.0 - third) ** 2
            elif rule_name == '10/40':
                second = shares_sorted[1] if len(shares_sorted) > 1 else 0.0
                third = shares_sorted[2] if len(shares_sorted) > 2 else 0.0
                penalty += max(0.0, 20.0 - second) ** 2
                penalty += max(0.0, 10.0 - third) ** 2
            return penalty

        if rule_name == '6/30':
            min_count, threshold = thresholds.get('min_count_above_threshold', (3, 7.0))
            idx = int(min_count) - 1
            observed = shares_sorted[idx] if idx < len(shares_sorted) else 0.0
            penalty += max(0.0, float(threshold) - observed) ** 2
        elif rule_name == '7/35':
            min_count_15 = int(thresholds.get('min_count_15', 2))
            min_count_8 = int(thresholds.get('min_count_8', 1))
            threshold_15 = float(thresholds.get('threshold_15', 15.0))
            threshold_8 = float(thresholds.get('threshold_8', 8.0))
            idx_15 = min_count_15 - 1
            idx_8 = min_count_15 + min_count_8 - 1
            observed_15 = shares_sorted[idx_15] if idx_15 < len(shares_sorted) else 0.0
            observed_8 = shares_sorted[idx_8] if idx_8 < len(shares_sorted) else 0.0
            penalty += max(0.0, threshold_15 - observed_15) ** 2
            penalty += max(0.0, threshold_8 - observed_8) ** 2
        elif rule_name == '10/40':
            min_count_20 = int(thresholds.get('min_count_20', 2))
            min_count_10 = int(thresholds.get('min_count_10', 1))
            threshold_20 = float(thresholds.get('threshold_20', 20.0))
            threshold_10 = float(thresholds.get('threshold_10', 10.0))
            idx_20 = min_count_20 - 1
            idx_10 = min_count_20 + min_count_10 - 1
            observed_20 = shares_sorted[idx_20] if idx_20 < len(shares_sorted) else 0.0
            observed_10 = shares_sorted[idx_10] if idx_10 < len(shares_sorted) else 0.0
            penalty += max(0.0, threshold_20 - observed_20) ** 2
            penalty += max(0.0, threshold_10 - observed_10) ** 2

        return penalty

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
        scores: Dict[str, float] = {}
        # Build mapping of (dim, category) -> total peer category vol
        dim_cat_totals: Dict[Tuple[str, Any], float] = {}
        for c in all_categories:
            key = (c['dimension'], c['category'])
            dim_cat_totals[key] = dim_cat_totals.get(key, 0.0) + float(c['category_volume'])
        # For each dimension, compute max peer share across categories
        dim_max: Dict[str, float] = {}
        for c in all_categories:
            key = (c['dimension'], c['category'])
            denom = dim_cat_totals.get(key, 0.0)
            frac = (float(c['category_volume']) / denom) if denom > 0 else 0.0
            dim_max[c['dimension']] = max(dim_max.get(c['dimension'], 0.0), frac)
        # Convert to percentage
        for d, v in dim_max.items():
            scores[d] = v * 100.0
        return scores

    # New helpers: structural diagnostics and subset search
    def _compute_structural_caps_diagnostics(
        self,
        peers: List[str],
        all_categories: List[Dict[str, Any]],
        max_concentration: float,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        cap = float(max_concentration)
        tol = float(self.tolerance)
        dim_cat_totals: Dict[Tuple[str, Any], float] = {}
        for c in all_categories:
            key = (c['dimension'], c['category'])
            dim_cat_totals[key] = dim_cat_totals.get(key, 0.0) + float(c['category_volume'])
        rows: List[Dict[str, Any]] = []
        for c in all_categories:
            key = (c['dimension'], c['category'])
            v_p = float(c['category_volume'])
            total_cat = float(dim_cat_totals.get(key, 0.0))
            others = max(total_cat - v_p, 0.0)
            denom = self.min_weight * v_p + self.max_weight * others
            min_adj_share = (self.min_weight * v_p / denom * 100.0) if denom > 0 else 0.0
            margin = min_adj_share - cap - tol
            if margin > 0:
                rows.append({
                    'dimension': c['dimension'],
                    'category': c['category'],
                    'peer': c['peer'],
                    'min_adj_share_%': round(min_adj_share, 6),
                    'cap_%': cap,
                    'tolerance_pp': tol,
                    'margin_over_cap_pp': round(margin, 6),
                })
        detail_df = pd.DataFrame(rows)
        if detail_df.empty:
            summary_df = pd.DataFrame(columns=['dimension', 'infeasible_categories', 'infeasible_peers', 'worst_margin_pp'])
        else:
            grp = detail_df.groupby(['dimension', 'category']).size().reset_index(name='violating_peers')
            cat_counts = grp.groupby('dimension').size().rename('infeasible_categories')
            peer_counts = detail_df.groupby('dimension').size().rename('infeasible_peers')
            worst = detail_df.groupby('dimension')['margin_over_cap_pp'].max().rename('worst_margin_pp')
            summary_df = pd.concat([cat_counts, peer_counts, worst], axis=1).reset_index()
        return detail_df, summary_df

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
                sol = self._solve_global_weights_lp(peers, trial_cats, max_concentration, trial_peer_vols)
                stats = dict(self.last_lp_stats) if self.last_lp_stats else {}
                sum_slack = float(stats.get('sum_slack', 0.0) or 0.0)
                max_slack = float(stats.get('max_slack', 0.0) or 0.0)
                method = stats.get('method')
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
                    
                    sol = self._solve_global_weights_lp(peers, trial_cats, max_concentration, trial_peer_vols)
                    stats = dict(self.last_lp_stats) if self.last_lp_stats else {}
                    sum_slack = float(stats.get('sum_slack', 0.0) or 0.0)
                    max_slack = float(stats.get('max_slack', 0.0) or 0.0)
                    method = stats.get('method')
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

            dim_sol = self._solve_global_weights_lp(peers, dim_cats, max_concentration, dim_peer_vols)
            if dim_sol is not None:
                self.per_dimension_weights[dimension] = dim_sol
                self.weight_methods[dimension] = "Per-Dimension-LP"
                logger.info(f"Per-dimension LP succeeded for '{dimension}'")
                continue

            target_multipliers = {p: weights[p] for p in peers} if weights else None
            dim_h = self._solve_dimension_weights_heuristic(
                peers,
                dim_cats,
                max_concentration,
                dim_peer_vols,
                target_multipliers,
                rule_name=rule_name
            )
            if dim_h:
                self.per_dimension_weights[dimension] = dim_h
                self.weight_methods[dimension] = "Per-Dimension-Bayesian"
                logger.info(f"Per-dimension Bayesian optimization applied for '{dimension}' (targeting global weights)")
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

    def _solve_dimension_weights_heuristic(
        self,
        peers: List[str],
        dim_categories: List[Dict[str, Any]],
        max_concentration: float,
        peer_volumes: Dict[str, float],
        target_weights: Optional[Dict[str, float]] = None,
        rule_name: Optional[str] = None
    ) -> Dict[str, float]:
        """Bayesian-inspired optimization solver for a single dimension's categories.
        Returns a peer->multiplier dict within [min_weight, max_weight].
        
        Uses scipy.optimize.minimize with L-BFGS-B to find weights that minimize:
        1. Constraint violations (primary objective)
        2. Deviation from target_weights (secondary, if provided)
        3. Additional Control 3.2 constraints (when enabled)
        
        This is much more efficient than iterative heuristics since the LP solver
        has already placed weights near optimal boundaries.
        
        Time-aware: When categories include time_period field, validates constraints for each
        unique (dimension, category, time_period) combination separately."""
        from scipy.optimize import minimize
        
        # Build unique constraint keys for time-aware validation
        unique_keys = set()
        for cat in dim_categories:
            key = (cat['dimension'], cat['category'], cat.get('time_period'))
            unique_keys.add(key)
        unique_keys_list = list(unique_keys)
        
        # Map constraints to category indices
        constraint_map = {}
        for key in unique_keys_list:
            dim, category, time_period = key
            constraint_map[key] = [
                i for i, c in enumerate(dim_categories)
                if c['dimension'] == dim 
                and c['category'] == category 
                and c.get('time_period') == time_period
            ]

        constraint_stats = self._build_constraint_stats(dim_categories, peers, peer_volumes)
        
        peer_index = {peer: i for i, peer in enumerate(peers)}
        if rule_name is None:
            rule_name = PrivacyValidator.select_rule(len(peers))

        # Check for structural feasibility before optimization
        min_entities_check = True
        if self.enforce_additional_constraints and rule_name:
            rule_cfg = PrivacyValidator.get_rule_config(rule_name)
            if rule_cfg and rule_cfg.get('additional'):
                min_entities = int(rule_cfg.get('min_entities', 0))
                if len(peers) < min_entities:
                     min_entities_check = False

        shortfall_penalty = 0.0
        if self.enforce_additional_constraints and rule_name and not min_entities_check:
            min_entities = int(PrivacyValidator.get_rule_config(rule_name).get('min_entities', 0))
            shortfall = max(min_entities - len(peers), 0)
            shortfall_penalty = float(shortfall * shortfall * 100.0)

        constraint_data: Dict[Tuple[str, str, Optional[str]], Dict[str, Any]] = {}
        for key, cat_indices in constraint_map.items():
            dim, _, _ = key
            matching_cats = [dim_categories[i] for i in cat_indices]
            peer_cat_vols = {p: 0.0 for p in peers}
            for cat in matching_cats:
                peer_cat_vols[cat['peer']] = float(cat.get('category_volume', 0.0))

            stats = constraint_stats.get(key)
            rep_weight = self._representativeness_weight(stats)

            enforce = False
            thresholds = None
            if self.enforce_additional_constraints and rule_name and min_entities_check:
                enforce, _, thresholds, _ = self._assess_additional_constraints_applicability(
                    rule_name, dim, peer_cat_vols, stats
                )

            constraint_data[key] = {
                'peer_cat_vols': peer_cat_vols,
                'rep_weight': rep_weight,
                'enforce': enforce,
                'thresholds': thresholds
            }
        
        # Objective function: minimize violations + deviation from target
        def objective(weight_array):
            # Primary: sum of squared constraint violations
            violation_penalty = 0.0
            additional_penalty = 0.0
            max_share = max_concentration + self.tolerance
            
            for key in constraint_map.keys():
                dim, _, _ = key
                data = constraint_data[key]
                peer_cat_vols = data['peer_cat_vols']
                rep_weight = data['rep_weight']

                total_weighted = sum(peer_cat_vols[p] * weight_array[peer_index[p]] for p in peers)
                shares: List[float] = []

                if total_weighted > 0:
                    for p in peers:
                        cat_vol_weighted = peer_cat_vols[p] * weight_array[peer_index[p]]
                        adjusted_share = (cat_vol_weighted / total_weighted * 100.0)
                        shares.append(adjusted_share)
                        if self._is_share_violation(adjusted_share, max_concentration):
                            excess = adjusted_share - max_share
                            violation_penalty += rep_weight * (excess ** 2)  # Quadratic penalty
                else:
                    shares = [0.0 for _ in peers]

                if self.enforce_additional_constraints and rule_name:
                    if not min_entities_check:
                        additional_penalty += shortfall_penalty
                    elif data['enforce']:
                        additional_penalty += rep_weight * self._additional_constraints_penalty(
                            shares, rule_name, data['thresholds']
                        )
            
            # Secondary: stay close to target_weights (if provided)
            deviation_penalty = 0.0
            if target_weights:
                for i, peer in enumerate(peers):
                    target = target_weights.get(peer, 1.0)
                    deviation_penalty += (weight_array[i] - target) ** 2
            
            # Balance penalties
            return (violation_penalty + additional_penalty) * self.VIOLATION_PENALTY_WEIGHT + deviation_penalty
        
        # Initialize from target_weights or LP-suggested values
        if target_weights:
            x0 = np.array([target_weights.get(peer, 1.0) for peer in peers])
        else:
            x0 = np.ones(len(peers))
        
        # Bounds: [min_weight, max_weight] for each peer
        bounds = [(self.min_weight, self.max_weight) for _ in peers]
        
        # Run optimization with L-BFGS-B (handles bounds efficiently)
        result = minimize(
            objective,
            x0=x0,
            method='L-BFGS-B',
            bounds=bounds,
            options={'maxiter': 500, 'ftol': 1e-6}
        )
        
        # Extract optimized weights
        optimized_weights = {peer: result.x[i] for i, peer in enumerate(peers)}
        
        # Rescale to mean 1.0 while respecting bounds
        avg = sum(optimized_weights.values()) / len(optimized_weights)
        if avg > 0:
            k = 1.0 / avg
            for p in list(optimized_weights.keys()):
                optimized_weights[p] = max(self.min_weight, min(optimized_weights[p] * k, self.max_weight))
        
        weights = optimized_weights
        
        # Final validation: check remaining violations
        final_violations = []
        additional_violations = []
        for (dim, category, time_period) in unique_keys_list:
            cat_indices = constraint_map[(dim, category, time_period)]
            matching_cats = [dim_categories[i] for i in cat_indices]
            peer_cat_vols = {p: 0.0 for p in peers}
            for cat in matching_cats:
                peer_cat_vols[cat['peer']] = float(cat.get('category_volume', 0.0))
            total_weighted = sum(peer_cat_vols[p] * weights[p] for p in peers)
            stats = constraint_stats.get((dim, category, time_period))

            if total_weighted > 0:
                shares = []
                for p in peers:
                    cat_vol_weighted = peer_cat_vols[p] * weights[p]
                    adjusted_share = (cat_vol_weighted / total_weighted * 100.0)
                    shares.append(adjusted_share)
                    if self._is_share_violation(adjusted_share, max_concentration):
                        final_violations.append({
                            'peer': p,
                            'dim': dim,
                            'cat': category,
                            'time': time_period,
                            'share': adjusted_share,
                            'excess': adjusted_share - max_concentration - self.tolerance
                        })

                if self.enforce_additional_constraints and rule_name:
                    enforce, _, thresholds, relaxed = self._assess_additional_constraints_applicability(
                        rule_name, dim, peer_cat_vols, stats
                    )
                    if enforce:
                        passed, details = self._evaluate_additional_constraints(shares, rule_name, thresholds)
                        if not passed:
                            participant_count = self._participant_count(peer_cat_vols)
                            top_shares = sorted(shares, reverse=True)[:3]
                            additional_violations.append({
                                'dim': dim,
                                'cat': category,
                                'time': time_period,
                                'participants': participant_count,
                                'effective_peers': round(float(stats.get('effective_peers', 0.0)) if stats else 0.0, 4),
                                'representativeness': round(float(stats.get('representativeness', 0.0)) if stats else 0.0, 6),
                                'top_shares': ", ".join(f"{s:.2f}%" for s in top_shares),
                                'details': details,
                                'dynamic_thresholds': thresholds or {},
                                'relaxed': relaxed,
                            })
        
        if final_violations:
            logger.warning(f"Bayesian optimization completed with {len(final_violations)} violations still present "
                         f"(max excess: {max([v['excess'] for v in final_violations]):.2f}pp). "
                         f"Consider increasing --tolerance or --max-weight.")
            # Log top 3 violations for diagnostics
            sorted_viol = sorted(final_violations, key=lambda x: x['excess'], reverse=True)[:3]
            for v in sorted_viol:
                time_str = f" time={v['time']}" if v['time'] else ""
                logger.debug(f"  {v['peer']} in {v['dim']}={v['cat']}{time_str}: "
                           f"{v['share']:.2f}% (excess: {v['excess']:.2f}pp)")

        if additional_violations:
            logger.warning(f"Bayesian optimization completed with {len(additional_violations)} additional-constraint violations.")
            for v in additional_violations[:3]:
                time_str = f" time={v['time']}" if v['time'] else ""
                details = "; ".join(v.get('details', []))
                top_shares = v.get('top_shares', '')
                participants = v.get('participants', 0)
                logger.debug(
                    f"  {v['dim']}={v['cat']}{time_str}: participants={participants}, top_shares={top_shares}, {details}"
                )
        
        return weights

    def calculate_global_privacy_weights(
        self, 
        df: pd.DataFrame, 
        metric_col: str,
        dimensions: List[str]
    ) -> None:
        """
        Calculate privacy-constrained weights that work across ALL dimension categories.
        Uses iterative algorithm to find weights that satisfy privacy rules globally,
        with an LP that also penalizes rank inversions (descending by overall share).
        
        Parameters:
        -----------
        df : DataFrame
            Input dataframe
        metric_col : str
            Metric column to use for weight calculation
        dimensions : List[str]
            List of dimension columns to check privacy constraints across
        """
        if not self.consistent_weights:
            return

        # Build initial categories for provided dimensions
        all_categories, peer_volumes, peers = self._build_categories(df, metric_col, dimensions)
        peer_count = len(peers)
        rule_name, max_concentration = self._get_privacy_rule(peer_count)
        self.privacy_rule_name = rule_name
        self._reset_dynamic_constraint_stats()

        # Structural diagnostics upfront for reporting
        try:
            det_df, sum_df = self._compute_structural_caps_diagnostics(peers, all_categories, max_concentration)
            self.structural_detail_df = det_df
            self.structural_summary_df = sum_df
        except Exception as e:  # pragma: no cover
            logger.warning(f"Structural diagnostics failed: {e}")

        logger.info(f"Calculating global privacy-constrained weights for {peer_count} peers")
        logger.info(f"Privacy rule: {rule_name}")
        logger.info(f"Max concentration: {max_concentration}%")
        logger.info(f"Checking all categories across dimensions: {dimensions}")
        logger.info(f"Found {len(all_categories)} dimension/category combinations")

        # Initialize weights to 1.0 for all peers
        weights: Dict[str, float] = {peer: 1.0 for peer in peers}

        # Try LP on all dimensions
        lp_solution = self._solve_global_weights_lp(peers, all_categories, max_concentration, peer_volumes)
        converged = False
        used_dimensions = list(dimensions)
        removed_dimensions: List[str] = []

        # Slacks-first second attempt on full set before dropping any dimensions
        if lp_solution is None and self.prefer_slacks_first:
            logger.info("Attempting slacks-first LP on full dimension set before dropping any dimensions")
            # Temporarily reduce rank penalty to 0 to give more flexibility
            orig_rank = self.rank_preservation_strength
            self.rank_preservation_strength = 0.0
            lp_solution = self._solve_global_weights_lp(peers, all_categories, max_concentration, peer_volumes)
            self.rank_preservation_strength = orig_rank

        # If LP solved but used slack above threshold, trigger subset search even on success
        if lp_solution is not None and self.trigger_subset_on_slack:
            sum_slack = float(self.last_lp_stats.get('sum_slack', 0.0) or 0.0)
            if self._is_slack_excess(sum_slack):
                logger.info(
                    f"LP returned success but used cap slack sum={sum_slack:.6f} > threshold={self.max_cap_slack:.6f}; triggering subset search"
                )
                best_dims, best_weights = self._search_largest_feasible_subset(
                    df, metric_col, dimensions, max_concentration, peer_volumes, peers, all_categories
                )
                if best_weights is not None:
                    self.slack_subset_triggered = True
                    weights = best_weights
                    converged = True
                    used_dimensions = best_dims
                    removed_dimensions = [d for d in dimensions if d not in best_dims]
                    logger.info(f"Slack-aware policy selected global dimensions: {used_dimensions}")

                    # Process removed dimensions with per-dimension solving
                    self.per_dimension_weights.clear()
                    self._solve_per_dimension_weights(
                        df,
                        metric_col,
                        removed_dimensions,
                        peers,
                        max_concentration,
                        weights,
                        rule_name
                    )
                else:
                    logger.info("Subset search failed to improve; keeping full-set LP solution despite slack usage")

        if lp_solution is None:
            # Optional: automatic search for largest feasible subset
            if self.auto_subset_search:
                logger.info("Searching for largest feasible global dimension subset (auto_subset_search enabled)")
                best_dims, best_weights = self._search_largest_feasible_subset(df, metric_col, dimensions, max_concentration, peer_volumes, peers, all_categories)
                if best_weights is not None:
                    weights = best_weights
                    converged = True
                    used_dimensions = best_dims
                    removed_dimensions = [d for d in dimensions if d not in best_dims]
                    logger.info(f"Auto search selected global dimensions: {used_dimensions}")

                    # Process removed dimensions with per-dimension solving
                    self.per_dimension_weights.clear()
                    self._solve_per_dimension_weights(
                        df,
                        metric_col,
                        removed_dimensions,
                        peers,
                        max_concentration,
                        weights,
                        rule_name
                    )
            else:
                # Dimension-dropping fallback before heuristic
                scores = self._dimension_unbalance_scores(all_categories)
                ordered_dims = sorted(scores.keys(), key=lambda d: scores[d], reverse=True)
                logger.warning("LP infeasible; attempting fallback by dropping most unbalanced dimensions in order: {}".format(ordered_dims))
                for k in range(1, len(ordered_dims) + 1):
                    trial_dims = [d for d in dimensions if d not in ordered_dims[:k]]
                    if not trial_dims:
                        continue
                    trial_cats, trial_peer_vols, _ = self._build_categories(df, metric_col, trial_dims)
                    if not trial_cats:
                        continue
                    sol = self._solve_global_weights_lp(peers, trial_cats, max_concentration, trial_peer_vols)
                    if sol is not None:
                        weights = sol
                        converged = True
                        used_dimensions = trial_dims
                        removed_dimensions = ordered_dims[:k]
                        logger.info(f"LP succeeded after dropping dimensions: {removed_dimensions}")
                        # Attempt per-removed-dimension individual balancing
                        self.per_dimension_weights.clear()
                        self._solve_per_dimension_weights(
                            df,
                            metric_col,
                            removed_dimensions,
                            peers,
                            max_concentration,
                            weights,
                            rule_name
                        )
                        break
        else:
            # LP solved and either slack policy kept it or no slack trigger
            if not converged:
                weights = lp_solution
                converged = True
                # Mark all dimensions as using Global-LP
                for dim in used_dimensions:
                    self.weight_methods[dim] = "Global-LP"

        self.global_dimensions_used = used_dimensions
        self.removed_dimensions = removed_dimensions

        if converged:
            # Enforce additional constraints (if configured) via heuristic re-optimization
            self.additional_constraint_violations = []
            if self.enforce_additional_constraints and rule_name in ('6/30', '7/35', '10/40'):
                violations = self._find_additional_constraint_violations(all_categories, peers, weights, rule_name, peer_volumes)
                self.additional_constraint_violations = violations
                if violations:
                    logger.warning(f"Additional constraints violated in {len(violations)} categories; running heuristic optimization to correct.")
                    target_multipliers = {p: weights[p] for p in peers} if weights else None
                    heuristic_weights = self._solve_dimension_weights_heuristic(
                        peers,
                        all_categories,
                        max_concentration,
                        peer_volumes,
                        target_multipliers,
                        rule_name=rule_name
                    )
                    if heuristic_weights:
                        weights = heuristic_weights
                        self.additional_constraint_violations = self._find_additional_constraint_violations(
                            all_categories, peers, weights, rule_name, peer_volumes
                        )
                        if self.additional_constraint_violations:
                            logger.warning(
                                f"Additional constraints still violated in {len(self.additional_constraint_violations)} categories after heuristic optimization."
                            )
                    else:
                        logger.warning("Heuristic optimization failed; keeping LP weights with additional-constraint violations.")

            # Tiny post-optimization nudge for borderline cap excesses
            weights = self._nudge_borderline_cap_excess(weights, all_categories, max_concentration, used_dimensions)

            # Store and validate
            self._store_final_weights(peers, peer_volumes, weights)
            
            # For time-aware validation, we need to map time-aware dimension names back to original dimensions
            if self.time_column and self.consistent_weights:
                # Create mapping from time-aware dimension names to original dimensions
                original_dims = set(used_dimensions)
                time_aware_to_original = {}
                for cat in all_categories:
                    dim_name = cat['dimension']
                    if dim_name.startswith(f'_TIME_TOTAL_{self.time_column}'):
                        # Monthly total constraints - map to special validation
                        time_aware_to_original[dim_name] = '_TIME_TOTAL'
                    elif dim_name.endswith(f'_{self.time_column}'):
                        # Monthly category constraints - extract original dimension
                        original_dim = dim_name.replace(f'_{self.time_column}', '')
                        if original_dim in original_dims:
                            time_aware_to_original[dim_name] = original_dim
                
                # Build validation set including time_period for time-aware categories
                val_dims_set = set((time_aware_to_original.get(c['dimension'], c['dimension']), c['category'], c.get('time_period')) 
                                 for c in all_categories 
                                 if time_aware_to_original.get(c['dimension'], c['dimension']) in original_dims or c['dimension'].startswith('_TIME_TOTAL'))
            else:
                val_dims_set = set((c['dimension'], c['category'], None) for c in all_categories if c['dimension'] in used_dimensions)
            
            logger.info("\nGlobal weights validation across all {} categories:".format(len(val_dims_set)))
            logger.info("\nFinal global weight multipliers:")
            
            # Track dimensions with violations
            dimensions_with_violations: List[str] = []
            
            for peer in sorted(peers, key=lambda p: weights[p], reverse=True):
                peer_max_share = 0.0
                peer_violation_dims: List[str] = []
                for cat in all_categories:
                    if cat['peer'] != peer:
                        continue
                    
                    # For time-aware analysis, check if this category should be included in validation
                    if self.time_column and self.consistent_weights:
                        dim_name = cat['dimension']
                        if dim_name.startswith(f'_TIME_TOTAL_{self.time_column}'):
                            # Include monthly total constraints in validation
                            include_in_validation = True
                            original_dim = '_TIME_TOTAL'
                        elif dim_name.endswith(f'_{self.time_column}'):
                            # Include monthly category constraints if original dimension is used
                            original_dim = dim_name.replace(f'_{self.time_column}', '')
                            include_in_validation = original_dim in used_dimensions
                        else:
                            include_in_validation = cat['dimension'] in used_dimensions
                            original_dim = cat['dimension']
                    else:
                        include_in_validation = cat['dimension'] in used_dimensions
                        original_dim = cat['dimension']
                    
                    if not include_in_validation:
                        continue
                    
                    # Calculate weighted share for this peer in this category (time-aware)
                    category_vol_weighted = cat['category_volume'] * weights[peer]
                    
                    # Get all peer entries for the same dimension-category-(time) combination
                    if 'time_period' in cat:
                        # Time-aware: match dimension, category, AND time_period
                        matching_cats = [
                            c for c in all_categories
                            if c['dimension'] == cat['dimension'] 
                            and c['category'] == cat['category']
                            and c.get('time_period') == cat.get('time_period')
                        ]
                    else:
                        # Non-time-aware: match dimension and category only
                        matching_cats = [
                            c for c in all_categories
                            if c['dimension'] == cat['dimension'] 
                            and c['category'] == cat['category']
                        ]
                    
                    total_weighted = sum(c['category_volume'] * weights[c['peer']] for c in matching_cats)
                    adjusted_share = (category_vol_weighted / total_weighted * 100) if total_weighted > 0 else 0.0
                    
                    # Always track max share for reporting
                    peer_max_share = max(peer_max_share, adjusted_share)
                    
                    # Track violations at the time-aware level
                    if self._is_share_violation(adjusted_share, max_concentration):
                        if original_dim not in peer_violation_dims:
                            peer_violation_dims.append(original_dim)
                
                # Status based on whether there are actual violations, not just high max_share
                status = "OK" if len(peer_violation_dims) == 0 else "VIOLATION"
                logger.info(
                    f"  {peer}: multiplier={weights[peer]:.4f}, max_adjusted_share={peer_max_share:.4f}% [{status}]"
                )
                
                # Collect unique violation dimensions
                for vd in peer_violation_dims:
                    if vd not in dimensions_with_violations:
                        dimensions_with_violations.append(vd)
            
            # For dimensions with violations, attempt per-dimension weight solving
            # Filter out special dimensions like _TIME_TOTAL which are virtual constraints
            real_dimensions_with_violations = [vd for vd in dimensions_with_violations 
                                              if not vd.startswith('_TIME_TOTAL')]
            
            if real_dimensions_with_violations:
                logger.info(f"\nDimensions with violations detected: {real_dimensions_with_violations}")
                logger.info("Computing per-dimension weights for these dimensions...")
                for vd in real_dimensions_with_violations:
                    vd_cats, vd_peer_vols, _ = self._build_categories(df, metric_col, [vd])
                    if vd_cats:
                        # Check if time-aware
                        has_time = any('time_period' in cat for cat in vd_cats)
                        time_info = f" (time-aware: {len([c for c in vd_cats if c.get('time_period')])} constraints)" if has_time else ""
                        logger.info(f"Solving per-dimension weights for '{vd}'{time_info}")
                        
                        # Try LP first with stricter slack penalty for per-dimension solving
                        # Save original tolerance and temporarily reduce it for per-dimension LP
                        orig_tolerance = self.tolerance
                        self.tolerance = 0.0  # Force exact compliance for per-dimension LP
                        vd_sol = self._solve_global_weights_lp(peers, vd_cats, max_concentration, vd_peer_vols)
                        self.tolerance = orig_tolerance  # Restore original tolerance
                        if vd_sol is not None:
                            # Validate that LP solution actually satisfies tolerance
                            has_violations = False
                            for cat in vd_cats:
                                if 'time_period' in cat:
                                    matching_cats = [c for c in vd_cats 
                                                   if c['dimension'] == cat['dimension'] 
                                                   and c['category'] == cat['category']
                                                   and c.get('time_period') == cat.get('time_period')]
                                else:
                                    matching_cats = [c for c in vd_cats 
                                                   if c['dimension'] == cat['dimension'] 
                                                   and c['category'] == cat['category']]
                                
                                cat_vol_weighted = cat['category_volume'] * vd_sol[cat['peer']]
                                total_weighted = sum(c['category_volume'] * vd_sol[c['peer']] for c in matching_cats)
                                adjusted_share = (cat_vol_weighted / total_weighted * 100) if total_weighted > 0 else 0.0
                                
                                if self._is_share_violation(adjusted_share, max_concentration):
                                    has_violations = True
                                    break
                            
                            if not has_violations:
                                self.per_dimension_weights[vd] = vd_sol
                                self.weight_methods[vd] = "Per-Dimension-LP"
                                logger.info(f"  Per-dimension LP succeeded for '{vd}' with no violations")
                            else:
                                logger.info(f"  Per-dimension LP produced violations for '{vd}', trying Bayesian optimization")
                                vd_sol = None  # Force fallback to heuristic
                        
                        if vd_sol is None:
                            # Fallback to Bayesian optimization with global weights as target
                            target_multipliers = {p: weights[p] for p in peers}
                            vd_h = self._solve_dimension_weights_heuristic(
                                peers,
                                vd_cats,
                                max_concentration,
                                vd_peer_vols,
                                target_multipliers,
                                rule_name=rule_name
                            )
                            if vd_h:
                                self.per_dimension_weights[vd] = vd_h
                                self.weight_methods[vd] = "Per-Dimension-Bayesian"
                                logger.info(f"  Per-dimension Bayesian optimization applied for '{vd}' (targeting global weights)")
                            else:
                                logger.warning(f"  Per-dimension solving failed for '{vd}'")
    
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
        for p, cat_vol in peer_category_volumes.items():
            total_vol = peer_totals_map[p]
            share = (cat_vol / total_vol * 100.0) if total_vol > 0 else 0
            peer_shares.append(share)
        bic_value = float(np.percentile(peer_shares, self.bic_percentile * 100.0)) if len(peer_shares) > 0 else 0.0
        
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
        for p in peer_totals_map.keys():
            # Only include peers with denominator > 0
            if peer_category_dens.get(p, 0.0) > 0:
                rate = (peer_category_nums.get(p, 0.0) / peer_category_dens[p] * 100.0)
                peer_rates.append(rate)
        # For fraud rates (lower is better), use 1 - bic_percentile. For other rates (higher is better), use bic_percentile
        bic_pct = (1.0 - self.bic_percentile) if numerator_col.lower().startswith('fraud') else self.bic_percentile
        bic_value = float(np.percentile(peer_rates, bic_pct * 100.0)) if len(peer_rates) > 0 else 0.0
        
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
        logger.info(f"Running SHARE analysis for dimension: {dimension_column}")
        
        results: List[Dict[str, Any]] = []
        
        # Check if time column is set for time-dimension analysis
        if self.time_column and self.time_column in df.columns:
            # Time-aware analysis: aggregate by entity, dimension, and time
            entity_category_time_agg = df.groupby([self.entity_column, dimension_column, self.time_column]).agg({metric_col: 'sum'}).reset_index()
            entity_totals_by_time = entity_category_time_agg.groupby([self.entity_column, self.time_column])[metric_col].sum()
            
            # Also get overall aggregation (without time) for "General" rows
            entity_category_agg = df.groupby([self.entity_column, dimension_column]).agg({metric_col: 'sum'}).reset_index()
            entity_totals = entity_category_agg.groupby(self.entity_column)[metric_col].sum()
            
            categories = entity_category_agg[dimension_column].unique()
            time_periods = sorted(df[self.time_column].unique())
            
            for category in categories:
                # First, add time-specific rows
                for time_period in time_periods:
                    time_category_df = entity_category_time_agg[
                        (entity_category_time_agg[dimension_column] == category) &
                        (entity_category_time_agg[self.time_column] == time_period)
                    ].copy()
                    
                    result = self._calculate_share_metrics(
                        time_category_df, entity_totals_by_time, dimension_column, category, 
                        metric_col, time_period=time_period
                    )
                    if result:
                        results.append(result)
                
                # Then add "General" row (aggregated across all time periods)
                category_df = entity_category_agg[entity_category_agg[dimension_column] == category].copy()
                result = self._calculate_share_metrics(
                    category_df, entity_totals, dimension_column, category, 
                    metric_col, time_period="General"
                )
                if result:
                    results.append(result)
        else:
            # Non-time-aware analysis: aggregate by entity and dimension category only
            entity_category_agg = df.groupby([self.entity_column, dimension_column]).agg({metric_col: 'sum'}).reset_index()
            entity_totals = entity_category_agg.groupby(self.entity_column)[metric_col].sum()
            categories = entity_category_agg[dimension_column].unique()
            
            for category in categories:
                category_df = entity_category_agg[entity_category_agg[dimension_column] == category].copy()
                result = self._calculate_share_metrics(
                    category_df, entity_totals, dimension_column, category, 
                    metric_col, time_period=None
                )
                if result:
                    results.append(result)
        
        return pd.DataFrame(results)

    def analyze_dimension_rate(
        self,
        df: pd.DataFrame,
        dimension_column: str,
        total_col: str,
        numerator_col: str
    ) -> pd.DataFrame:
        """Analyze a single dimension with RATE (approval/fraud)."""
        logger.info(f"Running RATE analysis for dimension: {dimension_column}")
        
        results: List[Dict[str, Any]] = []
        
        # Check if time column is set for time-dimension analysis
        if self.time_column and self.time_column in df.columns:
            # Time-aware analysis: aggregate by entity, dimension, and time
            entity_category_time_agg = df.groupby([self.entity_column, dimension_column, self.time_column]).agg({total_col: 'sum', numerator_col: 'sum'}).reset_index()
            entity_totals_by_time = entity_category_time_agg.groupby([self.entity_column, self.time_column])[total_col].sum()
            
            # Also get overall aggregation (without time) for "General" rows
            entity_category_agg = df.groupby([self.entity_column, dimension_column]).agg({total_col: 'sum', numerator_col: 'sum'}).reset_index()
            entity_totals = entity_category_agg.groupby(self.entity_column)[total_col].sum()
            
            categories = entity_category_agg[dimension_column].unique()
            time_periods = sorted(df[self.time_column].unique())
            
            for category in categories:
                # First, add time-specific rows
                for time_period in time_periods:
                    time_category_df = entity_category_time_agg[
                        (entity_category_time_agg[dimension_column] == category) &
                        (entity_category_time_agg[self.time_column] == time_period)
                    ].copy()
                    
                    result = self._calculate_rate_metrics(
                        time_category_df, entity_totals_by_time, dimension_column, category, 
                        total_col, numerator_col, time_period=time_period
                    )
                    if result:
                        results.append(result)
                
                # Then add "General" row (aggregated across all time periods)
                category_df = entity_category_agg[entity_category_agg[dimension_column] == category].copy()
                result = self._calculate_rate_metrics(
                    category_df, entity_totals, dimension_column, category, 
                    total_col, numerator_col, time_period="General"
                )
                if result:
                    results.append(result)
        else:
            # Non-time-aware analysis: aggregate by entity and dimension category only
            entity_category_agg = df.groupby([self.entity_column, dimension_column]).agg({total_col: 'sum', numerator_col: 'sum'}).reset_index()
            entity_totals = entity_category_agg.groupby(self.entity_column)[total_col].sum()
            categories = entity_category_agg[dimension_column].unique()
            
            for category in categories:
                category_df = entity_category_agg[entity_category_agg[dimension_column] == category].copy()
                result = self._calculate_rate_metrics(
                    category_df, entity_totals, dimension_column, category, 
                    total_col, numerator_col, time_period=None
                )
                if result:
                    results.append(result)
        
        return pd.DataFrame(results)

    def build_privacy_validation_dataframe(self, df: pd.DataFrame, metric_col: str, dimensions: List[str]) -> pd.DataFrame:
        """Build detailed privacy validation dataframe showing original and balanced shares for each dimension-category-(time) combination."""
        if not self.consistent_weights or not self.global_weights:
            return pd.DataFrame()
        validation_rows: List[Dict[str, Any]] = []
        peers = list(self.global_weights.keys())
        peer_count = len(peers)
        rule_name, max_concentration = self._get_privacy_rule(peer_count)
        weights = {p: self.global_weights[p]['multiplier'] for p in peers}
        for dimension in dimensions:
            dim_weights = dict(weights)
            if dimension in self.per_dimension_weights:
                dim_weights.update(self.per_dimension_weights[dimension])
            weight_source = "Per-Dimension" if dimension in self.per_dimension_weights else "Global"
            weight_method = self.weight_methods.get(dimension, "Global-LP")
            if self.time_column and self.time_column in df.columns:
                time_periods = sorted(df[self.time_column].unique())
                for time_period in time_periods:
                    time_df = df[df[self.time_column] == time_period]
                    entity_dim_agg = time_df.groupby([self.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()
                    for category in entity_dim_agg[dimension].unique():
                        cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
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

                        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
                        min_entities = int(rule_cfg.get('min_entities', 0)) if rule_cfg else 0
                        participant_count = sum(1 for p in peer_data if p['volume'] > 0)
                        if min_entities and participant_count < min_entities:
                            additional_passed = True
                            additional_detail = "Skipped (insufficient participants)"
                        else:
                            additional_passed, additional_details = PrivacyValidator.evaluate_additional_constraints(
                                balanced_shares, rule_name
                            )
                            additional_detail = "; ".join(additional_details) if additional_details else ""

                        for idx, peer_info in enumerate(peer_data):
                            peer, peer_vol = peer_info['peer'], peer_info['volume']
                            peer_weight = dim_weights.get(peer, 1.0)
                            original_share = (peer_vol / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                            balanced_vol = peer_vol * peer_weight
                            balanced_share = balanced_shares[idx]
                            is_violation = self._is_share_violation(balanced_share, max_concentration)
                            compliant = (not is_violation) and additional_passed
                            violation_margin = balanced_share - max_concentration if is_violation else 0.0
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
                                'Additional_Constraints_Passed': 'Yes' if additional_passed else 'No',
                                'Additional_Constraint_Detail': additional_detail,
                                'Compliant': 'Yes' if compliant else 'No',
                                'Violation_Margin_%': round(violation_margin, 4) if violation_margin > 0 else 0.0
                            })
            else:
                entity_dim_agg = df.groupby([self.entity_column, dimension]).agg({metric_col: 'sum'}).reset_index()
                for category in entity_dim_agg[dimension].unique():
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
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

                    rule_cfg = PrivacyValidator.get_rule_config(rule_name)
                    min_entities = int(rule_cfg.get('min_entities', 0)) if rule_cfg else 0
                    participant_count = sum(1 for p in peer_data if p['volume'] > 0)
                    if min_entities and participant_count < min_entities:
                        additional_passed = True
                        additional_detail = "Skipped (insufficient participants)"
                    else:
                        additional_passed, additional_details = PrivacyValidator.evaluate_additional_constraints(
                            balanced_shares, rule_name
                        )
                        additional_detail = "; ".join(additional_details) if additional_details else ""

                    for idx, peer_info in enumerate(peer_data):
                        peer, peer_vol = peer_info['peer'], peer_info['volume']
                        peer_weight = dim_weights.get(peer, 1.0)
                        original_share = (peer_vol / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                        balanced_vol = peer_vol * peer_weight
                        balanced_share = balanced_shares[idx]
                        is_violation = self._is_share_violation(balanced_share, max_concentration)
                        compliant = (not is_violation) and additional_passed
                        violation_margin = balanced_share - max_concentration if is_violation else 0.0
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
                            'Original_Share_%': round(original_share, 4),
                            'Balanced_Volume': balanced_vol,
                            'Balanced_Share_%': round(balanced_share, 4),
                            'Privacy_Cap_%': max_concentration,
                            'Tolerance_%': self.tolerance,
                            'Additional_Constraints_Passed': 'Yes' if additional_passed else 'No',
                            'Additional_Constraint_Detail': additional_detail,
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
                time_periods = sorted([t for t in df[self.time_column].unique() if t is not None])
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
        logger.warning("calculate_share_distortion is deprecated. Use calculate_share_impact instead.")
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
                time_periods = sorted([t for t in df[self.time_column].unique() if t is not None])
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
        logger.warning("calculate_rate_weight_effect is deprecated. Use calculate_rate_impact instead.")
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
        return self.calculate_impact_summary(distortion_df, analysis_type)

