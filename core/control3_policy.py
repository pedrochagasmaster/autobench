"""Control 3 policy gates that sit outside numeric weight optimization."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any, Dict, Iterable, Optional


CLEARING_SPEND_BASIS = "clearing_spend"
CONTROL3_POLICY_KEYS = (
    "privacy_basis",
    "contains_digital_wallet_metrics",
    "digital_wallet_review_approved",
    "contains_top_merchant_output",
    "dual_entity_axis",
    "dual_entity_axis_review_approved",
    "recurring_deliverable",
    "last_privacy_recheck_date",
    "peer_group_altered",
)


@dataclass(frozen=True)
class Control3PolicyEvidence:
    """Merged run-level Control 3 declarations used for policy gating."""

    privacy_basis: Optional[str] = None
    contains_digital_wallet_metrics: bool = False
    digital_wallet_review_approved: bool = False
    contains_top_merchant_output: bool = False
    dual_entity_axis: bool = False
    dual_entity_axis_review_approved: bool = False
    recurring_deliverable: bool = False
    last_privacy_recheck_date: Optional[Any] = None
    peer_group_altered: bool = False

    @classmethod
    def from_mapping(cls, values: Dict[str, Any]) -> "Control3PolicyEvidence":
        return cls(
            privacy_basis=values.get("privacy_basis"),
            contains_digital_wallet_metrics=bool(values.get("contains_digital_wallet_metrics", False)),
            digital_wallet_review_approved=bool(values.get("digital_wallet_review_approved", False)),
            contains_top_merchant_output=bool(values.get("contains_top_merchant_output", False)),
            dual_entity_axis=bool(values.get("dual_entity_axis", False)),
            dual_entity_axis_review_approved=bool(values.get("dual_entity_axis_review_approved", False)),
            recurring_deliverable=bool(values.get("recurring_deliverable", False)),
            last_privacy_recheck_date=values.get("last_privacy_recheck_date"),
            peer_group_altered=bool(values.get("peer_group_altered", False)),
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
    "digital_wallet_metrics_require_privacy_review": (
        "Obtain the required Privacy review for digital wallet metrics, then "
        "re-run with --digital-wallet-review-approved."
    ),
    "top_merchant_lists_not_allowed": (
        "Control 3 prohibits top-merchant deliverables; remove the top-merchant "
        "list from the output and drop --contains-top-merchant-output."
    ),
    "dual_entity_axis_requires_privacy_review": (
        "Obtain the required Privacy review for the dual entity-axis benchmark, "
        "then re-run with --dual-entity-axis-review-approved."
    ),
    "recurring_deliverable_recheck_required": (
        "Record a current privacy re-check with --last-privacy-recheck-date "
        "YYYY-MM-DD (within the last 365 days; re-check whenever the peer group "
        "changes)."
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


def _parse_date(value: Optional[Any]) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def _has_fraud_or_chargeback(rate_types: Iterable[str]) -> bool:
    normalized = {str(rate_type).strip().lower() for rate_type in rate_types}
    return bool(normalized.intersection({"fraud", "chargeback"}))


def evaluate_control3_policy(
    policy_input: Control3PolicyInput,
    *,
    today: Optional[date] = None,
) -> Control3PolicyResult:
    """Evaluate enforceable Control 3 run-level policy gates.

    These gates cover requirements that cannot be solved by privacy weighting
    alone. They block only when a run declares a sensitive condition and lacks
    the required explicit evidence.
    """
    today = today or date.today()
    requirements: Dict[str, str] = {
        "control_3_2_numeric_rules": "enforced_by_privacy_validator",
        "citi_25pct_protected_entity_cap": "enforced_when_protected_entity_configured",
        "merchant_4_35_eligibility": "enforced_by_merchant_mode_rule_selection",
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

    if policy_input.contains_digital_wallet_metrics and not policy_input.digital_wallet_review_approved:
        return Control3PolicyResult(
            allowed=False,
            blocked_reason="digital_wallet_metrics_require_privacy_review",
            requirements={**requirements, "digital_wallet_review": "blocked_missing_privacy_review"},
        )
    requirements["digital_wallet_review"] = (
        "manual_approval_recorded" if policy_input.contains_digital_wallet_metrics else "not_applicable"
    )

    if policy_input.contains_top_merchant_output:
        return Control3PolicyResult(
            allowed=False,
            blocked_reason="top_merchant_lists_not_allowed",
            requirements={**requirements, "top_merchant_outputs": "blocked_not_allowed"},
        )
    requirements["top_merchant_outputs"] = "enforced"

    if policy_input.dual_entity_axis and not policy_input.dual_entity_axis_review_approved:
        return Control3PolicyResult(
            allowed=False,
            blocked_reason="dual_entity_axis_requires_privacy_review",
            requirements={**requirements, "dual_entity_axis_protection": "blocked_missing_privacy_review"},
        )
    requirements["dual_entity_axis_protection"] = (
        "manual_approval_recorded" if policy_input.dual_entity_axis else "not_applicable"
    )

    if policy_input.recurring_deliverable:
        recheck_date = _parse_date(policy_input.last_privacy_recheck_date)
        details["last_privacy_recheck_date"] = recheck_date.isoformat() if recheck_date else None
        needs_recheck = recheck_date is None or (today - recheck_date).days > 365
        if policy_input.peer_group_altered and recheck_date != today:
            needs_recheck = True
        if needs_recheck:
            return Control3PolicyResult(
                allowed=False,
                blocked_reason="recurring_deliverable_recheck_required",
                requirements={**requirements, "recurring_recheck_evidence": "blocked_missing_current_recheck"},
                details=details,
            )
        requirements["recurring_recheck_evidence"] = "enforced"
    else:
        requirements["recurring_recheck_evidence"] = "not_applicable"

    return Control3PolicyResult(allowed=True, requirements=requirements, details=details)
