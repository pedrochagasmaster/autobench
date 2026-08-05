"""Deterministic JSON schema tests for the privacy-coverage benchmark tool.

Uses a small sanitized fixture (not the 242x33x3 production-scale shape) so the
file stays well under ~30s. Asserts safe aggregate keys only.
"""

from __future__ import annotations

import json
import math
from typing import Any, Dict, Set, Tuple

from core.contracts import PublicationUnit
from core.privacy_coverage import build_candidate_universe
from tests.fixtures.safe_coverage_fixture import (
    FIXTURE_MAX_WEIGHT,
    FIXTURE_MIN_WEIGHT,
    build_safe_coverage_getnet_shaped_df,
)
from tools.benchmark_privacy_coverage_solver import _PAYLOAD_KEY_ORDER, main

_FIXTURE_PEERS: Tuple[str, ...] = (
    "PeerA",
    "PeerB",
    "PeerC",
    "PeerD",
    "PeerE",
    "PeerF",
)

_EXPECTED_KEYS: Set[str] = set(_PAYLOAD_KEY_ORDER)

_NUMERIC_KEYS = (
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
    "release_count",
    "suppression_count",
    "candidate_vectors_evaluated",
)

_FORBIDDEN_SUBSTRINGS = (
    "Peer01",
    "PeerA",
    "PeerB",
    "Unit001",
    "Unit002",
    "SectorX",
    "SectorY",
    "transaction_amount",
    "aligned_volumes",
    "peer_volumes",
    "global_weights",
    "weight_vector",
)


def _small_sanitized_universe() -> Tuple[
    Tuple[PublicationUnit, ...], Tuple[str, ...], float, float
]:
    df = build_safe_coverage_getnet_shaped_df()
    universe = build_candidate_universe(
        df,
        entity_col="issuer_name",
        metric="transaction_amount",
        secondary_metrics=["transaction_count", "merchant_count"],
        dimensions=["region", "sector"],
        time_col="quarter",
    )
    return universe, _FIXTURE_PEERS, FIXTURE_MIN_WEIGHT, FIXTURE_MAX_WEIGHT


def _run_benchmark_payload(capsys: Any) -> Dict[str, Any]:
    exit_code = main([], universe_factory=_small_sanitized_universe)
    captured = capsys.readouterr()
    assert exit_code == 0, captured.out + captured.err
    payload = json.loads(captured.out)
    assert isinstance(payload, dict)
    return payload


def test_benchmark_stdout_is_one_json_object(capsys: Any) -> None:
    payload = _run_benchmark_payload(capsys)
    assert set(payload.keys()) == _EXPECTED_KEYS
    assert list(payload.keys()) == list(_PAYLOAD_KEY_ORDER)


def test_benchmark_json_schema_and_types(capsys: Any) -> None:
    payload = _run_benchmark_payload(capsys)

    assert set(payload.keys()) == _EXPECTED_KEYS
    assert set(payload.keys()) - _EXPECTED_KEYS == set()

    for key in _NUMERIC_KEYS:
        assert isinstance(payload[key], (int, float)), key
        assert math.isfinite(float(payload[key])), key

    assert payload["search_state"] == "search_complete"
    assert isinstance(payload["search_method"], str)
    assert isinstance(payload["verifier_result"], str)
    assert len(payload["release_mask_digest"]) == 64


def test_benchmark_json_omits_forbidden_content(capsys: Any) -> None:
    payload = _run_benchmark_payload(capsys)
    encoded = json.dumps(payload)
    for fragment in _FORBIDDEN_SUBSTRINGS:
        assert fragment not in encoded, fragment
    for key, value in payload.items():
        assert not isinstance(value, (dict, list)), key
