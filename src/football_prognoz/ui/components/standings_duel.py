"""Two-club league table snapshot (position, record, points, GD)."""

from __future__ import annotations

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.domain.team import StandingRow
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.team_label import team_label
from football_prognoz.ui.components.venue import venue_badge
from football_prognoz.ui.theme import ACCENT, FG, MUTED, SURFACE, scaled


def _record(row: StandingRow) -> str:
    return f"{row.won}–{row.draw}–{row.lost}"


def _gd(row: StandingRow) -> str:
    delta = row.goals_for - row.goals_against
    return f"{delta:+d}"


def _club_row(
    row: StandingRow | None,
    match: Match,
    side: str,
    *,
    window_width: int,
) -> ft.Control:
    name = match.home_name if side == "home" else match.away_name
    crest = match.home_crest if side == "home" else match.away_crest
    team_id = match.home_id if side == "home" else match.away_id
    place = "—" if row is None else str(row.position)
    stats = "нет строки таблицы" if row is None else (
        f"{row.played} игр  ·  {_record(row)}  ·  {row.points} оч.  ·  {_gd(row)}"
    )
    bar = 0
    if row is not None:
        bar = max(8, min(100, row.points * 4))
    return ft.Container(
        content=ft.Column(
            [
                ft.Row(
                    [
                        venue_badge(side, size=14),
                        ft.Text(
                            place,
                            size=scaled(18, window_width),
                            weight=ft.FontWeight.BOLD,
                            color=ACCENT if side == "home" else FG,
                            width=28,
                        ),
                        crest_image(crest, label=name, size=22, team_id=team_id),
                        team_label(name, size=scaled(13, window_width)),
                    ],
                    spacing=8,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Text(stats, size=scaled(11, window_width), color=MUTED),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(expand=bar or 1, bgcolor=ACCENT, border_radius=6),
                            ft.Container(
                                expand=max(1, 100 - bar),
                                bgcolor=SURFACE,
                                border_radius=6,
                            ),
                        ],
                        spacing=0,
                    ),
                    height=6,
                    border_radius=6,
                    clip_behavior=ft.ClipBehavior.HARD_EDGE,
                )
                if row is not None
                else ft.Container(),
            ],
            spacing=6,
            tight=True,
        ),
        bgcolor=SURFACE,
        padding=10,
        border_radius=10,
    )


def standings_duel(
    match: Match,
    home: StandingRow | None,
    away: StandingRow | None,
    *,
    window_width: int = 1440,
) -> ft.Control:
    return ft.Column(
        [
            _club_row(home, match, "home", window_width=window_width),
            _club_row(away, match, "away", window_width=window_width),
        ],
        spacing=8,
        tight=True,
    )
