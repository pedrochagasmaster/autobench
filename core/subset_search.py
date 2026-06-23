"""Subset search for largest feasible global dimension set."""

from __future__ import annotations

import logging
import random
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .solver_request_builder import build_lp_request

logger = logging.getLogger(__name__)


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
        while tested < max_tests and len(trial_dims) > 0:
            tested += 1
            trial_cats, trial_peer_vols, _ = analyzer._build_categories(df, metric_col, trial_dims)
            if not trial_cats:
                if len(trial_dims) > 1:
                    scores = analyzer._dimension_unbalance_scores(
                        all_categories if all_categories else trial_cats
                    )
                    drop_dim = max(trial_dims, key=lambda d: scores.get(d, 0.0))
                    analyzer.subset_search_results.append(
                        {
                            "Attempt": tested,
                            "Dimensions": list(trial_dims),
                            "Count": len(trial_dims),
                            "Success": False,
                            "Max_Slack": None,
                            "Sum_Slack": None,
                            "Method": None,
                            "Note": f"No cats; dropping {drop_dim}",
                        }
                    )
                    trial_dims = [d for d in trial_dims if d != drop_dim]
                    continue
                break

            lp_result = analyzer.lp_solver.solve(
                build_lp_request(
                    analyzer,
                    peers=peers,
                    categories=trial_cats,
                    max_concentration=max_concentration,
                    peer_volumes=trial_peer_vols,
                )
            )
            if lp_result and lp_result.success:
                analyzer.last_lp_stats = lp_result.stats
                sol = lp_result.weights
                stats = dict(lp_result.stats)
            else:
                sol = None
                stats = {}
            sum_slack = float(stats.get("sum_slack", 0.0) or 0.0) if stats else None
            max_slack = float(stats.get("max_slack", 0.0) or 0.0) if stats else None
            method = stats.get("method") if stats else None
            success = sol is not None
            note = ""
            if success and analyzer.trigger_subset_on_slack and analyzer._is_slack_excess(sum_slack):
                success = False
                note = f"Rejected due to slack {sum_slack:.6f} > {analyzer.max_cap_slack:.6f}"
            analyzer.subset_search_results.append(
                {
                    "Attempt": tested,
                    "Dimensions": list(trial_dims),
                    "Count": len(trial_dims),
                    "Success": bool(success),
                    "Max_Slack": (max_slack if success else (None if note else max_slack)),
                    "Sum_Slack": (sum_slack if success else (None if note else sum_slack)),
                    "Method": method,
                    "Note": note,
                }
            )
            if success and sol is not None:
                score = (len(trial_dims), sum_slack if sum_slack is not None else 0.0)
                if score[0] > best_score[0] or (score[0] == best_score[0] and score[1] < best_score[1]):
                    best_score = score
                    best_dims = list(trial_dims)
                    best_weights = sol
                if len(trial_dims) == len(dimensions) and not analyzer._is_slack_excess(sum_slack):
                    break
                if not analyzer._is_slack_excess(sum_slack):
                    break
            if len(trial_dims) <= 1:
                break
            scores = analyzer._dimension_unbalance_scores(trial_cats)
            drop_dim = max(trial_dims, key=lambda d: scores.get(d, 0.0))
            trial_dims = [d for d in trial_dims if d != drop_dim]
    else:
        import itertools

        # Seeded RNG: the "random" strategy is about exploration order, not
        # true randomness. Identical inputs must yield identical reports so
        # runs are reproducible for audit purposes.
        rng = random.Random(0)
        tested = 0
        n = len(dimensions)
        for subset_size in range(n - 1, 0, -1):
            if tested >= max_tests:
                break
            all_combinations = list(itertools.combinations(dimensions, subset_size))
            rng.shuffle(all_combinations)
            for combo in all_combinations:
                if tested >= max_tests:
                    break
                tested += 1
                trial_dims = list(combo)
                trial_cats, trial_peer_vols, _ = analyzer._build_categories(df, metric_col, trial_dims)
                if not trial_cats:
                    analyzer.subset_search_results.append(
                        {
                            "Attempt": tested,
                            "Dimensions": list(trial_dims),
                            "Count": len(trial_dims),
                            "Success": False,
                            "Max_Slack": None,
                            "Sum_Slack": None,
                            "Method": None,
                            "Note": "No categories found",
                        }
                    )
                    continue

                lp_result = analyzer.lp_solver.solve(
                    build_lp_request(
                        analyzer,
                        peers=peers,
                        categories=trial_cats,
                        max_concentration=max_concentration,
                        peer_volumes=trial_peer_vols,
                    )
                )
                if lp_result and lp_result.success:
                    analyzer.last_lp_stats = lp_result.stats
                    sol = lp_result.weights
                    stats = dict(lp_result.stats)
                else:
                    sol = None
                    stats = {}
                sum_slack = float(stats.get("sum_slack", 0.0) or 0.0) if stats else None
                max_slack = float(stats.get("max_slack", 0.0) or 0.0) if stats else None
                method = stats.get("method") if stats else None
                success = sol is not None
                note = ""
                if success and analyzer.trigger_subset_on_slack and analyzer._is_slack_excess(sum_slack):
                    success = False
                    note = f"Rejected due to slack {sum_slack:.6f} > {analyzer.max_cap_slack:.6f}"
                analyzer.subset_search_results.append(
                    {
                        "Attempt": tested,
                        "Dimensions": list(trial_dims),
                        "Count": len(trial_dims),
                        "Success": bool(success),
                        "Max_Slack": (max_slack if success else (None if note else max_slack)),
                        "Sum_Slack": (sum_slack if success else (None if note else sum_slack)),
                        "Method": method,
                        "Note": note,
                    }
                )
                if success and sol is not None:
                    score = (len(trial_dims), sum_slack if sum_slack is not None else 0.0)
                    if score[0] > best_score[0] or (score[0] == best_score[0] and score[1] < best_score[1]):
                        best_score = score
                        best_dims = list(trial_dims)
                        best_weights = sol
                    if not analyzer._is_slack_excess(sum_slack):
                        logger.info(
                            "Random search found feasible subset of size %s after %s attempts",
                            subset_size,
                            tested,
                        )
                        return best_dims, best_weights

    return best_dims, best_weights
