from __future__ import annotations

import pytest

from tools.prod_tui.agent_loop import Action, AgentLoop, BlockedActionError, detect_screen, parse_screen
from tools.prod_tui.robocop_tmux import ProdTuiConfig, TmuxDriver


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Active Jobs\nRUNNING 1\nKerberos: 1h 05m", "Dashboard"),
        ("New Job\nSource  Destination", "NewJob"),
        ("Browse Impala\nSHOW TABLES", "Browser"),
        ("History\nSucceeded", "History"),
        ("SQL Preview\nSELECT 1", "Preview"),
        ("Confirm Launch? [y/N]", "Confirm"),
    ],
)
def test_detect_screen_types(text: str, expected: str) -> None:
    assert detect_screen(text) == expected


def test_parse_screen_extracts_dashboard_state() -> None:
    state = parse_screen("Active Jobs\nRUNNING 2\nKerberos: 0h 06m\njob_a Running")
    assert state.screen_name == "Dashboard"
    assert state.kerberos_ttl == 360
    assert state.running_jobs == 2
    assert state.active_jobs


def test_parse_screen_extracts_form_fields() -> None:
    state = parse_screen(
        "New Job\nSQL File: /tmp/dispatch_smoke_test.sql\nSchema: aa_enc\nTable: dispatch_smoke_user\nEmail: test@example.com"
    )
    assert state.screen_name == "NewJob"
    assert state.form_fields["sql_file"] == "/tmp/dispatch_smoke_test.sql"
    assert state.form_fields["schema"] == "aa_enc"
    assert state.form_fields["table"] == "dispatch_smoke_user"
    assert state.form_fields["email"] == "test@example.com"


def test_parse_screen_strips_ansi() -> None:
    state = parse_screen("\x1b[31mActive Jobs\x1b[0m\nKRB_TTL=301")
    assert state.screen_name == "Dashboard"
    assert state.kerberos_ttl == 301
    assert "\x1b" not in state.raw_text


class _BlockedStep:
    def observe(self, screen: str) -> Action:
        return Action(name="drop_table", keys=["d"])

    def verify(self, screen: str) -> bool:
        return True


def test_agent_loop_blocks_blocked_actions(tmp_path) -> None:
    driver = TmuxDriver("user@edge", "session", "/repo")
    driver.capture_screen = lambda: "Active Jobs"  # type: ignore[method-assign]
    loop = AgentLoop(driver, ProdTuiConfig(host="user@edge", repo_path="/repo"), log_dir=tmp_path)
    with pytest.raises(BlockedActionError):
        loop.run_step(_BlockedStep())
    assert list(tmp_path.glob("agent_run_*.jsonl"))
