from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.team_label import team_label
from football_prognoz.ui.components.venue import venue_badge
from football_prognoz.ui.formatters import format_kickoff_date, format_kickoff_time
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.theme import ACCENT, CARD, FG, MUTED, SURFACE, glass_border, scaled


def _status_chip(label: str, *, window_width: int) -> ft.Control:
    return ft.Container(
        content=ft.Text(
            label,
            size=scaled(11, window_width),
            color=MUTED,
            max_lines=1,
            overflow=ft.TextOverflow.ELLIPSIS,
        ),
        bgcolor=SURFACE,
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
        border_radius=8,
    )


def _forecast_chip(*, window_width: int) -> ft.Control:
    return ft.Container(
        content=ft.Text(
            "Прогноз",
            size=scaled(11, window_width),
            weight=ft.FontWeight.W_600,
            color="#0F172A",
        ),
        bgcolor=ACCENT,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=8,
    )


def _team_row(
    crest: str | None,
    name: str,
    team_id: int,
    *,
    size: int,
    spacing: int,
    name_size: int,
    side: str,
    name_first: bool = False,
    expand: bool = False,
) -> ft.Row:
    crest_ctl = crest_image(crest, label=name, size=size, team_id=team_id)
    name_ctl = team_label(
        name,
        size=name_size,
        align=ft.TextAlign.RIGHT if name_first else ft.TextAlign.LEFT,
        expand=expand,
    )
    mark = venue_badge(side, size=max(12, size - 8))
    children = [name_ctl, crest_ctl, mark] if name_first else [mark, crest_ctl, name_ctl]
    return ft.Row(
        children,
        spacing=spacing,
        expand=expand,
        wrap=False,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def match_card(
    match: Match,
    on_open: Callable[[Match], None],
    *,
    compact: bool = False,
    selected: bool = False,
    narrow: bool = False,
    window_width: int = 1440,
) -> ft.Control:
    kickoff = format_kickoff_date(match.utc_date)
    time = format_kickoff_time(match.utc_date)
    border = ft.Border.all(1, ACCENT) if selected else glass_border()
    crest_size = 20 if compact else 24
    team_spacing = 6 if compact else 8
    name_size = scaled(12 if compact else 13, window_width)
    pad: int | ft.Padding = 8 if compact else ft.Padding.symmetric(horizontal=10, vertical=8)

    home = _team_row(
        match.home_crest,
        match.home_name,
        match.home_id,
        size=crest_size,
        spacing=team_spacing,
        name_size=name_size,
        side="home",
        expand=True,
    )
    away = _team_row(
        match.away_crest,
        match.away_name,
        match.away_id,
        size=crest_size,
        spacing=team_spacing,
        name_size=name_size,
        side="away",
        name_first=False,
        expand=True,
    )

    actions = ft.Row(
        [
            _status_chip(match.status.value, window_width=window_width),
            _forecast_chip(window_width=window_width),
        ],
        spacing=8,
        wrap=True,
        run_spacing=4,
    )
    date_block = ft.Column(
        [
            ft.Text(kickoff, size=scaled(12, window_width), color=FG),
            ft.Text(time, size=scaled(11, window_width), color=MUTED),
        ],
        spacing=0,
        tight=True,
    )
    teams = ft.Column(
        [home, away],
        spacing=4 if compact else 6,
        tight=True,
        expand=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    if narrow:
        content: ft.Control = ft.Column(
            [date_block, teams, actions],
            spacing=6 if compact else 8,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    else:
        content = ft.Row(
            [
                date_block,
                teams,
                actions,
            ],
            spacing=10,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )

    return apply_motion(
        ft.Container(
            content=content,
            bgcolor=CARD,
            border=border,
            border_radius=12,
            padding=pad,
            ink=True,
            on_click=lambda _e, current=match: on_open(current),
        ),
        interactive=True,
    )
