#!/usr/bin/env python3
"""Synthesise the walkthrough's voice track with the Fish Audio API.

One clip per scene, from the same narration the video puts on screen:

    src/content/narration.json   the chapter lines
    public/tui/manifest.json     the walkthrough captions

Each clip is written to ``public/vo/<scene>.mp3`` and its measured duration is
recorded in ``public/vo/manifest.json``. The composition reads that manifest and
stretches each scene to fit its own line, so the edit follows the read rather
than the other way round.

Usage:

    export FISH_API_KEY=...
    python3 scripts/make_voiceover.py                       # default voice
    python3 scripts/make_voiceover.py --reference-id <id>   # a saved voice model
    python3 scripts/make_voiceover.py --force               # ignore the cache

Without ``FISH_API_KEY`` the script writes an empty manifest and exits cleanly,
so the video still renders (captions only, no voice track).

Docs: https://docs.fish.audio/api-reference/endpoint/openapi-v1/text-to-speech
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent

TTS_URL = "https://api.fish.audio/v1/tts"
# The model is sent as a request header and is required on every call.
# s2.1-pro-free is the same weights as s2.1-pro at $0 (no TTFA/DPA SLA).
# Prefer it so `npm run assets` works without paid API credit; pass
# --model s2.1-pro when production credits and SLAs are required.
DEFAULT_MODEL = "s2.1-pro-free"
DEFAULT_FORMAT = "mp3"
DEFAULT_BITRATE = 128
REQUEST_TIMEOUT = 180
MAX_ATTEMPTS = 4


def load_lines() -> list[tuple[str, str]]:
    """Scene id and narration text, in timeline order."""
    chapters: dict[str, str] = json.loads(
        (PROJECT_DIR / "src" / "content" / "narration.json").read_text(encoding="utf-8")
    )

    tui_manifest_path = PROJECT_DIR / "public" / "tui" / "manifest.json"
    if not tui_manifest_path.exists():
        raise SystemExit(
            "public/tui/manifest.json is missing. Run scripts/capture_tui.py first."
        )
    tui = json.loads(tui_manifest_path.read_text(encoding="utf-8"))

    lines: list[tuple[str, str]] = []
    for index, step in enumerate(tui["steps"]):
        lines.append((f"t{index:02d}", step["caption"]))
    for scene, text in chapters.items():
        lines.append((scene, text))

    # Timeline order: chapters s02..s10, then the walkthrough, then s11..s18.
    def sort_key(item: tuple[str, str]) -> tuple[int, int]:
        scene = item[0]
        number = int(scene[1:])
        if scene.startswith("t"):
            return (1, number)
        return (0 if number <= 10 else 2, number)

    return sorted(lines, key=sort_key)


def voice_fingerprint(text: str, request: dict[str, Any], model: str) -> str:
    """Identifies a clip so unchanged lines are not re-synthesised or re-billed."""
    payload = json.dumps(
        {"text": text, "model": model, "request": request},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def synthesize(text: str, request: dict[str, Any], model: str, api_key: str) -> bytes:
    body = json.dumps({**request, "text": text}).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "model": model,
    }

    last_error: Optional[str] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        req = urllib.request.Request(TTS_URL, data=body, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
                audio = response.read()
            if not audio:
                raise RuntimeError("Fish Audio returned an empty body")
            return audio
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", "replace")[:400]
            # 401/402/422 are not going to fix themselves on a retry.
            if error.code in (401, 402, 404, 422):
                raise SystemExit(
                    f"Fish Audio rejected the request ({error.code}): {detail}"
                ) from error
            last_error = f"HTTP {error.code}: {detail}"
        except (urllib.error.URLError, TimeoutError, RuntimeError) as error:
            last_error = str(error)

        if attempt < MAX_ATTEMPTS:
            backoff = 2**attempt
            print(f"    retry {attempt}/{MAX_ATTEMPTS - 1} in {backoff}s ({last_error})")
            time.sleep(backoff)

    raise SystemExit(f"Fish Audio request failed after {MAX_ATTEMPTS} attempts: {last_error}")


def probe_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(result.stdout.strip())


def write_manifest(output_dir: Path, clips: dict[str, Any], meta: dict[str, Any]) -> None:
    (output_dir / "manifest.json").write_text(
        json.dumps({**meta, "clips": clips}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "public" / "vo")
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=(
            "Fish Audio TTS model: s2.1-pro-free (default), s2.1-pro, "
            "s2-pro, or s1"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List the lines that would be synthesised, and their size, without calling the API",
    )
    parser.add_argument(
        "--reference-id",
        default=os.environ.get("FISH_VOICE_ID"),
        help="Voice model id to speak in; omit for the default voice",
    )
    parser.add_argument("--speed", type=float, default=1.0, help="prosody.speed, 0.5-2")
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.6,
        help="Lower is steadier, which suits narration",
    )
    parser.add_argument("--force", action="store_true", help="Re-synthesise every line")
    args = parser.parse_args()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    lines = load_lines()

    if args.dry_run:
        characters = sum(len(text) for _, text in lines)
        words = sum(len(text.split()) for _, text in lines)
        for scene, text in lines:
            print(f"  {scene}  {len(text):4d} chars  {text[:72]}…")
        print(
            f"\n{len(lines)} lines, {words} words, {characters} characters, "
            f"model {args.model}"
        )
        return

    api_key = os.environ.get("FISH_API_KEY")
    if not api_key:
        write_manifest(
            args.output_dir,
            {},
            {
                "generated": False,
                "reason": "FISH_API_KEY is not set",
                "model": args.model,
            },
        )
        print(
            "FISH_API_KEY is not set: wrote an empty voice-over manifest.\n"
            "The video will render with captions and no voice track. Set the key "
            "and re-run to add narration."
        )
        return

    request: dict[str, Any] = {
        "format": DEFAULT_FORMAT,
        "mp3_bitrate": DEFAULT_BITRATE,
        # "normal" is the steadier of the two; this is not an interactive path.
        "latency": "normal",
        "temperature": args.temperature,
        "prosody": {"speed": args.speed, "volume": 0},
        "normalize": True,
    }
    if args.reference_id:
        request["reference_id"] = args.reference_id

    existing: dict[str, Any] = {}
    manifest_path = args.output_dir / "manifest.json"
    if manifest_path.exists() and not args.force:
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8")).get("clips", {})
        except json.JSONDecodeError:
            existing = {}

    clips: dict[str, Any] = {}
    reused = 0
    for scene, text in lines:
        fingerprint = voice_fingerprint(text, request, args.model)
        target = args.output_dir / f"{scene}.mp3"
        cached = existing.get(scene)
        if cached and cached.get("hash") == fingerprint and target.exists():
            clips[scene] = cached
            reused += 1
            continue

        print(f"  {scene}  {len(text.split()):3d} words")
        target.write_bytes(synthesize(text, request, args.model, api_key))
        clips[scene] = {
            "file": f"vo/{scene}.mp3",
            "seconds": round(probe_seconds(target), 3),
            "hash": fingerprint,
            "words": len(text.split()),
        }

    for stale in args.output_dir.glob("*.mp3"):
        if stale.stem not in clips:
            stale.unlink()

    total = sum(clip["seconds"] for clip in clips.values())
    write_manifest(
        args.output_dir,
        clips,
        {
            "generated": True,
            "model": args.model,
            "reference_id": args.reference_id,
            "speed": args.speed,
            "total_seconds": round(total, 2),
        },
    )
    print(
        f"wrote {len(clips)} clips ({reused} reused from cache), "
        f"{total:.1f}s of narration, to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
    sys.exit(0)
