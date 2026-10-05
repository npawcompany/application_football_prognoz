---
name: vkr-oformlenie
description: >
  Оформление пояснительной записки и отчёта Football Prognoz по методичке ТГУ 2024,
  ГОСТ Р 59194-2020, схемам draw.io и скриншотам Flet. Use when editing the diploma
  or practice report, vkr.docx, otchet-preddiplomnaya.docx, manuscript markdown,
  MU_po_VKR_2024, functional requirements, or figures under docs/vkr. Do not use
  for application feature code.
---

# Оформление отчёта ВКР

## When

Текст, таблицы, рисунки и `.docx` пояснительной записки или отчёта по преддипломной практике. План и готовый порядок правок: `docs/vkr/PLAN-PRAVKI.md`.

## Source of truth

1. `docs/vkr/sources/MU_po_VKR_2024.pdf` — методические указания ТГУ, Тольятти, 2024.
2. `docs/vkr/oformlenie-tgu.md` — разбор той же методички. При расхождении открыть PDF.
3. `docs/VKR.md` — каркас глав. Требования остаются в § 1.3, технологии — в § 2.1.
4. Факты только из кода и `docs/FORECAST.md`, `docs/ARCHITECTURE.md`, `docs/DATA_SOURCES.md`, `docs/BUILD.md`. Числа, которых нет в прогоне, не добавлять.

Не подменять методичку справочником Мильчина и навыками `russian-editorial-review` / `ru-text`.

## Steps

1. Прочитать `docs/vkr/PLAN-PRAVKI.md` и скриншоты `docs/vkr/sources/otzyv/`.
2. Править рукопись в `docs/vkr/manuscript/`, затем схемы `.drawio`.
3. Экспорт схем только официальным клиентом: `bash scripts/export_drawio.sh`. Не использовать `scripts/render_vkr_schemes.py` как итоговый PNG.
4. Новые снимки экранов: `scripts/capture_vkr_screens.py`, файлы в `docs/vkr/manuscript/figures/screens/`.
5. Новый документ собирать существующим сборщиком `scripts/build_vkr_docx.mjs` (поля 30/15/20/20 мм, Times New Roman 14, интервал 1,5, маркер «–», подписи «Таблица N – …» и «Рисунок N – …»). Выход новой версии: `docs/vkr/otchet-preddiplomnaya.docx`. Прежний `docs/vkr/vkr.docx` не удалять, пока новый файл не проверен.

## Guardrails

- Требование по ГОСТ Р 59194-2020 описывает функцию или характеристику программного обеспечения, а не действие пользователя. Одно свойство на одно требование, идентификатор не меняется, формулировка проверяемая. Обязательность: «должен» и формы этого слова. Отрицательные и непроверяемые обороты не использовать.
- Сравнение в таблице — объекты одной категории (программные продукты). Способ программирования («своя сборка на Python») в ту же таблицу не ставить.
- Безличные формулировки. Личные местоимения «он», «они» не использовать. Один термин на одно понятие. Сокращения «т. д.», «т. п.», «т. е.» не вводить.
- Языковая модель не выбирает исход матча. Продукт не является советом по ставкам.

## Related skills

Загрузить вместе с `football-prognoz`. Не загружать одновременно `russian-editorial-review`.
