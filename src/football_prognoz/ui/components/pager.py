"""Compact page controls. Intrinsic height — do not expand into a scrolling parent."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.ui.theme import ACCENT, FG, MUTED


def _caption(*, page: int, total: int, page_size: int) -> str:
    if total <= 0:
        return "Нет матчей"
    size = page_size if page_size > 0 else 1
    start = page * size + 1
    end = min((page + 1) * size, total)
    return f"{start}–{end} из {total}"


def pager(
    *,
    page: int,
    page_count: int,
    total: int,
    page_size: int,
    on_page: Callable[[int], None],
) -> ft.Control:
    last = max(page_count, 1) - 1
    back = ft.TextButton(
        "Назад",
        disabled=page <= 0,
        on_click=lambda _e: on_page(page - 1),
        style=ft.ButtonStyle(color=FG),
    )
    forward = ft.TextButton(
        "Вперёд",
        disabled=page >= last,
        on_click=lambda _e: on_page(page + 1),
        style=ft.ButtonStyle(color=ACCENT),
    )
    return ft.Row(
        [
            back,
            ft.Text(_caption(page=page, total=total, page_size=page_size), size=12, color=MUTED),
            forward,
        ],
        spacing=8,
        run_spacing=4,
        wrap=True,
        alignment=ft.MainAxisAlignment.CENTER,
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )
