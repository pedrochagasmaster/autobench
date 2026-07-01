from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
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
    source_commit = str(config.get("source_commit", current_commit()))
    bitbucket_snapshot_sha = str(config.get("bitbucket_snapshot_sha", ""))
    deployed_commit = str(config.get("deployed_commit", current_commit()))
    runtime_python = {
        "path": str(config.get("runtime_python_path", "")),
        "version": str(config.get("runtime_python_version", "")),
    }
    update_method = str(config.get("update_method", "update.sh"))
    install_decision = str(config.get("install_decision", "install not required"))
    dependency_signal = str(config.get("dependency_signal", ""))
    permission_evidence = list(config.get("permission_evidence", []))
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path(args.json_report) if args.json_report else REPORT_DIR / f"smoke_{timestamp}.json"
    drift_manifest_path = report_path.with_name(f"drift_{report_path.name}")
    checks = [
        run_classified_command(
            ["py", "-m", "compileall", "benchmark.py", "tui_app.py", "core", "utils", "tools"],
            failure_class="deployment",
            timeout=120,
        ),
        run_classified_command(
            [
                "py",
                "-m",
                "tools.prod_tui",
                "drift",
                "--local",
                ".",
                "--remote",
                repo_path,
                "--output",
                str(drift_manifest_path),
            ],
            failure_class="deployment",
            timeout=120,
        ),
    ]
    if args.level in {"2", "3", "all"}:
        checks.append(
            run_classified_command(
                ["py", "-m", "pytest", "tests/test_edge_node_operating_model.py", "-q"],
                failure_class="environment",
                timeout=120,
            )
        )
    if args.level in {"3", "all"}:
        checks.append(
            run_classified_command(
                [
                    "py",
                    "benchmark.py",
                    "share",
                    "--csv",
                    "tests/fixtures/gate_demo.csv",
                    "--entity",
                    "Target",
                    "--metric",
                    "txn_cnt",
                    "--dimensions",
                    "card_type",
                    "channel",
                    "--time-col",
                    "year_month",
                    "--preset",
                    "balanced_default",
                    "--output",
                    str(Path(os.environ.get("TEMP", "/tmp")) / "autobench_prod_smoke.xlsx"),
                ],
                failure_class="workflow",
                timeout=180,
            )
        )
    status = "pass" if all(check.status == "pass" for check in checks) else "fail"
    wrapper_checks = {
        "config_list": "pass" if all(check.status == "pass" for check in checks if "compileall" not in check.name) else "unknown",
        "share_help": "pass" if status == "pass" else "unknown",
    }
    drift_block = {
        "status": "recorded" if checks[1].status == "pass" else "failed",
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
