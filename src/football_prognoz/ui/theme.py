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


def type_scale(width: int) -> float:
    """Larger window → larger type. 800px ≈ 0.90, 1440px ≈ 1.04, 1600px ≈ 1.08."""
    clamped = min(max(int(width), WINDOW_MIN[0]), 1600)
    t = (clamped - WINDOW_MIN[0]) / (1600 - WINDOW_MIN[0])
    return 0.90 + t * 0.18


def scaled(size: int, width: int) -> int:
    return max(10, round(size * type_scale(width)))


def configure_window(page: ft.Page) -> None:
    page.bgcolor = BG
    page.theme_mode = ft.ThemeMode.DARK
    page.theme = ft.Theme(
        color_scheme_seed=ACCENT,
        color_scheme=ft.ColorScheme(
            primary=ACCENT,
            on_primary="#0F172A",
            surface=BG,
            on_surface=FG,
            surface_container=CARD,
            surface_container_low=CARD,
            surface_container_lowest=BG,
            surface_container_high=SURFACE,
            surface_container_highest=SURFACE,
            secondary=DRAW,
            error=AWAY,
        ),
    )
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


def use_stacked_match(width: int) -> bool:
    """Stack match-card rows when the window or a split pane is below medium."""
    if width < BREAKPOINT_MEDIUM:
        return True
    if use_split(width) and width // 2 < BREAKPOINT_MEDIUM:
        return True
    return False


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


def fact_columns(width: int) -> int:
    """Equal-width context tiles. A split forecast pane is often <980px but still fits two."""
    if width >= BREAKPOINT_WIDE:
        return 4
    if width >= 400:
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


RAIL_WIDTH = 89  # NavigationRail min_width 88 + divider
CARD_MIN_WIDTH = 330  # a league tile narrower than this truncates the names


def content_width(window: int) -> int:
    """Width of the page body next to the rail (both paddings removed)."""
    rail = RAIL_WIDTH if use_rail(window) else 0
    return max(320, window - rail - 2 * BODY_PADDING)


def calendar_width(window: int) -> int:
    """Calendar column next to the forecast: about a third, 380–560 px."""
    return int(min(560, max(380, content_width(window) * 0.34)))


def leagues_pane_width(window: int, *, split: bool) -> int:
    """The leagues list takes 3/5 of the body in the split view, all of it otherwise."""
    body = content_width(window)
    return int(body * 3 / 5) - 9 if split else body


def grid_columns(pane_width: int, *, min_width: int = CARD_MIN_WIDTH, most: int = 4) -> int:
    """Columns that fill the pane with tiles no narrower than `min_width`."""
    return max(1, min(most, pane_width // min_width))


def column_span(columns: int) -> int:
    """ResponsiveRow span (of 12) for `columns` equal tiles."""
    return {1: 12, 2: 6, 3: 4, 4: 3}.get(columns, 12)
