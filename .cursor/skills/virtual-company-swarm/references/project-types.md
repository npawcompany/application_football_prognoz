# Виды проектов и скиллы

Грузить **тело** SKILL.md: overlay + **один** доменный (макс. 2 сразу). Остальные имена — только маршрутизация.

**Overlay на любую крупную задачу:** `virtual-company-swarm` → `subagent-orchestrator`. Журнал: `agent-action-journal`. QA перед «готово»: `verification-before-completion`. Git: `git` / `git-workflow-and-versioning`. Постановка CrewAI/LangGraph/Hermes: `multiagent-runtime-install` (+ `python-venv-manager`).

Не грузить вместе тела: `agent-orchestrator` + `multi-agent-task-orchestrator` + `parallel-agents`. Vue vs React — взаимоисключающе. Figma URL → figma-скиллы, не `canvas-design` вместо них.

---

## A. Семейства из пака (виртуальная компания ведёт разработку)

| # | Вид проекта | Primary skill | Ещё в каталоге (не все тела) |
|---|-------------|----------------|------------------------------|
| 1 | React / Next веб | `react-best-practices` | `frontend-ui-engineering`, `web-design-guidelines` |
| 2 | Vue / Nuxt / vanilla | `vue-nuxt-vanilla` | `frontend-ui-engineering` (без React-скилла) |
| 3 | UI с нуля (без Figma) | `frontend-design` | `frontend-ui-engineering`, `theme-factory` |
| 4 | Python API / CLI / сервис | `python-dev` | `python-venv-manager`, `pytest-best-practices` |
| 5 | Go-сервис | `golang-code-style` | `golang-database`, `go-mod-helper`, `golang-concurrency` |
| 6 | Данные / Postgres | `sql-databases` | `sqlalchemy-postgres`, `query-optimizer`, `query-builder` |
| 7 | Docker / compose | `docker-compose` | `docker-basics`, `docker-production`, `docker-security` |
| 8 | Kubernetes | `k8s-troubleshooter` | `docker-production`, `observability-and-instrumentation` |
| 9 | Terraform / IaC | `terraform-style-guide` | `terraform-test`, `iac-terraform`, `infra-multicloud` |
| 10 | CI/CD | `ci-cd` | `ci-cd-and-automation`, `deploy-to-vercel` |
| 11 | Figma → код | `figma-design-to-code` | `figma-connect`, `figma-use` |
| 12 | Дизайн в Figma | `figma-generate-design` | `figma-use`, `figma-generate-library` |
| 13 | Браузерный QA | `webapp-testing` | `cursor-ide-browser` **или** `agent-browser` **или** `playwright-mcp-browsers` |
| 14 | n8n-автоматизация | `using-n8n-skills-official` | `automation-hub`, `n8n-workflow-patterns` |
| 15 | Zapier / Make | `zapier-make-patterns` | не форсить n8n |
| 16 | Документы Office / PDF | `docx` / `pptx` / `xlsx` / `pdf` | ingest в MD: `markitdown` (не вместе с edit) |
| 17 | Ресёрч / краулинг | `firecrawl-search` | `firecrawl-scrape`, `firecrawl-crawl`, `firecrawl-map` |
| 18 | Русский текст / редакция | `ru-text` | `russian-literature-kb`, `russian-editorial-review`, `redaktura` |
| 19 | Контент / посты | `statya` / `post` / `promo` / `ux-copy` | `internal-comms` |
| 20 | Креатив (арт, видеопромпты) | `algorithmic-art` / `ai-video-prompts` | `slack-gif-creator`, `canvas-design` |
| 21 | Сам пак скиллов / правил | `custom-skill-factory` | `create-rule`, `create-skill`, `learn-and-guides` |

Роли swarm: Router = `skills-router` + `subagent-orchestrator`; Architect = `spec-driven-development` / `documentation-and-adrs`; Dev = `incremental-implementation` + строка таблицы; QA = `verification-before-completion` + `test-driven-development` / `pytest-best-practices`.

---

## B. CrewAI (Python-экипаж как продукт)

Сначала `multiagent-runtime-install`, код — `python-dev`. Overlay swarm остаётся в Cursor; экипаж — отдельный процесс.

| # | Вид | Primary | Дополнительно |
|---|-----|---------|---------------|
| 22 | Ресёрч-экипаж | `multiagent-runtime-install` | `firecrawl-search`, `python-venv-manager` |
| 23 | Контент / редактура | то же | `ru-text` или `statya` |
| 24 | Саппорт-триаж | то же | `api-and-interface-design` |
| 25 | Ревью / миграция кода | то же | `code-review-and-quality`, `git` |
| 26 | Извлечение данных из файлов | то же | `markitdown`, `xlsx` |
| 27 | Ops-отчёты по расписанию | то же | `observability-and-instrumentation` |
| 28 | «Виртуальная фирма» на Python (PO/Dev/QA как crew) | то же | `virtual-company-swarm` только как спека ролей, не второй рантайм |

---

## C. LangGraph (граф как бэкенд)

| # | Вид | Primary | Дополнительно |
|---|-----|---------|---------------|
| 29 | Чат с инструментами | `multiagent-runtime-install` | `python-dev`, `api-and-interface-design` |
| 30 | RAG-ассистент | то же | `sql-databases` если индекс в БД |
| 31 | Граф с человеком в петле | то же | `spec-driven-development` |
| 32 | Супервизор нескольких агентов | то же | не дублировать телами `multi-agent-task-orchestrator` |
| 33 | Агентный ETL | то же | `query-builder`, `python-dev` |
| 34 | Маршрутизатор тикетов | то же | `api-and-interface-design` |
| 35 | Durable workflow (рестарт, чекпоинты) | то же | `observability-and-instrumentation` |

Фронт к графу: строка 1 или 2 из блока A, не третий мозг.

---

## D. Hermes Agent (на машину, не в git)

| # | Вид | Primary | Дополнительно |
|---|-----|---------|---------------|
| 36 | Личный CLI-агент | `multiagent-runtime-install` | `memory-forge` (идеи памяти, не замена CLI) |
| 37 | Шлюз Telegram / Discord | то же | ключи только в `.env` / конфиг Hermes |
| 38 | Агент с памятью между сессиями | то же | `project-memory` в репо, если нужна git-память |
| 39 | Фоновый оператор / gateway | то же | не смешивать с Cursor Task без явной границы |

---

## E. Гибриды (один мозг в проде)

| # | Вид | Primary | Второй (не три тела) |
|---|-----|---------|----------------------|
| 40 | Cursor пишет, LangGraph — API продукта | домен из A | `multiagent-runtime-install` |
| 41 | Cursor пишет, CrewAI — пакетные экипажи | домен из A | `multiagent-runtime-install` |
| 42 | React/Vue + LangGraph API | `react-best-practices` **или** `vue-nuxt-vanilla` | runtime-install |
| 43 | n8n дергает Crew/LangGraph | `using-n8n-skills-official` | runtime-install |
| 44 | Hermes снаружи, Cursor в IDE | `virtual-company-swarm` | runtime-install только при установке Hermes |

Не делать: CrewAI + LangGraph + Hermes в одном продукте. Не инжектить рантаймы в каждый репозиторий — только `.cursorrules`.

---

## F. Внешние киты (21-project-kits)

Overlay swarm не ставит эти продукты сам. Primary — кит; setup в `references/setup.md`.

| # | Вид | Primary | Не грузить вместе |
|---|-----|---------|-------------------|
| 45 | Rybbit analytics (self-host/hosted) | `rybbit-analytics` | Firecrawl как аналитика |
| 46 | BoardUI agent chat / dashboard | `boardui` | `ui-ux-pro-max`, Vue |
| 47 | witr (почему процесс жив) | `witr` | подмена на k8s без нужды |
| 48 | GitHub Spec Kit (specify + /speckit-*) | `github-spec-kit` | тело `spec-driven-development` |
| 49 | UI/UX Pro Max (дизайн-система из каталога) | `ui-ux-pro-max-setup` затем сгенерированный `ui-ux-pro-max` | `boardui` + `frontend-design` |
| 50 | ScrapeGraphAI (LLM scrape graphs) | `scrapegraph-ai` | Firecrawl |
