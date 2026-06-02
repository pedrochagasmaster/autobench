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
| [`mattpocock/skills`](https://github.com/mattpocock/skills) | 24 skills (full promoted catalog except writing/Obsidian — see below) |
| [`cursor/plugins`](https://github.com/cursor/plugins) | `thermo-nuclear-review` |

### Matt Pocock — engineering & workflow

- **Engineering:** `diagnose`, `design-an-interface`, `grill-with-docs`, `improve-codebase-architecture`, `prototype`, `request-refactor-plan`, `review`, `setup-matt-pocock-skills`, `tdd`, `to-issues`, `to-prd`, `triage`, `ubiquitous-language`, `zoom-out`
- **Productivity:** `caveman`, `grill-me`, `handoff`, `teach`, `write-a-skill`
- **General:** `qa`, `git-guardrails-claude-code`, `migrate-to-shoehorn`, `scaffold-exercises`, `setup-pre-commit`

**Not installed** (intentionally): `writing-beats`, `writing-fragments`, `writing-shape`, `edit-article`, `obsidian-vault`

### Cursor plugins

- **`thermo-nuclear-review`** — deep security/correctness audit of branch changes (`/thermo-nuclear-review`)

## Quickstart

1. Run **`/setup-matt-pocock-skills`** once to scaffold `docs/agents/` (issue tracker, triage labels, domain docs). Commit what it creates so cloud agents inherit config.
2. Common entrypoints: `/tdd`, `/diagnose`, `/review`, `/grill-me`, `/grill-with-docs`, `/ubiquitous-language`, `/to-prd`, `/to-issues`, `/triage`, `/qa`, `/zoom-out`, `/improve-codebase-architecture`

See the [mattpocock/skills README](https://github.com/mattpocock/skills) for full catalog and rationale.

## Add or remove skills

```bash
npx skills add mattpocock/skills --agent cursor -y --skill <name>
npx skills add cursor/plugins@thermo-nuclear-review --agent cursor -y
npx skills experimental_install   # restore from skills-lock.json
```

## Cloud-agent notes

- Commit `.agents/skills/` and `skills-lock.json` so cloud VMs get the same skill set.
- User-scoped skills under `~/.cursor/skills/` are **not** available to cloud agents.
