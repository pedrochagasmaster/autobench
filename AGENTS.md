# Autobench Agent Guide

Autobench is a privacy-compliant peer benchmark tool for Mastercard Control
3.2. It has two user entry points:

- CLI: `benchmark.py`
- TUI: `tui_app.py`

The core engine lives in `core/`; shared configuration and validation helpers
live in `utils/`.

## Non-negotiable rules

- Do not weaken privacy enforcement.
- Do not bypass input validation for publishable output.
- Keep CLI and TUI behavior aligned through `core.analysis_run`.
- Do not commit generated workbooks, balanced CSVs, audit packages, logs,
  deploy zips, screenshots, credentials, or RSA/Kerberos secrets.
- Do not push to remotes unless the user explicitly asks.

## Local development

Use [CONTRIBUTING.md](CONTRIBUTING.md) for the contributor runway.

Core loop:

```powershell
py -m pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt
.\tools\dev\local_check.ps1
```

For a fast smoke:

```powershell
py benchmark.py share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --output gate_demo_share.xlsx
py benchmark.py rate --csv tests/fixtures/gate_demo.csv --entity Target --total-col total --approved-col approved --fraud-col fraud --dimensions card_type channel --time-col year_month --preset balanced_default --export-balanced-csv --output gate_demo_rate.xlsx
```

## Release workflow

Default releases are orchestrated from `D:\Projects\edge-deploy-core`:

```powershell
py -m edge_deploy release --tool autobench --smoke standard
```

Repo-local scripts such as `update.sh`, `deploy_and_install.ps1`, and
`tools/prod_tui` are bootstrap, recovery, or diagnosis tools only.

For details, read:

- [docs/development-workflow.md](docs/development-workflow.md)
- `.agents/skills/autobench-edge-deploy/SKILL.md`

## Where to look

- Product/user docs: [README.md](README.md)
- Contributor path: [CONTRIBUTING.md](CONTRIBUTING.md)
- Release path: [docs/development-workflow.md](docs/development-workflow.md)
- Control 3 source: [docs/control-3-customer-merchant-performance-v5-20260603.md](docs/control-3-customer-merchant-performance-v5-20260603.md)
- Technical internals: [docs/CORE_TECHNICAL_DOC.md](docs/CORE_TECHNICAL_DOC.md)
