# Page: Match

Overrides MASTER for the 1X2 forecast (nav index 2).

## Layout
Title **Прогноз матча**. Match label with official home/away crests (Fira Sans SemiBold 22). Date in muted Fira Code. Wide Календарь split: this page is the right pane (`embedded`, no back). Forecast tab: one wide column. Compact disclaimer chip always visible.

Reading order: disclaimer → teams → **исход 1/X/2** → **табло счёта** → контекст → состав → AI. Numbers before prose.

## Probability
Card **Исход матча**. Three equal tiles (1 / X / 2) with Fira Code percents. Favorite tile gets a 1px status border and the caption **Фаворит**. Home/away tiles show venue icons (`HOME` / `DIRECTIONS_BUS`). Under the tiles: a thin segmented mix bar (not a fused 44px bar — labels live on the tiles so color is not the only encoding).
- 1 (home): `--color-accent` `#22C55E`
- X (draw): `--color-draw` `#F59E0B`
- 2 (away): `--color-destructive` `#EF4444`

## Preliminary score
Card **Предварительный счёт** as a scoreboard, not a paragraph.
- Club names + official crests + venue icons above the large Fira Code `H:A`.
- Predicted winner name is **underlined** (accent). Draw → nobody underlined.
- Green chip `{n}% · самый вероятный`.
- Right: **Ожидаемые голы** — two meters (home accent, away destructive) plus `{λh} : {λa} · по голам за 5 матчей`.
- No λ letter, no Elo, no “без травм” essay in the UI.
- Below 980px: stack board above meters (`compact`).

## Facts card (SDS Stats Card × grid)
Section label **Контекст матча** — these blocks explain the card, they are not a second classifier.
Equal height tiles in a row (`height` scaled, 4/2/1 columns). Form labels use the same home/away icons.
- Форма: W/D/L pills (`#22C55E` / `#F59E0B` / `#EF4444`), dark digit `#0F172A`.
- Elo: `home · away` in Fira Code and signed delta.
- H2H summary string.
- Таблица: positions in Fira Code and cache size.

## Squad
Card **Состав и тренер** from `GET /v4/teams/{id}` (cached 24h). Coach first, then players by position. Status line = role + nationality + age. No invented injuries.

## AI block
Heading **AI-пояснение**. Body text or muted banner if no OpenAI key: numbers already computed locally.

Disclaimer always visible.
