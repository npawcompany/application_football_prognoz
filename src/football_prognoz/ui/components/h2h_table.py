"""Last-5 head-to-head as a compact score table (no club names)."""

from __future__ import annotations

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.venue import venue_badge
from football_prognoz.ui.formatters import format_kickoff_date, format_kickoff_time
from football_prognoz.ui.theme import ACCENT, AWAY, FG, MUTED, SURFACE, glass_border, scaled


def _score_half(goals: int | None, *, won: bool, window_width: int) -> ft.Text:
    return ft.Text(
        "—" if goals is None else str(goals),
        size=scaled(14, window_width),
        weight=ft.FontWeight.BOLD if won else ft.FontWeight.W_600,
        color=ACCENT if won else FG,
        style=ft.TextStyle(
            decoration=ft.TextDecoration.UNDERLINE,
            decoration_color=ACCENT,
            decoration_thickness=2,
        )
        if won
        else None,
    )


def _h2h_row(match: Match, *, window_width: int) -> ft.Control:
    home_goals = match.score.home
    away_goals = match.score.away
    home_won = (
        home_goals is not None and away_goals is not None and home_goals > away_goals
    )
    away_won = (
        home_goals is not None and away_goals is not None and away_goals > home_goals
    )
    return ft.Container(
        content=ft.Row(
            [
                ft.Column(
                    [
                        ft.Text(
                            format_kickoff_date(match.utc_date),
                            size=scaled(11, window_width),
                            color=FG,
                        ),
                        ft.Text(
                            format_kickoff_time(match.utc_date),
                            size=scaled(10, window_width),
                            color=MUTED,
                        ),
                    ],
                    spacing=0,
                    tight=True,
                    width=88,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            venue_badge("home", size=14),
                            crest_image(
                                match.home_crest,
                                label=match.home_name,
                                size=22,
                                team_id=match.home_id,
                            ),
                        ],
                        spacing=6,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    expand=True,
                ),
                ft.Row(
                    [
                        _score_half(home_goals, won=home_won, window_width=window_width),
                        ft.Text(":", size=scaled(13, window_width), color=MUTED),
                        _score_half(away_goals, won=away_won, window_width=window_width),
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Container(
                    content=ft.Row(
                        [
                            crest_image(
                                match.away_crest,
                                label=match.away_name,
                                size=22,
                                team_id=match.away_id,
                            ),
                            venue_badge("away", size=14),
                        ],
                        spacing=6,
                        alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    expand=True,
                ),
            ],
            spacing=8,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=SURFACE,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        border_radius=10,
        border=ft.Border.all(1, ACCENT)
        if home_won
        else (ft.Border.all(1, AWAY) if away_won else None),
    )


def _header(window_width: int) -> ft.Control:
    mute = scaled(11, window_width)
    return ft.Row(
        [
            ft.Text("Дата", size=mute, color=MUTED, width=88),
            ft.Container(
                content=ft.Row(
                    [
                        venue_badge("home", size=14),
                        ft.Text("Дома", size=mute, color=MUTED),
                    ],
                    spacing=6,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
            ),
            ft.Text(
                "Счёт",
                size=mute,
                color=MUTED,
                width=48,
                text_align=ft.TextAlign.CENTER,
            ),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Text("Гости", size=mute, color=MUTED),
                        venue_badge("away", size=14),
                    ],
                    spacing=6,
                    alignment=ft.MainAxisAlignment.END,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                expand=True,
            ),
        ],
        spacing=8,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def h2h_table(
    matches: tuple[Match, ...] | list[Match],
    *,
    window_width: int = 1440,
) -> ft.Control:
    if not matches:
        return ft.Text("Нет очных встреч", size=scaled(13, window_width), color=MUTED)
    rows = [_header(window_width)]
    rows.extend(_h2h_row(item, window_width=window_width) for item in matches)
    return ft.Container(
        content=ft.Column(rows, spacing=6, tight=True),
        border=glass_border(),
        border_radius=10,
        padding=8,
    )
