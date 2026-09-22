"""Country flag + name. Standard label wherever a country is shown."""

from __future__ import annotations

import flet as ft

from football_prognoz.config import ROOT_DIR
from football_prognoz.domain.country import flag_code
from football_prognoz.ui.theme import MUTED

FLAGS_DIR = ROOT_DIR / "assets" / "flags"


def flag_asset(code: str | None) -> str | None:
    if not code:
        return None
    path = FLAGS_DIR / f"{code}.svg"
    if path.is_file():
        return f"/flags/{code}.svg"
    return None


def flag_image(
    name: str | None,
    *,
    size: int = 14,
    iso3: str | None = None,
) -> ft.Control | None:
    code = flag_code(name, iso3=iso3)
    src = flag_asset(code)
    if src is None:
        return None
    return ft.Image(
        src=src,
        width=size,
        height=max(10, round(size * 0.75)),
        fit=ft.BoxFit.CONTAIN,
        tooltip=name,
    )


def country_label(
    name: str | None,
    *,
    size: int = 12,
    color: str = MUTED,
    iso3: str | None = None,
    expand: bool = False,
) -> ft.Control:
    if not name:
        return ft.Container()
    mark = flag_image(name, size=max(12, size + 2), iso3=iso3)
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
