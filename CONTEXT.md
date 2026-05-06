# Privacy-Compliant Peer Benchmarking

This context describes the domain language for benchmark analyses that compare a target entity against privacy-compliant peer groups and produce audit-ready workbooks.

## Language

**Analysis Workbook**:
An internal workbook that includes benchmark results plus diagnostic evidence needed to audit weighting, compliance, and solver behavior.
_Avoid_: debug workbook, full report

**Publication Workbook**:
A stakeholder-facing workbook that includes clean benchmark results without diagnostic sheets, weight details, or technical metadata.
_Avoid_: client workbook, simplified report

**Diagnostic Sheet**:
A workbook sheet that explains how an analysis was produced or validated, such as peer weights, weight methods, privacy validation, structural diagnostics, rank changes, preset comparison, impact analysis, or data quality.
_Avoid_: debug tab, hidden evidence

**Privacy Block**:
A run-stopping compliance condition that prevents benchmark output when the peer group cannot satisfy the minimum privacy rule requirements.
_Avoid_: validation warning, soft failure

**Merchant Four-Peer Exception**:
A narrow privacy rule exception that permits merchant benchmarking under `4/35` only when the peer group has exactly four peers.
_Avoid_: merchant default rule, merchant override

**Canonical Config Key**:
The preferred configuration field name used after loading and merging config files, even when legacy aliases are accepted at input boundaries.
_Avoid_: current spelling, real key

**Solver Success**:
The benchmark-facing verdict that a solver result is usable after privacy validation under the configured tolerance.
_Avoid_: optimizer convergence, scipy success

**Sweep Runner**:
A developer verification script that executes generated CLI cases and records results without making the recorded run output part of the product source.
_Avoid_: committed sweep output, permanent results fixture

**Audit Remediation Scope**:
The bounded set of changes needed to restore audited runtime behavior, compliance correctness, and verification tooling without redesigning the optimizer architecture.
_Avoid_: cleanup sprint, architecture refactor

**Consolidation Base**:
The behavior-first branch used as the reference for remediation before sweep coverage is added for final verification.
_Avoid_: winning PR, final merge

**Durable Regression Test**:
A source-controlled test that protects stable benchmark behavior without depending on generated sweep outputs or one run's result counts.
_Avoid_: sweep snapshot test, branch result assertion

## Relationships

- An **Analysis Workbook** may include many **Diagnostic Sheets**.
- A **Publication Workbook** includes benchmark results but excludes **Diagnostic Sheets**.
- A **Privacy Block** prevents both **Analysis Workbook** and **Publication Workbook** generation.
- The **Merchant Four-Peer Exception** does not replace the standard privacy rule ladder for merchant peer groups with more than four peers.
- `max_attempts` is the **Canonical Config Key** for subset-search attempts; `max_tests` is only a legacy input alias.
- Optimizer convergence may be recorded as diagnostic detail, but **Solver Success** requires post-validation privacy feasibility.
- A **Sweep Runner** may create result logs during verification, but those logs are not source-controlled benchmark behavior.
- **Audit Remediation Scope** includes direct drift fixes, not broad decomposition of `DimensionalAnalyzer` or deprecated wrapper removal.
- The **Consolidation Base** establishes production behavior before the **Sweep Runner** is used to broaden final verification.
- A **Durable Regression Test** may invoke the **Sweep Runner**, but it should not assert one committed sweep output file as product truth.

## Example dialogue

> **Dev:** "Should `Peer Weights` appear in the publication output?"
> **Domain expert:** "No — `Peer Weights` is a **Diagnostic Sheet**, so it belongs in the **Analysis Workbook** only."
>
> **Dev:** "If input validation is disabled, can a three-peer run still write output?"
> **Domain expert:** "No — insufficient peers is a **Privacy Block**, not an optional validation warning."
>
> **Dev:** "Should a ten-peer merchant group still use `4/35`?"
> **Domain expert:** "No — the **Merchant Four-Peer Exception** applies only at exactly four peers."
>
> **Dev:** "Can a preset keep using `max_tests`?"
> **Domain expert:** "Yes at the input boundary, but merged config should expose `max_attempts` as the **Canonical Config Key**."
>
> **Dev:** "If L-BFGS-B converged but privacy caps still fail, is the solver successful?"
> **Domain expert:** "No — convergence is diagnostic detail; **Solver Success** means the result is usable after privacy validation."
>
> **Dev:** "Should we commit the full 1,063-case sweep result JSON?"
> **Domain expert:** "No — keep the **Sweep Runner**, not generated run output."
>
> **Dev:** "Should we split `DimensionalAnalyzer` while consolidating the PRs?"
> **Domain expert:** "No — that is outside **Audit Remediation Scope** unless a targeted blocker requires touching it."
>
> **Dev:** "Should the sweep decide the first behavior pass?"
> **Domain expert:** "No — start from the **Consolidation Base**, then use the **Sweep Runner** to catch remaining gaps."
>
> **Dev:** "Should a unit test assert the exact 1,063-case sweep summary from a previous branch?"
> **Domain expert:** "No — write a **Durable Regression Test** for the behavior, not a snapshot of generated run output."

## Flagged ambiguities

- "report" was used to mean both **Analysis Workbook** and **Publication Workbook** — resolved: use the precise workbook term when output behavior matters.
- "validation" was used to cover both optional input checks and compliance enforcement — resolved: insufficient peer count is a **Privacy Block**.
- "merchant rule" was used ambiguously — resolved: `4/35` is the **Merchant Four-Peer Exception**, not the default merchant rule for all peer counts.
- "preset key" was used for both accepted input aliases and runtime config names — resolved: use **Canonical Config Key** for the merged name and call legacy spellings aliases.
- "success" was used for both optimizer convergence and benchmark feasibility — resolved: **Solver Success** is the post-validation feasibility verdict.
- "sweep artifacts" was used for both reusable tooling and generated run output — resolved: source-control the **Sweep Runner**, not generated result logs.
- "remediation" was used to include broad cleanup — resolved: **Audit Remediation Scope** is limited to audited blockers and direct drift fixes.
- "base PR" was used to mean both implementation reference and final merge target — resolved: **Consolidation Base** means behavior reference, not wholesale merge.
- "test coverage" was used for both stable regression tests and generated sweep snapshots — resolved: keep **Durable Regression Tests** in source control and produce sweep snapshots during verification only.
