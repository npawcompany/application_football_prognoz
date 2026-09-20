from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.match import Match


def match_card(match: Match, on_open: Callable[[Match], None]) -> ft.Control:
    kickoff = match.utc_date.strftime("%d.%m.%Y %H:%M UTC")
    score = ""
    if match.score.home is not None and match.score.away is not None:
        score = f"{match.score.home}:{match.score.away}"
    return ft.Container(
        content=ft.ListTile(
            title=ft.Text(match.label, weight=ft.FontWeight.W_600),
            subtitle=ft.Text(f"{kickoff} · {match.status.value}"),
            trailing=ft.Text(score or "—"),
            on_click=lambda _e, current=match: on_open(current),
        ),
        bgcolor=ft.Colors.BLUE_GREY_900,
        border_radius=10,
        padding=4,
        margin=ft.margin.only(bottom=8),
    )
