import shlex
from pathlib import Path

from openpyxl import Workbook

from scripts.perform_gate_test import GateTestRunner


def test_gate_command_parser_preserves_quoted_entity_names() -> None:
    command = 'py benchmark.py share --entity "BANCO SANTANDER" --csv data/readme_demo.csv'

    parsed = ["/usr/bin/python3"] + shlex.split(command[3:])

    assert parsed[3] == "--entity"
    assert parsed[4] == "BANCO SANTANDER"


def test_verify_case_flags_missing_bps_headers(tmp_path: Path) -> None:
    analysis = tmp_path / "rate.xlsx"
    publication = tmp_path / "rate_publication.xlsx"

    analysis_wb = Workbook()
    analysis_ws = analysis_wb.active
    analysis_ws.title = "Summary"
    analysis_wb.save(analysis)
    analysis_wb.close()

    pub_wb = Workbook()
    pub_ws = pub_wb.active
    pub_ws.title = "Executive Summary"
    data_ws = pub_wb.create_sheet("approval_card_type")
    data_ws["A3"] = "Category"
    data_ws["B3"] = "Fraud Rate"
    data_ws["A4"] = "A"
    data_ws["B4"] = 1.23
    pub_wb.save(publication)
    pub_wb.close()

    runner = GateTestRunner(output_dir=str(tmp_path / "gate"))
    case = {
        "id": "rate_publication_bps",
        "params": {"output": str(analysis)},
        "expectations": ["publication_workbook", "fraud_in_bps_in_publication"],
    }

    failures = runner.verify_case(case)

    assert "Fraud publication output is missing bps header" in failures
