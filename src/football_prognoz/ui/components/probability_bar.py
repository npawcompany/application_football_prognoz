from __future__ import annotations

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.domain.prediction import Probabilities, Scoreline
from football_prognoz.ui.theme import ACCENT, AWAY, CARD, DRAW, FG, MUTED, SURFACE, glass_border

_ON_ACCENT = "#0F172A"
_GOAL_SCALE = 3.0


def probability_bar(probs: Probabilities) -> ft.Control:
    tiles = [
        ("1", "Хозяева", probs.home, ACCENT),
        ("X", "Ничья", probs.draw, DRAW),
        ("2", "Гости", probs.away, AWAY),
    ]
    favorite = probs.favorite_label

    def tile(code: str, caption: str, value: float, color: str) -> ft.Control:
        chosen = code == favorite
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(code, size=12, color=MUTED, weight=ft.FontWeight.W_600),
                    ft.Text(
                        f"{value * 100:.0f}%",
                        size=28,
                        weight=ft.FontWeight.BOLD,
                        color=FG,
                        font_family="Fira Code",
                    ),
                    ft.Text(caption, size=12, color=MUTED),
                    ft.Text(
                        "Фаворит" if chosen else " ",
                        size=11,
                        color=color if chosen else MUTED,
                        weight=ft.FontWeight.W_600,
                    ),
                ],
                spacing=2,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            bgcolor=SURFACE,
            border=ft.Border.all(1, color) if chosen else glass_border(),
            border_radius=12,
            padding=12,
            expand=True,
        )

    def segment(value: float, color: str) -> ft.Control:
        return ft.Container(
            bgcolor=color,
            expand=max(1, int(round(value * 100))),
            height=10,
            border_radius=8,
            tooltip=f"{value * 100:.0f}%",
        )

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Исход матча", size=13, color=MUTED),
                ft.Row(
                    [tile(code, caption, value, color) for code, caption, value, color in tiles],
                    spacing=8,
                ),
                ft.Row(
                    [segment(value, color) for _code, _caption, value, color in tiles],
                    spacing=4,
                ),
            ],
            spacing=10,
        ),
        bgcolor=CARD,
        border=glass_border(),
        border_radius=12,
        padding=12,
    )


def _goal_meter(label: str, value: float, color: str) -> ft.Control:
    filled = max(1, int(round(min(value, _GOAL_SCALE) / _GOAL_SCALE * 100)))
    rest = max(1, 100 - filled)
    return ft.Column(
        [
            ft.Row(
                [
                    ft.Text(label, size=12, color=MUTED),
                    ft.Text(
                        f"{value:.2f}",
                        size=13,
                        color=FG,
                        weight=ft.FontWeight.W_600,
                        font_family="Fira Code",
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
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
    )


def preliminary_score_card(
    score: Scoreline,
    match: Match | None = None,
    *,
    compact: bool = False,
) -> ft.Control:
    percent = f"{score.probability * 100:.0f}%"
    home_name = match.home_name if match else "Хозяева"
    away_name = match.away_name if match else "Гости"
    board = ft.Column(
        [
            ft.Text("Предварительный счёт", size=13, color=MUTED),
            ft.Text(
                score.label,
                size=40,
                weight=ft.FontWeight.BOLD,
                color=FG,
                font_family="Fira Code",
            ),
            ft.Container(
                content=ft.Text(
                    f"{percent}  ·  самый вероятный",
                    size=12,
                    color=_ON_ACCENT,
                    weight=ft.FontWeight.W_600,
                ),
                bgcolor=ACCENT,
                padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                border_radius=8,
            ),
        ],
        spacing=8,
        horizontal_alignment=ft.CrossAxisAlignment.START,
    )
    meters = ft.Column(
        [
            ft.Text("Ожидаемые голы", size=13, color=MUTED),
            _goal_meter(home_name, score.expected_home, ACCENT),
            _goal_meter(away_name, score.expected_away, AWAY),
            ft.Text(
                f"{score.expected_home:.2f} : {score.expected_away:.2f}  ·  по голам за 5 матчей",
                size=12,
                color=MUTED,
            ),
        ],
        spacing=8,
        expand=True,
    )
    body: ft.Control
    if compact:
        body = ft.Column([board, meters], spacing=14)
    else:
        body = ft.Row(
            [board, ft.Container(width=1, bgcolor=SURFACE, height=96), meters],
            spacing=20,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )
    return ft.Container(
        content=body,
        bgcolor=CARD,
        border=glass_border(),
        border_radius=12,
        padding=16,
    )
