from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import flet as ft

from football_prognoz.ui.theme import AWAY, CARD, DRAW, FG, MUTED, glass_border


def run_background(
    page: ft.Page,
    work: Callable[[], Any],
    on_ok: Callable[[Any], None],
    on_err: Callable[[str], None],
) -> None:
    """Run blocking I/O off the UI thread, then apply results on the UI thread."""

    async def task() -> None:
        try:
            result = await asyncio.to_thread(work)
        except Exception as exc:  # noqa: BLE001 — surface any I/O error in the UI
            on_err(str(exc))
            page.update()
            return
        on_ok(result)
        page.update()

    runner = getattr(page, "run_task", None)
    if callable(runner):
        runner(task)
        return

    def target() -> None:
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001
            on_err(str(exc))
            page.update()
            return
        on_ok(result)
        page.update()

    thread_runner = getattr(page, "run_thread", None)
    if callable(thread_runner):
        thread_runner(target)
    else:
        import threading

        threading.Thread(target=target, daemon=True).start()


def error_banner(text: str) -> ft.Control:
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.ERROR_OUTLINE, color=FG, size=16),
                ft.Text(text, color=FG, expand=True, size=13),
            ],
            spacing=8,
        ),
        bgcolor=AWAY,
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        border_radius=10,
        semantics_label=text,
    )


def info_banner(text: str, action_hint: str | None = None) -> ft.Control:
    lines = [ft.Text(text, color=FG, expand=True, size=13)]
    if action_hint:
        lines.append(ft.Text(action_hint, size=11, color=MUTED))
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.INFO_OUTLINE, color=DRAW, size=16),
                ft.Column(lines, spacing=2, expand=True),
            ],
            spacing=8,
        ),
        bgcolor=CARD,
        border=glass_border(),
        padding=ft.padding.symmetric(horizontal=10, vertical=8),
        border_radius=10,
    )


def disclaimer() -> ft.Control:
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.HELP_OUTLINE, size=14, color=MUTED),
                ft.Text(
                    "Прогноз статистический. Это не совет ставить деньги.",
                    size=11,
                    color=MUTED,
                    expand=True,
                ),
            ],
            spacing=6,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        ),
        bgcolor=ft.Colors.with_opacity(0.35, CARD),
        border=glass_border(),
        padding=ft.padding.symmetric(horizontal=10, vertical=6),
        border_radius=16,
    )
