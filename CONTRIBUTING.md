# Contributing to Autobench

This is the shortest safe path for making a change.

## 1. Set up

```powershell
cd D:\Projects\autobench
py -m pip install -r requirements.txt -r requirements-dev.txt -c constraints.txt
```

## 2. Make a change

Start from `main` unless the user asks for a branch.

```powershell
git status --short --branch
git branch -vv
```

Run focused tests for the files you touched. If you are unsure, run the local
gate.

## 3. Validate locally

Fast product smoke:

```powershell
py benchmark.py share --csv tests/fixtures/gate_demo.csv --entity Target --metric txn_cnt --dimensions card_type channel --time-col year_month --preset balanced_default --output gate_demo_share.xlsx
py benchmark.py rate --csv tests/fixtures/gate_demo.csv --entity Target --total-col total --approved-col approved --fraud-col fraud --dimensions card_type channel --time-col year_month --preset balanced_default --export-balanced-csv --output gate_demo_rate.xlsx
```

Full local gate:

```powershell
.\tools\dev\local_check.ps1
```

## 4. Commit

```powershell
git diff
git add <files>
git commit -m "Describe the change"
```

Do not commit generated `.xlsx`, balanced CSVs, audit packages, logs, deploy
zips, screenshots, local data, credentials, or passcodes.

## 5. Release

Normal releases happen from `edge-deploy-core`, not from this repo:

```powershell
cd D:\Projects\edge-deploy-core
py -m edge_deploy release --tool autobench --smoke standard
```

Use repo-local deployment scripts only for bootstrap, recovery, or diagnosis.
