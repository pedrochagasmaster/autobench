# Plan 015: Set a freshness policy for generated context bundles and fix stale AGENTS.md inventory

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat e0950c4..HEAD -- AGENTS.md README.md .gitignore scripts/build_master_context.py docs/`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P3
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: docs
- **Planned at**: commit `e0950c4`, 2026-06-10

## Why this matters

The generated context bundles (`docs/autobench_master_context*.md`, built by `scripts/build_master_context.py`) are snapshots: the current ones are stamped `Generated: 2026-06-08`, `Git status: dirty`, "Do not edit manually" — and they embed full doc/source copies that go stale on every commit. A stale committed bundle is worse than none for the audit/agent-handoff use case it serves. Separately, AGENTS.md's file tree omits live compliance docs (`control3_gap_matrix.md`, `control3_implementation_summary.md`, `EXECUTIVE_PRESENTATION_SCRIPT.md`) and describes the gate as "17+" scenarios when there are 18, and as "committed gate case definitions" while the runner actually regenerates `test_gate/*/cases.jsonl` on every run — contributors can't tell whether `test_gate/` diffs should be committed.

## Current state

- `docs/autobench_master_context.md:3-10` — header shows generation timestamp, source commit, and `Git status: dirty`. Three bundle files exist (`autobench_master_context.md`, `_docs.md`, `_code.md`); per the repo's git status at planning time they are **untracked** (never committed) — verify with `git status --short docs/`.
- `scripts/build_master_context.py` — the generator; `CORE_DOCS` list at ~lines 38-50 names the docs it bundles; it excludes its own output from re-inclusion (~lines 113-115).
- `README.md:381-389` — documents how to generate the bundle; no freshness policy stated.
- `AGENTS.md` file-structure block (~lines 130-190): docs/ subsection lists six entries, omitting the three named above; `test_gate/` is described as "Committed gate case definitions (portable)"; the gate is described as "Generates 17+ representative scenarios".
- `scripts/perform_gate_test.py` — `generate_cases()` always regenerates `test_gate` cases from `generate_cli_sweep.py --mode gate` before running (per audit; verify by reading the first ~60 lines).
- `.gitignore` — read it to see what's already excluded around docs/outputs.

## Commands you will need

| Purpose | Command | Expected on success |
|---------|---------|---------------------|
| Bundle status | `git status --short docs/` | shows whether bundles are tracked |
| Regen check | `py scripts/build_master_context.py` | exits 0, writes bundles |
| Full suite (sanity) | `py -m pytest tests/ -q` | all pass |

## Scope

**In scope**:
- `.gitignore`
- `AGENTS.md` (file-tree block, gate description, test_gate policy sentence)
- `README.md` (bundle freshness note)
- Deleting the untracked `docs/autobench_master_context*.md` files from the working tree (they are generated artifacts)

**Out of scope**:
- `scripts/build_master_context.py` — generator behavior is fine.
- `scripts/perform_gate_test.py` — regeneration behavior is fine; only the *description* is being fixed.
- Any other AGENTS.md content (business rules, algorithm docs).

## Git workflow

- Branch: `advisor/015-docs-policy`
- Commit message style: `docs: <imperative>`
- Do NOT push or open a PR unless instructed.

## Steps

### Step 1: Gitignore the generated bundles and remove working copies

Confirm the bundles are untracked (`git status --short docs/` shows `??` for them). Add to `.gitignore`:

```
# Generated agent/audit context bundles — regenerate with: py scripts/build_master_context.py
docs/autobench_master_context*.md
```

Delete the three working-tree files (`docs/autobench_master_context.md`, `docs/autobench_master_context_docs.md`, `docs/autobench_master_context_code.md`).

If the bundles turn out to be **tracked** (drift since planning), use `git rm --cached` instead of plain delete and note it in the commit message.

**Verify**: `git status` no longer shows the bundle files; `py scripts/build_master_context.py` still regenerates them on demand and they remain ignored.

### Step 2: State the freshness policy in README

In `README.md`'s "Additional Documentation" section (after the generation instructions ~line 381-389), add:

```markdown
The bundles are generated artifacts and are gitignored: always regenerate
immediately before an agent handoff or audit submission, and confirm the
header shows the expected commit and a clean git status.
```

**Verify**: `rg -n "regenerate" README.md` shows the new policy line.

### Step 3: Fix the AGENTS.md inventory

In the AGENTS.md file-structure block:
- Add the missing docs entries with one-line purposes: `control3_gap_matrix.md`, `control3_implementation_summary.md`, `EXECUTIVE_PRESENTATION_SCRIPT.md`. Cross-check the actual `docs/` directory listing first (`Get-ChildItem docs/`) and reconcile any other adds/removes you find — the tree must match reality at your HEAD.
- Change the bundle line to note bundles are generated and gitignored.
- Change "Generates 17+ representative scenarios" to the actual count (count rows: `Get-Content test_gate/share/cases.jsonl, test_gate/rate/cases.jsonl, test_gate/config/cases.jsonl | Measure-Object -Line` — expected 18; use whatever the real number is). Note: the "17+" string appears in **two** places in AGENTS.md — the file-structure block AND the "Running tests" section (~line 645, "Generates 17+ representative scenarios") — fix both (`rg -n "17\+" AGENTS.md` to find them all).
- Replace "Committed gate case definitions (portable)" with an explicit policy sentence: the gate runner regenerates `test_gate/*/cases.jsonl` from `generate_cli_sweep.py --mode gate` on every run; commit `test_gate/` diffs only when the generator logic changes intentionally. The "Generated-artifact policy" paragraph (~AGENTS.md:191) makes the same stale claim — align it too.

**Verify**: every file named in the AGENTS.md docs/ tree exists (`Test-Path` each), and the gate-count claim matches the jsonl line count.

### Step 4: Sanity check

**Verify**: `py -m pytest tests/ -q` → all pass (docs-only change; this is a regression tripwire, not a doc check).

## Test plan

None — docs and ignore rules. Verification is the greps/path checks above.

## Done criteria

- [ ] `docs/autobench_master_context*.md` gitignored and absent from `git status`
- [ ] README states the regenerate-before-handoff policy
- [ ] AGENTS.md docs/ tree matches the real `docs/` directory; gate case count is exact; `test_gate/` commit policy is explicit
- [ ] `py -m pytest tests/ -q` exits 0
- [ ] `plans/README.md` status row updated

## STOP conditions

- The bundles are tracked **and** other tooling (CI, scripts) reads them from the repo (grep `autobench_master_context` across the repo excluding docs/) — gitignoring would break that consumer; report.
- `docs/` contains files whose purpose you cannot determine for the tree description — list them as-is without invented descriptions and note the unknowns.

## Maintenance notes

- The audit considered a CI job that regenerates bundles and fails on diff; rejected for now (bundles are no longer committed, so there is nothing to drift). Revisit only if the maintainer decides bundles must ship in-repo.
- AGENTS.md's file tree will drift again; reviewers of structural PRs (new core modules, doc adds) should ask for tree updates.
