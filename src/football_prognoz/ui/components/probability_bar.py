from __future__ import annotations

import flet as ft

from football_prognoz.domain.prediction import Probabilities


def probability_bar(probs: Probabilities) -> ft.Control:
    def segment(label: str, value: float, color: str) -> ft.Control:
        percent = f"{value * 100:.0f}%"
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(label, size=12, color=ft.Colors.WHITE),
                    ft.Text(percent, size=20, weight=ft.FontWeight.BOLD),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=4,
            ),
            bgcolor=color,
            expand=max(1, int(round(value * 100))),
            padding=12,
            border_radius=8,
        )

    return ft.Column(
        [
            ft.Text("Вероятности 1 / X / 2", weight=ft.FontWeight.BOLD),
            ft.Row(
                [
                    segment("1 (дом)", probs.home, ft.Colors.GREEN_700),
                    segment("X (ничья)", probs.draw, ft.Colors.BLUE_GREY_600),
                    segment("2 (гости)", probs.away, ft.Colors.ORANGE_800),
                ],
                spacing=8,
            ),
        ],
        spacing=8,
    )
