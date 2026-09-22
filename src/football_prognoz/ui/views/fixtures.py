from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

import flet as ft

from football_prognoz.domain.match import Match
from football_prognoz.services.filters import (
    DateWindow,
    FixtureQuery,
    MatchSort,
    MatchStatusFilter,
    PageResult,
)
from football_prognoz.ui.components.crest import crest_image
from football_prognoz.ui.components.filter_panel import filter_panel
from football_prognoz.ui.components.match_card import match_card
from football_prognoz.ui.components.pager import pager
from football_prognoz.ui.motion import with_cursor
from football_prognoz.ui.runtime import disclaimer, error_banner, info_banner
from football_prognoz.ui.theme import BG, FG, MUTED, use_stacked_match


def _heading(status: MatchStatusFilter) -> str:
    return {
        MatchStatusFilter.UPCOMING: "Предстоящие матчи",
        MatchStatusFilter.LIVE: "Живые матчи",
        MatchStatusFilter.FINISHED: "Завершённые матчи",
        MatchStatusFilter.ALL: "Матчи",
    }[status]


def _empty_copy(status: MatchStatusFilter) -> str:
    return {
        MatchStatusFilter.UPCOMING: "Нет предстоящих матчей. Нажмите обновить.",
        MatchStatusFilter.LIVE: "Сейчас нет живых матчей.",
        MatchStatusFilter.FINISHED: "Нет завершённых матчей. Нажмите обновить.",
        MatchStatusFilter.ALL: "Нет матчей. Нажмите обновить.",
    }[status]


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
    query: FixtureQuery | None = None,
    page_result: PageResult | None = None,
    on_query: Callable[[FixtureQuery], None] | None = None,
) -> ft.Control:
    status = query.status if query is not None else MatchStatusFilter.UPCOMING
    title_row: list[ft.Control] = []
    if not embedded:
        title_row.append(
            with_cursor(
                ft.IconButton(
                    icon=ft.Icons.ARROW_BACK,
                    tooltip="К лигам",
                    on_click=lambda _e: on_back(),
                ),
                interactive=True,
            )
        )
    title_row.extend(
        [
            crest_image(league_emblem, label=league_name, size=28, code=league_code),
            ft.Column(
                [
                    ft.Text(league_name, size=12, color=MUTED, max_lines=1),
                    ft.Text(
                        _heading(status),
                        size=18 if embedded else 22,
                        weight=ft.FontWeight.BOLD,
                        color=FG,
                        max_lines=1,
                        overflow=ft.TextOverflow.ELLIPSIS,
                    ),
                ],
                spacing=0,
                expand=True,
            ),
            with_cursor(
                ft.IconButton(
                    icon=ft.Icons.REFRESH,
                    tooltip="Обновить",
                    on_click=lambda _e: on_refresh(),
                ),
                interactive=True,
            ),
        ]
    )
    body: list[ft.Control] = [
        ft.Row(title_row, vertical_alignment=ft.CrossAxisAlignment.CENTER),
    ]
    if on_query is not None and query is not None:
        body.append(
            filter_panel(
                team_query=query.team_query,
                on_team_query=lambda text: on_query(replace(query, team_query=text, page=0)),
                status=query.status.value,
                on_status=lambda value: on_query(
                    replace(query, status=MatchStatusFilter(value), page=0)
                ),
                date_window=query.date_window.value,
                on_date_window=lambda value: on_query(
                    replace(query, date_window=DateWindow(value), page=0)
                ),
                matchday="" if query.matchday is None else str(query.matchday),
                on_matchday=lambda text: on_query(_query_with_matchday(query, text)),
                sort=query.sort.value,
                on_sort=lambda value: on_query(replace(query, sort=MatchSort(value), page=0)),
                on_reset=lambda: on_query(FixtureQuery(page_size=query.page_size)),
            )
        )
    if show_disclaimer:
        body.append(disclaimer())
    if error:
        body.append(error_banner(error))
    shown = page_result.items if page_result is not None else matches
    if loading:
        body.append(
            ft.Container(
                content=ft.ProgressRing(color="#22C55E"),
                alignment=ft.Alignment.CENTER,
            )
        )
    elif not shown:
        body.append(info_banner(_empty_copy(status)))
    else:
        compact = compact_grid or embedded
        narrow = use_stacked_match(window_width)
        cards = [
            with_cursor(
                match_card(
                    item,
                    on_open,
                    compact=compact,
                    selected=item.id == selected_match_id,
                    narrow=narrow,
                    window_width=window_width,
                ),
                interactive=True,
            )
            for item in shown
        ]
        body.append(
            ft.Container(
                content=ft.ListView(
                    controls=cards,
                    expand=True,
                    spacing=8,
                    padding=0,
                ),
                expand=True,
                bgcolor=BG,
            )
        )
    if page_result is not None and on_query is not None and query is not None and not loading:
        body.append(
            pager(
                page=page_result.page,
                page_count=page_result.page_count,
                total=page_result.total,
                page_size=page_result.page_size,
                on_page=lambda page: on_query(replace(query, page=page)),
            )
        )
    return ft.Container(
        content=ft.Column(body, spacing=12, expand=True),
        expand=True,
        bgcolor=BG,
    )


def _query_with_matchday(query: FixtureQuery, text: str) -> FixtureQuery:
    stripped = text.strip()
    if not stripped:
        day = None
    else:
        try:
            day = int(stripped)
        except ValueError:
            return query
    return replace(query, matchday=day, page=0)
