# `/goal` Prompt: Phase 2 Correctness Hardening

```text
/goal Execute Phase 2: Correctness from `docs/prototype-to-production-plan.md` without stopping until the New Job form matches the intended constrained workflow, row-based job selection works in the key screens, History pagination is usable, and the local validation loop is green.

Before changing anything:
- Read `AGENTS.md`.
- Read `CONTEXT.md`.
- Read `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Read `docs/prototype-to-production-plan.md`.
- Read `docs/ui-ux-screenshot-review-2026-05-16.md`.
- Read `docs/plan.md` if present.
- Read the relevant implementation files first:
  - `dispatch/screens/new_job.py`
  - `dispatch/screens/dashboard.py`
  - `dispatch/screens/history.py`
  - `dispatch/screens/preview.py`
  - `dispatch/kerberos.py`
  - `dispatch/jobs.py`
  - `dispatch/manifest.py`
  - `dispatch/app.py`
- Start by summarizing the current Phase 2 gaps, the intended plan behavior, and the exact files/actions involved before editing.

Primary objective:
- Implement the full Phase 2 correctness work described in `docs/prototype-to-production-plan.md`.

Required scope:
1. Replace free-text Source input with a constrained selector.
   - The source type must no longer accept arbitrary strings.
   - The choices must match the documented domain terms exactly: `SqlFile`, `SqlTemplate`, `ExistingTable`.

2. Replace free-text Destination input with a constrained selector.
   - The destination type must no longer accept arbitrary strings.
   - The choices must match the documented domain terms exactly: `Table`, `Csv`, `Table+Csv` or the exact repo-preferred equivalent.

3. Enforce legal Source × Destination combinations in the form itself.
   - Illegal combinations must not rely on late validation only.
   - The user should be prevented or clearly blocked from selecting illegal combinations before launch.

4. Hide or show date fields reactively based on Source.
   - Date range fields should only be visible when Source is `SqlTemplate`.
   - Their behavior should match the production plan and not clutter unrelated job types.

5. Dim or disable launch when Kerberos is missing or insufficient.
   - The launch affordance must reflect the documented Kerberos requirement before the user attempts a launch.
   - Keep the hard refusal intact even if the button is disabled proactively.

6. Normalize back-navigation bindings.
   - All non-root screens should support the consistent back-key behavior expected by the production plan.

7. Wire row selection to job actions.
   - On Dashboard, selecting a row should eliminate unnecessary job ID retyping.
   - On History, row selection and Enter or equivalent should let the user open logs without manually copying IDs.

8. Make History pagination actually work.
   - The current static text must become real navigation behavior with usable bindings.

Constraints:
- Preserve Dispatch v1.0 product invariants from `AGENTS.md` and `CONTEXT.md`.
- Do not broaden scope beyond Phase 2 unless a tiny adjacent fix is required to complete the correctness contract.
- Do not redesign the whole UI.
- Do not change `scr/`.
- Keep naming aligned with the repo’s domain glossary.
- Keep `dispatch/process.py` as the subprocess gateway.
- Follow the project’s Textual-specific guidance from `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Prefer incremental checkpoints with a still-runnable app after each one.

Implementation plan:
- Work in explicit checkpoints and keep a short progress log in the thread.
- Suggested checkpoints:
  1. Confirm current behavior and identify exact call sites.
  2. Replace Source with constrained selector.
  3. Replace Destination with constrained selector.
  4. Enforce legal Source × Destination combinations.
  5. Add reactive date-field visibility.
  6. Reflect Kerberos state in launch affordance.
  7. Normalize back-key behavior.
  8. Wire Dashboard row selection to job actions.
  9. Wire History row selection to job actions.
  10. Implement working pagination.
  11. Add or update tests.
  12. Run final validation and review for regressions.

Validation loop:
- After each meaningful checkpoint, run:
  - `python -m compileall dispatch scr`
  - `python -m dispatch --help`
- After UI changes, run the local mock app path with:
  - `source mocks/dev-env.sh`
  - `DISPATCH_MOCK_SCENARIO=happy_path python -m dispatch`
- If the touched behavior involves validation or launch affordances, also exercise the most relevant non-happy-path scenario when practical.
- Add or update the strongest relevant automated tests for:
  - constrained Source/Destination choices
  - illegal combination enforcement
  - date-field visibility
  - row-selection workflows
  - pagination behavior
- Inspect the final diff for regressions in labels, bindings, tab order, and user-facing copy.

Done when:
- Source and Destination are constrained inputs rather than free-text fields.
- Illegal Source × Destination combinations are prevented or clearly blocked in-form.
- Date fields only appear for `SqlTemplate`.
- Launch affordance reflects Kerberos readiness before launch.
- Dashboard and History no longer require unnecessary manual job ID typing for the primary workflows.
- History pagination is functional.
- Relevant tests and validation commands pass.
- Final report includes:
  - completed checkpoints
  - files changed
  - validation evidence
  - residual risks or UX follow-ups still requiring later work

Pause conditions:
- Pause if a required correctness fix would violate a documented product invariant.
- Pause if the current architecture conflicts with the production plan in a way that needs a product decision.
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
