"""
DataLoader - Data loading and validation module.

Supports multiple data sources (CSV, SQL) and validates schema compliance.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Any, Tuple
from pathlib import Path
from enum import Enum
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity levels for data validation issues."""
    ERROR = "ERROR"      # Abort analysis - data is invalid
    WARNING = "WARNING"  # Continue with caution - data quality concern
    INFO = "INFO"        # Informational - no action required


@dataclass
class ValidationIssue:
    """Represents a data quality issue found during validation."""
    severity: ValidationSeverity
    category: str
    message: str
    row_indices: Optional[List[int]] = None
    auto_fix_available: bool = False
    fix_description: Optional[str] = None
    
    def __str__(self) -> str:
        return f"[{self.severity.value}] {self.category}: {self.message}"


# Default thresholds for data quality validation
# These can be overridden via config file (input.validation_thresholds)
VALIDATION_THRESHOLDS = {
    'min_denominator': 100,           # Minimum total for stable rate calculation
    'min_peer_count': 5,              # Minimum peers for privacy compliance
    'max_rate_deviation': 50.0,       # Max rate deviation from 0-100% expected range
    'min_rows_per_category': 3,       # Minimum rows per category for statistical validity
    'max_null_percentage': 5.0,       # Max percentage of null values in critical columns
    'max_entity_concentration': 50.0, # Max single entity concentration (warning threshold)
}

class DataLoader:
    """
    Handles data loading from multiple sources and schema validation.
    
    Supports:
    - CSV files
    - SQL queries and tables
    - Schema detection (full vs minimal)
    - Column mapping and normalization
    """
    
    REQUIRED_MINIMAL_SCHEMA = [
        'entity_identifier',
        'transaction_count',
        'transaction_amount'
    ]
    
    REQUIRED_FULL_SCHEMA = [
        'entity_identifier',
        'approved_count',
        'approved_amount',
        'total_count',
        'total_amount'
    ]
    
    OPTIONAL_FULL_SCHEMA = [
        'declined_count',
        'declined_amount',
        'fraud_count',
        'fraud_amount'
    ]
    
    def __init__(self, config: Any):
        """
        Initialize data loader.
        
        Parameters:
        -----------
        config : ConfigManager
            Configuration manager instance
        """
        self.config = config
        logger.info("Initialized DataLoader")
    
    def load_data(self, args: Any) -> pd.DataFrame:
        """
        Load data from source specified in arguments.
        
        Parameters:
        -----------
        args : argparse.Namespace
            Command line arguments
            
        Returns:
        --------
        pd.DataFrame
            Loaded and preprocessed data
        """
        if hasattr(args, 'csv') and args.csv:
            return self.load_from_csv(args.csv)
        elif hasattr(args, 'sql_query') and args.sql_query:
            return self.load_from_sql_query(args.sql_query)
        elif hasattr(args, 'sql_table') and args.sql_table:
            return self.load_from_sql_table(args.sql_table)
        else:
            raise ValueError("No valid data source specified")
    
    def load_from_csv(self, file_path: str) -> pd.DataFrame:
        """
        Load data from CSV file.
        
        Parameters:
        -----------
        file_path : str
            Path to CSV file
            
        Returns:
        --------
        pd.DataFrame
            Loaded data
        """
        logger.info(f"Loading data from CSV: {file_path}")
        
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {file_path}")
        
        try:
            df = pd.read_csv(file_path)
            logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")
            
            # Normalize column names
            df = self._normalize_columns(df)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to load CSV: {str(e)}")
            raise
    
    def load_from_sql_query(self, query_file: str) -> pd.DataFrame:
        """
        Load data from SQL query file.
        
        Parameters:
        -----------
        query_file : str
            Path to SQL query file
            
        Returns:
        --------
        pd.DataFrame
            Query results
        """
        logger.info(f"Loading data from SQL query: {query_file}")
        
        path = Path(query_file)
        if not path.exists():
            raise FileNotFoundError(f"Query file not found: {query_file}")
        
        try:
            # Read query from file
            with open(query_file, 'r') as f:
                query = f.read()
            
            # Execute query (requires SQL connection configuration)
            connection = self.config.get_sql_connection()
            df = pd.read_sql(query, connection)
            
            logger.info(f"Loaded {len(df)} rows from query")
            
            # Normalize column names
            df = self._normalize_columns(df)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to execute SQL query: {str(e)}")
            raise
    
    def load_from_sql_table(self, table_name: str) -> pd.DataFrame:
        """
        Load data from SQL table.
        
        Parameters:
        -----------
        table_name : str
            Name of table to query
            
        Returns:
        --------
        pd.DataFrame
            Table data
        """
        logger.info(f"Loading data from SQL table: {table_name}")
        
        try:
            connection = self.config.get_sql_connection()
            query = f"SELECT * FROM {table_name}"
            df = pd.read_sql(query, connection)
            
            logger.info(f"Loaded {len(df)} rows from table")
            
            # Normalize column names
            df = self._normalize_columns(df)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to load SQL table: {str(e)}")
            raise
    
    def _normalize_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize column names to standard format.
        
        Parameters:
        -----------
        df : pd.DataFrame
            Input dataframe
            
        Returns:
        --------
        pd.DataFrame
            Dataframe with normalized columns
        """
        # Convert to lowercase and replace spaces/special chars
        df.columns = df.columns.str.lower().str.strip()
        df.columns = df.columns.str.replace(' ', '_')
        df.columns = df.columns.str.replace('-', '_')
        df.columns = df.columns.str.replace('[^a-zA-Z0-9_]', '', regex=True)
        
        # Note: Column mappings removed - use actual column names from dataset
        # Users specify column names via CLI flags (--entity-col, --metric, etc.)
        
        return df
    
    def validate_minimal_schema(self, df: pd.DataFrame) -> bool:
        """
        Validate if dataframe has minimal required schema.
        
        Parameters:
        -----------
        df : pd.DataFrame
            Dataframe to validate
            
        Returns:
        --------
        bool
            True if minimal schema is present
        """
        # Check for transaction count column
        count_cols = [col for col in df.columns 
                     if any(term in col.lower() for term in 
                           ['transaction_count', 'txn_count', 'count', 'cnt'])]
        
        # Check for transaction amount column
        amount_cols = [col for col in df.columns 
                      if any(term in col.lower() for term in 
                            ['transaction_amount', 'txn_amt', 'amount', 'amt', 'tpv', 'volume'])]
        
        # Check for entity identifier
        entity_cols = [col for col in df.columns 
                      if any(term in col.lower() for term in 
                            ['entity', 'issuer', 'merchant', 'bank', 'institution'])]
        
        has_minimal = len(count_cols) > 0 and len(amount_cols) > 0 and len(entity_cols) > 0
        
        if has_minimal:
            logger.info("✓ Minimal schema detected (transaction count and amount)")
        else:
            logger.warning("✗ Minimal schema not found")
            logger.warning(f"  Count columns: {count_cols}")
            logger.warning(f"  Amount columns: {amount_cols}")
            logger.warning(f"  Entity columns: {entity_cols}")
        
        return has_minimal
    
    def validate_full_schema(self, df: pd.DataFrame) -> bool:
        """
        Validate if dataframe has full schema for rate analysis.
        
        Parameters:
        -----------
        df : pd.DataFrame
            Dataframe to validate
            
        Returns:
        --------
        bool
            True if full schema is present
        """
        # Check for approved columns
        approved_cols = [col for col in df.columns 
                        if 'approved' in col.lower() or 'auth_approved' in col.lower()]
        
        # Check for total/declined columns
        total_cols = [col for col in df.columns 
                     if any(term in col.lower() for term in ['total', 'auth_total'])]
        
        declined_cols = [col for col in df.columns 
                        if 'declined' in col.lower() or 'decline' in col.lower()]
        
        # Check for entity identifier
        entity_cols = [col for col in df.columns 
                      if any(term in col.lower() for term in 
                            ['entity', 'issuer', 'merchant', 'bank', 'institution'])]
        
        has_full = (len(approved_cols) > 0 and 
                   (len(total_cols) > 0 or len(declined_cols) > 0) and 
                   len(entity_cols) > 0)
        
        if has_full:
            logger.info("✓ Full schema detected (approved/declined breakdown)")
        else:
            logger.warning("✗ Full schema not found")
            logger.warning(f"  Approved columns: {approved_cols}")
            logger.warning(f"  Total columns: {total_cols}")
            logger.warning(f"  Declined columns: {declined_cols}")
        
        return has_full
    
    def detect_schema_type(self, df: pd.DataFrame) -> str:
        """
        Detect which schema type is present in the data.
        
        Parameters:
        -----------
        df : pd.DataFrame
            Dataframe to analyze
            
        Returns:
        --------
        str
            'full', 'minimal', or 'unknown'
        """
        has_full = self.validate_full_schema(df)
        has_minimal = self.validate_minimal_schema(df)
        
        if has_full:
            return 'full'
        elif has_minimal:
            return 'minimal'
        else:
            return 'unknown'
    
    def get_available_dimensions(self, df: pd.DataFrame) -> List[str]:
        """
        Identify available analysis dimensions in the data.
        
        Parameters:
        -----------
        df : pd.DataFrame
            Input dataframe
            
        Returns:
        --------
        List[str]
            List of potential dimension columns
        """
        # Exclude numeric columns and identifiers
        numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
        
        identifier_keywords = ['entity', 'issuer', 'merchant', 'id', 'code', 'name']
        identifier_cols = [col for col in df.columns 
                          if any(kw in col.lower() for kw in identifier_keywords)]
        
        # Get categorical columns
        exclude_cols = set(numeric_cols + identifier_cols)
        dimension_cols = [col for col in df.columns if col not in exclude_cols]
        
        logger.info(f"Found {len(dimension_cols)} potential dimension columns")
        return dimension_cols
    
    def preprocess_data(
        self,
        df: pd.DataFrame,
        fill_na: Any = 0,
        remove_zeros: bool = True
    ) -> pd.DataFrame:
        """
        Preprocess data for analysis.
        
        Parameters:
        -----------
        df : pd.DataFrame
            Input dataframe
        fill_na : Any
            Value to fill missing data
        remove_zeros : bool
            Whether to remove rows with all zeros in metrics
            
        Returns:
        --------
        pd.DataFrame
            Preprocessed dataframe
        """
        logger.info("Preprocessing data...")
        
        df_clean = df.copy()
        
        # Fill missing values
        df_clean = df_clean.fillna(fill_na)
        
        # Remove rows with all zeros in numeric columns
        if remove_zeros:
            numeric_cols = df_clean.select_dtypes(include=[np.number]).columns
            df_clean = df_clean[(df_clean[numeric_cols] != 0).any(axis=1)]
        
        logger.info(f"Preprocessed: {len(df_clean)} rows remaining")
        
        return df_clean

    def _match_target_entity(
        self,
        df: pd.DataFrame,
        entity_col: str,
        target_entity: Optional[str]
    ) -> Optional[str]:
        if not target_entity:
            return None
        if target_entity in df[entity_col].values:
            return target_entity
        entity_upper = str(target_entity).upper()
        for entity in df[entity_col].unique():
            if entity is not None and str(entity).upper() == entity_upper:
                return str(entity)
        return None

    def _collect_entity_validation_issues(
        self,
        df: pd.DataFrame,
        entity_col: str,
        target_entity: Optional[str],
        thresholds: Dict[str, Any],
        include_entity_samples: bool
    ) -> List[ValidationIssue]:
        issues: List[ValidationIssue] = []
        unique_entities = df[entity_col].nunique()
        target_match = self._match_target_entity(df, entity_col, target_entity)
        peer_count = unique_entities - 1 if target_match else unique_entities

        if peer_count < thresholds['min_peer_count']:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="insufficient_peers",
                message=(
                    f"Only {peer_count} peer entities found (excluding target). "
                    f"Minimum {thresholds['min_peer_count']} required for privacy compliance."
                )
            ))

        if target_entity:
            if target_match is None:
                if include_entity_samples:
                    sample = df[entity_col].unique()[:10].tolist()
                    message = (
                        f"Target entity '{target_entity}' not found in data. "
                        f"Available entities: {sample}"
                    )
                else:
                    message = f"Target entity '{target_entity}' not found in data."
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="missing_entity",
                    message=message
                ))
            elif target_match != target_entity:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.INFO,
                    category="entity_case",
                    message=f"Target entity found with different case: '{target_match}'"
                ))

        return issues
    
    def validate_share_input(
        self,
        df: pd.DataFrame,
        metric_col: str,
        entity_col: str,
        dimensions: List[str],
        time_col: Optional[str] = None,
        target_entity: Optional[str] = None,
        thresholds: Optional[Dict[str, Any]] = None
    ) -> List[ValidationIssue]:
        """
        Validate input data for share analysis.
        
        Checks for:
        - Missing required columns
        - Null values in critical columns
        - Negative metric values
        - Entity count (privacy compliance)
        - Category coverage
        - Entity concentration
        
        Parameters:
        -----------
        df : pd.DataFrame
            Input dataframe
        metric_col : str
            Column containing metric values (e.g., volume_brl, txn_count)
        entity_col : str
            Column containing entity identifiers
        dimensions : List[str]
            List of dimension columns
        time_col : Optional[str]
            Time column if present
        target_entity : Optional[str]
            Target entity for analysis
        thresholds : Optional[Dict[str, Any]]
            Custom validation thresholds (overrides defaults)
            
        Returns:
        --------
        List[ValidationIssue]
            List of validation issues found
        """
        issues: List[ValidationIssue] = []
        
        # Merge thresholds with defaults
        t = {**VALIDATION_THRESHOLDS, **(thresholds or {})}
        
        # 1. Check required columns exist
        required_cols = [metric_col, entity_col] + dimensions
        if time_col:
            required_cols.append(time_col)
            
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="missing_columns",
                message=f"Required columns not found: {missing_cols}. Available: {list(df.columns)}"
            ))
            return issues  # Cannot continue validation without required columns
        
        # 2. Check for null values in critical columns
        for col in required_cols:
            null_count = df[col].isnull().sum()
            null_pct = 100.0 * null_count / len(df) if len(df) > 0 else 0
            
            if null_pct > t['max_null_percentage']:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="null_values",
                    message=f"Column '{col}' has {null_pct:.1f}% null values (threshold: {t['max_null_percentage']}%)",
                    row_indices=df[df[col].isnull()].index.tolist()[:100],
                    auto_fix_available=True,
                    fix_description=f"Fill nulls with 0 or mode for categorical columns"
                ))
            elif null_count > 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="null_values",
                    message=f"Column '{col}' has {null_count} null values ({null_pct:.2f}%)",
                    row_indices=df[df[col].isnull()].index.tolist()[:20]
                ))
        
        # 3. Check for negative metric values
        negative_mask = df[metric_col] < 0
        if negative_mask.any():
            negative_count = negative_mask.sum()
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="negative_values",
                message=f"Metric column '{metric_col}' has {negative_count} negative values",
                row_indices=df[negative_mask].index.tolist()[:50]
            ))

        # 4-5. Check entity count and target entity existence
        issues.extend(
            self._collect_entity_validation_issues(
                df,
                entity_col,
                target_entity,
                t,
                include_entity_samples=True
            )
        )
        
        # 6. Check minimum rows per category (for each dimension)
        for dim in dimensions:
            category_counts = df[dim].value_counts()
            small_categories = category_counts[category_counts < t['min_rows_per_category']]
            if len(small_categories) > 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="small_categories",
                    message=f"Dimension '{dim}' has {len(small_categories)} categories with fewer than {t['min_rows_per_category']} rows: {small_categories.index.tolist()[:5]}"
                ))
        
        # 7. Check entity concentration
        total_metric = df[metric_col].sum()
        if total_metric > 0:
            entity_shares = df.groupby(entity_col)[metric_col].sum() / total_metric * 100
            high_concentration = entity_shares[entity_shares > t['max_entity_concentration']]
            if len(high_concentration) > 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="high_concentration",
                    message=f"High entity concentration detected: {dict(high_concentration.round(1))}. Consider balanced weighting."
                ))
        
        logger.info(f"Share validation complete: {len([i for i in issues if i.severity == ValidationSeverity.ERROR])} errors, "
                   f"{len([i for i in issues if i.severity == ValidationSeverity.WARNING])} warnings")
        
        return issues
    
    def validate_rate_input(
        self,
        df: pd.DataFrame,
        total_col: str,
        numerator_cols: Dict[str, str],
        entity_col: str,
        dimensions: List[str],
        time_col: Optional[str] = None,
        target_entity: Optional[str] = None,
        thresholds: Optional[Dict[str, Any]] = None
    ) -> List[ValidationIssue]:
        """
        Validate input data for rate analysis.
        
        Checks for:
        - Missing required columns
        - Null values in critical columns
        - Negative or invalid rate values
        - Numerator > denominator
        - Entity count (privacy compliance)
        - Minimum denominator for stable rates
        
        Parameters:
        -----------
        df : pd.DataFrame
            Input dataframe
        total_col : str
            Column containing total/denominator values
        numerator_cols : Dict[str, str]
            Dict mapping rate name to numerator column (e.g., {'approval': 'approved_col'})
        entity_col : str
            Column containing entity identifiers
        dimensions : List[str]
            List of dimension columns
        time_col : Optional[str]
            Time column if present
        target_entity : Optional[str]
            Target entity for analysis
        thresholds : Optional[Dict[str, Any]]
            Custom validation thresholds
            
        Returns:
        --------
        List[ValidationIssue]
            List of validation issues found
        """
        issues: List[ValidationIssue] = []
        
        # Merge thresholds with defaults
        t = {**VALIDATION_THRESHOLDS, **(thresholds or {})}
        
        # 1. Check required columns exist
        all_num_cols = list(numerator_cols.values())
        required_cols = [total_col, entity_col] + all_num_cols + dimensions
        if time_col:
            required_cols.append(time_col)
            
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="missing_columns",
                message=f"Required columns not found: {missing_cols}. Available: {list(df.columns)}"
            ))
            return issues
        
        # 2. Check for null values in critical columns
        for col in [total_col] + all_num_cols:
            null_count = df[col].isnull().sum()
            null_pct = 100.0 * null_count / len(df) if len(df) > 0 else 0
            
            if null_pct > t['max_null_percentage']:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="null_values",
                    message=f"Column '{col}' has {null_pct:.1f}% null values (threshold: {t['max_null_percentage']}%)",
                    row_indices=df[df[col].isnull()].index.tolist()[:100]
                ))
            elif null_count > 0:
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.WARNING,
                    category="null_values",
                    message=f"Column '{col}' has {null_count} null values ({null_pct:.2f}%)"
                ))
        
        # 3. Check for negative values in numeric columns
        for col in [total_col] + all_num_cols:
            negative_mask = df[col] < 0
            if negative_mask.any():
                negative_count = negative_mask.sum()
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="negative_values",
                    message=f"Column '{col}' has {negative_count} negative values",
                    row_indices=df[negative_mask].index.tolist()[:50]
                ))
        
        # 4. Check numerator <= denominator for each rate
        for rate_name, num_col in numerator_cols.items():
            invalid_mask = df[num_col] > df[total_col]
            if invalid_mask.any():
                invalid_count = invalid_mask.sum()
                issues.append(ValidationIssue(
                    severity=ValidationSeverity.ERROR,
                    category="invalid_rate",
                    message=f"Rate '{rate_name}': {invalid_count} rows have numerator ({num_col}) > denominator ({total_col})",
                    row_indices=df[invalid_mask].index.tolist()[:50]
                ))
        
        # 5. Check minimum denominator for stable rates
        low_denom_mask = (df[total_col] > 0) & (df[total_col] < t['min_denominator'])
        if low_denom_mask.any():
            low_count = low_denom_mask.sum()
            issues.append(ValidationIssue(
                severity=ValidationSeverity.WARNING,
                category="low_denominator",
                message=f"{low_count} rows have denominator below {t['min_denominator']} - rates may be unstable",
                row_indices=df[low_denom_mask].index.tolist()[:20]
            ))

        # 6-7. Check entity count and target entity existence
        issues.extend(
            self._collect_entity_validation_issues(
                df,
                entity_col,
                target_entity,
                t,
                include_entity_samples=False
            )
        )
        
        # 8. Check for outlier rates
        for rate_name, num_col in numerator_cols.items():
            valid_rows = df[total_col] > 0
            if valid_rows.any():
                rates = 100.0 * df.loc[valid_rows, num_col] / df.loc[valid_rows, total_col]
                outlier_mask = (rates < 0) | (rates > 100 + t['max_rate_deviation'])
                outliers = rates[outlier_mask]
                if len(outliers) > 0:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        category="outlier_rates",
                        message=f"Rate '{rate_name}' has {len(outliers)} outlier values outside 0-100% range"
                    ))
        
        logger.info(f"Rate validation complete: {len([i for i in issues if i.severity == ValidationSeverity.ERROR])} errors, "
                   f"{len([i for i in issues if i.severity == ValidationSeverity.WARNING])} warnings")
        
        return issues

