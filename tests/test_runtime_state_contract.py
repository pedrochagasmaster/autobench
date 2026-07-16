"""Private state and caller-working-directory contracts for a shared runtime."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.telemetry.constants import DEFAULT_SHARED_DIR
from core.telemetry.identity import Identity, encode_user_token
from core.telemetry.writer import paths_for
from utils.runtime_environment import stale_personal_runtime_warning


def _identity(username: str, uid: int) -> Identity:
    return Identity(uid=uid, username=username, token=encode_user_token(username))


def test_users_resolve_distinct_private_autobench_homes() -> None:
    alice = paths_for(_identity("alice", 1001), "/ads_storage/autobench/telemetry")
    bob = paths_for(_identity("bob", 1002), "/ads_storage/autobench/telemetry")

    assert alice.private_file == Path(
        "/ads_storage/alice/.autobench/telemetry/events.jsonl"
    )
    assert bob.private_file == Path(
        "/ads_storage/bob/.autobench/telemetry/events.jsonl"
    )
    assert alice.private_file.parents[1] != bob.private_file.parents[1]


def test_private_state_directories_are_user_specific() -> None:
    for username in ("alice", "bob"):
        home = Path("/ads_storage") / username / ".autobench"
        assert home / "config" != Path("/ads_storage/autobench/config")
        assert home / "logs" != Path("/ads_storage/autobench/logs")
        assert home / "cache" != Path("/ads_storage/autobench/cache")
        assert home / "telemetry" != DEFAULT_SHARED_DIR


def test_shared_telemetry_stays_separate_from_private_state() -> None:
    paths = paths_for(_identity("alice", 1001), "/ads_storage/autobench/telemetry")

    assert os.fspath(paths.shared_users_dir) == "/ads_storage/autobench/telemetry/users"
    assert paths.private_file.parent == Path(
        "/ads_storage/alice/.autobench/telemetry"
    )


def test_entrypoints_do_not_rebase_the_callers_working_directory() -> None:
    benchmark = Path("benchmark.py").read_text(encoding="utf-8")
    tui = Path("tui_app.py").read_text(encoding="utf-8")

    assert "os.chdir(" not in benchmark
    assert "os.chdir(" not in tui
    assert "CsvDirectoryTree(os.getcwd()" in tui


def test_application_code_does_not_require_a_personal_virtualenv() -> None:
    production_python = [
        Path("benchmark.py"),
        Path("tui_app.py"),
        *Path("core").rglob("*.py"),
        *Path("utils").rglob("*.py"),
    ]

    assert all(
        ".autobench/venv" not in path.read_text(encoding="utf-8")
        for path in production_python
    )


def test_stale_personal_runtime_is_diagnosed() -> None:
    warning = stale_personal_runtime_warning(
        executable=Path("/ads_storage/alice/.autobench/venv/bin/python"),
        environ={"USER": "alice"},
    )

    assert "onboard.sh" in warning
    assert "unsupported personal virtual environment" in warning
    assert (
        stale_personal_runtime_warning(
            executable=Path(sys.executable),
            environ={"AUTOBENCH_DATA_ROOT": "/ads_storage/alice"},
        )
        == ""
    )


def test_stale_runtime_diagnostic_degrades_on_resolution_error(
    monkeypatch,
) -> None:
    original_resolve = Path.resolve

    def fail_personal_runtime(path: Path, *args, **kwargs):
        if path.name == "venv":
            raise RuntimeError("symlink loop")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fail_personal_runtime)

    assert (
        stale_personal_runtime_warning(
            executable=Path("/shared/runtime/bin/python"),
            environ={"AUTOBENCH_DATA_ROOT": "/ads_storage/alice"},
        )
        == ""
    )
