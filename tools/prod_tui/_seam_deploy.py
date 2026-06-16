"""Compare / deploy the deployed Dispatch tree over an authenticated tmux pane.

Multi-node aware: ``--config`` selects which edge node to act on (each node has
its own ``config-*.yaml`` and its own SSH/Kerberos session, since the nodes are
independent filesystems). Default target is the node-03 ``config.yaml``."""
from __future__ import annotations

import argparse
import base64
import hashlib
import re
import sys
from pathlib import Path

from tools.prod_tui.robocop_tmux import driver_from_config_path, DEFAULT_CONFIG_PATH

REMOTE = "/ads_storage/dispatch/dispatch/app.py"
LOCAL = Path("dispatch/app.py")
REMOTE_COPY = Path("tools/prod_tui/_remote_app.py")

# Which node config the next _driver() call targets. Overridden by --config so a
# single invocation acts on exactly one node.
_CONFIG_PATH = str(DEFAULT_CONFIG_PATH)

# Local source root -> remote deployed root. The repo is deployed at
# /ads_storage/dispatch, so the package lives at /ads_storage/dispatch/dispatch.
SYNC_ROOTS = (
    ("dispatch", "/ads_storage/dispatch/dispatch"),
    ("scr", "/ads_storage/dispatch/scr"),
)


def _md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _remote_md5s(d, remote_root: str) -> dict[str, str]:
    """Return {relpath: md5} for every *.py under a remote root in one round-trip."""
    out, _ = d.run_remote(
        f"find {remote_root} -name '*.py' -not -path '*/__pycache__/*' "
        f"-exec md5sum {{}} +",
        timeout=90,
    )
    result: dict[str, str] = {}
    prefix = remote_root.rstrip("/") + "/"
    for line in out.splitlines():
        m = re.match(r"([0-9a-f]{32})\s+(\S.*)$", line.strip())
        if not m:
            continue
        path = m.group(2)
        if path.startswith(prefix):
            result[path[len(prefix):]] = m.group(1)
    return result


def _scan() -> list[tuple[str, str, str, str, str]]:
    """Compare local vs remote for all sync roots.

    Returns rows of (status, local_root, relpath, local_md5, remote_md5).
    """
    d = _driver()
    rows: list[tuple[str, str, str, str, str]] = []
    for local_root, remote_root in SYNC_ROOTS:
        lroot = Path(local_root)
        if not lroot.exists():
            continue
        remote = _remote_md5s(d, remote_root)
        local_rels = {p.relative_to(lroot).as_posix() for p in lroot.rglob("*.py")
                      if "__pycache__" not in p.parts}
        for rel in sorted(local_rels):
            lmd5 = _md5(lroot / rel)
            rmd5 = remote.get(rel, "")
            if not rmd5:
                rows.append(("MISSING_REMOTE", local_root, rel, lmd5, ""))
            elif rmd5 != lmd5:
                rows.append(("DIFFER", local_root, rel, lmd5, rmd5))
            else:
                rows.append(("MATCH", local_root, rel, lmd5, rmd5))
        for rel in sorted(remote):
            if rel not in local_rels:
                rows.append(("MISSING_LOCAL", local_root, rel, "", remote[rel]))
    return rows


def verify() -> None:
    rows = _scan()
    drift = [r for r in rows if r[0] != "MATCH"]
    for status, root, rel, lmd5, rmd5 in rows:
        if status == "MATCH":
            continue
        print(f"[{status:14}] {root}/{rel}  local={lmd5[:8] or '--------'} remote={rmd5[:8] or '--------'}")
    matched = sum(1 for r in rows if r[0] == "MATCH")
    print(f"\nMATCH={matched}  DRIFT={len(drift)}  TOTAL={len(rows)}")
    if not drift:
        print("IN_SYNC")


def sync() -> None:
    """Redeploy drifted dispatch/ files. scr/ drift is reported but never
    auto-deployed (production-sensitive orchestrators)."""
    rows = _scan()
    for status, root, rel, lmd5, rmd5 in rows:
        if status == "MATCH":
            continue
        if root == "scr":
            print(f"[SKIP-SCR {status}] {root}/{rel} (deploy manually if intended)")
            continue
        if status == "MISSING_LOCAL":
            print(f"[SKIP {status}] {root}/{rel} (exists only on remote)")
            continue
        local_rel = f"{root}/{rel}"
        remote_path = f"{dict(SYNC_ROOTS)[root]}/{rel}"
        print(f"--- deploying {local_rel} -> {remote_path} ({status}) ---")
        deploy_file(local_rel, remote_path)
    print("\n--- re-verifying ---")
    verify()


def deploy_all() -> None:
    """Deploy every drifting file, *including* scr/, then re-verify.

    Use this to bring a fresh / independent node to parity (e.g. node 04).
    Unlike ``sync``, this intentionally pushes the production-sensitive scr/
    orchestrators too - the ADR-0005 review still governs whether those changes
    are blessed, but a node already running them must not silently drift.
    """
    rows = _scan()
    drift = [r for r in rows if r[0] not in ("MATCH", "MISSING_LOCAL")]
    if not drift:
        print("Nothing to deploy.")
        verify()
        return
    for status, root, rel, _lmd5, _rmd5 in rows:
        if status == "MATCH":
            continue
        if status == "MISSING_LOCAL":
            print(f"[SKIP {status}] {root}/{rel} (exists only on remote)")
            continue
        local_rel = f"{root}/{rel}"
        remote_path = f"{dict(SYNC_ROOTS)[root]}/{rel}"
        tag = " [scr/]" if root == "scr" else ""
        print(f"--- deploying{tag} {local_rel} -> {remote_path} ({status}) ---")
        deploy_file(local_rel, remote_path)
    print("\n--- re-verifying ---")
    verify()


def _driver():
    _cfg, d = driver_from_config_path(_CONFIG_PATH)
    return d


def fetch() -> None:
    d = _driver()
    out, code = d.run_remote(f"base64 {REMOTE} | tr -d '\\n'", timeout=30)
    if code != 0:
        print("FETCH FAILED", code)
        print(out[-500:])
        sys.exit(1)
    data = base64.b64decode("".join(out.split()))
    REMOTE_COPY.write_bytes(data)
    print("FETCHED", len(data), "bytes ->", REMOTE_COPY)


def deploy(src: Path) -> None:
    d = _driver()
    payload = src.read_bytes()
    encoded = base64.b64encode(payload).decode("ascii")
    # Back up the current remote file once.
    _, code = d.run_remote(f"cp -n {REMOTE} {REMOTE}.seam_bak", timeout=20)
    print("backup exit", code)
    chunk = 1000
    parts = [encoded[i:i + chunk] for i in range(0, len(encoded), chunk)]
    tmp = "/tmp/app_seam.b64"
    for idx, part in enumerate(parts):
        redir = ">" if idx == 0 else ">>"
        _, c = d.run_remote(f"printf %s '{part}' {redir} {tmp}", timeout=20)
        if c != 0:
            print("chunk", idx, "failed", c)
            sys.exit(1)
    _, c = d.run_remote(f"base64 -d {tmp} > {REMOTE}", timeout=20)
    print("decode exit", c)
    # Validate syntax and seam presence remotely.
    out, c = d.run_remote(
        f"python3 -c \"import ast,sys; ast.parse(open('{REMOTE}').read()); "
        f"print('SEAM' if 'DISPATCH_TEST_PREFILL' in open('{REMOTE}').read() else 'NOSEAM')\"",
        timeout=25,
    )
    print("validate exit", c)
    print(out[-300:])


def diag() -> None:
    d = _driver()
    py = "/ads_storage/e176097/.dispatch/venv/bin/python"
    out, code = d.run_remote(f"{py} -c 'import textual; print(textual.__version__)'", timeout=25)
    print("textual exit", code, "->", out.strip().splitlines()[-2] if out.strip().splitlines() else "")
    out, code = d.run_remote("md5sum /ads_storage/dispatch/dispatch/screens/new_job.py", timeout=20)
    import re
    m = re.search(r"([0-9a-f]{32})", out)
    print("new_job md5", m.group(1) if m else "NONE")


def diag2() -> None:
    d = _driver()
    py = "/ads_storage/e176097/.dispatch/venv/bin/python"
    out, _ = d.run_remote(f"{py} -m pip show textual 2>/dev/null | grep -i version", timeout=25)
    print("--- textual version ---")
    print(out)
    out, _ = d.run_remote(
        "grep -n -A 35 'def _apply_prefill' /ads_storage/dispatch/dispatch/screens/new_job.py",
        timeout=20,
    )
    print("--- remote _apply_prefill ---")
    print(out)


def whichmod() -> None:
    d = _driver()
    py = "/ads_storage/e176097/.dispatch/venv/bin/python"
    cmd = (
        f"PYTHONPATH=/ads_storage/dispatch {py} -c "
        "'import dispatch.screens.new_job as m; print(m.__file__); "
        "import inspect; src=inspect.getsource(m._apply_prefill) if hasattr(m,\"_apply_prefill\") else \"\"; "
        "print(\"HAS_PRESS\", \"_press_radio\" in open(m.__file__).read())'"
    )
    out, code = d.run_remote(cmd, timeout=30)
    print("exit", code)
    print(out[-700:])


def deploy_file(local_rel: str, remote_path: str) -> None:
    d = _driver()
    payload = Path(local_rel).read_bytes()
    encoded = base64.b64encode(payload).decode("ascii")
    d.run_remote(f"cp -n {remote_path} {remote_path}.seam_bak", timeout=20)
    chunk = 1000
    parts = [encoded[i:i + chunk] for i in range(0, len(encoded), chunk)]
    tmp = "/tmp/_deploy.b64"
    for idx, part in enumerate(parts):
        redir = ">" if idx == 0 else ">>"
        _, c = d.run_remote(f"printf %s '{part}' {redir} {tmp}", timeout=20)
        if c != 0:
            print("chunk", idx, "failed", c)
            sys.exit(1)
    _, c = d.run_remote(f"base64 -d {tmp} > {remote_path}", timeout=20)
    print("decode exit", c)
    out, c = d.run_remote(
        f"/ads_storage/e176097/.dispatch/venv/bin/python -c \"import ast; ast.parse(open('{remote_path}').read()); print('OK')\"",
        timeout=25,
    )
    print("validate exit", c, "->", out.strip().splitlines()[-2] if out.strip().splitlines() else "")


MODES = (
    "verify", "sync", "deploy-all", "fetch", "deploy",
    "deploy-newjob", "deploy-manifest", "deploy-path", "diag", "diag2", "whichmod",
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare/deploy the Dispatch tree to an edge node over its tmux pane.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_PATH),
        help="Node config to target (default: node-03 config.yaml). "
             "Use config-node04.yaml for node 04.",
    )
    parser.add_argument("mode", nargs="?", default="verify", choices=MODES)
    parser.add_argument("args", nargs="*", help="extra args (deploy-path LOCAL REMOTE)")
    ns = parser.parse_args(argv)

    global _CONFIG_PATH
    _CONFIG_PATH = ns.config

    if ns.mode == "verify":
        verify()
    elif ns.mode == "sync":
        sync()
    elif ns.mode == "deploy-all":
        deploy_all()
    elif ns.mode == "fetch":
        fetch()
    elif ns.mode == "deploy":
        deploy(LOCAL)
    elif ns.mode == "deploy-newjob":
        deploy_file("dispatch/screens/new_job.py", "/ads_storage/dispatch/dispatch/screens/new_job.py")
    elif ns.mode == "deploy-manifest":
        deploy_file("dispatch/manifest.py", "/ads_storage/dispatch/dispatch/manifest.py")
    elif ns.mode == "deploy-path":
        if len(ns.args) != 2:
            parser.error("deploy-path requires LOCAL and REMOTE arguments")
        deploy_file(ns.args[0], ns.args[1])
    elif ns.mode == "diag":
        diag()
    elif ns.mode == "diag2":
        diag2()
    elif ns.mode == "whichmod":
        whichmod()
    return 0


if __name__ == "__main__":
    sys.exit(main())
