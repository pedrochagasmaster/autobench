"""
Unit tests for DataLoader column normalization collision handling.
"""

import unittest
import os
import pandas as pd
from unittest.mock import MagicMock
from tempfile import NamedTemporaryFile
from core.data_loader import DataLoader


class TestColumnNormalizationCollisions(unittest.TestCase):
    """Test column name collision detection and resolution."""
    
    def setUp(self):
        """Create a DataLoader instance with mocked config."""
        mock_config = MagicMock()
        self.loader = DataLoader(mock_config)
    
    def test_no_collision_unique_columns(self):
        """Test that unique columns are normalized without suffixes."""
        df = pd.DataFrame({
            'Entity Name': [1],
            'Transaction Count': [2],
            'Volume BRL': [3]
        })
        
        result = self.loader._normalize_columns(df)
        
        expected = ['entity_name', 'transaction_count', 'volume_brl']
        self.assertEqual(list(result.columns), expected)
    
    def test_collision_detection_rate_percent_hash(self):
        """Test that 'Rate (%)' and 'Rate (#)' collision is detected and resolved."""
        df = pd.DataFrame({
            'Rate (%)': [1.5],
            'Rate (#)': [100],
            'Other Col': ['test']
        })
        
        with self.assertLogs('core.data_loader', level='WARNING') as log:
            result = self.loader._normalize_columns(df)
        
        # Should have logged a warning
        self.assertTrue(any('collision' in msg.lower() for msg in log.output))
        
        # Both columns should exist, one with suffix
        self.assertIn('rate', result.columns)
        self.assertIn('rate_1', result.columns)
        self.assertIn('other_col', result.columns)
    
    def test_suffix_appended_on_collision(self):
        """Test that numeric suffix uses the original column index."""
        df = pd.DataFrame({
            'Col A': [1],
            'Col-A': [2],
            'Col.A': [3],
            'Other': [4]
        })
        
        result = self.loader._normalize_columns(df)
        
        # First 'col_a' wins, subsequent get index suffixes
        self.assertIn('col_a', result.columns)
        self.assertIn('col_a_1', result.columns)
        self.assertIn('col_a_2', result.columns)
        self.assertIn('other', result.columns)
        self.assertEqual(len(result.columns), 4)
    
    def test_separator_normalization(self):
        """Test that various separators are normalized to underscores."""
        df = pd.DataFrame({
            'column-name': [1],
            'column.name.2': [2],
            'column  name  3': [3]
        })
        
        result = self.loader._normalize_columns(df)
        
        self.assertIn('column_name', result.columns)
        self.assertIn('column_name_2', result.columns)
        self.assertIn('column_name_3', result.columns)
    
    def test_special_chars_removed(self):
        """Test that special characters are removed after separator handling."""
        df = pd.DataFrame({
            'Amount ($)': [100],
            'Rate (%)': [5.5],
            'Count [#]': [10]
        })
        
        result = self.loader._normalize_columns(df)
        
        # Special chars ($, %, [, ], #) should be removed 
        self.assertTrue(all(c.isalnum() or c == '_' for col in result.columns for c in col))

    def test_minimal_schema_heuristic_avoids_account_false_positive(self):
        """Ensure account_type is not treated as a count column."""
        df = pd.DataFrame({
            'issuer_name': ['A', 'B'],
            'account_type': ['x', 'y'],
            'txn_amt': [10, 20],
        })
        self.assertFalse(self.loader.validate_minimal_schema(df))

    def test_load_from_csv_respects_row_limit(self):
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda *args, **kwargs: {
            ('input', 'schema_detection_mode'): 'heuristic',
            ('input', 'max_csv_size_mb'): None,
            ('input', 'max_csv_rows'): 2,
            ('input', 'csv_chunk_size'): None,
        }.get(tuple(args), kwargs.get('default'))
        mock_config.get_column_mapping.return_value = {}

        loader = DataLoader(mock_config)
        with NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp:
            temp.write("issuer_name,txn_cnt\nA,1\nB,2\nC,3\n")
            temp_path = temp.name

        try:
            df = loader.load_from_csv(temp_path)
            self.assertEqual(len(df), 2)
        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
