from __future__ import annotations

import asyncio
import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from football_prognoz.ui.theme import AWAY, BG, CARD, DRAW, FG, MUTED, glass_border


@dataclass
class _PreloaderBits:
    overlay: ft.Container
    label: ft.Text


_PRELOADERS: weakref.WeakKeyDictionary[Any, _PreloaderBits] = weakref.WeakKeyDictionary()
_BG_TASKS: weakref.WeakKeyDictionary[Any, Any] = weakref.WeakKeyDictionary()
_DEBOUNCE: weakref.WeakKeyDictionary[Any, dict[str, Any]] = weakref.WeakKeyDictionary()
_ID_PRELOADERS: dict[int, _PreloaderBits] = {}
_ID_BG_TASKS: dict[int, Any] = {}
_ID_DEBOUNCE: dict[int, dict[str, Any]] = {}


def _map_get(store: weakref.WeakKeyDictionary, fallback: dict[int, Any], page: Any) -> Any:
    try:
        return store.get(page)
    except TypeError:
        return fallback.get(id(page))


def _map_set(
    store: weakref.WeakKeyDictionary,
    fallback: dict[int, Any],
    page: Any,
    value: Any,
) -> None:
    try:
        store[page] = value
    except TypeError:
        fallback[id(page)] = value


def show_preloader(page: ft.Page, message: str) -> None:
    """Show a full-window spinner in page.overlay without replacing page body."""
    bits = _map_get(_PRELOADERS, _ID_PRELOADERS, page)
    if bits is None:
        label = ft.Text(
            message,
            color=FG,
            size=14,
            text_align=ft.TextAlign.CENTER,
        )
        overlay = ft.Container(
            content=ft.Column(
                [
                    ft.ProgressRing(color="#22C55E", width=42, height=42),
                    label,
                ],
                spacing=12,
                tight=True,
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
            left=0,
            top=0,
            right=0,
            bottom=0,
            bgcolor=ft.Colors.with_opacity(0.72, BG),
            alignment=ft.Alignment.CENTER,
            visible=True,
        )
        bits = _PreloaderBits(overlay=overlay, label=label)
        _map_set(_PRELOADERS, _ID_PRELOADERS, page, bits)
        overlay_list = getattr(page, "overlay", None)
        if overlay_list is not None:
            overlay_list.append(overlay)
    else:
        bits.label.value = message
        bits.overlay.visible = True
        overlay_list = getattr(page, "overlay", None)
        if overlay_list is not None and bits.overlay not in overlay_list:
            overlay_list.append(bits.overlay)
    page.update()


def hide_preloader(page: ft.Page) -> None:
    bits = _map_get(_PRELOADERS, _ID_PRELOADERS, page)
    if bits is None:
        return
    bits.overlay.visible = False
    page.update()


def _cancel_handle(handle: Any) -> None:
    cancel = getattr(handle, "cancel", None)
    if not callable(cancel):
        return
    try:
        cancel()
    except Exception:  # noqa: BLE001 — best-effort cancel of a previous task
        pass


def _cancel_previous_task(page: ft.Page) -> None:
    previous = _map_get(_BG_TASKS, _ID_BG_TASKS, page)
    if previous is None:
        return
    _cancel_handle(previous)


def _finish_ok(page: ft.Page, on_ok: Callable[[Any], None], result: Any) -> None:
    hide_preloader(page)
    on_ok(result)
    page.update()


def _finish_err(page: ft.Page, on_err: Callable[[str], None], message: str) -> None:
    hide_preloader(page)
    on_err(message)
    page.update()


def run_background(
    page: ft.Page,
    work: Callable[[], Any],
    on_ok: Callable[[Any], None],
    on_err: Callable[[str], None],
    *,
    message: str | None = None,
    cancel_previous: bool = True,
) -> None:
    """Run blocking I/O off the UI thread, then apply results on the UI thread."""
    if message:
        show_preloader(page, message)

    if cancel_previous:
        _cancel_previous_task(page)

    async def task() -> None:
        try:
            result = await asyncio.to_thread(work)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — surface any I/O error in the UI
            _finish_err(page, on_err, str(exc))
            return
        _finish_ok(page, on_ok, result)

    runner = getattr(page, "run_task", None)
    if callable(runner):
        _map_set(_BG_TASKS, _ID_BG_TASKS, page, runner(task))
        return

    def target() -> None:
        try:
            result = work()
        except Exception as exc:  # noqa: BLE001
            _finish_err(page, on_err, str(exc))
            return
        _finish_ok(page, on_ok, result)

    thread_runner = getattr(page, "run_thread", None)
    if callable(thread_runner):
        _map_set(_BG_TASKS, _ID_BG_TASKS, page, thread_runner(target))
        return

    worker = threading.Thread(target=target, daemon=True)
    _map_set(_BG_TASKS, _ID_BG_TASKS, page, worker)
    worker.start()


def debounce(
    page: ft.Page,
    key: str,
    delay_s: float,
    callback: Callable[[], None],
) -> None:
    """Coalesce rapid events (window resize) into one delayed callback."""
    pending = _map_get(_DEBOUNCE, _ID_DEBOUNCE, page)
    if pending is None:
        pending = {}
        _map_set(_DEBOUNCE, _ID_DEBOUNCE, page, pending)
    previous = pending.get(key)
    if previous is not None:
        _cancel_handle(previous)

    async def task() -> None:
        try:
            await asyncio.sleep(delay_s)
        except asyncio.CancelledError:
            raise
        callback()
        page.update()

    runner = getattr(page, "run_task", None)
    if callable(runner):
        pending[key] = runner(task)
        return

    timer = threading.Timer(delay_s, callback)
    timer.daemon = True
    pending[key] = timer
    timer.start()


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
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
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
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
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
        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
        border_radius=16,
    )
