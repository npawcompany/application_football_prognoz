---
name: token-sentinel
description: >
  Monitor approximate token spend and context pressure; warn before exhaustion; detect confusion
  and trigger a clean reset (handoff + compact/new chat). Use every multi-step task, long browser
  sessions, or when user asks about tokens/memory/context. Coordinates context-budget,
  token-budget-advisor, strategic-compact, context-budget-discipline.
---

# Token & memory sentinel

## Mission
1. **Estimate** tokens for the current request and the planned solution
2. **Warn** when context is filling or spend is wasteful
3. **Reset** when confused — flush memory to disk, then compact / new session

## Heuristics (no exact meter in all Cursor builds)
Use the same calibration as `context-budget` / `token-budget-advisor`:
- prose ≈ `words × 1.3`
- code/mixed ≈ `chars / 4`
- tool dump of HTML/snapshot/log → treat as high; prefer files on disk

Track roughly:
| Bucket | What |
|--------|------|
| Input (request) | User message + open files/skills descriptions |
| Working set | Files/tools loaded this turn |
| Output (solution) | Your reply + generated code |

## Warning thresholds (relative to model window)
Assume window W (e.g. 200k). If unknown, treat “long session + many tools” as pressure.

| Level | Signal | Action |
|-------|--------|--------|
| OK | short task, few tools | proceed |
| WARN ~50–70% | many reads, browser snapshots, long thread | tell user estimate; switch to token-thrifty; write notes to disk |
| HIGH ~70–85% | repeated re-reads, looping | **flush handoff** (`learn-and-guides` / progress.md); suggest `/compact` or `strategic-compact` |
| CRITICAL | incoherent, forgetting earlier decisions, tool loops | **STOP** → confusion protocol |

At **end of substantial replies**, add a one-liner when WARN+:
`Tokens≈ in:~X out:~Y session:WARN|HIGH — next: thrifty|compact|new-chat`

## Confusion / “need to clear” protocol
Triggers (any 2+):
- Contradicting own earlier plan in the same thread
- Re-reading the same files without new info
- Same failing browser/tool action 3+ times
- User says agent is lost / repeating
- Cannot state current goal in one sentence

Then do **RESET**:
1. **WRITE** durable state to disk (progress, decisions, open questions) — `context-budget-discipline` WRITE
2. **Summarize** 10-line handoff for the user
3. Recommend **new Agent chat** (preferred) or strategic `/compact` if platform supports it
4. Do **not** continue heavy tool use in the polluted context

## Coordination with ready skills
| Skill | Role |
|-------|------|
| `context-budget` | Inventory what’s eating context |
| `token-budget-advisor` | Ask user depth % before huge answers |
| `strategic-compact` | Compact at phase boundaries |
| `context-budget-discipline` | SELECT/WRITE/COMPRESS/ISOLATE |
| `recursive-context-pruning` | Gatekeeper pruning |
| `token-thrifty` / `skills-router` | Daily prevention |
| `caveman` / `caveman-compress` | Shrink prose / memory files |

## What you cannot do
Cursor may not expose exact live token counters to the agent. Always label numbers as **estimates**. Never invent precise billing figures.