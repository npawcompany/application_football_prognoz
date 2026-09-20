# Page: Match

Overrides MASTER for the 1X2 forecast (nav index 2).

## Layout
Title **Прогноз матча**. Match label with official home/away crests (Fira Sans SemiBold 22). Date in muted Fira Code. Wide Календарь split: this page is the right pane (`embedded`, no back). Forecast tab: one wide column. Compact disclaimer chip always visible.

## Probability (chart = stacked 100% bar)
Categories 1 / X / 2. Direct labels + percent. Do not encode by color alone.
- 1 (home): `--color-accent` `#22C55E`
- X (draw): `--color-draw` `#F59E0B`
- 2 (away): `--color-destructive` `#EF4444`
Accessible fallback: three numbered tiles under the bar.

## Preliminary score
Card **Предварительный счёт**. Large `H:A` from Poisson mode of last-5 goal averages (K1/K2). Under it: cell probability and λ. Not ceil/floor. Not Elo.

## Facts card (SDS Stats Card × grid)
Форма хозяев / гостей · Elo · H2H · места в таблице · матчей в кэше.

## AI block
Heading **AI-пояснение**. Body text or muted banner if no OpenAI key: numbers already computed locally.

Disclaimer always visible.
