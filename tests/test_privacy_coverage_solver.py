"""Tests for the deterministic Verified Safe Coverage search."""

from __future__ import annotations

from typing import Any, Dict, Tuple

import numpy as np
import pytest

from core.contracts import PublicationUnit, SafeCoverageResult
from core.privacy_coverage import build_candidate_universe, candidate_universe_digest
from core.privacy_coverage_solver import (
    SafeCoverageSolverError,
    find_verified_safe_coverage,
    weighted_shares,
)
from core.privacy_coverage_verifier import verify_safe_coverage_result
from core.privacy_policy import PrivacyPolicy
from core.privacy_rules import evaluate_rule
from tests.fixtures.safe_coverage_fixture import build_safe_coverage_getnet_shaped_df

_PEERS: Tuple[str, ...] = (
    "PeerA",
    "PeerB",
    "PeerC",
    "PeerD",
    "PeerE",
    "PeerF",
)
_DIGEST = "0" * 64


def _fixture_universe(**overrides: Any) -> Tuple[PublicationUnit, ...]:
    settings: Dict[str, Any] = {
        "entity_col": "issuer_name",
        "metric": "transaction_amount",
        "secondary_metrics": ["transaction_count", "merchant_count"],
        "dimensions": ["region", "sector"],
        "time_col": "quarter",
    }
    settings.update(overrides)
    return build_candidate_universe(
        build_safe_coverage_getnet_shaped_df(),
        **settings,
    )


def _run_search(
    universe: Tuple[PublicationUnit, ...],
    *,
    min_weight: float = 0.5,
    max_weight: float = 2.0,
    peers: Tuple[str, ...] = _PEERS,
    citibank_entity_name: str | None = None,
) -> SafeCoverageResult:
    return find_verified_safe_coverage(
        universe,
        peers,
        min_weight=min_weight,
        max_weight=max_weight,
        rule_configs={},
        citibank_entity_name=citibank_entity_name,
        input_digest=_DIGEST,
        configuration_digest=_DIGEST,
        policy_version="v5",
        policy_source="docs/control-3-v5.md",
        rule_set_digest=PrivacyPolicy.rule_set_digest(),
        candidate_universe_digest=candidate_universe_digest(universe),
    )


def _expected_release_keys(
    universe: Tuple[PublicationUnit, ...],
    result: SafeCoverageResult,
) -> Tuple[str, ...]:
    expected = []
    for unit in universe:
        for rule_name in sorted(unit.applicable_rules):
            if all(
                evaluate_rule(
                    rule_name,
                    weighted_shares(
                        record["peer_volumes"],
                        result.global_weights,
                    ).values(),
                ).strict_passed
                for record in unit.metric_records
            ):
                expected.append(unit.internal_key)
                break
    return tuple(sorted(expected))


def test_search_returns_verified_partial_coverage() -> None:
    universe = _fixture_universe()
    result = _run_search(universe)

    assert result.search_state == "search_complete"
    assert result.search_method
    assert result.candidate_vectors_evaluated > 1
    assert 0 < len(result.release_set) < len(universe)
    assert len(result.release_set) + len(result.suppression_set) == len(universe)
    assert tuple(result.release_set) == _expected_release_keys(universe, result)

    outcome = verify_safe_coverage_result(
        result,
        min_weight=0.5,
        max_weight=2.0,
        client_release_keys=result.release_set,
    )
    assert outcome.passed, outcome.failures


def test_repeated_search_is_deterministic() -> None:
    universe = _fixture_universe()
    first = _run_search(universe)
    second = _run_search(universe)

    assert first.global_weights == second.global_weights
    assert first.release_set == second.release_set
    assert first.release_mask_digest == second.release_mask_digest
    assert (
        first.candidate_vectors_evaluated
        == second.candidate_vectors_evaluated
    )


def test_all_passing_units_are_released() -> None:
    universe = _fixture_universe()
    result = _run_search(universe)
    assert set(result.release_set) == set(_expected_release_keys(universe, result))


def test_fixed_neutral_weights_release_all_safe_units() -> None:
    frame = build_safe_coverage_getnet_shaped_df()
    frame = frame[frame["sector"] == "SectorY"].reset_index(drop=True)
    universe = build_candidate_universe(
        frame,
        entity_col="issuer_name",
        metric="transaction_amount",
        secondary_metrics=["transaction_count", "merchant_count"],
        dimensions=["sector"],
        time_col="quarter",
    )
    result = _run_search(universe, min_weight=1.0, max_weight=1.0)
    assert len(result.release_set) == len(universe)
    assert result.suppression_set == ()
    assert set(result.global_weights.values()) == {1.0}


def test_unproven_anchor_candidate_can_enter_safe_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    universe = _fixture_universe()

    def fake_anchor(*args: Any, **kwargs: Any) -> Tuple[np.ndarray, str, str]:
        del args, kwargs
        return np.ones(len(_PEERS)), "limit_reached", "test"

    monkeypatch.setattr(
        "core.privacy_coverage_solver._anchor_candidate",
        fake_anchor,
    )
    result = _run_search(universe)
    assert result.search_state == "search_complete"
    assert result.release_set


def test_solver_options_are_rejected() -> None:
    universe = _fixture_universe()
    with pytest.raises(SafeCoverageSolverError, match="solver_options"):
        find_verified_safe_coverage(
            universe,
            _PEERS,
            min_weight=0.5,
            max_weight=2.0,
            rule_configs={},
            citibank_entity_name=None,
            input_digest=_DIGEST,
            configuration_digest=_DIGEST,
            policy_version="v5",
            policy_source="docs",
            rule_set_digest=_DIGEST,
            candidate_universe_digest=candidate_universe_digest(universe),
            solver_options={"time_limit": 1},
        )


@pytest.mark.parametrize(
    ("minimum", "maximum"),
    ((0.0, 2.0), (1.1, 2.0), (0.5, 0.9), (2.0, 1.0)),
)
def test_invalid_weight_bounds_are_rejected(
    minimum: float,
    maximum: float,
) -> None:
    universe = _fixture_universe()
    with pytest.raises(SafeCoverageSolverError):
        _run_search(universe, min_weight=minimum, max_weight=maximum)


def test_weighted_shares_drop_zero_volume_peers() -> None:
    shares = weighted_shares(
        {"A": 10.0, "B": 0.0, "C": 30.0},
        {"A": 2.0, "B": 5.0, "C": 1.0},
    )
    assert shares == pytest.approx({"A": 40.0, "C": 60.0})


def test_unknown_rule_is_rejected() -> None:
    source = _fixture_universe()[0]
    bad = PublicationUnit(
        internal_key=source.internal_key,
        dimension=source.dimension,
        category=source.category,
        time_period=source.time_period,
        output_scope=source.output_scope,
        metric_records=source.metric_records,
        applicable_rules=("unknown",),
        mandatory_overlays=source.mandatory_overlays,
    )
    with pytest.raises(SafeCoverageSolverError, match="unknown privacy rule"):
        _run_search((bad,))
