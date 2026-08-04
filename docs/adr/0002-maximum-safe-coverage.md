# ADR 0002: Define the Maximum Safe Coverage release policy

- Status: Accepted
- Date: 2026-08-04

## Context

Autobench currently authorizes share-analysis output only when one global weight
vector makes the complete governed output pass the existing privacy policy. If
one governed output cell fails, no benchmark-bearing artifact is released.
Some inputs have no global vector that authorizes every cell even though a
strict subset could be released without weakening any privacy limit.

Autobench therefore needs an explicit policy for selecting the largest safe
subset, proving that the subset is maximum, and preventing suppressed data from
reaching or being restored by downstream client sinks.

## Decision

Autobench has exactly two privacy release modes:

- `complete-output` is the default and preserves existing behavior. It releases
  the complete governed output only when the current privacy policy authorizes
  that output.
- `maximize-safe-coverage` releases the maximum proven-safe subset of eligible
  share-analysis output. It never weakens or replaces an existing privacy rule.

Maximum Safe Coverage applies only to share analysis. Rate analysis and the
combination of Maximum Safe Coverage with per-dimension weights are rejected.
One global weight vector applies to every released Publication Unit; the mode
must not select a different vector by dimension, unit, metric, or sink.

The following terminology is normative:

- A **Publication Unit** is one all-or-nothing client output cell identified by
  its stable output scope, including dimension, category, time period, and any
  applicable output scope. All governed metrics for that key belong to the
  unit. The unit passes only when every required metric passes one complete
  applicable rule and every required mandatory overlay. A metric row is not a
  Publication Unit, and metrics from one unit cannot be released separately.
- The **Candidate Universe** is the fixed set of privacy-eligible Publication
  Units, constructed after existing structural category suppression and before
  coverage optimization. Optimization cannot add, remove, copy, or weight
  units in this universe.
- The **Release Set** is the set of Publication Units authorized for client
  output.
- The **Suppression Set** is the Candidate Universe minus the Release Set.
- The **Coverage Certificate** is client-safe evidence for the exact released
  artifact.
- The **Suppressed Publication View** is the filtered client artifact containing
  only the Release Set.

The optimization objective is lexicographic and is solved in stages, in this
exact priority order:

1. Maximize the count of released Publication Units.
2. Minimize total analytical distortion with that count fixed.
3. Minimize distance from neutral weights with the earlier objectives fixed.
4. Select one deterministic canonical release mask and weight vector.

Rows, metrics, volume, business value, target performance, and protected values
must not influence release priority. Unsafe large-coefficient combinations are
not an acceptable substitute for staged solves.

A result may be called **maximum** only when the solver reports an optimal
result, the primary integer objective is integral, the mixed-integer gap is
exactly zero under the solver contract, the rounded dual bound equals the
released-unit count, and an independent verifier accepts the exact result. A
time limit, a feasible result, or a small nonzero gap is not proof. An unproven
candidate must not reach a normal client sink.

Independent verification is fail-closed and does not trust solver pass flags.
It recalculates privacy from the original input and final global weights using
the existing rule evaluator, not the solver's constraint helpers. It verifies
Candidate Universe membership and uniqueness, complete required metrics,
applicable authorizing rules and mandatory overlays, global-vector bounds and
consistency, exact Release Set filtering, absence of Suppression Set units from
all client sinks, optimal status, zero gap, the proving dual bound, coherent
input/configuration/policy/universe/mask evidence, and hashes of the files
written to disk. Any verification failure blocks all benchmark-bearing output.

The Coverage Certificate contains only client-safe evidence: aggregate
candidate, released, and suppressed counts; coverage percentage; visible
Publication Unit keys and their authorizing rules; global weights only when
current policy permits publication; policy, solver, proof, and artifact-hash
metadata; and a digest over canonical safe fields. It must not contain a
suppressed key, a digest of an individual suppressed key, a suppressed category
name, protected source values, or per-rule failure details for suppressed
units. Missing cells in the Suppressed Publication View are identified only as
privacy-suppressed.

Consumers must preserve suppression monotonically:

```text
final_release_set must be a subset of autobench_release_set
```

A consumer may suppress more Publication Units but must never restore an
Autobench-suppressed unit. Every client sink must consume the exact verified
Release Set before formatting and must not rebuild output from an unfiltered
object.

## Guarantees

- Maximum Safe Coverage changes the release set, not privacy limits.
- Every visible Publication Unit passes as one all-metric unit under one global
  vector.
- Maximum coverage is claimed only with optimal, zero-gap, dual-bound, and
  independent-verifier evidence.
- Coverage evidence does not disclose suppressed unit identities or protected
  suppressed values.
- Empty, unproven, or invalid results produce only the current safe denial
  audit, never benchmark-bearing output.

## Non-goals

This policy does not prove that published output is safe from reconstruction.
Autobench proves only direct Control 3 privacy for this mode. Consumers remain
responsible for merchant, visible-total, complementary-suppression, recurring-
release, and joint-disclosure checks, and must provide complementary
suppression when required.

This decision does not add or weaken privacy rules or limits, change the Citi
mandatory overlay, introduce merchant-count or Getnet-specific policy, add
complementary-suppression equations, support rate analysis, assign business
weights to Publication Units, or create a general optimization framework.

## Consequences

Maximum Safe Coverage can produce an intentionally incomplete share-analysis
view. All interfaces and client sinks must apply the same verified Release Set,
and each new sink must be reviewed for suppression leaks. Operators and
consumers must retain proof evidence, preserve the monotone consumer rule, and
review recurring releases together because multiple individually safe releases
can enable reconstruction.