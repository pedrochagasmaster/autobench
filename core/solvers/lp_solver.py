import logging
import numpy as np
from typing import List, Optional, Tuple

from core.contracts import SolverRequest
from .base_solver import PrivacySolver, SolverResult

logger = logging.getLogger(__name__)

try:
    from scipy.optimize import linprog  # type: ignore
    from scipy.sparse import csr_matrix, eye, hstack, vstack  # type: ignore
    _SCIPY_AVAILABLE = True
except ImportError:
    linprog = None
    csr_matrix = eye = hstack = vstack = None
    _SCIPY_AVAILABLE = False

class LPSolver(PrivacySolver):
    """
    Solves for privacy weights using Linear Programming (SciPy Highs).
    Strictly enforces per-category share caps while minimizing deviation from 1.0.
    """
    
    def solve(self, request: SolverRequest) -> Optional[SolverResult]:
        """
        Solve global weights optimization problem.
        
        SolverRequest fields used:
        - rank_preservation_strength, tolerance, volume_weighted_penalties
        - volume_weighting_exponent, min_weight, max_weight
        - lambda_penalty, max_iterations
        """
        if not _SCIPY_AVAILABLE:
            raise RuntimeError(
                "SciPy is required for LP privacy-cap optimization. Install scipy>=1.8.0."
            )

        solver_request = request
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

        # Build category vectors v_c in R^P in one pass. The previous nested
        # scan was quadratic in the number of peer/category records.
        cat_vectors_by_key = {}
        for cat in categories:
            key = (cat['dimension'], cat['category'])
            if cat['peer'] not in peer_index:
                continue
            vector = cat_vectors_by_key.setdefault(key, np.zeros(P, dtype=float))
            vector[peer_index[cat['peer']]] += float(cat['category_volume'])
        cat_vectors: List[np.ndarray] = [
            vector for vector in cat_vectors_by_key.values() if vector.sum() > 0
        ]

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

        category_matrix = np.vstack(cat_vectors)
        # A zero-volume peer's cap row is always satisfied, so only create the
        # mathematically active peer/category inequalities.
        cap_category_indices, cap_peer_indices = np.nonzero(category_matrix > 0)
        num_cap_constraints = len(cap_category_indices)

        # Variables: [m (P), t_plus (P), t_minus (P), s_cap (num_cap_constraints), s_rank (K)]
        n_vars = 3 * P + num_cap_constraints + K
        
        # Penalty for cap slacks: higher tolerance allows more slack
        if lambda_penalty is not None:
            base_lambda_cap = float(max(lambda_penalty, 0.0))
        else:
            base_lambda_cap = float(100.0 / max(tolerance, 1e-6))
        
        # Calculate volume-weighted slack penalties if enabled
        if volume_weighted_penalties:
            category_volumes = category_matrix.sum(axis=1)
            total_category_vol = float(category_volumes.sum())
            if total_category_vol > 0:
                category_penalties = base_lambda_cap * (
                    category_volumes / total_category_vol
                ) ** volume_weighting_exponent
                slack_penalty_array = category_penalties[cap_category_indices]
            else:
                slack_penalty_array = np.full(num_cap_constraints, base_lambda_cap, dtype=float)
        else:
            slack_penalty_array = np.full(num_cap_constraints, base_lambda_cap, dtype=float)
        
        c = np.concatenate([
            np.zeros(P, dtype=float),           # m
            np.ones(P, dtype=float),            # t_plus
            np.ones(P, dtype=float),            # t_minus
            slack_penalty_array,                # s_cap
            np.full(K, rank_preservation_strength, dtype=float)  # s_rank
        ])

        # This LP encodes max-concentration caps. Tier participant requirements
        # are evaluated after solving because they are count-based, non-linear
        # constraints in the current solver architecture.
        # Share cap constraints
        cap_coefficients = -cap * category_matrix[cap_category_indices].copy()
        cap_coefficients[
            np.arange(num_cap_constraints), cap_peer_indices
        ] += category_matrix[cap_category_indices, cap_peer_indices]
        zero_cap_deviation = csr_matrix((num_cap_constraints, 2 * P))
        zero_cap_rank = csr_matrix((num_cap_constraints, K))
        cap_rows = hstack(
            [
                csr_matrix(cap_coefficients),
                zero_cap_deviation,
                -eye(num_cap_constraints, format='csr'),
                zero_cap_rank,
            ],
            format='csr',
        )
        cap_rhs = np.zeros(num_cap_constraints, dtype=float)

        # Deviation constraints
        deviation_rows_dense = np.zeros((2 * P, n_vars), dtype=float)
        deviation_rhs = np.empty(2 * P, dtype=float)
        for p_idx in range(P):
            positive_row = 2 * p_idx
            negative_row = positive_row + 1
            deviation_rows_dense[positive_row, p_idx] = 1.0
            deviation_rows_dense[positive_row, P + p_idx] = -1.0
            deviation_rhs[positive_row] = 1.0
            deviation_rows_dense[negative_row, p_idx] = -1.0
            deviation_rows_dense[negative_row, 2 * P + p_idx] = -1.0
            deviation_rhs[negative_row] = -1.0

        # Rank preservation
        rank_rows_dense = np.zeros((K, n_vars), dtype=float)
        for k, (i, j) in enumerate(pair_indices):
            rank_rows_dense[k, i] = -peer_vol_arr[i]
            rank_rows_dense[k, j] = peer_vol_arr[j]
            rank_rows_dense[k, 3 * P + num_cap_constraints + k] = 1.0

        A_ub = vstack(
            [cap_rows, csr_matrix(deviation_rows_dense), csr_matrix(rank_rows_dense)],
            format='csr',
        )
        b_ub_arr = np.concatenate(
            [cap_rhs, deviation_rhs, np.zeros(K, dtype=float)]
        )

        # Bounds
        bounds: List[Tuple[float, Optional[float]]] = []
        for _ in range(P):
            bounds.append((min_weight, max_weight))
        for _ in range(2 * P):
            bounds.append((0.0, None))
        for _ in range(num_cap_constraints):
            bounds.append((0.0, None))
        for _ in range(K):
            bounds.append((0.0, None))

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
            'converged': True,
            'residual_cap_violation': max_slack_abs > 0,
            'residual_additional_violation': False,
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
            'num_constraints': int(A_ub.shape[0])
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
