# Plan 019: Wire JSON output through the live orchestration path (output.format: json)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- core/output_artifacts.py core/report_generator.py core/contracts.py core/analysis_run.py benchmark.py utils/config_manager.py config/template.yaml utils/validators.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P2
- **Effort**: M
- **Risk**: LOW
- **Depends on**: plans/003-analysis-run-integration-test.md (recommended net); coordinate with plans/006-strict-posture-publication-gate.md and plans/009-dead-code-cleanup.md if in flight (same files)
- **Category**: direction
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

JSON output is stated-but-undelivered: `ReportGenerator._generate_json_report` is implemented, `utils/validators.py` accepts `output.format ∈ {xlsx, csv, json}`, AGENTS.md and the executive script list JSON as a format — but the live orchestration (`write_outputs`) only ever writes Excel, and `config/template.yaml` admits "currently only xlsx supported". The maintainer has chosen to **wire** it (2026-06-10). Design decision baked into this plan: `output.format: json` produces a JSON report **as an additional sidecar artifact next to the analysis workbook**, not a replacement — every downstream consumer (gate verification, audit log/package, publication path, CSV cross-validation) assumes the workbook exists, so replacement would be a much riskier change for no demonstrated need. The JSON file is an analysis-grade artifact: it is NOT publication-redacted and must say so in its payload.

## Current state

- `core/report_generator.py:116-127` — the dormant dispatch (`generate_report(..., format=...)`) routes `'json'` to `_generate_json_report`; nothing calls it with `format='json'`.
- `core/report_generator.py:662-683` — `_generate_json_report` (verbatim):

```python
output_data = {
    'analysis_type': analysis_type,
    'metadata': metadata or {},
    'results': {}
}
for metric_name, result_data in results.items():
    if isinstance(result_data, dict):
        output_data['results'][metric_name] = result_data
    elif isinstance(result_data, pd.DataFrame):
        output_data['results'][metric_name] = result_data.to_dict(orient='records')
with open(output_file, 'w') as f:
    json.dump(output_data, f, indent=2, default=str)
```

  Weakness: `metadata` values that are DataFrames get `str()`-mangled by `default=str` — fix in Step 2.
- `core/output_artifacts.py:53-151` — `write_outputs` builds a `ReportModel`, then writes analysis and/or publication workbooks based on `output.output_format` (`analysis|publication|both` — note this is a **different key** from `output.format`). The analysis write happens at lines 144-146. This is where the JSON sidecar hooks in.
- `core/contracts.py` — `AnalysisArtifacts` has no JSON-output field today; one is added in Step 3.
- `utils/validators.py` (~lines 284-285) — already accepts `json` for `output.format`; no change needed there.
- `config/template.yaml` (~lines 67-68) — `output.format` documented as "currently only xlsx supported"; update.
- Rate runs: `artifacts.results` is a nested dict `{rate_type: {dimension: result}}`; the Excel path flattens it to `f"{rate_type}_{dimension}"` keys (see `core/output_artifacts.py:85-90`) — the JSON path must handle the nesting (flatten identically for consistency).
- `output.format` has no CLI flag today (`_apply_cli_overrides` mapping in `utils/config_manager.py:740-776` has no entry) — add one. A new CLI flag needs **three** wiring points: (1) the argparse declaration in `benchmark.py`; (2) the `_apply_cli_overrides` mapping; (3) `COMMON_CLI_OVERRIDES` in `core/analysis_run.py:41-59` — the tuple of arg names `build_run_config` forwards into `ConfigManager`. Omitting (3) makes the flag silently dead.
- Naming collision warning: `--output-format` (existing flag) selects analysis/publication/both. The new flag is `--report-format` and must NOT touch the existing one. The right argparse home is the shared common-flags helper in `benchmark.py` (find it with `rg -n "output-format|add_argument" benchmark.py` and add `--report-format` beside `--output-format`).
- Audit package (`core/audit_package.py:write_audit_package`) bundles `report_paths` + csv + audit log; the JSON sidecar should be added via `_add_existing_file` (tolerates None/missing).

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Manual run | `py benchmark.py share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --report-format json --output plans_v19.xlsx` | exit 0, writes `plans_v19.xlsx` AND `plans_v19.json` |
| JSON validity | `py -c "import json; json.load(open('plans_v19.json'))"` | no error |
| Full suite | `py -m pytest tests/ -q` | all pass |
| Gate | `py scripts/perform_gate_test.py` | exit 0 |
| Typecheck | `py -m mypy core/ utils/` | exit 0 |

## Scope

**In scope**:
- `core/output_artifacts.py` (the sidecar hook)
- `core/report_generator.py` (JSON-safe metadata in `_generate_json_report`)
- `core/contracts.py` (`AnalysisArtifacts.json_output: Optional[str] = None`)
- `core/analysis_run.py` (include JSON in audit package; only if needed — see Step 4)
- `benchmark.py` (`--report-format` flag), `utils/config_manager.py` (CLI mapping)
- `config/template.yaml`, `README.md`, `AGENTS.md` (format documentation)
- `tests/test_json_output.py` (create)

**Out of scope**:
- `output.format: csv` (`_generate_csv_report`) — remains unwired; do not extend the dispatch beyond json. Note it stays documented as unsupported.
- Publication-redacted JSON — explicitly not built; the JSON carries a marker instead.
- The TUI `output_format` Select widget (analysis/publication/both) — different concept; no TUI change.
- Replacing the workbook — sidecar only, per the design decision above.

## Git workflow

- Branch: `advisor/019-json-output`
- Commit per step; message style: `feat: emit JSON report sidecar for output.format=json`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Add the config plumbing and CLI flag

- `benchmark.py` parser (the shared common-flags helper — see the naming-collision note in Current state): add `--report-format {xlsx,json}` with default `None` (config wins). Help text: "xlsx (default) or json — json additionally writes a machine-readable <output>.json next to the workbook".
- `utils/config_manager.py` `_apply_cli_overrides` mapping: `'report_format': ('output', 'format')`.
- `core/analysis_run.py`: add `'report_format'` to `COMMON_CLI_OVERRIDES` (lines 41-59) — required for the CLI value to reach `ConfigManager` at all.
- Confirm the default config has `output.format: xlsx` (read `_get_default_config`); leave the default unchanged.

**Verify**: `py benchmark.py share --help` shows `--report-format`; `py -m pytest tests/ -q` → all pass.

### Step 2: Make `_generate_json_report` metadata-safe

In `core/report_generator.py`, before building `output_data`, convert metadata to JSON-safe form:

```python
def _json_safe_metadata(self, metadata: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for key, value in (metadata or {}).items():
        if isinstance(value, pd.DataFrame):
            safe[key] = value.to_dict(orient='records')
        else:
            safe[key] = value
    return safe
```

Use it in `_generate_json_report` (`'metadata': self._json_safe_metadata(metadata)`), and add two payload keys at the top level: `'publication_safe': False` and `'generated_by': 'autobench'` plus the compliance essentials lifted explicitly so consumers don't dig: `'run_status': (metadata or {}).get('run_status')`, `'compliance_verdict': (metadata or {}).get('compliance_verdict')`. Keep `default=str` as the final fallback.

**Verify**: `py -m pytest tests/ -q` → all pass (nothing calls it yet).

### Step 3: Hook the sidecar into `write_outputs`

- `core/contracts.py`: add `json_output: Optional[str] = None` to `AnalysisArtifacts` (match the dataclass's existing style/field ordering rules — defaulted fields last).
- `core/output_artifacts.py`: in `write_outputs`, after the analysis workbook write (lines 144-146), add:

```python
report_format = (
    config.get("output", "format", default="xlsx") if config is not None else "xlsx"
)
if report_format == "json" and writer.write_analysis:
    json_path = str(Path(output_file).with_suffix(".json"))
    from core.report_generator import ReportGenerator

    json_results = artifacts.results
    if request.is_rate and isinstance(artifacts.results, dict) and all(
        isinstance(v, dict) for v in artifacts.results.values()
    ):
        json_results = {
            f"{rate_type}_{dimension}": value
            for rate_type, rate_results in artifacts.results.items()
            for dimension, value in rate_results.items()
        }
    ReportGenerator(config).generate_report(
        json_results,
        json_path,
        format="json",
        analysis_type="share" if request.is_share else "rate",
        metadata=artifacts.metadata,
    )
    artifacts.json_output = json_path
    logger.info("JSON report written to %s", json_path)
```

  (The rate-flattening mirrors the publication path at lines 85-90 exactly.)

**Verify**: run the manual command from "Commands you will need" → both files exist; `py -c "import json; d=json.load(open('plans_v19.json')); print(d['compliance_verdict'], d['publication_safe'])"` → `fully_compliant False`. Delete the generated files.

### Step 4: Bundle into the audit package

In `core/analysis_run.py`, where `write_audit_package` is called (~line 1534-1542), nothing structural changes — but the JSON sidecar should ship in the package. Simplest: append `artifacts.json_output` to the `report_paths` iterable passed in (it's `Iterable[str]`; `_add_existing_file` skips `None`/missing). Check `build_report_paths` first — if extending `report_paths` has other consumers (the publication gate from plan 006 reads it), pass the JSON path as an additional element only at the audit-package call site: `report_paths=[*(artifacts.report_paths or []), *( [artifacts.json_output] if artifacts.json_output else [] )]`.

**Verify**: full manual run:

```powershell
py benchmark.py share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --report-format json --audit-package --output plans_v19.xlsx
```

→ exit 0, and the zip contains the `.json` file (`py -c "import zipfile; print(zipfile.ZipFile('plans_v19_audit_package.zip').namelist())"`). Delete generated files.

### Step 5: Tests

`tests/test_json_output.py` (invocation pattern from `tests/test_analysis_run_integration.py` if landed, else `tests/test_output_artifacts.py`):
1. Share run with `output.format=json` (via `cli_overrides={'report_format': 'json'}` or request field — match how the test harness passes overrides) → `<stem>.json` exists, parses, has keys `analysis_type`, `results`, `metadata`, `run_status`, `compliance_verdict`, `publication_safe is False`; `results` has one entry per analyzed dimension; workbook ALSO exists.
2. Rate run with json → keys in `results` are flattened `f"{rate_type}_{dimension}"` names.
3. Default run (no format override) → no `.json` file written, `artifacts.json_output is None`.
4. Metadata DataFrames are records, not strings. Caution: `privacy_validation_result` in metadata is a result **object**, not a DataFrame (`core/analysis_run.py:597`) — do not use it. DataFrame-valued metadata keys are mostly debug-gated (`structural_summary_df`, `rank_changes_df`, `subset_search_df`); the robust test: run with `debug=True`, parse the JSON, find every metadata key ending in `_df`, and assert each parsed value is a `list` (records), never a `str`. If no `_df` key exists in the run's metadata, assert instead via a direct unit call to `_json_safe_metadata({"x_df": pd.DataFrame({"a": [1]})})`.

**Verify**: `py -m pytest tests/test_json_output.py -q` → all pass.

### Step 6: Docs + full verification

- `config/template.yaml`: update the `output.format` comment: `# xlsx (default) | json (adds a machine-readable .json beside the analysis workbook; not publication-redacted) — csv not yet supported`.
- `README.md` Outputs section + `AGENTS.md` config-schema block: same one-line description.

**Verify**: `py -m pytest tests/ -q` → all pass; `py scripts/perform_gate_test.py` → exit 0 (gate never sets format=json, so untouched); `py -m mypy core/ utils/` → exit 0; `rg -n "only xlsx supported" config/template.yaml` → no match (exit code 1).

## Test plan

See Step 5 — share sidecar, rate flattening, default-off, metadata serialization quality.

## Done criteria

- [ ] `--report-format json` (and `output.format: json` in config) writes `<output stem>.json` beside the workbook; default behavior byte-identical to today
- [ ] JSON parses and carries `run_status`, `compliance_verdict`, `publication_safe: false`, per-dimension results
- [ ] JSON sidecar lands in the audit package when both flags are set
- [ ] `py -m pytest tests/ -q`, `py scripts/perform_gate_test.py`, `py -m mypy core/ utils/` all exit 0
- [ ] Template/README/AGENTS no longer claim "only xlsx supported"
- [ ] `plans/README.md` status row updated

## STOP conditions

- `artifacts.metadata` contains values that crash `json.dump` even with `default=str` (e.g. circular references) — report the offending key; do not strip metadata wholesale.
- `AnalysisArtifacts` is consumed somewhere that breaks on a new field (unlikely for a defaulted dataclass field; if it's not a dataclass or has `__slots__`, report).
- Plan 006 landed and its publication-withholding logic conflicts with your `write_outputs` edit (merge conflict zone) — rebase carefully; if the interaction is semantically unclear (should strict+violations also withhold the JSON sidecar?), STOP and ask — recommended answer: yes, withhold JSON too, since it is unredacted analysis data, but that needs maintainer confirmation.

## Maintenance notes

- The JSON payload shape (`analysis_type` / `metadata` / `results` + lifted compliance keys) is now a consumer contract — document any future change in README and bump a `schema_version` key if the shape changes (consider adding `'schema_version': 1` now; cheap insurance — executor's choice, note it either way).
- `output.format: csv` remains accepted by the validator but unwired — deliberately left for a future decision; reviewers should not let it silently ship half-wired.
- If publication-safe JSON is ever requested, mirror `_publication_safe_metadata` (`core/report_generator.py:445-451`) — do not reuse the analysis JSON.
