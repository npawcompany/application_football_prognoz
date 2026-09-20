from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.filter_bar import filter_bar
from football_prognoz.ui.components.match_card import match_card
from football_prognoz.ui.runtime import disclaimer, error_banner, info_banner
from football_prognoz.ui.theme import FG, MUTED, match_extent, match_runs


def fixtures_view(
    league_name: str,
    matches: list[Match],
    *,
    loading: bool,
    error: str | None,
    on_open: Callable[[Match], None],
    on_back: Callable[[], None],
    on_refresh: Callable[[], None],
    league_emblem: str | None = None,
    league_code: str | None = None,
    window_width: int = 1440,
    embedded: bool = False,
    compact_grid: bool = False,
    selected_match_id: int | None = None,
    show_disclaimer: bool = True,
    team_query: str = "",
    on_team_query: Callable[[str], None] | None = None,
    upcoming_only: bool = True,
    on_upcoming_only: Callable[[bool], None] | None = None,
) -> ft.Control:
    title_row: list[ft.Control] = []
    if not embedded:
        title_row.append(
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                tooltip="К лигам",
                on_click=lambda _e: on_back(),
            )
        )
    title_row.extend(
        [
            crest_image(league_emblem, label=league_name, size=28, code=league_code),
            ft.Column(
                [
                    ft.Text(league_name, size=12, color=MUTED),
                    ft.Text(
                        "Предстоящие матчи" if upcoming_only else "Матчи",
                        size=18 if embedded else 22,
                        weight=ft.FontWeight.BOLD,
                        color=FG,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            ft.IconButton(
                icon=ft.Icons.REFRESH,
                tooltip="Обновить",
                on_click=lambda _e: on_refresh(),
            ),
        ]
    )
    body: list[ft.Control] = [
        ft.Row(title_row, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ]
    if on_team_query is not None:
        chips: list[tuple[str, bool, Callable[[], None]]] = [
            (
                "Предстоящие",
                upcoming_only,
                lambda: on_upcoming_only(True) if on_upcoming_only else None,
            ),
            (
                "Все матчи",
                not upcoming_only,
                lambda: on_upcoming_only(False) if on_upcoming_only else None,
            ),
        ]
        body.append(
            filter_bar(
                hint="Команда",
                value=team_query,
                on_change=on_team_query,
                chips=chips,
            )
        )
    if show_disclaimer:
        body.append(disclaimer())
    if error:
        body.append(error_banner(error))
    if loading:
        body.append(
            ft.Container(
                content=ft.ProgressRing(color="#22C55E"),
                alignment=ft.Alignment.CENTER,
            )
        )
    elif not matches:
        empty = (
            "Нет предстоящих матчей в кэше. Нажмите обновить."
            if upcoming_only
            else "Нет матчей в кэше. Нажмите обновить."
        )
        body.append(info_banner(empty))
    else:
        compact = compact_grid or embedded
        cards = [
            match_card(
                item,
                on_open,
                compact=compact,
                selected=item.id == selected_match_id,
            )
            for item in matches
        ]
        if compact_grid and match_runs(window_width) >= 2:
            body.append(
                ft.GridView(
                    controls=cards,
                    expand=True,
                    max_extent=match_extent(window_width),
                    child_aspect_ratio=5.6,
                    spacing=8,
                    run_spacing=8,
                    padding=0,
                )
            )
        else:
            body.append(
                ft.ListView(
                    controls=cards,
                    expand=True,
                    spacing=8,
                    padding=0,
                )
            )
    return ft.Column(body, spacing=12, expand=True)
