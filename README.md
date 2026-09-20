# Football Prognoz

Десктоп-приложение на Python (Windows и macOS) для статистических прогнозов футбольных матчей: вероятности **1 / X / 2** и текстовый разбор по фактам.

Полное описание: [docs/PRODUCT.md](docs/PRODUCT.md). Архитектура: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Правила: [docs/RULES.md](docs/RULES.md). Документация источников: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md). Порядок изучения доков: [docs/DOC_STUDY.md](docs/DOC_STUDY.md). Диплом (ВКР): [docs/VKR.md](docs/VKR.md). Текст глав 1.1 и 2.2 на вычитку: [docs/vkr/tekst-na-vychitku.md](docs/vkr/tekst-na-vychitku.md). Расчёт прогноза (факты / оценки / 1X2): [docs/FORECAST.md](docs/FORECAST.md). Наивная эвристика 5 матчей: [docs/HEURISTIC_FIVE_MATCH.md](docs/HEURISTIC_FIVE_MATCH.md).

Прогноз **не является** советом ставить деньги.

## Стек

Flet (окно приложения), httpx, pandas, SQLite, Elo + Poisson. LLM (OpenAI или Ollama) только объясняет уже посчитанные вероятности.

Данные: [football-data.org](https://www.football-data.org/) (календарь и результаты) и [football-data.co.uk](https://www.football-data.co.uk/data.php) (длинные CSV).

## Требования

- Python 3.11+
- Ключ [football-data.org](https://www.football-data.org/client/register) (бесплатный план)
- Опционально: ключ OpenAI или локальный Ollama

## Запуск

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env        # впишите FOOTBALL_DATA_API_KEY
python -m football_prognoz
```

С `uv`:

```bash
uv sync --extra dev
uv run python -m football_prognoz
```

## Тесты

```bash
pytest
```

Тесты ходят только в фикстуры `data/samples/`, без живого API.

## Сборка установщиков

Собирать **только на целевой ОС** (Windows-сборку не делать на Linux, macOS-сборку — только на Mac). Нужен установленный Flutter/Flet CLI по [доке Flet](https://flet.dev/docs/publish/windows/).

```bash
flet build windows --product "Football Prognoz" --company "Football Prognoz"
flet build macos --product "Football Prognoz" --org com.footballprognoz --bundle-id com.footballprognoz.app
```

Конфигурация сборки: секция `[tool.flet]` в `pyproject.toml`.
