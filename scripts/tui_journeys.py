"""Keystroke measurement for the Autobench TUI journeys (J1-J4).

Drives the real ``BenchmarkApp`` of any checkout headlessly with Textual
Pilot and counts every key press on the minimal keyboard-only path of each
journey (docs/research/tui-redesign-phase0/02-journeys-keystrokes.md). The
engine (``execute_run``) is replaced by a fake success, so nothing is analysed
and no report is written. Validation still runs for real, which is what lets
J4b reach the validation dialog. HOME, the session file, the log folder and
the working directory point into a scratch folder; telemetry is off. Nothing
is written to the checkout.

Two UI families are supported and picked automatically from ``--repo``:

* ``legacy``: the single scrolling form before the redesign (``ddea32c`` and
  earlier); the journeys are the Phase 0 appendix script's.
* ``steps``: the five-step layout (Phase 2 PR 4 onward). Steps mount on first
  show, so the driver mounts every step first (no keys) and computes the
  shortest Tab / Shift+Tab path over the whole step flow. Step jumps use the
  command palette (owner decision 7): ^P, one digit, Enter.

Counting rules (Phase 0): every press counts and typed characters count one
each. Select overlays move with arrows (``--typeahead`` types the option's
first letter first). Focus moves by whichever of Tab or Shift+Tab is shorter.
KLM: K = 0.2 s per key, M = 1.35 s per mental operator, system response time
excluded.

Usage:
    python scripts/tui_journeys.py --repo <checkout> [--sizes 120x40 80x24]
        [--only J1 J2] [--typeahead] [--json out.json] [--work-dir DIR]

``--only`` takes journey-name prefixes; J3 (re-run after restart) needs a
J1-share-min run before it in the same invocation, which saves the session.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
ap.add_argument("--repo", required=True, type=Path, help="checkout whose tui_app.py is measured")
ap.add_argument("--sizes", nargs="+", default=["120x40", "80x24"], help="terminal sizes, WIDTHxHEIGHT")
ap.add_argument("--only", nargs="*", default=[], help="journey name prefixes to run")
ap.add_argument("--typeahead", action="store_true", help="type an option's first letter in Select overlays")
ap.add_argument("--json", type=Path, default=None, help="write results here")
ap.add_argument("--work-dir", type=Path, default=None, help="scratch folder (default: a new temp dir)")
ap.add_argument("--verbose", action="store_true", help="print every key and the focus after it")
args = ap.parse_args()

REPO = args.repo.resolve()
S = (args.work_dir or Path(tempfile.mkdtemp(prefix="tui-journeys-"))).resolve()
WORK = S / "work"  # the app's cwd (quick picks, override files)
(WORK / "data").mkdir(parents=True, exist_ok=True)
(S / "home").mkdir(exist_ok=True)
DEMO = REPO / "docs" / "autobench_demo.csv"
# J4b fixture: the demo data with one negative metric value (a validation ERROR).
_rows = DEMO.read_text().splitlines()
_bad = _rows[:2] + [_rows[2].replace(",120,1200,", ",-120,1200,")] + _rows[3:]
(WORK / "data" / "bad_demo.csv").write_text("\n".join(_bad) + "\n")
shutil.copy(DEMO, WORK / "data" / "autobench_demo.csv")
# Quick picks list newest first: keep the demo file first, as in Phase 0.
os.utime(WORK / "data" / "bad_demo.csv", (time.time() - 60, time.time() - 60))

os.environ["HOME"] = str(S / "home")
os.environ["AUTOBENCH_TELEMETRY"] = "0"
os.environ["AUTOBENCH_LOG_DIR"] = str(S / "logs")
os.chdir(WORK)
sys.path.insert(0, str(REPO))

import tui_app  # noqa: E402
from core.contracts import AnalysisArtifacts  # noqa: E402
from textual.widgets import Select, SelectionList  # noqa: E402
from textual.widgets._select import SelectOverlay  # noqa: E402

FAMILY = "steps" if hasattr(tui_app, "STEPS") and hasattr(tui_app.BenchmarkApp, "ensure_step") else "legacy"
tui_app.SESSION_FILE = S / "home" / "session.yaml"
EXECUTED: list = []
CSV = "data/autobench_demo.csv"
BAD_CSV = "data/bad_demo.csv"
ARROWS = {"up", "down", "left", "right"}


def _fake_execute_run(request, logger, **_hooks):
    EXECUTED.append(request)
    return AnalysisArtifacts(
        metadata={},
        compliance_summary={
            "posture": request.compliance_posture or "strict",
            "compliance_verdict": "fully_compliant",
            "acknowledgement_state": "n/a",
        },
        report_paths=[str(S / "FAKE_report_not_written.xlsx")],
        privacy_sink_authorized=True,
        privacy_log_authorized=False,
    )


tui_app.execute_run = _fake_execute_run


@dataclass
class Meter:
    name: str
    keys: list = field(default_factory=list)  # (key, category, note)
    mental: list = field(default_factory=list)  # labels of M operators
    notes: list = field(default_factory=list)

    @staticmethod
    def cat(k: str) -> str:
        if k in ("tab", "shift+tab"):
            return "tab"
        if k in ARROWS:
            return "arrow"
        if k == "enter":
            return "enter"
        if k == "space":
            return "space"
        if len(k) == 1:
            return "typed"
        return "chord"  # ctrl+r, escape, f1 ...

    def summary(self) -> dict:
        c: Dict[str, int] = {}
        for _, cat, _ in self.keys:
            c[cat] = c.get(cat, 0) + 1
        k, m = len(self.keys), len(self.mental)
        return {
            "journey": self.name,
            "total_keys": k,
            **{f"n_{x}": c.get(x, 0) for x in ("tab", "arrow", "enter", "space", "typed", "chord")},
            "M": m,
            "klm_seconds": round(k * 0.2 + m * 1.35, 1),
            "notes": self.notes,
            "seq": self.rle(),
        }

    def rle(self) -> str:
        """Run-length key sequence, typed text collapsed: 'type(23) enter tab×2 ...'."""
        out, prev, n = [], None, 0
        for k, cat, _ in self.keys + [(None, None, None)]:
            tok = "type" if cat == "typed" else k
            if tok == prev:
                n += 1
                continue
            if prev is not None:
                out.append(f"{prev}({n})" if prev == "type" else (f"{prev}×{n}" if n > 1 else prev))
            prev, n = tok, 1
        return " ".join(out)


class Driver:
    """Key presses with counting; ``go`` differs per UI family."""

    def __init__(self, pilot: Any, meter: Meter) -> None:
        self.p, self.app, self.m = pilot, pilot.app, meter

    async def press(self, *keys: str, note: str = "") -> None:
        for k in keys:
            self.m.keys.append((k, Meter.cat(k), note))
            await self.p.press(k)
            if args.verbose:
                print(f"    {k:10s} -> {self.fid()}  ({note})")
        await self.p.pause()

    async def type(self, text: str, note: str = "") -> None:
        await self.press(*list(text), note=note)

    def M(self, label: str) -> None:  # noqa: N802 - KLM operator name
        self.m.mental.append(label)

    def fid(self) -> Optional[str]:
        f = self.app.focused
        return None if f is None else (f.id or type(f).__name__)

    def chain(self) -> List[str]:
        return [w.id or type(w).__name__ for w in self.app.screen.focus_chain]

    async def settle_focus(self) -> None:
        for _ in range(40):
            if getattr(self.app, "_pending_focus", None) is None:
                break
            await self.p.pause(0.02)
        await self.p.pause()

    async def go(self, target: str, note: str = "") -> None:
        chain = self.chain()
        if target not in chain:
            raise RuntimeError(f"{target} not in focus chain: {chain}")
        cur = self.fid()
        i, j, n = (chain.index(cur) if cur in chain else -1), chain.index(target), len(chain)
        fwd, back = (j - i) % n, (i - j) % n
        key, steps = ("tab", fwd) if fwd <= back else ("shift+tab", back)
        for _ in range(steps):
            await self.press(key, note=note or f"to {target}")
            await self.settle_focus()
        assert self.fid() == target, (self.fid(), target, chain)

    async def pick(self, select_id: str, value: Any, note: str = "", navigate: bool = True) -> None:
        """Open a Select overlay, move to the option, Enter."""
        if navigate:
            await self.go(select_id, note)
        sel = self.app.query_one(f"#{select_id}", Select)
        await self.press("enter", note=f"open {select_id}")
        overlay = sel.query_one(SelectOverlay)
        values = [v for _, v in sel._options]
        prompts = [str(p) for p, _ in sel._options]
        tgt = values.index(value)
        if args.typeahead and str(value)[:1].isalnum():
            await self.press(prompts[tgt].strip()[0], note="type-ahead")
        guard = 0
        # Pressed until highlighted, so disabled separator rows are skipped
        # exactly as the widget skips them.
        while overlay.highlighted != tgt and guard < 120:
            cur = -1 if overlay.highlighted is None else overlay.highlighted
            await self.press("down" if tgt > cur else "up", note=f"seek {value}")
            guard += 1
        await self.press("enter", note=f"choose {value}")
        await self.p.pause(0.1)
        assert sel.value == value, (select_id, sel.value, value)

    async def check(self, list_id: str, values: List[str], note: str = "", navigate: bool = True) -> None:
        if navigate:
            await self.go(list_id, note)
        sl = self.app.query_one(f"#{list_id}", SelectionList)
        for v in values:
            idx = next(i for i in range(sl.option_count) if sl.get_option_at_index(i).value == v)
            guard = 0
            while sl.highlighted != idx and guard < 60:
                cur = -1 if sl.highlighted is None else sl.highlighted
                await self.press("down" if idx > cur else "up", note=f"seek {v}")
                guard += 1
            await self.press("space", note=f"toggle {v}")
        assert set(values) <= set(sl.selected), (list_id, sl.selected)

    async def wait_done(self, timeout: float = 60.0) -> str:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.app._run_state in ("success", "error", "blocked"):
                return self.app._run_state
            if type(self.app.screen).__name__ != "Screen":
                return "modal:" + type(self.app.screen).__name__
            await self.p.pause(0.1)
        return self.app._run_state

    async def confirm_modal(self, button_id: str, note: str) -> None:
        """Activate a dialog button from wherever the dialog put initial focus."""
        if self.fid() != button_id:
            await self.go(button_id, note=f"{note}: focus {button_id}")
        await self.press("enter", note=note)

    async def finish_run(self) -> str:
        for _ in range(3):
            state = await self.wait_done()
            if state == "modal:ConfirmScreen":
                self.m.notes.append(f"consent modal, focus={self.fid()}")
                self.M("read + accept accuracy_first consent")
                await self.confirm_modal("btn_confirm_yes", "accept consent")
            elif state == "modal:ClearingSpendConfirmScreen":
                self.m.notes.append(f"clearing-spend modal, focus={self.fid()}")
                self.M("read + confirm clearing-spend basis")
                await self.confirm_modal("btn_confirm_yes", "confirm clearing spend")
            elif state == "modal:ValidationModal":
                self.M("read validation issues")
                await self.confirm_modal("btn_proceed", "proceed")
            else:
                return state
            await self.p.pause(0.2)
        return await self.wait_done()


class StepsDriver(Driver):
    """Five-step layout: Tab walks the steps in order (data..review) and wraps."""

    def chain(self) -> List[str]:
        app = self.app
        if app.screen is not getattr(app, "_main_screen", None) or app._results_view_open():
            return super().chain()
        out = []
        for step in tui_app.STEPS:
            body = app.query_one(f"#{step.container_id}")
            for w in body.walk_children():
                if not w.can_focus or w.disabled or not w.allow_focus():
                    continue
                if any(not n.display for n in w.ancestors_with_self if n is not body and n is not app):
                    continue
                if any(getattr(n, "disabled", False) for n in w.ancestors):
                    continue
                if any(
                    getattr(a, "collapsed", False) and a is not w
                    for a in w.ancestors
                    if type(a).__name__ in ("Collapsible", "Disclosure")
                ) and type(w).__name__ != "CollapsibleTitle":
                    continue
                out.append(w.id or type(w).__name__)
        return out

    async def jump_step(self, digit: str, expect_step: str) -> None:
        """Owner decision 7: the palette is the step jump (^P, digit, Enter)."""
        await self.press("ctrl+p", note="palette")
        await self.p.pause(0.3)
        await self.press(digit, note=f"step {digit}")
        await self.p.pause(0.5)
        await self.press("enter", note="go to step")
        await self.settle_focus()
        await self.p.pause(0.2)
        assert self.app._current_step == expect_step, self.app._current_step


# ── Legacy journeys (Phase 0 appendix, unchanged paths) ──────────────────


async def legacy_load_csv(d: Driver, path: str = CSV, via_picker: bool = False) -> None:
    d.M("recall/locate CSV path")
    if via_picker:
        await d.press("ctrl+o", note="open picker")
        await d.p.pause(0.3)
        quick = d.app.screen.query_one("#picker_quick_list")
        if hasattr(quick, "option_count"):  # OptionList picker (Phase 2 PR 2)
            items = [quick.get_option_at_index(i).id for i in range(quick.option_count)]
            cur = quick.highlighted or 0
        else:  # ListView of file items
            items = [c.file_path for c in quick.children]
            cur = quick.index if quick.index is not None else 0
        if d.fid() != "picker_quick_list":
            await d.go("picker_quick_list")
        tgt = items.index(path)
        await d.press(*["down"] * (tgt - cur), note="seek file")
        await d.press("enter", note="pick file")
    else:
        assert d.fid() == "csv_path"
        await d.type(path, note="type CSV path")
        await d.press("enter", note="load headers")
    await d.p.pause(0.3)


async def legacy_j1(d: Driver, *, via_picker: bool = False, time_col: bool = False, dims_by: str = "tab") -> str:
    await legacy_load_csv(d, via_picker=via_picker)
    d.M("verify entity column default (issuer_name)")
    d.M("choose target entity")
    await d.pick("entity_name", "Target")
    if time_col:
        d.M("decide time column")
        await d.pick("time_col", "year_month")
    d.M("decide preset (accept default compliance_strict)")
    d.M("verify metric default (txn_cnt)")
    d.M("choose dimensions")
    await d.check("share_dims", ["card_type", "input_mode"])
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.finish_run()
    d.M("read result panel")
    return state


async def legacy_j2(d: Driver, *, fraud: bool = False, preset: Optional[str] = None, **_kw: Any) -> str:
    await legacy_load_csv(d)
    d.M("choose target entity")
    await d.pick("entity_name", "Target")
    if preset:
        d.M(f"choose preset {preset}")
        await d.pick("preset_select", preset)
    d.M("switch to Rate tab")
    await d.go("ContentTabs")
    await d.press("right", note="Rate tab")
    await d.p.pause(0.2)
    assert tui_app.BenchmarkApp._analysis_mode(d.app) == "rate"
    d.M("choose Total (default txn_cnt is wrong for this file)")
    await d.pick("rate_total", "total")
    d.M("choose Approved column")
    await d.pick("rate_approved", "approved")
    if fraud:
        d.M("choose Fraud column")
        await d.pick("rate_fraud", "fraud")
    d.M("choose dimensions")
    await d.check("rate_dims", ["card_type", "input_mode"])
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.finish_run()
    d.M("read result panel")
    return state


async def legacy_j3(d: Driver, **_kw: Any) -> str:
    await legacy_load_csv(d)
    d.m.notes.append(f"after CSV reload: dims={list(d.app.query_one('#share_dims').selected)}")
    d.M("re-choose target entity (never restored)")
    await d.pick("entity_name", "Target")
    d.M("change the parameter: preset -> strategic_consistency")
    await d.pick("preset_select", "strategic_consistency")
    d.M("re-choose dimensions (lost)")
    await d.check("share_dims", ["card_type", "input_mode"])
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.finish_run()
    d.M("read result panel")
    return state


async def legacy_j3b(d: Driver, **_kw: Any) -> str:
    await legacy_j1(d)
    k0, m0 = len(d.m.keys), len(d.m.mental)
    d.M("change the parameter: preset -> strategic_consistency")
    await d.pick("preset_select", "strategic_consistency")
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.finish_run()
    d.M("read result panel")
    d.m.keys, d.m.mental = d.m.keys[k0:], d.m.mental[m0:]  # count only the re-run
    return state


async def legacy_j4a(d: Driver) -> str:
    """Forget dimensions, the launch is refused, recover."""
    await legacy_load_csv(d)
    d.M("choose target entity")
    await d.pick("entity_name", "Target")
    d.M("initiate run (dims forgotten)")
    await d.press("ctrl+r", note="run")
    await d.p.pause(1.0)
    d.m.notes.append(f"after block: state={d.app._run_state} focus={d.fid()}")
    d.M("read toast, understand what is missing")
    await d.check("share_dims", ["card_type"])
    d.M("re-run")
    await d.press("ctrl+r", note="run")
    return await d.finish_run()


async def legacy_j4b(d: Driver) -> str:
    """Negative metric: validation ERROR, cancel, fix the file, re-run."""
    await legacy_load_csv(d, path=BAD_CSV)
    d.M("choose target entity")
    await d.pick("entity_name", "Target")
    d.M("choose dimensions")
    await d.check("share_dims", ["card_type", "input_mode"])
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.wait_done()
    d.m.notes.append(f"first state={state} modal_focus={d.fid()}")
    if state == "modal:ValidationModal":
        d.M("read issue list")
        await d.press("escape", note="cancel validation")
        await d.p.pause(0.3)
    d.M("fix data outside TUI, re-point CSV path")
    await d.go("csv_path")
    await d.press("ctrl+u", note="clear path")
    await d.type(CSV, note="type corrected path")
    await d.press("enter", note="reload headers")
    await d.p.pause(0.3)
    d.M("re-run")
    await d.press("ctrl+r", note="run")
    return await d.finish_run()


# ── Step-layout journeys (Phase 2 PR 4 onward) ───────────────────────────


async def steps_load_csv(d: StepsDriver, path: str = CSV, via_picker: bool = False) -> None:
    d.M("recall/locate CSV path")
    if via_picker:
        await d.press("ctrl+o", note="open picker")
        screen = d.app.screen
        for _ in range(100):  # quick picks load in a worker (PR 6)
            if getattr(screen, "_quick_loaded", True):
                break
            await d.p.pause(0.05)
        await d.p.pause(0.3)
        quick = d.app.screen.query_one("#picker_quick_list")
        items = [quick.get_option_at_index(i).id for i in range(quick.option_count)]
        if d.fid() != "picker_quick_list":
            await d.go("picker_quick_list")
        tgt, cur = items.index(path), quick.highlighted or 0
        await d.press(*["down"] * (tgt - cur), note="seek file")
        await d.press("enter", note="pick file")
    else:
        assert d.fid() == "csv_path"
        await d.type(path, note="type CSV path")
        await d.press("enter", note="load headers")
    await d.settle_focus()
    await d.p.pause(0.3)
    d.m.notes.append(f"focus after load: {d.fid()}")


async def steps_target(d: StepsDriver) -> None:
    d.M("choose target entity")
    # PR 5: focus is already on Target entity after the load.
    await d.pick("entity_name", "Target", navigate=d.fid() != "entity_name")


async def steps_j1(d: StepsDriver, *, via_picker: bool = False, time_col: bool = False, dims_by: str = "tab") -> str:
    await steps_load_csv(d, via_picker=via_picker)
    d.M("verify entity column default (issuer_name)")
    await steps_target(d)
    d.M("decide preset (accept default compliance_strict)")
    d.M("verify metric default (txn_cnt)")
    if time_col:
        d.M("decide time column")
        await d.go("more_options_title" if "more_options_title" in d.chain() else "CollapsibleTitle")
        await d.press("enter", note="open More options")
        await d.p.pause(0.3)
        await d.pick("time_col", "year_month")
    d.M("choose dimensions")
    if dims_by == "ctrl+r":
        # ^R while not ready jumps to the first blocker: the dimensions list.
        await d.press("ctrl+r", note="jump to first blocker")
        await d.p.pause(0.5)
        await d.settle_focus()
        assert d.fid() == "dims", d.fid()
        await d.check("dims", ["card_type", "input_mode"], navigate=False)
    elif dims_by == "palette":
        await d.jump_step("3", "analysis")
        assert d.fid() == "dims", d.fid()
        await d.check("dims", ["card_type", "input_mode"], navigate=False)
    else:
        await d.check("dims", ["card_type", "input_mode"])
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.finish_run()
    d.M("read result panel")
    return state


async def steps_j2(d: StepsDriver, *, fraud: bool = False, preset: Optional[str] = None, preset_by: str = "tab") -> str:
    await steps_load_csv(d)
    await steps_target(d)
    d.M("switch to Rate")
    await d.go("mode_switch")
    await d.press("right", note="Rate")
    await d.p.pause(0.2)
    assert d.app.form.mode == "rate"
    d.M("choose Total (no default)")
    await d.pick("rate_total", "total")
    d.M("choose Approved column")
    await d.pick("rate_approved", "approved")
    if fraud:
        d.M("choose Fraud column")
        await d.pick("rate_fraud", "fraud")
    d.M("choose dimensions")
    await d.check("dims", ["card_type", "input_mode"])
    if preset:
        d.M(f"choose preset {preset}")
        if preset_by == "palette":
            await d.jump_step("4", "privacy")
            assert d.fid() == "preset_select", d.fid()
            await d.pick("preset_select", preset, navigate=False)
        else:
            await d.pick("preset_select", preset)
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.finish_run()
    d.M("read result panel")
    return state


async def steps_j3(d: StepsDriver, *, preset_by: str = "tab") -> str:
    restored = {"mode": d.app.form.mode, "preset": d.app.form.preset, "pending": dict(d.app._pending_session)}
    d.m.notes.append(f"restored at mount: {restored}")
    await steps_load_csv(d)
    d.m.notes.append(
        f"after load: metric={d.app.form.metric} dims={d.app.form.dimensions} restored={sorted(d.app.form.restored)}"
    )
    d.M("re-choose target entity (never restored)")
    await steps_target(d)
    d.M("change the parameter: preset -> strategic_consistency")
    if preset_by == "palette":
        await d.jump_step("4", "privacy")
        await d.pick("preset_select", "strategic_consistency", navigate=False)
    else:
        await d.pick("preset_select", "strategic_consistency")
    d.M("verify restored values")
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.finish_run()
    d.M("read result panel")
    return state


async def steps_j3b(d: StepsDriver, *, preset_by: str = "tab") -> str:
    await steps_j1(d)
    k0, m0 = len(d.m.keys), len(d.m.mental)
    d.m.notes.append(f"focus after run 1: {d.fid()} step={d.app._current_step}")
    d.M("change the parameter: preset -> strategic_consistency")
    if d.app._results_view_open() and preset_by != "palette":
        # Below 110 columns the results view is open after a run: ^T back to the form.
        await d.press("ctrl+t", note="back to the form")
    if preset_by == "palette":
        await d.jump_step("4", "privacy")
        await d.pick("preset_select", "strategic_consistency", navigate=False)
    else:
        await d.pick("preset_select", "strategic_consistency")
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.finish_run()
    d.M("read result panel")
    d.m.keys, d.m.mental = d.m.keys[k0:], d.m.mental[m0:]  # count only the re-run
    return state


async def steps_j4a(d: StepsDriver) -> str:
    """Forget dimensions: ^R names the blocker and focuses it; recover."""
    await steps_load_csv(d)
    await steps_target(d)
    d.M("initiate run (dims forgotten)")
    await d.press("ctrl+r", note="run")
    await d.p.pause(0.5)
    await d.settle_focus()
    d.m.notes.append(f"after block: state={d.app._run_state} focus={d.fid()} step={d.app._current_step}")
    d.M("read the action bar, understand what is missing")
    await d.check("dims", ["card_type"], navigate=d.fid() != "dims")
    d.M("re-run")
    await d.press("ctrl+r", note="run")
    return await d.finish_run()


async def steps_j4b(d: StepsDriver) -> str:
    """Negative metric: validation ERROR, cancel, fix the file, re-run."""
    await steps_load_csv(d, path=BAD_CSV)
    await steps_target(d)
    d.M("choose dimensions")
    await d.check("dims", ["card_type", "input_mode"])
    d.M("initiate run")
    await d.press("ctrl+r", note="run")
    state = await d.wait_done()
    d.m.notes.append(f"first state={state} modal_focus={d.fid()}")
    if state == "modal:ValidationModal":
        d.M("read issue list")
        await d.press("escape", note="cancel validation")
        for _ in range(100):  # the form unlocks when the attempt has ended
            if d.app._run_state not in ("validating", "running"):
                break
            await d.p.pause(0.05)
        await d.p.pause(0.3)
        await d.settle_focus()
        d.m.notes.append(f"after cancel: state={d.app._run_state} focus={d.fid()}")
    d.M("fix data outside TUI, re-point CSV path")
    await d.go("csv_path")
    await d.press("ctrl+u", note="clear path")
    await d.type(CSV, note="type corrected path")
    await d.press("enter", note="reload headers")
    await d.settle_focus()
    await d.p.pause(0.3)
    d.m.notes.append(f"after reload: entity={d.app.form.entity} dims={d.app.form.dimensions}")
    d.M("re-run")
    await d.press("ctrl+r", note="run")
    return await d.finish_run()


JourneyFn = Callable[..., Awaitable[str]]
PLANS: Dict[str, List[Tuple[str, JourneyFn, Dict[str, Any]]]] = {
    "legacy": [
        ("J1-share-min", legacy_j1, {}),
        ("J3-rerun-after-restore", legacy_j3, {"_fresh": False}),
        ("J1-share+time", legacy_j1, {"time_col": True}),
        ("J1-share-picker", legacy_j1, {"via_picker": True}),
        ("J2-rate-approval", legacy_j2, {}),
        ("J2-rate-fraud", legacy_j2, {"fraud": True}),
        ("J2-rate-fraud-accuracy-first", legacy_j2, {"fraud": True, "preset": "low_distortion"}),
        ("J3b-rerun-same-process", legacy_j3b, {}),
        ("J4a-preflight-recover", legacy_j4a, {}),
        ("J4b-validation-recover", legacy_j4b, {}),
    ],
    "steps": [
        ("J1-share-min", steps_j1, {}),
        ("J3-rerun-after-restore", steps_j3, {"_fresh": False}),
        ("J3-rerun-after-restore-palette", steps_j3, {"_fresh": False, "preset_by": "palette"}),
        ("J1-share+time", steps_j1, {"time_col": True}),
        ("J1-share-ctrl-r-jump", steps_j1, {"dims_by": "ctrl+r"}),
        ("J1-share-palette-jump", steps_j1, {"dims_by": "palette"}),
        ("J1-share-picker", steps_j1, {"via_picker": True}),
        ("J2-rate-approval", steps_j2, {}),
        ("J2-rate-fraud", steps_j2, {"fraud": True}),
        ("J2-rate-fraud-accuracy-first", steps_j2, {"fraud": True, "preset": "low_distortion"}),
        ("J2-rate-fraud-accuracy-first-palette", steps_j2,
         {"fraud": True, "preset": "low_distortion", "preset_by": "palette"}),
        ("J3b-rerun-same-process", steps_j3b, {}),
        ("J3b-rerun-same-process-palette", steps_j3b, {"preset_by": "palette"}),
        ("J4a-preflight-recover", steps_j4a, {}),
        ("J4b-validation-recover", steps_j4b, {}),
    ],
}


async def run_journey(name: str, fn: JourneyFn, size: Tuple[int, int], fresh_session: bool = True, **kw: Any) -> dict:
    if fresh_session and tui_app.SESSION_FILE.exists():
        tui_app.SESSION_FILE.unlink()
    m = Meter(f"{name}@{size[0]}x{size[1]}")
    EXECUTED.clear()
    async with tui_app.BenchmarkApp().run_test(size=size) as pilot:
        await pilot.pause(0.3)
        if FAMILY == "steps":
            # Mount every step up front so the Tab path can be computed (no keys).
            for step in tui_app.STEPS:
                await pilot.app.ensure_step(step.id)
            await pilot.pause()
            d: Driver = StepsDriver(pilot, m)
        else:
            d = Driver(pilot, m)
        assert pilot.app.focused is not None and pilot.app.focused.id == "csv_path"
        state = await fn(d, **kw)
        m.notes.append(f"final state={state}; engine calls={len(EXECUTED)}")
        if name == "J1-share-min" and fresh_session:
            await pilot.press("ctrl+q")  # saves the session for J3
            await pilot.pause(0.2)
    return m.summary()


async def main() -> List[dict]:
    results: List[dict] = []
    for size_text in args.sizes:
        size = tuple(int(v) for v in size_text.split("x"))
        for name, fn, kw in PLANS[FAMILY]:
            if args.only and not any(name.startswith(o) for o in args.only):
                continue
            kw = dict(kw)
            fresh = kw.pop("_fresh", True)
            try:
                results.append(await run_journey(name, fn, size, fresh_session=fresh, **kw))
            except Exception as exc:  # report and continue with the next journey
                traceback.print_exc()
                results.append({"journey": f"{name}@{size[0]}x{size[1]}", "error": repr(exc)})
    return results


if __name__ == "__main__":
    res = asyncio.run(main())
    meta = {"repo": str(REPO), "family": FAMILY, "typeahead": args.typeahead, "work_dir": str(S)}
    if args.json:
        args.json.write_text(json.dumps({"meta": meta, "results": res}, indent=1, default=str))
    print(f"# {meta}")
    for r in res:
        if "error" in r:
            print(f"{r['journey']:46s} ERROR {r['error']}")
            continue
        print(
            f"{r['journey']:46s} keys={r['total_keys']:3d} typed={r['n_typed']:2d} tab={r['n_tab']:2d} "
            f"arrow={r['n_arrow']:2d} M={r['M']:2d} KLM={r['klm_seconds']}s | {r['seq']}"
        )
        for n in r["notes"]:
            print("      -", n)
    sys.stdout.flush()
    # Thread workers of the last app may still be parked; do not wait for them.
    os._exit(0)
