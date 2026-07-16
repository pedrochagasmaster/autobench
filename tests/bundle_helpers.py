"""Verified dependency-bundle fixtures shared by runtime and install tests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

DEFAULT_FILES = {
    "requirements/requirements.txt": (
        b"pandas\nnumpy\nopenpyxl\nPyYAML\nscipy\ntextual\n"
    )
}


def make_bundle(
    tmp_path: Path,
    files: dict[str, bytes] | None = None,
    *,
    target_python: str = "3.10",
) -> tuple[Path, str]:
    bundle_files = dict(DEFAULT_FILES if files is None else files)
    seed = hashlib.sha256(
        json.dumps(sorted(bundle_files)).encode()
        + b"".join(bundle_files.values())
        + target_python.encode()
    )
    bundle = tmp_path / f"bundle-{seed.hexdigest()[:8]}"
    manifest_files = []
    for relative, content in sorted(bundle_files.items()):
        target = bundle.joinpath(*relative.split("/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        manifest_files.append(
            {
                "path": relative,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
                "kind": "wheel" if relative.startswith("wheels/") else "dependency",
            }
        )
    (bundle / "requirements").mkdir(exist_ok=True)
    (bundle / "wheels").mkdir(exist_ok=True)
    identity = {
        "schema": "edge-deploy/dependency-bundle/1",
        "tool": "autobench",
        "source_sha": "a" * 40,
        "target": {
            "python": target_python,
            "implementation": "cp",
            "abi": "cp310",
            "platform": "manylinux2014_x86_64",
        },
        "files": manifest_files,
    }
    canonical = (
        json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    digest = hashlib.sha256(canonical).hexdigest()
    (bundle / "manifest.json").write_text(
        json.dumps({**identity, "bundle_digest": digest}), encoding="utf-8"
    )
    return bundle, digest
