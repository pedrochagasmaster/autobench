"""Test-first contract for the direct HiGHS coverage adapter and neutral MIP start.

Steps 1, 2, and 5 of Plan 004. Small generated models only — no protected data.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from unittest.mock import MagicMock

import numpy as np
import pytest

from core.constants import COMPARISON_EPSILON
from core.contracts import APPROVED_PRIVACY_RULE_NAMES, PublicationUnit
from core.privacy_coverage import CITIBANK_OVERLAY_NAME
from core.privacy_coverage_model import (
    CoverageRuleView,
    StageConstraintSet,
    WitnessClass,
    classify_secondary_witness,
    compile_coverage_model,
    effective_threshold,
    normalized_shares,
)
from core.privacy_rules import privacy_rule_from_config

_MIN_W = 0.5
_MAX_W = 2.0
_FEAS_TOL = 1e-6


def _rule_views() -> Dict[str, CoverageRuleView]:
    views: Dict[str, CoverageRuleView] = {}
    for name in APPROVED_PRIVACY_RULE_NAMES:
        resolved = privacy_rule_from_config(name)
        tiers = tuple(
            sorted(
                (
                    (int(count), float(threshold))
                    for count, threshold in resolved.secondary_requirements.values()
                ),
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
) -> Dict[str, Any]:
    metrics: List[Dict[str, Any]] = []
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


def _make_unit(
    key: str,
    peer_volumes: Mapping[str, float],
    *,
    applicable_rules: Sequence[str],
    metric_count: int = 1,
    overlays: Sequence[str] = (),
    metric_volumes: Optional[Sequence[Mapping[str, float]]] = None,
) -> PublicationUnit:
    if metric_volumes is None:
        volumes_list: Sequence[Mapping[str, float]] = [peer_volumes] * metric_count
    else:
        volumes_list = metric_volumes
    metrics = tuple(
        {
            "metric": f"metric_{index}",
            "peer_volumes": dict(volumes),
            "total_volume": float(sum(volumes.values())),
            "participant_count": sum(1 for value in volumes.values() if value > 0.0),
        }
        for index, volumes in enumerate(volumes_list)
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


def _compile(
    units: Sequence[PublicationUnit],
    peers: Sequence[str],
    *,
    enable_rule_dominance: bool = True,
    enable_structural_presolve: bool = True,
    citibank_entity_name: Optional[str] = None,
    min_weight: float = _MIN_W,
    max_weight: float = _MAX_W,
):
    canonical = [_canonicalize_unit(unit, peers) for unit in units]
    return compile_coverage_model(
        canonical,
        tuple(peers),
        min_weight=min_weight,
        max_weight=max_weight,
        rules=_rule_views(),
        citibank_entity_name=citibank_entity_name,
        enable_rule_dominance=enable_rule_dominance,
        enable_structural_presolve=enable_structural_presolve,
    )


def _balanced_volumes(peers: Sequence[str], total: float = 100.0) -> Dict[str, float]:
    share = total / float(len(peers))
    return {peer: share for peer in peers}


def _hand_stage(
    *,
    n_vars: int,
    objective: np.ndarray,
    integrality: np.ndarray,
    bounds_lb: np.ndarray,
    bounds_ub: np.ndarray,
    matrix_csr_rows: Sequence[Sequence[Tuple[int, float]]],
    constraints_lb: np.ndarray,
    constraints_ub: np.ndarray,
) -> StageConstraintSet:
    from scipy.sparse import csc_array, csr_array

    n_rows = len(matrix_csr_rows)
    data: List[float] = []
    indices: List[int] = []
    indptr: List[int] = [0]
    for row in matrix_csr_rows:
        for col, value in sorted(row):
            if value == 0.0:
                continue
            indices.append(int(col))
            data.append(float(value))
        indptr.append(len(indices))
    csr = csr_array(
        (np.asarray(data), np.asarray(indices), np.asarray(indptr)),
        shape=(n_rows, n_vars),
    )
    return StageConstraintSet(
        n_vars=n_vars,
        objective=np.asarray(objective, dtype=float),
        integrality=np.asarray(integrality, dtype=int),
        bounds_lb=np.asarray(bounds_lb, dtype=float),
        bounds_ub=np.asarray(bounds_ub, dtype=float),
        constraints=csc_array(csr),
        constraints_lb=np.asarray(constraints_lb, dtype=float),
        constraints_ub=np.asarray(constraints_ub, dtype=float),
    )


# ---------------------------------------------------------------------------
# Step 1: adapter and proof contract
# ---------------------------------------------------------------------------


def test_csc_model_loading_consumes_arrays_without_dense_conversion() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession

    peers = ("P1", "P2", "P3", "P4", "P5")
    unit = _make_unit("u1", _balanced_volumes(peers), applicable_rules=("5/25",))
    model = _compile([unit], peers)
    stage = model.stage1
    session = HighsCoverageSession(stage)
    assert session.constraint_matrix is stage.constraints
    assert session.consumed_csc_indptr is stage.constraints.indptr
    assert session.consumed_csc_indices is stage.constraints.indices
    assert session.consumed_csc_data is stage.constraints.data
    result = session.solve()
    assert result.model_status in {"optimal", "limit_reached", "infeasible"}
    assert result.column_values.shape == (stage.n_vars,)


def test_binary_and_continuous_integrality_mapping() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession

    # max x + 0.5 y; x binary, y continuous in [0, 2]; x + y <= 2
    stage = _hand_stage(
        n_vars=2,
        objective=np.array([-1.0, -0.5]),
        integrality=np.array([1, 0]),
        bounds_lb=np.array([0.0, 0.0]),
        bounds_ub=np.array([1.0, 2.0]),
        matrix_csr_rows=[[(0, 1.0), (1, 1.0)]],
        constraints_lb=np.array([-np.inf]),
        constraints_ub=np.array([2.0]),
    )
    session = HighsCoverageSession(stage)
    mapping = session.loaded_integrality_kinds()
    assert mapping[0] == "integer"
    assert mapping[1] == "continuous"
    result = session.solve()
    assert result.model_status == "optimal"
    assert abs(result.column_values[0] - 1.0) <= _FEAS_TOL
    assert abs(result.column_values[1] - 1.0) <= _FEAS_TOL


def test_finite_and_infinite_bounds() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession

    stage = _hand_stage(
        n_vars=2,
        objective=np.array([1.0, 1.0]),
        integrality=np.array([0, 0]),
        bounds_lb=np.array([0.0, -np.inf]),
        bounds_ub=np.array([np.inf, 5.0]),
        matrix_csr_rows=[[(0, 1.0), (1, 1.0)]],
        constraints_lb=np.array([1.0]),
        constraints_ub=np.array([np.inf]),
    )
    session = HighsCoverageSession(stage)
    result = session.solve()
    assert result.model_status == "optimal"
    assert np.all(np.isfinite(result.column_values))


def test_minimization_and_maximization_objective_signs() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession

    stage = _hand_stage(
        n_vars=1,
        objective=np.array([3.0]),
        integrality=np.array([0]),
        bounds_lb=np.array([1.0]),
        bounds_ub=np.array([4.0]),
        matrix_csr_rows=[],
        constraints_lb=np.array([]),
        constraints_ub=np.array([]),
    )
    # Empty constraint system: hand-build 0-row CSC.
    from scipy.sparse import csc_array

    stage = StageConstraintSet(
        n_vars=1,
        objective=np.array([3.0]),
        integrality=np.array([0]),
        bounds_lb=np.array([1.0]),
        bounds_ub=np.array([4.0]),
        constraints=csc_array((0, 1), dtype=float),
        constraints_lb=np.zeros(0, dtype=float),
        constraints_ub=np.zeros(0, dtype=float),
    )
    min_session = HighsCoverageSession(stage, maximize=False)
    min_result = min_session.solve()
    assert min_result.model_status == "optimal"
    assert abs(min_result.column_values[0] - 1.0) <= _FEAS_TOL
    assert abs(min_result.objective_value - 3.0) <= _FEAS_TOL

    max_session = HighsCoverageSession(stage, maximize=True)
    max_result = max_session.solve()
    assert max_result.model_status == "optimal"
    assert abs(max_result.column_values[0] - 4.0) <= _FEAS_TOL
    assert abs(max_result.objective_value - 12.0) <= _FEAS_TOL


def test_optimal_status_on_tiny_mip() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession

    peers = ("P1", "P2", "P3", "P4", "P5")
    unit = _make_unit("safe", _balanced_volumes(peers), applicable_rules=("5/25",))
    model = _compile([unit], peers)
    result = HighsCoverageSession(model.stage1).solve()
    assert result.model_status == "optimal"
    assert result.mip_gap == 0.0
    assert np.isfinite(result.mip_dual_bound)
    assert result.max_primal_infeasibility <= _FEAS_TOL
    assert result.max_integrality_violation <= _FEAS_TOL


def test_infeasible_status() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession

    stage = _hand_stage(
        n_vars=1,
        objective=np.array([1.0]),
        integrality=np.array([1]),
        bounds_lb=np.array([0.0]),
        bounds_ub=np.array([1.0]),
        matrix_csr_rows=[[(0, 1.0)]],
        constraints_lb=np.array([2.0]),
        constraints_ub=np.array([3.0]),
    )
    result = HighsCoverageSession(stage).solve()
    assert result.model_status == "infeasible"


def test_time_limit_status_with_tiny_limit() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession

    # Small but nontrivial binary knapsack that needs search under a tiny limit.
    n = 40
    costs = np.ones(n, dtype=float)
    stage = _hand_stage(
        n_vars=n,
        objective=-costs,
        integrality=np.ones(n, dtype=int),
        bounds_lb=np.zeros(n, dtype=float),
        bounds_ub=np.ones(n, dtype=float),
        matrix_csr_rows=[[(i, float(i + 1)) for i in range(n)]],
        constraints_lb=np.array([-np.inf]),
        constraints_ub=np.array([float(sum(range(1, n + 1)) // 2)]),
    )
    result = HighsCoverageSession(stage, time_limit=1e-9).solve()
    # Extremely tight limit should not prove optimality; accept time_limit or
    # another fail-closed non-optimal state if the solver finishes instantly.
    assert result.model_status != "optimal"
    assert result.model_status in {
        "time_limit",
        "limit_reached",
        "iteration_limit",
        "solver_error",
    }


@pytest.mark.parametrize(
    ("status_name", "expected_state"),
    [
        ("kIterationLimit", "iteration_limit"),
        ("kInterrupt", "solver_error"),
        ("kHighsInterrupt", "solver_error"),
        ("kUnknown", "solver_error"),
        ("kSolveError", "solver_error"),
        ("kMemoryLimit", "limit_reached"),
        ("kSolutionLimit", "limit_reached"),
        ("kObjectiveBound", "limit_reached"),
        ("kUnbounded", "unbounded"),
        ("kUnboundedOrInfeasible", "solver_error"),
    ],
)
def test_mapped_fail_closed_statuses(status_name: str, expected_state: str) -> None:
    from highspy import HighsModelStatus

    from core.privacy_coverage_highs import map_highs_model_status

    status = getattr(HighsModelStatus, status_name)
    assert map_highs_model_status(status) == expected_state


def test_missing_and_nonfinite_proof_fields_fail_closed() -> None:
    from core.privacy_coverage_highs import apply_proof_contract

    base = {
        "raw_model_status": "kOptimal",
        "mapped_status": "optimal",
        "objective_value": 1.0,
        "mip_primal_bound": 1.0,
        "mip_dual_bound": 1.0,
        "mip_gap": 0.0,
        "max_primal_infeasibility": 0.0,
        "max_integrality_violation": 0.0,
    }
    assert apply_proof_contract(**base) == "optimal"

    assert (
        apply_proof_contract(**{**base, "mip_dual_bound": float("nan")})
        == "limit_reached"
    )
    assert (
        apply_proof_contract(**{**base, "mip_gap": float("inf")}) == "limit_reached"
    )
    assert apply_proof_contract(**{**base, "objective_value": None}) == "limit_reached"
    assert apply_proof_contract(**{**base, "mip_primal_bound": None}) == "limit_reached"


def test_nonzero_relative_gap_fails_closed() -> None:
    from core.privacy_coverage_highs import apply_proof_contract

    assert (
        apply_proof_contract(
            raw_model_status="kOptimal",
            mapped_status="optimal",
            objective_value=10.0,
            mip_primal_bound=10.0,
            mip_dual_bound=9.0,
            mip_gap=0.1,
            max_primal_infeasibility=0.0,
            max_integrality_violation=0.0,
        )
        == "limit_reached"
    )


def test_nonzero_absolute_objective_difference_fails_closed() -> None:
    from core.privacy_coverage_highs import apply_proof_contract

    assert (
        apply_proof_contract(
            raw_model_status="kOptimal",
            mapped_status="optimal",
            objective_value=10.0,
            mip_primal_bound=10.0,
            mip_dual_bound=9.5,
            mip_gap=0.0,
            max_primal_infeasibility=0.0,
            max_integrality_violation=0.0,
        )
        == "limit_reached"
    )


def test_primal_and_integrality_violations_fail_closed() -> None:
    from core.privacy_coverage_highs import apply_proof_contract

    assert (
        apply_proof_contract(
            raw_model_status="kOptimal",
            mapped_status="optimal",
            objective_value=1.0,
            mip_primal_bound=1.0,
            mip_dual_bound=1.0,
            mip_gap=0.0,
            max_primal_infeasibility=_FEAS_TOL + 1e-9,
            max_integrality_violation=0.0,
        )
        == "limit_reached"
    )
    assert (
        apply_proof_contract(
            raw_model_status="kOptimal",
            mapped_status="optimal",
            objective_value=1.0,
            mip_primal_bound=1.0,
            mip_dual_bound=1.0,
            mip_gap=0.0,
            max_primal_infeasibility=0.0,
            max_integrality_violation=_FEAS_TOL + 1e-9,
        )
        == "limit_reached"
    )


def test_all_unproven_states_fail_closed_never_optimal() -> None:
    from highspy import HighsModelStatus

    from core.privacy_coverage_highs import apply_proof_contract, map_highs_model_status

    for _name, status in HighsModelStatus.__members__.items():
        mapped = map_highs_model_status(status)
        if status.name == "kOptimal":
            continue
        # Non-optimal raw statuses must never become optimal via the contract.
        final = apply_proof_contract(
            raw_model_status=status.name,
            mapped_status=mapped,
            objective_value=1.0,
            mip_primal_bound=1.0,
            mip_dual_bound=1.0,
            mip_gap=0.0,
            max_primal_infeasibility=0.0,
            max_integrality_violation=0.0,
        )
        assert final != "optimal"
        assert final == mapped


def test_progress_events_capture_safe_numeric_fields_only() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession

    peers = ("P1", "P2", "P3", "P4", "P5", "P6")
    unit = _make_unit("safe", _balanced_volumes(peers), applicable_rules=("5/25",))
    model = _compile([unit], peers)
    session = HighsCoverageSession(model.stage1)
    session.solve()
    for event in session.progress_events:
        assert set(event.__dataclass_fields__) == {
            "elapsed_seconds",
            "node_count",
            "primal_bound",
            "dual_bound",
            "mip_gap",
        }
        assert np.isfinite(event.elapsed_seconds)
        assert isinstance(event.node_count, int)


# ---------------------------------------------------------------------------
# Step 2 / Step 5: complete neutral MIP start
# ---------------------------------------------------------------------------


def test_neutral_start_merchant_and_non_merchant_rule_sets() -> None:
    from core.privacy_coverage_highs import build_neutral_mip_start

    peers = ("P1", "P2", "P3", "P4", "P5", "P6")
    volumes = _balanced_volumes(peers)
    non_merchant = _make_unit("nm", volumes, applicable_rules=("5/25", "6/30"))
    merchant = _make_unit("m", volumes, applicable_rules=("4/35",))
    model = _compile(
        [non_merchant, merchant],
        peers,
        enable_rule_dominance=False,
    )
    unit_data = [_canonicalize_unit(u, peers) for u in (non_merchant, merchant)]
    start = build_neutral_mip_start(model, unit_data)
    assert start.shape == (model.stage1.n_vars,)
    assert np.all(np.isfinite(start))
    assert start[model.r_index["nm"]] == 1.0
    assert start[model.r_index["m"]] == 1.0


def test_neutral_start_covers_each_secondary_witness_tier() -> None:
    from core.privacy_coverage_highs import build_neutral_mip_start

    # 10/40 requires 10 participants; equal shares keep both secondary tiers
    # uncertain under [0.5, 2] weights so z variables exist for each tier.
    peers = tuple(f"P{i}" for i in range(1, 11))
    volumes = _balanced_volumes(peers)
    unit = _make_unit("u", volumes, applicable_rules=("10/40",))
    model = _compile([unit], peers, enable_rule_dominance=False)
    plan = next(p for p in model._unit_plans if p["key"] == "u")
    assert "10/40" in plan["active_rules"]
    tiers = plan["rule_plans"]["10/40"]["tiers"]
    assert len(tiers) >= 2
    tier_indices = {int(tier["tier_index"]) for tier in tiers}
    assert tier_indices == {0, 1}
    start = build_neutral_mip_start(model, [_canonicalize_unit(unit, peers)])
    assert start.shape == (model.stage1.n_vars,)
    seen_tiers = {key[3] for key in model.z_index}
    assert seen_tiers == {0, 1}
    for _key, idx in model.z_index.items():
        assert start[idx] in (0.0, 1.0)


def test_neutral_start_citi_overlay() -> None:
    from core.privacy_coverage_highs import build_neutral_mip_start

    peers = ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "CitiPeer")
    # Citi under 25% at neutral weights; unit otherwise safe under 5/25.
    volumes = {
        "Alpha": 18.0,
        "Beta": 18.0,
        "Gamma": 18.0,
        "Delta": 18.0,
        "Epsilon": 18.0,
        "CitiPeer": 10.0,
    }
    unit = _make_unit(
        "citi_unit",
        volumes,
        applicable_rules=("5/25",),
        overlays=(CITIBANK_OVERLAY_NAME,),
    )
    model = _compile(
        [unit],
        peers,
        citibank_entity_name="CitiPeer",
        enable_rule_dominance=False,
    )
    start = build_neutral_mip_start(model, [_canonicalize_unit(unit, peers)])
    assert start[model.r_index["citi_unit"]] == 1.0

    # Citi over 25% forces r=0 for a feasible start.
    hot_volumes = {
        "Alpha": 14.0,
        "Beta": 14.0,
        "Gamma": 14.0,
        "Delta": 14.0,
        "Epsilon": 14.0,
        "CitiPeer": 30.0,
    }
    hot_unit = _make_unit(
        "hot",
        hot_volumes,
        applicable_rules=("5/25",),
        overlays=(CITIBANK_OVERLAY_NAME,),
    )
    hot_model = _compile(
        [hot_unit],
        peers,
        citibank_entity_name="CitiPeer",
        enable_rule_dominance=False,
    )
    hot_start = build_neutral_mip_start(
        hot_model, [_canonicalize_unit(hot_unit, peers)]
    )
    assert hot_start[hot_model.r_index["hot"]] == 0.0


def test_neutral_start_always_true_and_impossible_witnesses() -> None:
    from core.privacy_coverage_highs import build_neutral_mip_start

    # Fixed weights collapse interval classification to the neutral point so a
    # high Dom share is always-true and a tiny peer is impossible, while the
    # 40% primary cap still always-passes. Ten peers satisfy 10/40 min_entities.
    # Dom/A clear the 20% tier; Dom/A/B clear the 10% tier; Tiny is impossible.
    peers = ("Dom", "Tiny", "A", "B", "C", "D", "E", "F", "G", "H")
    rest = 40.0 / 6.0
    volumes = {
        "Dom": 25.0,
        "A": 22.0,
        "B": 12.0,
        "Tiny": 1.0,
        **{name: rest for name in ("C", "D", "E", "F", "G", "H")},
    }
    fractions = normalized_shares(volumes, peers)
    fixed = 1.0
    assert (
        classify_secondary_witness(
            fractions, "Dom", effective_threshold(10.0), fixed, fixed
        )
        is WitnessClass.ALWAYS_TRUE
    )
    assert (
        classify_secondary_witness(
            fractions, "Tiny", effective_threshold(20.0), fixed, fixed
        )
        is WitnessClass.IMPOSSIBLE
    )
    unit = _make_unit("w", volumes, applicable_rules=("10/40",))
    model = _compile(
        [unit],
        peers,
        enable_rule_dominance=False,
        min_weight=fixed,
        max_weight=fixed,
    )
    assert model.statistics.always_true_witness_count >= 1
    assert model.statistics.impossible_witness_count >= 1
    # Always-true Dom at the 10% tier and impossible Tiny at the 20% tier
    # must not allocate z variables.
    for _unit_key, _metric, _rule, tier_i, peer in model.z_index:
        assert not (peer == "Dom" and tier_i == 1)
        assert not (peer == "Tiny" and tier_i == 0)
    start = build_neutral_mip_start(model, [_canonicalize_unit(unit, peers)])
    assert start.shape == (model.stage1.n_vars,)
    assert np.all(np.isfinite(start))


@pytest.mark.parametrize(
    ("threshold", "rule_name", "volumes"),
    [
        # 10/40: need 2 peers >= 20% and 3 >= 10%. Focus sits exactly on each tier.
        (
            20.0,
            "10/40",
            {
                "Focus": 20.0,
                "P2": 20.0,
                "P3": 10.0,
                "P4": 10.0,
                "P5": 8.0,
                "P6": 8.0,
                "P7": 8.0,
                "P8": 6.0,
                "P9": 5.0,
                "P10": 5.0,
            },
        ),
        (
            10.0,
            "10/40",
            {
                "Focus": 10.0,
                "P2": 20.0,
                "P3": 20.0,
                "P4": 10.0,
                "P5": 8.0,
                "P6": 8.0,
                "P7": 8.0,
                "P8": 6.0,
                "P9": 5.0,
                "P10": 5.0,
            },
        ),
        # 7/35: need 2 peers >= 15% and 3 >= 8%.
        (
            15.0,
            "7/35",
            {
                "Focus": 15.0,
                "P2": 15.0,
                "P3": 15.0,
                "P4": 14.0,
                "P5": 14.0,
                "P6": 14.0,
                "P7": 13.0,
            },
        ),
        (
            8.0,
            "7/35",
            {
                "Focus": 8.0,
                "P2": 15.0,
                "P3": 15.0,
                "P4": 15.0,
                "P5": 16.0,
                "P6": 16.0,
                "P7": 15.0,
            },
        ),
    ],
)
def test_neutral_start_uncertain_witness_at_threshold_boundary(
    threshold: float,
    rule_name: str,
    volumes: Mapping[str, float],
) -> None:
    from core.privacy_coverage_highs import build_neutral_mip_start
    from core.privacy_coverage_solver import weighted_shares

    peers = tuple(volumes)
    weights = {peer: 1.0 for peer in peers}
    shares = weighted_shares(volumes, weights)
    assert abs(shares["Focus"] - threshold) <= 1e-9
    unit = _make_unit("bound", volumes, applicable_rules=(rule_name,))
    # Disable structural witness classification so Focus remains an uncertain z
    # variable even when wide weight bounds would otherwise prune it.
    model = _compile(
        [unit],
        peers,
        enable_rule_dominance=False,
        enable_structural_presolve=False,
    )
    start = build_neutral_mip_start(model, [_canonicalize_unit(unit, peers)])
    assert start[model.r_index["bound"]] == 1.0
    meets = shares["Focus"] + COMPARISON_EPSILON >= threshold
    plan = next(item for item in model._unit_plans if item["key"] == "bound")
    tier_index = next(
        int(tier["tier_index"])
        for tier in plan["rule_plans"][rule_name]["tiers"]
        if float(tier["threshold"]) == float(threshold)
    )
    focus_z = [
        (key, idx)
        for key, idx in model.z_index.items()
        if key[0] == "bound" and key[4] == "Focus" and key[3] == tier_index
    ]
    assert focus_z, "expected an uncertain Focus witness at the boundary tier"
    for _key, idx in focus_z:
        assert start[idx] == (1.0 if meets else 0.0)


def test_neutral_start_no_authorizing_rule_sets_r_zero() -> None:
    from core.privacy_coverage_highs import build_neutral_mip_start

    peers = ("P1", "P2", "P3", "P4", "P5")
    volumes = {"P1": 90.0, "P2": 2.5, "P3": 2.5, "P4": 2.5, "P5": 2.5}
    unit = _make_unit("blocked", volumes, applicable_rules=("5/25",))
    model = _compile([unit], peers, enable_rule_dominance=False)
    start = build_neutral_mip_start(model, [_canonicalize_unit(unit, peers)])
    assert start[model.r_index["blocked"]] == 0.0
    for (_uk, _rule), idx in model.y_index.items():
        assert start[idx] == 0.0


def test_neutral_start_two_passing_rules_selects_canonical() -> None:
    from core.privacy_coverage_highs import build_neutral_mip_start

    peers = ("P1", "P2", "P3", "P4", "P5", "P6")
    volumes = _balanced_volumes(peers)
    unit = _make_unit("two", volumes, applicable_rules=("5/25", "6/30"))
    model = _compile([unit], peers, enable_rule_dominance=False)
    plan = next(p for p in model._unit_plans if p["key"] == "two")
    active = list(plan["active_rules"])
    assert "5/25" in active and "6/30" in active
    start = build_neutral_mip_start(model, [_canonicalize_unit(unit, peers)])
    assert start[model.r_index["two"]] == 1.0
    # Canonical first among active rules in model order.
    chosen = active[0]
    for rule_name in active:
        y = start[model.y_index[("two", rule_name)]]
        assert y == (1.0 if rule_name == chosen else 0.0)


def test_neutral_start_complete_vector_and_zero_row_violations() -> None:
    from core.privacy_coverage_highs import (
        NeutralMipStartError,
        build_neutral_mip_start,
        validate_start_against_stage,
    )

    peers = ("P1", "P2", "P3", "P4", "P5")
    unit = _make_unit("u", _balanced_volumes(peers), applicable_rules=("5/25", "7/35"))
    model = _compile([unit], peers, enable_rule_dominance=False)
    unit_data = [_canonicalize_unit(unit, peers)]
    start = build_neutral_mip_start(model, unit_data)
    assert start.shape == (model.stage1.n_vars,)
    assert not np.isnan(start).any()
    validate_start_against_stage(model.stage1, start)
    # Tampering any family must be rejected.
    families = {
        "w": list(model.w_index.values())[:1],
        "b": list(model.b_index.values())[:1],
        "r": list(model.r_index.values())[:1],
        "y": list(model.y_index.values())[:1],
        "z": list(model.z_index.values())[:1] if model.z_index else [],
    }
    for family, indices in families.items():
        if not indices:
            continue
        tampered = start.copy()
        idx = indices[0]
        if family in {"w", "b"}:
            tampered[idx] = model.max_weight + 1.0
        else:
            tampered[idx] = 1.0 - tampered[idx]
        with pytest.raises(NeutralMipStartError):
            validate_start_against_stage(model.stage1, tampered)


def test_highs_accepts_complete_start_and_matches_primal_bound() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession, build_neutral_mip_start

    peers = ("P1", "P2", "P3", "P4", "P5")
    unit = _make_unit("u", _balanced_volumes(peers), applicable_rules=("5/25",))
    model = _compile([unit], peers)
    unit_data = [_canonicalize_unit(unit, peers)]
    start = build_neutral_mip_start(model, unit_data)
    start_objective = float(model.stage1.objective @ start)

    session = HighsCoverageSession(model.stage1)
    session.set_complete_start(start)
    result = session.solve()
    assert result.model_status == "optimal"
    # Start release count is a lower bound on the proven maximum.
    start_release = float(start[model.r_index["u"]])
    proven_release = -float(result.objective_value)
    assert proven_release + _FEAS_TOL >= start_release
    assert result.mip_primal_bound <= start_objective + _FEAS_TOL or (
        # HiGHS reports primal bound in the model sense; for minimize of -r,
        # better (more negative) objectives are smaller.
        result.mip_primal_bound <= start_objective + _FEAS_TOL
    )
    # Incumbent objective must be at least as good as the start (min sense).
    assert result.objective_value <= start_objective + _FEAS_TOL


def test_repeated_runs_identical_first_incumbent_value() -> None:
    from core.privacy_coverage_highs import HighsCoverageSession, build_neutral_mip_start

    peers = ("P1", "P2", "P3", "P4", "P5", "P6")
    units = [
        _make_unit("a", _balanced_volumes(peers), applicable_rules=("5/25",)),
        _make_unit(
            "b",
            {"P1": 40.0, "P2": 15.0, "P3": 15.0, "P4": 10.0, "P5": 10.0, "P6": 10.0},
            applicable_rules=("6/30",),
        ),
    ]
    model = _compile(units, peers, enable_rule_dominance=False)
    unit_data = [_canonicalize_unit(u, peers) for u in units]
    start = build_neutral_mip_start(model, unit_data)

    incumbent_values = []
    for _ in range(2):
        session = HighsCoverageSession(model.stage1)
        session.set_complete_start(start)
        result = session.solve()
        assert result.model_status == "optimal"
        incumbent_values.append(float(result.objective_value))
    assert incumbent_values[0] == incumbent_values[1]


def test_set_complete_start_rejects_invalid_vector() -> None:
    from core.privacy_coverage_highs import (
        HighsCoverageSession,
        NeutralMipStartError,
        build_neutral_mip_start,
    )

    peers = ("P1", "P2", "P3", "P4", "P5")
    unit = _make_unit("u", _balanced_volumes(peers), applicable_rules=("5/25",))
    model = _compile([unit], peers)
    start = build_neutral_mip_start(model, [_canonicalize_unit(unit, peers)])
    bad = start.copy()
    bad[model.r_index["u"]] = 1.0 - bad[model.r_index["u"]]
    # Flip r without adjusting y — row violation.
    if abs(bad[model.r_index["u"]] - start[model.r_index["u"]]) < 1e-15:
        bad[list(model.w_index.values())[0]] = model.max_weight + 5.0
    session = HighsCoverageSession(model.stage1)
    with pytest.raises(NeutralMipStartError):
        session.set_complete_start(bad)


def test_mock_solver_error_status_path() -> None:
    from highspy import HighsModelStatus, HighsStatus

    from core.privacy_coverage_highs import HighsCoverageSession

    peers = ("P1", "P2", "P3", "P4", "P5")
    unit = _make_unit("u", _balanced_volumes(peers), applicable_rules=("5/25",))
    model = _compile([unit], peers)
    session = HighsCoverageSession(model.stage1)

    session._highs.run = MagicMock(return_value=HighsStatus.kError)  # noqa: SLF001
    result = session.solve()
    assert result.model_status == "solver_error"

    session2 = HighsCoverageSession(model.stage1)
    session2._highs.run = MagicMock(return_value=HighsStatus.kOk)  # noqa: SLF001
    session2._highs.getModelStatus = MagicMock(  # noqa: SLF001
        return_value=HighsModelStatus.kUnknown
    )
    info = MagicMock()
    info.objective_function_value = 0.0
    info.mip_dual_bound = 0.0
    info.mip_gap = 0.0
    info.max_primal_infeasibility = 0.0
    info.max_integrality_violation = 0.0
    info.mip_node_count = 0
    info.primal_solution_status = 0
    info.primal_dual_integral = 0.0
    # Provide mip_primal_bound via a side channel used by the adapter if present.
    session2._highs.getInfo = MagicMock(return_value=info)  # noqa: SLF001
    sol = MagicMock()
    sol.col_value = np.zeros(model.stage1.n_vars)
    session2._highs.getSolution = MagicMock(return_value=sol)  # noqa: SLF001
    session2._highs.getRunTime = MagicMock(return_value=0.0)  # noqa: SLF001
    result2 = session2.solve()
    assert result2.model_status == "solver_error"
