from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]


REQUIRED_OPERATING_MODEL_FILES = [
    "install.sh",
    "onboarding.md",
    "VERSION",
    ".gitattributes",
    "docs/release-workflow.md",
    "docs/edge-node-first-time-setup.md",
    "docs/production-testing.md",
    "tools/dev/local_check.ps1",
    "tools/dev/git_sync_status.ps1",
    "tools/dev/publish_bitbucket_snapshot.ps1",
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
        [sys.executable, "-m", "tools.prod_tui"],
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


def test_prod_tui_config_template_includes_session_and_auth_fields() -> None:
    template = (ROOT / "tools/prod_tui/config-template.yaml").read_text(encoding="utf-8")

    assert 'session_name: "autobench-prod-test"' in template
    assert 'pane_target: ""' in template
    assert 'auth_state: "ready"' in template
    assert "human_takeover_required: false" in template
    assert 'update_method: "update.sh"' in template
    assert 'install_decision: "install not required"' in template
    assert 'dependency_signal: ""' in template
    assert 'permission_evidence: []' in template


def test_prod_tui_docs_cover_tmux_preflight_and_passcode_boundary() -> None:
    docs = "\n".join(
        [
            (ROOT / "docs/production-testing.md").read_text(encoding="utf-8"),
            (ROOT / "tools/prod_tui/README.md").read_text(encoding="utf-8"),
        ]
    )

    assert "tmux capture-pane" in docs
    assert "PASSCODE" in docs
    assert "human takeover" in docs or "humans enter credentials" in docs
    assert "--remote /ads_storage/autobench" in docs
    assert "not yet" in docs and "implemented" in docs


def test_prod_tui_report_records_session_and_auth_metadata(tmp_path: Path) -> None:
    from tools.prod_tui.harness import CheckResult, write_report

    report = write_report(
        tmp_path / "report.json",
        node="node04",
        repo_path="/ads_storage/autobench",
        commit="deadbeef",
        version="3.0",
        checks=[CheckResult(name="wrapper", status="pass")],
        config_name="config-node04.yaml",
        session_name="autobench-prod-test",
        pane_target="autobench:0.0",
        auth_state="handoff",
        human_takeover_required=True,
        source_commit="abc1234",
        bitbucket_snapshot_sha="def5678",
        deployed_commit="fedcba9",
        runtime_python={"path": "/sys_apps_01/python/python310/bin/python3.10", "version": "Python 3.10.14"},
        update_method="update.sh",
        install_decision="install recommended",
        dependency_signal="VERSION changed",
        drift={"status": "not_implemented", "manifest_path": "tools/prod_tui/reports/drift.json"},
        smoke={"level": "2", "report_path": "tools/prod_tui/reports/smoke.json"},
        wrapper_checks={
            "config_list": "pass",
            "share_help": "pass",
        },
        permission_evidence=[
            "ls -ld /ads_storage/autobench -> drwxr-xr-x",
            "ls -l /ads_storage/autobench/*.sh -> all executable",
        ],
        summary_line="SUMMARY node=node04 status=pass auth=handoff handoff=yes",
    )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["config_name"] == "config-node04.yaml"
    assert payload["session_name"] == "autobench-prod-test"
    assert payload["pane_target"] == "autobench:0.0"
    assert payload["auth_state"] == "handoff"
    assert payload["human_takeover_required"] is True
    assert payload["source_commit"] == "abc1234"
    assert payload["bitbucket_snapshot_sha"] == "def5678"
    assert payload["deployed_commit"] == "fedcba9"
    assert payload["runtime_python"]["version"] == "Python 3.10.14"
    assert payload["update_method"] == "update.sh"
    assert payload["install_decision"] == "install recommended"
    assert payload["dependency_signal"] == "VERSION changed"
    assert payload["drift"]["manifest_path"] == "tools/prod_tui/reports/drift.json"
    assert payload["smoke"]["level"] == "2"
    assert payload["wrapper_checks"]["share_help"] == "pass"
    assert payload["permission_evidence"][0].startswith("ls -ld /ads_storage/autobench")
    assert payload["summary_line"] == "SUMMARY node=node04 status=pass auth=handoff handoff=yes"


def test_drift_records_remote_limitation_and_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from tools.prod_tui.harness import drift

    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "engine.py").write_text("print('ok')\n", encoding="utf-8")
    output = tmp_path / "drift.json"

    exit_code = drift(
        SimpleNamespace(
            local=str(tmp_path),
            remote="/ads_storage/autobench",
            output=str(output),
        )
    )

    captured = capsys.readouterr()
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["remote_path"] == "/ads_storage/autobench"
    assert payload["remote_comparison"]["status"] == "not_implemented"
    assert "REMOTE_NOT_COMPARED" in captured.out
    assert "DRIFT=0" not in captured.out
    assert "IN_SYNC" not in captured.out
    assert "SUMMARY local=" in captured.out


def test_smoke_uses_configured_report_contract_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tools.prod_tui import harness

    config_path = tmp_path / "config.yaml"
    report_path = tmp_path / "smoke.json"
    config_path.write_text(
        "\n".join(
            [
                'host: "node04"',
                'repo_path: "/ads_storage/autobench"',
                'session_name: "autobench-prod-test"',
                'pane_target: "autobench:0.0"',
                'auth_state: "handoff"',
                'human_takeover_required: true',
                'source_commit: "abc1234"',
                'bitbucket_snapshot_sha: "def5678"',
                'deployed_commit: "fedcba9"',
                'runtime_python_path: "/sys_apps_01/python/python310/bin/python3.10"',
                'runtime_python_version: "Python 3.10.14"',
                'update_method: "update.sh"',
                'install_decision: "install recommended"',
                'dependency_signal: "VERSION changed"',
                'permission_evidence:',
                '  - "ls -ld /ads_storage/autobench -> drwxr-xr-x"',
            ]
        ),
        encoding="utf-8",
    )

    def fake_run_command(args: list[str], cwd: Path = ROOT, timeout: int = 120) -> harness.CheckResult:
        return harness.CheckResult(name=" ".join(args), status="pass", output="ok")

    monkeypatch.setattr(harness, "run_command", fake_run_command)
    monkeypatch.setattr(harness, "current_commit", lambda root=ROOT: "deadbeef")
    monkeypatch.setattr(harness, "current_version", lambda root=ROOT: "3.0.0")

    exit_code = harness.smoke(
        SimpleNamespace(
            config=str(config_path),
            level="2",
            json_report=str(report_path),
            save_screens=False,
        )
    )

    captured = capsys.readouterr()
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["source_commit"] == "abc1234"
    assert payload["bitbucket_snapshot_sha"] == "def5678"
    assert payload["deployed_commit"] == "fedcba9"
    assert payload["update_method"] == "update.sh"
    assert payload["install_decision"] == "install recommended"
    assert payload["dependency_signal"] == "VERSION changed"
    assert payload["smoke"]["level"] == "2"
    assert payload["smoke"]["report_path"] == str(report_path)
    assert payload["drift"]["manifest_path"] == str(report_path.with_name("drift_" + report_path.name))
    assert payload["drift"]["remote_path"] == "/ads_storage/autobench"
    assert payload["checks"][0]["failure_class"] == "deployment"
    assert payload["checks"][1]["failure_class"] == "deployment"
    assert payload["checks"][2]["failure_class"] == "environment"
    assert payload["wrapper_checks"]["config_list"] == "pass"
    assert payload["permission_evidence"][0].startswith("ls -ld /ads_storage/autobench")
    assert "source=abc1234" in captured.out
    assert "snapshot=def5678" in captured.out
    assert "install=install recommended" in captured.out


def test_level3_smoke_marks_controlled_analysis_as_workflow_failure_class(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tools.prod_tui import harness

    config_path = tmp_path / "config.yaml"
    report_path = tmp_path / "smoke.json"
    config_path.write_text('host: "node04"\nrepo_path: "/ads_storage/autobench"\n', encoding="utf-8")

    def fake_run_command(args: list[str], cwd: Path = ROOT, timeout: int = 120) -> harness.CheckResult:
        return harness.CheckResult(name=" ".join(args), status="pass", output="ok")

    monkeypatch.setattr(harness, "run_command", fake_run_command)
    monkeypatch.setattr(harness, "current_commit", lambda root=ROOT: "deadbeef")
    monkeypatch.setattr(harness, "current_version", lambda root=ROOT: "3.0.0")

    exit_code = harness.smoke(
        SimpleNamespace(
            config=str(config_path),
            level="3",
            json_report=str(report_path),
            save_screens=False,
        )
    )

    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert payload["checks"][-1]["failure_class"] == "workflow"


def test_local_check_references_repo_gate_commands() -> None:
    script = (ROOT / "tools/dev/local_check.ps1").read_text(encoding="utf-8")

    assert "py -m compileall" in script
    assert "py -m ruff check ." in script
    assert "py -m mypy --no-site-packages core/ utils/" in script
    assert "py scripts/perform_gate_test.py" in script
    assert "py -m pytest" in script


def test_autobench_bitbucket_remote_is_documented() -> None:
    docs = {
        "release": (ROOT / "docs/release-workflow.md").read_text(
            encoding="utf-8"
        ),
        "first_time_setup": (ROOT / "docs/edge-node-first-time-setup.md").read_text(
            encoding="utf-8"
        ),
    }

    combined = "\n".join(docs.values())

    assert (
        "https://scm.mastercard.int/stash/scm/~e176097/autobench.git" in combined
    )
    assert (
        "git clone -o bitbucket "
        "https://scm.mastercard.int/stash/scm/~e176097/autobench.git autobench"
        in docs["first_time_setup"]
    )
    assert "dispatch.git autobench" not in docs["first_time_setup"]
    assert "/ads_storage/autobench" in combined
    assert "/ads_storage/$USER/.autobench" in combined


def test_release_command_has_one_canonical_home() -> None:
    docs = [
        (ROOT / "docs/release-workflow.md").read_text(encoding="utf-8"),
        (ROOT / "docs/edge-node-first-time-setup.md").read_text(encoding="utf-8"),
    ]

    assert "python -m edge_deploy release" in docs[0]
    assert "recovery" in docs[1].lower() or "bootstrap" in docs[1].lower()
    assert "--tool autobench" not in "\n".join(docs)


def test_active_docs_define_node_specific_rollback_and_human_gated_acceptance() -> None:
    docs = [
        (ROOT / "docs/release-workflow.md").read_text(encoding="utf-8"),
        (ROOT / "docs/production-testing.md").read_text(encoding="utf-8"),
        (ROOT / "tools/prod_tui/README.md").read_text(encoding="utf-8"),
    ]

    combined = "\n".join(docs)

    assert "release report" in combined
    assert "recovery" in combined.lower()
    assert "wrapper checks" in combined
    assert "smoke" in combined.lower()
    assert "local verification is not a substitute" in combined
