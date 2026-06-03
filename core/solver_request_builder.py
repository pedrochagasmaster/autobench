"""Shared SolverRequest construction for LP and heuristic solvers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .contracts import SolverRequest


def build_lp_request(
    settings: Any,
    *,
    peers: List[str],
    categories: List[Dict[str, Any]],
    max_concentration: float,
    peer_volumes: Dict[str, float],
    tolerance: Optional[float] = None,
) -> SolverRequest:
    """Build an LP SolverRequest from analyzer-like settings."""
    return SolverRequest(
        peers=peers,
        categories=categories,
        max_concentration=max_concentration,
        peer_volumes=peer_volumes,
        rank_preservation_strength=settings.rank_preservation_strength,
        rank_constraint_mode=settings.rank_constraint_mode,
        rank_constraint_k=settings.rank_constraint_k,
        tolerance=float(settings.tolerance if tolerance is None else tolerance),
        volume_weighted_penalties=settings.volume_weighted_penalties,
        volume_weighting_exponent=settings.volume_weighting_exponent,
        lambda_penalty=settings.lambda_penalty,
        max_iterations=settings.max_iterations,
        min_weight=settings.min_weight,
        max_weight=settings.max_weight,
    )


def build_heuristic_request(
    settings: Any,
    *,
    peers: List[str],
    categories: List[Dict[str, Any]],
    max_concentration: float,
    peer_volumes: Dict[str, float],
    target_weights: Optional[Dict[str, float]],
    rule_name: Optional[str],
    tolerance: Optional[float] = None,
) -> SolverRequest:
    """Build a heuristic SolverRequest from analyzer-like settings."""
    return SolverRequest(
        peers=peers,
        categories=categories,
        max_concentration=max_concentration,
        peer_volumes=peer_volumes,
        target_weights=target_weights,
        rule_name=rule_name,
        min_weight=settings.min_weight,
        max_weight=settings.max_weight,
        tolerance=float(settings.tolerance if tolerance is None else tolerance),
        max_iterations=settings.bayesian_max_iterations,
        learning_rate=settings.bayesian_learning_rate,
        violation_penalty_weight=settings.violation_penalty_weight,
        merchant_mode=settings.merchant_mode,
        enforce_additional_constraints=settings.enforce_additional_constraints,
        dynamic_constraints_enabled=settings.dynamic_constraints_enabled,
        time_column=settings.time_column,
        min_peer_count_for_constraints=settings.min_peer_count_for_constraints,
        min_effective_peer_count=settings.min_effective_peer_count,
        min_category_volume_share=settings.min_category_volume_share,
        min_overall_volume_share=settings.min_overall_volume_share,
        min_representativeness=settings.min_representativeness,
        dynamic_threshold_scale_floor=settings.dynamic_threshold_scale_floor,
        dynamic_count_scale_floor=settings.dynamic_count_scale_floor,
        representativeness_penalty_floor=settings.representativeness_penalty_floor,
        representativeness_penalty_power=settings.representativeness_penalty_power,
    )
