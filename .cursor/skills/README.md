# `.cursor/skills/`

Project-scoped Cursor [Agent Skills](https://cursor.com/docs/skills) that are
auto-discovered by both the Cursor IDE and Cursor Cloud Agents whenever the
repo is checked out.

## Source

These skills are vendored from
[`mattpocock/skills`](https://github.com/mattpocock/skills) (commit at the time
of import). Upstream is MIT-licensed; the original `LICENSE` file is preserved
alongside this README.

To update, re-clone upstream and copy the relevant buckets:

```bash
git clone --depth 1 https://github.com/mattpocock/skills.git /tmp/mattpocock-skills
rm -rf .cursor/skills/engineering .cursor/skills/productivity .cursor/skills/misc
cp -r /tmp/mattpocock-skills/skills/engineering .cursor/skills/
cp -r /tmp/mattpocock-skills/skills/productivity .cursor/skills/
cp -r /tmp/mattpocock-skills/skills/misc          .cursor/skills/
cp /tmp/mattpocock-skills/LICENSE .cursor/skills/LICENSE
```

The upstream `personal/`, `in-progress/`, and `deprecated/` buckets are
intentionally excluded — per upstream `CLAUDE.md` they are not promoted.

## Layout

Skills are kept in their upstream bucket layout. Cursor supports nested
skill directories, so `engineering/tdd/SKILL.md` is discovered the same as
`tdd/SKILL.md` would be.

```
.cursor/skills/
├── engineering/   # daily code work (tdd, diagnose, grill-with-docs, ...)
├── productivity/  # workflow tools (grill-me, caveman, write-a-skill)
└── misc/          # rarely-used helpers (setup-pre-commit, ...)
```

## Quickstart

Per upstream README, **run `/setup-matt-pocock-skills` once** to scaffold the
per-repo config (issue tracker choice, triage label vocabulary, docs location)
that the engineering skills consume. Commit any files it creates so cloud
agents inherit the configured state.

After that, the most useful entrypoints are:

- `/grill-me`, `/grill-with-docs` — interview the agent / get interviewed before
  starting work.
- `/tdd` — red-green-refactor loop for features and bug fixes.
- `/diagnose` — disciplined diagnosis loop for hard bugs.
- `/to-prd`, `/to-issues`, `/triage` — turn discussion into PRDs / issues /
  triaged work.
- `/zoom-out`, `/improve-codebase-architecture` — keep the codebase from rotting
  into a ball of mud.

See the upstream [README](https://github.com/mattpocock/skills) for the full
catalog and rationale.

## Cloud-agent notes

- Project skills committed under `.cursor/skills/` (or `.agents/skills/`,
  `.claude/skills/`) are picked up automatically by Cursor Cloud Agents because
  the cloud VM clones this repo on each run.
- User-scoped skills under `~/.cursor/skills/` on a developer's laptop are
  **not** available to cloud agents. Vendor anything you want cloud agents to
  use into this directory.
