# Autobench Offline Telemetry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add default-enabled, privacy-minimized, offline JSONL telemetry for
Autobench sessions and analyses, plus safe local `who` and `summary` reports.

**Architecture:** A focused `core/telemetry/` package separates identity and
schema validation, safe append operations, queue/service lifecycle, safe
streaming reads, and rendering. Product code calls only typed event helpers.
CLI/TUI integration emits at domain boundaries, and the deployment script
provisions the portable shared directory.

**Tech Stack:** Python 3.10+, stdlib `queue`, `threading`, `fcntl`, `pwd`,
descriptor-based `os` APIs, argparse, Textual, pytest, Ruff, and mypy.

**Locked choices:** data capacity is 256 records; encoded JSONL records are at
most 8 KiB including LF; future timestamp tolerance is five minutes; CLI
lookback defaults to 30 days; usernames are valid nonempty NSS names of at most
128 UTF-8 bytes with no separators, traversal names, or control characters.

---

## File structure

- `core/telemetry/constants.py`: numeric limits, environment names, and default
  paths.
- `core/telemetry/identity.py`: effective-UID NSS resolution, validation, and
  base64url token encoding.
- `core/telemetry/events.py`: exact event/property schemas, envelope creation,
  strict decoding, timestamp validation, and serialization.
- `core/telemetry/capability.py`: Linux/shared-filesystem runtime gate.
- `core/telemetry/writer.py`: private/shared path construction and safe append.
- `core/telemetry/service.py`: queue, daemon consumer, state, and shutdown.
- `core/telemetry/__init__.py`: typed best-effort product helpers only.
- `core/telemetry/reader.py`: safe streaming source selection and aggregation.
- `core/telemetry/render.py`: terminal-safe deterministic reports.
- `scripts/validate_telemetry_filesystem.py`: operator capability validation.
- `tests/telemetry/`: focused unit and integration tests.

No module may add an import inside a function or method. No generic public
`emit(name, props)` function is permitted.

### Task 1: Identity and event contracts

**Files:**
- Create: `core/telemetry/__init__.py`
- Create: `core/telemetry/constants.py`
- Create: `core/telemetry/identity.py`
- Create: `core/telemetry/events.py`
- Create: `tests/telemetry/test_identity.py`
- Create: `tests/telemetry/test_events.py`

- [ ] **Step 1: Write identity tests before production code**

Test these exact APIs:

```python
@dataclass(frozen=True)
class Identity:
    uid: int
    username: str
    token: str

def validate_username(username: str) -> str: ...
def encode_user_token(username: str) -> str: ...
def resolve_identity(
    *,
    geteuid: Callable[[], int] = os.geteuid,
    getpwuid: Callable[[int], Any] = pwd.getpwuid,
) -> Identity: ...
def lookup_uid(username: str) -> int: ...
```

Tests must prove effective UID—not `USER`/`LOGNAME`—drives NSS lookup;
base64url encoding is deterministic, unpadded, reversible, collision-free for
the fixture set, and matches `[A-Za-z0-9_-]{1,172}`; and empty names, `.`, `..`,
`/`, `\`, controls, and names over 128 encoded bytes are rejected.

- [ ] **Step 2: Run the identity tests and verify RED**

Run:

```bash
python -m pytest tests/telemetry/test_identity.py -v
```

Expected: collection fails because `core.telemetry.identity` does not exist.

- [ ] **Step 3: Implement constants and identity minimally**

Define:

```python
SCHEMA_VERSION = 1
MAX_RECORD_BYTES = 8192
SHARED_GATE_SCAN_MAX_BYTES = 64 * 1024
DATA_CAPACITY = 256
PHYSICAL_QUEUE_CAPACITY = DATA_CAPACITY + 2
SHUTDOWN_BUDGET_S = 0.250
FUTURE_SKEW_S = 300
DEFAULT_DAYS = 30
DEFAULT_SHARED_DIR = Path("/ads_storage/autobench/telemetry")
DISABLED_VALUES = frozenset({"0", "false", "off", "no"})
```

Encode validated UTF-8 username bytes with
`base64.urlsafe_b64encode(...).rstrip(b"=")` and validate the resulting token
against the documented grammar.

- [ ] **Step 4: Run identity tests and verify GREEN**

- [ ] **Step 5: Write event tests before event implementation**

Lock these types and functions:

```python
class EventValidationError(ValueError): ...
class UnsupportedSchemaVersion(EventValidationError): ...

@dataclass(frozen=True)
class ValidatedEvent:
    schema_version: int
    ts: datetime
    event: str
    user: str
    session_id: str
    app_version: str
    props: Mapping[str, object]

def build_record(
    event: str,
    props: Mapping[str, object],
    *,
    user: str,
    session_id: UUID,
    app_version: str,
    now: datetime | None = None,
) -> bytes: ...

def decode_record(raw_line: bytes) -> ValidatedEvent: ...
```

Parametrize all eight approved events. Require exact envelope and property key
sets, UUID session IDs, strict UTC `Z` timestamps, nonempty bounded version,
finite `duration_s` from 0 through 31,536,000 rounded to milliseconds, one
trailing LF, compact JSON, and an 8 KiB encoded-byte limit. Verify unknown
events, extra/missing keys, nested/arbitrary payloads, NaN/infinity, bad enums,
invalid usernames, invalid UUIDs, unsupported schema versions, malformed
UTF-8/JSON, and sensitive-looking extra keys are rejected.

- [ ] **Step 6: Run event tests and verify RED**

Run:

```bash
python -m pytest tests/telemetry/test_events.py -v
```

- [ ] **Step 7: Implement the exact catalog and verify GREEN**

Use these property schemas:

```text
session_start: launch_context=cli_share|cli_rate|tui
session_end: duration_s=finite bounded number
surface_viewed: surface=share|rate
action_attempted|completed|cancelled: action=share_analysis|rate_analysis
action_refused: action plus reason=configuration|input_validation|compliance_policy
action_failed: action plus category=input|analysis|output|unexpected
```

- [ ] **Step 8: Commit the task**

```bash
git add core/telemetry tests/telemetry
git commit -m "feat: define telemetry identity and event contracts"
git push -u origin cursor/offline-telemetry-abe3
```

### Task 2: Safe writer and capability gate

**Files:**
- Create: `core/telemetry/capability.py`
- Create: `core/telemetry/writer.py`
- Create: `tests/telemetry/test_capability.py`
- Create: `tests/telemetry/test_writer.py`

- [ ] **Step 1: Write capability and writer tests**

Lock these APIs:

```python
def shared_writer_supported(users_dir: Path) -> bool: ...

@dataclass(frozen=True)
class WriterPaths:
    private_file: Path
    shared_users_dir: Path

@dataclass(frozen=True)
class AppendResult:
    private_ok: bool
    shared_attempted: bool
    shared_ok: bool

def paths_for(identity: Identity, shared_dir: Path) -> WriterPaths: ...
def append_one(
    path: Path,
    record: bytes,
    *,
    expected_uid: int,
    final_mode: int,
    create_private_parents: bool,
) -> bool: ...
def append_record(
    record: bytes,
    *,
    identity: Identity,
    paths: WriterPaths,
    shared_enabled: bool,
) -> AppendResult: ...
```

The gate tests cover non-Linux, every required `os`/`fcntl` primitive,
`/proc/sys/fs/protected_hardlinks != 1`, missing/non-directory `users`,
and absence of sticky/world-write/search mode. It returns false rather than
raising. Runtime gating supplements—not replaces—the operator filesystem
validation task.

Writer tests use only `tmp_path` and verify private `.autobench/telemetry`
directories are normalized to `0700`, private files to `0600`, shared parent
directories are never created at runtime, and shared files become `0644`.
Spy on `os.open` for
`O_APPEND|O_CREAT|O_WRONLY|O_CLOEXEC|O_NONBLOCK|O_NOFOLLOW`.

Use deadline-guarded tests for attacker-planted symlink, FIFO, directory,
socket/device where available, hardlink, foreign owner, and lock contention.
Require descriptor `fstat` regular-file/effective-owner/single-link checks,
`LOCK_EX|LOCK_NB`, `fchmod`, EINTR retry, short-write completion, and close on
every error path. Verify private and shared failures are independent.

- [ ] **Step 2: Run writer tests and verify RED**

```bash
python -m pytest tests/telemetry/test_capability.py tests/telemetry/test_writer.py -v
```

- [ ] **Step 3: Implement safe append without path-based trust checks**

All trust decisions after open use the descriptor. The shared path is exactly
`<shared-dir>/users/<identity.token>.jsonl`; the private path is exactly
`/ads_storage/<identity.username>/.autobench/telemetry/events.jsonl`, with an
injectable storage root for tests. A hard write error returns false; it never
raises through the product facade.

- [ ] **Step 4: Run tests and verify GREEN**

- [ ] **Step 5: Commit and push**

```bash
git add core/telemetry/capability.py core/telemetry/writer.py tests/telemetry
git commit -m "feat: safely append private and shared telemetry"
git push -u origin cursor/offline-telemetry-abe3
```

### Task 3: Bounded service and typed product helpers

**Files:**
- Create: `core/telemetry/service.py`
- Modify: `core/telemetry/__init__.py`
- Create: `tests/telemetry/test_service.py`
- Create: `tests/telemetry/test_public_helpers.py`

- [ ] **Step 1: Write service lifecycle tests**

Construct `TelemetryService` with injected identity, monotonic/UTC clocks,
version, environment mapping, append callback, capacity, and shutdown budget.
Test no thread exists before the first valid accepted event; physical capacity
is data capacity plus two; data admission stops at 256 queued data records;
newest events drop without waiting; and one daemon consumer preserves FIFO
order without holding the admission lock during writes.

Use a blocking fake writer released in `finally` to prove shutdown returns
within `0.250 + 0.050` seconds. Verify
`accepting -> closing -> closed`, one reserved session-end followed by one
flush marker, acknowledgement only after prior appends, idempotent shutdown,
control-record overflow tolerance, event rejection during closing/closed,
writer exception isolation, and no restart after closed.

- [ ] **Step 2: Run service tests and verify RED**

```bash
python -m pytest tests/telemetry/test_service.py -v
```

- [ ] **Step 3: Implement service and public facade**

Expose only:

```python
def start_session(launch_context: LaunchContext) -> None: ...
def end_session() -> None: ...
def surface_viewed(surface: Surface) -> None: ...
def action_attempted(action: Action) -> None: ...
def action_completed(action: Action) -> None: ...
def action_cancelled(action: Action) -> None: ...
def action_refused(action: Action, reason: RefuseReason) -> None: ...
def action_failed(action: Action, category: FailCategory) -> None: ...
```

Every helper catches all telemetry exceptions, validates before enqueue, and
logs only debug diagnostics. The process singleton reads the canonical
repository `VERSION`, creates one random UUID, and computes duration from
monotonic session start. Default-on configuration is disabled only by
case-insensitive `0`, `false`, `off`, or `no`; the shared override names the
parent of `users/` exactly. Invalid configuration disables the affected write
path without affecting the app. Keep a private `_reset_for_tests()` hook.

- [ ] **Step 4: Write and pass public-helper tests**

Verify exact helper delegation, opt-out spellings, default enabled behavior,
override handling, no generic `emit`, invalid arguments never raising, and
reader-module imports not constructing or starting the service.

- [ ] **Step 5: Commit and push**

```bash
git add core/telemetry tests/telemetry
git commit -m "feat: add bounded best-effort telemetry service"
git push -u origin cursor/offline-telemetry-abe3
```

### Task 4: Safe reader, aggregation, and rendering

**Files:**
- Create: `core/telemetry/reader.py`
- Create: `core/telemetry/render.py`
- Create: `tests/telemetry/test_reader.py`
- Create: `tests/telemetry/test_aggregation.py`
- Create: `tests/telemetry/test_render.py`

- [ ] **Step 1: Write safe-reader tests**

Lock result models:

```python
@dataclass(frozen=True)
class WhoRow:
    user: str
    sessions: int
    last_seen: datetime
    completed: int

@dataclass(frozen=True)
class Summary:
    surfaces: Mapping[str, int]
    actions: Mapping[str, int]
    outcomes: Mapping[str, int]
```

Open only direct `*.jsonl` entries with
`O_RDONLY|O_CLOEXEC|O_NONBLOCK|O_NOFOLLOW`; require regular, singly linked
files. Private reads additionally require effective-UID ownership. Stream
bounded lines without loading history and discard a final unterminated line.
Skip malformed/oversized lines independently and warn for unsupported schema.

For each shared file, buffer no more than the first valid event before
acceptance. Before yielding it, require the filename token to equal the
encoding of its user, NSS lookup of that user to equal descriptor `st_uid`,
and all later records to carry that same user. Reject the whole file when the
initial owner/token identity check fails.

Shared source preference requires at least one *qualifying* expected event
file (safe open + first schema-valid owner/token gate + safe ancestors).
Hostile symlink/FIFO/hardlink/malformed/token-mismatch entries alone must fall
back to private; when any file qualifies, select only sorted qualifying shared
paths and never combine private. For `--user`, if any shared file qualifies
fleet-wide, stay shared-only and include the encoded user path only when it
qualifies (empty shared otherwise); do not accept a raw filename by token
grammar alone.

Pre-gate discovery of that first owner/token event is limited by
`SHARED_GATE_SCAN_MAX_BYTES` (64 KiB physical `os.read` bytes, counting
oversized/no-LF/invalid content). The budget applies only before the gate
during qualification and TOCTOU reopen re-gating; files with no gate event in
budget are rejected/nonqualifying. After a successful gate, lift the budget and
continue full-file streaming from the same buffered iterator with ordinary
per-line 8 KiB limits and malformed-line isolation.

Test the inclusive days boundary, no lower bound when days is `None`, rejection
beyond five minutes future skew, `--user` validation/token path resolution,
and terminal-control rejection/sanitization.

- [ ] **Step 2: Run reader tests and verify RED**

```bash
python -m pytest tests/telemetry/test_reader.py -v
```

- [ ] **Step 3: Implement source selection and streaming**

When at least one direct shared `users/*.jsonl` candidate *qualifies* as an
expected event file (safe open/fstat, first schema-valid owner/token gate within
`SHARED_GATE_SCAN_MAX_BYTES`, safe ancestors), select only the sorted
qualifying shared paths. Otherwise select only the current user's private file.
Never combine copies. Hostile non-qualifying `*.jsonl` entries must not
suppress private fallback.

- [ ] **Step 4: Write aggregation and rendering tests**

`who` counts distinct `(user, session_id)` pairs on valid `session_start`,
maximum accepted timestamp, and each `action_completed`. `summary` counts
surfaces, action categories for all action events, and terminal completed,
cancelled, refused, and failed outcomes. Sort users and dimensions in fixed
catalog order.

Lock human output with golden strings. Remove ANSI CSI/OSC sequences and replace
remaining C0/C1 controls before rendering. Use UTC second-precision `Z`
timestamps.

- [ ] **Step 5: Implement and pass all focused tests**

```bash
python -m pytest tests/telemetry/test_reader.py tests/telemetry/test_aggregation.py tests/telemetry/test_render.py -v
```

- [ ] **Step 6: Commit and push**

```bash
git add core/telemetry/reader.py core/telemetry/render.py tests/telemetry
git commit -m "feat: aggregate safe offline telemetry reports"
git push -u origin cursor/offline-telemetry-abe3
```

### Task 5: Aggregation CLI

**Files:**
- Modify: `benchmark.py`
- Create: `tests/telemetry/test_cli.py`
- Modify: `README.md`

- [ ] **Step 1: Write parser and dispatch tests**

Test:

```text
benchmark.py telemetry who [--days N] [--dir PATH]
benchmark.py telemetry summary [--days N] [--dir PATH] [--user NAME]
```

Require default 30 days, inclusive nonnegative days, exact `--dir` semantics,
deterministic empty and populated output, invalid-user errors, and visible
schema warnings. Unit tests must prove telemetry commands do not call analysis
logging, session helpers, writer append, or interactive TUI code.

- [ ] **Step 2: Run CLI tests and verify RED**

```bash
python -m pytest tests/telemetry/test_cli.py -v
```

- [ ] **Step 3: Implement top-level imports, parser, and early dispatch**

Dispatch telemetry immediately after version/config handling and before
analysis logging or session startup. Return zero for a valid empty report and
one for invalid CLI filters/configuration. Do not add inline imports; while
touching `benchmark.py`, move its existing local imports to module scope when
needed to satisfy the workspace rule.

- [ ] **Step 4: Update README usage/privacy disclosure and pass tests**

- [ ] **Step 5: Commit and push**

```bash
git add benchmark.py README.md tests/telemetry/test_cli.py
git commit -m "feat: add telemetry who and summary commands"
git push -u origin cursor/offline-telemetry-abe3
```

### Task 6: Analysis, CLI-session, and TUI instrumentation

**Files:**
- Modify: `core/analysis_run.py`
- Modify: `benchmark.py`
- Modify: `tui_app.py`
- Create: `tests/telemetry/test_analysis_integration.py`
- Create: `tests/telemetry/test_cli_session.py`
- Create: `tests/telemetry/test_tui_integration.py`

- [ ] **Step 1: Write shared-analysis integration tests**

Refactor the existing `_execute_run` body to `_execute_run_impl` only after
tests fail. Keep `_execute_run` as a thin telemetry wrapper. A private tracker
sets the current phase (`configuration`, `input`, `analysis`, `output`) at
explicit boundaries inside the implementation without capturing request data.
The wrapper emits attempt first, completion after all output/audit work, maps
`RunBlocked` to refusal `compliance_policy`, maps `RunAborted` to refusal
`input_validation`, maps pre-analysis configuration rejection to refusal
`configuration`, and maps other failures to the current stable category before
re-raising the original exception unchanged.

Tests cover successful share/rate order, each refusal/failure category,
telemetry-helper exceptions not changing outcomes, and captured serialized
records containing no paths, entity/column/dimension names, presets, argv,
exceptions, observability metadata, peers, or analysis output.

- [ ] **Step 2: Run integration tests and verify RED**

```bash
python -m pytest tests/telemetry/test_analysis_integration.py -v
```

- [ ] **Step 3: Implement analysis instrumentation and verify GREEN**

- [ ] **Step 4: Write CLI-session and TUI tests**

CLI share/rate starts `cli_share`/`cli_rate` only after parser and preset
validation and ends in `finally`; config, version, help, and telemetry commands
start no session.

TUI starts `tui` after successful mount, emits initial `share`, emits `share` or
`rate` only on actual top-level tab activation, and ends on unmount. Emit
`action_cancelled` only when the validation modal returns false, using the
saved request mode. CSV-picker cancellation and quit confirmation are not
analysis cancellation seams. Shared orchestration events must not be duplicated
by CLI/TUI exception handlers.

- [ ] **Step 5: Implement and run focused integration tests**

```bash
python -m pytest tests/telemetry/test_cli_session.py tests/telemetry/test_tui_integration.py tests/test_analysis_run_integration.py tests/test_tui_contracts.py -v
```

- [ ] **Step 6: Commit and push**

```bash
git add core/analysis_run.py benchmark.py tui_app.py tests/telemetry
git commit -m "feat: instrument Autobench sessions and analyses"
git push -u origin cursor/offline-telemetry-abe3
```

### Task 7: Deployment provisioning and filesystem validation

**Files:**
- Modify: `update.sh`
- Create: `scripts/validate_telemetry_filesystem.py`
- Modify: `docs/edge-node-first-time-setup.md`
- Modify: `docs/production-testing.md`
- Modify: `tests/test_production_scripts.py`
- Modify: `tests/test_edge_node_operating_model.py`

- [ ] **Step 1: Write deployment contract tests**

Tests require the trusted update path to create the configured telemetry parent
and `users` child, normalize `0755`/`1777`, and leave per-user installation
unable to provision shared parents. The validator must report pass/fail for
Linux required flags, protected hardlinks, sticky/world-writable/search mode,
regular owner/link reporting, nonblocking cross-process advisory lock,
append behavior, FIFO nonblocking behavior, and same-filesystem rename.

- [ ] **Step 2: Run deployment tests and verify RED**

```bash
python -m pytest tests/test_production_scripts.py tests/test_edge_node_operating_model.py -v
```

- [ ] **Step 3: Implement provisioning and validator**

`update.sh`, which runs as the trusted deployment owner, uses:

```sh
TELEMETRY_DIR="${AUTOBENCH_TELEMETRY_DIR:-/ads_storage/autobench/telemetry}"
mkdir -p "$TELEMETRY_DIR/users"
chmod 0755 "$TELEMETRY_DIR"
chmod 1777 "$TELEMETRY_DIR/users"
```

The Python validator creates unpredictable `O_EXCL|O_NOFOLLOW` temporary entries
under `users`, cleans up only its owned entries, and exits nonzero when any
required guarantee fails. It never reads telemetry payloads.

- [ ] **Step 4: Document world-readable disclosure and operations**

Document default-on opt-out, override semantics, local readability, capability
validation command, shared fallback behavior, pre-creation denial of service,
retention/deletion ownership, and the prohibition on treating telemetry as an
audit record.

- [ ] **Step 5: Commit and push**

```bash
git add update.sh scripts/validate_telemetry_filesystem.py docs tests/test_production_scripts.py tests/test_edge_node_operating_model.py
git commit -m "feat: provision and validate shared telemetry storage"
git push -u origin cursor/offline-telemetry-abe3
```

### Task 8: Privacy regression and full verification

**Files:**
- Create: `tests/telemetry/test_privacy_regression.py`
- Modify only if failures expose a telemetry defect.

- [ ] **Step 1: Add privacy/non-interference regression tests**

Run equivalent share analyses with telemetry enabled and disabled and assert
equal compliance verdicts and analysis results. Verify strict publication
withholding is unchanged, no telemetry fields enter analysis metadata/audit
artifacts, no raw exception/path/request values reach JSONL, and no generated
JSONL is tracked.

- [ ] **Step 2: Run all telemetry tests**

```bash
python -m pytest tests/telemetry -v
```

- [ ] **Step 3: Run static checks**

```bash
python -m ruff check .
python -m mypy core/ utils/
```

- [ ] **Step 4: Run the complete suite**

```bash
python -m pytest -n 4 --dist loadfile
```

Expected: all tests pass with no telemetry errors or warnings.

- [ ] **Step 5: Commit any focused verification fixes and push**

```bash
git add core benchmark.py tui_app.py update.sh scripts docs README.md tests
git commit -m "test: verify offline telemetry privacy and resilience"
git push -u origin cursor/offline-telemetry-abe3
```

- [ ] **Step 6: Update the draft pull request**

Record exact test results and release risk. Do not add generated telemetry,
reports, credentials, or deployment artifacts.
