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
        target_entity: str,
        entity_column: str = 'entity_identifier',
        bic_percentile: float = 0.85,
        debug_mode: bool = False,
        consistent_weights: bool = False,
        max_iterations: int = 1000,
        tolerance: float = 1.0,
        max_weight: float = 10.0,
        min_weight: float = 0.01,
        volume_preservation_strength: float = 0.5
    ):
        """
        Initialize dimensional analyzer.
        
        Parameters:
        -----------
        target_entity : str
            Name of the target entity to analyze
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
            Strength of volume preservation (0.0-1.0, default: 0.5)
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
        self.volume_preservation_strength = volume_preservation_strength
        self.global_weights = {}  # Store global weights for consistent mode
        self.weights_data = []  # Store weights for debug reporting
        # New: store per-dimension specific weights when global LP drops some dimensions
        self.per_dimension_weights: Dict[str, Dict[str, float]] = {}
        self.global_dimensions_used: List[str] = []
        self.removed_dimensions: List[str] = []
        logger.info(f"Initialized DimensionalAnalyzer for entity: {target_entity}")
        if debug_mode:
            logger.info("Debug mode enabled - will include unweighted averages and weights tracking")
        if consistent_weights:
            logger.info("Consistent weights mode enabled - same privacy-constrained weights across all dimensions")
            logger.info(f"Weight parameters: max_iterations={max_iterations}, tolerance={tolerance}%, "
                       f"max_weight={max_weight}x, min_weight={min_weight}x, volume_preservation={volume_preservation_strength}")
    
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
        Minimizes L1 distance to 1.0 (optionally volume-aware) within [min_weight, max_weight] bounds.
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
        # Variables: [m (P), t_plus (P), t_minus (P)]
        n_vars = 3 * P
        # Objective: minimize sum_p w_p (t_plus_p + t_minus_p)
        # Build simple weights (1.0) optionally scaled by peer volume preservation
        peer_vol_arr = np.array([peer_volumes.get(p, 0.0) for p in peers], dtype=float)
        if peer_vol_arr.sum() > 0:
            vol_w = peer_vol_arr / max(peer_vol_arr.mean(), 1e-9)
        else:
            vol_w = np.ones(P, dtype=float)
        base_w = np.ones(P, dtype=float)
        w = (1.0 - self.volume_preservation_strength) * base_w + self.volume_preservation_strength * vol_w
        c = np.concatenate([np.zeros(P, dtype=float), w, w])

        A_ub_rows: List[np.ndarray] = []
        b_ub: List[float] = []

        # Share cap constraints for each category and each peer
        for v in cat_vectors:
            # Skip empty categories (already filtered)
            for p_idx in range(P):
                # Build coefficients for m variables
                coeff_m = (-cap) * v.copy()
                coeff_m[p_idx] += v[p_idx]  # (1-cap) * v_p
                # Full row across all variables
                row = np.zeros(n_vars, dtype=float)
                row[0:P] = coeff_m
                # t variables have 0 coeff in these constraints
                A_ub_rows.append(row)
                b_ub.append(0.0)

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

        # Solve LP
        try:
            res = linprog(c=c, A_ub=A_ub, b_ub=b_ub_arr, A_eq=None, b_eq=None, bounds=bounds, method='highs')  # type: ignore
        except Exception as e:  # pragma: no cover
            logger.error(f"LP solver error: {e}")
            return None

        if res is None or not res.success:
            logger.warning("LP solver failed or found no feasible solution; falling back to heuristic.")
            return None

        x = res.x
        m = x[0:P].copy()

        # Optional rescale to bring average near 1.0 without violating bounds
        avg = float(m.mean()) if P > 0 else 1.0
        if avg > 0:
            k_target = 1.0 / avg
            # Feasible k within bounds
            k_min = max(self.min_weight / mi for mi in m if mi > 0)
            k_max = min(self.max_weight / mi for mi in m if mi > 0)
            k = min(max(k_target, k_min), k_max)
            m = m * k
            # Final clip (should be redundant)
            m = np.clip(m, self.min_weight, self.max_weight)

        return {peer: float(m[peer_index[peer]]) for peer in peers}

    def _build_categories(self, df: pd.DataFrame, metric_col: str, dimensions: List[str]) -> Tuple[List[Dict[str, Any]], Dict[str, float], List[str]]:
        """Aggregate by entity and dimension categories for the given dimensions."""
        all_categories: List[Dict[str, Any]] = []
        for dim in dimensions:
            entity_dim_agg = df.groupby([self.entity_column, dim]).agg({metric_col: 'sum'}).reset_index()
            entity_totals = entity_dim_agg.groupby(self.entity_column)[metric_col].sum()
            categories = entity_dim_agg[dim].unique()
            for category in categories:
                category_df = entity_dim_agg[entity_dim_agg[dim] == category].copy()
                peer_df = category_df[category_df[self.entity_column] != self.target_entity]
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

    def _store_final_weights(self, peers: List[str], peer_volumes: Dict[str, float], weights: Dict[str, float]) -> None:
        """Persist final weights into self.global_weights as dict with volume, weight, multiplier."""
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
        # Store
        self.global_weights.clear()
        total_adjusted_vol = sum(peer_volumes.get(p, 0.0) * weights[p] for p in peers) if peers else 0.0
        for peer in peers:
            peer_vol = peer_volumes.get(peer, 0.0)
            adjusted_vol = peer_vol * weights[peer]
            final_weight_pct = (adjusted_vol / total_adjusted_vol * 100) if total_adjusted_vol > 0 else 0
            self.global_weights[peer] = {'volume': peer_vol, 'weight': final_weight_pct, 'multiplier': weights[peer]}

    def calculate_global_privacy_weights(
        self, 
        df: pd.DataFrame, 
        metric_col: str,
        dimensions: List[str]
    ) -> None:
        """
        Calculate privacy-constrained weights that work across ALL dimension categories.
        Uses iterative algorithm to find weights that satisfy privacy rules globally.
        
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

        if lp_solution is None:
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
                        rd_cats, _, _ = self._build_categories(df, metric_col, [rd])
                        if rd_cats:
                            rd_sol = self._solve_global_weights_lp(peers, rd_cats, max_concentration, peer_volumes)
                            if rd_sol is not None:
                                self.per_dimension_weights[rd] = rd_sol
                                logger.info(f"Per-dimension LP succeeded for removed dimension '{rd}'")
                            else:
                                logger.warning(f"Per-dimension LP failed for removed dimension '{rd}'")
                    break

        else:
            weights = lp_solution
            converged = True

        self.global_dimensions_used = used_dimensions
        self.removed_dimensions = removed_dimensions

        if converged:
            # Store and validate
            self._store_final_weights(peers, peer_volumes, weights)
            val_dims_set = set((c['dimension'], c['category']) for c in all_categories if c['dimension'] in used_dimensions)
            logger.info("\nGlobal weights validation across all {} categories:".format(len(val_dims_set)))
            logger.info("\nFinal global weight multipliers:")
            for peer in sorted(peers, key=lambda p: weights[p], reverse=True):
                peer_max_share = 0.0
                for cat in all_categories:
                    if cat['dimension'] not in used_dimensions or cat['peer'] != peer:
                        continue
                    category_vol_weighted = cat['category_volume'] * weights[peer]
                    total_weighted = sum(
                        c['category_volume'] * weights[c['peer']]
                        for c in all_categories
                        if c['dimension'] in used_dimensions and c['dimension'] == cat['dimension'] and c['category'] == cat['category']
                    )
                    adjusted_share = (category_vol_weighted / total_weighted * 100) if total_weighted > 0 else 0
                    peer_max_share = max(peer_max_share, adjusted_share)
                status = "OK" if peer_max_share <= max_concentration + self.tolerance else "VIOLATION"
                logger.info(f"  {peer}: multiplier={weights[peer]:.4f}, max_adjusted_share={peer_max_share:.2f}% [{status}]")
            if removed_dimensions:
                logger.info(f"Global weights computed over dimensions: {used_dimensions}; removed due to infeasibility: {removed_dimensions}")
                if self.per_dimension_weights:
                    logger.info(f"Per-dimension weights available for: {list(self.per_dimension_weights.keys())}")
            return

        # If still not converged, fall back to heuristic (original loop)
        logger.warning("LP solver failed for all tried subsets; falling back to heuristic.")
        # Heuristic iterative adjustment using all dimensions
        last_max_violation = float('inf')
        stagnation_count = 0
        for iteration in range(self.max_iterations):
            violations = []
            for cat in all_categories:
                peer = cat['peer']
                category_vol_weighted = cat['category_volume'] * weights[peer]
                total_weighted = sum(
                    c['category_volume'] * weights[c['peer']]
                    for c in all_categories
                    if c['dimension'] == cat['dimension'] and c['category'] == cat['category']
                )
                adjusted_share = (category_vol_weighted / total_weighted * 100) if total_weighted > 0 else 0
                if adjusted_share > max_concentration:
                    violations.append({'peer': peer, 'dimension': cat['dimension'], 'category': cat['category'], 'share': adjusted_share, 'excess': adjusted_share - max_concentration})
            max_violation_this_iter = max([v['excess'] for v in violations], default=0)
            if max_violation_this_iter <= self.tolerance:
                logger.info(f"Global weights converged after {iteration} iterations")
                break
            if abs(max_violation_this_iter - last_max_violation) < 0.01:
                stagnation_count += 1
            else:
                stagnation_count = 0
            last_max_violation = max_violation_this_iter
            base_alpha = 0.05 + (iteration / self.max_iterations) * 0.6
            if stagnation_count > 10:
                base_alpha *= 1.5
            for violation in violations:
                peer = violation['peer']
                reduction_factor = 1.0 - (base_alpha * (violation['excess'] / max_concentration))
                weights[peer] *= max(0.1, reduction_factor)
            if iteration < self.max_iterations * 0.6:
                violating_peers = set([v['peer'] for v in violations])
                for peer in peers:
                    if peer not in violating_peers:
                        peer_vol = peer_volumes.get(peer, 1)
                        total_vol = sum(peer_volumes.values())
                        relative_size = peer_vol / total_vol if total_vol > 0 else 1
                        boost_factor = 1.0 + (base_alpha * 0.3 * (1.0 - relative_size))
                        weights[peer] *= boost_factor
            preservation_progress = iteration / self.max_iterations
            adaptive_preservation = self.volume_preservation_strength * (1.0 - preservation_progress * 0.5)
            for peer in peers:
                peer_vol = peer_volumes.get(peer, 1)
                total_vol = sum(peer_volumes.values())
                natural_weight = peer_vol / total_vol if total_vol > 0 else (1.0 / len(peers))
                weights[peer] = weights[peer] * (1 - adaptive_preservation) + natural_weight * len(peers) * adaptive_preservation
        else:
            logger.warning(f"Global weights did not fully converge after {self.max_iterations} iterations")
            logger.warning(f"Max violation: {max_violation_this_iter:.2f}% (tolerance: {self.tolerance}%)")
        self._store_final_weights(peers, peer_volumes, weights)
        # Validate on all categories
        logger.info("\nGlobal weights validation across all {} categories:".format(len(set([(c['dimension'], c['category']) for c in all_categories]))))
        logger.info("\nFinal global weight multipliers:")
        for peer in sorted(peers, key=lambda p: weights[p], reverse=True):
            peer_max_share = 0
            for cat in all_categories:
                if cat['peer'] == peer:
                    category_vol_weighted = cat['category_volume'] * weights[peer]
                    total_weighted = sum(
                        c['category_volume'] * weights[c['peer']]
                        for c in all_categories
                        if c['dimension'] == cat['dimension'] and c['category'] == cat['category']
                    )
                    adjusted_share = (category_vol_weighted / total_weighted * 100) if total_weighted > 0 else 0
                    peer_max_share = max(peer_max_share, adjusted_share)
            status = "OK" if peer_max_share <= max_concentration + self.tolerance else "VIOLATION"
            logger.info(f"  {peer}: multiplier={weights[peer]:.4f}, max_adjusted_share={peer_max_share:.2f}% [{status}]")

    def identify_dimensional_columns(
        self,
        df: pd.DataFrame,
        exclude_columns: Optional[List[str]] = None
    ) -> List[str]:
        """
        Automatically identify dimensional columns in the dataset.
        
        Parameters:
        -----------
        df : DataFrame
            Input dataframe
        exclude_columns : List[str], optional
            Columns to exclude from dimensional analysis
        
        Returns:
        --------
        List[str]
            List of dimensional column names
        """
        if exclude_columns is None:
            exclude_columns = []
        
        # Default exclusions
        default_exclusions = [
            self.entity_column,
            'peer_group',
            'ano_mes',  # Time period
            'issuer_name',  # Entity name
            'mcc_cd',  # Too granular
            'merchant_group',  # Too granular
            'txn_cnt',  # Metric column
            'tpv',  # Metric column
            'app_cnt',  # Metric column
            'approval_rate',  # Calculated metric
        ]
        
        exclude_columns.extend(default_exclusions)
        
        # Find categorical columns with reasonable cardinality
        dimensional_cols = []
        for col in df.columns:
            if col in exclude_columns:
                continue
            
            # Check if column is categorical or has low cardinality
            unique_count = df[col].nunique()
            
            if unique_count < 100 and unique_count > 1:  # Reasonable cardinality
                dimensional_cols.append(col)
                logger.info(f"Identified dimensional column: {col} ({unique_count} categories)")
        
        return dimensional_cols
    
    def analyze_dimension_share(
        self,
        df: pd.DataFrame,
        dimension_column: str,
        metric_col: str = 'txn_cnt'
    ) -> pd.DataFrame:
        """
        Analyze a single dimension with SHARE distribution metrics.
        
        Share = percentage of entity's total volume that falls in each category.
        For example: "30% of target's transactions are Domestic, 70% are Cross-border"
        
        Parameters:
        -----------
        df : DataFrame
            Input dataframe
        dimension_column : str
            Name of the dimension to analyze
        metric_col : str
            Metric column to analyze (default: 'txn_cnt' for transaction count)
        
        Returns:
        --------
        DataFrame
            Analysis results with columns: Category, Peer_Balanced_Avg_%, BIC_%
        """
        logger.info(f"Running SHARE analysis for dimension: {dimension_column}")
        
        # Note: Global privacy weights are calculated once before analyzing dimensions
        # (in benchmark.py) when consistent_weights mode is enabled
        
        # Aggregate by entity and dimension category
        entity_category_agg = df.groupby([self.entity_column, dimension_column]).agg({
            metric_col: 'sum'
        }).reset_index()
        
        # Calculate total for each entity
        entity_totals = entity_category_agg.groupby(self.entity_column)[metric_col].sum()
        
        results = []
        categories = entity_category_agg[dimension_column].unique()
        
        for category in categories:
            category_df = entity_category_agg[entity_category_agg[dimension_column] == category].copy()
            
            # Separate target and peers
            target_df = category_df[category_df[self.entity_column] == self.target_entity]
            peer_df = category_df[category_df[self.entity_column] != self.target_entity]
            
            if len(peer_df) == 0:
                logger.warning(f"No peers found for category '{category}'")
                continue
            
            # Target entity's share
            target_category_vol = target_df[metric_col].sum()
            target_total_vol = entity_totals[self.target_entity]
            target_share = (target_category_vol / target_total_vol * 100) if target_total_vol > 0 else 0
            
            # Balanced peer average (weighted)
            peer_category_total = 0
            peer_overall_total = 0
            peer_weights = {}  # Track weights for debug mode
            peer_category_volumes = {}  # Track category volumes for debug mode
            
            for peer_entity in peer_df[self.entity_column].unique():
                peer_category_vol = peer_df[peer_df[self.entity_column] == peer_entity][metric_col].sum()
                peer_total_vol = entity_totals[peer_entity]
                peer_category_total += peer_category_vol
                peer_overall_total += peer_total_vol
                
                # Track weight and category volume for this peer
                if self.debug_mode:
                    peer_weights[peer_entity] = peer_total_vol
                    peer_category_volumes[peer_entity] = peer_category_vol
            
            peer_balanced_avg = (peer_category_total / peer_overall_total * 100) if peer_overall_total > 0 else 0
            
            # Store weights data for debug reporting
            if self.debug_mode:
                # First, calculate total adjusted volume for this category
                # Use per-dimension weights if available; otherwise global
                def get_mult(p: str) -> float:
                    if self.consistent_weights:
                        if dimension_column in self.per_dimension_weights and p in self.per_dimension_weights[dimension_column]:
                            return float(self.per_dimension_weights[dimension_column][p])
                        if p in self.global_weights:
                            return float(self.global_weights[p].get('multiplier', 1.0))
                    return 1.0
                total_adjusted_volume = sum(
                    peer_category_volumes[p] * get_mult(p)
                    for p in peer_weights.keys()
                )
                
                for peer_entity, peer_total in peer_weights.items():
                    peer_category_vol = peer_category_volumes[peer_entity]
                    raw_concentration = (peer_category_vol / peer_category_total * 100) if peer_category_total > 0 else 0
                    weight_multiplier = get_mult(peer_entity)
                    adjusted_volume = peer_category_vol * weight_multiplier
                    adjusted_share = (adjusted_volume / total_adjusted_volume * 100) if total_adjusted_volume > 0 else 0
                    peer_share_pct = (peer_category_vol / peer_total * 100) if peer_total > 0 else 0
                    contribution = (peer_share_pct * adjusted_share / 100)
                    self.weights_data.append({
                        'Dimension': dimension_column,
                        'Category': str(category),
                        'Peer': peer_entity,
                        'Total_Volume': peer_total,
                        'Category_Volume': peer_category_vol,
                        'Raw_Concentration_%': round(raw_concentration, 2),
                        'Weight_Multiplier': round(weight_multiplier, 4),
                        'Adjusted_Volume': round(adjusted_volume, 2),
                        'Adjusted_Share_%': round(adjusted_share, 2),
                        'Contribution_pp': round(contribution, 2)
                    })
            
            # Best-in-Class (85th percentile)
            peer_shares = []
            peer_entities_list = []
            for peer_entity in peer_df[self.entity_column].unique():
                peer_category_vol = peer_df[peer_df[self.entity_column] == peer_entity][metric_col].sum()
                peer_total_vol = entity_totals[peer_entity]
                peer_share = (peer_category_vol / peer_total_vol * 100) if peer_total_vol > 0 else 0
                peer_shares.append(peer_share)
                peer_entities_list.append(peer_entity)
            
            # DEBUG: Log peer_shares for investigation
            if self.debug_mode and len(peer_shares) > 0:
                logger.debug(f"Dimension={dimension_column}, Category={category}: "
                           f"peer_shares={[f'{s:.2f}%' for s in peer_shares]}, "
                           f"peers={peer_entities_list[:3]}..., "
                           f"mean={pd.Series(peer_shares).mean():.2f}%")
            
            bic_share = pd.Series(peer_shares).quantile(self.bic_percentile) if len(peer_shares) > 0 else 0
            
            # Calculate unweighted average (simple mean) for debug mode
            unweighted_avg = pd.Series(peer_shares).mean() if len(peer_shares) > 0 else 0
            
            # Calculate distance from peer group
            distance = target_share - peer_balanced_avg
            
            result = {
                'Category': str(category),
                'Player_%': round(target_share, 2),
                'Peer_Balanced_Avg_%': round(peer_balanced_avg, 2),
                'Distance_pp': round(distance, 2),
                'BIC_%': round(bic_share, 2)
            }
            
            # Add debug columns if debug mode is enabled
            if self.debug_mode:
                result['Peer_Unweighted_Avg_%'] = round(unweighted_avg, 2)
                result['Peer_Count'] = len(peer_shares)
            
            results.append(result)
        
        result_df = pd.DataFrame(results)
        logger.info(f"Completed share analysis for {dimension_column}: {len(result_df)} categories")
        
        return result_df
    
    def analyze_dimension_rate(
        self,
        df: pd.DataFrame,
        dimension_column: str,
        total_col: str,
        numerator_col: str
    ) -> pd.DataFrame:
        """
        Analyze a single dimension with RATE metrics (approval rate or fraud rate).
        
        Rate = numerator / total (e.g., approved / transactions for approval rate)
        
        Parameters:
        -----------
        df : DataFrame
            Input dataframe
        dimension_column : str
            Name of the dimension to analyze
        total_col : str
            Column with total count (denominator)
        numerator_col : str
            Column with numerator (approved, fraud, etc.)
        
        Returns:
        --------
        DataFrame
            Analysis results with columns: Category, Peer_Balanced_Rate_%, BIC_%
        """
        logger.info(f"Running RATE analysis for dimension: {dimension_column}")
        
        # Note: Global privacy weights are calculated once before analyzing dimensions
        # (in benchmark.py) when consistent_weights mode is enabled
        
        # Aggregate by entity and dimension category
        entity_category_agg = df.groupby([self.entity_column, dimension_column]).agg({
            total_col: 'sum',
            numerator_col: 'sum'
        }).reset_index()
        
        results = []
        categories = entity_category_agg[dimension_column].unique()
        
        for category in categories:
            category_df = entity_category_agg[entity_category_agg[dimension_column] == category].copy()
            
            # Separate target and peers
            target_df = category_df[category_df[self.entity_column] == self.target_entity]
            peer_df = category_df[category_df[self.entity_column] != self.target_entity]
            
            if len(peer_df) == 0:
                logger.warning(f"No peers found for category '{category}'")
                continue
            
            # Target entity's rate
            target_numerator = target_df[numerator_col].sum()
            target_total = target_df[total_col].sum()
            target_rate = (target_numerator / target_total * 100) if target_total > 0 else 0
            
            # Balanced peer average rate (weighted)
            peer_numerator_total = peer_df[numerator_col].sum()
            peer_total_total = peer_df[total_col].sum()
            peer_balanced_rate = (peer_numerator_total / peer_total_total * 100) if peer_total_total > 0 else 0
            
            # Track weights for debug mode
            if self.debug_mode:
                for peer_entity in peer_df[self.entity_column].unique():
                    peer_entity_df = peer_df[peer_df[self.entity_column] == peer_entity]
                    peer_num = peer_entity_df[numerator_col].sum()
                    peer_tot = peer_entity_df[total_col].sum()
                    
                    # Calculate raw concentration (without weights)
                    raw_concentration = (peer_tot / peer_total_total * 100) if peer_total_total > 0 else 0
                    
                    # Get weight multiplier
                    if self.consistent_weights and peer_entity in self.global_weights:
                        weight_multiplier = self.global_weights[peer_entity].get('multiplier', 1.0)
                        weight_pct = self.global_weights[peer_entity]['weight']
                    else:
                        weight_multiplier = 1.0
                        weight_pct = (peer_tot / peer_total_total * 100) if peer_total_total > 0 else 0
                    
                    # Calculate adjusted volume
                    adjusted_volume = peer_tot * weight_multiplier
                    
                    # Calculate adjusted share (as percentage of total adjusted volume)
                    total_adjusted_volume = 0
                    for p_entity in peer_df[self.entity_column].unique():
                        p_tot = peer_df[peer_df[self.entity_column] == p_entity][total_col].sum()
                        p_mult = self.global_weights[p_entity].get('multiplier', 1.0) if self.consistent_weights and p_entity in self.global_weights else 1.0
                        total_adjusted_volume += p_tot * p_mult
                    
                    adjusted_share = (adjusted_volume / total_adjusted_volume * 100) if total_adjusted_volume > 0 else 0
                    
                    # Calculate contribution to balanced average
                    peer_rate = (peer_num / peer_tot * 100) if peer_tot > 0 else 0
                    contribution = (peer_rate * adjusted_share / 100)
                    
                    self.weights_data.append({
                        'Dimension': dimension_column,
                        'Category': str(category),
                        'Peer': peer_entity,
                        'Total_Volume': peer_tot,
                        'Category_Volume': peer_num,
                        'Raw_Concentration_%': round(raw_concentration, 2),
                        'Weight_Multiplier': round(weight_multiplier, 4),
                        'Adjusted_Volume': round(adjusted_volume, 2),
                        'Adjusted_Share_%': round(adjusted_share, 2),
                        'Contribution_pp': round(contribution, 2)
                    })
            
            # Best-in-Class (percentile of individual peer rates)
            peer_rates = []
            for peer_entity in peer_df[self.entity_column].unique():
                peer_entity_df = peer_df[peer_df[self.entity_column] == peer_entity]
                peer_num = peer_entity_df[numerator_col].sum()
                peer_tot = peer_entity_df[total_col].sum()
                peer_rate = (peer_num / peer_tot * 100) if peer_tot > 0 else 0
                peer_rates.append(peer_rate)
            
            bic_rate = pd.Series(peer_rates).quantile(self.bic_percentile) if len(peer_rates) > 0 else 0
            
            # Calculate unweighted average (simple mean) for debug mode
            unweighted_avg = pd.Series(peer_rates).mean() if len(peer_rates) > 0 else 0
            
            # Calculate distance from peer group
            distance = target_rate - peer_balanced_rate
            
            result = {
                'Category': str(category),
                'Player_%': round(target_rate, 2),
                'Peer_Balanced_Rate_%': round(peer_balanced_rate, 2),
                'Distance_pp': round(distance, 2),
                'BIC_%': round(bic_rate, 2)
            }
            
            # Add debug columns if debug mode is enabled
            if self.debug_mode:
                result['Peer_Unweighted_Avg_%'] = round(unweighted_avg, 2)
                result['Peer_Count'] = len(peer_rates)
            
            results.append(result)
        
        result_df = pd.DataFrame(results)
        logger.info(f"Completed rate analysis for {dimension_column}: {len(result_df)} categories")
        
        return result_df

    # Keep the old analyze_dimension for backward compatibility, but make it call analyze_dimension_share
    def analyze_dimension(
        self,
        df: pd.DataFrame,
        dimension_column: str,
        metric_col: str = 'txn_cnt'
    ) -> pd.DataFrame:
        """
        Analyze a single dimension (defaults to share analysis for backward compatibility).
        
        This method is kept for backward compatibility. New code should use
        analyze_dimension_share() or analyze_dimension_rate() explicitly.
        """
        return self.analyze_dimension_share(df, dimension_column, metric_col)
    
    def get_weights_dataframe(self) -> pd.DataFrame:
        """
        Get the weights data as a DataFrame for debug reporting.
        
        Returns:
        --------
        DataFrame
            Weights data with columns: Dimension, Category, Peer, Total_Volume, Weight_%
        """
        if not self.weights_data:
            return pd.DataFrame()
        
        return pd.DataFrame(self.weights_data)
    
    def analyze_all_dimensions(
        self,
        df: pd.DataFrame,
        dimensional_columns: Optional[List[str]] = None
    ) -> Dict[str, pd.DataFrame]:
        """
        Analyze all dimensional columns with balanced metrics.
        
        Parameters:
        -----------
        df : DataFrame
            Input dataframe
        dimensional_columns : List[str], optional
            List of dimensions to analyze. If None, auto-detect.
        
        Returns:
        --------
        Dict[str, DataFrame]
            Dictionary mapping dimension names to analysis results
        """
        if dimensional_columns is None:
            dimensional_columns = self.identify_dimensional_columns(df)
        
        logger.info(f"Analyzing {len(dimensional_columns)} dimensions")
        
        results = {}
        
        for dim_col in dimensional_columns:
            try:
                dim_results = self.analyze_dimension(
                    df=df,
                    dimension_column=dim_col
                )
                results[dim_col] = dim_results
            except Exception as e:
                logger.error(f"Error analyzing dimension {dim_col}: {str(e)}")
                continue
        
        logger.info(f"Successfully analyzed {len(results)} dimensions")
        
        return results
