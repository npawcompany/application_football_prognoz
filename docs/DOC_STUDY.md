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

## Заметка изучения — Flet 0.80 (2026-09-20)

- **Дата:** 2026-09-20
- **Версия:** проект `flet>=0.27.0,<0.81` → фактически линейка **0.80.x** (PyPI: 0.80.0–0.80.5). Официальный блог: 0.80.0 = **Flet 1.0 Beta**; API заявлен как ~99% стабильный до 1.0. Живой сайт `flet.dev/docs` на дату чтения уже отражает 1.0 (на PyPI текущий пакет — `1.0.0`); ниже только то, что есть на канонических страницах, без переноса фактов из 0.85+.
- **URL (официальные, прочитаны):**
  - https://flet.dev/docs/ — Introduction (корневой `/docs/getting-started/` **404**)
  - https://flet.dev/docs/getting-started/create-flet-app/
  - https://flet.dev/docs/getting-started/running-app/
  - https://flet.dev/docs/controls/page/
  - https://flet.dev/docs/controls/basepage/
  - https://flet.dev/docs/cookbook/async-apps/
  - https://flet.dev/docs/cookbook/auto-update/
  - https://flet.dev/docs/controls/text/
  - https://flet.dev/docs/types/textoverflow/
  - https://flet.dev/docs/controls/textfield/
  - https://flet.dev/docs/controls/progressring/
  - https://flet.dev/docs/controls/alertdialog/
  - https://flet.dev/docs/controls/dialogcontrol/
  - https://flet.dev/docs/controls/container/ (пример `page.overlay.append`)
  - https://flet.dev/docs/types/border/
  - https://flet.dev/docs/publish/web/dynamic-website/ (sync vs async handlers)
  - https://flet.dev/docs/updates/breaking-changes/
  - https://flet.dev/blog/flet-1-0-beta/

### Что берём в код (факты)

1. **Точка входа:** `import flet as ft`, `def main(page: ft.Page): …`, `ft.run(main)`. `page` — контейнер окна/вкладки; `page.add()` добавляет контролы. События: `e.control` — источник; у `TextField` новое значение — `e.control.value`. Авто-update: после возврата из handler / `main()` Flet сам вызывает `page.update()` (если handler не вызвал `.update()` явно).
2. **`page.overlay` (прелоадер поверх UI):** на `BasePage` свойство `overlay: list[BaseControl]` — «list of overlay controls rendered above page content». В официальном примере Container: `page.overlay.append(container := ft.Container(left=…, top=…, …))`. Готового рецепта «preloader» в доке нет: спиннер — это `ProgressRing` (или `Container` вокруг него), положенный в `overlay` и показанный/скрытый через `visible` / `append`+`remove`. Позиционирование в примере — `left`/`top` у `Container`, не «центрировать на весь экран» из коробки.
3. **`page.run_task` vs поток UI:** приложение на **одном** asyncio event loop; этот же loop шлёт UI. Правило доки: **Never block the event loop** — `time.sleep()` / синхронный `requests.get()` морозят UI на всех платформах (не только web). `run_task(handler, *args, **kwargs) -> Future`: запускает **coroutine function** (не уже вызванную корутину — иначе `TypeError`) как `Task` на loop страницы; держит ссылку на task и гоняет исключения через обработку ошибок Flet. `did_mount`/`will_unmount` синхронные — фон стартуют через `run_task`, не `await`. Если task стартовали из lambda/handler, handler уже закончился: авто-update **не** включает правки из task → внутри task нужен явный `.update()`. `await` сам по себе авто-update не шлёт.
4. **Не путать с `run_thread`:** в Page API есть и `run_thread` (callable в executor страницы). Cookbook «Async apps»: для результата блокирующего вызова брать **`await asyncio.to_thread(fn, *args)`**; `page.run_thread` — fire-and-forget и на static web/Pyodide выполняется **inline** (потоков нет). Для I/O и прелоадера берём **async handler + `run_task` + `asyncio.to_thread` при необходимости**, не `run_thread` как основной путь.
5. **`Text` overflow / `max_lines`:** `overflow: TextOverflow = TextOverflow.CLIP` (дефолт). `TextOverflow.ELLIPSIS` — «Use an ellipsis to indicate that the text has overflowed». `max_lines: int | None = None` — обрезка по `overflow`; при `max_lines=1` текст не wrapping. Пример в доке: длинная строка с `overflow=ft.TextOverflow.ELLIPSIS`; showcase — `max_lines=1` + `overflow=…`. Также `FADE`, `VISIBLE`, `CLIP`.
6. **`TextField.on_change` (фильтры):** `on_change: ControlEventHandler[TextField] | None = None` — «Called when the typed input for the TextField has changed». Пример «Handling change events»: `message.value = e.control.value`. Getting started прямо указывает `on_change` + `e.control.value`. `input_filter` — as-you-type filtering; **и `on_change`, и input filters не применяются**, если значение меняют программно. `on_submit` — Enter в фокусе (не замена `on_change`).
7. **`ProgressRing`:** круговой индикатор. `value: Number | None = None` — `None` = **indeterminate** (анимация без доли прогресса); `0.0`…`1.0` (clamp) = determinate. Пример «Determinate and Indeterminate»: `async def main`, цикл `determinate_ring.value = i * 0.01`, `await asyncio.sleep(0.1)`, `page.update()`. Индетерминированный: `ft.ProgressRing()` без `value`. Размер в примере: `width=16, height=16, stroke_width=2`. Тема: `Theme.progress_indicator_theme`.
8. **`AlertDialog` / modal:** `modal: bool = False` — можно ли закрыть кликом снаружи. Показ: `page.show_dialog(dialog)` (`DialogControl`, **must not yet be open**, иначе `RuntimeError`). Закрытие: `page.pop_dialog()` — снимает верхний открытый диалог со стека. Нужен хотя бы один из `title` / `content` / `actions` (`ValueError` иначе). `content` типично `Column` с `Text`. `scrollable=True` — title+content в scroll, кнопки остаются. `DialogControl.open` / `on_dismiss` тоже есть; канон 0.80-доки — `show_dialog`/`pop_dialog`, не старый `page.dialog = …`.
9. **Границы:** актуальные примеры — **`ft.Border.all(width, color)`** (classmethod), не модуль `ft.border`. `Padding.all`, `BorderRadius.all` в тех же примерах. Index breaking-changes: удаление «Deprecated spacing and border helper functions» отнесено к **Flet 0.85.0** (вне пина `<0.81`); на страницах 0.80/1.0-доки `ft.border.all` **не описан**.
10. **Запуск:** `flet run` / `uv run flet run` — desktop + hot reload; `flet run --web` — браузер. Entry в коде — `ft.run(main)`.

### Лимиты / deprecations / ошибки (только из доки)

- **Модель 0.80 / 1.0 Beta:** sync-handler больше не «просто в thread pool» как в 0.28. Blocking на loop = замёрзший UI. Cookbook ссылается на «Migrating from Flet 0.28 to 1.0»; **прямой URL гайда с `/docs/updates/` не удалось открыть** (угаданные slugs — 404).
- **`show_dialog`:** `RuntimeError`, если диалог уже open. `pop_dialog()` → `DialogControl | None`.
- **`AlertDialog`:** `ValueError`, если нет title/content/actions.
- **`run_task`:** `TypeError`, если передать уже вызванную корутину.
- **Авто-update:** не покрывает середину длинного handler и не покрывает работу внутри `run_task` после завершения handler. Mid-progress: `yield` в generator-handler **или** явный `.update()`; chunk должен быть коротким, иначе UI всё равно стопорится между yield.
- **Static website / Pyodide:** потоков нет; `run_thread` не спасает. Наш десктоп (Windows/macOS) — не этот случай.
- **InputBorder / loose border properties** на Dropdown и т.п. помечены deprecated since **1.0.0**, removal **1.3.0** — это не `ft.Border.all`.
- **0.85.0+** (вне нашего пина): removed spacing/border helpers; не утверждаем, что `ft.border.all` уже удалён в 0.80.x.

### Чего в доке нет (не выдумывать)

- Страницы **https://flet.dev/docs/getting-started/** — 404; старт — `create-flet-app` и `running-app`.
- **Готового API «overlay preloader»** (нет метода `show_preloader`, нет примера ProgressRing именно в `overlay`). Есть только `overlay` как список + отдельно ProgressRing.
- **Debounce/throttle** для `TextField.on_change` (фильтр списка матчей) — не описан; частота событий не нормирована.
- Как **центрировать** спиннер в overlay на весь экран (пример overlay — `left`/`top` у Container).
- Нужен ли `page.update()` сразу после `overlay.append` — в Container-примере `append` без отдельного `update` до `page.add`; для task-прелоадера дока требует явный `update()` внутри task.
- **`page.open(...)`** встречается в гайде расширений; канон диалогов на BasePage — `show_dialog` / `pop_dialog`. Не смешивать, пока не прочитан DialogControl usage целиком.
- Пошаговый текст **Migrating from 0.28 to 1.0** (ссылка есть, страница по угаданным URL не отдалась).
- Соответствие **каждого** символа live-доки 1.0.0 пину 0.80.5: changelog 0.80.5 (LaTeX Markdown, web leak) не про эти контролы.
- LangChain, `page.run_thread` как основной async-путь, поля JSON football-data — вне этой заметки.
