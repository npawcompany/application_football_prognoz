---
name: python-dev
description: >
  Build and maintain Python apps: packaging, venv/uv/poetry, typing, pytest, FastAPI/Django/Flask,
  scripts, and data tooling. Use for any Python coding task. Prefer modern tooling (uv/ruff/pytest)
  and match project existing conventions.
---

# Python development

## Environment
- Prefer **uv** or existing lockfile tool (poetry/pip-tools); see `python-venv-manager`
- Never install into global Python unless user asks
- Pin deps; commit lockfiles when project already uses them

## Style
- Type hints on public functions; `pydantic` for IO boundaries
- Ruff for lint/format if available; else black/isort only if project uses them
- Explicit packages (`src/` layout when greenfield)

## Testing
- pytest (see `pytest-best-practices`); AAA; fixtures over copy-paste
- Prefer fast unit tests; mark integration/network tests

## Web APIs
- FastAPI: pydantic models, dependency injection, clear router modules
- Django: apps boundaries, ORM migrations, avoid fat views
- Flask: blueprints; keep simple

## Data / files
- pandas only when tabular analysis needs it
- For document→markdown use `markitdown` skill / Microsoft MarkItDown CLI
- SQL via SQLAlchemy or parameterized drivers (`sql-databases`)

## Anti-patterns
- `requirements.txt` without pins on new prod services
- Swallowing exceptions; bare `except:`
- Mutable default args
- Heavy work in import time