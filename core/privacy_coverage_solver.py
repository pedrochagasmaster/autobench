"""Maximum Safe Coverage MILP solver using ``scipy.optimize.milp``.

Owns the mixed-integer formulation for
``PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE``. The independent verifier remains
a separate Module and must recalculate every policy check from the original
inputs and the final global weight vector.

This Module must not authorize a client sink. It produces a trusted internal
``SafeCoverageResult`` with ``verifier_result='not_run'`` until the verifier
attests the release.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import csr_matrix

from core.canonical_order import canonical_key, canonical_order
from core.constants import COMPARISON_EPSILON
from core.contracts import (
    APPROVED_PRIVACY_RULE_NAMES,
    PrivacyReleaseMode,
    PublicationUnit,
    SafeCoverageResult,
)
from core.privacy_coverage import CITIBANK_OVERLAY_NAME
from core.privacy_rules import privacy_rule_from_config

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

# Small tightening applied to primary-cap and secondary-tier thresholds inside
# the MILP so that the recomputed share obtained after HiGHS termination stays
# strictly on the ``evaluate_rule`` side of ``COMPARISON_EPSILON`` under any
# floating-point drift. The buffer is orders of magnitude smaller than the
# policy epsilon and does not weaken any rule. It only prevents parity
# failures caused by rounding when reconstructing shares from returned weights.
_MILP_NUMERIC_BUFFER = 1e-9

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


@dataclass(frozen=True)
class _Rule:
    """Solver-side view of one approved privacy rule.

    ``secondary_tiers`` uses cumulative counts, matching the normalization in
    ``core.privacy_rules._secondary_requirements_from_config`` so that the
    MILP formulation and ``evaluate_rule`` share exactly one policy meaning.
    """

    name: str
    min_entities: int
    max_concentration: float
    secondary_tiers: Tuple[Tuple[int, float], ...]


def _build_rule(
    name: str,
    rule_configs: Mapping[str, Mapping[str, Any]],
) -> _Rule:
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
    return _Rule(
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

    rule_cache: Dict[str, _Rule] = {}

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
                rule_cache[rule_name] = _build_rule(rule_name, rule_configs)
        unit_data.append(
            {
                "key": unit.internal_key,
                "unit": unit,
                "metrics": metric_records,
                "rules": rules_canonical,
                "overlays": tuple(unit.mandatory_overlays),
            }
        )

    citi_peer: Optional[str] = None
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
        citi_peer = matches[0]

    # Variable layout (all packed into one flat SciPy x vector).
    n_peers = len(peers)
    w_index: Dict[str, int] = {peer: i for i, peer in enumerate(peers)}
    offset = n_peers

    r_index: Dict[str, int] = {}
    for u in unit_data:
        r_index[u["key"]] = offset
        offset += 1

    y_index: Dict[Tuple[str, str], int] = {}
    for u in unit_data:
        for rule_name in u["rules"]:
            y_index[(u["key"], rule_name)] = offset
            offset += 1

    z_index: Dict[Tuple[str, str, str, int, str], int] = {}
    for u in unit_data:
        for metric_record in u["metrics"]:
            metric_name = metric_record["metric"]
            positive_peers = metric_record["positive_peers"]
            for rule_name in u["rules"]:
                rule = rule_cache[rule_name]
                for tier_i, _tier in enumerate(rule.secondary_tiers):
                    for peer in positive_peers:
                        z_index[
                            (u["key"], metric_name, rule_name, tier_i, peer)
                        ] = offset
                        offset += 1

    d_index: Dict[Tuple[str, str, str], int] = {}
    for u in unit_data:
        for metric_record in u["metrics"]:
            metric_name = metric_record["metric"]
            for peer in metric_record["positive_peers"]:
                d_index[(u["key"], metric_name, peer)] = offset
                offset += 1

    q_index: Dict[str, int] = {}
    for peer in peers:
        q_index[peer] = offset
        offset += 1

    n_vars = offset

    lb = np.zeros(n_vars)
    ub = np.zeros(n_vars)
    integrality = np.zeros(n_vars, dtype=int)

    for peer, idx in w_index.items():
        lb[idx] = min_weight
        ub[idx] = max_weight

    for u in unit_data:
        idx = r_index[u["key"]]
        integrality[idx] = 1
        lb[idx] = 0.0
        ub[idx] = 1.0 if u["rules"] else 0.0

    # Disable rules whose participant minimum is not structurally satisfied by
    # every governed metric in the unit. This mirrors ``evaluate_rule``: a
    # participant count below the minimum is a hard structural failure.
    for u in unit_data:
        for rule_name in u["rules"]:
            rule = rule_cache[rule_name]
            idx = y_index[(u["key"], rule_name)]
            integrality[idx] = 1
            lb[idx] = 0.0
            ub[idx] = 1.0
            for metric_record in u["metrics"]:
                if len(metric_record["positive_peers"]) < rule.min_entities:
                    ub[idx] = 0.0
                    break

    for _z_key, idx in z_index.items():
        integrality[idx] = 1
        lb[idx] = 0.0
        ub[idx] = 1.0

    m_d = float(max_weight - min_weight)
    for _d_key, idx in d_index.items():
        integrality[idx] = 0
        lb[idx] = 0.0
        ub[idx] = m_d if m_d > 0.0 else 0.0

    q_upper = max(max_weight - 1.0, 1.0 - min_weight, 0.0)
    for peer, idx in q_index.items():
        integrality[idx] = 0
        lb[idx] = 0.0
        ub[idx] = q_upper

    # Sparse triplets for the base constraint matrix. Each row has a scalar
    # lower/upper bound (either finite or +/- infinity).
    row_data: List[float] = []
    row_indices: List[int] = []
    row_indptr: List[int] = [0]
    row_lb: List[float] = []
    row_ub: List[float] = []

    def _push_row(entries: Sequence[Tuple[int, float]], lb_val: float, ub_val: float) -> None:
        # Aggregate duplicate column indices deterministically and drop zeros.
        aggregated: Dict[int, float] = {}
        for col, value in entries:
            if value == 0.0:
                continue
            aggregated[col] = aggregated.get(col, 0.0) + value
        ordered_cols = sorted(col for col, value in aggregated.items() if value != 0.0)
        for col in ordered_cols:
            row_indices.append(col)
            row_data.append(aggregated[col])
        row_indptr.append(len(row_indices))
        row_lb.append(lb_val)
        row_ub.append(ub_val)

    def _interval_min(coefficients: Mapping[str, float]) -> float:
        total = 0.0
        for peer, coef in coefficients.items():
            if coef >= 0.0:
                total += coef * min_weight
            else:
                total += coef * max_weight
        return total

    def _interval_max(coefficients: Mapping[str, float]) -> float:
        total = 0.0
        for peer, coef in coefficients.items():
            if coef >= 0.0:
                total += coef * max_weight
            else:
                total += coef * min_weight
        return total

    # 1. Rule-selection totals: sum_r y_ur = r_u.
    for u in unit_data:
        entries: List[Tuple[int, float]] = []
        entries.append((r_index[u["key"]], -1.0))
        for rule_name in u["rules"]:
            entries.append((y_index[(u["key"], rule_name)], 1.0))
        _push_row(entries, 0.0, 0.0)

    # 2. Primary cap rows.
    #
    # For rule r selected on unit u (y_ur=1), every peer p with positive volume
    # must satisfy g_umrp(w) = c_r*T - 100*a_ump*w_p >= 0, with
    # c_r = C_r + COMPARISON_EPSILON. The big-M relaxation g >= -M*(1-y_ur)
    # becomes, in flat LinearConstraint form,
    #     g(w) - M * y_ur >= -M
    # where M is the smallest safe value derived from interval bounds on g.
    for u in unit_data:
        for metric_record in u["metrics"]:
            aligned = metric_record["aligned_volumes"]
            positive_peers = metric_record["positive_peers"]
            for rule_name in u["rules"]:
                rule = rule_cache[rule_name]
                c_r = rule.max_concentration + COMPARISON_EPSILON - _MILP_NUMERIC_BUFFER
                for peer in positive_peers:
                    coefficients: Dict[str, float] = {}
                    for j_peer, volume in aligned.items():
                        if volume == 0.0:
                            continue
                        if j_peer == peer:
                            coefficients[j_peer] = (c_r - 100.0) * volume
                        else:
                            coefficients[j_peer] = c_r * volume
                    inf_g = _interval_min(coefficients)
                    big_m = max(0.0, -inf_g)
                    entries = [
                        (w_index[j_peer], coef)
                        for j_peer, coef in coefficients.items()
                    ]
                    entries.append(
                        (y_index[(u["key"], rule_name)], -big_m)
                    )
                    _push_row(entries, -big_m, math.inf)

    # 3. Secondary tier witness rows and count/upper-bound rows.
    for u in unit_data:
        for metric_record in u["metrics"]:
            aligned = metric_record["aligned_volumes"]
            positive_peers = metric_record["positive_peers"]
            for rule_name in u["rules"]:
                rule = rule_cache[rule_name]
                for tier_i, (required_count, threshold) in enumerate(
                    rule.secondary_tiers
                ):
                    tau = threshold - COMPARISON_EPSILON + _MILP_NUMERIC_BUFFER
                    # Witness rows: h(w) - M*z_umrtp >= -M, where the plain
                    # implication is z=1 => h >= 0 (peer p meets tier t).
                    for peer in positive_peers:
                        coefficients = {}
                        for j_peer, volume in aligned.items():
                            if volume == 0.0:
                                continue
                            if j_peer == peer:
                                coefficients[j_peer] = (100.0 - tau) * volume
                            else:
                                coefficients[j_peer] = -tau * volume
                        inf_h = _interval_min(coefficients)
                        big_m = max(0.0, -inf_h)
                        entries = [
                            (w_index[j_peer], coef)
                            for j_peer, coef in coefficients.items()
                        ]
                        entries.append(
                            (
                                z_index[
                                    (
                                        u["key"],
                                        metric_record["metric"],
                                        rule_name,
                                        tier_i,
                                        peer,
                                    )
                                ],
                                -big_m,
                            )
                        )
                        _push_row(entries, -big_m, math.inf)

                    # Upper-bound rows: z_umrtp <= y_ur.
                    for peer in positive_peers:
                        entries = [
                            (
                                z_index[
                                    (
                                        u["key"],
                                        metric_record["metric"],
                                        rule_name,
                                        tier_i,
                                        peer,
                                    )
                                ],
                                1.0,
                            ),
                            (
                                y_index[(u["key"], rule_name)],
                                -1.0,
                            ),
                        ]
                        _push_row(entries, -math.inf, 0.0)

                    # Cumulative-count row: sum_p z >= k_t * y.
                    entries = []
                    for peer in positive_peers:
                        entries.append(
                            (
                                z_index[
                                    (
                                        u["key"],
                                        metric_record["metric"],
                                        rule_name,
                                        tier_i,
                                        peer,
                                    )
                                ],
                                1.0,
                            )
                        )
                    entries.append(
                        (
                            y_index[(u["key"], rule_name)],
                            -float(required_count),
                        )
                    )
                    _push_row(entries, 0.0, math.inf)

    # 4. Citi mandatory overlay: conditioned on r_u.
    for u in unit_data:
        if CITIBANK_OVERLAY_NAME not in u["overlays"]:
            continue
        if citi_peer is None:
            continue
        for metric_record in u["metrics"]:
            aligned = metric_record["aligned_volumes"]
            a_citi = aligned.get(citi_peer, 0.0)
            if a_citi <= 0.0:
                continue
            coefficients = {}
            for j_peer, volume in aligned.items():
                if volume == 0.0:
                    continue
                if j_peer == citi_peer:
                    coefficients[j_peer] = (25.0 - 100.0) * volume
                else:
                    coefficients[j_peer] = 25.0 * volume
            inf_c = _interval_min(coefficients)
            big_m = max(0.0, -inf_c)
            entries = [
                (w_index[j_peer], coef)
                for j_peer, coef in coefficients.items()
            ]
            # Overlay conditioned on r_u: g_citi(w) - M*r_u >= -M.
            entries.append((r_index[u["key"]], -big_m))
            _push_row(entries, -big_m, math.inf)

    # 5. Distortion auxiliary d_ump linearization (released-unit conditional).
    for u in unit_data:
        for metric_record in u["metrics"]:
            aligned = metric_record["aligned_volumes"]
            total = metric_record["total"]
            # wbar_um coefficients: f_umj = a_umj / A_um.
            f_coef = {
                peer: (aligned[peer] / total) if total > 0.0 else 0.0
                for peer in peers
            }
            for peer in metric_record["positive_peers"]:
                d_idx = d_index[(u["key"], metric_record["metric"], peer)]
                # Row A: d_ump - (w_p - wbar_um) + M_d * r_u >= 0  when r=1
                #   i.e. d + wbar - w_p + M_d*(r-1) >= 0 rearranged
                # We enforce: d_ump >= (w_p - wbar_um) - M_d*(1 - r_u).
                # -> d_ump - w_p + sum_j f_j w_j + M_d r_u >= -M_d + M_d = 0? Let's redo:
                # d_ump >= (w_p - wbar_um) - M_d*(1 - r_u)
                # d_ump - w_p + wbar_um - M_d*r_u >= -M_d
                # d_ump + (sum_j f_j w_j) - w_p - M_d*r_u >= -M_d
                entries_a: List[Tuple[int, float]] = [(d_idx, 1.0)]
                for j_peer in peers:
                    coef = f_coef[j_peer] + (-1.0 if j_peer == peer else 0.0)
                    entries_a.append((w_index[j_peer], coef))
                entries_a.append((r_index[u["key"]], -m_d))
                _push_row(entries_a, -m_d, math.inf)

                # Row B: d_ump >= -(w_p - wbar_um) - M_d*(1 - r_u)
                # d_ump - (wbar - w_p) - M_d + M_d*r_u >= 0
                # d_ump - wbar + w_p - M_d*r_u >= -M_d
                # d_ump - sum_j f_j w_j + w_p - M_d*r_u >= -M_d
                entries_b: List[Tuple[int, float]] = [(d_idx, 1.0)]
                for j_peer in peers:
                    coef = -f_coef[j_peer] + (1.0 if j_peer == peer else 0.0)
                    entries_b.append((w_index[j_peer], coef))
                entries_b.append((r_index[u["key"]], -m_d))
                _push_row(entries_b, -m_d, math.inf)

                # Upper bound gated on release: d_ump - M_d*r_u <= 0.
                entries_c = [(d_idx, 1.0), (r_index[u["key"]], -m_d)]
                _push_row(entries_c, -math.inf, 0.0)

    # 6. Neutral-weight distance q_p >= |w_p - 1|.
    for peer in peers:
        _push_row(
            [(q_index[peer], 1.0), (w_index[peer], -1.0)],
            -1.0,
            math.inf,
        )
        _push_row(
            [(q_index[peer], 1.0), (w_index[peer], 1.0)],
            1.0,
            math.inf,
        )

    base_matrix = csr_matrix(
        (np.asarray(row_data), np.asarray(row_indices), np.asarray(row_indptr)),
        shape=(len(row_lb), n_vars),
    )
    base_row_lb = np.asarray(row_lb)
    base_row_ub = np.asarray(row_ub)
    base_constraint = LinearConstraint(base_matrix, base_row_lb, base_row_ub)

    integrality_arr = integrality

    def _make_bounds(lb_arr: np.ndarray, ub_arr: np.ndarray) -> Bounds:
        return Bounds(lb_arr.copy(), ub_arr.copy())

    current_lb = lb.copy()
    current_ub = ub.copy()

    def _solve(
        objective: np.ndarray,
        extras: Sequence[LinearConstraint],
    ) -> Any:
        constraints: List[LinearConstraint] = [base_constraint]
        constraints.extend(extras)
        return milp(
            c=objective,
            integrality=integrality_arr,
            bounds=_make_bounds(current_lb, current_ub),
            constraints=constraints,
            options=sanitized_options,
        )

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

    def _validate_result(res: Any) -> Optional[str]:
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

    # ---------------- Stage 1: maximize sum r_u ----------------
    c1 = np.zeros(n_vars)
    for u in unit_data:
        c1[r_index[u["key"]]] = -1.0

    result1 = _solve(c1, ())
    stage1_failure = _validate_result(result1)
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
    stage1_fun = float(result1.fun)
    sum_r_stage1 = -stage1_fun
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

    K_rounded = int(round(sum_r_stage1))
    integrality_ok = (
        abs(sum_r_stage1 - K_rounded) <= _INTEGRALITY_READBACK_TOLERANCE
    )

    # Stage 1 proof normalization: released-count sign.
    raw_dual = getattr(result1, "mip_dual_bound", None)
    raw_gap = getattr(result1, "mip_gap", None)
    proven = integrality_ok
    dual_bound_normalized: float = 0.0
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
    mip_gap_value: float = 0.0
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
    if round(dual_bound_normalized) != K_rounded:
        proven = False

    # If K is 0, we cannot release any unit. Return early with an optimal state
    # only when the primary solve is fully proven.
    if K_rounded == 0:
        state_for_empty = _STATE_OPTIMAL if proven else _STATE_UNPROVEN
        return _empty_release_result(
            universe=sorted_universe,
            peers=peers,
            solver_state=state_for_empty,
            mip_dual_bound=dual_bound_normalized,
            mip_gap=mip_gap_value,
            input_digest=input_digest,
            configuration_digest=configuration_digest,
            policy_version=policy_version,
            policy_source=policy_source,
            rule_set_digest=rule_set_digest,
            candidate_universe_digest=candidate_universe_digest,
        )

    # Cardinality constraint: sum r_u = K.
    card_row = np.zeros(n_vars)
    for u in unit_data:
        card_row[r_index[u["key"]]] = 1.0
    card_constraint = LinearConstraint(
        csr_matrix(card_row.reshape(1, -1)),
        float(K_rounded),
        float(K_rounded),
    )

    # ---------------- Stage 2: minimize weighted share impact ----------------
    c2 = np.zeros(n_vars)
    for u in unit_data:
        metric_count = len(u["metrics"])
        if metric_count == 0:
            continue
        for metric_record in u["metrics"]:
            aligned = metric_record["aligned_volumes"]
            total = metric_record["total"]
            for peer in metric_record["positive_peers"]:
                f_ump = aligned[peer] / total
                c2[d_index[(u["key"], metric_record["metric"], peer)]] += (
                    100.0 * f_ump / metric_count
                )

    result2 = _solve(c2, (card_constraint,))
    stage2_failure = _validate_result(result2)
    if stage2_failure is not None:
        # Fall back to stage 1 solution; report unproven state.
        return _finalize_from_x(
            x_vec=x1,
            unit_data=unit_data,
            keys=keys,
            peers=peers,
            r_index=r_index,
            y_index=y_index,
            d_index=d_index,
            q_index=q_index,
            rule_cache=rule_cache,
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
    tau_d = max(_LEX_TOLERANCE_ABS, _LEX_TOLERANCE_REL * max(1.0, abs(d_star)))
    d_bound_constraint = LinearConstraint(
        csr_matrix(c2.reshape(1, -1)),
        -math.inf,
        d_star + tau_d,
    )

    # ---------------- Stage 3: minimize neutral-weight distance ----------------
    c3 = np.zeros(n_vars)
    for peer in peers:
        c3[q_index[peer]] = 1.0 / float(n_peers)

    result3 = _solve(c3, (card_constraint, d_bound_constraint))
    stage3_failure = _validate_result(result3)
    if stage3_failure is not None:
        return _finalize_from_x(
            x_vec=x2,
            unit_data=unit_data,
            keys=keys,
            peers=peers,
            r_index=r_index,
            y_index=y_index,
            d_index=d_index,
            q_index=q_index,
            rule_cache=rule_cache,
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
    tau_n = max(_LEX_TOLERANCE_ABS, _LEX_TOLERANCE_REL * max(1.0, abs(n_star)))
    n_bound_constraint = LinearConstraint(
        csr_matrix(c3.reshape(1, -1)),
        -math.inf,
        n_star + tau_n,
    )

    # ---------------- Stage 4: deterministic canonical tie-breaking ----------
    # 4a. Release mask: visit units in canonical order, maximize r_u, fix it.
    stage4_extras: List[LinearConstraint] = [
        card_constraint,
        d_bound_constraint,
        n_bound_constraint,
    ]

    stage4_failure_state: Optional[str] = None

    for u in unit_data:
        idx = r_index[u["key"]]
        if current_lb[idx] == current_ub[idx]:
            continue
        obj = np.zeros(n_vars)
        obj[idx] = -1.0
        step_result = _solve(obj, stage4_extras)
        fail = _validate_result(step_result)
        if fail is not None:
            stage4_failure_state = fail
            break
        try:
            r_val = _extract_binary(np.asarray(step_result.x, dtype=float), idx)
        except RuntimeError:
            stage4_failure_state = _STATE_ERROR
            break
        current_lb[idx] = float(r_val)
        current_ub[idx] = float(r_val)

    if stage4_failure_state is not None:
        return _finalize_from_x(
            x_vec=x3,
            unit_data=unit_data,
            keys=keys,
            peers=peers,
            r_index=r_index,
            y_index=y_index,
            d_index=d_index,
            q_index=q_index,
            rule_cache=rule_cache,
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

    # 4b. Authorizing rules: visit released units in canonical order and pick
    # the first canonical rule that can be selected.
    for u in unit_data:
        r_idx = r_index[u["key"]]
        if current_ub[r_idx] == 0.0 or current_lb[r_idx] == 0.0 and current_ub[r_idx] == 0.0:
            # Suppressed unit: force y_ur = 0 for all rules.
            for rule_name in u["rules"]:
                y_idx = y_index[(u["key"], rule_name)]
                if current_lb[y_idx] != current_ub[y_idx]:
                    current_ub[y_idx] = 0.0
                    current_lb[y_idx] = 0.0
            continue
        if current_lb[r_idx] < 1.0:
            # Not yet fixed to 1 (should not happen at this point).
            continue
        selected_rule: Optional[str] = None
        for rule_name in u["rules"]:
            y_idx = y_index[(u["key"], rule_name)]
            if current_ub[y_idx] == 0.0:
                # Structurally disabled (e.g., participant minimum failure).
                continue
            if current_lb[y_idx] == current_ub[y_idx] == 1.0:
                selected_rule = rule_name
                break
            obj = np.zeros(n_vars)
            obj[y_idx] = -1.0
            step_result = _solve(obj, stage4_extras)
            fail = _validate_result(step_result)
            if fail is not None:
                stage4_failure_state = fail
                break
            try:
                y_val = _extract_binary(
                    np.asarray(step_result.x, dtype=float), y_idx
                )
            except RuntimeError:
                stage4_failure_state = _STATE_ERROR
                break
            current_lb[y_idx] = float(y_val)
            current_ub[y_idx] = float(y_val)
            if y_val == 1:
                selected_rule = rule_name
                # Force remaining rules to 0 to avoid ties.
                for other_rule in u["rules"]:
                    if other_rule == rule_name:
                        continue
                    other_idx = y_index[(u["key"], other_rule)]
                    if current_lb[other_idx] != current_ub[other_idx]:
                        current_lb[other_idx] = 0.0
                        current_ub[other_idx] = 0.0
                break
        if stage4_failure_state is not None:
            break
        if selected_rule is None:
            # No applicable authorizing rule was selected despite r_u = 1.
            # This is a structural inconsistency in the model; report unproven.
            stage4_failure_state = _STATE_ERROR
            break

    if stage4_failure_state is not None:
        return _finalize_from_x(
            x_vec=x3,
            unit_data=unit_data,
            keys=keys,
            peers=peers,
            r_index=r_index,
            y_index=y_index,
            d_index=d_index,
            q_index=q_index,
            rule_cache=rule_cache,
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

    # 4c. Weights: visit peers in canonical order and minimize w_p, then fix.
    for peer in peers:
        idx = w_index[peer]
        obj = np.zeros(n_vars)
        obj[idx] = 1.0
        step_result = _solve(obj, stage4_extras)
        fail = _validate_result(step_result)
        if fail is not None:
            stage4_failure_state = fail
            break
        w_val = float(step_result.x[idx])
        if not math.isfinite(w_val):
            stage4_failure_state = _STATE_ERROR
            break
        # Clamp inside original bounds to avoid tiny drift making the next
        # solve infeasible.
        w_val = max(min_weight, min(max_weight, w_val))
        current_lb[idx] = w_val
        current_ub[idx] = w_val

    if stage4_failure_state is not None:
        return _finalize_from_x(
            x_vec=x3,
            unit_data=unit_data,
            keys=keys,
            peers=peers,
            r_index=r_index,
            y_index=y_index,
            d_index=d_index,
            q_index=q_index,
            rule_cache=rule_cache,
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

    # 4d. Final feasibility solve to extract the canonical vector.
    final_obj = np.zeros(n_vars)
    final_result = _solve(final_obj, stage4_extras)
    final_failure = _validate_result(final_result)
    if final_failure is not None:
        return _finalize_from_x(
            x_vec=x3,
            unit_data=unit_data,
            keys=keys,
            peers=peers,
            r_index=r_index,
            y_index=y_index,
            d_index=d_index,
            q_index=q_index,
            rule_cache=rule_cache,
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

    x_final = np.asarray(final_result.x, dtype=float)
    solver_state = _STATE_OPTIMAL if proven else _STATE_UNPROVEN
    return _finalize_from_x(
        x_vec=x_final,
        unit_data=unit_data,
        keys=keys,
        peers=peers,
        r_index=r_index,
        y_index=y_index,
        d_index=d_index,
        q_index=q_index,
        rule_cache=rule_cache,
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


def _finalize_from_x(
    *,
    x_vec: np.ndarray,
    unit_data: Sequence[Mapping[str, Any]],
    keys: Sequence[str],
    peers: Sequence[str],
    r_index: Mapping[str, int],
    y_index: Mapping[Tuple[str, str], int],
    d_index: Mapping[Tuple[str, str, str], int],
    q_index: Mapping[str, int],
    rule_cache: Mapping[str, _Rule],
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
    """Build a ``SafeCoverageResult`` from a final variable vector."""
    released_keys: List[str] = []
    suppressed_keys: List[str] = []
    authorizing_rules: Dict[str, str] = {}
    for u in unit_data:
        u_key = u["key"]
        r_val_raw = float(x_vec[r_index[u_key]])
        r_val = int(round(r_val_raw))
        # Under numerical noise, an out-of-{0,1} value indicates the finalization
        # was not reached cleanly. Treat as suppressed rather than authorizing.
        if abs(r_val_raw - r_val) > _INTEGRALITY_READBACK_TOLERANCE or r_val not in (0, 1):
            suppressed_keys.append(u_key)
            continue
        if r_val == 0:
            suppressed_keys.append(u_key)
            continue
        released_keys.append(u_key)
        chosen_rule: Optional[str] = None
        for rule_name in u["rules"]:
            y_val_raw = float(x_vec[y_index[(u_key, rule_name)]])
            y_val = int(round(y_val_raw))
            if abs(y_val_raw - y_val) > _INTEGRALITY_READBACK_TOLERANCE:
                continue
            if y_val == 1:
                chosen_rule = rule_name
                break
        if chosen_rule is None:
            # Structural inconsistency: an r_u=1 unit must have exactly one y=1.
            # Preserve trusted evidence but demote solver_state.
            solver_state = _STATE_UNPROVEN
            released_keys.pop()
            suppressed_keys.append(u_key)
            continue
        authorizing_rules[u_key] = chosen_rule

    # Rebuild weights: peer canonical order is exactly the first n_peers
    # entries of the flat variable vector (see w_index construction).
    weights_out: Dict[str, float] = {}
    for i, peer in enumerate(peers):
        value = float(x_vec[i])
        if not math.isfinite(value):
            solver_state = _STATE_UNPROVEN
            value = 1.0
        weights_out[peer] = value

    # Canonical ordering for released and suppressed sets.
    released_sorted = tuple(sorted(released_keys, key=canonical_key))
    suppressed_sorted = tuple(sorted(suppressed_keys, key=canonical_key))

    # Sanity: every key must appear exactly once across the partition.
    all_keys = set(released_sorted) | set(suppressed_sorted)
    if all_keys != set(keys) or len(released_sorted) + len(suppressed_sorted) != len(keys):
        # Reconstruct partition safely: any missing key is suppressed.
        canonical_all = set(keys)
        missing = canonical_all - all_keys
        for missing_key in sorted(missing, key=canonical_key):
            suppressed_sorted = suppressed_sorted + (missing_key,)
        # Drop any that leaked into released but should not.
        released_sorted = tuple(k for k in released_sorted if k in canonical_all)
        solver_state = _STATE_UNPROVEN

    # Ensure primary_objective_value matches release count.
    primary_objective_value = len(released_sorted)
    # If proof required K but final release count differs, downgrade state.
    if solver_state == _STATE_OPTIMAL and math.isfinite(mip_dual_bound):
        if round(mip_dual_bound) != primary_objective_value:
            solver_state = _STATE_UNPROVEN

    return SafeCoverageResult(
        release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
        global_weights=weights_out,
        candidate_universe=sorted_universe,
        release_set=released_sorted,
        suppression_set=suppressed_sorted,
        authorizing_rules=authorizing_rules,
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
