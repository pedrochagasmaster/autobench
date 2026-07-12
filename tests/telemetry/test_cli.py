"""Tests for benchmark.py telemetry who/summary CLI."""

from __future__ import annotations

import json
import os
import pwd
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest

import benchmark
from core.telemetry.constants import DEFAULT_DAYS
from core.telemetry.events import build_record
from core.telemetry.identity import encode_user_token
from core.telemetry.reader import Summary, TelemetryReader
from core.telemetry.render import format_summary, format_who

REPO_ROOT = Path(__file__).resolve().parents[2]
BENCHMARK_PY = REPO_ROOT / "benchmark.py"

SESSION_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SESSION_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
APP_VERSION = "3.0"
FIXED_NOW = datetime(2026, 7, 12, 22, 0, 0, tzinfo=timezone.utc)


def _nss_username() -> str:
    return pwd.getpwuid(os.geteuid()).pw_name


def _record(
    event: str,
    props: dict[str, object],
    *,
    user: str,
    session_id: UUID = SESSION_A,
    now: datetime = FIXED_NOW,
) -> bytes:
    return build_record(
        event,
        props,
        user=user,
        session_id=session_id,
        app_version=APP_VERSION,
        now=now,
    )


def _write_shared(shared_dir: Path, username: str, *records: bytes) -> Path:
    users = shared_dir / "users"
    users.mkdir(parents=True, exist_ok=True)
    path = users / f"{encode_user_token(username)}.jsonl"
    path.write_bytes(b"".join(records))
    return path


def _write_hostile_shared_entry(shared_dir: Path) -> Path:
    """Create a users/*.jsonl so shared selection wins (no private fallback)."""
    users = shared_dir / "users"
    users.mkdir(parents=True, exist_ok=True)
    path = users / "hostile.jsonl"
    path.write_bytes(b"{not-json\n\x00\xffmalformed\n")
    return path


def _guard_ads_storage_opens(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Fail the test if anything opens a real /ads_storage path."""
    touched: list[str] = []
    real_open = os.open

    def guarded_open(path: object, flags: int, *args: object, **kwargs: object) -> int:
        raw = os.fspath(path)
        normalized = os.path.normpath(raw)
        if normalized == "/ads_storage" or normalized.startswith("/ads_storage/"):
            touched.append(normalized)
            raise AssertionError(f"must not open real /ads_storage path: {normalized}")
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", guarded_open)
    monkeypatch.setattr("core.telemetry.reader.os.open", guarded_open)
    return touched


def _patch_reader(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    now: datetime | None = FIXED_NOW,
) -> Path:
    """Force TelemetryReader storage_root under tmp_path; optional fixed now."""
    ads = tmp_path / "ads"
    ads.mkdir(exist_ok=True)
    real_cls = TelemetryReader

    def factory(*args: object, **kwargs: object) -> TelemetryReader:
        kwargs.setdefault("storage_root", ads)
        if now is not None:
            kwargs.setdefault("now", now)
        return real_cls(*args, **kwargs)

    monkeypatch.setattr(benchmark, "TelemetryReader", factory)
    return ads


@pytest.fixture
def isolate_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Keep telemetry CLI off real shared defaults; never touch host /ads_storage."""
    monkeypatch.delenv("AUTOBENCH_TELEMETRY_DIR", raising=False)
    monkeypatch.delenv("AUTOBENCH_TELEMETRY", raising=False)
    isolated = tmp_path / "default-shared"
    isolated.mkdir()
    monkeypatch.setattr("core.telemetry.reader.DEFAULT_SHARED_DIR", isolated)
    monkeypatch.setattr(
        "core.telemetry.constants.DEFAULT_SHARED_DIR",
        isolated,
    )
    _patch_reader(monkeypatch, tmp_path, now=FIXED_NOW)
    _guard_ads_storage_opens(monkeypatch)
    return isolated


def _run_main(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr(sys, "argv", ["benchmark.py", *argv])
    return benchmark.main()


def _run_telemetry_subprocess(
    args: list[str],
    *,
    env: dict[str, str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    assert BENCHMARK_PY.is_file()
    return subprocess.run(
        [sys.executable, str(BENCHMARK_PY), *args],
        cwd=str(cwd if cwd is not None else REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )


def test_repo_root_points_at_benchmark() -> None:
    assert REPO_ROOT.joinpath("benchmark.py").resolve() == BENCHMARK_PY.resolve()
    assert BENCHMARK_PY.is_file()


def test_parser_defaults_and_options() -> None:
    parser = benchmark.create_parser()
    who = parser.parse_args(["telemetry", "who"])
    assert who.command == "telemetry"
    assert who.telemetry_command == "who"
    assert who.days == DEFAULT_DAYS == 30
    assert who.dir is None

    who_opts = parser.parse_args(
        ["telemetry", "who", "--days", "7", "--dir", "/tmp/tel"]
    )
    assert who_opts.days == 7
    assert Path(who_opts.dir) == Path("/tmp/tel")

    zero = parser.parse_args(["telemetry", "who", "--days", "0"])
    assert zero.days == 0

    summary = parser.parse_args(["telemetry", "summary"])
    assert summary.telemetry_command == "summary"
    assert summary.days == DEFAULT_DAYS
    assert summary.dir is None
    assert summary.user is None

    summary_opts = parser.parse_args(
        [
            "telemetry",
            "summary",
            "--days",
            "14",
            "--dir",
            "/tmp/tel",
            "--user",
            "alice",
        ]
    )
    assert summary_opts.days == 14
    assert Path(summary_opts.dir) == Path("/tmp/tel")
    assert summary_opts.user == "alice"


def test_parser_help_includes_subcommands() -> None:
    parser = benchmark.create_parser()
    top = parser.format_help()
    assert "telemetry" in top

    for action in parser._actions:
        if getattr(action, "dest", None) != "command":
            continue
        choices = getattr(action, "choices", None) or {}
        assert "telemetry" in choices
        tel_parser = choices["telemetry"]
        text = tel_parser.format_help()
        assert "who" in text
        assert "summary" in text
        break
    else:
        pytest.fail("telemetry subparser not registered")


def test_subcommand_missing_returns_nonzero(
    isolate_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run_main(["telemetry"], monkeypatch)
    assert code == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "who" in combined.lower() or "summary" in combined.lower() or "usage" in combined.lower()


def test_negative_days_safe_error_no_traceback(
    isolate_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    code = _run_main(["telemetry", "who", "--days", "-1"], monkeypatch)
    assert code == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "days" in err.lower()
    assert code != 2


def test_days_zero_accepted(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user = _nss_username()
    shared = tmp_path / "shared-days0"
    # Comfortably inside days=0 inclusive window at FIXED_NOW; older excluded.
    payload = (
        _record(
            "session_start",
            {"launch_context": "tui"},
            user=user,
            session_id=SESSION_A,
            now=FIXED_NOW - timedelta(seconds=1),
        )
        + _record(
            "session_start",
            {"launch_context": "tui"},
            user=user,
            session_id=SESSION_B,
            now=FIXED_NOW,
        )
    )
    _write_shared(shared, user, payload)

    code = _run_main(
        ["telemetry", "who", "--dir", str(shared), "--days", "0"],
        monkeypatch,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "  1  " in out
    assert user in out


def test_invalid_user_generic_safe_error(
    isolate_env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    evil = "bad\x1b[31muser"
    code = _run_main(
        ["telemetry", "summary", "--user", evil, "--dir", str(isolate_env)],
        monkeypatch,
    )
    assert code == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "\x1b" not in combined
    assert "[31m" not in combined
    assert evil not in combined
    assert "user" in combined.lower() or "invalid" in combined.lower()


def test_explicit_dir_file_returns_one(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    not_dir = tmp_path / "not-a-dir"
    not_dir.write_text("x", encoding="utf-8")
    code = _run_main(["telemetry", "who", "--dir", str(not_dir)], monkeypatch)
    assert code == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "dir" in err.lower() or "directory" in err.lower()


def test_nss_keyerror_returns_safe_error(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def boom(*_a: object, **_k: object) -> TelemetryReader:
        raise KeyError("getpwuid: uid not found")

    monkeypatch.setattr(benchmark, "TelemetryReader", boom)
    shared = tmp_path / "shared-keyerror"
    shared.mkdir()
    code = _run_main(["telemetry", "who", "--dir", str(shared)], monkeypatch)
    captured = capsys.readouterr()
    assert code == 1
    assert "Traceback" not in captured.err
    assert "\x1b" not in captured.err
    assert "getpwuid" not in captured.err
    assert "uid not found" not in captured.err
    assert "error" in captured.err.lower()


def test_valid_empty_who_and_summary_never_touch_ads_storage(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shared = tmp_path / "shared-empty"
    shared.mkdir()
    # Shared users entry forces shared selection; private /ads_storage fallback impossible.
    _write_hostile_shared_entry(shared)
    touched = _guard_ads_storage_opens(monkeypatch)

    code_who = _run_main(["telemetry", "who", "--dir", str(shared)], monkeypatch)
    out_who = capsys.readouterr().out
    assert code_who == 0
    assert out_who == format_who([])
    assert touched == []

    code_sum = _run_main(
        ["telemetry", "summary", "--dir", str(shared)], monkeypatch
    )
    out_sum = capsys.readouterr().out
    assert code_sum == 0
    empty = Summary(
        surfaces={"share": 0, "rate": 0},
        actions={"share_analysis": 0, "rate_analysis": 0},
        outcomes={"completed": 0, "cancelled": 0, "refused": 0, "failed": 0},
    )
    assert out_sum == format_summary(empty)
    assert touched == []


def test_populated_shared_who_summary_deterministic(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user = _nss_username()
    shared = tmp_path / "shared-pop"
    t1 = FIXED_NOW - timedelta(hours=2)
    t2 = FIXED_NOW - timedelta(minutes=30)
    payload = (
        _record(
            "session_start",
            {"launch_context": "tui"},
            user=user,
            session_id=SESSION_A,
            now=t1,
        )
        + _record(
            "session_start",
            {"launch_context": "cli_share"},
            user=user,
            session_id=SESSION_B,
            now=t2,
        )
        + _record(
            "surface_viewed",
            {"surface": "share"},
            user=user,
            now=t2,
        )
        + _record(
            "action_completed",
            {"action": "share_analysis"},
            user=user,
            now=t2,
        )
    )
    _write_shared(shared, user, payload)

    code = _run_main(["telemetry", "who", "--dir", str(shared)], monkeypatch)
    who_out = capsys.readouterr().out
    assert code == 0
    assert who_out.startswith("USER  SESSIONS  LAST_SEEN  COMPLETED\n")
    assert user in who_out
    assert "  2  " in who_out
    assert who_out.rstrip().endswith("1")

    code2 = _run_main(
        ["telemetry", "summary", "--dir", str(shared)], monkeypatch
    )
    sum_out = capsys.readouterr().out
    assert code2 == 0
    assert sum_out == (
        "Surfaces\n"
        "share  1\n"
        "rate  0\n"
        "\n"
        "Actions\n"
        "share_analysis  1\n"
        "rate_analysis  0\n"
        "\n"
        "Outcomes\n"
        "completed  1\n"
        "cancelled  0\n"
        "refused  0\n"
        "failed  0\n"
    )


def test_days_filtering(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user = _nss_username()
    shared = tmp_path / "shared-days"
    old = FIXED_NOW - timedelta(days=40)
    recent = FIXED_NOW - timedelta(hours=1)
    payload = (
        _record(
            "session_start",
            {"launch_context": "tui"},
            user=user,
            session_id=SESSION_A,
            now=old,
        )
        + _record(
            "session_start",
            {"launch_context": "tui"},
            user=user,
            session_id=SESSION_B,
            now=recent,
        )
    )
    _write_shared(shared, user, payload)

    code = _run_main(
        ["telemetry", "who", "--dir", str(shared), "--days", "7"],
        monkeypatch,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "  1  " in out


def test_summary_user_filter(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user = _nss_username()
    shared = tmp_path / "shared-user"
    event_ts = FIXED_NOW - timedelta(minutes=5)
    _write_shared(
        shared,
        user,
        _record(
            "surface_viewed",
            {"surface": "rate"},
            user=user,
            now=event_ts,
        ),
    )
    code = _run_main(
        [
            "telemetry",
            "summary",
            "--dir",
            str(shared),
            "--user",
            user,
        ],
        monkeypatch,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "rate  1" in out

    code_miss = _run_main(
        [
            "telemetry",
            "summary",
            "--dir",
            str(shared),
            "--user",
            "nobody_missing_xyz",
        ],
        monkeypatch,
    )
    out_miss = capsys.readouterr().out
    assert code_miss == 0
    assert "rate  0" in out_miss
    assert "share  0" in out_miss


def test_unsupported_schema_warning_on_stderr(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    user = _nss_username()
    shared = tmp_path / "shared-schema"
    event_ts = FIXED_NOW - timedelta(minutes=1)
    bad_obj = {
        "schema_version": 99,
        "ts": event_ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "event": "session_start",
        "user": user,
        "session_id": str(SESSION_A),
        "app_version": APP_VERSION,
        "props": {"launch_context": "tui"},
    }
    bad = (json.dumps(bad_obj, separators=(",", ":")) + "\n").encode("utf-8")
    good = _record(
        "session_start",
        {"launch_context": "tui"},
        user=user,
        session_id=SESSION_B,
        now=event_ts,
    )
    _write_shared(shared, user, bad + good)

    code = _run_main(["telemetry", "who", "--dir", str(shared)], monkeypatch)
    captured = capsys.readouterr()
    assert code == 0
    assert "WARNING:" in captured.err
    assert "schema" in captured.err.lower() or "99" in captured.err
    assert user in captured.out


def test_setup_logging_not_called_for_telemetry(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    called: list[object] = []

    def _boom(*_a: object, **_k: object) -> None:
        called.append(True)
        raise AssertionError("setup_logging must not run for telemetry")

    monkeypatch.setattr(benchmark, "setup_logging", _boom)
    shared = tmp_path / "shared-nolog"
    shared.mkdir()
    _write_hostile_shared_entry(shared)
    assert _run_main(["telemetry", "who", "--dir", str(shared)], monkeypatch) == 0
    assert called == []
    assert (
        _run_main(["telemetry", "summary", "--dir", str(shared)], monkeypatch) == 0
    )
    assert called == []


def test_no_writer_or_service_initialization(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fail(*_a: object, **_k: object) -> None:
        raise AssertionError("telemetry service/writer must not initialize")

    monkeypatch.setattr("core.telemetry._get_service", _fail)
    monkeypatch.setattr("core.telemetry._build_default_service", _fail)
    monkeypatch.setattr("core.telemetry.start_session", _fail)
    monkeypatch.setattr(
        "core.telemetry.service.TelemetryService.__init__",
        _fail,
    )
    monkeypatch.setattr("core.telemetry.writer.append_record", _fail)
    monkeypatch.setattr("core.telemetry.writer.append_one", _fail)

    shared = tmp_path / "shared-nosvc"
    shared.mkdir()
    _write_hostile_shared_entry(shared)
    assert _run_main(["telemetry", "who", "--dir", str(shared)], monkeypatch) == 0
    assert (
        _run_main(["telemetry", "summary", "--dir", str(shared)], monkeypatch) == 0
    )


def test_telemetry_path_never_imports_tui_app(
    isolate_env: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sys.modules.pop("tui_app", None)
    shared = tmp_path / "shared-notui"
    shared.mkdir()
    _write_hostile_shared_entry(shared)
    assert _run_main(["telemetry", "who", "--dir", str(shared)], monkeypatch) == 0
    assert "tui_app" not in sys.modules


def test_subprocess_help_and_empty_who_from_repo_and_other_cwd(
    tmp_path: Path,
) -> None:
    shared = tmp_path / "sub-shared"
    shared.mkdir()
    _write_hostile_shared_entry(shared)

    env = os.environ.copy()
    env.pop("AUTOBENCH_TELEMETRY", None)
    env["AUTOBENCH_TELEMETRY_DIR"] = str(shared)

    help_result = _run_telemetry_subprocess(
        ["telemetry", "--help"],
        env=env,
        cwd=REPO_ROOT,
    )
    assert help_result.returncode == 0
    assert "who" in help_result.stdout
    assert "summary" in help_result.stdout

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    who_result = _run_telemetry_subprocess(
        ["telemetry", "who", "--dir", str(shared)],
        env=env,
        cwd=elsewhere,
    )
    assert who_result.returncode == 0
    assert "No telemetry events." in who_result.stdout
    assert "Traceback" not in who_result.stderr
    # Absolute script path must work even when process cwd is not the repo.
    assert BENCHMARK_PY.is_absolute()
