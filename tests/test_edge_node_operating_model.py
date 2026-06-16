from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_OPERATING_MODEL_FILES = [
    "install.sh",
    "onboarding.md",
    "VERSION",
    ".gitattributes",
    "docs/development-workflow.md",
    "docs/edge-node-first-time-setup.md",
    "docs/production-testing.md",
    "docs/edge-node-tui-operating-model.md",
    "tools/dev/local_check.ps1",
    "tools/dev/git_sync_status.ps1",
    "tools/prod_tui/README.md",
    "tools/prod_tui/__init__.py",
    "tools/prod_tui/__main__.py",
    "tools/prod_tui/harness.py",
    "tools/prod_tui/config-template.yaml",
]


@pytest.mark.parametrize("relative_path", REQUIRED_OPERATING_MODEL_FILES)
def test_edge_node_operating_model_artifacts_exist(relative_path: str) -> None:
    assert (ROOT / relative_path).is_file(), relative_path


def test_linux_bound_files_are_normalized_to_lf() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")

    assert "*.py text eol=lf" in attributes
    assert "*.sh text eol=lf" in attributes
    assert "*.ps1 text eol=crlf" in attributes


def test_generated_prod_tui_artifacts_are_ignored() -> None:
    ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "tools/prod_tui/screens/" in ignore
    assert "tools/prod_tui/reports/" in ignore
    assert "tools/prod_tui/logs/" in ignore
    assert "tools/prod_tui/*.log" in ignore


def test_installer_contract_is_autobench_specific() -> None:
    install = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "AUTOBENCH_DATA_ROOT" in install
    assert 'AUTOBENCH_HOME="$DATA_ROOT/.autobench"' in install
    assert 'cat > "$LOCAL_BIN/autobench"' in install
    assert "exec \"$AUTOBENCH_HOME/venv/bin/python\" \"$ROOT_DIR/tui_app.py\"" in install
    assert "cp \"$ROOT_DIR/VERSION\" \"$AUTOBENCH_HOME/installed_version\"" in install


def test_production_harness_help_runs() -> None:
    result = subprocess.run(
        ["py", "-m", "tools.prod_tui"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "Commands:" in result.stdout
    assert "smoke" in result.stdout
    assert "drift" in result.stdout


def test_prod_tui_report_redacts_sensitive_values(tmp_path: Path) -> None:
    from tools.prod_tui.harness import CheckResult, write_report

    report = write_report(
        tmp_path / "report.json",
        node="edge-node",
        repo_path="/ads_storage/autobench",
        commit="deadbeef",
        version="3.0",
        checks=[
            CheckResult(
                name="auth",
                status="fail",
                failure_class="environment",
                output=("tok" "en=abc pass" "word=def PASS" "CODE=123456 normal text"),
            )
        ],
    )

    body = report.read_text(encoding="utf-8")
    assert "normal text" in body
    assert "abc" not in body
    assert "def" not in body
    assert "123456" not in body
    assert "***REDACTED***" in body


def test_drift_manifest_ignores_generated_paths(tmp_path: Path) -> None:
    from tools.prod_tui.harness import build_manifest

    (tmp_path / "core").mkdir()
    (tmp_path / "tools" / "prod_tui" / "reports").mkdir(parents=True)
    (tmp_path / "core" / "engine.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "install.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (tmp_path / "tools" / "prod_tui" / "reports" / "run.json").write_text("{}", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "engine.pyc").write_bytes(b"ignored")

    manifest = build_manifest(tmp_path)

    assert sorted(manifest) == ["core/engine.py", "install.sh"]


def test_local_check_references_repo_gate_commands() -> None:
    script = (ROOT / "tools/dev/local_check.ps1").read_text(encoding="utf-8")

    assert "py -m compileall" in script
    assert "py -m ruff check ." in script
    assert "py -m mypy core/ utils/" in script
    assert "py scripts/perform_gate_test.py" in script
    assert "py -m pytest" in script


def test_autobench_bitbucket_remote_is_documented() -> None:
    docs = "\n".join(
        [
            (ROOT / "docs/development-workflow.md").read_text(encoding="utf-8"),
            (ROOT / "docs/edge-node-first-time-setup.md").read_text(encoding="utf-8"),
        ]
    )

    assert "https://scm.mastercard.int/stash/scm/~e176097/dispatch.git" in docs
    assert "/ads_storage/autobench" in docs
    assert "/ads_storage/$USER/.autobench" in docs
