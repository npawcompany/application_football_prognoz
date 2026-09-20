# Components

Assembly map for Flet. Layer names English; UI strings Russian.

| Component | Flet | Notes |
|-----------|------|--------|
| Window | `page.window` 1440×900, min 800×640 | OLED `#0F172A`, resizable |
| Nav | `NavigationBar` | Лиги / Календарь / Прогноз / Настройки · Phosphor-equivalent Material icons |
| LeagueCard | `ui/components/league_card.py` | Official emblem 48px, code badge, «Открыть календарь» |
| MatchCard | `ui/components/match_card.py` | Home/away crests 28px, UTC, status, «Прогноз» |
| ProbabilityBar | `ui/components/probability_bar.py` | Stacked 1 `#22C55E` / X `#F59E0B` / 2 `#EF4444` + text labels |
| Crest | `ui/components/crest.py` | API URL first, then `assets/crests/` |
| Disclaimer | `runtime.disclaimer` | Always visible on Календарь and Прогноз |
| Banner | `error_banner` / `info_banner` | `role` via semantics; empty states include next action |
| Settings fields | password+reveal for keys; plain for model/URL | Never show live secrets in mockups |

Interactive reference: [design-preview/index.html](../../design-preview/index.html). Figma file (partial, Starter quota): https://www.figma.com/design/ojnqGFKpOGtWp2pGTqQfB8/
