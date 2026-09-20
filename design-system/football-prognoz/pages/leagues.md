# Page: Leagues

Overrides MASTER for the league picker (nav index 0).

## Layout
Desktop window 1440×900, dark OLED glass (`#0F172A`). App bar + body. ≥1280: `NavigationRail`; &lt;980: bottom nav (4 items). Wide split: left league grid (4 cols), right fixtures of the selected league.

## Components (library)
- macOS 26 `Window` + `Window Controls/Standard` + `Window Title/Standard`
- SDS `Card Grid Icon` (league tiles)
- SDS `Icon Button` (refresh)
- SDS `Navigation Button List` (Лиги / Календарь / Прогноз / Настройки)
- Phosphor: soccer-ball (filled on selected), calendar, chart-bar, gear

## Content
Title **Лиги**. Subtitle: «Бесплатный план football-data.org: 12 соревнований.»
12 cards with **official emblems** (`competition.emblem` from football-data.org, fallback `assets/crests/leagues/{code}.png`): Premier League (PL), Primera Division (PD), Serie A (SA), Bundesliga (BL1), Ligue 1 (FL1), Primeira Liga (PPL), Eredivisie (DED), Championship (ELC), Brasileirão (BSA), Champions League (CL), World Cup (WC), European Championship (EC). Leading crest, name, code. Never generic shields.

## States
Loading: progress ring. Empty: muted banner «Нет лиг. Проверьте ключ API в Настройках.» Error: destructive banner.

## Density
`--space` 10–12px between cards, 12px page padding. Card padding 10–12px, radius 12, fill `--color-card`, 1px white ~18% opacity. `max_extent` 280 / 360 / 720, `child_aspect_ratio` ~2.4 (not 420 / 1.85).
