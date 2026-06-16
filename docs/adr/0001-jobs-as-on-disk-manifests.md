# Jobs are on-disk manifests under `/ads_storage/<user>/.dispatch/jobs/`

A **Job** is realised as a directory at
`/ads_storage/<user>/.dispatch/jobs/<jobid>/`, where `<jobid>` is
`<UTC timestamp>_<6-char-base32-random>` (e.g. `20260509T164500Z_a1b2c3`).
The directory holds a JSON manifest, the orchestrator's `run.log`, a `run.pid`
file, and a snapshot of the submitted SQL. CSV outputs are not stored under
the Job directory — they are written directly to the user's launch-time
working directory, with the absolute output path recorded in the manifest
(see ADR-0003). A small,
stdlib-only **runner script** — not the TUI — owns the lifecycle: it spawns
the orchestrator(s) under `nohup` + `setsid`, redirects stdout/stderr to
`run.log`, and writes the terminal **Job state** to the manifest on exit.
The TUI is read-only over `~/.dispatch/jobs/`, so the dashboard, history view,
and reattach (live `tail -f`) all reduce to filesystem reads with no IPC.

We chose `/ads_storage/<user>/` over `$HOME` because it is the same volume the
orchestrators already use; durability and quota properties are known-good for
Hadoop work, and Jobs remain visible if the user lands on a different edge
node.

## Considered alternatives

- **`tmux` session per Job.** Rejected because it adds a system dependency,
  the orchestrators are non-interactive (so a real terminal buys nothing),
  and nesting becomes awkward when users run the TUI itself inside their own
  `tmux` session. Manifest state would also no longer be authoritative —
  exit codes still need to be persisted out-of-band.
- **A long-lived per-user daemon owning Jobs.** Rejected as overkill; nothing
  about the workflow needs an always-on process when the orchestrators
  self-terminate and the runner script can update the manifest on exit.
- **`screen` per Job.** Strictly worse than `tmux` and rejected for the same
  reasons.

## Consequences

- The runner script and the manifest schema together form a stable on-disk
  contract. Changing them after launch breaks anyone with in-flight or
  historical Jobs, so they are versioned (manifest carries a `schema_version`
  field).
- Concurrency enforcement is just a count over `manifest.state == "Running"`;
  no locks needed.
- Cancel is `os.killpg(pgid, SIGTERM)` — clean because the runner spawns the
  orchestrator under a fresh process group via `setsid`.

## Invariant: the TUI never spawns an orchestrator directly

The TUI's only sanctioned way to start work is to spawn the **runner script**
(detached, via `nohup` + `setsid`). The runner is the orchestrator's parent.
This is what makes the TUI a thin client over `~/.dispatch/jobs/` — it can
crash, be closed, lose its ssh connection, or be force-killed without
affecting any running Job. A single helper module (`dispatch/process.py`) is
the only place in the TUI codebase allowed to spawn subprocesses, and code
review enforces this.

