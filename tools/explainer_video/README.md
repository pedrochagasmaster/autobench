# Autobench onboarding video

A [Remotion](https://remotion.dev) composition that walks a new analyst from
first access to a verified first run. It follows the teaching order of
[`docs/autobench-onboarding.html`](../../docs/autobench-onboarding.html) and is
built around a recorded walkthrough of the real TUI.

- Composition id: `AutobenchOnboarding`
- 1920×1080, 30 fps, 8445 frames (4 minutes 41 seconds)
- Chapters: what it does · set up · prepare · run (terminal UI, then CLI) · verify

## Setup

```bash
cd tools/explainer_video
npm install
npm run assets     # captures the TUI and synthesises the music bed
```

`npm run assets` runs two Python scripts and must be run before the first
render. Neither output is committed:

| Script | Writes | Why it is generated |
| --- | --- | --- |
| `scripts/capture_tui.py` | `public/tui/*.svg` and `manifest.json` | Screens of the real TUI, so the video cannot drift from the app |
| `scripts/make_music_bed.py` | `public/music_bed.wav` | Avoids committing a binary audio artifact |

## Preview and render

```bash
npx remotion studio --no-open
npx remotion render AutobenchOnboarding out/autobench_onboarding.mp4
```

Every scene is also registered on its own, so a single chapter or walkthrough
step can be iterated on without rendering the whole timeline:

```bash
npx remotion still Scene-s10 out/stills/s10.png --frame=200
npx remotion render Scene-t13 out/log_tail.mp4
```

Scene ids, chapter grouping, and per-scene durations live in `src/timeline.ts`,
which fails the build if the plan stops summing to the expected total.

## The TUI walkthrough is a recording, not a mock

`scripts/capture_tui.py` imports `tui_app.BenchmarkApp`, drives it headlessly
through the steps documented under "5 · Your first run", and exports one SVG per
step. The analysis really executes against `docs/autobench_demo.csv`, so the
closing screens show a real execution log, a real
`Compliance Verdict: fully_compliant`, and a real output path.

The capture refuses to publish screenshots unless the app really ran the
documented configuration: entity column `issuer_name`, target `Target`, time
column `year_month`, preset `compliance_strict`, metric `txn_cnt`, dimensions
`card_type`, `input_mode`, `card_type_input_mode`, and a run state of `success`.
It also refuses to write a screenshot containing a named institution.

Because the screenshots are vector SVG, the composition can push in on a single
widget and the terminal text stays sharp. `src/components/TuiShot.tsx` does the
framing; the highlight rectangles come from the widget regions recorded at
capture time, so a callout cannot point at the wrong control.

## Props

| Prop | Default | Effect |
| --- | --- | --- |
| `showControlReference` | `true` | Names Mastercard Control 3.2 under the privacy rule table |
| `showNarration` | `true` | Renders the narration as on-screen captions |
| `showProgress` | `true` | Thin chapter progress line at the top of the frame |
| `musicGain` | `0.22` | Bed level between the title card and the outro fade |

```bash
npx remotion render AutobenchOnboarding out/external_cut.mp4 \
  --props='{"showControlReference": false, "showNarration": true, "showProgress": true, "musicGain": 0.22}'
```

## Two standing decisions

**Entity names.** Every frame uses the generic `Target` / `P1…P6` labels of
`docs/autobench_demo.csv`. No real institution is named anywhere, and the
capture script fails if a screenshot contains one. The Compliance Declarations
group in the TUI, which does name a client overlay, stays collapsed throughout.

**Control 3.2.** `showControlReference` defaults to `true`, so the control is
named under the privacy rule table. The repository README already names it
publicly, so this discloses nothing new internally. Render with
`showControlReference: false` for any cut that leaves the organisation.

## Where the on-screen content comes from

`src/data/facts.ts` holds every string and number, traced to source:

| On screen | Source |
| --- | --- |
| Teaching order, callouts, troubleshooting | `docs/autobench-onboarding.html` |
| Privacy rule table | `core/privacy_validator.py`, `config/privacy_rules.yaml` |
| `Global-LP` / `Per-Dimension-LP` / `Per-Dimension-Bayesian` | `core/global_weight_optimizer.py` |
| Summary sheet labels and values | the workbook the demo command actually writes |
| Preset names and posture guidance | `presets/*.yaml`, `core/contracts.py` |
| Shortcut keys | `BenchmarkApp.BINDINGS` in `tui_app.py` |
| CLI command | `benchmark.py`, verified by running it |
| Edge node commands | `README.md`, `onboarding.md` |

The demo peer set checks itself at module load: the "before" chart has to breach
the 6/30 cap and the "after" chart has to clear it, or the render fails rather
than teaching a number the data does not support.

## Narration

`src/data/voiceover.ts` holds one line per chapter; the walkthrough lines come
from the capture manifest, so a caption and the screenshot beside it can never
describe different steps. There is no recorded voice track, so the lines render
as captions. When a read is recorded, dub it over the render and re-render with
`showNarration: false`.
