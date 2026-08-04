"""Canonical Publication Unit construction for Maximum Safe Coverage.

This Module owns Candidate Universe construction and filtering for share
analysis. It does not optimize, authorize client sinks, or evaluate rules for
release decisions. Solver and verifier Modules consume the units produced here.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, cast

import pandas as pd

from core.canonical_order import canonical_key, canonical_order
from core.category_builder import CategoryBuilder
from core.category_suppression import is_category_suppressed
from core.contracts import PublicationUnit
from core.privacy_policy import PrivacyPolicy

CITIBANK_OVERLAY_NAME = "citibank_maximum_25_percent"

# Safe aggregate reason codes for client evidence. These must never embed a
# suppressed category name or protected source value.
UNIT_INELIGIBLE_MISSING_METRIC = "missing_required_metric"
UNIT_INELIGIBLE_NONFINITE = "nonfinite_governed_value"
UNIT_INELIGIBLE_ZERO_TOTAL = "zero_metric_total"


class CandidateUniverseError(ValueError):
    """Raised when the Candidate Universe cannot be constructed safely."""


def build_publication_unit_key(
    *,
    dimension: str,
    category: str,
    time_period: Optional[str],
    output_scope: Optional[str] = None,
) -> str:
    """Return the canonical internal key for one Publication Unit.

    Identity is independent of display order and of metric contents.
    """
    parts = (
        ("dimension", str(dimension)),
        ("category", str(category)),
        ("time_period", "" if time_period is None else str(time_period)),
        ("output_scope", "" if output_scope is None else str(output_scope)),
    )
    return "|".join(f"{name}={value}" for name, value in parts)


def _normalize_time_period(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip()
    return text if text else None


def _output_key_fields(
    record: Mapping[str, Any],
) -> Tuple[str, str, Optional[str], Optional[str]]:
    dimension = record.get("dimension")
    category = record.get("category")
    if dimension is None or category is None:
        raise CandidateUniverseError(
            "Publication Unit records require non-null dimension and category"
        )
    dimension_text = str(dimension).strip()
    category_text = str(category).strip()
    if not dimension_text or not category_text:
        raise CandidateUniverseError(
            "Publication Unit dimension and category must be non-empty"
        )
    if "\n" in dimension_text or "\n" in category_text:
        raise CandidateUniverseError(
            "Publication Unit dimension and category must not contain newlines"
        )
    time_period = _normalize_time_period(record.get("time_period"))
    output_scope = record.get("output_scope")
    scope_text = None if output_scope is None else str(output_scope).strip() or None
    return dimension_text, category_text, time_period, scope_text


def _peer_volumes_for_cell(
    category_records: Sequence[Mapping[str, Any]],
    *,
    dimension: str,
    category: str,
    time_period: Optional[str],
) -> Dict[str, float]:
    volumes: Dict[str, float] = {}
    for record in category_records:
        rec_dim, rec_cat, rec_time, _scope = _output_key_fields(record)
        if (rec_dim, rec_cat, rec_time) != (dimension, category, time_period):
            continue
        peer = record.get("peer")
        if peer is None:
            raise CandidateUniverseError("Category records require a peer identity")
        volume = record.get("category_volume")
        if volume is None:
            raise CandidateUniverseError("Category records require category_volume")
        value = float(volume)
        if not math.isfinite(value):
            raise CandidateUniverseError(
                "Publication Unit peer volumes must be finite"
            )
        if value < 0.0:
            raise CandidateUniverseError(
                "Publication Unit peer volumes must be non-negative"
            )
        peer_name = str(peer)
        volumes[peer_name] = volumes.get(peer_name, 0.0) + value
    return {peer: volumes[peer] for peer in canonical_order(volumes)}


def _metric_record(
    *,
    metric: str,
    peer_volumes: Mapping[str, float],
) -> Dict[str, Any]:
    total = float(sum(peer_volumes.values()))
    return {
        "metric": metric,
        "peer_volumes": dict(peer_volumes),
        "total_volume": total,
        "participant_count": sum(1 for volume in peer_volumes.values() if volume > 0.0),
    }


def _mandatory_overlays(
    *,
    citibank_entity_name: Optional[str],
    citi_competitor_receives_output: bool,
    peers: Sequence[str],
) -> Tuple[str, ...]:
    if not citi_competitor_receives_output or not citibank_entity_name:
        return ()
    needle = citibank_entity_name.casefold()
    matches = [peer for peer in peers if peer.casefold() == needle]
    if len(matches) != 1:
        raise CandidateUniverseError(
            "Citibank overlay requires exactly one matching governed peer"
        )
    return (CITIBANK_OVERLAY_NAME,)


def _collect_output_cells(
    category_records: Sequence[Mapping[str, Any]],
) -> List[Tuple[str, str, Optional[str], Optional[str]]]:
    cells: Dict[Tuple[str, str, Optional[str], Optional[str]], None] = {}
    for record in category_records:
        key_fields = _output_key_fields(record)
        cells[key_fields] = None
    ordered = sorted(cells.keys(), key=lambda item: canonical_key(item))
    return ordered


def build_candidate_universe(
    df: pd.DataFrame,
    *,
    entity_col: str,
    metric: str,
    secondary_metrics: Optional[Sequence[str]] = None,
    dimensions: Sequence[str],
    time_col: Optional[str] = None,
    target_entity: Optional[str] = None,
    suppressed_categories: Optional[Sequence[Mapping[str, Any]]] = None,
    merchant_spend_scope: bool = False,
    citibank_entity_name: Optional[str] = None,
    citi_competitor_receives_output: bool = False,
    consistent_weights: bool = True,
    include_internal_time_totals: bool = False,
) -> Tuple[PublicationUnit, ...]:
    """Build the fixed Candidate Universe for share-analysis coverage.

    Structural suppressions are applied before units are retained. The returned
    universe is sorted canonically and is independent of input row order.
    """
    if not metric or not str(metric).strip():
        raise CandidateUniverseError("Primary metric is required")
    if not dimensions:
        raise CandidateUniverseError("At least one dimension is required")
    CategoryBuilder.validate_dimension_names(list(dimensions))

    required_metrics = [str(metric)]
    for secondary in secondary_metrics or ():
        name = str(secondary)
        if name and name not in required_metrics:
            required_metrics.append(name)

    builder = CategoryBuilder(
        entity_column=entity_col,
        target_entity=target_entity,
        time_column=time_col,
        consistent_weights=consistent_weights,
    )

    metric_category_records: Dict[str, List[Dict[str, Any]]] = {}
    peers: List[str] = []
    for metric_name in required_metrics:
        if metric_name not in df.columns:
            raise CandidateUniverseError(
                f"Required metric column is missing from input: {metric_name}"
            )
        categories, _peer_volumes, metric_peers = builder.build_categories(
            df, metric_name, list(dimensions)
        )
        if not include_internal_time_totals:
            categories = [
                record
                for record in categories
                if not CategoryBuilder.is_internal_dimension_name(record.get("dimension"))
            ]
        metric_category_records[metric_name] = categories
        peers = canonical_order([*peers, *metric_peers])

    if not peers:
        raise CandidateUniverseError("Candidate Universe requires governed peers")

    primary_records = metric_category_records[required_metrics[0]]
    cells = _collect_output_cells(primary_records)
    suppressed = cast(List[Dict[str, Any]], list(suppressed_categories or ()))
    overlays = _mandatory_overlays(
        citibank_entity_name=citibank_entity_name,
        citi_competitor_receives_output=citi_competitor_receives_output,
        peers=peers,
    )

    units_by_key: Dict[str, PublicationUnit] = {}
    for dimension, category, time_period, output_scope in cells:
        if is_category_suppressed(suppressed, dimension, category, time_period):
            continue

        metric_records: List[Dict[str, Any]] = []
        participant_counts: List[int] = []
        for metric_name in required_metrics:
            peer_volumes = _peer_volumes_for_cell(
                metric_category_records[metric_name],
                dimension=dimension,
                category=category,
                time_period=time_period,
            )
            if not peer_volumes:
                # Missing required metric for this cell: unit is ineligible.
                # Safe aggregate reason is recorded on a sentinel metric record
                # so downstream trusted evidence can explain exclusion without
                # exposing suppressed names.
                metric_records = [
                    {
                        "metric": metric_name,
                        "peer_volumes": {},
                        "total_volume": 0.0,
                        "participant_count": 0,
                        "ineligible_reason": UNIT_INELIGIBLE_MISSING_METRIC,
                    }
                ]
                break
            record = _metric_record(metric=metric_name, peer_volumes=peer_volumes)
            if record["total_volume"] <= 0.0:
                record["ineligible_reason"] = UNIT_INELIGIBLE_ZERO_TOTAL
            metric_records.append(record)
            participant_counts.append(int(record["participant_count"]))

        if any(
            record.get("ineligible_reason") == UNIT_INELIGIBLE_MISSING_METRIC
            for record in metric_records
        ):
            # A missing required metric makes the complete unit ineligible.
            # Keep it out of the Candidate Universe (privacy-eligible only).
            continue

        if any(count <= 0 for count in participant_counts):
            continue

        # Applicable rules are based on the minimum participant count across
        # required metrics so a secondary-metric-only thin cell cannot claim a
        # rule that its secondary population cannot satisfy.
        peer_count = min(participant_counts)
        applicable_rules = PrivacyPolicy.applicable_sweep_rules(
            peer_count,
            is_anonymized_aggregated_merchant_spend=merchant_spend_scope,
        )
        internal_key = build_publication_unit_key(
            dimension=dimension,
            category=category,
            time_period=time_period,
            output_scope=output_scope,
        )
        if internal_key in units_by_key:
            raise CandidateUniverseError(
                "Duplicate Publication Unit key in Candidate Universe"
            )
        units_by_key[internal_key] = PublicationUnit(
            internal_key=internal_key,
            dimension=dimension,
            category=category,
            time_period=time_period,
            output_scope=output_scope,
            metric_records=tuple(metric_records),
            applicable_rules=applicable_rules,
            mandatory_overlays=overlays,
        )

    ordered_keys = sorted(units_by_key.keys(), key=canonical_key)
    units = tuple(units_by_key[key] for key in ordered_keys)
    if not units:
        raise CandidateUniverseError(
            "Candidate Universe is empty after structural suppression"
        )
    return units


def candidate_universe_digest(units: Sequence[PublicationUnit]) -> str:
    """Return a trusted digest over the canonical Candidate Universe.

    The digest is intended for internal evidence only. It must not be exposed
    as a reversible low-entropy client token.
    """
    payload = [
        {
            "internal_key": unit.internal_key,
            "dimension": unit.dimension,
            "category": unit.category,
            "time_period": unit.time_period,
            "output_scope": unit.output_scope,
            "applicable_rules": list(unit.applicable_rules),
            "mandatory_overlays": list(unit.mandatory_overlays),
            "metric_records": [
                {
                    "metric": record["metric"],
                    "peer_volumes": dict(record["peer_volumes"]),
                    "total_volume": float(record["total_volume"]),
                    "participant_count": int(record["participant_count"]),
                }
                for record in unit.metric_records
            ],
        }
        for unit in units
    ]
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def filter_units_by_keys(
    units: Sequence[PublicationUnit],
    release_keys: Iterable[str],
) -> Tuple[PublicationUnit, ...]:
    """Return units whose internal keys are in ``release_keys``, canonically ordered."""
    allowed = set(release_keys)
    selected = [unit for unit in units if unit.internal_key in allowed]
    selected.sort(key=lambda unit: canonical_key(unit.internal_key))
    return tuple(selected)
