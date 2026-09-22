"""Title row shared by the leagues and fixtures screens."""

from __future__ import annotations

import flet as ft

from football_prognoz.ui.theme import FG, MUTED, scaled


def section_header(
    title: str,
    subtitle: str | None = None,
    trailing: ft.Control | None = None,
    *,
    window_width: int = 1440,
) -> ft.Control:
    lines: list[ft.Control] = [
        ft.Row(
            [
                ft.Text(
                    title,
                    size=scaled(22, window_width),
                    weight=ft.FontWeight.BOLD,
                    color=FG,
                    max_lines=1,
                    overflow=ft.TextOverflow.ELLIPSIS,
                    expand=True,
                    tooltip=title,
                )
            ],
            expand=True,
        )
    ]
    if subtitle:
        lines.append(
            ft.Text(
                subtitle,
                size=scaled(12, window_width),
                color=MUTED,
                max_lines=1,
                overflow=ft.TextOverflow.ELLIPSIS,
                tooltip=subtitle,
            )
        )
    children: list[ft.Control] = [
        ft.Column(
            lines,
            spacing=2,
            expand=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    ]
    if trailing is not None:
        children.append(trailing)
    return ft.Row(
        children,
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
