from __future__ import annotations

import flet as ft

from football_prognoz.ui.motion import WAIT_CURSOR, apply_motion, with_cursor
from football_prognoz.ui.theme import ACCENT, BG, FG, MUTED


def splash_view(message: str, *, fraction: float | None = None) -> ft.Control:
    """Centered boot screen: mark, title, Russian subtitle, ring, status line."""
    determinate = fraction is not None and 0.0 <= fraction <= 1.0
    ring = ft.ProgressRing(
        color=ACCENT,
        width=48,
        height=48,
        value=fraction if determinate else None,
    )
    mark = apply_motion(
        ft.Container(
            content=ft.Icon(ft.Icons.SPORTS_SOCCER, color="#0F172A", size=28),
            width=56,
            height=56,
            bgcolor=ACCENT,
            border_radius=28,
            alignment=ft.Alignment.CENTER,
        )
    )
    body = ft.Container(
        content=ft.Column(
            [
                mark,
                ft.Text(
                    "Football Prognoz",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=FG,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Загрузка данных…",
                    size=14,
                    color=MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
                ring,
                ft.Text(
                    message,
                    size=13,
                    color=FG,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=14,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
        bgcolor=BG,
        alignment=ft.Alignment.CENTER,
    )
    return with_cursor(body, WAIT_CURSOR)
