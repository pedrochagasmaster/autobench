# `/goal` Prompt: Phase 1 Safety Hardening

```text
/goal Execute Phase 1: Safety from `docs/prototype-to-production-plan.md` without stopping until every destructive or irreversible Dispatch TUI action is explicitly confirmed, the SQL preview flow is no longer misleading, and the local validation loop is green.

Before changing anything:
- Read `AGENTS.md`.
- Read `CONTEXT.md`.
- Read `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Read `docs/prototype-to-production-plan.md`.
- Read `docs/ui-ux-screenshot-review-2026-05-16.md`.
- Read `docs/plan.md` if present.
- Read the relevant implementation files first:
  - `dispatch/screens/browser.py`
  - `dispatch/screens/job_detail.py`
  - `dispatch/screens/new_job.py`
  - `dispatch/screens/preview.py`
  - `dispatch/process.py`
  - `dispatch/jobs.py`
  - `dispatch/manifest.py`
  - `dispatch/app.py`
- Start by summarizing the current Phase 1 gaps and the exact files/actions involved before editing.

Primary objective:
- Implement the full Phase 1 safety hardening described in `docs/prototype-to-production-plan.md`.

Required scope:
1. Create a reusable confirmation modal screen.
   - Add a `dispatch/screens/confirm.py` implementation or equivalent reusable confirmation screen.
   - It must support a title, body text, danger styling, and an explicit confirm/cancel result.
   - It must work cleanly with keyboard input and focus inside Textual.
   - It should support at least `Enter`, `Escape`, and direct yes/no style confirmation keys if appropriate.

2. Gate DROP TABLE behind confirmation.
   - In the Browser flow, pressing the destructive drop action must open the confirmation modal first.
   - Only confirmed actions may call the actual drop path.
   - The confirmation copy must clearly identify the table being dropped.

3. Gate Cancel Job behind confirmation.
   - In the Job Detail flow, pressing cancel must open the confirmation modal first.
   - The confirmation must include the job ID and PID when available.
   - Only confirmed actions may call `process.cancel_process_group()` or the equivalent cancellation path.

4. Gate Launch Job behind confirmation.
   - In the New Job flow, launching must require explicit confirmation first.
   - The confirmation should summarize the source, destination, target table, and any key launch details that reduce accidental execution.

5. Make SQL preview safe on missing files.
   - The preview flow must not crash or surface raw Python tracebacks for missing or unreadable SQL files.
   - The user must see clear, actionable feedback in the TUI.

6. Fix SQL Preview “Launch” semantics.
   - If the Preview screen says `Launch`, it must actually launch through the correct new-job submission path.
   - If that is not the right UX, rename the action so the wording exactly matches the behavior.
   - There must be no misleading path where the user believes a job launched when it only popped a screen.

Constraints:
- Preserve Dispatch v1.0 product invariants from `AGENTS.md` and `CONTEXT.md`.
- Do not broaden scope beyond Phase 1 unless a tiny adjacent fix is required to complete the safety contract.
- Do not redesign the whole UI.
- Do not change `scr/` unless absolutely necessary; if you think a `scr/` change is needed, stop and explain why against ADR policy before proceeding.
- Keep `dispatch/process.py` as the subprocess gateway.
- Prefer small checkpoints with a working app after each checkpoint.
- Follow the project’s Textual-specific guidance from `.agents/skills/dispatch-textual-tui/SKILL.md`.

Implementation plan:
- Work in explicit checkpoints and keep a short progress log in the thread.
- Suggested checkpoints:
  1. Confirm current behavior and identify exact call sites.
  2. Add reusable `ConfirmScreen`.
  3. Wire Browser DROP confirmation.
  4. Wire Job Detail cancel confirmation.
  5. Wire New Job launch confirmation.
  6. Fix Preview missing-file behavior.
  7. Fix Preview launch semantics.
  8. Add or update tests.
  9. Run final validation and review for regressions.

Validation loop:
- After each meaningful checkpoint, run:
  - `python -m compileall dispatch scr`
  - `python -m dispatch --help`
- After UI changes, run the local mock app path with:
  - `source mocks/dev-env.sh`
  - `DISPATCH_MOCK_SCENARIO=happy_path python -m dispatch`
- Add or update the strongest relevant automated tests for the changed behavior.
- If pilot or UI interaction tests already exist, use them. If they do not exist for this flow and adding them is practical within scope, add them for the confirmation and preview-safety paths.
- For every destructive action you gate, verify the negative path and positive path:
  - canceling the confirmation does nothing
  - confirming performs the intended action
- Inspect the final diff for regressions in labels, bindings, and user-facing copy.

Done when:
- No destructive or irreversible TUI action executes without explicit confirmation.
- Browser DROP is gated by confirmation.
- Job cancellation is gated by confirmation.
- Job launch is gated by confirmation.
- Preview does not crash on missing/unreadable SQL files.
- Preview launch semantics are accurate and not misleading.
- Relevant tests and validation commands pass.
- Final report includes:
  - completed checkpoints
  - files changed
  - validation evidence
  - any residual risks that still require real edge-node smoke testing

Pause conditions:
- Pause if a required safety fix would violate a documented product invariant.
- Pause if you discover that the existing plan or screenshot review conflicts with current architecture in a way that needs a product decision.
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
