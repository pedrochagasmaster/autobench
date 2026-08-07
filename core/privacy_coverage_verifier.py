"""Independent verification for Verified Safe Coverage releases.

This Module owns the fail-closed check that a
``SafeCoverageResult`` is genuinely publishable and the client-safe
``CoverageCertificate`` derived from it. It recalculates every release
decision from the original inputs (peer volumes in Publication Units) and the
final global weight vector using ``core.privacy_rules.evaluate_rule``. It does
not import a solver constraint helper, so a formulation defect in the MILP
model cannot silently propagate into an authorization.

Every verifier failure is a hard block. Failure codes and messages are
aggregate and client-safe; they must never embed a suppressed Publication Unit
key, a suppressed category name, or a protected source value.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from core.canonical_order import canonical_key
from core.constants import COMPARISON_EPSILON
from core.contracts import (
    APPROVED_PRIVACY_RULE_NAMES,
    COVERAGE_CERTIFICATE_ARTIFACT_TYPE,
    CoverageCertificate,
    PrivacyReleaseMode,
    PublicationUnit,
    SafeCoverageResult,
)
from core.privacy_coverage import (
    CITIBANK_OVERLAY_NAME,
    candidate_universe_digest,
)
from core.privacy_policy import PrivacyPolicy
from core.privacy_rules import evaluate_rule

__all__ = [
    "VerificationFailure",
    "VerificationOutcome",
    "SafeCoverageVerifierError",
    "verify_safe_coverage_result",
    "verify_coverage_certificate",
    "build_coverage_certificate",
    "compute_certificate_digest",
    "compute_release_mask_digest",
    "VERIFIER_RESULT_PASSED",
    "VERIFIER_RESULT_FAILED",
]

# Trusted status strings written back into ``SafeCoverageResult.verifier_result``.
# Solvers must emit ``"not_run"``; only a verifier pass may claim
# ``VERIFIER_RESULT_PASSED``.
VERIFIER_RESULT_PASSED = "verifier_passed"
VERIFIER_RESULT_FAILED = "verifier_failed"

_CITIBANK_MAXIMUM_SHARE = 25.0

# Aggregate, client-safe failure codes. Values are stable and are safe to
# expose in a denial audit or a diagnostic Interface, because they carry no
# suppressed key, suppressed category name, or protected source value.
V_INVALID_RELEASE_MODE = "verifier_invalid_release_mode"
V_UNKNOWN_RELEASE_KEY = "verifier_release_key_not_in_universe"
V_DUPLICATE_RELEASE_KEY = "verifier_release_key_duplicated"
V_RELEASE_PARTITION_MISMATCH = "verifier_release_partition_mismatch"
V_MISSING_METRIC = "verifier_visible_unit_missing_required_metric"
V_RULE_NOT_APPLICABLE = "verifier_authorizing_rule_not_applicable"
V_RULE_DID_NOT_PASS = "verifier_authorizing_rule_did_not_pass"
V_CITI_PEER_MISSING = "verifier_citibank_peer_not_identifiable"
V_CITI_OVERLAY_FAILED = "verifier_citibank_overlay_failed"
V_WEIGHT_MISSING = "verifier_weight_missing_for_governed_peer"
V_WEIGHT_OUT_OF_BOUNDS = "verifier_weight_out_of_bounds"
V_WEIGHT_NONFINITE = "verifier_weight_nonfinite"
V_CLIENT_KEYS_MISMATCH = "verifier_client_release_keys_mismatch"
V_SUPPRESSED_UNIT_IN_CLIENT_SINK = "verifier_suppressed_unit_in_client_sink"
V_SEARCH_STATE = "verifier_search_state_invalid"
V_WEIGHT_PARTITION_MISMATCH = "verifier_weight_partition_mismatch"
V_CANDIDATE_UNIVERSE_DIGEST = "verifier_candidate_universe_digest_mismatch"
V_RELEASE_MASK_DIGEST = "verifier_release_mask_digest_mismatch"
V_RULE_SET_DIGEST = "verifier_rule_set_digest_mismatch"
V_ARTIFACT_HASH_MISMATCH = "verifier_artifact_hash_mismatch"
V_ARTIFACT_MISSING = "verifier_artifact_missing"
V_SUPPRESSED_MARKER_LEAK = "verifier_suppressed_marker_in_client_sink"
V_AUTHORIZING_RULE_UNKNOWN = "verifier_authorizing_rule_unknown"
V_CERTIFICATE_TYPE = "verifier_certificate_artifact_type_mismatch"
V_CERTIFICATE_MODE = "verifier_certificate_release_mode_mismatch"
V_CERTIFICATE_COUNTS = "verifier_certificate_counts_mismatch"
V_CERTIFICATE_KEYS = "verifier_certificate_visible_keys_mismatch"
V_CERTIFICATE_AUTHORIZING = "verifier_certificate_authorizing_rules_mismatch"
V_CERTIFICATE_PROOF = "verifier_certificate_solver_proof_mismatch"
V_CERTIFICATE_DIGEST = "verifier_certificate_digest_mismatch"
V_CERTIFICATE_ARTIFACT_HASH = "verifier_certificate_artifact_hash_mismatch"
V_CERTIFICATE_POLICY = "verifier_certificate_policy_metadata_mismatch"

# Tolerance for bounds comparisons on continuous weight values. Chosen from a
# floating-point noise scale, not from any privacy epsilon; a weight tampered
# by more than this is caught by ``V_WEIGHT_OUT_OF_BOUNDS`` and a weight
# tampered by less than this is still caught by rule recomputation when it
# crosses a privacy threshold.
_WEIGHT_BOUND_TOLERANCE = 1e-9


class SafeCoverageVerifierError(ValueError):
    """Raised for structural input errors in the verifier public API.

    Runtime verification results are reported through ``VerificationOutcome``
    and never through this exception, so a fail-closed caller can treat the
    outcome uniformly.
    """


@dataclass(frozen=True)
class VerificationFailure:
    """One aggregate, client-safe verification failure."""

    code: str
    message: str


@dataclass(frozen=True)
class VerificationOutcome:
    """Result of independent verification. Fail-closed.

    ``passed`` is true only when every check succeeded. ``failures`` records
    each aggregate failing check for the safe denial audit. The recomputed
    digests and artifact hashes are the verifier's independent values, safe to
    compare against a stored trusted result or a client Coverage Certificate.
    """

    passed: bool
    failures: Tuple[VerificationFailure, ...]
    computed_release_mask_digest: str
    computed_candidate_universe_digest: str
    computed_rule_set_digest: str
    computed_artifact_hashes: Mapping[str, str]


def _fail(
    failures: List[VerificationFailure],
    code: str,
    message: str,
) -> None:
    failures.append(VerificationFailure(code=code, message=message))


def _sha256_file(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def compute_release_mask_digest(
    sorted_keys: Sequence[str],
    released_keys: Iterable[str],
) -> str:
    """Return the independently recomputed release-mask digest.

    Byte-identical to the solver's release-mask digest under a shared input,
    but implemented here so verification does not import a private solver
    helper. Any drift between the solver and this recomputation is flagged as
    a release-mask tamper by ``verify_safe_coverage_result``.
    """
    released_set = set(released_keys)
    mask_payload = [
        {"key": key, "released": key in released_set}
        for key in sorted_keys
    ]
    encoded = json.dumps(mask_payload, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _independent_weighted_shares(
    peer_volumes: Mapping[str, Any],
    weights: Mapping[str, float],
) -> Tuple[List[float], List[str]]:
    """Return positive-volume peer shares and their peer identities.

    Peers with zero source volume are dropped, matching the structural
    participant count used by ``evaluate_rule``. Missing peers in ``weights``
    default to a neutral multiplier of ``1.0``; the "every peer has a weight"
    check is performed separately so verification also flags a missing weight
    even when a rule recomputation still passes.
    """
    positive: List[Tuple[str, float, float]] = []
    for peer, volume in peer_volumes.items():
        try:
            raw = float(volume)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(raw) or raw <= 0.0:
            continue
        try:
            multiplier = float(weights.get(peer, 1.0))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(multiplier):
            continue
        positive.append((str(peer), raw, raw * multiplier))
    total = sum(weighted for _peer, _raw, weighted in positive)
    if total <= 0.0:
        return (
            [0.0 for _peer, _raw, _weighted in positive],
            [peer for peer, _raw, _weighted in positive],
        )
    shares = [100.0 * weighted / total for _peer, _raw, weighted in positive]
    peers = [peer for peer, _raw, _weighted in positive]
    return shares, peers


def _resolve_citi_peer(
    universe: Sequence[PublicationUnit],
    citibank_entity_name: Optional[str],
) -> Optional[str]:
    if not citibank_entity_name:
        return None
    needle = str(citibank_entity_name).casefold()
    seen: Dict[str, None] = {}
    for unit in universe:
        for record in unit.metric_records:
            for peer in record.get("peer_volumes", {}):
                if isinstance(peer, str) and peer.casefold() == needle:
                    seen.setdefault(peer, None)
    peers = list(seen)
    if len(peers) != 1:
        return None
    return peers[0]


def _check_release_partition(
    result: SafeCoverageResult,
    universe_by_key: Mapping[str, PublicationUnit],
    failures: List[VerificationFailure],
) -> None:
    release_keys = tuple(result.release_set)
    suppression_keys = tuple(result.suppression_set)

    if len(set(release_keys)) != len(release_keys):
        _fail(
            failures,
            V_DUPLICATE_RELEASE_KEY,
            "one or more Publication Unit keys appear more than once in the Release Set",
        )

    unknown = [key for key in release_keys if key not in universe_by_key]
    if unknown:
        _fail(
            failures,
            V_UNKNOWN_RELEASE_KEY,
            f"{len(unknown)} released Publication Unit key(s) are not in the Candidate Universe",
        )

    canonical_set = set(universe_by_key)
    if (
        set(release_keys) & set(suppression_keys)
        or set(release_keys) | set(suppression_keys) != canonical_set
    ):
        _fail(
            failures,
            V_RELEASE_PARTITION_MISMATCH,
            "the Release Set and Suppression Set must partition the Candidate Universe exactly",
        )


def _check_weight_bounds(
    result: SafeCoverageResult,
    min_weight: float,
    max_weight: float,
    failures: List[VerificationFailure],
) -> None:
    for _peer, value in result.global_weights.items():
        numeric = float(value)
        if not math.isfinite(numeric):
            _fail(
                failures,
                V_WEIGHT_NONFINITE,
                "a global weight value is not a finite number",
            )
            continue
        low = min_weight - _WEIGHT_BOUND_TOLERANCE
        high = max_weight + _WEIGHT_BOUND_TOLERANCE
        if numeric < low or numeric > high:
            _fail(
                failures,
                V_WEIGHT_OUT_OF_BOUNDS,
                "a global weight lies outside the declared weight bounds",
            )


def _check_governed_peer_weight_coverage(
    universe_by_key: Mapping[str, PublicationUnit],
    release_keys: Sequence[str],
    weights: Mapping[str, float],
    failures: List[VerificationFailure],
) -> None:
    reported = False
    for key in release_keys:
        unit = universe_by_key.get(key)
        if unit is None:
            continue
        for record in unit.metric_records:
            for peer, volume in record.get("peer_volumes", {}).items():
                try:
                    raw = float(volume)
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(raw) or raw <= 0.0:
                    continue
                if peer not in weights:
                    if not reported:
                        _fail(
                            failures,
                            V_WEIGHT_MISSING,
                            "a governed peer with positive volume in a visible unit has no global weight",
                        )
                        reported = True
                    return


def _check_visible_unit_rules(
    result: SafeCoverageResult,
    universe_by_key: Mapping[str, PublicationUnit],
    citi_peer: Optional[str],
    citibank_entity_name: Optional[str],
    failures: List[VerificationFailure],
) -> None:
    weights = result.global_weights
    for released_key in result.release_set:
        unit = universe_by_key.get(released_key)
        if unit is None:
            # Already flagged by universe-membership check.
            continue

        rule_name = result.authorizing_rules.get(released_key)
        if rule_name is None:
            _fail(
                failures,
                V_AUTHORIZING_RULE_UNKNOWN,
                "a visible Publication Unit has no recorded authorizing rule",
            )
            continue
        if rule_name not in APPROVED_PRIVACY_RULE_NAMES:
            _fail(
                failures,
                V_AUTHORIZING_RULE_UNKNOWN,
                "a visible Publication Unit's authorizing rule is not an approved rule",
            )
            continue
        if rule_name not in unit.applicable_rules:
            _fail(
                failures,
                V_RULE_NOT_APPLICABLE,
                "a visible Publication Unit's authorizing rule is not applicable to that unit",
            )
            continue

        rule_pass = True
        for record in unit.metric_records:
            volumes = record.get("peer_volumes", {})
            if not volumes:
                _fail(
                    failures,
                    V_MISSING_METRIC,
                    "a visible Publication Unit is missing peer volumes for a required metric",
                )
                rule_pass = False
                break
            shares, _peers = _independent_weighted_shares(volumes, weights)
            evaluation = evaluate_rule(rule_name, shares)
            if not evaluation.strict_passed:
                _fail(
                    failures,
                    V_RULE_DID_NOT_PASS,
                    "a visible Publication Unit did not satisfy its authorizing rule on recomputation",
                )
                rule_pass = False
                break

        if not rule_pass:
            continue

        if CITIBANK_OVERLAY_NAME in unit.mandatory_overlays:
            if citi_peer is None:
                _fail(
                    failures,
                    V_CITI_PEER_MISSING,
                    (
                        "citibank peer identity was required for overlay verification "
                        "but could not be resolved from the Candidate Universe"
                        if citibank_entity_name
                        else
                        "a visible Publication Unit carries the citibank overlay but "
                        "no citibank_entity_name was provided to the verifier"
                    ),
                )
                continue
            overlay_pass = True
            for record in unit.metric_records:
                shares, peers = _independent_weighted_shares(
                    record.get("peer_volumes", {}), weights
                )
                if citi_peer in peers:
                    citi_share = shares[peers.index(citi_peer)]
                    if citi_share > _CITIBANK_MAXIMUM_SHARE + COMPARISON_EPSILON:
                        overlay_pass = False
                        break
            if not overlay_pass:
                _fail(
                    failures,
                    V_CITI_OVERLAY_FAILED,
                    "a visible Publication Unit failed the citibank overlay on recomputation",
                )


def _check_search_contract(
    result: SafeCoverageResult,
    failures: List[VerificationFailure],
) -> None:
    if result.search_state != "search_complete":
        _fail(
            failures,
            V_SEARCH_STATE,
            "search_state must be 'search_complete'",
        )
    if not result.search_method or result.candidate_vectors_evaluated < 1:
        _fail(
            failures,
            V_SEARCH_STATE,
            "search metadata is incomplete",
        )


def _check_exact_partition_for_weights(
    result: SafeCoverageResult,
    universe_by_key: Mapping[str, PublicationUnit],
    citi_peer: Optional[str],
    failures: List[VerificationFailure],
) -> None:
    expected_release: List[str] = []
    expected_authorizing: Dict[str, str] = {}
    for key in sorted(universe_by_key, key=canonical_key):
        unit = universe_by_key[key]
        overlay_passed = True
        if CITIBANK_OVERLAY_NAME in unit.mandatory_overlays:
            if citi_peer is None:
                overlay_passed = False
            else:
                for record in unit.metric_records:
                    shares, peers = _independent_weighted_shares(
                        record.get("peer_volumes", {}),
                        result.global_weights,
                    )
                    if citi_peer in peers:
                        citi_share = shares[peers.index(citi_peer)]
                        if (
                            citi_share
                            > _CITIBANK_MAXIMUM_SHARE + COMPARISON_EPSILON
                        ):
                            overlay_passed = False
                            break
        if not overlay_passed:
            continue
        for rule_name in sorted(unit.applicable_rules, key=canonical_key):
            passed = True
            for record in unit.metric_records:
                shares, _peers = _independent_weighted_shares(
                    record.get("peer_volumes", {}),
                    result.global_weights,
                )
                if not evaluate_rule(rule_name, shares).strict_passed:
                    passed = False
                    break
            if passed:
                expected_release.append(key)
                expected_authorizing[key] = rule_name
                break
    if (
        tuple(expected_release) != tuple(result.release_set)
        or expected_authorizing != dict(result.authorizing_rules)
    ):
        _fail(
            failures,
            V_WEIGHT_PARTITION_MISMATCH,
            "the selected weights do not produce the recorded release partition",
        )


def verify_safe_coverage_result(
    result: SafeCoverageResult,
    *,
    min_weight: float,
    max_weight: float,
    citibank_entity_name: Optional[str] = None,
    client_release_keys: Optional[Iterable[str]] = None,
    artifact_paths: Optional[Mapping[str, str]] = None,
    expected_artifact_hashes: Optional[Mapping[str, str]] = None,
    suppressed_marker: Optional[str] = None,
) -> VerificationOutcome:
    """Independently verify a ``SafeCoverageResult`` fail-closed.

    Recalculates every visible-unit release decision from the Candidate
    Universe stored on ``result`` and from ``result.global_weights`` using
    ``evaluate_rule``. Checks the exact weight partition, digests, weight
    bounds, and client-sink invariants. When ``artifact_paths`` is provided,
    also recomputes SHA-256 hashes of every declared client artifact and, if
    ``expected_artifact_hashes`` is provided, compares them to detect a
    post-hash tamper. When ``suppressed_marker`` is provided, scans each
    declared client artifact for that marker; a leak fails verification.
    """
    if not isinstance(result, SafeCoverageResult):
        raise SafeCoverageVerifierError("result must be a SafeCoverageResult value")
    if isinstance(min_weight, bool) or not isinstance(min_weight, (int, float)):
        raise SafeCoverageVerifierError("min_weight must be a number")
    if isinstance(max_weight, bool) or not isinstance(max_weight, (int, float)):
        raise SafeCoverageVerifierError("max_weight must be a number")
    if (
        not math.isfinite(min_weight)
        or not math.isfinite(max_weight)
        or min_weight <= 0.0
        or min_weight > 1.0
        or max_weight < 1.0
        or max_weight < min_weight
    ):
        raise SafeCoverageVerifierError(
            "weight bounds must satisfy 0 < min_weight <= 1 <= max_weight"
        )

    failures: List[VerificationFailure] = []

    if result.release_mode != PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE:
        _fail(
            failures,
            V_INVALID_RELEASE_MODE,
            f"release_mode must be VERIFIED_SAFE_COVERAGE; got {result.release_mode.value!r}",
        )

    universe_by_key: Dict[str, PublicationUnit] = {
        unit.internal_key: unit for unit in result.candidate_universe
    }
    canonical_universe_keys = tuple(
        sorted(universe_by_key.keys(), key=canonical_key)
    )

    _check_release_partition(result, universe_by_key, failures)
    _check_weight_bounds(result, min_weight, max_weight, failures)
    _check_governed_peer_weight_coverage(
        universe_by_key,
        result.release_set,
        result.global_weights,
        failures,
    )

    citi_peer = _resolve_citi_peer(result.candidate_universe, citibank_entity_name)
    _check_visible_unit_rules(
        result,
        universe_by_key,
        citi_peer,
        citibank_entity_name,
        failures,
    )
    _check_exact_partition_for_weights(
        result,
        universe_by_key,
        citi_peer,
        failures,
    )
    _check_search_contract(result, failures)

    computed_universe_digest = candidate_universe_digest(result.candidate_universe)
    if computed_universe_digest != result.candidate_universe_digest:
        _fail(
            failures,
            V_CANDIDATE_UNIVERSE_DIGEST,
            "Candidate Universe digest does not match the trusted universe contents",
        )

    computed_mask_digest = compute_release_mask_digest(
        canonical_universe_keys,
        result.release_set,
    )
    if computed_mask_digest != result.release_mask_digest:
        _fail(
            failures,
            V_RELEASE_MASK_DIGEST,
            "release-mask digest does not match the trusted Release Set",
        )

    computed_rule_digest = PrivacyPolicy.rule_set_digest()
    if computed_rule_digest != result.rule_set_digest:
        _fail(
            failures,
            V_RULE_SET_DIGEST,
            "active rule-set digest does not match the trusted policy digest",
        )

    if client_release_keys is not None:
        client_set = {str(key) for key in client_release_keys}
        if client_set != set(result.release_set):
            _fail(
                failures,
                V_CLIENT_KEYS_MISMATCH,
                "client release keys do not equal the trusted Release Set",
            )
        elif any(key in set(result.suppression_set) for key in client_set):
            # Defensive: partition invariant already blocks this, but keep an
            # explicit check because the certificate is the only sink observed
            # by many clients.
            _fail(
                failures,
                V_SUPPRESSED_UNIT_IN_CLIENT_SINK,
                "a suppressed Publication Unit key appears in the client release keys",
            )

    computed_hashes: Dict[str, str] = {}
    if artifact_paths:
        for name, path in artifact_paths.items():
            name_str = str(name)
            try:
                digest = _sha256_file(path)
            except OSError:
                _fail(
                    failures,
                    V_ARTIFACT_MISSING,
                    "a declared client artifact could not be read for hash verification",
                )
                continue
            computed_hashes[name_str] = digest
            if expected_artifact_hashes is not None:
                expected = expected_artifact_hashes.get(name)
                if expected is None or str(expected) != digest:
                    _fail(
                        failures,
                        V_ARTIFACT_HASH_MISMATCH,
                        "a client artifact hash does not match the trusted value",
                    )

    if suppressed_marker is not None and artifact_paths:
        marker = str(suppressed_marker)
        if marker:
            leak_reported = False
            marker_bytes = marker.encode("utf-8")
            for _name, path in artifact_paths.items():
                if leak_reported:
                    break
                try:
                    with open(path, "rb") as handle:
                        blob = handle.read()
                except OSError:
                    # Missing files are already flagged; do not double-report.
                    continue
                if marker_bytes in blob:
                    _fail(
                        failures,
                        V_SUPPRESSED_MARKER_LEAK,
                        "a suppressed category marker was detected in a client artifact",
                    )
                    leak_reported = True

    return VerificationOutcome(
        passed=not failures,
        failures=tuple(failures),
        computed_release_mask_digest=computed_mask_digest,
        computed_candidate_universe_digest=computed_universe_digest,
        computed_rule_set_digest=computed_rule_digest,
        computed_artifact_hashes=dict(computed_hashes),
    )


def compute_certificate_digest(
    *,
    artifact_type: str,
    privacy_release_mode: PrivacyReleaseMode,
    candidate_unit_count: int,
    released_unit_count: int,
    suppressed_unit_count: int,
    coverage_percentage: float,
    visible_publication_unit_keys: Sequence[str],
    authorizing_rules: Mapping[str, str],
    global_weights: Optional[Mapping[str, float]],
    policy_version: str,
    policy_source: str,
    rule_set_digest: str,
    solver_name: str,
    solver_version: str,
    search_method: str,
    search_state: str,
    candidate_vectors_evaluated: int,
    artifact_hashes: Mapping[str, str],
) -> str:
    """Return the SHA-256 digest over canonical safe Coverage Certificate fields.

    The canonical form sorts every embedded mapping by key and rejects
    non-finite floats, so two byte-identical certificates produce identical
    digests regardless of dict iteration order or ``PYTHONHASHSEED``.
    """
    if not isinstance(privacy_release_mode, PrivacyReleaseMode):
        raise SafeCoverageVerifierError(
            "privacy_release_mode must be a PrivacyReleaseMode value"
        )
    weights_payload: Optional[Dict[str, float]]
    if global_weights is None:
        weights_payload = None
    else:
        weights_payload = {}
        for peer, weight in global_weights.items():
            numeric = float(weight)
            if not math.isfinite(numeric):
                raise SafeCoverageVerifierError(
                    "global_weights values must be finite for digest computation"
                )
            weights_payload[str(peer)] = numeric

    coverage = float(coverage_percentage)
    if not math.isfinite(coverage):
        raise SafeCoverageVerifierError(
            "coverage must be finite for digest computation"
        )

    canonical = {
        "artifact_type": str(artifact_type),
        "privacy_release_mode": privacy_release_mode.value,
        "candidate_unit_count": int(candidate_unit_count),
        "released_unit_count": int(released_unit_count),
        "suppressed_unit_count": int(suppressed_unit_count),
        "coverage_percentage": coverage,
        "visible_publication_unit_keys": [
            str(key) for key in visible_publication_unit_keys
        ],
        "authorizing_rules": {
            str(key): str(rule)
            for key, rule in sorted(dict(authorizing_rules).items())
        },
        "global_weights": (
            {peer: weights_payload[peer] for peer in sorted(weights_payload)}
            if weights_payload is not None
            else None
        ),
        "policy_version": str(policy_version),
        "policy_source": str(policy_source),
        "rule_set_digest": str(rule_set_digest),
        "solver_name": str(solver_name),
        "solver_version": str(solver_version),
        "search_method": str(search_method),
        "search_state": str(search_state),
        "candidate_vectors_evaluated": int(candidate_vectors_evaluated),
        "artifact_hashes": {
            str(key): str(value)
            for key, value in sorted(dict(artifact_hashes).items())
        },
    }
    encoded = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def build_coverage_certificate(
    result: SafeCoverageResult,
    *,
    artifact_hashes: Mapping[str, str],
    publish_weights: bool = True,
) -> CoverageCertificate:
    """Build the client-safe Coverage Certificate.

    Contains only client-safe evidence: visible Publication Unit keys, their
    authorizing rules, aggregate counts, coverage percentage, policy and
    solver metadata, artifact hashes, and a self-digest. Never contains a
    suppressed unit key, a per-suppressed-key digest, a suppressed category
    name, or protected source values.

    Pass ``publish_weights=False`` when current policy does not permit
    publishing the global weight vector; the certificate then records
    ``global_weights=None`` and the digest reflects that absence.
    """
    if not isinstance(result, SafeCoverageResult):
        raise SafeCoverageVerifierError("result must be a SafeCoverageResult value")
    if not isinstance(artifact_hashes, Mapping):
        raise SafeCoverageVerifierError(
            "artifact_hashes must be a Mapping[str, str]"
        )
    frozen_hashes: Dict[str, str] = {}
    for name, digest in artifact_hashes.items():
        if not isinstance(name, str) or not isinstance(digest, str):
            raise SafeCoverageVerifierError(
                "artifact_hashes must map string names to string hex digests"
            )
        frozen_hashes[name] = digest

    candidate = len(result.candidate_universe)
    released = len(result.release_set)
    suppressed = len(result.suppression_set)
    coverage_pct = 0.0 if candidate == 0 else 100.0 * released / candidate

    weights_payload: Optional[Mapping[str, float]]
    if publish_weights:
        weights_payload = {
            peer: float(value) for peer, value in result.global_weights.items()
        }
    else:
        weights_payload = None

    digest = compute_certificate_digest(
        artifact_type=COVERAGE_CERTIFICATE_ARTIFACT_TYPE,
        privacy_release_mode=result.release_mode,
        candidate_unit_count=candidate,
        released_unit_count=released,
        suppressed_unit_count=suppressed,
        coverage_percentage=coverage_pct,
        visible_publication_unit_keys=result.release_set,
        authorizing_rules=result.authorizing_rules,
        global_weights=weights_payload,
        policy_version=result.policy_version,
        policy_source=result.policy_source,
        rule_set_digest=result.rule_set_digest,
        solver_name=result.solver_name,
        solver_version=result.solver_version,
        search_method=result.search_method,
        search_state=result.search_state,
        candidate_vectors_evaluated=result.candidate_vectors_evaluated,
        artifact_hashes=frozen_hashes,
    )

    return CoverageCertificate(
        privacy_release_mode=result.release_mode,
        candidate_unit_count=candidate,
        released_unit_count=released,
        suppressed_unit_count=suppressed,
        coverage_percentage=coverage_pct,
        visible_publication_unit_keys=tuple(result.release_set),
        authorizing_rules=dict(result.authorizing_rules),
        global_weights=weights_payload,
        policy_version=result.policy_version,
        policy_source=result.policy_source,
        rule_set_digest=result.rule_set_digest,
        solver_name=result.solver_name,
        solver_version=result.solver_version,
        search_method=result.search_method,
        search_state=result.search_state,
        candidate_vectors_evaluated=result.candidate_vectors_evaluated,
        artifact_hashes=frozen_hashes,
        certificate_digest=digest,
    )


def verify_coverage_certificate(
    certificate: CoverageCertificate,
    *,
    result: SafeCoverageResult,
    expected_artifact_hashes: Optional[Mapping[str, str]] = None,
) -> VerificationOutcome:
    """Verify a Coverage Certificate against its trusted result. Fail-closed.

    Detects tampering of the visible keys, authorizing rules, aggregate
    counts, coverage percentage, policy or solver metadata, artifact hashes,
    and the ``certificate_digest`` self-hash. When ``expected_artifact_hashes``
    is provided, also compares the certificate's stored hashes to those
    expected values.
    """
    if not isinstance(certificate, CoverageCertificate):
        raise SafeCoverageVerifierError(
            "certificate must be a CoverageCertificate value"
        )
    if not isinstance(result, SafeCoverageResult):
        raise SafeCoverageVerifierError("result must be a SafeCoverageResult value")

    failures: List[VerificationFailure] = []

    if certificate.artifact_type != COVERAGE_CERTIFICATE_ARTIFACT_TYPE:
        _fail(
            failures,
            V_CERTIFICATE_TYPE,
            "certificate artifact_type differs from the expected fixed value",
        )
    if certificate.privacy_release_mode != result.release_mode:
        _fail(
            failures,
            V_CERTIFICATE_MODE,
            "certificate privacy_release_mode differs from the trusted result",
        )

    if certificate.candidate_unit_count != len(result.candidate_universe):
        _fail(
            failures,
            V_CERTIFICATE_COUNTS,
            "certificate candidate_unit_count differs from the trusted result",
        )
    if certificate.released_unit_count != len(result.release_set):
        _fail(
            failures,
            V_CERTIFICATE_COUNTS,
            "certificate released_unit_count differs from the trusted result",
        )
    if certificate.suppressed_unit_count != len(result.suppression_set):
        _fail(
            failures,
            V_CERTIFICATE_COUNTS,
            "certificate suppressed_unit_count differs from the trusted result",
        )

    visible = tuple(certificate.visible_publication_unit_keys)
    if visible != tuple(result.release_set):
        _fail(
            failures,
            V_CERTIFICATE_KEYS,
            "certificate visible Publication Unit keys do not equal the trusted Release Set",
        )
    suppression = set(result.suppression_set)
    if any(key in suppression for key in visible):
        _fail(
            failures,
            V_SUPPRESSED_UNIT_IN_CLIENT_SINK,
            "a suppressed Publication Unit key appears in the certificate visible keys",
        )

    if dict(certificate.authorizing_rules) != dict(result.authorizing_rules):
        _fail(
            failures,
            V_CERTIFICATE_AUTHORIZING,
            "certificate authorizing rules differ from the trusted result",
        )

    if certificate.search_method != result.search_method:
        _fail(
            failures,
            V_CERTIFICATE_PROOF,
            "certificate search_method differs from the trusted result",
        )
    if certificate.search_state != result.search_state:
        _fail(
            failures,
            V_CERTIFICATE_PROOF,
            "certificate search_state differs from the trusted result",
        )
    if (
        certificate.candidate_vectors_evaluated
        != result.candidate_vectors_evaluated
    ):
        _fail(
            failures,
            V_CERTIFICATE_PROOF,
            "certificate candidate count differs from the trusted result",
        )
    if certificate.solver_name != result.solver_name:
        _fail(
            failures,
            V_CERTIFICATE_PROOF,
            "certificate solver_name differs from the trusted result",
        )
    if certificate.solver_version != result.solver_version:
        _fail(
            failures,
            V_CERTIFICATE_PROOF,
            "certificate solver_version differs from the trusted result",
        )
    if certificate.rule_set_digest != result.rule_set_digest:
        _fail(
            failures,
            V_RULE_SET_DIGEST,
            "certificate rule_set_digest differs from the trusted result",
        )
    if (
        certificate.policy_version != result.policy_version
        or certificate.policy_source != result.policy_source
    ):
        _fail(
            failures,
            V_CERTIFICATE_POLICY,
            "certificate policy metadata differs from the trusted result",
        )

    computed_digest = compute_certificate_digest(
        artifact_type=certificate.artifact_type,
        privacy_release_mode=certificate.privacy_release_mode,
        candidate_unit_count=certificate.candidate_unit_count,
        released_unit_count=certificate.released_unit_count,
        suppressed_unit_count=certificate.suppressed_unit_count,
        coverage_percentage=certificate.coverage_percentage,
        visible_publication_unit_keys=certificate.visible_publication_unit_keys,
        authorizing_rules=certificate.authorizing_rules,
        global_weights=certificate.global_weights,
        policy_version=certificate.policy_version,
        policy_source=certificate.policy_source,
        rule_set_digest=certificate.rule_set_digest,
        solver_name=certificate.solver_name,
        solver_version=certificate.solver_version,
        search_method=certificate.search_method,
        search_state=certificate.search_state,
        candidate_vectors_evaluated=certificate.candidate_vectors_evaluated,
        artifact_hashes=certificate.artifact_hashes,
    )
    if computed_digest != certificate.certificate_digest:
        _fail(
            failures,
            V_CERTIFICATE_DIGEST,
            "certificate_digest does not match the canonical safe fields",
        )

    if expected_artifact_hashes is not None:
        expected = {str(k): str(v) for k, v in expected_artifact_hashes.items()}
        actual = {str(k): str(v) for k, v in certificate.artifact_hashes.items()}
        if actual != expected:
            _fail(
                failures,
                V_CERTIFICATE_ARTIFACT_HASH,
                "certificate artifact hashes do not match the expected values",
            )

    return VerificationOutcome(
        passed=not failures,
        failures=tuple(failures),
        computed_release_mask_digest=result.release_mask_digest,
        computed_candidate_universe_digest=result.candidate_universe_digest,
        computed_rule_set_digest=result.rule_set_digest,
        computed_artifact_hashes={},
    )
