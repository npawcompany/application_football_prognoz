# Football Prognoz

Десктоп-приложение на Python (Windows и macOS) для статистических прогнозов футбольных матчей: вероятности **1 / X / 2** и текстовый разбор по фактам.

Полное описание: [docs/PRODUCT.md](docs/PRODUCT.md). Архитектура: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Правила: [docs/RULES.md](docs/RULES.md). Документация источников: [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md). Порядок изучения доков: [docs/DOC_STUDY.md](docs/DOC_STUDY.md). Диплом (ВКР): [docs/VKR.md](docs/VKR.md). Текст глав 1.1 и 2.2 на вычитку: [docs/vkr/tekst-na-vychitku.md](docs/vkr/tekst-na-vychitku.md). Расчёт прогноза (факты / оценки / 1X2): [docs/FORECAST.md](docs/FORECAST.md). Наивная эвристика 5 матчей: [docs/HEURISTIC_FIVE_MATCH.md](docs/HEURISTIC_FIVE_MATCH.md).

Прогноз **не является** советом ставить деньги.

## Стек

Flet (окно приложения), httpx, pandas, SQLite, Elo + Poisson. LLM (Ollama Cloud или локальный Ollama) только объясняет уже посчитанные вероятности и никогда их не меняет.

Данные: [football-data.org](https://www.football-data.org/) (календарь и результаты), [football-data.co.uk](https://www.football-data.co.uk/data.php) (длинные CSV) и опционально [API-Football v3](https://www.api-football.com/documentation-v3) (травмы, дисквалификации, карточки, составы).

## Требования

- Python 3.11+
- Ключ [football-data.org](https://www.football-data.org/client/register) (бесплатный план)
- Опционально: ключ [Ollama Cloud](https://ollama.com/settings/keys) или локальный Ollama
- Опционально: ключ [API-Football](https://dashboard.api-football.com/register) (бесплатно 100 запросов в сутки)

## Настройка AI и API-Football

Все ключи вводятся в разделе **Настройки** (или в `.env`) и применяются сразу после «Сохранить», без перезапуска.

| Переменная | По умолчанию | Зачем |
|---|---|---|
| `OLLAMA_API_KEY` | пусто | Ключ Ollama Cloud. Пусто и облачный хост = AI-разбор выключен |
| `OLLAMA_HOST` | `https://ollama.com` | Для локального Ollama: `http://127.0.0.1:11434` (ключ не нужен) |
| `OLLAMA_MODEL` | `deepseek-v4.1-flash` | Основная модель разбора |
| `OLLAMA_FALLBACK_MODEL` | `gpt-oss:120b` | Одна повторная попытка при 404/5xx/пустом ответе |
| `API_FOOTBALL_KEY` | пусто | Блок «Состав и доступность». Пусто = 0 запросов |
| `GNEWS_API_KEY` | пусто | Новости команд через [GNews](https://gnews.io) (≤ 80 запросов/сутки, кэш 6 ч) |
| `NEWS_RSS_ENABLED` | `true` | Новости из RSS BBC Sport, Guardian, Sky Sports, ESPN без ключа (кэш 1 ч) |

API-Football расходует не больше 90 запросов в сутки (счётчик в SQLite), ответы кэшируются. На бесплатном плане текущий сезон может быть недоступен — тогда блок показывает заметку, прогноз не ломается.

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
