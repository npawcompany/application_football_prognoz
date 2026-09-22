# Components

Assembly map for Flet. Layer names English; UI strings Russian.

| Component | Flet | Notes |
|-----------|------|--------|
| Window | `page.window` 1440×900, min 800×640 | OLED `#0F172A`, resizable |
| Nav | `NavigationBar` | Лиги / Календарь / Прогноз / Настройки · Phosphor-equivalent Material icons |
| LeagueCard | `ui/components/league_card.py` | Official emblem 32px, code badge, «Календарь»; name ellipsis |
| MatchCard | `ui/components/match_card.py` | Compact 52–56px row, crests, UTC, status, «Прогноз»; name ellipsis |
| FilterBar | `ui/components/filter_bar.py` | Dense search + optional chips (accent when selected) |
| Splash | `ui/components/splash.py` | Boot: «Football Prognoz», «Загрузка данных…», ring, status |
| BusyOverlay | `runtime.show_preloader` | Dim 72% BG, ring 42px, e.g. «Считаем прогноз…» |
| ProbabilityBar | `ui/components/probability_bar.py` | Three 1/X/2 tiles + thin mix bar; favorite outlined |
| Scoreboard | `preliminary_score_card` | Large `H:A`, green chip, expected-goals meters |
| Crest | `ui/components/crest.py` | API URL first, then `assets/crests/` |
| Disclaimer | `runtime.disclaimer` | Always visible on Календарь and Прогноз |
| Banner | `error_banner` / `info_banner` | `role` via semantics; empty states include next action |
| Settings fields | password+reveal for keys; plain for model/URL/лиги | Mask secrets as `••••`; toggles from `settings_panel.py` |

Interactive reference: [design-preview/index.html](../../design-preview/index.html). Figma file (partial, Starter quota): https://www.figma.com/design/ojnqGFKpOGtWp2pGTqQfB8/
