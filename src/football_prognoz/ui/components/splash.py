from __future__ import annotations

import math

import flet as ft

from football_prognoz.ui.motion import WAIT_CURSOR, with_cursor
from football_prognoz.ui.runtime import is_mounted
from football_prognoz.ui.theme import ACCENT, FG, MUTED, ON_ACCENT, PANE_BG

SPIN_TURNS = 600  # one implicit rotation animation covers any realistic boot time
SPIN_SECONDS_PER_TURN = 1.6


def _ball() -> ft.Container:
    return ft.Container(
        content=ft.Icon(ft.Icons.SPORTS_SOCCER, color=ON_ACCENT, size=34),
        width=64,
        height=64,
        bgcolor=ACCENT,
        border_radius=32,
        alignment=ft.Alignment.CENTER,
        rotate=ft.Rotate(angle=0.0),
        animate_rotation=ft.Animation(
            duration=round(SPIN_TURNS * SPIN_SECONDS_PER_TURN * 1000),
            curve=ft.AnimationCurve.LINEAR,
        ),
    )


def start_spin(splash: ft.Control) -> None:
    """Kick the implicit rotation of the splash ball (call after it is on the page)."""
    ball = getattr(splash, "data", None)
    if not isinstance(ball, ft.Container) or not is_mounted(ball):
        return
    ball.rotate = ft.Rotate(angle=math.tau * SPIN_TURNS)
    try:
        ball.update()
    except (RuntimeError, AssertionError):
        pass


def splash_view(message: str, *, fraction: float | None = None) -> ft.Control:
    """Boot screen: spinning ball, title, status line and a progress bar."""
    determinate = fraction is not None and 0.0 <= fraction <= 1.0
    ball = _ball()
    body = ft.Container(
        content=ft.Column(
            [
                ball,
                ft.Text(
                    "Football Prognoz",
                    size=28,
                    weight=ft.FontWeight.BOLD,
                    color=FG,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Text(
                    "Загрузка данных…",
                    size=14,
                    color=MUTED,
                    text_align=ft.TextAlign.CENTER,
                ),
                ft.Container(
                    content=ft.ProgressBar(
                        value=fraction if determinate else None,
                        color=ACCENT,
                        bgcolor=ft.Colors.with_opacity(0.12, ft.Colors.WHITE),
                        border_radius=4,
                    ),
                    width=240,
                ),
                ft.Text(
                    message,
                    size=13,
                    color=FG,
                    text_align=ft.TextAlign.CENTER,
                ),
            ],
            spacing=14,
            tight=True,
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        expand=True,
        bgcolor=PANE_BG,
        alignment=ft.Alignment.CENTER,
    )
    wrapped = with_cursor(body, WAIT_CURSOR)
    wrapped.data = ball
    return wrapped
