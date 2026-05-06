"""Configuration validation and schema definitions.

This module provides configuration file validation against the v3.0 schema.
"""

import logging
from typing import Dict, Any, List, Optional
from pathlib import Path
from core.compliance import VALID_COMPLIANCE_POSTURES

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

logger = logging.getLogger(__name__)

CONFIG_SCHEMA_VERSION = "3.0"


class ConfigValidationError(Exception):
    """Raised when configuration validation fails."""
    pass


class ConfigValidator:
    """Validates configuration files against schema."""
    
    REQUIRED_FIELDS = {
        'version': str,
        'compliance_posture': str,
    }
    
    OPTIONAL_FIELDS = {
        'preset_name': str,
        'description': str,
        'input': dict,
        'output': dict,
        'optimization': dict,
        'analysis': dict,
        'column_mappings': dict,
        'advanced': dict,
    }
    
    VALID_ALGORITHMS = ['linear_programming', 'bayesian', 'hybrid']
    VALID_STRATEGIES = ['greedy', 'random', 'exhaustive']
    VALID_CONSISTENCY_MODES = ['global', 'per_dimension', 'adaptive']
    VALID_LOG_LEVELS = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
    
    @classmethod
    def validate(cls, config: Dict[str, Any]) -> List[str]:
        """Validate configuration and return list of errors.
        
        Args:
            config: Configuration dictionary to validate
            
        Returns:
            List of error messages (empty if valid)
        """
        errors = []
        
        # Check version
        if 'version' not in config:
            errors.append("Missing required field: version")
        elif not isinstance(config['version'], str):
            errors.append(f"Invalid type for version: expected str, got {type(config['version']).__name__}")
        elif config['version'] != CONFIG_SCHEMA_VERSION:
            errors.append(f"Unsupported config version: {config['version']} (expected {CONFIG_SCHEMA_VERSION})")

        if 'compliance_posture' not in config:
            errors.append("Missing required field: compliance_posture")
        elif not isinstance(config['compliance_posture'], str):
            errors.append("Invalid type for compliance_posture: expected str")
        elif config['compliance_posture'] not in VALID_COMPLIANCE_POSTURES:
            errors.append(
                "compliance_posture must be one of: "
                + ", ".join(VALID_COMPLIANCE_POSTURES)
            )
        
        # Validate structure - check for unknown fields at root level
        known_fields = set(cls.REQUIRED_FIELDS.keys()) | set(cls.OPTIONAL_FIELDS.keys())
        unknown_fields = set(config.keys()) - known_fields
        if unknown_fields:
            errors.append(f"Unknown configuration fields: {', '.join(unknown_fields)}")
        
        # Validate optional sections if present
        if 'input' in config:
            errors.extend(cls._validate_input(config['input']))
        
        if 'output' in config:
            errors.extend(cls._validate_output(config['output']))
        
        if 'optimization' in config:
            errors.extend(cls._validate_optimization(config['optimization']))
        
        if 'analysis' in config:
            errors.extend(cls._validate_analysis(config['analysis']))
        
        if 'column_mappings' in config:
            errors.extend(cls._validate_column_mappings(config['column_mappings']))
        
        return errors
    
    @classmethod
    def _validate_input(cls, input_config: Dict[str, Any]) -> List[str]:
        """Validate input settings."""
        errors = []
        
        if not isinstance(input_config, dict):
            errors.append("input must be a dictionary")
            return errors
        
        if 'entity_col' in input_config and not isinstance(input_config['entity_col'], str):
            errors.append("input.entity_col must be a string")
        
        if 'time_col' in input_config:
            time_col = input_config['time_col']
            if time_col is not None and not isinstance(time_col, str):
                errors.append("input.time_col must be a string or null")

        if 'schema_detection_mode' in input_config:
            mode = input_config['schema_detection_mode']
            valid_modes = ['heuristic', 'mapped', 'hybrid']
            if not isinstance(mode, str) or mode not in valid_modes:
                errors.append(f"input.schema_detection_mode must be one of: {', '.join(valid_modes)}")

        if 'max_csv_size_mb' in input_config:
            value = input_config['max_csv_size_mb']
            if value is not None and (not isinstance(value, (int, float)) or value <= 0):
                errors.append("input.max_csv_size_mb must be a positive number or null")

        for field in ['max_csv_rows', 'csv_chunk_size']:
            if field in input_config:
                value = input_config[field]
                if value is not None and (not isinstance(value, int) or value <= 0):
                    errors.append(f"input.{field} must be a positive integer or null")
        
        return errors
    
    @classmethod
    def _validate_output(cls, output_config: Dict[str, Any]) -> List[str]:
        """Validate output settings."""
        errors = []
        
        if not isinstance(output_config, dict):
            errors.append("output must be a dictionary")
            return errors
        
        if 'format' in output_config and output_config['format'] not in ['xlsx', 'csv', 'json']:
            errors.append("output.format must be one of: xlsx, csv, json")
        
        if 'log_level' in output_config and output_config['log_level'] not in cls.VALID_LOG_LEVELS:
            errors.append(f"output.log_level must be one of: {', '.join(cls.VALID_LOG_LEVELS)}")
        
        for bool_field in [
            'include_debug_sheets',
            'include_privacy_validation',
            'include_impact_summary',
            'include_preset_comparison',
            'include_calculated_metrics',
            'include_audit_log',
        ]:
            if bool_field in output_config and not isinstance(output_config[bool_field], bool):
                errors.append(f"output.{bool_field} must be a boolean")

        if 'impact_thresholds' in output_config:
            thresholds = output_config['impact_thresholds']
            if not isinstance(thresholds, dict):
                errors.append("output.impact_thresholds must be a dictionary")
            else:
                for key in ['high_pp', 'low_pp']:
                    if key in thresholds and not isinstance(thresholds[key], (int, float)):
                        errors.append(f"output.impact_thresholds.{key} must be a number")

        if 'distortion_thresholds' in output_config:
            thresholds = output_config['distortion_thresholds']
            if not isinstance(thresholds, dict):
                errors.append("output.distortion_thresholds must be a dictionary")
            else:
                for key in ['high_distortion_pp', 'low_distortion_pp']:
                    if key in thresholds and not isinstance(thresholds[key], (int, float)):
                        errors.append(f"output.distortion_thresholds.{key} must be a number")
        
        return errors
    
    @classmethod
    def _validate_optimization(cls, opt_config: Dict[str, Any]) -> List[str]:
        """Validate optimization settings."""
        errors = []
        
        if not isinstance(opt_config, dict):
            errors.append("optimization must be a dictionary")
            return errors
        
        # Validate algorithm
        if 'algorithm' in opt_config and opt_config['algorithm'] not in cls.VALID_ALGORITHMS:
            errors.append(f"optimization.algorithm must be one of: {', '.join(cls.VALID_ALGORITHMS)}")
        
        # Validate LP settings
        if 'linear_programming' in opt_config:
            lp = opt_config['linear_programming']
            if not isinstance(lp, dict):
                errors.append("optimization.linear_programming must be a dictionary")
            else:
                if 'max_iterations' in lp:
                    if not isinstance(lp['max_iterations'], int) or lp['max_iterations'] <= 0:
                        errors.append("optimization.linear_programming.max_iterations must be a positive integer")
                
                if 'tolerance' in lp:
                    if not isinstance(lp['tolerance'], (int, float)) or lp['tolerance'] < 0:
                        errors.append("optimization.linear_programming.tolerance must be >= 0")
                
                if 'rank_penalty_weight' in lp:
                    if not isinstance(lp['rank_penalty_weight'], (int, float)) or lp['rank_penalty_weight'] < 0:
                        errors.append("optimization.linear_programming.rank_penalty_weight must be >= 0")

                if 'lambda_penalty' in lp:
                    val = lp['lambda_penalty']
                    if val is not None and (not isinstance(val, (int, float)) or val < 0):
                        errors.append("optimization.linear_programming.lambda_penalty must be a non-negative number or null")

                if 'volume_weighted_penalties' in lp and not isinstance(lp['volume_weighted_penalties'], bool):
                    errors.append("optimization.linear_programming.volume_weighted_penalties must be a boolean")

                if 'volume_weighting_exponent' in lp:
                    val = lp['volume_weighting_exponent']
                    if not isinstance(val, (int, float)) or val < 0:
                        errors.append("optimization.linear_programming.volume_weighting_exponent must be >= 0")

                known_lp_keys = {
                    'max_iterations',
                    'tolerance',
                    'rank_penalty_weight',
                    'rank_constraints',
                    'lambda_penalty',
                    'volume_weighted_penalties',
                    'volume_weighting_exponent',
                }
                unknown_lp = set(lp.keys()) - known_lp_keys
                if unknown_lp:
                    errors.append(
                        "optimization.linear_programming has unknown fields: "
                        + ", ".join(sorted(unknown_lp))
                    )

                if 'rank_constraints' in lp:
                    rc = lp['rank_constraints']
                    if not isinstance(rc, dict):
                        errors.append("optimization.linear_programming.rank_constraints must be a dictionary")
                    else:
                        mode = rc.get('mode')
                        if mode is not None and mode not in ['all', 'neighbor']:
                            errors.append("optimization.linear_programming.rank_constraints.mode must be 'all' or 'neighbor'")
                        if 'neighbor_k' in rc:
                            if not isinstance(rc['neighbor_k'], int) or rc['neighbor_k'] <= 0:
                                errors.append("optimization.linear_programming.rank_constraints.neighbor_k must be a positive integer")
        
        # Validate bounds
        if 'bounds' in opt_config:
            bounds = opt_config['bounds']
            if not isinstance(bounds, dict):
                errors.append("optimization.bounds must be a dictionary")
            else:
                if 'max_weight' in bounds:
                    if not isinstance(bounds['max_weight'], (int, float)) or bounds['max_weight'] <= 0:
                        errors.append("optimization.bounds.max_weight must be > 0")
                
                if 'min_weight' in bounds:
                    if not isinstance(bounds['min_weight'], (int, float)) or bounds['min_weight'] <= 0:
                        errors.append("optimization.bounds.min_weight must be > 0")
                
                # Check that min < max
                if 'min_weight' in bounds and 'max_weight' in bounds:
                    if bounds['min_weight'] >= bounds['max_weight']:
                        errors.append("optimization.bounds.min_weight must be < max_weight")
        
        # Validate constraints
        if 'constraints' in opt_config:
            constraints = opt_config['constraints']
            if not isinstance(constraints, dict):
                errors.append("optimization.constraints must be a dictionary")
            else:
                if 'volume_preservation' in constraints:
                    vp = constraints['volume_preservation']
                    if not isinstance(vp, (int, float)) or vp < 0 or vp > 1:
                        errors.append("optimization.constraints.volume_preservation must be between 0.0 and 1.0")
                
                if 'consistency_mode' in constraints:
                    mode = constraints['consistency_mode']
                    if mode not in cls.VALID_CONSISTENCY_MODES:
                        errors.append(f"optimization.constraints.consistency_mode must be one of: {', '.join(cls.VALID_CONSISTENCY_MODES)}")

                if 'enforce_additional_constraints' in constraints:
                    if not isinstance(constraints['enforce_additional_constraints'], bool):
                        errors.append("optimization.constraints.enforce_additional_constraints must be a boolean")

                if 'enforce_single_weight_set' in constraints:
                    if not isinstance(constraints['enforce_single_weight_set'], bool):
                        errors.append("optimization.constraints.enforce_single_weight_set must be a boolean")

                if 'dynamic_constraints' in constraints:
                    dyn = constraints['dynamic_constraints']
                    if not isinstance(dyn, dict):
                        errors.append("optimization.constraints.dynamic_constraints must be a dictionary")
                    else:
                        if 'enabled' in dyn and not isinstance(dyn['enabled'], bool):
                            errors.append("optimization.constraints.dynamic_constraints.enabled must be a boolean")
                        int_fields = ['min_peer_count']
                        for field in int_fields:
                            if field in dyn and (not isinstance(dyn[field], int) or dyn[field] < 0):
                                errors.append(f"optimization.constraints.dynamic_constraints.{field} must be a non-negative integer")
                        float_fields = [
                            'min_effective_peer_count',
                            'min_category_volume_share',
                            'min_overall_volume_share',
                            'min_representativeness',
                            'threshold_scale_floor',
                            'count_scale_floor',
                            'penalty_floor',
                            'penalty_power',
                        ]
                        for field in float_fields:
                            if field in dyn and (not isinstance(dyn[field], (int, float)) or dyn[field] < 0):
                                errors.append(f"optimization.constraints.dynamic_constraints.{field} must be >= 0")
        
        # Validate subset search
        if 'subset_search' in opt_config:
            ss = opt_config['subset_search']
            if not isinstance(ss, dict):
                errors.append("optimization.subset_search must be a dictionary")
            else:
                if 'enabled' in ss and not isinstance(ss['enabled'], bool):
                    errors.append("optimization.subset_search.enabled must be a boolean")

                if 'strategy' in ss and ss['strategy'] not in cls.VALID_STRATEGIES:
                    errors.append(f"optimization.subset_search.strategy must be one of: {', '.join(cls.VALID_STRATEGIES)}")

                # ``max_tests`` is a documented legacy alias for ``max_attempts``.
                # It is normalised in ConfigManager._merge_config but accepted here so
                # that loading shipped presets via ``--config`` does not fail.
                attempts_value = ss.get('max_attempts', ss.get('max_tests'))
                if attempts_value is not None:
                    if not isinstance(attempts_value, int) or attempts_value <= 0:
                        errors.append(
                            "optimization.subset_search.max_attempts must be a positive integer"
                        )

                if 'max_slack_threshold' in ss:
                    if not isinstance(ss['max_slack_threshold'], (int, float)) or ss['max_slack_threshold'] < 0:
                        errors.append("optimization.subset_search.max_slack_threshold must be >= 0")

                for bool_field in ['trigger_on_slack', 'prefer_slacks_first']:
                    if bool_field in ss and not isinstance(ss[bool_field], bool):
                        errors.append(f"optimization.subset_search.{bool_field} must be a boolean")

                known_ss_keys = {
                    'enabled',
                    'strategy',
                    'max_attempts',
                    'max_tests',
                    'max_slack_threshold',
                    'trigger_on_slack',
                    'prefer_slacks_first',
                }
                unknown_ss = set(ss.keys()) - known_ss_keys
                if unknown_ss:
                    errors.append(
                        "optimization.subset_search has unknown fields: "
                        + ", ".join(sorted(unknown_ss))
                    )
        
        # Validate Bayesian settings
        if 'bayesian' in opt_config:
            bayesian = opt_config['bayesian']
            if not isinstance(bayesian, dict):
                errors.append("optimization.bayesian must be a dictionary")
            else:
                if 'max_iterations' in bayesian:
                    if not isinstance(bayesian['max_iterations'], int) or bayesian['max_iterations'] <= 0:
                        errors.append("optimization.bayesian.max_iterations must be a positive integer")
                
                if 'learning_rate' in bayesian:
                    if not isinstance(bayesian['learning_rate'], (int, float)) or bayesian['learning_rate'] <= 0:
                        errors.append("optimization.bayesian.learning_rate must be > 0")

                if 'violation_penalty_weight' in bayesian:
                    val = bayesian['violation_penalty_weight']
                    if not isinstance(val, (int, float)) or val <= 0:
                        errors.append("optimization.bayesian.violation_penalty_weight must be > 0")
        
        return errors
    
    @classmethod
    def _validate_analysis(cls, analysis_config: Dict[str, Any]) -> List[str]:
        """Validate analysis settings."""
        errors = []
        
        if not isinstance(analysis_config, dict):
            errors.append("analysis must be a dictionary")
            return errors
        
        for percentile_field in ['best_in_class_percentile', 'fraud_percentile']:
            if percentile_field in analysis_config:
                val = analysis_config[percentile_field]
                if not isinstance(val, (int, float)) or val < 0 or val > 1:
                    errors.append(f"analysis.{percentile_field} must be between 0.0 and 1.0")
        
        if 'auto_detect_dimensions' in analysis_config:
            if not isinstance(analysis_config['auto_detect_dimensions'], bool):
                errors.append("analysis.auto_detect_dimensions must be a boolean")
        
        if 'merchant_mode' in analysis_config:
            if not isinstance(analysis_config['merchant_mode'], bool):
                errors.append("analysis.merchant_mode must be a boolean")
        
        return errors
    
    @classmethod
    def _validate_column_mappings(cls, mappings: Dict[str, Any]) -> List[str]:
        """Validate column mappings."""
        errors = []
        
        if not isinstance(mappings, dict):
            errors.append("column_mappings must be a dictionary")
            return errors
        
        for key, value in mappings.items():
            if not isinstance(key, str):
                errors.append(f"column_mappings keys must be strings, got {type(key).__name__}")
            if not isinstance(value, str):
                errors.append(f"column_mappings[{key}] must be a string, got {type(value).__name__}")
        
        return errors


def load_config(path: Path) -> Dict[str, Any]:
    """Load and validate configuration file.
    
    Args:
        path: Path to configuration file (YAML or JSON)
        
    Returns:
        Configuration dictionary
        
    Raises:
        ConfigValidationError: If configuration is invalid
        FileNotFoundError: If file doesn't exist
        ImportError: If YAML library not available
    """
    if not YAML_AVAILABLE:
        raise ImportError("PyYAML is required to load configuration files. Install with: pip install pyyaml")
    
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path}")
    
    # Load file
    with open(path, 'r') as f:
        try:
            config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ConfigValidationError(f"Invalid YAML syntax: {e}")
    
    if config is None:
        raise ConfigValidationError("Configuration file is empty")
    
    if not isinstance(config, dict):
        raise ConfigValidationError("Configuration must be a dictionary at root level")
    
    # Validate
    errors = ConfigValidator.validate(config)
    if errors:
        error_msg = "Configuration validation failed:\n  " + "\n  ".join(errors)
        raise ConfigValidationError(error_msg)
    
    logger.info(f"Configuration loaded and validated: {path}")
    return config


def validate_config_file(path: Path) -> tuple[bool, List[str]]:
    """Validate a configuration file and return results.
    
    Args:
        path: Path to configuration file
        
    Returns:
        Tuple of (is_valid, error_list)
    """
    try:
        load_config(path)
        return True, []
    except ConfigValidationError as e:
        return False, [str(e)]
    except Exception as e:
        return False, [f"Error loading configuration: {e}"]
