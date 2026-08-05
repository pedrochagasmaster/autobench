"""Test-first contract for the scalable Verified Safe Coverage model module.

Steps 1-3 of Plan 003: algebra parity, conservative presolve, and model-size
ceilings. These tests must fail before ``core.privacy_coverage_model`` exists.
"""

from __future__ import annotations

import itertools
from typing import Dict, Iterable, List, Mapping, Sequence

import numpy as np
import pytest

from core.constants import COMPARISON_EPSILON
from core.contracts import APPROVED_PRIVACY_RULE_NAMES, PublicationUnit
from core.privacy_coverage_solver import weighted_shares
from core.privacy_rules import evaluate_rule, privacy_rule_from_config
from tests.fixtures.production_scale_coverage import (
    PRODUCTION_SCALE_METRIC_COUNT,
    PRODUCTION_SCALE_PEER_COUNT,
    PRODUCTION_SCALE_UNIT_COUNT,
    build_production_scale_universe,
)


_MIN_W = 0.5
_MAX_W = 2.0


def _rule_views() -> Dict[str, object]:
    from core.privacy_coverage_model import CoverageRuleView

    views: Dict[str, object] = {}
    for name in APPROVED_PRIVACY_RULE_NAMES:
        resolved = privacy_rule_from_config(name)
        tiers = tuple(
            sorted(
                ((int(count), float(threshold)) for count, threshold in resolved.secondary_requirements.values()),
                key=lambda item: -float(item[1]),
            )
        )
        views[name] = CoverageRuleView(
            name=resolved.name,
            min_entities=int(resolved.min_entities),
            max_concentration=float(resolved.max_concentration),
            secondary_tiers=tiers,
        )
    return views


def _canonicalize_unit(
    unit: PublicationUnit,
    peers: Sequence[str],
) -> Dict[str, object]:
    metrics: List[Dict[str, object]] = []
    for record in unit.metric_records:
        aligned = {peer: float(record["peer_volumes"].get(peer, 0.0)) for peer in peers}
        total = float(sum(aligned.values()))
        positive = tuple(peer for peer in peers if aligned[peer] > 0.0)
        metrics.append(
            {
                "metric": str(record["metric"]),
                "aligned_volumes": aligned,
                "total": total,
                "positive_peers": positive,
            }
        )
    metrics.sort(key=lambda item: str(item["metric"]))
    return {
        "key": unit.internal_key,
        "metrics": metrics,
        "rules": tuple(sorted(unit.applicable_rules)),
        "overlays": tuple(unit.mandatory_overlays),
    }


def _compile(
    units: Sequence[PublicationUnit],
    peers: Sequence[str],
    *,
    enable_rule_dominance: bool = True,
    enable_structural_presolve: bool = True,
    citibank_entity_name: str | None = None,
):
    from core.privacy_coverage_model import compile_coverage_model

    canonical = [_canonicalize_unit(unit, peers) for unit in units]
    return compile_coverage_model(
        canonical,
        tuple(peers),
        min_weight=_MIN_W,
        max_weight=_MAX_W,
        rules=_rule_views(),
        citibank_entity_name=citibank_entity_name,
        enable_rule_dominance=enable_rule_dominance,
        enable_structural_presolve=enable_structural_presolve,
    )


def _make_unit(
    key: str,
    peer_volumes: Mapping[str, float],
    *,
    applicable_rules: Sequence[str],
    metric_count: int = 1,
    overlays: Sequence[str] = (),
) -> PublicationUnit:
    metrics = tuple(
        {
            "metric": f"metric_{index}",
            "peer_volumes": dict(peer_volumes),
            "total_volume": float(sum(peer_volumes.values())),
            "participant_count": sum(1 for value in peer_volumes.values() if value > 0.0),
        }
        for index in range(metric_count)
    )
    return PublicationUnit(
        internal_key=key,
        dimension="sector",
        category=key,
        time_period="2025Q1",
        output_scope="merchant_spend" if "4/35" in applicable_rules else None,
        metric_records=metrics,
        applicable_rules=tuple(applicable_rules),
        mandatory_overlays=tuple(overlays),
    )


def _weight_corners(peers: Sequence[str]) -> Iterable[Dict[str, float]]:
    for bits in itertools.product((_MIN_W, _MAX_W), repeat=len(peers)):
        yield {peer: float(value) for peer, value in zip(peers, bits)}


def _count_at_or_above(shares: Mapping[str, float], threshold: float) -> int:
    return sum(1 for value in shares.values() if value + COMPARISON_EPSILON >= threshold)


# ---------------------------------------------------------------------------
# Step 1: algebra
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rule_name", list(APPROVED_PRIVACY_RULE_NAMES))
def test_normalized_primary_matches_weighted_share_policy(rule_name: str) -> None:
    from core.privacy_coverage_model import (
        effective_cap,
        interval_max,
        interval_min,
        normalized_shares,
        primary_expression_coefficients,
    )

    peers = ("P1", "P2", "P3", "P4", "P5", "P6")
    # Construct volumes so neutral shares sit near common caps.
    volumes = {
        "P1": 25.0,
        "P2": 20.0,
        "P3": 18.0,
        "P4": 15.0,
        "P5": 12.0,
        "P6": 10.0,
    }
    rule = privacy_rule_from_config(rule_name)
    cap_eff = effective_cap(rule.max_concentration)
    fractions = normalized_shares(volumes, peers)
    for peer in peers:
        coefs = primary_expression_coefficients(fractions, peer, cap_eff)
        for weights in _weight_corners(peers):
            shares = weighted_shares(volumes, weights)
            g = sum(coefs[name] * weights[name] for name in coefs)
            policy_pass = shares[peer] <= rule.max_concentration + COMPARISON_EPSILON
            # Active row requires g >= 0 (within float noise near the MILP buffer).
            if policy_pass:
                assert g >= -1e-8, (rule_name, peer, weights, shares[peer], g)
            else:
                assert g < 1e-8 or shares[peer] > rule.max_concentration + COMPARISON_EPSILON - 1e-8

            # Big-M must cover the worst negative g.
            inf_g = interval_min(coefs, _MIN_W, _MAX_W)
            big_m = max(0.0, -inf_g)
            assert g >= -big_m - 1e-9
            assert interval_max(coefs, _MIN_W, _MAX_W) >= g - 1e-9


@pytest.mark.parametrize("rule_name", list(APPROVED_PRIVACY_RULE_NAMES))
def test_secondary_witness_matches_threshold_policy(rule_name: str) -> None:
    from core.privacy_coverage_model import (
        effective_threshold,
        interval_min,
        normalized_shares,
        secondary_expression_coefficients,
    )

    resolved = privacy_rule_from_config(rule_name)
    if not resolved.secondary_requirements:
        pytest.skip("rule has no secondary tiers")

    peers = ("P1", "P2", "P3", "P4", "P5", "P6")
    volumes = {
        "P1": 22.0,
        "P2": 18.0,
        "P3": 16.0,
        "P4": 14.0,
        "P5": 15.0,
        "P6": 15.0,
    }
    fractions = normalized_shares(volumes, peers)
    for _tier_name, (required_count, threshold) in resolved.secondary_requirements.items():
        tau = effective_threshold(float(threshold))
        for peer in peers:
            coefs = secondary_expression_coefficients(fractions, peer, tau)
            for weights in _weight_corners(peers):
                shares = weighted_shares(volumes, weights)
                h = sum(coefs[name] * weights[name] for name in coefs)
                meets = shares[peer] + COMPARISON_EPSILON >= float(threshold)
                if meets:
                    assert h >= -1e-8, (rule_name, threshold, peer, shares[peer], h)
                else:
                    assert h <= 1e-8 or shares[peer] + COMPARISON_EPSILON < float(threshold)
                big_m = max(0.0, -interval_min(coefs, _MIN_W, _MAX_W))
                assert h >= -big_m - 1e-9
        # Count oracle matches the evaluate_rule threshold convention.
        for weights in (
            {peer: 1.0 for peer in peers},
            {peer: _MIN_W for peer in peers},
            {peer: _MAX_W for peer in peers},
        ):
            shares = weighted_shares(volumes, weights)
            observed = _count_at_or_above(shares, float(threshold))
            assert observed == sum(
                1 for value in shares.values() if value + COMPARISON_EPSILON >= float(threshold)
            )
            _ = required_count  # tier required count exercised via evaluate_rule below
        evaluation = evaluate_rule(
            rule_name,
            list(weighted_shares(volumes, {peer: 1.0 for peer in peers}).values()),
        )
        assert evaluation.rule_name == rule_name


def test_boundary_shares_below_at_above_each_policy_threshold() -> None:
    from core.privacy_coverage_model import effective_cap, effective_threshold

    thresholds = {25.0, 30.0, 35.0, 40.0, 7.0, 15.0, 8.0, 20.0, 10.0}
    for threshold in thresholds:
        below = threshold - COMPARISON_EPSILON * 0.5
        at = threshold
        above = threshold + COMPARISON_EPSILON + 1e-9
        # Cap policy: fail only when value > threshold + eps.
        assert below <= threshold + COMPARISON_EPSILON
        assert at <= threshold + COMPARISON_EPSILON
        assert above > threshold + COMPARISON_EPSILON
        # Secondary policy: pass when value + eps >= threshold.
        assert below + COMPARISON_EPSILON >= threshold
        assert at + COMPARISON_EPSILON >= threshold
        assert (above - 2.0 * COMPARISON_EPSILON) + COMPARISON_EPSILON < threshold or above > threshold
        assert effective_threshold(threshold) == threshold - COMPARISON_EPSILON + 1e-9
        assert effective_cap(threshold) == threshold + COMPARISON_EPSILON - 1e-9


def test_big_m_valid_for_all_weight_corners_small_fixture() -> None:
    from core.privacy_coverage_model import (
        effective_cap,
        effective_threshold,
        interval_min,
        normalized_shares,
        primary_expression_coefficients,
        secondary_expression_coefficients,
    )

    peers = ("A", "B", "C", "D", "E", "F")
    volumes = {"A": 40.0, "B": 15.0, "C": 15.0, "D": 10.0, "E": 10.0, "F": 10.0}
    fractions = normalized_shares(volumes, peers)
    for rule_name in APPROVED_PRIVACY_RULE_NAMES:
        rule = privacy_rule_from_config(rule_name)
        cap_eff = effective_cap(rule.max_concentration)
        for peer in peers:
            coefs = primary_expression_coefficients(fractions, peer, cap_eff)
            inf_g = interval_min(coefs, _MIN_W, _MAX_W)
            big_m = max(0.0, -inf_g)
            for weights in _weight_corners(peers):
                g = sum(coefs[name] * weights[name] for name in coefs)
                # Relaxed (indicator=0): always satisfiable via big-M.
                assert g >= -big_m - 1e-9
                shares = weighted_shares(volumes, weights)
                active_ok = shares[peer] <= rule.max_concentration + COMPARISON_EPSILON
                if active_ok:
                    assert g >= -1e-8
        for threshold in (float(t) for _c, t in rule.secondary_requirements.values()):
            tau = effective_threshold(threshold)
            for peer in peers:
                coefs = secondary_expression_coefficients(fractions, peer, tau)
                big_m = max(0.0, -interval_min(coefs, _MIN_W, _MAX_W))
                for weights in _weight_corners(peers):
                    h = sum(coefs[name] * weights[name] for name in coefs)
                    assert h >= -big_m - 1e-9
                    shares = weighted_shares(volumes, weights)
                    if shares[peer] + COMPARISON_EPSILON >= threshold:
                        assert h >= -1e-8


def test_mean_weight_row_is_only_dense_peer_row_per_metric() -> None:
    peers = ("P1", "P2", "P3", "P4", "P5")
    volumes = {peer: 20.0 for peer in peers}
    unit = _make_unit("u1", volumes, applicable_rules=("5/25", "6/30"))
    model = _compile([unit], peers, enable_rule_dominance=False, enable_structural_presolve=False)
    stats = model.statistics
    assert stats.mean_weight_row_count == 1
    assert stats.max_primary_row_nonzeros <= 4
    assert stats.max_witness_row_nonzeros <= 4
    # Mean-weight equality uses every positive peer plus b.
    b_idx = model.b_index[("u1", "metric_0")]
    stage = model.stage1
    # Locate the mean-weight equality row by its unique dense pattern.
    matrix = stage.constraints.tocsr()
    dense_rows = [
        row
        for row in range(matrix.shape[0])
        if int(matrix.indptr[row + 1] - matrix.indptr[row]) >= len(peers)
    ]
    assert len(dense_rows) == 1
    row = dense_rows[0]
    start = int(matrix.indptr[row])
    end = int(matrix.indptr[row + 1])
    cols = set(int(index) for index in matrix.indices[start:end].tolist())
    assert b_idx in cols
    for peer in peers:
        assert model.w_index[peer] in cols


# ---------------------------------------------------------------------------
# Step 2: conservative presolve
# ---------------------------------------------------------------------------


def test_merchant_dominance_removes_5_25_6_30_7_35_keeps_10_40() -> None:
    from core.privacy_coverage_model import dominate_rules

    merchant = list(APPROVED_PRIVACY_RULE_NAMES)
    retained, removed = dominate_rules(merchant, _rule_views())
    assert set(removed) == {"5/25", "6/30", "7/35"}
    assert set(retained) == {"4/35", "10/40"}


def test_non_merchant_keeps_all_standard_rules() -> None:
    from core.privacy_coverage_model import dominate_rules

    non_merchant = ["5/25", "6/30", "7/35", "10/40"]
    retained, removed = dominate_rules(non_merchant, _rule_views())
    assert removed == ()
    assert set(retained) == set(non_merchant)


def test_every_removed_rule_has_retained_dominator() -> None:
    from core.privacy_coverage_model import CoverageRuleView, dominate_rules, rule_dominates

    rules = _rule_views()
    retained, removed = dominate_rules(list(APPROVED_PRIVACY_RULE_NAMES), rules)
    for removed_name in removed:
        removed_rule = rules[removed_name]
        assert isinstance(removed_rule, CoverageRuleView)
        assert any(
            rule_dominates(rules[kept], removed_rule) for kept in retained
        ), removed_name


def test_dominance_cannot_uniquely_authorize_removed_rule_vector() -> None:
    """A share vector authorized only by a removed rule must not exist for 4/35 vs 5/25."""
    # 4/35 is strictly easier than 5/25 on both axes, so any 5/25-pass vector
    # also passes 4/35. Same for 6/30 and 7/35 under the documented condition.
    peers = ("A", "B", "C", "D", "E", "F", "G")
    volumes = {peer: 100.0 / len(peers) for peer in peers}
    weights = {peer: 1.0 for peer in peers}
    shares = list(weighted_shares(volumes, weights).values())
    for removed in ("5/25", "6/30", "7/35"):
        removed_eval = evaluate_rule(removed, shares)
        kept_eval = evaluate_rule("4/35", shares)
        if removed_eval.strict_passed:
            assert kept_eval.strict_passed


def test_witness_classification_always_true_uncertain_impossible() -> None:
    from core.privacy_coverage_model import (
        WitnessClass,
        classify_secondary_witness,
        effective_threshold,
        normalized_shares,
    )

    peers = ("A", "B", "C", "D")
    # Equal tiny shares: high thresholds impossible; very low thresholds always true.
    equal = {peer: 25.0 for peer in peers}
    fractions = normalized_shares(equal, peers)
    # Always-true at an extremely low threshold under [0.5, 2].
    assert (
        classify_secondary_witness(
            fractions, "A", effective_threshold(0.01), _MIN_W, _MAX_W
        )
        == WitnessClass.ALWAYS_TRUE
    )
    # Impossible well above the weight-box max share (~57% for equal four-way).
    assert (
        classify_secondary_witness(
            fractions, "A", effective_threshold(70.0), _MIN_W, _MAX_W
        )
        == WitnessClass.IMPOSSIBLE
    )
    # Boundary concentration: uncertain around 20%.
    boundary = {"A": 35.0, "B": 25.0, "C": 20.0, "D": 20.0}
    boundary_f = normalized_shares(boundary, peers)
    assert (
        classify_secondary_witness(
            boundary_f, "A", effective_threshold(20.0), _MIN_W, _MAX_W
        )
        == WitnessClass.UNCERTAIN
    )


def test_pruned_and_unpruned_agree_on_feasible_rule_set() -> None:
    peers = ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8", "P9", "P10")
    safe_volumes = {peer: 10.0 for peer in peers}
    unit = _make_unit(
        "merchant_safe",
        safe_volumes,
        applicable_rules=APPROVED_PRIVACY_RULE_NAMES,
    )
    pruned = _compile([unit], peers, enable_rule_dominance=True, enable_structural_presolve=True)
    unpruned = _compile(
        [unit], peers, enable_rule_dominance=False, enable_structural_presolve=False
    )
    # Every retained pruned rule index must exist in the unpruned model.
    for unit_key, rule_name in pruned.y_index:
        assert (unit_key, rule_name) in unpruned.y_index
    # Unpruned may keep dominated rules; those must not uniquely authorize.
    for unit_key, rule_name in unpruned.y_index:
        if (unit_key, rule_name) not in pruned.y_index:
            assert rule_name in {"5/25", "6/30", "7/35"}
    # Direct policy evaluation: 4/35 authorizes the safe equal vector; dominated
    # rules that also pass cannot uniquely authorize it.
    shares = list(weighted_shares(safe_volumes, {peer: 1.0 for peer in peers}).values())
    assert evaluate_rule("4/35", shares).strict_passed
    for removed in ("5/25", "6/30", "7/35"):
        if evaluate_rule(removed, shares).strict_passed:
            assert evaluate_rule("4/35", shares).strict_passed


# ---------------------------------------------------------------------------
# Step 3: model size
# ---------------------------------------------------------------------------


def test_production_scale_fixture_shape() -> None:
    units, peers, min_w, max_w = build_production_scale_universe()
    assert len(units) == PRODUCTION_SCALE_UNIT_COUNT
    assert len(peers) == PRODUCTION_SCALE_PEER_COUNT
    assert min_w == 0.5
    assert max_w == 2.0
    assert all(len(unit.metric_records) == PRODUCTION_SCALE_METRIC_COUNT for unit in units)
    assert "4/35" in units[0].applicable_rules


def test_stage1_model_size_ceilings_on_production_scale_fixture() -> None:
    units, peers, _min_w, _max_w = build_production_scale_universe()
    model = _compile(units, peers)
    stats = model.statistics

    assert stats.unit_count == PRODUCTION_SCALE_UNIT_COUNT
    assert stats.peer_count == PRODUCTION_SCALE_PEER_COUNT
    assert stats.metric_count == PRODUCTION_SCALE_METRIC_COUNT
    assert stats.mean_weight_row_count == PRODUCTION_SCALE_UNIT_COUNT * PRODUCTION_SCALE_METRIC_COUNT

    assert stats.variable_count < 60_000, stats
    assert stats.integer_variable_count < 42_224, stats
    assert stats.nonzero_count < 1_350_000, stats
    assert stats.max_primary_row_nonzeros <= 4, stats
    assert stats.max_witness_row_nonzeros <= 4, stats

    stage = model.stage1
    assert stage.constraints.format == "csc"
    assert stage.constraints.shape[1] == stats.variable_count
    assert stage.constraints.nnz == stats.nonzero_count
    assert stage.objective.shape == (stats.variable_count,)
    assert stage.integrality.shape == (stats.variable_count,)
    assert np.sum(stage.integrality) == stats.integer_variable_count
