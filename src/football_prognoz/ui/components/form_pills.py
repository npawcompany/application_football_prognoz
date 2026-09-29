"""W / D / L form chips extracted from the match-detail fact block."""

from __future__ import annotations

import flet as ft

from football_prognoz.ui.theme import ACCENT, AWAY, DRAW, FG, MUTED

_ON_PILL = "#0F172A"
_FORM_COLORS = {"W": ACCENT, "D": DRAW, "L": AWAY}


def form_pills(code: str) -> ft.Control:
    if not code or code == "—":
        return ft.Text("—", size=13, color=MUTED)
    chips: list[ft.Control] = []
    for char in code:
        color = _FORM_COLORS.get(char)
        if color is None:
            continue
        chips.append(
            ft.Container(
                content=ft.Text(
                    char,
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    color=_ON_PILL,
                ),
                bgcolor=color,
                width=22,
                height=22,
                border_radius=6,
                alignment=ft.Alignment.CENTER,
            )
        )
    return ft.Row(chips, spacing=4) if chips else ft.Text(code, size=13, color=FG)
