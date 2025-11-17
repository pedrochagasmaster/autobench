"""
DimensionalAnalyzer - Automatic dimensional breakdown analysis.

Analyzes metrics across all dimensional columns in the dataset,
following Mastercard privacy rules for balanced benchmarking.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Any, Optional, Tuple
import logging

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
        self.slack_subset_triggered: bool = False
        # Structural diagnostics placeholders
        self.structural_detail_df: pd.DataFrame = pd.DataFrame()
        self.structural_summary_df: pd.DataFrame = pd.DataFrame()
        # Rank changes (Milestone 2)
        self.rank_changes_df: pd.DataFrame = pd.DataFrame()
        # Privacy compliance validation (debug mode)
        self.privacy_validation_df: pd.DataFrame = pd.DataFrame()
        logger.info(f"Initialized DimensionalAnalyzer for entity: {target_entity}")
        if debug_mode:
            logger.info("Debug mode enabled - will include unweighted averages and weights tracking")
        if consistent_weights:
            logger.info("Consistent weights mode enabled - same privacy-constrained weights across all dimensions")
            logger.info(
                "Weight parameters: max_iterations=%s, tolerance=%s%%, "
                "max_weight=%sx, min_weight=%sx, rank_preservation=%s",
                max_iterations, tolerance, max_weight, min_weight, self.rank_preservation_strength
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
        lambda_cap = float(100.0 / max(self.tolerance, 1e-6))
        c = np.concatenate([
            np.zeros(P, dtype=float),                              # m
            np.ones(P, dtype=float),                               # t_plus
            np.ones(P, dtype=float),                               # t_minus
            np.full(num_cap_constraints, lambda_cap, dtype=float), # s_cap
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
            logger.info(f"LP used cap slacks: max={max_slack_pct:.4f}%, sum={sum_slack_pct:.4f}% (penalized with lambda={lambda_cap:.2f})")
        
        # Save stats for reporting (store both absolute and percentage)
        self.last_lp_stats = {
            'method': solved_method or 'highs',
            'max_slack': max_slack_pct,  # Now in percentage
            'sum_slack': sum_slack_pct,  # Now in percentage
            'max_slack_abs': max_slack_abs,  # Keep absolute for debugging
            'sum_slack_abs': sum_slack_abs,  # Keep absolute for debugging
            'lambda_cap': lambda_cap,
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
                if success and self.trigger_subset_on_slack and sum_slack > float(self.max_cap_slack):
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
                    if len(trial_dims) == len(dimensions) and sum_slack <= float(self.max_cap_slack):
                        break
                    if sum_slack <= float(self.max_cap_slack):
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
                    
                    if success and self.trigger_subset_on_slack and sum_slack > float(self.max_cap_slack):
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
                        if sum_slack <= float(self.max_cap_slack):
                            logger.info(f"Random search found feasible subset of size {subset_size} after {tested} attempts")
                            return best_dims, best_weights
        
        return best_dims, best_weights

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
        target_weights: Optional[Dict[str, float]] = None
    ) -> Dict[str, float]:
        """Bayesian-inspired optimization solver for a single dimension's categories.
        Returns a peer->multiplier dict within [min_weight, max_weight].
        
        Uses scipy.optimize.minimize with L-BFGS-B to find weights that minimize:
        1. Constraint violations (primary objective)
        2. Deviation from target_weights (secondary, if provided)
        
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
        
        # Objective function: minimize violations + deviation from target
        def objective(weight_array):
            weights_dict = {peer: weight_array[i] for i, peer in enumerate(peers)}
            
            # Primary: sum of squared constraint violations
            violation_penalty = 0.0
            max_share = max_concentration + self.tolerance
            
            for key, cat_indices in constraint_map.items():
                matching_cats = [dim_categories[i] for i in cat_indices]
                total_weighted = sum(c['category_volume'] * weights_dict[c['peer']] for c in matching_cats)
                
                if total_weighted > 0:
                    for cat in matching_cats:
                        p = cat['peer']
                        cat_vol_weighted = cat['category_volume'] * weights_dict[p]
                        adjusted_share = (cat_vol_weighted / total_weighted * 100)
                        
                        if adjusted_share > max_share:
                            excess = adjusted_share - max_share
                            violation_penalty += excess ** 2  # Quadratic penalty
            
            # Secondary: stay close to target_weights (if provided)
            deviation_penalty = 0.0
            if target_weights:
                for i, peer in enumerate(peers):
                    target = target_weights.get(peer, 1.0)
                    deviation_penalty += (weight_array[i] - target) ** 2
            
            # Balance penalties: violations are 100x more important
            return violation_penalty * 100.0 + deviation_penalty
        
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
        for (dim, category, time_period) in unique_keys_list:
            cat_indices = constraint_map[(dim, category, time_period)]
            matching_cats = [dim_categories[i] for i in cat_indices]
            total_weighted = sum(c['category_volume'] * weights[c['peer']] for c in matching_cats)
            
            if total_weighted > 0:
                for cat in matching_cats:
                    p = cat['peer']
                    cat_vol_weighted = cat['category_volume'] * weights[p]
                    adjusted_share = (cat_vol_weighted / total_weighted * 100)
                    
                    if adjusted_share > max_concentration + self.tolerance:
                        final_violations.append({
                            'peer': p, 
                            'dim': dim, 
                            'cat': category, 
                            'time': time_period,
                            'share': adjusted_share,
                            'excess': adjusted_share - max_concentration - self.tolerance
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
        if peer_count >= 10:
            max_concentration = 40.0
        elif peer_count >= 7:
            max_concentration = 35.0
        elif peer_count >= 6:
            max_concentration = 30.0
        elif peer_count >= 5:
            max_concentration = 25.0
        elif peer_count >= 4:
            max_concentration = 35.0
        else:
            max_concentration = 50.0

        # Structural diagnostics upfront for reporting
        try:
            det_df, sum_df = self._compute_structural_caps_diagnostics(peers, all_categories, max_concentration)
            self.structural_detail_df = det_df
            self.structural_summary_df = sum_df
        except Exception as e:  # pragma: no cover
            logger.warning(f"Structural diagnostics failed: {e}")

        logger.info(f"Calculating global privacy-constrained weights for {peer_count} peers")
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
            if sum_slack > float(self.max_cap_slack):
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
                    for rd in removed_dimensions:
                        rd_cats, rd_peer_vols, _ = self._build_categories(df, metric_col, [rd])
                        if rd_cats:
                            # Check if time-aware
                            has_time = any('time_period' in cat for cat in rd_cats)
                            time_info = f" (time-aware: {len([c for c in rd_cats if c.get('time_period')])} constraints)" if has_time else ""
                            logger.info(f"Solving per-dimension weights for removed dimension '{rd}'{time_info}")
                            
                            rd_sol = self._solve_global_weights_lp(peers, rd_cats, max_concentration, rd_peer_vols)
                            if rd_sol is not None:
                                self.per_dimension_weights[rd] = rd_sol
                                self.weight_methods[rd] = "Per-Dimension-LP"
                                logger.info(f"Per-dimension LP succeeded for removed dimension '{rd}'")
                            else:
                                # Heuristic per-dimension fallback - use global weights as target
                                target_multipliers = {p: weights[p] for p in peers} if weights else None
                                rd_h = self._solve_dimension_weights_heuristic(peers, rd_cats, max_concentration, rd_peer_vols, target_multipliers)
                                if rd_h:
                                    self.per_dimension_weights[rd] = rd_h
                                    self.weight_methods[rd] = "Per-Dimension-Bayesian"
                                    logger.info(f"Per-dimension Bayesian optimization applied for removed dimension '{rd}' (targeting global weights)")
                                else:
                                    logger.warning(f"Per-dimension solving failed for removed dimension '{rd}'")
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
                    for rd in removed_dimensions:
                        rd_cats, rd_peer_vols, _ = self._build_categories(df, metric_col, [rd])
                        if rd_cats:
                            # Check if time-aware
                            has_time = any('time_period' in cat for cat in rd_cats)
                            time_info = f" (time-aware: {len([c for c in rd_cats if c.get('time_period')])} constraints)" if has_time else ""
                            logger.info(f"Solving per-dimension weights for removed dimension '{rd}'{time_info}")
                            
                            rd_sol = self._solve_global_weights_lp(peers, rd_cats, max_concentration, rd_peer_vols)
                            if rd_sol is not None:
                                self.per_dimension_weights[rd] = rd_sol
                                self.weight_methods[rd] = "Per-Dimension-LP"
                                logger.info(f"Per-dimension LP succeeded for removed dimension '{rd}'")
                            else:
                                # Heuristic per-dimension fallback - use global weights as target
                                target_multipliers = {p: weights[p] for p in peers} if weights else None
                                rd_h = self._solve_dimension_weights_heuristic(peers, rd_cats, max_concentration, rd_peer_vols, target_multipliers)
                                if rd_h:
                                    self.per_dimension_weights[rd] = rd_h
                                    self.weight_methods[rd] = "Per-Dimension-Bayesian"
                                    logger.info(f"Per-dimension Bayesian optimization applied for removed dimension '{rd}' (targeting global weights)")
                                else:
                                    logger.warning(f"Per-dimension solving failed for removed dimension '{rd}'")
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
                        for rd in removed_dimensions:
                            rd_cats, rd_peer_vols, _ = self._build_categories(df, metric_col, [rd])
                            if rd_cats:
                                # Check if time-aware
                                has_time = any('time_period' in cat for cat in rd_cats)
                                time_info = f" (time-aware: {len([c for c in rd_cats if c.get('time_period')])} constraints)" if has_time else ""
                                logger.info(f"Solving per-dimension weights for '{rd}'{time_info}")
                                
                                rd_sol = self._solve_global_weights_lp(peers, rd_cats, max_concentration, rd_peer_vols)
                                if rd_sol is not None:
                                    self.per_dimension_weights[rd] = rd_sol
                                    self.weight_methods[rd] = "Per-Dimension-LP"
                                    logger.info(f"Per-dimension LP succeeded for removed dimension '{rd}'")
                                else:
                                    # Heuristic per-dimension fallback - use global weights as target
                                    target_multipliers = {p: weights[p] for p in peers} if weights else None
                                    rd_h = self._solve_dimension_weights_heuristic(peers, rd_cats, max_concentration, rd_peer_vols, target_multipliers)
                                    if rd_h:
                                        self.per_dimension_weights[rd] = rd_h
                                        self.weight_methods[rd] = "Per-Dimension-Bayesian"
                                        logger.info(f"Per-dimension Bayesian optimization applied for removed dimension '{rd}' (targeting global weights)")
                                    else:
                                        logger.warning(f"Per-dimension solving failed for removed dimension '{rd}'")
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
                    if adjusted_share > max_concentration + self.tolerance:
                        if original_dim not in peer_violation_dims:
                            peer_violation_dims.append(original_dim)
                
                # Status based on whether there are actual violations, not just high max_share
                status = "OK" if len(peer_violation_dims) == 0 else "VIOLATION"
                logger.info(f"  {peer}: multiplier={weights[peer]:.4f}, max_adjusted_share={peer_max_share:.2f}% [{status}]")
                
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
                                
                                if adjusted_share > max_concentration + self.tolerance:
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
                            vd_h = self._solve_dimension_weights_heuristic(peers, vd_cats, max_concentration, vd_peer_vols, target_multipliers)
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
        
        # Get all peers from global_weights if available, otherwise from entity_totals
        if self.consistent_weights and self.global_weights:
            all_peers = list(self.global_weights.keys())
        else:
            # Extract unique peers from entity_totals (which can be Series or dict)
            if time_period and time_period != "General":
                all_peers = list(set(k[0] if isinstance(k, tuple) else k for k in entity_totals.index))
            else:
                all_peers = list(entity_totals.index)
        
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
            def get_mult(p: str) -> float:
                if dimension_column in self.per_dimension_weights and p in self.per_dimension_weights[dimension_column]:
                    return float(self.per_dimension_weights[dimension_column][p])
                if p in self.global_weights:
                    return float(self.global_weights[p].get('multiplier', 1.0))
                return 1.0
            # Calculate weighted average share: sum(category_vol * weight) / sum(total_vol * weight)
            # Use the SAME set of peers (from peer_totals_map) for both numerator and denominator
            total_adjusted_category_volume = sum(peer_category_volumes.get(p, 0.0) * get_mult(p) for p in peer_totals_map.keys())
            total_adjusted_overall_volume = sum(peer_totals_map[p] * get_mult(p) for p in peer_totals_map.keys())
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
            result['Weight Effect (pp)'] = round(peer_balanced_avg - original_peer_avg, 6)
        
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
        
        # Get all peers from global_weights if available, otherwise from entity_totals
        if self.consistent_weights and self.global_weights:
            all_peers = list(self.global_weights.keys())
        else:
            # Extract unique peers from entity_totals (which can be Series or dict)
            if time_period and time_period != "General":
                all_peers = list(set(k[0] if isinstance(k, tuple) else k for k in entity_totals.index))
            else:
                all_peers = list(entity_totals.index)
        
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
            def get_mult(p: str) -> float:
                if dimension_column in self.per_dimension_weights and p in self.per_dimension_weights[dimension_column]:
                    return float(self.per_dimension_weights[dimension_column][p])
                if p in self.global_weights:
                    return float(self.global_weights[p].get('multiplier', 1.0))
                return 1.0
            # Calculate weighted average rate: sum(rate * weight * den) / sum(weight * den)
            # Use the SAME set of peers (from peer_totals_map) for consistency
            total_adjusted_den = sum(peer_category_dens.get(p, 0.0) * get_mult(p) for p in peer_totals_map.keys())
            peer_balanced_rate = 0.0
            for p in peer_totals_map.keys():
                # Only include peers with denominator > 0 in the weighted average
                if peer_category_dens.get(p, 0.0) > 0:
                    rate = (peer_category_nums.get(p, 0.0) / peer_category_dens[p] * 100.0)
                    adjusted_weight = (peer_category_dens[p] * get_mult(p) / total_adjusted_den * 100.0) if total_adjusted_den > 0 else 0.0
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

            result['Weight Effect (pp)'] = round(peer_balanced_rate - original_peer_rate, 6)
        
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
        if not self.debug_mode or not self.consistent_weights:
            return pd.DataFrame()
        validation_rows: List[Dict[str, Any]] = []
        peers = list(self.global_weights.keys())
        peer_count = len(peers)
        if peer_count >= 10: max_concentration = 40.0
        elif peer_count >= 7: max_concentration = 35.0
        elif peer_count >= 6: max_concentration = 30.0
        elif peer_count >= 5: max_concentration = 25.0
        elif peer_count >= 4: max_concentration = 35.0
        else: max_concentration = 50.0
        weights = {p: self.global_weights[p]['multiplier'] for p in peers}
        for dimension in dimensions:
            dim_weights = self.per_dimension_weights.get(dimension, weights)
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
                        for peer_info in peer_data:
                            peer, peer_vol, peer_weight = peer_info['peer'], peer_info['volume'], dim_weights.get(peer_info['peer'], 1.0)
                            original_share = (peer_vol / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                            balanced_vol = peer_vol * peer_weight
                            balanced_share = (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                            compliant = balanced_share <= max_concentration + self.tolerance
                            violation_margin = balanced_share - max_concentration if balanced_share > max_concentration else 0.0
                            validation_rows.append({'Dimension': dimension, 'Time_Period': time_period, 'Category': category, 'Peer': peer, 'Weight_Source': weight_source, 'Weight_Method': weight_method, 'Multiplier': peer_weight, 'Original_Volume': peer_vol, 'Original_Share_%': round(original_share, 4), 'Balanced_Volume': balanced_vol, 'Balanced_Share_%': round(balanced_share, 4), 'Privacy_Cap_%': max_concentration, 'Tolerance_%': self.tolerance, 'Compliant': 'Yes' if compliant else 'No', 'Violation_Margin_%': round(violation_margin, 4) if violation_margin > 0 else 0.0})
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
                    for peer_info in peer_data:
                        peer, peer_vol, peer_weight = peer_info['peer'], peer_info['volume'], dim_weights.get(peer_info['peer'], 1.0)
                        original_share = (peer_vol / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                        balanced_vol = peer_vol * peer_weight
                        balanced_share = (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                        compliant = balanced_share <= max_concentration + self.tolerance
                        violation_margin = balanced_share - max_concentration if balanced_share > max_concentration else 0.0
                        validation_rows.append({'Dimension': dimension, 'Time_Period': None, 'Category': category, 'Peer': peer, 'Weight_Source': weight_source, 'Weight_Method': weight_method, 'Multiplier': peer_weight, 'Original_Volume': peer_vol, 'Original_Share_%': round(original_share, 4), 'Balanced_Volume': balanced_vol, 'Balanced_Share_%': round(balanced_share, 4), 'Privacy_Cap_%': max_concentration, 'Tolerance_%': self.tolerance, 'Compliant': 'Yes' if compliant else 'No', 'Violation_Margin_%': round(violation_margin, 4) if violation_margin > 0 else 0.0})
        return pd.DataFrame(validation_rows)
