import logging
import unittest
from types import SimpleNamespace

import pandas as pd

from benchmark import (
    _build_dimensional_analyzer,
    _resolve_consistency_mode,
    _resolve_dimensions,
    _resolve_target_entity,
)
from utils.config_manager import ConfigManager


class _StubLoader:
    def __init__(self, dimensions):
        self._dimensions = dimensions

    def get_available_dimensions(self, _df):
        return list(self._dimensions)


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
            resolved = _resolve_target_entity(df, 'issuer_name', 'target', logging.getLogger(__name__))

        self.assertEqual(resolved, 'Target')
        self.assertTrue(any('case mismatch' in msg for msg in captured.output))

    def test_resolve_target_entity_returns_none_for_ambiguous_match(self) -> None:
        df = pd.DataFrame({'issuer_name': ['Target', 'TARGET', 'Peer1']})

        with self.assertLogs(level='ERROR') as captured:
            resolved = _resolve_target_entity(df, 'issuer_name', 'target', logging.getLogger(__name__))

        self.assertIsNone(resolved)
        self.assertTrue(any('Ambiguous entity name' in msg for msg in captured.output))

    def test_resolve_dimensions_prefers_explicit_list(self) -> None:
        args = SimpleNamespace(dimensions=['card_type'], auto=False)
        config = ConfigManager()
        loader = _StubLoader(['channel'])
        df = pd.DataFrame({'card_type': ['A']})

        dimensions = _resolve_dimensions(args, config, loader, df, logging.getLogger(__name__))

        self.assertEqual(dimensions, ['card_type'])

    def test_resolve_dimensions_uses_auto_detection_when_enabled(self) -> None:
        args = SimpleNamespace(dimensions=None, auto=True)
        config = ConfigManager()
        loader = _StubLoader(['card_type', 'channel'])
        df = pd.DataFrame({'card_type': ['A'], 'channel': ['POS']})

        dimensions = _resolve_dimensions(args, config, loader, df, logging.getLogger(__name__))

        self.assertEqual(dimensions, ['card_type', 'channel'])

    def test_resolve_dimensions_returns_none_when_no_source_is_available(self) -> None:
        args = SimpleNamespace(dimensions=None, auto=False)
        config = ConfigManager()
        loader = _StubLoader(['card_type'])
        df = pd.DataFrame({'card_type': ['A']})

        with self.assertLogs(level='ERROR') as captured:
            dimensions = _resolve_dimensions(args, config, loader, df, logging.getLogger(__name__))

        self.assertIsNone(dimensions)
        self.assertTrue(any('No dimensions provided' in msg for msg in captured.output))


if __name__ == '__main__':
    unittest.main()
