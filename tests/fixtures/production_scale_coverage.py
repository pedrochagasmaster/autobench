"""Sanitized production-scale Candidate Universe for coverage-model size tests.

Synthetic peers and categories only. No confidential Getnet categories, values,
or identifiers. Seeded for deterministic regeneration.
"""

from __future__ import annotations

from typing import Dict, List, Mapping, Tuple

import numpy as np

from core.contracts import PublicationUnit
from core.privacy_policy import PrivacyPolicy

PRODUCTION_SCALE_UNIT_COUNT = 242
PRODUCTION_SCALE_PEER_COUNT = 33
PRODUCTION_SCALE_METRIC_COUNT = 3
PRODUCTION_SCALE_MIN_WEIGHT = 0.5
PRODUCTION_SCALE_MAX_WEIGHT = 2.0
PRODUCTION_SCALE_SEED = 20260804

_METRICS = ("transaction_amount", "transaction_count", "merchant_count")


def production_scale_peers() -> Tuple[str, ...]:
    return tuple(f"Peer{index:02d}" for index in range(1, PRODUCTION_SCALE_PEER_COUNT + 1))


def _metric_record(metric: str, peer_volumes: Mapping[str, float]) -> Dict[str, object]:
    total = float(sum(peer_volumes.values()))
    return {
        "metric": metric,
        "peer_volumes": dict(peer_volumes),
        "total_volume": total,
        "participant_count": sum(1 for volume in peer_volumes.values() if volume > 0.0),
    }


def _safe_volumes(peers: Tuple[str, ...], rng: np.random.Generator) -> Dict[str, float]:
    """Near-equal positive volumes: primary caps always pass under weight bounds."""
    base = rng.uniform(0.95, 1.05, size=len(peers))
    return {peer: float(value) for peer, value in zip(peers, base)}


def _unsafe_volumes(peers: Tuple[str, ...], rng: np.random.Generator) -> Dict[str, float]:
    """One dominant peer: primary caps fail across the weight box."""
    volumes = {peer: float(rng.uniform(0.5, 1.5)) for peer in peers}
    dominant = peers[int(rng.integers(0, len(peers)))]
    volumes[dominant] = float(sum(volumes.values()) * 2.5)
    return volumes


def _boundary_volumes(peers: Tuple[str, ...], rng: np.random.Generator) -> Dict[str, float]:
    """Mixed concentration so some witnesses stay weight-dependent."""
    ranks = rng.permutation(len(peers))
    volumes: Dict[str, float] = {}
    for order, peer_index in enumerate(ranks):
        peer = peers[int(peer_index)]
        if order == 0:
            volumes[peer] = float(rng.uniform(28.0, 38.0))
        elif order < 4:
            volumes[peer] = float(rng.uniform(12.0, 18.0))
        elif order < 10:
            volumes[peer] = float(rng.uniform(4.0, 8.0))
        else:
            volumes[peer] = float(rng.uniform(0.5, 2.0))
    return volumes


def build_production_scale_universe() -> Tuple[Tuple[PublicationUnit, ...], Tuple[str, ...], float, float]:
    """Return (units, peers, min_weight, max_weight) for the 242 x 33 x 3 shape."""
    peers = production_scale_peers()
    rng = np.random.default_rng(PRODUCTION_SCALE_SEED)
    applicable = PrivacyPolicy.applicable_sweep_rules(
        len(peers),
        is_anonymized_aggregated_merchant_spend=True,
    )
    assert "4/35" in applicable
    assert len(applicable) == 5

    # Mix: clearly-safe, clearly-unsafe, and boundary units.
    kind_cycle = ("safe",) * 90 + ("unsafe",) * 80 + ("boundary",) * 72
    assert len(kind_cycle) == PRODUCTION_SCALE_UNIT_COUNT

    units: List[PublicationUnit] = []
    for index, kind in enumerate(kind_cycle, start=1):
        if kind == "safe":
            builder = _safe_volumes
        elif kind == "unsafe":
            builder = _unsafe_volumes
        else:
            builder = _boundary_volumes
        metric_records = tuple(
            _metric_record(metric, builder(peers, rng)) for metric in _METRICS
        )
        units.append(
            PublicationUnit(
                internal_key=f"Unit{index:03d}",
                dimension="sector",
                category=f"Sector{kind.capitalize()}{index:03d}",
                time_period="2025Q1",
                output_scope="merchant_spend",
                metric_records=metric_records,
                applicable_rules=applicable,
                mandatory_overlays=(),
            )
        )

    assert len(units) == PRODUCTION_SCALE_UNIT_COUNT
    assert all(len(unit.metric_records) == PRODUCTION_SCALE_METRIC_COUNT for unit in units)
    return (
        tuple(units),
        peers,
        PRODUCTION_SCALE_MIN_WEIGHT,
        PRODUCTION_SCALE_MAX_WEIGHT,
    )
