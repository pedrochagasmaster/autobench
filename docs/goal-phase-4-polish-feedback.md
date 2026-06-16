# `/goal` Prompt: Phase 4 Polish and Feedback

```text
/goal Execute Phase 4: Polish & Feedback from `docs/prototype-to-production-plan.md` without stopping until Dispatch’s core TUI workflows feel clearer, more discoverable, and more responsive, the highest-value remaining feedback and navigation gaps are addressed, and the local validation loop is green.

Before changing anything:
- Read `AGENTS.md`.
- Read `CONTEXT.md`.
- Read `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Read `docs/prototype-to-production-plan.md`.
- Read `docs/ui-ux-screenshot-review-2026-05-16.md`.
- Read `docs/plan.md` if present.
- Read the relevant implementation files first:
  - `dispatch/app.py`
  - `dispatch/screens/dashboard.py`
  - `dispatch/screens/new_job.py`
  - `dispatch/screens/preview.py`
  - `dispatch/screens/job_detail.py`
  - `dispatch/screens/history.py`
  - `dispatch/screens/browser.py`
- Start by summarizing the current Phase 4 gaps, the intended production-plan behavior, and the exact screens and interactions involved before editing.

Primary objective:
- Implement the full Phase 4 polish and feedback work described in `docs/prototype-to-production-plan.md`.

Required scope:
1. Improve help and discoverability.
   - Add the intended help behavior or equivalent guidance where the production plan calls for it.
   - Remove phantom or misleading interaction hints.

2. Improve notification and feedback behavior.
   - Add a proper notification or toast-like feedback path if that is the chosen Phase 4 mechanism.
   - Reduce reliance on brittle or easy-to-miss inline warning behavior where the plan indicates a stronger feedback system.

3. Resolve ambiguous bindings and labels.
   - Remove or clarify overloaded or confusing action bindings and labels.
   - Ensure user-facing copy matches actual behavior.

4. Improve empty states and guidance text.
   - Replace confusing placeholder rows or blank panes with useful guidance where appropriate.
   - Favor actionable copy over inert placeholders.

5. Add elapsed-time or other high-value contextual feedback where Phase 4 expects it.
   - Make long-running job state easier to interpret without forcing users to infer from raw timestamps alone.

6. Improve remaining form and feedback polish called for in Phase 4.
   - Dynamic defaults
   - inline validation feedback
   - persisted last-used values
   - any other documented Phase 4 polish items that remain after earlier goals

Constraints:
- Preserve Dispatch v1.0 product invariants from `AGENTS.md` and `CONTEXT.md`.
- Do not broaden scope beyond Phase 4 unless a tiny adjacent fix is required to complete the clarity/feedback contract.
- Do not redesign the whole UI into a different visual system.
- Do not change `scr/`.
- Follow the project’s Textual-specific guidance from `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Keep changes incremental, reviewable, and grounded in the screenshot review and production plan.

Implementation plan:
- Work in explicit checkpoints and keep a short progress log in the thread.
- Suggested checkpoints:
  1. Confirm current UX gaps and identify exact call sites.
  2. Improve help and discoverability.
  3. Improve notifications and feedback.
  4. Resolve ambiguous bindings and labels.
  5. Improve empty states and pane placeholders.
  6. Add elapsed-time and contextual status improvements.
  7. Finish remaining form-polish work from Phase 4.
  8. Add or update tests.
  9. Run final validation and review for regressions.

Validation loop:
- After each meaningful checkpoint, run:
  - `python -m compileall dispatch scr`
  - `python -m dispatch --help`
- After UI changes, run the local mock app path with:
  - `source mocks/dev-env.sh`
  - `DISPATCH_MOCK_SCENARIO=happy_path python -m dispatch`
- If the touched behavior involves long-running or error presentation, also exercise the most relevant non-happy-path scenario when practical.
- Add or update the strongest relevant automated tests for:
  - help and notification behavior
  - empty-state rendering
  - elapsed-time or status rendering
  - inline validation behavior
- Compare the resulting UX directly against the screenshot-review findings and the production plan.

Done when:
- The main workflows feel clearer, more discoverable, and more responsive.
- Notification and feedback behavior is materially improved.
- Ambiguous bindings and misleading labels are resolved.
- Empty states and placeholders are useful rather than inert or confusing.
- Relevant tests and validation commands pass.
- Final report includes:
  - completed checkpoints
  - files changed
  - validation evidence
  - explicitly deferred low-value polish if any remains

Pause conditions:
- Pause if the next meaningful polish step requires a product decision not resolved by the existing docs.
- Pause if the remaining work becomes mostly subjective low-value polish rather than meaningful workflow improvement.
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
