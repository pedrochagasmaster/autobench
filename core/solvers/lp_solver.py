import logging
import numpy as np
from typing import Any, Dict, List, Optional, Tuple

from core.contracts import SolverRequest
from .base_solver import PrivacySolver, SolverResult

logger = logging.getLogger(__name__)

try:
    from scipy.optimize import linprog  # type: ignore
    _SCIPY_AVAILABLE = True
except ImportError:
    linprog = None
    _SCIPY_AVAILABLE = False

class LPSolver(PrivacySolver):
    """
    Solves for privacy weights using Linear Programming (SciPy Highs).
    Strictly enforces per-category share caps while minimizing deviation from 1.0.
    """
    
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
        Solve global weights optimization problem.
        
        Expected kwargs:
        - rank_preservation_strength: float (default 0.1)
        - tolerance: float (default 0.1)
        - volume_weighted_penalties: bool (default False)
        - volume_weighting_exponent: float (default 1.0)
        - min_weight: float (default 0.5)
        - max_weight: float (default 3.0)
        - lambda_penalty: float (optional override for cap slack penalty)
        - max_iterations: int (optional LP iteration cap)
        """
        if not _SCIPY_AVAILABLE:
            logger.info("SciPy not available, skipping LP solver.")
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

        # Extract config
        rank_preservation_strength = float(solver_request.rank_preservation_strength)
        tolerance = float(solver_request.tolerance)
        volume_weighted_penalties = bool(solver_request.volume_weighted_penalties)
        volume_weighting_exponent = float(solver_request.volume_weighting_exponent)
        min_weight = float(solver_request.min_weight)
        max_weight = float(solver_request.max_weight)
        lambda_penalty = solver_request.lambda_penalty
        max_iterations = solver_request.max_iterations
        max_iterations_int = None
        if max_iterations is not None:
            try:
                max_iterations_int = int(max_iterations)
                if max_iterations_int <= 0:
                    max_iterations_int = None
            except Exception:
                max_iterations_int = None
        options = {'maxiter': max_iterations_int} if max_iterations_int else None

        P = len(peers)
        if P == 0:
            return None
        peer_index = {p: i for i, p in enumerate(peers)}

        # Build category vectors v_c in R^P
        cat_vectors: List[np.ndarray] = []
        cat_seen = set()
        for cat in categories:
            key = (cat['dimension'], cat['category'])
            if key in cat_seen:
                continue
            cat_seen.add(key)
            # Assemble vector for this category
            v = np.zeros(P, dtype=float)
            for c in categories:
                if c['dimension'] == key[0] and c['category'] == key[1]:
                    # Safer lookup in case peer not in list (shouldn't happen)
                    if c['peer'] in peer_index:
                        idx = peer_index[c['peer']]
                        v[idx] = float(c['category_volume'])
            if v.sum() > 0:
                cat_vectors.append(v)

        if not cat_vectors:
            logger.warning("No category volumes found for LP solver.")
            return None

        cap = max_concentration / 100.0
        # Baseline shares (overall) for rank order
        peer_vol_arr = np.array([peer_volumes.get(p, 0.0) for p in peers], dtype=float)
        total_vol = float(peer_vol_arr.sum())
        base_shares = peer_vol_arr / total_vol if total_vol > 0 else np.ones(P, dtype=float) / max(P, 1)
        
        # Create ordered pairs (i,j) where base_shares[i] >= base_shares[j]
        pair_indices: List[Tuple[int, int]] = []
        order = np.argsort(-base_shares)  # descending
        rank_mode = str(solver_request.rank_constraint_mode).lower()
        rank_k = int(solver_request.rank_constraint_k)
        if rank_mode == 'neighbor':
            k = max(rank_k, 1)
            for a in range(P):
                i = int(order[a])
                for b in range(a + 1, min(P, a + 1 + k)):
                    j = int(order[b])
                    pair_indices.append((i, j))
        else:
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
        
        # Penalty for cap slacks: higher tolerance allows more slack
        if lambda_penalty is not None:
            base_lambda_cap = float(max(lambda_penalty, 0.0))
        else:
            base_lambda_cap = float(100.0 / max(tolerance, 1e-6))
        
        # Calculate volume-weighted slack penalties if enabled
        if volume_weighted_penalties:
            category_volumes = []
            for v in cat_vectors:
                cat_vol = float(v.sum())
                category_volumes.append(cat_vol)
            
            total_category_vol = sum(category_volumes)
            slack_penalties = []
            for cat_idx, cat_vol in enumerate(category_volumes):
                vol_weight = (cat_vol / total_category_vol) ** volume_weighting_exponent if total_category_vol > 0 else 1.0
                for p_idx in range(P):
                    slack_penalties.append(base_lambda_cap * vol_weight)
            slack_penalty_array = np.array(slack_penalties, dtype=float)
        else:
            slack_penalty_array = np.full(num_cap_constraints, base_lambda_cap, dtype=float)
        
        c = np.concatenate([
            np.zeros(P, dtype=float),           # m
            np.ones(P, dtype=float),            # t_plus
            np.ones(P, dtype=float),            # t_minus
            slack_penalty_array,                # s_cap
            np.full(K, rank_preservation_strength, dtype=float)  # s_rank
        ])

        A_ub_rows: List[np.ndarray] = []
        b_ub: List[float] = []

        # Share cap constraints
        cap_idx = 0
        for v in cat_vectors:
            for p_idx in range(P):
                coeff_m = (-cap) * v.copy()
                coeff_m[p_idx] += v[p_idx]  # (1-cap) * v_p
                row = np.zeros(n_vars, dtype=float)
                row[0:P] = coeff_m
                row[3 * P + cap_idx] = -1.0
                A_ub_rows.append(row)
                b_ub.append(0.0)
                cap_idx += 1

        # Deviation constraints
        for p_idx in range(P):
            row = np.zeros(n_vars, dtype=float)
            row[p_idx] = 1.0
            row[P + p_idx] = -1.0
            A_ub_rows.append(row)
            b_ub.append(1.0)
            
            row = np.zeros(n_vars, dtype=float)
            row[p_idx] = -1.0
            row[2 * P + p_idx] = -1.0
            A_ub_rows.append(row)
            b_ub.append(-1.0)

        # Rank preservation
        for k, (i, j) in enumerate(pair_indices):
            row = np.zeros(n_vars, dtype=float)
            row[i] = -peer_vol_arr[i]
            row[j] = peer_vol_arr[j]
            row[3 * P + num_cap_constraints + k] = 1.0
            A_ub_rows.append(row)
            b_ub.append(0.0)

        A_ub = np.vstack(A_ub_rows) if A_ub_rows else None
        b_ub_arr = np.array(b_ub, dtype=float) if b_ub else None

        # Bounds
        bounds: List[Tuple[float, Optional[float]]] = []
        for _ in range(P): bounds.append((min_weight, max_weight))
        for _ in range(2 * P): bounds.append((0.0, None))
        for _ in range(num_cap_constraints): bounds.append((0.0, None))
        for _ in range(K): bounds.append((0.0, None))

        res = None
        solved_method = None
        for method in ['highs', 'highs-ds', 'highs-ipm']:
            try:
                res = linprog(
                    c=c,
                    A_ub=A_ub,
                    b_ub=b_ub_arr,
                    bounds=bounds,
                    method=method,
                    options=options
                ) # type: ignore
                if res is not None and res.success:
                    solved_method = method
                    break
            except Exception as e:
                logger.warning(f"LP solver error with method {method}: {e}")

        if res is None or not res.success:
            return None

        m = res.x[0:P]
        s_cap_used = res.x[3 * P: 3 * P + num_cap_constraints] if num_cap_constraints > 0 else np.array([])
        
        # Stats
        total_category_volume = sum(v.sum() for v in cat_vectors)
        total_peer_volume = float(peer_vol_arr.sum())
        max_slack_abs = float(s_cap_used.max()) if s_cap_used.size > 0 else 0.0
        sum_slack_abs = float(s_cap_used.sum()) if s_cap_used.size > 0 else 0.0
        max_slack_pct = (max_slack_abs / total_category_volume * 100.0) if total_category_volume > 0 else 0.0
        sum_slack_pct = (sum_slack_abs / total_category_volume * 100.0) if total_category_volume > 0 else 0.0
        max_slack_pct_peer = (max_slack_abs / total_peer_volume * 100.0) if total_peer_volume > 0 else 0.0
        sum_slack_pct_peer = (sum_slack_abs / total_peer_volume * 100.0) if total_peer_volume > 0 else 0.0

        stats = {
            'method': solved_method or 'highs',
            'max_slack': max_slack_pct,
            'sum_slack': sum_slack_pct,
            'max_slack_abs': max_slack_abs,
            'sum_slack_abs': sum_slack_abs,
            'max_slack_pct_peer_total': max_slack_pct_peer,
            'sum_slack_pct_peer_total': sum_slack_pct_peer,
            'total_category_volume': total_category_volume,
            'total_peer_volume': total_peer_volume,
            'lambda_cap': base_lambda_cap,
            'volume_weighted': volume_weighted_penalties,
            'num_vars': n_vars,
            'num_constraints': len(b_ub)
        }

        # Final rescale
        avg = float(m.mean()) if P > 0 else 1.0
        if avg > 0:
            k_target = 1.0 / avg
            k_min = max(min_weight / mi for mi in m if mi > 0)
            k_max = min(max_weight / mi for mi in m if mi > 0)
            k = min(max(k_target, k_min), k_max)
            m = m * k
            m = np.clip(m, min_weight, max_weight)

        weights = {peer: float(m[peer_index[peer]]) for peer in peers}
        
        return SolverResult(
            weights=weights,
            method='lp',
            stats=stats,
            success=True
        )
