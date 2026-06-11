"""Generate a master Markdown context bundle for the Autobench tool.

The output is intended for agent handoff, audit review, and offline context
loading. It is generated from current documentation, configuration, and
optionally the source files that define the live tool behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = Path("docs/autobench_master_context.md")
DOC_SECTIONS = {"Current Documentation", "Configuration"}
CODE_SECTIONS = {"Entrypoints", "Relevant Source", "Verification Surface"}

TEXT_EXTENSIONS = {
    ".cfg": "ini",
    ".ini": "ini",
    ".json": "json",
    ".jsonl": "jsonl",
    ".md": "markdown",
    ".ps1": "powershell",
    ".py": "python",
    ".sh": "bash",
    ".txt": "text",
    ".yaml": "yaml",
    ".yml": "yaml",
}

CORE_DOCS = [
    "README.md",
    "AGENTS.md",
    "SETUP.md",
    "docs/CORE_TECHNICAL_DOC.md",
    "docs/control-3-customer-merchant-performance-v5-20260603.md",
    "docs/control3_gap_matrix.md",
    "docs/control3_implementation_summary.md",
    "docs/OPERATIONAL_GAINS.md",
    "docs/EXECUTIVE_PRESENTATION_SCRIPT.md",
    "docs/RELEASE_PROCESS.md",
    "docs/RESOURCE_MANAGEMENT.md",
    "utils/CSV_VALIDATOR_README.md",
]

CONFIG_PATTERNS = [
    "config/*.yaml",
    "presets/*.yaml",
    "requirements*.txt",
    "constraints.txt",
    "pyproject.toml",
]

ENTRYPOINTS = [
    "benchmark.py",
    "tui_app.py",
    "run_tool.sh",
    "deploy_and_install.ps1",
    "setup_remote_env.sh",
    "setup_alias.sh",
]

SOURCE_PATTERNS = [
    "core/*.py",
    "core/solvers/*.py",
    "utils/*.py",
]

VERIFICATION_FILES = [
    "scripts/build_master_context.py",
    "scripts/perform_gate_test.py",
    "scripts/gate_expectations.py",
    "scripts/generate_cli_sweep.py",
    "scripts/run_cli_sweep.py",
    "scripts/run_cli_sweep_cases.py",
    "scripts/offline_bundle_checksums.py",
    "scripts/run_performance_benchmark.py",
    "tests/conftest.py",
    "tests/test_control3_policy_gates.py",
    "tests/test_privacy_rules_engine.py",
    "tests/test_privacy_rules_config.py",
    "tests/test_report_artifact_builder.py",
    "tests/test_output_artifacts.py",
    "tests/test_golden_outputs.py",
    "tests/test_gate_runner.py",
    "tests/test_tui_contracts.py",
    "tests/test_csv_validator.py",
    "test_gate/meta.json",
    "test_gate/share/cases.jsonl",
    "test_gate/rate/cases.jsonl",
    "test_gate/config/cases.jsonl",
]

EXCLUDED_PATTERNS = [
    ".git/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".venv/",
    "venv/",
    "env/",
    "data/",
    "outputs/",
    "test_sweeps/",
    "offline_packages/",
    "docs/autobench_master_context.md",
    "docs/autobench_master_context_docs.md",
    "docs/autobench_master_context_code.md",
]


@dataclass(frozen=True)
class IncludedFile:
    path: Path
    section: str
    reason: str


def run_git(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            text=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return "unavailable"
    return result.stdout.strip() or "unavailable"


def repo_path(path: Path | str) -> Path:
    return (ROOT / path).resolve()


def relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT).as_posix()


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def is_excluded(path: Path) -> bool:
    rel = relative(path)
    return any(rel == pattern.rstrip("/") or rel.startswith(pattern) for pattern in EXCLUDED_PATTERNS)


def discover(patterns: Iterable[str]) -> list[Path]:
    found: list[Path] = []
    for pattern in patterns:
        matches = sorted(ROOT.glob(pattern))
        found.extend(path for path in matches if path.is_file())
    return found


def add_file(
    files: list[IncludedFile],
    seen: set[str],
    path: Path | str,
    section: str,
    reason: str,
) -> None:
    absolute = repo_path(path)
    if not absolute.exists() or not absolute.is_file() or is_excluded(absolute):
        return
    if absolute.suffix.lower() not in TEXT_EXTENSIONS:
        return
    rel = relative(absolute)
    if rel in seen:
        return
    seen.add(rel)
    files.append(IncludedFile(path=absolute, section=section, reason=reason))


def collect_files(include_source: bool, include_all_tests: bool) -> list[IncludedFile]:
    files: list[IncludedFile] = []
    seen: set[str] = set()

    for path in CORE_DOCS:
        add_file(files, seen, path, "Current Documentation", "Current user, operator, policy, or technical context.")

    for path in discover(CONFIG_PATTERNS):
        add_file(files, seen, path, "Configuration", "Runtime dependency, config schema, or shipped preset.")

    if include_source:
        for path in ENTRYPOINTS:
            add_file(files, seen, path, "Entrypoints", "User-facing execution or deployment entrypoint.")
        for path in discover(SOURCE_PATTERNS):
            add_file(files, seen, path, "Relevant Source", "Live implementation source for loading, policy, optimization, reporting, or utilities.")
        for path in VERIFICATION_FILES:
            add_file(files, seen, path, "Verification Surface", "Gate, policy, report, output, or integration verification contract.")
        if include_all_tests:
            for path in discover(["tests/*.py", "test_gate/**/*.jsonl", "test_gate/**/*.ps1"]):
                add_file(files, seen, path, "Verification Surface", "Additional tracked test or gate-case coverage.")

    return files


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace").rstrip()


def fence_for(path: Path) -> str:
    return TEXT_EXTENSIONS.get(path.suffix.lower(), "text")


def split_output_paths(output: Path) -> tuple[Path, Path]:
    return (
        output.with_name(f"{output.stem}_docs{output.suffix}"),
        output.with_name(f"{output.stem}_code{output.suffix}"),
    )


def filter_files(files: list[IncludedFile], sections: set[str]) -> list[IncludedFile]:
    return [item for item in files if item.section in sections]


def render(files: list[IncludedFile], include_source: bool, bundle_type: str = "combined") -> str:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    commit = run_git(["rev-parse", "HEAD"])
    status = run_git(["status", "--short"])
    status_summary = "clean" if status == "unavailable" or status == "" else "dirty"
    title_suffix = {
        "combined": "",
        "docs": " - Documentation and Configuration",
        "code": " - Source and Verification",
    }.get(bundle_type, "")

    lines: list[str] = [
        f"# Autobench Master Context Bundle{title_suffix}",
        "",
        f"Generated: {generated_at}",
        f"Repository: `{ROOT}`",
        f"Git commit: `{commit}`",
        f"Git status: `{status_summary}`",
        f"Bundle type: `{bundle_type}`",
        f"Source requested: `{str(include_source).lower()}`",
        "",
        "This file is generated by `scripts/build_master_context.py`. Do not edit it manually.",
        "",
        "## Generation Policy",
        "",
        "- Current operational, technical, and Control 3 policy documentation is inlined.",
        "- Source inclusion is enabled by default through `--include-source`; use `--no-include-source` for a docs-only bundle.",
        "- Binary originals, generated outputs, caches, input data, and stale historical plans are excluded.",
        "- Each included file is fenced and carries path, reason, byte size, and SHA-256 provenance.",
        "",
        "## Included File Manifest",
        "",
        "| # | Section | Path | Bytes | SHA-256 |",
        "|---:|---|---|---:|---|",
    ]

    for index, item in enumerate(files, start=1):
        rel = relative(item.path)
        lines.append(
            f"| {index} | {item.section} | `{rel}` | {item.path.stat().st_size} | `{sha256(item.path)}` |"
        )

    lines.extend(["", "## Excluded By Policy", ""])
    for pattern in EXCLUDED_PATTERNS:
        lines.append(f"- `{pattern}`")

    current_section = None
    for index, item in enumerate(files, start=1):
        if item.section != current_section:
            current_section = item.section
            lines.extend(["", f"## {current_section}", ""])

        rel = relative(item.path)
        language = fence_for(item.path)
        lines.extend(
            [
                f"### {index}. `{rel}`",
                "",
                f"- Included because: {item.reason}",
                f"- Bytes: {item.path.stat().st_size}",
                f"- SHA-256: `{sha256(item.path)}`",
                "",
                f"```{language}",
                read_text(item.path),
                "```",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Autobench master Markdown context bundle.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output Markdown path.")
    source_group = parser.add_mutually_exclusive_group()
    source_group.add_argument(
        "--include-source",
        dest="include_source",
        action="store_true",
        default=True,
        help="Include relevant source files. This is the default.",
    )
    source_group.add_argument(
        "--no-include-source",
        dest="include_source",
        action="store_false",
        help="Generate a docs/config-only bundle.",
    )
    parser.add_argument(
        "--include-all-tests",
        action="store_true",
        help="Include every tracked test file instead of only the core verification surface.",
    )
    parser.add_argument(
        "--split-types",
        action="store_true",
        help="Write separate *_docs.md and *_code.md bundles instead of one combined file.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = repo_path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    files = collect_files(include_source=args.include_source, include_all_tests=args.include_all_tests)
    if args.split_types:
        docs_output, code_output = split_output_paths(output)
        docs_output.write_text(
            render(filter_files(files, DOC_SECTIONS), include_source=args.include_source, bundle_type="docs"),
            encoding="utf-8",
        )
        code_output.write_text(
            render(filter_files(files, CODE_SECTIONS), include_source=args.include_source, bundle_type="code"),
            encoding="utf-8",
        )

        print(f"Wrote {display_path(docs_output)}")
        print(f"Wrote {display_path(code_output)}")
        print(f"Included docs/config files: {len(filter_files(files, DOC_SECTIONS))}")
        print(f"Included source/verification files: {len(filter_files(files, CODE_SECTIONS))}")
        print(f"Source requested: {args.include_source}")
        return

    output.write_text(render(files, include_source=args.include_source), encoding="utf-8")

    print(f"Wrote {display_path(output)}")
    print(f"Included files: {len(files)}")
    print(f"Source requested: {args.include_source}")


if __name__ == "__main__":
    main()
