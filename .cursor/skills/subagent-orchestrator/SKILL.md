---
name: subagent-orchestrator
description: >
  Create Cursor subagents with roles, delegate tasks, run them in parallel when safe,
  and control/verify their results. Use when work should be split across agents,
  multi-agent orchestration, role assignment, Task/subagent dispatch, or reviewing
  subagent output. Cursor Task tool + create-subagent + superpowers patterns.
---

# Subagent orchestrator (Cursor)

## Role
You are the **orchestrator** (parent). Subagents implement; you plan, dispatch, verify, integrate.

## Ready skills to load with this
| Skill | When |
|-------|------|
| `create-subagent` | Define persistent agent files under `.cursor/agents/` |
| `subagent-driven-development` | Per-task fresh agent + two-stage review |
| `dispatching-parallel-agents` / `parallel-agents` | Independent fan-out |
| `multi-agent-task-orchestrator` / `agent-orchestrator` | Larger multi-agent plans |
| `agent-action-journal` | Log every dispatch/result for later RCA |

## When to spawn subagents
- ≥2 independent workstreams (research + implement + review)
- Long exploration that would pollute parent context
- Need a specialist persona (security, tests, UI, Russian edit)

**Do not** spawn for tiny 1-file edits — do them yourself.

## Role catalog (assign explicitly)
| Role id | Duty | Model hint |
|---------|------|------------|
| `implementer` | Code/change per acceptance criteria | default/inherit |
| `explorer` | Find files/APIs; return paths + summary only | fast |
| `reviewer-spec` | Check result vs acceptance criteria | strong |
| `reviewer-quality` | Bugs, security, simplicity | strong |
| `tester` | Run tests / browser checks; report evidence | default |
| `researcher` | Web/docs; write findings to files | default |
| `russian-editor` | Orthography/structure via ru-text stack | default |

## Dispatch protocol (Cursor)
1. **Decompose** into tasks with: goal, inputs, out-of-scope, acceptance criteria, files allowed to touch.
2. **Dependency graph** — parallel only if no shared writes; else waves.
3. **Baseline** — commit or note dirty files before parallel writers.
4. **Dispatch** via Task tool:
   - `subagent_type` matching role (or `generalPurpose` / `explore` with explicit role in prompt)
   - Full self-contained `prompt` (subagent has NO parent chat history)
   - `description` 3–5 words
   - Parallel: multiple Task calls in one turn when independent
5. **Log** each dispatch to agent-action-journal (role, task id, time, prompt hash/summary).
6. **Collect** results — require status: `DONE` | `DONE_WITH_CONCERNS` | `NEEDS_CONTEXT` | `BLOCKED`.
7. **Control gate** (mandatory before merge):
   - Spec review: acceptance criteria met?
   - Quality review: for non-trivial code
   - Re-dispatch once with fixes if failed; escalate to user if BLOCKED twice
8. **Integrate** yourself; do not trust subagent “LGTM” alone.

## Subagent brief template
```markdown
# Role: <role id>
# Task ID: <T1>
## Goal
## Allowed paths
## Forbidden
## Acceptance criteria (checklist)
## Context (files/summaries — not whole repo)
## Return format
- status
- summary (≤15 lines)
- files changed
- risks / concerns
- evidence (commands/tests)
```

## Control checklist
- [ ] One clear owner role per Task
- [ ] No two writers on same file in same wave
- [ ] Parent did verification, not only implementer
- [ ] Journal updated
- [ ] Token-thrifty: subagents write bulky output to disk

## Conflicts
- Parent must not re-implement everything the subagent did unless review failed.
- Do not nest infinite subagents (one orchestration level unless user asks).