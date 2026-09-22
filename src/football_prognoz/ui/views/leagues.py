from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.team import Competition
from football_prognoz.ui.components.filter_bar import filter_bar
from football_prognoz.ui.components.league_card import league_card
from football_prognoz.ui.components.section_header import section_header
from football_prognoz.ui.motion import with_cursor
from football_prognoz.ui.runtime import error_banner, info_banner
from football_prognoz.ui.theme import BG, LEAGUE_ASPECT_RATIO, grid_extent


def leagues_view(
    competitions: list[Competition],
    *,
    loading: bool,
    error: str | None,
    on_select: Callable[[Competition], None],
    on_refresh: Callable[[], None],
    window_width: int = 1440,
    selected_code: str | None = None,
    query: str = "",
    on_query: Callable[[str], None] | None = None,
    favorites_only: bool = False,
    on_favorites_only: Callable[[bool], None] | None = None,
    has_favorites: bool = False,
) -> ft.Control:
    header = section_header(
        "Лиги",
        "Бесплатный план football-data.org: 12 соревнований.",
        trailing=with_cursor(
            ft.IconButton(
                icon=ft.Icons.REFRESH,
                tooltip="Обновить",
                on_click=lambda _e: on_refresh(),
            ),
            interactive=True,
        ),
        window_width=window_width,
    )
    body: list[ft.Control] = [header]
    if on_query is not None:
        chips: list[tuple[str, bool, Callable[[], None]]] | None = None
        if has_favorites and on_favorites_only is not None:
            chips = [
                ("Все лиги", not favorites_only, lambda: on_favorites_only(False)),
                ("Любимые", favorites_only, lambda: on_favorites_only(True)),
            ]
        body.append(
            filter_bar(
                hint="Поиск лиги",
                value=query,
                on_change=on_query,
                chips=chips,
            )
        )
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
                    with_cursor(
                        league_card(item, on_select, selected=item.code == selected_code),
                        interactive=True,
                    )
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
    return ft.Container(
        content=ft.Column(body, spacing=12, expand=True),
        expand=True,
        bgcolor=BG,
    )
