# Plan 013: Pin dependencies with a constraints file, declare Python ≥3.10, drop unused deps

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- requirements.txt requirements-dev.txt mypy.ini .github/workflows/ci.yml scripts/cloud_install.sh`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: none
- **Category**: migration
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

Every dependency is a floor-only pin (`pandas>=1.3.0`, `textual>=0.40.0`, …) with no lockfile or upper bounds, so each fresh install and each CI run resolves whatever is newest — pandas 3.x and textual majors can land silently and break the build with zero code changes. Meanwhile the repo *claims* Python 3.8 support (`mypy.ini`'s `python_version = 3.8`, AGENTS.md's "Python 3.8+") but `tui_app.py` uses PEP 604 unions (`AnalysisRunRequest | None`) with **no** `from __future__ import annotations` — verified at commit `e0950c4` — so the recommended entry point already requires Python 3.10. Two dependencies are dead weight: `pypyodbc` backs a SQL path with no CLI/TUI/config surface (only reachable via `hasattr(args, 'sql_query')` on a hand-built namespace), and `python-dateutil` is never imported anywhere in product or test code.

## Current state

- `requirements.txt` (entire file, 21 lines): `pandas>=1.3.0`, `numpy>=1.21.0`, `openpyxl>=3.0.0`, `PyYAML>=6.0`, `scipy>=1.8.0`, `pypyodbc>=1.3.6` (commented "SQL support (optional)"), `python-dateutil>=2.8.0`, `textual>=0.40.0`.
- `requirements-dev.txt`: `pytest>=7.0.0`, `ruff>=0.4.0`, `mypy>=1.8.0`.
- `mypy.ini:2`: `python_version = 3.8` (also `[mypy-pypyodbc.*] ignore_missing_imports = True` at lines 16-17).
- `.github/workflows/ci.yml:14`: matrix is `["3.10", "3.12"]`; `:27`: `pip install -r requirements.txt -r requirements-dev.txt`.
- `tui_app.py`: contains `X | None` annotations (e.g. `saved_request: AnalysisRunRequest | None = None` ~line 1078) and **no** `__future__` import — parse-time syntax requiring ≥3.10 for class-body/parameter annotations evaluated at runtime; in any case CI never tests <3.10.
- `pypyodbc` usage: lazy import only in `utils/config_manager.py:456-475` (`get_sql_connection`); SQL loaders `core/data_loader.py:536-608` reachable only via `args.sql_query`/`args.sql_table`, which **no parser defines** (verified: zero matches in `benchmark.py`). Tests (`tests/test_data_loader_sql.py`) mock the connection with `sqlite3`, not pypyodbc.
- `python-dateutil`: zero `dateutil` imports repo-wide (verified by grep). pandas depends on it transitively anyway.
- Deploy script `deploy_and_install.ps1` special-cases pypyodbc (lines ~35-66 per audit) — check and update if you remove the dep.
- Docs claiming 3.8: `AGENTS.md` (Code Style table: "Python | 3.8+").

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Resolve current versions | `py -m pip freeze` | list of installed versions |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |
| Install check | `py -m pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt --dry-run` | resolves without conflict |

## Scope

**In scope**:
- `requirements.txt`, `requirements-dev.txt`
- `constraints.txt` (create)
- `mypy.ini`
- `.github/workflows/ci.yml`
- `scripts/cloud_install.sh`, `deploy_and_install.ps1` (install-line updates only)
- `AGENTS.md`, `README.md`, `SETUP.md` (Python-version statements only)

**Out of scope**:
- Removing the SQL **code** (`core/data_loader.py` loaders, `utils/config_manager.py:get_sql_connection`, `tests/test_data_loader_sql.py`) — the maintainer may still productize SQL (audit DIRECTION-01); only the *default dependency* is removed. The lazy import means the code works if a user installs an ODBC driver themselves.
- Typing-style modernization (`Optional[X]` → `X | None` sweeps) — cosmetic, rejected in the audit.
- Upgrading any dependency major version — this plan pins what works today; migrations are separate decisions.

## Git workflow

- Branch: `advisor/013-dependency-pinning`
- Commit per step; message style: `chore: <imperative>` / `docs: <imperative>`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Add upper bounds and drop dead deps in `requirements.txt`

Rewrite `requirements.txt`:

```
# Data processing
pandas>=2.0,<3
numpy>=1.24,<3

# Excel support
openpyxl>=3.1,<4

# Configuration
PyYAML>=6.0,<7

# Optimization (required for strict privacy-cap LP solver)
scipy>=1.10,<2

# TUI
textual>=0.40.0,<__CAP__
```

For the textual cap: run `py -m pip show textual` to find the locally installed (working) version, and cap at the **next major** above it (e.g. installed 3.2 → `<4`). Removed lines: `pypyodbc>=1.3.6` and `python-dateutil>=2.8.0`. Add a comment where pypyodbc was: `# SQL ingestion is optional: install an ODBC driver package (e.g. pypyodbc) manually if using load_from_sql_*`.

Also raise floors only as far as evidenced: keep floors at versions you can verify work (the locally installed set from `py -m pip freeze` proves one working combination; do not raise floors above what CI's 3.10 can satisfy).

**Verify**: `py -m pip install -r requirements.txt -r requirements-dev.txt --dry-run` → resolves.

### Step 2: Generate `constraints.txt`

Create a constraints file from the known-good environment:

```powershell
py -m pip freeze | Out-File -Encoding ascii constraints.txt
```

Then prune it to only the packages in `requirements*.txt` plus their direct transitive dependencies is *optional* — a full freeze is acceptable and simpler; if the freeze contains obviously local/unrelated packages (editor tooling etc.), prune those. Add a header comment:

```
# Known-good resolved versions. Refresh deliberately:
#   py -m pip install -U -r requirements.txt -r requirements-dev.txt
#   py -m pytest tests/ -q && py scripts/perform_gate_test.py
#   py -m pip freeze | Out-File -Encoding ascii constraints.txt   (PowerShell)
```

**Verify**: `py -m pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt --dry-run` → resolves without conflict.

### Step 3: Wire CI and install scripts to the constraints file

- `.github/workflows/ci.yml:27`: change to `pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt`.
- `scripts/cloud_install.sh`: same `-c constraints.txt` addition on its pip install line(s).
- `deploy_and_install.ps1`: update its install lines similarly, and remove/adjust the pypyodbc special-case block (read it first; if it handles offline bundles, remove only the pypyodbc-specific handling).

**Verify**: YAML still valid (`py -c "import yaml,io; yaml.safe_load(open('.github/workflows/ci.yml'))"` → no error).

### Step 4: Declare Python 3.10 floor

- `mypy.ini:2`: `python_version = 3.10`. Remove the `[mypy-pypyodbc.*]` section (lines 16-17) only if mypy passes without it (the lazy import in `config_manager.py` still references pypyodbc — mypy will flag the missing stub, so likely **keep** this section; test both ways).
- `AGENTS.md`: change the Code Style table row "Python | 3.8+" to "Python | 3.10+".
- `README.md` / `SETUP.md`: add/adjust a one-line Python requirement statement ("Requires Python 3.10+") near the install instructions. Check `SETUP.md` for an existing version mention first.
- Add `pin` for dev tools in `requirements-dev.txt`: `pytest>=7.0,<9`, `ruff>=0.4,<1`, `mypy>=1.8,<2` (covered by constraints anyway).

**Verify**: `py -m mypy core/ utils/` → exit 0.

### Step 5: Full verification

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0. Confirm `tests/test_data_loader_sql.py` still passes (it uses sqlite mocks, not pypyodbc).

## Test plan

No new tests — this is environment policy. The verification gates above plus CI on the PR (3.10 + 3.12 matrix with constraints) are the proof.

## Done criteria

- [ ] `requirements.txt` has upper bounds on every entry; no `pypyodbc`, no `python-dateutil`
- [ ] `constraints.txt` exists with refresh instructions and CI installs with `-c constraints.txt`
- [ ] `mypy.ini` says `python_version = 3.10`; AGENTS.md/README/SETUP say 3.10+
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m mypy core/ utils/` all exit 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- The locally installed dependency set fails the gate **before** any changes (pre-existing environment breakage) — report; do not freeze a broken set into constraints.
- `deploy_and_install.ps1`'s pypyodbc handling is load-bearing for an offline production bundle in a way that suggests SQL *is* used in production — report before removing the dep; the maintainer must decide (relates to audit DIRECTION-01).
- mypy fails after the 3.10 bump with more than ~5 new errors — the version bump changed inference; report the error list rather than fixing unrelated typing.

## Maintenance notes

- Constraints refresh cadence: deliberate, with the gate as the acceptance test (instructions are in the file header). Consider a monthly scheduled CI job later.
- pandas <3 cap is deliberate: a pandas-3 migration (Copy-on-Write semantics) should be its own planned effort with golden-output comparison.
- If SQL ingestion is productized later, reintroduce a maintained ODBC package (`pyodbc`, not `pypyodbc`) as an optional extra (`requirements-sql.txt`).
