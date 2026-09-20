"""Single-line team/league name that ellipsizes instead of overflowing."""

from __future__ import annotations

import flet as ft

from football_prognoz.ui.theme import FG


def team_label(
    text: str,
    *,
    size: int = 13,
    align: ft.TextAlign = ft.TextAlign.LEFT,
    weight: ft.FontWeight = ft.FontWeight.W_600,
    color: str = FG,
) -> ft.Text:
    return ft.Text(
        text,
        size=size,
        weight=weight,
        color=color,
        expand=True,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
        text_align=align,
        tooltip=text,
    )
