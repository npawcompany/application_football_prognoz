from __future__ import annotations

import asyncio
import threading

import flet as ft

from football_prognoz.ui.components.splash import splash_view
from football_prognoz.ui.runtime import hide_preloader, run_background, show_preloader
from football_prognoz.ui.theme import ACCENT, BG, FG


class _Handle:
    def __init__(self) -> None:
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True


class FakePage:
    """Minimal page: overlay list + run_task that only schedules."""

    def __init__(self) -> None:
        self.overlay: list = []
        self.controls: list = ["body-sentinel"]
        self.updates = 0
        self.scheduled: list = []

    def update(self) -> None:
        self.updates += 1

    def run_task(self, fn, *args, **kwargs):
        handle = _Handle()
        self.scheduled.append((fn, args, kwargs, handle))
        return handle


def test_show_preloader_uses_overlay_not_body() -> None:
    page = FakePage()
    show_preloader(page, "Загрузка лиг…")
    assert page.controls == ["body-sentinel"]
    assert len(page.overlay) == 1
    overlay = page.overlay[0]
    assert overlay.expand is True
    assert overlay.visible is True
    assert overlay.alignment == ft.Alignment.CENTER
    assert page.updates >= 1
    show_preloader(page, "Ещё секунда…")
    assert len(page.overlay) == 1
    assert overlay.content.controls[1].value == "Ещё секунда…"
    hide_preloader(page)
    assert overlay.visible is False


def test_run_background_does_not_call_work_synchronously() -> None:
    page = FakePage()
    called: list[int] = []

    def work() -> str:
        called.append(threading.get_ident())
        return "ok"

    results: list[str] = []
    run_background(page, work, results.append, lambda _e: None, message="Считаем…")
    assert called == []
    assert results == []
    assert len(page.overlay) == 1
    assert page.overlay[0].visible is True
    assert len(page.scheduled) == 1


def test_run_background_completes_via_to_thread() -> None:
    page = FakePage()
    worker_ident: list[int] = []

    def work() -> str:
        worker_ident.append(threading.get_ident())
        return "done"

    results: list[str] = []
    errors: list[str] = []
    run_background(page, work, results.append, errors.append)
    fn, args, kwargs, _handle = page.scheduled[0]
    asyncio.run(fn(*args, **kwargs))
    assert results == ["done"]
    assert errors == []
    assert worker_ident
    assert worker_ident[0] != threading.get_ident()
    assert page.overlay == [] or page.overlay[0].visible is False


def test_run_background_cancels_previous_task() -> None:
    page = FakePage()
    run_background(page, lambda: 1, lambda _r: None, lambda _e: None)
    first = page.scheduled[0][3]
    run_background(page, lambda: 2, lambda _r: None, lambda _e: None)
    assert first.cancelled is True
    assert len(page.scheduled) == 2


def test_run_background_keeps_previous_when_not_cancelled() -> None:
    page = FakePage()
    run_background(page, lambda: 1, lambda _r: None, lambda _e: None)
    first = page.scheduled[0][3]
    run_background(
        page,
        lambda: 2,
        lambda _r: None,
        lambda _e: None,
        cancel_previous=False,
    )
    assert first.cancelled is False
    assert len(page.scheduled) == 2


def test_run_background_fallback_thread_does_not_block_caller() -> None:
    class ThreadOnlyPage:
        def __init__(self) -> None:
            self.overlay: list = []
            self.updates = 0

        def update(self) -> None:
            self.updates += 1

    page = ThreadOnlyPage()

    started = threading.Event()
    release = threading.Event()
    results: list[int] = []

    def work() -> int:
        started.set()
        assert release.wait(timeout=2)
        return 7

    run_background(page, work, results.append, lambda _e: None)  # type: ignore[arg-type]
    assert started.wait(timeout=2)
    assert results == []
    release.set()
    for _ in range(50):
        if results:
            break
        threading.Event().wait(0.05)
    assert results == [7]


def test_splash_view_indeterminate_and_determinate() -> None:
    boot = splash_view("Лиги")
    assert boot.bgcolor == BG
    assert boot.alignment == ft.Alignment.CENTER
    column = boot.content
    title = column.controls[0]
    subtitle = column.controls[1]
    ring = column.controls[2]
    status = column.controls[3]
    assert title.value == "Football Prognoz"
    assert title.font_family == "Fira Code"
    assert title.color == FG
    assert subtitle.value == "Загрузка данных…"
    assert ring.value is None
    assert ring.color == ACCENT
    assert status.value == "Лиги"
    filled = splash_view("Матчи", fraction=0.4)
    assert filled.content.controls[2].value == 0.4
    overflow = splash_view("Матчи", fraction=1.5)
    assert overflow.content.controls[2].value is None
