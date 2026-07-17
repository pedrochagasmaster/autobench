# Autobench Promo Video

An Apple-ad style promotional video for Autobench, built with
[Remotion](https://www.remotion.dev/) (React-rendered video). All app footage
is real: the TUI frames are captured from the live application driven by
Textual's Pilot, and the terminal output comes from an actual
`benchmark.py share` run on `tests/fixtures/gate_demo.csv`.

The video is ~59 s, 1920x1080 at 30 fps: cold open → wordmark reveal → real
CLI run → real TUI walkthrough → Control 3.2 privacy caps → feature beats →
`fully_compliant` verdict → closing lockup. Scenes crossfade into each other
and the whole frame carries a subtle vignette and animated film grain. The
ambient soundtrack is synthesized deterministically by
`scripts/make_soundtrack.py` (numpy only, no licensed audio) with cue hits —
a riser/boom under the wordmark reveal and a bell chime on the verdict —
aligned to the Remotion timeline.

## Rendering

Requires Node 18+, Python 3.10+ with the repo dev dependencies installed, and
Chrome (for footage capture; Remotion downloads its own headless browser).

```bash
cd tools/promo_video
npm install

# 1. Capture real TUI footage (writes footage_svg/*.svg), then rasterize it.
python3 scripts/capture_footage.py
bash scripts/render_footage.sh

# 2. Stage fonts and synthesize the soundtrack into public/.
bash scripts/prepare_assets.sh

# 3. Render the video.
npm run render   # -> out/autobench-promo.mp4
```

`npm run studio` opens the Remotion studio for interactive editing.

Generated assets (`footage_svg/`, `public/footage|fonts|audio`, `out/`) are
gitignored; only the composition source and generator scripts are tracked.

## Structure

- `src/Root.tsx` — composition timeline (scene order and durations)
- `src/scenes/` — one component per scene
- `src/components.tsx`, `src/theme.ts` — shared motion/typography primitives
- `scripts/` — footage capture, asset staging, soundtrack synthesis
