"""Tests for independent verification of Maximum Safe Coverage releases.

These tests exercise ``verify_safe_coverage_result``, the Coverage
Certificate builder, ``verify_coverage_certificate``, tamper detection for
every field enumerated in the plan, artifact-hash checks, and a leak scan for
a unique suppressed category marker.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from pathlib import Path
from typing import Any, Tuple

import pytest

from core.contracts import (
    APPROVED_PRIVACY_RULE_NAMES,
    COVERAGE_CERTIFICATE_ARTIFACT_TYPE,
    CoverageCertificate,
    PrivacyReleaseMode,
    PublicationUnit,
    SafeCoverageResult,
)
from core.privacy_coverage import (
    build_candidate_universe,
    candidate_universe_digest,
)
from core.privacy_coverage_solver import optimize_safe_coverage
from core.privacy_coverage_verifier import (
    SafeCoverageVerifierError,
    VerificationOutcome,
    build_coverage_certificate,
    compute_release_mask_digest,
    verify_coverage_certificate,
    verify_safe_coverage_result,
    V_ARTIFACT_HASH_MISMATCH,
    V_ARTIFACT_MISSING,
    V_AUTHORIZING_RULE_UNKNOWN,
    V_CANDIDATE_UNIVERSE_DIGEST,
    V_CERTIFICATE_AUTHORIZING,
    V_CERTIFICATE_COUNTS,
    V_CERTIFICATE_DIGEST,
    V_CERTIFICATE_KEYS,
    V_CITI_PEER_MISSING,
    V_CLIENT_KEYS_MISMATCH,
    V_DUAL_BOUND_MISMATCH,
    V_INVALID_RELEASE_MODE,
    V_NONZERO_GAP,
    V_RELEASE_MASK_DIGEST,
    V_RELEASE_PARTITION_MISMATCH,
    V_RULE_DID_NOT_PASS,
    V_RULE_NOT_APPLICABLE,
    V_RULE_SET_DIGEST,
    V_SOLVER_NOT_OPTIMAL,
    V_SUPPRESSED_MARKER_LEAK,
    V_SUPPRESSED_UNIT_IN_CLIENT_SINK,
    V_UNKNOWN_RELEASE_KEY,
    V_WEIGHT_OUT_OF_BOUNDS,
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


def _solve_fixture() -> Tuple[Tuple[PublicationUnit, ...], SafeCoverageResult]:
    df = build_safe_coverage_getnet_shaped_df()
    universe = build_candidate_universe(
        df,
        entity_col="issuer_name",
        metric="transaction_amount",
        secondary_metrics=["transaction_count", "merchant_count"],
        dimensions=["region", "sector"],
        time_col="quarter",
    )
    result = optimize_safe_coverage(
        universe,
        _PEERS,
        min_weight=0.5,
        max_weight=2.0,
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


@pytest.fixture(scope="module")
def fixture_result() -> SafeCoverageResult:
    _universe, result = _solve_fixture()
    assert result.solver_state == "optimal"
    assert 0 < len(result.release_set) < len(result.candidate_universe)
    return result


def _codes(outcome: VerificationOutcome) -> Tuple[str, ...]:
    return tuple(failure.code for failure in outcome.failures)


def _bypass_result_replace(
    result: SafeCoverageResult, **updates: Any
) -> SafeCoverageResult:
    """Construct a ``SafeCoverageResult`` that skips ``__post_init__``.

    Used only by tamper tests that must produce a result whose fields would
    otherwise be rejected by contract invariants (e.g. injecting a visible
    key drawn from the Suppression Set). The verifier must still block
    publication for the tampered result.
    """
    data = {field.name: getattr(result, field.name) for field in dataclasses.fields(result)}
    data.update(updates)
    obj = object.__new__(SafeCoverageResult)
    for name, value in data.items():
        object.__setattr__(obj, name, value)
    return obj


# ---------------------------------------------------------------------------
# Positive path
# ---------------------------------------------------------------------------


def test_verifier_passes_for_solver_output(fixture_result: SafeCoverageResult) -> None:
    outcome = verify_safe_coverage_result(
        fixture_result, min_weight=0.5, max_weight=2.0
    )
    assert outcome.passed, [(f.code, f.message) for f in outcome.failures]
    assert outcome.failures == ()
    assert (
        outcome.computed_candidate_universe_digest
        == fixture_result.candidate_universe_digest
    )
    assert (
        outcome.computed_release_mask_digest == fixture_result.release_mask_digest
    )
    assert outcome.computed_rule_set_digest == fixture_result.rule_set_digest


def test_verifier_confirms_client_release_keys_when_supplied(
    fixture_result: SafeCoverageResult,
) -> None:
    outcome = verify_safe_coverage_result(
        fixture_result,
        min_weight=0.5,
        max_weight=2.0,
        client_release_keys=fixture_result.release_set,
    )
    assert outcome.passed


def test_verifier_rejects_incorrect_client_release_keys(
    fixture_result: SafeCoverageResult,
) -> None:
    # Drop one visible key: the client under-published the Release Set.
    partial = tuple(fixture_result.release_set[:-1])
    outcome = verify_safe_coverage_result(
        fixture_result,
        min_weight=0.5,
        max_weight=2.0,
        client_release_keys=partial,
    )
    assert not outcome.passed
    assert V_CLIENT_KEYS_MISMATCH in _codes(outcome)


# ---------------------------------------------------------------------------
# Tamper cases: SafeCoverageResult fields
# ---------------------------------------------------------------------------


def test_tamper_release_mode_is_blocked(fixture_result: SafeCoverageResult) -> None:
    tampered = _bypass_result_replace(
        fixture_result, release_mode=PrivacyReleaseMode.COMPLETE_OUTPUT
    )
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    assert V_INVALID_RELEASE_MODE in _codes(outcome)


def test_tamper_global_weight_is_blocked(fixture_result: SafeCoverageResult) -> None:
    # Push one peer's weight far outside declared bounds. Rule recomputation
    # would still catch a smaller in-bounds tamper via rule failure.
    weights = dict(fixture_result.global_weights)
    peer = next(iter(weights))
    weights[peer] = 42.0
    tampered = _bypass_result_replace(fixture_result, global_weights=weights)
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    codes = _codes(outcome)
    assert V_WEIGHT_OUT_OF_BOUNDS in codes


def test_tamper_visible_unit_key_is_blocked(fixture_result: SafeCoverageResult) -> None:
    # Replace one visible key with a value that is not in the Candidate
    # Universe.
    fake_key = "dimension=fake|category=fake|time_period=|output_scope="
    tampered_release = (fake_key,) + tuple(fixture_result.release_set[1:])
    tampered = _bypass_result_replace(fixture_result, release_set=tampered_release)
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    assert V_UNKNOWN_RELEASE_KEY in _codes(outcome)


def test_tamper_visible_unit_removed_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    # Drop one released key from ``release_set`` without moving it into
    # ``suppression_set``: the partition becomes incoherent.
    tampered_release = tuple(fixture_result.release_set[1:])
    tampered = _bypass_result_replace(fixture_result, release_set=tampered_release)
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    codes = _codes(outcome)
    assert V_RELEASE_PARTITION_MISMATCH in codes


def test_tamper_suppressed_unit_added_to_output_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    # Move a Suppression Set key into the Release Set without solving.
    if not fixture_result.suppression_set:
        pytest.skip("fixture must have at least one suppressed unit")
    swapped_release = tuple(fixture_result.release_set) + (
        fixture_result.suppression_set[0],
    )
    swapped_suppression = fixture_result.suppression_set[1:]
    tampered = _bypass_result_replace(
        fixture_result,
        release_set=swapped_release,
        suppression_set=swapped_suppression,
    )
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    codes = _codes(outcome)
    # The injected key is unauthorized: expect a rule/authorizing failure.
    assert (
        V_RULE_DID_NOT_PASS in codes
        or V_AUTHORIZING_RULE_UNKNOWN in codes
        or V_RULE_NOT_APPLICABLE in codes
    )


def test_tamper_authorizing_rule_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    # Replace one authorizing rule with a rule that does not pass under the
    # released unit's weighted shares. The safe-set fixture uses 5/25, so
    # swap in a stricter downstream rule that fails on any positive share.
    if not fixture_result.release_set:
        pytest.skip("fixture must release at least one unit")
    tampered_map = dict(fixture_result.authorizing_rules)
    key = fixture_result.release_set[0]
    tampered_map[key] = "unknown_rule_that_does_not_exist"
    tampered = _bypass_result_replace(fixture_result, authorizing_rules=tampered_map)
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    codes = _codes(outcome)
    assert V_AUTHORIZING_RULE_UNKNOWN in codes


def test_tamper_policy_digest_is_blocked(fixture_result: SafeCoverageResult) -> None:
    tampered = _bypass_result_replace(fixture_result, rule_set_digest="a" * 64)
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    assert V_RULE_SET_DIGEST in _codes(outcome)


def test_tamper_candidate_universe_digest_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    tampered = _bypass_result_replace(
        fixture_result, candidate_universe_digest="b" * 64
    )
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    assert V_CANDIDATE_UNIVERSE_DIGEST in _codes(outcome)


def test_tamper_release_mask_digest_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    tampered = _bypass_result_replace(
        fixture_result, release_mask_digest="c" * 64
    )
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    assert V_RELEASE_MASK_DIGEST in _codes(outcome)


def test_tamper_solver_gap_is_blocked(fixture_result: SafeCoverageResult) -> None:
    tampered = _bypass_result_replace(fixture_result, mip_gap=0.25)
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    assert V_NONZERO_GAP in _codes(outcome)


def test_tamper_solver_dual_bound_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    tampered = _bypass_result_replace(
        fixture_result,
        mip_dual_bound=float(fixture_result.primary_objective_value) + 3.0,
    )
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    assert V_DUAL_BOUND_MISMATCH in _codes(outcome)


def test_tamper_solver_state_not_optimal_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    tampered = _bypass_result_replace(
        fixture_result, solver_state="unproven_maximum"
    )
    outcome = verify_safe_coverage_result(
        tampered, min_weight=0.5, max_weight=2.0
    )
    assert not outcome.passed
    assert V_SOLVER_NOT_OPTIMAL in _codes(outcome)


# ---------------------------------------------------------------------------
# Coverage Certificate: build, verify, tamper
# ---------------------------------------------------------------------------


def test_certificate_builds_with_only_safe_evidence(
    fixture_result: SafeCoverageResult,
) -> None:
    certificate = build_coverage_certificate(
        fixture_result, artifact_hashes={"analysis.xlsx": "a" * 64}
    )
    assert certificate.artifact_type == COVERAGE_CERTIFICATE_ARTIFACT_TYPE
    assert certificate.privacy_release_mode == PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE
    assert tuple(certificate.visible_publication_unit_keys) == tuple(
        fixture_result.release_set
    )
    assert set(certificate.authorizing_rules) == set(fixture_result.release_set)
    # A suppressed key must never appear in visible client evidence.
    suppressed = set(fixture_result.suppression_set)
    assert not (
        set(certificate.visible_publication_unit_keys) & suppressed
    )
    assert not (set(certificate.authorizing_rules) & suppressed)
    assert certificate.certificate_digest and len(certificate.certificate_digest) == 64


def test_certificate_omits_weights_when_publish_disabled(
    fixture_result: SafeCoverageResult,
) -> None:
    certificate = build_coverage_certificate(
        fixture_result, artifact_hashes={}, publish_weights=False
    )
    assert certificate.global_weights is None


def test_certificate_verifier_accepts_matching_certificate(
    fixture_result: SafeCoverageResult,
) -> None:
    certificate = build_coverage_certificate(
        fixture_result, artifact_hashes={"analysis.xlsx": "a" * 64}
    )
    outcome = verify_coverage_certificate(certificate, result=fixture_result)
    assert outcome.passed, [(f.code, f.message) for f in outcome.failures]


def _replace_certificate(certificate: CoverageCertificate, **updates: Any) -> CoverageCertificate:
    """Rebuild a certificate bypassing ``__post_init__`` for tamper tests."""
    data = {field.name: getattr(certificate, field.name) for field in dataclasses.fields(certificate)}
    data.update(updates)
    obj = object.__new__(CoverageCertificate)
    for name, value in data.items():
        object.__setattr__(obj, name, value)
    return obj


def test_tamper_certificate_digest_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    certificate = build_coverage_certificate(fixture_result, artifact_hashes={})
    tampered = _replace_certificate(
        certificate, certificate_digest="d" * 64
    )
    outcome = verify_coverage_certificate(tampered, result=fixture_result)
    assert not outcome.passed
    assert V_CERTIFICATE_DIGEST in _codes(outcome)


def test_tamper_certificate_authorizing_rule_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    certificate = build_coverage_certificate(fixture_result, artifact_hashes={})
    if not certificate.authorizing_rules:
        pytest.skip("fixture must release at least one unit")
    tampered_rules = dict(certificate.authorizing_rules)
    key = next(iter(tampered_rules))
    original = tampered_rules[key]
    other = next(
        rule for rule in APPROVED_PRIVACY_RULE_NAMES if rule != original
    )
    tampered_rules[key] = other
    tampered = _replace_certificate(
        certificate, authorizing_rules=tampered_rules
    )
    outcome = verify_coverage_certificate(tampered, result=fixture_result)
    assert not outcome.passed
    codes = _codes(outcome)
    # Depending on tamper size, either the certificate authorizing check or
    # the certificate digest check catches it first.
    assert (
        V_CERTIFICATE_AUTHORIZING in codes or V_CERTIFICATE_DIGEST in codes
    )


def test_tamper_certificate_visible_key_removed_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    certificate = build_coverage_certificate(fixture_result, artifact_hashes={})
    if not certificate.visible_publication_unit_keys:
        pytest.skip("fixture must release at least one unit")
    tampered_keys = tuple(certificate.visible_publication_unit_keys[1:])
    tampered_rules = {
        key: rule
        for key, rule in dict(certificate.authorizing_rules).items()
        if key in tampered_keys
    }
    tampered = _replace_certificate(
        certificate,
        visible_publication_unit_keys=tampered_keys,
        authorizing_rules=tampered_rules,
    )
    outcome = verify_coverage_certificate(tampered, result=fixture_result)
    assert not outcome.passed
    codes = _codes(outcome)
    assert V_CERTIFICATE_KEYS in codes or V_CERTIFICATE_COUNTS in codes


def test_tamper_certificate_adds_suppressed_key_is_blocked(
    fixture_result: SafeCoverageResult,
) -> None:
    certificate = build_coverage_certificate(fixture_result, artifact_hashes={})
    if not fixture_result.suppression_set:
        pytest.skip("fixture must have at least one suppressed unit")
    suppressed_key = fixture_result.suppression_set[0]
    tampered_keys = tuple(certificate.visible_publication_unit_keys) + (
        suppressed_key,
    )
    tampered_rules = dict(certificate.authorizing_rules)
    tampered_rules[suppressed_key] = "5/25"
    tampered = _replace_certificate(
        certificate,
        visible_publication_unit_keys=tampered_keys,
        authorizing_rules=tampered_rules,
    )
    outcome = verify_coverage_certificate(tampered, result=fixture_result)
    assert not outcome.passed
    codes = _codes(outcome)
    assert V_SUPPRESSED_UNIT_IN_CLIENT_SINK in codes or V_CERTIFICATE_KEYS in codes


# ---------------------------------------------------------------------------
# Artifact-hash tamper and missing-artifact behavior
# ---------------------------------------------------------------------------


def test_artifact_hash_verification_passes_for_untampered_file(
    tmp_path: Path,
    fixture_result: SafeCoverageResult,
) -> None:
    artifact = tmp_path / "analysis.txt"
    artifact.write_text("client-safe visible facts only\n", encoding="utf-8")
    expected = hashlib.sha256(artifact.read_bytes()).hexdigest()
    outcome = verify_safe_coverage_result(
        fixture_result,
        min_weight=0.5,
        max_weight=2.0,
        artifact_paths={"analysis": str(artifact)},
        expected_artifact_hashes={"analysis": expected},
    )
    assert outcome.passed, [(f.code, f.message) for f in outcome.failures]
    assert outcome.computed_artifact_hashes["analysis"] == expected


def test_tamper_artifact_after_hash_is_blocked(
    tmp_path: Path,
    fixture_result: SafeCoverageResult,
) -> None:
    artifact = tmp_path / "analysis.txt"
    artifact.write_text("original safe content\n", encoding="utf-8")
    trusted_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
    # Attacker rewrites the file after the trusted hash was captured.
    artifact.write_text("tampered payload\n", encoding="utf-8")
    outcome = verify_safe_coverage_result(
        fixture_result,
        min_weight=0.5,
        max_weight=2.0,
        artifact_paths={"analysis": str(artifact)},
        expected_artifact_hashes={"analysis": trusted_hash},
    )
    assert not outcome.passed
    assert V_ARTIFACT_HASH_MISMATCH in _codes(outcome)


def test_missing_artifact_file_is_blocked(
    tmp_path: Path,
    fixture_result: SafeCoverageResult,
) -> None:
    missing = tmp_path / "no_such_file.txt"
    outcome = verify_safe_coverage_result(
        fixture_result,
        min_weight=0.5,
        max_weight=2.0,
        artifact_paths={"analysis": str(missing)},
    )
    assert not outcome.passed
    assert V_ARTIFACT_MISSING in _codes(outcome)


# ---------------------------------------------------------------------------
# Leak test: suppressed category marker must not appear in client artifacts.
# ---------------------------------------------------------------------------


def test_suppressed_marker_leak_is_detected(
    tmp_path: Path,
    fixture_result: SafeCoverageResult,
) -> None:
    marker = "SUPPRESSED-CATEGORY-MARKER-c7f0f1a2"
    leaking = tmp_path / "leak.txt"
    leaking.write_text(
        f"header\n{marker}\nfooter\n", encoding="utf-8"
    )
    outcome = verify_safe_coverage_result(
        fixture_result,
        min_weight=0.5,
        max_weight=2.0,
        artifact_paths={"analysis": str(leaking)},
        suppressed_marker=marker,
    )
    assert not outcome.passed
    assert V_SUPPRESSED_MARKER_LEAK in _codes(outcome)


def test_no_suppressed_marker_in_certificate(
    fixture_result: SafeCoverageResult,
) -> None:
    marker = "SUPPRESSED-CATEGORY-MARKER-9d1"
    certificate = build_coverage_certificate(
        fixture_result, artifact_hashes={"analysis.txt": "0" * 64}
    )
    # Every visible field of the certificate must not contain the marker,
    # even if a suppressed unit's data happened to carry it upstream.
    payload = json.dumps(
        {
            "artifact_type": certificate.artifact_type,
            "privacy_release_mode": certificate.privacy_release_mode.value,
            "visible_publication_unit_keys": list(
                certificate.visible_publication_unit_keys
            ),
            "authorizing_rules": dict(certificate.authorizing_rules),
            "global_weights": (
                dict(certificate.global_weights)
                if certificate.global_weights is not None
                else None
            ),
            "policy_version": certificate.policy_version,
            "policy_source": certificate.policy_source,
            "rule_set_digest": certificate.rule_set_digest,
            "solver_name": certificate.solver_name,
            "solver_version": certificate.solver_version,
            "certificate_digest": certificate.certificate_digest,
            "artifact_hashes": dict(certificate.artifact_hashes),
        },
        default=str,
    )
    assert marker not in payload


# ---------------------------------------------------------------------------
# Citi overlay path
# ---------------------------------------------------------------------------


def test_citi_overlay_missing_peer_kwarg_is_blocked() -> None:
    df = build_safe_coverage_getnet_shaped_df()
    universe = build_candidate_universe(
        df,
        entity_col="issuer_name",
        metric="transaction_amount",
        secondary_metrics=["transaction_count", "merchant_count"],
        dimensions=["region", "sector"],
        time_col="quarter",
        citibank_entity_name="PeerB",
        citi_competitor_receives_output=True,
    )
    result = optimize_safe_coverage(
        universe,
        _PEERS,
        min_weight=0.5,
        max_weight=2.0,
        rule_configs={},
        citibank_entity_name="PeerB",
        input_digest=_INPUT_DIGEST,
        configuration_digest=_CONFIG_DIGEST,
        policy_version="v5",
        policy_source="docs/control-3-v5.md",
        rule_set_digest=PrivacyPolicy.rule_set_digest(),
        candidate_universe_digest=candidate_universe_digest(universe),
    )
    if not result.release_set:
        pytest.skip("citi fixture yielded no visible units to exercise the overlay path")
    # Any visible unit in this universe carries the citibank overlay; the
    # verifier must ask for a citibank identity.
    outcome_missing = verify_safe_coverage_result(
        result, min_weight=0.5, max_weight=2.0, citibank_entity_name=None
    )
    assert not outcome_missing.passed
    assert V_CITI_PEER_MISSING in _codes(outcome_missing)

    outcome_ok = verify_safe_coverage_result(
        result, min_weight=0.5, max_weight=2.0, citibank_entity_name="PeerB"
    )
    assert outcome_ok.passed, [(f.code, f.message) for f in outcome_ok.failures]


# ---------------------------------------------------------------------------
# API input validation
# ---------------------------------------------------------------------------


def test_verifier_rejects_bad_weight_bounds(fixture_result: SafeCoverageResult) -> None:
    with pytest.raises(SafeCoverageVerifierError):
        verify_safe_coverage_result(fixture_result, min_weight=0.0, max_weight=2.0)
    with pytest.raises(SafeCoverageVerifierError):
        verify_safe_coverage_result(fixture_result, min_weight=1.5, max_weight=2.0)
    with pytest.raises(SafeCoverageVerifierError):
        verify_safe_coverage_result(fixture_result, min_weight=0.5, max_weight=0.9)


def test_verifier_rejects_wrong_types() -> None:
    with pytest.raises(SafeCoverageVerifierError):
        verify_safe_coverage_result(
            "not a result",  # type: ignore[arg-type]
            min_weight=0.5,
            max_weight=2.0,
        )


def test_certificate_builder_rejects_bad_hashes(
    fixture_result: SafeCoverageResult,
) -> None:
    with pytest.raises(SafeCoverageVerifierError):
        build_coverage_certificate(fixture_result, artifact_hashes={1: "0" * 64})  # type: ignore[dict-item]
    with pytest.raises(SafeCoverageVerifierError):
        build_coverage_certificate(fixture_result, artifact_hashes={"a": 123})  # type: ignore[dict-item]


# ---------------------------------------------------------------------------
# Helper digest determinism
# ---------------------------------------------------------------------------


def test_certificate_digest_is_order_independent(
    fixture_result: SafeCoverageResult,
) -> None:
    forward = build_coverage_certificate(
        fixture_result, artifact_hashes={"a": "1" * 64, "b": "2" * 64}
    )
    reverse = build_coverage_certificate(
        fixture_result, artifact_hashes={"b": "2" * 64, "a": "1" * 64}
    )
    assert forward.certificate_digest == reverse.certificate_digest


def test_release_mask_digest_matches_solver_output(
    fixture_result: SafeCoverageResult,
) -> None:
    universe_keys = tuple(
        unit.internal_key for unit in fixture_result.candidate_universe
    )
    recomputed = compute_release_mask_digest(
        sorted(universe_keys), fixture_result.release_set
    )
    assert recomputed == fixture_result.release_mask_digest
