# Архитектура

Пакет `football_prognoz`, исходники в `src/` (src-layout). UI не ходит в HTTP напрямую.

## Слои

| Слой | Путь | Можно | Нельзя |
|---|---|---|---|
| UI | `ui/` | `services/`, `domain/`, Flet | `httpx`, SQLite, сырой JSON API |
| Services | `services/` | `data/`, `models/`, `ai/`, `domain/` | виджеты Flet |
| Data | `data/` | HTTP, CSV, SQLite | Flet, LLM, бизнес-прогноз |
| Models | `models/` | фичи и вероятности 1X2 | HTTP, Flet |
| AI | `ai/` | LLM по готовым фактам | считать вероятности «кто победит» |
| Domain | `domain/` | dataclass/enum | I/O, Flet, httpx |

```text
ui  -->  services  -->  data (football-data.org, API-Football, CSV, SQLite)
                   -->  models (Elo, Poisson)
                   -->  ai (Ollama client, explainer)
ui  -->  domain
ui  -->  services.factory (build_service: сборка клиентов по Settings)
```

## Поток прогноза

Подробно, с формулами и разделением факт / оценка / вывод: [FORECAST.md](FORECAST.md).

1. Сервис матчей читает кэш SQLite; при промахе TTL ходит в football-data.org.
2. `features` собирает форму, H2H, Elo, средние голы за 5 матчей, место в таблице только из кэша.
3. `predictor` возвращает `p_home`, `p_draw`, `p_away` (сумма = 1): при малой выборке только Elo, иначе смесь Пуассон 65% + Elo 35%. Предварительный счёт — мода сетки по средним голам за 5 матчей, без Elo.
4. Числа 1X2 показываются сразу. Дальше в фоне `MatchService.enrich`:
   - `PlayerStatusService` (только с `API_FOOTBALL_KEY`) — травмы, дисквалификации, красные карточки, составы;
   - `NewsService` — свежие заголовки о командах: GNews по ключу, иначе RSS спортивных изданий (`NEWS_RSS_ENABLED`);
   - `FactsService` собирает пакет фактов: Elo, форма, дом/выезд, тренд голов, таблица, H2H, дни отдыха, состав;
   - `Explainer` отправляет пакет в Ollama (`POST /api/chat`, JSON-ответ), проверяет ответ (фаворит совпадает с расчётом, уверенность не выше потолка, нет «гарантий») и кэширует его.
5. UI: блок AI в одном из состояний — «загрузка», «ошибка», «не настроен», «готово». Вероятности LLM не меняет никогда.

## Сборка сервиса и настройки

`services/factory.build_service(settings)` создаёт клиентов football-data.org, API-Football и Ollama. Rate limiter'ы модульные и общие для всех сборок, поэтому пересоздание сервиса после «Сохранить» в Настройках не сбрасывает лимит. Старый сервис закрывается (`close()`), `.env` перечитывается при каждом `load_settings()`.

## Кэш

- SQLite: `data/cache/prognoz.db` (путь из `DATABASE_PATH`).
- TTL по умолчанию: 6 часов для `SCHEDULED`, 24 часа для `FINISHED` и таблиц.
- Повторный запрос к API только если кэш старше TTL или записи нет.
- Rate limit: не чаще 10 запросов в минуту (свободный план football-data.org), 10 в минуту и 90 в сутки для API-Football.
- Таблицы: `matches`, `standings`, `meta` (football-data.org); `api_cache` (ответы API-Football, GNews и RSS с TTL), `api_usage` (суточные счётчики запросов API-Football и GNews), `af_team_map` / `af_fixture_map` (сопоставление id), `llm_cache` (ответы LLM, 12 ч).
- «Очистить кэш» удаляет `api_cache` и `llm_cache`, но не сопоставления и не счётчик расхода.

## Секреты

Ключи только в `.env` в корне репозитория. Файл в `.gitignore`. В логи ключи не пишутся.
