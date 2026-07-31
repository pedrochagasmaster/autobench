"""Control 3 policy gates that sit outside numeric weight optimization."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Iterable, Optional


CLEARING_SPEND_BASIS = "clearing_spend"
CONTROL3_POLICY_KEYS = (
    "privacy_basis",
)


@dataclass(frozen=True)
class Control3PolicyEvidence:
    """Merged evidence required by machine-verifiable policy gates."""

    privacy_basis: Optional[str] = None

    @classmethod
    def from_mapping(cls, values: Dict[str, Any]) -> "Control3PolicyEvidence":
        return cls(
            privacy_basis=values.get("privacy_basis"),
        )

    def to_metadata_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Control3PolicyInput(Control3PolicyEvidence):
    """Control 3 evidence plus run mode facts for pre-analysis gating."""

    analysis_mode: str = "share"
    rate_types: Iterable[str] = field(default_factory=list)

    @classmethod
    def from_evidence(
        cls,
        evidence: Control3PolicyEvidence,
        *,
        analysis_mode: str,
        rate_types: Iterable[str],
    ) -> "Control3PolicyInput":
        return cls(
            **evidence.to_metadata_dict(),
            analysis_mode=analysis_mode,
            rate_types=rate_types,
        )


@dataclass(frozen=True)
class Control3PolicyResult:
    """Policy-gate result for a run."""

    allowed: bool
    blocked_reason: Optional[str] = None
    requirements: Dict[str, str] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)


REMEDIATION_HINTS: Dict[str, str] = {
    "fraud_chargeback_requires_clearing_spend_basis": (
        "Re-run with --privacy-basis clearing_spend; fraud/chargeback issuer "
        "benchmarking must use the clearing-spend concentration basis."
    ),
}


def remediation_hint(reason: Optional[str]) -> Optional[str]:
    """Return a human-facing remediation hint for a Control 3 block reason.

    Parameters
    ----------
    reason : str, optional
        The machine ``blocked_reason`` code produced by the policy gates.

    Returns
    -------
    str or None
        A short, actionable hint telling the user which flag/evidence resolves
        the block, or ``None`` when no hint is registered for ``reason``.
    """
    if not reason:
        return None
    return REMEDIATION_HINTS.get(reason)


def _normalized_basis(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return str(value).strip().lower().replace("-", "_").replace(" ", "_") or None


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

    basis = _normalized_basis(policy_input.privacy_basis)
    if _has_fraud_or_chargeback(policy_input.rate_types):
        if basis != CLEARING_SPEND_BASIS:
            return Control3PolicyResult(
                allowed=False,
                blocked_reason="fraud_chargeback_requires_clearing_spend_basis",
                requirements={**requirements, "fraud_chargeback_privacy_basis": "blocked_missing_required_basis"},
                details={"privacy_basis": basis},
            )
        requirements["fraud_chargeback_privacy_basis"] = "enforced"

    return Control3PolicyResult(allowed=True, requirements=requirements, details=details)
