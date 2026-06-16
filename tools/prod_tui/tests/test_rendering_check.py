from __future__ import annotations

from tools.prod_tui.smoke_test import _has_box_drawing


def test_real_box_drawing_is_detected() -> None:
    assert _has_box_drawing("╭─────╮\n│ New Job │\n╰─────╯")


def test_plain_ascii_is_not_box_drawing() -> None:
    assert not _has_box_drawing("New Job\nSource  Destination\nReady to launch")


def test_cp437_mojibake_box_drawing_is_recovered() -> None:
    """A non-UTF-8 tmux/SSH locale mis-decodes UTF-8 box bytes as cp437.

    ``│`` (UTF-8 ``E2 94 82``) arrives as the cp437 string ``Γöé``. The check
    must recognise this as box drawing rather than a rendering failure.
    """
    real = "╭─────╮\n│ New Job │\n╰─────╯"
    mojibake = real.encode("utf-8").decode("cp437")
    # Sanity: the mojibake must not contain the real glyphs.
    assert not any(ch in mojibake for ch in ("│", "─", "╭"))
    assert _has_box_drawing(mojibake)
