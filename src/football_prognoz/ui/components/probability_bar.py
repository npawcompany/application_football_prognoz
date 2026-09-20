from __future__ import annotations

import flet as ft

from football_prognoz.domain.prediction import Probabilities, Scoreline
from football_prognoz.ui.theme import ACCENT, AWAY, CARD, DRAW, FG, MUTED, glass_border


def probability_bar(probs: Probabilities) -> ft.Control:
    def segment(code: str, caption: str, value: float, color: str) -> ft.Control:
        percent = f"{value * 100:.0f}%"
        return ft.Container(
            content=ft.Text(f"{code}  {percent}", size=14, weight=ft.FontWeight.BOLD, color=FG),
            bgcolor=color,
            expand=max(1, int(round(value * 100))),
            padding=8,
            alignment=ft.Alignment.CENTER,
            tooltip=f"{caption}: {percent}",
        )

    tiles = [
        ("1", "Победа хозяев", probs.home, ACCENT),
        ("X", "Ничья", probs.draw, DRAW),
        ("2", "Победа гостей", probs.away, AWAY),
    ]
    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Вероятность исхода (1 / X / 2)", size=13, color=MUTED),
                ft.Row(
                    [segment(code, caption, value, color) for code, caption, value, color in tiles],
                    spacing=0,
                    expand=True,
                ),
                ft.Row(
                    [
                        ft.Text(f"{code} · {caption} · {value * 100:.0f}%", size=12, color=MUTED)
                        for code, caption, value, _color in tiles
                    ],
                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                ),
            ],
            spacing=8,
        ),
        bgcolor=CARD,
        border=glass_border(),
        border_radius=12,
        padding=12,
    )


def preliminary_score_card(score: Scoreline) -> ft.Control:
    percent = f"{score.probability * 100:.0f}%"
    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Предварительный счёт", size=13, color=MUTED),
                ft.Text(score.label, size=32, weight=ft.FontWeight.BOLD, color=FG),
                ft.Text(
                    f"Самая вероятная клетка сетки · {percent}",
                    size=12,
                    color=MUTED,
                ),
                ft.Text(
                    f"Ожидаемые голы λ {score.expected_home:.2f} : {score.expected_away:.2f} "
                    "— среднее забитых и пропущенных за 5 матчей, без Elo, таблицы и травм.",
                    size=12,
                    color=MUTED,
                ),
            ],
            spacing=6,
        ),
        bgcolor=CARD,
        border=glass_border(),
        border_radius=12,
        padding=12,
    )
