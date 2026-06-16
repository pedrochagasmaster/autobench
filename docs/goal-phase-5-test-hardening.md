# `/goal` Prompt: Phase 5 Test Hardening and Validation

```text
/goal Execute Phase 5: Test Hardening & Validation from `docs/prototype-to-production-plan.md` without stopping until Dispatch has strong automated coverage for the core screens and critical error paths, the manual edge-node validation checklist is documented, and the local validation loop is green.

Before changing anything:
- Read `AGENTS.md`.
- Read `CONTEXT.md`.
- Read `.agents/skills/dispatch-textual-tui/SKILL.md`.
- Read `docs/prototype-to-production-plan.md`.
- Read `docs/ui-ux-screenshot-review-2026-05-16.md`.
- Read `docs/plan.md` if present.
- Read the current test files and structure first:
  - existing tests under `tests/`
  - any snapshot or pilot-based UI tests
  - the main screen implementations under `dispatch/screens/`
  - any docs or scripts that already describe local validation
- Start by summarizing the current test coverage, the biggest gaps from Phase 5, and the exact files/surfaces involved before editing.

Primary objective:
- Implement the full Phase 5 test-hardening and validation work described in `docs/prototype-to-production-plan.md`.

Required scope:
1. Add or complete pilot tests for every core screen.
   - Cover the main user interactions for Dashboard, New Job, Preview, Job Detail, History, and Browser.

2. Add error-path UI tests.
   - Cover the main failure paths called out by the production plan, such as missing SQL file, missing config, expired Kerberos, illegal combinations, and concurrency-cap behavior where practical.

3. Add confirmation-flow tests.
   - Prove that destructive or irreversible actions are gated correctly.

4. Add form-constraint tests.
   - Prove that constrained inputs, legal combinations, and reactive form behavior work as intended.

5. Extend snapshot or regression coverage where appropriate.
   - Cover the main screens with meaningful regression assertions rather than superficial snapshots.

6. Add the manual edge-node smoke-test checklist doc.
   - Create the production-plan-specified checklist for real edge-node validation.
   - Keep it practical and directly runnable by a human reviewer.

Constraints:
- Preserve Dispatch v1.0 product invariants from `AGENTS.md` and `CONTEXT.md`.
- Do not broaden scope beyond Phase 5 unless a tiny adjacent fix is required to make the tests meaningful.
- Do not invent fake coverage that does not exercise real behavior.
- Do not change `scr/` just to make tests easier.
- Follow the project’s Textual-specific guidance from `.agents/skills/dispatch-textual-tui/SKILL.md`.
- If a test is too brittle or expensive, prefer a smaller robust test over a large flaky one.

Implementation plan:
- Work in explicit checkpoints and keep a short progress log in the thread.
- Suggested checkpoints:
  1. Confirm current coverage and identify exact gaps.
  2. Add or improve core screen interaction tests.
  3. Add error-path UI tests.
  4. Add confirmation-flow tests.
  5. Add form-constraint tests.
  6. Extend snapshot/regression coverage.
  7. Add `docs/edge-node-smoke-test.md`.
  8. Run full relevant validation and review for brittleness.

Validation loop:
- After each meaningful checkpoint, run:
  - `python -m compileall dispatch scr`
  - `python -m dispatch --help`
- Run the relevant test subsets after each checkpoint.
- Before final completion, run the strongest available local test suite for the touched files.
- After UI-test changes, run the local mock app path with:
  - `source mocks/dev-env.sh`
  - `DISPATCH_MOCK_SCENARIO=happy_path python -m dispatch`
- If practical, also use relevant failure scenarios to sanity-check the error-path tests.

Done when:
- Core screen interaction coverage is meaningfully stronger.
- Critical error-path coverage exists for the main documented risks.
- Confirmation flows and form constraints are explicitly tested.
- Snapshot or regression coverage is extended where valuable.
- `docs/edge-node-smoke-test.md` exists and is practical.
- Relevant tests and validation commands pass.
- Final report includes:
  - completed checkpoints
  - files changed
  - tests added or expanded
  - validation evidence
  - remaining gaps that still require real edge-node infrastructure

Pause conditions:
- Pause if a required test depends on unavailable corporate infrastructure rather than local mocks.
- Pause if a desired test would be so brittle that it would reduce confidence rather than improve it.
- Pause if a required validation step conflicts with the repo’s documented constraints.

Progress reporting:
- Keep updates compact.
- Each status update should say:
  - current checkpoint
  - what tests or validations were added/run
  - what remains
  - whether blocked

Stop only when the stopping condition is satisfied or you are genuinely blocked by one of the pause conditions.
```
