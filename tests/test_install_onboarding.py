"""Installer onboarding should give users a short path to running dispatch."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_install_updates_path_instead_of_alias_only() -> None:
    install_script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert 'export PATH="$HOME/.local/bin:$PATH"' in install_script
    assert "alias dispatch=" not in install_script


def test_install_prints_current_session_next_step() -> None:
    install_script = (ROOT / "install.sh").read_text(encoding="utf-8")

    assert "To use dispatch in this shell now:" in install_script
    assert "export PATH=" in install_script
