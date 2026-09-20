# Правила изучения документации

Цель — не «прочитать всё», а закрыть конкретный этап кода официальным источником, без выдуманных полей API и виджетов Flet.

## Общие правила

1. Источник истины — официальные доки текущей мажорной версии. Блоги и Stack Overflow — не первый шаг.
2. Перед кодом по библиотеке: прочитать канонический URL, выписать сюда или в [DATA_SOURCES.md](DATA_SOURCES.md) 5–10 фактов (методы, лимиты, обязательные заголовки).
3. Не изобретать поля JSON. Если поля нет в доке football-data.org v4 — его нет.
4. После изучения — маленький вертикальный срез (один запрос + один виджет), не абстрактный «фреймворк на будущее».
5. Версии библиотек пинить; при апгрейде перечитывать changelog.
6. Живые запросы при изучении идут через кэш или `scripts/`, не из UI-цикла, чтобы не сжечь 10 req/min.

## Порядок изучения по этапам

### Этап 1 — Flet

- [Getting started](https://flet.dev/docs/getting-started/)
- Controls, Navigation
- [Publish Windows](https://flet.dev/docs/publish/windows/)
- [Publish macOS](https://flet.dev/docs/publish/macos/)

Нужно уметь: страница, список, форма, тема, неблокирующая загрузка.

### Этап 2 — football-data.org

- [API Reference](https://www.football-data.org/documentation/api)
- [Quickstart](https://www.football-data.org/documentation/quickstart)
- [Coverage](https://www.football-data.org/coverage)
- [Pricing](https://www.football-data.org/pricing)

Нужно уметь: заголовок `X-Auth-Token`, `/v4/competitions`, `/matches?season=&status=&dateFrom=`, коды лиг `PL` / `PD` / `SA` / `BL1` / `FL1`.

### Этап 2 — CSV

- [football-data.co.uk data](https://www.football-data.co.uk/data.php)
- Notes.txt: колонки `FTHG`, `FTAG`, `FTR`, `Hx`, `Ax`.

### Этап 3 — модель

- scikit-learn User Guide только на выбранный estimator.
- Poisson / Dixon–Coles — по формуле (или statsmodels), не по случайным ноутбукам без источника.

### Этап 3 — LLM

- Официальные docs OpenAI Chat Completions **или** Ollama generate.
- Ключи и биллинг — из их документации.
- Промпт принимает только факты + вероятности.

### Этап 5 — сборка

- Только страницы `flet build` для целевой ОС.
- Сборку Windows не делать на Linux; сборку macOS не делать вне macOS.

## Шаблон заметки после чтения

- Дата и URL
- Версия API / библиотеки
- Что взяли в код (2–5 пунктов)
- Лимиты и ошибки
- Чего в доке нет (чтобы не фантазировать)

## Запрещено

- Копировать чужие API-ключи и чужие полные дампы.
- Парсить сайты вместо официального API, если API уже выбран.
- Учить PySide6 / Kivy / Streamlit «на всякий случай» — стек зафиксирован как Flet.
