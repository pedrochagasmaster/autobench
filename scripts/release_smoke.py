"""Offline release smoke: real HiGHS solve plus independent verification."""

from __future__ import annotations

from importlib.metadata import version
from typing import Tuple

import highspy
import numpy
import scipy

from core.contracts import PublicationUnit, SafeCoverageResult
from core.privacy_coverage import (
    build_candidate_universe,
    candidate_universe_digest,
)
from core.privacy_coverage_solver import find_verified_safe_coverage
from core.privacy_coverage_verifier import (
    build_coverage_certificate,
    verify_coverage_certificate,
    verify_safe_coverage_result,
)
from core.privacy_policy import PrivacyPolicy
from tests.fixtures.safe_coverage_fixture import (
    build_safe_coverage_getnet_shaped_df,
)

_PEERS: Tuple[str, ...] = (
    "PeerA",
    "PeerB",
    "PeerC",
    "PeerD",
    "PeerE",
    "PeerF",
)
_INPUT_DIGEST = "0" * 64
_CONFIG_DIGEST = "0" * 64
_MIN_WEIGHT = 0.5
_MAX_WEIGHT = 2.0


def _solve_fixture() -> Tuple[Tuple[PublicationUnit, ...], SafeCoverageResult]:
    """Build the sanitized fixture universe and run the production solver."""
    df = build_safe_coverage_getnet_shaped_df()
    universe = build_candidate_universe(
        df,
        entity_col="issuer_name",
        metric="transaction_amount",
        secondary_metrics=["transaction_count", "merchant_count"],
        dimensions=["region", "sector"],
        time_col="quarter",
    )
    result = find_verified_safe_coverage(
        universe,
        _PEERS,
        min_weight=_MIN_WEIGHT,
        max_weight=_MAX_WEIGHT,
        rule_configs={},
        citibank_entity_name=None,
        input_digest=_INPUT_DIGEST,
        configuration_digest=_CONFIG_DIGEST,
        policy_version="v5",
        policy_source="docs/control-3-v5.md",
        rule_set_digest=PrivacyPolicy.rule_set_digest(),
        candidate_universe_digest=candidate_universe_digest(universe),
    )
    return universe, result


def run() -> str:
    """Return a success line after a real solve and independent verification."""
    highspy_version = version("highspy")
    if not callable(getattr(highspy, "Highs", None)):
        raise RuntimeError("highspy.Highs is unavailable after import")
    _universe, result = _solve_fixture()

    if result.search_state != "search_complete":
        raise RuntimeError(
            f"verified-safe-coverage smoke search incomplete: {result.search_state!r}"
        )
    if not result.release_set or not result.suppression_set:
        raise RuntimeError(
            "verified-safe-coverage smoke requires a non-empty proper partition "
            f"(release={len(result.release_set)} "
            f"suppression={len(result.suppression_set)})"
        )
    if set(result.release_set) & set(result.suppression_set):
        raise RuntimeError("verified-safe-coverage smoke release partition overlaps")

    outcome = verify_safe_coverage_result(
        result,
        min_weight=_MIN_WEIGHT,
        max_weight=_MAX_WEIGHT,
    )
    if not outcome.passed:
        failures = ", ".join(
            f"{failure.code}:{failure.message}" for failure in outcome.failures
        )
        raise RuntimeError(
            f"verified-safe-coverage smoke independent verify failed: {failures}"
        )

    certificate = build_coverage_certificate(result, artifact_hashes={})
    cert_outcome = verify_coverage_certificate(certificate, result=result)
    if not cert_outcome.passed:
        failures = ", ".join(
            f"{failure.code}:{failure.message}" for failure in cert_outcome.failures
        )
        raise RuntimeError(
            f"verified-safe-coverage smoke certificate failed: {failures}"
        )

    return (
        "release smoke passed: "
        f"highspy={highspy_version} "
        f"numpy={numpy.__version__} "
        f"scipy={scipy.__version__} "
        f"solver={result.solver_name} "
        f"release={len(result.release_set)} "
        f"suppression={len(result.suppression_set)} "
        "verify=passed certificate=passed"
    )


if __name__ == "__main__":
    print(run())
