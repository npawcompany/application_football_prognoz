"""Title row shared by the leagues and fixtures screens."""

from __future__ import annotations

import flet as ft

from football_prognoz.ui.theme import FG, MUTED


def section_header(
    title: str,
    subtitle: str | None = None,
    trailing: ft.Control | None = None,
) -> ft.Control:
    lines: list[ft.Control] = [
        ft.Row(
            [
                ft.Text(
                    title,
                    size=22,
                    weight=ft.FontWeight.BOLD,
                    color=FG,
                    font_family="Fira Code",
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
                size=12,
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
