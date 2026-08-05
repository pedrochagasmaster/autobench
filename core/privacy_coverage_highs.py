"""Direct highspy adapter and complete neutral MIP start for Verified Safe Coverage.

Internal Module. Consumes ``StageConstraintSet`` / ``CoverageModel`` from
``core.privacy_coverage_model`` without changing public solver contracts.

Do not export this Module from ``core.__init__``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, List, Mapping, Optional, Sequence, Tuple, cast

import numpy as np
from highspy import (
    Highs,
    HighsModel,
    HighsModelStatus,
    HighsSolution,
    HighsStatus,
    HighsVarType,
    MatrixFormat,
    ObjSense,
    SolutionStatus,
    kHighsInf,
    kSolutionStatusFeasible,
    kSolutionStatusInfeasible,
    kSolutionStatusNone,
)
from highspy._core.cb import (
    HighsCallbackType,
    kCallbackMipImprovingSolution,
    kCallbackMipLogging,
)
from scipy.sparse import csc_array

from core.constants import COMPARISON_EPSILON
from core.privacy_coverage import CITIBANK_OVERLAY_NAME
from core.privacy_coverage_model import (
    CoverageModel,
    StageConstraintSet,
    effective_threshold,
)
from core.privacy_coverage_solver import weighted_shares
from core.privacy_rules import evaluate_rule

__all__ = [
    "HighsCoverageSession",
    "HighsCoverageSolveResult",
    "HighsProgressEvent",
    "NeutralMipStartError",
    "apply_proof_contract",
    "build_neutral_mip_start",
    "map_highs_model_status",
    "validate_start_against_stage",
]

# Mirror existing solver state strings in ``core.privacy_coverage_solver``.
_STATE_OPTIMAL = "optimal"
_STATE_INFEASIBLE = "infeasible"
_STATE_UNBOUNDED = "unbounded"
_STATE_TIME_LIMIT = "time_limit"
_STATE_ITERATION_LIMIT = "iteration_limit"
_STATE_ERROR = "solver_error"
_STATE_UNPROVEN = "limit_reached"

# Match ``core.privacy_coverage_solver`` read-back / feasibility scale.
_FEASIBILITY_TOLERANCE = 1e-6
_INTEGRALITY_READBACK_TOLERANCE = 1e-6

_CITIBANK_MAXIMUM_SHARE = 25.0


class NeutralMipStartError(ValueError):
    """Raised when a complete MIP start fails local bound or row validation."""


@dataclass(frozen=True)
class HighsProgressEvent:
    """Safe numeric MIP progress snapshot (no identifiers or protected values)."""

    elapsed_seconds: float
    node_count: int
    primal_bound: float
    dual_bound: float
    mip_gap: float


@dataclass(frozen=True)
class HighsCoverageSolveResult:
    """Typed internal HiGHS solve result without raw highspy objects."""

    model_status: str
    primal_solution_status: str
    column_values: np.ndarray
    objective_value: float
    mip_primal_bound: float
    mip_dual_bound: float
    mip_gap: float
    max_primal_infeasibility: float
    max_integrality_violation: float
    node_count: int
    run_time: float
    first_verified_incumbent_time: Optional[float]


def _require_ok(status: HighsStatus, action: str) -> None:
    if status == HighsStatus.kError:
        raise RuntimeError(f"HiGHS {action} failed with HighsStatus.kError")
    # kOk and kWarning are accepted; warnings are not fatal.


def _to_highs_bound(value: float) -> float:
    if not math.isfinite(value):
        return float(kHighsInf) if value > 0.0 else float(-kHighsInf)
    return float(value)


def _map_primal_solution_status(raw: Any) -> str:
    try:
        code = int(raw)
    except (TypeError, ValueError):
        return "none"
    if code == int(kSolutionStatusFeasible) or raw == SolutionStatus.kSolutionStatusFeasible:
        return "feasible"
    if (
        code == int(kSolutionStatusInfeasible)
        or raw == SolutionStatus.kSolutionStatusInfeasible
    ):
        return "infeasible"
    if code == int(kSolutionStatusNone) or raw == SolutionStatus.kSolutionStatusNone:
        return "none"
    return "none"


def map_highs_model_status(status: HighsModelStatus) -> str:
    """Map a HiGHS model status to an existing solver state string (pre-proof)."""
    if status == HighsModelStatus.kOptimal:
        return _STATE_OPTIMAL
    if status == HighsModelStatus.kInfeasible:
        return _STATE_INFEASIBLE
    if status == HighsModelStatus.kUnbounded:
        return _STATE_UNBOUNDED
    if status == HighsModelStatus.kTimeLimit:
        return _STATE_TIME_LIMIT
    if status == HighsModelStatus.kIterationLimit:
        return _STATE_ITERATION_LIMIT
    interrupt_statuses = {
        HighsModelStatus.kInterrupt,
        HighsModelStatus.kUnknown,
        HighsModelStatus.kUnboundedOrInfeasible,
        HighsModelStatus.kLoadError,
        HighsModelStatus.kModelError,
        HighsModelStatus.kPresolveError,
        HighsModelStatus.kSolveError,
        HighsModelStatus.kPostsolveError,
        HighsModelStatus.kModelEmpty,
        HighsModelStatus.kNotset,
    }
    # Present in highspy 1.15 runtime; stubs may omit the alias.
    highs_interrupt = getattr(HighsModelStatus, "kHighsInterrupt", None)
    if highs_interrupt is not None:
        interrupt_statuses.add(highs_interrupt)
    if status in interrupt_statuses:
        return _STATE_ERROR
    # Feasible-but-unproven and resource limits fail closed as unproven.
    if status in (
        HighsModelStatus.kObjectiveBound,
        HighsModelStatus.kObjectiveTarget,
        HighsModelStatus.kSolutionLimit,
        HighsModelStatus.kMemoryLimit,
    ):
        return _STATE_UNPROVEN
    return _STATE_ERROR


def apply_proof_contract(
    *,
    raw_model_status: str,
    mapped_status: str,
    objective_value: Optional[float],
    mip_primal_bound: Optional[float],
    mip_dual_bound: Optional[float],
    mip_gap: Optional[float],
    max_primal_infeasibility: Optional[float],
    max_integrality_violation: Optional[float],
    feasibility_tolerance: float = _FEASIBILITY_TOLERANCE,
    integrality_tolerance: float = _INTEGRALITY_READBACK_TOLERANCE,
    require_mip_proof_fields: bool = True,
) -> str:
    """Return the fail-closed solver state after applying the Plan 004 proof gate.

    Pure continuous models set ``require_mip_proof_fields=False`` because HiGHS
    leaves MIP gap / integrality fields non-finite after an LP solve.
    """
    if mapped_status != _STATE_OPTIMAL or raw_model_status != "kOptimal":
        return mapped_status if mapped_status != _STATE_OPTIMAL else _STATE_UNPROVEN

    if objective_value is None or max_primal_infeasibility is None:
        return _STATE_UNPROVEN
    if not math.isfinite(float(objective_value)):
        return _STATE_UNPROVEN
    if not math.isfinite(float(max_primal_infeasibility)):
        return _STATE_UNPROVEN
    if float(max_primal_infeasibility) > feasibility_tolerance:
        return _STATE_UNPROVEN

    if not require_mip_proof_fields:
        return _STATE_OPTIMAL

    if mip_primal_bound is None or mip_dual_bound is None or mip_gap is None:
        return _STATE_UNPROVEN
    if max_integrality_violation is None:
        return _STATE_UNPROVEN
    for value in (mip_primal_bound, mip_dual_bound, mip_gap, max_integrality_violation):
        if not math.isfinite(float(value)):
            return _STATE_UNPROVEN

    if float(mip_gap) != 0.0:
        return _STATE_UNPROVEN
    if float(objective_value) != float(mip_dual_bound):
        return _STATE_UNPROVEN
    if float(max_integrality_violation) > integrality_tolerance:
        return _STATE_UNPROVEN
    return _STATE_OPTIMAL


def validate_start_against_stage(
    stage: StageConstraintSet,
    column_values: np.ndarray,
    *,
    feasibility_tolerance: float = _FEASIBILITY_TOLERANCE,
) -> None:
    """Reject a start vector that violates bounds or rows beyond tolerance."""
    x_vec = np.asarray(column_values, dtype=float)
    if x_vec.shape != (stage.n_vars,):
        raise NeutralMipStartError(
            f"start length {x_vec.shape} does not match n_vars={stage.n_vars}"
        )
    if not np.all(np.isfinite(x_vec)):
        raise NeutralMipStartError("start contains non-finite values")

    below = x_vec < stage.bounds_lb - feasibility_tolerance
    above = x_vec > stage.bounds_ub + feasibility_tolerance
    if np.any(below) or np.any(above):
        raise NeutralMipStartError("start violates variable bounds")

    if stage.constraints.shape[0] == 0:
        return
    row_values = stage.constraints @ x_vec
    row_lb = stage.constraints_lb
    row_ub = stage.constraints_ub
    low_viol = row_values < row_lb - feasibility_tolerance
    high_viol = row_values > row_ub + feasibility_tolerance
    # Infinite bounds never violate.
    low_viol = np.logical_and(low_viol, np.isfinite(row_lb))
    high_viol = np.logical_and(high_viol, np.isfinite(row_ub))
    if np.any(low_viol) or np.any(high_viol):
        raise NeutralMipStartError("start violates model rows")


def build_neutral_mip_start(
    model: CoverageModel,
    unit_data: Sequence[Mapping[str, Any]],
    *,
    rule_configs: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> np.ndarray:
    """Build a complete Stage-1 MIP start at neutral weights and validate rows.

    Every Stage-1 variable receives a value. Rule authorization reuses
    ``evaluate_rule`` / ``weighted_shares``. Witness bits use the model's
    effective-threshold encoding. The start is rejected (not repaired) when
    any bound or row fails local validation.
    """
    stage = model.stage1
    x_vec = np.zeros(stage.n_vars, dtype=float)
    configs = rule_configs or {}

    for peer in model.peers:
        x_vec[model.w_index[peer]] = 1.0

    unit_by_key = {str(unit["key"]): unit for unit in unit_data}
    normalized_by_key = {str(unit["key"]): unit for unit in model._normalized}
    citi_peer = model._citi_peer

    for unit in model._normalized:
        unit_key = str(unit["key"])
        for metric in unit["metrics"]:
            metric_name = str(metric["metric"])
            fractions = metric["fractions"]
            mean_weight = sum(
                float(fractions[peer]) * 1.0 for peer in model.peers
            )
            x_vec[model.b_index[(unit_key, metric_name)]] = float(mean_weight)

    for plan in model._unit_plans:
        unit_key = str(plan["key"])
        source = unit_by_key.get(unit_key) or normalized_by_key[unit_key]
        weights = {peer: 1.0 for peer in model.peers}

        citi_blocks_release = False
        if CITIBANK_OVERLAY_NAME in tuple(plan.get("overlays", ())) and citi_peer:
            for metric in source["metrics"]:
                volumes = metric["aligned_volumes"]
                if float(volumes.get(citi_peer, 0.0)) <= 0.0:
                    continue
                shares = weighted_shares(volumes, weights)
                if shares.get(citi_peer, 0.0) > _CITIBANK_MAXIMUM_SHARE + COMPARISON_EPSILON:
                    citi_blocks_release = True
                    break

        authorizing: Optional[str] = None
        if not plan["release_disabled"] and not citi_blocks_release:
            for rule_name in plan["active_rules"]:
                cfg = configs.get(str(rule_name))
                rule_config = dict(cfg) if cfg is not None else None
                passes = True
                for metric in source["metrics"]:
                    shares = weighted_shares(metric["aligned_volumes"], weights)
                    evaluation = evaluate_rule(
                        str(rule_name),
                        list(shares.values()),
                        rule_config=rule_config,
                    )
                    if not evaluation.strict_passed:
                        passes = False
                        break
                if passes:
                    authorizing = str(rule_name)
                    break

        release = 1.0 if authorizing is not None else 0.0
        # Honour compiled fixation (structurally impossible release).
        r_idx = model.r_index[unit_key]
        if stage.bounds_ub[r_idx] <= 0.0:
            release = 0.0
            authorizing = None
        x_vec[r_idx] = release

        for rule_name in plan["active_rules"]:
            y_idx = model.y_index[(unit_key, str(rule_name))]
            x_vec[y_idx] = 1.0 if authorizing == str(rule_name) else 0.0

        for rule_name in plan["active_rules"]:
            rule_plan = plan["rule_plans"][rule_name]
            y_selected = authorizing == str(rule_name)
            for tier in rule_plan["tiers"]:
                tier_i = int(tier["tier_index"])
                threshold = float(tier["threshold"])
                tau = effective_threshold(threshold)
                normalized_metrics = {
                    str(item["metric"]): item
                    for item in normalized_by_key[unit_key]["metrics"]
                }
                for metric in source["metrics"]:
                    metric_name = str(metric["metric"])
                    metric_tier = tier["per_metric"][metric_name]
                    frac_map = normalized_metrics[metric_name]["fractions"]
                    b_val = float(x_vec[model.b_index[(unit_key, metric_name)]])
                    for peer in metric_tier["uncertain_peers"]:
                        peer_s = str(peer)
                        z_idx = model.z_index[
                            (unit_key, metric_name, str(rule_name), tier_i, peer_s)
                        ]
                        # Model encoding: 100*f*w - tau*b >= 0 when z=1.
                        expression = 100.0 * float(frac_map[peer_s]) * 1.0 - tau * b_val
                        witness = expression >= -_FEASIBILITY_TOLERANCE
                        # z <= y: only selected rule may carry positive witnesses.
                        x_vec[z_idx] = 1.0 if (y_selected and witness) else 0.0

    validate_start_against_stage(stage, x_vec)
    return x_vec


class HighsCoverageSession:
    """Own one ``highspy.Highs`` instance for a single coverage solve stage."""

    def __init__(
        self,
        stage: StageConstraintSet,
        *,
        time_limit: Optional[float] = None,
        maximize: bool = False,
        threads: int = 1,
        mip_max_nodes: Optional[int] = None,
    ) -> None:
        self._stage = stage
        self._maximize = bool(maximize)
        self._constraint_matrix: csc_array = stage.constraints
        self._progress_events: List[HighsProgressEvent] = []
        self._first_verified_incumbent_time: Optional[float] = None
        self._highs = Highs()
        self._configure_options(
            time_limit=time_limit,
            threads=threads,
            mip_max_nodes=mip_max_nodes,
        )
        self._install_callbacks()
        self._load_model()

    @property
    def stage(self) -> StageConstraintSet:
        return self._stage

    @property
    def constraint_matrix(self) -> csc_array:
        """The CSC matrix object consumed by this session (no dense copy)."""
        return self._constraint_matrix

    @property
    def consumed_csc_indptr(self) -> np.ndarray:
        return self._constraint_matrix.indptr

    @property
    def consumed_csc_indices(self) -> np.ndarray:
        return self._constraint_matrix.indices

    @property
    def consumed_csc_data(self) -> np.ndarray:
        return self._constraint_matrix.data

    @property
    def progress_events(self) -> Tuple[HighsProgressEvent, ...]:
        return tuple(self._progress_events)

    @property
    def highs_version(self) -> str:
        return str(self._highs.version())

    def loaded_integrality_kinds(self) -> Tuple[str, ...]:
        """Return per-column integrality labels loaded into HiGHS."""
        kinds: List[str] = []
        for flag in self._stage.integrality:
            kinds.append("integer" if int(flag) != 0 else "continuous")
        return tuple(kinds)

    def _configure_options(
        self,
        *,
        time_limit: Optional[float],
        threads: int,
        mip_max_nodes: Optional[int],
    ) -> None:
        if threads < 1:
            raise ValueError("threads must be positive")
        if mip_max_nodes is not None and mip_max_nodes < 0:
            raise ValueError("mip_max_nodes must be non-negative")
        _require_ok(self._highs.setOptionValue("output_flag", False), "setOptionValue(output_flag)")
        _require_ok(self._highs.setOptionValue("mip_rel_gap", 0), "setOptionValue(mip_rel_gap)")
        _require_ok(self._highs.setOptionValue("mip_abs_gap", 0), "setOptionValue(mip_abs_gap)")
        _require_ok(self._highs.setOptionValue("random_seed", 0), "setOptionValue(random_seed)")
        _require_ok(
            self._highs.setOptionValue("threads", int(threads)),
            "setOptionValue(threads)",
        )
        if mip_max_nodes is not None:
            _require_ok(
                self._highs.setOptionValue("mip_max_nodes", int(mip_max_nodes)),
                "setOptionValue(mip_max_nodes)",
            )
        if time_limit is not None:
            _require_ok(
                self._highs.setOptionValue("time_limit", float(time_limit)),
                "setOptionValue(time_limit)",
            )

    def _install_callbacks(self) -> None:
        def _callback(
            cb_type: Any,
            _message: str,
            data_out: Any,
            _data_in: Any,
            _user_data: Any,
        ) -> None:
            try:
                elapsed = float(getattr(data_out, "running_time", float("nan")))
                nodes = int(getattr(data_out, "mip_node_count", 0))
                primal = float(getattr(data_out, "mip_primal_bound", float("nan")))
                dual = float(getattr(data_out, "mip_dual_bound", float("nan")))
                gap = float(getattr(data_out, "mip_gap", float("nan")))
            except (TypeError, ValueError):
                return
            self._progress_events.append(
                HighsProgressEvent(
                    elapsed_seconds=elapsed,
                    node_count=nodes,
                    primal_bound=primal,
                    dual_bound=dual,
                    mip_gap=gap,
                )
            )
            cb_enum = HighsCallbackType(cb_type) if not isinstance(cb_type, HighsCallbackType) else cb_type
            if cb_enum != HighsCallbackType.kCallbackMipImprovingSolution:
                return
            if self._first_verified_incumbent_time is not None:
                return
            mip_solution = getattr(data_out, "mip_solution", None)
            if mip_solution is None:
                # Accept improving-solution event time when vector is unavailable.
                if math.isfinite(elapsed):
                    self._first_verified_incumbent_time = elapsed
                return
            try:
                validate_start_against_stage(
                    self._stage,
                    np.asarray(mip_solution, dtype=float),
                )
            except NeutralMipStartError:
                return
            if math.isfinite(elapsed):
                self._first_verified_incumbent_time = elapsed

        _require_ok(self._highs.setCallback(_callback, None), "setCallback")
        _require_ok(
            self._highs.startCallback(kCallbackMipLogging),
            "startCallback(MipLogging)",
        )
        _require_ok(
            self._highs.startCallback(kCallbackMipImprovingSolution),
            "startCallback(MipImprovingSolution)",
        )

    def _load_model(self) -> None:
        stage = self._stage
        matrix = self._constraint_matrix
        model = HighsModel()
        lp = model.lp_
        lp.num_col_ = int(stage.n_vars)
        lp.num_row_ = int(matrix.shape[0])
        lp.sense_ = ObjSense.kMaximize if self._maximize else ObjSense.kMinimize
        lp.offset_ = 0.0
        lp.col_cost_ = np.asarray(stage.objective, dtype=np.float64).copy()
        lp.col_lower_ = np.asarray(
            [_to_highs_bound(float(v)) for v in stage.bounds_lb],
            dtype=np.float64,
        )
        lp.col_upper_ = np.asarray(
            [_to_highs_bound(float(v)) for v in stage.bounds_ub],
            dtype=np.float64,
        )
        if lp.num_row_ > 0:
            lp.row_lower_ = np.asarray(
                [_to_highs_bound(float(v)) for v in stage.constraints_lb],
                dtype=np.float64,
            )
            lp.row_upper_ = np.asarray(
                [_to_highs_bound(float(v)) for v in stage.constraints_ub],
                dtype=np.float64,
            )
        else:
            lp.row_lower_ = np.zeros(0, dtype=np.float64)
            lp.row_upper_ = np.zeros(0, dtype=np.float64)

        a_matrix = lp.a_matrix_
        a_matrix.format_ = MatrixFormat.kColwise
        a_matrix.num_col_ = int(stage.n_vars)
        a_matrix.num_row_ = int(matrix.shape[0])
        # Pass CSC arrays directly — no dense conversion.
        a_matrix.start_ = np.asarray(matrix.indptr, dtype=np.int32)
        a_matrix.index_ = np.asarray(matrix.indices, dtype=np.int32)
        a_matrix.value_ = np.asarray(matrix.data, dtype=np.float64)

        integrality = np.array(
            [
                HighsVarType.kInteger if int(flag) != 0 else HighsVarType.kContinuous
                for flag in stage.integrality
            ],
            dtype=object,
        )
        lp.integrality_ = cast(Any, integrality)

        _require_ok(self._highs.passModel(model), "passModel")

    def set_complete_start(self, column_values: np.ndarray) -> None:
        """Validate then load a complete MIP start via ``setSolution``."""
        validate_start_against_stage(self._stage, column_values)
        solution = HighsSolution()
        solution.col_value = np.asarray(column_values, dtype=np.float64).copy()
        _require_ok(self._highs.setSolution(solution), "setSolution")

    def change_objective(
        self,
        objective: np.ndarray,
        *,
        maximize: Optional[bool] = None,
    ) -> None:
        obj = np.asarray(objective, dtype=np.float64)
        if obj.shape != (self._stage.n_vars,):
            raise ValueError("objective length must match stage.n_vars")
        indices = np.arange(self._stage.n_vars, dtype=np.int32)
        _require_ok(
            self._highs.changeColsCost(int(self._stage.n_vars), indices, obj),
            "changeColsCost",
        )
        if maximize is not None:
            self._maximize = bool(maximize)
            sense = ObjSense.kMaximize if self._maximize else ObjSense.kMinimize
            _require_ok(self._highs.changeObjectiveSense(sense), "changeObjectiveSense")

    def change_row_bounds(self, row_index: int, lower: float, upper: float) -> None:
        _require_ok(
            self._highs.changeRowBounds(
                int(row_index),
                _to_highs_bound(float(lower)),
                _to_highs_bound(float(upper)),
            ),
            "changeRowBounds",
        )

    def solve(self) -> HighsCoverageSolveResult:
        self._progress_events.clear()
        self._first_verified_incumbent_time = None
        run_status = self._highs.run()
        if run_status == HighsStatus.kError:
            return HighsCoverageSolveResult(
                model_status=_STATE_ERROR,
                primal_solution_status="none",
                column_values=np.full(self._stage.n_vars, np.nan, dtype=float),
                objective_value=float("nan"),
                mip_primal_bound=float("nan"),
                mip_dual_bound=float("nan"),
                mip_gap=float("nan"),
                max_primal_infeasibility=float("nan"),
                max_integrality_violation=float("nan"),
                node_count=0,
                run_time=float(self._highs.getRunTime()),
                first_verified_incumbent_time=None,
            )
        _require_ok(run_status, "run")

        model_status = self._highs.getModelStatus()
        mapped = map_highs_model_status(model_status)
        info = self._highs.getInfo()
        solution = self._highs.getSolution()
        col_value = np.asarray(getattr(solution, "col_value", np.array([])), dtype=float)
        if col_value.shape != (self._stage.n_vars,):
            col_value = np.full(self._stage.n_vars, np.nan, dtype=float)

        objective_value = _optional_float(getattr(info, "objective_function_value", None))
        mip_dual_bound = _optional_float(getattr(info, "mip_dual_bound", None))
        mip_gap = _optional_float(getattr(info, "mip_gap", None))
        max_primal = _optional_float(getattr(info, "max_primal_infeasibility", None))
        max_integrality = _optional_float(getattr(info, "max_integrality_violation", None))
        # HighsInfo has no mip_primal_bound field; prefer the latest callback
        # primal bound, else the incumbent objective when a solution exists.
        mip_primal_bound = None
        if self._progress_events:
            last_primal = self._progress_events[-1].primal_bound
            if math.isfinite(last_primal):
                mip_primal_bound = float(last_primal)
        if mip_primal_bound is None:
            mip_primal_bound = objective_value
        try:
            node_count = int(getattr(info, "mip_node_count", 0))
        except (TypeError, ValueError):
            node_count = 0
        primal_status = _map_primal_solution_status(
            getattr(info, "primal_solution_status", kSolutionStatusNone)
        )

        require_mip_proof = bool(np.any(self._stage.integrality != 0))
        final_status = apply_proof_contract(
            raw_model_status=model_status.name,
            mapped_status=mapped,
            objective_value=objective_value,
            mip_primal_bound=mip_primal_bound,
            mip_dual_bound=mip_dual_bound,
            mip_gap=mip_gap,
            max_primal_infeasibility=max_primal,
            max_integrality_violation=max_integrality,
            require_mip_proof_fields=require_mip_proof,
        )

        return HighsCoverageSolveResult(
            model_status=final_status,
            primal_solution_status=primal_status,
            column_values=col_value.copy(),
            objective_value=_nan_if_none(objective_value),
            mip_primal_bound=_nan_if_none(mip_primal_bound),
            mip_dual_bound=_nan_if_none(mip_dual_bound),
            mip_gap=_nan_if_none(mip_gap),
            max_primal_infeasibility=_nan_if_none(max_primal),
            max_integrality_violation=_nan_if_none(max_integrality),
            node_count=node_count,
            run_time=float(self._highs.getRunTime()),
            first_verified_incumbent_time=self._first_verified_incumbent_time,
        )


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nan_if_none(value: Optional[float]) -> float:
    if value is None:
        return float("nan")
    return float(value)
