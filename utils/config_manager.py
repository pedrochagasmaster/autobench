"""
ConfigManager - Configuration management for benchmarking tool.

Handles configuration loading, column mappings, and preset management.
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List

try:
    import yaml
except ImportError:  # pragma: no cover - validators already handle this path
    yaml = None

from core.compliance import VALID_COMPLIANCE_POSTURES
from core.control3_policy import Control3PolicyEvidence

logger = logging.getLogger(__name__)


@dataclass
class BoundsConfig:
    max_weight: float = 10.0
    min_weight: float = 0.01


@dataclass
class LinearProgrammingConfig:
    max_iterations: int = 1000
    tolerance: float = 1.0
    rank_penalty_weight: float = 1.0
    rank_constraints: Dict[str, Any] = field(default_factory=lambda: {"mode": "all", "neighbor_k": 1})
    volume_weighted_penalties: bool = False
    volume_weighting_exponent: float = 1.0
    lambda_penalty: Optional[float] = None


@dataclass
class SubsetSearchConfig:
    enabled: bool = True
    strategy: str = "greedy"
    max_attempts: int = 200
    trigger_on_slack: bool = True
    max_slack_threshold: float = 0.0
    prefer_slacks_first: bool = False


@dataclass
class ConstraintsConfig:
    volume_preservation: float = 0.5
    consistency_mode: str = "global"
    enforce_single_weight_set: bool = False
    enforce_additional_constraints: bool = True
    dynamic_constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BayesianConfig:
    max_iterations: int = 500
    learning_rate: float = 0.01
    violation_penalty_weight: float = 1000.0


@dataclass
class AnalysisConfig:
    best_in_class_percentile: float = 0.85
    fraud_percentile: float = 0.15
    auto_detect_dimensions: bool = False
    merchant_mode: bool = False


@dataclass
class OutputConfig:
    format: str = "xlsx"
    output_format: str = "analysis"
    include_debug_sheets: bool = True
    include_privacy_validation: bool = True
    include_impact_summary: bool = True
    include_preset_comparison: bool = False
    include_calculated_metrics: bool = False
    include_audit_log: bool = True
    fraud_in_bps: bool = True
    log_level: str = "INFO"
    impact_thresholds: Dict[str, Any] = field(default_factory=dict)
    distortion_thresholds: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedConfig:
    """Typed view of merged configuration for analysis orchestration."""

    bounds: BoundsConfig = field(default_factory=BoundsConfig)
    linear_programming: LinearProgrammingConfig = field(default_factory=LinearProgrammingConfig)
    subset_search: SubsetSearchConfig = field(default_factory=SubsetSearchConfig)
    constraints: ConstraintsConfig = field(default_factory=ConstraintsConfig)
    bayesian: BayesianConfig = field(default_factory=BayesianConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    control3: Control3PolicyEvidence = field(default_factory=Control3PolicyEvidence)
    compliance_posture: str = "strict"

    @classmethod
    def from_merged_config(cls, config: Dict[str, Any]) -> "ResolvedConfig":
        """Build a typed config object from a merged ConfigManager dict."""
        opt = config.get("optimization", {}) or {}
        lp = opt.get("linear_programming", {}) or {}
        bounds = opt.get("bounds", {}) or {}
        subset = opt.get("subset_search", {}) or {}
        constraints = opt.get("constraints", {}) or {}
        bayesian = opt.get("bayesian", {}) or {}
        analysis = config.get("analysis", {}) or {}
        output = config.get("output", {}) or {}
        control3 = config.get("control3", {}) or {}

        max_attempts = subset.get("max_attempts", subset.get("max_tests", 200))
        include_impact_summary = output.get("include_impact_summary")
        if include_impact_summary is None:
            include_impact_summary = output.get("include_distortion_summary", True)

        return cls(
            bounds=BoundsConfig(
                max_weight=float(bounds.get("max_weight", 10.0)),
                min_weight=float(bounds.get("min_weight", 0.01)),
            ),
            linear_programming=LinearProgrammingConfig(
                max_iterations=int(lp.get("max_iterations", 1000)),
                tolerance=float(lp.get("tolerance", 1.0)),
                rank_penalty_weight=float(lp.get("rank_penalty_weight", 1.0)),
                rank_constraints=dict(lp.get("rank_constraints", {"mode": "all", "neighbor_k": 1})),
                volume_weighted_penalties=bool(lp.get("volume_weighted_penalties", False)),
                volume_weighting_exponent=float(lp.get("volume_weighting_exponent", 1.0)),
                lambda_penalty=lp.get("lambda_penalty"),
            ),
            subset_search=SubsetSearchConfig(
                enabled=bool(subset.get("enabled", True)),
                strategy=str(subset.get("strategy", "greedy")),
                max_attempts=int(max_attempts),
                trigger_on_slack=bool(subset.get("trigger_on_slack", True)),
                max_slack_threshold=float(subset.get("max_slack_threshold", 0.0)),
                prefer_slacks_first=bool(subset.get("prefer_slacks_first", False)),
            ),
            constraints=ConstraintsConfig(
                volume_preservation=float(constraints.get("volume_preservation", 0.5)),
                consistency_mode=str(constraints.get("consistency_mode", "global")),
                enforce_single_weight_set=bool(constraints.get("enforce_single_weight_set", False)),
                enforce_additional_constraints=bool(constraints.get("enforce_additional_constraints", True)),
                dynamic_constraints=dict(constraints.get("dynamic_constraints", {}) or {}),
            ),
            bayesian=BayesianConfig(
                max_iterations=int(bayesian.get("max_iterations", 500)),
                learning_rate=float(bayesian.get("learning_rate", 0.01)),
                violation_penalty_weight=float(bayesian.get("violation_penalty_weight", 1000.0)),
            ),
            analysis=AnalysisConfig(
                best_in_class_percentile=float(analysis.get("best_in_class_percentile", 0.85)),
                fraud_percentile=float(analysis.get("fraud_percentile", 0.15)),
                auto_detect_dimensions=bool(analysis.get("auto_detect_dimensions", False)),
                merchant_mode=bool(analysis.get("merchant_mode", False)),
            ),
            output=OutputConfig(
                format=str(output.get("format", "xlsx")),
                output_format=str(output.get("output_format", "analysis")),
                include_debug_sheets=bool(output.get("include_debug_sheets", True)),
                include_privacy_validation=bool(output.get("include_privacy_validation", True)),
                include_impact_summary=bool(include_impact_summary),
                include_preset_comparison=bool(output.get("include_preset_comparison", False)),
                include_calculated_metrics=bool(output.get("include_calculated_metrics", False)),
                include_audit_log=bool(output.get("include_audit_log", True)),
                fraud_in_bps=bool(output.get("fraud_in_bps", True)),
                log_level=str(output.get("log_level", "INFO")),
                impact_thresholds=dict(output.get("impact_thresholds", {}) or {}),
                distortion_thresholds=dict(output.get("distortion_thresholds", {}) or {}),
            ),
            control3=Control3PolicyEvidence.from_mapping(control3),
            compliance_posture=str(config.get("compliance_posture", "strict")),
        )


class ConfigManager:
    """
    Manages configuration for benchmark analysis.
    
    Handles:
    - Column mappings
    - Privacy rule configurations
    - Comparison metrics
    - SQL connection settings
    """
    
    DEFAULT_COLUMN_MAPPING = {
        # Entity identifiers
        'issuer_name': 'entity_identifier',
        'merchant_id': 'entity_identifier',
        'merchant_name': 'entity_identifier',
        'bank_name': 'entity_identifier',
        'institution_name': 'entity_identifier',
        
        # Transaction counts
        'txn_count': 'transaction_count',
        'count': 'transaction_count',
        'cnt': 'transaction_count',
        
        # Transaction amounts
        'txn_amt': 'transaction_amount',
        'tpv': 'transaction_amount',
        'amount': 'transaction_amount',
        'volume': 'transaction_amount',
        
        # Approved transactions
        'appr_txns': 'approved_count',
        'approved_count': 'approved_count',
        'auth_approved': 'approved_count',
        'appr_count': 'approved_count',
        
        # Approved amounts
        'appr_amount': 'approved_amount',
        'approved_amt': 'approved_amount',
        'auth_approved_amt': 'approved_amount',
        
        # Total transactions
        'total_txns': 'total_count',
        'auth_total': 'total_count',
        'total_count': 'total_count',
        
        # Total amounts
        'total_amount': 'total_amount',
        'auth_total_amt': 'total_amount',
        'total_amt': 'total_amount',
        
        # Fraud transactions
        'fraud_cnt': 'fraud_count',
        'qt_fraud': 'fraud_count',
        'fraud_tran': 'fraud_count',
        
        # Fraud amounts
        'fraud_amt': 'fraud_amount',
        'amount_fraud': 'fraud_amount',
        'fraud_amt_usd': 'fraud_amount',
    }
    
    DEFAULT_COMPARISON_METRICS = {
        'rate': [
            'approved_count',
            'total_count',
            'fraud_count'
        ],
        'share': [
            'transaction_count'
        ],
        'volume': [
            'transaction_count',
            'transaction_amount'
        ]
    }
    
    def __init__(self, 
                 config_file: Optional[str] = None,
                 preset: Optional[str] = None,
                 cli_overrides: Optional[Dict[str, Any]] = None):
        """
        Initialize configuration manager with hierarchy support.
        
        Configuration hierarchy (lowest to highest priority):
        1. Defaults (hardcoded)
        2. Preset (if specified)
        3. Config file (if specified)
        4. CLI overrides (highest priority)
        
        Parameters:
        -----------
        config_file : str, optional
            Path to custom configuration file (YAML or JSON)
        preset : str, optional
            Preset name to load
        cli_overrides : dict, optional
            CLI argument overrides (highest priority)
        """
        # Start with defaults
        self.config = self._get_default_config()
        self.column_mapping = self.DEFAULT_COLUMN_MAPPING.copy()
        self.comparison_metrics = self.DEFAULT_COMPARISON_METRICS.copy()
        self.sql_config = {}
        self._preset_name = preset
        self._preset_declared_posture = None
        self._config_declared_posture = False
        self._cli_declared_posture = False
        self._material_overrides: List[str] = []
        
        # Apply preset if specified
        if preset:
            self._load_preset(preset)
        
        # Load custom config file if specified
        if config_file:
            self._config_declared_posture = self._file_declares_posture(config_file)
            self.load_config(config_file)
        
        # Apply CLI overrides (highest priority)
        if cli_overrides:
            self._cli_declared_posture = 'compliance_posture' in cli_overrides
            self._apply_cli_overrides(cli_overrides)

        self._apply_runtime_profiles()
        self._validate_compliance_posture()
        
        logger.info("Initialized ConfigManager")
        if preset:
            logger.info(f"Applied preset: {preset}")
        if config_file:
            logger.info(f"Loaded config: {config_file}")
    
    def load_config(self, config_file: str) -> None:
        """
        Load configuration from YAML or JSON file.
        
        Parameters:
        -----------
        config_file : str
            Path to configuration file (.yaml, .yml, or .json)
        """
        logger.info(f"Loading configuration from: {config_file}")
        
        path = Path(config_file)
        if not path.exists():
            logger.warning(f"Config file not found: {config_file}")
            return
        
        try:
            from .validators import load_config

            loaded_config = load_config(path)
            
            # Merge loaded config into current config
            self._merge_config(loaded_config)
            
            # Update column mapping if provided
            if 'column_mappings' in loaded_config:
                self.column_mapping.update(loaded_config['column_mappings'])
            
            # Update comparison metrics if provided
            if 'comparison_metrics' in loaded_config:
                self.comparison_metrics.update(loaded_config['comparison_metrics'])
            
            # Load SQL configuration
            if 'sql' in loaded_config:
                self.sql_config = loaded_config['sql']
            
            logger.info("Configuration loaded successfully")
            
        except Exception as e:
            logger.error(f"Failed to load configuration: {str(e)}")
            raise
    
    def load_column_mapping(self, mapping_file: str) -> None:
        """
        Load column mapping from JSON file.
        
        Parameters:
        -----------
        mapping_file : str
            Path to column mapping file
        """
        logger.info(f"Loading column mapping from: {mapping_file}")
        
        path = Path(mapping_file)
        if not path.exists():
            logger.warning(f"Mapping file not found: {mapping_file}")
            return
        
        try:
            with open(path, 'r') as f:
                mapping = json.load(f)
            
            self.column_mapping.update(mapping)
            logger.info(f"Loaded {len(mapping)} column mappings")
            
        except Exception as e:
            logger.error(f"Failed to load column mapping: {str(e)}")
            raise
    
    def get_column_mapping(self) -> Dict[str, str]:
        """
        Get current column mapping.
        
        Returns:
        --------
        Dict[str, str]
            Column name mapping dictionary
        """
        return self.column_mapping.copy()
    
    def get_comparison_metrics(self, analysis_dimensions: List[str]) -> Dict[str, List[str]]:
        """
        Get comparison metrics for analysis dimensions.
        
        Parameters:
        -----------
        analysis_dimensions : List[str]
            List of dimensions being analyzed
            
        Returns:
        --------
        Dict[str, List[str]]
            Comparison metrics by dimension
        """
        # Build metrics dictionary for each dimension
        metrics_by_dimension = {}
        
        for dimension in analysis_dimensions:
            # Use default metrics or custom if configured
            if dimension in self.config.get('dimension_metrics', {}):
                metrics_by_dimension[dimension] = self.config['dimension_metrics'][dimension]
            else:
                # Use rate metrics as default
                metrics_by_dimension[dimension] = self.comparison_metrics['rate']
        
        return metrics_by_dimension
    
    def get_evaluation_metrics(self, analysis_type: str) -> List[str]:
        """
        Get evaluation metrics for privacy validation.
        
        Parameters:
        -----------
        analysis_type : str
            Type of analysis ('rate', 'share', 'volume')
            
        Returns:
        --------
        List[str]
            List of metrics to evaluate
        """
        if analysis_type in self.comparison_metrics:
            return self.comparison_metrics[analysis_type]
        else:
            logger.warning(f"Unknown analysis type: {analysis_type}, using rate metrics")
            return self.comparison_metrics['rate']
    
    def get_sql_connection(self) -> Any:
        """
        Get SQL database connection.
        
        Returns:
        --------
        Connection object
        """
        if not self.sql_config:
            raise ValueError("SQL configuration not loaded")
        
        try:
            import pypyodbc
            
            connection_string = self.sql_config.get('connection_string')
            if connection_string:
                return pypyodbc.connect(connection_string)
            
            # Build connection string from components
            driver = self.sql_config.get('driver', 'SQL Server')
            server = self.sql_config.get('server')
            database = self.sql_config.get('database')
            uid = self.sql_config.get('uid')
            pwd = self.sql_config.get('pwd')
            
            conn_str = f"Driver={{{driver}}};Server={server};Database={database};"
            if uid:
                conn_str += f"UID={uid};PWD={pwd};"
            else:
                conn_str += "Trusted_Connection=yes;"
            
            return pypyodbc.connect(conn_str)
            
        except ImportError:
            logger.error("pypyodbc not installed. Install with: pip install pypyodbc")
            raise
        except Exception as e:
            logger.error(f"Failed to create SQL connection: {str(e)}")
            raise
    
    def save_config(self, output_file: str) -> None:
        """
        Save current configuration to file.
        
        Parameters:
        -----------
        output_file : str
            Path to save configuration
        """
        logger.info(f"Saving configuration to: {output_file}")
        
        config_data = {
            'column_mappings': self.column_mapping,
            'comparison_metrics': self.comparison_metrics,
            'sql': self.sql_config
        }
        
        with open(output_file, 'w') as f:
            json.dump(config_data, f, indent=2)
        
        logger.info("Configuration saved successfully")
    
    def get_preset_config(self, preset_name: str) -> Optional[Dict[str, Any]]:
        """
        Get preset configuration by name.
        
        Parameters:
        -----------
        preset_name : str
            Name of preset
            
        Returns:
        --------
        Dict or None
            Preset configuration
        """
        presets_file = Path(__file__).parent.parent / 'presets.json'
        
        if not presets_file.exists():
            logger.warning("presets.json not found")
            return None
        
        try:
            with open(presets_file, 'r') as f:
                presets = json.load(f).get('presets', {})
            
            return presets.get(preset_name)
            
        except Exception as e:
            logger.error(f"Failed to load preset: {str(e)}")
            return None
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration.
        
        Returns:
        --------
        Dict[str, Any]
            Default configuration dictionary
        """
        return {
            'version': '3.0',
            'compliance_posture': 'strict',
            'input': {
                'entity_col': 'issuer_name',
                'time_col': None,
                'schema_detection_mode': 'heuristic',
                'validate_input': True,
                'project_csv_columns': True,
                'max_csv_size_mb': None,
                'max_csv_rows': None,
                'csv_chunk_size': None,
                'validation_thresholds': {
                    'min_denominator': 100,
                    'min_peer_count': 5,
                    'max_rate_deviation': 50.0,
                    'min_rows_per_category': 3,
                    'max_null_percentage': 5.0,
                    'max_entity_concentration': 50.0,
                },
            },
            'output': {
                'format': 'xlsx',
                'output_format': 'analysis',  # 'analysis', 'publication', or 'both'
                'include_debug_sheets': True,
                'include_privacy_validation': True,
                'include_impact_summary': True,
                'include_preset_comparison': False,
                'include_calculated_metrics': False,
                'include_audit_log': True,
                'impact_thresholds': {
                    'high_pp': 1.0,
                    'low_pp': 0.25,
                },
                'distortion_thresholds': {
                    'high_distortion_pp': 1.0,
                    'low_distortion_pp': 0.25,
                },
                'fraud_in_bps': True,  # Convert fraud rates to basis points in publication
                'log_level': 'INFO',
            },
            'optimization': {
                'algorithm': 'linear_programming',
                'linear_programming': {
                'max_iterations': 1000,
                'tolerance': 1.0,
                'rank_penalty_weight': 1.0,
                'rank_constraints': {
                    'mode': 'all',
                    'neighbor_k': 1,
                },
            },
                'bounds': {
                    'max_weight': 10.0,
                    'min_weight': 0.01,
                },
                'constraints': {
                    'volume_preservation': 0.5,
                    'consistency_mode': 'global',
                    'enforce_single_weight_set': False,
                    'enforce_additional_constraints': True,
                    'dynamic_constraints': {
                        'enabled': False,
                        'min_peer_count': 4,
                        'min_effective_peer_count': 3.0,
                        'min_category_volume_share': 0.001,
                        'min_overall_volume_share': 0.0005,
                        'min_representativeness': 0.1,
                        'threshold_scale_floor': 0.6,
                        'count_scale_floor': 0.5,
                        'penalty_floor': 0.25,
                        'penalty_power': 1.0,
                    },
                },
                'subset_search': {
                    'enabled': True,
                    'strategy': 'greedy',
                    'max_attempts': 200,
                    'trigger_on_slack': True,
                    'max_slack_threshold': 0.0,
                    'prefer_slacks_first': False,
                },
                'bayesian': {
                    'max_iterations': 500,
                    'learning_rate': 0.01,
                    'violation_penalty_weight': 1000.0,
                },
            },
            'analysis': {
                'best_in_class_percentile': 0.85,
                'fraud_percentile': 0.15,
                'auto_detect_dimensions': False,
                'merchant_mode': False,
            },
            'control3': {
                'privacy_basis': None,
                'contains_digital_wallet_metrics': False,
                'digital_wallet_review_approved': False,
                'contains_top_merchant_output': False,
                'dual_entity_axis': False,
                'dual_entity_axis_review_approved': False,
                'recurring_deliverable': False,
                'last_privacy_recheck_date': None,
                'peer_group_altered': False,
            },
            'runtime': {
                'lean_mode': False,
            },
        }
    
    def _load_preset(self, preset_name: str) -> None:
        """Load preset configuration.
        
        Parameters:
        -----------
        preset_name : str
            Name of preset to load
        """
        try:
            from .preset_manager import PresetManager
            
            preset_mgr = PresetManager()
            preset_config = preset_mgr.get_preset(preset_name)
            
            if preset_config:
                self._preset_declared_posture = preset_config.get('compliance_posture')
                self._merge_config(preset_config)
                logger.info(f"Loaded preset: {preset_name}")
            else:
                available = preset_mgr.list_presets()
                if available:
                    raise ValueError(f"Preset '{preset_name}' not found. Available: {', '.join(available)}")
                else:
                    raise ValueError(f"Preset '{preset_name}' not found. No presets available.")
        except ImportError as e:
            logger.warning(f"Could not load preset manager: {e}")
        except Exception as e:
            logger.error(f"Failed to load preset '{preset_name}': {e}")
            raise
    
    def _merge_config(self, override: Dict[str, Any]) -> None:
        """Deep merge override config into current config.
        
        Parameters:
        -----------
        override : Dict[str, Any]
            Configuration to merge (higher priority)
        """
        def deep_merge(base, override):
            """Recursively merge override into base."""
            for key, value in override.items():
                if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                    deep_merge(base[key], value)
                else:
                    base[key] = value
        
        # Skip metadata fields that shouldn't merge
        metadata_fields = {'version', 'preset_name', 'description'}
        override_copy = {k: v for k, v in override.items() if k not in metadata_fields}
        
        deep_merge(self.config, override_copy)

        # Backward compatibility: subset_search.max_tests -> subset_search.max_attempts
        opt_cfg = self.config.get('optimization', {})
        if isinstance(opt_cfg, dict):
            subset_cfg = opt_cfg.get('subset_search', {})
            if isinstance(subset_cfg, dict):
                if 'max_attempts' not in subset_cfg and 'max_tests' in subset_cfg:
                    subset_cfg['max_attempts'] = subset_cfg.get('max_tests')

        # Backward compatibility: map legacy distortion keys to impact keys
        output_cfg = self.config.get('output', {})
        if isinstance(output_cfg, dict):
            if 'include_impact_summary' not in output_cfg and 'include_distortion_summary' in output_cfg:
                output_cfg['include_impact_summary'] = output_cfg.get('include_distortion_summary', False)
            if 'impact_thresholds' not in output_cfg and 'distortion_thresholds' in output_cfg:
                legacy = output_cfg.get('distortion_thresholds', {}) or {}
                output_cfg['impact_thresholds'] = {
                    'high_pp': legacy.get('high_distortion_pp', 1.0),
                    'low_pp': legacy.get('low_distortion_pp', 0.25),
                }
    
    def _apply_cli_overrides(self, overrides: Dict[str, Any]) -> None:
        """Apply CLI argument overrides.
        
        Parameters:
        -----------
        overrides : Dict[str, Any]
            CLI arguments to override config values
        """
        # Map CLI args to config paths
        mapping = {
            'entity_col': ('input', 'entity_col'),
            'time_col': ('input', 'time_col'),
            'debug': ('output', 'include_debug_sheets'),
            'log_level': ('output', 'log_level'),
            'per_dimension_weights': ('optimization', 'constraints', 'consistency_mode'),
            'max_iterations': ('optimization', 'linear_programming', 'max_iterations'),
            'tolerance': ('optimization', 'linear_programming', 'tolerance'),
            'max_weight': ('optimization', 'bounds', 'max_weight'),
            'min_weight': ('optimization', 'bounds', 'min_weight'),
            'volume_preservation': ('optimization', 'constraints', 'volume_preservation'),
            'bic_percentile': ('analysis', 'best_in_class_percentile'),
            'auto': ('analysis', 'auto_detect_dimensions'),
            'auto_subset_search': ('optimization', 'subset_search', 'enabled'),
            'subset_search_max_tests': ('optimization', 'subset_search', 'max_attempts'),
            'trigger_subset_on_slack': ('optimization', 'subset_search', 'trigger_on_slack'),
            'max_cap_slack': ('optimization', 'subset_search', 'max_slack_threshold'),
            # New enhanced analysis flags
            'validate_input': ('input', 'validate_input'),
            'compare_presets': ('output', 'include_preset_comparison'),
            'analyze_distortion': ('output', 'include_impact_summary'),
            'output_format': ('output', 'output_format'),
            'include_calculated': ('output', 'include_calculated_metrics'),
            'fraud_in_bps': ('output', 'fraud_in_bps'),
            'lean': ('runtime', 'lean_mode'),
            'compliance_posture': ('compliance_posture',),
            'privacy_basis': ('control3', 'privacy_basis'),
            'contains_digital_wallet_metrics': ('control3', 'contains_digital_wallet_metrics'),
            'digital_wallet_review_approved': ('control3', 'digital_wallet_review_approved'),
            'contains_top_merchant_output': ('control3', 'contains_top_merchant_output'),
            'dual_entity_axis': ('control3', 'dual_entity_axis'),
            'dual_entity_axis_review_approved': ('control3', 'dual_entity_axis_review_approved'),
            'recurring_deliverable': ('control3', 'recurring_deliverable'),
            'last_privacy_recheck_date': ('control3', 'last_privacy_recheck_date'),
            'peer_group_altered': ('control3', 'peer_group_altered'),
        }
        material_cli_keys = {
            'per_dimension_weights',
            'max_iterations',
            'tolerance',
            'max_weight',
            'min_weight',
            'volume_preservation',
            'auto_subset_search',
            'subset_search_max_tests',
            'trigger_subset_on_slack',
            'max_cap_slack',
        }
        
        for cli_key, config_path in mapping.items():
            if cli_key in overrides and overrides[cli_key] is not None:
                if cli_key in material_cli_keys:
                    self._material_overrides.append(cli_key)
                if cli_key == 'per_dimension_weights':
                    value = 'per_dimension' if overrides[cli_key] else 'global'
                    self._set_nested(self.config, config_path, value)
                else:
                    self._set_nested(self.config, config_path, overrides[cli_key])
                logger.debug(f"CLI override: {cli_key} = {overrides[cli_key]}")

        self._apply_runtime_profiles()

    def _apply_runtime_profiles(self) -> None:
        runtime_cfg = self.config.get('runtime', {})
        if not isinstance(runtime_cfg, dict) or not runtime_cfg.get('lean_mode', False):
            return

        self._set_nested(self.config, ('input', 'validate_input'), False)
        self._set_nested(self.config, ('input', 'project_csv_columns'), True)
        self._set_nested(self.config, ('output', 'include_debug_sheets'), False)
        self._set_nested(self.config, ('output', 'include_privacy_validation'), False)
        self._set_nested(self.config, ('output', 'include_impact_summary'), False)
        self._set_nested(self.config, ('output', 'include_preset_comparison'), False)
        self._set_nested(self.config, ('output', 'include_calculated_metrics'), False)
        self._set_nested(self.config, ('output', 'include_audit_log'), False)
        self._set_nested(self.config, ('output', 'output_format'), 'analysis')
        self._set_nested(self.config, ('analysis', 'auto_detect_dimensions'), False)
        self._set_nested(self.config, ('optimization', 'subset_search', 'enabled'), False)
        current_max_attempts = self.config.get('optimization', {}).get('subset_search', {}).get('max_attempts', 200)
        try:
            max_attempts = min(int(current_max_attempts), 20)
        except Exception:
            max_attempts = 20
        self._set_nested(self.config, ('optimization', 'subset_search', 'max_attempts'), max_attempts)

    def _file_declares_posture(self, config_file: str) -> bool:
        path = Path(config_file)
        if not path.exists():
            return False
        try:
            if path.suffix.lower() in ['.yaml', '.yml'] and yaml is not None:
                with open(path, 'r') as f:
                    loaded = yaml.safe_load(f) or {}
            else:
                with open(path, 'r') as f:
                    loaded = json.load(f)
        except Exception:
            return False
        return isinstance(loaded, dict) and 'compliance_posture' in loaded

    def _validate_compliance_posture(self) -> None:
        posture = self.config.get('compliance_posture')
        if posture not in VALID_COMPLIANCE_POSTURES:
            allowed = ', '.join(VALID_COMPLIANCE_POSTURES)
            raise ValueError(f"Invalid or missing compliance_posture: {posture!r}. Expected one of: {allowed}")
        if (
            self._preset_name
            and self._material_overrides
            and not self._config_declared_posture
            and not self._cli_declared_posture
        ):
            changed = ', '.join(sorted(set(self._material_overrides)))
            raise ValueError(
                "Material optimization overrides require an explicit final compliance_posture "
                f"via config file or CLI override. Overrides: {changed}"
            )
    
    def _set_nested(self, d: dict, path: tuple, value: Any) -> None:
        """Set nested dictionary value using path tuple.
        
        Parameters:
        -----------
        d : dict
            Dictionary to modify
        path : tuple
            Path to nested value (e.g., ('optimization', 'bounds', 'max_weight'))
        value : Any
            Value to set
        """
        for key in path[:-1]:
            d = d.setdefault(key, {})
        d[path[-1]] = value
    
    def get(self, *path, default=None):
        """Get configuration value using path.
        
        Parameters:
        -----------
        *path : str
            Path components (e.g., 'optimization', 'bounds', 'max_weight')
        default : Any, optional
            Default value if path not found
            
        Returns:
        --------
        Any
            Configuration value at path, or default if not found
            
        Examples:
        ---------
        >>> config.get('optimization', 'bounds', 'max_weight')
        10.0
        >>> config.get('optimization', 'bounds', 'max_weight', default=5.0)
        10.0
        >>> config.get('nonexistent', 'path', default=None)
        None
        """
        value = self.config
        for key in path:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    def resolve(self) -> ResolvedConfig:
        """Return a typed view of the merged configuration."""
        return ResolvedConfig.from_merged_config(self.config)

