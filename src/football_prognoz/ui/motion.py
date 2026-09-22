"""Block motion, branded cursor, and dark scroll panes for Flet 0.80."""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

import flet as ft

from football_prognoz.ui.theme import BG

__all__ = [
    "PAGE_CURSOR",
    "WAIT_CURSOR",
    "apply_motion",
    "hover_scale",
    "play_after",
    "scroll_pane",
    "with_cursor",
]

PAGE_CURSOR = ft.MouseCursor.PRECISE
WAIT_CURSOR = ft.MouseCursor.WAIT
_CLICK = ft.MouseCursor.CLICK


def hover_scale(event: ft.ControlEvent) -> None:
    """Grow a block slightly while the pointer is over it."""
    target = event.control
    if target is None:
        return
    hovering = event.data is True or str(event.data).lower() == "true"
    target.scale = 1.02 if hovering else 1.0
    try:
        target.update()
    except Exception:  # noqa: BLE001 — unmounted hover during pane swap
        pass


def play_after(delay_s: float, callback: Callable[[], None]) -> None:
    """Run `callback` once, off the constructor path. Daemon timer — never blocks boot."""
    timer = threading.Timer(max(0.0, delay_s), callback)
    timer.daemon = True
    timer.start()


def apply_motion(control: ft.Container, *, interactive: bool = False) -> ft.Container:
    """Enable implicit fade/offset/scale on a card. Interactive cards also grow on hover."""
    control.animate_opacity = 320
    control.animate_offset = 320
    control.animate_scale = 180
    if interactive:
        control.on_hover = hover_scale
    return control


def with_cursor(
    content: ft.Control,
    cursor: ft.MouseCursor | None = None,
    *,
    interactive: bool = False,
) -> ft.Control:
    """Wrap a control so the pointer uses the branded or click cursor."""
    chosen = cursor if cursor is not None else (_CLICK if interactive else PAGE_CURSOR)
    return ft.GestureDetector(content=content, mouse_cursor=chosen)


def scroll_pane(
    controls: Iterable[ft.Control],
    *,
    spacing: int = 12,
) -> ft.Control:
    """Fill leftover pane space with theme BG instead of Material gray."""
    return ft.Container(
        content=ft.ListView(
            list(controls),
            expand=True,
            spacing=spacing,
            padding=0,
        ),
        expand=True,
        bgcolor=BG,
    )
