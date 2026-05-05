"""Compliance posture helpers for analysis runs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd

VALID_COMPLIANCE_POSTURES = frozenset({"strict", "best_effort", "accuracy_first"})


@dataclass
class ComplianceSummary:
    """Summarised compliance state for a run."""

    posture: str = "strict"
    acknowledgement_given: bool = False
    violations: int = 0
    structural_infeasibility: Optional[Dict[str, Any]] = None
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        has_violations = self.violations > 0
        has_structural = bool(self.structural_infeasibility)

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
) -> ComplianceSummary:
    violations = 0
    if privacy_validation_df is not None and not privacy_validation_df.empty:
        if "compliant" in privacy_validation_df.columns:
            violations = int((~privacy_validation_df["compliant"]).sum())
    return ComplianceSummary(
        posture=posture or "strict",
        acknowledgement_given=acknowledgement_given,
        violations=violations,
        structural_infeasibility=structural_infeasibility,
    )


def build_blocked_compliance_summary(
    posture: str,
    acknowledgement_given: bool,
) -> ComplianceSummary:
    return ComplianceSummary(
        posture=posture,
        acknowledgement_given=acknowledgement_given,
        details={"blocked": True, "reason": "acknowledgement required"},
    )
