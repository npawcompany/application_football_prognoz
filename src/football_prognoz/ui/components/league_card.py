from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.country import competition_country
from football_prognoz.domain.team import Competition
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.flag import country_label
from football_prognoz.ui.components.team_label import team_label
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.theme import ACCENT, CARD, FG, MUTED, SURFACE, glass_border


def league_card(
    item: Competition,
    on_select: Callable[[Competition], None],
    *,
    selected: bool = False,
    note: str | None = None,
    dimmed: bool = False,
    favorite: bool = False,
) -> ft.Control:
    country = item.area_name or competition_country(item.code)
    subtitle: list[ft.Control] = [
        ft.Text(
            note or "Календарь",
            size=11,
            color=MUTED if dimmed else ACCENT,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        )
    ]
    if country:
        subtitle.append(country_label(country, size=11, iso3=item.area_code))
    badge = f"★ {item.code}" if favorite else item.code
    return apply_motion(
        ft.Container(
            content=ft.Row(
                [
                    crest_image(item.emblem, label=item.name, size=32, code=item.code),
                    ft.Column(
                        [
                            ft.Row(
                                [team_label(item.name, size=14)],
                                spacing=0,
                                expand=True,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                subtitle,
                                spacing=8,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                    ),
                    ft.Container(
                        content=ft.Text(badge, size=11, weight=ft.FontWeight.W_600, color=FG),
                        bgcolor=SURFACE,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                        border_radius=6,
                    ),
                ],
                spacing=10,
                expand=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=CARD,
            border=ft.Border.all(1, ACCENT) if selected else glass_border(),
            border_radius=12,
            padding=10,
            ink=True,
            on_click=lambda _e, current=item: on_select(current),
            tooltip=f"{item.name}: {note}" if note else item.name,
            opacity=0.45 if dimmed else 1.0,
        ),
        interactive=True,
    )
