# Plan 014: Centralize tool config in pyproject.toml, stop ignoring F401, run mypy in CI, add a gate fast-subset

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- .github/workflows/ci.yml mypy.ini scripts/perform_gate_test.py AGENTS.md README.md scripts/build_master_context.py`
> (F401 fixes touch additional source files; those are checked per-file in Step 2.)
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: plans/013-dependency-pinning-python-310.md (Python 3.10 declaration; not strictly blocking)
- **Category**: dx
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

Four DX gaps verified at `e0950c4`: (1) there is no `pyproject.toml` — ruff rules exist only as CLI flags inside the CI workflow, so local lint can't match CI without copying flags from YAML; (2) CI explicitly ignores `F401` (unused imports), so dead imports accumulate (`tui_app.py:31` imports `Worker, WorkerState` and never uses them); (3) `AGENTS.md` documents `mypy core/ utils/` as a mandatory verification, but **CI never runs mypy** — type regressions merge green; (4) the only integration check is the full 18-case subprocess gate with no documented fast subset, making the inner dev loop needlessly slow.

## Current state

- No `pyproject.toml`, no `pytest.ini`, no `.ruff.toml` (verified by glob). Tool config today: `mypy.ini` only.
- `.github/workflows/ci.yml:29-39`:

```yaml
- name: Ruff lint
  run: |
    ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py
- name: Unit tests
  run: |
    python -m pytest tests/ -v
- name: Gate test
  run: |
    python scripts/perform_gate_test.py
```

  No mypy step.
- `mypy.ini` (entire file): `python_version`, `strict = True`, excludes `benchmark.py` and `tui_app.py`, per-module ignores for scipy/openpyxl/pypyodbc/textual, and `[mypy-core.balanced_export] ignore_errors = True`.
- `scripts/perform_gate_test.py` — `generate_cases()` regenerates `test_gate/*/cases.jsonl` then a serial loop in `GateTestRunner.run()` (lines 700-718) runs every case as a `subprocess.run`; each case dict carries its identifier under the `"id"` key (used at line 701). There is **no argparse today** — `if __name__ == "__main__"` at lines 758-760 calls the runner directly; add argparse for `--only`. 18 cases total (4 share + 5 rate + 9 config); a valid exemplar id for the fast path is `share_gate_baseline` (`test_gate/share/cases.jsonl` line 1).
- AGENTS.md "Running tests" block documents: lint command (same flags as CI), `py -m pytest`, gate, `mypy core/ utils/`.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Lint (new canonical) | `py -m ruff check .` | exit 0 (config from pyproject) |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |
| Unit tests | `py -m pytest tests/ -q` | all pass |
| Full gate | `py scripts/perform_gate_test.py` | exit 0, 18 cases |
| Fast gate (new) | `py scripts/perform_gate_test.py --only <case_id>` | exit 0, 1 case |

## Scope

**In scope**:
- `pyproject.toml` (create)
- `mypy.ini` (delete, after migrating into pyproject)
- `.github/workflows/ci.yml`
- `scripts/perform_gate_test.py` (add `--only` filter)
- `AGENTS.md`, `README.md` (verification-commands sections)
- Source files for mechanical F401 fixes (removing unused imports) — this includes `benchmark.py`, `tui_app.py`, `core/`, `utils/`, `scripts/`, and `tests/` as Step 2 lints all of them; no edits beyond import removals
- `scripts/build_master_context.py` — its `CONFIG_PATTERNS` list (line ~57) names `mypy.ini`; update it to `pyproject.toml` when the ini is deleted

**Out of scope**:
- Expanding ruff to `I`, `B`, `UP`, `SIM` rule families — larger churn; do it as follow-up once F401 is clean. (Record this in the PR description.)
- Removing mypy's exclusions for `benchmark.py`/`tui_app.py`/`balanced_export` — that's a typing project, not config plumbing.
- Pre-commit hooks — optional follow-up, not planned.
- Formatter adoption (`ruff format`) — repo has no formatter convention; don't introduce one unilaterally.

## Git workflow

- Branch: `advisor/014-tooling-consolidation`
- Commit per step; message style: `chore: <imperative>` / `ci: <imperative>`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Create `pyproject.toml`

```toml
[project]
name = "autobench"
version = "3.0"
description = "Privacy-compliant peer benchmark tool (Mastercard Control 3.2)"
requires-python = ">=3.10"

[tool.ruff]
target-version = "py310"
line-length = 120

[tool.ruff.lint]
select = ["E", "F"]
ignore = ["E501"]   # F401 no longer ignored

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.10"
strict = true
warn_unused_configs = true
exclude = ["benchmark.py", "tui_app.py"]

[[tool.mypy.overrides]]
module = ["scipy.*", "openpyxl.*", "pypyodbc.*", "textual.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "core.balanced_export"
ignore_errors = true
```

Notes: mirror the **current** `mypy.ini` semantics exactly (the exclude regex `^benchmark\.py$|^tui_app\.py$` becomes the list form — verify mypy still skips those two files by running `py -m mypy core/ utils/` and confirming the same module set is checked). If plan 013 has not landed, use `python_version = "3.8"` to match current `mypy.ini` and let plan 013 bump it — do not couple the plans.

Then delete `mypy.ini`.

**Verify**: `py -m mypy core/ utils/` → exit 0 with the same output as before deletion; `py -m pytest tests/ -q` → all pass.

### Step 2: Fix F401 violations

Run `py -m ruff check --select F401 benchmark.py core/ utils/ tui_app.py scripts/ tests/` and remove each unused import (known: `tui_app.py:31` `from textual.worker import Worker, WorkerState`). Caution: some imports are intentional re-exports — `core/__init__.py` exports `DimensionalAnalyzer`, `PrivacyValidator`, `DataLoader` (per AGENTS.md), and `core/report_generator.py:161` has a `noqa: F401`. For genuine re-exports add `__all__` or per-line `# noqa: F401` with a comment; do not delete public API re-exports.

**Verify**: `py -m ruff check .` → exit 0; `py -m pytest tests/ -q` → all pass (an import removal that breaks something means it wasn't unused — restore it with `# noqa` and investigate).

### Step 3: Update CI

In `.github/workflows/ci.yml`:
- Lint step becomes `ruff check .` (config now lives in pyproject).
- Add a mypy step after lint:

```yaml
- name: Mypy typecheck
  run: |
    mypy core/ utils/
```

**Verify**: `py -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"` → no error.

### Step 4: Add `--only` filter to the gate

In `scripts/perform_gate_test.py`, add an argparse option `--only CASE_ID` (repeatable) that filters the loaded cases by their id/name before the run loop (read how cases are loaded and identified first — `test_gate/*/cases.jsonl` rows have identifiers; use whatever key the runner already logs per case). When `--only` is used, print a prominent warning that this is a smoke run, not the mandatory full gate. Document in AGENTS.md's testing section: full gate before PR; `--only share_gate_baseline` (or the actual first share case id — look it up in `test_gate/share/cases.jsonl`) for the inner loop.

**Verify**: `py scripts/perform_gate_test.py --only <real case id>` → runs exactly 1 case, exit 0; `py scripts/perform_gate_test.py` → still runs all 18, exit 0.

### Step 5: Update docs

- `AGENTS.md` "Running tests"/verification sections: replace the long ruff flag invocation with `py -m ruff check .`; note that CI now enforces mypy; document the `--only` gate flag.
- `README.md` "Validation and Testing": same lint command update.

**Verify**: `rg -n "ignore E501,F401|--select E,F" AGENTS.md README.md .github/workflows/ci.yml` → no stale flag strings remain (exit code 1; historical docs not in scope may still match elsewhere).

## Test plan

No new pytest tests. The gate `--only` flag is verified by running it (Step 4). CI changes are verified by YAML parse locally and by the PR's CI run.

## Done criteria

- [ ] `pyproject.toml` exists; `mypy.ini` deleted; `py -m mypy core/ utils/` output unchanged
- [ ] `py -m ruff check .` exits 0 (F401 enforced and clean)
- [ ] CI workflow contains a mypy step and the simplified ruff invocation
- [ ] `py scripts/perform_gate_test.py --only <case>` runs a single case; full gate still runs 18
- [ ] `py -m pytest tests/ -q` and full gate exit 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- `py -m mypy core/ utils/` does **not** exit 0 at baseline (before your changes) — AGENTS.md's claim is stale and adding it to CI would break main; report the error count and stop (the maintainer must decide whether to fix types or scope the CI step).
- F401 cleanup surfaces >25 violations — that's beyond mechanical; fix the top files, `# noqa` the rest with a tracking comment, and note the count.
- The gate runner's case-loading structure makes id-based filtering ambiguous (no stable per-case id) — report rather than inventing identifiers.

## Maintenance notes

- Follow-up deliberately deferred: ruff `I/B/SIM/UP` expansion; un-excluding `benchmark.py`/`tui_app.py`/`core.balanced_export` from mypy; pre-commit hooks.
- Reviewers: confirm CI matrix still passes on both 3.10 and 3.12, and that the pyproject `requires-python` matches whatever plan 013 declared.
