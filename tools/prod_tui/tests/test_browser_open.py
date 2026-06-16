from __future__ import annotations

import types

from tools.prod_tui.smoke_test import DASHBOARD_READY, _open_via_toggle_key

_DASHBOARD = "Jobs \u00b7 running first \u00b7 last 7 days\n n New Job  b Browse"
_BROWSER = "Browse Impala Metadata\nSchema \u00b7 table filter"


class _ToggleDriver:
    """Models the dashboard ``b`` hotkey, which opens the browser but is bound
    to Back (pop) once the browser is open. Optionally drops the first N
    keystrokes to simulate a high-latency SSH link."""

    def __init__(self, *, drop_first: int = 0) -> None:
        self.open = False
        self.presses = 0
        self._drop_remaining = drop_first

    def send_key(self, key: str) -> None:
        self.presses += 1
        if key != "b":
            return
        if self.open:
            # Inside the browser, ``b`` is Back -> closes it.
            self.open = False
            return
        if self._drop_remaining > 0:
            self._drop_remaining -= 1
            return  # keystroke dropped over SSH
        self.open = True

    def capture_screen(self, history_lines: int = 0) -> str:
        return _BROWSER if self.open else _DASHBOARD


def _ctx(driver: _ToggleDriver) -> types.SimpleNamespace:
    return types.SimpleNamespace(driver=driver)


def test_opens_on_first_landed_press() -> None:
    driver = _ToggleDriver()
    result = _open_via_toggle_key(
        _ctx(driver), "browser_opens", "b", "Browse Impala",
        dashboard_marker=DASHBOARD_READY, timeout=5.0, resend_after=0.6,
    )
    assert result.passed
    assert driver.open is True
    # Must not have toggled the browser shut with a stray resend.
    assert driver.presses == 1


def test_recovers_from_dropped_first_keystroke() -> None:
    driver = _ToggleDriver(drop_first=1)
    result = _open_via_toggle_key(
        _ctx(driver), "browser_opens", "b", "Browse Impala",
        dashboard_marker=DASHBOARD_READY, timeout=6.0, resend_after=0.6,
    )
    assert result.passed
    assert driver.open is True


def test_times_out_when_screen_never_opens() -> None:
    driver = _ToggleDriver(drop_first=10_000)  # every press is dropped
    result = _open_via_toggle_key(
        _ctx(driver), "browser_opens", "b", "Browse Impala",
        dashboard_marker=DASHBOARD_READY, timeout=2.0, resend_after=0.6,
    )
    assert not result.passed
