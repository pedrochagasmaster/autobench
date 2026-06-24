# Autobench Live Demo Runbook (Analyst Edition)

> **Audience:** Analysts / operators who will actually run the tool.
> **Format:** Live, hands-on walkthrough of the running tool (TUI + CLI + outputs).
> **Length:** 10–15 minutes (run sheet budgeted to ~13:00 + Q&A).
> **Environment:** Edge Node over SSH, launched with `autobench` (TUI) and
> `autobench-cli` (CLI).

This is an operator runbook, not a slide script. For executive framing decks,
see `docs/EXECUTIVE_PRESENTATION_SCRIPT.md` and
`docs/Autobench_v3.0_Precision_Compliance_PRESENTATION_SCRIPT.md`.

---

## The story arc (one line)

"You drive a guided run from the TUI, you read a compliant, explainable report,
and when you ask for something sensitive the tool stops you — then shows you the
one declaration that makes it compliant."

Three beats:

1. **Guided run** — the TUI does a privacy-compliant share analysis with no
   manual cap math.
2. **Explainable output** — the report states the verdict, the rule it picked,
   the peer weights, and the per-category privacy validation.
3. **Guardrails are real** — a fraud run is *blocked* until you declare the
   correct privacy basis; then it passes and produces an audit package.

---

## Pre-flight checklist (do this ~15 min before, off-screen)

Run these once so the live session is smooth. Do **not** improvise paths on
screen.

1. **Open the session and connect.**

```bash
# local laptop
tmux new -s autobench_demo        # or your usual psmux/tmux session
ssh -p 2222 <user>@<edge-node>
```

2. **Make sure the launchers resolve.**

```bash
export PATH="$HOME/.local/bin:$PATH"
which autobench
which autobench-cli
autobench-cli config list          # confirms presets load
```

If `autobench` is not found, run `./install.sh` from `/ads_storage/autobench`
first (see `docs/edge-node-first-time-setup.md`).

3. **If the workflow touches Kerberos-backed data**, initialize it now so a
   token prompt never appears mid-demo. (Not needed for the bundled fixture.)

```bash
kinit && klist
```

4. **Create a clean, writable working directory and stage the fixture.** This
   keeps the on-screen CSV path short and lets the TUI Browse dialog find it.

```bash
mkdir -p /ads_storage/$USER/demo
cp /ads_storage/autobench/tests/fixtures/gate_demo.csv /ads_storage/$USER/demo/
cd /ads_storage/$USER/demo
ls
```

5. **Size the terminal generously** (at least ~120x32). The TUI is a full-screen
   layout; a small window clips the panels.

6. **Do one silent dry run** of the exact share command (Appendix A1) to warm
   caches and confirm a `fully_compliant` verdict, then delete the outputs:

```bash
rm -f demo_*.xlsx demo_*.csv demo_*_audit.log benchmark_log_*.txt
```

7. **Pre-stage the workbook for the "read the output" beat.** You are on SSH —
   there is no Excel on the node. Before the session, copy one generated
   workbook back to your laptop and open it in Excel, ready on a second screen
   or browser tab:

```bash
# from your laptop
scp -P 2222 <user>@<edge-node>:/ads_storage/$USER/demo/demo_share.xlsx .
```

   During the live run you will point at the **terminal signals** and the TUI
   **Run Status / Last Run** panels, then flip to the pre-opened workbook to
   show what the analyst receives.

---

## Run sheet (≈13 minutes)

| Time | Beat | Surface |
|---|---|---|
| 0:00–1:00 | Framing: what this tool guarantees and what you'll see | talk |
| 1:00–6:00 | **TUI guided share run** (the everyday path) | `autobench` |
| 6:00–8:00 | Read the output: verdict, rule, weights, privacy validation | TUI panel + staged workbook |
| 8:00–11:00 | **CLI** for repeatable runs + the Control 3 policy gate | `autobench-cli` |
| 11:00–12:30 | Audit package + balanced CSV closer | `autobench-cli` |
| 12:30–13:00 | Recap + hand to Q&A | talk |

If you are tight on time, cut the audit-package beat first, then the
peer-only aside. Never cut the policy-gate beat — it is the most memorable.

---

## Beat 1 — Framing (0:00–1:00)

Say:

> "This is the same engine whether you run it from this guided interface or from
> the command line. It compares an entity against its peers while enforcing
> Mastercard Control 3.2 privacy caps **automatically** — you never hand-tune
> the caps. I'll run a real analysis, read the report, and then show you what
> happens when we ask for something the policy doesn't allow."

Then launch the TUI:

```bash
autobench
```

---

## Beat 2 — TUI guided share run (1:00–6:00)

The layout is **Configuration** on the left, **Activity** (Run Status / Last
Run / Log) on the right. Work top-down through the numbered sections.

1. **Section 1 · Data Source** — in **CSV file path**, type `gate_demo.csv`
   (it's in your working dir) and press **Enter**. Headers load; the meta line
   confirms the row/column count.
   - Say: *"It reads the headers immediately so I pick columns from dropdowns
     instead of typing them."*

2. **Section 2 · Entity**
   - **Entity ID column** → `issuer_name`
   - **Target entity** → `Target`
   - Say: *"Leaving the target blank runs a peer-only market view — same engine,
     no single entity in focus. I'll mention that again at the end."*

3. **Section 3 · Analysis Options**
   - **Time period column** → `year_month` (enables time-aware consistency: one
     weight set valid across both months).
   - **Output filename** → `demo_share.xlsx`
   - **Optimization preset** → `balanced_default`. Press **F1** for the Preset
     Guide if someone asks what the others do.
   - Leave **Validate input** and **Analyze impact** checked.
   - Say: *"The preset captures intent. `balanced_default` is the everyday
     choice; `compliance_strict` is for regulatory submissions."*

4. **Section 4 · Analysis Mode → Share Analysis tab**
   - **Primary metric column** → `txn_cnt`
   - Leave **Debug sheets** and **Export balanced CSV** checked.
   - **Manual dimension selection** → check `card_type` and `channel`.

5. **Run** — press **Ctrl+R** (or click **▶ Run Analysis**).
   - Watch the right pane: input validation passes first, then the log shows the
     privacy rule being selected and the optimizer solving.
   - Call it out live: *"It validated the input before computing, picked the
     **6/30** rule from the peer count on its own, and solved for weights that
     keep every peer under 30% in every category."*

> **Keyboard cheat:** `Ctrl+O` open CSV · `Ctrl+R` run · `F1` preset guide ·
> `Ctrl+A` advanced panel · `Ctrl+E` export overrides · `Ctrl+L` clear log.

---

## Beat 3 — Read the output (6:00–8:00)

The node has no Excel, so read results in two places:

- **TUI Run Status / Last Run panels** show success and the saved report path.
- **Flip to the pre-staged workbook** on your laptop and walk these sheets:
  - **Summary** — point to **Input Validation: pass** and **Compliance Verdict:
    fully_compliant**, plus the inputs/preset captured for reproducibility.
  - **`card_type` / `channel` sheets** — target vs. balanced peer average, the
    percentage-point gaps, and best-in-class.
  - **Weight Methods** — which strategy was used per dimension (Global-LP here).
  - **Privacy Validation** (debug) — per-category concentration checks; this is
    the proof the caps held.

Say:

> "The report *is* the audit trail. Anyone can see which rule applied, what the
> peer weights were, how ranks shifted, and that every category passed — without
> being able to back out any single peer's position."

---

## Beat 4 — CLI + the Control 3 policy gate (8:00–11:00)

Switch to the shell. First show that the same run is a one-liner for automation:

```bash
autobench-cli share \
  --csv gate_demo.csv \
  --entity Target \
  --metric txn_cnt \
  --dimensions card_type channel \
  --time-col year_month \
  --preset balanced_default \
  --output demo_share_cli.xlsx
```

Say: *"Same engine, same verdict — this is what a scheduled pipeline runs."*

**Now the memorable beat — the guardrail.** Ask for a fraud-rate benchmark
*without* declaring the privacy basis:

```bash
autobench-cli rate \
  --csv gate_demo.csv \
  --entity Target \
  --total-col total --approved-col approved --fraud-col fraud \
  --dimensions card_type channel \
  --time-col year_month \
  --preset balanced_default \
  --output demo_rate.xlsx
```

It **blocks** with `fraud_chargeback_requires_clearing_spend_basis`.

Say:

> "That's not a bug — it's policy enforcement. Control 3 requires fraud and
> chargeback benchmarking to be done on a clearing-spend basis. The tool refuses
> to silently produce a number on the wrong basis. I declare the basis and it
> proceeds."

Re-run with the one declaration that satisfies the gate:

```bash
autobench-cli rate \
  --csv gate_demo.csv \
  --entity Target \
  --total-col total --approved-col approved --fraud-col fraud \
  --privacy-basis clearing_spend \
  --dimensions card_type channel \
  --time-col year_month \
  --preset balanced_default \
  --export-balanced-csv \
  --output demo_rate.xlsx
```

Now it prints **Compliance Verdict: fully_compliant**, writes the workbook, and
exports a balanced CSV that is cross-validated against the workbook.

> **Why this is a CLI beat, not a TUI beat:** the TUI doesn't expose a
> privacy-basis control, so fraud runs are driven from the CLI (or a config
> file). If asked, say: *"Approval-rate and share runs go through the TUI;
> fraud/chargeback runs declare the basis on the command line or in config."*

---

## Beat 5 — Audit package + BI closer (11:00–12:30)

Show that any run can be packaged for review in one flag:

```bash
autobench-cli share \
  --csv gate_demo.csv \
  --entity Target \
  --metric txn_cnt \
  --dimensions card_type channel \
  --time-col year_month \
  --preset compliance_strict \
  --compliance-posture strict \
  --audit-package \
  --output demo_audit.xlsx
```

It writes `demo_audit_audit_package.zip` (workbook(s), balanced CSV when
exported, audit log, redacted config snapshot, validation summary).

Say:

> "For a regulatory submission you switch the preset to `compliance_strict` and
> add `--audit-package`. That bundles everything a reviewer needs to reproduce
> the run, with secrets redacted. And the balanced CSV from the rate run drops
> straight into Power BI or Tableau."

---

## Beat 6 — Recap (12:30–13:00)

> "Three things to remember: the caps are enforced automatically and chosen by
> peer count; every output explains itself and is reproducible; and the policy
> gates stop a non-compliant run instead of hiding it. Same engine in the TUI
> you'll use day to day and in the CLI a pipeline runs."

Then take questions.

---

## Fallbacks & troubleshooting (keep this visible)

| Symptom | Cause | On-screen fix |
|---|---|---|
| `autobench: command not found` | `~/.local/bin` not on PATH | `export PATH="$HOME/.local/bin:$PATH"` (or open a new SSH session) |
| Output write fails | Working dir not writable | Run from `/ads_storage/$USER/demo` or write to `/tmp` |
| TUI looks clipped/garbled | Terminal too small | Resize to ≥120x32 and relaunch `autobench` |
| Headers don't load in TUI | Didn't commit the path | Click into **CSV file path**, press **Enter** |
| Fraud run "fails" | **Expected** — policy gate | This is the demo beat; add `--privacy-basis clearing_spend` |
| Token prompt mid-run | Kerberos not initialized | `kinit` before the session (pre-flight step 3) |
| Lost the TUI | Background analysis still running | It runs in a thread; the panel stays responsive — wait for the log |

If the live tool misbehaves entirely, fall back to narrating the pre-staged
workbook and the saved terminal output from your dry run.

---

## Appendix A — Copy/paste commands (Edge Node)

All commands assume `cd /ads_storage/$USER/demo` with `gate_demo.csv` staged.

**A1 — Guided share equivalent (dry-run / CLI):**

```bash
autobench-cli share --csv gate_demo.csv --entity Target --metric txn_cnt \
  --dimensions card_type channel --time-col year_month \
  --preset balanced_default --output demo_share.xlsx
```

**A2 — Peer-only market view (no target):**

```bash
autobench-cli share --csv gate_demo.csv --metric txn_cnt \
  --dimensions card_type channel --time-col year_month \
  --preset balanced_default --output demo_peeronly.xlsx
```

**A3 — Fraud rate, blocked (the guardrail):**

```bash
autobench-cli rate --csv gate_demo.csv --entity Target \
  --total-col total --approved-col approved --fraud-col fraud \
  --dimensions card_type channel --time-col year_month \
  --preset balanced_default --output demo_rate.xlsx
```

**A4 — Fraud rate, compliant (basis declared):**

```bash
autobench-cli rate --csv gate_demo.csv --entity Target \
  --total-col total --approved-col approved --fraud-col fraud \
  --privacy-basis clearing_spend --dimensions card_type channel \
  --time-col year_month --preset balanced_default \
  --export-balanced-csv --output demo_rate.xlsx
```

**A5 — Strict run with audit package:**

```bash
autobench-cli share --csv gate_demo.csv --entity Target --metric txn_cnt \
  --dimensions card_type channel --time-col year_month \
  --preset compliance_strict --compliance-posture strict \
  --audit-package --output demo_audit.xlsx
```

> Local-machine fallback (this Windows dev box): replace `autobench-cli` with
> `py benchmark.py` and use backslash paths, e.g.
> `--csv tests\fixtures\gate_demo.csv`.

---

## Appendix B — The fixture at a glance (`gate_demo.csv`)

- Columns: `issuer_name, year_month, card_type, channel, txn_cnt, total,
  approved, fraud`.
- 1 target (`Target`) + 6 peers (`P1`–`P6`) across 2 months (`2024-01`,
  `2024-02`), dimensions `card_type` (CREDIT/DEBIT) and `channel`
  (Online/Store).
- With a target present there are 6 peers → engine auto-selects the **6/30**
  rule. Peer-only adds the former target back as a peer → 7 peers → **7/35**.
- `P1` is intentionally the dominant peer, so the cap visibly bites (its share
  is pulled down to the 30% cap). That makes the privacy enforcement easy to
  point at.

---

## Appendix C — Likely analyst questions

- **"Do I ever set the caps myself?"** No. The rule is chosen from the peer
  count; you choose intent via a preset.
- **"What if there aren't enough peers?"** It selects the appropriate rule or
  flags insufficiency rather than producing a non-compliant result.
- **"Can I force a blocked run through?"** No. Policy gates (fraud basis,
  top-merchant output, digital-wallet/dual-axis review) are enforced or require
  recorded approval; they aren't silently bypassed.
- **"Where do my outputs go?"** Wherever you point `--output` (and the balanced
  CSV beside it). Retrieve them with `scp` or a shared mount to open in Excel.
- **"Is an old run defensible later?"** Yes — runs are timestamped,
  parameterized, and reproducible; `--audit-package` bundles the evidence.

---

## Reset between runs / after the demo

```bash
cd /ads_storage/$USER/demo
rm -f demo_*.xlsx demo_*.csv demo_*_audit.log demo_*_audit_package.zip benchmark_log_*.txt
```
