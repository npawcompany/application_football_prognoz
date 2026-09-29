---
name: football-prognoz
description: >
  Project skill for Football Prognoz: Python 3.11+ Flet desktop app, Elo+Poisson
  1X2 model, SQLite cache, football-data.org + CSV. Use for any work in this repo.
---

# Football Prognoz — project skill

Stack: **Python 3.11+**, Flet, httpx, pandas, SQLite, scikit-learn, Elo + Poisson. LLM only explains already computed probabilities.

## Load with this skill (max 2 bodies)

| Job | Primary | Support |
|-----|---------|---------|
| Any Python change | `python-dev` | `python-venv-manager` |
| Tests | `pytest-best-practices` | `verification-before-completion` |
| Model / sklearn | `scikit-learn` | `source-driven-development` |
| SQLite cache | `sql-databases` | — |
| Flet / API fields | `source-driven-development` | `docs/DOC_STUDY.md` |
| Multi-file feature | `virtual-company-swarm` | `subagent-orchestrator` |
| Failures / RCA | `agent-action-journal` | `debugging-and-error-recovery` |

Router: `skills-router`. Do not co-load overlapping orchestration skills.

## Non-negotiables (also in `.cursor/rules/football-prognoz.mdc`)

- UI talks only to `services/` and `domain/`. No `httpx` or SQLite from views.
- New HTTP APIs: document in `docs/DATA_SOURCES.md` first.
- Do not replace the local 1X2 model with ChatGPT.
- Cache every network response. football-data.org: 10 req/min.
- Code/commits English. UI strings Russian.
- Never commit `.env`, cache, CSVs, or keys.
- Tests use `data/samples/` only — no live API.
- Diploma / naive 5-match heuristic: `docs/VKR.md`, `docs/HEURISTIC_FIVE_MATCH.md`. Do not replace Elo+Poisson with ceil-home/floor-away scoring.

## Official docs first

Follow `docs/DOC_STUDY.md`: Flet, football-data.org v4, football-data.co.uk CSV, sklearn estimator, OpenAI/Ollama.

## Run

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # FOOTBALL_DATA_API_KEY
python -m football_prognoz
pytest
```
