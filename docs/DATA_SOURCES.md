# Источники данных

Запись в этом файле обязательна **до** нового HTTP-клиента.

## football-data.org (основной REST)

- Документация: https://www.football-data.org/documentation/api
- Quickstart: https://www.football-data.org/documentation/quickstart
- Coverage: https://www.football-data.org/coverage
- База: `https://api.football-data.org/v4`
- Заголовок: `X-Auth-Token: <key>`
- Free: 12 соревнований, 10 запросов/мин, счёт и расписание с задержкой.

### Endpoint’ы, которые использует приложение

- `GET /v4/competitions` — список лиг. Маппим `id`, `code`, `name`, `emblem`, `type` (`LEAGUE` / `CUP`), `area.name`, `area.code`, `area.flag`, `currentSeason.startDate`, `currentSeason.endDate`. Даты сезона решают, серая ли лига в списках (сезон закончился или начнётся позже чем через ~6 мес.). Ответ 400/401/403 означает «ключ не принят» (замок на экран настроек). TTL 24 ч.
- `GET /v4/competitions/{code}/matches` — календарь **текущего** сезона. Параметр `season` не передаём: API сам отдаёт `currentSeason`, это верно и для лиг июль–июнь, и для BSA (календарный год), и для WC/EC (год турнира). TTL 6 ч.
- `GET /v4/matches?dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD` — матчи всех доступных лиг за период (оба параметра обязательны вместе). Документ: Match → «Available filters for the list resource» (https://docs.football-data.org/general/v4/match.html). Период не шире 10 дней (иначе API отвечает 400). Календарь дня берёт **одну неделю за раз** (пн–вс ±1 день на часовые пояса = 9 дней), TTL 6 ч для текущих и будущих недель, 24 ч для прошедших. Поля: те же, что у матча, плюс `competition.code` / `competition.type` / `competition.emblem` (код лиги берём оттуда); матчи лиг вне free-тира отбрасываем.
- `GET /v4/competitions/{code}/standings` — таблица. Берём **все** блоки `type=TOTAL` (у WC/EC/CL их несколько, поле `group` = `GROUP_A`…), команду не дублируем. TTL 24 ч.
- `GET /v4/competitions/{code}/teams` — клубы/сборные сезона (по умолчанию текущий; `?season=YYYY` для прошлых). `{code}` — код или id соревнования.
- `GET /v4/teams/{id}` — карточка клуба: `coach`, `squad`, `venue`, `address`, `area`. Только в фоне после показа прогноза.
- `GET /v4/matches/{id}` — деталь матча: `venue`, `homeTeam.lineup` / `bench` (основа и запас). TTL 6 ч. Только в фоне.

Клиент держит лимит 10 запросов/мин сам и **не спит под замком**. Фоновые запросы деталей (`/teams/{id}`, `/matches/{id}`) ждут свободный слот не дольше 15 с, иначе считаем ответ 429 и показываем кэш.

### Поля матча (v4), которые маппим в domain

`id`, `utcDate`, `status`, `matchday`, `homeTeam.id`, `homeTeam.name`, `awayTeam.id`, `awayTeam.name`, `score.fullTime.home`, `score.fullTime.away`, `score.winner`.

### Поля команды (v4 `/competitions/{code}/teams`), которые маппим в domain.Team

`id`, `name`, `shortName`, `tla`, `crest`.

### Поля состава (v4 `/teams/{id}`), которые маппим в domain.TeamRoster

Документ: раздел Team / Player на https://www.football-data.org/documentation/api

- Команда: `id`, `name`, `crest`.
- Тренер `coach`: `id`, `name`, `dateOfBirth`, `nationality`, `contract.until` (если объект есть).
- Игрок `squad[]`: `id`, `name`, `position` (`Goalkeeper` / `Defence`|`Defender` / `Midfield`|`Midfielder` / `Offence`|`Attacker`), `dateOfBirth`, `nationality`, `role`, `shirtNumber` (номер часто пустой вне lineup матча).

Стартовый состав матча (`homeTeam.lineup` / `bench` в примере Match) на бесплатном тарифе для ещё не сыгранных игр обычно пустой — в UI показываем **заявку клуба**, не XI. Травм и «состояния готовности» в v4 нет: в карточке только амплуа, гражданство и возраст с `dateOfBirth`.

Не выдумывать поля вроде `xG` или `injuries` — в free v4 их нет.

### Поля стадиона / страны (v4)

Документ: Match (`venue`) и Team (`venue`, `address`, `area.name`, `area.code`) на https://www.football-data.org/documentation/api

- Матч: `venue` — название стадиона (часто пусто в list-ответе → берём `Team.venue` хозяев).
- Команда: `venue`, `address` (из него эвристика города), `area.name`, `area.code` (ISO3 / FIFA вроде `ENG`).
- Отдельного поля «город» в v4 нет.
- Стартовый состав: `GET /v4/matches/{id}` → `homeTeam.lineup` / `bench` / `coach` (пример Match в той же доке). На SCHEDULED часто пусто. Один запрос на матч, TTL 6 ч. Нет поля player Elo.

### Флаги стран (API `area.flag` + бандл)

- Источник 1: `area.flag` из `GET /v4/competitions` — SVG на том же CDN, что гербы (`https://crests.football-data.org/770.svg` — Англия, `EUR.svg` — Европа). URL лежит в SQLite (`competitions.area_flag`), картинку кэширует Flutter (в памяти, на сессию). Отдельных запросов к API нет, лимит 10/мин не тратится.
- Источник 2 (fallback): бандл [flag-icons](https://github.com/lipis/flag-icons) v7.5.0, MIT, файлы `flags/4x3/*.svg`. Показывается, если URL нет, CDN не ответил или приложение офлайн (`Image.error_content`).
- Скрипт бандла: `python scripts/sync_flags.py` → `src/assets/flags/{code}.svg`.
- Коды: ISO 3166-1 alpha-2; сборные UK — `gb-eng`, `gb-sct`, `gb-wls`, `gb-nir`; Европа — `eu`.
- Без флага в API: World (`area.code` `INT`, `flag: null`) и континенты → значок глобуса; неизвестное имя → контур флага. Логика: `domain.country.resolve_flag`.
- Флаги игроков/клубов (`nationality`, `area.name` у команды) — только бандл.

### CDN гербов (официальный, тот же хост, что в `crest` / `emblem`)

- База: `https://crests.football-data.org/`
- Клуб/сборная: `https://crests.football-data.org/{id}.png`
- Соревнование: сначала `https://crests.football-data.org/{code}.png` (например `PL.png`); если CDN 404 — тот же хост `{competitionId}.png` (как в поле `emblem` v4).
- Живой HTTP только из `scripts/sync_crests.py` (не из UI). Лимит API 10 req/min. Если оба URL 404 (типично BSA) → `manifest.missing`, без Wikipedia и без букмекеров.
- В старых примерах доки ещё встречается `crestURI`; в JSON v4 поле называется `crest` (как уже маппим в матчах).

### Коды free-тира

`PL`, `PD`, `SA`, `BL1`, `FL1`, `DED`, `PPL`, `ELC`, `BSA`, `CL`, `WC`, `EC`.

### Ошибки

- `400` / `401` / `403` — нет/неверный ключ или лига не в тарифе (для `/competitions` → «ключ не принят»).
- `429` — превышен лимит; клиент обязан подождать (или отдать кэш, если ждать дольше 15 с).
- Нет сети / таймаут / не-JSON ответ → та же ошибка `FootballDataError`, UI берёт данные из кэша SQLite.

### Заметка изучения

- Дата: 2026-09-20
- URL: https://www.football-data.org/documentation/api
- Версия: v4
- В код: `X-Auth-Token`, matches + standings + teams + `GET /teams/{id}` (coach/squad), TTL-кэш, 10 req/min, CDN crests
- 2026-09-29: `area.flag` соревнований показываем в UI (CDN crests), бандл — запасной вариант
- 2026-09-29: `GET /v4/matches?dateFrom&dateTo` для календаря по дням; поля `type`, `area`, `currentSeason` у соревнований; все группы в standings; без `season` в календаре лиги
- Лимиты: 10/мин на free
- В доке нет: xG, injuries, гарантии lineup на SCHEDULED; часть эмблем (BSA) может отдавать CDN 404 и на `{code}.png`, и на `{id}.png`

## football-data.co.uk (CSV для обучения)

- https://www.football-data.co.uk/data.php
- Пример: `https://www.football-data.co.uk/mmz4281/2425/E0.csv`
- Колонки: `Div`, `Date`, `HomeTeam`, `AwayTeam`, `FTHG`, `FTAG`, `FTR`
- Маппинг дивизионов: `E0→PL`, `SP1→PD`, `I1→SA`, `D1→BL1`, `F1→FL1`, `N1→DED`, `P1→PPL`, `E1→ELC`
- Не коммитить скачанные CSV (`data/csv/` в gitignore). В git только `data/samples/`.

### Заметка изучения

- Дата: 2026-09-20
- URL: https://www.football-data.co.uk/data.php
- В код: парсер Date (`%d/%m/%Y` и `%d/%m/%y`), FTHG/FTAG/FTR
- Лимиты: публичные файлы, обновление ~2 раза в неделю
- В доке нет: стабильного REST; это файлы, не API

## Ollama Cloud / локальный Ollama (только текст)

OpenAI из проекта убран. Объяснитель ходит в Ollama одним прямым HTTP-вызовом, без LangChain.

- Документация: https://docs.ollama.com/cloud , https://docs.ollama.com/api/chat , https://docs.ollama.com/api/authentication , https://docs.ollama.com/api/errors , https://docs.ollama.com/capabilities/thinking , https://docs.ollama.com/capabilities/structured-outputs
- База: `OLLAMA_HOST`, по умолчанию `https://ollama.com` (облако). Для локального сервера: `OLLAMA_HOST=http://127.0.0.1:11434`, ключ не нужен.
- Endpoint: `POST {OLLAMA_HOST}/api/chat` (нативный API). OpenAI-совместимый `POST {OLLAMA_HOST}/v1/chat/completions` тоже существует, но приложение его не использует: выключить thinking надёжно можно только в нативном API (`"think": false`).
- Заголовок: `Authorization: Bearer <OLLAMA_API_KEY>` (ключ: https://ollama.com/settings/keys, не истекает). Без ключа облако отвечает 401. Для локального хоста заголовок не отправляется.
- Модели (имена из `GET https://ollama.com/api/tags`, без суффикса `:cloud`): по умолчанию `gpt-oss:120b` (thinking выключить нельзя, отправляем `"think": "low"`), запасная `gpt-oss:20b`. Модель выбирается в Настройках из выпадающего списка (`OLLAMA_MODEL`, `OLLAMA_FALLBACK_MODEL`; можно вписать любое имя). Список в приложении (`KNOWN_OLLAMA_MODELS`) снят с `GET https://ollama.com/api/tags` 2026-09-30: `gpt-oss:120b`, `gpt-oss:20b`, `gemma4:31b`, `nemotron-3-super`, `nemotron-3-nano:30b`, `deepseek-v4.1-flash`, `deepseek-v4-pro:0813`, `glm-5.3-flash`, `glm-5.3`, `glm-5.2`, `minimax-m3`, `minimax-m2.7`, `mistral-large-3:675b`, `kimi-k2.6`, `kimi-k3`, `nemotron-3-ultra`.
- Бесплатный тариф: официального списка «starter models» нет в открытом доступе (виден только в кабинете). По странице pricing и ответам 402 считаем бесплатными `gpt-oss:120b` и `gpt-oss:20b` (`FREE_OLLAMA_MODELS`); остальные помечены в списке «может требовать кредиты» / «платно». ⚠ Проверить в кабинете ollama.com.
- Тело запроса: `model`, `messages[{role, content}]`, `stream: false`, `think`, `format: "json"`, `options.temperature`.
- Ответ (поля, которые читаем): `model`, `message.role`, `message.content`, `done`, `done_reason`. Думающие модели кладут рассуждение в `message.thinking` — его не показываем. Метрики `prompt_eval_count` / `eval_count` не используем.
- Ошибки: JSON `{"error": "..."}`; коды 400, 401, 402 (модель не входит в тариф / кончились кредиты), 403, 404 (нет модели), 429 (лимит / очередь), 500, 502 (облачная модель недоступна).
- Цепочка моделей: на 402, 403 со словами subscription/plan/upgrade/credits, 404 и 5xx клиент идёт дальше по цепочке `OLLAMA_MODEL → OLLAMA_FALLBACK_MODEL → бесплатные gpt-oss:120b / gpt-oss:20b` (бесплатные — только для облачного хоста). Если ответила не выбранная модель, в разборе показывается уведомление на русском: какая модель ответила и что модель можно сменить в Настройках. 401 (ключ) цепочку не запускает.
- JSON-режим на облаке не гарантирован: страница structured outputs пишет «Ollama's Cloud currently does not support structured outputs», а страница OpenAI-совместимости упоминает JSON mode. Поэтому схема ответа описана в системном промпте, `format: "json"` отправляется как подсказка, ответ всегда валидируется, при невалидном JSON — один повтор с `temperature: 0`.
- Лимиты: Free — стартовые кредиты и набор «starter models», 1 одновременный запрос (https://ollama.com/pricing). Точный список starter-моделей виден только в кабинете.
- Кэш запросов: ответ LLM хранится в SQLite (`llm_cache`) по хэшу `модель + промпт`, TTL 12 ч.
- Сохранённые разборы: каждый успешный AI-разбор матча и «Итог по новостям» пишется в `llm_analyses(match_id, kind, payload, model, generated_at, kickoff_utc)`; `clear_all` их не трогает. Политика вызовов — в `docs/FORECAST.md`, раздел «Когда вызывается LLM».
- Вход объяснителя: пакет фактов + уже посчитанные вероятности 1X2 + таблица ставок (`markets`: id, рынок, вероятность, справедливый кэф, уверенность; недоступные рынки — отдельным списком с причиной). Запрещено просить модель «угадать счёт» или менять вероятности. Ответ: разбор + `market_comments` + ровно 3 `top_markets` + `risks`; каждый id рынка должен быть в таблице, процент в тексте — не дальше 1,5 п.п. от таблицы, иначе один повтор.
- Итог по новостям: отдельный вызов с пронумерованными заголовками (`h1…`, `a1…`), ответ ссылается только на эти id; цитаты сверяются с заголовками, проценты запрещены.

### Заметка изучения

- Дата: 2026-09-29
- URL: https://docs.ollama.com/api/chat , https://docs.ollama.com/cloud
- В код: `POST /api/chat`, Bearer-ключ, `think`, `format: "json"`, fallback-модель, 1 повтор при невалидном JSON
- Лимиты: 401 без ключа, 429 при переполнении очереди, 502 при недоступной облачной модели
- В доке нет: гарантии JSON-схемы на облаке; списка starter-моделей free-тарифа
- Дата: 2026-09-30 — список моделей из `GET https://ollama.com/api/tags`; код 402 из https://docs.ollama.com/api/errors ; бесплатные модели выбраны по https://ollama.com/pricing (официального списка нет)

## API-Football v3 (api-sports.io): травмы, карточки, составы, трансферы

Необязательный источник косвенных факторов. **Включается только при заданном `API_FOOTBALL_KEY`**: без ключа приложение не делает ни одного запроса и не показывает ошибок. Прогноз 1X2 от этого источника не зависит — данные идут только в пакет фактов для LLM и в блок «Состав и доступность».

> ⚠ Ответы ещё **не проверены вживую**: ключа пока нет. Поля ниже взяты из официальной OpenAPI-спецификации v3.9.3 (`https://www.api-football.com/public/doc/openapi.yaml`, архивная копия от 02.11.2025: http://web.archive.org/web/20251102131202/https://www.api-football.com/public/doc/openapi.yaml) и документации https://www.api-football.com/documentation-v3 . Фикстуры в `data/samples/api_football/` — официальные примеры ответов из этой спецификации (и синтетический календарь в той же схеме для теста сопоставления). После получения ключа сверить каждый endpoint одним запросом.

- База: `https://v3.football.api-sports.io` (аккаунт dashboard.api-football.com; RapidAPI — другой URL и другой ключ, не поддерживаем).
- Заголовок: `x-apisports-key: <API_FOOTBALL_KEY>`. Только GET; разрешены только заголовки `x-rapidapi-host`, `x-rapidapi-key`, `x-apisports-key` — лишние дают ошибку. Поэтому клиент не шлёт своих заголовков, кроме ключа.
- Обёртка ответа: `get`, `parameters`, `errors`, `results`, `paging.current`, `paging.total`, `response`. `errors` бывает пустым массивом `[]` или объектом (`{"time": ..., "bug": ..., "report": ...}`; на практике также `token`, `plan`, `requests`, `rateLimit` — ⚠ проверить). Непустой `errors` = ошибка, даже при HTTP 200.
- HTTP-ошибки из спеки: `204` (нет данных), `499` (time out), `500` — тело `{"message": "..."}`.
- Заголовки ответа: `x-ratelimit-requests-limit`, `x-ratelimit-requests-remaining` (сутки), `X-RateLimit-Limit`, `X-RateLimit-Remaining` (минута). Превышение минутного лимита может привести к блокировке файрволом.
- `GET /status` не тратит суточную квоту: `response.subscription.plan`, `response.requests.current`, `response.requests.limit_day`.
- Тарифы: Free — 100 запросов в сутки, все endpoint'ы, но ограничены сезоны (по отзывам 2026 — только 2022–2024, текущий сезон недоступен → `errors.plan`, ⚠ проверить). Pro $19 — 7 500/сутки. Минутный лимит в спецификации не указан — клиент по умолчанию держит 10/мин и дополнительно читает `X-RateLimit-Remaining`.

### Как приложение бережёт квоту

- Суточный бюджет 90 запросов (запас до 100) считается в SQLite по UTC-дню (`api_usage`); при исчерпании запросы не отправляются до следующих суток. Если `x-ratelimit-requests-remaining` = 0 — бюджет дня закрывается сразу.
- Минутный лимит: общий `RateLimiter` на процесс (не сбрасывается при сохранении настроек).
- `429` → пауза (`Retry-After`, иначе 2 с, 4 с), максимум 2 повтора, потом ошибка без повтора.
- Ошибка тарифа (`errors.plan`) кэшируется на 24 ч для пары лига/сезон — повторно не тратим запросы.
- Порядок важности на прогноз: календарь сезона → травмы → карточки последних матчей → составы (только около начала) → рейтинги → sidelined → трансферы → статистика последних матчей (угловые / карточки / фолы / пенальти для таблицы ставок). Четыре последних пропускаются, если в бюджете дня осталось меньше 20 запросов.
- Статистика: последние 3 завершённых матча каждой команды (до 6 запросов `/fixtures/statistics` на прогноз, завершённый матч кэшируется 30 дней, `af:stats:<fixture>`); пенальти берутся из уже закэшированных `/fixtures/events` (`af:events`), без новых запросов.

### Endpoint'ы и поля, которые читаем

| Endpoint | Параметры | Поля ответа (`response[]`) | Обновление у провайдера | TTL в SQLite |
|---|---|---|---|---|
| `GET /fixtures` | `league`, `season` (весь сезон одним запросом) | `fixture.id`, `fixture.date`, `fixture.timestamp`, `fixture.status.short`, `league.id`, `league.season`, `teams.home.id/name`, `teams.away.id/name`, `goals.home/away` | — | 12 ч |
| `GET /injuries` | `fixture` | `player.id`, `player.name`, `player.type` (`Missing Fixture` / `Questionable`), `player.reason` (`Knee Injury`, `Suspended`, …), `team.id`, `team.name`, `fixture.id`, `fixture.date` | каждые 4 ч | 4 ч |
| `GET /sidelined` | `players` (до 20 id через `-`) | `id`, `sidelined[].type`, `sidelined[].start`, `sidelined[].end` (с `player=` — плоский список `type/start/end`) | несколько раз в неделю | 24 ч |
| `GET /fixtures/events` | `fixture` | `time.elapsed`, `time.extra`, `team.id`, `team.name`, `player.id`, `player.name`, `type` (`Goal`/`Card`/`subst`/`Var`), `detail` (`Yellow Card`, `Red Card`/`Red card`, `Second Yellow card` — ⚠ регистр проверить) | каждые 15 с | 30 дней (матч завершён) |
| `GET /transfers` | `team` | `player.id`, `player.name`, `update`, `transfers[].date`, `transfers[].type`, `transfers[].teams.in.id/name`, `transfers[].teams.out.id/name` | несколько раз в неделю | 7 дней |
| `GET /fixtures/lineups` | `fixture` | `team.id`, `team.name`, `formation`, `startXI[].player.{id,name,number,pos,grid}`, `substitutes[].player.{…}`, `coach.{id,name}` | каждые 15 мин, за 20–40 мин до матча | 15 мин до матча, 30 дней после |
| `GET /fixtures/statistics` | `fixture` | `team.id`, `team.name`, `statistics[].type` / `.value`; читаем `Corner Kicks`, `Fouls`, `Yellow Cards`, `Red Cards`; `null` = 0 | каждую минуту | 30 дней (матч завершён) |
| `GET /fixtures/players` | `fixture` | `team.id`, `players[].player.{id,name}`, `players[].statistics[0].games.{minutes,position,rating}`, `statistics[0].cards.{yellow,red}`; `rating` — строка (`"6.3"`) | каждую минуту | 30 дней |

Пенальти: события `type = Goal` с `detail = Penalty` (забит) или `Missed Penalty` (не забит); удары серии пенальти (`comments = "Penalty Shootout"` или минута > 120) не считаются. ⚠ Значения `detail` взяты из спецификации, вживую не сверены. Без ключа рынки угловых / карточек / фолов / пенальти показываются как «нет данных (нужен ключ API-Football)».

Составы запрашиваются только в окне от 60 мин до начала до 3 ч после, либо для завершённого матча; иначе 0 запросов. Рейтинги — только за последний сыгранный матч каждой команды.

### Сопоставление с football-data.org

- Лиги — статическая карта (`FD_TO_AF_LEAGUE`): `PL→39`, `PD→140`, `SA→135`, `BL1→78`, `FL1→61`, `DED→88`, `PPL→94`, `ELC→40`, `BSA→71`, `CL→2`, `WC→1`, `EC→4`. PL 39, CL 2 и Ligue 1 61 есть в примерах спецификации; остальные общеизвестны — ⚠ сверить `GET /leagues?id=` после получения ключа.
- Сезон API-Football = год начала сезона; для `BSA`, `WC`, `EC` — календарный год матча.
- Матчи и команды: берём календарь сезона (`/fixtures?league=&season=`), ищем фикстуру с датой в пределах ±36 ч от `utcDate` football-data.org и совпадающими нормализованными названиями хозяев и гостей (нижний регистр, без диакритики, без токенов `fc`, `afc`, `cf`, `sc`, `ac`, `club`, `de`, … , `&`→`and`, плюс ручные синонимы: `Wolves`, `Inter`, `Man City` и т.п.). Совпавшая пара сохраняет и маппинг команд.
- Результат хранится навсегда в SQLite: `af_team_map(fd_team_id, af_team_id, fd_name, af_name, method, updated_at)` и `af_fixture_map(fd_match_id, af_fixture_id, af_league_id, season, updated_at)`.

### Заметка изучения

- Дата: 2026-09-29
- URL: https://www.api-football.com/documentation-v3 , OpenAPI v3.9.3 (архив 02.11.2025)
- Версия: v3
- В код: `x-apisports-key`, обёртка `errors`/`response`, `/fixtures`, `/injuries`, `/sidelined`, `/fixtures/events`, `/transfers`, `/fixtures/lineups`, `/fixtures/players`, `/fixtures/statistics` (2026-09-30, пример ответа из спецификации — `data/samples/api_football/fixtures_statistics.json`), суточный бюджет, 429-бэкофф
- Лимиты: Free 100/сутки, минутный лимит — по заголовку `X-RateLimit-*`
- В доке нет: точного минутного лимита free, формата `errors` для ошибок тарифа (известен по отзывам), предсказанных составов

---

## Новости: GNews API (по ключу) и RSS спортивных изданий (без ключа)

Новости — **косвенный** фактор для AI-разбора и карточки матча. В расчёт 1X2 и предварительного счёта они не входят. В пакет фактов попадают только заголовок, источник, дата, тема (травма / дисквалификация / тренер / трансфер / состав / клуб и финансы / матч и форма / прочее) и до 300 символов описания; полный текст статей не хранится.

### Выбор источника (сравнение бесплатных тарифов, проверено 2026-09-29)

| Сервис | Бесплатно | Задержка | Ограничения | Решение |
|---|---|---|---|---|
| NewsAPI.org | 100 запросов/сутки | 24 ч | только dev-окружение, в production запрещено | не берём |
| **GNews** | 100 запросов/сутки, до 10 статей | 12 ч | некоммерческое использование; 1 запрос/с | **основной источник по ключу** (ВКР — некоммерческий проект) |
| NewsData.io | 200 кредитов/сутки | 12 ч | без полного текста, ключевое слово ≤ 100 символов | запасной вариант, не реализован |
| **RSS** BBC Sport, The Guardian, Sky Sports, ESPN | без ключа | нет | только последние 20–85 записей ленты, поиск — наш фильтр по названию команды | **fallback без ключа** |

### GNews — `GET https://gnews.io/api/v4/search`

- Ключ: заголовок `X-Api-Key` (в URL ключ не кладём, чтобы он не попал в логи httpx). Переменная `GNEWS_API_KEY`; пусто — 0 запросов.
- Параметры: `q` (≤ 200 символов, фразы в кавычках, `AND`/`OR`/`NOT`), `lang=en`, `max=10`, `in=title,description`, `from` (ISO 8601, 7 дней назад), `sortby=publishedAt`.
- Запрос по команде: `"<название>" AND (football OR soccer)`; название — из football-data.org без `FC`/`AFC`.
- Ответ: `totalArticles`, `articles[].{id,title,description,content,url,image,publishedAt,lang,source.{id,name,url,country}}`.
- Ошибки: 400 (плохой `q`/дата), 401 (ключ), 403 (суточная квота, сброс в 00:00 UTC), 429 (больше 1 запроса/с), 500/503. Тело: `{"errors": [...]}` или `{"errors": {"q": "..."}}`.
- Квота в приложении: не больше 80 запросов в сутки (`api_usage`, провайдер `gnews`), 1 запрос на команду, кэш 6 ч в `api_cache` (`gnews:<team>`). На 403 день закрывается.

### RSS (без ключа)

| Лента | URL | Записей (29.09.2026) |
|---|---|---|
| BBC Sport — Football | `https://feeds.bbci.co.uk/sport/football/rss.xml` | ~85 |
| The Guardian — Football | `https://www.theguardian.com/football/rss` | ~56 |
| Sky Sports — Football news | `https://www.skysports.com/rss/12040` | ~20 |
| ESPN — Soccer | `https://www.espn.com/espn/rss/soccer/news` | ~21 |

- Формат RSS 2.0: `channel/item/{title, description, link, guid, pubDate (RFC 822)}`; у Guardian `description` — HTML (теги убираем), есть `category`.
- Каждая лента качается не чаще раза в час (TTL 1 ч, `api_cache`, ключ `rss:<url>`), в кэш кладётся уже разобранный список (заголовок, ссылка, дата, 300 символов описания).
- Отбор: заголовок или описание содержит одно из названий команды целым словом (полное имя без `FC`, короткое имя из синонимов: `Man City`, `Spurs`, `Wolves`, `LASK`, `Salzburg`, `Betis`, `Sporting`…), свежесть ≤ 7 дней, до 5 заголовков на команду. Правило аббревиатур: из «LASK Linz» берётся и «LASK»; название города само по себе никогда не используется как синоним (иначе «Linz» ловил бы чужие новости).
- GNews-запрос объединяет до 3 синонимов через `OR`: `("lask linz" OR "lask") AND (football OR soccer)`.
- Устойчивый разбор RSS: BOM, кодировка из XML-декларации (с запасными cp1252 / latin-1), управляющие символы, «голые» `&` и HTML-сущности чинятся до разбора; если XML всё равно битый — записи достаются регулярным выражением; HTML-страница вместо ленты даёт понятную ошибку. Запрос шлёт `Accept: application/rss+xml, application/xml`. Лента ESPN проверена 2026-09-30: HTTP 200, валидный XML — прежняя ошибка «не удалось разобрать XML» не воспроизвелась, поэтому разбор усилен, а лента оставлена.
- Темы: травма, дисквалификация, тренер, трансфер, состав (lineup, squad, XI, starts, benched…), клуб и финансы (owner, stadium, sponsor, fine, revenue…), матч и форма (preview, win, defeat, draw, form, table…); только остальное — «прочее».
- Включение: `NEWS_RSS_ENABLED=true` (по умолчанию). При заданном `GNEWS_API_KEY` RSS используется только если GNews не вернул ничего или недоступен.

### Что уходит в LLM

Блок `news` пакета фактов: `{home: [{title, source, published, topic}], away: [...], provider, note}` с пометкой «заголовки не проверены и не меняют вероятности». Промпт запрещает выдавать заголовок за подтверждённый факт состава.

«Итог по новостям» — отдельный запрос: `{home: [{id: "h1", title, source, published, topic, summary}], away: [{id: "a1", …}]}`. Ответ: `summary` (2–4 предложения), по каждой команде `points[{text, headline}]` и `relevance`, `stale_note`. Проверка: каждый `headline` — существующий id своей команды, в тексте нет процентов, цитаты в кавычках совпадают с заголовками, не больше 5 предложений; иначе один повтор, затем ошибка без сохранения. Без ключа Ollama — «Итог недоступен: нет ключа Ollama».

### Заметка изучения

- Дата: 2026-09-29
- URL: https://docs.gnews.io/endpoints/search-endpoint , https://docs.gnews.io/authentication , https://docs.gnews.io/error-handling , https://gnews.io/pricing , https://newsapi.org/pricing , https://newsdata.io/documentation ; RSS-ленты проверены `curl` (HTTP 200, `text/xml`)
- Версия: GNews v4, RSS 2.0
- В код: `/api/v4/search`, `X-Api-Key`, ошибки 401/403/429, суточная квота; парсер RSS 2.0 на `xml.etree`
- Лимиты: GNews free 100/сутки, 1 запрос/с, задержка 12 ч; RSS — без лимита, берём не чаще 1 раза в час
- В доке нет: гарантий состава RSS-лент (могут меняться без уведомления), тематической разметки заголовков — тему определяем по ключевым словам
