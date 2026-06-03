from types import SimpleNamespace

from core.contracts import WeightLookup, WeightingResult


def test_weight_lookup_prefers_dimension_multiplier_over_global() -> None:
    lookup = WeightLookup(
        global_weights={"PeerA": {"multiplier": 1.25}},
        per_dimension_weights={"merchant": {"PeerA": 0.75}},
    )

    assert lookup.multiplier("PeerA", "merchant") == 0.75
    assert lookup.multiplier("PeerA", "channel") == 1.25


def test_weight_lookup_defaults_unknown_peer_to_one() -> None:
    lookup = WeightLookup(global_weights={}, per_dimension_weights={})

    assert lookup.multiplier("PeerA", "merchant") == 1.0


def test_weight_lookup_can_snapshot_from_weighting_result() -> None:
    result = WeightingResult(
        global_weights={"PeerA": {"multiplier": 1.1}},
        per_dimension_weights={"merchant": {"PeerB": 1.3}},
    )

    lookup = WeightLookup.from_weighting_result(result)

    assert lookup.multiplier("PeerA", "merchant") == 1.1
    assert lookup.multiplier("PeerB", "merchant") == 1.3


def test_weight_lookup_can_snapshot_from_analyzer_compatibility_fields() -> None:
    analyzer = SimpleNamespace(
        global_weights={"PeerA": {"multiplier": 1.1}},
        per_dimension_weights={"merchant": {"PeerA": 0.9}},
    )

    lookup = WeightLookup.from_analyzer(analyzer)

    assert lookup.multiplier("PeerA", "merchant") == 0.9
