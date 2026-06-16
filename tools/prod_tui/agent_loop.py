"""Agent loop helpers for safely driving the production TUI harness."""

from __future__ import annotations

import json
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

try:  # pragma: no cover - exercised when run as a script
    from . import safety
    from .robocop_tmux import ProdTuiConfig, TmuxDriver
except ImportError:  # pragma: no cover
    import safety
    from robocop_tmux import ProdTuiConfig, TmuxDriver

HARNESS_DIR = Path(__file__).resolve().parent
LOGS_DIR = HARNESS_DIR / "logs"
ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


@dataclass
class ScreenState:
    screen_name: str
    kerberos_ttl: int | None
    running_jobs: int
    active_jobs: list[dict[str, str]]
    form_fields: dict[str, str]
    raw_text: str


@dataclass(frozen=True)
class Action:
    name: str
    keys: list[str] = field(default_factory=list)
    text: str | None = None
    expect: str | None = None
    kerberos_ttl: int | None = None
    running_jobs: int = 0
    table_name: str = ""
    sql_text: str = ""


class AgentStep(Protocol):
    def observe(self, screen: str) -> Action: ...
    def verify(self, screen: str) -> bool: ...


class BlockedActionError(RuntimeError):
    """Raised when an agent attempts a blocked production action."""


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def detect_screen(text: str) -> str:
    if re.search(r"SQL Preview|Preview", text, re.IGNORECASE):
        return "Preview"
    if re.search(r"Browse Impala", text, re.IGNORECASE):
        return "Browser"
    if re.search(r"New Job|Source.*Destination", text, re.IGNORECASE | re.DOTALL):
        return "NewJob"
    if re.search(r"History", text, re.IGNORECASE):
        return "History"
    if re.search(r"confirm|Are you sure|\[y/N\]", text, re.IGNORECASE):
        return "Confirm"
    if re.search(r"Active Jobs|RUNNING|Kerberos", text, re.IGNORECASE):
        return "Dashboard"
    return "Unknown"


def parse_kerberos_ttl(text: str) -> int | None:
    match = re.search(r"Kerberos:\s*(?:(\d+)h)?\s*(?:(\d+)m)?", text, re.IGNORECASE)
    if match and (match.group(1) or match.group(2)):
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        return hours * 3600 + minutes * 60
    match = re.search(r"KRB_TTL=(\d+)", text)
    if match:
        return int(match.group(1))
    if re.search(r"Kerberos:\s*MISSING", text, re.IGNORECASE):
        return None
    return None


def parse_running_jobs(text: str) -> int:
    match = re.search(r"RUNNING\s+(\d+)", text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    count = len(re.findall(r"\bRunning\b", text))
    return max(0, count - 1) if "RUNNING" in text.upper() and count else count


def parse_form_fields(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    patterns = {
        "sql_file": r"SQL File\s*[:│|]?\s*([^\n│]+)",
        "schema": r"Schema\s*[:│|]?\s*([^\n│]+)",
        "table": r"Table\s*[:│|]?\s*([^\n│]+)",
        "email": r"Email\s*[:│|]?\s*([^\n│]+)",
    }
    for name, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            fields[name] = match.group(1).strip()
    return fields


def parse_active_jobs(text: str) -> list[dict[str, str]]:
    jobs: list[dict[str, str]] = []
    for line in text.splitlines():
        if re.search(r"\b(Running|Succeeded|Failed|Cancelled)\b", line):
            jobs.append({"line": line.strip()})
    return jobs


def parse_screen(screen: str) -> ScreenState:
    clean = strip_ansi(screen)
    return ScreenState(
        screen_name=detect_screen(clean),
        kerberos_ttl=parse_kerberos_ttl(clean),
        running_jobs=parse_running_jobs(clean),
        active_jobs=parse_active_jobs(clean),
        form_fields=parse_form_fields(clean),
        raw_text=clean,
    )


class AgentLoop:
    """Execute observe/send/verify steps through the production safety gate."""

    def __init__(self, driver: TmuxDriver, config: ProdTuiConfig, log_dir: Path = LOGS_DIR) -> None:
        self.driver = driver
        self.config = config
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        self.log_path = self.log_dir / f"agent_run_{stamp}.jsonl"

    def _log(self, state: ScreenState, action: Action, tier: safety.ActionTier, result: str) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "screen_state": asdict(state) | {"raw_text": state.raw_text[:1000]},
            "action": asdict(action),
            "safety_tier": tier.value,
            "result": result,
        }
        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    def _check_action(self, action: Action) -> safety.ActionTier:
        tier = safety.classify(action.name)
        if tier is safety.ActionTier.BLOCKED:
            raise BlockedActionError(f"Blocked production action: {action.name}")
        if tier is safety.ActionTier.CONTROLLED:
            violations = safety.check_launch_preconditions(
                action.kerberos_ttl,
                action.running_jobs,
                action.table_name,
                action.sql_text,
                table_prefix=self.config.table_prefix,
                smoke_query_sql=self.config.smoke_query_sql,
            )
            if violations:
                raise BlockedActionError("Controlled action preconditions failed: " + "; ".join(violations))
        return tier

    def run_step(self, step: AgentStep, timeout: float = 10.0) -> bool:
        screen = self.driver.capture_screen()
        state = parse_screen(screen)
        action = step.observe(screen)
        try:
            tier = self._check_action(action)
        except BlockedActionError:
            self._log(state, action, safety.ActionTier.BLOCKED, "blocked")
            raise

        if action.text is not None:
            self.driver.send_keys(action.text, literal=True)
        for key in action.keys:
            self.driver.send_key(key)

        next_screen = self.driver.wait_for(action.expect, timeout=timeout) if action.expect else self.driver.capture_screen()
        ok = step.verify(next_screen)
        self._log(parse_screen(next_screen), action, tier, "passed" if ok else "failed")
        return ok
