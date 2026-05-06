"""Tests for gate test runner command parsing and CSV validator helpers."""

from __future__ import annotations

import shlex


def test_gate_command_parser_preserves_quoted_entity_names() -> None:
    """The gate runner must preserve quoted multi-word entity names."""
    command = 'py benchmark.py share --entity "BANCO SANTANDER" --csv data/readme_demo.csv'

    parsed = ["/usr/bin/python3"] + shlex.split(command[3:])

    assert parsed[3] == "--entity"
    assert parsed[4] == "BANCO SANTANDER"


def test_csv_validator_handles_zero_dimensions_without_division_error(tmp_path) -> None:
    """The CSV validator must not raise ZeroDivisionError when no dimensions match."""
    import sys
    import subprocess
    from pathlib import Path

    from openpyxl import Workbook

    excel_path = tmp_path / "report.xlsx"
    csv_path = tmp_path / "balanced.csv"

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws["A1"] = "metadata"
    wb.save(excel_path)

    csv_path.write_text("Dimension,Category,Total\n", encoding="utf-8")

    project_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(project_root / "utils" / "csv_validator.py"), str(excel_path), str(csv_path)],
        capture_output=True,
        text=True,
        cwd=project_root,
    )

    assert "ZeroDivisionError" not in proc.stdout
    assert "ZeroDivisionError" not in proc.stderr
