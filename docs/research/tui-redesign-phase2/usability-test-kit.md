# TUI Redesign Phase 2: Usability Test Kit

This kit is for the owner to run a moderated test of the redesigned TUI with
**5 real operators**. It measures the same journeys as the keystroke study
(Phase 0 [02](../tui-redesign-phase0/02-journeys-keystrokes.md)), adds one
error-recovery task, and ends with the System Usability Scale (SUS). The
telemetry part (section 8) is what tells you, weeks later, whether the
redesign helps outside the lab.

Five users find most usability problems in a task-based test; they are **not**
enough for statistical claims about time or SUS. Report medians and ranges,
quote what people did and said, and treat the numbers as directional.

## 1. Setup (once, before the first session)

| Item | Value |
|---|---|
| Build | The release that contains Phase 2 PR 6. Note its `VERSION` on every sheet |
| Terminal | The operator's own terminal and SSH route if possible. Otherwise 120x40, then repeat task 1 at 80x24 for at least 2 users |
| Data | `docs/autobench_demo.csv` copied to a fresh folder, e.g. `~/usability/data/autobench_demo.csv` |
| Error file | `bad_demo.csv`: the demo with one negative `txn_cnt` (row 2: `120` → `-120`). The same fixture `scripts/tui_journeys.py` builds |
| Launch | `cd ~/usability && autobench` (fresh session file: delete `~/.benchmark_tui/session.yaml` before each user) |
| Recording | Screen recording or a second person timing and writing. No recording of the data itself is needed |
| Telemetry | Leave it on (the default). Sessions from the test have their own `app_version` window; exclude the test users or the test day from the field baseline (section 8) |

The run writes real reports. Use a scratch folder and delete it afterwards.
The demo file has no real institutions in it.

## 2. Consent note (read aloud, then ask for a yes)

> Thank you for helping. We are testing the software, not you. There are no
> wrong answers, and if something is hard, that is what we need to find.
> I will give you a few short tasks in the Autobench terminal app, using a
> demo file with made-up data. I will time each task and take notes on what
> happens on screen. I may ask you to think aloud. You can stop at any time
> and skip any task. Notes are kept with your initials only and are used to
> improve the tool. Is that OK?

Record: date, initials, role, years using Autobench (0 / <1 / 1+), CLI or TUI
user today, terminal and size.

## 3. Timing protocol

- **Start** the clock when you finish reading the task card and the operator
  looks at the screen. **Stop** it when the success criterion is visible on
  screen (the verdict and report path, or the end state named on the card).
- Do **not** help. If asked, say "What would you try?". After **2 minutes
  stuck** on one sub-step, or **5 minutes** on the whole task, give the
  scripted hint for that task and mark the task **assisted**.
- Count an **error** each time the operator: launches a run that is refused,
  answers a dialog the wrong way and has to redo it, picks a wrong column, or
  leaves the task path and has to come back.
- Note **every** time the operator says they are unsure about privacy or
  consent wording. These are the most important observations.
- After each task: "On a scale of 1 to 7, how easy was that?" (Single Ease
  Question, 7 = very easy).

Task outcome codes: **S** success unaided, **A** success with a hint,
**F** failed or abandoned.

## 4. Task scripts

Give each task as a printed card. Do not mention keys, step names or widget
names that are not on the card. Run them in this order; task 3 relies on the
session saved by task 1.

### Task 1 (J1): share benchmark

> Your manager wants a share benchmark for the issuer **Target** in the file
> `data/autobench_demo.csv`, broken down by **card type** and **input mode**.
> Use the standard (default) privacy settings. Run it, and tell me where the
> report was saved.

| | |
|---|---|
| Success | Run finishes with the verdict shown; operator reads out or copies the report path |
| Optimal path (measured) | 42 keys at 120x40 and 80x24 (`type(23) enter×2 down×7 enter tab×3 down×2 space down space ctrl+r`) |
| Watch for | Do they see the step rail and the action bar? Do they find the dimensions? Do they use Ctrl+R before they are done, and does the jump to the missing field help? Can they find the report path at 80x24 (Ctrl+T)? |
| Hint (after 2 min stuck) | "The bar at the bottom says what is still missing." |

### Task 2 (J2): rate benchmark with fraud

> Now a **rate** benchmark for **Target** with the same file: approval rate
> and fraud rate, using `total` as the denominator, by card type and input
> mode. The `total` column holds clearing-spend amounts.

| | |
|---|---|
| Success | Run finishes; operator confirmed the clearing-spend question deliberately (watch where focus was when they pressed Enter) |
| Optimal path | 62 keys |
| Watch for | Finding the Share/Rate switch; choosing Total/Approved/Fraud; reading the clearing-spend dialog. The dialog opens with **Cancel** focused: does the operator read it or press Enter twice? |
| Hint | "The mode is on step 3." |

### Task 3 (J3): re-run tomorrow with a different preset

Close the app (Ctrl+Q) and start it again before giving the card.

> It is the next morning. Re-run yesterday's **share** analysis for Target,
> but with the **strategic_consistency** preset.

| | |
|---|---|
| Success | Run finishes with preset `strategic_consistency` |
| Optimal path | 47 keys (39 with the command palette) |
| Watch for | Do they notice what was restored (marked ↺) and what was not (the target entity and declarations are never restored, on purpose)? Do they find the preset on step 4? Does anyone try Ctrl+P? |
| Hint | "Ctrl+P lists the steps." |

### Task 4 (J4b): recover from a data problem

Before the card, put `data/bad_demo.csv` in place.

> A colleague sends you `data/bad_demo.csv`. Run the same share analysis on
> it. If something is wrong with the data, find out what, then run it on the
> good file `data/autobench_demo.csv` instead.

| | |
|---|---|
| Success | Operator reads the validation issue (negative value in `txn_cnt`), cancels, points the app at the good file and the run finishes |
| Optimal path | 68 keys |
| Watch for | Does the validation dialog make the problem and the row clear? Do they know Proceed is unavailable because of an error? After Cancel, do they know where they are and how to change the file? |
| Hint | "The file path is on step 1." |

## 5. Observation sheet (one per user per task)

```
User ____  Task __  Size ____  Start __:__:__  Stop __:__:__  Time ____ s
Outcome  S / A / F      Hint given? __     SEQ (1-7) __
Errors (count + what):
  refused launch __  wrong dialog answer __  wrong column __  lost / back-tracked __
Keys noticed in use:  Tab  Shift+Tab  Ctrl+R  Ctrl+P  Ctrl+T  Ctrl+Y  Ctrl+G  F1  F8  mouse
Privacy/consent wording doubts (quote):

Where they hesitated (screen + what they said):

What worked well:

Severity of each problem seen (0-4, Nielsen):
```

## 6. SUS questionnaire (after all tasks)

Ask the operator to answer quickly, 1 = strongly disagree … 5 = strongly agree.

1. I think that I would like to use this system frequently.
2. I found the system unnecessarily complex.
3. I thought the system was easy to use.
4. I think that I would need the support of a technical person to be able to use this system.
5. I found the various functions in this system were well integrated.
6. I thought there was too much inconsistency in this system.
7. I would imagine that most people would learn to use this system very quickly.
8. I found the system very cumbersome to use.
9. I felt very confident using the system.
10. I needed to learn a lot of things before I could get going with this system.

**Scoring.** For odd items, score − 1. For even items, 5 − score. Sum the ten
values and multiply by 2.5 (range 0–100). Report each user's score, the
median and the range. As a reference point, 68 is the commonly cited
average; above 80 is good. With 5 users a single score moves the median a
lot, so read SUS together with the task outcomes.

Finish with two open questions: "What was the most confusing moment?" and
"What would you change first?"

## 7. Summarising the sessions

| Task | Success (S/A/F) | Median time (range) | Median errors | Median SEQ | Top problem (severity) |
|---|---|---|---|---|---|
| 1 J1 | | | | | |
| 2 J2 | | | | | |
| 3 J3 | | | | | |
| 4 J4b | | | | | |

SUS: per-user scores, median, range. Map each problem to a Phase 0
heuristic finding where one exists
([03](../tui-redesign-phase0/03-heuristic-review.md) and the re-review in
[00-results](00-results.md)), or log it as new with a severity.

## 8. Telemetry: baseline and follow-up windows

Telemetry already records closed-enum events only (05 §1.5). The friction
report needs no extra setup.

**Pull a window.** On a node that can read the shared store:

```bash
# Baseline: the last release BEFORE the redesign, TUI sessions only.
benchmark.py telemetry friction --days 28 --context tui --app-version <old VERSION>
# Follow-up: the redesign release, same window length.
benchmark.py telemetry friction --days 28 --context tui --app-version <new VERSION>
# Control: the CLI, which did not change, over the same two windows.
benchmark.py telemetry friction --days 28 --context cli_share --app-version <old VERSION>
benchmark.py telemetry friction --days 28 --context cli_share --app-version <new VERSION>
```

Add `--dir <telemetry parent>` if the store is not at the default shared path.
The report shows the funnel per action (INTENTS, BLOCKED, CANCELLED,
ATTEMPTED, COMPLETED, WITHHELD, REFUSED, FAILED, CANCEL_IN_RUN), refusals by
reason, launch blocks by reason, cancels by prompt and surface usage.

**Which numbers** (05 §6): headline **M1 run-intent success** = completed ÷
intents; M2 completion per attempt; M3 avoidable refusals; M5 no-intent
sessions; guardrail **G-a** compliance-policy refusals ÷ attempts must not
drop because of weaker enforcement.

**Comparability caveats.**
- A pre-v2 window counts no BLOCKED and fewer CANCELLED. For a v1-comparable
  M1, subtract BLOCKED from INTENTS (05 §8.9).
- Schema v4 moves "Citi competitor ticked, no Citibank entity" from REFUSED
  (`compliance_policy`) to BLOCKED (`citi_entity_missing`). Add those blocks
  back to the compliance-policy refusals before reading G-a (05 §8.11).
- Exclude the deployment day and the next 48 hours, and the usability-test
  sessions.

**Sample needed** (05 §6). Per period:

| change to detect | n per period |
|---|---|
| M1 0.55 → 0.70 | ≈ 160 run intents |
| M1 0.60 → 0.70 | ≈ 350 run intents |
| M3 0.20 → 0.10 | ≈ 200 attempts |
| M5 0.30 → 0.20 | ≈ 290 TUI sessions |

Do not report a ratio whose denominator is under 30 (the report marks those
with `*`). Require at least 10–15 distinct TUI users per period and report
per-user M1 as well; with a small fleet use a paired sign test across users
active in both periods (8/8, 9/10, 10/12 or 12/15 must improve at α = 0.05).
If the fleet produces fewer than about 150 TUI intents in 4 weeks, treat the
telemetry as directional and rely on this test.
