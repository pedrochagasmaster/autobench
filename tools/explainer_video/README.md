# Autobench onboarding video

A [Remotion](https://remotion.dev) composition that walks a new analyst from
first access to a verified first run. It follows the teaching order of
[`docs/autobench-onboarding.html`](../../docs/autobench-onboarding.html) and is
built around a recorded walkthrough of the real TUI.

- Composition id: `AutobenchOnboarding`
- 1920×1080, 30 fps; 8175 frames (4 minutes 32 seconds) without a voice track,
  and as long as the narration needs with one
- Chapters: what it does · set up · prepare · run (terminal UI, then CLI) · verify

## Setup

```bash
cd tools/explainer_video
npm install
npm run assets     # captures the TUI and synthesises the music bed
```

`npm run assets` runs three Python scripts and must be run before the first
render. None of their output is committed:

| Script | Writes | Why it is generated |
| --- | --- | --- |
| `scripts/capture_tui.py` | `public/tui/*.svg` and `manifest.json` | Screens of the real TUI, so the video cannot drift from the app |
| `scripts/make_voiceover.py` | `public/vo/*.mp3` and `manifest.json` | Narration, synthesised from the same lines the captions show |
| `scripts/make_music_bed.py` | `public/music_bed.wav` | Avoids committing a binary audio artifact |

## Voice track

`scripts/make_voiceover.py` synthesises one clip per scene with the
[Fish Audio](https://docs.fish.audio) TTS API, reading the same narration the
video puts on screen — `src/content/narration.json` for the chapters and the
capture manifest for the walkthrough steps, so the spoken line and the caption
beside it cannot diverge.

```bash
export FISH_API_KEY=...                                  # required
python3 scripts/make_voiceover.py                        # s2.1-pro-free, default voice
python3 scripts/make_voiceover.py --model s2.1-pro       # paid production model
python3 scripts/make_voiceover.py --reference-id <id>    # a saved voice model
python3 scripts/make_voiceover.py --speed 0.95 --force   # re-synthesise everything
```

The default model is `s2.1-pro-free` (same weights as `s2.1-pro`, no paid API
credit required). Use `--model s2.1-pro` when you want the production SLA.
Clips are cached by a hash of the text and the voice settings, so re-running
only re-synthesises lines that changed.

**The edit follows the read.** Each scene is held for `lead + clip + tail`, or
its animation floor, whichever is longer, so nothing is cut off mid-sentence and
no scene waits around after its line ends. Without a voice track, scenes fall
back to the caption-paced lengths in `src/timeline.ts` and the total is checked
against a fixed constant. The music bed ducks by 7.5 dB whenever narration is
present.

Without `FISH_API_KEY` the script writes an empty manifest and exits cleanly, so
the video still renders with captions and no voice.

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
| `musicGain` | `0.22` | Bed level; automatically ducked when a voice track exists |
| `voiceGain` | `1` | Narration level |

```bash
npx remotion render AutobenchOnboarding out/external_cut.mp4 \
  --props='{"showControlReference": false, "showNarration": true, "showProgress": true, "musicGain": 0.22, "voiceGain": 1}'
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

`src/content/narration.json` holds one line per chapter, and the walkthrough
lines come from the capture manifest, so a caption, the screenshot beside it, and
the spoken line cannot describe different steps. The captions stay on with a
voice track — they are the subtitles. Set `showNarration: false` for a
clean-frame cut.
