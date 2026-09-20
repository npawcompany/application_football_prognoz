from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.team import Competition
from football_prognoz.ui.runtime import error_banner, info_banner


def leagues_view(
    competitions: list[Competition],
    *,
    loading: bool,
    error: str | None,
    on_select: Callable[[Competition], None],
    on_refresh: Callable[[], None],
) -> ft.Control:
    body: list[ft.Control] = [
        ft.Row(
            [
                ft.Text("Лиги", size=24, weight=ft.FontWeight.BOLD),
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="Обновить",
                    on_click=lambda _e: on_refresh(),
                ),
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        ),
        ft.Text("Бесплатный план football-data.org: 12 соревнований."),
    ]
    if error:
        body.append(error_banner(error))
    if loading:
        body.append(ft.ProgressRing())
    elif not competitions:
        body.append(info_banner("Нет лиг. Проверьте ключ API в Настройках."))
    else:
        for item in competitions:
            body.append(
                ft.Container(
                    content=ft.ListTile(
                        leading=ft.Icon(ft.Icons.SPORTS_SOCCER),
                        title=ft.Text(item.name),
                        subtitle=ft.Text(item.code),
                        on_click=lambda _e, current=item: on_select(current),
                    ),
                    bgcolor=ft.Colors.BLUE_GREY_900,
                    border_radius=10,
                    margin=ft.margin.only(bottom=8),
                )
            )
    return ft.Column(body, spacing=12, expand=True, scroll=ft.ScrollMode.AUTO)
