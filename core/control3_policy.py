"""Control 3 policy gates that sit outside numeric weight optimization."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional


CLEARING_SPEND_BASIS = "clearing_spend"


@dataclass(frozen=True)
class Control3PolicyInput:
    """Run facts for Control 3 pre-analysis policy."""

    analysis_mode: str = "share"
    rate_types: Iterable[str] = field(default_factory=list)


@dataclass(frozen=True)
class Control3PolicyResult:
    """Policy-gate result for a run."""

    allowed: bool
    blocked_reason: Optional[str] = None
    requirements: Dict[str, str] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)


def _has_fraud_or_chargeback(rate_types: Iterable[str]) -> bool:
    normalized = {str(rate_type).strip().lower() for rate_type in rate_types}
    return bool(normalized.intersection({"fraud", "chargeback"}))


def evaluate_control3_policy(
    policy_input: Control3PolicyInput,
) -> Control3PolicyResult:
    """Evaluate enforceable Control 3 run-level policy gates.

    These gates cover machine-verifiable requirements that affect the
    calculation itself. Business eligibility and review decisions happen
    upstream of Autobench rather than through analyst self-attestations.
    """
    requirements: Dict[str, str] = {
        "control_3_2_numeric_rules": "enforced_by_privacy_validator",
        "citi_25pct_protected_entity_cap": "enforced_when_protected_entity_configured",
        "merchant_4_35_eligibility": "enforced_by_privacy_rule_strategy",
        "control_3_3_publication_confidentiality": "enforced_by_publication_redaction",
    }
    details: Dict[str, Any] = {}

    if _has_fraud_or_chargeback(policy_input.rate_types):
        requirements["fraud_concentration_basis"] = "derived_from_total_col"
        details["fraud_concentration_basis"] = CLEARING_SPEND_BASIS

    return Control3PolicyResult(allowed=True, requirements=requirements, details=details)
