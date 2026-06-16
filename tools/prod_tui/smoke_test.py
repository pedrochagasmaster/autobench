"""Level 1 and 2 production smoke runner for the Dispatch TUI harness."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence

try:  # pragma: no cover - exercised when run as a script
    from .robocop_tmux import (
        AuthenticationError, DEFAULT_CONFIG_PATH, ProdTuiConfig, SessionGoneError,
        TmuxDriver, load_config,
    )
except ImportError:  # pragma: no cover
    from robocop_tmux import (
        AuthenticationError, DEFAULT_CONFIG_PATH, ProdTuiConfig, SessionGoneError,
        TmuxDriver, load_config,
    )

HARNESS_DIR = Path(__file__).resolve().parent
REPORTS_DIR = HARNESS_DIR / "reports"
SCREENS_DIR = HARNESS_DIR / "screens"

# Text unique to the Dispatch Overview/dashboard in the current UI (v1.1.x).
# The dashboard was redesigned away from an "Active Jobs" table to a
# "running first" cockpit with a stat row and an empty-state line.
DASHBOARD_READY = r"running first|No jobs in the last 7 days|FINISHED 7D"


@dataclass
class SmokeResult:
    name: str
    passed: bool
    message: str
    screen_capture: str = ""
    level: int = 0
    elapsed_ms: int = 0


@dataclass
class RunContext:
    config: ProdTuiConfig
    driver: TmuxDriver
    run_timestamp: str
    save_screens: bool = False
    verbose: bool = False
    screens_dir: Path | None = None
    results: list[SmokeResult] = field(default_factory=list)
    passcode: str | None = None
    reuse_session: bool = False

    def capture(self, name: str, history_lines: int = 200) -> str:
        screen = self.driver.capture_screen(history_lines=history_lines)
        if self.save_screens:
            if self.screens_dir is None:
                self.screens_dir = SCREENS_DIR / f"run_{self.run_timestamp}"
            self.screens_dir.mkdir(parents=True, exist_ok=True)
            safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name).strip("_")
            (self.screens_dir / f"{len(self.results):02d}_{safe_name}.txt").write_text(
                screen + "\n",
                encoding="utf-8",
            )
        return screen


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _ok(name: str, message: str, screen: str = "") -> SmokeResult:
    return SmokeResult(name=name, passed=True, message=message, screen_capture=screen)


def _fail(name: str, message: str, screen: str = "") -> SmokeResult:
    return SmokeResult(name=name, passed=False, message=message, screen_capture=screen)


def _ensure_prompt(ctx: RunContext) -> None:
    ctx.driver.return_to_shell()
    ctx.driver.type_command_confirmed(f"cd {ctx.config.repo_path}")
    time.sleep(0.5)


def check_ssh_connectivity(ctx: RunContext) -> SmokeResult:
    if ctx.reuse_session:
        if not ctx.driver.session_exists():
            raise RuntimeError(
                f"--reuse-session was set but no live tmux session {ctx.config.session_name!r} exists. "
                "Authenticate one first, e.g.: "
                "py tools/prod_tui/robocop_tmux.py start --passcode <CODE>"
            )
        screen = ctx.capture("ssh_connectivity")
        return _ok("ssh_connectivity", "Reusing existing authenticated tmux session", screen)
    ctx.driver.start_session(passcode=ctx.passcode)
    screen = ctx.capture("ssh_connectivity")
    return _ok("ssh_connectivity", "Remote tmux session started", screen)


def check_tmux_geometry(ctx: RunContext) -> SmokeResult:
    result = ctx.driver._tmux([
        "display-message",
        "-p",
        "-t",
        ctx.config.session_name,
        "#{window_width} #{window_height}"
    ])
    assert isinstance(result, subprocess.CompletedProcess)
    output = result.stdout.strip()
    expected = f"{ctx.config.terminal_width} {ctx.config.terminal_height}"
    screen = ctx.capture("tmux_geometry")
    if output != expected:
        return _fail("tmux_geometry", f"Expected {expected}, got {output!r}", screen)
    return _ok("tmux_geometry", f"tmux geometry is {output}", screen)


def check_compileall(ctx: RunContext) -> SmokeResult:
    py = "$(command -v python3.11 || command -v python3.10 || echo /sys_apps_01/python/python310/bin/python3.10)"
    _, code = ctx.driver.run_remote(f"{py} -m compileall dispatch scr", timeout=60)
    screen = ctx.capture("compileall")
    if code != 0:
        return _fail("compileall", f"compileall exited {code}", screen)
    return _ok("compileall", "compileall dispatch scr passed", screen)


def check_dispatch_opens(ctx: RunContext) -> SmokeResult:
    _ensure_prompt(ctx)
    ctx.driver.type_command_confirmed("dispatch")
    screen = ctx.driver.wait_for(rf"{DASHBOARD_READY}|RUNNING|KERBEROS", timeout=20, poll_interval=1.0)
    return _ok("dispatch_opens", "Dispatch dashboard became visible", screen)


def check_dashboard_renders(ctx: RunContext) -> SmokeResult:
    screen = ctx.capture("dashboard_renders")
    if "RUNNING" not in screen or not re.search(DASHBOARD_READY, screen):
        return _fail("dashboard_renders", "Dashboard stat row / overview text not visible", screen)
    return _ok("dashboard_renders", "Dashboard contains stat card / overview text", screen)


def check_kerberos_status(ctx: RunContext) -> SmokeResult:
    screen = ctx.capture("kerberos_status")
    if re.search(r"KERBEROS[\s\S]{1,100}?(N/A|MISSING|\d|[0-9]+[hm])", screen, flags=re.IGNORECASE):
        return _ok("kerberos_status", "Kerberos status is visible", screen)
    return _fail("kerberos_status", "Kerberos status was not visible", screen)


def _press_and_wait(
    ctx: RunContext,
    name: str,
    key: str,
    pattern: str,
    timeout: float = 12.0,
    resend_every: float = 2.5,
) -> SmokeResult:
    # On a high-latency SSH link a single TUI key press is occasionally
    # dropped, so re-send the key every few seconds until the target screen
    # appears (re-checking before each resend so a successful press stops it).
    deadline = time.monotonic() + timeout
    last_send = 0.0
    last_screen = ""
    while time.monotonic() < deadline:
        if time.monotonic() - last_send >= resend_every:
            ctx.driver.send_key(key)
            last_send = time.monotonic()
        try:
            last_screen = ctx.driver.wait_for(pattern, timeout=resend_every, poll_interval=0.5)
            return _ok(name, f"Pressed {key} and observed {pattern}", last_screen)
        except TimeoutError as exc:
            last_screen = str(exc)
    return _fail(name, f"Timed out waiting for {pattern!r} after pressing {key!r}", ctx.capture(name))


def _open_via_toggle_key(
    ctx: RunContext,
    name: str,
    key: str,
    pattern: str,
    *,
    dashboard_marker: str = DASHBOARD_READY,
    timeout: float = 18.0,
    resend_after: float = 3.0,
) -> SmokeResult:
    # Some dashboard hotkeys (notably ``b`` for Browse) are also bound to Back
    # inside the screen they open, so the unconditional resend in
    # ``_press_and_wait`` would *close* a screen that successfully opened on an
    # earlier press. Only resend the key while the dashboard is still visible
    # (the destination is definitely not open), which both recovers a dropped
    # keystroke and never toggles an open screen shut.
    deadline = time.monotonic() + timeout
    target = re.compile(pattern)
    home = re.compile(dashboard_marker)
    last_send = 0.0
    last_screen = ""
    while time.monotonic() < deadline:
        last_screen = ctx.driver.capture_screen()
        if target.search(last_screen):
            return _ok(name, f"Pressed {key} and observed {pattern}", last_screen)
        now = time.monotonic()
        if home.search(last_screen) and now - last_send >= resend_after:
            ctx.driver.send_key(key)
            last_send = now
        time.sleep(0.5)
    return _fail(name, f"Timed out waiting for {pattern!r} after pressing {key!r}", last_screen)


def check_new_job_navigation(ctx: RunContext) -> SmokeResult:
    return _press_and_wait(ctx, "navigation_new_job", "n", r"New Job|Source.*Destination")


def check_back_to_dashboard_from_new_job(ctx: RunContext) -> SmokeResult:
    ctx.driver.send_key("Escape")
    try:
        screen = ctx.driver.wait_for(DASHBOARD_READY, timeout=5)
    except TimeoutError:
        ctx.driver.send_key("b")
        screen = ctx.driver.wait_for(DASHBOARD_READY, timeout=5)
    return _ok("navigation_back_dashboard", "Returned to dashboard from New Job", screen)


def check_browser_opens(ctx: RunContext) -> SmokeResult:
    # ``b`` opens the browser from the dashboard but is bound to Back inside it,
    # so use the toggle-safe opener that only resends while still on the
    # dashboard.
    return _open_via_toggle_key(ctx, "browser_opens", "b", "Browse Impala")


def check_back_from_browser(ctx: RunContext) -> SmokeResult:
    ctx.driver.send_key("Escape")
    return _press_and_wait(ctx, "browser_back_dashboard", "Escape", DASHBOARD_READY)


def check_history_opens(ctx: RunContext) -> SmokeResult:
    return _press_and_wait(ctx, "history_opens", "h", "History")


def check_back_from_history(ctx: RunContext) -> SmokeResult:
    ctx.driver.send_key("Escape")
    return _press_and_wait(ctx, "history_back_dashboard", "Escape", DASHBOARD_READY)


def check_quit_cleanly(ctx: RunContext) -> SmokeResult:
    ctx.driver.return_to_shell()
    screen = ctx.capture("quit_cleanly")
    return _ok("quit_cleanly", "Dispatch exited and tmux session stayed alive", screen)


def check_install_runs(ctx: RunContext) -> SmokeResult:
    email = ctx.config.operator_email or "dispatch-smoke@example.com"
    _, code = ctx.driver.run_remote(f"DISPATCH_EMAIL={email} ./install.sh", timeout=180)
    screen = ctx.capture("install_runs")
    if code != 0:
        return _fail("install_runs", f"install.sh exited {code}", screen)
    return _ok("install_runs", "install.sh completed", screen)


def check_dispatch_shortcut(ctx: RunContext) -> SmokeResult:
    screen, code = ctx.driver.run_remote("which dispatch", timeout=10)
    if code != 0 or not re.search(r"\.local/bin/dispatch|/dispatch", screen):
        return _fail("dispatch_shortcut", "dispatch shortcut did not resolve", ctx.capture("dispatch_shortcut"))
    return _ok("dispatch_shortcut", "dispatch shortcut resolved", screen)


def check_klist_detected(ctx: RunContext) -> SmokeResult:
    _, code = ctx.driver.run_remote("klist -s", timeout=10)
    screen = ctx.capture("klist_detected")
    if code != 0:
        return _fail("klist_detected", "klist did not find a valid Kerberos ticket", screen)
    return _ok("klist_detected", "Kerberos ticket detected", screen)


def check_impala_shell_path(ctx: RunContext) -> SmokeResult:
    _, code = ctx.driver.run_remote("which impala-shell", timeout=10)
    screen = ctx.capture("impala_shell_path")
    if code != 0:
        return _fail("impala_shell_path", "impala-shell was not on PATH", screen)
    return _ok("impala_shell_path", "impala-shell was found on PATH", screen)


def check_python_version(ctx: RunContext) -> SmokeResult:
    py = "$(command -v python3.11 || command -v python3.10 || echo /sys_apps_01/python/python310/bin/python3.10)"
    screen, code = ctx.driver.run_remote(f"{py} --version", timeout=10)
    if code != 0 or not re.search(r"Python 3\.(10|11)", screen):
        return _fail("python_version", "supported Python (3.10/3.11) was not found", ctx.capture("python_version"))
    return _ok("python_version", "Supported Python is available", screen)


def check_ads_storage_writable(ctx: RunContext) -> SmokeResult:
    command = "mkdir -p /ads_storage/$USER/.dispatch && touch /ads_storage/$USER/.dispatch/.smoke_test"
    _, code = ctx.driver.run_remote(command, timeout=15)
    screen = ctx.capture("ads_storage_writable")
    if code != 0:
        return _fail("ads_storage_writable", "/ads_storage/$USER/.dispatch was not writable", screen)
    return _ok("ads_storage_writable", "/ads_storage/$USER/.dispatch is writable", screen)


def check_version_matches(ctx: RunContext) -> SmokeResult:
    command = (
        "test -f VERSION && test -f /ads_storage/$USER/.dispatch/installed_version "
        "&& diff -u VERSION /ads_storage/$USER/.dispatch/installed_version >/dev/null"
    )
    _, code = ctx.driver.run_remote(command, timeout=15)
    screen = ctx.capture("version_matches")
    if code != 0:
        return _fail("version_matches", "Installed version did not match repo VERSION", screen)
    return _ok("version_matches", "Installed version matches repo VERSION", screen)


def check_cwd_captured(ctx: RunContext) -> SmokeResult:
    ctx.driver.return_to_shell()
    ctx.driver.type_command_confirmed("cd /tmp && dispatch")
    ctx.driver.wait_for(DASHBOARD_READY, timeout=20)
    ctx.driver.send_key("n")
    ctx.driver.wait_for(r"New Job", timeout=10)
    screen = ctx.capture("cwd_captured")
    ctx.driver.return_to_shell()
    if "/tmp" not in screen:
        return _fail("cwd_captured", "New Job screen did not show launch directory /tmp", screen)
    return _ok("cwd_captured", "Launch-time cwd is visible in New Job", screen)


_BOX_DRAWING_CHARS = ("┌", "┐", "│", "─", "╭", "╮", "╰", "╯", "▔", "▁", "█")


def _has_box_drawing(screen: str) -> bool:
    """True when the capture shows Textual box-drawing chrome.

    A correctly transported capture contains real box-drawing glyphs. On a tmux
    /SSH session whose locale is not UTF-8, those same UTF-8 bytes are mis-decoded
    as cp437 (e.g. ``│`` arrives as ``Γöé``); this is an intermittent transport
    flake, not a rendering failure. Recover by round-tripping the mojibake back
    through cp437 → UTF-8 before deciding the TUI failed to draw.
    """
    if any(ch in screen for ch in _BOX_DRAWING_CHARS):
        return True
    try:
        recovered = screen.encode("cp437", "ignore").decode("utf-8", "ignore")
    except (UnicodeError, LookupError):
        return False
    return any(ch in recovered for ch in _BOX_DRAWING_CHARS)


def check_textual_rendering(ctx: RunContext) -> SmokeResult:
    ctx.driver.return_to_shell()
    ctx.driver.type_command_confirmed("dispatch")
    screen = ctx.driver.wait_for(DASHBOARD_READY, timeout=20)
    ctx.driver.return_to_shell()
    if _has_box_drawing(screen) and "\x1b[" not in screen:
        return _ok("textual_rendering", "Textual box drawing rendered cleanly", screen)
    return _fail("textual_rendering", "Box drawing was missing or ANSI escapes were visible", screen)


LEVEL_1_CHECKS: list[Callable[[RunContext], SmokeResult]] = [
    check_ssh_connectivity,
    check_tmux_geometry,
    check_compileall,
    check_dispatch_opens,
    check_dashboard_renders,
    check_kerberos_status,
    check_new_job_navigation,
    check_back_to_dashboard_from_new_job,
    check_browser_opens,
    check_back_from_browser,
    check_history_opens,
    check_back_from_history,
    check_quit_cleanly,
]

LEVEL_2_CHECKS: list[Callable[[RunContext], SmokeResult]] = [
    # Shell-only checks first, while the pane is guaranteed at a bash prompt.
    check_install_runs,
    check_dispatch_shortcut,
    check_klist_detected,
    check_impala_shell_path,
    check_python_version,
    check_ads_storage_writable,
    check_version_matches,
    # TUI-launching checks last; each returns to a shell prompt when done.
    check_cwd_captured,
    check_textual_rendering,
]


def run_check(ctx: RunContext, level: int, check: Callable[[RunContext], SmokeResult]) -> SmokeResult:
    started = time.monotonic()
    abort: SessionGoneError | AuthenticationError | None = None
    try:
        result = check(ctx)
    except (SessionGoneError, AuthenticationError) as exc:
        abort = exc
        result = _fail(check.__name__.removeprefix("check_"), f"{type(exc).__name__}: {exc}", "")
    except Exception as exc:  # noqa: BLE001 - the runner must continue by default.
        try:
            screen = ctx.capture(check.__name__)
        except Exception:  # noqa: BLE001
            screen = ""
        result = _fail(check.__name__.removeprefix("check_"), f"{type(exc).__name__}: {exc}", screen)
    result.level = level
    result.elapsed_ms = int((time.monotonic() - started) * 1000)
    ctx.results.append(result)
    print_result(result)
    if abort is not None:
        # Either the pane is dead or auth was rejected; every remaining check
        # would fail identically. Abort so the report and summary stay legible.
        raise abort
    return result


def print_result(result: SmokeResult) -> None:
    status = "PASS" if result.passed else "FAIL"
    try:
        print(f"[{status}] L{result.level} {result.name}: {result.message}")
    except Exception:
        safe_msg = str(result.message).encode("ascii", "replace").decode("ascii")
        print(f"[{status}] L{result.level} {result.name}: {safe_msg}")
    
    if not result.passed and result.screen_capture:
        print("--- last screen ---")
        try:
            print(result.screen_capture)
        except Exception:
            print(result.screen_capture.encode(sys.stdout.encoding or 'ascii', 'replace').decode(sys.stdout.encoding or 'ascii'))
        print("--- end screen ---")


def selected_levels(level: str) -> list[int]:
    if level == "all":
        return [1, 2]
    return [int(level)]


def checks_for_level(level: int) -> Iterable[Callable[[RunContext], SmokeResult]]:
    return LEVEL_1_CHECKS if level == 1 else LEVEL_2_CHECKS


def write_json_report(
    ctx: RunContext,
    levels: list[int],
    started: float,
    path: str | Path | None = None,
) -> Path:
    report_path = Path(path) if path else REPORTS_DIR / f"smoke_{ctx.run_timestamp}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "host": ctx.config.host,
        "levels_run": levels,
        "duration_seconds": round(time.monotonic() - started, 3),
        "results": [asdict(result) for result in ctx.results],
        "summary": {
            "total": len(ctx.results),
            "passed": sum(1 for result in ctx.results if result.passed),
            "failed": sum(1 for result in ctx.results if not result.passed),
        },
        "screen_captures": str(ctx.screens_dir) if ctx.screens_dir else None,
    }
    report_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return report_path


def print_summary(results: Sequence[SmokeResult], report_path: Path) -> None:
    passed = sum(1 for result in results if result.passed)
    failed = len(results) - passed
    print(f"\nSummary: {passed}/{len(results)} passed, {failed} failed")
    print(f"JSON report: {report_path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run production smoke checks against Dispatch over SSH/tmux")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument("--level", choices=["1", "2", "all"], default="1")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--save-screens", action="store_true")
    parser.add_argument("--json-report", help="Write JSON report to this path")
    parser.add_argument("--fail-fast", action="store_true", help="Stop after the first failed check")
    parser.add_argument("--passcode", help="Passcode for SSH authentication")
    parser.add_argument(
        "--reuse-session",
        action="store_true",
        help="Reuse an already-authenticated tmux session instead of starting a new one. "
             "Start one first with: py tools/prod_tui/robocop_tmux.py start --passcode <CODE>",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    started = time.monotonic()
    run_timestamp = utc_stamp()
    try:
        config = load_config(args.config)
        driver = TmuxDriver.from_config(config, retries=2)
        ctx = RunContext(
            config=config,
            driver=driver,
            run_timestamp=run_timestamp,
            save_screens=args.save_screens,
            verbose=args.verbose,
        )
        ctx.passcode = args.passcode
        ctx.reuse_session = args.reuse_session
        levels = selected_levels(args.level)
        for level in levels:
            for check in checks_for_level(level):
                result = run_check(ctx, level, check)
                if args.fail_fast and not result.passed:
                    raise SystemExit(1)
        report_path = write_json_report(ctx, levels, started, args.json_report)
        print_summary(ctx.results, report_path)
        return 0 if all(result.passed for result in ctx.results) else 1
    except SystemExit as exc:
        code = int(exc.code or 0)
        try:
            report_path = write_json_report(ctx, levels, started, args.json_report)  # type: ignore[name-defined]
            print_summary(ctx.results, report_path)  # type: ignore[name-defined]
        except Exception:
            pass
        return code
    except SessionGoneError as exc:
        print(f"Aborted: {exc}", file=sys.stderr)
        try:
            report_path = write_json_report(ctx, levels, started, args.json_report)  # type: ignore[name-defined]
            print_summary(ctx.results, report_path)  # type: ignore[name-defined]
        except Exception:  # noqa: BLE001
            pass
        return 2
    except Exception as exc:  # noqa: BLE001
        print(f"Harness error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
