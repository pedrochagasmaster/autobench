# Autobench Development and Release Workflow

This is the canonical Autobench release workflow. For local setup, focused
tests, and commit hygiene, start with [../CONTRIBUTING.md](../CONTRIBUTING.md).

The default release path is the installed `edge-deploy-core` package; repo-local
deployment scripts are retained for bootstrap, recovery, and deep
troubleshooting.

## Default Workflow

1. Start from `main` unless the user explicitly asks for another branch.

   ```powershell
   cd <autobench-repo>
   git status --short --branch
   git branch -vv
   ```

2. Make the change and run focused checks for the touched files.

3. Run the local gate before committing:

   ```powershell
   .\tools\dev\local_check.ps1
   ```

4. Commit the reviewed change locally:

   ```powershell
   git diff
   git add <files>
   git commit -m "Describe the change"
   ```

5. Release with the installed `edge-deploy-core` package:

   ```powershell
   py -m edge_deploy release --tool autobench --smoke standard
   ```

   Use `--tool both` when Autobench and Dispatch must be released together.
   The release command publishes the deployable snapshot, drives node03 and
   node04 updates, handles the interactive RSA prompts in the visible terminal,
   runs drift/smoke validation, and writes the release evidence under
   `edge-deploy\reports\release-*` under the current shell directory unless
   `--report-dir` is set.

6. Verify the release report:

   - `release.json` has `overall_status: "passed"`.
   - Every Autobench rollout has `status: "passed"`.
   - `remote_git_preflight` is present for each node.
   - Drift and smoke checks passed for node03 and node04.
   - No secret-shaped values were written to the report.

## Remotes

Keep remote roles explicit:

- `origin`: GitHub mirror/review remote.
- `bitbucket`: corporate deployment remote for the Edge Nodes:
  `https://scm.mastercard.int/stash/scm/~e176097/autobench.git`.

Configure Bitbucket once if needed:

```powershell
git remote add bitbucket https://scm.mastercard.int/stash/scm/~e176097/autobench.git
git remote -v
```

If the remote already exists with another URL, fix it:

```powershell
git remote set-url bitbucket https://scm.mastercard.int/stash/scm/~e176097/autobench.git
```

Do not push to either remote from an agent session unless the user explicitly
asks. The release orchestrator owns the normal deployment push.

## Release Decision Table

| Situation | Use | Scope |
| --- | --- | --- |
| Normal development release | `py -m edge_deploy release --tool autobench --smoke standard` | Default path for production promotion, node updates, drift, smoke, and report evidence. |
| Coordinated Autobench + Dispatch release | `py -m edge_deploy release --tool both --smoke standard` | Default path when both tools need the same release process. |
| Exact rollback or targeted recovery | `edge_deploy release` with the selected rollback/recovery option, or the repo-local skill when the orchestrator cannot proceed | Operator-controlled exception; record the report path and target SHA. |
| First-time node bootstrap or offline dependency refresh | `deploy_and_install.ps1`, `setup_remote_env.sh`, and `install.sh` | Bootstrap/recovery only, not the default release path. |
| Low-level node diagnosis | `tools/prod_tui`, `update.sh`, tmux/SSH inspection | Deep troubleshooting only, preferably after checking the release report. |

## What the Release Orchestrator Does

For Autobench, `edge_deploy release` is responsible for the end-to-end release:

- confirms the local source commit,
- publishes the deployment snapshot to the corporate remote,
- updates `/ads_storage/autobench` on node03 and node04,
- uses a safe Git fetch shape and self-heals the known corrupt
  `refs/remotes/bitbucket/main` condition,
- preserves per-user runtime state,
- records update, drift, smoke, and permission evidence,
- produces machine-readable reports under `edge-deploy/reports/release-*`.

The operator may still have to type RSA PASSCODEs in the visible terminal.
Manual tmux attachment and node-side commands are not part of the default path.

## Recovery and Bootstrap Paths

Use `.agents/skills/autobench-edge-deploy/WORKFLOW.md` only when the normal
release command is unavailable or the release report points to a node-specific
condition that requires manual inspection.

Repo-local commands such as these are valid only in that recovery/bootstrap
context:

```powershell
.\tools\dev\publish_bitbucket_snapshot.ps1
.\deploy_and_install.ps1
```

```bash
cd /ads_storage/autobench
./update.sh
./install.sh
```

When using recovery paths, record the node, target SHA, command output, drift
result, smoke result, and why the default release command was not sufficient.

## Production Validation

The default validation is the release report produced by `edge_deploy release`.
Use the repo-local production harness for additional diagnosis or deeper
coverage:

```powershell
cd <autobench-repo>
py -m tools.prod_tui smoke --config tools/prod_tui/config-node04.yaml --level 2 --save-screens
py -m tools.prod_tui drift --local . --remote /ads_storage/autobench
```

For changes that affect end-to-end analysis behavior, the release smoke or a
manual recovery session may also run:

```bash
cd /ads_storage/autobench
autobench-cli config list
autobench-cli share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --export-balanced-csv --output /tmp/autobench_smoke.xlsx
```

## Change Hygiene

- Do not commit generated bundles, reports, logs, screens, local data, or
  credentials.
- Do not commit RSA passcodes, Kerberos passwords, PATs, or internal
  screenshots.
- Prefer the orchestrated release report over ad hoc terminal notes for release
  evidence.
- If any manual server edit occurs, run drift detection before claiming parity.
