# Executive Presentation Script — Privacy-Compliant Peer Benchmark Tool

> **Format:** 7-minute executive presentation (descriptive + use-case focused).
> **Style:** McKinsey/BCG conventions — action titles (the title states the takeaway), the Pyramid Principle (answer first, then support), and MECE content blocks.
> **Runtime:** Budgeted to 7:00 across 8 slides.

---

## Deck overview

| # | Action title | Time | Cumulative |
|---|--------------|------|-----------|
| 1 | Title / framing | 0:20 | 0:20 |
| 2 | What it is (governing thought) | 0:55 | 1:15 |
| 3 | The compliance foundation: Control 3.2, enforced automatically | 0:55 | 2:10 |
| 4 | How it works: caps solved as an optimization | 0:55 | 3:05 |
| 5 | What you can configure: modes and presets | 0:55 | 4:00 |
| 6 | What it produces: explainable, shareable outputs | 0:50 | 4:50 |
| 7 | Where it's used: representative use cases | 1:15 | 6:05 |
| 8 | Summary: where the tool fits | 0:35 | 6:40 |
|   | Buffer / Q&A transition | 0:20 | 7:00 |

---

## SLIDE 1 — Title

**Header (action title):** A Single Engine for Privacy-Compliant Peer Benchmarking

**Sub-header:** Comparing entities against peer groups under Mastercard Control 3.2

**Visual description:**
- Clean title slide. Title bold on the left two-thirds; thin accent rule beneath.
- Right third: a simple motif — a target entity icon centered inside a ring of peer icons, with a lock badge denoting privacy compliance.
- Footer: presenter, role, date, "Confidential — Internal."

**On-slide text:**
- Title + sub-header only.

**Speaker script (~0:20):**
"I want to walk you through a tool we use to benchmark a financial entity — an issuer, bank, or merchant — against a peer group. What makes it distinctive is that it does this while enforcing Mastercard's Control 3.2 privacy rules automatically. Let me describe what it is, how it works, and where we put it to use."

---

## SLIDE 2 — What it is (governing thought)

**Header (action title):** It turns raw peer data into compliant, explainable benchmarks

**Sub-header:** One pipeline from input data to a defensible report

**Visual description:**
- Three-pillar layout under a single headline: **Ingest → Enforce → Explain**.
- Each pillar has an icon and a one-line descriptor.
- Pyramid framing: headline on top, three pillars beneath.

**On-slide text:**
- Ingest: aggregated transaction data in long format (CSV or SQL).
- Enforce: privacy caps applied automatically so no peer dominates.
- Explain: outputs document every weighting and compliance decision.
- Available via command line (CLI) and a guided interface (TUI).

**Speaker script (~0:55):**
"At its core, the tool does three things. First, it ingests aggregated transaction data — one row per entity and dimension, from a CSV or a SQL source. Second, it enforces privacy: it computes peer weights so that no single peer dominates the comparison beyond what the rules allow. Third, it explains itself — every output documents which weights were applied, which rule was used, and how compliance was met. It's the same engine whether you drive it from the command line or from the guided interface, so the analysis is consistent regardless of who runs it or how."

---

## SLIDE 3 — The compliance foundation

**Header (action title):** Control 3.2 is built in — the correct rule is selected by peer count

**Sub-header:** Privacy caps are enforced by design, not by manual checklist

**Visual description:**
- A clean reference table of the rule set (rule, minimum peers, max concentration).
- A small concentration chart: one peer towering over others (raw) versus capped bars under a dashed "max concentration" line (enforced).
- Lock icon labeled "Auto-selected by peer count."

**On-slide text:**
- 5/25 · 6/30 · 7/35 · 10/40 — selected automatically by number of peers.
- 4/35 — merchant benchmarking only.
- Higher-tier rules add participation requirements (e.g., minimum shares per peer).
- The engine refuses to silently bypass a cap; infeasibility is surfaced, not hidden.

**Speaker script (~0:55):**
"The foundation is compliance. Mastercard Control 3.2 defines a family of privacy rules — five-twenty-five, six-thirty, seven-thirty-five, ten-forty, and a four-thirty-five rule specific to merchants. Each sets a minimum number of peers and a maximum concentration any one peer can hold, and the higher tiers add extra participation requirements. The key point: the tool selects the correct rule automatically from the peer count, so it's not something an analyst has to remember or look up. And it won't quietly break a cap — if a comparison genuinely can't be made compliant, it tells you, rather than producing a number that looks fine but isn't."

---

## SLIDE 4 — How it works

**Header (action title):** Privacy caps are solved as an optimization, with graceful fallbacks

**Sub-header:** Keep results close to raw while guaranteeing compliance

**Visual description:**
- Left-to-right pipeline: **Data → Validate → Build privacy categories → Optimize weights → Report**.
- Beneath the optimize step, a three-stage funnel: **Global LP → Subset search → Bayesian fallback**.
- Caption: "Greedy mode is deterministic and reproducible."

**On-slide text:**
- Objective: minimize distortion from the raw data.
- Constraint: every peer's share stays under the privacy cap, in every category.
- Method: linear programming first; structured fallbacks when data is hard.
- Time-aware mode: a single weight set valid across all periods.
- Diagnostics explain why whenever a constraint can't be satisfied.

**Speaker script (~0:55):**
"Here's the mechanism, briefly. The tool frames compliance as an optimization problem: find the peer weights that keep every peer under the cap, in every category, while changing the underlying numbers as little as possible. It uses linear programming first. If the data is difficult, it steps down in a structured way — trying smaller dimension subsets, then a robust fallback — rather than failing outright. There's also a time-aware mode that holds one weight set valid across every period, which keeps longitudinal comparisons stable. And throughout, it produces diagnostics that explain exactly where and why any constraint couldn't be met."

---

## SLIDE 5 — What you can configure

**Header (action title):** Presets and modes let you match the analysis to the question

**Sub-header:** Intent is expressed once; the engine translates it into parameters

**Visual description:**
- Left column: **Analysis modes** (Share, Rate, Peer-only, Time-aware).
- Right column: **Presets** as labeled chips with a one-line intent each.
- A thin arrow from "Preset (intent)" to "Solver parameters (behavior)."

**On-slide text:**
- Modes: share, rate (approval/fraud), peer-only, time-aware consistency.
- Weighting: one global weight set, or per-dimension weights.
- Presets encode agreed intent:
  - compliance_strict — regulatory/audit reporting
  - strategic_consistency — single global weights for dashboards
  - low_distortion / minimal_distortion — accuracy-first
  - research_exploratory — sparse or difficult datasets

**Speaker script (~0:55):**
"The tool is configurable, but in a controlled way. There are a few analysis modes — share, rate (which covers approval and fraud), a peer-only mode with no target entity, and a time-aware mode. You can apply one consistent set of weights across all dimensions, or solve each dimension independently. Rather than tuning dozens of parameters by hand, analysts pick a preset that captures *intent* — 'strict compliance' for regulatory work, 'strategic consistency' for dashboards that need one stable weight set, 'low distortion' when accuracy matters most, 'exploratory' for sparse data. The engine translates that intent into the underlying solver settings, so the same intent produces the same behavior every time."

---

## SLIDE 6 — What it produces

**Header (action title):** Outputs are built to be shared and defended, not just read

**Sub-header:** From a stakeholder summary to a full audit trail

**Visual description:**
- A workbook graphic with labeled tabs: Summary · Per-dimension · Weight Methods · Rank Changes · Privacy Validation · Diagnostics.
- Beside it, format badges: **Excel · CSV · JSON**, plus a "Publication workbook" badge.

**On-slide text:**
- Summary sheet: inputs, parameters, and run metadata.
- Per-dimension results: balanced peer averages, best-in-class, target deltas.
- Transparency sheets: peer weights, solver used, rank changes, privacy validation.
- Formats: Excel, CSV, JSON; plus a clean publication workbook.
- Every run is timestamped and reproducible.

**Speaker script (~0:50):**
"The outputs are designed to be handed to someone else. There's a summary that captures the inputs and parameters, the per-dimension results — balanced peer averages, best-in-class benchmarks, and where the target sits relative to peers — and a set of transparency sheets: the actual peer weights, which solver was used, how rankings shifted, and the privacy validation per category. You can produce Excel, CSV, or JSON, plus a cleaned-up publication workbook for stakeholders. And because every run is timestamped and reproducible, the report *is* the audit trail."

---

## SLIDE 7 — Use cases (the focus)

**Header (action title):** The same engine supports regulatory, strategic, and exploratory work

**Sub-header:** Five representative scenarios across the benchmarking lifecycle

**Visual description:**
- A 5-row table: **Use case · Mode/Preset · What it answers.**
- Small icons per row (audit shield, dashboard, market, fraud, merchant) for fast scanning.

**On-slide text (table):**

| Use case | Mode / Preset | What it answers |
| --- | --- | --- |
| Regulatory / audit reporting | share + compliance_strict | "Is our benchmark defensible to a regulator or auditor?" |
| Executive dashboards | time-aware + strategic_consistency | "How does our entity track vs peers, consistently, month over month?" |
| Market / peer benchmarks (no target) | peer-only mode | "What is the market average and best-in-class across peers?" |
| Approval & fraud benchmarking | rate mode (fraud in bps) | "How do our approval and fraud rates compare to peers?" |
| Merchant benchmarking | 4/35 rule | "How does a merchant compare within a small, compliant peer set?" |

**Speaker script (~1:15):**
"Let me ground this in how it's actually used — five scenarios. First, regulatory and audit reporting: with the strict-compliance preset, we produce a benchmark where zero cap violations are tolerated and the full trail is captured, so it stands up to a regulator. Second, executive dashboards: using time-aware mode with the strategic-consistency preset, we hold one stable weight set across months, so the dashboard doesn't jump around period to period. Third, market benchmarks with no target entity — peer-only mode — where the question isn't 'how does *we* compare' but 'what does the market look like,' producing peer averages and best-in-class. Fourth, approval and fraud benchmarking through rate mode, with fraud expressed in basis points for the kind of comparison risk teams expect. And fifth, merchant benchmarking, where the four-thirty-five rule lets us work with a smaller peer set while staying compliant. Same engine, same compliance guarantees — different questions."

---

## SLIDE 8 — Summary

**Header (action title):** One compliant, explainable engine for every peer comparison we run

**Sub-header:** Where the tool fits in our workflow

**Visual description:**
- A simple recap band: **Ingest → Enforce Control 3.2 → Configure intent → Explainable output.**
- Beneath it, the five use-case icons from Slide 7, reinforcing breadth.

**On-slide text:**
- Privacy compliance is built in and automatic.
- Intent-driven presets make analyses consistent and repeatable.
- Outputs are transparent, reproducible, and audit-ready.
- Covers regulatory, strategic, market, rate, and merchant scenarios.

**Speaker script (~0:35):**
"To pull it together: this is one engine that takes peer data in, enforces Control 3.2 automatically, lets analysts express intent through presets, and produces outputs that are transparent and reproducible. Whether the work is regulatory, strategic, a market view, a rate comparison, or a merchant study, it's the same compliant foundation underneath. Happy to take questions or walk through any of those use cases in more detail."

---

## Delivery notes

- **Pace:** ~130 words/minute; Slide 7 is intentionally the longest since use cases are the focus. Trim Slide 4 first if you run long.
- **Anticipated Q&A:**
  1. "Can it bypass a cap if we ask it to?" → No — caps are enforced by design; infeasibility is surfaced via diagnostics.
  2. "What if there aren't enough peers?" → It selects the appropriate rule, or flags insufficiency rather than producing a non-compliant result.
  3. "Is a past run defensible later?" → Yes — runs are timestamped, parameterized, and reproducible (deterministic in greedy mode).
