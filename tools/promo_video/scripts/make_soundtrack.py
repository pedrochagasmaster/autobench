"""Synthesize the promo soundtrack: a minimal ambient pad with a soft pulse.

Deterministic, dependency-light (numpy only). Writes a 16-bit stereo WAV to
public/audio/soundtrack.wav. Regenerate with: python3 scripts/make_soundtrack.py
"""

import wave
from pathlib import Path

import numpy as np

SR = 44100
DURATION = 63.0
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

# A-minor ambient progression, 7s per chord: Am9, Fmaj7, Cmaj7, G6 — twice.
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

# Loose pentatonic plucks for sparkle, sparse in the intro, denser later.
PLUCK_NOTES = [76, 79, 81, 84, 88]
beat = 60 / 82  # 82 bpm feel
k = 0
t_cursor = 4.0
while t_cursor < DURATION - 3:
    density = 0.35 if t_cursor < 14 else 0.62
    if rng.random() < density:
        midi = PLUCK_NOTES[k % len(PLUCK_NOTES)] + (12 if rng.random() < 0.12 else 0)
        place(mix, pluck(midi), t_cursor, gain=0.30 * rng.uniform(0.6, 1.0))
        k += 1
    t_cursor += beat * rng.choice([1.0, 1.0, 1.5, 2.0])

# Sub pulse enters with the title reveal (~9.3s) and holds a heartbeat pattern.
t_cursor = 9.3
while t_cursor < DURATION - 4:
    place(mix, sub_pulse(33), t_cursor, gain=0.5)
    t_cursor += beat * 2

# Gentle glue: soften highs, then normalize with headroom.
mix = lowpass(mix, cutoff=5200)

# Stereo width via a tiny delay on the right channel.
delay = int(0.011 * SR)
left = mix
right = np.concatenate([np.zeros(delay), mix[:-delay]])
stereo = np.stack([left, right], axis=1)

# Master fade in/out.
fade_in = int(1.2 * SR)
fade_out = int(3.2 * SR)
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
