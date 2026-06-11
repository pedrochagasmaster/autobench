"""Equivalence tests for DimensionalAnalyzer construction from ResolvedConfig.

Freezes the analyzer attribute values produced by ``build_dimensional_analyzer``
for two presets so that moving the kwarg mapping into
``DimensionalAnalyzer.from_resolved`` provably preserves behavior.
"""

import logging
import unittest
from typing import Any, Dict

from core.analysis_run import build_dimensional_analyzer
from core.dimensional_analyzer import DimensionalAnalyzer
from utils.config_manager import ConfigManager

# Constructor-relevant attributes stored on the analyzer instance.
# Note: the constructor kwarg `volume_preservation_strength` is stored as
# `rank_preservation_strength` (and mirrored under its original name).
ATTRS = [
    "target_entity", "entity_column", "bic_percentile", "debug_mode",
    "consistent_weights",
    "max_iterations", "tolerance", "max_weight", "min_weight",
    "rank_preservation_strength", "volume_preservation_strength",
    "prefer_slacks_first", "auto_subset_search", "subset_search_max_tests",
    "greedy_subset_search", "trigger_subset_on_slack", "max_cap_slack",
    "time_column", "volume_weighted_penalties", "volume_weighting_exponent",
    "lambda_penalty", "enforce_additional_constraints",
    "dynamic_constraints_enabled", "min_peer_count_for_constraints",
    "min_effective_peer_count", "min_category_volume_share",
    "min_overall_volume_share", "min_representativeness",
    "dynamic_threshold_scale_floor", "dynamic_count_scale_floor",
    "representativeness_penalty_floor", "representativeness_penalty_power",
    "merchant_mode", "rank_constraint_mode", "rank_constraint_k",
    "bayesian_max_iterations", "bayesian_learning_rate",
    "violation_penalty_weight", "enforce_single_weight_set",
]

_COMMON_SNAPSHOT: Dict[str, Any] = {
    "target_entity": "Target",
    "entity_column": "issuer_name",
    "bic_percentile": 0.85,
    "debug_mode": False,
    "consistent_weights": True,
    "max_iterations": 1000,
    "max_weight": 10.0,
    "min_weight": 0.01,
    "prefer_slacks_first": False,
    "auto_subset_search": True,
    "subset_search_max_tests": 200,
    "trigger_subset_on_slack": True,
    "time_column": None,
    "volume_weighted_penalties": False,
    "volume_weighting_exponent": 1.0,
    "lambda_penalty": None,
    "enforce_additional_constraints": True,
    "dynamic_constraints_enabled": False,
    "min_peer_count_for_constraints": 4,
    "min_effective_peer_count": 3.0,
    "min_category_volume_share": 0.001,
    "min_overall_volume_share": 0.0005,
    "min_representativeness": 0.1,
    "dynamic_threshold_scale_floor": 0.6,
    "dynamic_count_scale_floor": 0.5,
    "representativeness_penalty_floor": 0.25,
    "representativeness_penalty_power": 1.0,
    "merchant_mode": False,
    "rank_constraint_mode": "all",
    "rank_constraint_k": 1,
    "bayesian_max_iterations": 100,
    "bayesian_learning_rate": 0.01,
    "violation_penalty_weight": 1000.0,
    "enforce_single_weight_set": False,
}

EXPECTED_SNAPSHOTS: Dict[str, Dict[str, Any]] = {
    "balanced_default": {
        **_COMMON_SNAPSHOT,
        "tolerance": 2.0,
        "rank_preservation_strength": 1.0,
        "volume_preservation_strength": 1.0,
        "greedy_subset_search": False,
        "max_cap_slack": 0.05,
    },
    "compliance_strict": {
        **_COMMON_SNAPSHOT,
        "tolerance": 0.0,
        "rank_preservation_strength": 0.95,
        "volume_preservation_strength": 0.95,
        "greedy_subset_search": True,
        "max_cap_slack": 0.0,
    },
}

METADATA_KEYS = {
    "consistent_weights", "consistency_mode", "rank_penalty_weight",
    "rank_preservation_strength", "lambda_penalty",
    "bayesian_max_iterations", "bayesian_learning_rate",
    "violation_penalty_weight", "enforce_single_weight_set",
    "dynamic_constraints_config",
}


def _build_via_helper(preset: str) -> tuple:
    config = ConfigManager(preset=preset)
    resolved = config.resolve()
    return build_dimensional_analyzer(
        target_entity="Target",
        entity_col="issuer_name",
        resolved=resolved,
        time_col=None,
        debug_mode=False,
        bic_percentile=0.85,
        logger=logging.getLogger("test"),
        consistent_weights=True,
    )


def _snapshot(analyzer: DimensionalAnalyzer) -> Dict[str, Any]:
    return {attr: getattr(analyzer, attr) for attr in ATTRS}


class TestBuildDimensionalAnalyzerSnapshot(unittest.TestCase):
    """Frozen attribute contract for analyzer construction from config."""

    def test_balanced_default_snapshot(self) -> None:
        analyzer, _ = _build_via_helper("balanced_default")
        self.assertEqual(_snapshot(analyzer), EXPECTED_SNAPSHOTS["balanced_default"])

    def test_compliance_strict_snapshot(self) -> None:
        analyzer, _ = _build_via_helper("compliance_strict")
        self.assertEqual(_snapshot(analyzer), EXPECTED_SNAPSHOTS["compliance_strict"])

    def test_metadata_dict_contract(self) -> None:
        for preset in EXPECTED_SNAPSHOTS:
            with self.subTest(preset=preset):
                _, settings = _build_via_helper(preset)
                self.assertEqual(set(settings.keys()), METADATA_KEYS)


class TestFromResolved(unittest.TestCase):
    """Direct construction via DimensionalAnalyzer.from_resolved."""

    @staticmethod
    def _build_direct(preset: str) -> DimensionalAnalyzer:
        resolved = ConfigManager(preset=preset).resolve()
        rank_preservation_strength = (
            resolved.constraints.volume_preservation
            * float(resolved.linear_programming.rank_penalty_weight)
        )
        return DimensionalAnalyzer.from_resolved(
            resolved,
            target_entity="Target",
            entity_column="issuer_name",
            time_column=None,
            debug_mode=False,
            bic_percentile=0.85,
            consistent_weights=True,
            rank_preservation_strength=rank_preservation_strength,
            lambda_penalty=resolved.linear_programming.lambda_penalty,
        )

    def test_matches_frozen_snapshot(self) -> None:
        for preset, expected in EXPECTED_SNAPSHOTS.items():
            with self.subTest(preset=preset):
                self.assertEqual(_snapshot(self._build_direct(preset)), expected)

    def test_compliance_strict_negative_drift(self) -> None:
        resolved = ConfigManager(preset="compliance_strict").resolve()
        analyzer = self._build_direct("compliance_strict")
        self.assertEqual(analyzer.tolerance, 0.0)
        self.assertEqual(analyzer.auto_subset_search, resolved.subset_search.enabled)


if __name__ == "__main__":
    unittest.main()
