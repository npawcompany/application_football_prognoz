from __future__ import annotations

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import Probabilities, Scoreline
from football_prognoz.domain.team import TeamRoster
from football_prognoz.ui.components.crest import crest_image, resolve_src
from football_prognoz.ui.components.flag import country_label
from football_prognoz.ui.components.team_label import team_label
from football_prognoz.ui.components.venue import venue_badge
from football_prognoz.ui.motion import apply_motion
from football_prognoz.ui.theme import (
    ACCENT,
    AWAY,
    CARD,
    DRAW,
    FG,
    MUTED,
    SURFACE,
    glass_border,
    scaled,
)

_ON_ACCENT = "#0F172A"
_GOAL_SCALE = 3.0
_FILL_MS = 900


def probability_bar(
    probs: Probabilities,
    *,
    compact: bool = False,
    window_width: int = 1440,
) -> ft.Control:
    tiles = [
        ("1", "Хозяева", "home", probs.home, ACCENT),
        ("X", "Ничья", None, probs.draw, DRAW),
        ("2", "Гости", "away", probs.away, AWAY),
    ]
    favorite = probs.favorite_label
    percent_size = scaled(20 if compact else 28, window_width)
    tile_pad = 8 if compact else 12
    caption_size = scaled(12, window_width)
    tile_h = 92 if compact else 104

    def tile(code: str, caption: str, side: str | None, value: float, color: str) -> ft.Control:
        chosen = code == favorite
        filled = max(1, min(100, int(round(value * 100))))
        empty = 100 - filled
        wash = ft.Container(
            expand=True,
            bgcolor=ft.Colors.with_opacity(0.42 if chosen else 0.28, color),
            animate_opacity=_FILL_MS,
            data={"fill": value},
        )
        bar = ft.ProgressBar(
            value=value,
            color=color,
            bgcolor=ft.Colors.with_opacity(0.18, color),
            bar_height=6,
            border_radius=8,
            data={"fill": value},
        )
        fill_children: list[ft.Control] = [
            ft.Container(
                content=wash,
                expand=filled,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            )
        ]
        if empty:
            fill_children.append(ft.Container(expand=empty))
        labels = ft.Column(
            [
                ft.Text(code, size=caption_size, color=MUTED, weight=ft.FontWeight.W_600),
                ft.Text(
                    f"{value * 100:.0f}%",
                    size=percent_size,
                    weight=ft.FontWeight.BOLD,
                    color=FG,
                ),
                ft.Row(
                    [
                        venue_badge(side, size=12),
                        ft.Text(caption, size=caption_size, color=MUTED),
                    ],
                    spacing=4,
                    tight=True,
                    alignment=ft.MainAxisAlignment.CENTER,
                )
                if side
                else ft.Text(caption, size=caption_size, color=MUTED),
                ft.Text(
                    "Фаворит" if chosen else " ",
                    size=scaled(11, window_width),
                    color=color if chosen else MUTED,
                    weight=ft.FontWeight.W_600,
                ),
                bar,
            ],
            spacing=2,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )
        return apply_motion(
            ft.Container(
                content=ft.Stack(
                    [
                        ft.Row(
                            fill_children,
                            spacing=0,
                            expand=True,
                            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                        ),
                        ft.Container(
                            content=labels,
                            alignment=ft.Alignment.CENTER,
                            padding=tile_pad,
                            expand=True,
                        ),
                    ],
                    expand=True,
                    fit=ft.StackFit.EXPAND,
                ),
                bgcolor=SURFACE,
                border=ft.Border.all(1, color) if chosen else glass_border(),
                border_radius=12,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
                height=tile_h,
                expand=not compact,
            ),
            interactive=True,
        )

    def segment(value: float, color: str) -> ft.Control:
        return ft.Container(
            bgcolor=color,
            expand=max(1, int(round(value * 100))),
            height=10,
            border_radius=8,
            tooltip=f"{value * 100:.0f}%",
        )

    tile_controls = [
        tile(code, caption, side, value, color)
        for code, caption, side, value, color in tiles
    ]
    if compact:
        tile_layout: ft.Control = ft.Column(
            tile_controls,
            spacing=8,
            tight=True,
            horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
        )
    else:
        tile_layout = ft.Row(tile_controls, spacing=8)

    return apply_motion(
        ft.Container(
            content=ft.Column(
                [
                    ft.Text("Исход матча", size=scaled(13, window_width), color=MUTED),
                    tile_layout,
                    ft.Row(
                        [segment(value, color) for _code, _caption, _side, value, color in tiles],
                        spacing=4,
                    ),
                ],
                spacing=10,
                tight=True,
            ),
            bgcolor=CARD,
            border=glass_border(),
            border_radius=12,
            padding=12,
        )
    )


def _winner_style(active: bool) -> ft.TextStyle | None:
    if not active:
        return None
    return ft.TextStyle(
        decoration=ft.TextDecoration.UNDERLINE,
        decoration_color=ACCENT,
        decoration_thickness=2,
    )


def _score_team(
    name: str,
    *,
    crest: str | None,
    team_id: int,
    side: str,
    winner: bool,
    window_width: int,
) -> ft.Control:
    return ft.Row(
        [
            venue_badge(side, size=16),
            crest_image(crest, label=name, size=28, team_id=team_id),
            team_label(
                name,
                size=scaled(14, window_width),
                color=ACCENT if winner else FG,
                style=_winner_style(winner),
            ),
        ],
        spacing=8,
        expand=True,
        wrap=False,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def _ghost_crest(src: str | None, team_id: int, *, size: int = 96) -> ft.Control:
    resolved = resolve_src(src, team_id=team_id)
    if not resolved:
        return ft.Container(width=size, height=size)
    return ft.Image(
        src=resolved,
        width=size,
        height=size,
        fit=ft.BoxFit.CONTAIN,
        opacity=0.14,
    )


def _place_column(
    match: Match | None,
    roster: TeamRoster | None,
    *,
    window_width: int,
) -> ft.Control:
    stadium = (match.venue if match else None) or (roster.venue if roster else None)
    city = roster.city if roster else None
    country = roster.country if roster else None
    bits: list[ft.Control] = [
        ft.Text("Место", size=scaled(11, window_width), color=MUTED),
    ]
    if stadium:
        bits.append(
            ft.Text(
                stadium,
                size=scaled(13, window_width),
                color=FG,
                weight=ft.FontWeight.W_600,
                max_lines=2,
            )
        )
    if city:
        bits.append(ft.Text(city, size=scaled(12, window_width), color=MUTED, max_lines=1))
    if country:
        bits.append(country_label(country, size=scaled(12, window_width)))
    if len(bits) == 1:
        bits.append(ft.Text("Стадион не указан", size=scaled(12, window_width), color=MUTED))
    return ft.Column(bits, spacing=4, tight=True, width=160)


def _goal_meter(
    name: str,
    value: float,
    color: str,
    *,
    crest: str | None,
    team_id: int,
    side: str,
    window_width: int,
) -> ft.Control:
    filled = max(1, int(round(min(value, _GOAL_SCALE) / _GOAL_SCALE * 100)))
    rest = max(1, 100 - filled)
    return ft.Column(
        [
            ft.Row(
                [
                    venue_badge(side, size=12),
                    crest_image(crest, label=name, size=16, team_id=team_id),
                    team_label(
                        name,
                        size=scaled(12, window_width),
                        weight=ft.FontWeight.NORMAL,
                        color=MUTED,
                    ),
                    ft.Text(
                        f"{value:.2f}",
                        size=scaled(13, window_width),
                        color=FG,
                        weight=ft.FontWeight.W_600,
                    ),
                ],
                spacing=6,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            ft.Container(
                content=ft.Row(
                    [
                        ft.Container(expand=filled, bgcolor=color, border_radius=6),
                        ft.Container(expand=rest, bgcolor=SURFACE, border_radius=6),
                    ],
                    spacing=0,
                ),
                height=8,
                border_radius=6,
                clip_behavior=ft.ClipBehavior.HARD_EDGE,
            ),
        ],
        spacing=4,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )


def preliminary_score_card(
    score: Scoreline,
    match: Match | None = None,
    *,
    compact: bool = False,
    window_width: int = 1440,
    home_roster: TeamRoster | None = None,
) -> ft.Control:
    percent = f"{score.probability * 100:.0f}%"
    home_name = match.home_name if match else "Хозяева"
    away_name = match.away_name if match else "Гости"
    home_id = match.home_id if match else 0
    away_id = match.away_id if match else 0
    home_crest = match.home_crest if match else None
    away_crest = match.away_crest if match else None
    winner = score.winner_side
    teams = ft.Row(
        [
            _score_team(
                home_name,
                crest=home_crest,
                team_id=home_id,
                side="home",
                winner=winner == "home",
                window_width=window_width,
            ),
            ft.Text("·", size=scaled(16, window_width), color=MUTED),
            _score_team(
                away_name,
                crest=away_crest,
                team_id=away_id,
                side="away",
                winner=winner == "away",
                window_width=window_width,
            ),
        ],
        spacing=10,
        wrap=False,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
    watermark = ft.Row(
        [
            _ghost_crest(home_crest, home_id),
            ft.Text(
                "VS",
                size=scaled(42, window_width),
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.with_opacity(0.16, FG),
            ),
            _ghost_crest(away_crest, away_id),
        ],
        alignment=ft.MainAxisAlignment.SPACE_AROUND,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
        expand=True,
    )
    board_copy = ft.Column(
        [
            ft.Text("Предварительный счёт", size=scaled(13, window_width), color=MUTED),
            teams,
            ft.Text(
                score.label,
                size=scaled(40, window_width),
                weight=ft.FontWeight.BOLD,
                color=FG,
            ),
            ft.Container(
                content=ft.Text(
                    f"{percent}  ·  самый вероятный",
                    size=scaled(12, window_width),
                    color=_ON_ACCENT,
                    weight=ft.FontWeight.W_600,
                ),
                bgcolor=ACCENT,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                border_radius=8,
            ),
        ],
        spacing=8,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.START,
    )
    board = ft.Container(
        content=ft.Stack(
            [
                ft.Container(content=watermark, alignment=ft.Alignment.CENTER, expand=True),
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Container(content=board_copy, expand=True),
                            _place_column(match, home_roster, window_width=window_width),
                        ],
                        spacing=12,
                        vertical_alignment=ft.CrossAxisAlignment.START,
                        wrap=False,
                    ),
                    padding=4,
                ),
            ]
        ),
        height=176,
        clip_behavior=ft.ClipBehavior.HARD_EDGE,
    )
    meters = ft.Column(
        [
            ft.Text("Ожидаемые голы", size=scaled(13, window_width), color=MUTED),
            _goal_meter(
                home_name,
                score.expected_home,
                ACCENT,
                crest=home_crest,
                team_id=home_id,
                side="home",
                window_width=window_width,
            ),
            _goal_meter(
                away_name,
                score.expected_away,
                AWAY,
                crest=away_crest,
                team_id=away_id,
                side="away",
                window_width=window_width,
            ),
            ft.Text(
                f"{score.expected_home:.2f} : {score.expected_away:.2f}  ·  по голам за 5 матчей",
                size=scaled(12, window_width),
                color=MUTED,
            ),
        ],
        spacing=8,
        tight=True,
        horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
    )
    body: ft.Control
    if compact:
        body = ft.Column([board, meters], spacing=14, tight=True)
    else:
        body = ft.Row(
            [
                ft.Container(content=board, expand=True),
                ft.Container(width=1, bgcolor=SURFACE, height=120),
                ft.Container(content=meters, expand=True),
            ],
            spacing=20,
            vertical_alignment=ft.CrossAxisAlignment.START,
            wrap=True,
            run_spacing=12,
        )
    return apply_motion(
        ft.Container(
            content=body,
            bgcolor=CARD,
            border=glass_border(),
            border_radius=12,
            padding=16,
        )
    )
