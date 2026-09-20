# Page: Settings

Overrides MASTER for local `.env` keys (nav index 3).

## Layout
One wide column in the shell (no master–detail split). Form + helper aside may wrap; aside width ~360px from the medium breakpoint up.

## Components
- SDS `Input Field` (password + reveal) × 4
- SDS `Button` primary: Сохранить (`--color-accent`)
- SDS `Button` secondary/outline: Проверить football-data.org
- Success/error banners

## Fields
1. FOOTBALL_DATA_API_KEY (required)
2. OPENAI_API_KEY (optional)
3. OPENAI_MODEL
4. OPENAI_BASE_URL

Helper: «Ключи хранятся только в локальном `.env` и не попадают в git.»

Never show live secret values in mockups — use masked `••••••••` placeholders.
