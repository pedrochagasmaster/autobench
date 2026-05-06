import logging
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

from core.contracts import SolverRequest

try:
    from scipy.optimize import minimize  # type: ignore
    _SCIPY_AVAILABLE = True
except Exception:
    minimize = None  # type: ignore
    _SCIPY_AVAILABLE = False
from core.privacy_validator import PrivacyValidator
from core.diagnostics_engine import DiagnosticsEngine
from core.constants import DEFAULT_HEURISTIC_VIOLATION_PENALTY_WEIGHT
from core.category_builder import CategoryBuilder
from .base_solver import PrivacySolver, SolverResult

logger = logging.getLogger(__name__)

class HeuristicSolver(PrivacySolver):
    """
    Solves for privacy weights using heuristic optimization (L-BFGS-B).
    Handles complex privacy rules (additional constraints) and dynamic thresholds.
    """
    
    # Defaults from DimensionalAnalyzer
    VIOLATION_PENALTY_WEIGHT = DEFAULT_HEURISTIC_VIOLATION_PENALTY_WEIGHT
    
    def solve(
        self,
        request: Optional[SolverRequest] = None,
        *,
        peers: Optional[List[str]] = None,
        categories: Optional[List[Dict[str, Any]]] = None,
        max_concentration: Optional[float] = None,
        peer_volumes: Optional[Dict[str, float]] = None,
        **kwargs: Any
    ) -> Optional[SolverResult]:
        """
        Solve optimization problem using heuristics.
        
        Expected kwargs:
        - target_weights: Dict[str, float] (optional)
        - min_weight: float
        - max_weight: float
        - tolerance: float
        - max_iterations: int
        - learning_rate: float (finite-difference step size for optimizer)
        - enforce_additional_constraints: bool
        - dynamic_constraints_enabled: bool
        - time_column: str (optional)
        - rule_name: str (optional)
        
        # Dynamic constraint params
        - min_peer_count_for_constraints: int
        - min_effective_peer_count: float
        - min_category_volume_share: float
        - min_overall_volume_share: float
        - min_representativeness: float
        - dynamic_threshold_scale_floor: float
        - dynamic_count_scale_floor: float
        """
        if not _SCIPY_AVAILABLE:
            logger.info("SciPy not available, skipping heuristic solver.")
            return None

        solver_request = self.coerce_request(
            request,
            peers=peers,
            categories=categories,
            max_concentration=max_concentration,
            peer_volumes=peer_volumes,
            **kwargs,
        )
        peers = solver_request.peers
        categories = solver_request.categories
        max_concentration = solver_request.max_concentration
        peer_volumes = solver_request.peer_volumes

        # Config
        target_weights = solver_request.target_weights
        min_weight = solver_request.min_weight
        max_weight = solver_request.max_weight
        tolerance = solver_request.tolerance
        max_iterations = int(solver_request.max_iterations or 500)
        learning_rate = solver_request.learning_rate
        penalty_weight = float(solver_request.violation_penalty_weight)
        enforce_additional = solver_request.enforce_additional_constraints
        dynamic_enabled = solver_request.dynamic_constraints_enabled
        time_column = solver_request.time_column
        rule_name = solver_request.rule_name
        merchant_mode = bool(solver_request.merchant_mode)

        self.min_peer_count_for_constraints = solver_request.min_peer_count_for_constraints
        self.min_effective_peer_count = solver_request.min_effective_peer_count
        self.min_category_volume_share = solver_request.min_category_volume_share
        self.min_overall_volume_share = solver_request.min_overall_volume_share
        self.min_representativeness = solver_request.min_representativeness
        self.dynamic_threshold_scale_floor = solver_request.dynamic_threshold_scale_floor
        self.dynamic_count_scale_floor = solver_request.dynamic_count_scale_floor
        self.representativeness_penalty_floor = float(solver_request.representativeness_penalty_floor)
        self.representativeness_penalty_power = float(solver_request.representativeness_penalty_power)
        
        # Prepare
        peer_index = {peer: i for i, peer in enumerate(peers)}
        
        # Build constraint stats
        constraint_stats = DiagnosticsEngine.build_constraint_stats(categories, peers, peer_volumes)
        
        # Identify unique constraints
        unique_keys = set()
        for cat in categories:
            key = (cat['dimension'], cat['category'], cat.get('time_period'))
            unique_keys.add(key)
        unique_keys_list = list(unique_keys)
        
        # Map constraints
        constraint_map = {}
        for key in unique_keys_list:
            dim, category, time_period = key
            constraint_map[key] = [
                i for i, c in enumerate(categories)
                if c['dimension'] == dim 
                and c['category'] == category 
                and c.get('time_period') == time_period
            ]

        if not rule_name:
            rule_name = PrivacyValidator.select_rule(len(peers), merchant_mode=merchant_mode)

        # Check structural feasibility
        min_entities_check = True
        if enforce_additional and rule_name:
            rule_cfg = PrivacyValidator.get_rule_config(rule_name)
            if rule_cfg and rule_cfg.get('additional'):
                min_entities = int(rule_cfg.get('min_entities', 0))
                if len(peers) < min_entities:
                    min_entities_check = False

        shortfall_penalty = 0.0
        if enforce_additional and rule_name and not min_entities_check:
            min_entities = int(PrivacyValidator.get_rule_config(rule_name).get('min_entities', 0))
            shortfall = max(min_entities - len(peers), 0)
            shortfall_penalty = float(shortfall * shortfall * 100.0)

        # Pre-calculate constraint data
        constraint_data = {}
        for key, cat_indices in constraint_map.items():
            dim, _, _ = key
            matching_cats = [categories[i] for i in cat_indices]
            peer_cat_vols = {p: 0.0 for p in peers}
            for cat in matching_cats:
                peer_cat_vols[cat['peer']] = float(cat.get('category_volume', 0.0))

            stats = constraint_stats.get(key)
            rep_weight = self._representativeness_weight(stats)

            enforce = False
            thresholds = None
            if enforce_additional and rule_name and min_entities_check:
                enforce, _, thresholds, _ = self._assess_additional_constraints_applicability(
                    rule_name, dim, peer_cat_vols, stats, enforce_additional, dynamic_enabled, time_column
                )

            constraint_data[key] = {
                'peer_cat_vols': peer_cat_vols,
                'rep_weight': rep_weight,
                'enforce': enforce,
                'thresholds': thresholds
            }

        def objective(weight_array):
            violation_penalty = 0.0
            additional_penalty = 0.0
            max_share = max_concentration + tolerance
            
            for key in constraint_map.keys():
                data = constraint_data[key]
                peer_cat_vols = data['peer_cat_vols']
                rep_weight = data['rep_weight']

                total_weighted = sum(peer_cat_vols[p] * weight_array[peer_index[p]] for p in peers)
                shares = []

                if total_weighted > 0:
                    for p in peers:
                        cat_vol_weighted = peer_cat_vols[p] * weight_array[peer_index[p]]
                        adjusted_share = (cat_vol_weighted / total_weighted * 100.0)
                        shares.append(adjusted_share)
                        if adjusted_share > max_share: # Simple violation check
                            excess = adjusted_share - max_share
                            violation_penalty += rep_weight * (excess ** 2)
                else:
                    shares = [0.0 for _ in peers]

                if enforce_additional and rule_name:
                    if not min_entities_check:
                        additional_penalty += shortfall_penalty
                    elif data['enforce']:
                        additional_penalty += rep_weight * self._additional_constraints_penalty(
                            shares, rule_name, data['thresholds']
                        )
            
            deviation_penalty = 0.0
            if target_weights:
                for i, peer in enumerate(peers):
                    target = target_weights.get(peer, 1.0)
                    deviation_penalty += (weight_array[i] - target) ** 2
            
            return (violation_penalty + additional_penalty) * penalty_weight + deviation_penalty

        if target_weights:
            x0 = np.array([target_weights.get(peer, 1.0) for peer in peers])
        else:
            x0 = np.ones(len(peers))
        
        bounds = [(min_weight, max_weight) for _ in peers]
        
        options = {'maxiter': max_iterations, 'ftol': 1e-6}
        if learning_rate is not None:
            try:
                learning_rate_val = float(learning_rate)
                if learning_rate_val > 0:
                    # Use learning_rate as the finite-difference step size for gradients
                    options['eps'] = learning_rate_val
            except Exception:
                pass

        result = minimize(
            objective,
            x0=x0,
            method='L-BFGS-B',
            bounds=bounds,
            options=options
        )
        
        optimized_weights = {peer: result.x[i] for i, peer in enumerate(peers)}

        def _normalize_mean(
            weights: Dict[str, float],
            target_mean: float,
            min_w: float,
            max_w: float
        ) -> Dict[str, float]:
            peers_list = list(weights.keys())
            w = np.array([weights[p] for p in peers_list], dtype=float)
            target_sum = target_mean * len(peers_list)
            free = np.ones(len(peers_list), dtype=bool)

            for _ in range(len(peers_list) + 1):
                sum_fixed = float(w[~free].sum())
                sum_free = float(w[free].sum())
                if sum_free <= 0:
                    break
                k = (target_sum - sum_fixed) / sum_free
                w_scaled = w.copy()
                w_scaled[free] = w[free] * k

                below = w_scaled < min_w
                above = w_scaled > max_w
                newly_fixed = (below | above) & free
                if not newly_fixed.any():
                    w = w_scaled
                    break

                w[below] = min_w
                w[above] = max_w
                free = free & ~newly_fixed

            return {p: float(w[i]) for i, p in enumerate(peers_list)}

        optimized_weights = _normalize_mean(optimized_weights, 1.0, min_weight, max_weight)
        
        residual_violation = False
        for key in constraint_map.keys():
            data = constraint_data[key]
            peer_cat_vols = data['peer_cat_vols']
            total_weighted = sum(
                peer_cat_vols[p] * optimized_weights[p] for p in peers
            )
            if total_weighted <= 0:
                continue
            for p in peers:
                share = (peer_cat_vols[p] * optimized_weights[p]) / total_weighted * 100.0
                if share > max_concentration + max(tolerance, 1e-9):
                    residual_violation = True
                    break
            if residual_violation:
                break

        # Solver success is the benchmark-facing feasibility verdict; keep the
        # raw SciPy convergence flag separately for diagnostics.
        if tolerance <= 1e-9 and residual_violation:
            converged = False
        else:
            converged = bool(result.success)

        stats = {
            'success': converged,
            'scipy_success': bool(result.success),
            'residual_violation': residual_violation,
            'message': result.message,
        }
        
        return SolverResult(
            weights=optimized_weights,
            method='heuristic',
            stats=stats,
            success=converged
        )

    def _representativeness_weight(self, stats: Optional[Dict[str, float]]) -> float:
        if not stats:
            return 1.0
        rep = float(stats.get('representativeness', 0.0))
        scaled = rep ** self.representativeness_penalty_power if rep > 0 else 0.0
        return max(self.representativeness_penalty_floor, scaled)

    def _participant_count(self, peer_volumes: Dict[str, float]) -> int:
        return sum(1 for v in peer_volumes.values() if v > 0)

    def _assess_additional_constraints_applicability(
        self,
        rule_name: Optional[str],
        dimension: Optional[str],
        peer_volumes: Dict[str, float],
        stats: Optional[Dict[str, float]],
        enforce_additional: bool,
        dynamic_enabled: bool,
        time_column: Optional[str]
    ) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]], bool]:
        if not enforce_additional or not rule_name:
            return False, 'disabled', None, False
        
        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
        if not rule_cfg or not rule_cfg.get('additional'):
            return False, 'no_additional', None, False

        if dimension:
            if dimension == '_TIME_TOTAL':
                return False, 'time_total', None, False
            if time_column and dimension.startswith(f"{CategoryBuilder.TIME_TOTAL_DIMENSION_PREFIX}{time_column}"):
                return False, 'time_total', None, False

        min_entities = int(rule_cfg.get('min_entities', 0))
        participants = self._participant_count(peer_volumes)
        if min_entities and participants < min_entities:
            return False, 'low_peers', None, False

        if not dynamic_enabled or not stats:
            return True, None, None, False

        if participants < self.min_peer_count_for_constraints:
            return False, 'low_peers', None, False
        if float(stats.get('effective_peers', 0.0)) < self.min_effective_peer_count:
            return False, 'low_effective_peers', None, False
        if (float(stats.get('volume_share', 0.0)) < self.min_category_volume_share or 
            float(stats.get('overall_share', 0.0)) < self.min_overall_volume_share):
            return False, 'low_volume', None, False
        if float(stats.get('representativeness', 0.0)) < self.min_representativeness:
            return False, 'low_representativeness', None, False

        thresholds, relaxed = self._get_dynamic_additional_thresholds(
            rule_name, participants, float(stats.get('representativeness', 0.0))
        )
        return True, None, thresholds, relaxed

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
            return {'tier_1': (dyn_count, dyn_threshold)}, relaxed
        
        if rule_name == '7/35':
            min_count_15 = int(additional.get('min_count_15', 2))
            min_count_8 = int(additional.get('min_count_8', 1))
            dyn_count_15 = max(1, int(round(min_count_15 * count_scale)))
            dyn_count_8 = max(0, int(round(min_count_8 * count_scale)))
            return {
                'tier_1': (dyn_count_15, 15.0 * rep_scale),
                'tier_2': (dyn_count_8, 8.0 * rep_scale)
            }, relaxed
            
        if rule_name == '10/40':
            min_count_20 = int(additional.get('min_count_20', 2))
            min_count_10 = int(additional.get('min_count_10', 1))
            dyn_count_20 = max(1, int(round(min_count_20 * count_scale)))
            dyn_count_10 = max(0, int(round(min_count_10 * count_scale)))
            return {
                'tier_1': (dyn_count_20, 20.0 * rep_scale),
                'tier_2': (dyn_count_10, 10.0 * rep_scale)
            }, relaxed
        return None, False

    def _additional_constraints_penalty(
        self,
        shares: List[float],
        rule_name: str,
        thresholds: Optional[Dict[str, Any]] = None,
    ) -> float:
        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
        if not rule_cfg or not rule_cfg.get('additional'):
            return 0.0

        shares_sorted = sorted(shares, reverse=True)
        penalty = 0.0

        if thresholds is None:
            thresholds = PrivacyValidator.get_penalty_thresholds(rule_name)
        
        if not thresholds:
            return 0.0
        
        tiers = sorted(thresholds.items(), key=lambda x: x[1][1], reverse=True)
        cumulative_count = 0
        
        for tier_name, (min_count, threshold) in tiers:
            idx = cumulative_count + min_count - 1
            observed = shares_sorted[idx] if idx < len(shares_sorted) else 0.0
            penalty += max(0.0, threshold - observed) ** 2
            cumulative_count += min_count

        return penalty
