# Agent skills

Project skills are installed with the [skills CLI](https://skills.sh/) into
`.agents/skills/` and tracked in `skills-lock.json` at the repo root. Cursor
IDE and Cloud Agents discover them from `.agents/skills/` (also
`.cursor/skills/` and `.claude/skills/` if present).

## Update all skills

```bash
npx skills update -y
```

## Installed packages

| Package | Skills |
|---------|--------|
| [`mattpocock/skills`](https://github.com/mattpocock/skills) | Engineering, productivity, and misc helpers (18 skills; excludes upstream `personal/`, `in-progress`, `deprecated`) |
| [`cursor/plugins`](https://github.com/cursor/plugins) | `thermo-nuclear-review` |

### Matt Pocock skills

- **Engineering:** `diagnose`, `grill-with-docs`, `improve-codebase-architecture`, `prototype`, `setup-matt-pocock-skills`, `tdd`, `to-issues`, `to-prd`, `triage`, `zoom-out`
- **Productivity:** `caveman`, `grill-me`, `handoff`, `write-a-skill`
- **Misc:** `git-guardrails-claude-code`, `migrate-to-shoehorn`, `scaffold-exercises`, `setup-pre-commit`

### Cursor plugins

- **`thermo-nuclear-review`** — deep security/correctness audit of branch changes (`/thermo-nuclear-review`)

## Quickstart

1. Run **`/setup-matt-pocock-skills`** once to scaffold `docs/agents/` (issue tracker, triage labels, domain docs). Commit what it creates so cloud agents inherit config.
2. Common entrypoints: `/tdd`, `/diagnose`, `/grill-me`, `/grill-with-docs`, `/to-prd`, `/to-issues`, `/triage`, `/zoom-out`, `/improve-codebase-architecture`

See the [mattpocock/skills README](https://github.com/mattpocock/skills) for full catalog and rationale.

## Add or remove skills

```bash
# Add one skill from a package
npx skills add mattpocock/skills --agent cursor -y --skill qa

# Add thermo-nuclear (if missing)
npx skills add cursor/plugins@thermo-nuclear-review --agent cursor -y

# Reinstall everything from lock file
npx skills experimental_install
```

## Cloud-agent notes

- Commit `.agents/skills/` and `skills-lock.json` so cloud VMs get the same skill set.
- User-scoped skills under `~/.cursor/skills/` are **not** available to cloud agents.
