"""Local tmux/psmux driver and CLI for production Dispatch TUI validation.

Session model
-------------
``TmuxDriver`` creates and manages tmux sessions **locally** (using the ``tmux``
binary available on the local machine — standard tmux on Linux/macOS, or psmux
on Windows which provides a ``tmux.exe`` shim).

The remote shell lives *inside* the tmux pane: ``start_session`` opens a
new detached local tmux session whose initial command is an SSH connection to
the Edge Node, landing in ``repo_path``.  All subsequent ``send_keys``,
``capture_screen``, and ``stop_session`` calls operate on that local session
without additional SSH round-trips.

One-off remote operations (file writes, ``impala-shell`` queries, ``klist``)
still use direct SSH via ``_ssh()``.
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

DEFAULT_CONFIG_PATH = Path(__file__).with_name("config.yaml")

# Matches an ANSI escape sequence so screen text can be inspected as plain text.
_ANSI_RE = r"\x1b\[[0-9;?]*[ -/]*[@-~]"
# A bash/sh *primary* prompt at the end of a line (``$`` or ``#``). The ``>``
# PS2 continuation prompt is intentionally excluded: treating it as a real
# prompt would let the harness append commands onto a dangling, unterminated
# line instead of recognising the pane is stuck.
SHELL_PROMPT_RE = r"[\$#]\s*$"
# Visible Dispatch TUI chrome. If any of this is on screen we are *not* at a
# shell prompt, even if a stray prompt-like character appears in a widget.
TUI_CHROME_RE = (
    r"Dispatch \u2014 Impala|Active Jobs|Browse Impala|Browse Impala Metadata|"
    r"New Job|Job History|SQL Preview|\? help|esc Back"
)
# The Overview/dashboard is the app's *top* screen: pressing ``q`` there quits
# Dispatch cleanly back to the shell. Any other TUI screen is a pushed sub-screen
# that ``Escape`` pops (its footer shows ``esc Back``); ``q`` on those would be
# typed into a focused Input instead of quitting.
DASHBOARD_TOP_RE = r"running first|n New Job\b"


class SessionGoneError(RuntimeError):
    """Raised when the tmux session has disappeared (pane process exited).

    Surfacing this distinctly stops the harness from cascading a dozen opaque
    ``capture-pane returned non-zero`` failures when the SSH pane has died.
    """


class AuthenticationError(RuntimeError):
    """Raised when the Edge Node rejects the SSH credential / passcode.

    RSA SecurID tokencodes are single-use and rotate roughly every 60s, so a
    stale or mistyped code makes ``sshd`` re-display ``Enter PASSCODE:``.
    Surfacing this distinctly lets the harness abort *immediately* with an
    actionable message instead of grinding every check against a pane that is
    stuck at the authentication prompt.
    """


@dataclass(frozen=True)
class ProdTuiConfig:
    """Configuration for the production TUI harness."""

    host: str
    repo_path: str
    session_name: str = "robocop-prod-test"
    terminal_width: int = 120
    terminal_height: int = 40
    ssh_options: str = ""
    ssh_connect_timeout: int = 15
    smoke_query_sql: str = "SELECT 1 AS smoke_test_value"
    scratch_schema: str = "aa_enc"
    table_prefix: str = "dispatch_smoke"
    max_smoke_job_wait_seconds: int = 120
    operator_email: str = ""
    impala_coordinator: str = "dw.prod.impala.mastercard.int:21000"

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ProdTuiConfig":
        return cls(
            host=str(data.get("host", "your-user@edge-node")),
            repo_path=str(data.get("repo_path", "/ads_storage/dispatch")),
            session_name=str(data.get("session_name", "robocop-prod-test")),
            terminal_width=int(data.get("terminal_width", 120)),
            terminal_height=int(data.get("terminal_height", 40)),
            ssh_options=str(data.get("ssh_options", "") or ""),
            ssh_connect_timeout=int(data.get("ssh_connect_timeout", 15)),
            smoke_query_sql=str(data.get("smoke_query_sql", "SELECT 1 AS smoke_test_value")),
            scratch_schema=str(data.get("scratch_schema", "aa_enc")),
            table_prefix=str(data.get("table_prefix", "dispatch_smoke")),
            max_smoke_job_wait_seconds=int(data.get("max_smoke_job_wait_seconds", 120)),
            operator_email=str(data.get("operator_email", "") or os.environ.get("DISPATCH_EMAIL", "")),
            impala_coordinator=str(
                data.get("impala_coordinator", "dw.prod.impala.mastercard.int:21000")
            ),
        )

    def current_user(self) -> str:
        user_part = self.host.rsplit("@", 1)[0] if "@" in self.host else ""
        return os.environ.get("USER") or os.environ.get("USERNAME") or user_part or "dispatch"


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if not value:
        return ""
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    if value.lower() in {"true", "false"}:
        return value.lower() == "true"
    try:
        return int(value)
    except ValueError:
        return value


def _fallback_yaml_load(text: str) -> dict[str, Any]:
    """Parse the simple key/value YAML used by the harness config.

    PyYAML is the supported parser for operators, but this fallback keeps unit
    tests and command construction usable in a minimal local environment.
    """
    data: dict[str, Any] = {}
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip()] = _parse_scalar(value)
    return data


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> ProdTuiConfig:
    config_path = Path(path)
    text = config_path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        data = _fallback_yaml_load(text)
    else:
        loaded = yaml.safe_load(text) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"Config must be a YAML mapping: {config_path}")
        data = loaded
    return ProdTuiConfig.from_mapping(data)


class TmuxDriver:
    """Drive a local tmux/psmux session whose pane is an SSH connection to the Edge Node.

    Session lifecycle
    -----------------
    ``start_session()`` creates a **local** detached tmux session.  Its initial
    command is ``ssh [options] host "cd repo_path && exec bash -l"``, so the
    remote shell is already at the right working directory.

    All pane control (``send_keys``, ``capture_screen``, ``attach``,
    ``stop_session``) runs tmux commands locally — no extra SSH hops.

    One-off remote operations (file writes, ``impala-shell``, ``klist``) run
    through ``run_remote()`` in the *already-authenticated* pane. A second
    ``ssh host cmd`` is intentionally not used: with single-use RSA / 2FA it
    would block forever on the ``Enter PASSCODE:`` prompt.
    """

    def __init__(
        self,
        host: str,
        session: str,
        repo_path: str,
        width: int = 120,
        height: int = 40,
        ssh_options: str = "",
        retries: int = 0,
        retry_backoff: float = 3.0,
    ) -> None:
        self.host = host
        self.session = session
        self.repo_path = repo_path
        self.width = width
        self.height = height
        self.ssh_options = ssh_options
        self.ssh_connect_timeout: int = 15
        self.retries = retries
        self.retry_backoff = retry_backoff

    @classmethod
    def from_config(cls, config: ProdTuiConfig, *, retries: int = 0) -> "TmuxDriver":
        driver = cls(
            host=config.host,
            session=config.session_name,
            repo_path=config.repo_path,
            width=config.terminal_width,
            height=config.terminal_height,
            ssh_options=config.ssh_options,
            retries=retries,
        )
        driver.ssh_connect_timeout = config.ssh_connect_timeout
        return driver

    # ------------------------------------------------------------------
    # Local tmux helpers
    # ------------------------------------------------------------------

    def _tmux(
        self,
        argv: list[str],
        *,
        check: bool = True,
        capture_output: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        """Run a tmux command locally (works with psmux on Windows)."""
        return subprocess.run(
            ["tmux"] + argv,
            check=check,
            capture_output=capture_output,
            text=True,
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Session management (local tmux)
    # ------------------------------------------------------------------

    def _build_pane_command(self) -> str:
        """Build the shell command that the tmux pane will run on startup.

        This command SSHes into the remote host and lands at ``repo_path``.
        ``-t`` forces PTY allocation so the remote login shell is fully
        interactive (correct prompt, job control, readline, etc.).
        """
        ssh_parts = ["ssh", "-t"]
        if self.ssh_options:
            ssh_parts.extend(shlex.split(self.ssh_options))
        ssh_parts.append(self.host)
        # Remote shell: cd to repo, then start a login bash.
        remote_cmd = f"cd {shlex.quote(self.repo_path)} && exec bash -l"
        ssh_parts.append(remote_cmd)
        return " ".join(shlex.quote(p) for p in ssh_parts)

    def session_exists(self) -> bool:
        """Return True if the local tmux session is currently alive."""
        result = self._tmux(["has-session", "-t", self.session], check=False)
        return result.returncode == 0

    def start_session(self, *, connect_timeout: float | None = None, passcode: str | None = None) -> bool:
        """Create a local tmux session whose pane SSHes into the Edge Node.

        Blocks until a shell prompt or an authentication prompt appears.

        Returns
        -------
        True
            Shell prompt seen — session is fully ready.
        False
            Authentication prompt (PASSCODE / password) seen. If ``passcode``
            is supplied it is sent automatically and the method waits for the
            shell. Otherwise the pane is left at the prompt for the caller to
            handle via ``send_keys``.

        Raises
        ------
        TimeoutError
            Neither a shell nor an auth prompt appeared within the timeout.
        """
        import re as _re
        timeout = connect_timeout if connect_timeout is not None else getattr(self, "ssh_connect_timeout", 20)

        # Kill any stale local session with the same name.
        self._tmux(["kill-session", "-t", self.session], check=False)

        pane_cmd = self._build_pane_command()
        self._tmux(
            [
                "new-session", "-d",
                "-s", self.session,
                "-x", str(int(self.width)),
                "-y", str(int(self.height)),
                pane_cmd,
            ]
        )

        _AUTH_RE = r"PASSCODE:|[Pp]assword:|PIN:"
        _PROMPT_RE = r"[\$#]\s*$"
        combined = rf"(?:{_PROMPT_RE})|(?:{_AUTH_RE})"

        try:
            screen = self.wait_for(combined, timeout=float(timeout), poll_interval=1.0)
        except TimeoutError as exc:
            try:
                last = self.capture_screen()
            except Exception:
                last = "(pane capture failed)"
            raise TimeoutError(
                f"SSH did not produce a shell or auth prompt within {timeout}s.\n"
                f"Pane contents:\n{last}"
            ) from exc

        if _re.search(_AUTH_RE, screen):
            if passcode:
                self.send_keys(passcode, literal=True)
                self.send_key("Enter")
                self._await_auth_result(timeout=float(timeout))
                return True
            return False

        return True

    def _await_auth_result(self, *, timeout: float, poll_interval: float = 1.0) -> None:
        """Block until the pane reaches a shell prompt after a passcode is sent.

        Fails fast (rather than waiting out the full timeout) the moment the
        Edge Node signals rejection: ``sshd`` re-displays the auth prompt — so a
        *second* ``Enter PASSCODE:`` on screen, or an explicit ``Permission
        denied`` / ``Authentication failed`` line, means the credential was
        stale or wrong.

        Raises
        ------
        AuthenticationError
            The credential was rejected, or no shell appeared in ``timeout``.
        """
        import re

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            screen = self.capture_screen()
            if self.at_shell_prompt(screen):
                return
            plain = re.sub(_ANSI_RE, "", screen)
            if re.search(r"Permission denied|Authentication failed|Too many authentication", plain, re.IGNORECASE):
                raise AuthenticationError(
                    "Edge Node rejected the credential (authentication failed). "
                    "RSA passcodes are single-use and rotate ~every 60s — request a fresh one."
                )
            # A re-displayed auth prompt (>= 2 on screen) means the first code was refused.
            if len(re.findall(r"PASSCODE:|[Pp]assword:|PIN:", plain)) >= 2:
                raise AuthenticationError(
                    "Edge Node re-prompted for a PASSCODE — the code was stale or wrong. "
                    "RSA passcodes are single-use and rotate ~every 60s; send a fresh one."
                )
            time.sleep(poll_interval)

        raise AuthenticationError(
            f"Sent a passcode but no shell prompt appeared within {timeout:.0f}s. "
            "The credential was likely wrong or expired; request a fresh RSA passcode."
        )

    def stop_session(self) -> None:
        """Kill the local tmux session."""
        self._tmux(
            ["kill-session", "-t", self.session],
            check=False,
        )

    # ------------------------------------------------------------------
    # Pane control (local tmux)
    # ------------------------------------------------------------------

    def send_keys(self, keys: str, *, literal: bool = False) -> None:
        argv = ["send-keys"]
        if literal:
            argv.append("-l")
        argv += ["-t", self.session, keys]
        if not literal:
            argv.append("Enter")
        self._tmux(argv)

    def send_key(self, key: str) -> None:
        """Send a single tmux key name without appending Enter."""
        self._tmux(["send-keys", "-t", self.session, key])

    def send_text(self, text: str) -> None:
        self.send_keys(text, literal=True)
        self.send_key("Enter")

    def capture_screen(self, history_lines: int = 0) -> str:
        argv = ["capture-pane", "-t", self.session, "-p"]
        if history_lines > 0:
            argv.extend(["-S", f"-{int(history_lines)}"])
        result = self._tmux(argv, check=False)
        if result.returncode != 0:
            if not self.session_exists():
                raise SessionGoneError(
                    f"tmux session {self.session!r} no longer exists "
                    "(the SSH pane process has exited)."
                )
            raise subprocess.CalledProcessError(
                result.returncode, ["tmux"] + argv, result.stdout, result.stderr
            )
        return result.stdout.rstrip()

    def resize_window(self, width: int, height: int) -> None:
        """Resize the (possibly detached) tmux window.

        Used to give a taller viewport for tall TUI screens (e.g. the New Job
        form with the Table destination) so all rows render inside the pane
        that ``capture-pane`` can read.
        """
        self._tmux(
            ["resize-window", "-t", self.session, "-x", str(int(width)), "-y", str(int(height))],
            check=False,
        )

    def attach(self) -> None:
        """Attach the current terminal to the local tmux session."""
        subprocess.run(["tmux", "attach", "-t", self.session], check=False)

    def wait_for(
        self,
        pattern: str,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> str:
        import re

        deadline = time.monotonic() + timeout
        last_screen = ""
        while time.monotonic() < deadline:
            last_screen = self.capture_screen()
            if re.search(pattern, last_screen, flags=re.MULTILINE):
                return last_screen
            time.sleep(poll_interval)
        raise TimeoutError(
            f"Timed out after {timeout:.1f}s waiting for {pattern!r}.\n"
            f"Last screen:\n{last_screen}"
        )

    # ------------------------------------------------------------------
    # Shell-prompt detection and recovery
    # ------------------------------------------------------------------

    def at_shell_prompt(self, screen: str | None = None) -> bool:
        """Return True when the pane is sitting at a bash/sh prompt.

        Robust against the Dispatch TUI: if any TUI chrome is visible the pane
        is considered *not* at a shell prompt, even when a prompt-like character
        happens to appear inside a widget (e.g. a focused search ``Input``).
        """
        import re

        text = screen if screen is not None else self.capture_screen()
        text = re.sub(_ANSI_RE, "", text)
        if re.search(TUI_CHROME_RE, text):
            return False
        lines = [line for line in text.splitlines() if line.strip()]
        if not lines:
            return False
        return re.search(SHELL_PROMPT_RE, lines[-1]) is not None

    def return_to_shell(self, timeout: float = 25.0, poll_interval: float = 0.6) -> bool:
        """Deterministically return the pane to a bash prompt.

        Designed for high-latency SSH where individual key presses are
        occasionally dropped. Rather than escalating through a fixed sequence
        (which marched into ``C-c`` and could take down the pane when a ``q``
        was lost), this re-evaluates the screen on every poll and re-sends the
        *correct* key for the current screen until a shell prompt appears:

        * Sub-screen (footer shows ``esc Back``) or any non-dashboard chrome ->
          ``Escape`` to pop back toward the Overview.
        * Overview/dashboard (``q`` quits the app cleanly) -> ``q``.

        ``C-c`` is never sent: ``q`` quits Dispatch cleanly, and a stray
        ``C-c`` against a shell mid-transition is what previously killed the
        session. Dropped keys are tolerated because each poll re-sends.

        Raises
        ------
        SessionGoneError
            If the tmux pane has exited (propagated from ``capture_screen``).
        RuntimeError
            If no shell prompt appears within ``timeout``.
        """
        import re
        import time

        deadline = time.monotonic() + timeout
        last_key_at = 0.0
        while time.monotonic() < deadline:
            screen = self.capture_screen()
            if self.at_shell_prompt(screen):
                return True
            # Re-send at most ~every 1.2s so a transition has time to render
            # but a dropped key is retried promptly.
            if time.monotonic() - last_key_at >= 1.2:
                plain = re.sub(_ANSI_RE, "", screen)
                if re.search(TUI_CHROME_RE, plain):
                    # Inside Dispatch: quit from the top screen, otherwise pop.
                    if re.search(DASHBOARD_TOP_RE, plain) and not re.search(r"esc Back", plain):
                        self.send_key("q")
                    else:
                        self.send_key("Escape")
                else:
                    # Not in the app, but not a clean prompt either: there is
                    # leftover/partial input on the line (e.g. a stray key left
                    # a half-typed command and a tab-completion menu). Clear the
                    # line so the prompt becomes clean instead of spamming keys.
                    self.send_key("C-u")
                last_key_at = time.monotonic()
            time.sleep(poll_interval)

        raise RuntimeError(
            "Could not return to a shell prompt; the Dispatch TUI may be stuck.\n"
            f"Last screen:\n{self.capture_screen()}"
        )

    def run_remote(
        self,
        command: str,
        *,
        timeout: float = 30.0,
        ensure_shell: bool = True,
    ) -> tuple[str, int]:
        """Run a one-off command in the authenticated pane; return (screen, exit_code).

        This replaces direct ``ssh host cmd`` calls for one-off remote work.
        Because it reuses the already-authenticated tmux pane, it works with
        single-use RSA / 2FA logins, where a second non-interactive ``ssh``
        would block forever on the ``Enter PASSCODE:`` prompt.

        A unique, split exit-code sentinel is appended so the echoed command
        line can never be mistaken for command output, and the real exit status
        is recovered.
        """
        import re
        import uuid

        if ensure_shell:
            self.return_to_shell()
        # Discard any stray/partial input left on the line so the command we are
        # about to send cannot be concatenated onto leftover characters.
        self.send_key("C-u")

        nonce = uuid.uuid4().hex[:12]
        # The ``'`` split keeps the literal marker out of the echoed command
        # line: bash concatenates ``'\n__RC'`` + ``'_<nonce>_%s__\n'`` so only
        # the printed output contains ``__RC_<nonce>_<code>__``.
        marker_cmd = f"{command}; printf '\\n__RC''_{nonce}_%s__\\n' \"$?\""
        self.send_keys(marker_cmd)

        pattern = rf"__RC_{nonce}_(\d+)__"
        screen = self.wait_for(pattern, timeout=timeout, poll_interval=0.5)
        match = re.search(pattern, screen)
        exit_code = int(match.group(1)) if match else -1
        return screen, exit_code

    def _last_nonempty_line(self, screen: str | None = None) -> str:
        import re

        text = screen if screen is not None else self.capture_screen()
        text = re.sub(_ANSI_RE, "", text)
        lines = [line for line in text.splitlines() if line.strip()]
        return lines[-1] if lines else ""

    def type_command_confirmed(
        self,
        command: str,
        *,
        confirm_timeout: float = 6.0,
        retries: int = 3,
        poll_interval: float = 0.3,
    ) -> bool:
        """Type a shell command, confirm it echoed intact, then press Enter.

        On a high-latency SSH PTY the first character of a freshly typed command
        is occasionally dropped (e.g. ``dispatch`` arriving as ``ispatch``),
        especially right after a full-screen TUI restores the terminal. This
        types the command *without* Enter, waits until the prompt line actually
        contains the full command text, and only then sends Enter — clearing the
        line (``C-u``) and retyping if the echo came back corrupted.

        Returns
        -------
        bool
            True if the echo was confirmed before Enter, False if it pressed
            Enter as a last resort after exhausting ``retries``.
        """
        for _ in range(max(1, retries)):
            self.send_key("C-u")  # discard any partial/dropped input on the line
            time.sleep(0.15)
            self.send_keys(command, literal=True)
            deadline = time.monotonic() + confirm_timeout
            while time.monotonic() < deadline:
                if command in self._last_nonempty_line():
                    self.send_key("Enter")
                    return True
                time.sleep(poll_interval)
        # Last resort: submit whatever is on the line so the caller's wait_for
        # can still fail loudly rather than hang on a half-typed command.
        self.send_key("Enter")
        return False


def driver_from_config_path(path: str | Path, *, retries: int = 0) -> tuple[ProdTuiConfig, TmuxDriver]:
    config = load_config(path)
    return config, TmuxDriver.from_config(config, retries=retries)


_KEY_ALIASES = {
    "tab": "Tab",
    "enter": "Enter",
    "escape": "Escape",
    "esc": "Escape",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "delete": "Delete",
    "backspace": "BSpace",
    "ctrl-a": "C-a",
    "ctrl-c": "C-c",
    "ctrl-e": "C-e",
}


def _add_common_args(parser: argparse.ArgumentParser, *, default: bool = True) -> None:
    kwargs: dict[str, object] = {
        "help": "Path to production TUI harness config.yaml",
    }
    if default:
        kwargs["default"] = str(DEFAULT_CONFIG_PATH)
    else:
        kwargs["default"] = argparse.SUPPRESS
    parser.add_argument("--config", **kwargs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Drive Dispatch in a local tmux/psmux session connected to the Edge Node via SSH"
    )
    _add_common_args(parser)
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser(
        "start",
        help="Start a local tmux session and SSH into the Edge Node",
    )
    _add_common_args(start, default=False)
    start.add_argument(
        "--passcode",
        default=None,
        help="MFA passcode / RSA token to send when the server asks for one",
    )

    send = subparsers.add_parser("send", help="Send a shell command or TUI action and Enter")
    _add_common_args(send, default=False)
    send.add_argument("text")

    keys = subparsers.add_parser("keys", help="Send one or more tmux key names")
    _add_common_args(keys, default=False)
    keys.add_argument("keys", nargs="+")

    capture = subparsers.add_parser("capture", help="Capture the current tmux pane")
    _add_common_args(capture, default=False)
    capture.add_argument("--raw", action="store_true", help="Print raw capture text")
    capture.add_argument("--history-lines", type=int, default=200)

    attach = subparsers.add_parser("attach", help="Attach interactively to the local tmux session")
    _add_common_args(attach, default=False)

    stop = subparsers.add_parser("stop", help="Kill the local tmux session")
    _add_common_args(stop, default=False)

    return parser


def _safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        enc = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(enc, "replace").decode(enc))


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001
                pass
    parser = build_parser()
    args = parser.parse_args(argv)
    config, driver = driver_from_config_path(args.config)

    if args.command == "start":
        passcode = getattr(args, "passcode", None)
        ready = driver.start_session(passcode=passcode)
        if ready:
            print(
                f"Started local tmux session {config.session_name!r} "
                f"({config.terminal_width}x{config.terminal_height}) "
                f"connected to {config.host} at {config.repo_path}"
            )
        else:
            print(
                f"Session {config.session_name!r} started — waiting for authentication.\n"
                f"Send your PASSCODE with:\n"
                f"  py tools/prod_tui/robocop_tmux.py --config {args.config} send <YOUR_PASSCODE>"
            )
        return 0
    if args.command == "send":
        driver.send_keys(args.text)
        return 0
    if args.command == "keys":
        for key in args.keys:
            driver.send_key(_KEY_ALIASES.get(key.lower(), key))
        return 0
    if args.command == "capture":
        screen = driver.capture_screen(history_lines=args.history_lines)
        _safe_print(screen)
        return 0
    if args.command == "attach":
        driver.attach()
        return 0
    if args.command == "stop":
        driver.stop_session()
        return 0
    parser.error(f"Unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
