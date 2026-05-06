"""
Unit tests for enhanced analysis features.

Covers:
- Target-vs-peer impact math (share)
- Target-vs-peer impact math (rate)
- Per-dimension weight fallback to global weights
- Validation hard-fail path
- Publication output generation
- Exhaustive preset comparison (+ per-dimension variants)
"""

import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

import pandas as pd
import pytest
import numpy as np

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.dimensional_analyzer import DimensionalAnalyzer
from core.data_loader import DataLoader, ValidationSeverity
from benchmark import run_share_analysis, run_rate_analysis, run_preset_comparison
from utils.config_manager import ConfigManager


class TestImpactMath(unittest.TestCase):
    def test_share_impact_target_vs_peers(self) -> None:
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
        impact_df = analyzer.calculate_share_impact(
            df=df,
            metric_col='txn_cnt',
            dimensions=['card_type'],
            target_entity='Target'
        )
        self.assertEqual(len(impact_df), 1)
        impact = float(impact_df.loc[0, 'Impact_PP'])
        # Raw share = 100 / (100 + 400) = 20%
        # Balanced share = 100 / (100 + (100*2 + 300*1)) = 100 / 600 = 16.6667%
        self.assertAlmostEqual(impact, -3.3333, places=3)

    def test_rate_impact_excludes_target(self) -> None:
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
        impact_df = analyzer.calculate_rate_impact(
            df=df,
            total_col='total',
            numerator_cols={'approval': 'approved'},
            dimensions=['card_type']
        )
        self.assertEqual(len(impact_df), 1)
        impact = float(impact_df.loc[0, 'approval_Impact_PP'])
        # Raw peer rate = (90 + 30) / (100 + 300) = 30%
        # Balanced peer rate = (90*2 + 30*1) / (100*2 + 300*1) = 42%
        self.assertAlmostEqual(impact, 12.0, places=2)

    def test_per_dimension_weight_fallback(self) -> None:
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
            'Peer1': {'multiplier': 1.0},
            'Peer2': {'multiplier': 0.5},
        }
        analyzer.per_dimension_weights = {
            'card_type': {'Peer1': 2.0}
        }
        impact_df = analyzer.calculate_rate_impact(
            df=df,
            total_col='total',
            numerator_cols={'approval': 'approved'},
            dimensions=['card_type']
        )
        impact = float(impact_df.loc[0, 'approval_Impact_PP'])
        # Raw peer rate = 30%
        # Balanced peer rate uses Peer1 weight=2.0, Peer2 fallback=0.5
        # (90*2 + 30*0.5) / (100*2 + 300*0.5) = 195 / 350 = 55.7143%
        self.assertAlmostEqual(impact, 25.7143, places=3)


class TestValidationAndOutputs(unittest.TestCase):
    def test_validation_hard_fail(self) -> None:
        df = pd.DataFrame({
            'issuer_name': ['A', 'B', 'C'],
            'card_type': ['A', 'A', 'A'],
            'txn_cnt': [100.0, 200.0, 300.0],
        })
        args = SimpleNamespace(
            csv='',
            df=df,
            metric='txn_cnt',
            secondary_metrics=None,
            entity='A',
            entity_col='issuer_name',
            output=None,
            dimensions=['card_type'],
            auto=False,
            time_col=None,
            config=None,
            preset=None,
            debug=False,
            log_level='INFO',
            per_dimension_weights=False,
            export_balanced_csv=False,
            validate_input=True,
            compare_presets=False,
            analyze_distortion=False,
            output_format='analysis',
            include_calculated=False,
            auto_subset_search=None,
            subset_search_max_tests=None,
            trigger_subset_on_slack=None,
            max_cap_slack=None,
        )
        import logging
        logger = logging.getLogger("test_validation")
        result = run_share_analysis(args, logger)
        self.assertEqual(result, 1, "Validation should hard-fail on insufficient peers")

    def test_publication_output_generated(self) -> None:
        df = pd.DataFrame({
            'issuer_name': ['Target', 'P1', 'P2', 'P3', 'P4', 'P5'],
            'card_type': ['A', 'A', 'A', 'A', 'A', 'A'],
            'txn_cnt': [100, 200, 300, 150, 120, 130],
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "share_test.xlsx")
            args = SimpleNamespace(
                csv='',
                df=df,
                metric='txn_cnt',
                secondary_metrics=None,
                entity='Target',
                entity_col='issuer_name',
                output=output_path,
                dimensions=['card_type'],
                auto=False,
                time_col=None,
                config=None,
                preset=None,
                debug=False,
                log_level='INFO',
                per_dimension_weights=False,
                export_balanced_csv=False,
                validate_input=False,
                compare_presets=False,
                analyze_distortion=False,
                output_format='both',
                include_calculated=False,
                auto_subset_search=None,
                subset_search_max_tests=None,
                trigger_subset_on_slack=None,
                max_cap_slack=None,
            )
            import logging
            logger = logging.getLogger("test_publication")
            result = run_share_analysis(args, logger)
            self.assertEqual(result, 0)
            self.assertTrue(os.path.exists(output_path))
            pub_path = output_path.replace(".xlsx", "_publication.xlsx")
            self.assertTrue(os.path.exists(pub_path))

    def test_publication_output_generated_multi_rate(self) -> None:
        df = pd.DataFrame({
            'issuer_name': ['Target', 'P1', 'P2', 'P3', 'P4', 'P5'],
            'card_type': ['A', 'A', 'A', 'A', 'A', 'A'],
            'total': [1000, 2000, 3000, 1500, 1200, 1300],
            'approved': [900, 1800, 2700, 1400, 1100, 1200],
            'fraud': [10, 20, 30, 15, 12, 13],
        })
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "rate_test.xlsx")
            args = SimpleNamespace(
                csv='',
                df=df,
                total_col='total',
                approved_col='approved',
                fraud_col='fraud',
                secondary_metrics=None,
                entity='Target',
                entity_col='issuer_name',
                output=output_path,
                dimensions=['card_type'],
                auto=False,
                time_col=None,
                config=None,
                preset=None,
                debug=False,
                log_level='INFO',
                per_dimension_weights=False,
                export_balanced_csv=False,
                validate_input=False,
                compare_presets=False,
                analyze_distortion=False,
                output_format='both',
                include_calculated=False,
                fraud_in_bps=True,
                auto_subset_search=None,
                subset_search_max_tests=None,
                trigger_subset_on_slack=None,
                max_cap_slack=None,
            )
            import logging
            logger = logging.getLogger("test_publication_rate")
            result = run_rate_analysis(args, logger)
            self.assertEqual(result, 0)
            self.assertTrue(os.path.exists(output_path))
            pub_path = output_path.replace(".xlsx", "_publication.xlsx")
            self.assertTrue(os.path.exists(pub_path))

    def test_preset_comparison_exhaustive(self) -> None:
        df = pd.DataFrame({
            'issuer_name': ['Target', 'P1', 'P2', 'P3', 'P4', 'P5'],
            'card_type': ['A', 'A', 'A', 'A', 'A', 'A'],
            'txn_cnt': [100, 200, 300, 150, 120, 130],
        })
        from utils.preset_manager import PresetManager
        preset_mgr = PresetManager()
        presets = preset_mgr.list_presets()
        comparison_df = run_preset_comparison(
            df=df,
            metric_col='txn_cnt',
            entity_col='issuer_name',
            dimensions=['card_type'],
            target_entity='Target',
            time_col=None,
            analysis_type='share',
            logger=__import__("logging").getLogger("test_presets")
        )
        expected = set()
        for preset in presets:
            expected.add(preset)
            expected.add(f"{preset}+perdim")
        self.assertTrue(expected.issubset(set(comparison_df['Preset'].tolist())))


class TestValidationEdgeCases:
    """Test edge cases in data validation."""

    @pytest.fixture
    def config(self):
        return ConfigManager()

    @pytest.fixture
    def data_loader(self, config):
        return DataLoader(config)

    def test_unicode_entity_names(self, data_loader):
        """Test validation with Unicode entity names."""
        df = pd.DataFrame({
            'issuer_name': ['Banco São Paulo', 'Itaú Unibanco', 'Bradesco', 'Santander', 'Nubank', 'Inter'],
            'metric': [100, 200, 150, 180, 90, 60],
            'dimension': ['A', 'A', 'B', 'B', 'A', 'B']
        })

        issues = data_loader.validate_share_input(
            df=df,
            metric_col='metric',
            entity_col='issuer_name',
            dimensions=['dimension'],
            target_entity='Banco São Paulo'
        )

        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert len(errors) == 0, f"Unicode entity names should not cause errors: {errors}"

    def test_empty_dataframe(self, data_loader):
        """Test validation with empty DataFrame."""
        df = pd.DataFrame(columns=['issuer_name', 'metric', 'dimension'])

        issues = data_loader.validate_share_input(
            df=df,
            metric_col='metric',
            entity_col='issuer_name',
            dimensions=['dimension']
        )

        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert any('peer' in str(i.message).lower() for i in errors)

    def test_null_heavy_data(self, data_loader):
        """Test validation when nulls exceed threshold."""
        df = pd.DataFrame({
            'issuer_name': ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J'],
            'metric': [100, None, None, None, None, None, 90, 80, 70, 60],
            'dimension': ['X'] * 10
        })

        issues = data_loader.validate_share_input(
            df=df,
            metric_col='metric',
            entity_col='issuer_name',
            dimensions=['dimension']
        )

        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert any('null' in str(i.message).lower() for i in errors)

    def test_rate_values_above_100_percent_are_errors(self, data_loader):
        """Test impossible computed rates are validation errors."""
        df = pd.DataFrame({
            'issuer_name': ['Target', 'P1', 'P2', 'P3', 'P4', 'P5', 'P6'],
            'card_type': ['A'] * 7,
            'total': [100, 100, 100, 100, 100, 100, 100],
            'approved': [90, 101, 80, 70, 60, 50, 40],
        })

        issues = data_loader.validate_rate_input(
            df=df,
            total_col='total',
            numerator_cols={'approval': 'approved'},
            entity_col='issuer_name',
            dimensions=['card_type'],
            target_entity='Target',
        )

        errors = [i for i in issues if i.severity == ValidationSeverity.ERROR]
        assert any(i.category == 'invalid_rates' for i in errors)


class TestPresetComparison:
    """Test preset comparison edge cases."""

    def test_empty_dimensions_list(self):
        """Test preset comparison with no dimensions."""
        import logging

        df = pd.DataFrame({
            'issuer_name': ['A', 'B', 'C', 'D', 'E'],
            'metric': [100, 200, 150, 180, 90]
        })

        result = run_preset_comparison(
            df=df,
            metric_col='metric',
            entity_col='issuer_name',
            dimensions=[],
            target_entity='A',
            time_col=None,
            analysis_type='share',
            logger=logging.getLogger()
        )

        assert result.empty, "Empty dimensions should return empty DataFrame"


class TestTimeColumnHandling:
    """Test time column edge cases."""

    def test_time_column_with_nulls(self):
        """Test impact calc when time column has None values."""
        df = pd.DataFrame({
            'issuer_name': ['A', 'B', 'A', 'B', 'A', 'B'],
            'metric': [100, 200, 150, 180, 90, 60],
            'dimension': ['X', 'X', 'X', 'X', 'Y', 'Y'],
            'period': ['2024-01', '2024-01', None, None, '2024-02', '2024-02']
        })

        analyzer = DimensionalAnalyzer(
            target_entity='A',
            entity_column='issuer_name',
            time_column='period'
        )

        result = analyzer.calculate_share_impact(
            df=df,
            metric_col='metric',
            dimensions=['dimension'],
            target_entity='A'
        )

        assert not result.empty


class TestDefensiveCalculations:
    """Test defensive handling of bad data."""

    def test_negative_values_filtered(self):
        """Test that negative values are filtered out."""
        df = pd.DataFrame({
            'issuer_name': ['A', 'B', 'C', 'D', 'E'],
            'metric': [100, -50, 150, 180, 90],
            'dimension': ['X'] * 5
        })

        analyzer = DimensionalAnalyzer(
            target_entity='A',
            entity_column='issuer_name'
        )

        result = analyzer.calculate_share_impact(
            df=df,
            metric_col='metric',
            dimensions=['dimension'],
            target_entity='A'
        )

        assert not result.empty


if __name__ == "__main__":
    unittest.main(verbosity=2)
