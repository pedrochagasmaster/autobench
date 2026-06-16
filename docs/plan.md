# Dispatch — Implementation Plan

This document is the consolidated specification for migrating the **Hadoop
Query Launcher** from a Windows GUI (`run_query.ps1`) to a server-side TUI
named **Dispatch** running directly on the Hadoop edge node. It synthesises
the design conversation into a single reference for implementers.

It assumes the reader has already read [`CONTEXT.md`](../CONTEXT.md) for the
domain language and the architectural decisions in
[`docs/adr/`](./adr/).

---

## 1. Vision

Today, running a long Impala query is a multi-system ritual: open a Windows
GUI on a workstation, fill a form, watch it scp a file, paste a generated
command into a separately-launched ssh terminal, and trust the email
notifications. Dispatch collapses that ritual into one server-side TUI.
Users `ssh` to the edge node, `cd` to where their `.sql` files live, run
`dispatch`, fill a form, and walk away. **Jobs** survive ssh disconnects
because they're owned by an out-of-process runner, not by the TUI itself.

Dispatch reuses the production-tested orchestrator scripts in `scr/` as the
queue-cycling, retrying, email-notifying engine — they remain a frozen
black-box API for v1.0 and are subject to surgical, mock-validated changes
thereafter (ADR-0005).

---

## 2. What changes for users

| Today | After Dispatch v1.0 |
|---|---|
| Double-click `run_query_engine.bat` on Windows | Run `dispatch` from any directory on the edge node |
| Form fields point at a local Windows path | Form is CWD-aware: shows `*.sql` in `$PWD` |
| `scp` step uploads SQL | No `scp`; the SQL is already on the server |
| Manual `kinit` after ssh; orchestrator fails late if you forgot | TUI pre-flights `klist`; TTL is shown live; in-TUI `kinit` via terminal-suspend |
| Terminal window IS the live tail; closing it loses the tail | Job dashboard reattaches the live tail at any time |
| Four named workflows with hidden mode-flag interactions | Two orthogonal axes — `Source` × `Destination` — with greyed-out illegal cells |
| No way to see "what's running for me" | First-class Job dashboard + 7-day history |
| CSV results come back as `.csv.gz` over `scp` | CSV lands uncompressed in `$PWD` |
| One Job per "Launch" click; no concurrency awareness | Hard cap of 2 Running Jobs per user |

---

## 3. Domain model

See [`CONTEXT.md`](../CONTEXT.md) for canonical definitions. Headline:

A **Job** is `(Source, Destination, params)`. **Source** is one of `SqlFile`
/ `SqlTemplate` / `ExistingTable`. **Destination** is one of `Table` / `Csv`
/ `Table + Csv`. Five legal cells in the matrix; each maps to one or two
calls to an **Orchestrator script** in `scr/`.

| Source ↓ / Destination → | Table | Csv | Table + Csv |
|---|---|---|---|
| `SqlFile` | `Query_Impala_Parametrized.py` | `download_to_csv.py --query-file` | both, sequenced |
| `SqlTemplate` | `monthly_query_processor.py` | — | — |
| `ExistingTable` | — | `download_to_csv.py --table-name` | — |

`SqlTemplate + Csv` is intentionally absent — monthly outputs are for
downstream analytical use, not bulk CSV export.

---

## 4. Architectural decisions

| ADR | Decision |
|---|---|
| [0001](./adr/0001-jobs-as-on-disk-manifests.md) | **Jobs are on-disk manifests under `/ads_storage/<user>/.dispatch/jobs/`.** A small stdlib runner script owns the lifecycle; the TUI is read-only over the directory. |
| [0002](./adr/0002-textual-for-the-tui.md) | **Textual is the TUI framework**, vendored as wheels and installed into a per-user venv. The orchestrators keep their stdlib-only policy. |
| [0003](./adr/0003-csv-output-uncompressed-in-user-cwd.md) | **CSVs land uncompressed in the user's launch-time CWD.** The runner decomposes `Table + Csv` into two orchestrator calls instead of using the orchestrator's gzipping `--download` path. |
| [0004](./adr/0004-mock-layer-for-offline-dev.md) | **A `mocks/` directory fakes every external system** so the tool runs end-to-end on a developer laptop. |
| [0005](./adr/0005-scr-modification-policy.md) | **The `scr/` orchestrators get a loosened modification policy** — obvious bug fixes and de-duplication are allowed once the mock layer lands, with required validation. |

---

## 5. Repository layout (target)

```
/                                          # repo root
├── CONTEXT.md                             # domain glossary
├── README.md                              # rewritten at v1.0 to describe Dispatch
├── docs/
│   ├── plan.md                            # this file
│   ├── adr/                               # ADRs 0001–0005
│   └── agents/                            # existing agent skill docs
├── scr/                                   # orchestrators (frozen API)
│   ├── README.md                          # NEW — "stable; see ADR-0005"
│   ├── Query_Impala_Parametrized.py
│   ├── download_to_csv.py
│   ├── monthly_query_processor.py
│   └── _common.py                         # NEW (post-ADR-0005) — shared helpers
├── dispatch/                              # NEW — the TUI Python package
│   ├── __init__.py
│   ├── __main__.py                        # entry point: `python -m dispatch`
│   ├── app.py                             # Textual App
│   ├── process.py                         # SOLE sanctioned subprocess entry point
│   ├── runner.py                          # the runner script (spawned via nohup+setsid)
│   ├── manifest.py                        # Job manifest schema (TypedDict) + read/write/validate
│   ├── jobs.py                            # Job listing, state queries, concurrency cap helpers
│   ├── kerberos.py                        # klist -s pre-flight, TTL parsing, suspend-and-run kinit
│   ├── sql.py                             # {date_inicio}/{date_fim} detection, DDL preview,
│   │                                      # monthly-partition resolution preview
│   ├── impala.py                          # SHOW TABLES / DESCRIBE / DROP via mock-friendly impala-shell
│   ├── config.py                          # /ads_storage/<user>/.dispatch/config.json read/write
│   ├── version.py                         # __version__ constant; compared against deployed VERSION
│   └── screens/
│       ├── dashboard.py                   # Active + recently-finished tables; key bindings
│       ├── new_job.py                     # Source x Destination wizard; pre-flight checks
│       ├── job_detail.py                  # Job header + RichLog tailing run.log; cancel
│       ├── history.py                     # Jobs older than 7 days; search by table/date
│       └── browser.py                     # Impala metadata browser (schema, tables, describe)
├── mocks/                                 # NEW — see ADR-0004
│   ├── bin/
│   ├── smtpd.py
│   ├── scenarios/
│   └── dev-env.sh
├── vendor/                                # NEW — pinned wheels for offline install
├── requirements.txt                       # NEW — pinned deps
├── pyproject.toml                         # NEW — defines the `dispatch` console script
├── install.sh                             # NEW — per-user installer; idempotent
└── VERSION                                # NEW — single source of truth for version string
```

The legacy GUI files (`run_query.ps1`, `run_query_engine.bat`) are deleted at
v1.0.

---

## 6. Per-user data directory

```
/ads_storage/<user>/.dispatch/
├── config.json                # email; future per-user defaults
├── installed_version          # written by install.sh; compared to repo VERSION
├── venv/                      # the per-user venv
└── jobs/
    └── <jobid>/               # per-Job directory
        ├── manifest.json      # see schema below
        ├── run.log            # nohup target — stdout+stderr of orchestrator(s)
        ├── run.pid            # PID = process group ID (for killpg cancel)
        └── job.sql            # snapshot of submitted SQL at launch time
```

`<jobid>` format: `<UTC ISO-8601 compact>_<6-char-base32-random>` — e.g.
`20260509T164500Z_a1b2c3`.

### Manifest schema

```json
{
  "schema_version": 1,
  "id": "20260509T164500Z_a1b2c3",
  "tool": "dispatch",
  "user": "e123456",
  "source": {
    "type": "SqlFile",
    "sql_path_at_launch": "/home/e123456/projects/q3/foo.sql"
  },
  "destination": {
    "type": "Table+Csv",
    "schema": "aa_enc",
    "table_name": "q3_load",
    "csv_path": "/home/e123456/projects/q3/q3_load.csv"
  },
  "params": {
    "to_email": "team@mastercard.com",
    "subject": "Q3 settlement load"
  },
  "orchestrator_calls": [
    {"script": "Query_Impala_Parametrized.py", "argv": ["..."]},
    {"script": "download_to_csv.py", "argv": ["..."]}
  ],
  "state": "Running",
  "pid": 12345,
  "started_at": "2026-05-09T16:45:00Z",
  "finished_at": null,
  "exit_code": null
}
```

---

## 7. The runner script (`dispatch/runner.py`)

A small stdlib-only Python script the TUI launches via `nohup` + `setsid`.

### 7.1 CLI contract

```
python -m dispatch.runner --job-dir <absolute path to a Job directory>
```

The job directory MUST already contain a valid `manifest.json` with
`state: "Pending"`, a populated `orchestrator_calls` list, and the SQL
snapshot at `job.sql`. The runner mutates the manifest in place. No
other CLI flags. No reading from stdin.

### 7.2 Lifecycle

```python
# Pseudocode — dispatch/runner.py
def main(job_dir: Path) -> None:
    manifest = Manifest.load(job_dir / "manifest.json")
    assert manifest["state"] == "Pending"

    log = open(job_dir / "run.log", "ab", buffering=0)
    (job_dir / "run.pid").write_text(str(os.getpid()))
    install_signal_handlers()

    manifest.update(state="Running", started_at=now_utc(), pid=os.getpid())

    try:
        for call in manifest["orchestrator_calls"]:
            global current_proc
            current_proc = subprocess.Popen(call["argv"], stdout=log, stderr=log)
            rc = current_proc.wait()
            if rc != 0:
                manifest.update(state="Failed", exit_code=rc, finished_at=now_utc())
                return
        manifest.update(state="Succeeded", exit_code=0, finished_at=now_utc())
    except Exception as e:
        log.write(f"\n[runner] Unhandled error: {e}\n".encode())
        manifest.update(state="Failed", exit_code=-1, finished_at=now_utc())
```

The runner is `setsid`-spawned by the TUI via `dispatch/process.py`, so
its PID is its process group leader. Cancel from the TUI is
`os.killpg(manifest["pid"], signal.SIGTERM)`.

### 7.3 Signal handling

- **`SIGTERM`** (sent by the TUI on cancel): trap it, forward `SIGTERM`
  to the current orchestrator process, wait up to 10 seconds, escalate
  to `SIGKILL` if still alive, write
  `state: "Cancelled"`, `exit_code: -signal.SIGTERM`, `finished_at` to
  the manifest, exit 0.
- **`SIGHUP`** (ssh disconnect): explicitly ignored. The whole point of
  `nohup` + `setsid` is that the runner outlives the TUI's ssh session.
- **`SIGINT`**: ignored for the same reason.

### 7.4 Failure modes

| Condition | Runner behaviour |
|---|---|
| Manifest unreadable / corrupt | Write `manifest.error.json` with the exception, exit code 3. The TUI must validate manifests on write so this is "should never happen". |
| `manifest["state"] != "Pending"` at start | Exit code 4 without modifying the manifest. Prevents double-spawn. |
| Orchestrator argv malformed | Not validated by the runner. `subprocess.Popen` raises; we catch, write the exception to `run.log`, set state `Failed`, exit_code `-1`. |
| `setsid` fails | Treated as fatal pre-flight. Runner writes `[runner] could not detach` to `run.log`, sets state `Failed`, exit_code `-2`, exits. The TUI must surface this. |

---

## 8. The TUI

### Startup sequence

When the user runs `dispatch`:

1. Capture `Path.cwd()` once and store on the `App` — this is the
   "launch-time CWD" that `Csv` Job paths will be relative to. Never
   re-read `cwd()` mid-session; the user may navigate the filesystem
   inside the TUI but their initial directory is sticky for output
   purposes.
2. Read `/ads_storage/<user>/.dispatch/config.json`. If absent, the
   user hasn't run `install.sh`; show a one-screen "run `install.sh`"
   message and exit.
3. Compare `installed_version` against the deployed `VERSION`; show a
   non-blocking warning banner if older.
4. Pre-flight Kerberos via `klist -s`. If absent, dim the launch
   button and show "Kerberos ticket missing — press K to kinit". If
   present, parse TTL and start a 60s refresh timer.
5. Scan `/ads_storage/<user>/.dispatch/jobs/` once to populate the
   dashboard, then re-scan every 2 seconds via a background task.
6. Render the Dashboard tab.

Crash-resistance: any step 2–5 failure logs to `~/.dispatch/dispatch.log`
and proceeds with degraded UI rather than blocking the user.

### Navigation

Three top-level tabs plus a modal-style "New Job" wizard:

- **Dashboard** — Active Jobs (max 2) and Recently Finished (last 7 days).
- **History** — Jobs older than 7 days. Searchable by table name and date.
- **Browser** — Impala metadata: list/describe/drop tables in a schema.

Persistent header shows `Kerberos: <ttl>` and a "deployed version vs.
installed version" warning when they differ.

### Dashboard wireframe

```
┌─ Dispatch ─────────────────────────────────── Kerberos: 7h 32m ─┐
│  Active Jobs (1 / 2)                                            │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ ID            Source      Destination     State    Elapsed │ │
│  │ 2026…_a1b2c3  SqlFile     Table + Csv     Running     3m   │ │
│  └────────────────────────────────────────────────────────────┘ │
│  Recently Finished                                              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ 2026…_99fa01  SqlTemplate Table         Succeeded     42m   │ │
│  │ 2026…_77bd02  SqlFile     Csv           Failed        18s   │ │
│  └────────────────────────────────────────────────────────────┘ │
│ [N]ew Job [A]ttach [C]ancel [V]iew Logs [H]istory [B]rowse [Q]  │
└─────────────────────────────────────────────────────────────────┘
```

### New Job wireframe

```
┌─ New Job ──────────────────────────────────── Kerberos: 7h 32m ─┐
│  SQL File:     [foo.sql                                      ▼] │
│                Auto-detected: SqlFile (no {date_*} markers)     │
│                [E]dit in $EDITOR    [Shift-N] New blank         │
│                                                                 │
│  Source:       (•) SqlFile  ( ) SqlTemplate  ( ) ExistingTable  │
│  Destination:  ( ) Table    (•) Csv          ( ) Table + Csv    │
│                                                                 │
│  Schema:       [aa_enc                                     ] │
│  Table name:   [q3_settle_load                                ] │
│  Email:        [team@mastercard.com                           ] │
│  Subject:      [Q3 settlement load                            ] │
│                                                                 │
│  Date range:   (hidden — only shown for SqlTemplate)            │
│                                                                 │
│  [P]review SQL  [L]aunch  [Esc] Back                            │
└─────────────────────────────────────────────────────────────────┘
```

Behaviour:

- The SQL File picker defaults to `*.sql` in the launch-time `$PWD`.
- Source is **auto-detected** from the file: presence of both
  `{date_inicio}` and `{date_fim}` → `SqlTemplate`; absence → `SqlFile`. A
  mismatch with the user's explicit pick produces a soft warning with a
  one-key flip.
- Hard-refused launches: missing Kerberos ticket; ticket TTL < 5 minutes;
  user already has 2 Running Jobs; illegal `(Source, Destination)` cell;
  `SqlTemplate` source without both placeholders.
- Soft warnings: ticket TTL < 1 hour; CWD not writable for `Csv`
  destinations.
- `[P]review SQL` shows the wrapped DDL (for `Table` destinations) or the
  resolved monthly partitions (for `SqlTemplate`).

### Job Detail wireframe (the reattached live tail)

```
┌─ Job 20260509T164500Z_a1b2c3 ──────────────── Kerberos: 7h 28m ─┐
│  Source: SqlFile (foo.sql)     Destination: Table + Csv         │
│  State:  Running               Started: 16:45:02 (3m 14s ago)   │
│  Table:  aa_enc.q3_settle_load                               │
│  CSV:    /home/e123456/projects/q3/q3_settle_load.csv           │
│  ┌─ run.log (live) ───────────────────────────────────────────┐ │
│  │ 16:45:02 INFO  Executing query on adhoc_fast               │ │
│  │ 16:45:35 WARN  adhoc_fast returned QUEUE_FULL              │ │
│  │ 16:45:35 INFO  Trying acs_small                            │ │
│  │ 16:46:08 INFO  Query accepted on acs_small                 │ │
│  └─────────────────────────────────────────────────────────────┘ │
│ [C]ancel Job  [B]ack                                            │
└─────────────────────────────────────────────────────────────────┘
```

Implementation: `RichLog` widget bound to a tailing `open(run.log,
"rb")`-style coroutine. Bounded memory regardless of total log size.

### Browser wireframe

```
┌─ Browse Impala Metadata ────────────────────── Kerberos: 7h 28m ┐
│  Schema: [aa_enc             ▼]   Filter: [your_*          ] │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Table                          Updated      Size  Rows     │ │
│  │ your_test_table                2026-05-08   ?     ?        │ │
│  │ your_q3_load                   2026-05-07   ?     ?        │ │
│  └────────────────────────────────────────────────────────────┘ │
│ [Enter] Describe  [E]xport to CSV  [D]rop  [B]ack               │
└─────────────────────────────────────────────────────────────────┘
```

`Size`/`Rows` populate lazily via `SHOW TABLE STATS` only when a row is
selected, to avoid hammering the cluster on schema browse.

---

## 9. Install flow (`install.sh`)

Per-user, idempotent, re-runnable for upgrades:

1. **Verify environment**: Python 3.10 at the existing
   `/sys_apps_01/python/python310/bin/python3.10`; `klist` and
   `impala-shell` present; `/ads_storage/$USER/` writable.
2. **Create venv** at `/ads_storage/$USER/.dispatch/venv/`.
3. **Install vendored wheels**:
   `pip install --no-index --find-links=/ads_storage/dispatch/vendor/ \
   -r /ads_storage/dispatch/requirements.txt`
4. **Install the `dispatch` shortcut**: symlink
   `~/.local/bin/dispatch → /ads_storage/$USER/.dispatch/venv/bin/dispatch`.
   If `~/.local/bin` is not on `$PATH`, append
   `alias dispatch='...'` to `~/.bashrc` (and `~/.zshrc` if it exists),
   detected by the user's actual `$SHELL`.
5. **Create skeleton**: `~/.dispatch/jobs/`.
6. **First-run only**: prompt for email; write `~/.dispatch/config.json`.
   No schema prompt — schema changes per Job.
7. **Record installed version**: write `~/.dispatch/installed_version` from
   the repo's `VERSION` file.
8. **Print "open a new shell and run `dispatch`"**.

Re-run = upgrade in place. `~/.dispatch/jobs/` and `config.json` are never
touched on re-run.

---

## 10. Mock layer

See [ADR-0004](./adr/0004-mock-layer-for-offline-dev.md). To enter dev mode
on a non-Hadoop machine:

```bash
source mocks/dev-env.sh   # exports DISPATCH_DATA_ROOT, prepends mocks/bin to PATH,
                          # sets MAILHOST, starts SMTP catcher, prints banner
dispatch
```

Scenarios live in `mocks/scenarios/<name>.json`; switch with
`export DISPATCH_MOCK_SCENARIO=memory_exceeded`. Captured emails appear as
`.eml` files in `mocks/sent_emails/` (gitignored).

---

## 11. Migration

At v1.0 ship:

- **Hard delete** `run_query.ps1` and `run_query_engine.bat`.
- **Rewrite** `README.md` to describe Dispatch (the existing README is
  Windows-GUI-centric).
- **Rename deploy path** on the edge node from
  `/ads_storage/hadoop_query_launcher/` to `/ads_storage/dispatch/`. The
  hardcoded path in `Query_Impala_Parametrized.export_table_to_csv` is
  externalised to `DISPATCH_SCR_DIR` per ADR-0005 as part of the same
  change.
- **No coexistence period.** Existing PowerShell users move directly to
  `dispatch` on the edge node.

---

## 12. Implementation milestones

Even though every primitive is in v1.0 (no "phase 2"), the PR sequence
matters for safe, reviewable, mock-validated progress.

| # | PR | Depends on | Lands |
|---|---|---|---|
| 1 | `mocks/` substrate **+ MAILHOST bootstrap exception** | — | ADR-0004 in code; CI can run end-to-end against fakes. Includes a single one-line `scr/Query_Impala_Parametrized.send_email` change to read `MAILHOST` from the env var (default = current hardcoded `"mailhost.mclocal.int"`). Without this, the mock SMTP catcher cannot intercept the orchestrators' emails. |
| 2 | `dispatch/` package skeleton + `pyproject.toml` + `requirements.txt` + `vendor/` | 1 | `python -m dispatch` opens a non-empty Textual screen; installs cleanly via `pip install -e .` |
| 3 | Manifest schema + runner script + `dispatch/process.py` | 2 | ADR-0001 in code; runner can be smoke-tested against mock scenarios |
| 4 | New Job wizard (Source × Destination logic, `$EDITOR` shell-out, template auto-detect, Kerberos pre-flight) | 3 | First end-to-end "I can launch a Job" PR |
| 5 | Dashboard (active/finished tables, attach to live tail, cancel) | 3 | First "I can supervise a Job" PR |
| 6 | History view with 7-day collapse | 5 | Closes the Job-lifecycle category |
| 7 | Impala metadata browser (`SHOW TABLES` / `DESCRIBE` / `DROP`) | 2 | Browser tab functional |
| 8 | SQL preview + monthly partition preview | 4 | Pre-launch trust-builder primitives |
| 9 | `install.sh` + `VERSION` file + version-mismatch banner | 2 | Distribution path |
| 10 | `scr/` de-duplication + `_common.py` + remaining path externalisation | 1 | ADR-0005 in code |
| 11 | Hard delete legacy GUI; README rewrite | 5, 6, 7, 8, 9 | v1.0 ship |

PRs 1–3 are blocking dependencies for everything after. Beyond that,
PRs 4–9 can be parallelised by different contributors. PR 10 cannot
land before PR 1 (ADR-0005 requires the mock layer). PR 11 is the
last; it gates on every user-facing capability being live.

### 12.1 Per-PR definition of done

Every PR must satisfy this baseline:

- [ ] All listed deliverables exist and pass `python3.10 -m py_compile`.
- [ ] `flake8 . --max-line-length=120` clean on changed files (per `AGENTS.md`).
- [ ] `pylint <changed-files> --disable=C0114,C0115,C0116,C0103,W0718 --max-line-length=120` clean (per `AGENTS.md`).
- [ ] PR description includes the validation table or screenshot called out in the PR-specific row below.
- [ ] One commit per logical change; no force-pushes.
- [ ] Cross-references to relevant ADRs in the PR body.
- [ ] Opened as draft until reviewed.

PR-specific extras:

| PR | Validation artefact required in PR body |
|---|---|
| 1 | A 6×3 table (six scenarios × three orchestrators) showing `✓` or a one-line note for each cell, plus a directory listing of `mocks/sent_emails/` showing captured `.eml` files. |
| 2 | A screenshot of `python -m dispatch` rendering its initial Textual screen on a Linux VM. Plus `pip install -e .` clean output. |
| 3 | Manifest reaches `Succeeded` / `Failed` / `Cancelled` for each scenario; demonstrate that `kill -HUP` of the parent shell does not affect the runner. |
| 4 | Source × Destination matrix exhaustively reachable in the wizard (one screenshot per legal cell); auto-detect tested with both `{date_*}`-bearing and bare SQL files. |
| 5 | Live-tail latency screenshot under 1s; demonstrate that cancel terminates the orchestrator's process group (`ps -ef \| grep impala-shell` empty after cancel). |
| 6 | Screenshot of a Job at day 6 still in dashboard, day 8 in history. (Use file mtime fudging if needed.) |
| 7 | Screenshot of `SHOW TABLES` and `DESCRIBE` rendering against the mock. |
| 8 | Screenshot of the auto-generated `DROP TABLE / CREATE TABLE STORED AS PARQUET LOCATION ... AS` wrapper for a `Table` Job; screenshot of resolved monthly partitions for a `SqlTemplate` Job. |
| 9 | `install.sh` re-run preserves existing config and `jobs/`; demonstrate via diff. |
| 10 | Side-by-side log captures from pre-change and post-change orchestrator runs against all six `mocks/scenarios/` (per ADR-0005). |
| 11 | `git diff --stat` showing only the deletions (`run_query.ps1`, `run_query_engine.bat`) plus the README rewrite. |

### 12.2 Anti-patterns (do not merge code that does any of these)

- **Spawning subprocesses outside `dispatch/process.py`.** Single
  sanctioned entry point per ADR-0001 and ADR-0002.
- **Spawning an orchestrator directly from the TUI.** Always go through
  the runner. Even in tests.
- **Calling `subprocess.run(...)` from a Textual callback.** Use
  `asyncio.create_subprocess_exec` or `loop.run_in_executor` via
  `dispatch.process`.
- **Backing Jobs with `tmux` or `screen`.** Use `nohup` + `setsid`
  (ADR-0001).
- **Gzipping CSV output.** ADR-0003 forbids it.
- **Storing CSV under `~/.dispatch/`.** They go to the user's
  launch-time CWD (ADR-0003).
- **Modifying `scr/` outside the rules in ADR-0005.** PR #1 has the
  documented bootstrap exception (`MAILHOST`); PR #10 does the larger
  de-duplication. Anything in between requires its own ADR.
- **Installing third-party deps into `/sys_apps_01/python/python310/`**
  (the orchestrators' interpreter). All TUI deps live in the per-user
  venv only.
- **Reading passwords inside the TUI.** Use `App.suspend()` and let
  `kinit` own the terminal.
- **Retrying a fatal classified error in the runner.** The orchestrators
  already classify and short-circuit fatals; the runner runs each
  orchestrator exactly once.
- **Assuming `$HOME` and `/ads_storage/<user>/` are the same volume.**
  They aren't always; the data dir is anchored at
  `/ads_storage/<user>/.dispatch/` for a reason.
- **Blocking the Textual event loop on filesystem I/O during dashboard
  refresh.** Manifest reads are cheap individually but should be
  backgrounded if scanning more than ~50 jobs.

---

## 13. Quick reference for implementers

### 13.1 Exact `argv` emitted by the orchestrators today

Verified by reading the source. Mocks and the runner must accept these
unchanged. The fake `impala-shell` should be permissive about argument
order and unknown flags (the orchestrators may add flags later).

**`Query_Impala_Parametrized.run_on_impala`** (file:
`scr/Query_Impala_Parametrized.py`, line ~248):

```
impala-shell -k -i dw.prod.impala.mastercard.int:21000 --ssl
             --delimited --print_header --output_delimiter=|
             -q "<query>"
```

`<query>` = `set request_pool=<pool>; <user_sql>`. Extract pool with
`re.match(r'\s*set\s+request_pool\s*=\s*(\w+)\s*;', query, re.IGNORECASE)`.

**`download_to_csv.run_export_on_impala`** (file:
`scr/download_to_csv.py`, line ~40):

```
impala-shell -k -i dw.prod.impala.mastercard.int:21000 --ssl
             --delimited --print_header --output_delimiter=,
             -q "<query>" -o <output_file>
```

`<query>` = `set request_pool=<pool>; set mem_limit=1000g; <user_sql>`.

`monthly_query_processor.py` does not call `impala-shell` directly; it
imports `run_on_impala` from `Query_Impala_Parametrized`, which means
testing it requires the importing module to be on `PYTHONPATH`
(typically by running from `scr/`).

### 13.2 Manifest's `orchestrator_calls` for each legal cell

| Cell | Calls (in order) |
|---|---|
| `(SqlFile, Table)` | `Query_Impala_Parametrized.py --sql-file <jobdir>/job.sql --table-name <s.t> --to-email <email> --subject <subj> --user <user> --session-folder <jobdir>` |
| `(SqlFile, Csv)` | `download_to_csv.py --query-file <jobdir>/job.sql --output-file <pwd>/<name>.csv` |
| `(SqlFile, Table+Csv)` | (1) `Query_Impala_Parametrized.py …` (no `--download`); (2) `download_to_csv.py --table-name <s.t> --output-file <pwd>/<name>.csv` |
| `(SqlTemplate, Table)` | `monthly_query_processor.py --sql-file <jobdir>/job.sql --schema <s> --table-name <t> --start-date <m/d/y> --end-date <m/d/y> --user <user> --to-email <email> --subject <subj>` |
| `(ExistingTable, Csv)` | `download_to_csv.py --table-name <s.t> --output-file <pwd>/<name>.csv` |

Note: the orchestrators' date format is `MM/DD/YYYY` (American); the
TUI must convert from a YYYY-MM-DD picker to that string before
populating `argv`.

### 13.3 Hardcoded values worth knowing

- Impala host: `dw.prod.impala.mastercard.int:21000`.
- Resource pool order: `["adhoc_fast", "acs_small", "adhoc_small",
  "acs_large", "adhoc"]` in `Query_Impala_Parametrized.py` and
  `monthly_query_processor.py`; `["adhoc_fast", "adhoc_small",
  "adhoc"]` in `download_to_csv.py`. (Yes, `download_to_csv.py` uses a
  shorter list. This is one of the de-duplications PR #10 fixes.)
- Retry interval after a full cycle: 30 seconds.
- `monthly_query_processor.py` halts after 10 retry cycles per step
  (~5 minutes wall-clock per step minimum); the other two retry
  forever.
- Sender email: `AutoQueryExecution_Analytics@mastercard.com`.
- HDFS table location pattern (auto-generated wrapper): `/das/<schema-prefix>/enc/<user>/<table>` where `<schema-prefix>` is the part of `<schema>` before the first underscore (e.g. `aa_enc` → `aa`).

---

## 14. Known risks

| Risk | Mitigation |
|---|---|
| Textual on a corporate jumphost may glitch on terminal-feature negotiation | First Edge Node smoke-test at PR 2; fall back to `urwid` is documented in ADR-0002 if needed |
| Kerberos `klist` not on `$PATH` on some hardened nodes | Graceful degradation: pre-flight skipped, orchestrator's `AUTH_ERROR` path catches it; warning written to `~/.dispatch/dispatch.log` |
| User runs `dispatch` from a CWD they can't write to | Soft warning at New Job time for `Csv` destinations; orchestrator surfaces filesystem error if user proceeds |
| Concurrent re-installs by the same user race on `venv/` | `install.sh` takes a lockfile at `~/.dispatch/install.lock` |
| `scr/` modifications regress production behaviour despite mock validation | ADR-0005's required process — two reviewers, one with prod-run experience, side-by-side log captures |
| Mock layer drifts from real `impala-shell` argv | Treated as integration bug; argv contract documented in `mocks/bin/impala-shell` source comment, paired with the orchestrators' actual invocations |

---

## 15. Out of scope for v1.0

Recorded so they don't get re-litigated:

- Auto-queueing of a 3rd Job when 2 slots are full (hard refuse only).
- Cross-user Job visibility.
- Cluster / queue health dashboard.
- Mid-Job Kerberos auto-renewal.
- A staging-cluster integration test environment.
- Resume-from-failure for partially-completed `Table + Csv` Jobs.
