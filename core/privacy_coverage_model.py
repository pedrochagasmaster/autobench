"""Normalized sparse Maximum Safe Coverage MILP model compilation.

Internal Module. Builds Stage-1 through Stage-4 constraint sets for
``PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE`` without solving. The public
solver entry point remains ``core.privacy_coverage_solver.optimize_safe_coverage``.

Do not export this Module from ``core.__init__``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from scipy.sparse import csc_array, csr_array

from core.canonical_order import canonical_key, canonical_order
from core.constants import COMPARISON_EPSILON
from core.privacy_coverage import CITIBANK_OVERLAY_NAME

_MILP_NUMERIC_BUFFER = 1e-9
_RELEASE_BLOCK_SIZE = 16


class WitnessClass(str, Enum):
    ALWAYS_TRUE = "always_true"
    UNCERTAIN = "uncertain"
    IMPOSSIBLE = "impossible"


class PrimaryClass(str, Enum):
    ALWAYS_PASS = "always_pass"
    UNCERTAIN = "uncertain"
    NEVER_PASS = "never_pass"


@dataclass(frozen=True)
class CoverageRuleView:
    """Solver-facing view of one approved privacy rule."""

    name: str
    min_entities: int
    max_concentration: float
    secondary_tiers: Tuple[Tuple[int, float], ...]


@dataclass(frozen=True)
class CoverageModelStatistics:
    """Safe aggregate counts for compiled Stage-1 models."""

    unit_count: int
    peer_count: int
    metric_count: int
    variable_count: int
    integer_variable_count: int
    row_count: int
    nonzero_count: int
    max_primary_row_nonzeros: int
    max_witness_row_nonzeros: int
    mean_weight_row_count: int
    pruned_rule_count: int
    always_true_witness_count: int
    impossible_witness_count: int


@dataclass(frozen=True)
class StageConstraintSet:
    """One complete CSC constraint system for a solver stage."""

    n_vars: int
    objective: np.ndarray
    integrality: np.ndarray
    bounds_lb: np.ndarray
    bounds_ub: np.ndarray
    constraints: csc_array
    constraints_lb: np.ndarray
    constraints_ub: np.ndarray
    d_index: Mapping[Tuple[str, str, str], int] = field(default_factory=dict)
    q_index: Mapping[str, int] = field(default_factory=dict)


@dataclass
class ReleaseBlock:
    """Prepared Stage-4 release-mask block with mutable fixation bounds."""

    variable_indices: Tuple[int, ...]
    coefficients: Tuple[float, ...]
    lb: float = -math.inf
    ub: float = math.inf

    def fix(self, value: int) -> None:
        self.lb = float(value)
        self.ub = float(value)

    def clear_fix(self) -> None:
        self.lb = -math.inf
        self.ub = math.inf


@dataclass
class CoverageModel:
    """Compiled coverage model with staged constraint construction."""

    peers: Tuple[str, ...]
    min_weight: float
    max_weight: float
    w_index: Dict[str, int]
    b_index: Dict[Tuple[str, str], int]
    r_index: Dict[str, int]
    y_index: Dict[Tuple[str, str], int]
    z_index: Dict[Tuple[str, str, str, int, str], int]
    stage1: StageConstraintSet
    statistics: CoverageModelStatistics
    release_blocks: Tuple[ReleaseBlock, ...]
    _unit_plans: Tuple[Dict[str, Any], ...]
    _normalized: Tuple[Dict[str, Any], ...]
    _citi_peer: Optional[str]

    def extend_stage2(self, release_count: int) -> StageConstraintSet:
        """Return Stage 2: Stage-1 rows plus distortion vars/rows and sum(r)=K."""
        if release_count < 0:
            raise ValueError("release_count must be non-negative")
        stage1 = self.stage1
        d_index: Dict[Tuple[str, str, str], int] = {}
        offset = stage1.n_vars
        for unit in self._normalized:
            for metric in unit["metrics"]:
                metric_name = str(metric["metric"])
                for peer in metric["positive_peers"]:
                    d_index[(str(unit["key"]), metric_name, str(peer))] = offset
                    offset += 1
        n_vars = offset
        m_d = float(self.max_weight - self.min_weight)

        objective = np.zeros(n_vars, dtype=float)
        for idx in d_index.values():
            objective[idx] = 1.0

        integrality = np.zeros(n_vars, dtype=int)
        integrality[: stage1.n_vars] = stage1.integrality
        bounds_lb = np.zeros(n_vars, dtype=float)
        bounds_ub = np.zeros(n_vars, dtype=float)
        bounds_lb[: stage1.n_vars] = stage1.bounds_lb
        bounds_ub[: stage1.n_vars] = stage1.bounds_ub
        for idx in d_index.values():
            bounds_lb[idx] = 0.0
            bounds_ub[idx] = m_d if m_d > 0.0 else 0.0

        builder = _RowBuilder(n_vars)
        builder.extend_from_csc(
            stage1.constraints,
            stage1.constraints_lb,
            stage1.constraints_ub,
        )

        # Cardinality: sum_u r_u = K.
        builder.push(
            [(self.r_index[str(unit["key"])], 1.0) for unit in self._normalized],
            float(release_count),
            float(release_count),
        )

        for unit in self._normalized:
            unit_key = str(unit["key"])
            r_idx = self.r_index[unit_key]
            for metric in unit["metrics"]:
                metric_name = str(metric["metric"])
                b_idx = self.b_index[(unit_key, metric_name)]
                for peer in metric["positive_peers"]:
                    peer_s = str(peer)
                    d_idx = d_index[(unit_key, metric_name, peer_s)]
                    w_idx = self.w_index[peer_s]
                    # d >= (w - b) - M_d*(1-r)  =>  d - w + b - M_d*r >= -M_d
                    builder.push(
                        [
                            (d_idx, 1.0),
                            (w_idx, -1.0),
                            (b_idx, 1.0),
                            (r_idx, -m_d),
                        ],
                        -m_d,
                        math.inf,
                    )
                    # d >= -(w - b) - M_d*(1-r)  =>  d + w - b - M_d*r >= -M_d
                    builder.push(
                        [
                            (d_idx, 1.0),
                            (w_idx, 1.0),
                            (b_idx, -1.0),
                            (r_idx, -m_d),
                        ],
                        -m_d,
                        math.inf,
                    )
                    # d <= M_d * r
                    builder.push([(d_idx, 1.0), (r_idx, -m_d)], -math.inf, 0.0)

        constraints, row_lb, row_ub = builder.build_csc()
        return StageConstraintSet(
            n_vars=n_vars,
            objective=objective,
            integrality=integrality,
            bounds_lb=bounds_lb,
            bounds_ub=bounds_ub,
            constraints=constraints,
            constraints_lb=row_lb,
            constraints_ub=row_ub,
            d_index=d_index,
        )

    def extend_stage3(self, stage2: StageConstraintSet) -> StageConstraintSet:
        """Return Stage 3: Stage-2 rows plus neutral-distance variables."""
        q_index: Dict[str, int] = {}
        offset = stage2.n_vars
        for peer in self.peers:
            q_index[peer] = offset
            offset += 1
        n_vars = offset
        q_upper = max(self.max_weight - 1.0, 1.0 - self.min_weight, 0.0)

        objective = np.zeros(n_vars, dtype=float)
        for idx in q_index.values():
            objective[idx] = 1.0

        integrality = np.zeros(n_vars, dtype=int)
        integrality[: stage2.n_vars] = stage2.integrality
        bounds_lb = np.zeros(n_vars, dtype=float)
        bounds_ub = np.zeros(n_vars, dtype=float)
        bounds_lb[: stage2.n_vars] = stage2.bounds_lb
        bounds_ub[: stage2.n_vars] = stage2.bounds_ub
        for idx in q_index.values():
            bounds_lb[idx] = 0.0
            bounds_ub[idx] = q_upper

        builder = _RowBuilder(n_vars)
        builder.extend_from_csc(
            stage2.constraints,
            stage2.constraints_lb,
            stage2.constraints_ub,
        )
        for peer in self.peers:
            q_idx = q_index[peer]
            w_idx = self.w_index[peer]
            # q >= w - 1  =>  q - w >= -1
            builder.push([(q_idx, 1.0), (w_idx, -1.0)], -1.0, math.inf)
            # q >= 1 - w  =>  q + w >= 1
            builder.push([(q_idx, 1.0), (w_idx, 1.0)], 1.0, math.inf)

        constraints, row_lb, row_ub = builder.build_csc()
        return StageConstraintSet(
            n_vars=n_vars,
            objective=objective,
            integrality=integrality,
            bounds_lb=bounds_lb,
            bounds_ub=bounds_ub,
            constraints=constraints,
            constraints_lb=row_lb,
            constraints_ub=row_ub,
            d_index=dict(stage2.d_index),
            q_index=q_index,
        )

    def with_linear_upper_bound(
        self,
        stage: StageConstraintSet,
        coefficients: Mapping[int, float],
        upper_bound: float,
    ) -> StageConstraintSet:
        """Return ``stage`` plus one row ``sum(c_i x_i) <= upper_bound``."""
        entries = [(int(idx), float(coef)) for idx, coef in coefficients.items() if coef != 0.0]
        return _append_rows(stage, [(entries, -math.inf, float(upper_bound))])

    def build_stage4(
        self,
        stage3: StageConstraintSet,
        *,
        distortion_ub: float,
        neutral_ub: float,
    ) -> Tuple[StageConstraintSet, Tuple[int, ...]]:
        """Return Stage-4 CSC set with lex bounds and prepared release-block rows.

        Release-block row bounds stay mutable via ``ReleaseBlock.fix`` /
        ``clear_fix``; callers must copy ``constraints_lb`` / ``constraints_ub``
        and apply current block bounds before each ``milp`` call.
        """
        extra_rows: List[Tuple[List[Tuple[int, float]], float, float]] = []

        d_coefs = [(idx, 1.0) for idx in stage3.d_index.values()]
        if d_coefs:
            extra_rows.append((d_coefs, -math.inf, float(distortion_ub)))

        q_coefs = [(idx, 1.0) for idx in stage3.q_index.values()]
        if q_coefs:
            extra_rows.append((q_coefs, -math.inf, float(neutral_ub)))

        block_row_start = stage3.constraints.shape[0] + len(extra_rows)
        for block in self.release_blocks:
            entries = [
                (int(idx), float(coef))
                for idx, coef in zip(block.variable_indices, block.coefficients)
            ]
            extra_rows.append((entries, float(block.lb), float(block.ub)))

        stage4 = _append_rows(stage3, extra_rows)
        block_row_indices = tuple(
            block_row_start + offset for offset in range(len(self.release_blocks))
        )
        return stage4, block_row_indices


def _append_rows(
    stage: StageConstraintSet,
    extra_rows: Sequence[Tuple[Sequence[Tuple[int, float]], float, float]],
) -> StageConstraintSet:
    """Return a new stage set with additional sparse rows appended."""
    if not extra_rows:
        return stage
    builder = _RowBuilder(stage.n_vars)
    builder.extend_from_csc(
        stage.constraints,
        stage.constraints_lb,
        stage.constraints_ub,
    )
    for entries, lb_val, ub_val in extra_rows:
        builder.push(entries, lb_val, ub_val)
    constraints, row_lb, row_ub = builder.build_csc()
    return StageConstraintSet(
        n_vars=stage.n_vars,
        objective=stage.objective.copy(),
        integrality=stage.integrality.copy(),
        bounds_lb=stage.bounds_lb.copy(),
        bounds_ub=stage.bounds_ub.copy(),
        constraints=constraints,
        constraints_lb=row_lb,
        constraints_ub=row_ub,
        d_index=dict(stage.d_index),
        q_index=dict(stage.q_index),
    )


class _RowBuilder:
    """Accumulate sparse triplets and emit one CSC matrix."""

    def __init__(self, n_vars: int) -> None:
        self.n_vars = n_vars
        self._data: List[float] = []
        self._indices: List[int] = []
        self._indptr: List[int] = [0]
        self._lb: List[float] = []
        self._ub: List[float] = []
        self.max_primary_nnz = 0
        self.max_witness_nnz = 0
        self.mean_weight_rows = 0
        self.primary_rows = 0
        self.witness_rows = 0

    def push(
        self,
        entries: Sequence[Tuple[int, float]],
        lb_val: float,
        ub_val: float,
        *,
        family: Optional[str] = None,
    ) -> None:
        aggregated: Dict[int, float] = {}
        for col, value in entries:
            if value == 0.0:
                continue
            aggregated[col] = aggregated.get(col, 0.0) + float(value)
        ordered = sorted(col for col, value in aggregated.items() if value != 0.0)
        for col in ordered:
            self._indices.append(col)
            self._data.append(aggregated[col])
        nnz = len(ordered)
        self._indptr.append(len(self._indices))
        self._lb.append(float(lb_val))
        self._ub.append(float(ub_val))
        if family == "primary":
            self.primary_rows += 1
            self.max_primary_nnz = max(self.max_primary_nnz, nnz)
        elif family == "witness":
            self.witness_rows += 1
            self.max_witness_nnz = max(self.max_witness_nnz, nnz)
        elif family == "mean_weight":
            self.mean_weight_rows += 1

    def extend_from_csc(
        self,
        matrix: csc_array,
        row_lb: np.ndarray,
        row_ub: np.ndarray,
    ) -> None:
        csr = matrix.tocsr()
        for row in range(csr.shape[0]):
            start = int(csr.indptr[row])
            end = int(csr.indptr[row + 1])
            entries = [
                (int(csr.indices[pos]), float(csr.data[pos]))
                for pos in range(start, end)
            ]
            self.push(entries, float(row_lb[row]), float(row_ub[row]))

    def build_csc(self) -> Tuple[csc_array, np.ndarray, np.ndarray]:
        n_rows = len(self._lb)
        # Triplets are accumulated in CSR order; convert once to CSC.
        csr = csr_array(
            (np.asarray(self._data), np.asarray(self._indices), np.asarray(self._indptr)),
            shape=(n_rows, self.n_vars),
        )
        matrix = csc_array(csr)
        row_lb = np.asarray(self._lb, dtype=float)
        row_ub = np.asarray(self._ub, dtype=float)
        # Free intermediate Python lists after CSC construction.
        self._data = []
        self._indices = []
        self._indptr = [0]
        self._lb = []
        self._ub = []
        del csr
        return matrix, row_lb, row_ub


def effective_cap(max_concentration: float) -> float:
    return float(max_concentration) + COMPARISON_EPSILON - _MILP_NUMERIC_BUFFER


def effective_threshold(threshold: float) -> float:
    return float(threshold) - COMPARISON_EPSILON + _MILP_NUMERIC_BUFFER


def normalized_shares(
    volumes: Mapping[str, float],
    peers: Sequence[str],
) -> Dict[str, float]:
    aligned = {peer: float(volumes.get(peer, 0.0)) for peer in peers}
    total = float(sum(aligned.values()))
    if total <= 0.0:
        raise ValueError("normalized shares require a positive total volume")
    return {peer: aligned[peer] / total for peer in peers}


def interval_min(
    coefficients: Mapping[str, float],
    min_weight: float,
    max_weight: float,
) -> float:
    total = 0.0
    for _peer, coef in coefficients.items():
        if coef >= 0.0:
            total += coef * min_weight
        else:
            total += coef * max_weight
    return total


def interval_max(
    coefficients: Mapping[str, float],
    min_weight: float,
    max_weight: float,
) -> float:
    total = 0.0
    for _peer, coef in coefficients.items():
        if coef >= 0.0:
            total += coef * max_weight
        else:
            total += coef * min_weight
    return total


def primary_expression_coefficients(
    fractions: Mapping[str, float],
    peer: str,
    cap_eff: float,
) -> Dict[str, float]:
    """Expanded g = cap*b - 100*f_p*w_p with b substituted."""
    coefficients: Dict[str, float] = {}
    for name, frac in fractions.items():
        if frac == 0.0:
            continue
        if name == peer:
            coefficients[name] = (cap_eff - 100.0) * frac
        else:
            coefficients[name] = cap_eff * frac
    return coefficients


def secondary_expression_coefficients(
    fractions: Mapping[str, float],
    peer: str,
    tau_eff: float,
) -> Dict[str, float]:
    """Expanded h = 100*f_p*w_p - tau*b with b substituted."""
    coefficients: Dict[str, float] = {}
    for name, frac in fractions.items():
        if frac == 0.0:
            continue
        if name == peer:
            coefficients[name] = (100.0 - tau_eff) * frac
        else:
            coefficients[name] = -tau_eff * frac
    return coefficients


def citi_expression_coefficients(
    fractions: Mapping[str, float],
    citi_peer: str,
) -> Dict[str, float]:
    """Expanded g = 25*b - 100*f_citi*w_citi with b substituted."""
    coefficients: Dict[str, float] = {}
    for name, frac in fractions.items():
        if frac == 0.0:
            continue
        if name == citi_peer:
            coefficients[name] = (25.0 - 100.0) * frac
        else:
            coefficients[name] = 25.0 * frac
    return coefficients


def classify_primary_cap(
    fractions: Mapping[str, float],
    peer: str,
    cap_eff: float,
    min_weight: float,
    max_weight: float,
) -> PrimaryClass:
    coefs = primary_expression_coefficients(fractions, peer, cap_eff)
    if interval_min(coefs, min_weight, max_weight) >= 0.0:
        return PrimaryClass.ALWAYS_PASS
    if interval_max(coefs, min_weight, max_weight) < 0.0:
        return PrimaryClass.NEVER_PASS
    return PrimaryClass.UNCERTAIN


def classify_secondary_witness(
    fractions: Mapping[str, float],
    peer: str,
    tau_eff: float,
    min_weight: float,
    max_weight: float,
) -> WitnessClass:
    coefs = secondary_expression_coefficients(fractions, peer, tau_eff)
    if interval_min(coefs, min_weight, max_weight) >= 0.0:
        return WitnessClass.ALWAYS_TRUE
    if interval_max(coefs, min_weight, max_weight) < 0.0:
        return WitnessClass.IMPOSSIBLE
    return WitnessClass.UNCERTAIN


def classify_citi_row(
    fractions: Mapping[str, float],
    citi_peer: str,
    min_weight: float,
    max_weight: float,
) -> PrimaryClass:
    if fractions.get(citi_peer, 0.0) <= 0.0:
        return PrimaryClass.ALWAYS_PASS
    coefs = citi_expression_coefficients(fractions, citi_peer)
    if interval_min(coefs, min_weight, max_weight) >= 0.0:
        return PrimaryClass.ALWAYS_PASS
    if interval_max(coefs, min_weight, max_weight) < 0.0:
        return PrimaryClass.NEVER_PASS
    return PrimaryClass.UNCERTAIN


def rule_dominates(rule_a: CoverageRuleView, rule_b: CoverageRuleView) -> bool:
    """Return True when A is always easier than B under the conservative test."""
    if rule_a.secondary_tiers:
        return False
    if rule_a.min_entities > rule_b.min_entities:
        return False
    if rule_a.max_concentration < rule_b.max_concentration:
        return False
    strict = (
        rule_a.min_entities < rule_b.min_entities
        or rule_a.max_concentration > rule_b.max_concentration
        or bool(rule_b.secondary_tiers)
    )
    return strict


def dominate_rules(
    rule_names: Sequence[str],
    rules: Mapping[str, CoverageRuleView],
) -> Tuple[Tuple[str, ...], Tuple[str, ...]]:
    """Return (retained, removed) after conservative dominance pruning."""
    ordered = tuple(canonical_order(rule_names))
    removed: List[str] = []
    retained: List[str] = []
    for candidate in ordered:
        rule_b = rules[candidate]
        dominated = any(
            other != candidate and rule_dominates(rules[other], rule_b)
            for other in ordered
        )
        if dominated:
            removed.append(candidate)
        else:
            retained.append(candidate)
    return tuple(retained), tuple(removed)


def _resolve_citi_peer(
    peers: Sequence[str],
    citibank_entity_name: Optional[str],
    units: Sequence[Mapping[str, Any]],
) -> Optional[str]:
    needs = any(CITIBANK_OVERLAY_NAME in tuple(unit.get("overlays", ())) for unit in units)
    if not needs:
        return None
    if not citibank_entity_name:
        raise ValueError(
            "citibank_entity_name is required when a unit carries the citibank overlay"
        )
    needle = citibank_entity_name.casefold()
    matches = [peer for peer in peers if peer.casefold() == needle]
    if len(matches) != 1:
        raise ValueError("citibank peer identity must exist exactly once in peers")
    return matches[0]


def _prepare_normalized_units(
    units: Sequence[Mapping[str, Any]],
    peers: Sequence[str],
) -> List[Dict[str, Any]]:
    prepared: List[Dict[str, Any]] = []
    for unit in units:
        metrics: List[Dict[str, Any]] = []
        for record in unit["metrics"]:
            aligned = {
                peer: float(record["aligned_volumes"].get(peer, 0.0)) for peer in peers
            }
            total = float(record.get("total", sum(aligned.values())))
            if total <= 0.0:
                raise ValueError(
                    f"unit {unit['key']!r} metric {record['metric']!r} has zero total"
                )
            fractions = {peer: aligned[peer] / total for peer in peers}
            positive = tuple(
                peer for peer in peers if aligned[peer] > 0.0
            )
            if "positive_peers" in record:
                positive = tuple(record["positive_peers"])
            metrics.append(
                {
                    "metric": str(record["metric"]),
                    "aligned_volumes": aligned,
                    "total": total,
                    "fractions": fractions,
                    "positive_peers": positive,
                }
            )
        metrics.sort(key=lambda item: canonical_key(item["metric"]))
        prepared.append(
            {
                "key": str(unit["key"]),
                "metrics": metrics,
                "rules": tuple(unit["rules"]),
                "overlays": tuple(unit.get("overlays", ())),
            }
        )
    prepared.sort(key=lambda item: canonical_key(item["key"]))
    return prepared


def _plan_unit_rules(
    unit: Mapping[str, Any],
    rules: Mapping[str, CoverageRuleView],
    *,
    min_weight: float,
    max_weight: float,
    citi_peer: Optional[str],
    enable_rule_dominance: bool,
    enable_structural_presolve: bool,
) -> Dict[str, Any]:
    applicable = tuple(unit["rules"])
    pruned_rule_count = 0
    if enable_rule_dominance:
        retained, removed = dominate_rules(applicable, rules)
        pruned_rule_count = len(removed)
    else:
        retained = tuple(canonical_order(applicable))

    active_rules: List[str] = []
    rule_plans: Dict[str, Dict[str, Any]] = {}
    always_true_total = 0
    impossible_total = 0

    for rule_name in retained:
        rule = rules[rule_name]
        disabled = False
        # Structural participant minimum.
        for metric in unit["metrics"]:
            if len(metric["positive_peers"]) < rule.min_entities:
                disabled = True
                break

        primary_peers: Dict[str, List[str]] = {}
        if not disabled and enable_structural_presolve:
            for metric in unit["metrics"]:
                metric_name = str(metric["metric"])
                fractions = metric["fractions"]
                cap_eff = effective_cap(rule.max_concentration)
                keep_peers: List[str] = []
                for peer in metric["positive_peers"]:
                    classification = classify_primary_cap(
                        fractions, peer, cap_eff, min_weight, max_weight
                    )
                    if classification is PrimaryClass.NEVER_PASS:
                        disabled = True
                        break
                    if classification is PrimaryClass.UNCERTAIN:
                        keep_peers.append(str(peer))
                primary_peers[metric_name] = keep_peers
                if disabled:
                    break
        elif not disabled:
            for metric in unit["metrics"]:
                primary_peers[str(metric["metric"])] = [
                    str(peer) for peer in metric["positive_peers"]
                ]

        tier_plans: List[Dict[str, Any]] = []
        if not disabled:
            for tier_i, (required_count, threshold) in enumerate(rule.secondary_tiers):
                tau = effective_threshold(threshold)
                per_metric: Dict[str, Dict[str, Any]] = {}
                for metric in unit["metrics"]:
                    metric_name = str(metric["metric"])
                    fractions = metric["fractions"]
                    uncertain: List[str] = []
                    always_true = 0
                    impossible = 0
                    for peer in metric["positive_peers"]:
                        if enable_structural_presolve:
                            witness_class = classify_secondary_witness(
                                fractions, str(peer), tau, min_weight, max_weight
                            )
                        else:
                            witness_class = WitnessClass.UNCERTAIN
                        if witness_class is WitnessClass.ALWAYS_TRUE:
                            always_true += 1
                            always_true_total += 1
                        elif witness_class is WitnessClass.IMPOSSIBLE:
                            impossible += 1
                            impossible_total += 1
                        else:
                            uncertain.append(str(peer))
                    remaining = int(required_count) - always_true
                    if remaining < 0:
                        remaining = 0
                    if remaining > len(uncertain):
                        disabled = True
                    per_metric[metric_name] = {
                        "uncertain_peers": tuple(uncertain),
                        "always_true": always_true,
                        "impossible": impossible,
                        "required_remaining": remaining,
                        "required_count": int(required_count),
                        "tau": tau,
                    }
                if disabled:
                    break
                tier_plans.append(
                    {
                        "tier_index": tier_i,
                        "required_count": int(required_count),
                        "threshold": float(threshold),
                        "per_metric": per_metric,
                    }
                )

        if disabled:
            rule_plans[rule_name] = {
                "active": False,
                "primary_peers": {},
                "tiers": [],
            }
            continue

        active_rules.append(rule_name)
        rule_plans[rule_name] = {
            "active": True,
            "primary_peers": primary_peers,
            "tiers": tier_plans,
        }

    # Citi overlay structural classification.
    citi_rows: List[Dict[str, Any]] = []
    release_disabled = not active_rules
    if CITIBANK_OVERLAY_NAME in unit["overlays"] and citi_peer is not None:
        for metric in unit["metrics"]:
            fractions = metric["fractions"]
            if fractions.get(citi_peer, 0.0) <= 0.0:
                continue
            if enable_structural_presolve:
                classification = classify_citi_row(
                    fractions, citi_peer, min_weight, max_weight
                )
            else:
                classification = PrimaryClass.UNCERTAIN
            if classification is PrimaryClass.NEVER_PASS:
                release_disabled = True
                citi_rows = []
                break
            if classification is PrimaryClass.UNCERTAIN:
                citi_rows.append(
                    {
                        "metric": str(metric["metric"]),
                        "fractions": fractions,
                    }
                )

    return {
        "key": unit["key"],
        "active_rules": tuple(active_rules),
        "rule_plans": rule_plans,
        "citi_rows": citi_rows,
        "release_disabled": release_disabled,
        "pruned_rule_count": pruned_rule_count,
        "always_true_witness_count": always_true_total,
        "impossible_witness_count": impossible_total,
        "overlays": unit["overlays"],
    }


def compile_coverage_model(
    units: Sequence[Mapping[str, Any]],
    peers: Sequence[str],
    *,
    min_weight: float,
    max_weight: float,
    rules: Mapping[str, CoverageRuleView],
    citibank_entity_name: Optional[str] = None,
    enable_rule_dominance: bool = True,
    enable_structural_presolve: bool = True,
) -> CoverageModel:
    """Compile the normalized Stage-1 coverage model and stage extension hooks."""
    if not math.isfinite(min_weight) or min_weight <= 0.0:
        raise ValueError("min_weight must be a positive finite value")
    if not math.isfinite(max_weight) or max_weight < min_weight:
        raise ValueError("max_weight must be finite and at least min_weight")
    peer_tuple = tuple(canonical_order(peers))
    if not peer_tuple or len(set(peers)) != len(peers):
        raise ValueError("peers must be a non-empty sequence of distinct identities")

    normalized = _prepare_normalized_units(units, peer_tuple)
    citi_peer = _resolve_citi_peer(peer_tuple, citibank_entity_name, normalized)

    unit_plans = [
        _plan_unit_rules(
            unit,
            rules,
            min_weight=min_weight,
            max_weight=max_weight,
            citi_peer=citi_peer,
            enable_rule_dominance=enable_rule_dominance,
            enable_structural_presolve=enable_structural_presolve,
        )
        for unit in normalized
    ]

    # Variable allocation (Stage 1 only).
    w_index = {peer: index for index, peer in enumerate(peer_tuple)}
    offset = len(peer_tuple)

    b_index: Dict[Tuple[str, str], int] = {}
    for unit in normalized:
        for metric in unit["metrics"]:
            b_index[(str(unit["key"]), str(metric["metric"]))] = offset
            offset += 1

    r_index: Dict[str, int] = {}
    for plan in unit_plans:
        r_index[str(plan["key"])] = offset
        offset += 1

    y_index: Dict[Tuple[str, str], int] = {}
    for plan in unit_plans:
        for rule_name in plan["active_rules"]:
            y_index[(str(plan["key"]), str(rule_name))] = offset
            offset += 1
        # Keep inactive retained? No — only allocate y for active rules.
        # Dominated/disabled rules are omitted entirely.

    z_index: Dict[Tuple[str, str, str, int, str], int] = {}
    for plan in unit_plans:
        unit_key = str(plan["key"])
        for rule_name in plan["active_rules"]:
            rule_plan = plan["rule_plans"][rule_name]
            for tier in rule_plan["tiers"]:
                tier_i = int(tier["tier_index"])
                for metric_name, metric_tier in tier["per_metric"].items():
                    for peer in metric_tier["uncertain_peers"]:
                        z_index[
                            (unit_key, str(metric_name), str(rule_name), tier_i, str(peer))
                        ] = offset
                        offset += 1

    n_vars = offset
    integrality = np.zeros(n_vars, dtype=int)
    bounds_lb = np.zeros(n_vars, dtype=float)
    bounds_ub = np.zeros(n_vars, dtype=float)

    for peer, idx in w_index.items():
        bounds_lb[idx] = min_weight
        bounds_ub[idx] = max_weight

    for idx in b_index.values():
        bounds_lb[idx] = min_weight
        bounds_ub[idx] = max_weight

    for plan in unit_plans:
        idx = r_index[str(plan["key"])]
        integrality[idx] = 1
        bounds_lb[idx] = 0.0
        bounds_ub[idx] = 0.0 if plan["release_disabled"] else 1.0

    for idx in y_index.values():
        integrality[idx] = 1
        bounds_lb[idx] = 0.0
        bounds_ub[idx] = 1.0

    for idx in z_index.values():
        integrality[idx] = 1
        bounds_lb[idx] = 0.0
        bounds_ub[idx] = 1.0

    builder = _RowBuilder(n_vars)

    # Mean-weight equalities: b - sum_p f_p w_p = 0.
    for unit in normalized:
        unit_key = str(unit["key"])
        for metric in unit["metrics"]:
            metric_name = str(metric["metric"])
            b_idx = b_index[(unit_key, metric_name)]
            entries: List[Tuple[int, float]] = [(b_idx, 1.0)]
            for peer in peer_tuple:
                frac = float(metric["fractions"][peer])
                if frac != 0.0:
                    entries.append((w_index[peer], -frac))
            builder.push(entries, 0.0, 0.0, family="mean_weight")

    # Rule selection: sum_r y = r.
    for plan in unit_plans:
        unit_key = str(plan["key"])
        entries = [(r_index[unit_key], -1.0)]
        for rule_name in plan["active_rules"]:
            entries.append((y_index[(unit_key, rule_name)], 1.0))
        if plan["active_rules"] or not plan["release_disabled"]:
            builder.push(entries, 0.0, 0.0)
        elif plan["release_disabled"] and not plan["active_rules"]:
            # r is fixed at 0 via bounds; still add empty equality r=0 via bounds.
            pass

    # Primary cap rows (sparse, at most 3 variable coefficients).
    for plan, unit in zip(unit_plans, normalized):
        unit_key = str(plan["key"])
        for rule_name in plan["active_rules"]:
            rule = rules[rule_name]
            rule_plan = plan["rule_plans"][rule_name]
            cap_eff = effective_cap(rule.max_concentration)
            y_idx = y_index[(unit_key, rule_name)]
            for metric in unit["metrics"]:
                metric_name = str(metric["metric"])
                fractions = metric["fractions"]
                b_idx = b_index[(unit_key, metric_name)]
                for peer in rule_plan["primary_peers"].get(metric_name, ()):
                    peer_s = str(peer)
                    # Expanded big-M from complete expression.
                    coefs = primary_expression_coefficients(fractions, peer_s, cap_eff)
                    big_m = max(0.0, -interval_min(coefs, min_weight, max_weight))
                    # cap*b - 100*f_p*w_p - M*y >= -M
                    entries = [
                        (b_idx, cap_eff),
                        (w_index[peer_s], -100.0 * fractions[peer_s]),
                        (y_idx, -big_m),
                    ]
                    builder.push(entries, -big_m, math.inf, family="primary")

    # Secondary witnesses, z<=y, and tier counts.
    for plan, unit in zip(unit_plans, normalized):
        unit_key = str(plan["key"])
        for rule_name in plan["active_rules"]:
            rule_plan = plan["rule_plans"][rule_name]
            y_idx = y_index[(unit_key, rule_name)]
            for tier in rule_plan["tiers"]:
                tier_i = int(tier["tier_index"])
                for metric in unit["metrics"]:
                    metric_name = str(metric["metric"])
                    metric_tier = tier["per_metric"][metric_name]
                    fractions = metric["fractions"]
                    b_idx = b_index[(unit_key, metric_name)]
                    tau = float(metric_tier["tau"])
                    uncertain = metric_tier["uncertain_peers"]
                    for peer in uncertain:
                        peer_s = str(peer)
                        coefs = secondary_expression_coefficients(fractions, peer_s, tau)
                        big_m = max(0.0, -interval_min(coefs, min_weight, max_weight))
                        z_idx = z_index[(unit_key, metric_name, rule_name, tier_i, peer_s)]
                        # 100*f_p*w_p - tau*b - M*z >= -M
                        entries = [
                            (w_index[peer_s], 100.0 * fractions[peer_s]),
                            (b_idx, -tau),
                            (z_idx, -big_m),
                        ]
                        builder.push(entries, -big_m, math.inf, family="witness")
                        # z <= y
                        builder.push([(z_idx, 1.0), (y_idx, -1.0)], -math.inf, 0.0)

                    # sum(z) + always_true >= required * y
                    # => sum(z) - required*y >= -always_true
                    always_true = int(metric_tier["always_true"])
                    required = int(metric_tier["required_count"])
                    entries = [
                        (
                            z_index[(unit_key, metric_name, rule_name, tier_i, str(peer))],
                            1.0,
                        )
                        for peer in uncertain
                    ]
                    entries.append((y_idx, -float(required)))
                    builder.push(entries, -float(always_true), math.inf)

    # Citi overlay rows conditioned on r.
    if citi_peer is not None:
        for plan, unit in zip(unit_plans, normalized):
            if CITIBANK_OVERLAY_NAME not in plan["overlays"]:
                continue
            unit_key = str(plan["key"])
            r_idx = r_index[unit_key]
            for citi_row in plan["citi_rows"]:
                metric_name = str(citi_row["metric"])
                fractions = citi_row["fractions"]
                b_idx = b_index[(unit_key, metric_name)]
                coefs = citi_expression_coefficients(fractions, citi_peer)
                big_m = max(0.0, -interval_min(coefs, min_weight, max_weight))
                # 25*b - 100*f_citi*w_citi - M*r >= -M
                entries = [
                    (b_idx, 25.0),
                    (w_index[citi_peer], -100.0 * float(fractions[citi_peer])),
                    (r_idx, -big_m),
                ]
                builder.push(entries, -big_m, math.inf, family="primary")

    constraints, row_lb, row_ub = builder.build_csc()

    objective = np.zeros(n_vars, dtype=float)
    for plan in unit_plans:
        objective[r_index[str(plan["key"])]] = -1.0

    stage1 = StageConstraintSet(
        n_vars=n_vars,
        objective=objective,
        integrality=integrality,
        bounds_lb=bounds_lb,
        bounds_ub=bounds_ub,
        constraints=constraints,
        constraints_lb=row_lb,
        constraints_ub=row_ub,
    )

    # Stage-4 release blocks over canonical release variables.
    release_indices = tuple(
        r_index[str(plan["key"])]
        for plan in sorted(unit_plans, key=lambda item: canonical_key(item["key"]))
    )
    blocks: List[ReleaseBlock] = []
    for start in range(0, len(release_indices), _RELEASE_BLOCK_SIZE):
        chunk = release_indices[start : start + _RELEASE_BLOCK_SIZE]
        n = len(chunk)
        coefficients = tuple(float(2 ** (n - 1 - position)) for position in range(n))
        blocks.append(ReleaseBlock(variable_indices=chunk, coefficients=coefficients))

    pruned_rule_count = sum(int(plan["pruned_rule_count"]) for plan in unit_plans)
    always_true_witness_count = sum(
        int(plan["always_true_witness_count"]) for plan in unit_plans
    )
    impossible_witness_count = sum(
        int(plan["impossible_witness_count"]) for plan in unit_plans
    )
    metric_count = len(
        {str(metric["metric"]) for unit in normalized for metric in unit["metrics"]}
    )
    integer_variable_count = int(np.sum(integrality))

    statistics = CoverageModelStatistics(
        unit_count=len(normalized),
        peer_count=len(peer_tuple),
        metric_count=metric_count,
        variable_count=n_vars,
        integer_variable_count=integer_variable_count,
        row_count=int(constraints.shape[0]),
        nonzero_count=int(constraints.nnz),
        max_primary_row_nonzeros=builder.max_primary_nnz,
        max_witness_row_nonzeros=builder.max_witness_nnz,
        mean_weight_row_count=builder.mean_weight_rows,
        pruned_rule_count=pruned_rule_count,
        always_true_witness_count=always_true_witness_count,
        impossible_witness_count=impossible_witness_count,
    )

    return CoverageModel(
        peers=peer_tuple,
        min_weight=float(min_weight),
        max_weight=float(max_weight),
        w_index=w_index,
        b_index=b_index,
        r_index=r_index,
        y_index=y_index,
        z_index=z_index,
        stage1=stage1,
        statistics=statistics,
        release_blocks=tuple(blocks),
        _unit_plans=tuple(unit_plans),
        _normalized=tuple(normalized),
        _citi_peer=citi_peer,
    )


__all__ = [
    "CoverageModel",
    "CoverageModelStatistics",
    "CoverageRuleView",
    "PrimaryClass",
    "ReleaseBlock",
    "StageConstraintSet",
    "WitnessClass",
    "citi_expression_coefficients",
    "classify_citi_row",
    "classify_primary_cap",
    "classify_secondary_witness",
    "compile_coverage_model",
    "dominate_rules",
    "effective_cap",
    "effective_threshold",
    "interval_max",
    "interval_min",
    "normalized_shares",
    "primary_expression_coefficients",
    "rule_dominates",
    "secondary_expression_coefficients",
]
