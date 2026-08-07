"""Tests for canonical Publication Unit / Candidate Universe construction."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from core.canonical_order import canonical_key
from core.category_suppression import compute_suppressed_categories
from core.privacy_coverage import (
    CandidateUniverseError,
    build_candidate_universe,
    build_publication_unit_key,
    candidate_universe_digest,
)
from tests.fixtures.safe_coverage_fixture import build_safe_coverage_getnet_shaped_df


def _build_universe(df: pd.DataFrame, **overrides):
    kwargs = {
        "entity_col": "issuer_name",
        "metric": "transaction_amount",
        "secondary_metrics": ["transaction_count", "merchant_count"],
        "dimensions": ["region", "sector"],
        "time_col": "quarter",
        "target_entity": None,
        "suppressed_categories": [],
        "merchant_spend_scope": False,
        "consistent_weights": True,
    }
    kwargs.update(overrides)
    return build_candidate_universe(df, **kwargs)


def test_publication_unit_key_is_stable() -> None:
    key_a = build_publication_unit_key(
        dimension="region",
        category="North",
        time_period="2025Q1",
        output_scope=None,
    )
    key_b = build_publication_unit_key(
        dimension="region",
        category="North",
        time_period="2025Q1",
    )
    assert key_a == key_b
    assert "dimension=region" in key_a
    assert "category=North" in key_a


def test_candidate_universe_row_order_invariant() -> None:
    df = build_safe_coverage_getnet_shaped_df()
    shuffled = df.sample(frac=1.0, random_state=7).reset_index(drop=True)
    reversed_df = df.iloc[::-1].reset_index(drop=True)

    universe_a = _build_universe(df)
    universe_b = _build_universe(shuffled)
    universe_c = _build_universe(reversed_df)

    keys_a = tuple(unit.internal_key for unit in universe_a)
    assert keys_a == tuple(unit.internal_key for unit in universe_b)
    assert keys_a == tuple(unit.internal_key for unit in universe_c)
    assert keys_a == tuple(sorted(keys_a, key=canonical_key))
    assert candidate_universe_digest(universe_a) == candidate_universe_digest(universe_b)


def test_duplicate_keys_rejected(monkeypatch) -> None:
    df = build_safe_coverage_getnet_shaped_df()

    original = build_publication_unit_key

    def collide(**kwargs):
        return "collision"

    monkeypatch.setattr(
        "core.privacy_coverage.build_publication_unit_key",
        collide,
    )
    with pytest.raises(CandidateUniverseError, match="Duplicate Publication Unit key"):
        _build_universe(df)
    monkeypatch.setattr(
        "core.privacy_coverage.build_publication_unit_key",
        original,
    )


def test_structural_suppression_excludes_units() -> None:
    df = build_safe_coverage_getnet_shaped_df()
    full = _build_universe(df)
    suppressed = [
        {
            "dimension": "sector_quarter",
            "category": "SectorX_2025Q1",
            "time_period": "2025Q1",
            "participants": 1,
            "reason": "below_min_entities",
        }
    ]
    filtered = _build_universe(df, suppressed_categories=suppressed)
    full_keys = {unit.internal_key for unit in full}
    filtered_keys = {unit.internal_key for unit in filtered}
    assert filtered_keys < full_keys
    assert all(
        not (unit.category == "SectorX_2025Q1" and unit.time_period == "2025Q1")
        for unit in filtered
    )


def test_missing_required_metric_excludes_complete_unit() -> None:
    df = build_safe_coverage_getnet_shaped_df()
    mask = (
        (df["sector"] == "SectorZ")
        & (df["quarter"] == "2025Q1")
        & (df["region"] == "South")
    )
    df = df[~mask].reset_index(drop=True)

    universe = _build_universe(df)
    assert all(
        not (unit.category.startswith("SectorZ_") and unit.time_period == "2025Q1")
        for unit in universe
    )


def test_nonfinite_values_rejected() -> None:
    df = build_safe_coverage_getnet_shaped_df().copy()
    df.loc[0, "transaction_amount"] = math.inf
    with pytest.raises(CandidateUniverseError, match="finite"):
        _build_universe(df)


def test_fixture_has_safe_and_unsafe_shapes() -> None:
    df = build_safe_coverage_getnet_shaped_df()
    universe = _build_universe(df)
    assert len(universe) >= 3

    def max_neutral_share(unit, metric_name: str) -> float:
        record = next(r for r in unit.metric_records if r["metric"] == metric_name)
        volumes = record["peer_volumes"]
        total = sum(volumes.values())
        return 100.0 * max(volumes.values()) / total

    safe_units = [
        unit
        for unit in universe
        if unit.category.startswith("SectorY_")
        and max_neutral_share(unit, "transaction_amount") <= 25.0
    ]
    unsafe_units = [
        unit
        for unit in universe
        if unit.category.startswith("SectorX_")
        and max_neutral_share(unit, "transaction_amount") > 40.0
    ]
    secondary_fail_units = [
        unit
        for unit in universe
        if unit.category.startswith("SectorZ_")
        and max_neutral_share(unit, "transaction_amount") <= 25.0
        and max_neutral_share(unit, "merchant_count") > 40.0
    ]
    assert safe_units
    assert unsafe_units
    assert secondary_fail_units
    for unit in universe:
        assert unit.applicable_rules
        assert unit.metric_records
        assert {record["metric"] for record in unit.metric_records} == {
            "transaction_amount",
            "transaction_count",
            "merchant_count",
        }


def test_compute_suppression_integrates_with_universe() -> None:
    df = build_safe_coverage_getnet_shaped_df()
    # Force a thin category by keeping only two peers in SectorY/Q2.
    thin = df[
        ~(
            (df["sector"] == "SectorY")
            & (df["quarter"] == "2025Q2")
            & (df["issuer_name"].isin(["PeerC", "PeerD", "PeerE", "PeerF"]))
        )
    ].reset_index(drop=True)
    suppressed = compute_suppressed_categories(
        thin,
        entity_col="issuer_name",
        target_entity=None,
        dimensions=["sector"],
        metric_col="transaction_amount",
        min_entities=5,
        time_col="quarter",
    )
    universe = _build_universe(thin, suppressed_categories=suppressed, dimensions=["sector"])
    assert all(
        not (unit.category == "SectorY" and unit.time_period == "2025Q2")
        for unit in universe
    )
