from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.theme import ACCENT, CARD, FG, MUTED, SURFACE, glass_border


def _name(text: str, *, align: ft.TextAlign = ft.TextAlign.LEFT) -> ft.Text:
    return ft.Text(
        text,
        size=13,
        weight=ft.FontWeight.W_600,
        color=FG,
        expand=True,
        max_lines=1,
        overflow=ft.TextOverflow.ELLIPSIS,
        text_align=align,
    )


def match_card(
    match: Match,
    on_open: Callable[[Match], None],
    *,
    compact: bool = False,
    selected: bool = False,
) -> ft.Control:
    kickoff = match.utc_date.strftime("%d.%m.%Y")
    time = match.utc_date.strftime("%H:%M UTC")
    border = ft.border.all(1, ACCENT) if selected else glass_border()
    if compact:
        return ft.Container(
            content=ft.Row(
                [
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    crest_image(
                                        match.home_crest,
                                        label=match.home_name,
                                        size=20,
                                        team_id=match.home_id,
                                    ),
                                    _name(match.home_name),
                                ],
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                [
                                    crest_image(
                                        match.away_crest,
                                        label=match.away_name,
                                        size=20,
                                        team_id=match.away_id,
                                    ),
                                    _name(match.away_name),
                                ],
                                spacing=6,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Column(
                        [
                            ft.Text(kickoff, size=11, color=MUTED, font_family="Fira Code"),
                            ft.Text("Прогноз", size=11, weight=ft.FontWeight.W_600, color=ACCENT),
                        ],
                        spacing=2,
                        horizontal_alignment=ft.CrossAxisAlignment.END,
                    ),
                ],
                spacing=8,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=CARD,
            border=border,
            border_radius=12,
            padding=8,
            height=56,
            ink=True,
            on_click=lambda _e, current=match: on_open(current),
        )

    home = ft.Row(
        [
            crest_image(match.home_crest, label=match.home_name, size=24, team_id=match.home_id),
            _name(match.home_name),
        ],
        spacing=8,
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    away = ft.Row(
        [
            _name(match.away_name, align=ft.TextAlign.RIGHT),
            crest_image(match.away_crest, label=match.away_name, size=24, team_id=match.away_id),
        ],
        spacing=8,
        expand=True,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    return ft.Container(
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(kickoff, size=12, color=FG),
                        ft.Text(time, size=11, color=MUTED),
                    ],
                    spacing=0,
                    width=108,
                ),
                home,
                ft.Container(
                    content=ft.Text("VS", size=11, weight=ft.FontWeight.BOLD, color=MUTED),
                    bgcolor=SURFACE,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    border_radius=8,
                ),
                away,
                ft.Container(
                    content=ft.Text(match.status.value, size=11, color=MUTED),
                    bgcolor=SURFACE,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    border_radius=8,
                ),
                ft.Container(
                    content=ft.Text(
                        "Прогноз",
                        size=11,
                        weight=ft.FontWeight.W_600,
                        color="#0F172A",
                    ),
                    bgcolor=ACCENT,
                    padding=ft.padding.symmetric(horizontal=10, vertical=4),
                    border_radius=8,
                ),
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=CARD,
        border=border,
        border_radius=12,
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        height=52,
        ink=True,
        on_click=lambda _e, current=match: on_open(current),
    )
