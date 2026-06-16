# `/goal` Prompt: Phase 3 Resilience and Observability

```text
/goal Execute Phase 3: Resilience & Observability from `docs/prototype-to-production-plan.md` without stopping until the Dispatch TUI degrades gracefully under the main failure conditions, user-facing crashes are replaced with clear behavior and logging, and the local validation loop is green.

Before changing anything:
- Read `AGENTS.md`.
- Read `CONTEXT.md`.
- Read `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Read `docs/prototype-to-production-plan.md`.
- Read `docs/ui-ux-screenshot-review-2026-05-16.md`.
- Read `docs/plan.md` if present.
- Read the relevant implementation files first:
  - `dispatch/app.py`
  - `dispatch/config.py`
  - `dispatch/kerberos.py`
  - `dispatch/jobs.py`
  - `dispatch/manifest.py`
  - `dispatch/screens/new_job.py`
  - `dispatch/screens/browser.py`
  - any startup/bootstrap entrypoints involved in app launch
- Start by summarizing the current Phase 3 gaps, the intended production-plan behavior, and the exact failure paths and files involved before editing.

Primary objective:
- Implement the full Phase 3 resilience and observability work described in `docs/prototype-to-production-plan.md`.

Required scope:
1. Add crash logging or equivalent startup/runtime error logging.
   - Failures that should not silently disappear must be logged to the intended persistent location or an equivalent documented path.
   - Logging must support diagnosing startup and runtime failures without surfacing raw tracebacks to end users in the normal UI flow.

2. Handle missing config gracefully.
   - If required config is missing, the app should degrade in a controlled, user-readable way instead of crashing.
   - The behavior should match the production plan as closely as possible.

3. Make SQL read and preview failures safe and user-readable wherever still needed.
   - Missing or unreadable SQL inputs must produce clear feedback rather than traceback-driven failure.

4. Add minimum-terminal-size or terminal-degradation handling if Phase 3 requires it.
   - The app should fail gracefully or guide the user if the terminal is too small for safe operation.

5. Gracefully handle Kerberos failure states.
   - Missing, expired, or insufficient Kerberos state should produce explicit UI behavior and clear messages rather than brittle or late failures.

6. Handle corrupt or unreadable manifests safely.
   - The TUI should not silently swallow important manifest failures without surfacing enough context for the user or maintainer.
   - If some manifests are unreadable, the app should degrade safely and remain usable where possible.

7. Add loading, timeout, or slow-operation feedback where the production plan calls for it.
   - Browser or metadata operations that can feel stalled should provide user feedback rather than looking frozen.

Constraints:
- Preserve Dispatch v1.0 product invariants from `AGENTS.md` and `CONTEXT.md`.
- Do not broaden scope beyond Phase 3 unless a tiny adjacent fix is required to complete the resilience contract.
- Do not redesign the whole UI.
- Do not change `scr/`.
- Keep `dispatch/process.py` as the subprocess gateway.
- Follow the project’s Textual-specific guidance from `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Prefer incremental checkpoints with a still-runnable app after each one.

Implementation plan:
- Work in explicit checkpoints and keep a short progress log in the thread.
- Suggested checkpoints:
  1. Confirm current failure behavior and identify exact call sites.
  2. Add crash/error logging path.
  3. Handle missing-config startup gracefully.
  4. Handle Kerberos failure states more explicitly.
  5. Handle corrupt/unreadable manifests safely.
  6. Add timeout/loading feedback for slow operations.
  7. Add terminal-size or degradation handling if required.
  8. Add or update tests.
  9. Run final validation and review for regressions.

Validation loop:
- After each meaningful checkpoint, run:
  - `python -m compileall dispatch scr`
  - `python -m dispatch --help`
- After UI changes, run the local mock app path with:
  - `source mocks/dev-env.sh`
  - `DISPATCH_MOCK_SCENARIO=happy_path python -m dispatch`
- Exercise the most relevant failure scenarios when practical:
  - `auth_error`
  - `slow`
  - any local setup that reproduces missing config or unreadable state
- Add or update the strongest relevant automated tests for:
  - startup degradation
  - missing config
  - Kerberos failure paths
  - corrupt manifest handling
  - loading and timeout UI behavior
- Inspect final behavior for any remaining raw traceback exposure in user-facing flows.

Done when:
- The TUI no longer falls over on the main documented failure modes.
- Missing config degrades gracefully.
- Kerberos failure states are explicit and user-readable.
- Corrupt or unreadable manifests are handled safely.
- Logging exists for important failures.
- Relevant tests and validation commands pass.
- Final report includes:
  - completed checkpoints
  - files changed
  - validation evidence
  - any residual risks still requiring real edge-node validation

Pause conditions:
- Pause if a required resilience fix would violate a documented product invariant.
- Pause if the production plan conflicts with current architecture in a way that needs a product decision.
- Pause if a required validation step depends on unavailable corporate infrastructure rather than local mocks.

Progress reporting:
- Keep updates compact.
- Each status update should say:
  - current checkpoint
  - what was verified
  - what remains
  - whether blocked

Stop only when the stopping condition is satisfied or you are genuinely blocked by one of the pause conditions.
```
