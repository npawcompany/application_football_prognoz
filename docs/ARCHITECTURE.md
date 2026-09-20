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
ui  -->  services  -->  data (football-data.org, CSV, SQLite)
                   -->  models (Elo, Poisson)
                   -->  ai (explainer)
ui  -->  domain
```

## Поток прогноза

Подробно, с формулами и разделением факт / оценка / вывод: [FORECAST.md](FORECAST.md).

1. Сервис матчей читает кэш SQLite; при промахе TTL ходит в football-data.org.
2. `features` собирает форму, H2H, Elo, средние голы за 5 матчей, место в таблице только из кэша.
3. `predictor` возвращает `p_home`, `p_draw`, `p_away` (сумма = 1): при малой выборке только Elo, иначе смесь Пуассон 65% + Elo 35%. Предварительный счёт — мода сетки по средним голам за 5 матчей, без Elo.
4. `explainer` получает JSON фактов + вероятности + предварительный счёт. Если ключа OpenAI нет — текст не генерируется.
5. UI показывает числа всегда; блок AI — только при наличии текста.

## Кэш

- SQLite: `data/cache/prognoz.db` (путь из `DATABASE_PATH`).
- TTL по умолчанию: 6 часов для `SCHEDULED`, 24 часа для `FINISHED` и таблиц.
- Повторный запрос к API только если кэш старше TTL или записи нет.
- Rate limit: не чаще 10 запросов в минуту (свободный план football-data.org).

## Секреты

Ключи только в `.env` в корне репозитория. Файл в `.gitignore`. В логи ключи не пишутся.
