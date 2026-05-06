import shlex
from pathlib import Path

import pandas as pd
import pytest

from scripts.perform_gate_test import GateTestRunner


def test_gate_command_parser_preserves_quoted_entity_names() -> None:
    command = 'py benchmark.py share --entity "BANCO SANTANDER" --csv data/readme_demo.csv'

    parsed = ["/usr/bin/python3"] + shlex.split(command[3:])

    assert parsed[3] == "--entity"
    assert parsed[4] == "BANCO SANTANDER"


def test_verify_workbook_content_detects_excel_error_strings(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    workbook_path = tmp_path / "error_sheet.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "card_type"
    ws["A1"] = "Metric: card_type"
    ws["A3"] = "Category"
    ws["B3"] = "Target Share %"
    ws["A4"] = "A"
    ws["B4"] = "#DIV/0!"
    wb.save(workbook_path)

    runner = GateTestRunner(output_dir=str(tmp_path / "gate"))
    loaded = wb.__class__()
    loaded = None
    from openpyxl import load_workbook

    workbook = load_workbook(workbook_path, read_only=True, data_only=False)
    try:
        failures = runner.verify_workbook_content(workbook, "share_gate_error", "share")
    finally:
        workbook.close()

    assert any("Contains Excel errors" in failure for failure in failures)


def test_verify_case_requires_bps_headers_for_fraud_publication(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    from openpyxl import Workbook

    output_dir = tmp_path / "gate"
    output_dir.mkdir()
    analysis_path = tmp_path / "rate.xlsx"
    publication_path = tmp_path / "rate_publication.xlsx"

    for path in (analysis_path, publication_path):
        wb = Workbook()
        ws = wb.active
        ws.title = "Executive Summary" if "publication" in path.name else "Summary"
        detail = wb.create_sheet("approval_card_type")
        detail["A3"] = "Category"
        detail["B3"] = "Fraud Rate"
        detail["A4"] = "A"
        detail["B4"] = 1.25
        wb.save(path)

    runner = GateTestRunner(output_dir=str(output_dir))
    case = {
        "id": "rate_gate_bps",
        "params": {"output": str(analysis_path), "fraud_col": "fraud", "dimensions": ["approval_card_type"]},
        "expectations": ["analysis_workbook", "publication_workbook", "fraud_in_bps_in_publication"],
    }

    failures = runner.verify_case(case)

    assert "Fraud publication output is missing bps header" in failures
