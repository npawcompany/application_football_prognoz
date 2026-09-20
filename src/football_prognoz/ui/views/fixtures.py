from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.ui.components.match_card import match_card
from football_prognoz.ui.runtime import disclaimer, error_banner, info_banner


def fixtures_view(
    league_name: str,
    matches: list[Match],
    *,
    loading: bool,
    error: str | None,
    on_open: Callable[[Match], None],
    on_back: Callable[[], None],
    on_refresh: Callable[[], None],
) -> ft.Control:
    body: list[ft.Control] = [
        ft.Row(
            [
                ft.IconButton(icon=ft.Icons.ARROW_BACK, on_click=lambda _e: on_back()),
                ft.Text(league_name, size=22, weight=ft.FontWeight.BOLD, expand=True),
                ft.IconButton(icon=ft.Icons.REFRESH, on_click=lambda _e: on_refresh()),
            ]
        ),
        ft.Text("Предстоящие матчи"),
        disclaimer(),
    ]
    if error:
        body.append(error_banner(error))
    if loading:
        body.append(ft.ProgressRing())
    elif not matches:
        body.append(info_banner("Нет предстоящих матчей в кэше. Нажмите обновить."))
    else:
        body.extend(match_card(item, on_open) for item in matches)
    return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
