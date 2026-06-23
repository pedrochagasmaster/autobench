# Plan 008: Redact credentials from the audit-package config snapshot

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/audit_package.py core/analysis_run.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: security
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

`--audit-package` bundles a full JSON dump of the merged config into a zip designed to be **shared** as release/audit evidence. The config can contain a `sql` block with `connection_string`, `uid`, and `pwd` (loaded from user YAML via `utils/config_manager.py:444-475`, consumed by `get_sql_connection`). Anyone who configures SQL credentials and then shares an audit package ships their database password inside it. The snapshot must redact secret-bearing keys before serialization. (Never write actual secret values into tests or logs while doing this work.)

## Current state

- `core/analysis_run.py:1534-1542` — the call site passes the raw merged config:

```python
artifacts.audit_package_output = write_audit_package(
    analysis_output_file=analysis_output_file,
    report_paths=artifacts.report_paths or [],
    csv_output=artifacts.csv_output,
    audit_log_output=artifacts.audit_log_output,
    config_snapshot=config.config,
    metadata=metadata,
)
```

- `core/audit_package.py:68-71` — serialized verbatim:

```python
zf.writestr(
    "config_snapshot.json",
    json.dumps(config_snapshot, indent=2, sort_keys=True, default=_json_default),
)
```

- Secret-bearing config keys (from `utils/config_manager.py:444-475` — read it to confirm exact key names): `sql.connection_string`, `sql.uid`, `sql.pwd`, `sql.server`, `sql.database` (server/database are not credentials but are infrastructure identifiers — redact `connection_string`, `pwd`, `uid`; keep `server`/`database` unless they embed credentials).
- Tests for the package: create `tests/test_audit_package.py` (decided — `write_audit_package` currently has only end-to-end coverage via `tests/test_golden_outputs.py:199+`, no unit-level tests to extend).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Targeted tests | `py -m pytest tests/ -k audit -q` | all pass |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `core/audit_package.py`
- tests (extend existing audit-package tests or create `tests/test_audit_package.py`)

**Out of scope**:
- `utils/config_manager.py` — SQL config loading stays as-is.
- `core/audit_log.py` — check whether the audit **log** also embeds the config (`rg -n "config" core/audit_log.py`); if it does, report it in your summary as follow-up, but do not expand scope.

## Git workflow

- Branch: `advisor/008-audit-package-redaction`
- Commit message style: `fix: redact credentials from audit package snapshot`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Add a redaction helper in `core/audit_package.py`

```python
_REDACTED = "***REDACTED***"
_SECRET_KEYS = {"connection_string", "pwd", "password", "uid", "user", "token", "secret", "api_key"}

def _redact_secrets(obj: Any) -> Any:
    """Recursively mask secret-bearing keys before snapshot serialization."""
    if isinstance(obj, dict):
        return {
            key: (_REDACTED if str(key).lower() in _SECRET_KEYS else _redact_secrets(value))
            for key, value in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_secrets(item) for item in obj]
    return obj
```

Apply it in `write_audit_package`:

```python
zf.writestr(
    "config_snapshot.json",
    json.dumps(_redact_secrets(config_snapshot), indent=2, sort_keys=True, default=_json_default),
)
```

Key-name matching is deliberately broad (recursive, case-insensitive) so future config sections with secrets are covered without code changes.

**Verify**: `py -m pytest tests/ -q` → all pass.

### Step 2: Tests

Test cases (construct config dicts with **placeholder** values like `"dummy-not-a-real-secret"`, never realistic credentials):
1. `_redact_secrets({"sql": {"connection_string": "dummy", "pwd": "dummy", "server": "host1"}})` → `connection_string` and `pwd` are `***REDACTED***`, `server` preserved.
2. Nesting: secrets two levels deep are redacted.
3. End-to-end: call `write_audit_package` with a `config_snapshot` containing a dummy `sql.pwd`, into `tmp_path`; open the zip, read `config_snapshot.json`, assert the dummy value does not appear anywhere in the JSON text and `***REDACTED***` does.
4. Non-secret config (a normal `optimization` block) round-trips unchanged.

**Verify**: `py -m pytest tests/ -k audit -q` → all pass.

### Step 3: Full verification

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0; `py -m mypy core/ utils/` → exit 0.

## Test plan

See Step 2. Pattern: existing zip-handling assertions if present in `tests/`; otherwise standard `zipfile.ZipFile(path).read("config_snapshot.json")`.

## Done criteria

- [ ] End-to-end test proves a dummy secret value never appears in `config_snapshot.json`
- [ ] Non-secret config values still appear verbatim (snapshot stays useful)
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m mypy core/ utils/` all exit 0
- [ ] `git status` shows only in-scope files
- [ ] `plans/README.md` status row updated

## STOP conditions

- The gate's audit-package verification asserts on snapshot contents that the redaction changes (unlikely — gate fixtures have no `sql` block) — report the case.
- You find real-looking credentials already committed anywhere in the repo while working — do not copy them anywhere; report the `file:line` and credential type only, and recommend rotation.

## Maintenance notes

- Anyone who shared an audit package containing SQL credentials **before** this fix should rotate those credentials — note this in the PR description.
- If SQL ingestion is later productized (audit DIRECTION-01), credentials should move out of YAML entirely (env vars / DSN); this redaction is the safety net, not the design.
