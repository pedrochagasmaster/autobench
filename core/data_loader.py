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
import re

logger = logging.getLogger(__name__)


def _validate_sql_identifier(identifier: str) -> str:
    """Validate a SQL identifier to prevent injection attacks."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?", identifier):
        raise ValueError(f"Unsafe SQL table name: {identifier!r}")
    return identifier


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
        self.schema_detection_mode = 'heuristic'
        self.column_mapping: Dict[str, str] = {}
        self.max_csv_size_mb: Optional[float] = None
        self.max_csv_rows: Optional[int] = None
        self.csv_chunk_size: Optional[int] = None
        if config is not None:
            if hasattr(config, 'get'):
                try:
                    self.schema_detection_mode = str(
                        config.get('input', 'schema_detection_mode', default='heuristic')
                    ).lower()
                except Exception:
                    self.schema_detection_mode = 'heuristic'
                try:
                    max_csv_size_mb = config.get('input', 'max_csv_size_mb', default=None)
                    self.max_csv_size_mb = float(max_csv_size_mb) if max_csv_size_mb else None
                except Exception:
                    self.max_csv_size_mb = None
                try:
                    max_csv_rows = config.get('input', 'max_csv_rows', default=None)
                    self.max_csv_rows = int(max_csv_rows) if max_csv_rows else None
                except Exception:
                    self.max_csv_rows = None
                try:
                    csv_chunk_size = config.get('input', 'csv_chunk_size', default=None)
                    self.csv_chunk_size = int(csv_chunk_size) if csv_chunk_size else None
                except Exception:
                    self.csv_chunk_size = None
            if hasattr(config, 'get_column_mapping'):
                try:
                    self.column_mapping = config.get_column_mapping() or {}
                except Exception:
                    self.column_mapping = {}
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
            return self.load_from_csv(args.csv, nrows=getattr(args, 'nrows', None))
        elif hasattr(args, 'sql_query') and args.sql_query:
            return self.load_from_sql_query(args.sql_query)
        elif hasattr(args, 'sql_table') and args.sql_table:
            return self.load_from_sql_table(args.sql_table)
        else:
            raise ValueError("No valid data source specified")
    
    def load_from_csv(self, file_path: str, nrows: Optional[int] = None) -> pd.DataFrame:
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

        if self.max_csv_size_mb is not None:
            file_size_mb = path.stat().st_size / (1024.0 * 1024.0)
            if file_size_mb > self.max_csv_size_mb:
                raise ValueError(
                    f"CSV file is too large ({file_size_mb:.2f} MB). "
                    f"Configured max_csv_size_mb={self.max_csv_size_mb}."
                )

        try:
            effective_nrows = nrows if nrows is not None else self.max_csv_rows
            df = self._read_csv_with_limits(file_path, effective_nrows)
            logger.info(f"Loaded {len(df)} rows, {len(df.columns)} columns")
            
            # Normalize column names
            df = self._normalize_columns(df)
            
            return df
            
        except Exception as e:
            logger.error(f"Failed to load CSV: {str(e)}")
            raise

    def _read_csv_with_limits(self, file_path: str, nrows: Optional[int]) -> pd.DataFrame:
        chunk_size = self.csv_chunk_size if self.csv_chunk_size and self.csv_chunk_size > 0 else None
        if chunk_size is None:
            return pd.read_csv(file_path, nrows=nrows)

        chunks: List[pd.DataFrame] = []
        rows_read = 0
        for chunk in pd.read_csv(file_path, chunksize=chunk_size):
            if nrows is None:
                chunks.append(chunk)
                continue

            remaining = nrows - rows_read
            if remaining <= 0:
                break
            if len(chunk) > remaining:
                chunk = chunk.iloc[:remaining]
            chunks.append(chunk)
            rows_read += len(chunk)
            if rows_read >= nrows:
                break

        if not chunks:
            return pd.DataFrame()
        return pd.concat(chunks, ignore_index=True)
    
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
            safe_table_name = _validate_sql_identifier(table_name)
            query = f"SELECT * FROM {safe_table_name}"
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
        Normalize column names to standard format with collision detection.
        
        Parameters:
        -----------
        df : pd.DataFrame
            Input dataframe
            
        Returns:
        --------
        pd.DataFrame
            Dataframe with normalized columns
            
        Notes:
        ------
        If normalization causes column name collisions (e.g., "Rate (%)" and
        "Rate (#)" both normalizing to "rate"), a warning is logged and 
        numeric suffixes are appended to resolve the collision.
        """
        original_columns = df.columns.tolist()
        
        # Step 1: Lowercase and strip whitespace
        new_cols = df.columns.str.lower().str.strip()
        # Step 2: Replace common separators with underscores
        new_cols = new_cols.str.replace(r'[\s\-\.]+', '_', regex=True)
        # Step 3: Remove remaining special characters
        new_cols = new_cols.str.replace(r'[^a-z0-9_]', '', regex=True)
        # Step 4: Clean up consecutive/trailing underscores
        new_cols = new_cols.str.replace(r'_+', '_', regex=True)
        new_cols = new_cols.str.strip('_')
        
        # Step 4: Detect and resolve collisions
        seen: Dict[str, int] = {}
        final_cols = []
        for i, col in enumerate(new_cols):
            if col in seen:
                original_a = original_columns[seen[col]]
                original_b = original_columns[i]
                logger.warning(
                    f"Column name collision after normalization: "
                    f"'{original_a}' and '{original_b}' both normalize to '{col}'. "
                    f"Appending suffix '_{i}' to resolve."
                )
                final_cols.append(f"{col}_{i}")
            else:
                seen[col] = i
                final_cols.append(col)
        
        df.columns = final_cols
        
        # Note: Column mappings removed - use actual column names from dataset
        # Users specify column names via CLI flags (--entity-col, --metric, etc.)
        
        return df

    def _map_columns_to_canonical(self, columns: List[str]) -> Dict[str, List[str]]:
        if not self.column_mapping:
            return {}
        mapped: Dict[str, List[str]] = {}
        for col in columns:
            canonical = self.column_mapping.get(col)
            if canonical:
                mapped.setdefault(canonical, []).append(col)
        return mapped

    @staticmethod
    def _column_tokens(column_name: str) -> List[str]:
        return [tok for tok in re.split(r'[_\W]+', str(column_name).lower()) if tok]

    @classmethod
    def _is_count_like_column(cls, column_name: str) -> bool:
        tokens = set(cls._column_tokens(column_name))
        return bool(tokens.intersection({'count', 'counts', 'cnt', 'txn_count', 'transaction_count'})) or (
            ('txn' in tokens or 'transaction' in tokens or 'txns' in tokens) and bool(tokens.intersection({'count', 'cnt'}))
        )

    @classmethod
    def _is_amount_like_column(cls, column_name: str) -> bool:
        tokens = set(cls._column_tokens(column_name))
        return bool(tokens.intersection({'amount', 'amt', 'tpv', 'volume', 'value'}))

    @classmethod
    def _is_entity_like_column(cls, column_name: str) -> bool:
        tokens = set(cls._column_tokens(column_name))
        return bool(tokens.intersection({'entity', 'issuer', 'merchant', 'bank', 'institution'}))

    @classmethod
    def _is_approved_like_column(cls, column_name: str) -> bool:
        tokens = set(cls._column_tokens(column_name))
        return bool(tokens.intersection({'approved', 'approval', 'appr'}))

    @classmethod
    def _is_total_like_column(cls, column_name: str) -> bool:
        tokens = set(cls._column_tokens(column_name))
        return bool(tokens.intersection({'total', 'overall'}))

    @classmethod
    def _is_declined_like_column(cls, column_name: str) -> bool:
        tokens = set(cls._column_tokens(column_name))
        return bool(tokens.intersection({'declined', 'decline', 'rejected'}))
    
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
        mapped_roles = self._map_columns_to_canonical(df.columns.tolist())
        if mapped_roles and self.schema_detection_mode in ('mapped', 'hybrid'):
            count_cols = mapped_roles.get('transaction_count', [])
            amount_cols = mapped_roles.get('transaction_amount', [])
            entity_cols = mapped_roles.get('entity_identifier', [])
            has_minimal = bool(count_cols and amount_cols and entity_cols)
            if has_minimal:
                logger.info(
                    "Minimal schema detected via column mappings "
                    "(count=%s, amount=%s, entity=%s)",
                    count_cols,
                    amount_cols,
                    entity_cols
                )
                return True
            if self.schema_detection_mode == 'mapped':
                logger.warning("Minimal schema not found using column mappings.")
                logger.warning(f"  Count columns: {count_cols}")
                logger.warning(f"  Amount columns: {amount_cols}")
                logger.warning(f"  Entity columns: {entity_cols}")
                return False
            logger.info("Minimal schema not found via column mappings; falling back to heuristic detection.")

        # Check for transaction count column
        count_cols = [col for col in df.columns if self._is_count_like_column(col)]
        
        # Check for transaction amount column
        amount_cols = [col for col in df.columns if self._is_amount_like_column(col)]
        
        # Check for entity identifier
        entity_cols = [col for col in df.columns if self._is_entity_like_column(col)]
        
        has_minimal = len(count_cols) > 0 and len(amount_cols) > 0 and len(entity_cols) > 0
        
        if has_minimal:
            logger.info("Minimal schema detected (transaction count and amount)")
        else:
            logger.warning("Minimal schema not found")
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
        mapped_roles = self._map_columns_to_canonical(df.columns.tolist())
        if mapped_roles and self.schema_detection_mode in ('mapped', 'hybrid'):
            approved_cols = mapped_roles.get('approved_count', []) + mapped_roles.get('approved_amount', [])
            total_cols = mapped_roles.get('total_count', []) + mapped_roles.get('total_amount', [])
            declined_cols = mapped_roles.get('declined_count', []) + mapped_roles.get('declined_amount', [])
            entity_cols = mapped_roles.get('entity_identifier', [])
            has_full = bool(approved_cols and (total_cols or declined_cols) and entity_cols)
            if has_full:
                logger.info(
                    "Full schema detected via column mappings "
                    "(approved=%s, total=%s, declined=%s, entity=%s)",
                    approved_cols,
                    total_cols,
                    declined_cols,
                    entity_cols
                )
                return True
            if self.schema_detection_mode == 'mapped':
                logger.warning("Full schema not found using column mappings.")
                logger.warning(f"  Approved columns: {approved_cols}")
                logger.warning(f"  Total columns: {total_cols}")
                logger.warning(f"  Declined columns: {declined_cols}")
                logger.warning(f"  Entity columns: {entity_cols}")
                return False
            logger.info("Full schema not found via column mappings; falling back to heuristic detection.")

        # Check for approved columns
        approved_cols = [col for col in df.columns if self._is_approved_like_column(col)]
        
        # Check for total/declined columns
        total_cols = [col for col in df.columns if self._is_total_like_column(col)]
        
        declined_cols = [col for col in df.columns if self._is_declined_like_column(col)]
        
        # Check for entity identifier
        entity_cols = [col for col in df.columns if self._is_entity_like_column(col)]
        
        has_full = (len(approved_cols) > 0 and 
                   (len(total_cols) > 0 or len(declined_cols) > 0) and 
                   len(entity_cols) > 0)
        
        if has_full:
            logger.info("Full schema detected (approved/declined breakdown)")
        else:
            logger.warning("Full schema not found")
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
                message=(
                    f"Required columns not found: {missing_cols}. "
                    "Check column names after normalization (lowercase + underscores)."
                )
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
                    fix_description="Fill nulls with 0 or mode for categorical columns"
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
        if not all_num_cols:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="missing_columns",
                message="No numerator columns provided for rate analysis."
            ))
            return issues
        required_cols = [total_col, entity_col] + all_num_cols + dimensions
        if time_col:
            required_cols.append(time_col)
            
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            issues.append(ValidationIssue(
                severity=ValidationSeverity.ERROR,
                category="missing_columns",
                message=(
                    f"Required columns not found: {missing_cols}. "
                    "Check column names after normalization (lowercase + underscores)."
                )
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
        
        # 8. Check for impossible and outlier rates
        for rate_name, num_col in numerator_cols.items():
            valid_rows = df[total_col] > 0
            if valid_rows.any():
                rates = 100.0 * df.loc[valid_rows, num_col] / df.loc[valid_rows, total_col]
                impossible_mask = rates > 100.0
                if impossible_mask.any():
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.ERROR,
                        category="invalid_rates",
                        message=f"Rate '{rate_name}' has {int(impossible_mask.sum())} values above 100%",
                        row_indices=rates[impossible_mask].index.tolist()[:50],
                    ))
                outlier_mask = (rates < 0) | (rates > 100 + t['max_rate_deviation'])
                outlier_mask = outlier_mask & ~impossible_mask
                outliers = rates[outlier_mask]
                if len(outliers) > 0:
                    issues.append(ValidationIssue(
                        severity=ValidationSeverity.WARNING,
                        category="outlier_rates",
                        message=f"Rate '{rate_name}' has {len(outliers)} outlier values outside expected range"
                    ))
        
        logger.info(f"Rate validation complete: {len([i for i in issues if i.severity == ValidationSeverity.ERROR])} errors, "
                   f"{len([i for i in issues if i.severity == ValidationSeverity.WARNING])} warnings")
        
        return issues

