"""Synthesize the promo soundtrack: ambient pads, a pulse, and cue hits.

Deterministic, dependency-light (numpy only). Writes a 16-bit stereo WAV to
public/audio/soundtrack.wav. Regenerate with: python3 scripts/make_soundtrack.py

Cue map (matches the Remotion timeline in src/Root.tsx, 30 fps, 15-frame
crossfades):
  8.83 s  wordmark reveal   -> riser resolves into a sub boom
  9.5  s  pulse enters      -> heartbeat sub every 2 beats
  47.2 s  compliance verdict -> soft bell chime
  51.1 s  outro             -> pulse stops, pads breathe out
"""

import wave
from pathlib import Path

import numpy as np

SR = 44100
DURATION = 59.5
BPM = 82
BEAT = 60 / BPM
BOOM_AT = 8.83
PULSE_FROM = 9.5
PULSE_TO = 51.1
CHIME_AT = 47.2
OUT = Path(__file__).resolve().parent.parent / "public" / "audio" / "soundtrack.wav"

rng = np.random.default_rng(7)


def note_hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def adsr(n: int, attack: float, release: float) -> np.ndarray:
    env = np.ones(n)
    a = int(attack * SR)
    r = int(release * SR)
    if a > 0:
        env[:a] = np.linspace(0, 1, a) ** 2
    if r > 0:
        env[-r:] *= np.linspace(1, 0, r) ** 1.5
    return env


def pad_chord(midis: list[float], seconds: float) -> np.ndarray:
    """Slow-attack detuned-sine pad."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    out = np.zeros(n)
    for midi in midis:
        f = note_hz(midi)
        for detune, amp in ((0.0, 1.0), (0.13, 0.55), (-0.11, 0.55)):
            phase = rng.uniform(0, 2 * np.pi)
            out += amp * np.sin(2 * np.pi * (f + detune) * t + phase)
            out += 0.18 * amp * np.sin(2 * np.pi * (2 * f + detune) * t + phase)
    out *= adsr(n, attack=1.4, release=1.8) / (len(midis) * 2.2)
    return out


def pluck(midi: float, seconds: float = 1.6) -> np.ndarray:
    """Soft sine pluck with a fast decay."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    f = note_hz(midi)
    env = np.exp(-t * 4.2)
    return (np.sin(2 * np.pi * f * t) + 0.3 * np.sin(4 * np.pi * f * t)) * env * 0.5


def sub_pulse(midi: float, seconds: float = 0.55) -> np.ndarray:
    """Round sub-bass thump."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    f = note_hz(midi)
    sweep = f * (1 + 0.7 * np.exp(-t * 30))
    env = np.exp(-t * 7.5)
    return np.sin(2 * np.pi * np.cumsum(sweep) / SR) * env


def boom(seconds: float = 1.6) -> np.ndarray:
    """Deep cinematic hit: sub sweep plus a filtered noise thump."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    sweep = 72 * np.exp(-t * 2.2) + 30
    body = np.sin(2 * np.pi * np.cumsum(sweep) / SR) * np.exp(-t * 3.2)
    noise = rng.normal(0, 1, n) * np.exp(-t * 14)
    alpha = 1 - np.exp(-2 * np.pi * 260 / SR)
    acc = 0.0
    thump = np.empty(n)
    for k in range(n):
        acc += alpha * (noise[k] - acc)
        thump[k] = acc
    return body + thump * 0.7


def riser(seconds: float = 2.6) -> np.ndarray:
    """Swelling noise plus a rising tone, leading into the boom."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    swell = (t / seconds) ** 2.4
    noise = rng.normal(0, 1, n)
    alpha = 1 - np.exp(-2 * np.pi * 1900 / SR)
    acc = 0.0
    hiss = np.empty(n)
    for k in range(n):
        acc += alpha * (noise[k] - acc)
        hiss[k] = acc
    tone_freq = 180 * 2 ** (t / seconds * 1.8)
    tone = np.sin(2 * np.pi * np.cumsum(tone_freq) / SR)
    return (hiss * 0.75 + tone * 0.3) * swell


def chime(midi: float = 81, seconds: float = 2.6) -> np.ndarray:
    """Bell-like additive tone for the verdict moment."""
    n = int(seconds * SR)
    t = np.arange(n) / SR
    f = note_hz(midi)
    out = np.zeros(n)
    for ratio, amp, decay in ((1.0, 1.0, 2.2), (2.76, 0.4, 4.5), (5.4, 0.18, 7.0)):
        out += amp * np.sin(2 * np.pi * f * ratio * t) * np.exp(-t * decay)
    return out * 0.5


def place(buf: np.ndarray, clip: np.ndarray, at: float, gain: float = 1.0) -> None:
    i = int(at * SR)
    j = min(i + len(clip), len(buf))
    if i < len(buf):
        buf[i:j] += clip[: j - i] * gain


def lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    """One-pole lowpass, applied twice for a softer top end."""
    alpha = 1 - np.exp(-2 * np.pi * cutoff / SR)
    y = np.copy(x)
    for _ in range(2):
        acc = 0.0
        out = np.empty_like(y)
        for k in range(len(y)):
            acc += alpha * (y[k] - acc)
            out[k] = acc
        y = out
    return y


N = int(DURATION * SR)
mix = np.zeros(N)

# A-minor ambient progression, 7s per chord: Am9, Fmaj7, Cmaj7add9, G6.
CHORDS = [
    [57, 64, 67, 71, 76],   # Am9
    [53, 60, 64, 69, 76],   # Fmaj7
    [48, 55, 64, 71, 74],   # Cmaj7add9
    [55, 62, 66, 71, 76],   # G6
]
CHORD_LEN = 7.0
for rep in range(2):
    for ci, chord in enumerate(CHORDS):
        at = (rep * len(CHORDS) + ci) * CHORD_LEN
        if at >= DURATION:
            break
        place(mix, pad_chord(chord, CHORD_LEN + 2.0), at, gain=0.62)

# A composed pentatonic motif on the beat grid (kept sparse before the boom).
MOTIF = [76, 81, 79, 84, 81, 76, 79, 88]
step = 0
t_cursor = 4.0
while t_cursor < DURATION - 4:
    sparse = t_cursor < BOOM_AT
    if not sparse or step % 2 == 0:
        midi = MOTIF[step % len(MOTIF)]
        gain = 0.26 if sparse else 0.32
        place(mix, pluck(midi), t_cursor, gain=gain * rng.uniform(0.85, 1.0))
    step += 1
    t_cursor += BEAT * (2.0 if sparse else rng.choice([1.0, 1.0, 1.5]))

# Cues.
place(mix, riser(2.6), BOOM_AT - 2.6, gain=0.5)
place(mix, boom(), BOOM_AT, gain=0.95)
place(mix, chime(81), CHIME_AT, gain=0.55)
place(mix, chime(88), CHIME_AT + 0.12, gain=0.3)

# Heartbeat sub, entering after the boom and resting for the outro.
t_cursor = PULSE_FROM
while t_cursor < min(PULSE_TO, DURATION - 4):
    place(mix, sub_pulse(33), t_cursor, gain=0.5)
    t_cursor += BEAT * 2

# Gentle glue: soften highs, then normalize with headroom.
mix = lowpass(mix, cutoff=5600)

# Stereo width via a tiny delay on the right channel.
delay = int(0.011 * SR)
left = mix
right = np.concatenate([np.zeros(delay), mix[:-delay]])
stereo = np.stack([left, right], axis=1)

# Master fade in/out.
fade_in = int(1.2 * SR)
fade_out = int(3.4 * SR)
stereo[:fade_in] *= np.linspace(0, 1, fade_in)[:, None]
stereo[-fade_out:] *= np.linspace(1, 0, fade_out)[:, None] ** 1.4

stereo *= 0.82 / np.max(np.abs(stereo))
pcm = (stereo * 32767).astype(np.int16)

OUT.parent.mkdir(parents=True, exist_ok=True)
with wave.open(str(OUT), "wb") as wf:
    wf.setnchannels(2)
    wf.setsampwidth(2)
    wf.setframerate(SR)
    wf.writeframes(pcm.tobytes())

print(f"Wrote {OUT} ({DURATION:.0f}s, {OUT.stat().st_size / 1e6:.1f} MB)")
