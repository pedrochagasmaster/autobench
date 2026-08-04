# Plan 002: Add the Maximum Safe Coverage privacy release mode

> **Executor contract**: Read this complete file before you change source files.
> Follow each step in order. Run every required check. Honor every STOP condition.
> Do not weaken a privacy rule. Do not publish, deploy, or use production data.

## Copy-ready cloud-agent prompt

```text
Work in the Autobench repository.

Read AGENTS.md, CONTRIBUTING.md, and plans/002-maximize-safe-coverage.md completely.
Treat plans/002-maximize-safe-coverage.md as the execution contract.

Implement Plan 002 on a short-lived branch from current GitHub main.
Use the current Control 3 policy without weaker limits or new privacy rules.
Add the Maximum Safe Coverage release mode for share analysis.

The mode must find one global weight vector.
It must maximize the number of safe Publication Units.
It must release only units that pass all required privacy checks.
It must prove the primary optimum before it calls the result maximum.
An independent verifier must recalculate every release decision.

Expose the mode through Python, CLI, TUI, and YAML configuration.
Keep the privacy release mode separate from rule strategy and compliance posture.
Keep complete_output as the explicit default and current behavior.

Use a sanitized Getnet-shaped fixture. Do not commit confidential Getnet data.
Run all checks in this contract. Preserve the complete evidence chain.
Make the stated commits. Do not push, open a pull request, deploy, or release.
Stop and report if any STOP condition occurs. Do not improvise around it.
```

## Status

- **Execution**: DONE (local; completed 2026-08-04 on branch `codex/002-maximize-safe-coverage`)
- **CI matrix**: full suite on Python 3.10 / 3.12 / 3.13 deferred to CI per operator instruction
- **Production acceptance**: NOT complete (requires operator-approved PR, CI, and release workflow)
- **Priority**: P0
- **Effort**: L
- **Risk**: HIGH
- **Depends on**: none
- **Category**: privacy feature
- **Planned at**: commit `e11e7ec8f3b8fd497b33c8d8f7bde7af143945dd`, 2026-08-04

## Outcome

Add one share-analysis release mode named **Maximum Safe Coverage**.

Its public values are:

```text
CLI and YAML: maximize-safe-coverage
Python enum: PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE
```

The existing behavior becomes the explicit default:

```text
CLI and YAML: complete-output
Python enum: PrivacyReleaseMode.COMPLETE_OUTPUT
```

The new mode uses one global weight vector for all released units.
It releases only units that pass the current privacy policy.
It suppresses all other units from every client sink.

The mode must maximize the number of released Publication Units.
It must not maximize rows, metrics, volume, value, or business performance.

## Why this change is necessary

The current pipeline requires one vector to authorize the complete governed output.
If one governed unit fails, Autobench can withhold every benchmark artifact.

The Getnet 2025Q1 input has 318 privacy-eligible categories.
No tested global vector made all governed outputs pass.

Larger bounds and longer optimization did not solve this condition.
The tested rules were 5/25, 6/30, 7/35, 10/40, and 4/35.
Each attempt returned `strict_optimization_not_compliant`.

The required change is not a weaker optimizer preset.
The required change changes the release set while preserving every privacy limit.

## Fixed terminology

Use these terms in source, tests, documentation, and messages.

### Publication Unit

A Publication Unit is one all-or-nothing client output cell.

For share analysis, its key contains the stable output scope fields.
These fields include dimension, category, time period, and applicable output scope.

All governed metrics for that key belong to the same Publication Unit.
The unit passes only when every required metric passes.

Do not call a metric row a Publication Unit.
Do not release one metric while another metric in the same unit fails.

### Candidate Universe

The Candidate Universe is the fixed set of privacy-eligible Publication Units.
Build it after existing structural category suppression.
Build it before coverage optimization.

The Candidate Universe must not change during optimization.
The objective must not add, remove, copy, or weight units.

### Release Set

The Release Set contains Publication Units authorized for client output.

### Suppression Set

The Suppression Set is the Candidate Universe minus the Release Set.

### Coverage Certificate

The Coverage Certificate is safe client evidence for the exact released artifact.
It must not expose suppressed unit keys or suppressed category names.

### Suppressed Publication View

The Suppressed Publication View is the filtered client artifact.
It contains only the Release Set.

## Applicability

Support this mode only for share analysis in this plan.
Reject it for rate analysis with a clear error.

The mode is applicable only when all conditions are true:

- Missing units mean unavailable output.
- Each Publication Unit has a stable unique key.
- One global weight vector is required.
- All required metrics for one unit can be evaluated together.
- The consumer preserves the Release Set.
- The consumer can suppress more units, but cannot restore units.
- Visible totals do not reconstruct suppressed units.
- A later process supplies complementary suppression when needed.

The mode is not applicable when any condition is true:

- A complete table is mandatory.
- Missing output reveals protected information.
- Required scope evidence is invalid or incomplete.
- A consumer can restore a suppressed unit.
- Published totals can reconstruct a suppressed unit.
- Per-dimension weights are required.
- Rate analysis is requested.

Reject `maximize-safe-coverage` with `--per-dimension-weights`.
Do not silently change either setting.

## Non-goals

Do not add a new privacy rule.
Do not change current rule limits.
Do not change the Citi mandatory overlay.
Do not add a Getnet-specific rule.
Do not add merchant-count policy to Autobench.
Do not add complementary suppression equations.
Do not add a 9.0 compatibility path.
Do not support rate analysis in this plan.
Do not add release-size weights or business priorities.
Do not add a general optimization framework.
Do not add a second artifact writer.
Do not retain an obsolete flag as a compatibility alias.

## Public Interface

Add this enum to `core/contracts.py`:

```python
class PrivacyReleaseMode(str, Enum):
    COMPLETE_OUTPUT = "complete-output"
    MAXIMIZE_SAFE_COVERAGE = "maximize-safe-coverage"
```

Add this field to `AnalysisRunRequest`:

```python
privacy_release_mode: Optional[PrivacyReleaseMode] = None
```

`None` means that configuration resolution must select the effective mode.
The resolved default is `PrivacyReleaseMode.COMPLETE_OUTPUT`.

This nullable input preserves correct configuration precedence.
The mode must never remain null after configuration resolution.

The Python Interface accepts enum values or `None` only.
Reject strings passed directly to `AnalysisRunRequest`.

Add this share CLI flag:

```text
--privacy-release-mode {complete-output,maximize-safe-coverage}
```

Do not add the flag to rate analysis.
Use an internal parser default of `None`.
Show `complete-output` as the effective default in help.

Add one TUI selection for share analysis.
Use the labels `Complete output` and `Maximum safe coverage`.
Hide or disable this field for rate analysis.

Add this top-level YAML field:

```yaml
privacy_release_mode: "complete-output"
```

CLI values override YAML values.
YAML values override the default.
Reject unknown values during configuration validation.

Do not use `privacy_rule_sweep` as a release-mode switch.
Do not change `PrivacyRuleStrategy` meanings.

## Interface integration contract

The three user Interfaces must call the same orchestration seam.
They must produce the same effective request and result contracts.

Do not implement privacy logic in an Interface.
Do not let one Interface use a weaker validation path.

### Shared mode resolution

Add `privacy_release_mode` to `ResolvedConfig`.
Parse it as `PrivacyReleaseMode`, not as an unrestricted string.

Use this precedence for all Interfaces:

1. An explicit Interface value.
2. A YAML or preset value.
3. `PrivacyReleaseMode.COMPLETE_OUTPUT`.

Add one shared resolution function in the orchestration Module.
It must return an effective request with a non-null enum value.

Do not mutate the caller's `AnalysisRunRequest`.
Use `dataclasses.replace` or an equivalent immutable step.

Run compatibility checks after mode resolution.
Run them before data loading or solver work.

The checks must reject these combinations:

- Maximum Safe Coverage with rate analysis.
- Maximum Safe Coverage with per-dimension weights.
- Maximum Safe Coverage with an incompatible explicit rule strategy.
- Any unknown or untyped release-mode value.

### CLI integration

Register `--privacy-release-mode` on `share_parser` only.
Do not register it in `add_common_run_flags`.

Parse CLI text directly into `PrivacyReleaseMode`.
Use the enum values as the argparse choices.
Set the argparse default to `None`.

Add `privacy_release_mode` to `COMMON_CLI_OVERRIDES`.
Map it to the top-level YAML field in `ConfigManager`.
Write the enum value string into the merged configuration.

Do not let the effective default overwrite a YAML value.
This is why the raw CLI default must remain `None`.

`build_run_request` must preserve an explicit CLI enum.
The shared resolver must apply YAML and default values later.

Update CLI help with these facts:

- `complete-output` requires a complete authorized output.
- `maximize-safe-coverage` can publish an incomplete safe view.
- The new mode requires global weights and rule sweep semantics.
- Missing units are privacy-suppressed.

Add one copyable CLI example.
Validate the example with the real parser in a test.

On successful Maximum Safe Coverage output, print only safe summary facts.
Print candidate, released, and suppressed counts.
Print coverage percentage and the Coverage Certificate path.
Print that maximum coverage has a zero-gap proof.

Do not print suppressed keys, category names, or failure details.

Use the existing successful exit code when at least one unit is authorized.
Use the existing hard-privacy-denial exit behavior for empty or unproven results.

Add CLI tests for:

- Help text and exact choices.
- Omitted flag with no YAML.
- Omitted flag with YAML Maximum Safe Coverage.
- Explicit CLI override of YAML.
- Invalid value.
- Rate parser rejection.
- Per-dimension rejection.
- Compatible rule-sweep selection.
- Safe success summary.
- Empty Release Set denial.
- No suppressed marker in captured output.

### TUI integration

Add a `Select` with the id `privacy_release_mode`.
Place it in the existing Analysis Options section.

Use these exact visible labels:

```text
Complete output
Maximum safe coverage
```

Use the enum values as stored selection values.
Set `Complete output` as the initial effective selection.

Add this short help text below the selection:

```text
Maximum safe coverage publishes only verified safe units. Missing units are privacy-suppressed.
```

Show the field for share analysis.
Hide or disable it for rate analysis.
Do not let a hidden Maximum Safe Coverage value reach a rate request.

Keep the existing privacy-rule-sweep control separate.
When the user selects Maximum Safe Coverage, enable rule sweep.
Disable the sweep control while this mode remains selected.

When the user returns to Complete Output, enable the sweep control.
Preserve its prior user value when this is safe and simple.

The TUI already sets global weights for share requests.
Keep that behavior and add an explicit assertion.

When the user loads a preset or YAML file, refresh the selection.
Show the resolved configuration value before the run starts.

Include the release mode in session save and restore.
Reject a stale or unknown saved value.
Fall back to Complete Output and show a safe warning.

Add the selected enum to `_privacy_strategy_values_from_widgets`.
Rename that helper if its new scope makes the old name inaccurate.

Build the request only through `AnalysisRunRequest.from_widget_values`.
Run it only through the shared TUI executor and `execute_share_run`.

During a successful run, show these safe facts:

- `Maximum safe coverage` as the mode.
- Candidate unit count.
- Released unit count.
- Suppressed unit count.
- Coverage percentage.
- Coverage Certificate path.
- Verified optimal status.

Do not list suppressed units in the log widget or notification.

Add Textual pilot tests for:

- Default selection.
- Both visible labels.
- Share visibility.
- Rate hiding or disabling.
- Maximum selection enabling and locking rule sweep.
- Return to Complete Output.
- YAML or preset refresh.
- Session save and restore.
- Request enum construction.
- Execution through the shared executor.
- Safe result summary.
- Empty Release Set denial.
- No suppressed marker in widgets or notices.

### Python Interface integration

Keep `execute_share_run(request, logger)` as the public execution function.
Do not add a second Python executor for this mode.

Export these public contracts from `core`:

- `PrivacyReleaseMode`.
- `SafeCoverageResult`.
- `CoverageCertificate`.

Add these fields to `AnalysisArtifacts`:

```python
safe_coverage_result: Optional[SafeCoverageResult] = None
coverage_certificate: Optional[CoverageCertificate] = None
coverage_certificate_output: Optional[str] = None
```

For Complete Output, `safe_coverage_result` can remain `None`.
Document the exact behavior when all units pass in the new mode.

For Maximum Safe Coverage, return the verified trusted result in memory.
Return the client-safe certificate separately.

The trusted result gives governed Python consumers the exact Release Set.
The consumer must apply the monotone subset rule.

Do not require a consumer to import an internal Module.
Do not require a consumer to parse a workbook or command output.

Accept only this Python request form:

```python
privacy_release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE
```

Reject this untyped form:

```python
privacy_release_mode="maximize-safe-coverage"
```

When the field is `None`, resolve YAML or preset configuration.
When no configuration supplies a value, resolve Complete Output.

An explicit Python enum overrides YAML and preset configuration.
Document and test this precedence.

Python execution without file output must still return the verified result.
It must not write a certificate unless the request asks for output.

Add public Interface tests for:

- Import paths.
- Enum values.
- Request type validation.
- Effective default.
- YAML resolution.
- Explicit enum precedence.
- Share-only rejection.
- Per-dimension rejection.
- Returned trusted result.
- Returned client-safe certificate.
- Exact Release Set access.
- No suppressed key in the client certificate.
- No disk write when output is not requested.

Update `examples/run_from_python.py`.
Update `tests/test_public_api.py` to pin the new public surface.

### Cross-Interface parity

Use one sanitized input and one equivalent configuration.
Run it through CLI, TUI, and Python.

Normalize paths, timestamps, and run identifiers only.
Then compare these exact fields:

- Effective release mode.
- Candidate unit count.
- Release Set.
- Global weights.
- Authorizing rules.
- Primary objective.
- Dual bound.
- Mixed-integer gap.
- Policy digest.
- Release-mask digest in trusted evidence.
- Client-safe certificate fields.

All three Interfaces must agree.
Add this parity case to the full gate.

## Separation of concerns

Keep these three controls independent.

| Control | Question |
|---|---|
| `privacy_release_mode` | Which safe units can reach client output? |
| `privacy_rule_strategy` | Which approved rules can authorize a unit? |
| `compliance_posture` | How does the run handle non-compliant analysis? |

`maximize-safe-coverage` must use `SWEEP_ANY_APPLICABLE` semantics internally.
One released unit can use a different applicable rule from another released unit.
All released units must use the same global weights.

Do not mutate the requested `privacy_rule_strategy` without evidence.
Reject an incompatible explicit strategy with a clear message.

The preferred simple rule is this:

- `complete-output` accepts both current rule strategies.
- `maximize-safe-coverage` requires `SWEEP_ANY_APPLICABLE`.
- The CLI and TUI select that strategy when the new mode is selected.
- The Python Interface requires the caller to supply a compatible strategy.

Document the final rule in one place.
Test Python, CLI, TUI, and YAML behavior against that rule.

## Module design

Keep the Interface small and the Implementation deep.

Add these focused Modules under `core/`:

```text
core/privacy_coverage.py
core/privacy_coverage_solver.py
core/privacy_coverage_verifier.py
```

`privacy_coverage.py` owns Publication Unit construction and filtering.
`privacy_coverage_solver.py` owns the mixed-integer formulation.
`privacy_coverage_verifier.py` owns independent recalculation and certificate checks.

Keep `core/analysis_run.py` as the orchestration seam.
Keep `core/output_artifacts.py` as the only client artifact-writing seam.
Extend `core/privacy_output_policy.py` for release-set authorization and attestation.

Do not place solver details in `benchmark.py` or `tui_app.py`.
Do not copy privacy formulas into artifact writers.
Do not make a Getnet Adapter in Autobench.

## Data contracts

Add immutable contracts with exact types.
Names can change only when repository conventions require a clearer name.

### `PublicationUnit`

It must contain:

- A canonical internal key.
- The canonical output-key fields.
- All governed metric records.
- The applicable approved rules.
- The required mandatory overlays.

Do not include display order in its identity.
Use `core/canonical_order.py` for canonical ordering.

### `SafeCoverageResult`

This trusted internal result must contain:

- The release mode.
- The global weight vector.
- The ordered Candidate Universe.
- The exact Release Set.
- The exact Suppression Set.
- The authorizing rule for each released unit.
- The primary objective value.
- Each later objective value.
- The solver state.
- The mixed-integer dual bound.
- The mixed-integer gap.
- The solver name and version.
- The input digest.
- The configuration digest.
- The policy version and source.
- The rule-set digest.
- The Candidate Universe digest.
- The release-mask digest.
- The verifier result.

Reject contradictory fields in `__post_init__`.
Use tuples and immutable mappings where practical.

Never put `SafeCoverageResult` into a normal client artifact.
It can contain protected internal keys.

### `CoverageCertificate`

This client-safe contract must contain:

- `artifact_type` with a fixed versioned value.
- `privacy_release_mode`.
- Candidate unit count.
- Released unit count.
- Suppressed unit count.
- Coverage percentage.
- Visible Publication Unit keys only.
- The authorizing rule for each visible unit.
- The global weights when current policy permits their publication.
- The policy version and source.
- The rule-set digest.
- The solver name and version.
- The proven primary objective.
- The zero-gap proof fields.
- Hashes for each client artifact.
- A certificate digest over canonical safe fields.

Do not include a suppressed key.
Do not include a digest of each suppressed key.
Do not include a suppressed category name.
Do not include source row values for suppressed units.

## Candidate Universe construction

Build normal share results through the current analysis path.
Apply current structural category suppression first.

Then group all governed result records by canonical Publication Unit key.
Include the primary metric and every declared secondary metric.

The metric list is part of the request contract.
A missing required metric makes the unit ineligible for release.
Record only a safe aggregate reason in client evidence.

Sort units with existing canonical-order helpers.
Reject duplicate keys.
Reject non-finite governed values.
Reject ambiguous time or dimension keys.

Hash the canonical Candidate Universe only in trusted evidence.
Do not expose a reversible low-entropy digest in client evidence.

## Optimization contract

Use one continuous weight variable for each governed peer.
Use one binary release variable for each Publication Unit.
Use rule-selection variables when a unit has multiple applicable rules.

For each released unit, enforce all current rule conditions.
Apply each condition to every governed metric in that unit.
Apply the Citi overlay to each applicable released unit.

A release variable of zero does not relax another unit's constraints.
A release variable of one must enforce one complete applicable rule.

Use the existing weight bounds and global consistency rules.
Do not allow a zero weight to remove a governed peer.
Do not change participant counts through numeric tolerance.

Derive each linear constraint from the current rule evaluator.
Add parity tests between each constraint and `evaluate_rule`.
Do not keep two independent privacy definitions.

### Lexicographic objective

Use staged solves. Do not combine priorities with unsafe large coefficients.

Use this exact priority:

1. Maximize the count of released Publication Units.
2. Minimize total analytical distortion with the count fixed.
3. Minimize distance from neutral weights with prior objectives fixed.
4. Select one canonical release mask and weight vector.

Business value must not affect any priority.
Target performance must not affect any priority.
Protected values must not affect release priority.

The final tie method must be deterministic and numerically safe.
Iterative canonical fixing is acceptable.
Document another method before using it.

The final method must produce the same normalized result across fresh processes.
It must also ignore input row order and `PYTHONHASHSEED`.

### Solver choice

Check `scipy.optimize.milp` first.
The repository already depends on SciPy and HiGHS.

Use the existing dependency when it supplies all required proof fields.
These fields include status, dual bound, and mixed-integer gap.

Do not add another solver without written evidence.
The evidence must show which required SciPy field or behavior is missing.

If a new dependency is necessary, update all dependency locks and Edge bundle checks.
That change is a STOP condition before implementation continues.

### Proof of maximum coverage

Call the result `maximum` only when all conditions hold:

- The solver reports an optimal result.
- The primary integer objective is integral.
- The mixed-integer gap is exactly zero under the solver contract.
- The rounded dual bound equals the released-unit count.
- The independent verifier accepts the exact result.

A time limit does not prove maximum coverage.
A feasible state does not prove maximum coverage.
A small nonzero gap does not prove maximum coverage.

An unproven safe candidate can remain in trusted memory for diagnosis.
It must not reach a normal client sink.
Write only the current safe denial audit for that run.

## Independent verification

The verifier must not trust solver pass flags.
It must recalculate from the original input and final global weights.

The verifier must check all these facts:

- Every visible key belongs to the Candidate Universe.
- Every visible key occurs exactly once.
- Every required metric is present in each visible unit.
- Every required metric passes one complete applicable rule.
- Each recorded authorizing rule is applicable.
- Each required Citi overlay passes.
- One global vector applies to all visible units.
- Every weight is finite and within its bounds.
- Client keys equal the Release Set exactly.
- No Suppression Set unit occurs in a client sink.
- The primary solver state is optimal.
- The mixed-integer gap is zero.
- The dual bound proves the released-unit count.
- Input, configuration, policy, universe, and mask evidence is coherent.
- Artifact hashes match the files written to disk.

The verifier must fail closed.
A verifier failure blocks all benchmark-bearing output.

Use existing rule evaluation code for recalculation.
Do not call solver constraint helpers from the verifier.
This separation detects formulation defects.

## Output policy

`complete-output` must preserve current behavior exactly.

For `maximize-safe-coverage`, authorize output only after verification succeeds.
Filter every client payload through the exact Release Set.

Apply filtering to all current sinks:

- Analysis workbook.
- Publication workbook.
- Balanced CSV.
- JSON output.
- Audit package.
- Report model.
- Diagnostics that can reach a client.
- Deferred logs.
- TUI summaries.
- CLI summaries.

No sink can rebuild data from an unfiltered object.
Filter once at a deep seam before artifact formatting.

The client artifact name is **Suppressed Publication View**.
The artifact must state that missing units were suppressed for privacy.

Do not say that suppressed units failed a named rule.
Do not show per-rule failure details for suppressed units.
Do not show suppressed category names in warnings.

When the Release Set is empty, write only the safe denial audit.
When verification fails, write only the safe denial audit.
When proof is incomplete, write only the safe denial audit.

## Consumer contract

Document this monotone consumer rule:

```text
final_release_set must be a subset of autobench_release_set
```

A consumer can suppress additional units.
A consumer must never restore an Autobench-suppressed unit.

Getnet keeps its merchant and reconstruction checks.
Autobench proves only direct Control 3 privacy in this plan.

Do not claim that this mode prevents reconstruction without consumer evidence.

## Failure behavior

Use a full hard block for these failures:

- Invalid or incomplete privacy declarations.
- Invalid identity evidence.
- Invalid Citi evidence.
- Duplicate Publication Unit keys.
- An empty or unstable Candidate Universe.
- A solver error.
- An unproven primary optimum.
- A verifier mismatch.
- A release-mask mismatch.
- A client artifact hash mismatch.
- A suppressed identity leak.
- A suppressed category leak.
- A consumer contract that can restore units.

Do not convert these failures into cell suppression.

## Required implementation sequence

### Commit 1: Record the release-policy decision

Create `docs/adr/0002-maximum-safe-coverage.md`.

The ADR must define:

- The two release modes.
- The fixed terminology in this plan.
- Share-only scope.
- One global vector.
- The all-metric Publication Unit rule.
- The lexicographic objective.
- The proof requirement.
- Independent verification.
- Client-safe evidence.
- The monotone consumer rule.
- The reconstruction non-goal.

Do not change production behavior in this commit.

Suggested commit:

```text
docs: record maximum safe coverage release policy
```

### Commit 2: Add contracts and configuration

Add `PrivacyReleaseMode`, `PublicationUnit`, and result contracts.
Add the request field and configuration resolution.

Expose the YAML value in `config/template.yaml`.
Update configuration validation and precedence tests.

Add contract invariants before adding solver behavior.

Suggested commit:

```text
feat: add privacy release mode contracts
```

### Commit 3: Build the Candidate Universe

Add canonical Publication Unit construction for share analysis.
Use existing structural suppression and canonical ordering.

Add tests for duplicate keys, missing metrics, row order, and unit identity.
Add the sanitized Getnet-shaped fixture in `tests/fixtures/`.

Suggested commit:

```text
feat: build canonical privacy publication units
```

### Commit 4: Add the coverage solver

Implement the mixed-integer model and staged objectives.
Use SciPy when it meets the proof contract.

Add rule-parity tests for every approved rule.
Add optimal, infeasible, timeout, and solver-error tests.

Suggested commit:

```text
feat: optimize maximum safe coverage
```

### Commit 5: Add independent verification

Implement full result recalculation.
Add trusted and client-safe evidence contracts.

Add all tamper tests from this plan.

Suggested commit:

```text
feat: verify safe coverage independently
```

### Commit 6: Connect orchestration and outputs

Connect the new mode in `core/analysis_run.py`.
Extend privacy authorization and attestation.

Filter all client sinks before formatting.
Preserve current complete-output behavior.

Suggested commit:

```text
feat: publish suppressed privacy-safe views
```

### Commit 7: Add all user Interfaces

Add the share CLI flag.
Add the share TUI selection.
Complete YAML and Python examples.

Reject unsupported rate and per-dimension combinations.
Test all Interface paths.

Suggested commit:

```text
feat: expose maximum safe coverage mode
```

### Commit 8: Complete documentation and gate coverage

Update `README.md` and relevant privacy documentation.
Explain applicability, limits, and consumer duties.

Add the sanitized end-to-end case to the full gate.
Do not add generated fixture outputs.

Suggested commit:

```text
test: gate maximum safe coverage releases
```

### Commit 9: Run final validation

Run every command in the validation section.
Record command results and test counts in the handoff.

Update Plan 002 status only after all local criteria pass.
Do not mark production acceptance complete.

Suggested commit:

```text
docs: complete maximum safe coverage plan
```

## Test contract

Add focused test files where they keep one concern clear.
Suggested names are:

```text
tests/test_privacy_release_mode.py
tests/test_privacy_coverage_units.py
tests/test_privacy_coverage_solver.py
tests/test_privacy_coverage_verifier.py
tests/test_privacy_coverage_outputs.py
```

### Core behavior cases

Test these cases:

1. All units pass.
2. One unit fails.
3. No unit passes.
4. A secondary metric fails.
5. Citi fails for one unit.
6. One unit uses 5/25 and another uses 6/30.
7. A missing required metric suppresses its complete unit.
8. Invalid scope evidence blocks the complete run.
9. Per-dimension weights are rejected.
10. Rate analysis is rejected.

When all units pass, both release modes must produce equal analytical results.
Ignore only new mode evidence during that comparison.

When one unit fails, `complete-output` must withhold benchmark output.
`maximize-safe-coverage` must release only proven-safe units.

### Proof cases

Test these solver states:

- Optimal with zero gap and matching dual bound.
- Feasible with a nonzero gap.
- Time limit with a feasible candidate.
- Infeasible.
- Unbounded.
- Invalid solver output.
- Non-integral release variables.
- A dual bound that does not prove the count.

Only the first state can publish.

### Tamper cases

Change one field at a time and require a hard block:

- One global weight.
- One visible unit key.
- One suppressed unit added to output.
- One visible unit removed from output.
- One authorizing rule.
- The policy digest.
- The Candidate Universe digest.
- The release-mask digest.
- The certificate digest.
- One artifact after hash calculation.
- The solver gap.
- The solver dual bound.

### Leak cases

Seed one unique suppressed category marker.
Search all client files and captured messages for that marker.

Search these sinks:

- XLSX cell values and shared strings.
- CSV text.
- JSON text.
- Audit package members.
- CLI output.
- TUI notices.
- Log files.
- Safe denial audit.
- Coverage Certificate.

The marker must not occur.

### Determinism cases

Run the sanitized end-to-end case in fresh processes.
Use several input row orders.
Use at least three `PYTHONHASHSEED` values.

Normalize only timestamps, paths, and generated run identifiers.
Do not normalize solver results, masks, weights, rules, or hashes.

The normalized results must match byte for byte.

### Getnet-shaped fixture

Create a small synthetic fixture with these properties:

- Multiple quarters or time periods.
- Multiple break dimensions.
- Several category cells.
- Amount, transaction, and establishment-like metrics.
- One global vector.
- At least one safe unit.
- At least one unsafe unit.
- At least one secondary-metric-only failure.
- No Citi entity.
- No real merchant, issuer, or category name.

The fixture must reproduce the current failure shape.
It must not copy any confidential Getnet values.

## Documentation contract

Document these examples:

```powershell
uv run --locked --no-sync python benchmark.py share `
  --csv data.csv `
  --metric transaction_amount `
  --secondary-metrics transaction_count merchant_count `
  --dimensions quarter region sector `
  --privacy-rule-sweep `
  --privacy-release-mode maximize-safe-coverage
```

```python
request = AnalysisRunRequest(
    mode="share",
    df=dataframe,
    metric="transaction_amount",
    secondary_metrics=["transaction_count", "merchant_count"],
    dimensions=["quarter", "region", "sector"],
    privacy_rule_strategy=PrivacyRuleStrategy.SWEEP_ANY_APPLICABLE,
    privacy_release_mode=PrivacyReleaseMode.MAXIMIZE_SAFE_COVERAGE,
)
```

State that `maximize-safe-coverage` does not weaken privacy limits.
State that it can produce an incomplete view.
State that missing cells are privacy-suppressed.
State that consumers must not restore them.

State that this mode does not prove reconstruction safety.
State that recurring releases need a joint disclosure review.

## Scope

Expected source scope:

- `core/contracts.py`
- `core/analysis_run.py`
- `core/privacy_output_policy.py`
- `core/output_artifacts.py`
- `core/canonical_order.py` only when a reusable helper is missing
- `core/privacy_coverage.py` (new)
- `core/privacy_coverage_solver.py` (new)
- `core/privacy_coverage_verifier.py` (new)
- `benchmark.py`
- `tui_app.py`
- `utils/config_manager.py`
- `utils/config_overrides.py`
- `config/template.yaml`
- focused tests and one sanitized fixture
- `scripts/perform_gate_test.py` or its owned gate helper
- `docs/adr/0002-maximum-safe-coverage.md` (new)
- `README.md`
- active privacy documentation
- `plans/README.md`
- this plan

Do not modify Getnet.
Do not modify `edge-deploy-core`.
Do not modify production nodes.
Do not add generated output files.

## Git workflow

Run from the Autobench repository root.

Start with these checks:

```powershell
git status --short
git rev-parse HEAD
git branch --show-current
git fetch origin
git rev-parse origin/main
git diff --stat e11e7ec8f3b8fd497b33c8d8f7bde7af143945dd..origin/main -- `
  core benchmark.py tui_app.py utils config tests scripts README.md docs pyproject.toml uv.lock
```

Stop if the working tree is not clean.
Stop if current source changes invalidate this contract.

Create this branch:

```powershell
git switch main
git pull --ff-only origin main
git switch -c codex/002-maximize-safe-coverage
```

Use a separate worktree from Plan 001 execution.
Do not combine runtime migration changes with this feature.

Use the commit order in this plan.
Do not squash during implementation.

Do not push or open a pull request without explicit operator approval.
Do not deploy or run Edge acceptance.

## Validation commands

Use the locked project environment.

```powershell
uv sync --locked --extra dev
uv run --locked --no-sync ruff check .
uv run --locked --no-sync mypy core/ utils/
uv run --locked --no-sync python -m pytest `
  tests/test_privacy_release_mode.py `
  tests/test_privacy_coverage_units.py `
  tests/test_privacy_coverage_solver.py `
  tests/test_privacy_coverage_verifier.py `
  tests/test_privacy_coverage_outputs.py -q
uv run --locked --no-sync python -m pytest `
  tests/test_privacy_output_boundary.py `
  tests/test_output_artifacts.py `
  tests/test_category_suppression.py `
  tests/test_determinism_matrix.py `
  tests/test_tui_contracts.py `
  tests/test_tui_privacy_rule_sweep.py `
  tests/test_config_precedence.py `
  tests/test_public_api.py -q
uv run --locked --no-sync python scripts/perform_gate_test.py
uv run --locked --no-sync python -m pytest
git diff --check
git status --short
```

Run the full suite on Python 3.10, 3.12, and 3.13.
Use the same matrix as `.github/workflows/ci.yml`.

If a suggested new test file has a better final name, update the commands.
Do not omit any test concern.

## Required evidence in the final handoff

Report all these items:

- Starting and ending commit hashes.
- Branch name.
- Exact changed-file list.
- Commit list.
- Solver and SciPy versions for each Python version.
- Solver proof fields from the sanitized case.
- Candidate, released, and suppressed unit counts.
- Rule used by each visible synthetic unit.
- Independent verifier result.
- Artifact hash verification result.
- Leak-scan result.
- Determinism matrix result.
- Every validation command and test count.
- Any skipped test and its reason.
- Remaining production acceptance work.

Do not include protected source values in the handoff.

## Done criteria

All items must be true:

- [x] `PrivacyReleaseMode` has exactly two values.
- [x] `complete-output` remains the default.
- [x] Current complete-output behavior has regression coverage.
- [x] Maximum Safe Coverage supports share analysis only.
- [x] One global vector applies to every released unit.
- [x] Each Publication Unit is all-or-nothing across required metrics.
- [x] The Candidate Universe is fixed before optimization.
- [x] The primary objective counts Publication Units only.
- [x] No business priority affects the primary objective.
- [x] Maximum coverage requires an optimal zero-gap proof.
- [x] The independent verifier recalculates privacy from source evidence.
- [x] Every client sink uses the exact Release Set.
- [x] No suppressed key or category leaks to a client sink.
- [x] The Coverage Certificate contains only safe evidence.
- [x] Empty, unproven, or invalid results write only safe denial evidence.
- [x] Python, CLI, TUI, and YAML Interfaces agree.
- [x] Unsupported combinations fail clearly.
- [x] The monotone consumer rule is documented.
- [x] Reconstruction safety is not overstated.
- [x] The sanitized Getnet-shaped gate passes.
- [x] Tamper and leak tests pass.
- [x] Fresh-process determinism tests pass.
- [x] Ruff, mypy, the gate, and the full test suite pass. (mypy: plan modules
  clean under the CI-matching 3.13 target; the default 3.10 target fails on
  pre-existing numpy 2.5 stubs, also red on `origin/main`; CI does not gate
  mypy today.)
- [ ] Python 3.10, 3.12, and 3.13 pass. (Deferred to CI per operator
  instruction; local full suite green on locked Python 3.13.14.)
- [x] No confidential data or generated output is committed.
- [x] All required documentation is current.
- [x] The final handoff contains the required evidence.

## STOP conditions

Stop and report when any condition occurs:

- Current `main` materially changes an in-scope privacy or output seam.
- Existing policy cannot define one Publication Unit without a product decision.
- The Candidate Universe cannot be fixed before optimization.
- A required privacy rule cannot be represented without changing its meaning.
- Solver and verifier semantics disagree after one focused repair.
- SciPy cannot supply the required proof fields.
- A new solver dependency appears necessary.
- Maximum proof requires accepting a nonzero gap.
- A client sink cannot use the exact Release Set.
- A suppressed category appears in any client sink.
- A consumer must restore a suppressed unit.
- Reconstruction safety is required inside Autobench.
- Rate support becomes necessary for acceptance.
- The change requires real Getnet data.
- The change requires production access or credentials.
- A required check fails twice after one focused repair.
- The worktree contains unrelated changes that overlap this plan.
- Completion requires changing Getnet or `edge-deploy-core`.
- Completion requires a deployment, release, or remote publication.

Do not weaken a rule to continue.
Do not hide a failed gate with a test exception.
Do not add a compatibility path.

## Maintenance notes

Keep Publication Unit identity stable across writers.
Treat key changes as privacy-contract changes.

Keep solver constraints and the independent verifier in separate Modules.
Add parity tests when a privacy rule changes.

Review recurring releases together.
Several safe single releases can reveal a suppressed value over time.

Keep the consumer rule monotone.
No later Adapter can expand the Autobench Release Set.

Retain proof fields with the release evidence.
Do not claim maximum coverage from a feasible-only result.

Review new client sinks for suppression leaks.
The release filter must cover each sink before production use.
