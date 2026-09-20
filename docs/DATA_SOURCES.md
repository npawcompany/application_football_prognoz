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

- `GET /v4/competitions` — список лиг.
- `GET /v4/competitions/{code}/matches?season=YYYY&status=&dateFrom=&dateTo=`
- `GET /v4/competitions/{code}/standings`

### Поля матча (v4), которые маппим в domain

`id`, `utcDate`, `status`, `matchday`, `homeTeam.id`, `homeTeam.name`, `awayTeam.id`, `awayTeam.name`, `score.fullTime.home`, `score.fullTime.away`, `score.winner`.

Не выдумывать поля вроде `xG` или `injuries` — в free v4 их нет.

### Коды free-тира

`PL`, `PD`, `SA`, `BL1`, `FL1`, `DED`, `PPL`, `ELC`, `BSA`, `CL`, `WC`, `EC`.

### Ошибки

- `403` — нет/неверный ключ или лига не в тарифе.
- `429` — превышен лимит; клиент обязан подождать.

### Заметка изучения

- Дата: 2026-09-20
- URL: https://www.football-data.org/documentation/api
- Версия: v4
- В код: `X-Auth-Token`, matches + standings, TTL-кэш, 10 req/min
- Лимиты: 10/мин на free
- В доке нет: xG, составы на free без add-on

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
