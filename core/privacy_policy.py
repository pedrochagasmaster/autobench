"""Privacy policy facade wrapping PrivacyValidator rule selection."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .privacy_validator import PrivacyValidator

logger = logging.getLogger(__name__)


@dataclass
class PrivacyPolicySettings:
    """Settings bundle for dynamic constraint evaluation."""

    enforce_additional_constraints: bool = False
    dynamic_constraints_enabled: bool = False
    min_peer_count_for_constraints: int = 6
    min_effective_peer_count: int = 3
    min_category_volume_share: float = 0.01
    min_overall_volume_share: float = 0.01
    min_representativeness: float = 0.5
    dynamic_threshold_scale_floor: float = 0.5
    dynamic_count_scale_floor: float = 0.5


@dataclass
class ConstraintDecision:
    """Result of additional constraint applicability assessment."""

    enforce: bool = False
    reason: Optional[str] = None
    thresholds: Optional[Dict[str, Any]] = None
    relaxed: bool = False


class PrivacyPolicy:
    """High-level policy facade over PrivacyValidator rules."""

    def __init__(
        self,
        merchant_mode: bool = False,
        time_column: Optional[str] = None,
    ) -> None:
        self.merchant_mode = merchant_mode
        self.time_column = time_column

    def select_rule(self, peer_count: int) -> Tuple[str, Dict[str, Any]]:
        rule_name = PrivacyValidator.select_rule(peer_count, merchant_mode=self.merchant_mode)
        rule_cfg = PrivacyValidator.get_rule_config(rule_name)
        return rule_name, rule_cfg

    def _dynamic_thresholds(
        self,
        *,
        rule_name: str,
        participants: int,
        representativeness: float,
        settings: Optional[PrivacyPolicySettings] = None,
    ) -> Optional[Dict[str, Any]]:
        if settings is None:
            settings = PrivacyPolicySettings()

        if not settings.enforce_additional_constraints:
            return None
        if not settings.dynamic_constraints_enabled:
            thresholds = PrivacyValidator.get_penalty_thresholds(rule_name)
            return thresholds if thresholds else None

        base_thresholds = PrivacyValidator.get_penalty_thresholds(rule_name)
        if not base_thresholds:
            return None

        if participants < settings.min_peer_count_for_constraints:
            return None

        scale = max(
            settings.dynamic_threshold_scale_floor,
            min(1.0, representativeness / max(settings.min_representativeness, 1e-9)),
        )
        count_scale = max(
            settings.dynamic_count_scale_floor,
            min(1.0, representativeness / max(settings.min_representativeness, 1e-9)),
        )

        adjusted: Dict[str, Any] = {}
        for tier, (count, threshold) in base_thresholds.items():
            adj_count = max(1, int(round(count * count_scale)))
            adj_threshold = threshold * scale
            adjusted[tier] = (adj_count, adj_threshold)
        return adjusted

    def assess_additional_constraints(
        self,
        *,
        rule_name: Optional[str],
        dimension: Optional[str],
        peers: List[str],
        peer_volumes: Dict[str, float],
        stats: Optional[Dict[str, float]] = None,
        settings: Optional[PrivacyPolicySettings] = None,
    ) -> ConstraintDecision:
        if settings is None:
            settings = PrivacyPolicySettings()

        if not settings.enforce_additional_constraints:
            return ConstraintDecision(enforce=False, reason="additional constraints disabled")

        if not rule_name or rule_name == "insufficient":
            return ConstraintDecision(enforce=False, reason=f"rule {rule_name!r} has no additional constraints")

        base_thresholds = PrivacyValidator.get_penalty_thresholds(rule_name)
        if not base_thresholds:
            return ConstraintDecision(enforce=False, reason=f"rule {rule_name!r} has no additional constraints")

        peer_count = len(peers)
        if peer_count < settings.min_peer_count_for_constraints:
            return ConstraintDecision(
                enforce=False,
                reason=f"peer count {peer_count} below minimum {settings.min_peer_count_for_constraints}",
            )

        total_volume = sum(peer_volumes.values()) if peer_volumes else 0.0
        if total_volume <= 0:
            return ConstraintDecision(enforce=False, reason="zero total volume")

        representativeness = 1.0
        if stats:
            representativeness = stats.get("representativeness", 1.0)

        thresholds = self._dynamic_thresholds(
            rule_name=rule_name,
            participants=peer_count,
            representativeness=representativeness,
            settings=settings,
        )

        relaxed = settings.dynamic_constraints_enabled and thresholds != base_thresholds
        return ConstraintDecision(
            enforce=True,
            thresholds=thresholds,
            relaxed=relaxed,
        )
