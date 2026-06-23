# Autobench v3.0 Precision Compliance - Presentation Script

> Source deck: `docs/Autobench_v3.0_Precision_Compliance.pdf`
>
> Scope note: this script follows the PDF export. The matching PPTX contains
> hidden slides, but those slides are not scripted here because they are excluded
> from the PDF that will be presented.
>
> Recommended runtime: 10 to 12 minutes, plus Q&A.
>
> Core message: Autobench turns privacy-compliant benchmarking from a manual,
> senior-dependent exercise into a controlled optimization workflow: compliant by
> construction, low-distortion by design, and audit-ready by default.

---

## Presenter Frame

### One-Sentence Version

"Autobench is a precision compliance engine that turns raw peer data into
privacy-compliant, low-distortion, audit-ready performance benchmarks."

### Narrative Spine

1. Peer benchmarking has a structural problem: privacy caps protect peers, but
   manual balancing can damage market truth.
2. Autobench resolves that problem mathematically through constrained
   optimization.
3. The workflow is operational, not theoretical: guided analyst experience,
   policy gates, diagnostics, BI-ready exports, and audit packages.
4. The business result is faster delivery, lower compliance risk, and a scalable
   foundation for products like the A&F dashboard.

### Tone

Use an executive, confident tone. Do not over-explain the math. The audience
should leave with a clear business conclusion: this is a governed analytical
engine, not a spreadsheet automation utility.

### Presenter Cheat Sheet

Terminology to keep straight:

- **Control 3** is the broader customer/merchant performance policy family;
  **Control 3.2** is the concentration-cap provision the engine enforces
  (minimum peers plus a maximum single-peer share). The deck uses both terms.
  Treat "Control 3.2" as shorthand for the privacy caps.
- **A&F** reads as Authorization & Fraud (the dashboard's core metric families:
  authorization rates and fraud rates). Confirm the house definition before
  presenting.

Numbers to know cold (Slide 9), since this is where executives push back:

- Balancing time per peer: ~5-7 days falls to ~1-2 days (average 6 to 1.5).
- ~75% average reduction in balancing time per peer.
- 5-peer project: ~30 days to ~7.5 days. 6-peer project: ~36 days to ~9 days.
- These are balancing-phase gains. Data extraction time is unchanged.

One honesty guardrail: Slide 8 reads "cryptographically verifiable audit
trails." The package is verified today by completeness and reproducibility, not
by a signature. See the Slide 8 presenter note and the Q&A entry before you
present.

---

## Slide Timing

| PDF page | Slide | Time | Cumulative | What the audience should remember |
|---:|---|---:|---:|---|
| 1 | Title | 0:45 | 0:45 | Autobench is the compliance engine behind scalable peer benchmarking. |
| 2 | Compliance paradox | 1:25 | 2:10 | The hard problem is preserving market truth while enforcing privacy caps. |
| 3 | Architecture | 1:05 | 3:15 | The system has a simple path: ingest, optimize, publish evidence. |
| 4 | Analyst experience | 1:00 | 4:15 | The TUI makes compliant execution repeatable for analysts. |
| 5 | Distortion visibility | 1:10 | 5:25 | Compliance impact is measured in percentage points, not guessed. |
| 6 | Policy enforcement | 1:20 | 6:45 | The workflow separates enforceable rules, approval gates, and hard blocks. |
| 7 | Deliverables | 1:10 | 7:55 | Outputs serve three audiences: decision makers, BI users, and auditors. |
| 8 | Value realization | 1:05 | 9:00 | The advantage is compliance, better math, and operating leverage. |
| 9 | Efficiency and scalability | 1:20 | 10:20 | The balancing phase drops by roughly 75%. |
| 10 | A&F field use case | 1:35 | 11:55 | The A&F dashboard shows how the engine becomes a scalable market product. |
| 11 | Blank page | 0:00 | 11:55 | No content. Use only as an end state. |

Content runs ~11:55. The opening paragraph overlaps Slide 1, so deliver it inside
that 0:45 or add ~0:30 if you speak it before advancing. If you run long, trim
Slide 6 or Slide 2 first.

---

## Opening

Use this before advancing into the deck, or as the first spoken paragraph on
slide 1.

"Today I will walk through Autobench v3.0, our precision compliance engine for
peer benchmarking.

The simple version is this: Autobench lets us compare an entity against a peer
group while enforcing privacy rules mathematically. It protects peer
confidentiality, preserves as much market signal as possible, and creates the
evidence trail needed to defend the result."

---

## Slide 1 - Autobench: The Precision Compliance Engine

**Purpose:** Establish the category. Autobench is not just a reporting tool; it
is the engine that makes compliant benchmarking scalable.

**On-slide message:** Next-generation benchmarking. Minimal distortion. Absolute
control.

**Speaker script:**

"Autobench exists because peer benchmarking has become too important to run as a
manual balancing exercise.

When we benchmark an issuer, acquirer, merchant, or market segment, we need two
things at the same time. The result has to be analytically useful, and it has to
protect the confidentiality of every peer in the comparison.

Those requirements can pull against each other. If we enforce privacy too
bluntly, we lose market truth. If we preserve market truth too casually, we risk
violating concentration caps.

Autobench is the engine built for that exact tension. It takes raw peer data,
applies Control 3 privacy constraints, solves the balancing problem
mathematically, and produces outputs that analysts can explain and auditors can
review.

So the promise of this deck is the subtitle: next-generation benchmarking,
minimal distortion, and absolute control."

**Emphasize:** "engine" and "mathematically." This frames Autobench as governed
infrastructure, not a convenience script.

**Transition:** "The reason this matters starts with the compliance paradox."

---

## Slide 2 - The Compliance Paradox

**Purpose:** Make the business problem feel unavoidable. The slide should land
as the reason Autobench needs to exist.

**On-slide message:** Compliant benchmarking forces a trade-off between privacy
and market truth. Autobench resolves it mathematically, not manually.

**Speaker script:**

"This is the core problem.

Control 3 constraints exist to prevent a benchmark from exposing or over-weighting
any individual peer. We need concentration caps. We need minimum participant
thresholds. And we need confidence that the published benchmark is not only
useful, but compliant.

At the same time, the business needs market reality. The benchmark has to
preserve positioning, rank integrity, and performance differences that matter
for commercial decisions.

That creates the paradox. The privacy rules protect the benchmark, but applying
them manually can distort the benchmark.

In a manual workflow, an analyst adjusts peer weights, checks the caps, adjusts
again, checks again, and then has to explain why the final result is still
representative. That process is slow, inconsistent, and hard to audit.

Autobench changes the operating model. It treats compliance as a constrained
optimization problem. The engine searches for weights that satisfy the privacy
caps while keeping the balanced result as close as possible to the raw market
data.

That is the shift: compliance is not a final inspection step. It is embedded in
the calculation itself."

**Emphasize:** The phrase "not a final inspection step." That is the slide's
main executive takeaway.

**Transition:** "The architecture is built around that idea: ingest, enforce,
and publish evidence."

---

## Slide 3 - Architecture

**Purpose:** Show that the concept is implemented as a coherent workflow, not as
isolated scripts.

**On-slide message:** Three coordinated phases turn raw data into audit-ready
intelligence.

**Speaker script:**

"The architecture is deliberately simple at the top level.

Phase one is ingestion. The tool can be used through automated pipelines, the
CLI, or the analyst workbench. The goal is to bring the data into a normalized,
validated structure before any benchmark is calculated.

Phase two is the core engine. This is where Autobench applies schema validation,
Control 3.2 privacy validation, and global linear-programming optimization. The
important point is that the solver is not calculating a simple peer average. It
is solving for compliant peer weights across the categories in scope.

Phase three is output. Autobench produces Excel reports, diagnostic sheets,
balanced CSV exports, and audit packages. That turns the analysis from a result
into a defensible artifact.

This gives us a clean chain of custody. We know what data went in, what privacy
rules were applied, how the weights were chosen, and what evidence was produced
for review."

**Emphasize:** "chain of custody." It connects architecture to auditability.

**Transition:** "The next question is how analysts interact with that engine in
practice."

---

## Slide 4 - Analyst Experience

**Purpose:** Prove that the tool can be adopted operationally. The interface
reduces friction and standardizes execution.

**On-slide message:** A robust TUI eliminates pure-CLI friction.

**Speaker script:**

"The analyst experience matters because compliance only scales if the workflow
is repeatable.

The TUI gives analysts a guided path through the run. First, it is
validation-first. Before the heavy computation starts, it checks for nulls,
schema errors, and peer-constraint issues. That catches bad inputs before they
become bad outputs.

Second, configuration is controlled. Analysts select the file, entity, metrics,
dimensions, presets, and output mode in a structured interface rather than
rebuilding a command from memory.

Third, diagnostics are visible while the run is happening. The analysis executes
in the background, the interface remains responsive, and logs are surfaced in
the tool.

Fourth, advanced overrides are still available for expert users. The difference
is that those overrides live inside a governed workflow.

The business benefit is consistency. The same analysis intent produces the same
behavior, even when different analysts run it."

**Presenter note:** If someone asks how expert overrides are exposed, the TUI's
advanced panel toggles on with Ctrl+A. The point to make is that expert controls
live inside the guided workflow, not beside it.

**Emphasize:** The TUI is not only usability; it is standardization.

**Transition:** "Once the benchmark is produced, the next question is how much
the privacy balancing moved the market signal."

---

## Slide 5 - Distortion Visibility

**Purpose:** Make the analytics quality argument. Autobench does not hide the
trade-off created by privacy caps; it quantifies it.

**On-slide message:** Every percentage point of distortion is measured, not
assumed.

**Speaker script:**

"This is one of the most important parts of the tool.

Autobench does not just say, 'the benchmark is compliant.' It also tells us what
compliance cost analytically.

For each category, the tool compares raw market share with the balanced,
compliant share. The difference is reported as distortion in percentage points.
That gives analysts a direct way to answer: how much did the privacy constraint
move the result?

The tool also tracks rank changes. If weighting changes the ordering of peers or
categories, that is recorded. That matters because rank movement is often where
stakeholders first challenge the result.

Preset comparison adds another layer. Analysts can compare configurations and
see which one produces the lowest mean distortion while still respecting the
rules.

The takeaway is that Autobench makes the trade-off visible. It does not hide the
cost of compliance inside a black box. It exposes the cost so the team can make
a better decision and defend that decision later."

**Emphasize:** "what compliance cost analytically." That is the sharpest framing
for this slide.

**Transition:** "Mathematical compliance is necessary, but it is not the whole
policy picture. Some cases require governance controls."

---

## Slide 6 - Policy Enforcement

**Purpose:** Show that Autobench understands the boundary between automated
math, required approval, and prohibited output.

**On-slide message:** The system actively guards against unauthorized data
combinations.

**Speaker script:**

"This slide is about policy controls beyond the numeric cap calculation.

Some requirements can be enforced directly by the system. Fraud and chargeback
analysis is an example. The run must declare the correct privacy basis:
clearing spend. If that condition is not present, the workflow blocks the run.

Some requirements need explicit Privacy review. Digital wallet analysis and
dual-entity-axis analysis fall into that category. The tool cannot replace the
governance decision, but it can require evidence that the decision happened.

And some outputs are simply not allowed. Top-merchant lists are hard-blocked
because they are outside the permitted policy posture.

That separation is important. Autobench does not pretend every compliance
question can be reduced to a formula. It separates enforceable controls, manual
approval gates, and prohibited outputs.

That is what makes the workflow credible. The tool automates what should be
automated, and it forces explicit review where human governance is required."

**Emphasize:** "automates what should be automated." This avoids overclaiming.

**Transition:** "Once the run clears those controls, the output has to serve
multiple audiences."

---

## Slide 7 - Deliverables

**Purpose:** Position the outputs as a complete operating package: decision
artifact, data product, and audit evidence.

**On-slide message:** Actionable intelligence, packaged for decisions and for
audit.

**Speaker script:**

"Autobench produces three deliverable types.

The Excel report is the primary decision artifact. It gives stakeholders the
summary, run metadata, category comparisons, target versus best-in-class views,
rank changes, and weight methods.

The balanced CSV is the data product. It is designed for Tableau, Power BI, and
other downstream workflows. It can carry raw share, balanced share, distortion,
and other calculated metrics. Just as important, it is validated for parity with
the Excel report.

The audit package is the evidence layer. It captures inputs, configuration, and
logs so the run can be reproduced and reviewed.

The point is that Autobench does not stop at calculation. It packages the result
for the people who need to use it: executives who need a conclusion, analysts
who need data, and reviewers who need evidence."

**Emphasize:** "decision artifact, data product, evidence layer."

**Transition:** "Those deliverables are what convert the engine into business
value."

---

## Slide 8 - Value Realization

**Purpose:** Synthesize the value proposition into three executive pillars:
compliance, analytical quality, and operating leverage.

**On-slide message:** Autobench turns regulatory constraint into analytical
advantage.

**Speaker script:**

"The value realization comes from three places.

First, absolute compliance. The engine is built around Control 3.2 privacy caps,
and the output trail is designed for review. That lowers the risk of inconsistent
manual application.

Second, mathematical superiority. The solver minimizes distortion instead of
relying on manual balancing judgment. That lets us keep more of the market signal
while still enforcing the privacy rules.

Third, operational agility. The TUI makes the workflow accessible. Lean execution
keeps it practical in memory-limited environments. And the deliverables are
ready for both stakeholder review and downstream analysis.

So the larger point is this: compliant data is no longer a compromise. If we can
measure the constraint, optimize around it, and document the result, compliance
becomes part of analytical quality."

**Presenter note:** The slide reads "cryptographically verifiable audit trails."
The script deliberately says the output trail is "designed for review" because
today the audit package is verified through completeness and reproducibility, not
a cryptographic signature. If anyone presses on the slide wording, use the
audit-trail answer in Q&A instead of defending a signing claim.

**Emphasize:** The final sentence. It is the strategic claim of the presentation.

**Transition:** "The next slide quantifies the operational side of that value."

---

## Slide 9 - Efficiency and Scalability

**Purpose:** Translate technical automation into time saved, staffing leverage,
and market-wide scalability.

**On-slide message:** Automating the balancing phase cuts benchmark time by
about 75%.

**Speaker script:**

"This slide shows the operating impact.

The extraction step still exists. We still need the right source data and the
right peer definitions. The major gain is in balancing, which was previously the
most manual and senior-dependent part of the process.

Before Autobench, balancing one peer could take roughly five to seven days. With
the tool, that becomes roughly one to two days. On average, that is about a 75%
reduction in balancing time per peer.

The effect compounds when we move from one peer to a market-wide study. A
five-peer project that previously required about 30 days of balancing effort can
move toward about 7.5 days. A six-peer project can move from roughly 36 days to
about 9 days.

That changes the operating model. Large benchmark studies no longer need to be
treated as bespoke spreadsheet exercises. They can be executed as repeatable
analytical runs, with senior time redirected toward interpretation, client
strategy, and higher-value advisory work."

**Emphasize:** This is not just cycle-time reduction; it is a staffing and scale
change.

**Transition:** "The final content slide shows what this looks like in a field
use case."

---

## Slide 10 - Use Case in the Field: A&F Dashboard

**Purpose:** Ground the engine in a concrete product use case and show the path
from tool to market-facing capability.

**On-slide message:** A&F Dashboard - scalable benchmarking for the LAC market.

**Speaker script:**

"The A&F dashboard is where the story becomes concrete.

The first foundation is peer readiness. The dashboard uses pre-defined peer
groups for issuers and acquirers, with 14 months of history from January 2025
through February 2026. Brazil is live, and the broader LAC rollout is underway.

The second foundation is metric depth. The dashboard can support raw and clean
authorization rates, fraud rates, declined-reason share, count and amount views,
credit and debit splits, card-present and card-not-present cuts, domestic and
cross-border cuts, tokenization, 3DS, MCC, ticket size, and more.

The third foundation is ACS impact. Autobench reduces effort on the hardest
parts of the workflow: extraction, peer grouping, compliant balancing, and
repeatable output production. That frees senior people to focus on diagnosis,
recommendations, and client value.

This also opens the door to a stronger commercial model: A&F Report as a
Service. Instead of rebuilding each benchmark manually, we can scale a governed
benchmarking engine across markets and peer groups.

That is the broader significance of Autobench. It is not only improving one
analysis process. It creates reusable infrastructure for privacy-compliant
performance analytics."

**Closing script:**

"To close: Autobench solves the core tension in peer benchmarking. It protects
privacy, preserves market signal, quantifies distortion, creates audit evidence,
and reduces the manual effort required to scale. That is why it is best thought
of as a precision compliance engine, not just a reporting tool."

**Transition to Q&A:** "I will pause there. I am happy to go deeper on the
optimization method, the Control 3 policy gates, or the A&F dashboard rollout."

---

## Slide 11 - Blank Final Page

No spoken content is required.

If the blank page appears, use it as a neutral Q&A screen:

"I will pause there and take questions."

---

## Condensed Version (One Line Per Slide)

Use this if the slot is cut short. Each line is the spoken spine for its slide.
Read straight through, this runs about three to four minutes; add one supporting
sentence per slide and it fills a five-to-seven-minute slot.

**Slide 1:** "Autobench is our precision compliance engine for peer
benchmarking. It compares entities against peer groups while enforcing privacy
rules mathematically."

**Slide 2:** "The central problem is the compliance paradox. We need privacy
caps, but we also need market truth. Manual balancing is slow, inconsistent, and
hard to defend."

**Slide 3:** "The workflow is simple: ingest the data, optimize compliant peer
weights, and produce evidence-rich outputs."

**Slide 4:** "The TUI makes that workflow repeatable for analysts. It validates
inputs, structures configuration, and surfaces diagnostics."

**Slide 5:** "Autobench measures distortion directly. It shows how far the
balanced result moved from the raw market share."

**Slide 6:** "The policy layer separates what can be enforced automatically,
what needs Privacy review, and what must be blocked."

**Slide 7:** "The deliverables serve three audiences: Excel for decisions, CSV
for BI workflows, and audit packages for review."

**Slide 8:** "The result is compliance, better math, and operational agility."

**Slide 9:** "Operationally, the balancing phase falls by about 75%, which
changes staffing and scalability."

**Slide 10:** "The A&F dashboard shows the field application: reusable peer
groups, deep performance metrics, and a path to A&F Report as a Service."

**Close:** "Autobench turns privacy-compliant benchmarking from a manual process
into reusable analytical infrastructure."

---

## Q&A Prep

### Q: What is the simplest way to describe Autobench?

"It is a controlled benchmarking engine. It takes peer data, enforces privacy
caps, minimizes distortion, and produces an audit-ready benchmark."

### Q: What is the advantage over manual weighting?

"Manual weighting depends on analyst judgment and repeated checking. Autobench
solves the same problem as constrained optimization, which makes the result more
repeatable, more transparent, and easier to defend."

### Q: Does Autobench ever bypass a privacy cap to produce an answer?

"No. Privacy caps are constraints. If a compliant result cannot be produced, the
system surfaces that through diagnostics or policy gates rather than silently
publishing a non-compliant benchmark."

### Q: Why is distortion visibility important?

"A compliant benchmark can still be analytically weak if the balancing moved the
data too far. Distortion visibility shows exactly how much the compliant result
differs from the raw market data."

### Q: Why are some policy items manual approval gates?

"Because some requirements are governance decisions, not mathematical
conditions. The tool can require and record approval evidence, but it should not
pretend to replace Privacy review."

### Q: What makes the output audit-ready?

"The run captures inputs, configuration, weights, solver methods, rank changes,
privacy validation, and logs. That gives reviewers a clear path from source data
to published benchmark."

### Q: Is the audit trail cryptographically signed or verifiable?

"The audit package captures everything needed to verify a run independently: the
report, the balanced CSV, the run log, a redacted configuration snapshot, and a
validation summary, all in one timestamped archive. The verification model today
is reproducibility. Anyone can rerun the captured configuration and get the same
result. Sensitive fields like connection strings and passwords are redacted
before packaging. If a deployment needs cryptographic signing or hashing on top
of that, it can be layered on. The package is built to carry it."

### Q: How solid is the 75% time-savings figure?

"It comes from measured balancing-phase effort, not a projection. Balancing one
peer dropped from roughly five-to-seven days of manual work to one-to-two days
with the tool, which is about 75% on the average case. Extraction time is
unchanged, so the headline is specifically about the balancing phase, which was
the most manual and senior-dependent step. At project scale, a five-peer study
moves from about 30 days to about 7.5, and a six-peer study from about 36 to
about 9."

### Q: Could an individual peer be identified from the outputs?

"That is exactly what the privacy layer prevents. The input is aggregated,
long-format peer data; the concentration caps stop any single peer from
dominating a category; and the minimum-participant thresholds keep peer groups
from getting too thin. In the audit package, secret connection details are
redacted. The outputs are built to be shared without exposing an individual
peer's position."

### Q: What should leadership remember?

"Autobench reduces compliance risk and cycle time at the same time. It makes
privacy-compliant benchmarking scalable enough to support repeatable products
like the A&F dashboard."

---

## Final Leave-Behind Paragraph

"Autobench v3.0 turns peer benchmarking into a governed optimization workflow.
It enforces Control 3 privacy requirements, minimizes distortion from raw market
data, makes the compliance trade-off visible, and packages every run for
decision-making and audit. The result is a faster, more defensible, and more
scalable foundation for performance analytics."
