"""Country / region flag + name. Standard label wherever an area is shown.

Every area gets a mark (see domain.country.resolve_flag): the football-data.org
`area.flag` URL when known (Flutter's image cache keeps it for the session) with the
bundled flag-icons SVG as the offline/error fallback, a globe for World and
continents, a flag outline for unknown names.
"""

from __future__ import annotations

from functools import lru_cache

import flet as ft

from football_prognoz.config import ASSETS_DIR
from football_prognoz.domain.country import (
    FLAG_ICON_GLOBE,
    FlagSource,
    flag_code,
    resolve_flag,
)
from football_prognoz.ui.theme import MUTED, SURFACE

FLAGS_DIR = ASSETS_DIR / "flags"
FLAG_ASPECT = 4 / 3


@lru_cache(maxsize=512)
def flag_asset(code: str | None) -> str | None:
    """Bundled flag URL (cached: the UI thread renders flags on every repaint)."""
    if not code:
        return None
    path = FLAGS_DIR / f"{code}.svg"
    if path.is_file():
        return f"/flags/{code}.svg"
    return None


def _box(content: ft.Control | None, width: int, height: int, tooltip: str | None) -> ft.Control:
    return ft.Container(
        content=content,
        width=width,
        height=height,
        border_radius=3,
        clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        alignment=ft.Alignment.CENTER,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.18, ft.Colors.WHITE)),
        tooltip=tooltip,
    )


def _icon(source: FlagSource, width: int, height: int) -> ft.Control:
    icon = ft.Icons.PUBLIC if source.icon == FLAG_ICON_GLOBE else ft.Icons.OUTLINED_FLAG
    return ft.Container(
        content=ft.Icon(icon, size=max(10, height - 2), color=MUTED),
        width=width,
        height=height,
        bgcolor=SURFACE,
        alignment=ft.Alignment.CENTER,
    )


def flag_mark(
    name: str | None,
    *,
    size: int = 16,
    iso3: str | None = None,
    flag_url: str | None = None,
) -> ft.Control | None:
    """Fixed 4:3 flag box; None only when there is nothing to name."""
    source = resolve_flag(name, iso3=iso3, flag_url=flag_url)
    if source.empty:
        return None
    width = size
    height = max(10, round(size / FLAG_ASPECT))
    local = flag_asset(source.asset)
    fallback: ft.Control
    if local is not None:
        fallback = ft.Image(src=local, width=width, height=height, fit=ft.BoxFit.COVER)
    else:
        fallback = _icon(source, width, height)
    mark: ft.Control = fallback
    if source.url:
        mark = ft.Image(
            src=source.url,
            width=width,
            height=height,
            fit=ft.BoxFit.COVER,
            error_content=fallback,
        )
    return _box(mark, width, height, name)


def flag_image(
    name: str | None,
    *,
    size: int = 14,
    iso3: str | None = None,
    flag_url: str | None = None,
) -> ft.Control | None:
    """Backwards-compatible name: same as flag_mark."""
    return flag_mark(name, size=size, iso3=iso3, flag_url=flag_url)


def country_label(
    name: str | None,
    *,
    size: int = 12,
    color: str = MUTED,
    iso3: str | None = None,
    flag_url: str | None = None,
    expand: bool = False,
) -> ft.Control:
    if not name:
        return ft.Container()
    mark = flag_mark(name, size=max(14, size + 6), iso3=iso3, flag_url=flag_url)
    text = ft.Text(
        name,
        size=size,
        color=color,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
        tooltip=name,
        expand=expand,
    )
    children: list[ft.Control] = [text]
    if mark is not None:
        children.insert(0, mark)
    return ft.Row(
        children,
        spacing=6,
        tight=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


__all__ = ["country_label", "flag_asset", "flag_code", "flag_image", "flag_mark"]
