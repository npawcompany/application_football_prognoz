from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.team import Competition
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.team_label import team_label
from football_prognoz.ui.theme import ACCENT, CARD, FG, SURFACE, glass_border


def league_card(
    item: Competition,
    on_select: Callable[[Competition], None],
    *,
    selected: bool = False,
) -> ft.Control:
    return ft.Container(
        content=ft.Row(
            [
                crest_image(item.emblem, label=item.name, size=32, code=item.code),
                ft.Column(
                    [
                        ft.Row(
                            [team_label(item.name, size=14)],
                            spacing=0,
                            expand=True,
                        ),
                        ft.Text("Календарь", size=11, color=ACCENT),
                    ],
                    spacing=2,
                    expand=True,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
                ft.Container(
                    content=ft.Text(item.code, size=11, weight=ft.FontWeight.W_600, color=FG),
                    bgcolor=SURFACE,
                    padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                    border_radius=6,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=CARD,
        border=ft.Border.all(1, ACCENT) if selected else glass_border(),
        border_radius=12,
        padding=10,
        ink=True,
        on_click=lambda _e, current=item: on_select(current),
        tooltip=item.name,
    )
