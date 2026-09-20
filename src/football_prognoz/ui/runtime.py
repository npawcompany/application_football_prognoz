from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import flet as ft


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
        content=ft.Text(text, color=ft.Colors.WHITE),
        bgcolor=ft.Colors.RED_700,
        padding=12,
        border_radius=8,
    )


def info_banner(text: str) -> ft.Control:
    return ft.Container(
        content=ft.Text(text),
        bgcolor=ft.Colors.BLUE_GREY_800,
        padding=12,
        border_radius=8,
    )


def disclaimer() -> ft.Control:
    return ft.Text(
        "Прогноз статистический и не является советом ставить деньги.",
        size=12,
        italic=True,
        color=ft.Colors.GREY_400,
    )
