"""
Unit tests for legacy wrappers (Distortion/Weight Effect).

Ensures backward compatibility for scripts using deprecated method names.
"""

import unittest
import pandas as pd
from core.dimensional_analyzer import DimensionalAnalyzer

class TestLegacyWrappers(unittest.TestCase):
    def test_calculate_share_distortion_wrapper(self) -> None:
        """Test that calculate_share_distortion wraps calculate_share_impact."""
        df = pd.DataFrame({
            'issuer_name': ['Target', 'Peer1', 'Peer2'],
            'card_type': ['A', 'A', 'A'],
            'txn_cnt': [100.0, 100.0, 300.0],
        })
        analyzer = DimensionalAnalyzer(
            target_entity='Target',
            entity_column='issuer_name',
            consistent_weights=True
        )
        analyzer.global_weights = {
            'Peer1': {'multiplier': 2.0},
            'Peer2': {'multiplier': 1.0},
        }
        
        # Call legacy method
        df_legacy = analyzer.calculate_share_distortion(
            df=df,
            metric_col='txn_cnt',
            dimensions=['card_type'],
            target_entity='Target'
        )
        
        # Verify columns exist
        self.assertIn('Impact_PP', df_legacy.columns)
        self.assertIn('Distortion_PP', df_legacy.columns)
        
        # Verify values match
        self.assertEqual(
            df_legacy.loc[0, 'Impact_PP'], 
            df_legacy.loc[0, 'Distortion_PP']
        )

    def test_calculate_rate_weight_effect_wrapper(self) -> None:
        """Test that calculate_rate_weight_effect wraps calculate_rate_impact."""
        df = pd.DataFrame({
            'issuer_name': ['Target', 'Peer1', 'Peer2'],
            'card_type': ['A', 'A', 'A'],
            'total': [100.0, 100.0, 300.0],
            'approved': [100.0, 90.0, 30.0],
        })
        analyzer = DimensionalAnalyzer(
            target_entity='Target',
            entity_column='issuer_name',
            consistent_weights=True
        )
        analyzer.global_weights = {
            'Peer1': {'multiplier': 2.0},
            'Peer2': {'multiplier': 1.0},
        }
        
        # Call legacy method
        df_legacy = analyzer.calculate_rate_weight_effect(
            df=df,
            total_col='total',
            numerator_cols={'approval': 'approved'},
            dimensions=['card_type']
        )
        
        # Verify columns exist
        self.assertIn('approval_Impact_PP', df_legacy.columns)
        self.assertIn('approval_Weight_Effect_PP', df_legacy.columns)
        
        # Verify values match
        self.assertEqual(
            df_legacy.loc[0, 'approval_Impact_PP'], 
            df_legacy.loc[0, 'approval_Weight_Effect_PP']
        )

if __name__ == '__main__':
    unittest.main()
