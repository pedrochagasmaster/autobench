"""
Unit tests for ReportGenerator dependency handling.
"""

import unittest
from unittest.mock import MagicMock, patch

from openpyxl import Workbook

from core.data_loader import ValidationIssue, ValidationSeverity
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

    def test_data_quality_sheet_renders_structured_issue_details(self) -> None:
        workbook = Workbook()
        generator = ReportGenerator(MagicMock())
        issue = ValidationIssue(
            severity=ValidationSeverity.WARNING,
            category="low_denominator",
            message="4 rows have denominator below 100 - rates may be unstable.",
            row_indices=[0, 1, 3, 5],
            details={
                "column": "total",
                "threshold": 100,
                "affected_rows": 4,
                "affected_categories": {
                    "dimension": {
                        "Small": 2,
                        "<missing>": 2,
                    }
                },
            },
        )

        generator.add_data_quality_sheet(workbook, [issue], passed=True)

        sheet = workbook["Data Quality"]
        headers = [cell.value for cell in sheet[7]]
        self.assertEqual(headers[:5], ["Severity", "Category", "Message", "Details", "Sample Rows"])
        self.assertEqual(sheet["B8"].value, "low_denominator")
        self.assertIn('"affected_rows": 4', sheet["D8"].value)
        self.assertEqual(sheet["E8"].value, "0, 1, 3, 5")

    def test_data_quality_sheet_has_standard_headers_when_clean(self) -> None:
        workbook = Workbook()
        generator = ReportGenerator(MagicMock())

        generator.add_data_quality_sheet(workbook, [], passed=True)

        sheet = workbook["Data Quality"]
        self.assertEqual(sheet["A5"].value, "Errors: 0 | Warnings: 0 | Info: 0")
        self.assertEqual(sheet["A6"].value, "No issues detected.")
        headers = [cell.value for cell in sheet[7]]
        self.assertEqual(headers[:5], ["Severity", "Category", "Message", "Details", "Sample Rows"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
