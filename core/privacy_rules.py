"""Canonical Mastercard Control 3.2 privacy rule evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .constants import COMPARISON_EPSILON


@dataclass(frozen=True)
class PrivacyRule:
    """A Control 3.2 privacy rule definition."""

    name: str
    min_entities: int
    max_concentration: float
    secondary_requirements: Dict[str, Tuple[int, float]] = field(default_factory=dict)


@dataclass(frozen=True)
class PrivacyRuleEvaluation:
    """Structured result of evaluating one privacy rule against participant shares."""

    rule_name: str
    primary_cap_passed: bool
    participant_count_passed: bool
    secondary_rule_passed: bool
    relaxation_used: bool
    primary_cap_failures: int
    participant_failures: List[str]
    secondary_failures: List[str]
    max_share: float
    participant_count: int

    @property
    def strict_passed(self) -> bool:
        return (
            self.primary_cap_passed
            and self.participant_count_passed
            and self.secondary_rule_passed
            and not self.relaxation_used
        )


class RuleMode(str, Enum):
    STRICT = "strict"
    ADAPTIVE = "adaptive"
    BEST_EFFORT = "best_effort"
    ACCURACY_FIRST = "accuracy_first"


def _rule_config(rule_name: str) -> Dict[str, Any]:
    """Read the active rule config without making privacy_validator a dependency."""
    from core.privacy_validator import PrivacyValidator

    return PrivacyValidator.get_rule_config(rule_name)


def _count_at_or_above(values: Iterable[float], threshold: float) -> int:
    return sum(1 for value in values if float(value) + COMPARISON_EPSILON >= threshold)


def _secondary_requirements_from_config(
    rule_name: str,
    rule_config: Optional[Dict[str, Any]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
) -> Dict[str, Tuple[int, float]]:
    """Normalize legacy rule config shapes into ordered tier requirements.

    Tier counts are cumulative: ``10/40`` requires two participants at 20% and
    one additional participant at 10%, so the second tier is represented as
    ``(3, 10.0)``.
    """
    if thresholds:
        if any(str(key).startswith("tier_") for key in thresholds):
            tiers = sorted(
                thresholds.items(),
                key=lambda item: float(item[1][1]),
                reverse=True,
            )
            cumulative = 0
            normalized: Dict[str, Tuple[int, float]] = {}
            for index, (_tier_name, value) in enumerate(tiers, start=1):
                count, threshold = value
                cumulative += int(count)
                normalized[f"tier_{index}"] = (cumulative, float(threshold))
            return normalized
        rule_config = {"additional": thresholds}

    cfg = rule_config if rule_config is not None else _rule_config(rule_name)
    additional = cfg.get("additional", {}) if cfg else {}
    if not additional:
        return {}

    if "min_count_above_threshold" in additional:
        count, threshold = additional["min_count_above_threshold"]
        return {"tier_1": (int(count), float(threshold))}
    if "min_count_15" in additional:
        first = int(additional.get("min_count_15", 2))
        second = int(additional.get("min_count_8", 1))
        return {
            "tier_1": (first, 15.0),
            "tier_2": (first + second, 8.0),
        }
    if "min_count_20" in additional:
        first = int(additional.get("min_count_20", 2))
        second = int(additional.get("min_count_10", 1))
        return {
            "tier_1": (first, 20.0),
            "tier_2": (first + second, 10.0),
        }
    return {}


def privacy_rule_from_config(
    rule_name: str,
    rule_config: Optional[Dict[str, Any]] = None,
) -> PrivacyRule:
    cfg = rule_config if rule_config is not None else _rule_config(rule_name)
    return PrivacyRule(
        name=rule_name,
        min_entities=int(cfg.get("min_entities", 0) or 0),
        max_concentration=float(cfg.get("max_concentration", 0.0) or 0.0),
        secondary_requirements=_secondary_requirements_from_config(rule_name, cfg),
    )


def evaluate_rule(
    rule_name: str,
    shares: Iterable[float],
    *,
    rule_config: Optional[Dict[str, Any]] = None,
    thresholds: Optional[Dict[str, Any]] = None,
    mode: RuleMode | str = RuleMode.STRICT,
    relaxation_used: bool = False,
) -> PrivacyRuleEvaluation:
    """Evaluate primary cap and secondary participant requirements."""
    normalized_mode = mode if isinstance(mode, RuleMode) else RuleMode(str(mode))
    rule = privacy_rule_from_config(rule_name, rule_config)
    share_values = sorted((float(value) for value in shares), reverse=True)
    participant_count = len(share_values)
    max_share = max(share_values) if share_values else 0.0
    primary_failures = sum(
        1
        for value in share_values
        if value > rule.max_concentration + COMPARISON_EPSILON
    )
    primary_passed = primary_failures == 0
    participant_failures: List[str] = []
    if rule.min_entities and participant_count < rule.min_entities:
        participant_failures.append(
            f"Rule {rule_name}: Need at least {rule.min_entities} participants, found {participant_count}"
        )

    secondary_failures: List[str] = []
    requirements = (
        _secondary_requirements_from_config(rule_name, rule_config, thresholds)
        if normalized_mode != RuleMode.STRICT and thresholds
        else rule.secondary_requirements
    )
    for _name, (required_count, threshold) in requirements.items():
        observed = _count_at_or_above(share_values, threshold)
        if observed < required_count:
            secondary_failures.append(
                f"Rule {rule_name}: Need {required_count} participants >= {threshold:g}%, found {observed}"
            )

    return PrivacyRuleEvaluation(
        rule_name=rule_name,
        primary_cap_passed=primary_passed,
        participant_count_passed=not participant_failures,
        secondary_rule_passed=not secondary_failures,
        relaxation_used=bool(relaxation_used),
        primary_cap_failures=int(primary_failures),
        participant_failures=participant_failures,
        secondary_failures=secondary_failures,
        max_share=float(max_share),
        participant_count=participant_count,
    )


def additional_constraints_result(
    shares: Iterable[float],
    rule_name: str,
    *,
    thresholds: Optional[Dict[str, Any]] = None,
    relaxation_used: bool = False,
) -> Tuple[bool, List[str]]:
    mode = RuleMode.ADAPTIVE if thresholds is not None or relaxation_used else RuleMode.STRICT
    evaluation = evaluate_rule(
        rule_name,
        shares,
        thresholds=thresholds,
        mode=mode,
        relaxation_used=relaxation_used,
    )
    return (
        evaluation.participant_count_passed and evaluation.secondary_rule_passed,
        list(evaluation.participant_failures) + list(evaluation.secondary_failures),
    )
