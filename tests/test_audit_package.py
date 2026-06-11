"""Unit tests for audit package credential redaction."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

from core.audit_package import _redact_secrets, write_audit_package

_DUMMY_SECRET = "dummy-not-a-real-secret"


def test_redact_secrets_sql_keys() -> None:
    config = {
        "sql": {
            "connection_string": _DUMMY_SECRET,
            "pwd": _DUMMY_SECRET,
            "server": "host1",
        }
    }
    result = _redact_secrets(config)
    assert result["sql"]["connection_string"] == "***REDACTED***"
    assert result["sql"]["pwd"] == "***REDACTED***"
    assert result["sql"]["server"] == "host1"


def test_redact_secrets_nested() -> None:
    config = {
        "outer": {
            "inner": {
                "pwd": _DUMMY_SECRET,
                "name": "visible",
            }
        }
    }
    result = _redact_secrets(config)
    assert result["outer"]["inner"]["pwd"] == "***REDACTED***"
    assert result["outer"]["inner"]["name"] == "visible"


def test_write_audit_package_redacts_secrets_in_snapshot(tmp_path: Path) -> None:
    analysis_output = tmp_path / "run.xlsx"
    analysis_output.touch()

    package_path = write_audit_package(
        analysis_output_file=str(analysis_output),
        report_paths=[],
        csv_output=None,
        audit_log_output=None,
        config_snapshot={"sql": {"pwd": _DUMMY_SECRET, "server": "host1"}},
        metadata={},
    )

    with zipfile.ZipFile(package_path) as zf:
        snapshot_text = zf.read("config_snapshot.json").decode()

    assert _DUMMY_SECRET not in snapshot_text
    assert "***REDACTED***" in snapshot_text
    assert "host1" in snapshot_text


def test_redact_secrets_preserves_non_secret_config() -> None:
    config = {"optimization": {"linear_programming": {"tolerance": 2.0}}}
    assert _redact_secrets(config) == config


def test_write_audit_package_non_secret_config_round_trips(tmp_path: Path) -> None:
    analysis_output = tmp_path / "run.xlsx"
    analysis_output.touch()
    config = {"optimization": {"linear_programming": {"tolerance": 2.0}}}

    package_path = write_audit_package(
        analysis_output_file=str(analysis_output),
        report_paths=[],
        csv_output=None,
        audit_log_output=None,
        config_snapshot=config,
        metadata={},
    )

    with zipfile.ZipFile(package_path) as zf:
        snapshot = json.loads(zf.read("config_snapshot.json"))

    assert snapshot == config
