# Edge-Node Smoke Test Checklist

**Purpose:** Manual validation of Dispatch on the real Hadoop Edge Node before production merge.
**Prerequisite:** SSH access to the Edge Node, valid Kerberos ticket, `impala-shell` on PATH.

---

## Pre-flight

- [ ] SSH to the Edge Node (inside a local tmux session, see [docs/production_testing.md](./production_testing.md)): `ssh -p 2222 <user>@<edge-node>`
- [ ] Enter the **RSA SecurID PASSCODE** at the `Enter PASSCODE:` prompt
- [ ] Initialize Kerberos: `kinit`, then enter the Kerberos password at `Password for <user>@CORP.MASTERCARD.ORG:`
- [ ] Verify Python version: `python3.11 --version || python3.10 --version`
- [ ] Verify `impala-shell` is on PATH: `which impala-shell`
- [ ] Verify Kerberos ticket: `klist` shows a valid, non-expired ticket
- [ ] Verify `/ads_storage/<user>/` is writable: `touch /ads_storage/$USER/.dispatch/.smoke_test`
- [ ] Run `install.sh`: `DISPATCH_EMAIL=you@example.com DISPATCH_PYTHON_BIN=$(command -v python3.11 || command -v python3.10) ./install.sh`
- [ ] Verify install completed: `which dispatch` → `~/.local/bin/dispatch`
- [ ] Verify version file matches: `cat /ads_storage/$USER/.dispatch/installed_version` matches `cat VERSION`

## Level 1 — Safe Smoke (no job launch)

- [ ] `python3.10 -m compileall dispatch scr` → exit 0, no errors
- [ ] `python3.10 -m dispatch --help` → prints usage
- [ ] Launch Dispatch: `cd /path/to/sql/files && dispatch`
- [ ] **Dashboard renders:** stat cards (Running/Finished/Failed/Kerberos) visible
- [ ] **Kerberos indicator:** header shows TTL (e.g. "Kerberos: 7h 23m"), not "MISSING"
- [ ] **Version banner:** no mismatch warning if install is current
- [ ] **Navigate to New Job:** press `N` → form with RadioSet source/dest appears
- [ ] **Source × Destination matrix** visible and correct
- [ ] **Date fields** hidden unless SqlTemplate selected
- [ ] **Launch button** enabled (if Kerberos is healthy) or disabled (if missing)
- [ ] **Navigate back:** press `B` or `Esc` → returns to Dashboard
- [ ] **Navigate to History:** press `H` → history table with pagination
- [ ] **Pagination:** press `]` / `[` → pages change if enough jobs
- [ ] **Navigate back from History:** press `B` → Dashboard
- [ ] **Navigate to Browser:** press `B` on Dashboard → Browser screen
- [ ] **SHOW TABLES:** click button or enter → tables populate
- [ ] **Auto-describe:** first table auto-described with structured column view
- [ ] **Navigate back from Browser:** press `B` → Dashboard
- [ ] **Help screen:** press `?` → help modal with all keybindings appears
- [ ] **Close help:** press `Esc` or `?` → modal closes
- [ ] **Quit:** press `Q` → clean exit, bash prompt returns

## Level 2 — Real Environment Checks (no destructive actions)

- [ ] **Terminal rendering:** box-drawing characters, color, and styled text render correctly over SSH
- [ ] **Terminal size:** resize terminal below 80×24 → warning notification appears
- [ ] **CWD captured:** New Job form pre-fills SQL file from the launch directory
- [ ] **SQL file detection:** if a `.sql` file exists in CWD, source type auto-detected
- [ ] **Preview screen:** press `P` in New Job → SQL rendered with line numbers and keyword highlighting, scrollable
- [ ] **Browser DESCRIBE:** select a table, press Enter → columns shown as structured Name/Type/Comment table
- [ ] **Kerberos refresh:** press `K` in New Job → kinit prompt appears, TTL updates after
- [ ] **Empty dashboard:** with no jobs, empty-state text says "No active Jobs — press N to create one"
- [ ] **Event trail:** dashboard bottom shows startup event with timestamp
- [ ] **dispatch.log exists:** `cat ~/.dispatch/dispatch.log` shows startup entry

## Level 3 — Controlled Job Launch

**Use only a trivial smoke query to minimize risk.**

```sql
SELECT 1 AS smoke_test_value
```

- [ ] Create smoke SQL: `echo "SELECT 1 AS smoke_test_value" > /tmp/dispatch_smoke.sql`
- [ ] `cd /tmp && dispatch`
- [ ] Press `N` → New Job
- [ ] Source: SqlFile (default)
- [ ] Destination: Table
- [ ] SQL File: `/tmp/dispatch_smoke.sql`
- [ ] Schema: `aa_enc` (or `coe_enc`)
- [ ] Table Name: `dispatch_smoke_<user>_<date>`
- [ ] Email: your email
- [ ] Press `P` → Preview shows correct DDL wrapping the SELECT
- [ ] Press `Enter` (Accept) → back to New Job
- [ ] Press `L` → confirmation modal appears with job summary
- [ ] Confirm launch → "Launched Job" toast appears
- [ ] Dashboard shows job as RUNNING with elapsed time counting
- [ ] Wait for job to reach SUCCEEDED or FAILED
- [ ] If SUCCEEDED: press `V` → job detail shows logs, CSV path shows N/A (table-only)
- [ ] Navigate to Browser → SHOW TABLES → filter `dispatch_smoke_*` → smoke table visible
- [ ] Press `D` on smoke table → typed confirmation required → type full name → table dropped
- [ ] Clean up: `rm /tmp/dispatch_smoke.sql`

## Level 3b — Error Path Validation

- [ ] **Missing SQL file:** enter nonexistent path in New Job, press `P` → error message, no crash
- [ ] **Illegal combination:** select ExistingTable + Table → Table radio disabled
- [ ] **Concurrency cap:** with 2 running jobs, try to launch a 3rd → validation error
- [ ] **Cancel confirmation:** open a running job detail, press `C` → confirmation modal, cancel the cancellation
- [ ] **DROP confirmation:** in Browser, press `D` → must type exact table name, wrong name rejected

## Post-test

- [ ] Quit Dispatch
- [ ] Review `~/.dispatch/dispatch.log` for any unexpected errors
- [ ] Confirm no orphaned smoke tables remain
- [ ] Record terminal emulator name and SSH chain details for future reference
