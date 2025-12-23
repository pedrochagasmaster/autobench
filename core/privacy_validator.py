"""
PrivacyValidator - Privacy compliance validation for peer groups.

Implements multiple privacy rules (5/25, 6/30, 7/35, 10/40, 4/35) and
validates concentration limits for regulatory compliance.

Rule Specifications:
-------------------
- 5/25: Min 5 participants, max 25% per participant
  Example: [25, 25, 25, 24, 1]

- 6/30: Min 6 participants, max 30% per participant, at least 3 participants ≥ 7%
  Example: [30, 24.5, 24.5, 7, 7, 7] or [30, 30, 30, 3.33, 3.33, 3.33]

- 7/35: Min 7 participants, max 35% per participant, at least 2 ≥ 15%, 
        and at least 1 additional participant ≥ 8%
  Example: [35, 15, 15, 8.75, 8.75, 8.75, 8.75]

- 10/40: Min 10 participants, max 40% per participant, at least 2 ≥ 20%, 
         and at least 1 additional participant ≥ 10%
  Example: [40, 20, 20, 10, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6]

- 4/35 (Merchant benchmarking only): Min 4 participants, max 35% per participant
"""

import pandas as pd
import numpy as np
from typing import List, Tuple, Optional, Dict
import logging

logger = logging.getLogger(__name__)


class PrivacyValidator:
    """
    Validates peer groups against privacy concentration rules.
    
    Supports multiple privacy rules with maximum concentration limits
    and minimum percentage requirements:
    
    - 5/25: 5 minimum entities, 25% max concentration
      Compliant example: [25, 25, 25, 24, 1]
      
    - 6/30: 6 minimum entities, 30% max concentration
      + At least 3 participants must be ≥ 7%
      Compliant examples: [30, 24.5, 24.5, 7, 7, 7] or [30, 30, 30, 3.33, 3.33, 3.33]
      
    - 7/35: 7 minimum entities, 35% max concentration
      + At least 2 participants must be ≥ 15%
      + At least 1 additional participant must be ≥ 8%
      Compliant example: [35, 15, 15, 8.75, 8.75, 8.75, 8.75]
      
    - 10/40: 10 minimum entities, 40% max concentration
      + At least 2 participants must be ≥ 20%
      + At least 1 additional participant must be ≥ 10%
      Compliant example: [40, 20, 20, 10, 1.6, 1.6, 1.6, 1.6, 1.6, 1.6]
      
    - 4/35: 4 minimum entities, 35% max concentration (merchant benchmarking only)
    """
    
    RULES = {
        # 5/25: No participant may exceed 25%
        '5/25': {
            'min_entities': 5, 
            'max_concentration': 25.0
        },
        # 6/30: No participant may exceed 30%, at least 3 participants must be ≥ 7%
        '6/30': {
            'min_entities': 6, 
            'max_concentration': 30.0,
            'additional': {'min_count_above_threshold': (3, 7.0)}
        },
        # 7/35: No participant may exceed 35%, at least 2 ≥ 15%, at least 1 additional ≥ 8%
        '7/35': {
            'min_entities': 7, 
            'max_concentration': 35.0,
            'additional': {'min_count_15': 2, 'min_count_8': 1}
        },
        # 10/40: No participant may exceed 40%, at least 2 ≥ 20%, at least 1 additional ≥ 10%
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
    
    def __init__(
        self,
        min_participants: int = 5,
        max_concentration: float = 25.0,
        rule_name: Optional[str] = None,
        protected_entities: Optional[List[str]] = None,
        protected_max_concentration: float = 25.0
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
        protected_max_concentration : float
            Maximum concentration for protected entities
        """
        if rule_name and rule_name in self.RULES:
            rule = self.RULES[rule_name]
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
        self.protected_max_concentration = protected_max_concentration
        
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
        warnings = []
        is_compliant = True
        
        # Check minimum participants
        num_entities = len(peer_group)
        if num_entities < self.min_participants:
            warnings.append(
                f"Insufficient entities: {num_entities} < {self.min_participants}"
            )
            is_compliant = False
            return is_compliant, warnings
        
        # Check concentration for each metric
        for metric in metrics:
            if metric not in peer_group.columns:
                warnings.append(f"Metric '{metric}' not found in data")
                continue
            
            # Calculate total
            total = peer_group[metric].sum()
            
            if total == 0:
                warnings.append(f"Total for metric '{metric}' is zero")
                continue
            
            # Calculate concentration percentages
            peer_group_copy = peer_group.copy()
            peer_group_copy['concentration'] = (peer_group_copy[metric] / total) * 100
            
            # Check each entity's concentration
            for idx, row in peer_group_copy.iterrows():
                entity_name = row[entity_column]
                concentration = row['concentration']
                
                # Apply protected entity limit if applicable
                if entity_name in self.protected_entities:
                    if concentration > self.protected_max_concentration:
                        warnings.append(
                            f"Protected entity '{entity_name}' exceeds {self.protected_max_concentration}% "
                            f"for '{metric}': {concentration:.2f}%"
                        )
                        is_compliant = False
                # Apply standard limit
                elif concentration > self.max_concentration:
                    warnings.append(
                        f"Entity '{entity_name}' exceeds {self.max_concentration}% "
                        f"for '{metric}': {concentration:.2f}%"
                    )
                    is_compliant = False
            
            # Check additional constraints based on rule
            if self.additional_constraints:
                constraint_check, constraint_warnings = self._check_additional_constraints(
                    peer_group_copy, metric, entity_column
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
        
        # Rule 6/30: At least 3 entities ≥ 7%
        if 'min_count_above_threshold' in self.additional_constraints:
            min_count, threshold = self.additional_constraints['min_count_above_threshold']
            count_above = (peer_group['concentration'] >= threshold).sum()
            
            if count_above < min_count:
                warnings.append(
                    f"Rule 6/30: Need {min_count} entities ≥ {threshold}%, found {count_above}"
                )
                constraints_met = False
        
        # Rule 7/35: At least 2 entities ≥ 15% AND 1 entity ≥ 8%
        if 'min_count_15' in self.additional_constraints:
            count_15 = (peer_group['concentration'] >= 15.0).sum()
            count_8 = (peer_group['concentration'] >= 8.0).sum()
            
            if count_15 < self.additional_constraints['min_count_15']:
                warnings.append(
                    f"Rule 7/35: Need {self.additional_constraints['min_count_15']} "
                    f"entities ≥ 15%, found {count_15}"
                )
                constraints_met = False
            
            if count_8 < (self.additional_constraints['min_count_15'] + 
                         self.additional_constraints.get('min_count_8', 0)):
                warnings.append(
                    f"Rule 7/35: Additional entity ≥ 8% requirement not met"
                )
                constraints_met = False
        
        # Rule 10/40: At least 2 entities ≥ 20% AND 1 entity ≥ 10%
        if 'min_count_20' in self.additional_constraints:
            count_20 = (peer_group['concentration'] >= 20.0).sum()
            count_10 = (peer_group['concentration'] >= 10.0).sum()
            
            if count_20 < self.additional_constraints['min_count_20']:
                warnings.append(
                    f"Rule 10/40: Need {self.additional_constraints['min_count_20']} "
                    f"entities ≥ 20%, found {count_20}"
                )
                constraints_met = False
            
            if count_10 < (self.additional_constraints['min_count_20'] + 
                          self.additional_constraints.get('min_count_10', 0)):
                warnings.append(
                    f"Rule 10/40: Additional entity ≥ 10% requirement not met"
                )
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
        if self.rule_name in self.RULES:
            rule = self.RULES[self.rule_name]
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
