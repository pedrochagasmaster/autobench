"""Shared helpers for the analytical determinism regression tests.

The determinism guarantee is: identical input bytes, resolved configuration,
Autobench version, and supported locked runtime produce identical analytical
results. Generated files are deliberately outside the guarantee, so the
fingerprint built here keeps every analytical value and drops everything that
is allowed to move between runs (timestamps, session identifiers, generated
file names, log creation times, workbook binary data).

Run as a module to emit one fingerprint on stdout, which is how the
fresh-process matrix compares runs across ``PYTHONHASHSEED`` values::

    python -m tests.determinism_support <case> <preset>
"""

from __future__ import annotations

import json
import logging
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.analysis_run import (  # noqa: E402
    build_dimensional_analyzer,
    execute_rate_run,
    execute_share_run,
)
from core.contracts import AnalysisRunRequest  # noqa: E402
from utils.config_manager import ConfigManager  # noqa: E402

FIXTURES = Path(__file__).resolve().parent / "fixtures"

# gate_demo.csv solves cleanly on the global LP path. determinism_fallbacks.csv
# holds a structurally infeasible channel category, which pushes the presets
# through subset search, per-dimension solving, and heuristic correction.
GATE_FIXTURE = FIXTURES / "gate_demo.csv"
FALLBACK_FIXTURE = FIXTURES / "determinism_fallbacks.csv"

PRESETS = (
    "balanced_default",
    "compliance_strict",
    "low_distortion",
    "minimal_distortion",
    "research_exploratory",
    "strategic_consistency",
)

# "run" cases go through the full CLI/TUI/Python entry point. "solve" cases
# stop at the weight optimizer, which keeps solver output visible for preset and
# posture combinations whose run output the publication gate withholds.
CASES: Dict[str, Dict[str, Any]] = {
    # Global LP success on both explicit dimensions.
    "share_lp": {
        "kind": "run",
        "mode": "share",
        "csv": GATE_FIXTURE,
        "dimensions": ["card_type", "channel"],
    },
    # Automatic dimension selection instead of an explicit list.
    "share_auto_dimensions": {
        "kind": "run",
        "mode": "share",
        "csv": GATE_FIXTURE,
        "auto": True,
    },
    # Subset search, per-dimension fallback, and heuristic correction.
    "share_fallbacks": {
        "kind": "run",
        "mode": "share",
        "csv": FALLBACK_FIXTURE,
        "dimensions": ["card_type", "channel"],
    },
    # Approval and fraud rate analysis.
    "rate_lp": {
        "kind": "run",
        "mode": "rate",
        "csv": GATE_FIXTURE,
        "dimensions": ["card_type", "channel"],
    },
    "rate_fallbacks": {
        "kind": "run",
        "mode": "rate",
        "csv": FALLBACK_FIXTURE,
        "dimensions": ["card_type", "channel"],
    },
    # Weight optimization only, so every preset reports solver output.
    "solve_lp": {
        "kind": "solve",
        "csv": GATE_FIXTURE,
        "dimensions": ["card_type", "channel"],
    },
    "solve_fallbacks": {
        "kind": "solve",
        "csv": FALLBACK_FIXTURE,
        "dimensions": ["card_type", "channel"],
    },
    # The same problem with the dimension list reversed; the analytical result
    # must not depend on the order the dimensions were supplied in.
    "solve_fallbacks_reversed": {
        "kind": "solve",
        "csv": FALLBACK_FIXTURE,
        "dimensions": ["channel", "card_type"],
    },
    # Per-dimension weighting instead of one global weight set.
    "solve_per_dimension": {
        "kind": "solve",
        "csv": FALLBACK_FIXTURE,
        "dimensions": ["card_type", "channel"],
        "consistent_weights": False,
    },
}


def _number(value: Any) -> Any:
    """Serialize a float without losing bits, so equality stays exact."""
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, (int, bool, str)) or value is None:
        return value
    if hasattr(value, "item"):
        return _number(value.item())
    return str(value)


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _normalize(val) for key, val in sorted(value.items(), key=str)}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    if isinstance(value, pd.DataFrame):
        return _frame(value)
    return _number(value)


def _frame(frame: Optional[pd.DataFrame]) -> Optional[Dict[str, Any]]:
    """Render a dataframe as ordered columns plus normalized row records."""
    if frame is None or not isinstance(frame, pd.DataFrame):
        return None
    return {
        "columns": [str(column) for column in frame.columns],
        "rows": [
            [_normalize(record[column]) for column in frame.columns]
            for _, record in frame.iterrows()
        ],
    }


def _results(results: Any) -> Any:
    if isinstance(results, dict):
        return {str(key): _results(value) for key, value in sorted(results.items(), key=str)}
    return _frame(results)


def analyzer_fingerprint(analyzer: Any) -> Optional[Dict[str, Any]]:
    """Return the normalized weight-optimization output of an analyzer."""
    if analyzer is None:
        return None
    return {
        "global_weights": _normalize(analyzer.global_weights),
        "per_dimension_weights": _normalize(analyzer.per_dimension_weights),
        "weight_methods": _normalize(analyzer.weight_methods),
        "global_dimensions_used": _normalize(analyzer.global_dimensions_used),
        "removed_dimensions": _normalize(analyzer.removed_dimensions),
        "privacy_rule_name": analyzer.privacy_rule_name,
        "subset_search_results": _normalize(analyzer.subset_search_results),
        "rank_changes": _frame(analyzer.rank_changes_df),
    }


def analytical_fingerprint(artifacts: Any) -> Dict[str, Any]:
    """Return the normalized analytical result of a completed run."""
    metadata = artifacts.metadata or {}
    decision = artifacts.privacy_output_decision

    return {
        "analyzer": analyzer_fingerprint(artifacts.analyzer),
        "calculated_values": _results(artifacts.results),
        "privacy_validation": _frame(artifacts.privacy_validation_df),
        "compliance_summary": _normalize(artifacts.compliance_summary),
        "suppressed_categories": _normalize(metadata.get("suppressed_categories")),
        "suppressed_metric_categories": _normalize(
            metadata.get("suppressed_metric_categories")
        ),
        "privacy_publication_authorized": (
            None if decision is None else decision.privacy_publication_authorized
        ),
        "hard_privacy_block": None if decision is None else decision.hard_privacy_block,
        "withholding_reason": None if decision is None else decision.withholding_reason,
    }


def build_request(case: str, preset: str, output: Path) -> AnalysisRunRequest:
    """Build the run request for a named case and preset."""
    spec = CASES[case]
    kwargs: Dict[str, Any] = {
        "mode": spec["mode"],
        "csv": str(spec["csv"]),
        "entity": "Target",
        "time_col": "year_month",
        "preset": preset,
        "compliance_posture": "best_effort",
        "acknowledge_accuracy_first": True,
        "output": str(output),
        "auto": bool(spec.get("auto", False)),
        "dimensions": spec.get("dimensions"),
        "per_dimension_weights": bool(spec.get("per_dimension_weights", False)),
    }
    if spec["mode"] == "share":
        kwargs["metric"] = "txn_cnt"
    else:
        kwargs["total_col"] = "total"
        kwargs["approved_col"] = "approved"
        kwargs["fraud_col"] = "fraud"
        kwargs["control3_overrides"] = {"privacy_basis": "clearing_spend"}
    return AnalysisRunRequest(**kwargs)


def build_analyzer(case: str, preset: str) -> Any:
    """Build the analyzer a "solve" case optimizes weights with."""
    spec = CASES[case]
    analyzer, _ = build_dimensional_analyzer(
        target_entity="Target",
        entity_col="issuer_name",
        resolved=ConfigManager(preset=preset).resolve(),
        time_col="year_month",
        debug_mode=False,
        bic_percentile=0.85,
        logger=logging.getLogger("determinism"),
        consistent_weights=spec.get("consistent_weights", True),
    )
    return analyzer


def run_case(case: str, preset: str) -> Dict[str, Any]:
    """Execute one case/preset pair and return its analytical fingerprint."""
    spec = CASES[case]
    logger = logging.getLogger("determinism")

    if spec["kind"] == "solve":
        analyzer = build_analyzer(case, preset)
        frame = pd.read_csv(spec["csv"])
        analyzer.fit_privacy_weights(frame, "txn_cnt", list(spec["dimensions"]))
        return {"analyzer": analyzer_fingerprint(analyzer)}

    with tempfile.TemporaryDirectory() as work_dir:
        request = build_request(case, preset, Path(work_dir) / "analysis.xlsx")
        runner = execute_share_run if request.is_share else execute_rate_run
        artifacts = runner(request, logger)
        return analytical_fingerprint(artifacts)


def fingerprint_json(case: str, preset: str) -> str:
    """Return the fingerprint of one case/preset pair as canonical JSON."""
    return json.dumps(run_case(case, preset), sort_keys=True, separators=(",", ":"))


def _main(argv: List[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write("usage: python -m tests.determinism_support <case> <preset>\n")
        return 2
    logging.disable(logging.CRITICAL)
    sys.stdout.write(fingerprint_json(argv[0], argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
