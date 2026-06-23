# Release Process

Date: 2026-05-30

This checklist covers production releases for the offline Mastercard deployment
described in `SETUP.md`.

## Pre-release

1. Confirm the release branch passes CI:
   - `ruff check --select E,F --ignore E501,F401 benchmark.py core/ utils/ tui_app.py`
   - `py -m pytest tests/ -v`
   - `py scripts/perform_gate_test.py`
2. Update release notes or changelog if the release is user-visible.
3. Tag the commit after merge to `main`.

## Build offline bundle

1. On a networked Windows machine with PowerShell:
   ```powershell
   .\deploy_and_install.ps1
   ```
2. Verify `offline_packages/`, `requirements.txt`, `SHA256SUMS`, and
   `scripts/offline_bundle_checksums.py` are included in the bundle.
3. Confirm `setup_remote_env.sh` reports successful checksum verification before
   installing packages.

## Server smoke (after deploy)

Run on the target server:

```bash
cd /ads_storage/autobench
./run_tool.sh share --help
./run_tool.sh config list
./run_tool.sh share \
  --csv tests/fixtures/gate_demo.csv \
  --entity Target \
  --metric txn_cnt \
  --dimensions card_type channel \
  --time-col year_month \
  --preset balanced_default \
  --export-balanced-csv \
  --audit-package \
  --output /tmp/release_smoke.xlsx
```

Expected signals:

- Help and preset list commands exit 0.
- Smoke analysis exits 0 and writes `/tmp/release_smoke.xlsx`.
- Smoke analysis writes `/tmp/release_smoke_balanced.csv`,
  `/tmp/release_smoke_audit.log`, and `/tmp/release_smoke_audit_package.zip`.
- Workbook contains `Summary`, dimension sheets, `Weight Methods`, and `Rank Changes`.
- Workbook `Summary` shows `Input Validation: pass` and `Compliance Verdict: fully_compliant`.

## Rollback

1. Restore the previous git tag on the server:
   ```bash
   git checkout -f <previous-tag>
   ```
2. Re-run the server smoke commands.
3. If dependency versions changed, redeploy the previous offline bundle instead of
   reusing the current `offline_packages/` directory.

## Recovery from failed dependency installs

1. Remove the broken virtual environment or site-packages target documented in
   `setup_remote_env.sh`.
2. Re-extract the known-good offline bundle.
3. Re-run `setup_remote_env.sh`.
4. Re-run the server smoke commands before announcing the release.
