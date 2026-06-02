"""Typed privacy validation domain result and legacy DataFrame rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd


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
            primary_cap = bool(
                record.get("Primary_Cap_Passed", str(record.get("Compliant", "No")).lower() == "yes")
            )
            secondary_passed = str(record.get("Additional_Constraints_Passed", "Yes")).strip().lower() == "yes"
            relaxation_used = str(record.get("Additional_Constraints_Relaxed", "No")).strip().lower() == "yes"
            strict_compliant = (
                bool(record.get("Strict_Compliant"))
                if "Strict_Compliant" in record
                else (
                    str(record.get("Compliant", "No")).strip().lower() == "yes"
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
    """Build a typed validation result from the current legacy renderer."""
    from core.privacy_validation_builder import build_privacy_validation_dataframe

    return PrivacyValidationResult.from_dataframe(
        build_privacy_validation_dataframe(analyzer, df, metric_col, dimensions)
    )
