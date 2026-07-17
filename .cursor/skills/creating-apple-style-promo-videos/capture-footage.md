# Capturing Real App Footage Headlessly

The recipes below are self-sufficient. A working reference implementation lives in the Autobench repo at `tools/promo_video/scripts/` (`capture_footage.py`, `render_footage.sh`).

## Textual TUIs (Python)

Drive the real app with Pilot and save SVG screenshots — no display needed:

```python
async with app.run_test(size=(140, 42)) as pilot:   # wide terminal = crisp footage
    ...set widget values, click, wait...
    app.save_screenshot("state.svg")
```

Pitfalls that will bite you (all hit in practice):

- **Session persistence leaks between runs.** If the app restores prior state (session files, config), your "fresh app" shot silently shows last run's values — and two screenshots come out byte-identical. Redirect the session path to a temp dir before instantiating the app. Verify captures differ: `md5sum *.svg`.
- **Pilot can't click off-screen targets** (`OutOfBounds`). `.focus()` the widget first so the scroll container brings it into view, pause, then click.
- **Poll for completion** on real analysis runs: loop on the app's run-state attribute with a deadline instead of a fixed sleep.
- **On-screen paths appear in the video.** Set output paths to something short and neutral (`outputs/report.xlsx`), not `/tmp/tmpXYZ/...`.

## SVG → transparent PNG (headless Chrome)

Textual SVGs keep the rounded window + shadow. Render them on transparency so they composite onto any background:

```bash
chrome --headless=new --disable-gpu --no-sandbox --disable-dev-shm-usage \
  --user-data-dir="$(mktemp -d)" --hide-scrollbars \
  --force-device-scale-factor=2 --default-background-color=00000000 \
  --screenshot=out.png --window-size=<viewBox WxH> file://shot.svg
```

- Read `--window-size` from the SVG `viewBox`; `scale-factor=2` gives retina sharpness.
- **Chrome lingers after writing the file** in headless environments: wrap in `timeout 60 ... || true`, then assert the PNG exists and is non-empty. A unique `--user-data-dir` per invocation avoids `SingletonLock` failures.
- Never `pkill -f chrome` from a shell whose own command line contains "chrome" — it kills the shell.

## Terminal/CLI output

Don't screen-record. Run the real command once, save the exact stdout to a text file (commit it — it is the scene's script data), then **re-type it in the video** with per-token syntax coloring and staged log reveal. Full control of pacing, and every number on screen is real. Long outputs: show a representative subset (trim, never rewrite) — budget in style-grammar.md.

## Other UI stacks

Same principles, different drivers: Playwright/CDP screenshots for web/Electron; `tmux capture-pane` or a PTY harness for curses-style CLIs (the control-cli skill covers these harnesses).
