from __future__ import annotations

import flet as ft

from football_prognoz.ui.motion import PAGE_CURSOR, apply_motion, hover_scale, with_cursor
from football_prognoz.ui.notify import notify_system, notify_user


class _Page:
    def __init__(self) -> None:
        self.dialogs: list[object] = []

    def show_dialog(self, dialog: object) -> None:
        self.dialogs.append(dialog)

    def pop_dialog(self) -> None:
        if self.dialogs:
            self.dialogs.pop()


def test_apply_motion_sets_animation_and_hover() -> None:
    box = apply_motion(ft.Container(content=ft.Text("x")), interactive=True)
    assert box.animate_opacity == 320
    assert box.animate_scale == 180
    assert box.on_hover is hover_scale
    wrapped = with_cursor(box, interactive=True)
    assert isinstance(wrapped, ft.GestureDetector)
    assert wrapped.mouse_cursor == ft.MouseCursor.CLICK
    page_wrap = with_cursor(box)
    assert page_wrap.mouse_cursor == PAGE_CURSOR


def test_hover_scale_grows_then_resets() -> None:
    box = ft.Container()
    event = type("Event", (), {"control": box, "data": True})()
    hover_scale(event)
    assert box.scale == 1.02
    event.data = False
    hover_scale(event)
    assert box.scale == 1.0


def test_notify_user_shows_snack_and_error_alert() -> None:
    page = _Page()
    notify_user(page, "Сохранено", kind="success")
    assert page.dialogs
    assert isinstance(page.dialogs[0], ft.SnackBar)
    notify_user(page, "Нет ключа", kind="error")
    assert any(isinstance(item, ft.AlertDialog) for item in page.dialogs)


def test_notify_system_skips_empty_and_can_be_monkeypatched(monkeypatch) -> None:
    assert notify_system("Football Prognoz", "") is False
    called: list[list[str]] = []

    def fake_run(args, **_kwargs):
        called.append(list(args))
        return type("Done", (), {"returncode": 0})()

    monkeypatch.setattr("football_prognoz.ui.notify.sys.platform", "darwin")
    monkeypatch.setattr("football_prognoz.ui.notify.subprocess.run", fake_run)
    assert notify_system("Football Prognoz", "Готово") is True
    assert called
    assert called[0][0] == "osascript"


def test_notify_user_mirrors_to_system_off_the_ui_thread(monkeypatch) -> None:
    import threading
    import time

    seen: list[tuple[str, str, bool]] = []
    ui_thread = threading.current_thread()

    def slow_notify(title: str, body: str) -> bool:
        time.sleep(0.2)  # osascript waiting for the macOS permission prompt
        seen.append((title, body, threading.current_thread() is ui_thread))
        return True

    monkeypatch.setattr("football_prognoz.ui.notify.notify_system", slow_notify)
    started = time.monotonic()
    notify_user(_Page(), "Кэш очищен.", kind="info", system=True)
    assert time.monotonic() - started < 0.1  # the handler returns at once
    for _ in range(100):
        if seen:
            break
        time.sleep(0.02)
    assert seen == [("Football Prognoz", "Кэш очищен.", False)]
