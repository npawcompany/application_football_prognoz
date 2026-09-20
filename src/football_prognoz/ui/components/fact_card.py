"""Small labelled card used in the match-detail facts row."""

from __future__ import annotations

import flet as ft

from football_prognoz.ui.theme import CARD, MUTED, glass_border


def fact_card(title: str, body: ft.Control) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Text(title, size=11, color=MUTED),
                body,
            ],
            spacing=8,
        ),
        bgcolor=CARD,
        border=glass_border(),
        border_radius=12,
        padding=12,
        expand=True,
    )
