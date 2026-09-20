from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.team import Competition
from football_prognoz.ui.components.league_card import league_card
from football_prognoz.ui.runtime import error_banner, info_banner
from football_prognoz.ui.theme import FG, LEAGUE_ASPECT_RATIO, MUTED, grid_extent


def leagues_view(
    competitions: list[Competition],
    *,
    loading: bool,
    error: str | None,
    on_select: Callable[[Competition], None],
    on_refresh: Callable[[], None],
    window_width: int = 1440,
    selected_code: str | None = None,
) -> ft.Control:
    header = ft.Row(
        [
            ft.Column(
                [
                    ft.Text(
                        "Лиги",
                        size=22,
                        weight=ft.FontWeight.BOLD,
                        color=FG,
                        font_family="Fira Code",
                    ),
                    ft.Text(
                        "Бесплатный план football-data.org: 12 соревнований.",
                        size=12,
                        color=MUTED,
                    ),
                ],
                spacing=2,
                expand=True,
            ),
            ft.IconButton(
                icon=ft.Icons.REFRESH,
                tooltip="Обновить",
                on_click=lambda _e: on_refresh(),
            ),
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
    )
    body: list[ft.Control] = [header]
    if error:
        body.append(error_banner(error))
    if loading:
        body.append(
            ft.Container(
                content=ft.ProgressRing(color="#22C55E"),
                alignment=ft.Alignment.CENTER,
                expand=True,
            )
        )
    elif not competitions:
        body.append(
            info_banner(
                "Нет лиг. Проверьте ключ API в Настройках.",
                action_hint="Откройте Настройки",
            )
        )
    else:
        body.append(
            ft.GridView(
                controls=[
                    league_card(item, on_select, selected=item.code == selected_code)
                    for item in competitions
                ],
                expand=True,
                max_extent=grid_extent(window_width),
                child_aspect_ratio=LEAGUE_ASPECT_RATIO,
                spacing=10,
                run_spacing=10,
                padding=0,
            )
        )
    return ft.Column(body, spacing=12, expand=True)
