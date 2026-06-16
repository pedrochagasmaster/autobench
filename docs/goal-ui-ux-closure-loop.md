# `/goal` Prompt: UI/UX Closure Loop

```text
/goal Run a screenshot-review-driven UI/UX closure loop against `docs/ui-ux-screenshot-review-2026-05-16.md` without stopping until the highest-value interaction and clarity issues are fixed or explicitly deferred, the resulting screens are materially safer and easier to use, and the local validation loop is green.

Before changing anything:
- Read `AGENTS.md`.
- Read `CONTEXT.md`.
- Read `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Read `docs/ui-ux-screenshot-review-2026-05-16.md` in full.
- Read `docs/prototype-to-production-plan.md`.
- Read `docs/plan.md` if present.
- Read the relevant screen files first:
  - `dispatch/screens/dashboard.py`
  - `dispatch/screens/new_job.py`
  - `dispatch/screens/preview.py`
  - `dispatch/screens/job_detail.py`
  - `dispatch/screens/history.py`
  - `dispatch/screens/browser.py`
  - `dispatch/app.py`
- Identify the screenshot-review findings that have the highest product value, highest user risk, and strongest overlap with the production plan.
- Start by grouping the findings into a small set of checkpoints before editing.

Primary objective:
- Close the most important UI/UX gaps identified in `docs/ui-ux-screenshot-review-2026-05-16.md` using a checkpointed, validation-backed loop.

How to choose work:
- Prioritize issues that reduce user error, operational risk, or major workflow friction before cosmetic polish.
- Prefer findings that overlap with the production plan, especially around safety, selection UX, form controls, feedback, and misleading actions.
- Do not try to clear the entire document if that turns the goal into an open-ended backlog.
- Treat this as one durable objective with a bounded closure target, not a grab bag of unrelated tweaks.

Required working style:
- Work in focused checkpoints, each centered on one coherent UX cluster.
- After each checkpoint:
  - run the relevant validation commands
  - inspect the changed behavior directly
  - record what issue IDs were addressed
  - note which important findings remain
- Keep a short progress log in the thread with checkpoint names and closed issue IDs.

Suggested checkpoint clusters:
1. Safety and destructive-action clarity
   - Confirmation flows
   - dangerous button placement
   - misleading launch semantics

2. Selection and no-retyping workflows
   - row-selection visibility
   - row-to-action wiring
   - job ID entry friction on Dashboard and History

3. New Job form correctness and affordances
   - constrained Source/Destination controls
   - better date behavior
   - clearer validation and guidance

4. History and Browser usability
   - functional pagination
   - better empty states
   - clearer detail-pane behavior

5. Feedback and clarity polish
   - clearer labels and copy
   - elapsed time
   - clearer Kerberos messaging
   - removal of ambiguous or phantom interactions

Constraints:
- Preserve Dispatch v1.0 product invariants from `AGENTS.md` and `CONTEXT.md`.
- Keep behavior aligned with the production plan unless you find a documented reason to defer.
- Do not redesign the product into a different visual language.
- Do not change `scr/`.
- Follow the project’s Textual-specific guidance from `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Keep changes reviewable and incremental.
- If a finding is out of scope for this goal, explicitly defer it rather than silently ignoring it.

Validation loop:
- After each meaningful checkpoint, run:
  - `python -m compileall dispatch scr`
  - `python -m dispatch --help`
- After UI changes, run the local mock app path with:
  - `source mocks/dev-env.sh`
  - `DISPATCH_MOCK_SCENARIO=happy_path python -m dispatch`
- If existing snapshot or pilot tests cover the touched screens, run them.
- If practical within scope, add or update targeted tests for the highest-risk interaction changes.
- Use the screenshot review as the acceptance rubric: compare the changed behavior against the specific issue IDs and proposals you targeted.

Stopping condition:
- The highest-value screenshot-review findings have been fixed or explicitly deferred with reasons.
- The resulting UI is materially safer and easier to use in the main workflows.
- The goal remains bounded; do not continue into low-value polish once the major friction and risk items are resolved.
- Relevant tests and validation commands pass.

Done when:
- You can name the issue IDs from `docs/ui-ux-screenshot-review-2026-05-16.md` that were closed.
- The major workflow friction points in Dashboard, New Job, Preview, Job Detail, History, and Browser are substantially improved.
- Safety, selection UX, and misleading actions have been addressed first.
- Relevant tests and validation commands pass.
- Final report includes:
  - checkpoints completed
  - issue IDs addressed
  - files changed
  - validation evidence
  - explicitly deferred findings with reasons

Pause conditions:
- Pause if the next meaningful UX fix would require a product decision that is not resolved by the existing docs.
- Pause if the remaining work is mostly low-value polish rather than major UX closure.
- Pause if a required validation step depends on unavailable corporate infrastructure rather than local mocks.

Progress reporting:
- Keep updates compact.
- Each status update should say:
  - current checkpoint
  - issue IDs addressed
  - what was verified
  - what remains
  - whether blocked

Stop only when the stopping condition is satisfied or you are genuinely blocked by one of the pause conditions.
```
