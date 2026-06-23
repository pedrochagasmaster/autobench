# Plan 017: Design spike — productize SQL ingestion (CLI/config surface, driver choice, credential handling)

> **Executor instructions**: This is a **design/spike plan**, not a build plan.
> The deliverable is a design document plus a throwaway prototype validation —
> NOT a shipped feature. Follow the steps, answer every open question with
> evidence, and write the design doc. If anything in the "STOP conditions"
> section occurs, stop and report. When done, update the status row for this
> plan in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/data_loader.py utils/config_manager.py benchmark.py config/template.yaml`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: M (spike); the build it specifies is a separate, later plan
- **Risk**: LOW (spike itself touches no product code)
- **Depends on**: plans/013-dependency-pinning-python-310.md (decides pypyodbc's removal from default deps — the spike must account for it)
- **Category**: direction
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

The engine already implements SQL ingestion — `DataLoader.load_from_sql_query` / `load_from_sql_table` exist, are unit-tested (against sqlite mocks), and the executive-facing docs describe "CSV or SQL" as a product capability — but **no CLI flag, TUI control, or config schema reaches it**. Analysts whose source of truth is a warehouse export CSVs by hand. Before building the surface, three design decisions need evidence: driver choice (pypyodbc is near-abandoned; plan 013 removes it from default requirements), credential handling (plan 008 had to add redaction because credentials currently live in YAML), and query safety (the audit flagged that query files execute arbitrary SQL — any productized surface must constrain this). This spike produces the design the build plan will follow, plus a list of maintainer decisions.

## Current state

- `core/data_loader.py:191-194` — dormant dispatch (only reachable if a hand-built args namespace has these attributes; no parser defines them):

```python
elif hasattr(args, 'sql_query') and args.sql_query:
    return self.load_from_sql_query(args.sql_query)
elif hasattr(args, 'sql_table') and args.sql_table:
    return self.load_from_sql_table(args.sql_table)
```

- `core/data_loader.py:536-574` — `load_from_sql_query` reads an entire query file and passes it to `pd.read_sql(query, connection)` — no statement allowlist, no multi-statement rejection (audit SECURITY-02).
- `core/data_loader.py:576-613` — `load_from_sql_table` is safer: identifier-validated (`_validate_sql_identifier`, regex `[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][...]*)?`) `SELECT * FROM <table>`.
- `utils/config_manager.py:444-475` — `get_sql_connection()` (def at line 444) lazily imports `pypyodbc`, connects via `connection_string` or `uid`/`pwd` from `self.sql_config` (populated from a user YAML `sql:` block, loaded around line 351; **no** `sql:` block exists in `config/template.yaml`).
- `benchmark.py` — `--csv` is required on both subcommands; no SQL flags.
- `tests/test_data_loader_sql.py` — exercises both loaders with sqlite-backed mocks (not pypyodbc).
- Plan 008 (if landed) redacts `sql.*` secrets from audit packages; plan 013 (if landed) removes `pypyodbc` from `requirements.txt`, leaving the loaders functional only when a driver is user-installed.
- Stated product intent: `docs/EXECUTIVE_PRESENTATION_SCRIPT.md` and `docs/CORE_TECHNICAL_DOC.md` both describe SQL as an ingestion option.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Existing SQL tests | `py -m pytest tests/test_data_loader_sql.py -q` | all pass |
| Prototype sanity | `py -m pytest tests/ -q` | all pass (spike must not break anything) |
| Driver availability probe | `py -c "import pyodbc"` / `py -c "import pypyodbc"` | informational — record which import succeeds |

## Scope

**In scope** (files the spike may create):
- `docs/sql_ingestion_design.md` (the deliverable)
- A throwaway prototype under `outputs/` or a scratch branch — anything needed to answer the questions below; deleted or clearly marked before finishing.

**Out of scope** (do NOT modify):
- ALL product code: `core/data_loader.py`, `utils/config_manager.py`, `benchmark.py`, `tui_app.py`, `config/template.yaml`, `requirements*.txt`. The spike answers questions; the follow-up build plan changes code.
- TUI design beyond a one-paragraph recommendation (defer-or-not) in the doc.

## Git workflow

- Branch: `advisor/017-sql-spike`
- Commit message style: `docs: add SQL ingestion design`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Driver decision with evidence

Investigate and record in the design doc:
- `pypyodbc` health: last release date, maintenance status, wheel availability for Python 3.10/3.12 on Windows and Linux (check PyPI; the repo's `deploy_and_install.ps1` already special-cases it for lacking wheels).
- `pyodbc` as the replacement candidate: wheel availability, API compatibility with the two call sites (`connect(connection_string)` and `pd.read_sql(query, connection)` — both work identically on pyodbc).
- Whether `pd.read_sql` on a raw DBAPI connection emits pandas warnings on modern pandas (it warns for non-SQLAlchemy connections — verify on the pinned pandas version and record whether SQLAlchemy should be the recommended path instead).

**Verify**: design doc section "Driver" states a recommendation with the evidence above.

### Step 2: Credential-handling design

Design the `sql:` config schema. Constraints from this repo's reality:
- Credentials must NOT be stored in YAML configs that flow into audit packages (plan 008 redacts, but the design should avoid the hazard): recommend environment-variable indirection (e.g. `connection_string_env: BENCH_SQL_DSN`) and/or Windows-integrated auth (`trusted_connection=yes`), with plain `connection_string` supported but documented as discouraged.
- Sketch the schema in the doc, e.g.:

```yaml
sql:
  connection_string_env: BENCH_SQL_DSN   # preferred
  # connection_string: "..."             # discouraged; redacted in audit packages
  query_file: queries/monthly.sql        # or table: benchmark_data
```

- Define precedence vs `--csv` (mutually exclusive? `--csv` wins? error on both?). Recommend: mutually exclusive with a clear argparse error.

**Verify**: doc section "Configuration & credentials" contains the schema and precedence rule.

### Step 3: Query-safety design

Decide and document constraints for `load_from_sql_query` when exposed (today it executes arbitrary SQL — audit SECURITY-02):
- Recommend: single-statement `SELECT`-only validation (reject `;` beyond trailing, reject DML/DDL keywords at statement start), with read-only-connection guidance in docs; `load_from_sql_table` stays identifier-validated as-is.
- Document the residual risk honestly (keyword filters are not a security boundary; the real boundary is a read-only DB role).

**Verify**: doc section "Query safety" with the validation rules and their limits.

### Step 4: Prototype the end-to-end path

Without touching product code, prove the dormant path works: in a scratch script (e.g. `outputs/sql_spike.py`, gitignored), build a `SimpleNamespace` with `sql_query`/`sql_table` attributes and a `ConfigManager` subclass that overrides `get_sql_connection()` to return a local sqlite connection — this is exactly the `SqliteConfig` pattern in `tests/test_data_loader_sql.py` (read it first and copy its shape). Then run `DataLoader.load_data(args)` through to a real `execute_share_run` on the loaded frame. Record in the doc: what worked, what needed hand-holding (e.g. column normalization, required columns), and the exact integration points the build plan must touch (expected: `benchmark.py` parser + `--csv` requiredness, `AnalysisRunRequest` fields, `core/analysis_run.py` `prepare_run_data`, `config/template.yaml`, TUI source picker deferred).

**Verify**: `py -m pytest tests/ -q` → all pass (nothing product-side changed); the doc's "Integration points" section lists exact files/functions with line references.

### Step 5: Write the design doc and the open-questions list

`docs/sql_ingestion_design.md` must contain: Driver recommendation; config schema + credential policy; query-safety rules; CLI surface (`--sql-query FILE` / `--sql-table NAME`, `--csv` becomes optional-but-exclusive); integration-point inventory; test strategy (extend `tests/test_data_loader_sql.py`; one gate case is NOT recommended — gate must stay dependency-free); packaging (driver as optional extra `requirements-sql.txt`, per plan 013's note); and an **Open questions for the maintainer** section, at minimum:
1. Is there a real production SQL user today (the `deploy_and_install.ps1` pypyodbc handling suggests maybe)? Which DBMS?
2. pyodbc optional-extra vs SQLAlchemy dependency?
3. Should TUI get a source picker now or after CLI proves demand?
4. Is `load_from_sql_query` (arbitrary file) needed at all, or is `--sql-table` + a documented view-based workflow enough? (Strong simplification if yes.)

**Verify**: doc exists, all sections present, every claim carries evidence (version numbers, line refs, prototype results).

## Test plan

None — spike. The prototype's pass/fail observations go in the doc.

## Done criteria

- [ ] `docs/sql_ingestion_design.md` exists with all seven content areas from Step 5 (driver, credentials, query safety, CLI surface, integration points, test strategy, packaging) + open questions
- [ ] Driver recommendation backed by release/wheel evidence
- [ ] Prototype result recorded (worked / what broke), product code untouched (`git status` shows only the doc and scratch files)
- [ ] `py -m pytest tests/ -q` exits 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- The prototype reveals the dormant SQL path is fundamentally broken (e.g. `load_data(args)` cannot reach SQL without `csv` set first, or normalization mangles SQL results) in a way that invalidates "the engine already implements it" — document the breakage and stop; the design premise changes.
- Evidence of a live production SQL consumer (credentials/configs referenced in deploy scripts) — record it and stop before recommending removal of anything.

## Maintenance notes

- The follow-up **build plan** should be written only after the maintainer answers the open questions — especially question 4, which halves the scope if "table-only" is acceptable.
- Coordinate with plan 013: if pypyodbc is already removed from defaults, the build plan ships the driver as an optional extra; the design doc should state the install UX either way.
