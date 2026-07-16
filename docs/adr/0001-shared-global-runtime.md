# ADR 0001: Use one immutable shared runtime per Edge Node

- Status: Accepted
- Date: 2026-07-16

## Context

Autobench source is shared under `/ads_storage/autobench`, but the previous
installer created a separate virtual environment for every analyst. That made
dependency installation part of onboarding, duplicated large environments,
and gave source updates, dependency updates, failure recovery, and rollback
different operating models.

Autobench dependency bundles are already produced and verified by
edge-deploy. Their canonical `bundle_digest` identifies the exact requirements,
wheels, and target interpreter. Git commits and `VERSION` identify source
releases, not dependency runtime contents.

Autobench also has two kinds of state that must remain separate:

- one Release Operator-owned runtime and shared source tree; and
- private analyst state under `/ads_storage/<user>/.autobench`.

The existing shared telemetry tree under
`/ads_storage/autobench/telemetry` is a third ownership boundary. It remains
provisioned by the trusted operator path in `update.sh`.

## Decision

Each Edge Node has one Release Operator-managed runtime root:

```text
/ads_storage/autobench/.venv/
|-- releases/<bundle-digest>/
|-- current -> releases/<active-bundle-digest>
`-- install.lock
```

Runtime releases are immutable and addressed by the verified edge-deploy
dependency-bundle SHA-256 digest. A virtual environment is constructed directly
at its final `releases/<digest>` path because generated entrypoints embed
absolute paths.

`install.sh` is the non-interactive Release Operator interface. It validates
the verified offline bundle, serializes construction with a POSIX lock, creates
the candidate privately, installs with `--no-index`, runs `pip check`, imports
all required Autobench packages, and writes completion metadata only after
validation succeeds.

Activation atomically replaces `.venv/current`. Launchers resolve that symlink
to a physical path before `exec`, so an already-running process remains pinned
to its original runtime if a later deployment changes `current`.

The public shared launchers are:

- `/ads_storage/autobench/bin/autobench` for `tui_app.py`; and
- `/ads_storage/autobench/bin/autobench-cli` for `benchmark.py`.

`onboard.sh` is the analyst interface. It validates the active shared runtime,
creates or repairs only private `config`, `logs`, `cache`, and `telemetry`
directories, and installs thin launchers in `~/.local/bin`. It does not read a
dependency bundle, create a virtual environment, or run pip.

## Guarantees

- A source-only release reuses a complete runtime with the same digest.
- A dependency change creates a new runtime without modifying the previous
  one.
- A failed candidate never changes `current`.
- A corrupt active runtime is never rebuilt in place.
- A retained complete runtime can be reactivated for rollback without package
  installation or download.
- Completed runtimes are readable and executable by analysts but writable only
  by the Release Operator.
- Old complete runtimes and personal virtual environments are retained until a
  separately approved cleanup.
- Shared telemetry ownership and provisioning remain unchanged in `update.sh`;
  runtime installation never creates or weakens that tree.

## Consequences

Release Operators must deliver a valid dependency bundle before installation
and must manage runtime retention. Analysts no longer need bundle access or
dependency installation privileges. Existing personal launchers are replaced
by onboarding while private files and old personal virtual environments remain
untouched.
