#!/usr/bin/env python
"""Write and verify SHA-256 manifests for offline deployment bundles."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


ManifestEntry = Tuple[str, str]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _iter_files(paths: Sequence[Path], *, base_dir: Path) -> Iterable[Path]:
    for path in paths:
        resolved = path if path.is_absolute() else base_dir / path
        if not resolved.exists():
            raise FileNotFoundError(f"checksum input not found: {path}")
        if resolved.is_file():
            yield resolved
            continue
        for child in sorted(resolved.rglob("*")):
            if child.is_file():
                yield child


def build_manifest(paths: Sequence[Path], *, base_dir: Path) -> List[ManifestEntry]:
    """Build sorted ``(sha256, relative_path)`` entries for files under paths."""
    entries = []
    for file_path in _iter_files(paths, base_dir=base_dir):
        rel_path = file_path.relative_to(base_dir).as_posix()
        entries.append((_hash_file(file_path), rel_path))
    return sorted(entries, key=lambda item: item[1])


def write_manifest(paths: Sequence[Path], *, output: Path, base_dir: Path) -> None:
    entries = build_manifest(paths, base_dir=base_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for digest, rel_path in entries:
            handle.write(f"{digest}  {rel_path}\n")
    print(f"Wrote {len(entries)} checksum entries to {output}")


def read_manifest(path: Path) -> List[ManifestEntry]:
    entries: List[ManifestEntry] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            digest, rel_path = line.split(None, 1)
        except ValueError as exc:
            raise ValueError(f"invalid manifest line {line_number}: {line}") from exc
        entries.append((digest, rel_path.strip()))
    return entries


def verify_manifest(manifest: Path, *, base_dir: Path) -> bool:
    """Verify manifest entries relative to base_dir."""
    ok = True
    for expected_digest, rel_path in read_manifest(manifest):
        file_path = base_dir / rel_path
        if not file_path.exists():
            print(f"missing file: {rel_path}")
            ok = False
            continue
        actual_digest = _hash_file(file_path)
        if actual_digest != expected_digest:
            print(f"checksum mismatch: {rel_path}")
            ok = False
        else:
            print(f"ok: {rel_path}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Write or verify offline bundle SHA-256 manifests.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write", help="write a checksum manifest")
    write_parser.add_argument("paths", nargs="+", type=Path, help="files or directories to include")
    write_parser.add_argument("--output", type=Path, default=Path("SHA256SUMS"), help="manifest output path")
    write_parser.add_argument("--base-dir", type=Path, default=None, help="base directory for relative paths")

    verify_parser = subparsers.add_parser("verify", help="verify a checksum manifest")
    verify_parser.add_argument("--manifest", type=Path, default=Path("SHA256SUMS"), help="manifest to verify")
    verify_parser.add_argument("--base-dir", type=Path, default=None, help="base directory for relative paths")

    args = parser.parse_args()
    if args.command == "write":
        base_dir = (
            args.base_dir
            if args.base_dir is not None
            else (args.output.parent if args.output.is_absolute() else Path.cwd())
        ).resolve()
        write_manifest(args.paths, output=args.output, base_dir=base_dir)
        return 0

    base_dir = (
        args.base_dir
        if args.base_dir is not None
        else (args.manifest.parent if args.manifest.is_absolute() else Path.cwd())
    ).resolve()
    manifest = args.manifest if args.manifest.is_absolute() else base_dir / args.manifest
    return 0 if verify_manifest(manifest, base_dir=base_dir) else 1


if __name__ == "__main__":
    raise SystemExit(main())
