from __future__ import annotations

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

    def target() -> None:
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001 — surface any I/O error in the UI
            message = str(exc)

            def fail() -> None:
                on_err(message)
                page.update()

            _invoke(page, fail)
            return

        def ok() -> None:
            on_ok(result)
            page.update()

        _invoke(page, ok)

    runner = getattr(page, "run_thread", None)
    if callable(runner):
        runner(target)
    else:
        import threading

        threading.Thread(target=target, daemon=True).start()


def _invoke(page: ft.Page, callback: Callable[[], None]) -> None:
    caller = getattr(page, "call_from_thread", None)
    if callable(caller):
        caller(callback)
    else:
        callback()


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
