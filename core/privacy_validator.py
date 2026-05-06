"""
PrivacyValidator - Privacy compliance validation for peer groups.

Implements multiple privacy rules (5/25, 6/30, 7/35, 10/40, 4/35) and
validates concentration limits for regulatory compliance.

Rule Specifications:
-------------------
- 5/25: Min 5 participants, max 25% per participant
  Example: [25, 25, 25, 24, 1]

- 6/30: Min 6 participants, max 30% per participant, at least 3 participants >= 7%
  Example: [30, 24.5, 24.5, 7, 7, 7] or [30, 30, 30, 3.33, 3.33, 3.33]

- 7/35: Min 7 participants, max 35% per participant, at least 2 >= 15%, 
        and at least 1 additional participant >= 8%
  Example: [35, 15, 15, 8.75, 8.75, 8.75, 8.75]

- 10/40: Min 10 participants, max 40% per participant, at least 2 >= 20%, 
         and at least 1 additional participant >= 10%
  Example: [40, 20, 20, 10, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6]

- 4/35 (Merchant benchmarking only): Min 4 participants, max 35% per participant
"""

import logging
import os
from pathlib import Path
from typing import List, Tuple, Optional, Dict, Any, cast

import pandas as pd

from .constants import COMPARISON_EPSILON as SHARED_COMPARISON_EPSILON

logger = logging.getLogger(__name__)


class PrivacyValidator:
    """
    Validates peer groups against privacy concentration rules.
    
    Supports multiple privacy rules with maximum concentration limits
    and minimum percentage requirements:
    
    - 5/25: 5 minimum entities, 25% max concentration
      Compliant example: [25, 25, 25, 24, 1]
      
    - 6/30: 6 minimum entities, 30% max concentration
      + At least 3 participants must be >= 7%
      Compliant examples: [30, 24.5, 24.5, 7, 7, 7] or [30, 30, 30, 3.33, 3.33, 3.33]
      
    - 7/35: 7 minimum entities, 35% max concentration
      + At least 2 participants must be >= 15%
      + At least 1 additional participant must be >= 8%
      Compliant example: [35, 15, 15, 8.75, 8.75, 8.75, 8.75]
      
    - 10/40: 10 minimum entities, 40% max concentration
      + At least 2 participants must be >= 20%
      + At least 1 additional participant must be >= 10%
      Compliant example: [40, 20, 20, 10, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6]
      
    - 4/35: 4 minimum entities, 35% max concentration (merchant benchmarking only)
    """
    
    DEFAULT_RULES = {
        # 5/25: No participant may exceed 25%
        '5/25': {
            'min_entities': 5, 
            'max_concentration': 25.0
        },
        # 6/30: No participant may exceed 30%, at least 3 participants must be >= 7%
        '6/30': {
            'min_entities': 6, 
            'max_concentration': 30.0,
            'additional': {'min_count_above_threshold': (3, 7.0)}
        },
        # 7/35: No participant may exceed 35%, at least 2 >= 15%, at least 1 additional >= 8%
        '7/35': {
            'min_entities': 7, 
            'max_concentration': 35.0,
            'additional': {'min_count_15': 2, 'min_count_8': 1}
        },
        # 10/40: No participant may exceed 40%, at least 2 >= 20%, at least 1 additional >= 10%
        '10/40': {
            'min_entities': 10, 
            'max_concentration': 40.0,
            'additional': {'min_count_20': 2, 'min_count_10': 1}
        },
        # 4/35: Merchant benchmarking only - no participant may exceed 35%
        '4/35': {
            'min_entities': 4, 
            'max_concentration': 35.0
        }
    }

    RULES_ENV_VAR = "PBT_PRIVACY_RULES_FILE"
    DEFAULT_RULES_FILE = Path(__file__).resolve().parent.parent / "config" / "privacy_rules.yaml"
    COMPARISON_EPSILON = SHARED_COMPARISON_EPSILON
    _RULES_CACHE: Optional[Dict[str, Dict[str, Any]]] = None

    @classmethod
    def _rules_file_path(cls) -> Path:
        env_path = os.getenv(cls.RULES_ENV_VAR)
        if env_path:
            return Path(env_path)
        return cls.DEFAULT_RULES_FILE

    @classmethod
    def _validate_rules_schema(cls, rules: Dict[str, Dict[str, Any]]) -> None:
        for rule_name, rule_cfg in rules.items():
            if not isinstance(rule_cfg, dict):
                raise ValueError(f"Rule '{rule_name}' must map to a dictionary.")
            min_entities = rule_cfg.get('min_entities')
            max_concentration = rule_cfg.get('max_concentration')
            if not isinstance(min_entities, int) or min_entities <= 0:
                raise ValueError(f"Rule '{rule_name}' has invalid min_entities: {min_entities}")
            if not isinstance(max_concentration, (int, float)) or max_concentration <= 0:
                raise ValueError(f"Rule '{rule_name}' has invalid max_concentration: {max_concentration}")
            additional = rule_cfg.get('additional')
            if additional is not None and not isinstance(additional, dict):
                raise ValueError(f"Rule '{rule_name}' additional constraints must be a dictionary.")

    @classmethod
    def _load_rules_from_file(cls) -> Optional[Dict[str, Dict[str, Any]]]:
        path = cls._rules_file_path()
        if not path.exists():
            return None
        try:
            import yaml

            with open(path, 'r', encoding='utf-8') as handle:
                data = yaml.safe_load(handle) or {}
            if not isinstance(data, dict):
                raise ValueError("Privacy rules file must contain a dictionary at root.")
            rules = cast(Optional[Dict[str, Dict[str, Any]]], data.get('rules'))
            if not isinstance(rules, dict):
                raise ValueError("Privacy rules file must contain a 'rules' dictionary.")
            cls._validate_rules_schema(rules)
            logger.info("Loaded privacy rules from %s", path)
            return rules
        except Exception as exc:
            logger.warning("Failed to load privacy rules from %s: %s", path, exc)
            return None

    @classmethod
    def reload_rules(cls) -> Dict[str, Dict[str, Any]]:
        """Reload rules from disk or fall back to built-in defaults."""
        loaded_rules = cls._load_rules_from_file()
        cls._RULES_CACHE = loaded_rules or cls.DEFAULT_RULES.copy()
        return cls._RULES_CACHE

    @classmethod
    def get_rules(cls) -> Dict[str, Dict[str, Any]]:
        """Return active privacy rules, loading from file on first use."""
        if cls._RULES_CACHE is None:
            cls.reload_rules()
        return cls._RULES_CACHE or cls.DEFAULT_RULES

    @staticmethod
    def _count_at_or_above(values: List[float], threshold: float) -> int:
        epsilon = PrivacyValidator.COMPARISON_EPSILON
        return sum(1 for value in values if value + epsilon >= threshold)

    @classmethod
    def get_penalty_thresholds(cls, rule_name: str) -> Dict[str, Tuple[int, float]]:
        """
        Return thresholds for penalty calculation in optimization.
        
        This method exposes the "additional" constraints from RULES in a format
        suitable for optimization penalty functions used by DimensionalAnalyzer.
        Using this method instead of hardcoding values ensures consistency.
        
        Parameters:
        -----------
        rule_name : str
            Name of the privacy rule (e.g., '6/30', '7/35', '10/40')
            
        Returns:
        --------
        Dict[str, Tuple[int, float]]
            Dictionary mapping constraint names to (min_count, threshold_percentage).
            For example: {'tier_1': (3, 7.0)} means at least 3 participants >= 7%.
            
        Examples:
        ---------
        >>> PrivacyValidator.get_penalty_thresholds('6/30')
        {'tier_1': (3, 7.0)}
        >>> PrivacyValidator.get_penalty_thresholds('7/35')
        {'tier_1': (2, 15.0), 'tier_2': (1, 8.0)}
        """
        rule = cls.get_rules().get(rule_name, {})
        additional = rule.get('additional', {})
        
        if not additional:
            return {}
        
        result: Dict[str, Tuple[int, float]] = {}
        
        # Handle 6/30 format: min_count_above_threshold: (3, 7.0)
        if 'min_count_above_threshold' in additional:
            count, threshold = additional['min_count_above_threshold']
            result['tier_1'] = (count, threshold)
        
        # Handle 7/35 format: min_count_15: 2, min_count_8: 1
        if 'min_count_15' in additional:
            result['tier_1'] = (additional['min_count_15'], 15.0)
        if 'min_count_8' in additional:
            result['tier_2'] = (additional['min_count_8'], 8.0)
        
        # Handle 10/40 format: min_count_20: 2, min_count_10: 1
        if 'min_count_20' in additional:
            result['tier_1'] = (additional['min_count_20'], 20.0)
        if 'min_count_10' in additional:
            result['tier_2'] = (additional['min_count_10'], 10.0)
        
        return result

    def _check_min_participants(
        self,
        peer_group: pd.DataFrame,
        entity_column: str
    ) -> Tuple[bool, List[str]]:
        warnings: List[str] = []
        if entity_column in peer_group.columns:
            num_entities = int(peer_group[entity_column].nunique())
        else:
            num_entities = len(peer_group)
        if num_entities < self.min_participants:
            warnings.append(
                f"Insufficient entities: {num_entities} < {self.min_participants}"
            )
            return False, warnings
        return True, warnings

    def _build_concentration_frame(
        self,
        peer_group: pd.DataFrame,
        metric: str,
        entity_column: str
    ) -> Tuple[Optional[pd.DataFrame], List[str]]:
        warnings: List[str] = []
        if metric not in peer_group.columns:
            warnings.append(f"Metric '{metric}' not found in data")
            return None, warnings

        if entity_column in peer_group.columns:
            agg = peer_group.groupby(entity_column, as_index=False)[metric].sum()
        else:
            agg = peer_group.copy()
        total = agg[metric].sum()
        if total == 0:
            warnings.append(f"Total for metric '{metric}' is zero")
            return None, warnings
        agg['concentration'] = (agg[metric] / total) * 100
        return agg, warnings

    def _check_entity_concentration(
        self,
        peer_group: pd.DataFrame,
        metric: str,
        entity_column: str
    ) -> Tuple[bool, List[str]]:
        warnings: List[str] = []
        is_compliant = True

        for _, row in peer_group.iterrows():
            entity_name = row[entity_column]
            concentration = row['concentration']

            if entity_name in self.protected_entities:
                if concentration > self.protected_max_concentration:
                    warnings.append(
                        f"Protected entity '{entity_name}' exceeds {self.protected_max_concentration}% "
                        f"for '{metric}': {concentration:.2f}%"
                    )
                    is_compliant = False
            elif concentration > self.max_concentration:
                warnings.append(
                    f"Entity '{entity_name}' exceeds {self.max_concentration}% "
                    f"for '{metric}': {concentration:.2f}%"
                )
                is_compliant = False

        return is_compliant, warnings

    @classmethod
    def select_rule(cls, peer_count: int, merchant_mode: bool = False) -> str:
        """Select privacy rule name based on peer count.

        Note: 4/35 is applied only when merchant_mode is True.
        """
        rules = cls.get_rules()

        if merchant_mode and '4/35' in rules and peer_count == int(rules['4/35'].get('min_entities', 4)):
            return '4/35'

        ordered_rules = sorted(
            (
                (name, cfg)
                for name, cfg in rules.items()
                if name != '4/35'
            ),
            key=lambda item: int(item[1].get('min_entities', 0)),
            reverse=True,
        )
        for rule_name, rule_cfg in ordered_rules:
            if peer_count >= int(rule_cfg.get('min_entities', 0)):
                return rule_name

        return 'insufficient'

    @classmethod
    def get_rule_config(cls, rule_name: str) -> Dict[str, Any]:
        """Return rule configuration (min_entities, max_concentration, additional)."""
        return cls.get_rules().get(rule_name, {})

    @classmethod
    def evaluate_additional_constraints(
        cls,
        shares: List[float],
        rule_name: str
    ) -> Tuple[bool, List[str]]:
        """Evaluate additional Control 3.2 constraints for a list of shares.

        Parameters
        ----------
        shares : List[float]
            Percent shares for the peer group (already balanced), 0-100.
        rule_name : str
            Rule identifier (e.g., '6/30', '7/35').

        Returns
        -------
        Tuple[bool, List[str]]
            (passed, details). details contains human-readable failures.
        """
        rule = cls.get_rules().get(rule_name)
        if not rule:
            # No additional constraints for unknown or insufficient rule
            return True, []

        details: List[str] = []
        passed = True

        min_entities = int(rule.get('min_entities', 0))
        if len(shares) < min_entities:
            passed = False
            details.append(f"Need at least {min_entities} participants, found {len(shares)}")
            # Even if participant count is insufficient, return now.
            return passed, details

        shares_sorted = sorted([float(s) for s in shares], reverse=True)
        additional = rule.get('additional', {})

        # 6/30: at least 3 participants >= 7%
        if 'min_count_above_threshold' in additional:
            min_count, threshold = additional['min_count_above_threshold']
            count_above = cls._count_at_or_above(shares_sorted, threshold)
            if count_above < min_count:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count} participants >= {threshold}%, found {count_above}"
                )

        # 7/35: at least 2 >= 15% and 1 additional >= 8%
        if 'min_count_15' in additional:
            min_count_15 = additional.get('min_count_15', 0)
            min_count_8 = additional.get('min_count_8', 0)
            count_15 = cls._count_at_or_above(shares_sorted, 15.0)
            count_8 = cls._count_at_or_above(shares_sorted, 8.0)
            if count_15 < min_count_15:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_15} participants >= 15%, found {count_15}"
                )
            if count_8 < (min_count_15 + min_count_8):
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_8} additional participants >= 8%, found {max(count_8 - min_count_15, 0)}"
                )

        # 10/40: at least 2 >= 20% and 1 additional >= 10%
        if 'min_count_20' in additional:
            min_count_20 = additional.get('min_count_20', 0)
            min_count_10 = additional.get('min_count_10', 0)
            count_20 = cls._count_at_or_above(shares_sorted, 20.0)
            count_10 = cls._count_at_or_above(shares_sorted, 10.0)
            if count_20 < min_count_20:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_20} participants >= 20%, found {count_20}"
                )
            if count_10 < (min_count_20 + min_count_10):
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_10} additional participants >= 10%, found {max(count_10 - min_count_20, 0)}"
                )

        return passed, details

    @classmethod
    def evaluate_additional_constraints_with_thresholds(
        cls,
        shares: List[float],
        rule_name: str,
        thresholds: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, List[str]]:
        """Evaluate additional constraints using custom thresholds (dynamic scaling).

        thresholds can include:
        - {'tier_1': (min_count, threshold), 'tier_2': (min_count, threshold)}
        - or legacy keys used in RULES (min_count_above_threshold, min_count_15, min_count_8, ...)
        """
        if thresholds is None:
            return cls.evaluate_additional_constraints(shares, rule_name)

        shares_sorted = sorted([float(s) for s in shares], reverse=True)
        details: List[str] = []
        passed = True
        use_tiers = any(key.startswith('tier_') for key in thresholds.keys())

        if rule_name == '6/30':
            if use_tiers:
                min_count, threshold = thresholds.get('tier_1', (3, 7.0))
            else:
                min_count, threshold = thresholds.get('min_count_above_threshold', (3, 7.0))
            idx = int(min_count) - 1
            observed = shares_sorted[idx] if idx < len(shares_sorted) else 0.0
            if observed + cls.COMPARISON_EPSILON < threshold:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count} participants >= {threshold:.2f}%, "
                    f"found {cls._count_at_or_above(shares_sorted, threshold)}"
                )
        elif rule_name == '7/35':
            if use_tiers:
                min_count_15, threshold_15 = thresholds.get('tier_1', (2, 15.0))
                min_count_8, threshold_8 = thresholds.get('tier_2', (1, 8.0))
            else:
                min_count_15 = int(thresholds.get('min_count_15', 2))
                min_count_8 = int(thresholds.get('min_count_8', 1))
                threshold_15 = float(thresholds.get('threshold_15', 15.0))
                threshold_8 = float(thresholds.get('threshold_8', 8.0))
            idx_15 = min_count_15 - 1
            idx_8 = min_count_15 + min_count_8 - 1
            observed_15 = shares_sorted[idx_15] if idx_15 < len(shares_sorted) else 0.0
            observed_8 = shares_sorted[idx_8] if idx_8 < len(shares_sorted) else 0.0
            if observed_15 + cls.COMPARISON_EPSILON < threshold_15:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_15} participants >= {threshold_15:.2f}%, "
                    f"found {cls._count_at_or_above(shares_sorted, threshold_15)}"
                )
            if observed_8 + cls.COMPARISON_EPSILON < threshold_8:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_8} additional participants >= {threshold_8:.2f}%, "
                    f"found {max(cls._count_at_or_above(shares_sorted, threshold_8) - min_count_15, 0)}"
                )
        elif rule_name == '10/40':
            if use_tiers:
                min_count_20, threshold_20 = thresholds.get('tier_1', (2, 20.0))
                min_count_10, threshold_10 = thresholds.get('tier_2', (1, 10.0))
            else:
                min_count_20 = int(thresholds.get('min_count_20', 2))
                min_count_10 = int(thresholds.get('min_count_10', 1))
                threshold_20 = float(thresholds.get('threshold_20', 20.0))
                threshold_10 = float(thresholds.get('threshold_10', 10.0))
            idx_20 = min_count_20 - 1
            idx_10 = min_count_20 + min_count_10 - 1
            observed_20 = shares_sorted[idx_20] if idx_20 < len(shares_sorted) else 0.0
            observed_10 = shares_sorted[idx_10] if idx_10 < len(shares_sorted) else 0.0
            if observed_20 + cls.COMPARISON_EPSILON < threshold_20:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_20} participants >= {threshold_20:.2f}%, "
                    f"found {cls._count_at_or_above(shares_sorted, threshold_20)}"
                )
            if observed_10 + cls.COMPARISON_EPSILON < threshold_10:
                passed = False
                details.append(
                    f"Rule {rule_name}: Need {min_count_10} additional participants >= {threshold_10:.2f}%, "
                    f"found {max(cls._count_at_or_above(shares_sorted, threshold_10) - min_count_20, 0)}"
                )

        return passed, details
    
    def __init__(
        self,
        min_participants: int = 5,
        max_concentration: float = 25.0,
        rule_name: Optional[str] = None,
        protected_entities: Optional[List[str]] = None,
        protected_max_concentration: Optional[float] = None
    ):
        """
        Initialize privacy validator.
        
        Parameters:
        -----------
        min_participants : int
            Minimum number of entities in peer group
        max_concentration : float
            Maximum concentration percentage for any single entity
        rule_name : str, optional
            Named rule to apply (e.g., '5/25', '6/30')
        protected_entities : List[str], optional
            List of entity names with special concentration limits
        protected_max_concentration : float, optional
            Maximum concentration for protected entities. Defaults to selected rule cap.
        """
        rules = self.get_rules()
        if rule_name and rule_name in rules:
            rule = rules[rule_name]
            self.min_participants = rule['min_entities']
            self.max_concentration = rule['max_concentration']
            self.rule_name = rule_name
            self.additional_constraints = rule.get('additional', {})
        else:
            self.min_participants = min_participants
            self.max_concentration = max_concentration
            self.rule_name = 'custom'
            self.additional_constraints = {}
        
        self.protected_entities = protected_entities or []
        self.protected_max_concentration = (
            float(protected_max_concentration)
            if protected_max_concentration is not None
            else float(self.max_concentration)
        )
        
        logger.info(f"Initialized PrivacyValidator with rule: {self.rule_name}")
        logger.info(f"Min participants: {self.min_participants}, "
                   f"Max concentration: {self.max_concentration}%")
    
    def validate_peer_group(
        self,
        peer_group: pd.DataFrame,
        metrics: List[str],
        entity_column: str = 'entity_identifier'
    ) -> Tuple[bool, List[str]]:
        """
        Validate peer group against privacy rules.
        
        Parameters:
        -----------
        peer_group : pd.DataFrame
            Candidate peer group data
        metrics : List[str]
            Metric columns to check for concentration
        entity_column : str
            Column containing entity identifiers
            
        Returns:
        --------
        Tuple[bool, List[str]]
            (is_compliant, list_of_warnings)
        """
        warnings: List[str] = []
        is_compliant = True

        # Check minimum participants
        min_ok, min_warnings = self._check_min_participants(peer_group, entity_column)
        if not min_ok:
            warnings.extend(min_warnings)
            return False, warnings

        # Check concentration for each metric
        for metric in metrics:
            conc_df, metric_warnings = self._build_concentration_frame(peer_group, metric, entity_column)
            if metric_warnings:
                warnings.extend(metric_warnings)
            if conc_df is None:
                continue

            metric_ok, metric_warnings = self._check_entity_concentration(conc_df, metric, entity_column)
            if not metric_ok:
                is_compliant = False
            warnings.extend(metric_warnings)

            # Check additional constraints based on rule
            if self.additional_constraints:
                constraint_check, constraint_warnings = self._check_additional_constraints(
                    conc_df, metric, entity_column
                )
                if not constraint_check:
                    is_compliant = False
                warnings.extend(constraint_warnings)
        
        if is_compliant:
            logger.debug(f"Peer group is compliant with {self.rule_name} rule")
        else:
            logger.warning(f"Peer group violates {self.rule_name} rule: {len(warnings)} issues")
        
        return is_compliant, warnings
    
    def _check_additional_constraints(
        self,
        peer_group: pd.DataFrame,
        metric: str,
        entity_column: str
    ) -> Tuple[bool, List[str]]:
        """
        Check additional constraints for specific rules.
        
        Parameters:
        -----------
        peer_group : pd.DataFrame
            Peer group with concentration calculated
        metric : str
            Metric being evaluated
        entity_column : str
            Entity identifier column
            
        Returns:
        --------
        Tuple[bool, List[str]]
            (constraint_met, warnings)
        """
        warnings = []
        constraints_met = True
        
        # Rule 6/30: At least 3 entities >= 7%
        if 'min_count_above_threshold' in self.additional_constraints:
            min_count, threshold = self.additional_constraints['min_count_above_threshold']
            count_above = self._count_at_or_above(peer_group['concentration'].tolist(), threshold)
            
            if count_above < min_count:
                warnings.append(
                    f"Rule 6/30: Need {min_count} entities >= {threshold}%, found {count_above}"
                )
                constraints_met = False
        
        # Rule 7/35: At least 2 entities >= 15% AND 1 entity >= 8%
        if 'min_count_15' in self.additional_constraints:
            count_15 = self._count_at_or_above(peer_group['concentration'].tolist(), 15.0)
            count_8 = self._count_at_or_above(peer_group['concentration'].tolist(), 8.0)
            
            if count_15 < self.additional_constraints['min_count_15']:
                warnings.append(
                    f"Rule 7/35: Need {self.additional_constraints['min_count_15']} "
                    f"entities >= 15%, found {count_15}"
                )
                constraints_met = False
            
            if count_8 < (self.additional_constraints['min_count_15'] + 
                         self.additional_constraints.get('min_count_8', 0)):
                warnings.append("Rule 7/35: Additional entity >= 8% requirement not met")
                constraints_met = False
        
        # Rule 10/40: At least 2 entities >= 20% AND 1 entity >= 10%
        if 'min_count_20' in self.additional_constraints:
            count_20 = self._count_at_or_above(peer_group['concentration'].tolist(), 20.0)
            count_10 = self._count_at_or_above(peer_group['concentration'].tolist(), 10.0)
            
            if count_20 < self.additional_constraints['min_count_20']:
                warnings.append(
                    f"Rule 10/40: Need {self.additional_constraints['min_count_20']} "
                    f"entities >= 20%, found {count_20}"
                )
                constraints_met = False
            
            if count_10 < (self.additional_constraints['min_count_20'] + 
                          self.additional_constraints.get('min_count_10', 0)):
                warnings.append("Rule 10/40: Additional entity >= 10% requirement not met")
                constraints_met = False
        
        return constraints_met, warnings
    
    def calculate_concentration(
        self,
        peer_group: pd.DataFrame,
        metric: str,
        entity_column: str = 'entity_identifier'
    ) -> pd.DataFrame:
        """
        Calculate concentration percentages for a peer group.
        
        Parameters:
        -----------
        peer_group : pd.DataFrame
            Peer group data
        metric : str
            Metric column to calculate concentration
        entity_column : str
            Entity identifier column
            
        Returns:
        --------
        pd.DataFrame
            Peer group with concentration column added
        """
        result = peer_group.copy()
        total = result[metric].sum()
        
        if total > 0:
            result['concentration'] = (result[metric] / total) * 100
        else:
            result['concentration'] = 0
        
        return result
    
    def apply_weighting(
        self,
        peer_group: pd.DataFrame,
        metric: str,
        threshold_percentage: Optional[float] = None,
        entity_column: str = 'entity_identifier'
    ) -> pd.DataFrame:
        """
        Apply weighting to entities exceeding concentration threshold.
        
        This adjusts entity values to exactly meet the threshold,
        applying an adjustment factor.
        
        Parameters:
        -----------
        peer_group : pd.DataFrame
            Peer group data
        metric : str
            Metric column to weight
        threshold_percentage : float, optional
            Threshold to apply (uses max_concentration if None)
        entity_column : str
            Entity identifier column
            
        Returns:
        --------
        pd.DataFrame
            Weighted peer group with adjustment_factor column
        """
        if threshold_percentage is None:
            threshold_percentage = self.max_concentration
        
        logger.info(f"Applying weighting with {threshold_percentage}% threshold")
        
        result = peer_group.copy()
        result['adjustment_factor'] = 1.0
        
        # Iteratively adjust entities exceeding threshold
        max_iterations = 10
        iteration = 0
        
        while iteration < max_iterations:
            total = result[metric].sum()
            
            if total == 0:
                break
            
            # Calculate threshold value
            threshold_decimal = (threshold_percentage / 100) - 0.0001
            max_allowed = total * threshold_decimal
            
            # Find entities exceeding threshold
            exceeded = result[result[metric] > max_allowed].copy()
            
            if len(exceeded) == 0:
                break
            
            # Adjust exceeded entities
            for idx in exceeded.index:
                original_value = result.loc[idx, metric]
                result.loc[idx, metric] = max_allowed
                result.loc[idx, 'adjustment_factor'] = max_allowed / original_value
            
            iteration += 1
        
        if iteration > 0:
            logger.info(f"Applied weighting in {iteration} iterations, "
                       f"adjusted {len(result[result['adjustment_factor'] < 1.0])} entities")
        
        return result
    
    def get_rule_description(self) -> str:
        """Get human-readable description of current rule."""
        rules = self.get_rules()
        if self.rule_name in rules:
            rule = rules[self.rule_name]
            desc = f"Rule {self.rule_name}: "
            desc += f"Min {rule['min_entities']} entities, "
            desc += f"Max {rule['max_concentration']}% concentration"
            
            if 'additional' in rule:
                desc += " (with additional constraints)"
            
            return desc
        else:
            return (f"Custom rule: Min {self.min_participants} entities, "
                   f"Max {self.max_concentration}% concentration")
    
    def validate_fallback_rules(
        self,
        peer_group: pd.DataFrame,
        metrics: List[str],
        entity_column: str = 'entity_identifier'
    ) -> Tuple[Optional[str], bool, List[str]]:
        """
        Try fallback rules in order of permissiveness.
        
        Parameters:
        -----------
        peer_group : pd.DataFrame
            Peer group to validate
        metrics : List[str]
            Metrics to check
        entity_column : str
            Entity identifier column
            
        Returns:
        --------
        Tuple[Optional[str], bool, List[str]]
            (rule_name, is_compliant, warnings)
        """
        # Try rules in order: 5/25, 6/30, 7/35, 10/40
        rule_order = ['5/25', '6/30', '7/35', '10/40']
        
        for rule_name in rule_order:
            # Create temporary validator with this rule
            temp_validator = PrivacyValidator(
                rule_name=rule_name,
                protected_entities=self.protected_entities,
                protected_max_concentration=self.protected_max_concentration
            )
            
            is_compliant, warnings = temp_validator.validate_peer_group(
                peer_group, metrics, entity_column
            )
            
            if is_compliant:
                logger.info(f"Fallback successful with rule {rule_name}")
                return rule_name, is_compliant, warnings
        
        logger.warning("All fallback rules failed")
        return None, False, ["All privacy rules failed validation"]
