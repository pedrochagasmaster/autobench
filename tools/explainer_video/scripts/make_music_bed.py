#!/usr/bin/env python3
"""Generate the walkthrough's music bed.

The video needs a low-percussion bed that runs under the whole walkthrough.
Rather than commit a binary audio artifact, the bed is synthesised
deterministically from this script:

    python3 scripts/make_music_bed.py

Writes ``public/music_bed.wav`` (44.1 kHz, 16-bit stereo), which Remotion picks
up via ``staticFile("music_bed.wav")``.
"""

from __future__ import annotations

import argparse
import wave
from pathlib import Path

import numpy as np

SAMPLE_RATE = 44_100
# Long enough to cover a voice-paced walkthrough (Selene reads the current
# script in ~320 s, which lead/tail stretches past six minutes); the
# composition fades it out before the end.
DEFAULT_SECONDS = 420.0
BPM = 66.0

# A minor, one chord every four bars at 66 BPM.
PROGRESSION = (
    (110.00, 130.81, 164.81),  # Am
    (87.31, 130.81, 174.61),   # F
    (130.81, 164.81, 196.00),  # C
    (98.00, 123.47, 146.83),   # G
)


def _envelope(t: np.ndarray, attack: float, release: float, total: float) -> np.ndarray:
    """Linear fade in and out, flat in between."""
    env = np.ones_like(t)
    rising = t < attack
    env[rising] = t[rising] / attack
    falling = t > total - release
    env[falling] = np.maximum(0.0, (total - t[falling]) / release)
    return env


def _pad(t: np.ndarray, seconds: float) -> np.ndarray:
    """Sustained chord pad, cross-faded between progression steps."""
    chord_seconds = (60.0 / BPM) * 4 * 4
    out = np.zeros_like(t)
    for index, chord in enumerate(PROGRESSION * int(np.ceil(seconds / (chord_seconds * len(PROGRESSION))))):
        start = index * chord_seconds
        if start >= seconds:
            break
        # Overlap neighbours so chord changes breathe instead of stepping.
        window = (t >= start - 1.5) & (t < start + chord_seconds + 1.5)
        if not window.any():
            continue
        local = t[window] - start
        shape = np.clip(np.minimum(local + 1.5, chord_seconds + 1.5 - local) / 1.5, 0.0, 1.0)
        voice = np.zeros_like(local)
        for partial, freq in enumerate(chord):
            detune = 1.0 + 0.0009 * (partial - 1)
            voice += np.sin(2 * np.pi * freq * detune * (t[window])) * (0.55 ** partial)
            voice += 0.22 * np.sin(2 * np.pi * freq * 2 * (t[window]) + 0.4 * partial)
        out[window] += voice * shape
    return out


def _breath(t: np.ndarray) -> np.ndarray:
    """Slow amplitude drift so the bed does not sit perfectly still."""
    return 0.86 + 0.14 * np.sin(2 * np.pi * t / 17.0)


def _shimmer(t: np.ndarray) -> np.ndarray:
    """Quiet high partial, filtered noise stand-in."""
    lfo = 0.5 + 0.5 * np.sin(2 * np.pi * t / 23.0)
    return 0.035 * lfo * (
        np.sin(2 * np.pi * 1318.5 * t) + np.sin(2 * np.pi * 1975.5 * t + 1.1)
    )


def _pulse(t: np.ndarray, seconds: float) -> np.ndarray:
    """Low, soft heartbeat on every second beat. No transient snap."""
    beat = 60.0 / BPM
    out = np.zeros_like(t)
    hit = 0.0
    while hit < seconds:
        window = (t >= hit) & (t < hit + 0.75)
        if window.any():
            local = t[window] - hit
            decay = np.exp(-local * 7.0)
            body = np.sin(2 * np.pi * 55.0 * local) + 0.4 * np.sin(2 * np.pi * 82.5 * local)
            out[window] += 0.5 * decay * body
        hit += beat * 2
    return out


def render(seconds: float) -> np.ndarray:
    t = np.arange(int(seconds * SAMPLE_RATE), dtype=np.float64) / SAMPLE_RATE

    mono = _pad(t, seconds) * _breath(t) * 0.22
    mono += _shimmer(t)
    mono += _pulse(t, seconds) * 0.20
    mono *= _envelope(t, attack=3.0, release=6.0, total=seconds)

    # Gentle stereo width: delay one channel by a few milliseconds.
    offset = int(0.007 * SAMPLE_RATE)
    left = mono
    right = np.concatenate([np.zeros(offset), mono[:-offset]])

    stereo = np.stack([left, right * 0.97], axis=1)
    peak = float(np.max(np.abs(stereo)))
    if peak > 0:
        stereo = stereo / peak * 0.72
    return stereo


def write_wav(path: Path, stereo: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    samples = np.int16(np.clip(stereo, -1.0, 1.0) * 32767)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(samples.tobytes())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=float, default=DEFAULT_SECONDS)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "public" / "music_bed.wav",
    )
    args = parser.parse_args()

    stereo = render(args.seconds)
    write_wav(args.output, stereo)
    print(f"wrote {args.output} ({args.seconds:.1f}s, {SAMPLE_RATE} Hz stereo)")


if __name__ == "__main__":
    main()
