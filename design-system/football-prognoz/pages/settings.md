# Page: Settings

Overrides MASTER for local `.env` keys (nav index 3).

## Layout
One wide column in the shell (no master–detail split). Form + helper aside may wrap; aside width ~360px from the medium breakpoint up.

## Components
- SDS `Input Field` (password + reveal) × 2 keys; plain model, URL, favorite leagues
- SDS switches × 3
- SDS `Button` primary: Сохранить (`--color-accent`)
- SDS `Button` secondary/outline: Проверить football-data.org, Очистить кэш
- Success/error banners

## Fields
1. FOOTBALL_DATA_API_KEY · обязательный
2. OPENAI_API_KEY · необязательный
3. OPENAI_MODEL
4. OPENAI_BASE_URL

## Extra controls
5. **Любимые лиги** — hint `PL,PD,SA`
6. Switch «Ждать обновление всех лиг при старте»
7. Switch «Показывать AI-пояснение»
8. Switch «Компактный календарь»

Buttons (wrap): **Сохранить**, **Проверить football-data.org**, **Очистить кэш**.

Aside: «Локальное хранение ключей»; DB path `data/cache/prognoz.db`; «football-data.org · лимит 10 запросов/мин»; «OpenAI опционален для пояснения, не для выбора исхода». «Это не совет ставить деньги.»

Never show live secret values in mockups — use masked `••••••••` placeholders (bullets).
