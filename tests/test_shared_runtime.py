"""Shared runtime and launcher contracts."""

from __future__ import annotations

import json
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from bundle_helpers import make_bundle

import shared_runtime

ROOT = Path(__file__).resolve().parents[1]


def _metadata(runtime: Path) -> dict[str, object]:
    return {
        "bundle_digest": runtime.name,
        "approved_python": "/approved/python3.10",
        "runtime_python": str((runtime / "bin" / "python").absolute()),
        "python_version": "3.10.99",
        "pip_check": "passed",
        "required_imports": list(shared_runtime.REQUIRED_IMPORTS),
    }


def test_manifest_digest_drives_release_path_and_completed_reuse(tmp_path: Path) -> None:
    bundle, digest = make_bundle(tmp_path)
    _manifest, loaded_digest = shared_runtime._load_manifest(bundle)
    runtime = tmp_path / ".venv" / "releases" / digest
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "python").write_text("", encoding="utf-8")
    (runtime / "bin" / "python").chmod(0o755)
    (runtime / shared_runtime.COMPLETE_MARKER).write_text(
        json.dumps(_metadata(runtime)), encoding="utf-8"
    )

    assert loaded_digest == digest
    assert shared_runtime._complete_metadata(runtime, digest) == _metadata(runtime)


@pytest.mark.parametrize("unsafe_path", ["../escape", "/absolute", "other/file.txt"])
def test_manifest_rejects_unsafe_paths(tmp_path: Path, unsafe_path: str) -> None:
    bundle, _digest = make_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"][0]["path"] = unsafe_path
    identity = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    canonical = (
        json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    manifest["bundle_digest"] = hashlib.sha256(canonical).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(shared_runtime.RuntimeInstallError, match="unsafe path"):
        shared_runtime._load_manifest(bundle)


def test_manifest_rejects_tampered_bundle_file(tmp_path: Path) -> None:
    bundle, _digest = make_bundle(tmp_path)
    (bundle / "requirements" / "requirements.txt").write_text(
        "changed\n", encoding="utf-8"
    )

    with pytest.raises(shared_runtime.RuntimeInstallError, match="failed verification"):
        shared_runtime._load_manifest(bundle)


def test_manifest_rejects_undeclared_extra_file(tmp_path: Path) -> None:
    bundle, _digest = make_bundle(tmp_path)
    (bundle / "wheels" / "smuggled.whl").write_bytes(b"undeclared")

    with pytest.raises(
        shared_runtime.RuntimeInstallError, match="do not match the manifest"
    ):
        shared_runtime._load_manifest(bundle)


def test_manifest_rejects_malformed_digest_and_wrong_tool(tmp_path: Path) -> None:
    bundle, _digest = make_bundle(tmp_path)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["bundle_digest"] = "not-a-digest"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(shared_runtime.RuntimeInstallError, match="invalid bundle_digest"):
        shared_runtime._load_manifest(bundle)

    bundle, _digest = make_bundle(tmp_path, {"requirements/requirements.txt": b"x\n"})
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["tool"] = "robocop"
    identity = {key: value for key, value in manifest.items() if key != "bundle_digest"}
    manifest["bundle_digest"] = hashlib.sha256(
        (json.dumps(identity, sort_keys=True, separators=(",", ":")) + "\n").encode()
    ).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(shared_runtime.RuntimeInstallError, match="different tool"):
        shared_runtime._load_manifest(bundle)


@pytest.mark.parametrize(
    "requirements",
    [
        b"--find-links /tmp/evil\ndemo==1.0\n",
        b"-r /tmp/other.txt\n",
        b"demo @ file:///tmp/demo.whl\n",
        b"../demo.whl\n",
    ],
)
def test_manifest_rejects_requirements_that_escape_verified_bundle(
    tmp_path: Path, requirements: bytes
) -> None:
    bundle, _digest = make_bundle(
        tmp_path, {"requirements/requirements.txt": requirements}
    )

    with pytest.raises(shared_runtime.RuntimeInstallError, match="package specifications only"):
        shared_runtime._load_manifest(bundle)


def test_snapshot_rejects_symlinked_bundle_file(tmp_path: Path) -> None:
    bundle, _digest = make_bundle(
        tmp_path,
        {
            "requirements/requirements.txt": b"demo==1.0\n",
            "wheels/demo.whl": b"external wheel",
        },
    )
    external = tmp_path / "external.whl"
    external.write_bytes(b"external wheel")
    wheel = bundle / "wheels" / "demo.whl"
    wheel.unlink()
    try:
        wheel.symlink_to(external)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    with pytest.raises(shared_runtime.RuntimeInstallError, match="linked path"):
        shared_runtime._snapshot_bundle(bundle, tmp_path / "runtime-root")


def test_incomplete_completion_metadata_is_not_reusable(tmp_path: Path) -> None:
    runtime = tmp_path / ("a" * 64)
    (runtime / "bin").mkdir(parents=True)
    python = runtime / "bin" / "python"
    python.write_text("", encoding="utf-8")
    python.chmod(0o755)
    metadata = _metadata(runtime)
    metadata.pop("python_version")
    (runtime / shared_runtime.COMPLETE_MARKER).write_text(
        json.dumps(metadata), encoding="utf-8"
    )

    assert shared_runtime._complete_metadata(runtime, runtime.name) is None


def _copy_launchers(root: Path) -> tuple[Path, Path]:
    target_bin = root / "bin"
    target_bin.mkdir(parents=True)
    for name in ("autobench", "autobench-cli", "runtime_check.sh"):
        shutil.copy2(ROOT / "bin" / name, target_bin / name)
        (target_bin / name).chmod(0o755)
    return target_bin / "autobench", target_bin / "autobench-cli"


def _active_runtime(root: Path, tmp_path: Path) -> tuple[Path, Path]:
    runtime = root / ".venv" / "releases" / ("a" * 64)
    (runtime / "bin").mkdir(parents=True)
    (runtime / ".complete.json").write_text(
        json.dumps(_metadata(runtime)), encoding="utf-8"
    )
    capture = tmp_path / "capture.txt"
    fake_python = runtime / "bin" / "python"
    fake_python.write_text(
        "#!/usr/bin/env sh\n"
        'if [ "${1:-}" = "-" ]; then exec "$VALIDATOR_PYTHON" "$@"; fi\n'
        'printf \'%s\\n\' "$PWD" "$PYTHONPATH" "$AUTOBENCH_RUNTIME" "$@" > "$CAPTURE"\n',
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    try:
        (root / ".venv" / "current").symlink_to(
            Path("releases") / runtime.name, target_is_directory=True
        )
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")
    return runtime, capture


@pytest.mark.parametrize(
    ("launcher_name", "entrypoint"),
    [("autobench", "tui_app.py"), ("autobench-cli", "benchmark.py")],
)
def test_shared_launchers_forward_arguments_preserve_cwd_and_resolve_runtime(
    tmp_path: Path, launcher_name: str, entrypoint: str
) -> None:
    if shutil.which("sh") is None:
        pytest.skip("shared launcher smoke requires sh")
    root = tmp_path / "autobench-root"
    launchers = dict(zip(("autobench", "autobench-cli"), _copy_launchers(root)))
    runtime, capture = _active_runtime(root, tmp_path)
    launch_cwd = tmp_path / "work"
    launch_cwd.mkdir()
    env = os.environ.copy()
    env["CAPTURE"] = capture.resolve().as_posix()
    env["VALIDATOR_PYTHON"] = Path(sys.executable).resolve().as_posix()

    result = subprocess.run(
        ["sh", launchers[launcher_name].resolve().as_posix(), "--help", "two words"],
        cwd=launch_cwd,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    lines = capture.read_text(encoding="utf-8").splitlines()
    assert Path(lines[0]).resolve() == launch_cwd.resolve()
    assert Path(lines[1]).resolve() == root.resolve()
    assert Path(lines[2]).resolve() == runtime.resolve()
    assert Path(lines[3]).resolve() == (root / entrypoint).resolve()
    assert lines[4:] == ["--help", "two words"]


def test_shared_launcher_fails_clearly_without_active_runtime(tmp_path: Path) -> None:
    if shutil.which("sh") is None:
        pytest.skip("shared launcher smoke requires sh")
    launcher, _cli = _copy_launchers(tmp_path / "root")

    result = subprocess.run(
        ["sh", launcher.resolve().as_posix()],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "shared runtime is not active" in result.stderr


def test_shared_launcher_rejects_corrupt_completion_metadata(tmp_path: Path) -> None:
    if shutil.which("sh") is None:
        pytest.skip("shared launcher smoke requires sh")
    root = tmp_path / "root"
    launcher, _cli = _copy_launchers(root)
    runtime = root / ".venv" / "releases" / ("c" * 64)
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "python").write_text(
        '#!/usr/bin/env sh\nexec "$VALIDATOR_PYTHON" "$@"\n', encoding="utf-8"
    )
    (runtime / "bin" / "python").chmod(0o755)
    (runtime / ".complete.json").write_text("{}\n", encoding="utf-8")
    try:
        (root / ".venv" / "current").symlink_to(
            Path("releases") / runtime.name, target_is_directory=True
        )
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    result = subprocess.run(
        ["sh", launcher.resolve().as_posix()],
        env={**os.environ, "VALIDATOR_PYTHON": Path(sys.executable).resolve().as_posix()},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "completion metadata is corrupt" in result.stderr


def test_shared_launcher_rejects_runtime_outside_release_root(tmp_path: Path) -> None:
    if shutil.which("sh") is None:
        pytest.skip("shared launcher smoke requires sh")
    root = tmp_path / "root"
    launcher, _cli = _copy_launchers(root)
    rogue = tmp_path / "rogue"
    (rogue / "bin").mkdir(parents=True)
    (rogue / "bin" / "python").write_text("", encoding="utf-8")
    (rogue / "bin" / "python").chmod(0o755)
    (rogue / ".complete.json").write_text(
        json.dumps(_metadata(rogue)), encoding="utf-8"
    )
    (root / ".venv").mkdir(parents=True)
    try:
        (root / ".venv" / "current").symlink_to(rogue, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    result = subprocess.run(
        ["sh", launcher.resolve().as_posix()],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "resolves outside the release root" in result.stderr


def test_shared_launcher_rejects_malformed_json_with_matching_strings(
    tmp_path: Path,
) -> None:
    if shutil.which("sh") is None:
        pytest.skip("shared launcher smoke requires sh")
    root = tmp_path / "root"
    launcher, _cli = _copy_launchers(root)
    runtime = root / ".venv" / "releases" / ("d" * 64)
    (runtime / "bin").mkdir(parents=True)
    python = runtime / "bin" / "python"
    python.write_text(
        '#!/usr/bin/env sh\nexec "$VALIDATOR_PYTHON" "$@"\n', encoding="utf-8"
    )
    python.chmod(0o755)
    (runtime / ".complete.json").write_text(
        f'not-json "bundle_digest": "{runtime.name}" "pip_check": "passed"',
        encoding="utf-8",
    )
    try:
        (root / ".venv" / "current").symlink_to(
            Path("releases") / runtime.name, target_is_directory=True
        )
    except OSError as exc:
        pytest.skip(f"symlink creation is unavailable: {exc}")

    result = subprocess.run(
        ["sh", launcher.resolve().as_posix()],
        env={**os.environ, "VALIDATOR_PYTHON": Path(sys.executable).resolve().as_posix()},
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "completion metadata is corrupt" in result.stderr


def _fake_completed_build(
    runtime: Path, _bundle: Path, digest: str, _python: Path, _target: str | None
) -> None:
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin" / "python").write_text("", encoding="utf-8")
    (runtime / "bin" / "python").chmod(0o755)
    (runtime / shared_runtime.COMPLETE_MARKER).write_text(
        json.dumps(_metadata(runtime)), encoding="utf-8"
    )


def test_build_validates_in_order_and_records_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime"
    bundle, digest = make_bundle(
        tmp_path,
        {
            "requirements/requirements.txt": b"demo\n",
            "wheels/demo.whl": b"wheel",
        },
    )
    approved = tmp_path / "python3.10"
    calls: list[list[str]] = []

    def fake_run(command: list[str]) -> None:
        calls.append(command)
        if command[1:3] == ["-m", "venv"]:
            assert runtime.is_dir()
            if os.name != "nt":
                assert stat.S_IMODE(runtime.stat().st_mode) == 0o700
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin" / "python").write_text("", encoding="utf-8")

    monkeypatch.setattr(shared_runtime, "_run", fake_run)
    monkeypatch.setattr(shared_runtime, "_runtime_python_version", lambda _p: "3.10.99")

    shared_runtime._build_runtime(runtime, bundle, digest, approved, "3.10")

    assert calls[0] == [str(approved), "-m", "venv", str(runtime)]
    assert calls[1][1:5] == ["-m", "pip", "install", "--no-index"]
    assert calls[2][1:] == ["-m", "pip", "check"]
    assert calls[3][1:] == [
        "-c",
        "import pandas; import numpy; import openpyxl; import yaml; import scipy; import textual",
    ]
    metadata = json.loads(
        (runtime / shared_runtime.COMPLETE_MARKER).read_text(encoding="utf-8")
    )
    assert metadata["bundle_digest"] == digest
    assert metadata["python_version"] == "3.10.99"
    assert metadata["required_imports"] == list(shared_runtime.REQUIRED_IMPORTS)


@pytest.mark.parametrize("failure_index", [1, 2, 3])
def test_failed_validation_never_writes_completion_marker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_index: int
) -> None:
    runtime = tmp_path / "runtime"
    bundle, digest = make_bundle(tmp_path)
    calls = 0

    def fake_run(command: list[str]) -> None:
        nonlocal calls
        current = calls
        calls += 1
        if current == 0:
            (runtime / "bin").mkdir(parents=True)
            (runtime / "bin" / "python").write_text("", encoding="utf-8")
        if current == failure_index:
            raise shared_runtime.RuntimeInstallError("simulated failure")

    monkeypatch.setattr(shared_runtime, "_run", fake_run)
    monkeypatch.setattr(shared_runtime, "_runtime_python_version", lambda _p: "3.10.1")

    with pytest.raises(shared_runtime.RuntimeInstallError, match="simulated"):
        shared_runtime._build_runtime(runtime, bundle, digest, Path("/python"), "3.10")

    assert not (runtime / shared_runtime.COMPLETE_MARKER).exists()


def test_python_target_mismatch_fails_before_pip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtime = tmp_path / "runtime"
    bundle, digest = make_bundle(tmp_path)
    calls: list[list[str]] = []

    def fake_run(command: list[str]) -> None:
        calls.append(command)
        (runtime / "bin").mkdir(parents=True, exist_ok=True)
        (runtime / "bin" / "python").write_text("", encoding="utf-8")

    monkeypatch.setattr(shared_runtime, "_run", fake_run)
    monkeypatch.setattr(shared_runtime, "_runtime_python_version", lambda _p: "3.11.0")

    with pytest.raises(shared_runtime.RuntimeInstallError, match="targets Python 3.10"):
        shared_runtime._build_runtime(runtime, bundle, digest, Path("/python"), "3.10")

    assert len(calls) == 1
    assert not (runtime / shared_runtime.COMPLETE_MARKER).exists()


def test_activation_reuse_switch_and_rollback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":
        pytest.skip("activation symlinks are validated on Linux")
    root = tmp_path / "root"
    first_bundle, first_digest = make_bundle(
        tmp_path, {"requirements/requirements.txt": b"first\n"}
    )
    second_bundle, second_digest = make_bundle(
        tmp_path, {"requirements/requirements.txt": b"second\n"}
    )
    monkeypatch.setattr(shared_runtime, "_build_runtime", _fake_completed_build)

    assert shared_runtime.install(first_bundle, Path("/python"), root) == (
        first_digest,
        False,
    )
    assert shared_runtime.install(first_bundle, Path("/python"), root) == (
        first_digest,
        True,
    )
    assert shared_runtime.install(second_bundle, Path("/python"), root) == (
        second_digest,
        False,
    )
    assert (root / ".venv" / "current").resolve().name == second_digest
    assert shared_runtime.install(first_bundle, Path("/python"), root) == (
        first_digest,
        True,
    )
    assert (root / ".venv" / "current").resolve().name == first_digest


def test_failed_candidate_preserves_current_and_is_removed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":
        pytest.skip("activation symlinks are validated on Linux")
    root = tmp_path / "root"
    first, first_digest = make_bundle(
        tmp_path, {"requirements/requirements.txt": b"first\n"}
    )
    second, second_digest = make_bundle(
        tmp_path, {"requirements/requirements.txt": b"second\n"}
    )
    monkeypatch.setattr(shared_runtime, "_build_runtime", _fake_completed_build)
    shared_runtime.install(first, Path("/python"), root)

    def fail(runtime: Path, *_args: object) -> None:
        runtime.mkdir(parents=True)
        raise shared_runtime.RuntimeInstallError("simulated failure")

    monkeypatch.setattr(shared_runtime, "_build_runtime", fail)
    with pytest.raises(shared_runtime.RuntimeInstallError, match="simulated"):
        shared_runtime.install(second, Path("/python"), root)

    assert (root / ".venv" / "current").resolve().name == first_digest
    assert not (root / ".venv" / "releases" / second_digest).exists()


def test_corrupt_active_runtime_is_never_rebuilt_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":
        pytest.skip("activation symlinks are validated on Linux")
    root = tmp_path / "root"
    bundle, digest = make_bundle(tmp_path)
    monkeypatch.setattr(shared_runtime, "_build_runtime", _fake_completed_build)
    shared_runtime.install(bundle, Path("/python"), root)
    runtime = root / ".venv" / "releases" / digest
    (runtime / shared_runtime.COMPLETE_MARKER).write_text("{}\n", encoding="utf-8")

    with pytest.raises(shared_runtime.RuntimeInstallError, match="rebuilt in place"):
        shared_runtime.install(bundle, Path("/python"), root)

    assert (runtime / "bin" / "python").exists()


def test_incomplete_inactive_runtime_is_rebuilt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":
        pytest.skip("activation symlinks are validated on Linux")
    root = tmp_path / "root"
    bundle, digest = make_bundle(tmp_path)
    partial = root / ".venv" / "releases" / digest
    partial.mkdir(parents=True)
    (partial / "partial").write_text("incomplete", encoding="utf-8")

    def rebuild(runtime: Path, *args: object) -> None:
        shutil.rmtree(runtime)
        _fake_completed_build(runtime, *args)

    monkeypatch.setattr(shared_runtime, "_build_runtime", rebuild)
    assert shared_runtime.install(bundle, Path("/python"), root) == (digest, False)
    assert not (partial / "partial").exists()


def test_activation_cleans_stale_temporary_links(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.name == "nt":
        pytest.skip("activation symlinks are validated on Linux")
    root = tmp_path / "root"
    bundle, _digest = make_bundle(tmp_path)
    runtime_root = root / ".venv"
    runtime_root.mkdir(parents=True)
    (runtime_root / ".current.tmp.999").symlink_to(
        Path("releases") / ("d" * 64), target_is_directory=True
    )
    monkeypatch.setattr(shared_runtime, "_build_runtime", _fake_completed_build)

    shared_runtime.install(bundle, Path("/python"), root)

    assert not list(runtime_root.glob(".current.tmp.*"))


def test_install_lock_excludes_concurrent_installer(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("flock concurrency is validated on Linux")
    lock_path = tmp_path / "install.lock"
    first_acquired = threading.Event()
    release_first = threading.Event()
    second_acquired = threading.Event()

    def first() -> None:
        with shared_runtime._install_lock(lock_path):
            first_acquired.set()
            release_first.wait(timeout=5)

    def second() -> None:
        first_acquired.wait(timeout=5)
        with shared_runtime._install_lock(lock_path):
            second_acquired.set()

    first_thread = threading.Thread(target=first)
    second_thread = threading.Thread(target=second)
    first_thread.start()
    second_thread.start()
    assert first_acquired.wait(timeout=5)
    assert not second_acquired.wait(timeout=0.1)
    release_first.set()
    first_thread.join(timeout=5)
    second_thread.join(timeout=5)
    assert second_acquired.is_set()


def test_completed_runtime_permissions_are_not_publicly_writable(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX modes are validated on Linux")
    runtime = tmp_path / "runtime"
    package = runtime / "lib" / "package.py"
    executable = runtime / "bin" / "python"
    package.parent.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    package.write_text("", encoding="utf-8")
    executable.write_text("", encoding="utf-8")
    executable.chmod(0o755)
    approved = tmp_path / "approved"
    approved.write_text("", encoding="utf-8")
    approved.chmod(0o755)
    (runtime / "bin" / "python3").symlink_to(approved)

    shared_runtime._make_owner_writable_only(runtime)

    assert runtime.stat().st_mode & 0o022 == 0
    assert package.stat().st_mode & 0o044 == 0o044
    assert executable.stat().st_mode & 0o055 == 0o055
    assert stat.S_IMODE(approved.stat().st_mode) == 0o755


def test_completed_runtime_permissions_restore_bin_execution(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("POSIX modes are validated on Linux")
    runtime = tmp_path / "runtime"
    python = runtime / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("", encoding="utf-8")
    python.chmod(0o600)

    shared_runtime._make_owner_writable_only(runtime)

    assert python.stat().st_mode & 0o055 == 0o055


def test_install_rejects_symlinked_runtime_root(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip("runtime-root symlinks are validated on Linux")
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / ".venv").symlink_to(outside, target_is_directory=True)
    bundle, _digest = make_bundle(tmp_path)

    with pytest.raises(shared_runtime.RuntimeInstallError, match="must not be a symlink"):
        shared_runtime.install(bundle, Path("/python"), root)
