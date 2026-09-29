---
name: custom-skill-factory
description: >
  Create, validate, and install custom Agent Skills into the user system (~/.cursor/skills)
  or the Desktop ai-agent-skills-pack. Use when the user asks to make a new skill, wrap a
  workflow into SKILL.md, or extend the pack. Prefer this over writing skills ad-hoc.
---

# Custom skill factory

## Goal
Produce a valid skill folder and install it where Cursor will discover it.

## Never
- Write into `~/.cursor/skills-cursor/` (Cursor-managed)
- Create overlapping descriptions that fight `skills-router`
- Put secrets in SKILL.md

## Gather (ask if missing)
1. **name** — kebab-case, ≤64 chars
2. **description** — when to use + trigger words (≤1024). Must be UNIQUE vs catalog
3. **scope** — `user` (`~/.cursor/skills`) | `pack` (Desktop pack category) | `project` (`.cursor/skills`)
4. **auto** — auto-invoke from description? If no, set `disable-model-invocation: true`
5. **steps** — the procedure
6. **exclusive domain** — what it must NOT co-load with (for router note)

## Create layout
```
skill-name/
  SKILL.md          # required
  references/       # optional progressive disclosure
  scripts/          # optional
```

### SKILL.md template
```markdown
---
name: skill-name
description: >
  One precise paragraph: WHAT + WHEN. Include unique trigger nouns.
---

# Title

## When
## Steps
## Guardrails
## Related skills
```

Keep the main body short; put long docs in `references/` and say "read only if needed".

## Description quality (anti-conflict)
- Include stack/OS/tool unique tokens: `Nuxt`, `figma.com`, `EXPLAIN`, `Windows|Linux|macOS`
- Avoid vague "helps with coding"
- Add "Use when…" and "Do not use when…" one-liners in body

## Install paths
| Scope | Path |
|-------|------|
| user | `%USERPROFILE%\.cursor\skills\<name>\` or `~/.cursor/skills/<name>/` |
| project | `<repo>/.cursor/skills/<name>/` |
| pack | `ai-agent-skills-pack/<NN-category>/<name>/` + update MANIFEST if present |

Also mirror to `ai-agent-skills-pack/custom/<name>/` when creating pack skills.

## Validation checklist
- [ ] Frontmatter `name` + `description` present
- [ ] Folder name == `name`
- [ ] No collision with existing skill names in `~/.cursor/skills` or pack
- [ ] Description does not duplicate another skill’s triggers
- [ ] Added one line to skills-router exclusive matrix if needed (tell user / patch router)
- [ ] New Agent session recommended after install

## PowerShell helper (Windows)
```powershell
$name = 'my-skill'
$root = Join-Path $env:USERPROFILE ".cursor\skills\$name"
New-Item -ItemType Directory -Force -Path $root | Out-Null
# write SKILL.md then:
Write-Host "Installed $root — start a new Agent chat"
```

## Unix helper
```bash
name=my-skill
mkdir -p ~/.cursor/skills/$name
# write SKILL.md
```

## Related
- `create-skill`, `skill-creator` (deeper authoring theory)
- `skills-router` (register exclusivity)
- `memory-forge` (skill from repeated lessons)
- `learn-and-guides` (playbook first, skill later)