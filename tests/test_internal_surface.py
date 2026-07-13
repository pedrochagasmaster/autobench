"""Keep removed internal compatibility surfaces from growing back."""

import benchmark
import core.contracts as contracts
from core.dimensional_analyzer import DimensionalAnalyzer
from utils.preset_manager import PresetManager


def test_obsolete_internal_compatibility_surfaces_are_absent() -> None:
    assert not hasattr(contracts, "apply_weighting_result_to_analyzer")
    assert not hasattr(DimensionalAnalyzer, "calculate_global_weights")
    assert not hasattr(PresetManager, "load_preset")
    assert not hasattr(PresetManager, "invalid_presets")
    assert not hasattr(PresetManager, "get_invalid_presets")
    assert not hasattr(PresetManager, "get_preset_choices")
    assert not hasattr(benchmark, "run_preset_comparison")
