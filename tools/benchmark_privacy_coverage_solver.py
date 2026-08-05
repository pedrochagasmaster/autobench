#!/usr/bin/env python
"""Benchmark Verified Safe Coverage with safe aggregate output."""

from __future__ import annotations

import argparse
import ctypes
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from core.canonical_order import canonical_key  # noqa: E402
from core.contracts import PublicationUnit  # noqa: E402
from core.privacy_coverage import candidate_universe_digest  # noqa: E402
from core.privacy_coverage_model import (  # noqa: E402
    CoverageModelStatistics,
    CoverageRuleView,
    compile_coverage_model,
)
from core.privacy_coverage_solver import find_verified_safe_coverage  # noqa: E402
from core.privacy_coverage_verifier import verify_safe_coverage_result  # noqa: E402
from core.privacy_policy import PrivacyPolicy  # noqa: E402
from core.privacy_rules import privacy_rule_from_config  # noqa: E402
from tests.fixtures.production_scale_coverage import (  # noqa: E402
    build_production_scale_universe,
)

UniverseFactory = Callable[
    [], Tuple[Tuple[PublicationUnit, ...], Tuple[str, ...], float, float]
]

_PAYLOAD_KEY_ORDER = (
    "unit_count",
    "peer_count",
    "metric_count",
    "variable_count",
    "integer_variable_count",
    "row_count",
    "nonzero_count",
    "compile_seconds",
    "search_seconds",
    "peak_process_memory_bytes",
    "search_state",
    "search_method",
    "candidate_vectors_evaluated",
    "release_count",
    "suppression_count",
    "verifier_result",
    "release_mask_digest",
)


class _PROCESS_MEMORY_COUNTERS(ctypes.Structure):
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
    if sys.platform == "win32":
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        memory_info = getattr(kernel32, "K32GetProcessMemoryInfo", None)
        if memory_info is None:
            memory_info = ctypes.WinDLL(
                "psapi", use_last_error=True
            ).GetProcessMemoryInfo
        memory_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(_PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        memory_info.restype = wintypes.BOOL
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        counters = _PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        if not memory_info(
            kernel32.GetCurrentProcess(),
            ctypes.byref(counters),
            counters.cb,
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        return int(counters.PeakWorkingSetSize)
    import resource

    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def _rule_views() -> Dict[str, CoverageRuleView]:
    views: Dict[str, CoverageRuleView] = {}
    for name in PrivacyPolicy.sweep_rule_order():
        rule = privacy_rule_from_config(name)
        views[name] = CoverageRuleView(
            name=name,
            min_entities=rule.min_entities,
            max_concentration=rule.max_concentration,
            secondary_tiers=tuple(
                sorted(
                    rule.secondary_requirements.values(),
                    key=lambda item: -float(item[1]),
                )
            ),
        )
    return views


def _compile_statistics(
    universe: Tuple[PublicationUnit, ...],
    peers: Tuple[str, ...],
    minimum: float,
    maximum: float,
) -> Tuple[CoverageModelStatistics, float]:
    units: List[Dict[str, Any]] = []
    for unit in universe:
        metrics = []
        for record in unit.metric_records:
            aligned = {
                peer: float(record["peer_volumes"].get(peer, 0.0))
                for peer in peers
            }
            metrics.append(
                {
                    "metric": str(record["metric"]),
                    "aligned_volumes": aligned,
                    "total": sum(aligned.values()),
                    "positive_peers": tuple(
                        peer for peer in peers if aligned[peer] > 0.0
                    ),
                }
            )
        metrics.sort(key=lambda item: canonical_key(item["metric"]))
        units.append(
            {
                "key": unit.internal_key,
                "metrics": metrics,
                "rules": unit.applicable_rules,
                "overlays": unit.mandatory_overlays,
            }
        )
    started = time.perf_counter()
    model = compile_coverage_model(
        units,
        peers,
        min_weight=minimum,
        max_weight=maximum,
        rules=_rule_views(),
        enable_rule_dominance=True,
        enable_structural_presolve=True,
    )
    return model.statistics, time.perf_counter() - started


def main(
    argv: Optional[Sequence[str]] = None,
    *,
    universe_factory: Optional[UniverseFactory] = None,
) -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark Verified Safe Coverage on sanitized data."
    )
    parser.add_argument("--output-json", type=Path, default=None)
    args = parser.parse_args(argv)
    factory = universe_factory or build_production_scale_universe
    universe, peers, minimum, maximum = factory()
    stats, compile_seconds = _compile_statistics(
        universe, peers, minimum, maximum
    )
    started = time.perf_counter()
    result = find_verified_safe_coverage(
        universe,
        peers,
        min_weight=minimum,
        max_weight=maximum,
        rule_configs={},
        citibank_entity_name=None,
        input_digest="0" * 64,
        configuration_digest="0" * 64,
        policy_version="v5",
        policy_source="docs/control-3-v5.md",
        rule_set_digest=PrivacyPolicy.rule_set_digest(),
        candidate_universe_digest=candidate_universe_digest(universe),
    )
    search_seconds = time.perf_counter() - started
    outcome = verify_safe_coverage_result(
        result,
        min_weight=minimum,
        max_weight=maximum,
    )
    values = {
        "unit_count": stats.unit_count,
        "peer_count": stats.peer_count,
        "metric_count": stats.metric_count,
        "variable_count": stats.variable_count,
        "integer_variable_count": stats.integer_variable_count,
        "row_count": stats.row_count,
        "nonzero_count": stats.nonzero_count,
        "compile_seconds": compile_seconds,
        "search_seconds": search_seconds,
        "peak_process_memory_bytes": _peak_process_memory_bytes(),
        "search_state": result.search_state,
        "search_method": result.search_method,
        "candidate_vectors_evaluated": result.candidate_vectors_evaluated,
        "release_count": len(result.release_set),
        "suppression_count": len(result.suppression_set),
        "verifier_result": "passed" if outcome.passed else "failed",
        "release_mask_digest": result.release_mask_digest,
    }
    payload = {key: values[key] for key in _PAYLOAD_KEY_ORDER}
    encoded = json.dumps(payload, indent=2)
    print(encoded)
    if args.output_json is not None:
        args.output_json.parent.mkdir(parents=True, exist_ok=True)
        args.output_json.write_text(encoded + "\n", encoding="utf-8")
    return 0 if outcome.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
