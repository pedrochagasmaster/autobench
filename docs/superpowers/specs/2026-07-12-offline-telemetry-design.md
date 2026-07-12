# Autobench Offline Telemetry Design

Status: approved design; pending written-spec review

## Purpose and adaptation

Autobench will record low-volume product telemetry locally so edge-node
operators can answer who uses the application and how share and rate analyses
are used. Telemetry is self-reported product data, not an audit log, and must
never affect analysis, privacy enforcement, publication validation, or process
exit.

The reference design is adapted as follows:

| Setting | Autobench value |
|---|---|
| Application name | Autobench |
| Application slug | `autobench` |
| CLI command | `autobench-cli` / `benchmark.py` |
| Private home | `/ads_storage/<resolved-user>/.autobench` |
| Shared telemetry directory | `/ads_storage/autobench/telemetry` |
| Environment prefix | `AUTOBENCH` |
| Application version | canonical repository `VERSION` value |
| Shared access profile | portable local-readable |

Telemetry is enabled by default. Case-insensitive values `0`, `false`, `off`,
and `no` in `AUTOBENCH_TELEMETRY` disable private and shared writes.
`AUTOBENCH_TELEMETRY_DIR` overrides the shared telemetry directory exactly.
The override and the reader's `--dir` option both name the directory whose
direct child is `users/`.

The portable shared profile intentionally makes usernames and approved event
data readable by every local user. The deployment account creates
`/ads_storage/autobench/telemetry` with mode `0755` and its `users` child with
mode `1777`; the application never creates these shared parent directories.

## Architecture

A new `core.telemetry` package owns five independent concerns:

1. `identity` resolves the effective UID through NSS, validates the account
   name, and creates a deterministic base64url filename token without padding.
2. `events` defines the closed event catalog, property validation, envelope
   construction, and the 8 KiB encoded-record limit.
3. `writer` safely appends one serialized record to the private and shared
   destinations, attempting each destination independently.
4. `service` owns the state machine, bounded queue, daemon consumer, and
   bounded shutdown.
5. `reader` streams and validates files and produces aggregation models for
   the telemetry CLI.

Product code receives only event-specific helper methods. It will not receive
a public generic `emit(name, props)` API. Telemetry reader commands construct
the reader directly and do not initialize the writer or emit telemetry.

The service starts lazily with the first valid event. Producers perform only
bounded validation, envelope serialization, and a nonblocking enqueue. A
physical queue of `DATA_CAPACITY + 2` rejects ordinary events once
`DATA_CAPACITY` data records are queued, reserving slots for one session-end
record and one flush marker.

One daemon consumer drains records in order. It performs all filesystem work.
For each record it attempts the private append and then the shared append,
logging failures at debug level without propagating them.

## State and shutdown

The service state is guarded by the same lock used to admit records:

```text
accepting -> closing -> closed
```

Normal shutdown atomically enters `closing`, rejects new product events,
attempts to enqueue one `session_end`, and then attempts to enqueue one flush
marker. The consumer acknowledges the marker only after every earlier record
has completed both destination attempts. Shutdown waits at most the named
`SHUTDOWN_BUDGET_S = 0.250`, enters `closed`, and never restarts the consumer.
Missing control records, a blocked filesystem, and abrupt termination may lose
events by design.

## Event and privacy contract

Each JSONL line is a compact UTF-8 object followed by exactly one LF. The
envelope contains only:

- `schema_version`: integer `1`
- `ts`: strict UTC ISO-8601 timestamp ending in `Z`
- `event`: a catalogued name
- `user`: validated NSS username
- `session_id`: process-scoped random UUID
- `app_version`: canonical Autobench version
- `props`: the exact event-specific property object

The approved catalog is:

| Event | Allowed properties |
|---|---|
| `session_start` | `launch_context`: `cli_share`, `cli_rate`, or `tui` |
| `session_end` | `duration_s`: finite number from `0` through `31_536_000`, rounded to milliseconds |
| `surface_viewed` | `surface`: `share` or `rate` |
| `action_attempted` | `action`: `share_analysis` or `rate_analysis` |
| `action_completed` | `action`: `share_analysis` or `rate_analysis` |
| `action_cancelled` | `action`: `share_analysis` or `rate_analysis` |
| `action_refused` | `action`; `reason`: `configuration`, `input_validation`, or `compliance_policy` |
| `action_failed` | `action`; `category`: `input`, `analysis`, `output`, or `unexpected` |

Refusal `reason` values are `configuration`, `input_validation`, and
`compliance_policy`. Failure `category` values are `input`, `analysis`,
`output`, and `unexpected`. These values distinguish useful outcomes without
recording raw details or exception text.

Telemetry never records paths or basenames, entity names, account data from
input datasets, column or dimension names, presets, output names, command
arguments, environment values, exception text, domain objects, peer data, or
analysis results. Existing `RunObservability` metadata remains separate and is
not copied into telemetry.

## Filesystem safety

The private destination is
`/ads_storage/<resolved-user>/.autobench/telemetry/events.jsonl`. The writer
creates and enforces owner-only application and telemetry directories (`0700`)
and opens the file with mode `0600`.

The shared destination is
`/ads_storage/autobench/telemetry/users/<encoded-user-token>.jsonl`. New shared
files are normalized to mode `0644`.

Both destinations use descriptor-based opens with
`O_APPEND | O_CREAT | O_WRONLY | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW`.
Immediately after open, `fstat` must show a regular file owned by the effective
UID with exactly one link. The writer then enforces the final mode, attempts
`LOCK_EX | LOCK_NB`, and performs a bounded write loop that retries `EINTR`.
Every descriptor closes on every path. Symlinks, FIFOs, sockets, devices,
directories, foreign-owned files, multiply linked files, contended files, and
partial hard errors are skipped.

Shared telemetry is enabled only on Linux when the required open flags and
nonblocking `flock` are available and protected-hardlink behavior is enabled.
The deployment documentation records the required sticky-directory,
`O_APPEND`, `O_NOFOLLOW`, `O_NONBLOCK`, `fstat`, advisory-lock, and rename
semantics. If the capability gate fails, only the shared writer is disabled.

## Instrumentation seams

CLI share and rate commands create a session after argument parsing succeeds
and before the analysis becomes usable. The TUI creates a session once it is
mounted and usable. Each entry point closes its session in a `finally` path.

Analysis instrumentation sits at the shared orchestration boundary so CLI and
TUI behavior uses one catalog:

- attempt after a valid durable run request exists and execution is about to
  start;
- refusal when configuration, validation, or compliance policy prevents work;
- completion only after terminal analysis and required output handling succeed;
- failure when a terminal categorized error is observed;
- cancellation only where the application receives an explicit user
  cancellation signal.

TUI navigation emits `surface_viewed` only when a meaningful top-level surface
is actually shown, not on focus, keystrokes, logs, modal redraws, or low-level
widget events.

## Aggregation CLI

`benchmark.py telemetry who [--days N] [--dir PATH]` reports each user,
distinct session-start count, last-seen UTC timestamp, and completed-analysis
count. `benchmark.py telemetry summary [--days N] [--dir PATH]
[--user NAME]` reports deterministic counts by surface, action, and terminal
outcome. Human-readable output is the initial format.

The reader prefers shared `users/*.jsonl` files when at least one expected
event file is present; otherwise it reads only the current user's private
file. It never combines dual-written sources.

Every file is opened with
`O_RDONLY | O_CLOEXEC | O_NONBLOCK | O_NOFOLLOW` and accepted only if `fstat`
shows a regular singly linked file. Shared files are rejected before
aggregation unless the filename token matches the encoding of the record user,
NSS resolves that user, and the file owner matches the resolved UID. Each line
has a bounded byte length and must pass complete envelope and property-schema
validation.

The reader streams lines, isolates malformed lines, warns visibly for
unsupported schema versions, parses timestamps strictly, applies an inclusive
`ts >= now - days` boundary, and rejects timestamps beyond a documented
five-minute future-skew allowance. Sessions are distinct valid
`(user, session_id)` pairs observed on `session_start`. Last seen is the latest
accepted event. Output values are enum-controlled or terminal-sanitized and
sorted deterministically.

## Deployment and operations

The deployment/update path provisions and normalizes the shared directories;
runtime users do not. Deployment validation must run on the actual edge-node
mount and verify the filesystem capability gate, sticky-directory behavior,
safe file creation, advisory locking across processes, and rotation rename
semantics. Operational checks should flag owner/filename identity mismatches,
which can indicate a username pre-creation denial of service.

Opt-out stops future writes and does not delete existing records. Retention,
rotation, deletion authorization, and fleet collection remain operator-owned
procedures outside this implementation. No generated telemetry or reports are
committed to the repository.

## Testing

Implementation follows test-first development. Tests cover:

- identity validation and collision-free token encoding;
- exact event schemas, forbidden keys and values, byte-size limits, and
  sensitive-data rejection;
- queue capacity, drop-newest behavior, ordering, reserved slots, service
  states, idempotent shutdown, and the 250 ms upper bound;
- safe append behavior for permissions, symlinks, FIFOs, hardlinks, foreign
  ownership, lock contention, interrupted writes, and independent private and
  shared failure;
- environment opt-out, directory override, shared capability fallback, and
  lazy initialization;
- strict reader validation, oversized and malformed lines, owner/token
  mismatch, schema warnings, date/future-skew filtering, source preference,
  deterministic aggregation, and terminal-safe output;
- CLI parser behavior and confirmation that telemetry reader commands do not
  initialize the interactive application or writer;
- CLI and TUI session/action/surface integration without sensitive values.

Verification runs focused telemetry tests first, then Ruff, mypy over
`core/` and `utils/`, and the complete pytest suite.
