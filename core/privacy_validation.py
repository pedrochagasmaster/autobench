"""Typed privacy validation domain result and legacy DataFrame rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


def _parse_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    normalized = str(value).strip().lower()
    if normalized in {"yes", "true", "1", "y", "pass", "passed"}:
        return True
    if normalized in {"no", "false", "0", "n", "fail", "failed", ""}:
        return False
    return default


@dataclass(frozen=True)
class PrivacyValidationRow:
    dimension: str
    category: str
    time_period: Optional[Any]
    peer: str
    rule_name: str
    original_volume: float
    original_share_pct: float
    balanced_volume: float
    balanced_share_pct: float
    primary_cap_pct: float
    primary_cap_passed: bool
    secondary_rule_passed: bool
    relaxation_used: bool
    strict_compliant: bool
    weight_source: str = ""
    weight_method: str = ""
    multiplier: float = 1.0
    tolerance_pct: float = 0.0
    secondary_rule_enforced: bool = False
    secondary_rule_detail: str = ""
    structural_infeasible_peer: bool = False
    structural_infeasible_category: bool = False
    structural_margin_peer_pp: float = 0.0
    structural_margin_category_pp: float = 0.0
    violation_margin_pct: float = 0.0


@dataclass(frozen=True)
class PrivacyValidationResult:
    rows: List[PrivacyValidationRow]

    def strict_failures(self) -> List[PrivacyValidationRow]:
        return [row for row in self.rows if not row.strict_compliant]

    def to_dataframe(self) -> pd.DataFrame:
        rendered: List[Dict[str, Any]] = []
        for row in self.rows:
            rendered.append(
                {
                    "Dimension": row.dimension,
                    "Time_Period": row.time_period,
                    "Category": row.category,
                    "Peer": row.peer,
                    "Rule_Name": row.rule_name,
                    "Weight_Source": row.weight_source,
                    "Weight_Method": row.weight_method,
                    "Multiplier": row.multiplier,
                    "Original_Volume": row.original_volume,
                    "Original_Share_%": round(row.original_share_pct, 4),
                    "Balanced_Volume": row.balanced_volume,
                    "Balanced_Share_%": round(row.balanced_share_pct, 4),
                    "Privacy_Cap_%": row.primary_cap_pct,
                    "Tolerance_%": row.tolerance_pct,
                    "Primary_Cap_Passed": row.primary_cap_passed,
                    "Secondary_Rule_Passed": row.secondary_rule_passed,
                    "Relaxation_Used": row.relaxation_used,
                    "Strict_Compliant": row.strict_compliant,
                    "Additional_Constraints_Enforced": "Yes" if row.secondary_rule_enforced else "No",
                    "Additional_Constraints_Relaxed": "Yes" if row.relaxation_used else "No",
                    "Additional_Constraints_Passed": "Yes" if row.secondary_rule_passed else "No",
                    "Additional_Constraint_Detail": row.secondary_rule_detail,
                    "Structural_Infeasible_Peer": "Yes" if row.structural_infeasible_peer else "No",
                    "Structural_Infeasible_Category": "Yes" if row.structural_infeasible_category else "No",
                    "Structural_Margin_Peer_pp": round(row.structural_margin_peer_pp, 4),
                    "Structural_Margin_Category_pp": round(row.structural_margin_category_pp, 4),
                    "Compliant": "Yes" if row.strict_compliant else "No",
                    "Violation_Margin_%": round(row.violation_margin_pct, 4)
                    if row.violation_margin_pct > 0
                    else 0.0,
                }
            )
        return pd.DataFrame(rendered)

    @classmethod
    def from_dataframe(cls, df: pd.DataFrame) -> "PrivacyValidationResult":
        rows: List[PrivacyValidationRow] = []
        for record in df.to_dict("records"):
            primary_cap = _parse_bool(
                record.get("Primary_Cap_Passed"),
                default=_parse_bool(record.get("Compliant"), default=False),
            )
            secondary_passed = _parse_bool(
                record.get("Additional_Constraints_Passed"),
                default=_parse_bool(record.get("Secondary_Rule_Passed"), default=True),
            )
            relaxation_used = _parse_bool(
                record.get("Additional_Constraints_Relaxed"),
                default=_parse_bool(record.get("Relaxation_Used"), default=False),
            )
            strict_compliant = (
                _parse_bool(record.get("Strict_Compliant"), default=False)
                if "Strict_Compliant" in record
                else (
                    _parse_bool(record.get("Compliant"), default=False)
                    and not relaxation_used
                    and primary_cap
                    and secondary_passed
                )
            )
            rows.append(
                PrivacyValidationRow(
                    dimension=str(record.get("Dimension", "")),
                    category=str(record.get("Category", "")),
                    time_period=record.get("Time_Period"),
                    peer=str(record.get("Peer", "")),
                    rule_name=str(record.get("Rule_Name", "")),
                    original_volume=float(record.get("Original_Volume", 0.0) or 0.0),
                    original_share_pct=float(record.get("Original_Share_%", 0.0) or 0.0),
                    balanced_volume=float(record.get("Balanced_Volume", 0.0) or 0.0),
                    balanced_share_pct=float(record.get("Balanced_Share_%", 0.0) or 0.0),
                    primary_cap_pct=float(record.get("Privacy_Cap_%", 0.0) or 0.0),
                    primary_cap_passed=primary_cap,
                    secondary_rule_passed=secondary_passed,
                    relaxation_used=relaxation_used,
                    strict_compliant=bool(strict_compliant),
                    weight_source=str(record.get("Weight_Source", "")),
                    weight_method=str(record.get("Weight_Method", "")),
                    multiplier=float(record.get("Multiplier", 1.0) or 1.0),
                    tolerance_pct=float(record.get("Tolerance_%", 0.0) or 0.0),
                    secondary_rule_enforced=str(record.get("Additional_Constraints_Enforced", "No")).strip().lower() == "yes",
                    secondary_rule_detail=str(record.get("Additional_Constraint_Detail", "")),
                    structural_infeasible_peer=str(record.get("Structural_Infeasible_Peer", "No")).strip().lower() == "yes",
                    structural_infeasible_category=str(record.get("Structural_Infeasible_Category", "No")).strip().lower() == "yes",
                    structural_margin_peer_pp=float(record.get("Structural_Margin_Peer_pp", 0.0) or 0.0),
                    structural_margin_category_pp=float(record.get("Structural_Margin_Category_pp", 0.0) or 0.0),
                    violation_margin_pct=float(record.get("Violation_Margin_%", 0.0) or 0.0),
                )
            )
        return cls(rows=rows)


def build_privacy_validation_result(
    analyzer: Any,
    df: pd.DataFrame,
    metric_col: str,
    dimensions: List[str],
) -> PrivacyValidationResult:
    """Build detailed typed privacy validation rows for each dimension/category."""
    rows: List[PrivacyValidationRow] = []
    all_categories, peer_volumes, _ = analyzer._build_categories(df, metric_col, dimensions)
    peers = list(analyzer.global_weights.keys())
    if not peers:
        per_dim_peers = set()
        for weights in analyzer.per_dimension_weights.values():
            per_dim_peers.update(weights.keys())
        peers = sorted(per_dim_peers) if per_dim_peers else sorted(peer_volumes.keys())
    if not peers:
        return PrivacyValidationResult(rows=[])

    constraint_stats = analyzer._build_constraint_stats(all_categories, peers, peer_volumes) if all_categories else {}
    rule_name, max_concentration = analyzer._get_privacy_rule(len(peers))
    weights = {peer: float(analyzer.global_weights.get(peer, {}).get("multiplier", 1.0)) for peer in peers}

    structural_peer_margin: Dict[Tuple[str, str, str], float] = {}
    structural_category_margin: Dict[Tuple[str, str], float] = {}
    if analyzer.structural_detail_df is not None and not analyzer.structural_detail_df.empty:
        for row in analyzer.structural_detail_df.itertuples(index=False):
            dimension_key = str(getattr(row, "dimension", ""))
            category_key = str(getattr(row, "category", ""))
            peer_key = str(getattr(row, "peer", ""))
            margin = float(getattr(row, "margin_over_cap_pp", 0.0) or 0.0)
            if margin <= 0:
                continue
            structural_peer_margin[(dimension_key, category_key, peer_key)] = max(
                structural_peer_margin.get((dimension_key, category_key, peer_key), 0.0),
                margin,
            )
            structural_category_margin[(dimension_key, category_key)] = max(
                structural_category_margin.get((dimension_key, category_key), 0.0),
                margin,
            )

    def append_row(
        *,
        dimension: str,
        category: Any,
        time_period: Optional[Any],
        peer: str,
        weight_source: str,
        weight_method: str,
        multiplier: float,
        original_volume: float,
        original_share_pct: float,
        balanced_volume: float,
        balanced_share_pct: float,
        secondary_rule_enforced: bool,
        secondary_rule_passed: bool,
        relaxation_used: bool,
        secondary_rule_detail: str,
        structural_peer_pp: float = 0.0,
        structural_category_pp: float = 0.0,
    ) -> None:
        primary_cap_passed = not analyzer._is_share_violation(balanced_share_pct, max_concentration)
        violation_margin = balanced_share_pct - max_concentration if not primary_cap_passed else 0.0
        rows.append(
            PrivacyValidationRow(
                dimension=str(dimension),
                category=str(category),
                time_period=time_period,
                peer=str(peer),
                rule_name=rule_name,
                original_volume=float(original_volume),
                original_share_pct=float(original_share_pct),
                balanced_volume=float(balanced_volume),
                balanced_share_pct=float(balanced_share_pct),
                primary_cap_pct=float(max_concentration),
                primary_cap_passed=primary_cap_passed,
                secondary_rule_passed=bool(secondary_rule_passed),
                relaxation_used=bool(relaxation_used),
                strict_compliant=primary_cap_passed and bool(secondary_rule_passed) and not bool(relaxation_used),
                weight_source=weight_source,
                weight_method=weight_method,
                multiplier=float(multiplier),
                tolerance_pct=float(analyzer.tolerance),
                secondary_rule_enforced=bool(secondary_rule_enforced),
                secondary_rule_detail=secondary_rule_detail,
                structural_infeasible_peer=structural_peer_pp > 0,
                structural_infeasible_category=structural_category_pp > 0,
                structural_margin_peer_pp=float(structural_peer_pp) if structural_peer_pp > 0 else 0.0,
                structural_margin_category_pp=float(structural_category_pp) if structural_category_pp > 0 else 0.0,
                violation_margin_pct=float(violation_margin) if violation_margin > 0 else 0.0,
            )
        )

    def append_time_total_rows(time_period: Any) -> None:
        time_df = df[df[analyzer.time_column] == time_period]
        entity_agg = time_df.groupby(analyzer.entity_column).agg({metric_col: "sum"}).reset_index()
        peer_data = [
            {
                "peer": peer,
                "volume": float(entity_agg[entity_agg[analyzer.entity_column] == peer][metric_col].sum()),
            }
            for peer in peers
        ]
        total_original_vol = sum(peer_info["volume"] for peer_info in peer_data)
        total_balanced_vol = sum(peer_info["volume"] * weights.get(peer_info["peer"], 1.0) for peer_info in peer_data)
        for peer_info in peer_data:
            peer = peer_info["peer"]
            peer_weight = weights.get(peer, 1.0)
            original_share = (peer_info["volume"] / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
            balanced_vol = peer_info["volume"] * peer_weight
            balanced_share = (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
            append_row(
                dimension="_TIME_TOTAL_",
                category=str(time_period),
                time_period=time_period,
                peer=peer,
                weight_source="Global",
                weight_method=analyzer.weight_methods.get("_TIME_TOTAL_", "Global-LP"),
                multiplier=peer_weight,
                original_volume=peer_info["volume"],
                original_share_pct=original_share,
                balanced_volume=balanced_vol,
                balanced_share_pct=balanced_share,
                secondary_rule_enforced=False,
                secondary_rule_passed=True,
                relaxation_used=False,
                secondary_rule_detail="Time total cap validation",
            )

    def evaluate_category(
        dimension: str,
        category: Any,
        time_period: Optional[Any],
        peer_data: List[Dict[str, Any]],
    ) -> Tuple[List[float], bool, bool, bool, str]:
        peer_category_volumes = {peer_info["peer"]: peer_info["volume"] for peer_info in peer_data}
        stats_key = (
            (f"{dimension}_{analyzer.time_column}", f"{category}_{time_period}", time_period)
            if time_period is not None
            else (dimension, category, None)
        )
        stats = constraint_stats.get(stats_key)
        enforce, reason, thresholds, relaxed = analyzer._assess_additional_constraints_applicability(
            rule_name,
            dimension,
            peer_category_volumes,
            stats,
        )
        total_balanced_vol = sum(peer_info["volume"] * peer_info["weight"] for peer_info in peer_data)
        balanced_shares = [
            (peer_info["volume"] * peer_info["weight"] / total_balanced_vol * 100.0)
            if total_balanced_vol > 0
            else 0.0
            for peer_info in peer_data
        ]
        if enforce:
            additional_passed, additional_details = analyzer._evaluate_additional_constraints(
                balanced_shares,
                rule_name,
                thresholds,
            )
            threshold_detail = f" Thresholds={thresholds}" if thresholds else ""
            additional_detail = "; ".join(additional_details) if additional_details else ""
            additional_detail = f"{additional_detail}{threshold_detail}".strip()
            return balanced_shares, True, additional_passed, relaxed, additional_detail
        detail = "Not applicable" if reason == "no_additional" else f"Skipped ({reason})"
        return balanced_shares, False, True, relaxed, detail

    for dimension in dimensions:
        dim_weights = dict(weights)
        if dimension in analyzer.per_dimension_weights:
            dim_weights.update(analyzer.per_dimension_weights[dimension])
        weight_source = "Per-Dimension" if dimension in analyzer.per_dimension_weights else "Global"
        weight_method = analyzer.weight_methods.get(dimension, "Global-LP")

        if analyzer.time_column and analyzer.time_column in df.columns:
            time_periods = analyzer._get_time_periods(df)
            for time_period in time_periods:
                time_df = df[df[analyzer.time_column] == time_period]
                entity_dim_agg = time_df.groupby([analyzer.entity_column, dimension]).agg({metric_col: "sum"}).reset_index()
                for category in entity_dim_agg[dimension].unique():
                    cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                    peer_data = []
                    for peer in peers:
                        volume = float(cat_df[cat_df[analyzer.entity_column] == peer][metric_col].sum())
                        peer_data.append({"peer": peer, "volume": volume, "weight": dim_weights.get(peer, 1.0)})
                    total_original_vol = sum(peer_info["volume"] for peer_info in peer_data)
                    total_balanced_vol = sum(peer_info["volume"] * peer_info["weight"] for peer_info in peer_data)
                    balanced_shares, enforced, additional_passed, relaxed, detail = evaluate_category(
                        dimension,
                        category,
                        time_period,
                        peer_data,
                    )
                    structural_dim = f"{dimension}_{analyzer.time_column}"
                    structural_cat = f"{category}_{time_period}"
                    for index, peer_info in enumerate(peer_data):
                        original_share = (peer_info["volume"] / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                        balanced_vol = peer_info["volume"] * peer_info["weight"]
                        balanced_share = balanced_shares[index] if index < len(balanced_shares) else (
                            (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                        )
                        peer = peer_info["peer"]
                        append_row(
                            dimension=dimension,
                            category=category,
                            time_period=time_period,
                            peer=peer,
                            weight_source=weight_source,
                            weight_method=weight_method,
                            multiplier=peer_info["weight"],
                            original_volume=peer_info["volume"],
                            original_share_pct=original_share,
                            balanced_volume=balanced_vol,
                            balanced_share_pct=balanced_share,
                            secondary_rule_enforced=enforced,
                            secondary_rule_passed=additional_passed,
                            relaxation_used=relaxed,
                            secondary_rule_detail=detail,
                            structural_peer_pp=structural_peer_margin.get((structural_dim, structural_cat, str(peer)), 0.0),
                            structural_category_pp=structural_category_margin.get((structural_dim, structural_cat), 0.0),
                        )
            for time_period in time_periods:
                append_time_total_rows(time_period)
        else:
            entity_dim_agg = df.groupby([analyzer.entity_column, dimension]).agg({metric_col: "sum"}).reset_index()
            for category in entity_dim_agg[dimension].unique():
                cat_df = entity_dim_agg[entity_dim_agg[dimension] == category]
                peer_data = []
                for peer in peers:
                    volume = float(cat_df[cat_df[analyzer.entity_column] == peer][metric_col].sum())
                    peer_data.append({"peer": peer, "volume": volume, "weight": dim_weights.get(peer, 1.0)})
                total_original_vol = sum(peer_info["volume"] for peer_info in peer_data)
                total_balanced_vol = sum(peer_info["volume"] * peer_info["weight"] for peer_info in peer_data)
                balanced_shares, enforced, additional_passed, relaxed, detail = evaluate_category(
                    dimension,
                    category,
                    None,
                    peer_data,
                )
                structural_dim = str(dimension)
                structural_cat = str(category)
                for index, peer_info in enumerate(peer_data):
                    original_share = (peer_info["volume"] / total_original_vol * 100.0) if total_original_vol > 0 else 0.0
                    balanced_vol = peer_info["volume"] * peer_info["weight"]
                    balanced_share = balanced_shares[index] if index < len(balanced_shares) else (
                        (balanced_vol / total_balanced_vol * 100.0) if total_balanced_vol > 0 else 0.0
                    )
                    peer = peer_info["peer"]
                    append_row(
                        dimension=dimension,
                        category=category,
                        time_period=None,
                        peer=peer,
                        weight_source=weight_source,
                        weight_method=weight_method,
                        multiplier=peer_info["weight"],
                        original_volume=peer_info["volume"],
                        original_share_pct=original_share,
                        balanced_volume=balanced_vol,
                        balanced_share_pct=balanced_share,
                        secondary_rule_enforced=enforced,
                        secondary_rule_passed=additional_passed,
                        relaxation_used=relaxed,
                        secondary_rule_detail=detail,
                        structural_peer_pp=structural_peer_margin.get((structural_dim, structural_cat, str(peer)), 0.0),
                        structural_category_pp=structural_category_margin.get((structural_dim, structural_cat), 0.0),
                    )

    return PrivacyValidationResult(rows=rows)
