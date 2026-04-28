import logging
import unittest

from benchmark import _build_dimensional_analyzer, _resolve_consistency_mode
from utils.config_manager import ConfigManager


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


if __name__ == '__main__':
    unittest.main()
