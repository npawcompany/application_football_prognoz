"""Final score of a played match, compared with the forecast (read-only)."""

from __future__ import annotations

import flet as ft

from football_prognoz.domain.match import LIVE_STATUSES, Match
from football_prognoz.domain.prediction import (
    OUTCOME_SHORT_RU,
    MatchForecast,
    check_against_result,
)
from football_prognoz.ui.theme import ACCENT, AWAY, CARD, DRAW, FG, MUTED, scaled


def _verdict(label: str, hit: bool, *, window_width: int) -> ft.Control:
    color = ACCENT if hit else AWAY
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.CHECK_CIRCLE if hit else ft.Icons.CANCEL, size=14, color=color),
                ft.Text(label, size=scaled(12, window_width), color=FG),
            ],
            spacing=6,
            tight=True,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=ft.Colors.with_opacity(0.14, color),
        border_radius=8,
        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
    )


def result_banner(forecast: MatchForecast, *, window_width: int = 1440) -> ft.Control | None:
    """«Завершён 2:1» + outcome/score hit or miss; «Идёт 1:0» for live matches."""
    match: Match = forecast.match
    check = check_against_result(forecast)
    if check is None:
        if match.status in LIVE_STATUSES and match.has_score:
            return ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.SENSORS, color=DRAW, size=20),
                        ft.Text(
                            match.status_text,
                            size=scaled(20, window_width),
                            weight=ft.FontWeight.BOLD,
                            color=FG,
                        ),
                    ],
                    spacing=10,
                ),
                bgcolor=CARD,
                border=ft.Border.all(1, DRAW),
                border_radius=12,
                padding=12,
            )
        return None
    chance = round(check.predicted_probability * 100)
    predicted = f"Исход {OUTCOME_SHORT_RU[check.predicted]} ({chance}%)"
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.SPORTS_SCORE, color=ACCENT, size=28),
                ft.Column(
                    [
                        ft.Text(
                            match.status_text,
                            size=scaled(22, window_width),
                            weight=ft.FontWeight.BOLD,
                            color=FG,
                        ),
                        ft.Text(
                            "Сравнение с прогнозом модели (по данным до начала матча):",
                            size=scaled(12, window_width),
                            color=MUTED,
                        ),
                        ft.Row(
                            [
                                _verdict(
                                    f"{predicted} — {'угадан' if check.outcome_hit else 'нет'}",
                                    check.outcome_hit,
                                    window_width=window_width,
                                ),
                                _verdict(
                                    f"Счёт {check.predicted_score} — "
                                    f"{'угадан' if check.score_hit else 'нет'}",
                                    check.score_hit,
                                    window_width=window_width,
                                ),
                            ],
                            spacing=8,
                            run_spacing=6,
                            wrap=True,
                        ),
                    ],
                    spacing=6,
                    tight=True,
                    expand=True,
                ),
            ],
            spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ),
        bgcolor=CARD,
        border=ft.Border.all(1, ft.Colors.with_opacity(0.6, ACCENT)),
        border_radius=12,
        padding=14,
        tooltip=check.summary,
    )


__all__ = ["result_banner"]
