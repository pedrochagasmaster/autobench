#!/usr/bin/env python
"""Benchmark the Maximum Safe Coverage solver on the sanitized production-scale fixture.

Prints one JSON object of safe aggregate timings and counts to stdout. Does not
emit unit keys, categories, peer identities, source values, or weights.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

# Repo root must be on sys.path so ``tests.fixtures`` imports work when this
# file is executed as a script (``python tools/benchmark_privacy_coverage_solver.py``).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import core.privacy_coverage_highs as coverage_highs  # noqa: E402
import core.privacy_coverage_solver as coverage_solver  # noqa: E402
from core.canonical_order import canonical_key  # noqa: E402
from core.contracts import (  # noqa: E402
    APPROVED_PRIVACY_RULE_NAMES,
    PublicationUnit,
    SafeCoverageResult,
)
from core.privacy_coverage import candidate_universe_digest  # noqa: E402
from core.privacy_coverage_highs import (  # noqa: E402
    HighsCoverageSession,
    HighsCoverageSolveResult,
    NeutralMipStartError,
)
from core.privacy_coverage_model import (  # noqa: E402
    CoverageModelStatistics,
    CoverageRuleView,
    compile_coverage_model,
)
from core.privacy_coverage_solver import optimize_safe_coverage  # noqa: E402
from core.privacy_coverage_verifier import (  # noqa: E402
    VERIFIER_RESULT_FAILED,
    VERIFIER_RESULT_PASSED,
    verify_safe_coverage_result,
)
from core.privacy_policy import PrivacyPolicy  # noqa: E402
from core.privacy_rules import privacy_rule_from_config  # noqa: E402
from tests.fixtures.production_scale_coverage import (  # noqa: E402
    build_production_scale_universe,
)

_DIGEST_ZERO = "0" * 64
_POLICY_VERSION = "v5"
_POLICY_SOURCE = "docs/control-3-v5.md"

UniverseFactory = Callable[[], Tuple[Tuple[PublicationUnit, ...], Tuple[str, ...], float, float]]

# Fixed JSON key order for deterministic stdout (safe aggregates only).
_PAYLOAD_KEY_ORDER: Tuple[str, ...] = (
    "unit_count",
    "peer_count",
    "metric_count",
    "variable_count",
    "integer_variable_count",
    "row_count",
    "nonzero_count",
    "compile_seconds",
    "first_incumbent_seconds",
    "proof_seconds",
    "stage_durations",
    "total_solve_seconds",
    "peak_process_memory_bytes",
    "solver_state",
    "solver_states",
    "release_count",
    "suppression_count",
    "mip_primal_bound",
    "mip_dual_bound",
    "mip_gap",
    "node_count",
    "start_validation",
    "verifier_result",
)


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    """Windows PROCESS_MEMORY_COUNTERS for peak working-set queries."""

    _fields_ = [
        ("cb", wintypes.DWORD),
        ("PageFaultCount", wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def _peak_process_memory_bytes() -> int:
    """Return peak resident set size for this process (bytes). Stdlib only."""
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        # Prefer K32* (kernel32) then fall back to psapi for older Windows.
        get_mem_info = getattr(kernel32, "K32GetProcessMemoryInfo", None)
        if get_mem_info is None:
            get_mem_info = ctypes.WinDLL("psapi", use_last_error=True).GetProcessMemoryInfo
        get_mem_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        get_mem_info.restype = wintypes.BOOL
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE

        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        handle = kernel32.GetCurrentProcess()
        if not get_mem_info(handle, ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.PeakWorkingSetSize)

    # resource is POSIX-only; import stays platform-gated.
    import resource

    usage = resource.getrusage(resource.RUSAGE_SELF)
    return int(usage.ru_maxrss * 1024)


def _json_number(value: Optional[float]) -> Optional[float]:
    """Return a finite float for JSON, else null."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


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
    metrics.sort(key=lambda item: canonical_key(str(item["metric"])))
    return {
        "key": unit.internal_key,
        "metrics": metrics,
        "rules": tuple(sorted(unit.applicable_rules, key=canonical_key)),
        "overlays": tuple(unit.mandatory_overlays),
    }


def _compile_only(
    universe: Tuple[PublicationUnit, ...],
    peers: Tuple[str, ...],
    *,
    min_weight: float,
    max_weight: float,
) -> Tuple[CoverageModelStatistics, float]:
    unit_data = [_canonicalize_unit(unit, peers) for unit in universe]
    started = time.perf_counter()
    model = compile_coverage_model(
        unit_data,
        peers,
        min_weight=min_weight,
        max_weight=max_weight,
        rules=_rule_views(),
        citibank_entity_name=None,
        enable_rule_dominance=True,
        enable_structural_presolve=True,
    )
    elapsed = time.perf_counter() - started
    return model.statistics, elapsed


def _timed_optimize(
    universe: Tuple[PublicationUnit, ...],
    peers: Tuple[str, ...],
    *,
    min_weight: float,
    max_weight: float,
) -> Tuple[SafeCoverageResult, Dict[str, float], float, Dict[str, Any]]:
    """Run ``optimize_safe_coverage`` with HiGHS stage-call timing and Stage-1 proof telemetry.

    Observes Stage-1 adapter results by wrapping the private ``_solve_highs_stage``
    patch point and capturing ``HighsCoverageSession.solve`` / neutral-start build
    outcomes. Does not change ``optimize_safe_coverage``'s public signature.
    """
    stage_durations = {
        "stage1": 0.0,
        "stage2": 0.0,
        "stage3": 0.0,
        "stage4": 0.0,
    }
    stage1_telemetry: Dict[str, Any] = {
        "first_incumbent_seconds": None,
        "proof_seconds": None,
        "mip_primal_bound": None,
        "node_count": None,
        "start_validation": None,
    }
    call_count = 0
    # Public path uses ``_solve_highs_stage``; patch that binding for timing.
    original_solve = getattr(coverage_solver, "_solve_highs_stage")
    if not callable(original_solve):
        raise TypeError(
            "core.privacy_coverage_solver._solve_highs_stage is not callable"
        )
    original_session_solve = HighsCoverageSession.solve
    original_build_start = coverage_highs.build_neutral_mip_start

    def capturing_build_start(*args: Any, **kwargs: Any) -> Any:
        try:
            start = original_build_start(*args, **kwargs)
        except NeutralMipStartError:
            stage1_telemetry["start_validation"] = "rejected"
            raise
        stage1_telemetry["start_validation"] = "accepted"
        return start

    def timed_highs_stage(*args: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        started = time.perf_counter()
        captured: List[HighsCoverageSolveResult] = []

        def capturing_session_solve(self: HighsCoverageSession) -> HighsCoverageSolveResult:
            result = original_session_solve(self)
            if call_count == 1:
                captured.append(result)
            return result

        setattr(HighsCoverageSession, "solve", capturing_session_solve)
        try:
            return original_solve(*args, **kwargs)
        finally:
            setattr(HighsCoverageSession, "solve", original_session_solve)
            elapsed = time.perf_counter() - started
            if call_count == 1:
                stage_durations["stage1"] += elapsed
                stage1_telemetry["proof_seconds"] = elapsed
                if captured:
                    adapter = captured[0]
                    stage1_telemetry["first_incumbent_seconds"] = (
                        adapter.first_verified_incumbent_time
                    )
                    stage1_telemetry["mip_primal_bound"] = _json_number(
                        adapter.mip_primal_bound
                    )
                    stage1_telemetry["node_count"] = int(adapter.node_count)
            elif call_count == 2:
                stage_durations["stage2"] += elapsed
            elif call_count == 3:
                stage_durations["stage3"] += elapsed
            else:
                stage_durations["stage4"] += elapsed

    setattr(coverage_solver, "_solve_highs_stage", timed_highs_stage)
    setattr(coverage_highs, "build_neutral_mip_start", capturing_build_start)
    solve_started = time.perf_counter()
    try:
        result = optimize_safe_coverage(
            universe,
            peers,
            min_weight=min_weight,
            max_weight=max_weight,
            rule_configs={},
            citibank_entity_name=None,
            input_digest=_DIGEST_ZERO,
            configuration_digest=_DIGEST_ZERO,
            policy_version=_POLICY_VERSION,
            policy_source=_POLICY_SOURCE,
            rule_set_digest=PrivacyPolicy.rule_set_digest(),
            candidate_universe_digest=candidate_universe_digest(universe),
        )
    finally:
        setattr(coverage_solver, "_solve_highs_stage", original_solve)
        setattr(coverage_highs, "build_neutral_mip_start", original_build_start)
        setattr(HighsCoverageSession, "solve", original_session_solve)
    total_solve_seconds = time.perf_counter() - solve_started
    return result, stage_durations, total_solve_seconds, stage1_telemetry


def _build_payload(
    stats: CoverageModelStatistics,
    *,
    compile_seconds: float,
    stage_durations: Mapping[str, float],
    total_solve_seconds: float,
    peak_process_memory_bytes: int,
    result: SafeCoverageResult,
    verifier_result: str,
    stage1_telemetry: Mapping[str, Any],
) -> Dict[str, Any]:
    unordered = {
        "unit_count": stats.unit_count,
        "peer_count": stats.peer_count,
        "metric_count": stats.metric_count,
        "variable_count": stats.variable_count,
        "integer_variable_count": stats.integer_variable_count,
        "row_count": stats.row_count,
        "nonzero_count": stats.nonzero_count,
        "compile_seconds": compile_seconds,
        "first_incumbent_seconds": _json_number(
            stage1_telemetry.get("first_incumbent_seconds")
        ),
        "proof_seconds": _json_number(stage1_telemetry.get("proof_seconds")),
        "stage_durations": {
            "stage1": stage_durations["stage1"],
            "stage2": stage_durations["stage2"],
            "stage3": stage_durations["stage3"],
            "stage4": stage_durations["stage4"],
        },
        "total_solve_seconds": total_solve_seconds,
        "peak_process_memory_bytes": peak_process_memory_bytes,
        "solver_state": result.solver_state,
        "solver_states": [result.solver_state],
        "release_count": len(result.release_set),
        "suppression_count": len(result.suppression_set),
        "mip_primal_bound": stage1_telemetry.get("mip_primal_bound"),
        "mip_dual_bound": _json_number(result.mip_dual_bound),
        "mip_gap": _json_number(result.mip_gap),
        "node_count": stage1_telemetry.get("node_count"),
        "start_validation": stage1_telemetry.get("start_validation"),
        "verifier_result": verifier_result,
    }
    return {key: unordered[key] for key in _PAYLOAD_KEY_ORDER}


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    universe_factory: Optional[UniverseFactory] = None,
) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Benchmark Maximum Safe Coverage on the sanitized production-scale fixture."
        )
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional path to write the same JSON object (stdout always prints it).",
    )
    args = parser.parse_args(argv)

    factory = universe_factory or build_production_scale_universe
    universe, peers, min_weight, max_weight = factory()
    stats, compile_seconds = _compile_only(
        universe,
        peers,
        min_weight=min_weight,
        max_weight=max_weight,
    )
    result, stage_durations, total_solve_seconds, stage1_telemetry = _timed_optimize(
        universe,
        peers,
        min_weight=min_weight,
        max_weight=max_weight,
    )
    outcome = verify_safe_coverage_result(
        result,
        min_weight=min_weight,
        max_weight=max_weight,
    )
    verifier_result = VERIFIER_RESULT_PASSED if outcome.passed else VERIFIER_RESULT_FAILED
    peak_memory = _peak_process_memory_bytes()

    payload = _build_payload(
        stats,
        compile_seconds=compile_seconds,
        stage_durations=stage_durations,
        total_solve_seconds=total_solve_seconds,
        peak_process_memory_bytes=peak_memory,
        result=result,
        verifier_result=verifier_result,
        stage1_telemetry=stage1_telemetry,
    )
    encoded = json.dumps(payload, indent=2)
    print(encoded)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(encoded + "\n", encoding="utf-8")

    success = result.solver_state == "optimal" and outcome.passed
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
