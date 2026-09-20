"""Compact search field plus optional filter chips. Russian copy comes from the caller."""

from __future__ import annotations

from collections.abc import Callable

import flet as ft

from football_prognoz.ui.theme import ACCENT, BORDER, FG, SURFACE, glass_border

_ON_ACCENT = "#0F172A"


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


def filter_bar(
    *,
    hint: str,
    value: str,
    on_change: Callable[[str], None],
    chips: list[tuple[str, bool, Callable[[], None]]] | None = None,
) -> ft.Control:
    field = ft.TextField(
        value=value,
        label=hint,
        hint_text=hint,
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
        expand=True,
        on_change=lambda e: on_change(e.control.value or ""),
    )
    body: list[ft.Control] = [ft.Row([field], spacing=0)]
    if chips:
        body.append(
            ft.Row(
                [_chip(label, selected, callback) for label, selected, callback in chips],
                spacing=6,
                run_spacing=6,
                wrap=True,
            )
        )
    return ft.Column(body, spacing=8, horizontal_alignment=ft.CrossAxisAlignment.STRETCH)
