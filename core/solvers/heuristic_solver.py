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
    
    def solve(self, request: SolverRequest) -> Optional[SolverResult]:
        """
        Solve optimization problem using heuristics.
        """
        if not _SCIPY_AVAILABLE:
            logger.info("SciPy not available, skipping heuristic solver.")
            return None

        solver_request = request
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
        
        # Build each constraint once.  The former implementation rescanned the
        # complete category list for every unique key, which is quadratic and
        # makes production-sized time-aware analyses appear to hang before the
        # optimizer even starts.
        constraint_volumes: Dict[Any, np.ndarray] = {}
        for cat in categories:
            key = (cat['dimension'], cat['category'], cat.get('time_period'))
            row = constraint_volumes.get(key)
            if row is None:
                row = np.zeros(len(peers), dtype=float)
                constraint_volumes[key] = row
            peer_pos = peer_index.get(cat['peer'])
            if peer_pos is not None:
                # Preserve the previous last-record-wins behavior for duplicate
                # peer/key records.
                row[peer_pos] = float(cat.get('category_volume', 0.0))

        unique_keys_list = list(constraint_volumes)
        volume_matrix = np.vstack([constraint_volumes[key] for key in unique_keys_list])

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

        # Pre-calculate constraint data and encode it as arrays so every
        # L-BFGS-B objective evaluation is vectorized across constraints.
        rep_weights = np.ones(len(unique_keys_list), dtype=float)
        enforce_mask = np.zeros(len(unique_keys_list), dtype=bool)
        thresholds_by_row: List[List[Tuple[int, float]]] = []
        for row_idx, key in enumerate(unique_keys_list):
            dim, _, _ = key
            peer_cat_vols = {
                peer: float(volume_matrix[row_idx, peer_index[peer]])
                for peer in peers
            }

            stats = constraint_stats.get(key)
            rep_weight = self._representativeness_weight(stats)
            rep_weights[row_idx] = rep_weight

            enforce = False
            thresholds = None
            if enforce_additional and rule_name and min_entities_check:
                enforce, _, thresholds, _ = self._assess_additional_constraints_applicability(
                    rule_name, dim, peer_cat_vols, stats, enforce_additional, dynamic_enabled, time_column
                )

            enforce_mask[row_idx] = enforce
            if enforce:
                if thresholds is None:
                    thresholds = PrivacyValidator.get_penalty_thresholds(rule_name)
                tiers = sorted((thresholds or {}).items(), key=lambda item: item[1][1], reverse=True)
                cumulative_count = 0
                row_thresholds: List[Tuple[int, float]] = []
                for _tier_name, (min_count, threshold) in tiers:
                    ordinal_idx = cumulative_count + int(min_count) - 1
                    row_thresholds.append((ordinal_idx, float(threshold)))
                    cumulative_count += int(min_count)
                thresholds_by_row.append(row_thresholds)
            else:
                thresholds_by_row.append([])

        # Group each tier ordinal into vector lookups. Rules currently expose
        # at most two tiers, but this representation remains generic.
        tier_lookups: List[Tuple[np.ndarray, np.ndarray, np.ndarray]] = []
        max_tiers = max((len(tiers) for tiers in thresholds_by_row), default=0)
        for tier_pos in range(max_tiers):
            rows: List[int] = []
            ordinals: List[int] = []
            thresholds: List[float] = []
            for row_idx, tiers in enumerate(thresholds_by_row):
                if tier_pos < len(tiers):
                    ordinal_idx, threshold = tiers[tier_pos]
                    rows.append(row_idx)
                    ordinals.append(ordinal_idx)
                    thresholds.append(threshold)
            tier_lookups.append(
                (
                    np.asarray(rows, dtype=int),
                    np.asarray(ordinals, dtype=int),
                    np.asarray(thresholds, dtype=float),
                )
            )

        def objective(weight_array):
            max_share = max_concentration + tolerance
            weighted = volume_matrix * np.asarray(weight_array, dtype=float)
            totals = weighted.sum(axis=1)
            shares = np.divide(
                weighted * 100.0,
                totals[:, None],
                out=np.zeros_like(weighted),
                where=totals[:, None] > 0,
            )

            excess = np.maximum(shares - max_share, 0.0)
            violation_penalty = float(np.sum(rep_weights[:, None] * excess * excess))

            additional_penalty = 0.0
            if enforce_additional and rule_name:
                if not min_entities_check:
                    additional_penalty = shortfall_penalty * len(unique_keys_list)
                elif tier_lookups:
                    shares_desc = np.sort(shares, axis=1)[:, ::-1]
                    for rows, ordinals, thresholds in tier_lookups:
                        if rows.size == 0:
                            continue
                        observed = shares_desc[rows, ordinals]
                        shortfalls = np.maximum(thresholds - observed, 0.0)
                        additional_penalty += float(
                            np.sum(rep_weights[rows] * shortfalls * shortfalls)
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
        
        residual_cap_violation = False
        residual_additional_violation = False
        max_share = max_concentration + tolerance
        optimized_array = np.asarray([optimized_weights[p] for p in peers], dtype=float)
        weighted = volume_matrix * optimized_array
        totals = weighted.sum(axis=1)
        shares = np.divide(
            weighted * 100.0,
            totals[:, None],
            out=np.zeros_like(weighted),
            where=totals[:, None] > 0,
        )
        residual_cap_violation = bool(np.any(shares > max_share + 1e-9))
        if enforce_additional and rule_name:
            if not min_entities_check:
                residual_additional_violation = True
            else:
                for row_idx in np.flatnonzero(enforce_mask):
                    passed, _details = PrivacyValidator.evaluate_additional_constraints(
                        shares[row_idx].tolist(), rule_name
                    )
                    if not passed:
                        residual_additional_violation = True
                        break

        success = bool(result.success)
        if residual_cap_violation or residual_additional_violation:
            success = False

        # Stats are minimal for heuristic
        stats = {
            'success': success,
            'converged': success,
            'message': result.message,
            'residual_cap_violation': residual_cap_violation,
            'residual_additional_violation': residual_additional_violation,
        }
        
        return SolverResult(
            weights=optimized_weights,
            method='heuristic',
            stats=stats,
            success=success
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
