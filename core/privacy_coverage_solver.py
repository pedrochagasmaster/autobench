"""Deterministic search for verified safe privacy coverage.

This module finds one global weight vector for share analysis. It does not
claim that the result has maximum coverage. The independent verifier must
recalculate the final release partition before any client output.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import numpy as np
from scipy.stats import qmc

from core.canonical_order import canonical_key, canonical_order
from core.constants import COMPARISON_EPSILON
from core.contracts import (
    APPROVED_PRIVACY_RULE_NAMES,
    PrivacyReleaseMode,
    PublicationUnit,
    SafeCoverageResult,
)
from core.privacy_coverage import CITIBANK_OVERLAY_NAME
from core.privacy_coverage_model import (
    CoverageRuleView,
    compile_coverage_model,
)
from core.privacy_rules import evaluate_rule, privacy_rule_from_config

__all__ = [
    "SafeCoverageSolverError",
    "find_verified_safe_coverage",
    "weighted_shares",
]

_ANCHOR_NODE_LIMIT = 20
_ANCHOR_TIME_LIMIT_SECONDS = 90.0
_SEARCH_SEED = 20260805
_SOBOL_POWER = 12
_LOCAL_SAMPLE_COUNT = 4096
_LOCAL_SIGMAS = (1.0, 0.5, 0.25)
_COORDINATE_GRID_SIZE = 31
_COORDINATE_SWEEPS = 3
_MAX_CANDIDATE_MATRIX_VALUES = 4_000_000
_SEARCH_METHOD = "highs-anchor-20-nodes+deterministic-refinement-v1"
_SEARCH_STATE = "search_complete"
_CITIBANK_MAXIMUM_SHARE = 25.0


class SafeCoverageSolverError(ValueError):
    """Report invalid search inputs before search work starts."""


def weighted_shares(
    peer_volumes: Mapping[str, float],
    weights: Mapping[str, float],
) -> Dict[str, float]:
    """Return positive-volume peer shares under the selected weights."""
    filtered: List[Tuple[str, float]] = []
    for peer, volume in peer_volumes.items():
        raw = float(volume)
        if raw <= 0.0:
            continue
        filtered.append((peer, raw * float(weights.get(peer, 1.0))))
    total = sum(value for _peer, value in filtered)
    if total <= 0.0:
        return {peer: 0.0 for peer, _value in filtered}
    return {peer: 100.0 * value / total for peer, value in filtered}


def _build_rule_view(
    name: str,
    rule_configs: Mapping[str, Mapping[str, Any]],
) -> CoverageRuleView:
    if name not in APPROVED_PRIVACY_RULE_NAMES:
        raise SafeCoverageSolverError(f"unknown privacy rule: {name!r}")
    config = rule_configs.get(name)
    resolved = privacy_rule_from_config(
        name,
        dict(config) if config is not None else None,
    )
    tiers = tuple(
        (int(count), float(threshold))
        for count, threshold in sorted(
            resolved.secondary_requirements.values(),
            key=lambda item: -float(item[1]),
        )
    )
    return CoverageRuleView(
        name=resolved.name,
        min_entities=int(resolved.min_entities),
        max_concentration=float(resolved.max_concentration),
        secondary_tiers=tiers,
    )


def _canonicalize_metric_records(
    unit: PublicationUnit,
    peers: Sequence[str],
) -> List[Dict[str, Any]]:
    seen: set[str] = set()
    records: List[Dict[str, Any]] = []
    for record in unit.metric_records:
        metric_raw = record.get("metric")
        if not metric_raw:
            raise SafeCoverageSolverError(
                f"unit {unit.internal_key!r} has an unnamed governed metric"
            )
        metric = str(metric_raw)
        if metric in seen:
            raise SafeCoverageSolverError(
                f"unit {unit.internal_key!r} has duplicate metric {metric!r}"
            )
        seen.add(metric)
        source = record.get("peer_volumes", {})
        aligned: Dict[str, float] = {}
        for peer in peers:
            value = float(source.get(peer, 0.0))
            if not math.isfinite(value) or value < 0.0:
                raise SafeCoverageSolverError(
                    f"unit {unit.internal_key!r} metric {metric!r} has invalid volume"
                )
            aligned[peer] = value
        total = float(sum(aligned.values()))
        if total <= 0.0:
            raise SafeCoverageSolverError(
                f"unit {unit.internal_key!r} metric {metric!r} has zero total volume"
            )
        records.append(
            {
                "metric": metric,
                "aligned_volumes": aligned,
                "total": total,
                "positive_peers": tuple(
                    peer for peer in peers if aligned[peer] > 0.0
                ),
                "fractions": np.asarray(
                    [aligned[peer] / total for peer in peers],
                    dtype=float,
                ),
            }
        )
    records.sort(key=lambda item: canonical_key(item["metric"]))
    return records


def _release_mask_digest(
    sorted_keys: Sequence[str],
    released_keys: Iterable[str],
) -> str:
    released = set(released_keys)
    payload = [
        {"key": key, "released": key in released}
        for key in sorted_keys
    ]
    encoded = json.dumps(payload, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _select_anchor_rule(
    rule_names: Sequence[str],
    rules: Mapping[str, CoverageRuleView],
) -> str:
    primary_only = [
        name for name in rule_names if not rules[name].secondary_tiers
    ]
    candidates = primary_only or list(rule_names)
    return max(
        candidates,
        key=lambda name: (
            rules[name].max_concentration,
            rules[name].min_entities,
            tuple(-ord(character) for character in name),
        ),
    )


def _candidate_batch_size(peer_count: int, requested: int) -> int:
    by_memory = max(1, _MAX_CANDIDATE_MATRIX_VALUES // max(1, peer_count))
    return max(1, min(requested, by_memory))


def _rule_pass_mask(
    weighted: np.ndarray,
    positive_count: int,
    rule: CoverageRuleView,
) -> np.ndarray:
    count = weighted.shape[0]
    if positive_count < rule.min_entities:
        return np.zeros(count, dtype=bool)
    totals = weighted.sum(axis=1)
    valid = totals > 0.0
    shares = np.zeros_like(weighted)
    if np.any(valid):
        shares[valid] = 100.0 * weighted[valid] / totals[valid, None]
    passed = valid & (
        shares.max(axis=1) <= rule.max_concentration + COMPARISON_EPSILON
    )
    for required, threshold in rule.secondary_tiers:
        passed &= np.sum(
            shares + COMPARISON_EPSILON >= threshold,
            axis=1,
        ) >= required
    return passed


def _score_candidates(
    unit_data: Sequence[Mapping[str, Any]],
    rules: Mapping[str, CoverageRuleView],
    peers: Sequence[str],
    candidates: np.ndarray,
    citi_peer: Optional[str],
) -> np.ndarray:
    scores = np.zeros(len(candidates), dtype=np.int32)
    citi_index = peers.index(citi_peer) if citi_peer in peers else None
    for unit in unit_data:
        unit_pass = np.zeros(len(candidates), dtype=bool)
        for rule_name in unit["rules"]:
            rule_pass = np.ones(len(candidates), dtype=bool)
            for metric in unit["metrics"]:
                fractions = metric["fractions"]
                weighted = candidates * fractions[None, :]
                rule_pass &= _rule_pass_mask(
                    weighted,
                    len(metric["positive_peers"]),
                    rules[str(rule_name)],
                )
            unit_pass |= rule_pass
        if (
            CITIBANK_OVERLAY_NAME in unit["overlays"]
            and citi_index is not None
        ):
            for metric in unit["metrics"]:
                fractions = metric["fractions"]
                weighted = candidates * fractions[None, :]
                totals = weighted.sum(axis=1)
                citi_share = np.full(len(candidates), math.inf, dtype=float)
                valid = totals > 0.0
                citi_share[valid] = (
                    100.0 * weighted[valid, citi_index] / totals[valid]
                )
                unit_pass &= (
                    citi_share
                    <= _CITIBANK_MAXIMUM_SHARE + COMPARISON_EPSILON
                )
        scores += unit_pass.astype(np.int32)
    return scores


def _best_candidate(
    unit_data: Sequence[Mapping[str, Any]],
    rules: Mapping[str, CoverageRuleView],
    peers: Sequence[str],
    candidates: np.ndarray,
    citi_peer: Optional[str],
) -> Tuple[np.ndarray, int, float]:
    scores = _score_candidates(unit_data, rules, peers, candidates, citi_peer)
    distance = np.sum(np.abs(np.log(candidates)), axis=1)
    best_score = int(scores.max())
    eligible = np.flatnonzero(scores == best_score)
    best_distance = float(distance[eligible].min())
    tied = eligible[
        np.isclose(
            distance[eligible],
            best_distance,
            rtol=0.0,
            atol=1e-12,
        )
    ]
    index = int(tied[0])
    return candidates[index].copy(), best_score, best_distance


def _resolve_citi_peer(
    peers: Sequence[str],
    unit_data: Sequence[Mapping[str, Any]],
    citibank_entity_name: Optional[str],
) -> Optional[str]:
    if not any(
        CITIBANK_OVERLAY_NAME in unit["overlays"] for unit in unit_data
    ):
        return None
    if not citibank_entity_name:
        raise SafeCoverageSolverError(
            "citibank_entity_name is required for the Citibank overlay"
        )
    needle = citibank_entity_name.casefold()
    matches = [peer for peer in peers if peer.casefold() == needle]
    if len(matches) != 1:
        raise SafeCoverageSolverError(
            "citibank peer identity must exist once in governed_peers"
        )
    return matches[0]


def _anchor_candidate(
    unit_data: Sequence[Mapping[str, Any]],
    peers: Sequence[str],
    rules: Mapping[str, CoverageRuleView],
    rule_configs: Mapping[str, Mapping[str, Any]],
    *,
    min_weight: float,
    max_weight: float,
    citibank_entity_name: Optional[str],
) -> Tuple[Optional[np.ndarray], str, str]:
    from core.privacy_coverage_highs import (
        HighsCoverageSession,
        NeutralMipStartError,
        build_neutral_mip_start,
        validate_start_against_stage,
    )

    anchor_units: List[Dict[str, Any]] = []
    anchor_rules: Dict[str, CoverageRuleView] = {}
    for unit in unit_data:
        rule_name = _select_anchor_rule(unit["rules"], rules)
        anchor_units.append(
            {
                "key": unit["key"],
                "metrics": unit["metrics"],
                "rules": (rule_name,),
                "overlays": unit["overlays"],
            }
        )
        anchor_rules[rule_name] = replace(
            rules[rule_name],
            secondary_tiers=(),
        )
    model = compile_coverage_model(
        anchor_units,
        peers,
        min_weight=min_weight,
        max_weight=max_weight,
        rules=anchor_rules,
        citibank_entity_name=citibank_entity_name,
        enable_rule_dominance=True,
        enable_structural_presolve=True,
    )
    stage = replace(model.stage1, objective=-model.stage1.objective)
    session = HighsCoverageSession(
        stage,
        time_limit=_ANCHOR_TIME_LIMIT_SECONDS,
        maximize=True,
        threads=1,
        mip_max_nodes=_ANCHOR_NODE_LIMIT,
    )
    try:
        start = build_neutral_mip_start(
            model,
            anchor_units,
            rule_configs=rule_configs,
        )
        session.set_complete_start(start)
        result = session.solve()
        validate_start_against_stage(stage, result.column_values)
    except (NeutralMipStartError, RuntimeError, ValueError):
        return None, "anchor_failed", session.highs_version
    weights = np.asarray(
        [result.column_values[model.w_index[peer]] for peer in peers],
        dtype=float,
    )
    if (
        weights.shape != (len(peers),)
        or not np.all(np.isfinite(weights))
        or np.any(weights < min_weight)
        or np.any(weights > max_weight)
    ):
        return None, "anchor_failed", session.highs_version
    return weights, str(result.model_status), session.highs_version


def _refine_candidates(
    unit_data: Sequence[Mapping[str, Any]],
    rules: Mapping[str, CoverageRuleView],
    peers: Sequence[str],
    *,
    min_weight: float,
    max_weight: float,
    anchor: Optional[np.ndarray],
    citi_peer: Optional[str],
) -> Tuple[np.ndarray, int]:
    dimension = len(peers)
    evaluated = 0
    requested = 2 ** _SOBOL_POWER
    sample_count = _candidate_batch_size(dimension, requested)
    power = int(math.floor(math.log2(sample_count)))
    sample_count = 2 ** max(0, power)
    sampler = qmc.Sobol(d=dimension, scramble=True, seed=_SEARCH_SEED)
    unit_cube = sampler.random_base2(m=max(0, power))
    candidates = np.exp(
        math.log(min_weight)
        + unit_cube * (math.log(max_weight) - math.log(min_weight))
    )
    initial = [np.ones(dimension, dtype=float)]
    if anchor is not None:
        initial.insert(0, anchor)
    candidates = np.vstack([*initial, candidates])
    best, _score, _distance = _best_candidate(
        unit_data,
        rules,
        peers,
        candidates,
        citi_peer,
    )
    evaluated += len(candidates)

    rng = np.random.default_rng(_SEARCH_SEED)
    local_count = _candidate_batch_size(dimension, _LOCAL_SAMPLE_COUNT)
    for sigma in _LOCAL_SIGMAS:
        perturbation = rng.normal(0.0, sigma, size=(local_count, dimension))
        local = np.clip(
            np.exp(np.log(best)[None, :] + perturbation),
            min_weight,
            max_weight,
        )
        local = np.vstack([best, local])
        best, _score, _distance = _best_candidate(
            unit_data,
            rules,
            peers,
            local,
            citi_peer,
        )
        evaluated += len(local)

    grid = np.geomspace(min_weight, max_weight, _COORDINATE_GRID_SIZE)
    for _sweep in range(_COORDINATE_SWEEPS):
        changed = False
        for coordinate in range(dimension):
            coordinate_candidates = np.repeat(
                best[None, :],
                len(grid) + 1,
                axis=0,
            )
            coordinate_candidates[:-1, coordinate] = grid
            candidate, _candidate_score, _distance = _best_candidate(
                unit_data,
                rules,
                peers,
                coordinate_candidates,
                citi_peer,
            )
            evaluated += len(coordinate_candidates)
            if not np.array_equal(candidate, best):
                changed = True
            best = candidate
        if not changed:
            break
    return best, evaluated


def _direct_release_partition(
    unit_data: Sequence[Mapping[str, Any]],
    peers: Sequence[str],
    weights: np.ndarray,
    citi_peer: Optional[str],
    rule_configs: Mapping[str, Mapping[str, Any]],
) -> Tuple[List[str], List[str], Dict[str, str]]:
    weight_map = {
        peer: float(weights[index]) for index, peer in enumerate(peers)
    }
    released: List[str] = []
    suppressed: List[str] = []
    authorizing: Dict[str, str] = {}
    for unit in unit_data:
        citi_passed = True
        if CITIBANK_OVERLAY_NAME in unit["overlays"]:
            if citi_peer is None:
                citi_passed = False
            else:
                for metric in unit["metrics"]:
                    shares = weighted_shares(
                        metric["aligned_volumes"],
                        weight_map,
                    )
                    if (
                        shares.get(citi_peer, 0.0)
                        > _CITIBANK_MAXIMUM_SHARE + COMPARISON_EPSILON
                    ):
                        citi_passed = False
                        break
        authorizer: Optional[str] = None
        if citi_passed:
            for rule_name in unit["rules"]:
                passed = True
                for metric in unit["metrics"]:
                    shares = weighted_shares(
                        metric["aligned_volumes"],
                        weight_map,
                    )
                    evaluation = evaluate_rule(
                        str(rule_name),
                        list(shares.values()),
                        rule_config=(
                            dict(rule_configs[str(rule_name)])
                            if str(rule_name) in rule_configs
                            else None
                        ),
                    )
                    if not evaluation.strict_passed:
                        passed = False
                        break
                if passed:
                    authorizer = str(rule_name)
                    break
        key = str(unit["key"])
        if authorizer is None:
            suppressed.append(key)
        else:
            released.append(key)
            authorizing[key] = authorizer
    return released, suppressed, authorizing


def find_verified_safe_coverage(
    candidate_universe: Tuple[PublicationUnit, ...],
    governed_peers: Tuple[str, ...],
    *,
    min_weight: float,
    max_weight: float,
    rule_configs: Mapping[str, Mapping[str, Any]],
    citibank_entity_name: Optional[str],
    input_digest: str,
    configuration_digest: str,
    policy_version: str,
    policy_source: str,
    rule_set_digest: str,
    candidate_universe_digest: str,
    solver_options: Optional[Mapping[str, Any]] = None,
) -> SafeCoverageResult:
    """Find a deterministic safe release subset.

    The search does not prove a maximum. The caller must run the independent
    verifier before it authorizes a client sink.
    """
    if solver_options is not None:
        raise SafeCoverageSolverError(
            "solver_options are not supported by verified-safe-coverage"
        )
    if not math.isfinite(min_weight) or min_weight <= 0.0:
        raise SafeCoverageSolverError("min_weight must be positive and finite")
    if not math.isfinite(max_weight) or max_weight < min_weight:
        raise SafeCoverageSolverError(
            "max_weight must be finite and not less than min_weight"
        )
    if min_weight > 1.0 or max_weight < 1.0:
        raise SafeCoverageSolverError(
            "weight bounds must satisfy 0 < min_weight <= 1 <= max_weight"
        )
    if not isinstance(candidate_universe, tuple) or not candidate_universe:
        raise SafeCoverageSolverError("candidate_universe must be a non-empty tuple")
    peers = tuple(canonical_order(governed_peers))
    if not peers or len(set(governed_peers)) != len(governed_peers):
        raise SafeCoverageSolverError(
            "governed_peers must contain distinct identities"
        )

    universe = tuple(
        sorted(candidate_universe, key=lambda unit: canonical_key(unit.internal_key))
    )
    keys = tuple(unit.internal_key for unit in universe)
    if len(set(keys)) != len(keys):
        raise SafeCoverageSolverError(
            "candidate_universe contains duplicate internal keys"
        )
    rules: Dict[str, CoverageRuleView] = {}
    unit_data: List[Dict[str, Any]] = []
    for unit in universe:
        rule_names = tuple(sorted(unit.applicable_rules, key=canonical_key))
        if not rule_names:
            raise SafeCoverageSolverError(
                f"unit {unit.internal_key!r} has no applicable privacy rule"
            )
        for rule_name in rule_names:
            rules.setdefault(rule_name, _build_rule_view(rule_name, rule_configs))
        unit_data.append(
            {
                "key": unit.internal_key,
                "metrics": _canonicalize_metric_records(unit, peers),
                "rules": rule_names,
                "overlays": tuple(unit.mandatory_overlays),
            }
        )

    citi_peer = _resolve_citi_peer(
        peers,
        unit_data,
        citibank_entity_name,
    )
    anchor, _anchor_state, solver_version = _anchor_candidate(
        unit_data,
        peers,
        rules,
        rule_configs,
        min_weight=min_weight,
        max_weight=max_weight,
        citibank_entity_name=citibank_entity_name,
    )
    weights, evaluated = _refine_candidates(
        unit_data,
        rules,
        peers,
        min_weight=min_weight,
        max_weight=max_weight,
        anchor=anchor,
        citi_peer=citi_peer,
    )
    released, suppressed, authorizing = _direct_release_partition(
        unit_data,
        peers,
        weights,
        citi_peer,
        rule_configs,
    )
    weight_map = {
        peer: float(weights[index]) for index, peer in enumerate(peers)
    }
    return SafeCoverageResult(
        release_mode=PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE,
        global_weights=weight_map,
        candidate_universe=universe,
        release_set=tuple(released),
        suppression_set=tuple(suppressed),
        authorizing_rules=authorizing,
        search_method=_SEARCH_METHOD,
        search_state=_SEARCH_STATE,
        candidate_vectors_evaluated=evaluated,
        solver_name="highspy.Highs",
        solver_version=solver_version,
        input_digest=input_digest,
        configuration_digest=configuration_digest,
        policy_version=policy_version,
        policy_source=policy_source,
        rule_set_digest=rule_set_digest,
        candidate_universe_digest=candidate_universe_digest,
        release_mask_digest=_release_mask_digest(keys, released),
        verifier_result="not_run",
    )
