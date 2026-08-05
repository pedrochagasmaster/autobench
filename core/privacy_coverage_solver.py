"""Maximum Safe Coverage MILP solver using ``scipy.optimize.milp``.

Owns the staged mixed-integer solve for
``PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE``. Sparse model compilation lives in
``core.privacy_coverage_model``; this Module keeps the public
``optimize_safe_coverage`` contract and proof / fail-closed behavior.

The independent verifier remains a separate Module and must recalculate every
policy check from the original inputs and the final global weight vector.

This Module must not authorize a client sink. It produces a trusted internal
``SafeCoverageResult`` with ``verifier_result='not_run'`` until the verifier
attests the release.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp

from core.canonical_order import canonical_key, canonical_order
from core.contracts import (
    APPROVED_PRIVACY_RULE_NAMES,
    PrivacyReleaseMode,
    PublicationUnit,
    SafeCoverageResult,
)
from core.privacy_coverage import CITIBANK_OVERLAY_NAME
from core.privacy_coverage_model import (
    CoverageModel,
    CoverageRuleView,
    ReleaseBlock,
    StageConstraintSet,
    compile_coverage_model,
)
from core.privacy_rules import evaluate_rule, privacy_rule_from_config

__all__ = [
    "SafeCoverageSolverError",
    "optimize_safe_coverage",
    "weighted_shares",
]

_SOLVER_NAME = "scipy.optimize.milp"
_STATE_OPTIMAL = "optimal"
_STATE_INFEASIBLE = "infeasible"
_STATE_UNBOUNDED = "unbounded"
_STATE_TIME_LIMIT = "time_limit"
_STATE_ITERATION_LIMIT = "iteration_limit"
_STATE_ERROR = "solver_error"
_STATE_UNPROVEN = "unproven_maximum"

# Stage 2/3 lexicographic slack. Chosen from a single documented solver
# feasibility scale (not from a privacy epsilon). Wide enough that HiGHS
# feasibility tolerances do not accidentally exclude a valid tied solution
# in later stages, tight enough to preserve lexicographic priority.
_LEX_TOLERANCE_ABS = 1e-6
_LEX_TOLERANCE_REL = 1e-6

# Read-back tolerance for extracting integer values from a HiGHS x vector.
_INTEGRALITY_READBACK_TOLERANCE = 1e-6

# Only allow-listed keys are forwarded to ``milp(options=...)``. The proof
# contract still requires an exact zero gap, so a positive requested gap
# cannot weaken acceptance downstream.
_ALLOWED_SOLVER_OPTIONS = frozenset(
    {"disp", "presolve", "time_limit", "node_limit", "mip_rel_gap"}
)


class SafeCoverageSolverError(ValueError):
    """Raised when solver inputs are structurally invalid.

    This is a fail-closed input contract error, not a solver-runtime failure.
    Runtime failures (infeasible, timeout, malformed HiGHS output) are reported
    on the returned ``SafeCoverageResult.solver_state``.
    """


def _build_rule_view(
    name: str,
    rule_configs: Mapping[str, Mapping[str, Any]],
) -> CoverageRuleView:
    if name not in APPROVED_PRIVACY_RULE_NAMES:
        raise SafeCoverageSolverError(f"unknown privacy rule: {name!r}")
    cfg = rule_configs.get(name)
    resolved = privacy_rule_from_config(
        name, dict(cfg) if cfg is not None else None
    )
    tier_items = sorted(
        resolved.secondary_requirements.values(),
        key=lambda item: -float(item[1]),
    )
    tiers = tuple(
        (int(count), float(threshold)) for count, threshold in tier_items
    )
    return CoverageRuleView(
        name=resolved.name,
        min_entities=int(resolved.min_entities),
        max_concentration=float(resolved.max_concentration),
        secondary_tiers=tiers,
    )


def weighted_shares(
    peer_volumes: Mapping[str, float],
    weights: Mapping[str, float],
) -> Dict[str, float]:
    """Return positive-volume peer shares as percentages under ``weights``.

    Peers with zero source volume are dropped, mirroring the structural
    participant count used by ``evaluate_rule``. Missing peers in ``weights``
    default to a neutral multiplier of ``1.0``.
    """
    filtered: List[Tuple[str, float]] = []
    for peer, volume in peer_volumes.items():
        raw = float(volume)
        if raw <= 0.0:
            continue
        multiplier = float(weights.get(peer, 1.0))
        filtered.append((peer, raw * multiplier))
    total = sum(value for _peer, value in filtered)
    if total <= 0.0:
        return {peer: 0.0 for peer, _value in filtered}
    return {peer: 100.0 * value / total for peer, value in filtered}


def _canonicalize_metric_records(
    unit: PublicationUnit,
    peers: Sequence[str],
) -> List[Dict[str, Any]]:
    seen_metric_names: set = set()
    records: List[Dict[str, Any]] = []
    for record in unit.metric_records:
        metric_name_raw = record.get("metric")
        if not metric_name_raw:
            raise SafeCoverageSolverError(
                f"unit {unit.internal_key!r} has an unnamed governed metric"
            )
        metric_name = str(metric_name_raw)
        if metric_name in seen_metric_names:
            raise SafeCoverageSolverError(
                f"unit {unit.internal_key!r} has duplicate metric "
                f"{metric_name!r}"
            )
        seen_metric_names.add(metric_name)
        raw_volumes = record.get("peer_volumes", {})
        aligned: Dict[str, float] = {}
        for peer in peers:
            value = float(raw_volumes.get(peer, 0.0))
            if not math.isfinite(value) or value < 0.0:
                raise SafeCoverageSolverError(
                    f"unit {unit.internal_key!r} metric {metric_name!r} has "
                    "non-finite or negative peer volume"
                )
            aligned[peer] = value
        total = float(sum(aligned.values()))
        if total <= 0.0:
            raise SafeCoverageSolverError(
                f"unit {unit.internal_key!r} metric {metric_name!r} has zero "
                "total volume; a zero-total metric cannot be authorized"
            )
        positive_peers = tuple(peer for peer in peers if aligned[peer] > 0.0)
        records.append(
            {
                "metric": metric_name,
                "aligned_volumes": aligned,
                "total": total,
                "positive_peers": positive_peers,
            }
        )
    records.sort(key=lambda item: canonical_key(item["metric"]))
    return records


def _sanitize_solver_options(
    options: Optional[Mapping[str, Any]],
) -> Optional[Dict[str, Any]]:
    if options is None:
        return None
    unknown = set(options) - _ALLOWED_SOLVER_OPTIONS
    if unknown:
        raise SafeCoverageSolverError(
            f"solver_options contains unsupported keys: {sorted(unknown)!r}"
        )
    return {str(key): options[key] for key in options}


def _certifying_options(
    sanitized: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """Caller time/node limits pass through; relative gap is forced to zero."""
    options = dict(sanitized) if sanitized is not None else {}
    options["mip_rel_gap"] = 0
    return options


def _classify_status(status_code: int) -> str:
    if status_code == 2:
        return _STATE_INFEASIBLE
    if status_code == 3:
        return _STATE_UNBOUNDED
    if status_code == 4:
        return _STATE_ERROR
    if status_code == 5:
        return _STATE_TIME_LIMIT
    if status_code == 1:
        return _STATE_ITERATION_LIMIT
    return _STATE_ERROR


def _release_mask_digest(sorted_keys: Sequence[str], released_keys: Iterable[str]) -> str:
    released_set = set(released_keys)
    mask_payload = [
        {"key": key, "released": key in released_set}
        for key in sorted_keys
    ]
    encoded = json.dumps(mask_payload, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _empty_release_result(
    *,
    universe: Tuple[PublicationUnit, ...],
    peers: Sequence[str],
    solver_state: str,
    mip_dual_bound: float,
    mip_gap: float,
    input_digest: str,
    configuration_digest: str,
    policy_version: str,
    policy_source: str,
    rule_set_digest: str,
    candidate_universe_digest: str,
) -> SafeCoverageResult:
    """Return a valid partition with zero releases for failure or K=0 paths."""
    keys = tuple(unit.internal_key for unit in universe)
    return SafeCoverageResult(
        release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
        global_weights={peer: 1.0 for peer in peers},
        candidate_universe=universe,
        release_set=(),
        suppression_set=keys,
        authorizing_rules={},
        primary_objective_value=0,
        later_objective_values=(0.0, 0.0),
        solver_state=solver_state,
        mip_dual_bound=float(mip_dual_bound),
        mip_gap=float(mip_gap),
        solver_name=_SOLVER_NAME,
        solver_version=str(scipy.__version__),
        input_digest=input_digest,
        configuration_digest=configuration_digest,
        policy_version=policy_version,
        policy_source=policy_source,
        rule_set_digest=rule_set_digest,
        candidate_universe_digest=candidate_universe_digest,
        release_mask_digest=_release_mask_digest(keys, ()),
        verifier_result="not_run",
    )


def _solve_stage(
    stage: StageConstraintSet,
    *,
    objective: np.ndarray,
    options: Mapping[str, Any],
    bounds_lb: Optional[np.ndarray] = None,
    bounds_ub: Optional[np.ndarray] = None,
    constraints_lb: Optional[np.ndarray] = None,
    constraints_ub: Optional[np.ndarray] = None,
) -> Any:
    """Run one ``milp`` call with a single CSC ``LinearConstraint``."""
    lb = stage.bounds_lb if bounds_lb is None else bounds_lb
    ub = stage.bounds_ub if bounds_ub is None else bounds_ub
    row_lb = stage.constraints_lb if constraints_lb is None else constraints_lb
    row_ub = stage.constraints_ub if constraints_ub is None else constraints_ub
    constraint = LinearConstraint(stage.constraints, row_lb, row_ub)
    return milp(
        c=objective,
        integrality=stage.integrality,
        bounds=Bounds(np.asarray(lb, dtype=float), np.asarray(ub, dtype=float)),
        constraints=constraint,
        options=dict(options),
    )


def _validate_result(res: Any, n_vars: int) -> Optional[str]:
    if getattr(res, "status", None) is None:
        return _STATE_ERROR
    if int(res.status) != 0 or not bool(getattr(res, "success", False)):
        return _classify_status(int(res.status))
    x_vec = getattr(res, "x", None)
    if x_vec is None:
        return _STATE_ERROR
    arr = np.asarray(x_vec, dtype=float)
    if arr.shape != (n_vars,) or not np.all(np.isfinite(arr)):
        return _STATE_ERROR
    fun_val = getattr(res, "fun", None)
    if fun_val is None or not math.isfinite(float(fun_val)):
        return _STATE_ERROR
    return None


def _extract_binary(x_vec: np.ndarray, idx: int) -> int:
    value = float(x_vec[idx])
    if not math.isfinite(value):
        raise RuntimeError("non-finite binary component in solver output")
    rounded = round(value)
    if abs(value - rounded) > _INTEGRALITY_READBACK_TOLERANCE:
        raise RuntimeError("non-integer binary component in solver output")
    if rounded not in (0, 1):
        raise RuntimeError("binary variable outside {0,1} in solver output")
    return int(rounded)


def _stage1_proof(
    result: Any,
    sum_r: float,
) -> Tuple[bool, int, float, float]:
    """Return (proven, K, dual_bound_normalized, mip_gap)."""
    k_rounded = int(round(sum_r))
    proven = abs(sum_r - k_rounded) <= _INTEGRALITY_READBACK_TOLERANCE
    dual_bound_normalized = 0.0
    raw_dual = getattr(result, "mip_dual_bound", None)
    if raw_dual is None:
        proven = False
    else:
        try:
            dual_bound_normalized = -float(raw_dual)
        except (TypeError, ValueError):
            proven = False
    if not math.isfinite(dual_bound_normalized):
        proven = False
        dual_bound_normalized = 0.0

    mip_gap_value = 0.0
    raw_gap = getattr(result, "mip_gap", None)
    if raw_gap is None:
        proven = False
    else:
        try:
            mip_gap_value = float(raw_gap)
        except (TypeError, ValueError):
            proven = False
    if not math.isfinite(mip_gap_value) or mip_gap_value < 0.0:
        proven = False
        mip_gap_value = 0.0
    if mip_gap_value != 0.0:
        proven = False
    if round(dual_bound_normalized) != k_rounded:
        proven = False
    return proven, k_rounded, dual_bound_normalized, mip_gap_value


def _lex_tolerance(optimum: float) -> float:
    return max(_LEX_TOLERANCE_ABS, _LEX_TOLERANCE_REL * max(1.0, abs(optimum)))


def _select_authorizing_rules(
    unit_data: Sequence[Mapping[str, Any]],
    released_keys: Sequence[str],
    weights: Mapping[str, float],
    rule_configs: Mapping[str, Mapping[str, Any]],
) -> Tuple[Dict[str, str], List[str]]:
    """Return (authorizing_rules, units_missing_authorizer).

    Uses the first canonical applicable rule that passes every metric under
    ``evaluate_rule`` / ``weighted_shares``.
    """
    released = set(released_keys)
    authorizing: Dict[str, str] = {}
    missing: List[str] = []
    for unit in unit_data:
        key = str(unit["key"])
        if key not in released:
            continue
        selected: Optional[str] = None
        for rule_name in unit["rules"]:
            cfg = rule_configs.get(rule_name)
            rule_config = dict(cfg) if cfg is not None else None
            passes = True
            for metric in unit["metrics"]:
                shares = weighted_shares(metric["aligned_volumes"], weights)
                evaluation = evaluate_rule(
                    rule_name,
                    list(shares.values()),
                    rule_config=rule_config,
                )
                if not evaluation.strict_passed:
                    passes = False
                    break
            if passes:
                selected = str(rule_name)
                break
        if selected is None:
            missing.append(key)
        else:
            authorizing[key] = selected
    return authorizing, missing


def _weights_from_x(
    x_vec: np.ndarray,
    peers: Sequence[str],
    w_index: Mapping[str, int],
    *,
    min_weight: float,
    max_weight: float,
) -> Dict[str, float]:
    weights: Dict[str, float] = {}
    for peer in peers:
        value = float(x_vec[w_index[peer]])
        if not math.isfinite(value):
            value = 1.0
        weights[peer] = max(min_weight, min(max_weight, value))
    return weights


def _release_keys_from_x(
    x_vec: np.ndarray,
    unit_data: Sequence[Mapping[str, Any]],
    r_index: Mapping[str, int],
) -> Tuple[List[str], List[str]]:
    released: List[str] = []
    suppressed: List[str] = []
    for unit in unit_data:
        key = str(unit["key"])
        raw = float(x_vec[r_index[key]])
        rounded = int(round(raw))
        if abs(raw - rounded) > _INTEGRALITY_READBACK_TOLERANCE or rounded not in (0, 1):
            suppressed.append(key)
            continue
        if rounded == 1:
            released.append(key)
        else:
            suppressed.append(key)
    return released, suppressed


def _finalize_result(
    *,
    unit_data: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
    peers: Sequence[str],
    weights: Mapping[str, float],
    released_keys: Sequence[str],
    suppressed_keys: Sequence[str],
    authorizing_rules: Mapping[str, str],
    sorted_universe: Tuple[PublicationUnit, ...],
    solver_state: str,
    mip_dual_bound: float,
    mip_gap: float,
    later_objectives: Tuple[float, float],
    input_digest: str,
    configuration_digest: str,
    policy_version: str,
    policy_source: str,
    rule_set_digest: str,
    candidate_universe_digest: str,
) -> SafeCoverageResult:
    released_sorted = tuple(sorted(released_keys, key=canonical_key))
    suppressed_sorted = tuple(sorted(suppressed_keys, key=canonical_key))

    all_keys = set(released_sorted) | set(suppressed_sorted)
    if all_keys != set(keys) or len(released_sorted) + len(suppressed_sorted) != len(keys):
        canonical_all = set(keys)
        missing = canonical_all - all_keys
        for missing_key in sorted(missing, key=canonical_key):
            suppressed_sorted = suppressed_sorted + (missing_key,)
        released_sorted = tuple(k for k in released_sorted if k in canonical_all)
        solver_state = _STATE_UNPROVEN

    # Drop authorizing rules for units that are no longer released.
    released_set = set(released_sorted)
    authorizing_out = {
        key: rule
        for key, rule in authorizing_rules.items()
        if key in released_set
    }
    if set(authorizing_out) != released_set:
        solver_state = _STATE_UNPROVEN

    primary_objective_value = len(released_sorted)
    if solver_state == _STATE_OPTIMAL and math.isfinite(mip_dual_bound):
        if round(mip_dual_bound) != primary_objective_value:
            solver_state = _STATE_UNPROVEN

    weights_out = {peer: float(weights.get(peer, 1.0)) for peer in peers}
    for peer, value in weights_out.items():
        if not math.isfinite(value):
            weights_out[peer] = 1.0
            solver_state = _STATE_UNPROVEN

    return SafeCoverageResult(
        release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
        global_weights=weights_out,
        candidate_universe=sorted_universe,
        release_set=released_sorted,
        suppression_set=suppressed_sorted,
        authorizing_rules=authorizing_out,
        primary_objective_value=primary_objective_value,
        later_objective_values=tuple(float(v) for v in later_objectives),
        solver_state=solver_state,
        mip_dual_bound=float(mip_dual_bound),
        mip_gap=float(mip_gap),
        solver_name=_SOLVER_NAME,
        solver_version=str(scipy.__version__),
        input_digest=input_digest,
        configuration_digest=configuration_digest,
        policy_version=policy_version,
        policy_source=policy_source,
        rule_set_digest=rule_set_digest,
        candidate_universe_digest=candidate_universe_digest,
        release_mask_digest=_release_mask_digest(keys, released_sorted),
        verifier_result="not_run",
    )


def _finalize_from_partial_x(
    *,
    x_vec: np.ndarray,
    model: CoverageModel,
    unit_data: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
    peers: Sequence[str],
    rule_configs: Mapping[str, Mapping[str, Any]],
    sorted_universe: Tuple[PublicationUnit, ...],
    solver_state: str,
    mip_dual_bound: float,
    mip_gap: float,
    later_objectives: Tuple[float, float],
    input_digest: str,
    configuration_digest: str,
    policy_version: str,
    policy_source: str,
    rule_set_digest: str,
    candidate_universe_digest: str,
) -> SafeCoverageResult:
    weights = _weights_from_x(
        x_vec,
        peers,
        model.w_index,
        min_weight=model.min_weight,
        max_weight=model.max_weight,
    )
    released, suppressed = _release_keys_from_x(x_vec, unit_data, model.r_index)
    authorizing, missing = _select_authorizing_rules(
        unit_data, released, weights, rule_configs
    )
    if missing:
        solver_state = _STATE_UNPROVEN
        for key in missing:
            if key in released:
                released.remove(key)
            if key not in suppressed:
                suppressed.append(key)
            authorizing.pop(key, None)
    return _finalize_result(
        unit_data=unit_data,
        keys=keys,
        peers=peers,
        weights=weights,
        released_keys=released,
        suppressed_keys=suppressed,
        authorizing_rules=authorizing,
        sorted_universe=sorted_universe,
        solver_state=solver_state,
        mip_dual_bound=mip_dual_bound,
        mip_gap=mip_gap,
        later_objectives=later_objectives,
        input_digest=input_digest,
        configuration_digest=configuration_digest,
        policy_version=policy_version,
        policy_source=policy_source,
        rule_set_digest=rule_set_digest,
        candidate_universe_digest=candidate_universe_digest,
    )


def _sync_block_bounds(
    stage: StageConstraintSet,
    block_row_indices: Sequence[int],
    blocks: Sequence[ReleaseBlock],
) -> Tuple[np.ndarray, np.ndarray]:
    row_lb = stage.constraints_lb.copy()
    row_ub = stage.constraints_ub.copy()
    for row_idx, block in zip(block_row_indices, blocks):
        row_lb[row_idx] = float(block.lb)
        row_ub[row_idx] = float(block.ub)
    return row_lb, row_ub


def optimize_safe_coverage(
    candidate_universe: Tuple[PublicationUnit, ...],
    governed_peers: Tuple[str, ...],
    *,
    min_weight: float,
    max_weight: float,
    rule_configs: Mapping[str, Mapping[str, Any]],
    citibank_entity_name: Optional[str],
    input_digest: str,
    configuration_digest: str,
    policy_version: str,
    policy_source: str,
    rule_set_digest: str,
    candidate_universe_digest: str,
    solver_options: Optional[Mapping[str, Any]] = None,
) -> SafeCoverageResult:
    """Solve maximum safe coverage via a 4-stage lexicographic MILP.

    The returned candidate is trusted internal evidence with
    ``verifier_result='not_run'``. The caller must invoke the independent
    verifier before authorizing any client sink.
    """
    if not math.isfinite(min_weight) or min_weight <= 0.0:
        raise SafeCoverageSolverError(
            "min_weight must be a positive finite value"
        )
    if not math.isfinite(max_weight) or max_weight < min_weight:
        raise SafeCoverageSolverError(
            "max_weight must be finite and at least min_weight"
        )
    if min_weight > 1.0 or max_weight < 1.0:
        raise SafeCoverageSolverError(
            "weight bounds must satisfy 0 < min_weight <= 1 <= max_weight"
        )
    if not isinstance(candidate_universe, tuple):
        raise SafeCoverageSolverError("candidate_universe must be a tuple")
    if not candidate_universe:
        raise SafeCoverageSolverError("candidate_universe must not be empty")

    peers = tuple(canonical_order(governed_peers))
    if not peers or len(set(governed_peers)) != len(governed_peers):
        raise SafeCoverageSolverError(
            "governed_peers must be a non-empty sequence of distinct identities"
        )

    sanitized_options = _sanitize_solver_options(solver_options)
    cert_options = _certifying_options(sanitized_options)

    sorted_universe = tuple(
        sorted(
            candidate_universe,
            key=lambda unit: canonical_key(unit.internal_key),
        )
    )
    keys = tuple(unit.internal_key for unit in sorted_universe)
    if len(set(keys)) != len(keys):
        raise SafeCoverageSolverError(
            "candidate_universe contains duplicate internal keys"
        )

    rule_cache: Dict[str, CoverageRuleView] = {}
    unit_data: List[Dict[str, Any]] = []
    for unit in sorted_universe:
        metric_records = _canonicalize_metric_records(unit, peers)
        rules_canonical = tuple(sorted(unit.applicable_rules, key=canonical_key))
        if len(set(rules_canonical)) != len(rules_canonical):
            raise SafeCoverageSolverError(
                f"unit {unit.internal_key!r} has duplicate applicable rules"
            )
        for rule_name in rules_canonical:
            if rule_name not in rule_cache:
                rule_cache[rule_name] = _build_rule_view(rule_name, rule_configs)
        unit_data.append(
            {
                "key": unit.internal_key,
                "metrics": metric_records,
                "rules": rules_canonical,
                "overlays": tuple(unit.mandatory_overlays),
            }
        )

    if any(CITIBANK_OVERLAY_NAME in u["overlays"] for u in unit_data):
        if not citibank_entity_name:
            raise SafeCoverageSolverError(
                "citibank_entity_name is required when a unit carries the "
                "citibank overlay"
            )
        needle = citibank_entity_name.casefold()
        matches = [peer for peer in peers if peer.casefold() == needle]
        if len(matches) != 1:
            raise SafeCoverageSolverError(
                "citibank peer identity must exist exactly once in "
                "governed_peers"
            )

    model = compile_coverage_model(
        unit_data,
        peers,
        min_weight=min_weight,
        max_weight=max_weight,
        rules=rule_cache,
        citibank_entity_name=citibank_entity_name,
        enable_rule_dominance=True,
        enable_structural_presolve=True,
    )

    # ---------------- Stage 1: maximize sum r_u ----------------
    stage1 = model.stage1
    result1 = _solve_stage(stage1, objective=stage1.objective, options=cert_options)
    stage1_failure = _validate_result(result1, stage1.n_vars)
    if stage1_failure is not None:
        return _empty_release_result(
            universe=sorted_universe,
            peers=peers,
            solver_state=stage1_failure,
            mip_dual_bound=0.0,
            mip_gap=0.0,
            input_digest=input_digest,
            configuration_digest=configuration_digest,
            policy_version=policy_version,
            policy_source=policy_source,
            rule_set_digest=rule_set_digest,
            candidate_universe_digest=candidate_universe_digest,
        )

    x1 = np.asarray(result1.x, dtype=float)
    sum_r_stage1 = -float(result1.fun)
    if not math.isfinite(sum_r_stage1):
        return _empty_release_result(
            universe=sorted_universe,
            peers=peers,
            solver_state=_STATE_ERROR,
            mip_dual_bound=0.0,
            mip_gap=0.0,
            input_digest=input_digest,
            configuration_digest=configuration_digest,
            policy_version=policy_version,
            policy_source=policy_source,
            rule_set_digest=rule_set_digest,
            candidate_universe_digest=candidate_universe_digest,
        )

    proven, k_rounded, dual_bound_normalized, mip_gap_value = _stage1_proof(
        result1, sum_r_stage1
    )
    if not proven:
        return _empty_release_result(
            universe=sorted_universe,
            peers=peers,
            solver_state=_STATE_UNPROVEN,
            mip_dual_bound=dual_bound_normalized,
            mip_gap=mip_gap_value,
            input_digest=input_digest,
            configuration_digest=configuration_digest,
            policy_version=policy_version,
            policy_source=policy_source,
            rule_set_digest=rule_set_digest,
            candidate_universe_digest=candidate_universe_digest,
        )

    if k_rounded == 0:
        return _empty_release_result(
            universe=sorted_universe,
            peers=peers,
            solver_state=_STATE_OPTIMAL,
            mip_dual_bound=dual_bound_normalized,
            mip_gap=mip_gap_value,
            input_digest=input_digest,
            configuration_digest=configuration_digest,
            policy_version=policy_version,
            policy_source=policy_source,
            rule_set_digest=rule_set_digest,
            candidate_universe_digest=candidate_universe_digest,
        )

    # ---------------- Stage 2: minimize distortion ----------------
    stage2 = model.extend_stage2(k_rounded)
    # Release Stage-1 matrix local reference before the larger stage grows.
    del stage1
    result2 = _solve_stage(stage2, objective=stage2.objective, options=cert_options)
    stage2_failure = _validate_result(result2, stage2.n_vars)
    if stage2_failure is not None:
        return _finalize_from_partial_x(
            x_vec=x1,
            model=model,
            unit_data=unit_data,
            keys=keys,
            peers=peers,
            rule_configs=rule_configs,
            sorted_universe=sorted_universe,
            solver_state=_STATE_UNPROVEN,
            mip_dual_bound=dual_bound_normalized,
            mip_gap=mip_gap_value,
            later_objectives=(0.0, 0.0),
            input_digest=input_digest,
            configuration_digest=configuration_digest,
            policy_version=policy_version,
            policy_source=policy_source,
            rule_set_digest=rule_set_digest,
            candidate_universe_digest=candidate_universe_digest,
        )

    x2 = np.asarray(result2.x, dtype=float)
    d_star = float(result2.fun)
    tau_d = _lex_tolerance(d_star)
    distortion_ub = d_star + tau_d

    # ---------------- Stage 3: minimize neutral-weight distance ----------------
    stage3_base = model.extend_stage3(stage2)
    del stage2
    stage3 = model.with_linear_upper_bound(
        stage3_base,
        {idx: 1.0 for idx in stage3_base.d_index.values()},
        distortion_ub,
    )
    del stage3_base
    result3 = _solve_stage(stage3, objective=stage3.objective, options=cert_options)
    stage3_failure = _validate_result(result3, stage3.n_vars)
    if stage3_failure is not None:
        return _finalize_from_partial_x(
            x_vec=x2,
            model=model,
            unit_data=unit_data,
            keys=keys,
            peers=peers,
            rule_configs=rule_configs,
            sorted_universe=sorted_universe,
            solver_state=_STATE_UNPROVEN,
            mip_dual_bound=dual_bound_normalized,
            mip_gap=mip_gap_value,
            later_objectives=(d_star, 0.0),
            input_digest=input_digest,
            configuration_digest=configuration_digest,
            policy_version=policy_version,
            policy_source=policy_source,
            rule_set_digest=rule_set_digest,
            candidate_universe_digest=candidate_universe_digest,
        )

    x3 = np.asarray(result3.x, dtype=float)
    n_star = float(result3.fun)
    # A zero neutral-distance optimum fixes every weight at exactly 1.0.
    # Do not add lexicographic slack in this case.
    tau_n = 0.0 if n_star == 0.0 else _lex_tolerance(n_star)
    neutral_ub = n_star + tau_n

    # ---------------- Stage 4: deterministic canonical tie-breaking ----------
    stage4, block_row_indices = model.build_stage4(
        stage3,
        distortion_ub=distortion_ub,
        neutral_ub=neutral_ub,
    )
    del stage3

    bounds_lb = stage4.bounds_lb.copy()
    bounds_ub = stage4.bounds_ub.copy()
    blocks = model.release_blocks

    # 4a. Release-mask blocks: maximize integer block value, then fix.
    for block in blocks:
        objective = np.zeros(stage4.n_vars, dtype=float)
        for idx, coef in zip(block.variable_indices, block.coefficients):
            objective[idx] = -float(coef)
        row_lb, row_ub = _sync_block_bounds(stage4, block_row_indices, blocks)
        step_result = _solve_stage(
            stage4,
            objective=objective,
            options=cert_options,
            bounds_lb=bounds_lb,
            bounds_ub=bounds_ub,
            constraints_lb=row_lb,
            constraints_ub=row_ub,
        )
        fail = _validate_result(step_result, stage4.n_vars)
        if fail is not None:
            return _finalize_from_partial_x(
                x_vec=x3,
                model=model,
                unit_data=unit_data,
                keys=keys,
                peers=peers,
                rule_configs=rule_configs,
                sorted_universe=sorted_universe,
                solver_state=_STATE_UNPROVEN,
                mip_dual_bound=dual_bound_normalized,
                mip_gap=mip_gap_value,
                later_objectives=(d_star, n_star),
                input_digest=input_digest,
                configuration_digest=configuration_digest,
                policy_version=policy_version,
                policy_source=policy_source,
                rule_set_digest=rule_set_digest,
                candidate_universe_digest=candidate_universe_digest,
            )
        x_step = np.asarray(step_result.x, dtype=float)
        try:
            bit_values = [
                _extract_binary(x_step, idx) for idx in block.variable_indices
            ]
        except RuntimeError:
            return _finalize_from_partial_x(
                x_vec=x3,
                model=model,
                unit_data=unit_data,
                keys=keys,
                peers=peers,
                rule_configs=rule_configs,
                sorted_universe=sorted_universe,
                solver_state=_STATE_UNPROVEN,
                mip_dual_bound=dual_bound_normalized,
                mip_gap=mip_gap_value,
                later_objectives=(d_star, n_star),
                input_digest=input_digest,
                configuration_digest=configuration_digest,
                policy_version=policy_version,
                policy_source=policy_source,
                rule_set_digest=rule_set_digest,
                candidate_universe_digest=candidate_universe_digest,
            )
        block_value = int(
            sum(
                coef * bit
                for coef, bit in zip(block.coefficients, bit_values)
            )
        )
        block.fix(block_value)
        # Also pin the individual release variables for numerical stability.
        for idx, bit in zip(block.variable_indices, bit_values):
            bounds_lb[idx] = float(bit)
            bounds_ub[idx] = float(bit)

    # 4b. Weights: visit peers in canonical order and minimize w_p, then fix.
    for peer in peers:
        idx = model.w_index[peer]
        objective = np.zeros(stage4.n_vars, dtype=float)
        objective[idx] = 1.0
        row_lb, row_ub = _sync_block_bounds(stage4, block_row_indices, blocks)
        step_result = _solve_stage(
            stage4,
            objective=objective,
            options=cert_options,
            bounds_lb=bounds_lb,
            bounds_ub=bounds_ub,
            constraints_lb=row_lb,
            constraints_ub=row_ub,
        )
        fail = _validate_result(step_result, stage4.n_vars)
        if fail is not None:
            return _finalize_from_partial_x(
                x_vec=x3,
                model=model,
                unit_data=unit_data,
                keys=keys,
                peers=peers,
                rule_configs=rule_configs,
                sorted_universe=sorted_universe,
                solver_state=_STATE_UNPROVEN,
                mip_dual_bound=dual_bound_normalized,
                mip_gap=mip_gap_value,
                later_objectives=(d_star, n_star),
                input_digest=input_digest,
                configuration_digest=configuration_digest,
                policy_version=policy_version,
                policy_source=policy_source,
                rule_set_digest=rule_set_digest,
                candidate_universe_digest=candidate_universe_digest,
            )
        w_val = float(step_result.x[idx])
        if not math.isfinite(w_val):
            return _finalize_from_partial_x(
                x_vec=x3,
                model=model,
                unit_data=unit_data,
                keys=keys,
                peers=peers,
                rule_configs=rule_configs,
                sorted_universe=sorted_universe,
                solver_state=_STATE_UNPROVEN,
                mip_dual_bound=dual_bound_normalized,
                mip_gap=mip_gap_value,
                later_objectives=(d_star, n_star),
                input_digest=input_digest,
                configuration_digest=configuration_digest,
                policy_version=policy_version,
                policy_source=policy_source,
                rule_set_digest=rule_set_digest,
                candidate_universe_digest=candidate_universe_digest,
            )
        w_val = max(min_weight, min(max_weight, w_val))
        bounds_lb[idx] = w_val
        bounds_ub[idx] = w_val

    weights = {peer: float(bounds_lb[model.w_index[peer]]) for peer in peers}
    released = [
        str(unit["key"])
        for unit in unit_data
        if bounds_lb[model.r_index[str(unit["key"])]] >= 1.0 - _INTEGRALITY_READBACK_TOLERANCE
    ]
    suppressed = [
        str(unit["key"])
        for unit in unit_data
        if str(unit["key"]) not in set(released)
    ]

    # 4c. Canonical authorizing rules from direct policy evaluation (no per-rule solves).
    authorizing, missing = _select_authorizing_rules(
        unit_data, released, weights, rule_configs
    )
    solver_state = _STATE_OPTIMAL
    if missing:
        solver_state = _STATE_UNPROVEN
        for key in missing:
            if key in released:
                released.remove(key)
            if key not in suppressed:
                suppressed.append(key)
            authorizing.pop(key, None)

    # 4d. Final feasibility solve with fixed release mask and weights.
    row_lb, row_ub = _sync_block_bounds(stage4, block_row_indices, blocks)
    final_obj = np.zeros(stage4.n_vars, dtype=float)
    final_result = _solve_stage(
        stage4,
        objective=final_obj,
        options=cert_options,
        bounds_lb=bounds_lb,
        bounds_ub=bounds_ub,
        constraints_lb=row_lb,
        constraints_ub=row_ub,
    )
    final_failure = _validate_result(final_result, stage4.n_vars)
    if final_failure is not None:
        return _finalize_from_partial_x(
            x_vec=x3,
            model=model,
            unit_data=unit_data,
            keys=keys,
            peers=peers,
            rule_configs=rule_configs,
            sorted_universe=sorted_universe,
            solver_state=_STATE_UNPROVEN,
            mip_dual_bound=dual_bound_normalized,
            mip_gap=mip_gap_value,
            later_objectives=(d_star, n_star),
            input_digest=input_digest,
            configuration_digest=configuration_digest,
            policy_version=policy_version,
            policy_source=policy_source,
            rule_set_digest=rule_set_digest,
            candidate_universe_digest=candidate_universe_digest,
        )

    return _finalize_result(
        unit_data=unit_data,
        keys=keys,
        peers=peers,
        weights=weights,
        released_keys=released,
        suppressed_keys=suppressed,
        authorizing_rules=authorizing,
        sorted_universe=sorted_universe,
        solver_state=solver_state,
        mip_dual_bound=dual_bound_normalized,
        mip_gap=mip_gap_value,
        later_objectives=(d_star, n_star),
        input_digest=input_digest,
        configuration_digest=configuration_digest,
        policy_version=policy_version,
        policy_source=policy_source,
        rule_set_digest=rule_set_digest,
        candidate_universe_digest=candidate_universe_digest,
    )
