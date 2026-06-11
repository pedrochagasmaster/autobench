# SQL Ingestion Design (Spike 017)

**Status:** Design spike — not implemented.  
**Branch:** `advisor/017-sql-spike`  
**Date:** 2026-06-11  
**Scope:** Productize the dormant SQL loaders behind CLI/config with safe credential handling and driver choice.

---

## Executive summary

The engine already loads data from SQL (`DataLoader.load_from_sql_query`, `load_from_sql_table`, dispatched from `load_data` at lines 191–194), but **no CLI flag, TUI control, or `config/template.yaml` block exposes it**. A throwaway prototype (`outputs/sql_spike.py`, not committed) proved the dormant path loads data and runs a full share analysis when wired through `prepare_run_data` or via `execute_share_run(df=...)`.

**Recommendations:**

| Decision | Recommendation |
|----------|----------------|
| Driver | Replace `pypyodbc` with **`pyodbc`** as an optional extra (`requirements-sql.txt` or `[sql]` extra), aligned with plan 013 |
| Credentials | **Env-var indirection** (`connection_string_env`); plain `connection_string` discouraged; never `uid`/`pwd` in shareable YAML |
| Query surface | **Single-statement `SELECT`-only** validation for query files; real boundary is a read-only DB role |
| CLI | `--sql-query FILE` / `--sql-table NAME`, mutually exclusive with `--csv` |
| TUI | **Defer** until CLI proves demand |
| Gate tests | **Do not** add SQL to gate (keep dependency-free) |

---

## 1. Driver

### Current state

- `utils/config_manager.py:456` lazily imports **`pypyodbc`** and calls `pypyodbc.connect(...)`.
- `requirements.txt:15` lists `pypyodbc>=1.3.6` (comment: "SQL support (optional)").
- Plan **013** removes `pypyodbc` from default `requirements.txt` and notes reintroduction via a maintained ODBC package as an optional extra.

### pypyodbc health (evidence)

| Fact | Source |
|------|--------|
| Latest release **1.3.6**, uploaded **2021-12-23** | [PyPI pypyodbc JSON](https://pypi.org/pypi/pypyodbc/json) — only `sdist`, no wheels |
| Maintainer listed as **"Nobody - volunteers welcome"** | Same PyPI metadata |
| Status **4 - Beta** | PyPI classifiers |
| **No releases in 2024–2025** | Version history ends at 1.3.6 (2021) |

### Wheel availability

| Package | Python 3.10 / 3.12 Windows | Python 3.10 / 3.12 Linux |
|---------|---------------------------|--------------------------|
| **pypyodbc 1.3.6** | **No wheels** — source tarball only | **No wheels** — source tarball only |
| **pyodbc 5.3.0** (2025-10-17) | `win_amd64`, `win32`, `win_arm64` wheels for cp310 and cp312 | `manylinux2014_x86_64`, `musllinux_1_2_x86_64`, aarch64 wheels for cp310 and cp312 |

Repo evidence for pypyodbc wheel pain — `deploy_and_install.ps1:35–66`:

```powershell
# Filter out pypyodbc which doesn't have a wheel and fails with --only-binary
...
$PypyodbcReqs = $AllReqs | Where-Object { $_ -match "^pypyodbc" }
$BinaryReqs = $AllReqs | Where-Object { $_ -notmatch "^pypyodbc" }
...
if ($PypyodbcReqs) {
    Write-Host "Downloading source packages for: $PypyodbcReqs"
    foreach ($req in $PypyodbcReqs) {
        py -m pip download $req --dest $OfflineDir ... --no-deps
    }
}
```

This special-case exists because offline Linux bundles use `--only-binary=:all:` and **pypyodbc cannot satisfy it**.

### pyodbc API compatibility

Call sites today:

1. `pypyodbc.connect(connection_string)` — `config_manager.py:460, 475`
2. `pd.read_sql(query, connection)` — `data_loader.py:563, 596`

pypyodbc's PyPI description states it is **"almost totally same usage as pyodbc"**. `pyodbc.connect(...)` is drop-in for the connect call. `pd.read_sql` accepts any DBAPI-2 connection; unit tests already use **`sqlite3.Connection`** mocks (`tests/test_data_loader_sql.py`), not pypyodbc.

**Build-plan change:** swap `import pypyodbc` → `import pyodbc` in `get_sql_connection`, update error message to reference optional install.

### Local probe (this session)

| Command | Result |
|---------|--------|
| `py -c "import pypyodbc"` | **Success** (installed in dev environment) |
| `py -c "import pyodbc"` | **ModuleNotFoundError** (not in default install — supports optional-extra model) |

### pandas + raw DBAPI connections

Tested on **pandas 2.3.3** with `sqlite3.connect(':memory:')`:

```python
pd.read_sql("SELECT 1 as x", conn)  # no UserWarning captured
```

No pandas warning about non-SQLAlchemy connections was emitted. **Recommendation:** keep `pd.read_sql(query, connection)` on a raw ODBC connection; do **not** add SQLAlchemy as a hard dependency unless maintainers want engine-level features (connection pooling, dialect abstraction). SQLAlchemy is a separate open question (see §7).

### Driver recommendation

**Adopt `pyodbc>=5.3,<6` as an optional dependency; retire `pypyodbc`.**

Rationale: actively maintained (5.3.0, Oct 2025), production/stable, prebuilt wheels on Windows and Linux for CI matrix Python 3.10/3.12, eliminates deploy script special-casing, matches plan 013 direction.

---

## 2. Configuration & credentials

### Problem

`ConfigManager.load_config` already loads a top-level `sql:` block into `self.sql_config` (`config_manager.py:349–351`), but **`config/template.yaml` has no `sql:` section**. Today users could put `connection_string`, `uid`, and `pwd` in YAML; that config flows into audit packages. Redaction exists (`core/audit_package.py:14–26`) but is not a substitute for keeping secrets out of files analysts share.

Redaction keys today: `connection_string`, `pwd`, `password`, `uid`, `user`, `token`, `secret`, `api_key`.

**Gap:** `connection_string_env` is not redacted (it is not a secret — only the env var *name*). Values resolved at runtime must never be serialized into snapshots.

### Proposed `sql:` schema

```yaml
sql:
  # Preferred: DSN/credentials live in environment, not on disk
  connection_string_env: BENCH_SQL_DSN

  # Windows integrated auth (no uid/pwd in file)
  # trusted_connection: true   # build plan: append Trusted_Connection=yes when using server/database form

  # Discouraged: inline DSN (redacted in audit packages if present)
  # connection_string: "Driver={ODBC Driver 18 for SQL Server};Server=...;Database=...;"

  # Component form (also discouraged for secrets; uid/pwd redacted if present)
  # driver: "ODBC Driver 18 for SQL Server"
  # server: myserver.database.windows.net
  # database: benchmarks
  # uid: ...
  # pwd: ...

  # Default source when CLI omits --sql-query / --sql-table (optional convenience)
  query_file: queries/monthly_share.sql
  # table: dbo.benchmark_data   # mutually exclusive with query_file in config
```

**Resolution order for connection string:**

1. If `connection_string_env` is set → `os.environ[name]` (fail fast if unset).
2. Else if `connection_string` is set → use directly (log warning: discouraged).
3. Else if `server` + `database` → build ODBC string; append `Trusted_Connection=yes` when `trusted_connection: true`, else require env-based credentials (do not accept plain `pwd` in new docs).

**Build-plan additions:**

- Extend `get_sql_connection()` to resolve `connection_string_env`.
- Extend `_redact_secrets` to redact resolved connection strings in metadata if ever captured (belt-and-suspenders).
- Add schema validation in `utils/validators.py` for the `sql:` block.
- Document in `config/template.yaml` with commented examples.

### CLI / config precedence vs CSV

**Rule: exactly one input source per run.**

| Source | Flag / config |
|--------|----------------|
| CSV | `--csv PATH` |
| SQL query file | `--sql-query PATH` (overrides config `query_file` when set) |
| SQL table/view | `--sql-table NAME` (overrides config `table` when set) |

**Precedence:**

1. CLI flags beat config defaults (`query_file` / `table` in YAML).
2. `--csv`, `--sql-query`, and `--sql-table` are **mutually exclusive** — argparse `MutuallyExclusiveGroup` replacing `--csv required=True` with "one of required".
3. Current `load_data` dispatch (`data_loader.py:183–196`) checks **`csv` first**, then `sql_query`, then `sql_table`. If both `csv` and `sql_*` are set, CSV wins silently today. **Build plan must enforce exclusivity at parse time** to avoid surprise.

Prototype confirmed CSV-wins behavior: `outputs/sql_spike.py` `test_load_data_dispatch_precedence`.

---

## 3. Query safety

### Current behavior

| Loader | Safety today |
|--------|----------------|
| `load_from_sql_table` | Identifier validated via `_validate_sql_identifier` — regex `[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)?` (`data_loader.py:610–613`). Emits `SELECT * FROM {safe_name}` only. |
| `load_from_sql_query` | Reads entire file, passes to `pd.read_sql` — **no** statement validation (`data_loader.py:556–563). |

### Recommended validation for `load_from_sql_query` (build plan)

Apply **before** `pd.read_sql`:

1. **Strip** leading/trailing whitespace and SQL `--` / `/* */` comments (or reject files containing block comments — simpler).
2. **Reject** if more than one statement: semicolon not at end (`;` followed by non-whitespace).
3. **Reject** unless statement starts with `SELECT` (case-insensitive, after strip).
4. **Reject** leading keywords (after strip): `INSERT`, `UPDATE`, `DELETE`, `DROP`, `CREATE`, `ALTER`, `TRUNCATE`, `EXEC`, `EXECUTE`, `MERGE`, `GRANT`, `REVOKE`, `CALL`.
5. **Reject** obvious multi-statement injection patterns (`;` + DML/DDL keyword).

**Do not change** `load_from_sql_table` identifier validation except to document that **views** are the preferred abstraction (`--sql-table dbo.v_benchmark_share`).

### Residual risk (honest)

Keyword filters are **not a security boundary**. They reduce accidental misuse; a determined caller with query-file access can still craft creative `SELECT` payloads. The real controls are:

- **Read-only database role** with access limited to approved views.
- **No ad-hoc query files in production** if policy allows — table/view-only mode (see open question 4).
- Network/firewall restrictions on the warehouse.

Document read-only role requirement in operator docs and preset/compliance guidance.

---

## 4. CLI surface

### Proposed flags (share and rate subcommands)

Add to `add_common_run_flags` in `benchmark.py:90–92`:

```
--csv PATH              Path to CSV input (optional if SQL source set)
--sql-query PATH        Path to SQL query file (SELECT-only; validated)
--sql-table NAME        SQL table or view name (identifier-validated)
```

Replace `parser.add_argument('--csv', required=True, ...)` with a mutually exclusive group requiring one of the three.

**Examples:**

```powershell
py benchmark.py share ^
  --sql-table dbo.v_benchmark_share ^
  --config sql_prod.yaml ^
  --entity Target ^
  --metric txn_cnt ^
  --dimensions card_type channel ^
  --preset balanced_default

py benchmark.py share ^
  --sql-query queries/monthly.sql ^
  --config sql_prod.yaml ^
  ...
```

Config-only SQL source (no CLI SQL flag) is acceptable if `sql.query_file` or `sql.table` is set in YAML — but CLI should still require explicit `--config` so connection settings are intentional.

### TUI

**Defer.** Textual file-picker patterns exist for CSV; SQL needs connection profile management, driver install checks, and query safety UX. One paragraph is enough until CLI adoption is known. When added, mirror `AnalysisRunRequest` fields populated from widgets (`from_widget_values` at `contracts.py:165`).

---

## 5. Integration points

Inventory for the follow-up build plan (line refs from worktree at spike base `4dc200b`):

| Location | Change |
|----------|--------|
| `benchmark.py:90–92` | Mutually exclusive `--csv` / `--sql-query` / `--sql-table`; update help examples |
| `core/contracts.py:84–118` | Add `sql_query: Optional[str]`, `sql_table: Optional[str]` to `AnalysisRunRequest`; wire `from_namespace` / `to_namespace` |
| `core/analysis_run.py:333` | Extend metadata: `input_source` enum (`csv` / `sql_query` / `sql_table`), not only `input_csv` |
| `core/analysis_run.py:374–379` | `resolve_input_dataframe` — no change if args carry sql attrs |
| `core/analysis_run.py:396–412` | `prepare_run_data` — works once args include sql fields (prototype verified) |
| `core/data_loader.py:191–196` | Optional: assert exclusivity; add query validation hook before `pd.read_sql` |
| `core/data_loader.py:536–574` | Implement `_validate_sql_query_file()` |
| `utils/config_manager.py:349–351` | Already loads `sql:` block |
| `utils/config_manager.py:444–482` | Switch to `pyodbc`; implement `connection_string_env` |
| `utils/validators.py` | Validate `sql:` schema |
| `config/template.yaml` | Add commented `sql:` section |
| `core/audit_package.py:14` | Optionally add `connection_string_env` to non-secret allowlist; ensure resolved secrets never logged |
| `deploy_and_install.ps1:35–66` | Remove pypyodbc special-case when plan 013 + this land |
| `requirements-sql.txt` (new) | `pyodbc>=5.3,<6` |
| `requirements.txt` | No SQL driver (per plan 013) |
| `AGENTS.md` / `docs/CORE_TECHNICAL_DOC.md` | CLI examples, credential policy |

### Prototype results (`outputs/sql_spike.py`)

Run: `py outputs/sql_spike.py` → **All checks passed.**

| Path | Result |
|------|--------|
| `SimpleNamespace(sql_table="gate_demo")` → `DataLoader.load_data` | 42 rows, columns normalized |
| `SimpleNamespace(sql_query=...)` → `load_data` | Same schema as fixture |
| `prepare_run_data(args with sql_table only)` → `execute_share_run` | Workbook + `fully_compliant` verdict |
| CSV + sql_table both set | CSV wins (documented; parser must prevent) |

**Hand-holding noted:**

- SQL result must match CSV long-format schema (`issuer_name`, metrics, dimensions). Column normalization runs automatically (`_normalize_columns`).
- `ConfigManager` must have non-empty `sql_config` or `get_sql_connection` raises (`config_manager.py:452–453`).
- Full `_execute_run` path requires `AnalysisRunRequest` fields for sql sources (today only `csv` / `df`); prototype passed loaded `df` or used `prepare_run_data` directly.
- ODBC driver manager + DB-specific ODBC driver remain **OS prerequisites** (document in SETUP).

**STOP condition check:** Dormant path is **not** fundamentally broken. Prototype succeeded without product code changes.

---

## 6. Test strategy

| Layer | Approach |
|-------|----------|
| Unit | Extend `tests/test_data_loader_sql.py`: query validation accept/reject cases; `connection_string_env` resolution (mock `os.environ`); pyodbc import guard message |
| Integration | Add `tests/test_analysis_run_sql_integration.py` pattern: sqlite mock + `prepare_run_data` + short share run (mirror spike, in pytest) |
| CLI | `tests/test_benchmark_cli.py` (or similar): mutually exclusive parse errors; happy path with `--sql-table` mocked |
| Gate | **No SQL case** — gate stays portable, no ODBC driver, no network DB |

Existing: `py -m pytest tests/test_data_loader_sql.py -q` → **4 passed** (spike session).

Full suite: `py -m pytest tests/ -q` → **246 passed** (spike session, no product changes).

---

## 7. Packaging & install UX

Aligned with **plan 013** (pypyodbc removed from default install):

### Default install (no SQL)

```powershell
pip install -r requirements.txt
# or future: pip install autobench
```

SQL loaders remain in codebase; `get_sql_connection` fails with actionable message if driver missing.

### SQL optional extra

**Option A — requirements file (matches repo style today):**

```powershell
pip install -r requirements.txt -r requirements-sql.txt
```

`requirements-sql.txt`:

```
pyodbc>=5.3,<6
```

**Option B — PEP 621 optional dependency** (if/when pyproject.toml lands from plan 014):

```powershell
pip install autobench[sql]
```

### Platform notes

| OS | Prerequisite |
|----|--------------|
| Windows | ODBC Driver for SQL Server (or target DB); pyodbc wheel includes bindings |
| Linux CI | `unixODBC` system package + DB driver; pyodbc manylinux wheel (plan 013 CI matrix 3.10/3.12) |

Update `deploy_and_install.ps1` to treat `pyodbc` like other binary wheels (remove pypyodbc source-download block).

Update `scripts/cloud_install.sh` comment: SQL is opt-in.

---

## 8. Open questions for the maintainer

1. **Is there a real production SQL user today?**  
   `deploy_and_install.ps1` special-cases pypyodbc for offline Linux bundles (no wheels), which suggests someone anticipated SQL/Odbc deployments — but there is **no** CLI, no sample `sql:` config in repo, and tests mock sqlite only. **Which DBMS** (SQL Server, Snowflake ODBC, etc.)?

2. **pyodbc optional extra vs SQLAlchemy dependency?**  
   Spike recommendation: **pyodbc only** (minimal, matches existing DBAPI usage, no pandas warning on 2.3.3). SQLAlchemy adds weight unless connection pooling or multi-dialect URIs are required.

3. **Should TUI get a source picker now or after CLI proves demand?**  
   Spike recommendation: **defer TUI** until question 1 is answered and CLI is shipped.

4. **Is `load_from_sql_query` (arbitrary file) needed at all, or is `--sql-table` + documented views enough?**  
   If table/view-only is acceptable, scope halves: no query-file validator, no `--sql-query`, config `query_file` dropped. Analysts maintain logic in the warehouse as views.

---

## 9. Production SQL consumer flag (spike STOP review)

`deploy_and_install.ps1:35–66` proves the **packaging pipeline** handles pypyodbc specially; it does **not** prove live warehouse ingestion. No credentials, DSNs, or SQL configs were found in tracked repo files. **Did not STOP** — premise stands, but maintainers should confirm question 1 before build.

---

## References

- Plan 013: `plans/013-dependency-pinning-python-310.md` (optional `pyodbc`, remove default `pypyodbc`)
- Product intent: `docs/CORE_TECHNICAL_DOC.md` (CSV/SQL ingestion)
- Unit tests: `tests/test_data_loader_sql.py`
- Integration pattern: `tests/test_analysis_run_integration.py`
- Prototype: `outputs/sql_spike.py` (gitignored)
