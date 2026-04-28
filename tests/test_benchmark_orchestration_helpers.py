import logging
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from benchmark import _build_dimensional_analyzer, _resolve_consistency_mode
from core.analysis_run import (
    build_common_run_metadata,
    build_report_paths,
    build_run_config,
    collect_run_diagnostics,
    prepare_run_data,
    resolve_dimensions,
    resolve_entity_column,
    resolve_input_dataframe,
    resolve_output_settings,
    resolve_target_entity,
    summarize_validation_issues,
    validate_analysis_input,
    write_audit_log,
)
from core.data_loader import ValidationSeverity
from utils.config_manager import ConfigManager


class _StubLoader:
    def __init__(self, dimensions):
        self._dimensions = dimensions

    def get_available_dimensions(self, _df):
        return list(self._dimensions)

    def load_data(self, _args):
        raise AssertionError('load_data should not be called when args.df is already provided')


class TestBenchmarkOrchestrationHelpers(unittest.TestCase):
    def test_resolve_consistency_mode_defaults_to_global_on_unknown_value(self) -> None:
        opt_config = ConfigManager().config['optimization']
        opt_config = {
            **opt_config,
            'constraints': {
                **opt_config['constraints'],
                'consistency_mode': 'mystery-mode',
            },
        }

        with self.assertLogs(level='WARNING') as captured:
            consistent_weights, consistency_mode = _resolve_consistency_mode(opt_config, logging.getLogger(__name__))

        self.assertTrue(consistent_weights)
        self.assertEqual(consistency_mode, 'mystery-mode')
        self.assertTrue(any('Unknown consistency_mode' in msg for msg in captured.output))

    def test_build_dimensional_analyzer_uses_configured_consistency_mode(self) -> None:
        config = ConfigManager()
        opt_config = config.config['optimization']
        analysis_config = config.config['analysis']
        opt_config = {
            **opt_config,
            'constraints': {
                **opt_config['constraints'],
                'consistency_mode': 'per_dimension',
            },
        }

        analyzer, settings = _build_dimensional_analyzer(
            target_entity='Target',
            entity_col='issuer_name',
            analysis_config=analysis_config,
            opt_config=opt_config,
            time_col=None,
            debug_mode=False,
            bic_percentile=0.85,
            logger=logging.getLogger(__name__),
        )

        self.assertFalse(analyzer.consistent_weights)
        self.assertFalse(settings['consistent_weights'])
        self.assertEqual(settings['consistency_mode'], 'per_dimension')

    def test_build_dimensional_analyzer_respects_explicit_consistency_override(self) -> None:
        config = ConfigManager()
        opt_config = config.config['optimization']
        analysis_config = config.config['analysis']

        analyzer, settings = _build_dimensional_analyzer(
            target_entity='Target',
            entity_col='issuer_name',
            analysis_config=analysis_config,
            opt_config=opt_config,
            time_col='year_month',
            debug_mode=True,
            bic_percentile=0.9,
            logger=logging.getLogger(__name__),
            consistent_weights=False,
        )

        self.assertFalse(analyzer.consistent_weights)
        self.assertEqual(analyzer.time_column, 'year_month')
        self.assertTrue(analyzer.debug_mode)
        self.assertEqual(analyzer.bic_percentile, 0.9)
        self.assertFalse(settings['consistent_weights'])
        self.assertIn('dynamic_constraints_config', settings)

    def test_resolve_target_entity_normalizes_case(self) -> None:
        df = pd.DataFrame({'issuer_name': ['Target', 'Peer1']})

        with self.assertLogs(level='WARNING') as captured:
            resolved = resolve_target_entity(df, 'issuer_name', 'target', logging.getLogger(__name__))

        self.assertEqual(resolved, 'Target')
        self.assertTrue(any('case mismatch' in msg for msg in captured.output))

    def test_resolve_target_entity_returns_none_for_ambiguous_match(self) -> None:
        df = pd.DataFrame({'issuer_name': ['Target', 'TARGET', 'Peer1']})

        with self.assertLogs(level='ERROR') as captured:
            resolved = resolve_target_entity(df, 'issuer_name', 'target', logging.getLogger(__name__))

        self.assertIsNone(resolved)
        self.assertTrue(any('Ambiguous entity name' in msg for msg in captured.output))

    def test_resolve_dimensions_prefers_explicit_list(self) -> None:
        args = SimpleNamespace(dimensions=['card_type'], auto=False)
        config = ConfigManager()
        loader = _StubLoader(['channel'])
        df = pd.DataFrame({'card_type': ['A']})

        dimensions = resolve_dimensions(args, config, loader, df, logging.getLogger(__name__))

        self.assertEqual(dimensions, ['card_type'])

    def test_resolve_dimensions_uses_auto_detection_when_enabled(self) -> None:
        args = SimpleNamespace(dimensions=None, auto=True)
        config = ConfigManager()
        loader = _StubLoader(['card_type', 'channel'])
        df = pd.DataFrame({'card_type': ['A'], 'channel': ['POS']})

        dimensions = resolve_dimensions(args, config, loader, df, logging.getLogger(__name__))

        self.assertEqual(dimensions, ['card_type', 'channel'])

    def test_resolve_dimensions_returns_none_when_no_source_is_available(self) -> None:
        args = SimpleNamespace(dimensions=None, auto=False)
        config = ConfigManager()
        loader = _StubLoader(['card_type'])
        df = pd.DataFrame({'card_type': ['A']})

        with self.assertLogs(level='ERROR') as captured:
            dimensions = resolve_dimensions(args, config, loader, df, logging.getLogger(__name__))

        self.assertIsNone(dimensions)
        self.assertTrue(any('No dimensions provided' in msg for msg in captured.output))

    def test_resolve_entity_column_uses_standard_fallbacks(self) -> None:
        df = pd.DataFrame({'issuer_name': ['A'], 'metric': [1]})

        entity_col = resolve_entity_column(df, 'missing_col')

        self.assertEqual(entity_col, 'issuer_name')

    def test_resolve_input_dataframe_prefers_preloaded_dataframe(self) -> None:
        expected_df = pd.DataFrame({'metric': [1]})
        args = SimpleNamespace(df=expected_df)

        result_df = resolve_input_dataframe(args, _StubLoader(['ignored']))

        self.assertIs(result_df, expected_df)

    def test_build_run_config_applies_common_and_extra_overrides(self) -> None:
        args = SimpleNamespace(
            config=None,
            preset=None,
            entity_col='issuer_name',
            time_col='year_month',
            debug=True,
            log_level='DEBUG',
            per_dimension_weights=False,
            auto=True,
            auto_subset_search=True,
            subset_search_max_tests=50,
            trigger_subset_on_slack=True,
            max_cap_slack=1.5,
            validate_input=False,
            compare_presets=True,
            analyze_impact=None,
            analyze_distortion=True,
            output_format='publication',
            include_calculated=True,
        )

        config = build_run_config(args, extra_overrides={'fraud_in_bps': False})

        self.assertEqual(config.get('input', 'entity_col'), 'issuer_name')
        self.assertEqual(config.get('input', 'time_col'), 'year_month')
        self.assertEqual(config.get('output', 'log_level'), 'DEBUG')
        self.assertTrue(config.get('analysis', 'auto_detect_dimensions'))
        self.assertTrue(config.get('output', 'include_preset_comparison'))
        self.assertFalse(config.get('output', 'fraud_in_bps'))

    def test_resolve_output_settings_supports_legacy_distortion_flag(self) -> None:
        config = ConfigManager()
        config.config['output']['include_impact_summary'] = None
        config.config['output']['include_distortion_summary'] = True

        settings = resolve_output_settings(config)

        self.assertTrue(settings['include_impact_summary'])
        self.assertIn('output_format', settings)

    def test_prepare_run_data_uses_loader_and_resolves_entity_column(self) -> None:
        config = ConfigManager()
        config.config['input']['time_col'] = 'year_month'
        args = SimpleNamespace(df=None)
        loaded_df = pd.DataFrame({'issuer_name': ['A'], 'year_month': ['2025-01'], 'metric': [1]})

        class _FakeLoader:
            def __init__(self, _config):
                self.config = _config

            def load_data(self, _args):
                return loaded_df

        with patch('core.analysis_run.DataLoader', _FakeLoader):
            loader, df, entity_col, time_col = prepare_run_data(
                args,
                config,
                logging.getLogger(__name__),
                preferred_entity_col='missing_col',
            )

        self.assertEqual(entity_col, 'issuer_name')
        self.assertEqual(time_col, 'year_month')
        self.assertIs(df, loaded_df)
        self.assertIsInstance(loader, _FakeLoader)

    def test_validate_analysis_input_defaults_dimensions_from_loader(self) -> None:
        config = ConfigManager()
        df = pd.DataFrame({'issuer_name': ['A'], 'card_type': ['X'], 'metric': [1]})
        loader = _StubLoader(['card_type'])

        with patch('core.analysis_run.run_input_validation', return_value=(['ok'], False)) as mocked:
            issues, should_abort = validate_analysis_input(
                df=df,
                config=config,
                data_loader=loader,
                analysis_type='share',
                entity_col='issuer_name',
                time_col=None,
                target_entity='A',
                metric_col='metric',
            )

        self.assertEqual(issues, ['ok'])
        self.assertFalse(should_abort)
        self.assertEqual(mocked.call_args.kwargs['dimensions'], ['card_type'])

    def test_build_common_run_metadata_includes_shared_analyzer_fields(self) -> None:
        config = ConfigManager()
        analyzer = SimpleNamespace(
            rank_preservation_strength=0.75,
            privacy_rule_name='MC-3.2',
            enforce_additional_constraints=True,
            additional_constraint_violations=['a', 'b'],
            dynamic_constraints_enabled=True,
            dynamic_constraint_stats={'applied': 4},
            get_structural_infeasibility_summary=lambda: {'count': 1},
        )
        args = SimpleNamespace(
            preset='balanced',
            csv='input.csv',
            log_level='INFO',
            dimensions=['channel'],
            auto=False,
            entity_col='issuer_name',
        )

        metadata = build_common_run_metadata(
            args,
            config,
            analyzer,
            resolved_entity='Target',
            entity_col='issuer_name',
            total_records=100,
            unique_entities=5,
            dimensions_analyzed=2,
            dimension_names=['channel', 'product'],
            secondary_metrics=['amount'],
            debug_mode=True,
            consistent_weights=True,
            include_privacy_validation=True,
            include_impact_summary=False,
            include_preset_comparison=True,
            include_calculated_metrics=False,
            output_format='analysis',
            consistency_mode='global',
            enforce_single_weight_set=True,
        )

        self.assertEqual(metadata['entity'], 'Target')
        self.assertEqual(metadata['peer_count'], 4)
        self.assertEqual(metadata['privacy_rule'], 'MC-3.2')
        self.assertTrue(metadata['additional_constraints_enforced'])
        self.assertEqual(metadata['additional_constraint_violations_count'], 2)
        self.assertTrue(metadata['dynamic_constraints_enabled'])
        self.assertEqual(metadata['dynamic_constraints_stats'], {'applied': 4})
        self.assertEqual(metadata['structural_infeasibility_summary'], {'count': 1})
        self.assertEqual(metadata['dimension_names'], ['channel', 'product'])

    def test_collect_run_diagnostics_builds_shared_artifacts(self) -> None:
        weights_df = pd.DataFrame({'peer': ['A'], 'weight': [0.5]})
        privacy_df = pd.DataFrame({
            'Dimension': ['channel', 'channel'],
            'Category': ['POS', 'POS'],
            'Time_Period': ['2025-01', '2025-01'],
            'Structural_Infeasible_Category': ['Yes', 'Yes'],
        })
        analyzer = SimpleNamespace(
            get_weights_dataframe=lambda: weights_df,
            build_privacy_validation_dataframe=lambda _df, _metric_col, _dimensions: privacy_df,
            global_dimensions_used=['channel'],
            removed_dimensions=['product'],
            per_dimension_weights={'merchant': {'PeerA': 1.2}},
            weight_methods={'channel': 'Global-LP'},
            global_weights={'PeerA': {'multiplier': 1.1, 'weight': 50.0}},
        )

        diagnostics = collect_run_diagnostics(
            analyzer=analyzer,
            df=pd.DataFrame({'metric': [1]}),
            validation_metric_col='metric',
            dimensions=['channel', 'merchant', 'product'],
            debug_mode=True,
            include_privacy_validation=True,
            export_csv=False,
            consistent_weights=True,
            logger=logging.getLogger(__name__),
        )

        self.assertIs(diagnostics['weights_df'], weights_df)
        self.assertIs(diagnostics['privacy_validation_df'], privacy_df)
        self.assertEqual(diagnostics['metadata_updates']['structural_infeasible_validation_rows'], 2)
        self.assertEqual(diagnostics['metadata_updates']['structural_infeasible_validation_categories'], 1)
        self.assertFalse(diagnostics['method_breakdown_df'].empty)
        self.assertIn('Method', diagnostics['method_breakdown_df'].columns)

    def test_build_report_paths_respects_output_mode(self) -> None:
        report_paths = build_report_paths('both', 'analysis.xlsx', 'publication.xlsx')

        self.assertEqual(report_paths, ['analysis.xlsx', 'publication.xlsx'])

    def test_summarize_validation_issues_counts_each_severity(self) -> None:
        validation_issues = [
            SimpleNamespace(severity=ValidationSeverity.ERROR),
            SimpleNamespace(severity=ValidationSeverity.WARNING),
            SimpleNamespace(severity=ValidationSeverity.WARNING),
            SimpleNamespace(severity=ValidationSeverity.INFO),
        ]

        summary = summarize_validation_issues(validation_issues)

        self.assertEqual(summary['validation_errors'], 1)
        self.assertEqual(summary['validation_warnings'], 2)
        self.assertEqual(summary['validation_infos'], 1)

    def test_write_audit_log_omits_analyzer_ref_and_uses_report_summary(self) -> None:
        config = ConfigManager()
        metadata = {
            'privacy_rule': 'MC-3.2',
            'impact_summary': {'mean_abs_impact_pp': 1.25},
            'additional_constraint_violations_count': 3,
            'analyzer_ref': object(),
        }
        impact_df = pd.DataFrame({'Dimension': ['channel']})
        privacy_validation_df = pd.DataFrame({'rule': ['ok'], 'status': ['pass']})
        validation_issues = [SimpleNamespace(severity=ValidationSeverity.ERROR)]

        with patch('core.analysis_run.ReportGenerator') as report_generator_cls:
            audit_log_file = write_audit_log(
                config,
                analysis_output_file='benchmark_share_target.xlsx',
                metadata=metadata,
                report_paths=['benchmark_share_target.xlsx', 'benchmark_share_target_publication.xlsx'],
                dimensions_analyzed=4,
                csv_output='benchmark_share_target_balanced.csv',
                impact_df=impact_df,
                privacy_validation_df=privacy_validation_df,
                validation_issues=validation_issues,
            )

        report_generator_cls.assert_called_once_with(config)
        create_log = report_generator_cls.return_value.create_audit_log
        create_log.assert_called_once()
        called_log_file, called_metadata, called_summary = create_log.call_args.args
        self.assertEqual(audit_log_file, 'benchmark_share_target_audit.log')
        self.assertEqual(called_log_file, 'benchmark_share_target_audit.log')
        self.assertNotIn('analyzer_ref', called_metadata)
        self.assertEqual(called_summary['dimensions_analyzed'], 4)
        self.assertEqual(called_summary['privacy_validation_rows'], 1)
        self.assertEqual(called_summary['validation_errors'], 1)
        self.assertEqual(called_summary['outputs'], ['benchmark_share_target.xlsx', 'benchmark_share_target_publication.xlsx'])


if __name__ == '__main__':
    unittest.main()
