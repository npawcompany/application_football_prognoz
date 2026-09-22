"""In-app alerts (SnackBar / AlertDialog) and optional OS notifications."""

from __future__ import annotations

import shutil
import subprocess
import sys
from typing import Any

import flet as ft

from football_prognoz.ui.theme import ACCENT, AWAY, CARD, DRAW, FG, SURFACE

__all__ = ["notify_system", "notify_user"]

_KIND_BG = {
    "info": SURFACE,
    "success": ACCENT,
    "error": AWAY,
    "warning": DRAW,
}
_KIND_FG = {
    "info": FG,
    "success": "#0F172A",
    "error": FG,
    "warning": "#0F172A",
}


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def notify_system(title: str, body: str) -> bool:
    """Best-effort desktop notification. Never raises; no secrets in title/body."""
    title = title.strip() or "Football Prognoz"
    body = body.strip()
    if not body:
        return False
    try:
        if sys.platform == "darwin":
            script = (
                "display notification "
                f"{_applescript_string(body)} with title {_applescript_string(title)}"
            )
            subprocess.run(
                ["osascript", "-e", script],
                check=False,
                capture_output=True,
                timeout=5,
            )
            return True
        if sys.platform.startswith("linux") and shutil.which("notify-send"):
            subprocess.run(
                ["notify-send", title, body],
                check=False,
                capture_output=True,
                timeout=5,
            )
            return True
    except Exception:  # noqa: BLE001 — OS notify is optional
        return False
    return False


def notify_user(
    page: Any,
    message: str,
    *,
    kind: str = "info",
    title: str = "Football Prognoz",
    alert: bool = False,
    system: bool = False,
) -> None:
    """Show a snack (and optional dialog). Mirror to the OS when `system` is on."""
    text = (message or "").strip()
    if not text:
        return
    kind_key = kind if kind in _KIND_BG else "info"
    show = getattr(page, "show_dialog", None)
    snack = ft.SnackBar(
        content=ft.Text(text, color=_KIND_FG[kind_key], size=13),
        bgcolor=_KIND_BG[kind_key],
        behavior=ft.SnackBarBehavior.FLOATING,
        show_close_icon=True,
        duration=ft.Duration(milliseconds=4200),
    )
    if callable(show):
        show(snack)
        if alert or kind_key == "error":
            dialog = ft.AlertDialog(
                title=ft.Text("Ошибка" if kind_key == "error" else title, color=FG),
                content=ft.Text(text, color=FG, size=13),
                bgcolor=CARD,
                actions=[
                    ft.TextButton(
                        "Закрыть",
                        on_click=lambda _e: _dismiss(page),
                    )
                ],
            )
            show(dialog)
    if system:
        notify_system(title, text)


def _dismiss(page: Any) -> None:
    pop = getattr(page, "pop_dialog", None)
    if callable(pop):
        pop()
