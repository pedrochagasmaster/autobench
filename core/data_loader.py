"""
DataLoader - Data loading and validation module.

Supports multiple data sources (CSV, SQL) and validates schema compliance.
"""

import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Any
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


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
        
        # Apply column mapping from config
        column_mapping = self.config.get_column_mapping()
        if column_mapping:
            df = df.rename(columns=column_mapping)
        
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
