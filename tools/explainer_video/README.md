# Autobench explainer video

A [Remotion](https://remotion.dev) composition that explains what Autobench
computes, how the concentration rule is selected, how the weights are solved,
and what a run leaves on disk.

- Composition id: `AutobenchExplainer`
- 1920×1080, 30 fps, 3390 frames (113 seconds)
- 12 scenes, crossfaded with `fade()` and `linearTiming({durationInFrames: 12})`,
  except scene 6 which hard-cuts into scene 7

## Setup

```bash
cd tools/explainer_video
npm install
python3 scripts/make_music_bed.py   # writes public/music_bed.wav
```

The music bed is synthesised rather than committed, so `public/music_bed.wav` has
to exist before the first render. `npm install` needs network access on the first
run to fetch the headless Chromium that Remotion renders with.

## Preview and render

```bash
npx remotion studio --no-open           # interactive preview
npx remotion render AutobenchExplainer out/autobench_explainer.mp4
```

Every scene is also registered on its own so a single scene can be iterated on
without rendering the whole timeline:

```bash
npx remotion still Scene-s04 out/stills/s04.png --frame=210
npx remotion render Scene-s05 out/scene5.mp4
```

Scene ids and their timeline positions live in `src/timeline.ts`, which fails the
build if the scene plan stops summing to 3390 frames.

## Props

| Prop | Default | Effect |
| --- | --- | --- |
| `showControlReference` | `true` | Names Mastercard Control 3.2 under the scene 4 rule table |
| `showNarration` | `true` | Renders the narration as on-screen captions |
| `musicGain` | `0.34` | Bed level between the title card and the outro fade |

```bash
npx remotion render AutobenchExplainer out/external_cut.mp4 \
  --props='{"showControlReference": false, "showNarration": true, "musicGain": 0.34}'
```

## Two decisions the script left open

**Entity names.** Every frame uses generic labels (`Target`, `PEER_A` …) over the
semantics of `tests/fixtures/gate_demo.csv`. No real issuer name appears anywhere
in the composition, because named institutions sitting next to volume figures is
exactly what the concentration caps exist to prevent.

**Control 3.2.** `showControlReference` defaults to `true`, so the internal
control is named under the scene 4 rule table. The repository README already
names "Mastercard Control 3.2" publicly, so this discloses nothing new
internally. Render with `showControlReference: false` for any cut that leaves the
organisation.

## Where the on-screen content comes from

`src/data/facts.ts` holds every string and number the video renders, traced back
to the source of truth:

| On screen | Source |
| --- | --- |
| Rule table (`5/25` … `4/35`), min peers, caps, extra conditions | `core/privacy_validator.py`, `config/privacy_rules.yaml` |
| Rule selection by peer count, merchant-mode-only `4/35` | `PrivacyValidator.select_rule` |
| `Global-LP`, `Per-Dimension-LP`, `Per-Dimension-Bayesian` | `core/global_weight_optimizer.py` |
| `Rank Changes` columns (`Base_Rank`, `Adjusted_Rank`, `Delta` …) | `core/dimensional_analyzer.py` |
| Summary labels, `fully_compliant` | `core/report_generator.py`, `core/compliance.py` |
| CLI flags and subcommands | `benchmark.py` |
| Preset names and intents | `presets/*.yaml` |
| `execute_share_run` / `AnalysisRunRequest` snippet | `core/analysis_run.py`, `core/contracts.py` |
| Install and edge-node commands | `README.md`, `onboarding.md` |

The demo peer set in `facts.ts` is checked at module load: the scene 1 caption
only claims 61% concentration if the data says 61%, the reweighted set has to
respect the 7/35 cap, and the scene 5 ladder has to contain exactly two rank
swaps. Change a volume or a multiplier and the render fails rather than showing a
number that is not true.

## Narration

`src/data/voiceover.ts` holds the narration, one entry per scene. There is no
recorded voice track, so the lines render as captions along the bottom of the
frame. When a read is recorded, dub it over the render and re-render with
`showNarration: false`.
