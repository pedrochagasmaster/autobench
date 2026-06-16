# Production Testing Process

This is the canonical process for validating the real Dispatch Textual TUI on a
Hadoop Edge Node.

```text
local machine
  └─ tmux session
       └─ pane: ssh -p 2222 <user>@<edge-node>   ← RSA PASSCODE (2FA)
            └─ remote shell
                 ├─ kinit                          ← Kerberos password
                 └─ dispatch / impala-shell / tests
```

The agent does **not** drive Dispatch with plain `subprocess`, because Dispatch
is a real Textual TUI, not a stdin/stdout CLI. tmux gives persistence, screen
capture, and the ability for a human to attach to the same session.

> **Session model.** tmux runs **locally**; the SSH connection lives *inside*
> the tmux pane. All `send-keys` / `capture-pane` / `attach` calls operate on
> the local session — there is no second SSH hop per command. One-off
> non-interactive remote commands (file writes, `impala-shell`, `klist`) may use
> a separate direct `ssh`.

## Authentication

Two interactive secrets are required and must be entered by a human; never
hard-code or echo them:

1. **RSA SecurID PASSCODE** — prompted by SSH (`Enter PASSCODE:`) right after the
   login banner.
2. **Kerberos password** — prompted by `kinit` (`Password for
   <user>@CORP.MASTERCARD.ORG:`).

Confirm the ticket with `klist` before running Level 2 or Level 3 checks.

## Manual session (what the harness automates)

```bash
tmux new-session -d -s robocop-prod-test -x 120 -y 40
tmux send-keys  -t robocop-prod-test "ssh -p 2222 <user>@<edge-node>" Enter
# enter the RSA PASSCODE at the prompt (attach if typing it yourself):
tmux attach -t robocop-prod-test     # Ctrl-b d to detach without killing

# on the remote shell:
tmux send-keys -t robocop-prod-test "kinit" Enter   # enter Kerberos password
tmux send-keys -t robocop-prod-test "klist" Enter
tmux capture-pane -t robocop-prod-test -p
```

To launch the real TUI from a directory of SQL files:

```bash
tmux send-keys -t robocop-prod-test "cd /path/to/sql/files && dispatch" Enter
tmux capture-pane -t robocop-prod-test -p
```

## Harness (preferred)

`tools/prod_tui/` codifies the model above. See
[tools/prod_tui/README.md](../tools/prod_tui/README.md) for full usage. The host,
port, and SSH options live in `tools/prod_tui/config.yaml`.

```bash
# start the local tmux session + SSH (sends the PASSCODE for you if provided)
py -m tools.prod_tui tmux start --passcode <RSA_PASSCODE>

py -m tools.prod_tui tmux send "dispatch"
py -m tools.prod_tui tmux keys tab enter
py -m tools.prod_tui tmux capture
py -m tools.prod_tui tmux attach
py -m tools.prod_tui tmux stop

# scripted test levels
py -m tools.prod_tui smoke --level all --save-screens
py -m tools.prod_tui job --dry-run
```

The agent loop is: capture screen → reason about the visible UI → send a
key/action → capture again → assert the expected state.

## Deployment Path Before Testing

Use [docs/development-workflow.md](./development-workflow.md) as the canonical
workflow. Choose the deployment path before running production checks:

- **Bitbucket pull:** preferred for committed, reviewable deployments. Pull the
  branch or exact commit on each Edge Node, run `install.sh`, then validate.
- **`_seam_deploy sync`:** fast iteration for authenticated sessions. It syncs
  drifted `dispatch/` Python files and reports `scr/` drift without deploying
  it.
- **`_seam_deploy deploy-all`:** explicit node parity operation that may include
  `scr/`; ADR-0005 still governs whether that change is safe to merge.
- **Zip deploy:** first-time setup, vendor refresh, offline install, or recovery
  when the server working tree is not usable.

Node 03 and node 04 use independent filesystems. Update and validate both nodes
separately when the goal is production parity.

## Test levels

The detailed, checkable steps live in
[docs/edge-node-smoke-test.md](./edge-node-smoke-test.md). In short:

- **Level 1 — safe production smoke (no job launch):** SSH + tmux work,
  `compileall` is clean, the dashboard renders, Kerberos status shows, navigation
  works, SQL browser / history / preview open, quit is clean.
- **Level 2 — real environment checks (no destructive actions):** `install.sh`
  works against the real `/ads_storage/<user>/` path, `klist` is detected,
  `impala-shell` is on PATH, the launch CWD is captured, Textual renders over the
  corporate SSH chain.
- **Level 3 — controlled real job:** only a trivial scratch query
  (`SELECT 1 AS smoke_test_value`) into a writable scratch schema, with a
  destination table named `dispatch_smoke_<user>_<date>`.

## Safety classification

```text
SAFE:       navigate, preview, capture, inspect logs/history, --help, compileall
CONTROLLED: launch the smoke query with a dispatch_smoke_ prefixed table only
BLOCKED:    drop tables, run arbitrary SQL, modify scr/, delete files,
            launch unknown user SQL
```

A `CONTROLLED` launch is allowed only when:

- the target schema is explicitly scratch/writable,
- the SQL file is known and tiny,
- the destination table/output name starts with `dispatch_smoke_`,
- the Kerberos TTL is healthy (≥ 5 minutes), and
- no more than the allowed running-job cap (2) is active.

These mirror the app's own invariants (refuse missing/low Kerberos tickets and
more than two simultaneously Running jobs).

`pytest` / Textual `Pilot` remain the tool for deterministic, non-prod
regression tests; SSH + tmux + a real Edge Node is the acceptance harness.
