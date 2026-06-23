# Plan 020: Productize SQL ingestion (`--sql-table` + `--sql-query`)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 8bd1c8b..HEAD -- core/data_loader.py utils/config_manager.py benchmark.py core/contracts.py core/analysis_run.py utils/validators.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: L
- **Risk**: MEDIUM
- **Depends on**: 013 (pyodbc-as-extra direction), 017 (design spike — read `docs/sql_ingestion_design.md` fully first), 012 (TUI parity audit), 016/019 (request-field wiring patterns)
- **Category**: direction (maintainer selected full scope 2026-06-11: both `--sql-table` and `--sql-query`)
- **Planned at**: integration tip `8bd1c8b`, 2026-06-11

## Why this matters

The engine already loads from SQL (`DataLoader.load_from_sql_query`, `load_from_sql_table`, dispatched from `load_data`), but no CLI flag, config block, or doc exposes it — the path is dormant and dead-weight. The spike (plan 017) proved the dormant path works end-to-end with zero product changes (sqlite prototype → full share run, `fully_compliant`). The maintainer confirmed the full scope: ship both table/view ingestion **and** validated query-file ingestion, with safe credential handling. This plan is the build.

**Authoritative design**: `docs/sql_ingestion_design.md` (spike 017). This plan operationalizes it; where this plan and the spike doc disagree, STOP and report.

## Current state

(Line refs from integration tip `8bd1c8b`; re-verify with the drift check.)

- `core/data_loader.py` — `load_data` dispatches `csv` → `sql_query` → `sql_table` in that order (CSV silently wins today). `load_from_sql_query` reads the whole file and passes it to `pd.read_sql` with **no validation**. `load_from_sql_table` validates identifiers via `_validate_sql_identifier` (regex `[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?`) and emits `SELECT * FROM {safe_name}` only.
- `utils/config_manager.py` — `load_config` already loads a top-level `sql:` block into `self.sql_config`; `get_sql_connection` lazily imports **`pypyodbc`** (removed from `requirements.txt` by plan 013 — the import is now broken unless the user happens to have it) and raises if `sql_config` is empty.
- `config/template.yaml` — no `sql:` section.
- `benchmark.py` — `add_common_run_flags` declares `--csv` with `required=True`; no SQL flags.
- `core/contracts.py` — `AnalysisRunRequest` has `csv` and `df`/`prepared_dataset` fields, no `sql_query`/`sql_table`. `from_widget_values` (plan 012) rejects unknown fields; `tui_app.py` keeps a `TUI_UNSUPPORTED_FIELDS` set whose parity test fails if a new request field is left unclassified.
- `core/audit_package.py` — `_redact_secrets` masks `connection_string`, `pwd`, `password`, `uid`, `user`, `token`, `secret`, `api_key` (plan 008). `connection_string_env` is deliberately **not** in that set (the env-var *name* is not a secret).
- `pyproject.toml` exists (plan 014) — use `[project.optional-dependencies]` for the `sql` extra in addition to a `requirements-sql.txt` (repo install style is requirements files).
- `deploy_and_install.ps1` — verify plan 013 removed the pypyodbc source-download special-case; if any remnant exists, remove it here.
- Existing tests: `tests/test_data_loader_sql.py` (4 tests, sqlite mocks); integration pattern in `tests/test_analysis_run_integration.py`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0, 18 cases (no SQL case added) |
| Lint | `py -m ruff check .` | clean |
| Typecheck (local-only) | `py -m mypy core/ utils/` | no NEW errors vs baseline (~100 pre-existing) |
| CLI parse smoke | `py benchmark.py share --help` | shows the three mutually exclusive source flags |

## Scope

**In scope**:
- `utils/config_manager.py` — `pyodbc` import, `connection_string_env` resolution, connection-string build order
- `core/data_loader.py` — `_validate_sql_query_file()`, exclusivity assertion in `load_data`
- `benchmark.py` — mutually exclusive `--csv` / `--sql-query` / `--sql-table` group (share + rate)
- `core/contracts.py` — `sql_query: Optional[str]`, `sql_table: Optional[str]` on `AnalysisRunRequest`
- `core/analysis_run.py` — wire sql fields into args namespace / `prepare_run_data`; metadata `input_source`
- `tui_app.py` — classify both new fields in `TUI_UNSUPPORTED_FIELDS` (TUI picker explicitly deferred)
- `utils/validators.py` — `sql:` block schema validation
- `config/template.yaml` — commented `sql:` section
- `core/audit_package.py` — belt-and-suspenders: redact values that *look like* ODBC connection strings in metadata snapshots
- `requirements-sql.txt` (new) + `pyproject.toml` `[project.optional-dependencies] sql = ["pyodbc>=5.3,<6"]`
- Tests (see Test plan); docs (`README.md`, `AGENTS.md`, `SETUP.md`, `docs/CORE_TECHNICAL_DOC.md`)

**Out of scope**:
- TUI source picker (spike: defer until CLI proves demand)
- SQLAlchemy (spike: raw DBAPI via `pd.read_sql` works warning-free on pandas 2.3.3)
- Gate SQL case (gate stays dependency-free and portable)
- Connection pooling, multi-dialect support, async loading

## Git workflow

- Branch: `advisor/020-sql-ingestion`
- Commit message style: `feat: expose SQL ingestion via --sql-table/--sql-query with pyodbc extra`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Driver swap + optional extra

- `utils/config_manager.py` `get_sql_connection`: `import pypyodbc` → `import pyodbc`; on `ImportError` raise with an actionable message: `"SQL ingestion requires the optional pyodbc driver: pip install -r requirements-sql.txt (plus an OS-level ODBC driver)"`.
- Create `requirements-sql.txt` containing `pyodbc>=5.3,<6` with a two-line header comment (optional extra, OS ODBC prerequisites).
- `pyproject.toml`: add `[project.optional-dependencies]` with `sql = ["pyodbc>=5.3,<6"]`.
- Verify `deploy_and_install.ps1` has no pypyodbc remnant; remove if found.

**Verify**: `py -m pytest tests/test_data_loader_sql.py -q` → pass (sqlite mocks, no pyodbc needed); `py -m ruff check .` clean.

### Step 2: Credential handling in `get_sql_connection`

Implement the spike's resolution order:

1. `connection_string_env` set → `os.environ[name]`; **fail fast** with a clear error if the env var is unset (name the var in the message, never echo a partial value).
2. Else `connection_string` set → use directly, log a WARNING that inline DSNs are discouraged (redacted in audit packages, but keep secrets out of shareable YAML).
3. Else `server` + `database` → build `Driver={...};Server=...;Database=...`; append `Trusted_Connection=yes` when `trusted_connection: true`; otherwise require env-based credentials — do **not** accept plain `pwd` in the built string (raise with guidance to use `connection_string_env`).

- `utils/validators.py`: validate the `sql:` block — unknown keys rejected, `query_file`/`table` mutually exclusive in config, types checked.
- `config/template.yaml`: add the commented `sql:` section from the spike doc §2 (env-var form first, trusted-connection and discouraged forms commented).

**Verify**: new unit tests (Step 6) for all three resolution branches pass; `py benchmark.py config validate config/template.yaml` → valid.

### Step 3: Query-file validation

In `core/data_loader.py`, add `_validate_sql_query_file(sql_text: str) -> None` applied in `load_from_sql_query` **before** `pd.read_sql`:

1. Strip leading/trailing whitespace and `--` line comments; **reject** files containing `/* */` block comments (simpler than parsing them).
2. Reject multiple statements: any `;` followed by non-whitespace.
3. Require the statement to start with `SELECT` or `WITH` (case-insensitive, after stripping). (`WITH` covers CTEs; the spike lists `SELECT`-only — CTEs are standard read-only practice; if you prefer strict spike fidelity, `SELECT`-only and note it. Either way, document the choice.)
4. Reject leading keywords: `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `EXEC`, `EXECUTE`, `MERGE`, `GRANT`, `REVOKE`, `CALL`.

Raise `ValueError` with the failed rule named. Do **not** change `load_from_sql_table` identifier validation; document views as the preferred abstraction.

Also add an exclusivity assertion at the top of `load_data`: if more than one of `csv` / `sql_query` / `sql_table` is set on the args object, raise `ValueError` (defense-in-depth behind the argparse group).

**Verify**: unit accept/reject matrix passes (Step 6).

### Step 4: CLI + request contract wiring

- `benchmark.py` `add_common_run_flags`: replace `--csv required=True` with an argparse **mutually exclusive group, required=True**, containing `--csv PATH`, `--sql-query PATH`, `--sql-table NAME`. Help text per spike §4. Config-only SQL source (YAML `sql.query_file`/`sql.table` with no CLI source flag) is allowed only when `--config` is given — if no source flag and no config-declared source, argparse errors as today.
- `core/contracts.py`: add `sql_query: Optional[str] = None` and `sql_table: Optional[str] = None` to `AnalysisRunRequest`; wire through `from_namespace` / `to_namespace` so `prepare_run_data` sees them (the spike's prototype confirmed `prepare_run_data` works once the args carry the attrs).
- `core/analysis_run.py`: metadata records `input_source` (`"csv"` / `"sql_query"` / `"sql_table"`) alongside the existing `input_csv` key (keep `input_csv` for back-compat, `None` for SQL runs); the SQL source path/name lands in a new `input_sql` metadata key.
- `tui_app.py`: add `sql_query` and `sql_table` to `TUI_UNSUPPORTED_FIELDS` (plan 012's parity test will fail until you do).

**Verify**: `py benchmark.py share --help` shows the group; `py benchmark.py share --csv a.csv --sql-table t ...` → argparse error "not allowed with"; `py -m pytest tests/test_tui_contracts.py -q` → pass.

### Step 5: Audit-package hardening

In `core/audit_package.py`, extend redaction: any string **value** matching an ODBC connection-string shape (`(?i)(pwd|password|uid)\s*=` inside a `;`-delimited string) is replaced with `***REDACTED***` regardless of its key. Keep `connection_string_env` un-redacted (name only). Add unit tests for both.

**Verify**: `py -m pytest tests/test_audit_package.py -q` → pass.

### Step 6: Tests

| Layer | File | Cases |
|-------|------|-------|
| Unit — query validation | `tests/test_data_loader_sql.py` | accept: plain SELECT, SELECT with trailing `;`, `--`-commented header, (CTE if allowed); reject: INSERT/DROP/EXEC, two statements, block comment, empty file |
| Unit — credentials | `tests/test_config_manager_sql.py` (new) | env-var resolution (monkeypatch `os.environ`), unset env var fails fast, inline string warns, server+database+trusted builds `Trusted_Connection=yes`, server+database without trusted raises, pyodbc-missing import guard message (monkeypatch import) |
| Integration | `tests/test_analysis_run_sql_integration.py` (new) | sqlite in-memory connection (monkeypatch `get_sql_connection`) + `--sql-table`-style request through `execute_share_run` → workbook written, `metadata['input_source'] == 'sql_table'`; same for a query file |
| CLI | extend the existing CLI-parse test module | mutual-exclusion error; `--sql-table` happy parse |
| Audit | `tests/test_audit_package.py` | connection-string-shaped value redacted; `connection_string_env` preserved |
| Gate | — | **no SQL case** |

**Verify**: `py -m pytest tests/ -q` → all pass.

### Step 7: Docs + full verification

- `README.md`: input-sources section (CSV default; SQL optional extra; install line; one example each for table and query file; read-only DB role as the real security boundary).
- `SETUP.md`: ODBC OS prerequisites (Windows ODBC Driver; Linux `unixODBC` + driver).
- `AGENTS.md`: CLI flag table rows for `--sql-query`/`--sql-table`; credential policy one-liner.
- `docs/CORE_TECHNICAL_DOC.md`: short SQL ingestion section referencing `docs/sql_ingestion_design.md`.
- `docs/sql_ingestion_design.md`: update **Status** header to "Implemented by plan 020" and record the §8 answers (maintainer chose full scope incl. query files, 2026-06-11).

**Verify**: `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m ruff check .` all clean; mypy no new errors vs baseline.

## Test plan

See Step 6 — validation matrix, credential branches, sqlite integration, CLI exclusivity, audit redaction.

## Done criteria

- [ ] `--sql-table` and `--sql-query` work end-to-end (sqlite-mocked integration test proves the share path)
- [ ] Query files are SELECT-only validated; table names identifier-validated (unchanged)
- [ ] `connection_string_env` is the documented default; unset env var fails fast; no plain `pwd` accepted in built strings
- [ ] `pyodbc` is an optional extra (`requirements-sql.txt` + pyproject `[sql]`); default install untouched; gate has no SQL dependency
- [ ] `--csv`/`--sql-query`/`--sql-table` mutually exclusive at parse time; `load_data` defends in depth
- [ ] Audit packages never contain resolved connection strings
- [ ] TUI parity test passes with both fields classified unsupported
- [ ] Full suite, gate 18/18, ruff clean, mypy no new errors
- [ ] `plans/README.md` status row updated

## STOP conditions

- `tests/test_data_loader_sql.py` fails at baseline before any change — environment drift; report.
- The argparse mutually exclusive group cannot express "one of three required, but config-declared source also acceptable" without breaking existing `--csv` workflows — report with the parse matrix rather than weakening exclusivity.
- `pd.read_sql` on a raw `pyodbc` connection emits warnings or fails on the CI pandas version — report; do not silently add SQLAlchemy.
- Any test requires a live ODBC driver or network DB — the suite must stay sqlite-mocked; report instead of adding infra dependencies.
- This plan contradicts `docs/sql_ingestion_design.md` on a decision point — report which §.

## Maintenance notes

- Keyword filtering is **not** a security boundary (spike §3): document the read-only DB role requirement prominently; never advertise the validator as injection-proof.
- If a real production DBMS is confirmed later (spike §8 Q1 remains formally unanswered), add a vendor-specific smoke script under `scripts/` — not the gate.
- TUI source picker is the natural follow-up once CLI adoption is observed; mirror `from_widget_values` and reclassify the two fields out of `TUI_UNSUPPORTED_FIELDS`.
