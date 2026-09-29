from __future__ import annotations

import asyncio
import threading
import weakref
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import flet as ft

from football_prognoz.ui.theme import BG, CARD, DRAW, ERROR_BG, FG, MUTED, glass_border


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


def _task_slots(page: ft.Page) -> dict[str, Any]:
    slots = _map_get(_BG_TASKS, _ID_BG_TASKS, page)
    if slots is None:
        slots = {}
        _map_set(_BG_TASKS, _ID_BG_TASKS, page, slots)
    return slots


def _cancel_previous_task(page: ft.Page, key: str = "default") -> None:
    previous = _task_slots(page).pop(key, None)
    if previous is None:
        return
    _cancel_handle(previous)


def cancel_background(page: ft.Page, key: str) -> None:
    """Cancel the pending UI callback of a keyed background task (the thread may finish)."""
    _cancel_previous_task(page, key)


def is_mounted(control: Any) -> bool:
    """True when the control is on a page (Flet raises on `.page` otherwise)."""
    try:
        return getattr(control, "page", None) is not None
    except (RuntimeError, AssertionError):
        return False


def safe_update(*controls: Any) -> bool:
    """Update controls that are mounted; skip (return False) those that are not.

    Worker callbacks can arrive after the user switched screens, when the control is
    no longer on the page; Flet raises then, and the old code crashed the callback.
    """
    ok = True
    for control in controls:
        try:
            if not is_mounted(control):
                ok = False
                continue
            control.update()
        except (RuntimeError, AssertionError, AttributeError):
            ok = False
    return ok


def _finish_ok(page: ft.Page, on_ok: Callable[[Any], None], result: Any) -> None:
    hide_preloader(page)
    on_ok(result)
    page.update()


def _finish_err(page: ft.Page, on_err: Callable[[str], None], message: str) -> None:
    hide_preloader(page)
    on_err(message)
    page.update()


class Job:
    """One cancellable background job generation (AI analysis, calendar load).

    `start()` cancels the previous generation and returns a fresh token; results of
    an old token are stale and must be dropped (`is_current`).
    """

    def __init__(self) -> None:
        self.generation = 0
        self.cancel: threading.Event | None = None

    def start(self) -> tuple[int, threading.Event]:
        self.stop()
        self.generation += 1
        self.cancel = threading.Event()
        return self.generation, self.cancel

    def stop(self) -> None:
        if self.cancel is not None:
            self.cancel.set()
        self.cancel = None

    def is_current(self, generation: int) -> bool:
        return generation == self.generation and self.cancel is not None

    @property
    def running(self) -> bool:
        return self.cancel is not None and not self.cancel.is_set()

    def finish(self, generation: int) -> None:
        if generation == self.generation:
            self.cancel = None


def run_background(
    page: ft.Page,
    work: Callable[[], Any],
    on_ok: Callable[[Any], None],
    on_err: Callable[[str], None],
    *,
    message: str | None = None,
    cancel_previous: bool = True,
    key: str = "default",
) -> None:
    """Run blocking I/O off the UI thread, then apply results on the UI thread.

    `key` names the kind of task: a new task cancels only the pending callback of the
    previous task with the same key (calendar refresh does not kill a forecast).
    `message` shows the full-window preloader; use it only for short blocking actions.
    """
    if message:
        show_preloader(page, message)

    if cancel_previous:
        _cancel_previous_task(page, key)
    slots = _task_slots(page)

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
        slots[key] = runner(task)
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
        slots[key] = thread_runner(target)
        return

    worker = threading.Thread(target=target, daemon=True)
    slots[key] = worker
    worker.start()


def run_detached(
    page: ft.Page,
    work: Callable[[], Any],
    on_ok: Callable[[Any], None],
    on_err: Callable[[str], None],
) -> None:
    """Like run_background, but never cancelled by later background tasks.

    For long jobs (training-data collection) that must survive the user opening
    matches meanwhile. Cancellation is cooperative, via the job's own Event.
    """

    async def task() -> None:
        try:
            result = await asyncio.to_thread(work)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
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

    threading.Thread(target=target, daemon=True).start()


def post_to_ui(page: ft.Page, callback: Callable[[], None]) -> None:
    """Apply a UI change from a worker thread on the page's event loop."""
    runner = getattr(page, "run_task", None)
    if callable(runner):

        async def tick() -> None:
            callback()

        runner(tick)
        return
    callback()


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
                ft.Text(text, color=FG, size=13, max_lines=4),
            ],
            spacing=8,
            wrap=True,
        ),
        bgcolor=ERROR_BG,
        padding=ft.Padding.symmetric(horizontal=10, vertical=8),
        border_radius=10,
    )


def info_banner(text: str, action_hint: str | None = None) -> ft.Control:
    lines = [ft.Text(text, color=FG, size=13, max_lines=4)]
    if action_hint:
        lines.append(ft.Text(action_hint, size=11, color=MUTED, max_lines=2))
    return ft.Container(
        content=ft.Row(
            [
                ft.Icon(ft.Icons.INFO_OUTLINE, color=DRAW, size=16),
                ft.Column(lines, spacing=2),
            ],
            spacing=8,
            wrap=True,
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
