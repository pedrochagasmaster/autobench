# Mock layer for offline dev and end-to-end testing

The repository ships a `mocks/` directory that fakes every external system
the orchestrators and TUI depend on, so the entire tool can be run end-to-end
on a developer laptop or a Cursor Cloud Agent VM without an actual Hadoop
edge node, Kerberos KDC, or SMTP relay. This is the substrate that makes
end-to-end and manual testing possible in the first place, and is the
prerequisite for any modification of `scr/` (see ADR-0005).

## Layout

```
mocks/
├── bin/                       # placed first on $PATH by mocks/dev-env.sh
│   ├── impala-shell           # fake; reads $DISPATCH_MOCK_SCENARIO
│   ├── klist                  # fake; ticket TTL configurable
│   └── kinit                  # fake; accepts any password
├── smtpd.py                   # local stdlib smtpd; writes received messages
│                              # as .eml files to mocks/sent_emails/
├── scenarios/
│   ├── happy_path.json        # succeeds on adhoc_small first cycle
│   ├── all_queues_full.json   # cycles forever (kill to stop)
│   ├── memory_exceeded.json   # transient; clears after two cycles
│   ├── syntax_error.json      # fatal, immediate
│   ├── auth_error.json        # fatal, immediate
│   └── slow.json              # succeeds, but each query takes 30+ seconds
├── sent_emails/               # gitignored — captured emails, .eml format
└── dev-env.sh                 # `source` to enter dev mode
```

## Contract

Two environment variables drive the mock:

- **`DISPATCH_DATA_ROOT`** — overrides `/ads_storage/<user>/.dispatch/`. The
  TUI and the runner script honour this. The orchestrators don't read it
  directly (they're frozen-API), but they don't need to: they only write to
  `--session-folder` / `--output-file` paths the runner gives them, and the
  runner derives those from `DISPATCH_DATA_ROOT` when set.
- **`DISPATCH_MOCK_SCENARIO`** — read by the fake `impala-shell` to pick a
  behaviour from `mocks/scenarios/`. Defaults to `happy_path` when unset and
  the fake is on `$PATH`.

`mocks/dev-env.sh` exports both, prepends `mocks/bin/` to `$PATH`, sets
`MAILHOST` (consumed by a thin `scr/` adapter — see ADR-0005) to point at
the local fake SMTP at `127.0.0.1:2525`, starts the SMTP catcher in the
background, and prints a banner so the developer never confuses dev mode
with production.

## Considered alternatives

- **Run nothing locally; test only on the Edge Node.** Rejected: blocks
  every contributor without prod cluster access, makes CI for `scr/`
  refactoring impossible, and ties code review velocity to ssh availability.
- **Integration tests against a staging cluster.** A real future improvement,
  but it's expensive to provision and doesn't replace the need for a fast
  local feedback loop. Out of scope here.
- **Pure unit tests of the TUI without orchestrator integration.** Rejected
  as a sole strategy: the most interesting bugs live at the runner ↔
  orchestrator boundary, which unit tests can't cover.

## Consequences

- The fake `impala-shell` must accept the exact argv the orchestrators use
  (`-k -i <host> --ssl --delimited --print_header --output_delimiter=| -q
  <sql>` and the `-o <file>` form). Drift between the orchestrators' real
  invocation and the fake is an integration bug and is treated as one.
- Scenario JSON files are part of the tested contract: a new error
  classification added to `classificar_erro_impala` requires a matching
  scenario file before merge.
- `mocks/sent_emails/` is `.gitignore`d. The directory itself is created on
  demand by the SMTP catcher.
- The mock is a developer convenience and a CI substrate, not a security
  boundary. Production uses real `impala-shell`, real `klist`/`kinit`, and
  real `mailhost.mclocal.int`.
