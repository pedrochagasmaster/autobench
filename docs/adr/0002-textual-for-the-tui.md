# Textual is the TUI framework

The server-side TUI is built on **Textual** (Textualize), pinned to a specific
version with all transitive deps vendored as wheels under `vendor/` and
installed into a per-user venv on the Edge Node. The orchestrator scripts in
`scr/` keep their stdlib-only policy — this ADR loosens that rule for the TUI
only.

The TUI process is treated as untrusted infrastructure: per ADR-0001, it
never owns a Job. Framework choice therefore affects developer productivity
and aesthetic ceiling, not Job durability.

## Considered alternatives

- **`curses` (stdlib).** Rejected because the polish gap to a usable Job
  dashboard, file-tail widget, and form is large enough to dominate the build
  cost. Acceptable as a fallback only if Textual proves environmentally
  unworkable.
- **`urwid`.** Rejected as the named "boring fallback". Same architectural
  decoupling, smaller dep tree, but markedly worse DX and aesthetics. Worth
  reopening if Textual ever causes operational pain.
- **`prompt_toolkit`.** Wrong shape — optimised for editor-style apps, not
  dashboards.

## Consequences

- A `requirements.txt` with pinned versions plus a `vendor/` directory of
  wheels is added to the repo. Install is
  `pip install --user --no-index --find-links=vendor/ -r requirements.txt`.
- The TUI must use async-safe subprocess primitives
  (`asyncio.create_subprocess_exec` or `loop.run_in_executor`); blocking
  `subprocess.run` calls in callbacks would freeze the UI.
  `dispatch/process.py` is the single sanctioned entry point and enforces this.
- Textual is pre-1.0; we pin a version and treat the deps as frozen, only
  upgrading deliberately.
