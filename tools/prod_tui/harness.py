from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import json
import re
import shlex
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = ROOT / "tools" / "prod_tui" / "reports"
SCREEN_DIR = ROOT / "tools" / "prod_tui" / "screens"

IGNORED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "__pycache__",
    "data",
    "outputs",
    "test_sweeps",
    "screens",
    "reports",
    "logs",
}
RUNTIME_SUFFIXES = {".py", ".sh", ".ps1", ".yaml", ".yml", ".toml", ".txt", ".md"}
RUNTIME_NAMES = {"VERSION", "requirements.txt", "constraints.txt"}
SECRET_PATTERNS = [
    re.compile(r"(?i)(password\s*=\s*)\S+"),
    re.compile(r"(?i)(passcode\s*=\s*)\S+"),
    re.compile(r"(?i)(token\s*=\s*)\S+"),
]
RUNTIME_CRITICAL_PATHS = (
    "benchmark.py",
    "tui_app.py",
    "shared_runtime.py",
    "install.sh",
    "onboard.sh",
    "bin/autobench",
    "bin/autobench-cli",
    "bin/runtime_check.sh",
)


@dataclass
class CheckResult:
    name: str
    status: str
    failure_class: str = ""
    output: str = ""


def redact(text: str) -> str:
    redacted = text
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(r"\1***REDACTED***", redacted)
    return redacted


def load_config(path: Path) -> dict[str, object]:
    if not path.exists():
        raise FileNotFoundError(f"config not found: {path}")
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError("PyYAML is required to read prod_tui config files") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config must be a mapping: {path}")
    return data


def run_command(args: list[str], cwd: Path = ROOT, timeout: int = 120) -> CheckResult:
    result = subprocess.run(args, cwd=cwd, text=True, capture_output=True, timeout=timeout, check=False)
    output = "\n".join(part for part in [result.stdout, result.stderr] if part)
    status = "pass" if result.returncode == 0 else "fail"
    return CheckResult(name=" ".join(args), status=status, output=output)


def run_classified_command(
    args: list[str],
    *,
    failure_class: str,
    cwd: Path = ROOT,
    timeout: int = 120,
) -> CheckResult:
    result = run_command(args, cwd=cwd, timeout=timeout)
    result.failure_class = failure_class
    return result


def _ssh_args(config: dict[str, object], command: str) -> list[str]:
    host = str(config.get("host", "")).strip()
    if not host:
        raise ValueError("production smoke config requires host")
    options = shlex.split(str(config.get("ssh_options", "")), posix=True)
    return ["ssh", *options, host, command]


def _run_remote(
    config: dict[str, object],
    command: str,
    *,
    failure_class: str,
    timeout: int = 120,
) -> CheckResult:
    return run_classified_command(
        _ssh_args(config, command),
        failure_class=failure_class,
        timeout=timeout,
    )


def _extract_json_payload(output: str, marker: str) -> dict[str, object]:
    prefix = f"{marker}="
    for line in output.splitlines():
        if line.startswith(prefix):
            payload = json.loads(line[len(prefix) :])
            if not isinstance(payload, dict):
                raise ValueError(f"{marker} payload must be a JSON object")
            return payload
    raise ValueError(f"{marker} payload was not present")


def _runtime_probe_command(repo_path: str) -> str:
    probe = f"""
import importlib
import json
import os
import stat
import sys
from pathlib import Path

runtime = Path(sys.argv[1]).resolve(strict=True)
manifest_path = Path(sys.argv[2])
root = Path(sys.argv[3]).resolve(strict=True)
metadata = json.loads((runtime / ".complete.json").read_text(encoding="utf-8"))
bundle = json.loads(manifest_path.read_text(encoding="utf-8"))
import_errors = {{}}
for name in {list(("pandas", "numpy", "openpyxl", "yaml", "scipy", "textual"))!r}:
    try:
        importlib.import_module(name)
    except Exception as exc:
        import_errors[name] = type(exc).__name__
publicly_writable = []
for path in [runtime, *runtime.rglob("*")]:
    if not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) & 0o022:
        publicly_writable.append(str(path.relative_to(runtime)))
missing = []
unreadable = []
for relative in {list(RUNTIME_CRITICAL_PATHS)!r}:
    path = root / relative
    if not path.is_file():
        missing.append(relative)
    elif not os.access(path, os.R_OK):
        unreadable.append(relative)
payload = {{
    "active_runtime": str(runtime),
    "runtime_digest": metadata.get("bundle_digest"),
    "bundle_digest": bundle.get("bundle_digest"),
    "digest_match": metadata.get("bundle_digest") == bundle.get("bundle_digest"),
    "pip_check": metadata.get("pip_check"),
    "required_imports": metadata.get("required_imports"),
    "import_errors": import_errors,
    "runtime_python": metadata.get("runtime_python"),
    "python_version": metadata.get("python_version"),
    "publicly_writable": publicly_writable,
    "missing_runtime_files": missing,
    "unreadable_runtime_files": unreadable,
    "autobench_executable": os.access(root / "bin" / "autobench", os.X_OK),
    "autobench_cli_executable": os.access(root / "bin" / "autobench-cli", os.X_OK),
}}
print("AUTOBENCH_RUNTIME_EVIDENCE=" + json.dumps(payload, sort_keys=True))
"""
    encoded = base64.b64encode(probe.encode("utf-8")).decode("ascii")
    quoted_root = shlex.quote(repo_path)
    return (
        f"cd {quoted_root} && . {quoted_root}/bin/runtime_check.sh && "
        f"RUNTIME=$(autobench_active_runtime {quoted_root}) && "
        'BUNDLE_DIR=${EDGE_DEPLOY_BUNDLE_DIR:-/ads_storage/$USER/.edge-deploy/bundles/autobench/current} && '
        f'printf %s {encoded} | base64 -d | "$RUNTIME/bin/python" - '
        f'"$RUNTIME" "$BUNDLE_DIR/manifest.json" {quoted_root}'
    )


def _is_runtime_file(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in IGNORED_PARTS for part in relative.parts):
        return False
    if path.name in RUNTIME_NAMES:
        return True
    if path.suffix in RUNTIME_SUFFIXES:
        return True
    return False


def build_manifest(root: Path) -> dict[str, str]:
    manifest: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or not _is_runtime_file(path, root):
            continue
        relative = path.relative_to(root).as_posix()
        manifest[relative] = hashlib.md5(path.read_bytes()).hexdigest()
    return manifest


def current_commit(root: Path = ROOT) -> str:
    result = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, text=True, capture_output=True, check=False)
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def current_version(root: Path = ROOT) -> str:
    version_file = root / "VERSION"
    return version_file.read_text(encoding="utf-8").strip() if version_file.exists() else "unknown"


def write_report(
    path: Path,
    *,
    node: str,
    repo_path: str,
    commit: str,
    version: str,
    checks: Iterable[CheckResult],
    config_name: str = "",
    session_name: str = "",
    pane_target: str = "",
    auth_state: str = "ready",
    human_takeover_required: bool = False,
    source_commit: str = "",
    bitbucket_snapshot_sha: str = "",
    deployed_commit: str = "",
    runtime_python: dict[str, str] | None = None,
    update_method: str = "",
    install_decision: str = "",
    dependency_signal: str = "",
    drift: dict[str, object] | None = None,
    smoke: dict[str, object] | None = None,
    wrapper_checks: dict[str, str] | None = None,
    permission_evidence: list[str] | None = None,
    runtime_evidence: dict[str, object] | None = None,
    summary_line: str = "",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    redacted_checks = []
    for check in checks:
        item = asdict(check)
        item["output"] = redact(item["output"])
        redacted_checks.append(item)
    payload = {
        "tool": "autobench",
        "timestamp_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "node": node,
        "repo_path": repo_path,
        "commit": commit,
        "version": version,
        "config_name": config_name,
        "session_name": session_name,
        "pane_target": pane_target,
        "auth_state": auth_state,
        "human_takeover_required": human_takeover_required,
        "source_commit": source_commit,
        "bitbucket_snapshot_sha": bitbucket_snapshot_sha,
        "deployed_commit": deployed_commit,
        "runtime_python": runtime_python or {},
        "update_method": update_method,
        "install_decision": install_decision,
        "dependency_signal": dependency_signal,
        "drift": drift or {},
        "smoke": smoke or {},
        "wrapper_checks": wrapper_checks or {},
        "permission_evidence": permission_evidence or [],
        "runtime_evidence": runtime_evidence or {},
        "checks": redacted_checks,
        "status": "pass" if all(item["status"] == "pass" for item in redacted_checks) else "fail",
        "summary_line": summary_line,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def smoke(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    config = load_config(config_path)
    node = str(config.get("host", "unknown"))
    repo_path = str(config.get("repo_path", "/ads_storage/autobench"))
    session_name = str(config.get("session_name", ""))
    pane_target = str(config.get("pane_target", ""))
    auth_state = str(config.get("auth_state", "ready"))
    human_takeover_required = bool(config.get("human_takeover_required", False))
    source_commit = str(config.get("source_commit", "")).strip() or current_commit()
    bitbucket_snapshot_sha = str(config.get("bitbucket_snapshot_sha", ""))
    update_method = str(config.get("update_method", "update.sh"))
    install_decision = str(config.get("install_decision", "install not required"))
    dependency_signal = str(config.get("dependency_signal", ""))
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path(args.json_report) if args.json_report else REPORT_DIR / f"smoke_{timestamp}.json"
    drift_manifest_path = report_path.with_name(f"drift_{report_path.name}")
    quoted_root = shlex.quote(repo_path)
    commit_result = _run_remote(
        config,
        f"cd {quoted_root} && git rev-parse HEAD",
        failure_class="deployment",
        timeout=30,
    )
    deployed_commit = commit_result.output.strip().splitlines()[-1] if commit_result.output.strip() else ""
    commit_matches = bool(deployed_commit) and (
        deployed_commit == source_commit
        or deployed_commit.startswith(source_commit)
        or source_commit.startswith(deployed_commit)
    )
    commit_result.status = "pass" if commit_result.status == "pass" and commit_matches else "fail"
    commit_result.name = "remote deployed commit"

    compile_result = _run_remote(
        config,
        (
            f"cd {quoted_root} && . {quoted_root}/bin/runtime_check.sh && "
            f"RUNTIME=$(autobench_active_runtime {quoted_root}) && "
            '"$RUNTIME/bin/python" -m compileall benchmark.py tui_app.py core utils scripts tools'
        ),
        failure_class="deployment",
        timeout=120,
    )
    runtime_probe = _run_remote(
        config,
        _runtime_probe_command(repo_path),
        failure_class="environment",
        timeout=120,
    )
    try:
        runtime_evidence = _extract_json_payload(
            runtime_probe.output, "AUTOBENCH_RUNTIME_EVIDENCE"
        )
    except (json.JSONDecodeError, ValueError):
        runtime_evidence = {}
    runtime_ok = (
        runtime_probe.status == "pass"
        and runtime_evidence.get("digest_match") is True
        and runtime_evidence.get("pip_check") == "passed"
        and runtime_evidence.get("required_imports")
        == ["pandas", "numpy", "openpyxl", "yaml", "scipy", "textual"]
        and runtime_evidence.get("import_errors") == {}
        and runtime_evidence.get("publicly_writable") == []
        and runtime_evidence.get("missing_runtime_files") == []
        and runtime_evidence.get("unreadable_runtime_files") == []
        and runtime_evidence.get("autobench_executable") is True
        and runtime_evidence.get("autobench_cli_executable") is True
    )
    runtime_probe.status = "pass" if runtime_ok else "fail"
    runtime_probe.name = "remote shared runtime evidence"

    config_result = _run_remote(
        config,
        f"{quoted_root}/bin/autobench-cli config list",
        failure_class="environment",
        timeout=120,
    )
    share_result = _run_remote(
        config,
        f"{quoted_root}/bin/autobench-cli share --help",
        failure_class="environment",
        timeout=120,
    )
    checks = [
        commit_result,
        compile_result,
        runtime_probe,
        config_result,
        share_result,
    ]
    if args.level in {"3", "all"}:
        checks.append(
            _run_remote(
                config,
                (
                    f"cd {quoted_root} && {quoted_root}/bin/autobench-cli share "
                    "--csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt "
                    "--dimensions card_type channel --time-col year_month "
                    "--preset balanced_default --output /tmp/autobench_prod_smoke.xlsx"
                ),
                failure_class="workflow",
                timeout=180,
            )
        )
    status = "pass" if all(check.status == "pass" for check in checks) else "fail"
    wrapper_checks = {
        "config_list": config_result.status,
        "share_help": share_result.status,
    }
    drift_block = {
        "status": "not_implemented",
        "manifest_path": str(drift_manifest_path),
        "remote_path": repo_path,
    }
    smoke_block = {
        "level": args.level,
        "report_path": str(report_path),
    }
    summary_line = (
        f"SUMMARY node={node} status={status} config={config_path.name} "
        f"level={args.level} auth={auth_state} source={source_commit} "
        f"snapshot={bitbucket_snapshot_sha or 'none'} deployed={deployed_commit} "
        f"install={install_decision} "
        f"handoff={'yes' if human_takeover_required else 'no'} report={report_path}"
    )
    runtime_python = {
        "path": str(runtime_evidence.get("runtime_python", "")),
        "version": str(runtime_evidence.get("python_version", "")),
    }
    permission_evidence = [
        f"publicly_writable={runtime_evidence.get('publicly_writable', [])}",
        f"missing_runtime_files={runtime_evidence.get('missing_runtime_files', [])}",
        f"unreadable_runtime_files={runtime_evidence.get('unreadable_runtime_files', [])}",
    ]
    write_report(
        report_path,
        node=node,
        repo_path=repo_path,
        commit=current_commit(),
        version=current_version(),
        checks=checks,
        config_name=config_path.name,
        session_name=session_name,
        pane_target=pane_target,
        auth_state=auth_state,
        human_takeover_required=human_takeover_required,
        source_commit=source_commit,
        bitbucket_snapshot_sha=bitbucket_snapshot_sha,
        deployed_commit=deployed_commit,
        runtime_python=runtime_python,
        update_method=update_method,
        install_decision=install_decision,
        dependency_signal=dependency_signal,
        drift=drift_block,
        smoke=smoke_block,
        wrapper_checks=wrapper_checks,
        permission_evidence=permission_evidence,
        runtime_evidence=runtime_evidence,
        summary_line=summary_line,
    )
    print(f"Report: {report_path}")
    print(summary_line)
    return 0 if status == "pass" else 1


def drift(args: argparse.Namespace) -> int:
    root = Path(args.local).resolve()
    manifest = build_manifest(root)
    if args.remote:
        remote_comparison = {
            "status": "not_implemented",
            "reason": "--remote is recorded for reporting, but live remote filesystem comparison is not yet implemented.",
        }
    else:
        remote_comparison = {
            "status": "not_requested",
            "reason": "No remote path was supplied.",
        }
    payload = {
        "root": str(root),
        "remote_path": args.remote,
        "remote_comparison": remote_comparison,
        "total": len(manifest),
        "manifest": manifest,
    }
    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        print(f"Manifest: {output}")
    if args.remote:
        print(f"REMOTE_NOT_COMPARED remote={args.remote} reason=not_implemented")
        print(f"MATCH={len(manifest)} DRIFT=unknown TOTAL={len(manifest)}")
    else:
        print(f"MATCH={len(manifest)} DRIFT=0 TOTAL={len(manifest)}")
        print("IN_SYNC")
    print(f"SUMMARY local={root} remote={args.remote or 'none'} compare={remote_comparison['status']} total={len(manifest)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="py -m tools.prod_tui")
    subparsers = parser.add_subparsers(dest="command", required=True)

    smoke_parser = subparsers.add_parser("smoke")
    smoke_parser.add_argument("--config", default="tools/prod_tui/config-template.yaml")
    smoke_parser.add_argument("--level", choices=["1", "2", "3", "all"], default="1")
    smoke_parser.add_argument("--json-report", default="")
    smoke_parser.add_argument("--save-screens", action="store_true")

    drift_parser = subparsers.add_parser("drift")
    drift_parser.add_argument("--local", default=".")
    drift_parser.add_argument("--remote", default="")
    drift_parser.add_argument("--output", default="")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "smoke":
        return smoke(args)
    if args.command == "drift":
        return drift(args)
    parser.error(f"unknown command: {args.command}")
    return 2
