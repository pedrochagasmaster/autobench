import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.perform_gate_test import GateTestRunner


def test_gate_command_parser_preserves_quoted_entity_names(
    monkeypatch,
    tmp_path: Path,
) -> None:
    captured = {}

    runner = GateTestRunner(output_dir=str(tmp_path / "gate"))

    monkeypatch.setattr(runner, "generate_cases", lambda: None)
    monkeypatch.setattr(
        runner,
        "load_cases",
        lambda: [
            {
                "id": "quoted-entity",
                "command": 'py benchmark.py share --entity "BANCO SANTANDER" --csv data/readme_demo.csv',
                "expectations": [],
            }
        ],
    )
    monkeypatch.setattr(runner, "verify_case", lambda case: [])

    def fake_run(cmd_list, cwd=None, capture_output=None, text=None, timeout=None):
        captured["cmd_list"] = list(cmd_list)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr("scripts.perform_gate_test.subprocess.run", fake_run)

    with pytest.raises(SystemExit) as exc_info:
        runner.run()

    assert exc_info.value.code == 0

    assert captured["cmd_list"][3] == "--entity"
    assert captured["cmd_list"][4] == "BANCO SANTANDER"
