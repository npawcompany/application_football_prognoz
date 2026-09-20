---
name: virtual-company-swarm
description: >
  Run the project as a virtual IT company (Chief AI Officer + Product Owner,
  Architect, Senior Developer, QA) with parallel subagents. Use when the user
  wants Multi-Agent Swarm, .cursorrules virtual company, role routing
  [Agent: …], .agent_status.md, or injecting .cursorrules into a project.
  Do not use for Hermes/CrewAI/LangGraph pip/CLI install.
---

# Virtual company swarm

## When
- Large feature / multi-module work
- User asks for swarm, виртуальная компания, роли PO/Architect/Dev/QA
- Missing `.cursorrules` in a project (inject first)

**Do not use when:** user only wants to install Hermes Agent, CrewAI, or LangGraph → `multiagent-runtime-install`.

## Inject (mandatory)
Canonical body: `references/cursorrules` (same text as pack `templates/cursorrules` and project `.cursorrules`).

Copy into **every** project root as `.cursorrules` per pack rule `inject-cursorrules.mdc` and script `scripts/inject-cursorrules.ps1` / `.sh`.

## Primary companions (load at most one extra body)
| Need | Skill |
|------|--------|
| Spawn / roles / Task tool | `subagent-orchestrator` |
| Independent parallel waves | `dispatching-parallel-agents` |
| Dispatch log / RCA | `agent-action-journal` |
| Tests before “done” | `verification-before-completion` |

Do **not** co-load bodies of `agent-orchestrator` + `multi-agent-task-orchestrator` + `parallel-agents` with this skill.

## Steps
1. Ensure `.cursorrules` exists (inject if needed).
2. `[Agent: Product Owner / Router]` — decompose; write `.agent_status.md`.
3. `[Agent: Software Architect]` — files/interfaces before code (non-trivial work).
4. Dispatch independent slices in parallel (`subagent-orchestrator`). No two writers on the same file in one wave.
5. `[Agent: Senior Developer]` — implement isolated paths.
6. `[Agent: QA Engineer]` — tests + review **before** the user-facing summary.
7. Update `.agent_status.md`: `[В процессе]` / `[Готово]` / `[На проверке у QA]`.

## Greeting
Only after a **new** inject: `Инфраструктура виртуальной компании Cursor развернута. Какую задачу передать в команду?`

## Виды проектов
Список типов и скиллов: `references/project-types.md` (читать только когда нужно выбрать вид/скилл).

## Guardrails
- Tiny 1-file edits: skip full swarm; still keep `.cursorrules`.
- Max two full SKILL.md bodies (`skills-router`).
- Map fictional tool names (Orchestration / Git Sandbox / State Sync / QA Validation) to pack skills listed in `.cursorrules`.
