"""Global privacy weight optimization orchestration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .category_builder import CategoryBuilder
from .contracts import WeightingComplianceState, WeightingResult, weighting_result_from_analyzer
from .solver_request_builder import build_heuristic_request, build_lp_request
from .subset_search import search_largest_feasible_subset

logger = logging.getLogger(__name__)


def _weights_are_identity(weights: Dict[str, float], tol: float = 1e-9) -> bool:
    """Return True when all multipliers are effectively 1.0 within tolerance."""
    if not weights:
        return False
    return all(abs(float(multiplier) - 1.0) <= tol for multiplier in weights.values())


@dataclass
class WeightingProblem:
    """Inputs assembled before LP/subset/heuristic solving."""

    df: pd.DataFrame
    metric_col: str
    dimensions: List[str]
    all_categories: List[Dict[str, Any]]
    peer_volumes: Dict[str, float]
    peers: List[str]
    rule_name: str
    max_concentration: float
    single_weight_mode: bool


@dataclass
class WeightingSolveState:
    """Mutable optimization state carried through solver phases."""

    weights: Dict[str, float] = field(default_factory=dict)
    converged: bool = False
    used_dimensions: List[str] = field(default_factory=list)
    removed_dimensions: List[str] = field(default_factory=list)
    heuristic_converged: Optional[bool] = None
    residual_cap_violation: bool = False
    residual_additional_violation: bool = False


class GlobalWeightOptimizer:
    """Executes the global LP/subset/heuristic optimization workflow."""

    def __init__(self, analyzer: Any) -> None:
        self.analyzer = analyzer

    def calculate_global_privacy_weights(
        self,
        df: pd.DataFrame,
        metric_col: str,
        dimensions: List[str],
    ) -> Optional[WeightingResult]:
        analyzer = self.analyzer
        if not analyzer.consistent_weights:
            return None

        problem = self.build_weighting_problem(df, metric_col, dimensions)
        state = WeightingSolveState(
            weights={peer: 1.0 for peer in problem.peers},
            used_dimensions=list(dimensions),
        )

        lp_solution = self.solve_full_problem(problem)
        self.decide_subset_fallback(problem, state, lp_solution)
        self.run_heuristic_fallback(problem, state)

        if state.converged:
            self.finalize_converged_weights(problem, state)
            self.post_validate_and_correct(problem, state)

        return self.assemble_weighting_result(problem, state)

    def build_weighting_problem(
        self,
        df: pd.DataFrame,
        metric_col: str,
        dimensions: List[str],
    ) -> WeightingProblem:
        analyzer = self.analyzer
        single_weight_mode = bool(getattr(analyzer, "enforce_single_weight_set", False))

        if analyzer.time_column and analyzer.time_column in df.columns:
            all_categories, peer_volumes, peers = analyzer._build_time_aware_categories(
                df, metric_col, dimensions
            )
        else:
            all_categories, peer_volumes, peers = analyzer._build_categories(df, metric_col, dimensions)

        peer_count = len(peers)
        rule_name, max_concentration = analyzer._get_privacy_rule(peer_count)
        analyzer.privacy_rule_name = rule_name
        analyzer._reset_dynamic_constraint_stats()

        if rule_name == "insufficient":
            analyzer.compliance_blocked_reason = "insufficient_peers"
            analyzer.compliance_blocked_peer_count = peer_count
            analyzer.global_dimensions_used = []
            analyzer.removed_dimensions = list(dimensions)
            for dim in dimensions:
                analyzer.weight_methods.pop(dim, None)
            logger.error(
                "Insufficient peers for privacy rule selection (peers=%s). "
                "Aborting analysis to avoid emitting non-compliant identity weights.",
                peer_count,
            )
            raise ValueError(
                f"Insufficient peers for privacy rule selection: peers={peer_count}. "
                f"Minimum 5 peers required for standard mode (4 for merchant mode)."
            )

        try:
            det_df, sum_df = analyzer._compute_structural_caps_diagnostics(
                peers, all_categories, max_concentration
            )
            analyzer.structural_detail_df = det_df
            analyzer.structural_summary_df = sum_df
            structural = analyzer.get_structural_infeasibility_summary()
            if structural.get("has_structural_infeasibility"):
                logger.warning(
                    "Structural infeasibility detected: dimensions=%s categories=%s peers=%s worst_margin=%0.4fpp",
                    structural.get("infeasible_dimensions"),
                    structural.get("infeasible_categories"),
                    structural.get("infeasible_peers"),
                    structural.get("worst_margin_pp"),
                )
                logger.warning(
                    "Top structural issue: dimension=%s category=%s",
                    structural.get("top_infeasible_dimension"),
                    structural.get("top_infeasible_category"),
                )
        except Exception as exc:  # pragma: no cover
            logger.warning("Structural diagnostics failed: %s", exc)

        logger.info("Calculating global privacy-constrained weights for %s peers", peer_count)
        logger.info("Privacy rule: %s", rule_name)
        logger.info("Max concentration: %s%%", max_concentration)
        logger.info("Checking all categories across dimensions: %s", dimensions)
        logger.info("Found %s dimension/category combinations", len(all_categories))

        return WeightingProblem(
            df=df,
            metric_col=metric_col,
            dimensions=list(dimensions),
            all_categories=all_categories,
            peer_volumes=peer_volumes,
            peers=peers,
            rule_name=rule_name,
            max_concentration=max_concentration,
            single_weight_mode=single_weight_mode,
        )

    def _run_lp(
        self,
        problem: WeightingProblem,
        categories: List[Dict[str, Any]],
        volumes: Dict[str, float],
    ) -> Optional[Dict[str, float]]:
        analyzer = self.analyzer
        lp_result = analyzer.lp_solver.solve(
            build_lp_request(
                analyzer,
                peers=problem.peers,
                categories=categories,
                max_concentration=problem.max_concentration,
                peer_volumes=volumes,
            )
        )
        if lp_result and lp_result.success:
            analyzer.last_lp_stats = lp_result.stats
            return lp_result.weights
        return None

    def solve_full_problem(self, problem: WeightingProblem) -> Optional[Dict[str, float]]:
        analyzer = self.analyzer
        lp_solution = self._run_lp(problem, problem.all_categories, problem.peer_volumes)

        if lp_solution is None and analyzer.prefer_slacks_first:
            logger.info("Attempting slacks-first LP on full dimension set before dropping any dimensions")
            orig_rank = analyzer.rank_preservation_strength
            analyzer.rank_preservation_strength = 0.0
            lp_solution = self._run_lp(problem, problem.all_categories, problem.peer_volumes)
            analyzer.rank_preservation_strength = orig_rank

        return lp_solution

    def decide_subset_fallback(
        self,
        problem: WeightingProblem,
        state: WeightingSolveState,
        lp_solution: Optional[Dict[str, float]],
    ) -> None:
        analyzer = self.analyzer

        if lp_solution is not None and analyzer.trigger_subset_on_slack and not problem.single_weight_mode:
            sum_slack = float(analyzer.last_lp_stats.get("sum_slack", 0.0) or 0.0)
            if analyzer._is_slack_excess(sum_slack):
                logger.info(
                    "LP returned success but used cap slack sum=%0.6f > threshold=%0.6f; triggering subset search",
                    sum_slack,
                    analyzer.max_cap_slack,
                )
                best_dims, best_weights = search_largest_feasible_subset(
                    analyzer,
                    problem.df,
                    problem.metric_col,
                    problem.dimensions,
                    problem.max_concentration,
                    problem.peer_volumes,
                    problem.peers,
                    problem.all_categories,
                )
                if best_weights is not None:
                    analyzer.slack_subset_triggered = True
                    state.weights = best_weights
                    state.converged = True
                    state.used_dimensions = best_dims
                    state.removed_dimensions = [d for d in problem.dimensions if d not in best_dims]
                    logger.info("Slack-aware policy selected global dimensions: %s", state.used_dimensions)

                    analyzer.per_dimension_weights.clear()
                    analyzer._solve_per_dimension_weights(
                        problem.df,
                        problem.metric_col,
                        state.removed_dimensions,
                        problem.peers,
                        problem.max_concentration,
                        state.weights,
                        problem.rule_name,
                    )
                else:
                    logger.info("Subset search failed to improve; keeping full-set LP solution despite slack usage")
        elif lp_solution is not None and analyzer.trigger_subset_on_slack and problem.single_weight_mode:
            logger.info("Single weight-set mode active; skipping slack-triggered subset search")

        if lp_solution is None:
            if problem.single_weight_mode:
                logger.info("Single weight-set mode active; skipping subset-search and dimension-dropping fallbacks")
            elif analyzer.auto_subset_search:
                logger.info("Searching for largest feasible global dimension subset (auto_subset_search enabled)")
                best_dims, best_weights = search_largest_feasible_subset(
                    analyzer,
                    problem.df,
                    problem.metric_col,
                    problem.dimensions,
                    problem.max_concentration,
                    problem.peer_volumes,
                    problem.peers,
                    problem.all_categories,
                )
                if best_weights is not None:
                    state.weights = best_weights
                    state.converged = True
                    state.used_dimensions = best_dims
                    state.removed_dimensions = [d for d in problem.dimensions if d not in best_dims]
                    logger.info("Auto search selected global dimensions: %s", state.used_dimensions)

                    analyzer.per_dimension_weights.clear()
                    analyzer._solve_per_dimension_weights(
                        problem.df,
                        problem.metric_col,
                        state.removed_dimensions,
                        problem.peers,
                        problem.max_concentration,
                        state.weights,
                        problem.rule_name,
                    )
            else:
                scores = analyzer._dimension_unbalance_scores(problem.all_categories)
                ordered_dims = sorted(scores.keys(), key=lambda dim_name: scores[dim_name], reverse=True)
                logger.warning(
                    "LP infeasible; attempting fallback by dropping most unbalanced dimensions in order: %s",
                    ordered_dims,
                )
                for count in range(1, len(ordered_dims) + 1):
                    trial_dims = [dim_name for dim_name in problem.dimensions if dim_name not in ordered_dims[:count]]
                    if not trial_dims:
                        continue
                    trial_cats, trial_peer_vols, _ = analyzer._build_categories(
                        problem.df, problem.metric_col, trial_dims
                    )
                    if not trial_cats:
                        continue
                    solution = self._run_lp(
                        WeightingProblem(
                            df=problem.df,
                            metric_col=problem.metric_col,
                            dimensions=trial_dims,
                            all_categories=trial_cats,
                            peer_volumes=trial_peer_vols,
                            peers=problem.peers,
                            rule_name=problem.rule_name,
                            max_concentration=problem.max_concentration,
                            single_weight_mode=problem.single_weight_mode,
                        ),
                        trial_cats,
                        trial_peer_vols,
                    )
                    if solution is not None:
                        state.weights = solution
                        state.converged = True
                        state.used_dimensions = trial_dims
                        state.removed_dimensions = ordered_dims[:count]
                        logger.info("LP succeeded after dropping dimensions: %s", state.removed_dimensions)
                        analyzer.per_dimension_weights.clear()
                        analyzer._solve_per_dimension_weights(
                            problem.df,
                            problem.metric_col,
                            state.removed_dimensions,
                            problem.peers,
                            problem.max_concentration,
                            state.weights,
                            problem.rule_name,
                        )
                        break
        elif not state.converged:
            state.weights = lp_solution
            state.converged = True
            state.residual_cap_violation = bool(analyzer.last_lp_stats.get("residual_cap_violation", False))
            state.residual_additional_violation = bool(
                analyzer.last_lp_stats.get("residual_additional_violation", False)
            )
            for dim_name in state.used_dimensions:
                analyzer.weight_methods[dim_name] = "Global-LP"

        analyzer.global_dimensions_used = state.used_dimensions
        analyzer.removed_dimensions = state.removed_dimensions

    def run_heuristic_fallback(self, problem: WeightingProblem, state: WeightingSolveState) -> None:
        analyzer = self.analyzer
        if state.converged:
            return

        logger.warning("Global LP failed or no feasible subset found; attempting heuristic global optimization.")
        heuristic_result = analyzer.heuristic_solver.solve(
            build_heuristic_request(
                analyzer,
                peers=problem.peers,
                categories=problem.all_categories,
                max_concentration=problem.max_concentration,
                peer_volumes=problem.peer_volumes,
                target_weights=state.weights,
                rule_name=problem.rule_name,
            )
        )
        if heuristic_result:
            if not heuristic_result.success:
                logger.warning("Heuristic global solver did not converge; using best-effort weights.")
            state.heuristic_converged = bool(heuristic_result.stats.get("converged", heuristic_result.success))
            state.residual_cap_violation = bool(heuristic_result.stats.get("residual_cap_violation", False))
            state.residual_additional_violation = bool(
                heuristic_result.stats.get("residual_additional_violation", False)
            )
            state.weights = heuristic_result.weights
            state.converged = True
            state.used_dimensions = list(problem.dimensions)
            state.removed_dimensions = []
            for dim_name in state.used_dimensions:
                analyzer.weight_methods[dim_name] = "Global-Bayesian"
            analyzer.global_dimensions_used = state.used_dimensions
            analyzer.removed_dimensions = state.removed_dimensions
        else:
            analyzer.compliance_blocked_reason = "optimization_failed"
            logger.error(
                "Global LP, subset search, and heuristic optimization all failed; "
                "aborting analysis to avoid emitting unvalidated identity weights."
            )
            raise ValueError(
                "Weight optimization failed: no solver produced a feasible weight set. "
                "See Structural Diagnostics for infeasibility causes."
            )

    def finalize_converged_weights(self, problem: WeightingProblem, state: WeightingSolveState) -> None:
        analyzer = self.analyzer
        weights = state.weights

        analyzer.additional_constraint_violations = []
        if analyzer.enforce_additional_constraints and problem.rule_name in ("6/30", "7/35", "10/40"):
            violations = analyzer._find_additional_constraint_violations(
                problem.all_categories,
                problem.peers,
                weights,
                problem.rule_name,
                problem.peer_volumes,
            )
            analyzer.additional_constraint_violations = violations
            if violations:
                logger.warning(
                    "Additional constraints violated in %s categories; running heuristic optimization to correct.",
                    len(violations),
                )
                strict_feasibility_mode = float(analyzer.tolerance) <= float(analyzer.COMPARISON_EPSILON)
                target_multipliers = (
                    None
                    if strict_feasibility_mode
                    else ({peer: weights[peer] for peer in problem.peers} if weights else None)
                )
                if strict_feasibility_mode:
                    logger.info(
                        "Strict tolerance mode detected (tolerance=0). "
                        "Running feasibility-first heuristic without global-weight anchoring."
                    )
                heuristic_result = analyzer.heuristic_solver.solve(
                    build_heuristic_request(
                        analyzer,
                        peers=problem.peers,
                        categories=problem.all_categories,
                        max_concentration=problem.max_concentration,
                        peer_volumes=problem.peer_volumes,
                        target_weights=target_multipliers,
                        rule_name=problem.rule_name,
                    )
                )
                if heuristic_result:
                    if not heuristic_result.success:
                        logger.warning("Heuristic solver did not converge; using best-effort weights.")
                    weights = heuristic_result.weights
                    analyzer.additional_constraint_violations = analyzer._find_additional_constraint_violations(
                        problem.all_categories,
                        problem.peers,
                        weights,
                        problem.rule_name,
                        problem.peer_volumes,
                    )
                    if analyzer.additional_constraint_violations:
                        logger.warning(
                            "Additional constraints still violated in %s categories after heuristic optimization.",
                            len(analyzer.additional_constraint_violations),
                        )
                else:
                    logger.warning("Heuristic optimization failed; keeping LP weights with violations.")

        weights = analyzer._nudge_borderline_cap_excess(
            weights, problem.all_categories, problem.max_concentration, state.used_dimensions
        )
        analyzer._store_final_weights(problem.peers, problem.peer_volumes, weights)
        state.weights = weights

    def post_validate_and_correct(self, problem: WeightingProblem, state: WeightingSolveState) -> None:
        analyzer = self.analyzer
        weights = state.weights
        used_dimensions = state.used_dimensions
        all_categories = problem.all_categories

        if analyzer.time_column and analyzer.consistent_weights:
            original_dims = set(used_dimensions)
            time_aware_to_original: Dict[str, str] = {}
            for cat in all_categories:
                dim_name = cat["dimension"]
                if dim_name.startswith(f"{CategoryBuilder.TIME_TOTAL_DIMENSION_PREFIX}{analyzer.time_column}"):
                    time_aware_to_original[dim_name] = "_TIME_TOTAL"
                elif dim_name.endswith(f"_{analyzer.time_column}"):
                    original_dim = dim_name.replace(f"_{analyzer.time_column}", "")
                    if original_dim in original_dims:
                        time_aware_to_original[dim_name] = original_dim

            val_dims_set = set(
                (
                    time_aware_to_original.get(cat["dimension"], cat["dimension"]),
                    cat["category"],
                    cat.get("time_period"),
                )
                for cat in all_categories
                if time_aware_to_original.get(cat["dimension"], cat["dimension"]) in original_dims
                or cat["dimension"].startswith(CategoryBuilder.TIME_TOTAL_DIMENSION_PREFIX)
            )
        else:
            val_dims_set = set(
                (cat["dimension"], cat["category"], None)
                for cat in all_categories
                if cat["dimension"] in used_dimensions
            )

        logger.info("\nGlobal weights validation across all %s categories:", len(val_dims_set))
        logger.info("\nFinal global weight multipliers:")

        dimensions_with_violations: List[str] = []

        for peer in sorted(problem.peers, key=lambda peer_name: weights[peer_name], reverse=True):
            peer_max_share = 0.0
            peer_violation_dims: List[str] = []
            for cat in all_categories:
                if cat["peer"] != peer:
                    continue

                if analyzer.time_column and analyzer.consistent_weights:
                    dim_name = cat["dimension"]
                    if dim_name.startswith(f"{CategoryBuilder.TIME_TOTAL_DIMENSION_PREFIX}{analyzer.time_column}"):
                        include_in_validation = True
                        original_dim = "_TIME_TOTAL"
                    elif dim_name.endswith(f"_{analyzer.time_column}"):
                        original_dim = dim_name.replace(f"_{analyzer.time_column}", "")
                        include_in_validation = original_dim in used_dimensions
                    else:
                        include_in_validation = cat["dimension"] in used_dimensions
                        original_dim = cat["dimension"]
                else:
                    include_in_validation = cat["dimension"] in used_dimensions
                    original_dim = cat["dimension"]

                if not include_in_validation:
                    continue

                category_vol_weighted = cat["category_volume"] * weights[peer]
                if "time_period" in cat:
                    matching_cats = [
                        candidate
                        for candidate in all_categories
                        if candidate["dimension"] == cat["dimension"]
                        and candidate["category"] == cat["category"]
                        and candidate.get("time_period") == cat.get("time_period")
                    ]
                else:
                    matching_cats = [
                        candidate
                        for candidate in all_categories
                        if candidate["dimension"] == cat["dimension"]
                        and candidate["category"] == cat["category"]
                    ]

                total_weighted = sum(
                    candidate["category_volume"] * weights[candidate["peer"]] for candidate in matching_cats
                )
                adjusted_share = (category_vol_weighted / total_weighted * 100) if total_weighted > 0 else 0.0
                peer_max_share = max(peer_max_share, adjusted_share)

                if analyzer._is_share_violation(adjusted_share, problem.max_concentration):
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

        has_additional_violations = bool(getattr(analyzer, "additional_constraint_violations", []))
        if (
            _weights_are_identity(weights)
            and not real_dimensions_with_violations
            and not has_additional_violations
        ):
            logger.info(
                "Global optimization retained identity multipliers because all privacy constraints "
                "were already satisfied for the selected dimensions."
            )

        if problem.single_weight_mode and real_dimensions_with_violations:
            logger.info(
                "Single weight-set mode active; keeping global weights despite violating dimensions: %s",
                real_dimensions_with_violations,
            )
        elif real_dimensions_with_violations:
            logger.info("\nDimensions with violations detected: %s", real_dimensions_with_violations)
            logger.info("Computing per-dimension weights for these dimensions...")
            for violation_dim in real_dimensions_with_violations:
                if violation_dim not in problem.dimensions:
                    logger.info(
                        "Skipping non-user dimension during per-dimension re-weighting: %s",
                        violation_dim,
                    )
                    continue
                violation_cats, violation_peer_vols, _ = analyzer._build_categories(
                    problem.df, problem.metric_col, [violation_dim]
                )
                if not violation_cats:
                    continue

                has_time = any("time_period" in cat for cat in violation_cats)
                time_info = (
                    f" (time-aware: {len([cat for cat in violation_cats if cat.get('time_period')])} constraints)"
                    if has_time
                    else ""
                )
                logger.info("Solving per-dimension weights for '%s'%s", violation_dim, time_info)

                orig_tolerance = analyzer.tolerance
                analyzer.tolerance = 0.0
                lp_result = analyzer.lp_solver.solve(
                    build_lp_request(
                        analyzer,
                        peers=problem.peers,
                        categories=violation_cats,
                        max_concentration=problem.max_concentration,
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
                        if "time_period" in cat:
                            matching_cats = [
                                entry
                                for entry in violation_cats
                                if entry["dimension"] == cat["dimension"]
                                and entry["category"] == cat["category"]
                                and entry.get("time_period") == cat.get("time_period")
                            ]
                        else:
                            matching_cats = [
                                entry
                                for entry in violation_cats
                                if entry["dimension"] == cat["dimension"] and entry["category"] == cat["category"]
                            ]

                        cat_vol_weighted = cat["category_volume"] * violation_solution[cat["peer"]]
                        total_weighted = sum(
                            entry["category_volume"] * violation_solution[entry["peer"]]
                            for entry in matching_cats
                        )
                        adjusted_share = (cat_vol_weighted / total_weighted * 100) if total_weighted > 0 else 0.0

                        if analyzer._is_share_violation(adjusted_share, problem.max_concentration):
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
                    target_multipliers = (
                        None if strict_feasibility_mode else {peer: weights[peer] for peer in problem.peers}
                    )
                    if strict_feasibility_mode:
                        logger.info(
                            "  Strict tolerance mode detected for '%s'; "
                            "using feasibility-first per-dimension heuristic.",
                            violation_dim,
                        )
                    heuristic_result = analyzer.heuristic_solver.solve(
                        build_heuristic_request(
                            analyzer,
                            peers=problem.peers,
                            categories=violation_cats,
                            max_concentration=problem.max_concentration,
                            peer_volumes=violation_peer_vols,
                            target_weights=target_multipliers,
                            rule_name=problem.rule_name,
                            tolerance=analyzer.tolerance,
                        )
                    )
                    if heuristic_result:
                        if not heuristic_result.success:
                            logger.warning(
                                "Per-dimension heuristic solver did not converge; using best-effort weights."
                            )
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

    def assemble_weighting_result(
        self,
        problem: Optional[WeightingProblem] = None,
        state: Optional[WeightingSolveState] = None,
    ) -> WeightingResult:
        analyzer = self.analyzer
        result = weighting_result_from_analyzer(analyzer)
        residual_violations = len(getattr(analyzer, "additional_constraint_violations", []) or [])
        last_lp_stats = result.last_lp_stats or {}
        residual_cap_violation = bool(
            (state.residual_cap_violation or last_lp_stats.get("residual_cap_violation", False))
            if state is not None
            else last_lp_stats.get("residual_cap_violation", False)
        )
        residual_additional_violation = bool(
            (state.residual_additional_violation or last_lp_stats.get("residual_additional_violation", False))
            if state is not None
            else residual_violations
        )
        dynamic_stats = getattr(analyzer, "dynamic_constraint_stats", {}) or {}
        relaxation_used = int(dynamic_stats.get("relaxed", 0) or 0) > 0
        primary_passed = not residual_cap_violation
        secondary_passed = residual_violations == 0 and not residual_additional_violation
        heuristic_failed = state is not None and state.heuristic_converged is False
        if primary_passed and secondary_passed and not relaxation_used and not heuristic_failed:
            verdict = "strict_compliant"
        elif primary_passed and secondary_passed:
            verdict = "best_effort"
        else:
            verdict = "non_compliant"
        result.compliance_state = WeightingComplianceState(
            rule_name=(problem.rule_name if problem is not None else result.privacy_rule_name),
            primary_cap_passed=primary_passed,
            secondary_rule_passed=secondary_passed,
            relaxation_used=relaxation_used,
            heuristic_converged=state.heuristic_converged if state is not None else None,
            residual_violations=int(residual_violations),
            verdict=verdict,
        )
        analyzer.weighting_compliance_state = result.compliance_state
        return result
