"""Visual tokens for the Football Prognoz desktop shell.

Keep in sync with design-system/football-prognoz/MASTER.md and the Figma
Dark Pro Max collection on file ojnqGFKpOGtWp2pGTqQfB8.
"""

from __future__ import annotations

from typing import Any

import flet as ft

BG = "#0F172A"
CARD = "#1B2336"
SURFACE = "#272F42"
ACCENT = "#22C55E"
DRAW = "#F59E0B"
AWAY = "#EF4444"
FG = "#F8FAFC"
MUTED = "#94A3B8"
BORDER = "#475569"

WINDOW_DEFAULT = (1440, 900)
WINDOW_MIN = (800, 640)

BREAKPOINT_WIDE = 1280
BREAKPOINT_SPLIT = 1100
BREAKPOINT_MEDIUM = 980

LEAGUE_ASPECT_RATIO = 2.4
BODY_PADDING = 12
CARD_PADDING = 12


def glass_border() -> ft.Border:
    return ft.Border.all(1, ft.Colors.with_opacity(0.18, ft.Colors.WHITE))


def apply_page_fonts(page: ft.Page) -> None:
    fonts = getattr(page, "fonts", None)
    if isinstance(fonts, dict):
        return
    try:
        page.fonts = {
            "Fira Sans": "https://github.com/google/fonts/raw/main/ofl/firasans/FiraSans-Regular.ttf",
            "Fira Code": "https://github.com/google/fonts/raw/main/ofl/firacode/FiraCode%5Bwght%5D.ttf",
        }
    except Exception:  # noqa: BLE001 — optional web fonts; system UI is fine
        pass


def configure_window(page: ft.Page) -> None:
    apply_page_fonts(page)
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(color_scheme_seed=ACCENT, font_family="Fira Sans")
    page.padding = 0
    win = getattr(page, "window", None)
    if win is not None and hasattr(win, "width"):
        win.width = WINDOW_DEFAULT[0]
        win.height = WINDOW_DEFAULT[1]
        win.min_width = WINDOW_MIN[0]
        win.min_height = WINDOW_MIN[1]
        if hasattr(win, "bgcolor"):
            win.bgcolor = BG
        return
    page.window_width = WINDOW_DEFAULT[0]
    page.window_height = WINDOW_DEFAULT[1]
    page.window_min_width = WINDOW_MIN[0]
    page.window_min_height = WINDOW_MIN[1]


def window_width(page: ft.Page) -> int:
    """Live content width. Prefer page.width so OS resize actually reflows."""
    page_w = getattr(page, "width", None)
    if page_w:
        return int(page_w)
    win = getattr(page, "window", None)
    width = getattr(win, "width", None) if win is not None else None
    if width:
        return int(width)
    return int(getattr(page, "window_width", None) or WINDOW_DEFAULT[0])


def use_rail(width: int) -> bool:
    """Side NavigationRail at ≥1280; NavigationBar below that."""
    return width >= BREAKPOINT_WIDE


def use_split(width: int) -> bool:
    """Master–detail panes when the window is wide enough (~1100+)."""
    return width >= BREAKPOINT_SPLIT


def grid_extent(width: int) -> int:
    """League tile max width: 4 / 2 / 1 columns as the OS window shrinks."""
    if width >= BREAKPOINT_WIDE:
        return 280
    if width >= BREAKPOINT_MEDIUM:
        return 360
    return 720


def match_extent(width: int) -> int:
    """Compact fixture tiles: 2 columns on wide split, 1 column below."""
    if width >= BREAKPOINT_WIDE:
        return 280
    return 720


def league_runs(width: int) -> int:
    if width >= BREAKPOINT_WIDE:
        return 4
    if width >= BREAKPOINT_MEDIUM:
        return 2
    return 1


def match_runs(width: int) -> int:
    if width >= BREAKPOINT_WIDE:
        return 2
    return 1


def fact_runs(width: int) -> int:
    if width >= BREAKPOINT_WIDE:
        return 4
    if width >= BREAKPOINT_MEDIUM:
        return 2
    return 1


def card(content: ft.Control, **kwargs: Any) -> ft.Container:
    return ft.Container(
        content=content,
        bgcolor=CARD,
        border_radius=12,
        border=glass_border(),
        padding=CARD_PADDING,
        **kwargs,
    )
