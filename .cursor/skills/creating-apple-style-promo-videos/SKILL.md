---
name: creating-apple-style-promo-videos
description: Use when asked to create a demo, promo, launch, or showcase video for a software tool, app, CLI, or TUI — especially with an "Apple ad", cinematic, or premium feel — or when embedding real terminal/app footage in a rendered video.
---

# Creating Apple-Style Promo Videos

## Overview

Render the video as code with [Remotion](https://www.remotion.dev/) (React → mp4), composite **real app footage** captured from the live tool, and synthesize a royalty-free soundtrack whose cues are computed from the frame timeline. Everything is deterministic and regenerable from scripts; only source is committed.

This skill is self-contained. If you are in the Autobench repo, `tools/promo_video/` is a complete working example (composition, capture scripts, soundtrack generator, README) — otherwise build from the recipes here.

## When to Use

- "Make a demo/promo/launch video for this tool" — any app with a UI, TUI, or CLI.
- The bar is "feels like an Apple ad": big type, dark, minimal, musical.
- NOT for data-driven charts/plots (render those from data), and NOT for screen-recording walkthrough tutorials where narration matters more than polish.

## Workflow

1. **Run the real product first.** Execute the actual CLI on a real fixture; save the genuine log lines, numbers, and success output verbatim — they are the script. Never invent fake output. Any "big number" shown must be measured on this machine or be a verifiable documented fact.
2. **Capture real footage** headlessly (see [capture-footage.md](capture-footage.md) for TUI/terminal recipes and their pitfalls).
3. **Write the ad** before the code: one idea per scene, following the structure below.
4. **Build the Remotion timeline as data** — an array of `{ component, duration }` — with crossfade transitions between scenes (timeline arithmetic below).
5. **Synthesize the soundtrack** with cues aligned to scene starts (recipes in [style-grammar.md](style-grammar.md#audio)).
6. **Render, then review like a director**: extract frames with ffmpeg at every scene midpoint AND the midpoint of every crossfade, view them, check audio with `volumedetect`. Iterate until every frame could be a poster.

## Ad Structure (the Apple grammar)

| Beat | Duration | Content |
|---|---|---|
| Cold open | 8–10 s | 2–3 short declarative lines, white on black, one at a time |
| Wordmark reveal | 5–6 s | Gradient logotype + impact flash, synced to a bass boom |
| Product proof | 10–12 s | Real CLI/terminal run, typed live with syntax colors |
| Product tour | 10–12 s | Real UI footage as floating 3D product shots, 3 beats |
| Big numbers | 6–7 s | The one measured domain fact as huge numerals (caps, speed, scale) |
| Feature beats | 5–6 s | Hard cuts, one bold phrase each, 1.7–2 s per cut |
| Payoff | 5–6 s | The verdict/result moment with a chime and glow |
| Lockup | 6–8 s | Wordmark + tagline + copyable command chip, fade out |

~60 s total at 30 fps, 1920×1080. Copy style: sentence fragments with periods ("Press run. That's it."), dim the second clause, one bolded key word max.

**For a pure CLI with no visual UI:** the product-tour shots are additional rendered terminal windows (different commands/outputs) given the same floating 3D treatment as UI footage; prefer merging the tour into a longer product proof only when the tool really has just one command worth showing. A "wordmark" for a logo-less tool is simply its name set in the gradient display face. If the tool has no honest big-number fact, drop that beat and redistribute its time to the adjacent beats.

The exact typography, color, motion, and audio numbers are in [style-grammar.md](style-grammar.md).

## Timeline Arithmetic (get this exact)

With crossfade length `X` (15 frames works well) between all adjacent scenes:

```
start(i) = sum(duration of scenes 0..i-1) − X × i     # final-timeline frame
total    = sum(all durations) − X × (n − 1)
```

- **All scene junctions crossfade.** Hard cuts exist only *inside* the feature-beats scene; they don't change the arithmetic.
- A scene is only ~50% visible at `start(i)`. Sync impact moments (flash, boom, chime) to `start(i) + X`, when the crossfade completes.
- Audio cue seconds = `(start(i) + X) / fps`. Document the cue map in the soundtrack generator.
- Within a scene, sequential beats that fade out then in will dip to black — overlap them by ~10 frames and crossfade. (On the pure-black cold open this is invisible; anywhere with visible content it's a bug.)

## Common Mistakes

| Mistake | Fix |
|---|---|
| Scenes fade to black between cuts | Crossfade scenes (`@remotion/transitions`); overlap within-scene beats too |
| Fake or lorem screenshots | Capture the live app; run the real command; keep real paths/numbers |
| Stale app state leaks into "fresh" footage | Isolate session/config persistence (temp dir) before driving the app |
| Music ignores the picture | Compute cue times from the timeline arithmetic above |
| Licensed music or stock assets | Synthesize audio deterministically (numpy); use repo fonts or a scripted, pinned font download |
| Shipping without watching it | Extract and inspect frames at midpoints and crossfade midpoints; check `volumedetect` |
| Committing renders/footage/fonts | See artifact policy below |

## Artifact Policy

Commit: composition source, capture/generator scripts, small input fixtures (roughly < 100 KB; fetch bigger ones with a pinned, checked-in script), and the captured output text that scenes replay (it is the authoritative script data). Gitignore: rendered video, rasterized footage images, staged font copies, and synthesized audio — all regenerable by script. Font staging must be a checked-in script — copy from the repo's own fonts, or download a pinned release (e.g. Inter from `github.com/rsms/inter/releases`, JetBrains Mono from `github.com/JetBrains/JetBrainsMono/releases`) — so the render is reproducible from a fresh clone.

## Verification Loop

```bash
npx tsc --noEmit
npx remotion render <Comp> out/video.mp4 --timeout=120000   # first render needs the long timeout (font loading)
for t in <scene midpoints and crossfade midpoints>; do ffmpeg -y -ss $t -i out/video.mp4 -frames:v 1 -q:v 3 review/f_$t.jpg; done
ffmpeg -i out/video.mp4 -af volumedetect -f null -          # expect mean −22..−18 dB, max −4..−1.5 dB
```

Review every extracted frame visually. A crossfade that renders black, a caption overlapped by footage, or a ghosted double-exposure is a bug — fix and re-render. Also diff the on-screen terminal text against the saved capture files: every visible line must be real.
