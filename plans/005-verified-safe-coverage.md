# Plan 005: Replace maximum proof with verified safe coverage

Date: 2026-08-05.

Status: IN PROGRESS.

## Decision

The operator approved the `verified-safe-coverage` contract.

The mode publishes a deterministic safe subset.

It does not claim that the subset is the largest possible subset.

This plan replaces `maximize-safe-coverage`.

Do not add an alias or a compatibility path.

## Reason

Plans 003 and 004 removed the memory fault.

They did not prove the exact maximum on real Getnet data.

The real Stage 1 model kept a weak dual bound.

HiGHS did not return the required proof in 15 minutes.

The operator rejected commercial solvers.

Open-source proof tests also failed within the approved limits.

## Product contract

The new mode applies only to share analysis.

It requires one global weight vector.

It requires the `SWEEP_ANY_APPLICABLE` rule strategy.

It can publish an incomplete view.

Each missing unit means privacy suppression.

Consumers must not restore missing units.

The mode keeps all current privacy rules.

The mode keeps the current comparison epsilon.

The mode keeps the independent verifier.

The mode does not prove reconstruction safety across repeated releases.

## Search contract

The search uses an open-source HiGHS anchor.

The anchor uses one thread and random seed zero.

The anchor stops after 20 branch-and-bound nodes.

A 90-second limit stops an unusually slow anchor.

The search accepts a feasible anchor result without an optimum proof.

The search then uses deterministic candidate refinement.

The refinement uses a fixed Sobol seed.

The refinement uses fixed sample counts and fixed coordinate grids.

The search evaluates all applicable privacy rules directly.

The search selects the candidate with the highest verified release count.

It uses neutral-weight distance as the second selection key.

It uses the fixed candidate order as the last selection key.

The final release set contains every unit that passes at the selected weights.

The final suppression set contains every other candidate unit.

The result state is `search_complete`.

No output can use `optimal`, `maximum`, `zero gap`, or `proof` language.

## Verification contract

The solver returns trusted internal evidence with `verifier_result=not_run`.

The independent verifier recalculates every rule from the source candidate universe.

The verifier checks every released unit.

The verifier also checks every suppressed unit.

The verifier confirms that the selected weights produce the exact release partition.

The verifier checks Citibank overlays when they apply.

The verifier checks weight bounds and all trusted digests.

The verifier checks client keys and artifact hashes.

Any verifier failure blocks all client output.

## Interface changes

The CLI value becomes `verified-safe-coverage`.

The TUI label becomes `Verified safe coverage`.

The Python enum becomes `PrivacyReleaseMode.VERIFIED_SAFE_COVERAGE`.

Python callers must use the enum value.

YAML uses `privacy_release_mode: verified-safe-coverage`.

Help text must state that coverage is not a maximum claim.

## Contract changes

Remove maximum-proof fields from the client certificate.

Remove `primary_objective_value` from the client certificate.

Remove `mip_dual_bound` from the client certificate.

Remove `mip_gap` from the client certificate.

Record the search method, state, and evaluated candidate count.

Keep aggregate release counts, policy metadata, hashes, and visible keys.

## Tests first

Add tests for the new CLI value and the removed old value.

Add tests for the TUI label and help text.

Add tests for the Python enum and request type checks.

Add tests for deterministic repeated search results.

Add tests for acceptance of an unproven HiGHS incumbent.

Add tests for direct final rule evaluation.

Add tests that the release set includes all passing units.

Add tests that the verifier rejects a hidden passing unit.

Keep all privacy tamper tests.

## Local acceptance

Run `uv lock --check`.

Run Ruff on all changed Python files.

Run MyPy with Python 3.12 for the changed core files.

Run the complete test suite with four workers.

Run the production-scale sanitized benchmark twice.

The two runs must return the same release-mask digest.

## Getnet acceptance

Keep `outputs/dashboard_feed/current` unchanged.

Create one isolated candidate directory.

Run all five governed quarters through the current dashboard-feed producer.

Record source hashes before and after the run.

Run every dashboard-feed acceptance check.

Compare the three EY files with the accepted `f745a318` baseline.

Explain each material mismatch with row-level and policy evidence.

Do not promote the isolated candidate.

## Commit contract

Commit tests and contracts first.

Commit the search implementation next.

Commit interface and documentation changes next.

Commit Getnet acceptance evidence last, if repository policy permits it.

Keep all work local.

Do not push a branch.

Do not open a pull request.

## Execution checkpoint

The Plan 005 source and interface work is complete.

Autobench passed 1,016 tests and skipped 38 tests.

The lock and Ruff checks passed.

The sanitized production-scale benchmark returned the same release mask twice.

The Getnet adapter now fits amount only.

Transactions and establishments use the amount-selected weights.

They do not control the Getnet release decision.

The exact Getnet benchmark passed all five revised local quarter gates.

All five searches returned `search_complete`.

All five independent verifiers passed the complete partition.

Release counts were 224, 235, 233, 238, and 229.

Peak working set stayed below 255 MB.

Each quarter completed in less than one minute.

The accepted Getnet EY hashes stayed unchanged.

The full Getnet candidate is still pending.

The local attempt-02 package stops after the benchmark input.

The local retry09 package has aggregate SoW output and Edge table lineage.

It has no peer-level merchant-stage row export.

The accepted files are filtered outputs and cannot replace that source.

The active work scope is local only.

Do not change this plan to `DONE` before the three isolated EY files exist.
