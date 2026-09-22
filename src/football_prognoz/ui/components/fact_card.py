"""Small labelled card used in the match-detail facts row."""

from __future__ import annotations

import flet as ft

from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.theme import CARD, MUTED, glass_border


def fact_card(
    title: str,
    body: ft.Control,
    *,
    bgcolor: str | None = None,
    height: int | None = None,
) -> ft.Control:
    return apply_motion(
        ft.Container(
            content=ft.Column(
                [
                    ft.Text(title, size=11, color=MUTED),
                    body,
                ],
                spacing=6,
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
            ),
            bgcolor=bgcolor or CARD,
            border=glass_border(),
            border_radius=12,
            padding=12,
            expand=False,
            height=height,
            alignment=ft.Alignment.TOP_LEFT,
        )
    )
