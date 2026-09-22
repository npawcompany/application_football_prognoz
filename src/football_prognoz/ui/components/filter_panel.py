"""Dense fixture filters: team, status, date window, matchday, sort. Russian copy."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.ui.theme import ACCENT, BORDER, FG, SURFACE, glass_border

_ON_ACCENT = "#0F172A"

_STATUS_CHIPS: tuple[tuple[str, str], ...] = (
    ("upcoming", "Предстоящие"),
    ("live", "Живые"),
    ("finished", "Завершённые"),
    ("all", "Все матчи"),
)
_DATE_CHIPS: tuple[tuple[str, str], ...] = (
    ("any", "Любая дата"),
    ("today", "Сегодня"),
    ("days_7", "7 дней"),
    ("days_30", "30 дней"),
)
_SORT_CHIPS: tuple[tuple[str, str], ...] = (
    ("date_asc", "Дата ↑"),
    ("date_desc", "Дата ↓"),
    ("matchday", "Тур"),
    ("home", "Хозяева"),
    ("away", "Гости"),
    ("status", "Статус"),
)


def _chip(label: str, selected: bool, on_click: Callable[[], None]) -> ft.Control:
    return ft.Container(
        content=ft.Text(
            label,
            size=11,
            weight=ft.FontWeight.W_600,
            color=_ON_ACCENT if selected else FG,
        ),
        bgcolor=ACCENT if selected else SURFACE,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
        border_radius=8,
        border=None if selected else glass_border(),
        ink=True,
        on_click=lambda _e: on_click(),
    )


def _field(
    *,
    value: str,
    label: str,
    width: float,
    on_change: Callable[[str], None],
) -> ft.TextField:
    return ft.TextField(
        value=value,
        label=label,
        hint_text=label,
        dense=True,
        filled=True,
        bgcolor=SURFACE,
        fill_color=SURFACE,
        focused_bgcolor=SURFACE,
        color=FG,
        border_color=BORDER,
        focused_border_color=ACCENT,
        cursor_color=ACCENT,
        text_size=13,
        content_padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=8,
        width=width,
        on_change=lambda e: on_change(e.control.value or ""),
    )


def _chip_row(
    options: tuple[tuple[str, str], ...],
    current: str,
    on_pick: Callable[[str], None],
) -> ft.Row:
    selected = str(current)
    return ft.Row(
        [
            _chip(label, selected == value, lambda picked=value: on_pick(picked))
            for value, label in options
        ],
        spacing=6,
        run_spacing=6,
        wrap=True,
    )


def filter_panel(
    *,
    team_query: str,
    on_team_query: Callable[[str], None],
    status: str,
    on_status: Callable[[str], None],
    date_window: str,
    on_date_window: Callable[[str], None],
    matchday: str,
    on_matchday: Callable[[str], None],
    sort: str,
    on_sort: Callable[[str], None],
    on_reset: Callable[[], None],
) -> ft.Control:
    reset = ft.OutlinedButton(
        "Сбросить",
        on_click=lambda _e: on_reset(),
        style=ft.ButtonStyle(color=FG, side=ft.BorderSide(1, BORDER)),
    )
    return ft.Column(
        [
            ft.Row(
                [
                    _field(
                        value=team_query,
                        label="Команда",
                        width=220,
                        on_change=on_team_query,
                    ),
                    _field(
                        value=matchday,
                        label="Тур",
                        width=96,
                        on_change=on_matchday,
                    ),
                    reset,
                ],
                spacing=8,
                run_spacing=8,
                wrap=True,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            _chip_row(_STATUS_CHIPS, status, on_status),
            _chip_row(_DATE_CHIPS, date_window, on_date_window),
            _chip_row(_SORT_CHIPS, sort, on_sort),
        ],
        spacing=8,
        tight=True,
    )
