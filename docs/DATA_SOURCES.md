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

- `GET /v4/competitions` — список лиг. В ответе есть `area.name` / `area.code`; в UI страна лиги берётся из локальной карты free-кодов (`PL`→England и т.д.), флаг из бандла.
- `GET /v4/competitions/{code}/matches?season=YYYY&status=&dateFrom=&dateTo=`
- `GET /v4/competitions/{code}/standings`
- `GET /v4/competitions/{code}/teams` — клубы/сборные сезона (по умолчанию текущий; `?season=YYYY` для прошлых). `{code}` — код или id соревнования.
- `GET /v4/teams/{id}` — карточка клуба: `coach`, `squad`, `venue`, `address`, `area`.
- `GET /v4/matches/{id}` — деталь матча: `venue`, `homeTeam.lineup` / `bench` (основа и запас). TTL 6 ч.

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

### Флаги стран (бандл, не API)

- Набор: [flag-icons](https://github.com/lipis/flag-icons) v7.5.0, MIT, файлы `flags/4x3/*.svg`.
- Скрипт: `python scripts/sync_flags.py` → `assets/flags/{code}.svg`.
- Коды: ISO 3166-1 alpha-2; сборные UK — `gb-eng`, `gb-sct`, `gb-wls`, `gb-nir`.
- UI читает только бандл. Живой HTTP флагов из приложения запрещён.

### CDN гербов (официальный, тот же хост, что в `crest` / `emblem`)

- База: `https://crests.football-data.org/`
- Клуб/сборная: `https://crests.football-data.org/{id}.png`
- Соревнование: сначала `https://crests.football-data.org/{code}.png` (например `PL.png`); если CDN 404 — тот же хост `{competitionId}.png` (как в поле `emblem` v4).
- Живой HTTP только из `scripts/sync_crests.py` (не из UI). Лимит API 10 req/min. Если оба URL 404 (типично BSA) → `manifest.missing`, без Wikipedia и без букмекеров.
- В старых примерах доки ещё встречается `crestURI`; в JSON v4 поле называется `crest` (как уже маппим в матчах).

### Коды free-тира

`PL`, `PD`, `SA`, `BL1`, `FL1`, `DED`, `PPL`, `ELC`, `BSA`, `CL`, `WC`, `EC`.

### Ошибки

- `403` — нет/неверный ключ или лига не в тарифе.
- `429` — превышен лимит; клиент обязан подождать.

### Заметка изучения

- Дата: 2026-09-20
- URL: https://www.football-data.org/documentation/api
- Версия: v4
- В код: `X-Auth-Token`, matches + standings + teams + `GET /teams/{id}` (coach/squad), TTL-кэш, 10 req/min, CDN crests
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

## OpenAI / Ollama (только текст)

- OpenAI Chat Completions: `POST {OPENAI_BASE_URL}/chat/completions`
- По умолчанию `OPENAI_BASE_URL=https://api.openai.com/v1`, модель `gpt-4o-mini`
- Для Ollama: `OPENAI_BASE_URL=http://127.0.0.1:11434/v1` и локальная модель
- Вход explainer: JSON фактов + вероятности. Запрещено просить модель «угадать счёт» без фактов.

## API-Football (не в v1)

Отложено. Если подключать: сначала дополнить этот файл (лимит 100 req/day на free, `/fixtures`, `/predictions`), потом клиент.
