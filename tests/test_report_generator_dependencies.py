"""
Unit tests for ReportGenerator dependency handling.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.report_generator import ReportGenerator


class TestReportGeneratorDependencies(unittest.TestCase):
    def test_generate_report_requires_openpyxl(self) -> None:
        generator = ReportGenerator(MagicMock())

        real_import = __import__

        def guarded_import(name, *args, **kwargs):
            if name == "openpyxl":
                raise ImportError("No module named 'openpyxl'")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded_import):
            with self.assertRaises(ImportError) as ctx:
                generator.generate_report(
                    results={},
                    output_file="dummy.xlsx",
                    format="excel",
                    analysis_type="share",
                    metadata=None,
                )

        self.assertIn("openpyxl", str(ctx.exception))

    def test_unique_sheet_name_avoids_collisions(self) -> None:
        existing = ["Metric_1_abcdefghijklmnopqrstuvwxyz", "Metric_1_abcdefghijklmnopqrstuvwx_1"]
        name = ReportGenerator._build_unique_sheet_name("Metric_1_abcdefghijklmnopqrstuvwxyz", existing)
        self.assertNotIn(name, existing)
        self.assertLessEqual(len(name), 31)

    def test_rate_column_conversion_detection(self) -> None:
        self.assertTrue(ReportGenerator._should_convert_rate_column("fraud_Raw_%", convert_all_rates=False))
        self.assertFalse(ReportGenerator._should_convert_rate_column("approval_Impact_PP", convert_all_rates=True))


if __name__ == "__main__":
    unittest.main(verbosity=2)
