# Plan 002: Add direct tests for config merge precedence (CLI > config file > preset > defaults)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- utils/config_manager.py tests/`
> If `utils/config_manager.py` changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

The configuration hierarchy (CLI overrides > config file > preset > hardcoded defaults) is a stated invariant of this repo — `AGENTS.md` says all analysis logic must source parameters from the merged config. Yet no test in `tests/` constructs a `ConfigManager` with `cli_overrides` at all (verified by grep at commit `e0950c4`). A regression in `_apply_cli_overrides` or the merge order would silently run every analysis with wrong optimization/compliance parameters while appearing correctly configured. One small parametrized test module closes this hole.

## Current state

- `utils/config_manager.py:261-306` — constructor applies, in order: `_get_default_config()` → `_load_preset(preset)` → `load_config(config_file)` → `_apply_cli_overrides(cli_overrides)`. Docstring confirms: "Configuration hierarchy (lowest to highest priority): 1. Defaults 2. Preset 3. Config file 4. CLI overrides".
- `utils/config_manager.py:731-776` — `_apply_cli_overrides` maps flat CLI keys to nested config paths. Relevant entries:

```python
mapping = {
    'tolerance': ('optimization', 'linear_programming', 'tolerance'),
    'max_weight': ('optimization', 'bounds', 'max_weight'),
    'debug': ('output', 'include_debug_sheets'),
    'compliance_posture': ('compliance_posture',),
    ...
}
```

- `ConfigManager.get(*path, default=...)` is the access API; `config.resolve()` returns a typed `ResolvedConfig` (see `utils/config_manager.py:92-104` for the dataclass).
- Shipped presets live in `presets/`; `compliance_strict` sets `optimization.linear_programming.tolerance: 0.0` and `balanced_default` sets `2.0` (per the preset table in `AGENTS.md`).
- Test conventions: plain pytest functions, `tmp_path` fixture for temp files — see `tests/test_preset_workflow.py` for the pattern of writing a temp YAML config and constructing `ConfigManager` around it.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| New tests | `py -m pytest tests/test_config_precedence.py -q` | all pass |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Lint | `py -m ruff check --select E,F --ignore E501,F401 tests/` | exit 0 |

## Scope

**In scope**:
- `tests/test_config_precedence.py` (create)

**Out of scope**:
- `utils/config_manager.py` — characterize, don't change. If a precedence test fails, that's a product bug to report, not to fix here.
- `presets/*.yaml` — never modify shipped presets.

## Git workflow

- Branch: `advisor/002-config-precedence-tests`
- Commit message style: `test: assert config merge precedence`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Create `tests/test_config_precedence.py`

Write these tests (use `tmp_path` to create a temp YAML config file where needed; a minimal valid config file needs `version: "3.0"` at the top — confirm against `config/template.yaml`):

1. **Default baseline**: `ConfigManager()` → `config.get('optimization', 'linear_programming', 'tolerance')` equals the hardcoded default (read `_get_default_config()` to find it; assert that exact value).
2. **Preset beats default**: `ConfigManager(preset='compliance_strict')` → tolerance is `0.0`.
3. **Config file beats preset**: write a temp YAML with `version: "3.0"` and `optimization.linear_programming.tolerance: 7.5`; `ConfigManager(config_file=str(path), preset='compliance_strict')` → tolerance is `7.5`.
4. **CLI beats config file and preset**: same temp file, plus `cli_overrides={'tolerance': 3.25}` → tolerance is `3.25`.
5. **CLI `None` does not override**: `cli_overrides={'tolerance': None}` with the temp file → tolerance remains `7.5` (line 791: only non-`None` values are applied).
6. **Multiple paths**: `cli_overrides={'debug': True, 'max_weight': 5.0}` → `config.get('output', 'include_debug_sheets') is True` and `config.get('optimization', 'bounds', 'max_weight') == 5.0`.
7. **ResolvedConfig agrees**: for case 4, also assert `config.resolve().linear_programming.tolerance == 3.25` (confirm the attribute path on `ResolvedConfig` by reading `utils/config_manager.py:92-104` first; if the attribute is named differently, use the actual name).

**Verify**: `py -m pytest tests/test_config_precedence.py -q` → 7 tests pass.

### Step 2: Full verification

**Verify**: `py -m pytest tests/ -q` → all pass.

## Test plan

This plan is the test plan. Model file layout on `tests/test_preset_workflow.py`.

## Done criteria

- [ ] `py -m pytest tests/ -q` exits 0, with ≥7 new tests in `tests/test_config_precedence.py`
- [ ] At least one test constructs `ConfigManager` with all three of preset + config_file + cli_overrides simultaneously
- [ ] `git status` shows only the new test file
- [ ] `plans/README.md` status row updated

## STOP conditions

- A precedence test fails (CLI does not win, or preset beats config file) — report as a product bug with the failing combination; do not modify `utils/config_manager.py`.
- `ConfigManager` constructor signature differs from `(config_file, preset, cli_overrides)`.
- Constructing `ConfigManager(preset='compliance_strict')` raises (e.g. posture validation requires acknowledgement in test context) — report what it raised; you may pass additional documented kwargs/overrides if `_validate_compliance_posture` requires them, but record that in the test as a comment.

## Maintenance notes

- Any new CLI flag added to `_apply_cli_overrides` should get a row in this test module — reviewers should ask for it.
- This is a prerequisite-quality guard for plan 011 (ResolvedConfig constructor work).
