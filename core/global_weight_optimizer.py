"""Global privacy weight optimization orchestration."""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from .category_builder import CategoryBuilder
from .contracts import SolverRequest

logger = logging.getLogger(__name__)


def _weights_are_identity(weights: Dict[str, float], tol: float = 1e-9) -> bool:
    """Return True when all multipliers are effectively 1.0 within tolerance."""
    if not weights:
        return False
    return all(abs(float(multiplier) - 1.0) <= tol for multiplier in weights.values())


class GlobalWeightOptimizer:
    """Executes the global LP/subset/heuristic optimization workflow."""

    def __init__(self, analyzer: Any) -> None:
        self.analyzer = analyzer

    def _build_lp_request(
        self,
        *,
        peers: List[str],
        categories: List[Dict[str, Any]],
        max_concentration: float,
        peer_volumes: Dict[str, float],
        tolerance: Optional[float] = None,
    ) -> SolverRequest:
        analyzer = self.analyzer
        return SolverRequest(
            peers=peers,
            categories=categories,
            max_concentration=max_concentration,
            peer_volumes=peer_volumes,
            rank_preservation_strength=analyzer.rank_preservation_strength,
            rank_constraint_mode=analyzer.rank_constraint_mode,
            rank_constraint_k=analyzer.rank_constraint_k,
            tolerance=float(analyzer.tolerance if tolerance is None else tolerance),
            volume_weighted_penalties=analyzer.volume_weighted_penalties,
            volume_weighting_exponent=analyzer.volume_weighting_exponent,
            lambda_penalty=analyzer.lambda_penalty,
            max_iterations=analyzer.max_iterations,
            min_weight=analyzer.min_weight,
            max_weight=analyzer.max_weight,
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
        analyzer = self.analyzer
        return SolverRequest(
            peers=peers,
            categories=categories,
            max_concentration=max_concentration,
            peer_volumes=peer_volumes,
            target_weights=target_weights,
            rule_name=rule_name,
            min_weight=analyzer.min_weight,
            max_weight=analyzer.max_weight,
            tolerance=float(analyzer.tolerance if tolerance is None else tolerance),
            max_iterations=analyzer.bayesian_max_iterations,
            learning_rate=analyzer.bayesian_learning_rate,
            violation_penalty_weight=analyzer.violation_penalty_weight,
            merchant_mode=analyzer.merchant_mode,
            enforce_additional_constraints=analyzer.enforce_additional_constraints,
            dynamic_constraints_enabled=analyzer.dynamic_constraints_enabled,
            time_column=analyzer.time_column,
            min_peer_count_for_constraints=analyzer.min_peer_count_for_constraints,
            min_effective_peer_count=analyzer.min_effective_peer_count,
            min_category_volume_share=analyzer.min_category_volume_share,
            min_overall_volume_share=analyzer.min_overall_volume_share,
            min_representativeness=analyzer.min_representativeness,
            dynamic_threshold_scale_floor=analyzer.dynamic_threshold_scale_floor,
            dynamic_count_scale_floor=analyzer.dynamic_count_scale_floor,
            representativeness_penalty_floor=analyzer.representativeness_penalty_floor,
            representativeness_penalty_power=analyzer.representativeness_penalty_power,
        )

    def calculate_global_privacy_weights(
        self,
        df: pd.DataFrame,
        metric_col: str,
        dimensions: List[str],
    ) -> None:
        analyzer = self.analyzer
        if not analyzer.consistent_weights:
            return
        single_weight_mode = bool(getattr(analyzer, "enforce_single_weight_set", False))

        if analyzer.time_column and analyzer.time_column in df.columns:
            all_categories, peer_volumes, peers = analyzer._build_time_aware_categories(df, metric_col, dimensions)
        else:
            all_categories, peer_volumes, peers = analyzer._build_categories(df, metric_col, dimensions)
        peer_count = len(peers)
        rule_name, max_concentration = analyzer._get_privacy_rule(peer_count)
        analyzer.privacy_rule_name = rule_name
        analyzer._reset_dynamic_constraint_stats()

        if rule_name == 'insufficient':
            logger.error(
                "Insufficient peers for privacy rule selection (peers=%s). "
                "Skipping global optimization and using identity weights.",
                peer_count,
            )
            weights = {peer: 1.0 for peer in peers}
            analyzer.global_dimensions_used = list(dimensions)
            analyzer.removed_dimensions = []
            for dim in analyzer.global_dimensions_used:
                analyzer.weight_methods[dim] = "Global-Identity"
            analyzer._store_final_weights(peers, peer_volumes, weights)
            return

        try:
            det_df, sum_df = analyzer._compute_structural_caps_diagnostics(peers, all_categories, max_concentration)
            analyzer.structural_detail_df = det_df
            analyzer.structural_summary_df = sum_df
            structural = analyzer.get_structural_infeasibility_summary()
            if structural.get('has_structural_infeasibility'):
                logger.warning(
                    "Structural infeasibility detected: dimensions=%s categories=%s peers=%s worst_margin=%0.4fpp",
                    structural.get('infeasible_dimensions'),
                    structural.get('infeasible_categories'),
                    structural.get('infeasible_peers'),
                    structural.get('worst_margin_pp'),
                )
                logger.warning(
                    "Top structural issue: dimension=%s category=%s",
                    structural.get('top_infeasible_dimension'),
                    structural.get('top_infeasible_category'),
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Structural diagnostics failed: %s", exc)

        logger.info("Calculating global privacy-constrained weights for %s peers", peer_count)
        logger.info("Privacy rule: %s", rule_name)
        logger.info("Max concentration: %s%%", max_concentration)
        logger.info("Checking all categories across dimensions: %s", dimensions)
        logger.info("Found %s dimension/category combinations", len(all_categories))

        weights: Dict[str, float] = {peer: 1.0 for peer in peers}

        def run_lp(categories: List[Dict[str, Any]], volumes: Dict[str, float]) -> Optional[Dict[str, float]]:
            lp_result = analyzer.lp_solver.solve(
                self._build_lp_request(
                    peers=peers,
                    categories=categories,
                    max_concentration=max_concentration,
                    peer_volumes=volumes,
                )
            )
            if lp_result and lp_result.success:
                analyzer.last_lp_stats = lp_result.stats
                return lp_result.weights
            return None

        lp_solution = run_lp(all_categories, peer_volumes)
        converged = False
        used_dimensions = list(dimensions)
        removed_dimensions: List[str] = []

        if lp_solution is None and analyzer.prefer_slacks_first:
            logger.info("Attempting slacks-first LP on full dimension set before dropping any dimensions")
            orig_rank = analyzer.rank_preservation_strength
            analyzer.rank_preservation_strength = 0.0
            lp_solution = run_lp(all_categories, peer_volumes)
            analyzer.rank_preservation_strength = orig_rank

        if lp_solution is not None and analyzer.trigger_subset_on_slack and not single_weight_mode:
            sum_slack = float(analyzer.last_lp_stats.get('sum_slack', 0.0) or 0.0)
            if analyzer._is_slack_excess(sum_slack):
                logger.info(
                    "LP returned success but used cap slack sum=%0.6f > threshold=%0.6f; triggering subset search",
                    sum_slack,
                    analyzer.max_cap_slack,
                )
                best_dims, best_weights = analyzer._search_largest_feasible_subset(
                    df, metric_col, dimensions, max_concentration, peer_volumes, peers, all_categories
                )
                if best_weights is not None:
                    analyzer.slack_subset_triggered = True
                    weights = best_weights
                    converged = True
                    used_dimensions = best_dims
                    removed_dimensions = [d for d in dimensions if d not in best_dims]
                    logger.info("Slack-aware policy selected global dimensions: %s", used_dimensions)

                    analyzer.per_dimension_weights.clear()
                    analyzer._solve_per_dimension_weights(
                        df,
                        metric_col,
                        removed_dimensions,
                        peers,
                        max_concentration,
                        weights,
                        rule_name,
                    )
                else:
                    logger.info("Subset search failed to improve; keeping full-set LP solution despite slack usage")
        elif lp_solution is not None and analyzer.trigger_subset_on_slack and single_weight_mode:
            logger.info("Single weight-set mode active; skipping slack-triggered subset search")

        if lp_solution is None:
            if single_weight_mode:
                logger.info("Single weight-set mode active; skipping subset-search and dimension-dropping fallbacks")
            elif analyzer.auto_subset_search:
                logger.info("Searching for largest feasible global dimension subset (auto_subset_search enabled)")
                best_dims, best_weights = analyzer._search_largest_feasible_subset(
                    df, metric_col, dimensions, max_concentration, peer_volumes, peers, all_categories
                )
                if best_weights is not None:
                    weights = best_weights
                    converged = True
                    used_dimensions = best_dims
                    removed_dimensions = [d for d in dimensions if d not in best_dims]
                    logger.info("Auto search selected global dimensions: %s", used_dimensions)

                    analyzer.per_dimension_weights.clear()
                    analyzer._solve_per_dimension_weights(
                        df,
                        metric_col,
                        removed_dimensions,
                        peers,
                        max_concentration,
                        weights,
                        rule_name,
                    )
            else:
                scores = analyzer._dimension_unbalance_scores(all_categories)
                ordered_dims = sorted(scores.keys(), key=lambda dim_name: scores[dim_name], reverse=True)
                logger.warning(
                    "LP infeasible; attempting fallback by dropping most unbalanced dimensions in order: %s",
                    ordered_dims,
                )
                for count in range(1, len(ordered_dims) + 1):
                    trial_dims = [dim_name for dim_name in dimensions if dim_name not in ordered_dims[:count]]
                    if not trial_dims:
                        continue
                    trial_cats, trial_peer_vols, _ = analyzer._build_categories(df, metric_col, trial_dims)
                    if not trial_cats:
                        continue
                    solution = run_lp(trial_cats, trial_peer_vols)
                    if solution is not None:
                        weights = solution
                        converged = True
                        used_dimensions = trial_dims
                        removed_dimensions = ordered_dims[:count]
                        logger.info("LP succeeded after dropping dimensions: %s", removed_dimensions)
                        analyzer.per_dimension_weights.clear()
                        analyzer._solve_per_dimension_weights(
                            df,
                            metric_col,
                            removed_dimensions,
                            peers,
                            max_concentration,
                            weights,
                            rule_name,
                        )
                        break
        else:
            if not converged:
                weights = lp_solution
                converged = True
                for dim_name in used_dimensions:
                    analyzer.weight_methods[dim_name] = "Global-LP"

        analyzer.global_dimensions_used = used_dimensions
        analyzer.removed_dimensions = removed_dimensions

        if not converged:
            logger.warning("Global LP failed or no feasible subset found; attempting heuristic global optimization.")
            heuristic_result = analyzer.heuristic_solver.solve(
                self._build_heuristic_request(
                    peers=peers,
                    categories=all_categories,
                    max_concentration=max_concentration,
                    peer_volumes=peer_volumes,
                    target_weights=weights,
                    rule_name=rule_name,
                )
            )
            if heuristic_result:
                if not heuristic_result.success:
                    logger.warning("Heuristic global solver did not converge; using best-effort weights.")
                weights = heuristic_result.weights
                converged = True
                used_dimensions = list(dimensions)
                removed_dimensions = []
                for dim_name in used_dimensions:
                    analyzer.weight_methods[dim_name] = "Global-Bayesian"
                analyzer.global_dimensions_used = used_dimensions
                analyzer.removed_dimensions = removed_dimensions
            else:
                logger.warning("Heuristic global optimization failed; proceeding without global weights.")

        if converged:
            analyzer.additional_constraint_violations = []
            if analyzer.enforce_additional_constraints and rule_name in ('6/30', '7/35', '10/40'):
                violations = analyzer._find_additional_constraint_violations(
                    all_categories,
                    peers,
                    weights,
                    rule_name,
                    peer_volumes,
                )
                analyzer.additional_constraint_violations = violations
                if violations:
                    logger.warning(
                        "Additional constraints violated in %s categories; running heuristic optimization to correct.",
                        len(violations),
                    )
                    strict_feasibility_mode = float(analyzer.tolerance) <= float(analyzer.COMPARISON_EPSILON)
                    target_multipliers = None if strict_feasibility_mode else ({peer: weights[peer] for peer in peers} if weights else None)
                    if strict_feasibility_mode:
                        logger.info(
                            "Strict tolerance mode detected (tolerance=0). "
                            "Running feasibility-first heuristic without global-weight anchoring."
                        )
                    heuristic_result = analyzer.heuristic_solver.solve(
                        self._build_heuristic_request(
                            peers=peers,
                            categories=all_categories,
                            max_concentration=max_concentration,
                            peer_volumes=peer_volumes,
                            target_weights=target_multipliers,
                            rule_name=rule_name,
                        )
                    )
                    if heuristic_result:
                        if not heuristic_result.success:
                            logger.warning("Heuristic solver did not converge; using best-effort weights.")
                        weights = heuristic_result.weights
                        analyzer.additional_constraint_violations = analyzer._find_additional_constraint_violations(
                            all_categories,
                            peers,
                            weights,
                            rule_name,
                            peer_volumes,
                        )
                        if analyzer.additional_constraint_violations:
                            logger.warning(
                                "Additional constraints still violated in %s categories after heuristic optimization.",
                                len(analyzer.additional_constraint_violations),
                            )
                    else:
                        logger.warning("Heuristic optimization failed; keeping LP weights with violations.")

            weights = analyzer._nudge_borderline_cap_excess(weights, all_categories, max_concentration, used_dimensions)
            analyzer._store_final_weights(peers, peer_volumes, weights)

            if analyzer.time_column and analyzer.consistent_weights:
                original_dims = set(used_dimensions)
                time_aware_to_original: Dict[str, str] = {}
                for cat in all_categories:
                    dim_name = cat['dimension']
                    if dim_name.startswith(f"{CategoryBuilder.TIME_TOTAL_DIMENSION_PREFIX}{analyzer.time_column}"):
                        time_aware_to_original[dim_name] = '_TIME_TOTAL'
                    elif dim_name.endswith(f'_{analyzer.time_column}'):
                        original_dim = dim_name.replace(f'_{analyzer.time_column}', '')
                        if original_dim in original_dims:
                            time_aware_to_original[dim_name] = original_dim

                val_dims_set = set(
                    (
                        time_aware_to_original.get(cat['dimension'], cat['dimension']),
                        cat['category'],
                        cat.get('time_period'),
                    )
                    for cat in all_categories
                    if time_aware_to_original.get(cat['dimension'], cat['dimension']) in original_dims
                    or cat['dimension'].startswith(CategoryBuilder.TIME_TOTAL_DIMENSION_PREFIX)
                )
            else:
                val_dims_set = set(
                    (cat['dimension'], cat['category'], None)
                    for cat in all_categories
                    if cat['dimension'] in used_dimensions
                )

            logger.info("\nGlobal weights validation across all %s categories:", len(val_dims_set))
            logger.info("\nFinal global weight multipliers:")

            dimensions_with_violations: List[str] = []

            for peer in sorted(peers, key=lambda peer_name: weights[peer_name], reverse=True):
                peer_max_share = 0.0
                peer_violation_dims: List[str] = []
                for cat in all_categories:
                    if cat['peer'] != peer:
                        continue

                    if analyzer.time_column and analyzer.consistent_weights:
                        dim_name = cat['dimension']
                        if dim_name.startswith(f"{CategoryBuilder.TIME_TOTAL_DIMENSION_PREFIX}{analyzer.time_column}"):
                            include_in_validation = True
                            original_dim = '_TIME_TOTAL'
                        elif dim_name.endswith(f'_{analyzer.time_column}'):
                            original_dim = dim_name.replace(f'_{analyzer.time_column}', '')
                            include_in_validation = original_dim in used_dimensions
                        else:
                            include_in_validation = cat['dimension'] in used_dimensions
                            original_dim = cat['dimension']
                    else:
                        include_in_validation = cat['dimension'] in used_dimensions
                        original_dim = cat['dimension']

                    if not include_in_validation:
                        continue

                    category_vol_weighted = cat['category_volume'] * weights[peer]
                    if 'time_period' in cat:
                        matching_cats = [
                            candidate for candidate in all_categories
                            if candidate['dimension'] == cat['dimension']
                            and candidate['category'] == cat['category']
                            and candidate.get('time_period') == cat.get('time_period')
                        ]
                    else:
                        matching_cats = [
                            candidate for candidate in all_categories
                            if candidate['dimension'] == cat['dimension']
                            and candidate['category'] == cat['category']
                        ]

                    total_weighted = sum(candidate['category_volume'] * weights[candidate['peer']] for candidate in matching_cats)
                    adjusted_share = (category_vol_weighted / total_weighted * 100) if total_weighted > 0 else 0.0
                    peer_max_share = max(peer_max_share, adjusted_share)

                    if analyzer._is_share_violation(adjusted_share, max_concentration):
                        if original_dim not in peer_violation_dims:
                            peer_violation_dims.append(original_dim)

                status = "OK" if len(peer_violation_dims) == 0 else "VIOLATION"
                logger.info(
                    "  %s: multiplier=%.4f, max_adjusted_share=%.4f%% [%s]",
                    peer,
                    weights[peer],
                    peer_max_share,
                    status,
                )

                for violation_dim in peer_violation_dims:
                    if violation_dim not in dimensions_with_violations:
                        dimensions_with_violations.append(violation_dim)

            real_dimensions_with_violations = [
                violation_dim
                for violation_dim in dimensions_with_violations
                if not CategoryBuilder.is_internal_dimension_name(violation_dim)
            ]

            has_additional_violations = bool(getattr(analyzer, 'additional_constraint_violations', []))
            if (
                _weights_are_identity(weights)
                and not real_dimensions_with_violations
                and not has_additional_violations
            ):
                logger.info(
                    "Global optimization retained identity multipliers because all privacy constraints "
                    "were already satisfied for the selected dimensions."
                )

            if single_weight_mode and real_dimensions_with_violations:
                logger.info(
                    "Single weight-set mode active; keeping global weights despite violating dimensions: %s",
                    real_dimensions_with_violations,
                )
            elif real_dimensions_with_violations:
                logger.info("\nDimensions with violations detected: %s", real_dimensions_with_violations)
                logger.info("Computing per-dimension weights for these dimensions...")
                for violation_dim in real_dimensions_with_violations:
                    if violation_dim not in dimensions:
                        logger.info(
                            "Skipping non-user dimension during per-dimension re-weighting: %s",
                            violation_dim,
                        )
                        continue
                    violation_cats, violation_peer_vols, _ = analyzer._build_categories(df, metric_col, [violation_dim])
                    if not violation_cats:
                        continue

                    has_time = any('time_period' in cat for cat in violation_cats)
                    time_info = (
                        f" (time-aware: {len([cat for cat in violation_cats if cat.get('time_period')])} constraints)"
                        if has_time
                        else ""
                    )
                    logger.info("Solving per-dimension weights for '%s'%s", violation_dim, time_info)

                    orig_tolerance = analyzer.tolerance
                    analyzer.tolerance = 0.0
                    lp_result = analyzer.lp_solver.solve(
                        self._build_lp_request(
                            peers=peers,
                            categories=violation_cats,
                            max_concentration=max_concentration,
                            peer_volumes=violation_peer_vols,
                            tolerance=analyzer.tolerance,
                        )
                    )
                    violation_solution = lp_result.weights if lp_result and lp_result.success else None
                    if lp_result and lp_result.success:
                        analyzer.last_lp_stats = lp_result.stats
                    analyzer.tolerance = orig_tolerance

                    if violation_solution is not None:
                        has_violations = False
                        for cat in violation_cats:
                            if 'time_period' in cat:
                                matching_cats = [
                                    entry for entry in violation_cats
                                    if entry['dimension'] == cat['dimension']
                                    and entry['category'] == cat['category']
                                    and entry.get('time_period') == cat.get('time_period')
                                ]
                            else:
                                matching_cats = [
                                    entry for entry in violation_cats
                                    if entry['dimension'] == cat['dimension']
                                    and entry['category'] == cat['category']
                                ]

                            cat_vol_weighted = cat['category_volume'] * violation_solution[cat['peer']]
                            total_weighted = sum(
                                entry['category_volume'] * violation_solution[entry['peer']]
                                for entry in matching_cats
                            )
                            adjusted_share = (cat_vol_weighted / total_weighted * 100) if total_weighted > 0 else 0.0

                            if analyzer._is_share_violation(adjusted_share, max_concentration):
                                has_violations = True
                                break

                        if not has_violations:
                            analyzer.per_dimension_weights[violation_dim] = violation_solution
                            analyzer.weight_methods[violation_dim] = "Per-Dimension-LP"
                            logger.info("  Per-dimension LP succeeded for '%s' with no violations", violation_dim)
                        else:
                            logger.info(
                                "  Per-dimension LP produced violations for '%s', trying Bayesian optimization",
                                violation_dim,
                            )
                            violation_solution = None

                    if violation_solution is None:
                        strict_feasibility_mode = float(analyzer.tolerance) <= float(analyzer.COMPARISON_EPSILON)
                        target_multipliers = None if strict_feasibility_mode else {peer: weights[peer] for peer in peers}
                        if strict_feasibility_mode:
                            logger.info(
                                "  Strict tolerance mode detected for '%s'; "
                                "using feasibility-first per-dimension heuristic.",
                                violation_dim,
                            )
                        heuristic_result = analyzer.heuristic_solver.solve(
                            self._build_heuristic_request(
                                peers=peers,
                                categories=violation_cats,
                                max_concentration=max_concentration,
                                peer_volumes=violation_peer_vols,
                                target_weights=target_multipliers,
                                rule_name=rule_name,
                                tolerance=analyzer.tolerance,
                            )
                        )
                        if heuristic_result:
                            if not heuristic_result.success:
                                logger.warning("Per-dimension heuristic solver did not converge; using best-effort weights.")
                            analyzer.per_dimension_weights[violation_dim] = heuristic_result.weights
                            analyzer.weight_methods[violation_dim] = "Per-Dimension-Bayesian"
                            if target_multipliers is None:
                                logger.info(
                                    "  Per-dimension Bayesian optimization applied for '%s' (feasibility-first mode)",
                                    violation_dim,
                                )
                            else:
                                logger.info(
                                    "  Per-dimension Bayesian optimization applied for '%s' (targeting global weights)",
                                    violation_dim,
                                )
                        else:
                            logger.warning("  Per-dimension solving failed for '%s'", violation_dim)
