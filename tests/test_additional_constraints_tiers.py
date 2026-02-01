"""
Unit tests for tier-based dynamic additional-constraint evaluation.
"""

import unittest

from core.dimensional_analyzer import DimensionalAnalyzer


class TestTierThresholds(unittest.TestCase):
    def setUp(self) -> None:
        # Minimal analyzer instance; config is not needed for this private method.
        self.analyzer = DimensionalAnalyzer(target_entity=None)

    def test_tier_thresholds_pass(self) -> None:
        shares = [20.0, 16.0, 9.0, 5.0]
        thresholds = {
            "tier_1": (2, 15.0),
            "tier_2": (1, 8.0),
        }

        passed, details = self.analyzer._evaluate_additional_constraints(
            shares, "7/35", thresholds
        )

        self.assertTrue(passed)
        self.assertEqual(details, [])

    def test_tier_thresholds_fail(self) -> None:
        shares = [20.0, 14.0, 7.5, 5.0]
        thresholds = {
            "tier_1": (2, 15.0),
            "tier_2": (1, 8.0),
        }

        passed, details = self.analyzer._evaluate_additional_constraints(
            shares, "7/35", thresholds
        )

        self.assertFalse(passed)
        self.assertTrue(details)


if __name__ == "__main__":
    unittest.main(verbosity=2)
