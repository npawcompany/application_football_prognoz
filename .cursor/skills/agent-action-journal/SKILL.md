---
name: agent-action-journal
description: >
  Log agent and subagent actions to a durable journal (JSONL + markdown) for debugging,
  root-cause analysis, and audit. Use during multi-step work, after errors, when user asks
  what went wrong, or with subagent-orchestrator. Append-only; never rewrite history.
---

# Agent action journal

## Purpose
Git shows *what* changed. The journal shows *who* (parent/subagent role), *why*, *what tools*, and *what failed* — so you can find the error source later.

## Ready companions
| Skill | Use |
|-------|-----|
| `log-session` | End-of-session human distillate |
| `log-session-snapshot` | Resume bootstrap snapshot |
| `session-chronicle` | Provenance / UUID-style tracking when available |
| `agenttrace-session-audit` / `agentic-actions-auditor` | Deeper audit patterns |
| `handoff` | Clean handoff between sessions |
| `subagent-orchestrator` | Emit dispatch/result events here |

## Where to write (default)
Prefer project-local (gitignored if secrets):

```
.agent-journal/
  YYYY-MM-DD.jsonl      # machine timeline (append-only)
  YYYY-MM-DD.md         # human daily index (optional)
  incidents/            # RCA notes when investigating
```

If no project: `~/.cursor/agent-journal/` (user-global).

Create `.agent-journal/.gitignore` with `*` and `!.gitignore` only if user wants privacy — otherwise commit distillates, not raw tool dumps.

## Event schema (one JSON object per line)
```json
{
  "ts": "2026-07-24T12:00:00Z",
  "session": "optional-id",
  "actor": "parent|subagent:<role>|<task-id>",
  "event": "plan|dispatch|tool|result|error|decision|verify|integrate",
  "summary": "short human line",
  "paths": ["src/a.ts"],
  "tools": ["Shell","Task"],
  "status": "ok|fail|blocked",
  "error": null,
  "parent_event": null,
  "meta": {}
}
```

Rules:
- **Append only** — never edit past JSONL lines
- Keep `summary` ≤ 200 chars; put blobs on disk and reference path in `meta.artifact`
- On every **Task** dispatch/result and every **failed** tool — must log
- On user-visible errors — log `event=error` with message truncated to 500 chars

## When to log (minimum)
1. Start of multi-step task (`plan`)
2. Each subagent dispatch / return
3. Destructive or risky commands
4. Test/browser failures
5. Final integrate / handoff

## Investigation workflow (“найди источник проблемы”)
1. Ask: symptom + approximate time
2. `rg` / read `.agent-journal/YYYY-MM-DD.jsonl` filtered by `status=fail` or error text
3. Walk `parent_event` / task-id chain parent → subagent → tool
4. Open referenced `meta.artifact` / git diff at that timestamp
5. Write short RCA to `.agent-journal/incidents/YYYY-MM-DD-<slug>.md`:
   - Symptom
   - Timeline (event ids)
   - Root cause
   - Fix
   - Prevention

## Human daily index (optional markdown)
Append a bullet under `## Timeline` linking to task ids — distillate, not transcript (`log-session` at wrap-up).

## Token rules
- Do not paste entire journal into chat; `grep`/`Select-String` slices
- Pair with `token-sentinel` on long sessions

## Agent startup
If `.agent-journal/` exists and user continues work: skim last 20 JSONL lines or yesterday’s incident — do not reload full history.