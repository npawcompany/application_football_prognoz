---
name: skills-router
description: >
  Master router for a large installed skill catalog. ALWAYS apply at the start of multi-step work
  and whenever choosing which skill to load. Resolves conflicts, picks ONE primary skill per concern,
  and prevents loading overlapping skill bodies. Use for routing, skill conflicts, "which skill",
  or after installing the full ai-agent-skills-pack.
---

# Skills router (install-all safe)

## Why a full install can still be OK
Cursor injects mostly **name + description** for discoverability. Full `SKILL.md` bodies should load **only when selected**. This router is the policy that keeps a large catalog from fighting itself.

## Hard rules
1. **One primary skill per concern** (design OR figma-use OR frontend-design — not all three bodies).
2. **Load body only after match** — do not read every SKILL.md "just in case".
3. **Prefer narrower trigger** — if two match, pick the more specific (e.g. `figma-design-to-code` > `frontend-design` when a Figma URL is present).
4. **Exclusive domains** — see matrix below; never co-load exclusives.
5. **Token budget** — max **2** full skill bodies in flight unless user asks for more; use progressive refs inside a skill instead.
6. **Meta first** — for ambiguous tasks, apply this router + `token-thrifty` before specialist skills.

## Priority tiers (high → low)
| Tier | Skills | When |
|------|--------|------|
| 0 Meta | `skills-router`, `token-thrifty`, `caveman` (if user enabled) | Always consider |
| 1 Safety | `security-and-hardening`, system health | Secrets, prod, machine distress |
| 2 Task-primary | Exact domain match from matrix | Main job |
| 3 Support | testing, git, docs | After primary chosen |
| 4 Forge/memory | `learn-and-guides`, `project-memory`, `memory-forge` | End of session / explicit remember |

## Exclusive conflict matrix
Pick **left** when both seem relevant:

| Concern | Winner | Do not co-load |
|---------|--------|----------------|
| Figma URL / design file edit | `figma-use` / `figma-design-to-code` / … | `canvas-design` alone as substitute for Figma MCP |
| Vue/Nuxt | `vue-nuxt-vanilla` | `react-best-practices` |
| React/Next | `react-best-practices` + `frontend-ui-engineering` | `vue-nuxt-vanilla` |
| Web research | `firecrawl-search` → scrape | Pasting whole pages into chat |
| Office **edit** | `docx`/`pptx`/`xlsx`/`pdf` | MarkItDown (convert-only) |
| Office → Markdown ingest | `markitdown` | Full office edit skills |
| SQL design | `sql-databases` | Random ORM skill until dialect known |
| Postgres+SQLAlchemy | `sqlalchemy-postgres` | Generic after dialect locked |
| Go DB | `golang-database` | Python SQL skills |
| System load | `system-health` | Guessing without OS snapshot |
| Create new skill | `custom-skill-factory` | Ad-hoc SKILL.md without factory |
| SDLC methodology | Addy skill matching phase | Entire Addy catalog at once |
| Virtual company / swarm roles / `.cursorrules` inject | `virtual-company-swarm` → `subagent-orchestrator` | Bodies of `agent-orchestrator` + `multi-agent-task-orchestrator` + `parallel-agents` together |
| Hermes Agent / CrewAI / LangGraph install | `multiagent-runtime-install` | Global `pip install`; swapping for Cursor swarm |
| GitHub Spec Kit / specify-cli / `/speckit-*` | `github-spec-kit` | Lightweight `spec-driven-development` body at the same time |
| UI/UX Pro Max / `uipro` | generated `ui-ux-pro-max` after CLI; setup via `ui-ux-pro-max-setup` | `boardui` + `frontend-design` bodies together |
| BoardUI / `npx boardui` | `boardui` | `ui-ux-pro-max` / Vue as primary |
| ScrapeGraphAI library | `scrapegraph-ai` | Firecrawl skills as the scraper |
| Rybbit analytics | `rybbit-analytics` | Firecrawl / witr |
| witr (why is this running) | `witr` | `k8s-troubleshooter` as substitute for local PID/port |

## Selection algorithm
```
1. Parse user intent + artifacts (URL, path, stack, OS)
2. List candidate skills by description match (catalog only)
3. Apply exclusive matrix → drop losers
4. Rank by specificity + tier
5. Load ONE primary SKILL.md (+ optional one support)
6. If Figma: authenticate/connect per figma-connect, then mandatory figma-* prerequisite skills
7. Execute; do not open sibling overlapping skills mid-flight
8. On wrap-up: learn-and-guides if user wants memory
```

## Anti-patterns
- Installing 100 skills **and** pasting all bodies into rules/AGENTS.md
- Loading both `caveman` verbosity cut **and** long essay skills without need
- Parallel `frontend-design` + `web-design-guidelines` + `frontend-ui-engineering` full bodies
- Using MarkItDown and docx edit on the same file in one step without a clear pipeline

## After full pack install
Keep this skill + user rule `skills-routing` enabled. Catalog may be large; **routing discipline** is what saves tokens—not deleting the pack.

## Browser tool exclusivity (v1.3)
| Job | Winner | Avoid co-loading |
|-----|--------|------------------|
| In-Cursor Chromium UI | `cursor-ide-browser` | Full Playwright MCP unless needed |
| Fast Chromium automation | `agent-browser` | Heavy Playwright tool schemas |
| Firefox / cross-engine | `playwright-mcp-browsers` | Assuming Chromium-only ide-browser |
| Exploratory QA dogfood | `browser-dogfood` | Random scraping skills |
| Token/context pressure | `token-sentinel` | Ignoring HIGH pressure |

## Automation & Russian (v1.4)
| Concern | Winner | Avoid |
|---------|--------|-------|
| n8n workflow | `automation-hub` → `using-n8n-skills-official` | Inventing nodes without official skills |
| Zapier/Make | `zapier-make-patterns` | Forcing n8n if user asked Zapier |
| Russian text / literature | `russian-literature-kb` → `ru-text` | English copy skills as primary |
| Publisher formatting | `russian-editorial-review` | Skipping typography checklist |

## Orchestration & journal (v1.6)
| Concern | Winner |
|---------|--------|
| Virtual company / `.cursorrules` swarm | `virtual-company-swarm` |
| Spawn/roles/control subagents | `subagent-orchestrator` |
| Parallel independent tasks | `dispatching-parallel-agents` |
| Action history / RCA | `agent-action-journal` |
| Session wrap distillate | `log-session` |
| Hermes / CrewAI / LangGraph runtime | `multiagent-runtime-install` |
| Spec Kit CLI | `github-spec-kit` |
| UI/UX Pro Max install | `ui-ux-pro-max-setup` |
| BoardUI | `boardui` |
| ScrapeGraphAI | `scrapegraph-ai` |
| Rybbit | `rybbit-analytics` |
| witr | `witr` |