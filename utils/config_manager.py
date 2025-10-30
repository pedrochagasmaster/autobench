"""
ConfigManager - Configuration management for benchmarking tool.

Handles configuration loading, column mappings, and preset management.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


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
        'total_txns': 'transaction_count',
        'count': 'transaction_count',
        'cnt': 'transaction_count',
        
        # Transaction amounts
        'txn_amt': 'transaction_amount',
        'total_amount': 'transaction_amount',
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
    
    def __init__(self, config_file: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Parameters:
        -----------
        config_file : str, optional
            Path to custom configuration file
        """
        self.config = {}
        self.column_mapping = self.DEFAULT_COLUMN_MAPPING.copy()
        self.comparison_metrics = self.DEFAULT_COMPARISON_METRICS.copy()
        self.sql_config = {}
        
        if config_file:
            self.load_config(config_file)
        
        logger.info("Initialized ConfigManager")
    
    def load_config(self, config_file: str) -> None:
        """
        Load configuration from JSON file.
        
        Parameters:
        -----------
        config_file : str
            Path to configuration file
        """
        logger.info(f"Loading configuration from: {config_file}")
        
        path = Path(config_file)
        if not path.exists():
            logger.warning(f"Config file not found: {config_file}")
            return
        
        try:
            with open(path, 'r') as f:
                self.config = json.load(f)
            
            # Update column mapping if provided
            if 'column_mappings' in self.config:
                self.column_mapping.update(self.config['column_mappings'])
            
            # Update comparison metrics if provided
            if 'comparison_metrics' in self.config:
                self.comparison_metrics.update(self.config['comparison_metrics'])
            
            # Load SQL configuration
            if 'sql' in self.config:
                self.sql_config = self.config['sql']
            
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
