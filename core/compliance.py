"""Compliance posture helpers for analysis runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

VALID_COMPLIANCE_POSTURES = frozenset({"strict", "best_effort", "accuracy_first"})


def _count_at_or_above(values: List[float], threshold: float) -> int:
    return sum(1 for value in values if value >= threshold)


def _evaluate_strict_secondary_rule(rule_name: str, shares: List[float]) -> bool:
    """Evaluate canonical additional Control 3.2 rules without dynamic relaxation."""
    if rule_name == "6/30":
        return _count_at_or_above(shares, 7.0) >= 3
    if rule_name == "7/35":
        return _count_at_or_above(shares, 15.0) >= 2 and _count_at_or_above(shares, 8.0) >= 3
    if rule_name == "10/40":
        return _count_at_or_above(shares, 20.0) >= 2 and _count_at_or_above(shares, 10.0) >= 3
    return True


def build_strict_final_validation(privacy_validation_df: Optional[pd.DataFrame]) -> Dict[str, Any]:
    """Independently validate final privacy rows against canonical rules.

    This is intentionally stricter than the report row labels: relaxed dynamic
    constraints are counted as violations even if the row-level ``Compliant``
    label says "Yes".
    """
    result: Dict[str, Any] = {
        "checked": False,
        "rows": 0,
        "primary_cap_fail_rows": 0,
        "secondary_rule_fail_categories": 0,
        "relaxed_rows": 0,
        "total_violations": 0,
    }
    if privacy_validation_df is None or privacy_validation_df.empty:
        return result

    required = {"Dimension", "Category", "Rule_Name", "Balanced_Share_%", "Privacy_Cap_%"}
    missing = sorted(required - set(privacy_validation_df.columns))
    result["checked"] = True
    result["rows"] = int(len(privacy_validation_df))
    if missing:
        if "Compliant" in privacy_validation_df.columns or "compliant" in privacy_validation_df.columns:
            result["checked"] = False
            result["skipped_reason"] = "strict validation columns unavailable"
            result["missing_columns"] = missing
            return result
        result["missing_columns"] = missing
        result["total_violations"] = 1
        return result

    df = privacy_validation_df.copy()
    balanced = pd.to_numeric(df["Balanced_Share_%"], errors="coerce")
    cap = pd.to_numeric(df["Privacy_Cap_%"], errors="coerce")
    result["primary_cap_fail_rows"] = int(((balanced > cap) | balanced.isna() | cap.isna()).sum())

    if "Additional_Constraints_Relaxed" in df.columns:
        relaxed = df["Additional_Constraints_Relaxed"].astype(str).str.strip().str.lower()
        result["relaxed_rows"] = int((relaxed == "yes").sum())

    secondary_failures = 0
    group_cols = ["Dimension", "Category"]
    if "Time_Period" in df.columns:
        group_cols.append("Time_Period")

    for _, group in df.groupby(group_cols, dropna=False):
        rule_name = str(group["Rule_Name"].iloc[0]).strip()
        shares = pd.to_numeric(group["Balanced_Share_%"], errors="coerce").fillna(-1.0).tolist()
        if not _evaluate_strict_secondary_rule(rule_name, shares):
            secondary_failures += 1

    result["secondary_rule_fail_categories"] = int(secondary_failures)
    result["total_violations"] = int(
        result["primary_cap_fail_rows"]
        + result["secondary_rule_fail_categories"]
        + result["relaxed_rows"]
    )
    return result


@dataclass
class ComplianceSummary:
    """Summarised compliance state for a run."""

    posture: str = "strict"
    acknowledgement_given: bool = False
    violations: int = 0
    structural_infeasibility: Optional[Dict[str, Any]] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        if self.details.get("blocked"):
            return {
                "posture": self.posture,
                "acknowledgement_given": self.acknowledgement_given,
                "violations": self.violations,
                "structural_infeasibility": self.structural_infeasibility,
                "run_status": "blocked",
                "compliance_verdict": "blocked",
                "acknowledgement_state": "acknowledged" if self.acknowledgement_given else "required_missing",
                "posture_consistent": False,
                **self.details,
            }

        has_violations = self.violations > 0
        has_structural = bool(self.structural_infeasibility) and bool(
            self.structural_infeasibility.get("has_structural_infeasibility")
        )

        if self.posture == "strict":
            run_status = "non_compliant" if has_violations else "compliant"
        elif self.posture == "best_effort":
            run_status = "completed_with_warnings" if has_violations else "compliant"
        elif self.posture == "accuracy_first":
            run_status = "completed_accuracy_first"
        else:
            run_status = "completed"

        if has_violations:
            compliance_verdict = "violations_detected"
        elif has_structural:
            compliance_verdict = "structural_infeasibility"
        else:
            compliance_verdict = "fully_compliant"

        acknowledgement_state = "acknowledged" if self.acknowledgement_given else "not_required"
        posture_consistent = not (self.posture == "strict" and has_violations)

        return {
            "posture": self.posture,
            "acknowledgement_given": self.acknowledgement_given,
            "violations": self.violations,
            "structural_infeasibility": self.structural_infeasibility,
            "run_status": run_status,
            "compliance_verdict": compliance_verdict,
            "acknowledgement_state": acknowledgement_state,
            "posture_consistent": posture_consistent,
            **self.details,
        }


def build_compliance_summary(
    *,
    posture: Optional[str],
    acknowledgement_given: bool = False,
    privacy_validation_df: Optional[pd.DataFrame] = None,
    structural_infeasibility: Optional[Dict[str, Any]] = None,
    blocked_reason: Optional[str] = None,
    blocked_details: Optional[Dict[str, Any]] = None,
) -> ComplianceSummary:
    """Build a ``ComplianceSummary`` from raw run inputs.

    When ``blocked_reason`` is supplied (e.g. ``"insufficient_peers"`` raised
    by :mod:`core.global_weight_optimizer`), the resulting summary serialises
    as ``run_status="blocked"`` / ``compliance_verdict="blocked"`` instead of a
    misleading ``"completed_with_warnings"``.
    """
    violations = 0
    if privacy_validation_df is not None and not privacy_validation_df.empty:
        if "compliant" in privacy_validation_df.columns:
            violations = int((~privacy_validation_df["compliant"].astype(bool)).sum())
        elif "Compliant" in privacy_validation_df.columns:
            normalized = privacy_validation_df["Compliant"].astype(str).str.strip().str.lower()
            violations = int((normalized != "yes").sum())

    details: Dict[str, Any] = {}
    strict_final_validation = build_strict_final_validation(privacy_validation_df)
    if strict_final_validation.get("checked"):
        details["strict_final_validation"] = strict_final_validation
        violations += int(strict_final_validation.get("total_violations", 0))

    if blocked_reason:
        details["blocked"] = True
        details["reason"] = blocked_reason
        if blocked_details:
            details.update(blocked_details)

    return ComplianceSummary(
        posture=posture or "strict",
        acknowledgement_given=acknowledgement_given,
        violations=violations,
        structural_infeasibility=structural_infeasibility,
        details=details,
    )


def build_blocked_compliance_summary(
    posture: str,
    acknowledgement_given: bool,
    reason: str = "acknowledgement required",
    extra_details: Optional[Dict[str, Any]] = None,
) -> ComplianceSummary:
    details: Dict[str, Any] = {"blocked": True, "reason": reason}
    if extra_details:
        details.update(extra_details)
    return ComplianceSummary(
        posture=posture,
        acknowledgement_given=acknowledgement_given,
        details=details,
    )
