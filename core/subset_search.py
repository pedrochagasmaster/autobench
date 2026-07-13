"""Subset search for largest feasible global dimension set."""

from __future__ import annotations

import itertools
import logging
import random
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

import pandas as pd

from .solver_request_builder import build_lp_request

logger = logging.getLogger(__name__)


class _TrialResult(NamedTuple):
    """Trial outcome: empty categories are unrecorded by _solve_trial (callers
    record no-category notes); weights is None when there is no accepted
    solution (solver failure, missing weights, or slack rejection).
    """

    categories: List[Dict[str, Any]]
    weights: Optional[Dict[str, float]]
    sum_slack: Optional[float]


def _record_trial(
    analyzer: Any, attempt: int, trial_dims: List[str], *, success: bool,
    max_slack: Any = None, sum_slack: Any = None, method: Any = None, note: str = "",
) -> None:
    analyzer.subset_search_results.append(
        {
            "Attempt": attempt,
            "Dimensions": list(trial_dims),
            "Count": len(trial_dims),
            "Success": bool(success),
            "Max_Slack": (max_slack if success else (None if note else max_slack)),
            "Sum_Slack": (sum_slack if success else (None if note else sum_slack)),
            "Method": method,
            "Note": note,
        }
    )


def _update_best(
    best_score: Tuple[int, float], best_dims: List[str], best_weights: Optional[Dict[str, float]],
    trial_dims: List[str], weights: Dict[str, float], sum_slack: Optional[float],
) -> Tuple[Tuple[int, float], List[str], Optional[Dict[str, float]]]:
    score = (len(trial_dims), sum_slack if sum_slack is not None else 0.0)
    if score[0] > best_score[0] or (score[0] == best_score[0] and score[1] < best_score[1]):
        return score, list(trial_dims), weights
    return best_score, best_dims, best_weights


def _solve_trial(
    analyzer: Any, df: pd.DataFrame, metric_col: str, trial_dims: List[str],
    max_concentration: float, peers: List[str], attempt: int,
) -> _TrialResult:
    categories, peer_volumes, _ = analyzer._build_categories(df, metric_col, trial_dims)
    if not categories:
        return _TrialResult([], None, None)
    result = analyzer.lp_solver.solve(
        build_lp_request(
            analyzer,
            peers=peers,
            categories=categories,
            max_concentration=max_concentration,
            peer_volumes=peer_volumes,
        )
    )
    weights = None
    sum_slack = max_slack = method = None
    note = ""
    success = False
    if result and result.success:
        analyzer.last_lp_stats = result.stats
        stats = dict(result.stats)
        sum_slack = float(stats.get("sum_slack", 0.0) or 0.0)
        max_slack = float(stats.get("max_slack", 0.0) or 0.0)
        method = stats.get("method")
        candidate = result.weights
        success = candidate is not None
        if success and analyzer.trigger_subset_on_slack and analyzer._is_slack_excess(sum_slack):
            success = False
            note = f"Rejected due to slack {sum_slack:.6f} > {analyzer.max_cap_slack:.6f}"
        elif success:
            weights = candidate
    _record_trial(
        analyzer, attempt, trial_dims, success=success,
        max_slack=max_slack, sum_slack=sum_slack, method=method, note=note,
    )
    return _TrialResult(categories, weights, sum_slack if weights is not None else None)


def search_largest_feasible_subset(
    analyzer: Any,
    df: pd.DataFrame,
    metric_col: str,
    dimensions: List[str],
    max_concentration: float,
    peer_volumes: Dict[str, float],
    peers: List[str],
    all_categories: List[Dict[str, Any]],
) -> Tuple[List[str], Optional[Dict[str, float]]]:
    """Search for the largest feasible dimension subset under privacy caps."""
    analyzer.subset_search_results.clear()
    best_dims: List[str] = []
    best_weights: Optional[Dict[str, float]] = None
    best_score: Tuple[int, float] = (0, float("inf"))
    max_tests = max(int(analyzer.subset_search_max_tests), 1)

    if analyzer.greedy_subset_search:
        trial_dims = list(dimensions)
        tested = 0
        while tested < max_tests and trial_dims:
            tested += 1
            trial = _solve_trial(
                analyzer, df, metric_col, trial_dims, max_concentration, peers, tested
            )
            if not trial.categories:
                if len(trial_dims) <= 1:
                    break
                scores = analyzer._dimension_unbalance_scores(
                    all_categories if all_categories else trial.categories
                )
                drop_dim = max(trial_dims, key=lambda d: scores.get(d, 0.0))
                _record_trial(
                    analyzer, tested, trial_dims, success=False,
                    note=f"No cats; dropping {drop_dim}",
                )
                trial_dims = [d for d in trial_dims if d != drop_dim]
                continue
            if trial.weights is not None:
                best_score, best_dims, best_weights = _update_best(
                    best_score, best_dims, best_weights,
                    trial_dims, trial.weights, trial.sum_slack,
                )
                if not analyzer._is_slack_excess(trial.sum_slack):
                    break
            if len(trial_dims) <= 1:
                break
            scores = analyzer._dimension_unbalance_scores(trial.categories)
            drop_dim = max(trial_dims, key=lambda d: scores.get(d, 0.0))
            trial_dims = [d for d in trial_dims if d != drop_dim]
    else:
        # Seeded RNG: the "random" strategy is about exploration order, not
        # true randomness. Identical inputs must yield identical reports so
        # runs are reproducible for audit purposes.
        rng = random.Random(0)
        tested = 0
        for subset_size in range(len(dimensions) - 1, 0, -1):
            if tested >= max_tests:
                break
            combos = list(itertools.combinations(dimensions, subset_size))
            rng.shuffle(combos)
            for combo in combos:
                if tested >= max_tests:
                    break
                tested += 1
                trial_dims = list(combo)
                trial = _solve_trial(
                    analyzer, df, metric_col, trial_dims, max_concentration, peers, tested
                )
                if not trial.categories:
                    _record_trial(
                        analyzer, tested, trial_dims, success=False, note="No categories found"
                    )
                    continue
                if trial.weights is not None:
                    best_score, best_dims, best_weights = _update_best(
                        best_score, best_dims, best_weights,
                        trial_dims, trial.weights, trial.sum_slack,
                    )
                    if not analyzer._is_slack_excess(trial.sum_slack):
                        logger.info(
                            "Random search found feasible subset of size %s after %s attempts",
                            subset_size,
                            tested,
                        )
                        return best_dims, best_weights

    return best_dims, best_weights
