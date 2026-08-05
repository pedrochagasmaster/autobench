# ADR 0002: Define the Verified Safe Coverage release policy

- Status: Accepted
- Date: 2026-08-05

## Context

Complete-output mode withholds all output when one governed unit fails.

Some inputs can safely release only a subset of their governed units.

Plans 003 and 004 made the exact model smaller and added direct HiGHS use.

The real Getnet model still did not prove the exact maximum in 15 minutes.

The operator rejected commercial solvers.

## Decision

Autobench has two privacy release modes.

`complete-output` stays the default.

`verified-safe-coverage` publishes a deterministic safe subset.

The mode does not claim that the subset is the largest possible subset.

The mode applies only to share analysis.

The mode requires one global weight vector.

The mode requires `SWEEP_ANY_APPLICABLE` rule behavior.

Rate analysis and per-dimension weights are invalid combinations.

## Search

The search uses an open-source HiGHS anchor.

The anchor uses one thread, seed zero, and 20 branch-and-bound nodes.

A 90-second limit stops an unusually slow anchor.

The search accepts a feasible anchor result without an optimum proof.

A deterministic Sobol and coordinate search refines the anchor.

The search evaluates all applicable rules for each candidate vector.

It first selects the vector with the highest verified release count.

It then selects the vector nearest to neutral weights.

Fixed candidate order resolves any remaining tie.

## Release partition

A Publication Unit is one all-or-nothing output cell.

All governed metrics for that unit must pass one applicable rule.

All mandatory overlays must also pass.

The Candidate Universe is fixed before the search starts.

The Release Set contains every unit that passes at the selected weights.

The Suppression Set contains all other candidate units.

Consumers can suppress more units.

Consumers must never restore an Autobench-suppressed unit.

## Independent verification

The verifier does not use the search constraint helpers.

It recalculates every rule from the original Candidate Universe.

It checks every released unit and every suppressed unit.

It confirms the exact partition for the selected weights.

It checks the Citibank overlay when that overlay applies.

It checks weight bounds, policy digests, release-mask digests, and file hashes.

Any verifier failure blocks all benchmark-bearing output.

## Certificate

The certificate uses `coverage_certificate.v2`.

It contains safe aggregate counts and visible Publication Unit keys.

It contains the authorizing rule for each visible unit.

It contains search method, search state, and candidate-vector count.

It contains policy, solver, artifact-hash, and digest metadata.

It does not contain an optimum, dual-bound, or MIP-gap claim.

It does not contain suppressed keys or protected source values.

## Limits

This mode does not weaken a privacy rule.

This mode can produce an incomplete view.

Missing cells are privacy-suppressed.

This mode does not prove reconstruction safety.

Repeated releases need a joint disclosure review.

Merchant checks and complementary suppression remain consumer duties.
