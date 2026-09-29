# Page: Adaptive windows

Overrides MASTER for desktop window sizes. Football Prognoz is a **Flet desktop** app: each instance is a native OS window. Several windows can sit on one screen (tile, split, second instance). Layout follows **window width**, not a website viewport.

## Breakpoints

| Name | Window | Grid | Facts | Nav |
|------|--------|------|-------|-----|
| Compact | 800×640 min | 1 column | 1 column | labels + icons |
| Medium | ~1024×768 | 2 columns | 2 columns | labels + icons |
| Wide | 1440×900 default | 4 columns | 4 columns | NavigationRail |
| Desktop scene | 1920×1080 | two windows tiled | — | each window independent |

`page.window.min_width = 800`. No horizontal scroll. Match rows wrap crests + names; status + «Прогноз» stay visible or stack under the names on compact.

## Density (split_dense)

Flet shell follows **window width** via `page.on_resize` → `_render()` and `theme.window_width(page)`.

| Window | Nav | Split | League grid | Match list |
|--------|-----|-------|-------------|------------|
| ≥1280 | `NavigationRail` (Лиги / Календарь / Прогноз / Настройки) | yes | 4 cols, `max_extent` 280, `child_aspect_ratio` 2.4 | 2 compact cols |
| 1100–1279 | rail or `NavigationBar` | yes | 2 cols, extent 360 | 1 col |
| 980–1099 | `NavigationBar` | no | 2 cols, extent 360 | 1 col |
| <980 | `NavigationBar` | no | 1 col, extent 720 | 1 col |

Лиги (wide): left league grid, right fixtures of the selected league. Календарь (wide): left compact matches, right forecast. Прогноз / Настройки: one wide column. Card padding 10–12px, match rows 48–56px, disclaimer is a compact chip. Tokens stay OLED `#0F172A` / card `#1B2336` / accent `#22C55E`.

## Multi-window

- One process = one window. User may open a second window (second app instance) and put Календарь beside Прогноз.
- Design preview: `design-preview/index.html` scene `1920` shows two overlapping windows on one desktop.
- Do not fake a browser tab strip. Traffic-light window chrome only.

## Crests

Use official football-data.org marks (`competition.emblem`, `team.crest`). Bundled fallbacks live in `assets/crests/`. Never replace them with generic shield icons.
