# Style Grammar: the numbers behind the Apple-ad look

Strong defaults, proven in production. Deviate deliberately, not accidentally.

## Typography

- **Display face:** Inter Display (or the repo's own display font). Weights: 300/500/600/700. **Mono face:** JetBrains Mono for anything code.
- Headlines 72–96 px, wordmark 148–204 px, numerals up to 150 px, subtitles 32–46 px (at 1920×1080).
- Negative tracking on everything big: `-0.02em` to `-0.045em`. Animate tracking slightly tighter over time for a "settle" feel.
- Hierarchy inside one line by color, not size: key clause in `#f5f5f7`, secondary clause in `#86868b` ("One command. <dim>Fully governed.</dim>").
- ALL-CAPS only for tiny kicker labels, with wide `0.14em` tracking.

## Color

```
bg        #050506   near-black, never pure black
text      #f5f5f7   Apple off-white
textDim   #86868b   Apple gray
accents   #3a7bfd → #9f5bff → #ff5bb1   (100° linear gradient for wordmark/numerals)
success   #30d158   verdict/success moments only
```

- Background is never flat: 1–2 huge radial glows (blue/violet + pink) drifting slowly via sine of time, opacity 0.09–0.16.
- Gradient text via `background-clip: text`. Animate the gradient stops for a shine sweep on reveals.
- Finish: vignette (`radial-gradient`, edges to `rgba(0,0,0,0.42)`) + animated film grain (SVG `feTurbulence`, `seed={frame}`, opacity ~0.05, blend `overlay`).

## Motion

- **Everything eases hard:** `1 - (1-v)^3` or steeper; springs `damping 13–17, mass 0.6–0.9` for pops.
- **Rise-in** is the default entrance: translateY 40–90 px → 0, opacity 0 → 1, `blur(10px)` → 0, over ~20–24 frames.
- **Word-by-word stagger** (3–4 frames/word) for headlines — the signature kinetic-type move.
- Nothing is ever static: slow zoom 1.00 → 1.05, drift ±12 px, or a breathing glow on every held shot.
- Scene transitions: 15-frame crossfades (see SKILL.md timeline arithmetic). Cold-open lines fade in/out against pure black, so their dips are invisible. Feature beats: hard cuts inside the scene, ~55 frames each. Impact moments: white radial flash 0.55 → 0 over 14 frames.
- Product shots: footage floats bottom-anchored under the caption with `perspective(1500px) rotateX(7° → 2.5°)`, deep drop shadow, and a moving sheen stripe (`mix-blend-mode: screen`) sweeping across.

## Terminal chrome

- Rounded 22 px window, `rgba(14,14,18,0.94)` body, three traffic lights (`#ff5f57 #febc2e #28c840`), centered title "<tool-name> — zsh", 1px `rgba(255,255,255,0.09)` border, huge drop shadow.
- Command types at ~1 char/frame with a blinking `▍` (16-frame cycle); output lines reveal every ~9 frames.
- Token colors: command `#7ee787`, subcommand `#ffa657`, flags `#79c0ff`, values/args `#f5f5f7`, quoted program/filter strings `#e3b341`, log lines `rgba(245,245,247,0.62)`, success lines `#30d158` bold.
- Budget ~10–12 output lines per shot. Select a representative subset of the real output (opening lines, one or two key middle lines, the closing verdict) — trim, never rewrite.

## Audio

Deterministic numpy synthesis (fixed RNG seed), 44.1 kHz stereo, 82 BPM (beat = 0.732 s). Complete reference: `tools/promo_video/scripts/make_soundtrack.py` in the Autobench repo; recipes below are sufficient to rebuild it.

- **Pad bed:** for each chord tone, sum 3 sines detuned {0, +0.13, −0.11} Hz at gains {1.0, 0.55, 0.55} plus an octave-up sine at 0.18× — random phase per partial. Envelope: 1.4 s squared attack, 1.8 s release. Progression: Am9 → Fmaj7 → Cmaj7add9 → G6 (any mellow 4-chord loop works), 7 s per chord, looped.
- **Motif:** a short *composed* pentatonic sequence (e.g. E5 A5 G5 C6 A5 E5 G5 E6) stepped on the beat grid — a written motif reads as intentional where random notes read as noise. Pluck voice: sine + 0.3× octave, `exp(−4.2t)` decay. Sparse (every 2 beats) before the reveal, denser after.
- **Pulse:** sub thump every 2 beats — sine at ~55 Hz with a fast downward pitch sweep (`f × (1 + 0.7·exp(−30t))`), `exp(−7.5t)` decay. Enters right after the reveal boom, rests from the outro onward.
- **Riser → boom** at the wordmark reveal: 2.6 s of ~1.9 kHz-lowpassed noise + exponentially rising tone (180 Hz × 2^(1.8·t/T)) swelling as `(t/T)^2.4`, ending exactly at the boom; boom = sine sweeping 72→30 Hz (`exp(−2.2t)`) with `exp(−3.2t)` decay + a 260 Hz-lowpassed noise thump.
- **Chime** at the payoff: additive bell — partial ratios {1.0, 2.76, 5.4}, gains {1.0, 0.4, 0.18}, decays `exp(−{2.2, 4.5, 7.0}t)`; layer root + a second one a fifth up, 0.12 s late.
- **Stem gains** (starting balance; tune against the volumedetect targets): pad 0.62, motif plucks 0.26–0.32, pulse 0.5, riser 0.5, boom 0.95, chime 0.55 (+0.3 for the fifth-up layer). Any fixed RNG seed works — determinism matters, the value doesn't.
- **Mix:** lowpass the sum twice with a one-pole at ~5.6 kHz; stereo width via ~11 ms right-channel delay; 1.2 s fade-in; 3.4 s fade-out; normalize to 0.8 peak (≈ −2 dBFS).
- **Length:** video duration + ~1 s. Remotion truncates audio at the composition's final frame, so the extra second only guards against off-by-one cue drift at the tail — put the audible fade-out *before* the video ends.
- Cue seconds come from the timeline arithmetic in SKILL.md; write the cue map as a comment in the generator.
